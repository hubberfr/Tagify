"""
Tagify v8.1 — 图片标签管理系统
基于 WD ViT Tagger v3 深度学习模型，自动标注、搜索、浏览图片标签。

修复记录 (v8.1):
  - #1  get_canvas_windows() 使用 itemcget 替代 item，修复返回元组的 bug
  - #2  移除重复的 PIL import
  - #3  show_image_detail() 移除嵌套 mainloop()
  - #4  模型加载从模块级移到 App.__init__()，包裹异常处理
  - #5  thumbnail_cache 添加 LRU 上限 (500张)，防止内存无界增长
  - #6  process_images() 数据库连接从逐张开关改为全程复用单连接
  - #7  ARCHIVE_FOLDER 改用基于 __file__ 的绝对路径计算
  - #8  合并 _validate_image 与 get_thumbnail 中的重复图片打开
  - #9  show_original_image() 添加窗口去重，双击同张图不复开
  - #10 处理线程改为非 daemon，App 关闭时发送停止信号并等待线程结束
"""

import tkinter as tk
from io import BytesIO
from tkinter import ttk, messagebox
from PIL import Image, ImageTk, ImageFile, ImageDraw
import sqlite3
import os
import shutil
import threading
import numpy as np
from datetime import datetime
from collections import OrderedDict
import win32clipboard
import torch
import timm
import pandas as pd
import json
from safetensors.torch import load_file

# ── 应用配置加载 ──────────────────────────────────────────
APP_CONFIG_PATH = 'app_config.json'

def _load_config():
    """加载 app_config.json，缺失时使用内置默认值"""
    defaults = {
        "paths": {
            "model_path": "model.safetensors",
            "config_path": "config.json",
            "tags_csv": "selected_tags.csv",
            "input_folder": "input_image",
            "archive_folder": "../deepdanbooru-v3-20211112-sgd-e28 (1)/gallery",
            "db_file": "image_tags.db"
        },
        "model": {
            "image_size": [448, 448],
            "default_threshold": 0.5,
            "process_threshold": 0.05,
            "main_tag_threshold": 0.5,
            "detail_tag_min": 0.05,
            "valid_extensions": [".png", ".jpg", ".jpeg", ".webp"],
            "load_truncated_images": True
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
                "main_bg": "#f5f5f5",
                "accent": "#c8ccd0",
                "detail_bg": "#fafafa"
            }
        },
        "behavior": {
            "favorite_tag": "collect",
            "default_sort": "time",
            "default_order": "DESC",
            "shutdown_timeout": 3,
            "pagination_side": 4
        }
    }

    try:
        with open(APP_CONFIG_PATH, 'r', encoding='utf-8') as f:
            user_cfg = json.load(f)
        for section in user_cfg:
            if section in defaults and isinstance(user_cfg[section], dict):
                defaults[section].update(user_cfg[section])
        print(f"已加载配置: {APP_CONFIG_PATH}")
    except FileNotFoundError:
        print(f"未找到 {APP_CONFIG_PATH}，使用默认配置")
    except json.JSONDecodeError as e:
        print(f"配置文件解析失败: {e}，使用默认配置")

    return defaults

_cfg = _load_config()
_p = _cfg["paths"]
_m = _cfg["model"]
_u = _cfg["ui"]
_b = _cfg["behavior"]

# ── 路径 ──
MODEL_PATH   = _p["model_path"]
CONFIG_PATH  = _p["config_path"]
TAGS_CSV_PATH = _p["tags_csv"]
INPUT_FOLDER = _p["input_folder"]
DB_FILE      = _p["db_file"]

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ARCHIVE_FOLDER = os.path.normpath(os.path.join(SCRIPT_DIR, _p["archive_folder"]))
os.makedirs(ARCHIVE_FOLDER, exist_ok=True)

# ── 模型 ──
IMAGE_SIZE       = tuple(_m["image_size"])
DEFAULT_THRESHOLD = _m["default_threshold"]
PROCESS_THRESHOLD = _m["process_threshold"]
MAIN_TAG_THRESHOLD = _m["main_tag_threshold"]
DETAIL_TAG_MIN    = _m["detail_tag_min"]
VALID_EXTENSIONS  = tuple(_m["valid_extensions"])
ImageFile.LOAD_TRUNCATED_IMAGES = _m["load_truncated_images"]

# ── UI ──
WINDOW_SIZE      = f"{_u['window_size'][0]}x{_u['window_size'][1]}"
PANEL_LEFT_W     = _u["panel_widths"][0]
PANEL_CENTER_W   = _u["panel_widths"][1]
PANEL_RIGHT_W    = _u["panel_widths"][2]
THUMB_SIZE       = tuple(_u["thumbnail_size"])
THUMB_CACHE_MAX  = _u["thumbnail_cache_max"]
PAGE_SIZE        = _u["page_size"]
DEFAULT_COLUMNS  = _u["default_columns"]
THUMB_PADDING    = _u["thumbnail_padding"]
SEARCH_ENTRY_W   = _u["search_entry_width"]
TAG_BUTTON_W     = _u["tag_button_width"]
TAG_TREE_HEIGHT  = _u["tag_tree_height"]
TAG_COL_W        = _u["tag_column_width"]
CONF_COL_W       = _u["confidence_column_width"]
TREE_ROW_MAIN    = _u["tree_row_height_main"]
TREE_ROW_DETAIL  = _u["tree_row_height_detail"]
DETAIL_IMG_MAX   = tuple(_u["detail_image_max_size"])
DETAIL_WIN_RATIO = _u["detail_window_ratio"]
INFO_LABEL_W     = _u["info_label_width"]
PAGINATION_H     = _u["pagination_frame_height"]
INFO_FRAME_W     = _u["info_frame_width"]
MAIN_COLOR       = _u["colors"]["main_bg"]
ACCENT_COLOR     = _u["colors"]["accent"]
DETAIL_COLOR     = _u["colors"]["detail_bg"]

