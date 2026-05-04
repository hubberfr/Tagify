# app_config.json 配置说明

> 修改 `app_config.json` 后重启程序即可生效，无需改代码。
> 若文件缺失或格式错误，程序自动使用此处列出的默认值。

---

## paths — 文件路径

| 键 | 默认值 | 说明 |
|----|--------|------|
| `model_path` | `"model.safetensors"` | WD ViT v3 模型权重文件 |
| `config_path` | `"config.json"` | 模型架构配置（timm 用） |
| `tags_csv` | `"selected_tags.csv"` | Danbooru 标签列表（10862 个标签） |
| `input_folder` | `"input_image"` | 待处理图片的存放目录 |
| `archive_folder` | `"../deepdanbooru-v3-20211112-sgd-e28 (1)/gallery"` | 处理后图片归档目录（相对脚本所在位置） |
| `db_file` | `"image_tags.db"` | SQLite 数据库文件 |

---

## model — 模型与推理

| 键 | 默认值 | 说明 |
|----|--------|------|
| `image_size` | `[448, 448]` | 模型输入图片尺寸（宽, 高），不要修改 |
| `default_threshold` | `0.5` | predict() 方法的默认置信度阈值 |
| `process_threshold` | `0.05` | **批量处理时的最低阈值** — 只有置信度 > 此值的标签才会存入数据库。调大可减少标签数量，调小可获取更多细节标签 |
| `main_tag_threshold` | `0.5` | "主要标签"分界线 — 置信度 > 此值归为主要标签 |
| `detail_tag_min` | `0.05` | "详细标签"下限 — 勾选"显示更多标签"后显示的范围 |
| `valid_extensions` | `[".png", ".jpg", ".jpeg", ".webp"]` | 支持的图片格式 |
| `load_truncated_images` | `true` | 是否允许加载被截断的图片文件 |

### 阈值关系图
```
0.0  ────────────────────────────────────────── 1.0
      │←── 忽略 ──→│←── 详细标签(5-50%) ──→│←── 主要标签(>50%) ──→│
                   0.05                      0.5
              (detail_tag_min)        (main_tag_threshold)
```

---

## ui — 界面与显示

### 窗口布局
| 键 | 默认值 | 说明 |
|----|--------|------|
| `window_size` | `[1400, 800]` | 主窗口默认尺寸（宽, 高） |
| `panel_widths` | `[300, 700, 400]` | 左/中/右三栏初始宽度 |

### 缩略图
| 键 | 默认值 | 说明 |
|----|--------|------|
| `thumbnail_size` | `[150, 150]` | 缩略图最大尺寸（宽, 高） |
| `thumbnail_cache_max` | `500` | LRU 缓存最多缓存的缩略图数量 |
| `thumbnail_padding` | `20` | 缩略图之间的间距（像素） |
| `page_size` | `20` | 每页显示的图片数量 |
| `default_columns` | `4` | 默认每行图片数（窗口变宽会自动增加） |

### 标签搜索面板
| 键 | 默认值 | 说明 |
|----|--------|------|
| `search_entry_width` | `22` | 搜索框宽度（字符数） |
| `tag_button_width` | `280` | 搜索结果标签按钮宽度（像素） |

### 右侧标签详情面板
| 键 | 默认值 | 说明 |
|----|--------|------|
| `info_frame_width` | `380` | 图片信息/标签详情框架宽度 |
| `info_label_width` | `8` | 信息标签行（"名称:"等）的标签宽度 |
| `tag_tree_height` | `15` | 标签列表可见行数 |
| `tag_column_width` | `150` | 标签名列宽（像素） |
| `confidence_column_width` | `80` | 置信度列宽（像素） |
| `tree_row_height_main` | `25` | 主要标签行高 |
| `tree_row_height_detail` | `20` | 详细标签行高 |

### 原图查看
| 键 | 默认值 | 说明 |
|----|--------|------|
| `detail_image_max_size` | `[800, 800]` | 原图窗口最大显示尺寸 |
| `detail_window_ratio` | `0.8` | 原图窗口占屏幕比例（0~1） |

### 分页
| 键 | 默认值 | 说明 |
|----|--------|------|
| `pagination_frame_height` | `40` | 分页栏高度 |

### 颜色
| 键 | 默认值 | 说明 |
|----|--------|------|
| `colors.main_bg` | `"#f5f5f5"` | 主背景色（浅灰） |
| `colors.accent` | `"#c8ccd0"` | 悬停强调色 |
| `colors.detail_bg` | `"#fafafa"` | 详情面板背景色 |

---

## behavior — 行为设置

| 键 | 默认值 | 说明 |
|----|--------|------|
| `favorite_tag` | `"collect"` | 收藏功能使用的标签名 — 右键"收藏"会给图片打上此标签 |
| `default_sort` | `"time"` | 默认排序字段：`"time"` / `"name"` / `"size"` |
| `default_order` | `"DESC"` | 默认排序方向：`"DESC"` 降序 / `"ASC"` 升序 |
| `shutdown_timeout` | `3` | 关闭程序时等待处理线程的最长秒数 |
| `pagination_side` | `4` | 分页控件当前页两侧各显示几个页码 |

---

## 常见调整场景

| 想做什么 | 改哪个配置 |
|----------|-----------|
| 标签太多/太少 | `model.process_threshold` — 调大减少标签，调小增加标签 |
| 搜索结果太多 | `model.default_threshold` — 调大阈值 |
| 窗口太大/太小 | `ui.window_size` |
| 缩略图太大/太小 | `ui.thumbnail_size` |
| 右侧面板太窄 | `ui.panel_widths` 第三个值 |
| 更换图片存档位置 | `paths.archive_folder` |
| 更换收藏标签名 | `behavior.favorite_tag` |
| 默认按大小排序 | `behavior.default_sort` → `"size"` |
| 每页显示更多图 | `ui.page_size` |
