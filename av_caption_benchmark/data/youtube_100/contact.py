from pathlib import Path
import json
from PIL import Image, ImageDraw, ImageFont

root = Path(__file__).resolve().parent
rows = [json.loads(line) for line in (root / "manifest.jsonl").read_text(encoding="utf8").splitlines()]
font = ImageFont.truetype("arial.ttf", 13)
for start in range(0, len(rows), 25):
    batch = rows[start:start+25]
    sheet = Image.new("RGB", (1000, 5 * 138), "#1d2329")
    draw = ImageDraw.Draw(sheet)
    for i, row in enumerate(batch):
        x, y = i % 5 * 200, i // 5 * 138
        if row["preview"]:
            with Image.open(root / row["preview"]) as im:
                im.thumbnail((195, 108))
                sheet.paste(im, (x, y))
        draw.text((x+2, y+108), f"{start+i+1}  {row['video_id']}", font=font, fill="white")
        draw.text((x+2, y+123), row["topic"][:29], font=font, fill="#bcdcf2")
    sheet.save(root / f"review_{1+start//25}.jpg", quality=88)
