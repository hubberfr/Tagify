import tkinter as tk
from io import BytesIO
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
from PIL import Image, ImageTk, ImageFile, ImageDraw
import sqlite3
import os
import shutil
import threading
import numpy as np
from datetime import datetime
import win32clipboard
import torch
import timm
import pandas as pd
import json
from safetensors.torch import load_file

# 配置参数
MODEL_PATH = 'model.safetensors'  # 新模型的权重文件
CONFIG_PATH = 'config.json'  # 新模型的配置文件
TAGS_CSV_PATH = 'selected_tags.csv'  # 新模型的标签文件
INPUT_FOLDER = 'input_image'
ARCHIVE_FOLDER = '../deepdanbooru-v3-20211112-sgd-e28 (1)/gallery'
DB_FILE = 'image_tags.db'
THUMB_SIZE = (150, 150)
MAIN_COLOR = "#f5f5f5"
ACCENT_COLOR = "#c8ccd0"
DETAIL_COLOR = "#fafafa"
TEST_COLOR = "#ce1221"
ImageFile.LOAD_TRUNCATED_IMAGES = True  # 允许加载截断的图片

os.makedirs(ARCHIVE_FOLDER, exist_ok=True)


# ==================== 新模型加载 ====================
class WDTagger:
    """WD ViT Tagger v3 模型封装类"""

    def __init__(self, model_path=MODEL_PATH, config_path=CONFIG_PATH, csv_path=TAGS_CSV_PATH):
        print("正在初始化新模型...")

        # 1. 检查设备
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        print(f"使用设备: {self.device}")

        # 2. 加载配置
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)

        # 3. 创建模型
        self.model = timm.create_model(
            self.config['architecture'],
            pretrained=False,
            num_classes=self.config['num_classes'],
            **self.config['model_args']
        )

        # 4. 加载权重
        state_dict = load_file(model_path)
        self.model.load_state_dict(state_dict)
        self.model = self.model.to(self.device)
        self.model.eval()

        # 5. 加载标签
        self.df = pd.read_csv(csv_path)
        self.tags = self.df['name'].tolist()

        print(f"模型加载成功！标签数量: {len(self.tags)}")

    def preprocess(self, image):
        """预处理图片"""
        # 调整大小
        image = image.resize((448, 448), Image.BICUBIC)

        # 转换为numpy并归一化
        img_array = np.array(image).astype(np.float32) / 255.0

        # 标准化
        mean = np.array([0.5, 0.5, 0.5], dtype=np.float32)
        std = np.array([0.5, 0.5, 0.5], dtype=np.float32)
        img_array = (img_array - mean) / std

        # 转换为tensor并调整维度
        img_tensor = torch.from_numpy(img_array).permute(2, 0, 1)
        img_tensor = img_tensor.unsqueeze(0)

        return img_tensor.to(self.device)

    def predict(self, image, threshold=0.5):
        """预测图片标签"""
        input_tensor = self.preprocess(image)

        with torch.no_grad():
            outputs = self.model(input_tensor)
            probs = torch.sigmoid(outputs).cpu().numpy()[0]

        # 筛选置信度大于阈值的标签
        tag_confidences = [(self.tags[i], float(prob))
                           for i, prob in enumerate(probs) if prob > threshold]

        return tag_confidences


