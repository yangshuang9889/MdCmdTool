# -*- coding: utf-8 -*-
"""图标资源生成脚本：从两张设计图生成 app.ico / md_file.ico / app_icon.png / md_file_icon.png

用法：python make_icons.py [主图路径] [关联图路径]
不传参数时使用默认路径（原设计图所在位置）。生成结果写入本脚本所在目录，
build.bat 会校验这四个文件是否存在。
"""
import os
import sys

from PIL import Image

BASE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_MAIN = r"C:\Users\Administrator\Downloads\设计图标.jpeg"
DEFAULT_MD = r"C:\Users\Administrator\Downloads\设计图标 (1).jpeg"

# 与 Windows 资源管理器常用尺寸一致，缺帧会导致某些视图下图标模糊
SIZES = (16, 24, 32, 48, 64, 128, 256)
ICO_SIZE = 256       # ico 基图尺寸（多帧由它缩放生成）
PNG_SIZE = 64        # 关于弹窗展示用小图


def build(src, ico_name, png_name):
    if not os.path.exists(src):
        raise SystemExit("找不到源图：%s" % src)
    im = Image.open(src).convert("RGBA")
    w, h = im.size
    if w != h:  # 非正方形时居中裁切，避免图标被拉伸变形
        side = min(w, h)
        left = (w - side) // 2
        top = (h - side) // 2
        im = im.crop((left, top, left + side, top + side))

    ico_path = os.path.join(BASE, ico_name)
    png_path = os.path.join(BASE, png_name)
    im.resize((ICO_SIZE, ICO_SIZE), Image.LANCZOS).save(
        ico_path, format="ICO", sizes=[(s, s) for s in SIZES])
    im.resize((PNG_SIZE, PNG_SIZE), Image.LANCZOS).save(png_path, format="PNG")
    print("已生成 %s（%d 字节，%d 帧）与 %s（%d 字节）"
          % (ico_name, os.path.getsize(ico_path), len(SIZES),
             png_name, os.path.getsize(png_path)))


def main():
    main_src = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MAIN
    md_src = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_MD
    print("主图标源：%s" % main_src)
    build(main_src, "app.ico", "app_icon.png")
    print("关联图标源：%s" % md_src)
    build(md_src, "md_file.ico", "md_file_icon.png")
    print("完成。可执行 build.bat 重新打包。")


if __name__ == "__main__":
    main()