# ── 行为 ──
FAVORITE_TAG     = _b["favorite_tag"]
DEFAULT_SORT     = _b["default_sort"]
DEFAULT_ORDER    = _b["default_order"]
SHUTDOWN_TIMEOUT = _b["shutdown_timeout"]
PAGINATION_SIDE  = _b["pagination_side"]


# ── 模型封装 ──────────────────────────────────────────────
class WDTagger:
    """WD ViT Tagger v3 模型封装类"""

    def __init__(self, model_path=MODEL_PATH, config_path=CONFIG_PATH, csv_path=TAGS_CSV_PATH):
        print("正在初始化新模型...")

        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        print(f"使用设备: {self.device}")

        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)

        self.model = timm.create_model(
            self.config['architecture'],
            pretrained=False,
            num_classes=self.config['num_classes'],
            **self.config['model_args']
        )

        state_dict = load_file(model_path)
        self.model.load_state_dict(state_dict)
        self.model = self.model.to(self.device)
        self.model.eval()

        self.df = pd.read_csv(csv_path)
        self.tags = self.df['name'].tolist()

        print(f"模型加载成功！标签数量: {len(self.tags)}")

    def preprocess(self, image):
        """预处理图片"""
        image = image.resize(IMAGE_SIZE, Image.Resampling.BICUBIC)
        img_array = np.array(image).astype(np.float32) / 255.0

        mean = np.array([0.5, 0.5, 0.5], dtype=np.float32)
        std = np.array([0.5, 0.5, 0.5], dtype=np.float32)
        img_array = (img_array - mean) / std

        img_tensor = torch.from_numpy(img_array).permute(2, 0, 1)
        img_tensor = img_tensor.unsqueeze(0)
        return img_tensor.to(self.device)

    def predict(self, image, threshold=DEFAULT_THRESHOLD):
        """预测图片标签"""
        input_tensor = self.preprocess(image)

        with torch.no_grad():
            outputs = self.model(input_tensor)
            probs = torch.sigmoid(outputs).cpu().numpy()[0]

        tag_confidences = [(self.tags[i], float(prob))
                           for i, prob in enumerate(probs) if prob > threshold]
        return tag_confidences


# ── GUI 组件 ──────────────────────────────────────────────

class ThumbnailButton(tk.Frame):
    """自定义缩略图按钮"""

    def __init__(self, master, image, name, click_command, dblclick_command, context_menu_command):
        super().__init__(master, bg=MAIN_COLOR, padx=5, pady=5)
        self.click_command = click_command
        self.dblclick_command = dblclick_command
        self.context_menu_command = context_menu_command
        self.image_name = name

        self.img_label = tk.Label(self, image=image, bg=MAIN_COLOR)
        self.img_label.image = image
        self.img_label.pack()

        short_name = name[:18] + "..." if len(name) > 20 else name
        tk.Label(self, text=short_name, bg=MAIN_COLOR, fg="black", font=('微软雅黑', 8)).pack()

        self.img_label.bind("<Button-1>", self.on_click)
        self.img_label.bind("<Double-Button-1>", self.on_dblclick)
        self.img_label.bind("<Button-3>", self.on_right_click)
        self.bind("<Enter>", self.on_enter)
        self.bind("<Leave>", self.on_leave)

    def on_click(self, event):
        self.click_command()

    def on_dblclick(self, event):
        self.dblclick_command()

    def on_right_click(self, event):
        self.context_menu_command(self.image_name, event)

    def on_enter(self, event):
        self.config(bg=ACCENT_COLOR)
        self.img_label.config(bg=ACCENT_COLOR)

    def on_leave(self, event):
        self.config(bg=MAIN_COLOR)
        self.img_label.config(bg=MAIN_COLOR)


class Pagination(tk.Frame):
    """分页控件"""

    def __init__(self, master, total_pages, current_page, command):
        super().__init__(master, bg=MAIN_COLOR)
        self.command = command
        self.total_pages = total_pages
        self.current_page = current_page

        self.create_pagination_buttons()

    def create_pagination_buttons(self):
        for widget in self.winfo_children():
            widget.destroy()

        prev_btn = ttk.Button(self, text="◀", width=3,
                              command=lambda: self.command(max(1, self.current_page - 1)))
        prev_btn.pack(side=tk.LEFT, padx=2)

        page_range = self.get_page_range()

        for page in page_range:
            if page == "...":
                ttk.Label(self, text="...", width=3).pack(side=tk.LEFT, padx=2)
            else:
                btn_style = "primary.TButton" if page == self.current_page else "TButton"
                btn = ttk.Button(self, text=str(page), width=3, style=btn_style,
                                 command=lambda p=page: self.command(p))
                btn.pack(side=tk.LEFT, padx=2)

        next_btn = ttk.Button(self, text="▶", width=3,
                              command=lambda: self.command(min(self.total_pages, self.current_page + 1)))
        next_btn.pack(side=tk.LEFT, padx=2)

    def get_page_range(self):
        if self.total_pages <= 10:
            return range(1, self.total_pages + 1)

        visible_pages = []
        side_pages = PAGINATION_SIDE

        visible_pages.append(1)

        if self.current_page - side_pages > 2:
            visible_pages.append("...")
        elif self.current_page - side_pages == 2:
            visible_pages.append(2)

        left = max(2, self.current_page - side_pages)
        right = min(self.total_pages - 1, self.current_page + side_pages)
        visible_pages.extend(range(left, right + 1))

        if self.current_page + side_pages < self.total_pages - 1:
            visible_pages.append("...")
        elif self.current_page + side_pages == self.total_pages - 1:
            visible_pages.append(self.total_pages - 1)

        if self.total_pages > 1:
            visible_pages.append(self.total_pages)

        return visible_pages