# 初始化模型（全局变量）
print("正在加载模型...")
tagger = WDTagger()
print("模型加载完成！")

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

        # 事件绑定
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
        """生成分页按钮"""

        for widget in self.winfo_children():
            widget.destroy()

        # 添加上一页按钮
        prev_btn = ttk.Button(self, text="◀", width=3,
                              command=lambda: self.command(max(1, self.current_page - 1)))
        prev_btn.pack(side=tk.LEFT, padx=2)

        # 生成页码范围
        page_range = self.get_page_range()

        # 添加页码按钮
        for page in page_range:
            if page == "...":
                ttk.Label(self, text="...", width=3).pack(side=tk.LEFT, padx=2)
            else:
                btn_style = "primary.TButton" if page == self.current_page else "TButton"
                btn = ttk.Button(self, text=str(page), width=3, style=btn_style,
                                 command=lambda p=page: self.command(p))
                btn.pack(side=tk.LEFT, padx=2)

        # 添加下一页按钮
        next_btn = ttk.Button(self, text="▶", width=3,
                              command=lambda: self.command(min(self.total_pages, self.current_page + 1)))
        next_btn.pack(side=tk.LEFT, padx=2)

    def get_page_range(self):
        """生成页码范围"""
        if self.total_pages <= 10:
            return range(1, self.total_pages + 1)

        # 计算显示范围
        visible_pages = []
        side_pages = 4  # 当前页两侧显示的页数

        # 总是显示第一页
        visible_pages.append(1)

        # 计算左侧...
        if self.current_page - side_pages > 2:
            visible_pages.append("...")
        elif self.current_page - side_pages == 2:
            visible_pages.append(2)

        # 中间页数
        left = max(2, self.current_page - side_pages)
        right = min(self.total_pages - 1, self.current_page + side_pages)
        visible_pages.extend(range(left, right + 1))

        # 计算右侧...
        if self.current_page + side_pages < self.total_pages - 1:
            visible_pages.append("...")
        elif self.current_page + side_pages == self.total_pages - 1:
            visible_pages.append(self.total_pages - 1)

        # 总是显示最后一页
        if self.total_pages > 1:
            visible_pages.append(self.total_pages)

        return visible_pages



