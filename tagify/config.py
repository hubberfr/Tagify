"""
Tagify 配置模块 — 加载 app_config.json 并导出所有常量
支持运行时重载与设置保存: reload_config() / update_settings() / reset_settings()

说明：所有导出常量在「模块顶层」静态赋值（便于 IDE 静态解析）；
热重载通过 importlib.reload 重新执行本模块顶层代码实现，无需复制常量表。
"""
import copy
import importlib
import json
import os
import re
import sys

# 项目根目录: tagify/config.py 的上上级 = 项目根
_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_CONFIG_PATH = os.path.join(_PROJECT_DIR, "app_config.json")

# ── 默认配置 ──────────────────────────────────────────────
_DEFAULTS = {
    "_comment": "Tagify v9.1 应用配置文件 — 可在网页「设置」面板中修改，保存后即时生效",
    "paths": {
        "model_path": "model.safetensors",
        "config_path": "config.json",
        "tags_csv": "selected_tags.csv",
        "input_folder": "input_image",
        "archive_folder": "gallery",
        "db_file": "image_tags.db"
    },
    "model": {
        "image_size": [448, 448],
        "default_threshold": 0.5,
        "process_threshold": 0.05,
        "main_tag_threshold": 0.5,
        "detail_tag_min": 0.05,
        "valid_extensions": [".png", ".jpg", ".jpeg", ".webp"],
        "load_truncated_images": True,
        "device": "auto"
    },
    "ui": {
        "window_size": [1400, 800],
        "panel_widths": [300, 700, 400],
        "thumbnail_size": [150, 150],
        "thumbnail_cache_max": 500,
        "page_size": 20,
        "default_columns": 4,
        "thumbnail_padding": 20,
        "search_entry_width": 22,
        "tag_button_width": 280,
        "tag_tree_height": 15,
        "tag_column_width": 150,
        "confidence_column_width": 80,
        "tree_row_height_main": 25,
        "tree_row_height_detail": 20,
        "detail_image_max_size": [800, 800],
        "detail_window_ratio": 0.8,
        "info_label_width": 8,
        "pagination_frame_height": 40,
        "info_frame_width": 380,
        "colors": {
            "bg_main": "#fafbfc",
            "bg_panel": "#ffffff",
            "bg_card": "#ffffff",
            "border_card": "#e8eaed",
            "border_card_hover": "#4285f4",
            "accent_primary": "#1a73e8",
            "accent_hover": "#1557b0",
            "text_primary": "#202124",
            "text_secondary": "#5f6368",
            "text_muted": "#9aa0a6",
            "tag_button_bg": "#e8f0fe",
            "tag_button_bg_hover": "#d2e3fc",
            "rating_general": "#34a853",
            "rating_sensitive": "#f9ab00",
            "rating_questionable": "#e8710a",
            "rating_explicit": "#ea4335",
            "char_count_accent": "#9334e6",
            "char_name_accent": "#188038",
            "separator": "#dadce0",
            "progress_bar": "#1a73e8",
            "scrollbar_bg": "#f1f3f4",
            "scrollbar_fg": "#c4c7c5"
        }
    },
    "behavior": {
        "favorite_tag": "collect",
        "default_sort": "time",
        "default_order": "DESC",
        "sfw_only": True,
        "shutdown_timeout": 3,
        "pagination_side": 4
    }
}

# ── 设置界面可编辑字段（"分组.字段" -> 校验器）──────────────
# ("float", lo, hi) | ("int", lo, hi) | ("intpair", lo, hi) | ("bool",)
# ("str", min_len, max_len) | ("enum", (选项...)) | ("relpath",)
SETTINGS_SCHEMA = {
    "model.default_threshold": ("float", 0.0, 1.0),
    "model.process_threshold": ("float", 0.0, 1.0),
    "model.main_tag_threshold": ("float", 0.0, 1.0),
    "model.detail_tag_min": ("float", 0.0, 1.0),
    "ui.page_size": ("int", 1, 200),
    "ui.thumbnail_size": ("intpair", 32, 1024),
    "behavior.favorite_tag": ("str", 1, 64),
    "behavior.default_sort": ("enum", ("time", "name", "size")),
    "behavior.default_order": ("enum", ("ASC", "DESC")),
    "behavior.sfw_only": ("bool",),
    "paths.input_folder": ("relpath",),
    "paths.archive_folder": ("relpath",),
}