# ── 主应用 ────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Tagify v8.1")
        self.geometry(WINDOW_SIZE)
        self.configure(bg=MAIN_COLOR)

        # ── 状态变量 ──
        self.current_page = 1
        self.page_size = PAGE_SIZE
        self.total_pages = 0
        self.current_tag = None
        self.selected_image = None
        self.view_mode = "tag"
        self.columns_per_row = DEFAULT_COLUMNS
        self.FAVORITE_TAG = FAVORITE_TAG
        self.sort_by = DEFAULT_SORT
        self.sort_order = DEFAULT_ORDER

        # LRU 缩略图缓存 (#5 修复)
        self.thumbnail_cache = OrderedDict()

        # 打开的原图窗口追踪 (#9 修复)
        self.detail_windows = {}

        # 线程停止信号 (#10 修复)
        self._stop_event = threading.Event()
        self._worker_thread = None

        # ── 加载模型 (#4 修复: 移到 __init__ 内并包裹异常处理) ──
        self.tagger = None
        try:
            print("正在加载模型...")
            self.tagger = WDTagger()
            print("模型加载完成！")
        except Exception as e:
            print(f"模型加载失败: {e}")
            self.after(100, lambda: messagebox.showwarning(
                "模型加载失败",
                f"无法加载标签模型:\n{e}\n\n"
                "请检查 model.safetensors、config.json、selected_tags.csv 是否存在。\n"
                "程序将以离线模式运行（无法处理新图片）。"
            ))

        self.init_ui()
        self.init_database()

        # 样式
        self.style = ttk.Style()
        self.style.configure("primary.TButton", foreground="black", background="#0078d4")
        self.style.map("primary.TButton", background=[('active', '#006cbd')])
        self.style.configure("Treeview", background=DETAIL_COLOR, fieldbackground=DETAIL_COLOR, foreground="black")
        self.style.configure("Treeview.Heading", background=ACCENT_COLOR, foreground="black")

        # 注册窗口关闭回调 (#10 修复)
        self.protocol("WM_DELETE_WINDOW", self._on_app_close)

    # ── 窗口关闭处理 (#10 修复) ──
    def _on_app_close(self):
        """优雅关闭：通知工作线程停止，等待最多 3 秒"""
        if self._worker_thread and self._worker_thread.is_alive():
            self._stop_event.set()
            self._worker_thread.join(timeout=SHUTDOWN_TIMEOUT)
        self.destroy()

    # ── UI 构建 ──
    def init_ui(self):
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, pady=10)

        left_toolbar = ttk.Frame(toolbar)
        left_toolbar.pack(side=tk.LEFT)

        self.process_btn = ttk.Button(left_toolbar, text="开始批量处理", command=self.start_processing)
        self.process_btn.pack(side=tk.LEFT, padx=5)

        ttk.Button(left_toolbar, text="显示图库",
                   command=self.show_gallery).pack(side=tk.LEFT, padx=5)

        ttk.Button(left_toolbar, text="检查数据完整性",
                   command=self.check_data_integrity).pack(side=tk.LEFT, padx=5)

        self.progress = ttk.Progressbar(toolbar, mode='determinate')
        self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)

        self.main_paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.main_paned.pack(fill=tk.BOTH, expand=True)

        self.left_panel = ttk.Frame(self.main_paned, width=PANEL_LEFT_W)
        self.build_left_panel(self.left_panel)
        self.main_paned.add(self.left_panel, weight=3)

        self.center_panel = ttk.Frame(self.main_paned, width=PANEL_CENTER_W)
        self.build_center_panel(self.center_panel)
        self.main_paned.add(self.center_panel, weight=7)

        self.right_panel = ttk.Frame(self.main_paned, width=PANEL_RIGHT_W)
        self.build_right_panel(self.right_panel)
        self.main_paned.add(self.right_panel, weight=4)

        self.center_panel.bind("<Configure>", self.on_center_panel_resize)

    def on_center_panel_resize(self, event):
        if event.width > 0:
            thumb_width = THUMB_SIZE[0] + THUMB_PADDING
            new_columns = max(1, event.width // thumb_width)
            if new_columns != self.columns_per_row:
                self.columns_per_row = new_columns
                if hasattr(self, 'grid_frame'):
                    self.load_images()

    def build_left_panel(self, parent):
        search_frame = ttk.Frame(parent)
        search_frame.pack(fill=tk.X, padx=10, pady=10)

        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=SEARCH_ENTRY_W)
        search_entry.pack(side=tk.LEFT, padx=5)
        search_entry.bind("<Return>", lambda e: self.search_tags())

        ttk.Button(search_frame, text="搜索", command=self.search_tags).pack(side=tk.LEFT)

        self.tag_canvas = tk.Canvas(parent, bg=MAIN_COLOR, highlightthickness=0)
        scroll = ttk.Scrollbar(parent, command=self.tag_canvas.yview)
        self.tag_canvas.configure(yscrollcommand=scroll.set)

        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tag_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def build_center_panel(self, parent):
        self.sort_frame = ttk.Frame(parent)
        self.sort_frame.pack(fill=tk.X, padx=10, pady=10)

        self.sort_buttons = {
            'name': ttk.Button(self.sort_frame, text="名称排序", command=lambda: self.toggle_sort('name')),
            'size': ttk.Button(self.sort_frame, text="大小排序", command=lambda: self.toggle_sort('size')),
            'time': ttk.Button(self.sort_frame, text="时间排序 ▲", command=lambda: self.toggle_sort('time'))
        }

        self.sort_buttons['name'].pack(side=tk.LEFT, padx=2)
        self.sort_buttons['size'].pack(side=tk.LEFT, padx=2)
        self.sort_buttons['time'].pack(side=tk.LEFT, padx=2)

        container = ttk.Frame(parent)
        container.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(container, bg=MAIN_COLOR, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.grid_frame = ttk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.grid_frame, anchor="nw")

        self.pagination_frame = ttk.Frame(parent, height=PAGINATION_H)
        self.pagination_frame.pack(fill=tk.X, pady=5)

        self.grid_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(-1 * (e.delta // 120), "units"))

    def build_right_panel(self, parent):
        info_frame = ttk.LabelFrame(parent, text="图片信息", width=INFO_FRAME_W)
        info_frame.pack(fill=tk.X, padx=10, pady=5)

        self.info_labels = {
            'name': self.create_info_row(info_frame, "名称:", 0),
            'size': self.create_info_row(info_frame, "大小:", 1),
            'time': self.create_info_row(info_frame, "处理时间:", 2)
        }

        control_frame = ttk.Frame(parent)
        control_frame.pack(fill=tk.X, padx=10, pady=2)

        self.show_details_var = tk.BooleanVar(value=False)
        self.show_details_cb = ttk.Checkbutton(
            control_frame,
            text="显示更多标签 (5%-50%)",
            variable=self.show_details_var,
            command=self.toggle_details_display
        )
        self.show_details_cb.pack(side=tk.LEFT)

        self.tag_count_label = ttk.Label(control_frame, text="", foreground="gray")
        self.tag_count_label.pack(side=tk.RIGHT, padx=5)

        tag_frame = ttk.LabelFrame(parent, text="标签详情", width=INFO_FRAME_W)
        tag_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.tag_tree = ttk.Treeview(tag_frame, columns=('tag', 'confidence'), show='headings', height=TAG_TREE_HEIGHT)
        self.tag_tree.heading('tag', text='标签')
        self.tag_tree.heading('confidence', text='置信度')
        self.tag_tree.column('tag', width=TAG_COL_W, anchor='w')
        self.tag_tree.column('confidence', width=CONF_COL_W, anchor='center')

        style = ttk.Style()
        style.configure("Main.Treeview", rowheight=TREE_ROW_MAIN)
        style.configure("Detail.Treeview", rowheight=TREE_ROW_DETAIL)

        scroll = ttk.Scrollbar(tag_frame, orient="vertical", command=self.tag_tree.yview)
        self.tag_tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tag_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.tag_tree.bind("<Button-3>", self.on_tag_right_click)
        self.current_all_tags = []

    def toggle_details_display(self):
        if self.selected_image:
            self.show_image_info(self.selected_image)

    def toggle_sort(self, field):
        if self.sort_by == field:
            self.sort_order = "DESC" if self.sort_order == "ASC" else "ASC"
        else:
            self.sort_by = field
            self.sort_order = "DESC"

        for btn in self.sort_buttons.values():
            btn.config(text=btn.cget('text').replace(' ▲', '').replace(' ▼', ''))

        arrow = " ▲" if self.sort_order == "ASC" else " ▼"
        self.sort_buttons[field].config(text=self.sort_buttons[field].cget('text') + arrow)

        self.current_page = 1
        self.load_images()

    def update_sort_buttons_state(self):
        for btn in self.sort_buttons.values():
            btn.config(state=tk.NORMAL)

        for btn in self.sort_buttons.values():
            btn.config(text=btn.cget('text').replace(' ▲', '').replace(' ▼', ''))
        arrow = " ▲" if self.sort_order == "ASC" else " ▼"
        self.sort_buttons[self.sort_by].config(text=self.sort_buttons[self.sort_by].cget('text') + arrow)

    def create_info_row(self, parent, label, row):
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=0, sticky="ew", padx=5, pady=2)
        ttk.Label(frame, text=label, width=INFO_LABEL_W, anchor="e").pack(side=tk.LEFT)
        value_label = ttk.Label(frame, text="", foreground="black")
        value_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        return value_label

    # ── 数据库 ──
    def init_database(self):
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS tags
                          (
                              image_name TEXT,
                              tag        TEXT,
                              confidence REAL,
                              UNIQUE (image_name, tag)
                          )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS image_metadata
                          (
                              image_name   TEXT PRIMARY KEY,
                              file_size    INTEGER,
                              process_time TEXT
                          )''')
        conn.commit()
        conn.close()

    # ── 标签搜索 ──
    def search_tags(self):
        keyword = self.search_var.get().strip()
        if not keyword:
            messagebox.showwarning("提示", "请输入搜索关键词")
            return

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('''SELECT tag, COUNT(*) as count
                          FROM tags
                          WHERE tag LIKE ?
                          GROUP BY tag
                          ORDER BY count DESC''', (f'%{keyword}%',))

        self.tag_canvas.delete("all")
        # #1 修复: 使用 itemcget 正确获取 window 对象
        for w in self.get_canvas_windows():
            if w is not None:
                w.destroy()

        ypos = 10
        for tag, count in cursor.fetchall():
            btn = ttk.Button(self.tag_canvas, text=f"{tag} ({count})", command=lambda t=tag: self.show_tag(t))
            self.tag_canvas.create_window((10, ypos), window=btn, anchor="nw", width=TAG_BUTTON_W)
            ypos += 35

        self.tag_canvas.configure(scrollregion=self.tag_canvas.bbox("all"))
        conn.close()

        if keyword == self.FAVORITE_TAG.lower():
            self.show_tag(self.FAVORITE_TAG)

    # #1 修复: 正确获取 Canvas 上的 window 组件
    def get_canvas_windows(self):
        """获取 Canvas 上所有嵌入的 widget 对象"""
        result = []
        for item_id in self.tag_canvas.find_all():
            if self.tag_canvas.type(item_id) == "window":
                w = self.tag_canvas.itemcget(item_id, "window")
                result.append(w)
        return result

    # ── 图片信息 / 原图预览 ──
    def show_image_info(self, image_name):
        self.selected_image = image_name
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        cursor.execute('''SELECT file_size, process_time
                          FROM image_metadata
                          WHERE image_name = ?''', (image_name,))
        result = cursor.fetchone()
        if result:
            file_size, process_time = result
        else:
            file_size, process_time = 0, "未知"

        self.info_labels['name'].config(text=image_name)
        self.info_labels['size'].config(text=f"{round(file_size / 1024)} KB")
        self.info_labels['time'].config(text=process_time[:19] if process_time != "未知" else "未知")

        cursor.execute('''SELECT tag, confidence
                          FROM tags
                          WHERE image_name = ?
                          ORDER BY confidence DESC''', (image_name,))
        all_tags = cursor.fetchall()

        main_tags = [(tag, conf) for tag, conf in all_tags if conf > MAIN_TAG_THRESHOLD]
        detail_tags = [(tag, conf) for tag, conf in all_tags if DETAIL_TAG_MIN < conf <= MAIN_TAG_THRESHOLD]
        self.current_all_tags = all_tags

        self.tag_count_label.config(
            text=f"主要: {len(main_tags)} | 更多: {len(detail_tags)}"
        )

        self.tag_tree.delete(*self.tag_tree.get_children())

        for tag, conf in main_tags:
            self.tag_tree.insert('', 'end',
                                 values=(tag, f"{conf * 100:.2f}%"),
                                 tags=('main',))

        if self.show_details_var.get() and detail_tags:
            self.tag_tree.insert('', 'end',
                                 values=("─" * 30, "─" * 8),
                                 tags=('separator',))
            for tag, conf in detail_tags:
                self.tag_tree.insert('', 'end',
                                     values=(f"  {tag}", f"{conf * 100:.2f}%"),
                                     tags=('detail',))

        self.tag_tree.tag_configure('main', foreground='black', font=('微软雅黑', 9))
        self.tag_tree.tag_configure('detail', foreground='gray', font=('微软雅黑', 8))
        self.tag_tree.tag_configure('separator', foreground='lightgray', font=('微软雅黑', 7))

        conn.close()

    def _on_detail_close(self, image_name):
        """原图窗口关闭回调 (#9 修复)"""
        if image_name in self.detail_windows:
            self.detail_windows[image_name].destroy()
            del self.detail_windows[image_name]

    # #9 修复: 窗口去重，同一图片不复开
    def show_original_image(self, image_name):
        """显示原图（去重: 同一图片只开一个窗口）"""
        if image_name in self.detail_windows:
            win = self.detail_windows[image_name]
            if win.winfo_exists():
                win.lift()
                win.focus_force()
                return
            else:
                del self.detail_windows[image_name]

        detail_win = tk.Toplevel(self)
        detail_win.title(image_name)
        self.detail_windows[image_name] = detail_win
        detail_win.protocol("WM_DELETE_WINDOW", lambda: self._on_detail_close(image_name))

        img_path = os.path.join(ARCHIVE_FOLDER, image_name)
        try:
            img = Image.open(img_path)
            self.current_image = img.copy()

            width, height = img.size
            screen_width = self.winfo_screenwidth()
            screen_height = self.winfo_screenheight()
            max_size = (int(screen_width * DETAIL_WIN_RATIO), int(screen_height * DETAIL_WIN_RATIO))

            if width > max_size[0] or height > max_size[1]:
                img.thumbnail(max_size)

            photo = ImageTk.PhotoImage(img)
            label = tk.Label(detail_win, image=photo)
            label.image = photo
            label.pack()

            label.bind("<Button-3>", lambda e: self.show_image_context_menu(e, img_path))

        except Exception as e:
            messagebox.showerror("错误", f"无法打开图片：{str(e)}")

    # ── 收藏 ──
    def check_favorite_status(self, image_name):
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('''SELECT 1
                          FROM tags
                          WHERE image_name = ?
                            AND tag = ?''',
                       (image_name, self.FAVORITE_TAG))
        result = cursor.fetchone()
        conn.close()
        return result is not None

    def toggle_favorite(self, image_name, current_status):
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()

            if current_status:
                cursor.execute('''DELETE
                                  FROM tags
                                  WHERE image_name = ?
                                    AND tag = ?''',
                               (image_name, self.FAVORITE_TAG))
            else:
                cursor.execute('''INSERT OR REPLACE INTO tags
                                  VALUES (?, ?, ?)''',
                               (image_name, self.FAVORITE_TAG, 1.0))

            conn.commit()

            if self.current_tag == self.FAVORITE_TAG:
                self.load_images()

        except Exception as e:
            messagebox.showerror("操作失败", str(e))
        finally:
            conn.close()

    # ── 右键菜单 ──
    def show_image_context_menu(self, event, img_path):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="复制图片", command=lambda: self.copy_image_to_clipboard(img_path))
        image_name = os.path.basename(img_path)
        is_favorited = self.check_favorite_status(image_name)
        menu.add_command(
            label="取消收藏" if is_favorited else "收藏图片",
            command=lambda: self.toggle_favorite(image_name, is_favorited)
        )
        menu.add_separator()
        menu.add_command(label="删除图片", command=lambda: self.delete_image(img_path))
        menu.post(event.x_root, event.y_root)

    def show_thumbnail_context_menu(self, image_name, event):
        img_path = os.path.join(ARCHIVE_FOLDER, image_name)
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="复制图片", command=lambda: self.copy_image_to_clipboard(img_path))
        is_favorited = self.check_favorite_status(image_name)
        menu.add_command(
            label="取消收藏" if is_favorited else "收藏图片",
            command=lambda: self.toggle_favorite(image_name, is_favorited)
        )
        menu.add_separator()
        menu.add_command(label="删除图片", command=lambda: self.delete_image(img_path))
        menu.post(event.x_root, event.y_root)

    def on_tag_right_click(self, event):
        item = self.tag_tree.identify_row(event.y)
        if item:
            self.tag_tree.selection_set(item)
            tag = self.tag_tree.item(item, "values")[0]
            menu = tk.Menu(self, tearoff=0)
            menu.add_command(label="复制标签", command=lambda: self.copy_tag_to_clipboard(tag))
            menu.post(event.x_root, event.y_root)

    def copy_tag_to_clipboard(self, tag):
        self.clipboard_clear()
        self.clipboard_append(tag)
        self.update()

    def copy_image_to_clipboard(self, img_path):
        try:
            with Image.open(img_path) as img:
                output = BytesIO()
                img.convert("RGB").save(output, "BMP")
                data = output.getvalue()[14:]
                output.close()

            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
            win32clipboard.CloseClipboard()

        except Exception as e:
            messagebox.showerror("复制失败", f"无法复制图片到剪贴板：{str(e)}")

    def delete_image(self, img_path):
        if not messagebox.askyesno("确认删除", "确定要永久删除这张图片吗？"):
            return

        try:
            image_name = os.path.basename(img_path)

            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM tags WHERE image_name = ?", (image_name,))
            cursor.execute("DELETE FROM image_metadata WHERE image_name = ?", (image_name,))
            conn.commit()
            conn.close()

            if os.path.exists(img_path):
                os.remove(img_path)

            if image_name in self.thumbnail_cache:
                del self.thumbnail_cache[image_name]

            self.load_images()
            messagebox.showinfo("删除成功", "图片已成功删除")

            # 清理已关闭的窗口引用 (#9 修复)
            for name in list(self.detail_windows.keys()):
                if not self.detail_windows[name].winfo_exists():
                    del self.detail_windows[name]

        except Exception as e:
            messagebox.showerror("删除失败", f"删除过程中发生错误：{str(e)}")

    # ── 视图模式 ──
    def show_tag(self, tag):
        self.view_mode = "tag"
        self.current_tag = tag
        self.current_page = 1
        self.update_sort_buttons_state()
        self.load_images()

    def show_gallery(self):
        self.view_mode = "gallery"
        self.current_tag = None
        self.current_page = 1
        self.update_sort_buttons_state()
        self.load_images()

    # ── 图片加载与缓存 ──
    # 排序字段映射（类常量，避免每次方法调用重复创建）
    _GALLERY_SORT = {
        'name': 'image_name',
        'size': 'file_size',
        'time': 'process_time',
    }
    _TAG_SORT = {
        'name': 'm.image_name',
        'size': 'm.file_size',
        'time': 'm.process_time',
        'confidence': 't.confidence',
    }

    def load_images(self):
        for widget in self.grid_frame.winfo_children():
            widget.destroy()

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        try:
            if self.view_mode == "gallery":
                count_query = "SELECT COUNT(*) FROM image_metadata"
                data_query = f'''
                    SELECT image_name
                    FROM image_metadata
                    ORDER BY {self._GALLERY_SORT[self.sort_by]} {self.sort_order}
                    LIMIT ? OFFSET ?
                '''
                cursor.execute(count_query)
                total = cursor.fetchone()[0]
            else:
                count_query = '''
                    SELECT COUNT(DISTINCT m.image_name)
                    FROM tags t
                        JOIN image_metadata m ON t.image_name = m.image_name
                    WHERE t.tag = ?
                '''
                cursor.execute(count_query, (self.current_tag,))
                total = cursor.fetchone()[0]

                data_query = f'''
                    SELECT DISTINCT m.image_name
                    FROM tags t
                    JOIN image_metadata m ON t.image_name = m.image_name
                    WHERE t.tag = ?
                    ORDER BY {self._TAG_SORT[self.sort_by]} {self.sort_order}
                    LIMIT ? OFFSET ?
                '''

            self.total_pages = (total + self.page_size - 1) // self.page_size
            offset = (self.current_page - 1) * self.page_size

            if self.view_mode == "gallery":
                cursor.execute(data_query, (self.page_size, offset))
            else:
                cursor.execute(data_query, (self.current_tag, self.page_size, offset))

            row, col = 0, 0
            valid_count = 0

            for idx, (image_name,) in enumerate(cursor.fetchall()):
                thumbnail = self.get_thumbnail(image_name)

                if thumbnail:
                    btn = ThumbnailButton(
                        self.grid_frame,
                        thumbnail,
                        image_name,
                        click_command=lambda n=image_name: self.show_image_info(n),
                        dblclick_command=lambda n=image_name: self.show_original_image(n),
                        context_menu_command=self.show_thumbnail_context_menu
                    )
                    btn.grid(row=row, column=col, padx=5, pady=5)

                    col += 1
                    valid_count += 1

                    if col >= self.columns_per_row:
                        col = 0
                        row += 1

            if valid_count == 0:
                message_text = "图库中没有图片" if self.view_mode == "gallery" \
                    else f"没有找到标签为 '{self.current_tag}' 的图片"
                tk.Label(self.grid_frame,
                         text=message_text,
                         bg=MAIN_COLOR, font=('微软雅黑', 12)).grid(
                    row=0, column=0, columnspan=self.columns_per_row, pady=50)

            self.update_pagination()

        finally:
            conn.close()

    def update_pagination(self):
        for widget in self.pagination_frame.winfo_children():
            widget.destroy()

        if self.total_pages > 0:
            pagination = Pagination(self.pagination_frame, self.total_pages,
                                    self.current_page, self.goto_page)
            pagination.pack()

    def goto_page(self, page):
        self.current_page = page
        self.load_images()

    # #5 + #8 修复: LRU 限制 + 合并验证打开
    def get_thumbnail(self, image_name):
        """获取缩略图（LRU 缓存 + 单次打开验证）"""
        # LRU: 如果已在缓存中，移到末尾（最近使用）
        if image_name in self.thumbnail_cache:
            self.thumbnail_cache.move_to_end(image_name)
            return self.thumbnail_cache[image_name]

        image_path = os.path.join(ARCHIVE_FOLDER, image_name)
        try:
            # 快速文件大小检查
            if os.path.getsize(image_path) == 0:
                raise ValueError("文件为空")

            # #8 修复: 只打开一次图片，同时完成验证和缩略图生成
            img = Image.open(image_path)
            img.thumbnail(THUMB_SIZE)
            thumbnail = ImageTk.PhotoImage(img)

        except Exception as e:
            print(f"缩略图生成错误: {image_name} - {str(e)}")
            thumbnail = self._get_error_thumbnail()

        # 缓存
        self.thumbnail_cache[image_name] = thumbnail

        # #5 修复: LRU 逐出最旧条目
        while len(self.thumbnail_cache) > THUMB_CACHE_MAX:
            self.thumbnail_cache.popitem(last=False)

        return thumbnail

    def _get_error_thumbnail(self):
        img = Image.new('RGB', THUMB_SIZE, color='red')
        draw = ImageDraw.Draw(img)
        draw.text((10, 10), "ERR", fill='white')
        return ImageTk.PhotoImage(img)

    # #3 修复: 移除嵌套 mainloop（此方法当前未被调用，保留作备用）
    def show_image_detail(self, image_name):
        """备用图片详情窗口（供外部调用）"""
        detail_win = tk.Toplevel(self)
        detail_win.title(image_name)

        img = Image.open(os.path.join(ARCHIVE_FOLDER, image_name))
        img.thumbnail(DETAIL_IMG_MAX)
        photo = ImageTk.PhotoImage(img)
        tk.Label(detail_win, image=photo).pack()

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('''SELECT tag, confidence
                          FROM tags
                          WHERE image_name = ?
                          ORDER BY confidence DESC''', (image_name,))

        tree = ttk.Treeview(detail_win, columns=('tag', 'confidence'), show='headings')
        tree.heading('tag', text='标签')
        tree.heading('confidence', text='置信度')
        tree.column('tag', width=TAG_COL_W)
        tree.column('confidence', width=CONF_COL_W)

        for tag, conf in cursor.fetchall():
            tree.insert('', 'end', values=(tag, f"{conf * 100:.2f}%"))

        tree.pack(fill=tk.BOTH, expand=True)
        conn.close()
        # 不调用 mainloop()，子窗口由主循环驱动

    # ── 批量处理 (#6, #10 修复) ──
    def start_processing(self):
        # #4 修复: 模型未加载时的检查
        if self.tagger is None:
            messagebox.showerror("错误",
                                 "标签模型未加载，无法处理图片。\n"
                                 "请检查 model.safetensors 文件是否存在。")
            return

        if not os.path.exists(INPUT_FOLDER):
            messagebox.showerror("错误", f"输入文件夹 {INPUT_FOLDER} 不存在")
            return

        self.process_btn.config(state=tk.DISABLED)
        self.progress['value'] = 0

        # #10 修复: 非 daemon 线程 + 停止信号
        self._stop_event.clear()
        self._worker_thread = threading.Thread(target=self.process_images, daemon=False)
        self._worker_thread.start()

    def process_images(self):
        """处理图片（使用新模型）"""
        conn = None         # #6 修复: 循环外维持单一连接
        try:
            image_files = [f for f in os.listdir(INPUT_FOLDER) if f.lower().endswith(VALID_EXTENSIONS)]
            total = len(image_files)

            renamed_count = 0
            overwritten_count = 0

            # #6 修复: 整个循环共用一条数据库连接
            conn = sqlite3.connect(DB_FILE)

            for idx, filename in enumerate(image_files, 1):
                # #10 修复: 检查停止信号
                if self._stop_event.is_set():
                    self.after(0, lambda: messagebox.showinfo("已取消",
                                                               f"处理已中断，已完成 {idx - 1}/{total} 张"))
                    return

                src_path = os.path.join(INPUT_FOLDER, filename)

                try:
                    dest_path = os.path.join(ARCHIVE_FOLDER, filename)
                    if os.path.exists(dest_path):
                        unique_name = self._get_unique_filename(filename)
                        dest_path = os.path.join(ARCHIVE_FOLDER, unique_name)
                        final_filename = unique_name
                        renamed_count += 1
                        print(f"重名处理: {filename} -> {unique_name}")
                    else:
                        final_filename = filename

                    # 使用新模型预测
                    img = Image.open(src_path).convert('RGB')
                    tag_confidences = self.tagger.predict(img, threshold=PROCESS_THRESHOLD)

                    cursor = conn.cursor()

                    cursor.execute("SELECT 1 FROM image_metadata WHERE image_name = ?", (final_filename,))
                    if cursor.fetchone():
                        cursor.execute("DELETE FROM image_metadata WHERE image_name = ?", (final_filename,))
                        cursor.execute("DELETE FROM tags WHERE image_name = ?", (final_filename,))
                        overwritten_count += 1

                    cursor.execute('''INSERT INTO image_metadata
                                      VALUES (?, ?, ?)''',
                                   (final_filename, os.path.getsize(src_path),
                                    datetime.now().isoformat()))
                    cursor.executemany('''INSERT INTO tags
                                          VALUES (?, ?, ?)''',
                                       [(final_filename, tag, round(conf, 5))
                                        for tag, conf in tag_confidences])
                    conn.commit()

                    shutil.move(src_path, dest_path)

                    status_msg = f"处理中: {filename}"
                    if final_filename != filename:
                        status_msg += f" -> {final_filename}"

                    self.update_progress(idx / total * 100, status_msg)

                except Exception as e:
                    self.log_error(f"处理失败: {filename}\n{str(e)}")

            # 统计
            stats_msg = f"处理完成! 共 {total} 张图片"
            if renamed_count > 0:
                stats_msg += f", {renamed_count} 张因重名被重命名"
            if overwritten_count > 0:
                stats_msg += f", {overwritten_count} 张覆盖了旧记录"

            self.update_progress(100, "处理完成!")
            self.after(0, lambda: messagebox.showinfo("完成", stats_msg))
            self.search_tags()

        finally:
            # #6 修复: 确保连接关闭
            if conn:
                conn.close()
            self.after(0, lambda: self.process_btn.config(state=tk.NORMAL))

    def _get_unique_filename(self, filename):
        base_name, ext = os.path.splitext(filename)
        counter = 1
        while True:
            new_filename = f"{base_name}_{counter}{ext}"
            new_dest_path = os.path.join(ARCHIVE_FOLDER, new_filename)
            if not os.path.exists(new_dest_path):
                return new_filename
            counter += 1

    def update_progress(self, value, message):
        self.after(0, lambda: self.progress.config(value=value))
        self.after(0, lambda: self.title(f"Tagify - {message}"))

    def log_error(self, message):
        self.after(0, lambda: messagebox.showerror("处理错误", message))

    # ── 数据完整性检查 ──
    def check_data_integrity(self):
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()

            cursor.execute("SELECT image_name FROM image_metadata")
            db_files = set(row[0] for row in cursor.fetchall())

            actual_files = set(os.listdir(ARCHIVE_FOLDER))

            db_only = db_files - actual_files
            actual_only = actual_files - db_files

            report = f"数据完整性检查报告:\n\n"
            report += f"数据库记录数: {len(db_files)}\n"
            report += f"实际文件数: {len(actual_files)}\n\n"

            if db_only:
                report += f"⚠ 数据库中有但文件缺失: {len(db_only)} 个\n"
                for file in list(db_only)[:5]:
                    report += f"  • {file}\n"
                if len(db_only) > 5:
                    report += f"  • ... 还有 {len(db_only) - 5} 个\n"
                report += "\n"

            if actual_only:
                report += f"⚠ 文件存在但数据库无记录: {len(actual_only)} 个\n"
                for file in list(actual_only)[:5]:
                    report += f"  • {file}\n"
                if len(actual_only) > 5:
                    report += f"  • ... 还有 {len(actual_only) - 5} 个\n"
                report += "\n"

            if not db_only and not actual_only:
                report += "✓ 数据完整性良好，所有记录都匹配！"

            if db_only or actual_only:
                messagebox.showwarning("数据完整性检查", report)
            else:
                messagebox.showinfo("数据完整性检查", report)

            conn.close()

        except Exception as e:
            messagebox.showerror("检查失败", f"数据完整性检查失败: {str(e)}")


# ── 入口 ──
if __name__ == '__main__':
    app = App()
    app.mainloop()
