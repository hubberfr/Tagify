"""
Tagify 模型封装 — WD ViT Tagger v3
"""
import json
import numpy as np
import pandas as pd
import torch
import timm
from safetensors.torch import load_file
from PIL import Image

from tagify.config import (
    MODEL_PATH, CONFIG_PATH, TAGS_CSV_PATH,
    IMAGE_SIZE, DEFAULT_THRESHOLD, DEVICE,
)


def _resolve_device(pref):
    """解析推理设备，任何 CUDA 异常都回退 CPU，避免显卡驱动问题导致死机。
    pref: "auto"(默认) / "cuda" / "cpu"
    - "cpu": 完全不初始化 CUDA（显卡驱动异常时的安全选择）
    - "cuda": 强制 GPU，不可用则报错回退 CPU
    - "auto": 可用则 GPU，否则 CPU
    """
    pref = (pref or "auto").lower()
    if pref == "cpu":
        print("[设备] 已按配置强制使用 CPU（不会加载 CUDA）")
        return torch.device("cpu")

    try:
        if pref == "cuda":
            if not torch.cuda.is_available():
                raise RuntimeError("torch 未检测到可用 CUDA（可能未安装 GPU 版 PyTorch）")
            print("[设备] 使用 GPU (CUDA)")
            return torch.device("cuda")
        # auto
        if torch.cuda.is_available():
            print("[设备] 检测到 CUDA，使用 GPU 加速")
            return torch.device("cuda")
        print("[设备] 未检测到可用 CUDA，使用 CPU")
        return torch.device("cpu")
    except Exception as e:
        print(f"[设备] CUDA 初始化失败({e})，已自动回退到 CPU")
        return torch.device("cpu")


class WDTagger:
    """WD ViT Tagger v3 模型封装类"""

    def __init__(self, model_path=MODEL_PATH, config_path=CONFIG_PATH,
                 csv_path=TAGS_CSV_PATH, device=DEVICE):
        print("正在初始化新模型...")

        self.device = _resolve_device(device)
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
