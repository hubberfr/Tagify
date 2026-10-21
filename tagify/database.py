"""
Tagify 数据库模块 — 连接管理、建表、查询
"""
import os
import sqlite3
import pandas as pd
from PIL import ImageFile

from tagify import config as cfg

ImageFile.LOAD_TRUNCATED_IMAGES = cfg._cfg["model"]["load_truncated_images"]


def get_conn():
    """获取数据库连接（路径运行时读取，支持设置热更新）"""
    conn = sqlite3.connect(cfg.DB_FILE)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_database():
    """初始化数据库：建表 + 索引 + 导入 tag_metadata"""
    conn = get_conn()
    cursor = conn.cursor()

    # 标签表
    cursor.execute('''CREATE TABLE IF NOT EXISTS tags
                      (
                          image_name TEXT,
                          tag        TEXT,
                          confidence REAL,
                          UNIQUE (image_name, tag)
                      )''')

    # 图片元数据表（新增 width/height/format 字段）
    cursor.execute('''CREATE TABLE IF NOT EXISTS image_metadata
                      (
                          image_name   TEXT PRIMARY KEY,
                          file_size    INTEGER,
                          process_time TEXT,
                          width        INTEGER DEFAULT 0,
                          height       INTEGER DEFAULT 0,
                          format       TEXT    DEFAULT ''
                      )''')

    # 标签元数据表（从 CSV 导入）
    cursor.execute('''CREATE TABLE IF NOT EXISTS tag_metadata
                      (
                          tag_id   INTEGER PRIMARY KEY,
                          name     TEXT UNIQUE NOT NULL,
                          category INTEGER NOT NULL
                      )''')

    # 索引
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tags_tag ON tags(tag)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tags_image ON tags(image_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tagmeta_cat ON tag_metadata(category)")

    # 兼容旧表：新增列
    try:
        cursor.execute("ALTER TABLE image_metadata ADD COLUMN width INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE image_metadata ADD COLUMN height INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE image_metadata ADD COLUMN format TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()

    # 首次启动：导入 CSV 到 tag_metadata
    _import_tag_metadata()


def _import_tag_metadata():
    """从 selected_tags.csv 导入标签元数据（仅首次）"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM tag_metadata")
    if cursor.fetchone()[0] > 0:
        conn.close()
        return

    if not os.path.exists(cfg.TAGS_CSV_PATH):
        print(f"警告: 未找到 {cfg.TAGS_CSV_PATH}，标签分类功能不可用")
        conn.close()
        return

    print("首次启动: 正在导入标签元数据...")
    df = pd.read_csv(cfg.TAGS_CSV_PATH)
    count = 0
    for _, row in df.iterrows():
        cursor.execute(
            "INSERT OR IGNORE INTO tag_metadata VALUES (?, ?, ?)",
            (int(row['tag_id']), row['name'], int(row['category']))
        )
        count += 1
    conn.commit()
    conn.close()
    print(f"标签元数据导入完成: {count} 条")


def search_tags_db(keyword):
    """搜索标签，返回 [(tag, count), ...]"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('''SELECT t.tag, COUNT(*) as count
                      FROM tags t
                      WHERE t.tag LIKE ?
                      GROUP BY t.tag
                      ORDER BY count DESC''', (f'%{keyword}%',))
    results = cursor.fetchall()
    conn.close()
    return results


def search_tags_prefix(prefix, limit=10):
    """前缀搜索标签（用于自动补全）"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('''SELECT DISTINCT t.tag, COUNT(*) as count
                      FROM tags t
                      WHERE t.tag LIKE ?
                      GROUP BY t.tag
                      ORDER BY count DESC
                      LIMIT ?''', (f'{prefix}%', limit))
    results = cursor.fetchall()
    conn.close()
    return results


def search_tags_by_category(category, keyword=None, limit=100):
    """按类别搜索标签（从完整目录 tag_metadata 检索，左连接出现次数）。
    返回 [(tag, count), ...]，count 可能为 0（该标签尚未出现在任何图片上）。
    评级类别 (9) 按 tag_id 降序排列，保证 general→sensitive→questionable→explicit 顺序。"""
    conn = get_conn()
    cursor = conn.cursor()
    like = "AND tm.name LIKE ?" if keyword else ""
    params = [category]
    if keyword:
        params.append(f"%{keyword}%")
    params.append(limit)
    # category 经调用方限定为整数白名单，无注入风险
    order_by = "tm.tag_id DESC" if category == 9 else "COUNT(t.tag) DESC"
    cursor.execute(f'''SELECT tm.name, COUNT(t.tag) AS cnt
                       FROM tag_metadata tm
                       LEFT JOIN tags t ON t.tag = tm.name
                       WHERE tm.category = ? {like}
                       GROUP BY tm.name
                       ORDER BY {order_by}, tm.name
                       LIMIT ?''', params)
    results = cursor.fetchall()
    conn.close()
    return results


def get_tag_category_map():
    """返回 {tag_name: category_int} 字典（从 DB 缓存）"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT name, category FROM tag_metadata")
    result = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()
    return result


def get_image_tags(image_name):
    """获取图片的标签列表，按置信度降序"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('''SELECT tag, confidence
                      FROM tags
                      WHERE image_name = ?
                      ORDER BY confidence DESC''', (image_name,))
    results = cursor.fetchall()
    conn.close()
    return results


def get_image_metadata(image_name):
    """获取单张图片的元数据"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('''SELECT file_size, process_time, width, height, format
                      FROM image_metadata
                      WHERE image_name = ?''', (image_name,))
    result = cursor.fetchone()
    conn.close()
    return result


# ── SFW 屏蔽辅助 ──────────────────────────────────────────
_RATING_TAGS = ('general', 'sensitive', 'questionable', 'explicit')


def _nsfw_images_subquery():
    """返回 SELECT 子查询：主评级（置信度最高的评级标签）非 general 的图片名。
    用于 sfw_only 开启时从任何图库列表中排除 R18 图片。"""
    return '''SELECT image_name FROM (
        SELECT image_name, tag,
               ROW_NUMBER() OVER (
                   PARTITION BY image_name ORDER BY confidence DESC, tag
               ) AS rn
        FROM tags
        WHERE tag IN ('general', 'sensitive', 'questionable', 'explicit')
    ) WHERE rn = 1 AND tag <> 'general' '''


def count_gallery_images():
    """统计图库图片总数（sfw_only 开启时排除主评级非 general 的图片）"""
    conn = get_conn()
    cursor = conn.cursor()
    if cfg.SFW_ONLY:
        cursor.execute(f'''SELECT COUNT(*) FROM image_metadata m
                           WHERE m.image_name NOT IN ({_nsfw_images_subquery()})''')
    else:
        cursor.execute("SELECT COUNT(*) FROM image_metadata")
    total = cursor.fetchone()[0]
    conn.close()
    return total


def count_tag_images(tag):
    """统计某标签下的图片数（sfw_only 开启时同样过滤）"""
    conn = get_conn()
    cursor = conn.cursor()
    if cfg.SFW_ONLY:
        cursor.execute(f'''SELECT COUNT(DISTINCT m.image_name)
                           FROM tags t
                           JOIN image_metadata m ON t.image_name = m.image_name
                           WHERE t.tag = ?
                             AND m.image_name NOT IN ({_nsfw_images_subquery()})''', (tag,))
    else:
        cursor.execute('''SELECT COUNT(DISTINCT m.image_name)
                          FROM tags t
                          JOIN image_metadata m ON t.image_name = m.image_name
                          WHERE t.tag = ?''', (tag,))
    total = cursor.fetchone()[0]
    conn.close()
    return total


def query_gallery_images(sort_by, sort_order, limit, offset):
    """查图库图片列表（sfw_only 开启时排除主评级非 general 的图片）"""
    sort_map = {
        'name': 'image_name',
        'size': 'file_size',
        'time': 'process_time',
    }
    col = sort_map.get(sort_by, 'process_time')
    order = 'DESC' if sort_order == 'DESC' else 'ASC'

    conn = get_conn()
    cursor = conn.cursor()
    if cfg.SFW_ONLY:
        cursor.execute(f'''SELECT m.image_name
                           FROM image_metadata m
                           WHERE m.image_name NOT IN ({_nsfw_images_subquery()})
                           ORDER BY {col} {order}
                           LIMIT ? OFFSET ?''', (limit, offset))
    else:
        cursor.execute(f'''SELECT image_name
                           FROM image_metadata
                           ORDER BY {col} {order}
                           LIMIT ? OFFSET ?''', (limit, offset))
    results = [row[0] for row in cursor.fetchall()]
    conn.close()
    return results


def query_tag_images(tag, sort_by, sort_order, limit, offset):
    """查某标签下的图片列表（sfw_only 开启时同样过滤）"""
    sort_map = {
        'name': 'm.image_name',
        'size': 'm.file_size',
        'time': 'm.process_time',
        'confidence': 't.confidence',
    }
    col = sort_map.get(sort_by, 'm.process_time')
    order = 'DESC' if sort_order == 'DESC' else 'ASC'

    conn = get_conn()
    cursor = conn.cursor()
    if cfg.SFW_ONLY:
        cursor.execute(f'''SELECT DISTINCT m.image_name
                           FROM tags t
                           JOIN image_metadata m ON t.image_name = m.image_name
                           WHERE t.tag = ?
                             AND m.image_name NOT IN ({_nsfw_images_subquery()})
                           ORDER BY {col} {order}
                           LIMIT ? OFFSET ?''', (tag, limit, offset))
    else:
        cursor.execute(f'''SELECT DISTINCT m.image_name
                           FROM tags t
                           JOIN image_metadata m ON t.image_name = m.image_name
                           WHERE t.tag = ?
                           ORDER BY {col} {order}
                           LIMIT ? OFFSET ?''', (tag, limit, offset))
    results = [row[0] for row in cursor.fetchall()]
    conn.close()
    return results


def insert_image_record(image_name, file_size, width, height, fmt, process_time):
    """插入或更新图片元数据"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM image_metadata WHERE image_name = ?", (image_name,))
    if cursor.fetchone():
        cursor.execute("DELETE FROM tags WHERE image_name = ?", (image_name,))
        cursor.execute("DELETE FROM image_metadata WHERE image_name = ?", (image_name,))

    cursor.execute('''INSERT INTO image_metadata
                      VALUES (?, ?, ?, ?, ?, ?)''',
                   (image_name, file_size, process_time, width, height, fmt))
    conn.commit()
    conn.close()


def insert_tags_batch(image_name, tag_confidences):
    """批量插入标签"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.executemany('''INSERT INTO tags
                          VALUES (?, ?, ?)''',
                       [(image_name, tag, round(conf, 5))
                        for tag, conf in tag_confidences])
    conn.commit()
    conn.close()


def check_favorite_status(image_name, favorite_tag):
    """检查图片是否已收藏"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM tags WHERE image_name = ? AND tag = ?",
                   (image_name, favorite_tag))
    result = cursor.fetchone()
    conn.close()
    return result is not None


def toggle_favorite_db(image_name, favorite_tag, current_status):
    """切换收藏状态"""
    conn = get_conn()
    cursor = conn.cursor()
    if current_status:
        cursor.execute("DELETE FROM tags WHERE image_name = ? AND tag = ?",
                       (image_name, favorite_tag))
    else:
        cursor.execute("INSERT OR REPLACE INTO tags VALUES (?, ?, ?)",
                       (image_name, favorite_tag, 1.0))
    conn.commit()
    conn.close()


def delete_image_from_db(image_name):
    """删除图片的数据库记录"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tags WHERE image_name = ?", (image_name,))
    cursor.execute("DELETE FROM image_metadata WHERE image_name = ?", (image_name,))
    conn.commit()
    conn.close()


def check_data_integrity():
    """检查数据库与文件系统的一致性，返回报告字符串"""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT image_name FROM image_metadata")
    db_files = set(row[0] for row in cursor.fetchall())
    conn.close()

    valid_extensions = ('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif')
    actual_files = {f for f in os.listdir(cfg.ARCHIVE_FOLDER)
                    if f.lower().endswith(valid_extensions)}

    db_only = db_files - actual_files
    actual_only = actual_files - db_files

    report = "数据完整性检查报告:\n\n"
    report += f"数据库记录数: {len(db_files)}\n"
    report += f"实际文件数: {len(actual_files)}\n\n"

    if db_only:
        report += f"⚠ 数据库中有但文件缺失: {len(db_only)} 个\n"
        for f in list(db_only)[:5]:
            report += f"  • {f}\n"
        if len(db_only) > 5:
            report += f"  • ... 还有 {len(db_only) - 5} 个\n"
        report += "\n"

    if actual_only:
        report += f"⚠ 文件存在但数据库无记录: {len(actual_only)} 个\n"
        for f in list(actual_only)[:5]:
            report += f"  • {f}\n"
        if len(actual_only) > 5:
            report += f"  • ... 还有 {len(actual_only) - 5} 个\n"
        report += "\n"

    if not db_only and not actual_only:
        report += "✓ 数据完整性良好，所有记录都匹配！"

    return report, bool(db_only or actual_only)
