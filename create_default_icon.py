#!/usr/bin/env python
"""Create a default icon for the application."""

import sys

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("需要安装 Pillow: pip install Pillow")
    sys.exit(1)


def create_icon():
    """Create a simple icon with gradient background and text."""
    size = 256

    # Create image with gradient background
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw rounded rectangle background with gradient effect
    # Cyan to magenta gradient approximation
    for i in range(size):
        # Gradient from cyan (0, 200, 255) to magenta (200, 50, 200)
        r = int(0 + (200 - 0) * i / size)
        g = int(200 + (50 - 200) * i / size)
        b = int(255 + (200 - 255) * i / size)
        draw.line([(0, i), (size, i)], fill=(r, g, b, 255))

    # Add rounded corners mask
    mask = Image.new('L', (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    corner_radius = 40
    mask_draw.rounded_rectangle(
        [(0, 0), (size-1, size-1)],
        radius=corner_radius,
        fill=255
    )
    img.putalpha(mask)

    # Add text "SMD" with shadow
    try:
        # Try to use a nice font
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 80)
    except (IOError, OSError):
        try:
            font = ImageFont.truetype("arial.ttf", 80)
        except (IOError, OSError):
            font = ImageFont.load_default()

    text = "SMD"

    # Get text bounding box
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    # Center text
    x = (size - text_width) // 2
    y = (size - text_height) // 2 - 10

    # Draw shadow
    draw.text((x+3, y+3), text, fill=(0, 0, 0, 100), font=font)
    # Draw text
    draw.text((x, y), text, fill=(255, 255, 255, 255), font=font)

    # Add small icons below
    icons = "📱"
    try:
        small_font = ImageFont.truetype("/System/Library/Fonts/Apple Color Emoji.ttc", 40)
    except (IOError, OSError):
        small_font = font

    # Save as PNG
    img.save("assets/icon.png", "PNG")
    print("✅ 创建 assets/icon.png")

    # Save as ICO with multiple sizes
    sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save("assets/icon.ico", format='ICO', sizes=sizes)
    print("✅ 创建 assets/icon.ico")


if __name__ == "__main__":
    create_icon()
