"""Thumbnail 1280x720: mooi stukje beeld + titel onderaan."""
import subprocess
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"


def make(path, clips, title):
    # kies de clip met een helderheid die goed oogt (niet te donker) uit de eerste 3 hoofdstukken
    pool = [c for ch in clips[:3] for c in ch]
    best = min(pool, key=lambda c: abs(c[2] - 95))
    tmp = path + ".frame.png"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "3", "-i", best[0], "-frames:v", "1",
                    "-vf", "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720", tmp], check=True)
    im = Image.open(tmp).convert("RGB")
    im = ImageEnhance.Brightness(im).enhance(0.95)
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    for y in range(300, 720):  # donkere verloop onderaan
        d.line([(0, y), (1280, y)], fill=(0, 0, 0, int(190 * (y - 300) / 420)))
    im = Image.alpha_composite(im.convert("RGBA"), ov); d = ImageDraw.Draw(im)
    big = ImageFont.truetype(FONT, 78); small = ImageFont.truetype(FONT, 30)
    lines = [""]
    for w in title.split():
        if d.textlength((lines[-1] + " " + w).strip(), font=big) > 1150: lines.append(w)
        else: lines[-1] = (lines[-1] + " " + w).strip()
    y = 690 - 90 * len(lines)
    d.text((60, y - 52), "SLEEP STORY  ·  SWEET DREAMS", font=small, fill=(220, 225, 245, 255))
    for ln in lines:
        d.text((60, y), ln, font=big, fill=(255, 255, 255, 255), stroke_width=3, stroke_fill=(0, 0, 0, 200)); y += 90
    im.convert("RGB").save(path, quality=88)
    return path
