"""Kinetic Assembly thumbnail: stacked blocks mid-arrival + a self-healing loop arc."""
import math
from PIL import Image, ImageDraw, ImageFont, ImageFilter

FONT_DIR = "/Users/yuukiyamashita/Library/Application Support/Claude/local-agent-mode-sessions/skills-plugin/c80a8ab5-46f1-460f-8272-5d888a9dea9d/27edbd3b-2a46-42c9-9efc-ed37be5c5074/skills/canvas-design/canvas-fonts"

SCALE = 2
LOGICAL_W, LOGICAL_H = 1600, 900
W, H = LOGICAL_W * SCALE, LOGICAL_H * SCALE


def S(v):
    return int(v * SCALE)


INK = (18, 21, 27)
PAPER = (250, 249, 246)
AMBER = (255, 138, 0)
GRAY = (120, 124, 130)

img = Image.new("RGB", (W, H), PAPER)

# subtle vertical gradient for depth
grad = Image.new("L", (1, H), 0)
for y in range(H):
    t = y / H
    grad.putpixel((0, y), int(8 * (1 - t)))
grad = grad.resize((W, H))
shade = Image.new("RGB", (W, H), (234, 231, 223))
img = Image.composite(shade, img, grad)

# ---- Soft glow behind the amber (most-recently-arrived) block, drawn first ----
glow_cx, glow_cy = S(1160), S(430)
glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
gdraw = ImageDraw.Draw(glow)
gr = S(160)
gdraw.ellipse([glow_cx - gr, glow_cy - gr, glow_cx + gr, glow_cy + gr], fill=(255, 138, 0, 140))
glow = glow.filter(ImageFilter.GaussianBlur(S(55)))
img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")

draw = ImageDraw.Draw(img, "RGBA")

f_title = ImageFont.truetype(f"{FONT_DIR}/Outfit-Bold.ttf", S(116))
f_title2 = ImageFont.truetype(f"{FONT_DIR}/Outfit-Bold.ttf", S(78))
f_mono = ImageFont.truetype(f"{FONT_DIR}/JetBrainsMono-Regular.ttf", S(21))
f_mono_b = ImageFont.truetype(f"{FONT_DIR}/JetBrainsMono-Bold.ttf", S(22))

# ---- Stacked blocks, ascending diagonally toward upper-right ----
blocks = [
    # (x, y_bottom, w, h)
    (S(900), S(800), S(160), S(64)),
    (S(1000), S(710), S(170), S(68)),
    (S(1105), S(615), S(155), S(70)),
    (S(1195), S(515), S(175), S(72)),
    (S(1290), S(420), S(155), S(76)),  # amber, most recent
]
for i, (x, yb, w, h) in enumerate(blocks):
    is_last = i == len(blocks) - 1
    fill = AMBER if is_last else INK
    draw.rounded_rectangle([x, yb - h, x + w, yb], radius=S(12), fill=fill)

# ---- Self-healing loop arc, upper right ----
cx, cy, r = S(1330), S(210), S(120)
stroke = S(11)
draw.arc([cx - r, cy - r, cx + r, cy + r], start=-40, end=250, fill=AMBER, width=stroke)
ang = math.radians(250)
ax, ay = cx + r * math.cos(ang), cy + r * math.sin(ang)
tang = ang + math.pi / 2
ah = S(26)
p1 = (ax, ay)
p2 = (ax - ah * math.cos(tang - 0.5), ay - ah * math.sin(tang - 0.5))
p3 = (ax - ah * math.cos(tang + 0.5), ay - ah * math.sin(tang + 0.5))
draw.polygon([p1, p2, p3], fill=AMBER)
dot_ang = math.radians(-40)
dx, dy = cx + r * math.cos(dot_ang), cy + r * math.sin(dot_ang)
dr = S(12)
draw.ellipse([dx - dr, dy - dr, dx + dr, dy + dr], fill=INK)

# ---- Title, monumental, left side ----
tx, ty = S(90), S(320)
draw.text((tx, ty), "SELF-HEALING", font=f_title, fill=INK)
draw.text((tx, ty + S(128)), "INFRASTRUCTURE", font=f_title2, fill=AMBER)

ry = ty + S(128) + S(108)
draw.line([(tx, ry), (tx + S(760), ry)], fill=INK, width=S(3))

draw.text((tx, ry + S(22)), "Claude on Amazon Bedrock  x  AWS CloudFormation Express Mode",
          font=f_mono, fill=GRAY)

# small evidence line, bottom-right, log-register
stat = "STANDARD 51.91s -> EXPRESS 25.44s  (2.04x)"
bbox = draw.textbbox((0, 0), stat, font=f_mono_b)
sw = bbox[2] - bbox[0]
draw.text((W - sw - S(70), H - S(70)), stat, font=f_mono_b, fill=INK)

img = img.resize((LOGICAL_W, LOGICAL_H), Image.LANCZOS)
img.save("/Users/yuukiyamashita/cfn-express-agent-demo/thumbnail.png", "PNG")
img.convert("RGB").save("/Users/yuukiyamashita/cfn-express-agent-demo/thumbnail.jpg", "JPEG", quality=95)
print("done")
