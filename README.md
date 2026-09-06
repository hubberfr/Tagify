# Tagify — 图片自动打标签与分类管理系统

> 前后端分离的图片标签管理 Web 应用：基于 **WD ViT Tagger v3** 深度学习模型自动为图片打上 Danbooru 标签，并提供多维度搜索、按评级/角色分类浏览、收藏管理与数据完整性检查。

![Uploading 25e4a8c7a5d4654260d1d4baf74384e6.png…]()



---

## ✨ 功能特性

- **自动打标**：WD ViT Tagger v3 模型（448×448），识别精准，含 10861 个 Danbooru 标签
- **标签分类**：评级（general / sensitive / questionable / explicit）与角色标签自动识别，列表内高亮着色
- **类别搜索**：搜索 `rating` 列出评级分类，搜索 `character` 列出角色标签（支持 `rating:xxx` / `character xxx` 过滤）
- **多维浏览**：按名称 / 大小 / 时间 / 置信度排序、分页浏览、缩略图网格
- **图库管理**：单击查看详情与全部标签、双击查看原图、收藏、删除
- **屏蔽 R18（SFW）**：一键开关（默认开启），只展示 `general` 评级图片，方便向他人演示项目
- **完整设置面板**：主题、收藏标签、排序、分页、各置信度阈值、缩略图尺寸、路径等均可网页修改，**保存即生效**（热更新，无需重启）
- **明暗双主题**、响应式三栏布局、纯原生前端无框架依赖
- **数据完整性检查**：对比数据库记录与实际文件，报告不一致项

## 🧱 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python · FastAPI · Uvicorn · SQLite3 |
| 推理 | PyTorch · timm · safetensors · WD ViT Tagger v3 |
| 前端 | 原生 HTML / CSS / JavaScript（无构建步骤） |

## 📁 项目结构

```
tag/
├── main.py                 # 入口：加载模型、初始化数据库、启动 Web 服务
├── app_config.json         # 应用配置（亦可在网页「设置」中修改）
├── app_config.md           # 配置项说明文档
├── requirements.txt        # Python 依赖
├── config.json             # 模型架构配置（timm 使用，已随仓库提供）
├── tagify/                 # 核心逻辑包
│   ├── config.py           # 配置加载与运行时热更新
│   ├── model.py            # 模型推理封装
│   ├── database.py         # SQLite 建表 / 查询 / SFW 过滤
│   └── tags.py             # 标签类别判定、着色、排序
├── server/
│   └── api.py              # FastAPI 路由与后台批量处理线程
├── static/                 # 前端页面
│   ├── index.html
│   ├── style.css
│   └── app.js
├── input_image/            # 【需自行创建】存放待处理图片
├── gallery/                # 【自动创建】处理后图片归档目录
├── model.safetensors       # 【需从模型页下载】模型权重（不入库）
├── selected_tags.csv       # 【需从模型页下载】标签目录（不入库）
└── image_tags.db           # 【首次运行自动生成】SQLite 数据库
```

## 🚀 快速开始

### 1. 环境要求

- Python 3.9+
- pip 安装依赖

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

> GPU 用户请另外安装对应 CUDA 版本的 PyTorch，以获得更快的处理速度：
> `pip install torch --index-url https://download.pytorch.org/whl/cu121`

### 3. 下载模型与标签文件

从模型页下载以下**两个文件**放入项目根目录（与 `config.json` 同级）：

- `model.safetensors` — 模型权重（约 378 MB，超出 GitHub 单文件限制故未入库）
- `selected_tags.csv` — 标签目录（10861 条，需与模型版本配套，故未入库）