def _load_config():
    """加载 app_config.json，缺失时使用内置默认值（深度合并）"""
    cfg = json.loads(json.dumps(_DEFAULTS))  # 深拷贝

    try:
        with open(APP_CONFIG_PATH, 'r', encoding='utf-8') as f:
            user_cfg = json.load(f)
        _deep_merge(cfg, user_cfg)
        print(f"已加载配置: {APP_CONFIG_PATH}")
    except FileNotFoundError:
        print(f"未找到 {APP_CONFIG_PATH}，使用默认配置")
    except json.JSONDecodeError as e:
        print(f"配置文件解析失败: {e}，使用默认配置")

    return cfg


def _deep_merge(base, override):
    """递归合并 override 到 base，保留 base 中 override 没有的键"""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


# ── 模块顶层加载：读取配置并静态导出全部常量 ──────────────
# （热重载 = importlib.reload 重新执行本段代码，见 _refresh()）
_cfg = _load_config()
_p = _cfg["paths"]
_m = _cfg["model"]
_u = _cfg["ui"]
_b = _cfg["behavior"]

# ── 路径 ──
MODEL_PATH = _p["model_path"]
CONFIG_PATH = _p["config_path"]
TAGS_CSV_PATH = _p["tags_csv"]
INPUT_FOLDER = _p["input_folder"]
DB_FILE = _p["db_file"]
# 归档目录始终基于脚本位置解析为绝对路径，运行目录无关
ARCHIVE_FOLDER = os.path.normpath(os.path.join(_PROJECT_DIR, _p["archive_folder"]))
os.makedirs(ARCHIVE_FOLDER, exist_ok=True)

# ── 模型 ──
IMAGE_SIZE = tuple(_m["image_size"])
DEFAULT_THRESHOLD = _m["default_threshold"]
PROCESS_THRESHOLD = _m["process_threshold"]
MAIN_TAG_THRESHOLD = _m["main_tag_threshold"]
DETAIL_TAG_MIN = _m["detail_tag_min"]
VALID_EXTENSIONS = tuple(_m["valid_extensions"])
# 推理设备: "auto"(自动检测) / "cuda"(强制 GPU) / "cpu"(强制 CPU，驱动异常时可避免死机)
DEVICE = _m.get("device", "auto")

# ── UI 常量 ──
WINDOW_SIZE = f"{_u['window_size'][0]}x{_u['window_size'][1]}"
PANEL_LEFT_W = _u["panel_widths"][0]
PANEL_CENTER_W = _u["panel_widths"][1]
PANEL_RIGHT_W = _u["panel_widths"][2]
THUMB_SIZE = tuple(_u["thumbnail_size"])
THUMB_CACHE_MAX = _u["thumbnail_cache_max"]
PAGE_SIZE = _u["page_size"]
DEFAULT_COLUMNS = _u["default_columns"]
THUMB_PADDING = _u["thumbnail_padding"]
SEARCH_ENTRY_W = _u["search_entry_width"]
TAG_BUTTON_W = _u["tag_button_width"]
TAG_TREE_HEIGHT = _u["tag_tree_height"]
TAG_COL_W = _u["tag_column_width"]
CONF_COL_W = _u["confidence_column_width"]
TREE_ROW_MAIN = _u["tree_row_height_main"]
TREE_ROW_DETAIL = _u["tree_row_height_detail"]
DETAIL_IMG_MAX = tuple(_u["detail_image_max_size"])
DETAIL_WIN_RATIO = _u["detail_window_ratio"]
INFO_LABEL_W = _u["info_label_width"]
PAGINATION_H = _u["pagination_frame_height"]
INFO_FRAME_W = _u["info_frame_width"]

