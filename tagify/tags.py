"""
Tagify 标签分类模块 — 标签类别判定、显示名称、着色、排序
仅两类高亮: 评级标签 (category=9) + 角色名标签 (category=4)
"""
from tagify.database import get_tag_category_map
from tagify.config import (
    RATING_GENERAL, RATING_SENSITIVE, RATING_QUESTIONABLE, RATING_EXPLICIT,
    CHAR_NAME_ACCENT, TEXT_PRIMARY,
)

# ── 类别常量 ──
CAT_RATING = 9       # 评分标签: general/sensitive/questionable/explicit
CAT_CHARACTER = 4    # 命名角色标签
CAT_GENERAL = 0      # 一般标签

# 评分标签显示顺序
_RATING_ORDER = {'general': 0, 'sensitive': 1, 'questionable': 2, 'explicit': 3}

# 评分颜色映射
_RATING_COLORS = {
    'general':      RATING_GENERAL,
    'sensitive':    RATING_SENSITIVE,
    'questionable': RATING_QUESTIONABLE,
    'explicit':     RATING_EXPLICIT,
}

# 缓存：延迟加载
_tag_category_cache = None


def _ensure_cache():
    global _tag_category_cache
    if _tag_category_cache is None:
        _tag_category_cache = get_tag_category_map()


def get_category(tag_name):
    """返回标签类别: CAT_RATING / CAT_CHARACTER / CAT_GENERAL"""
    _ensure_cache()
    return _tag_category_cache.get(tag_name, CAT_GENERAL)


def get_display_name(tag_name):
    """评分标签返回 'rating:general' 格式，其余原样返回"""
    _ensure_cache()
    cat = _tag_category_cache.get(tag_name, CAT_GENERAL)
    if cat == CAT_RATING:
        clean = tag_name.replace('rating:', '')
        return f"rating:{clean}"
    return tag_name


def get_search_name(display_name):
    """从显示名称还原搜索用的原始标签名"""
    return display_name.replace('rating:', '').strip()


def get_color(tag_name):
    """评级标签返回对应颜色，角色名返回青绿色，其余返回默认色"""
    _ensure_cache()
    cat = _tag_category_cache.get(tag_name, CAT_GENERAL)
    if cat == CAT_RATING:
        return _RATING_COLORS.get(tag_name, TEXT_PRIMARY)
    if cat == CAT_CHARACTER:
        return CHAR_NAME_ACCENT
    return TEXT_PRIMARY


def tag_sort_key(tag_name, confidence):
    """排序键：评级 > 角色名 > 一般特征，每组内按置信度降序"""
    _ensure_cache()
    cat = _tag_category_cache.get(tag_name, CAT_GENERAL)
    if cat == CAT_RATING:
        base = _RATING_ORDER.get(tag_name, 99)
        return (0, base, -confidence)
    if cat == CAT_CHARACTER:
        return (1, 0, -confidence)
    return (2, 0, -confidence)
