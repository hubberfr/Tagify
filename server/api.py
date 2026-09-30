"""
Tagify FastAPI 路由
"""
import io
import os
import shutil
import threading
from datetime import datetime

from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

from tagify import config as cfg
from tagify.database import (
    search_tags_db, search_tags_prefix, search_tags_by_category,
    get_image_tags, get_image_metadata,
    count_gallery_images, count_tag_images,
    query_gallery_images, query_tag_images,
    insert_image_record, insert_tags_batch,
    check_favorite_status, toggle_favorite_db, delete_image_from_db,
    check_data_integrity, get_tag_category_map,
)
from tagify.tags import (
    get_display_name, get_color, tag_sort_key, get_category,
    CAT_RATING, CAT_CHARACTER,
)

# 类别关键词 -> tag_metadata.category（搜索 "rating" / "character" 时展示对应分类）
CATEGORY_KEYWORDS = {
    "rating": CAT_RATING,
    "character": CAT_CHARACTER,
}

# ── 应用工厂 ──────────────────────────────────────────────

def create_app(tagger=None):
    """创建并配置 FastAPI 应用"""
    app = FastAPI(title="Tagify", version="9.1")

    # 保存 tagger 引用
    app.state.tagger = tagger
    app.state.process_status = {"running": False, "progress": 0, "message": ""}

    # 静态文件
    static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
    os.makedirs(static_dir, exist_ok=True)
    app.mount("/static", StaticFiles(directory=static_dir, html=True), name="static")

    # 页面与静态资源禁用缓存，避免浏览器沿用旧版前端代码
    @app.middleware("http")
    async def no_cache_static(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static/") or request.url.path == "/":
            response.headers["Cache-Control"] = "no-cache"
        return response

    # ── 注册路由 ──
    _register_routes(app)

    return app


def _register_routes(app: FastAPI):

    # ── 根路由 ──
    @app.get("/")
    async def root():
        from fastapi.responses import FileResponse
        static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
        return FileResponse(os.path.join(static_dir, "index.html"))

    # ════════════════════════════════════════════════════
    #  配置（读取 / 保存 / 恢复默认，均即时生效）
    # ════════════════════════════════════════════════════

    @app.get("/api/config")
    async def get_config():
        return cfg.get_config_dict()

    @app.put("/api/config")
    async def update_config(payload: dict):
        if payload is None:
            raise HTTPException(400, "缺少配置数据")
        if not isinstance(payload, dict):
            raise HTTPException(400, "请求体必须是 JSON 对象")
        if payload.get("reset_defaults"):
            return cfg.reset_settings()
        err, new_config = cfg.update_settings(payload)
        if err:
            raise HTTPException(400, err)
        return new_config

    # ════════════════════════════════════════════════════
    #  标签搜索
    # ════════════════════════════════════════════════════

    @app.get("/api/tags/search")
    async def api_search_tags(q: str = Query(..., min_length=1)):
        query = q.strip()
        low = query.lower()
        results = None
        # 类别关键词：搜 "rating" 展示评级分类，搜 "character" 展示角色分类
        # 支持 "rating:xxx" / "character xxx" 形式过滤类别内标签
        for kw, cat in CATEGORY_KEYWORDS.items():
            if low == kw or low.startswith(kw + ":") or low.startswith(kw + " "):
                rest = query[len(kw):].lstrip(": ").strip()
                results = search_tags_by_category(cat, rest or None, limit=200)
                break
        if results is None:
            results = search_tags_db(query)
        return [
            {"tag": tag, "count": count, "color": get_color(tag),
             "display": get_display_name(tag), "category": get_category(tag)}
            for tag, count in results
        ]

    @app.get("/api/tags/suggest")
    async def api_suggest_tags(prefix: str = Query(..., min_length=1)):
        p = prefix.strip().lower()
        # 类别关键词（"rating" / "rating:xxx"）：返回该分类标签（用显示名，如 rating:general）
        for kw, cat in CATEGORY_KEYWORDS.items():
            if p == kw or p.startswith(kw + ":") or p.startswith(kw + " "):
                rest = p[len(kw):].lstrip(": ").strip()
                results = search_tags_by_category(cat, rest or None, limit=10)
                return [get_display_name(tag) for tag, _ in results]
        # 普通前缀搜索；若无匹配且输入是类别关键词前缀，则回退到类别建议
        results = search_tags_prefix(prefix, limit=10)
        if not results:
            for kw, cat in CATEGORY_KEYWORDS.items():
                if len(p) >= 2 and kw.startswith(p):
                    cat_results = search_tags_by_category(cat, None, limit=10)
                    if cat_results:
                        return [get_display_name(tag) for tag, _ in cat_results]
        return [tag for tag, _ in results]

    @app.get("/api/tags/categories")
    async def api_tag_categories():
        """返回标签类别映射，供前端着色"""
        return get_tag_category_map()

    # ════════════════════════════════════════════════════
    #  图片列表
    # ════════════════════════════════════════════════════

    @app.get("/api/images")
    async def api_list_images(
        tag: str = Query(None),
        page: int = Query(1, ge=1),
        sort: str = Query(None),
        order: str = Query(None),
    ):
        if sort is None:
            sort = cfg.DEFAULT_SORT
        if order is None:
            order = cfg.DEFAULT_ORDER
        if sort not in ("name", "size", "time", "confidence"):
            sort = cfg.DEFAULT_SORT
        if order not in ("ASC", "DESC"):
            order = cfg.DEFAULT_ORDER

        page_size = cfg.PAGE_SIZE
        if tag:
            total = count_tag_images(tag)
            images = query_tag_images(tag, sort, order, page_size, (page - 1) * page_size)
        else:
            total = count_gallery_images()
            images = query_gallery_images(sort, order, page_size, (page - 1) * page_size)

        total_pages = (total + page_size - 1) // page_size if total > 0 else 0

        return {
            "images": images,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "tag": tag,
        }

    # ════════════════════════════════════════════════════
    #  图片详情
    # ════════════════════════════════════════════════════

    @app.get("/api/images/{name}")
    async def api_image_detail(name: str):
        meta = get_image_metadata(name)
        if not meta:
            raise HTTPException(404, "图片不存在")

        file_size, process_time, width, height, fmt = meta
        all_tags = get_image_tags(name)

        # 按 评级>角色>一般 排序
        all_tags.sort(key=lambda x: tag_sort_key(x[0], x[1]))

        tags_data = []
        for tag_name, conf in all_tags:
            cat = get_category(tag_name)
            tags_data.append({
                "tag": tag_name,
                "display": get_display_name(tag_name),
                "confidence": round(conf, 4),
                "percent": f"{conf * 100:.2f}%",
                "color": get_color(tag_name),
                "category": cat,
                "is_rating": cat == CAT_RATING,
                "is_character": cat == CAT_CHARACTER,
            })

        is_fav = check_favorite_status(name, cfg.FAVORITE_TAG)

        return {
            "name": name,
            "file_size": file_size,
            "size_kb": f"{round(file_size / 1024)} KB" if file_size else "未知",
            "process_time": process_time[:19] if process_time and process_time != "未知" else "未知",
            "width": width or 0,
            "height": height or 0,
            "format": fmt or "",
            "tags": tags_data,
            "is_favorite": is_fav,
        }

    # ════════════════════════════════════════════════════
    #  图片文件服务
    # ════════════════════════════════════════════════════

    @app.get("/api/images/{name}/thumbnail")
    async def api_thumbnail(name: str):
        img_path = os.path.join(cfg.ARCHIVE_FOLDER, name)
        if not os.path.exists(img_path):
            raise HTTPException(404, "图片不存在")

        try:
            img = Image.open(img_path)
            # 如果图片有透明通道，转 RGB（白底）
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGBA')
                background = Image.new('RGBA', img.size, (255, 255, 255))
                img = Image.alpha_composite(background, img).convert('RGB')
            else:
                img = img.convert('RGB')
            img.thumbnail(cfg.THUMB_SIZE)
            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=85)
            buf.seek(0)
            return StreamingResponse(buf, media_type="image/jpeg")
        except Exception as e:
            raise HTTPException(500, f"缩略图生成失败: {str(e)}")

    @app.get("/gallery/{filename:path}")
    async def serve_gallery(filename: str):
        """直接服务原图文件（带路径穿越防护）"""
        archive_root = os.path.normcase(os.path.realpath(cfg.ARCHIVE_FOLDER))
        safe_path = os.path.normcase(os.path.realpath(
            os.path.join(cfg.ARCHIVE_FOLDER, filename)))
        # 安全检查：规范化后必须仍在归档目录内（防 .. 及同名前缀兄弟目录绕过）
        try:
            inside = os.path.commonpath([archive_root, safe_path]) == archive_root
        except ValueError:
            inside = False
        if not inside:
            raise HTTPException(403, "禁止访问")

        if not os.path.isfile(safe_path):
            raise HTTPException(404, "文件不存在")

        ext = os.path.splitext(filename)[1].lower()
        media_map = {
            '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
            '.webp': 'image/webp', '.gif': 'image/gif', '.bmp': 'image/bmp',
        }
        return FileResponse(safe_path, media_type=media_map.get(ext, 'image/jpeg'))

    # ════════════════════════════════════════════════════
    #  收藏
    # ════════════════════════════════════════════════════

    @app.post("/api/images/{name}/favorite")
    async def api_toggle_favorite(name: str):
        current = check_favorite_status(name, cfg.FAVORITE_TAG)
        try:
            toggle_favorite_db(name, cfg.FAVORITE_TAG, current)
            return {"favorite": not current}
        except Exception as e:
            raise HTTPException(500, str(e))

    # ════════════════════════════════════════════════════
    #  删除
    # ════════════════════════════════════════════════════

    @app.delete("/api/images/{name}")
    async def api_delete_image(name: str):
        img_path = os.path.join(cfg.ARCHIVE_FOLDER, name)
        try:
            if os.path.exists(img_path):
                os.remove(img_path)
            delete_image_from_db(name)
            return {"deleted": True}
        except Exception as e:
            raise HTTPException(500, str(e))

    # ════════════════════════════════════════════════════
    #  批量处理
    # ════════════════════════════════════════════════════

    @app.post("/api/process")
    async def api_start_process():
        if app.state.tagger is None:
            raise HTTPException(400, "模型未加载")

        if app.state.process_status["running"]:
            raise HTTPException(400, "正在处理中")

        if not os.path.exists(cfg.INPUT_FOLDER):
            raise HTTPException(400, "输入文件夹不存在")

        app.state.process_status = {"running": True, "progress": 0, "message": "开始处理..."}

        thread = threading.Thread(
            target=_process_images_thread,
            args=(app,),
            daemon=False
        )
        thread.start()
        return {"started": True}

    @app.get("/api/process/status")
    async def api_process_status():
        return app.state.process_status

    @app.post("/api/process/stop")
    async def api_stop_process():
        app.state.process_status["running"] = False
        return {"stopped": True}

    # ════════════════════════════════════════════════════
    #  数据完整性检查
    # ════════════════════════════════════════════════════

    @app.get("/api/check-integrity")
    async def api_check_integrity():
        try:
            report, has_issues = check_data_integrity()
            return {"report": report, "has_issues": has_issues}
        except Exception as e:
            raise HTTPException(500, str(e))