class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Tagify v8.0")  # 升级版本号，表示模型更新
        self.geometry("1400x800")
        self.configure(bg=MAIN_COLOR)

        # 初始化参数
        self.current_page = 1
        self.page_size = 20
        self.total_pages = 0
        self.current_tag = None
        self.selected_image = None
        self.thumbnail_cache = {}
        self.view_mode = "tag"
        self.columns_per_row = 4

        self.init_ui()
        self.init_database()
        self.FAVORITE_TAG = "collect"
        self.sort_by = "time"
        self.sort_order = "DESC"

        # 样式配置
        self.style = ttk.Style()
        self.style.configure("primary.TButton", foreground="black", background="#0078d4")
        self.style.map("primary.TButton", background=[('active', '#006cbd')])
        self.style.configure("Treeview", background=DETAIL_COLOR, fieldbackground=DETAIL_COLOR, foreground="black")
        self.style.configure("Treeview.Heading", background=ACCENT_COLOR, foreground="black")

    # ==================== 界面方法保持不变 ====================
    def init_ui(self):
        # 顶部工具栏
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, pady=10)

        # 左侧按钮组
        left_toolbar = ttk.Frame(toolbar)
        left_toolbar.pack(side=tk.LEFT)

        self.process_btn = ttk.Button(left_toolbar, text="开始批量处理", command=self.start_processing)
        self.process_btn.pack(side=tk.LEFT, padx=5)

        # 添加显示图库按钮
        ttk.Button(left_toolbar, text="显示图库",
                   command=self.show_gallery).pack(side=tk.LEFT, padx=5)

        # 添加检查按钮
        ttk.Button(left_toolbar, text="检查数据完整性",
                   command=self.check_data_integrity).pack(side=tk.LEFT, padx=5)

        # 中间进度条（占据剩余空间）
        self.progress = ttk.Progressbar(toolbar, mode='determinate')
        self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)

        # 主容器
        self.main_paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.main_paned.pack(fill=tk.BOTH, expand=True)

        # 左侧面板
        self.left_panel = ttk.Frame(self.main_paned, width=300)
        self.build_left_panel(self.left_panel)
        self.main_paned.add(self.left_panel, weight=3)

        # 中间面板
        self.center_panel = ttk.Frame(self.main_paned, width=700)
        self.build_center_panel(self.center_panel)
        self.main_paned.add(self.center_panel, weight=7)

        # 右侧面板
        self.right_panel = ttk.Frame(self.main_paned, width=400)
        self.build_right_panel(self.right_panel)
        self.main_paned.add(self.right_panel, weight=4)

        # 绑定面板大小变化事件
        self.center_panel.bind("<Configure>", self.on_center_panel_resize)

    def on_center_panel_resize(self, event):
        """中间面板大小变化时重新计算每行缩略图数量"""
        if event.width > 0:
            # 计算可容纳的列数（缩略图宽度 + 间距）
            thumb_width = THUMB_SIZE[0] + 20  # 缩略图宽度 + 左右间距
            new_columns = max(1, event.width // thumb_width)

            if new_columns != self.columns_per_row:
                self.columns_per_row = new_columns
                # 重新加载当前页以应用新的布局
                if hasattr(self, 'grid_frame'):
                    self.load_images()

    def build_left_panel(self, parent):
        """构建左侧搜索面板"""
        search_frame = ttk.Frame(parent)
        search_frame.pack(fill=tk.X, padx=10, pady=10)

        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=22)
        search_entry.pack(side=tk.LEFT, padx=5)
        search_entry.bind("<Return>", lambda e: self.search_tags())

        ttk.Button(search_frame, text="搜索", command=self.search_tags).pack(side=tk.LEFT)

        # 标签列表
        self.tag_canvas = tk.Canvas(parent, bg=MAIN_COLOR, highlightthickness=0)
        scroll = ttk.Scrollbar(parent, command=self.tag_canvas.yview)
        self.tag_canvas.configure(yscrollcommand=scroll.set)

        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tag_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def build_center_panel(self, parent):
        """构建中间图片区域"""

        # 排序工具栏
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

        # 滚动容器
        container = ttk.Frame(parent)
        container.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(container, bg=MAIN_COLOR, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.grid_frame = ttk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.grid_frame, anchor="nw")

        # 分页控件
        self.pagination_frame = ttk.Frame(parent, height=40)
        self.pagination_frame.pack(fill=tk.X, pady=5)

        # 绑定滚动事件
        self.grid_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(-1 * (e.delta // 120), "units"))

    def build_right_panel(self, parent):
        """构建右侧详细信息面板"""
        # 上部基本信息
        info_frame = ttk.LabelFrame(parent, text="图片信息", width=380)
        info_frame.pack(fill=tk.X, padx=10, pady=5)

        self.info_labels = {
            'name': self.create_info_row(info_frame, "名称:", 0),
            'size': self.create_info_row(info_frame, "大小:", 1),
            'time': self.create_info_row(info_frame, "处理时间:", 2)
        }

        # 添加显示详细标签的勾选框
        control_frame = ttk.Frame(parent)
        control_frame.pack(fill=tk.X, padx=10, pady=2)

        self.show_details_var = tk.BooleanVar(value=False)  # 默认不显示详细标签
        self.show_details_cb = ttk.Checkbutton(
            control_frame,
            text="显示更多标签 (5%-50%)",
            variable=self.show_details_var,
            command=self.toggle_details_display
        )
        self.show_details_cb.pack(side=tk.LEFT)

        # 添加标签计数显示
        self.tag_count_label = ttk.Label(control_frame, text="", foreground="gray")
        self.tag_count_label.pack(side=tk.RIGHT, padx=5)

        # 下部标签列表
        tag_frame = ttk.LabelFrame(parent, text="标签详情", width=380)
        tag_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.tag_tree = ttk.Treeview(tag_frame, columns=('tag', 'confidence'), show='headings', height=15)
        self.tag_tree.heading('tag', text='标签')
        self.tag_tree.heading('confidence', text='置信度')
        self.tag_tree.column('tag', width=150, anchor='w')
        self.tag_tree.column('confidence', width=80, anchor='center')

        # 设置标签样式
        style = ttk.Style()
        style.configure("Main.Treeview", rowheight=25)
        style.configure("Detail.Treeview", rowheight=20)

        # 添加滚动条
        scroll = ttk.Scrollbar(tag_frame, orient="vertical", command=self.tag_tree.yview)
        self.tag_tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tag_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 绑定右键菜单
        self.tag_tree.bind("<Button-3>", self.on_tag_right_click)

        # 存储当前图片的所有标签（包括详细标签）
        self.current_all_tags = []

    def toggle_details_display(self):
        """切换详细标签显示"""
        if self.selected_image:
            self.show_image_info(self.selected_image)

    def toggle_sort(self, field):
        """切换排序方式和顺序"""
        # 更新排序字段和顺序
        if self.sort_by == field:
            # 切换排序顺序
            self.sort_order = "DESC" if self.sort_order == "ASC" else "ASC"
        else:
            # 切换排序字段
            self.sort_by = field
            self.sort_order = "DESC"

        # 更新按钮显示
        for btn in self.sort_buttons.values():
            btn.config(text=btn.cget('text').replace(' ▲', '').replace(' ▼', ''))

        arrow = " ▲" if self.sort_order == "ASC" else " ▼"
        self.sort_buttons[field].config(text=self.sort_buttons[field].cget('text') + arrow)

        # 重新加载图片
        self.current_page = 1
        self.load_images()

    def update_sort_buttons_state(self):
        """更新排序按钮状态"""
        # 所有模式下都启用所有排序按钮
        for btn in self.sort_buttons.values():
            btn.config(state=tk.NORMAL)

        # 更新当前排序按钮的显示
        for btn in self.sort_buttons.values():
            btn.config(text=btn.cget('text').replace(' ▲', '').replace(' ▼', ''))
        arrow = " ▲" if self.sort_order == "ASC" else " ▼"
        self.sort_buttons[self.sort_by].config(text=self.sort_buttons[self.sort_by].cget('text') + arrow)

    def create_info_row(self, parent, label, row):
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=0, sticky="ew", padx=5, pady=2)

        ttk.Label(frame, text=label, width=8, anchor="e").pack(side=tk.LEFT)
        value_label = ttk.Label(frame, text="", foreground="black")
        value_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        return value_label

    def _on_frame_configure(self, event=None):
        """更新滚动区域"""
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _bind_mousewheel(self, event):
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_mousewheel(self, event):
        self.canvas.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event):
        """处理不同平台的滚轮事件"""
        if event.num == 4 or event.delta > 0:
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5 or event.delta < 0:
            self.canvas.yview_scroll(1, "units")

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

        # 修复清除Canvas的方式
        self.tag_canvas.delete("all")
        # 正确获取所有子组件
        for widget in self.get_canvas_windows():
            widget.destroy()

        ypos = 10
        for tag, count in cursor.fetchall():
            btn = ttk.Button(self.tag_canvas, text=f"{tag} ({count})", command=lambda t=tag: self.show_tag(t))
            self.tag_canvas.create_window((10, ypos), window=btn, anchor="nw", width=280)
            ypos += 35

        self.tag_canvas.configure(scrollregion=self.tag_canvas.bbox("all"))
        conn.close()

        # 自动匹配收藏标签
        if keyword == self.FAVORITE_TAG.lower():
            self.show_tag(self.FAVORITE_TAG)
            return

    def show_image_info(self, image_name):
        """显示图片详细信息（支持分层显示）"""
        self.selected_image = image_name
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        # 获取元数据
        cursor.execute('''SELECT file_size, process_time
                          FROM image_metadata
                          WHERE image_name = ?''', (image_name,))
        result = cursor.fetchone()
        if result:
            file_size, process_time = result
        else:
            file_size, process_time = 0, "未知"

        # 更新基本信息
        self.info_labels['name'].config(text=image_name)
        self.info_labels['size'].config(text=f"{round(file_size / 1024)} KB")
        self.info_labels['time'].config(text=process_time[:19] if process_time != "未知" else "未知")

        # 获取所有标签（不设阈值，获取全部）
        cursor.execute('''SELECT tag, confidence
                          FROM tags
                          WHERE image_name = ?
                          ORDER BY confidence DESC''', (image_name,))
        all_tags = cursor.fetchall()

        # 分类标签
        main_tags = [(tag, conf) for tag, conf in all_tags if conf > 0.5]
        detail_tags = [(tag, conf) for tag, conf in all_tags if 0.05 < conf <= 0.5]

        # 保存所有标签供后续使用
        self.current_all_tags = all_tags

        # 更新标签计数
        self.tag_count_label.config(
            text=f"主要: {len(main_tags)} | 更多: {len(detail_tags)}"
        )

        # 更新标签信息（根据勾选状态决定显示哪些）
        self.tag_tree.delete(*self.tag_tree.get_children())

        # 显示主要标签（>50%）
        for tag, conf in main_tags:
            item = self.tag_tree.insert('', 'end',
                                        values=(tag, f"{conf * 100:.2f}%"),
                                        tags=('main',))

        # 如果勾选了显示详细标签，则添加分隔线和详细标签
        if self.show_details_var.get() and detail_tags:
            # 添加一个分隔线（作为视觉分隔）
            self.tag_tree.insert('', 'end',
                                 values=("─" * 30, "─" * 8),
                                 tags=('separator',))

            # 显示详细标签（5%-50%）
            for tag, conf in detail_tags:
                self.tag_tree.insert('', 'end',
                                     values=(f"  {tag}", f"{conf * 100:.2f}%"),
                                     tags=('detail',))

        # 配置标签样式
        self.tag_tree.tag_configure('main',
                                    foreground='black',
                                    font=('微软雅黑', 9))
        self.tag_tree.tag_configure('detail',
                                    foreground='gray',
                                    font=('微软雅黑', 8))
        self.tag_tree.tag_configure('separator',
                                    foreground='lightgray',
                                    font=('微软雅黑', 7))

        conn.close()

    def show_original_image(self, image_name):
        """显示原图"""
        detail_win = tk.Toplevel(self)
        detail_win.title(image_name)

        img_path = os.path.join(ARCHIVE_FOLDER, image_name)
        try:
            img = Image.open(img_path)
            self.current_image = img.copy()  # 保存图片引用

            # 调整显示尺寸
            width, height = img.size
            screen_width = self.winfo_screenwidth()
            screen_height = self.winfo_screenheight()
            max_size = (int(screen_width * 0.8), int(screen_height * 0.8))

            if width > max_size[0] or height > max_size[1]:
                img.thumbnail(max_size)

            photo = ImageTk.PhotoImage(img)
            label = tk.Label(detail_win, image=photo)
            label.image = photo
            label.pack()

            # 绑定右键菜单
            label.bind("<Button-3>", lambda e: self.show_image_context_menu(e, img_path))

        except Exception as e:
            messagebox.showerror("错误", f"无法打开图片：{str(e)}")

    def check_favorite_status(self, image_name):
        """检查是否已收藏"""
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
        """切换收藏状态"""
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()

            if current_status:
                # 取消收藏
                cursor.execute('''DELETE
                                  FROM tags
                                  WHERE image_name = ?
                                    AND tag = ?''',
                               (image_name, self.FAVORITE_TAG))
            else:
                # 添加收藏
                cursor.execute('''INSERT OR REPLACE INTO tags 
                               VALUES (?, ?, ?)''',
                               (image_name, self.FAVORITE_TAG, 1.0))  # confidence固定为1.0

            conn.commit()

            # 如果当前正在查看收藏列表则刷新
            if self.current_tag == self.FAVORITE_TAG:
                self.load_images()

        except Exception as e:
            messagebox.showerror("操作失败", str(e))
        finally:
            conn.close()

    def show_image_context_menu(self, event, img_path):
        """显示图片右键菜单"""
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
        """显示缩略图右键菜单"""
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
        """标签树右键点击事件处理"""
        item = self.tag_tree.identify_row(event.y)
        if item:
            self.tag_tree.selection_set(item)
            tag = self.tag_tree.item(item, "values")[0]

            # 创建上下文菜单
            menu = tk.Menu(self, tearoff=0)
            menu.add_command(label="复制标签", command=lambda: self.copy_tag_to_clipboard(tag))
            menu.post(event.x_root, event.y_root)

    def copy_tag_to_clipboard(self, tag):
        """复制标签到剪贴板"""
        self.clipboard_clear()
        self.clipboard_append(tag)
        self.update()  # 确保剪贴板内容立即生效

    def copy_image_to_clipboard(self, img_path):
        """复制图片到剪贴板"""
        try:
            # 读取图片数据
            with Image.open(img_path) as img:
                output = BytesIO()
                img.convert("RGB").save(output, "BMP")
                data = output.getvalue()[14:]  # 去除BMP文件头
                output.close()

            # 写入剪贴板
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
            win32clipboard.CloseClipboard()

        except Exception as e:
            messagebox.showerror("复制失败", f"无法复制图片到剪贴板：{str(e)}")

    def delete_image(self, img_path):
        """删除图片及其数据库记录"""
        if not messagebox.askyesno("确认删除", "确定要永久删除这张图片吗？"):
            return

        try:
            image_name = os.path.basename(img_path)

            # 删除数据库记录
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM tags WHERE image_name = ?", (image_name,))
            cursor.execute("DELETE FROM image_metadata WHERE image_name = ?", (image_name,))
            conn.commit()
            conn.close()

            # 删除图片文件
            if os.path.exists(img_path):
                os.remove(img_path)

            # 清除缓存
            if image_name in self.thumbnail_cache:
                del self.thumbnail_cache[image_name]

            # 刷新界面
            self.load_images()
            messagebox.showinfo("删除成功", "图片已成功删除")

            # 关闭查看窗口（如果存在）
            for window in self.winfo_children():
                if isinstance(window, tk.Toplevel):
                    window.destroy()

        except Exception as e:
            messagebox.showerror("删除失败", f"删除过程中发生错误：{str(e)}")

    def get_canvas_windows(self):
        """获取Canvas上的所有窗口组件"""
        return [self.tag_canvas.item(widget, "window")
                for widget in self.tag_canvas.find_all()
                if self.tag_canvas.type(widget) == "window"]

    def show_tag(self, tag):
        """显示特定标签的图片"""
        self.view_mode = "tag"
        self.current_tag = tag
        self.current_page = 1
        self.update_sort_buttons_state()  # 更新排序按钮状态
        self.load_images()

    def show_gallery(self):
        """显示整个图库（时间倒序）"""
        self.view_mode = "gallery"
        self.current_tag = None
        self.current_page = 1
        self.update_sort_buttons_state()  # 更新排序按钮状态
        self.load_images()

    def load_images(self):
        """加载当前页图片"""
        for widget in self.grid_frame.winfo_children():
            widget.destroy()

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        try:
            if self.view_mode == "gallery":
                # 图库模式：显示所有图片，支持所有排序方式
                count_query = "SELECT COUNT(*) FROM image_metadata"

                # 构建排序映射
                sort_mapping = {
                    'name': 'image_name',
                    'size': 'file_size',
                    'time': 'process_time'
                }

                data_query = f'''
                    SELECT image_name 
                    FROM image_metadata 
                    ORDER BY {sort_mapping[self.sort_by]} {self.sort_order}
                    LIMIT ? OFFSET ?
                '''
                cursor.execute(count_query)
                total = cursor.fetchone()[0]
                self.total_pages = (total + self.page_size - 1) // self.page_size

                offset = (self.current_page - 1) * self.page_size
                cursor.execute(data_query, (self.page_size, offset))

            else:
                # 标签模式：原有逻辑
                sort_mapping = {
                    'name': 'm.image_name',
                    'size': 'm.file_size',
                    'time': 'm.process_time',
                    'confidence': 't.confidence'
                }

                count_query = '''
                              SELECT COUNT(DISTINCT m.image_name)
                              FROM tags t
                                       JOIN image_metadata m ON t.image_name = m.image_name
                              WHERE t.tag = ? \
                              '''
                cursor.execute(count_query, (self.current_tag,))
                total = cursor.fetchone()[0]
                self.total_pages = (total + self.page_size - 1) // self.page_size

                data_query = f'''
                    SELECT DISTINCT m.image_name 
                    FROM tags t
                    JOIN image_metadata m ON t.image_name = m.image_name
                    WHERE t.tag = ?
                    ORDER BY {sort_mapping[self.sort_by]} {self.sort_order}
                    LIMIT ? OFFSET ?
                '''
                offset = (self.current_page - 1) * self.page_size
                cursor.execute(data_query, (self.current_tag, self.page_size, offset))

            # 生成缩略图网格（保持不变）
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

            # 空状态提示（保持不变）
            if valid_count == 0:
                if self.view_mode == "gallery":
                    message_text = "图库中没有图片"
                else:
                    message_text = f"没有找到标签为 '{self.current_tag}' 的图片"

                tk.Label(self.grid_frame,
                         text=message_text,
                         bg=MAIN_COLOR, font=('微软雅黑', 12)).grid(row=0, column=0, columnspan=self.columns_per_row,
                                                                    pady=50)

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

    def get_thumbnail(self, image_name):
        if image_name in self.thumbnail_cache:
            return self.thumbnail_cache[image_name]

        image_path = os.path.join(ARCHIVE_FOLDER, image_name)
        try:
            # 先验证图片完整性
            if not self._validate_image(image_path):
                error_thumb = self._get_error_thumbnail()
                self.thumbnail_cache[image_name] = error_thumb
                return error_thumb

            img = Image.open(image_path)
            img.thumbnail(THUMB_SIZE)
            thumbnail = ImageTk.PhotoImage(img)
            self.thumbnail_cache[image_name] = thumbnail
            return thumbnail
        except Exception as e:
            print(f"缩略图生成错误: {image_name} - {str(e)}")
            error_thumb = self._get_error_thumbnail()
            self.thumbnail_cache[image_name] = error_thumb
            return error_thumb

    def _validate_image(self, image_path):
        """验证图片文件是否完整"""
        try:
            # 检查文件大小
            if os.path.getsize(image_path) == 0:
                return False

            # 尝试读取文件头
            with Image.open(image_path) as img:
                img.verify()  # 验证文件完整性
            return True
        except Exception as e:
            print(f"图片验证失败: {image_path} - {str(e)}")
            return False

    def _get_error_thumbnail(self):
        """生成错误占位缩略图"""
        img = Image.new('RGB', THUMB_SIZE, color='red')
        draw = ImageDraw.Draw(img)
        draw.text((10, 10), "ERR", fill='white')
        return ImageTk.PhotoImage(img)

    def show_image_detail(self, image_name):
        detail_win = tk.Toplevel(self)
        detail_win.title(image_name)

        img = Image.open(os.path.join(ARCHIVE_FOLDER, image_name))
        img.thumbnail((800, 800))
        photo = ImageTk.PhotoImage(img)
        tk.Label(detail_win, image=photo).pack()

        # 显示标签详情
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('''SELECT tag, confidence
                          FROM tags
                          WHERE image_name = ?
                          ORDER BY confidence DESC''', (image_name,))

        tree = ttk.Treeview(detail_win, columns=('tag', 'confidence'), show='headings')
        tree.heading('tag', text='标签')
        tree.heading('confidence', text='置信度')
        tree.column('tag', width=150)
        tree.column('confidence', width=100)

        for tag, conf in cursor.fetchall():
            tree.insert('', 'end', values=(tag, f"{conf * 100:.2f}%"))

        tree.pack(fill=tk.BOTH, expand=True)
        detail_win.mainloop()

    def start_processing(self):
        """开始处理（添加模型预热）"""
        if not os.path.exists(INPUT_FOLDER):
            messagebox.showerror("错误", f"输入文件夹 {INPUT_FOLDER} 不存在")
            return

        self.process_btn.config(state=tk.DISABLED)
        self.progress['value'] = 0
        threading.Thread(target=self.process_images, daemon=True).start()

    # ==================== 核心修改：process_images 方法 ====================
    def process_images(self):
        """处理图片（使用新模型）"""
        try:
            valid_ext = ('.png', '.jpg', '.jpeg', '.webp')
            image_files = [f for f in os.listdir(INPUT_FOLDER) if f.lower().endswith(valid_ext)]
            total = len(image_files)

            renamed_count = 0
            overwritten_count = 0

            for idx, filename in enumerate(image_files, 1):
                src_path = os.path.join(INPUT_FOLDER, filename)

                try:
                    # 检查目标文件是否已存在
                    dest_path = os.path.join(ARCHIVE_FOLDER, filename)
                    if os.path.exists(dest_path):
                        # 生成唯一文件名
                        unique_name = self._get_unique_filename(filename)
                        dest_path = os.path.join(ARCHIVE_FOLDER, unique_name)
                        final_filename = unique_name
                        renamed_count += 1
                        print(f"重名处理: {filename} -> {unique_name}")
                    else:
                        final_filename = filename

                    # 使用新模型预测
                    img = Image.open(src_path).convert('RGB')
                    tag_confidences = tagger.predict(img, threshold=0.05)

                    conn = sqlite3.connect(DB_FILE)
                    cursor = conn.cursor()

                    # 检查数据库是否已存在同名记录
                    cursor.execute("SELECT 1 FROM image_metadata WHERE image_name = ?", (final_filename,))
                    if cursor.fetchone():
                        # 如果数据库已存在，先删除旧记录
                        cursor.execute("DELETE FROM image_metadata WHERE image_name = ?", (final_filename,))
                        cursor.execute("DELETE FROM tags WHERE image_name = ?", (final_filename,))
                        overwritten_count += 1

                    # 插入新记录
                    cursor.execute('''INSERT INTO image_metadata
                                      VALUES (?, ?, ?)''',
                                   (final_filename, os.path.getsize(src_path),
                                    datetime.now().isoformat()))
                    cursor.executemany('''INSERT INTO tags
                                          VALUES (?, ?, ?)''',
                                       [(final_filename, tag, round(conf, 5))
                                        for tag, conf in tag_confidences])
                    conn.commit()
                    conn.close()

                    # 移动文件
                    shutil.move(src_path, dest_path)

                    status_msg = f"处理中: {filename}"
                    if final_filename != filename:
                        status_msg += f" -> {final_filename}"

                    self.update_progress(idx / total * 100, status_msg)

                except Exception as e:
                    self.log_error(f"处理失败: {filename}\n{str(e)}")

            # 显示统计信息
            stats_msg = f"处理完成! 共 {total} 张图片"
            if renamed_count > 0:
                stats_msg += f", {renamed_count} 张因重名被重命名"
            if overwritten_count > 0:
                stats_msg += f", {overwritten_count} 张覆盖了旧记录"

            self.update_progress(100, "处理完成!")
            self.after(0, lambda: messagebox.showinfo("完成", stats_msg))
            self.search_tags()

        finally:
            self.after(0, lambda: self.process_btn.config(state=tk.NORMAL))

    def _get_unique_filename(self, filename):
        """生成唯一文件名（完全不变）"""
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
        self.after(0, lambda: self.title(f"tagify - {message}"))

    def log_error(self, message):
        self.after(0, lambda: messagebox.showerror("处理错误", message))

    def check_data_integrity(self):
        """检查数据完整性（弹出提示框版本）"""
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()

            # 获取所有数据库记录
            cursor.execute("SELECT image_name FROM image_metadata")
            db_files = set(row[0] for row in cursor.fetchall())

            # 获取实际文件
            actual_files = set(os.listdir(ARCHIVE_FOLDER))

            # 找出不一致的记录
            db_only = db_files - actual_files
            actual_only = actual_files - db_files

            # 构建详细报告
            report = f"数据完整性检查报告:\n\n"
            report += f"数据库记录数: {len(db_files)}\n"
            report += f"实际文件数: {len(actual_files)}\n\n"

            if db_only:
                report += f"⚠ 数据库中有但文件缺失: {len(db_only)} 个\n"
                for file in list(db_only)[:5]:  # 只显示前5个
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

            # 弹出详细报告
            if db_only or actual_only:
                messagebox.showwarning("数据完整性检查", report)
            else:
                messagebox.showinfo("数据完整性检查", report)

            conn.close()

        except Exception as e:
            messagebox.showerror("检查失败", f"数据完整性检查失败: {str(e)}")



if __name__ == '__main__':
    app = App()
    app.mainloop()