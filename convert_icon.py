#!/usr/bin/env python
"""Convert image to .ico format for Windows executable."""

import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("需要安装 Pillow: pip install Pillow")
    sys.exit(1)


def convert_to_ico(input_path: str, output_path: str = None):
    """Convert image to .ico format with multiple sizes."""
    input_file = Path(input_path)

    if not input_file.exists():
        print(f"文件不存在: {input_file}")
        return False

    if output_path is None:
        output_path = input_file.with_suffix('.ico')
    else:
        output_path = Path(output_path)

    # Open image
    img = Image.open(input_file)

    # Convert to RGBA if needed
    if img.mode != 'RGBA':
        img = img.convert('RGBA')

    # Create icon with multiple sizes
    sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

    # Save as ICO
    img.save(
        output_path,
        format='ICO',
        sizes=sizes
    )

    print(f"✅ 图标已生成: {output_path}")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python convert_icon.py <图片路径> [输出路径]")
        print("示例: python convert_icon.py assets/icon.png assets/icon.ico")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None

    convert_to_ico(input_path, output_path)