# ── 颜色 ──
_colors = _u["colors"]
BG_MAIN = _colors["bg_main"]
BG_PANEL = _colors["bg_panel"]
BG_CARD = _colors["bg_card"]
BORDER_CARD = _colors["border_card"]
BORDER_CARD_HOVER = _colors["border_card_hover"]
ACCENT_PRIMARY = _colors["accent_primary"]
ACCENT_HOVER = _colors["accent_hover"]
TEXT_PRIMARY = _colors["text_primary"]
TEXT_SECONDARY = _colors["text_secondary"]
TEXT_MUTED = _colors["text_muted"]
TAG_BUTTON_BG = _colors["tag_button_bg"]
TAG_BUTTON_BG_HOVER = _colors["tag_button_bg_hover"]
RATING_GENERAL = _colors["rating_general"]
RATING_SENSITIVE = _colors["rating_sensitive"]
RATING_QUESTIONABLE = _colors["rating_questionable"]
RATING_EXPLICIT = _colors["rating_explicit"]
CHAR_COUNT_ACCENT = _colors["char_count_accent"]
CHAR_NAME_ACCENT = _colors["char_name_accent"]
SEPARATOR = _colors["separator"]
PROGRESS_BAR = _colors["progress_bar"]
SCROLLBAR_BG = _colors["scrollbar_bg"]
SCROLLBAR_FG = _colors["scrollbar_fg"]

# 兼容旧代码的别名
MAIN_COLOR = BG_MAIN
ACCENT_COLOR = _colors.get("accent", "#c8ccd0")
DETAIL_COLOR = _colors.get("detail_bg", "#fafafa")

# ── 行为 ──
FAVORITE_TAG = _b["favorite_tag"]
DEFAULT_SORT = _b["default_sort"]
DEFAULT_ORDER = _b["default_order"]
SHUTDOWN_TIMEOUT = _b["shutdown_timeout"]
PAGINATION_SIDE = _b["pagination_side"]
SFW_ONLY = _b["sfw_only"]

# ── 字体 ──
FONT_FAMILY = ('Segoe UI', '微软雅黑', 'TkDefaultFont')
FONT_TAG_MAIN = (FONT_FAMILY[0], 10)
FONT_TAG_DETAIL = (FONT_FAMILY[0], 9)
FONT_TAG_SEPARATOR = (FONT_FAMILY[0], 7)
FONT_CARD_NAME = (FONT_FAMILY[0], 8)
FONT_INFO = (FONT_FAMILY[0], 9)
FONT_BUTTON = (FONT_FAMILY[0], 9)
FONT_HEADING = (FONT_FAMILY[0], 11, 'bold')


# ── 公共 API ─────────────────────────────────────────────

def get_config_dict():
    """返回当前配置的深拷贝（供 API 返回给前端）"""
    return copy.deepcopy(_cfg)


def _refresh():
    """热重载：重新执行本模块顶层代码，刷新全部导出常量与 _cfg"""
    importlib.reload(sys.modules[__name__])


def reload_config():
    """从文件重新加载配置并刷新所有常量"""
    _refresh()
    return get_config_dict()


