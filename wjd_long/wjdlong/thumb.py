"""Thumbnail 1280x720: sterk dierenbeeld, grote hooktekst en TOP 10-label."""
import os, subprocess
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter

FD = os.path.join(os.path.dirname(__file__), "..", "assets", "fonts")


def make(path, clip, thumb_text, ss=2.5):
    tmp = path + ".png"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{ss}", "-i", clip, "-frames:v", "1", "-vf", "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720", tmp], check=True)
    im = Image.open(tmp).convert("RGB"); im = ImageEnhance.Contrast(im).enhance(1.12); im = ImageEnhance.Color(im).enhance(1.25)
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    for x in range(0, 900): d.line([(x, 0), (x, 720)], fill=(0, 0, 0, int(190 * (1 - x / 900) ** 1.4)))
    im = Image.alpha_composite(im.convert("RGBA"), ov); d = ImageDraw.Draw(im)
    bold = os.path.join(FD, "Poppins-Bold.ttf"); words = thumb_text.upper().split(); maxw = 700
    for size in range(190, 70, -6):
        f = ImageFont.truetype(bold, size); lines = [""]
        for w in words:
            if d.textlength((lines[-1] + " " + w).strip(), font=f) > maxw and lines[-1]: lines.append(w)
            else: lines[-1] = (lines[-1] + " " + w).strip()
        if len(lines) <= 3 and all(d.textlength(l, font=f) <= maxw for l in lines): break
    lh = int(size * 1.12); y = 380 - lh * len(lines) // 2
    for i, ln in enumerate(lines):
        col = (255, 213, 48) if i == len(lines) - 1 else (255, 255, 255)
        for dx, dy in [(-6, 0), (6, 0), (0, -6), (0, 6), (-5, -5), (5, 5), (-5, 5), (5, -5)]: d.text((50 + dx, y + dy), ln, font=f, fill=(0, 0, 0, 255))
        d.text((50, y), ln, font=f, fill=col); y += lh
    f2 = ImageFont.truetype(bold, 62); d.rounded_rectangle([40, 36, 330, 118], 18, fill=(208, 48, 48, 255)); d.text((62, 40), "TOP 10", font=f2, fill=(255, 255, 255))
    im.convert("RGB").save(path, quality=92); os.remove(tmp); return path
