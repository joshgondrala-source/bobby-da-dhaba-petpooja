"""
Generates ONE printable QR card for Bobby Da Dhaba.

The same QR code is used on every table and at the counter — it points to
the app's home page, where the guest chooses Dine In (and types their table
number) or Takeaway. This keeps things simple: one artwork, print as many
copies as needed for tables + counter, no per-table QR management.

Usage:
    python generate_qr_card.py                                 # uses http://127.0.0.1:5000
    python generate_qr_card.py https://bobbydadhaba.onrender.com  # for the live/prod URL
"""

import sys
import qrcode
from PIL import Image, ImageDraw, ImageFont


def get_font(size, bold=False):
    candidates = [
        "arialbd.ttf" if bold else "arial.ttf",
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
    ]
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def build_card(base_url, output_path="qr_card.png"):
    qr_img = qrcode.make(base_url.rstrip("/") + "/").convert("RGB")
    qr_img = qr_img.resize((640, 640))

    card_w, card_h = 800, 1050
    card = Image.new("RGB", (card_w, card_h), "white")
    draw = ImageDraw.Draw(card)

    brand_color = (92, 16, 16)
    gold_color = (200, 136, 30)
    muted_color = (110, 95, 80)

    draw.rectangle([0, 0, card_w, 14], fill=brand_color)

    title_font = get_font(46, bold=True)
    tag_font = get_font(22)
    scan_font = get_font(30, bold=True)
    note_font = get_font(22)

    title = "BOBBY DA DHABA"
    tw = draw.textlength(title, font=title_font)
    draw.text(((card_w - tw) / 2, 40), title, fill=brand_color, font=title_font)

    tag = "AUTHENTIC · DESI · TADKA"
    tagw = draw.textlength(tag, font=tag_font)
    draw.text(((card_w - tagw) / 2, 100), tag, fill=gold_color, font=tag_font)

    qr_x = (card_w - qr_img.width) // 2
    qr_y = 150
    card.paste(qr_img, (qr_x, qr_y))

    scan_text = "SCAN TO ORDER"
    sw = draw.textlength(scan_text, font=scan_font)
    draw.text(((card_w - sw) / 2, qr_y + qr_img.height + 24), scan_text, fill=brand_color, font=scan_font)

    note_lines = [
        "Scan \u2192 choose Dine In (enter your table no.) or Takeaway",
        "",
        "Once your order is placed, please don't move to another",
        "table. Need a separate takeaway parcel too? Just scan again",
        "and choose Takeaway \u2014 it's billed separately at the counter.",
    ]
    ny = qr_y + qr_img.height + 74
    for line in note_lines:
        lw = draw.textlength(line, font=note_font)
        draw.text(((card_w - lw) / 2, ny), line, fill=muted_color, font=note_font)
        ny += 32

    draw.rectangle([0, card_h - 14, card_w, card_h], fill=brand_color)

    card.save(output_path)
    print(f"Saved {output_path} (source URL: {base_url})")


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5000"
    build_card(url)
