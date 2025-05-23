# Tagify - 图片标签管理系统
基于deepdanbooru批量给图片添加标签,通过标签分类并搜索图片的软件,拥有简单实用的图像化界面
![2ad942e0-7207-4ca6-b976-e4d54f233e7b](https://github.com/user-attachments/assets/00c2d9b2-c31d-498e-a7c5-c283f7609b4f)


## 运行提示
- 运行前请在当前目录创建名为"input_image"的文件夹,以及创建名为"gallery"的文件夹
- 运行前请前往https://github.com/KichangKim/DeepDanbooru/releases/tag/v3-20211112-sgd-e28
- 下载对应model-resnet_custom_v3.h5模型以及标签放入当前目录下
- 并配置MODEL_PATH = 'model-resnet_custom_v3.h5'
- TAGS_FILE = 'tags.txt'

## 前置
- Python 3.9
- TensorFlow 2.x
- SQLite
- Tkinter GUI
- pywin32 310

## tagify使用指北
- 1.图片处理
- 将需要输入的图片放入input_image文件夹下
- 点击批量处理图片按钮
- 即可批量处理图片并剪切到gallery文件夹下,数据保存在image_tags.db文件中
- 2.根据标签搜索
- 在左侧面板输入框输入需要查询的标签,点击搜索按钮
- 下方会出现与之匹配的相关标签,括号中显示的是含有此标签的图片出现次数
- 3.图片预览查看
- 点击对应标签后,中间面板会出现含此标签的缩略图,一行4张,一页20张
- 单击缩略图右侧面板会显示详细信息和详细标签信息
- 双击缩略图可以查看原图
- 右键缩略图或者原图会出现菜单,有复制图片,收藏图片,添加自定义标签,从图库中删除功能
- 收藏图片功能会自动给图片添加"collect"标签
- 可以通过添加自定义标签实现自定义收藏
- 下方有分页按钮
- 上方有按名称,大小,存入时间排序按钮
- 右侧标签列表右键有复制标签功能

## 功能特性
- 基于深度学习的自动图片标注
- 自定义标签管理
- 可视化图片浏览
- 数据库持久化存储