# ── 后台处理线程 ──────────────────────────────────────────

def _process_images_thread(app: FastAPI):
    """批量处理图片（后台线程）"""
    try:
        image_files = [f for f in os.listdir(cfg.INPUT_FOLDER)
                       if f.lower().endswith(cfg.VALID_EXTENSIONS)]
        total = len(image_files)

        renamed_count = 0
        failed_count = 0
        status = app.state.process_status

        for idx, filename in enumerate(image_files, 1):
            if not status["running"]:
                status["message"] = f"已取消，完成 {idx - 1}/{total}"
                return

            src_path = os.path.join(cfg.INPUT_FOLDER, filename)
            try:
                dest_path = os.path.join(cfg.ARCHIVE_FOLDER, filename)
                if os.path.exists(dest_path):
                    unique_name = _unique_filename(filename)
                    dest_path = os.path.join(cfg.ARCHIVE_FOLDER, unique_name)
                    final_filename = unique_name
                    renamed_count += 1
                else:
                    final_filename = filename

                img = Image.open(src_path).convert('RGB')
                w, h = img.size
                fmt = img.format or os.path.splitext(filename)[1].lstrip('.')

                tag_confidences = app.state.tagger.predict(img, threshold=cfg.PROCESS_THRESHOLD)

                insert_image_record(
                    final_filename, os.path.getsize(src_path),
                    w, h, fmt, datetime.now().isoformat()
                )
                insert_tags_batch(final_filename, tag_confidences)
                shutil.move(src_path, dest_path)

                pct = int(idx / total * 100)
                msg = f"处理中: {filename}"
                if final_filename != filename:
                    msg += f" -> {final_filename}"
                status["progress"] = pct
                status["message"] = msg

            except Exception as e:
                failed_count += 1
                print(f"处理失败: {filename} - {e}")

        status["progress"] = 100
        status["message"] = f"完成! {total} 张" + \
            (f", {renamed_count} 张重命名" if renamed_count else "") + \
            (f", {failed_count} 张失败" if failed_count else "")

    except Exception as e:
        status["message"] = f"错误: {e}"
    finally:
        status["running"] = False


def _unique_filename(filename):
    base_name, ext = os.path.splitext(filename)
    counter = 1
    while True:
        new_filename = f"{base_name}_{counter}{ext}"
        if not os.path.exists(os.path.join(cfg.ARCHIVE_FOLDER, new_filename)):
            return new_filename
        counter += 1
