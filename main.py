"""
Tagify v9.1 — 图片标签管理系统 Web 版
基于 WD ViT Tagger v3 + FastAPI + 纯 HTML/CSS/JS

用法: python main.py [--device auto|cuda|cpu] [--port 8000]
     浏览器打开 http://localhost:8000

显卡驱动异常导致启动黑屏死机时，请用 --cpu 启动（完全不加载 CUDA）:
     python main.py --cpu
"""
import argparse
import os
import sys

_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_DIR not in sys.path:
    sys.path.insert(0, _PROJECT_DIR)


def parse_args():
    from tagify.config import DEVICE
    parser = argparse.ArgumentParser(description="Tagify v9.1 — 图片标签管理系统")
    parser.add_argument(
        "--device", choices=["auto", "cuda", "cpu"], default=DEVICE,
        help="推理设备: auto 自动检测 / cuda 强制 GPU / cpu 强制 CPU "
             "（显卡驱动异常导致黑屏时用 cpu）")
    parser.add_argument(
        "--cpu", action="store_true",
        help="强制使用 CPU（等价于 --device cpu，避免初始化 CUDA）")
    parser.add_argument("--port", type=int, default=8000, help="监听端口（默认 8000）")
    args = parser.parse_args()
    if args.cpu:
        args.device = "cpu"
    return args


if __name__ == '__main__':
    import uvicorn

    args = parse_args()

    # 加载模型（带错误处理；失败则离线模式运行，仅无法处理新图片）
    tagger = None
    try:
        from tagify.model import WDTagger
        print("正在加载模型...")
        tagger = WDTagger(device=args.device)
        print("模型加载完成！")
    except Exception as e:
        print(f"模型加载失败: {e}")
        print("程序将以离线模式运行（无法处理新图片）。")

    # 初始化数据库
    from tagify.database import init_database
    init_database()

    # 创建 FastAPI 应用
    from server.api import create_app
    app = create_app(tagger)

    print(f"\n  Tagify v9.1 已启动 → http://localhost:{args.port}\n")
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="info")