def _validate_field(key, value):
    """校验单个字段的最终值，返回错误字符串或 None"""
    rule = SETTINGS_SCHEMA.get(key)
    if rule is None:
        return None  # 非可编辑字段忽略
    kind = rule[0]
    if kind == "float":
        lo, hi = rule[1], rule[2]
        try:
            v = float(value)
        except (TypeError, ValueError):
            return f"「{key}」必须是数字"
        if not (lo <= v <= hi):
            return f"「{key}」必须在 {lo} ~ {hi} 之间"
    elif kind == "int":
        lo, hi = rule[1], rule[2]
        try:
            v = int(value)
        except (TypeError, ValueError):
            return f"「{key}」必须是整数"
        if not (lo <= v <= hi):
            return f"「{key}」必须在 {lo} ~ {hi} 之间"
    elif kind == "intpair":
        lo, hi = rule[1], rule[2]
        if (not isinstance(value, (list, tuple))) or len(value) != 2:
            return f"「{key}」必须是两个数字"
        try:
            a, b = int(value[0]), int(value[1])
        except (TypeError, ValueError):
            return f"「{key}」必须是两个整数"
        if not (lo <= a <= hi and lo <= b <= hi):
            return f"「{key}」各项必须在 {lo} ~ {hi} 之间"
    elif kind == "str":
        lo, hi = rule[1], rule[2]
        if not isinstance(value, str):
            return f"「{key}」必须是字符串"
        v = value.strip()
        if not (lo <= len(v) <= hi):
            return f"「{key}」长度必须在 {lo} ~ {hi} 之间"
    elif kind == "enum":
        if value not in rule[1]:
            return f"「{key}」必须是 {' / '.join(rule[1])} 之一"
    elif kind == "bool":
        if not isinstance(value, bool):
            return f"「{key}」必须是 true 或 false"
    elif kind == "relpath":
        if not isinstance(value, str):
            return f"「{key}」必须是字符串"
        v = value.strip().replace("\\", "/")
        if not v:
            return f"「{key}」不能为空"
        if v.startswith("/") or re.match(r"^[A-Za-z]:", v) or ".." in v.split("/"):
            return f"「{key}」必须是相对路径（不允许绝对路径或 ..）"
    return None


def _apply_patch(cfg, group, field, raw):
    """规范化并写入一个可编辑字段，返回错误字符串或 None"""
    key = f"{group}.{field}"
    rule = SETTINGS_SCHEMA.get(key)
    if rule is None:
        return None  # 不可编辑字段忽略
    kind = rule[0]
    try:
        if kind == "float":
            value = float(raw)
        elif kind == "int":
            value = int(raw)
        elif kind == "intpair":
            value = [int(raw[0]), int(raw[1])]
        elif kind == "str":
            value = str(raw).strip()
        elif kind == "enum":
            value = raw
        elif kind == "bool":
            if not isinstance(raw, bool):
                return f"「{key}」必须是 true 或 false"
            value = raw
        elif kind == "relpath":
            value = str(raw).strip().replace("\\", "/")
        else:
            return None
    except (TypeError, ValueError, IndexError):
        return f"「{key}」格式不正确"
    err = _validate_field(key, value)
    if err:
        return err
    cfg[group][field] = value
    return None


def update_settings(payload):
    """应用设置更新。payload: 分组字典（仅可编辑字段生效）。
    返回 (错误字符串或 None, 新配置 dict)"""
    if not isinstance(payload, dict):
        return "请求体必须是 JSON 对象", None

    new_cfg = copy.deepcopy(_cfg)
    errors = []
    for group, values in payload.items():
        if group not in new_cfg or not isinstance(values, dict):
            continue
        for field, raw in values.items():
            err = _apply_patch(new_cfg, group, field, raw)
            if err:
                errors.append(err)

    if errors:
        return "; ".join(errors), None

    # 阈值一致性检查
    m = new_cfg["model"]
    if m["detail_tag_min"] > m["main_tag_threshold"]:
        return "「详细标签下限」不能大于「主要标签阈值」", None

    # 写回文件并热重载生效
    _write_config(new_cfg)
    _refresh()
    print("配置已更新并保存:", APP_CONFIG_PATH)
    return None, get_config_dict()


def reset_settings():
    """恢复默认配置并写回文件，返回新配置 dict"""
    _write_config(copy.deepcopy(_DEFAULTS))
    _refresh()
    print("配置已恢复默认:", APP_CONFIG_PATH)
    return get_config_dict()


def _write_config(cfg):
    """写回配置文件（去除默认配置中不存在的残留键，保持文件整洁）"""
    clean = copy.deepcopy(cfg)
    _prune_unknown(clean, _DEFAULTS)
    with open(APP_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(clean, f, ensure_ascii=False, indent=2)


def _prune_unknown(cfg, defaults):
    """递归删除 cfg 中 defaults 不存在的键"""
    for key in list(cfg.keys()):
        if key not in defaults:
            del cfg[key]
        elif isinstance(cfg[key], dict) and isinstance(defaults[key], dict):
            _prune_unknown(cfg[key], defaults[key])