下载地址：[HuggingFace：SmilingWolf/wd-vit-tagger-v3](https://huggingface.co/SmilingWolf/wd-vit-tagger-v3)

> `config.json` 随仓库提供；若更换模型版本，请将以上三个文件一并更新为同一版本。

### 4. 启动

```bash
# 创建待处理图片目录（仅首次）
mkdir input_image

# 启动
python main.py
```

浏览器访问 **http://localhost:8000** 即可。

- 程序默认监听 `0.0.0.0:8000`，局域网内可通过 `http://<主机IP>:8000` 访问
- 若模型加载失败，程序会以**离线模式**启动（可浏览已有图库，但无法处理新图片）
- **显卡驱动异常导致启动黑屏/死机时**，改用 `python main.py --cpu` 强制 CPU 启动（完全不加载 CUDA）

## 📖 使用指南

### 批量处理图片

1. 将图片放入 `input_image/` 文件夹
2. 点击顶部 **「开始批量处理」**
3. 程序自动为每张图片打标并存入数据库，完成后图片移入 `gallery/`

### 搜索与浏览

- 左侧搜索框输入关键词，回车或点击**搜索**，下方列出含该关键词的标签及图片数，点击标签即筛选图库
- 输入时提供**自动补全**下拉建议
- **类别搜索**：输入 `rating` 显示 4 个评级标签，输入 `character` 显示全部角色标签；也可用 `rating:sensitive`、`character reimu` 精确定位
- 顶部「名称 / 时间 / 大小」按钮切换排序，点击同按钮切换升降序
- **单击**缩略图：右侧查看图片信息与标签详情（评级 / 角色 / 一般分区展示）
- **双击**缩略图：原图弹窗，可收藏 / 删除

### 收藏与删除

- 弹窗中点击「收藏」会给图片自动打上收藏标签（默认 `collect`），再次点击取消
- 「删除」会同时移除文件与数据库记录

### 数据完整性

- 点击 **「数据完整性」** 对比数据库记录与实际归档文件，报告缺失或多余项

## ⚙️ 设置

点击右上角 **⚙** 打开设置面板（居中大窗口），所有设置点击「保存设置」后**即时生效**并写入 `app_config.json`，无需重启：

| 分组 | 可配置项 |
|---|---|
| 外观 | 明 / 暗主题（仅保存在浏览器） |
| 通用 | 收藏标签名、**屏蔽 R18**（仅显示 general 评级）、默认排序、排序方向、每页图片数 |
| 标签与阈值 | 处理阈值、主要标签阈值、详细标签下限、默认阈值 |
| 界面 | 缩略图宽度 / 高度（图库卡片同步缩放） |
| 路径 | 输入文件夹、归档文件夹 |

- 「恢复默认」一键还原全部默认配置
- 完整配置键说明见 [`app_config.md`](app_config.md)

### 屏蔽 R18（SFW 模式）

向他人展示项目前，确认设置中的 **「屏蔽 R18」已开启（默认开启）**：图库与标签浏览只展示主评级为 `general` 的图片，详情面板也仅显示 `general` 评级徽章。

## 🧰 常见问题

**Q：提示"输入文件夹不存在"？**
创建 `input_image/` 目录并把图片放进去。

**Q：启动时提示模型加载失败？**
检查 `model.safetensors` 与 `selected_tags.csv` 是否都已下载到项目根目录、磁盘/内存是否充足；模型加载失败时程序以离线模式运行。

**Q：更新显卡驱动后，一启动程序就黑屏死机？**
本项目默认使用 CPU 版 PyTorch 推理，正常情况下**不会调用显卡**。若发生黑屏，通常是显卡驱动本身异常，请：
1. 用 `python main.py --cpu` 启动确认（程序完全跳过 CUDA 初始化）
2. 使用 DDU（Display Driver Uninstaller）在安全模式下彻底卸载驱动，重新安装 NVIDIA 官方驱动（或回滚到上一个稳定版本）
3. 安装 GPU 版 PyTorch 后若再次黑屏，可在 `app_config.json` 中将 `model.device` 改为 `"cpu"` 规避

**Q：如何加速批量处理？**
安装 CUDA 版 PyTorch（`pip install torch --index-url https://download.pytorch.org/whl/cu121`）；或调高设置中的「处理阈值」（如 0.35）减少每个模型的标签数量。

**Q：改了 `app_config.json` 但界面没变化？**
建议通过网页设置面板修改（保存即热生效）；直接改文件后需重启服务。路径类修改（如归档目录）后图库位置随之变化。

## 📝 数据与致谢

- 标签体系与标签计数源自 [Danbooru](https://danbooru.donmai.us/) 社区
- 模型：[WD ViT Tagger v3](https://huggingface.co/SmilingWolf/wd-vit-tagger-v3)（作者 SmilingWolf）。模型文件与标签数据的**许可证以模型页声明为准**，二次分发时请自行确认合规性
- 本项目代码仅供学习交流使用


