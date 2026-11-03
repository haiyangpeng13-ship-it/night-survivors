"""Run this script on your computer to build assets/ from raw_art/.

    py -3.13 make_assets.py

raw_art/ is never changed. The pictures are 16 x 16, so every asset is the same
picture with each pixel blown up to 3 x 3 pixels: sharp, not blurred.
Needs Pillow. main.py never imports this file.
"""

import pathlib
import sys

from PIL import Image, ImageChops, ImageOps

ROOT = pathlib.Path(__file__).resolve().parent
RAW = ROOT / "raw_art"
OUT = ROOT / "assets"


def upscale(image, scale):
    """Make every pixel a scale x scale block, without mixing colours."""
    size = (image.width * scale, image.height * scale)
    return image.resize(size, Image.NEAREST)


def recolour(image, tint):
    """Keep the shading of the picture but paint it one bright colour."""
    shade = image.convert("L")
    shade = ImageOps.autocontrast(shade)
    grey = Image.merge("RGB", (shade, shade, shade))
    colour = Image.new("RGB", image.size, tuple(int(c) for c in tint))
    glow = Image.new("RGB", image.size, tuple(int(c) * 45 // 100 for c in tint))
    lit = ImageChops.screen(ImageChops.multiply(colour, grey), glow)
    lit.putalpha(image.getchannel("A"))
    return lit


def main():
    sys.path.insert(0, str(ROOT))
    import rules

    art = rules.load_data(ROOT / "data" / "game.json")["art"]
    scale = art["scale"]
    OUT.mkdir(exist_ok=True)

    made = []
    for source in sorted(RAW.glob("*.png")):
        picture = Image.open(source)
        upscale(picture.convert("RGBA"), scale).save(OUT / source.name)
        made.append(source.name)

    gem_base = Image.open(RAW / art["gem_source"]).convert("RGBA")
    for gem in art["gems"]:
        upscale(recolour(gem_base, gem["tint"]), scale).save(OUT / gem["picture"])
        made.append(gem["picture"])

    print(f"wrote {len(made)} pictures to {OUT.name}/ at {scale}x:")
    for name in made:
        print("  assets/" + name)


if __name__ == "__main__":
    main()
