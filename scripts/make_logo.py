"""Generate the Listen logo: line-drawn ear + grunge stencil LISTEN wordmark.

Draws black artwork on transparent RGBA so the app can tint it per theme.
Outputs: assets/logo.png (full wordmark), assets/icon.png (ear only, rust).
"""
import random
from pathlib import Path

from PIL import Image, ImageDraw

random.seed(11)

W, H = 1860, 900
BLACK = (0, 0, 0, 255)

img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
d = ImageDraw.Draw(img)


def bez(p0, p1, p2, p3, n=120):
    pts = []
    for i in range(n + 1):
        t = i / n
        mt = 1 - t
        x = mt**3 * p0[0] + 3 * mt**2 * t * p1[0] + 3 * mt * t**2 * p2[0] + t**3 * p3[0]
        y = mt**3 * p0[1] + 3 * mt**2 * t * p1[1] + 3 * mt * t**2 * p2[1] + t**3 * p3[1]
        pts.append((x, y))
    return pts


def stroke(pts, width):
    r = width / 2
    for x, y in pts:
        d.ellipse((x - r, y - r, x + r, y + r), fill=BLACK)


# ----------------------------------------------------------------- ear
OUTER_W = 52
INNER_W = 42

# Outer helix: opening at mid-left, over the top, down the right,
# around the lobe, hooking back up-left.
outer = []
outer += bez((195, 445), (188, 300), (230, 195), (330, 185))
outer += bez((330, 185), (425, 178), (468, 275), (468, 395))
outer += bez((468, 395), (468, 515), (432, 612), (335, 678))
outer += bez((335, 678), (272, 715), (208, 690), (202, 635))
stroke(outer, OUTER_W)

# Inner curve: question-mark spiral ending in a blob.
inner = []
inner += bez((360, 355), (350, 280), (292, 272), (268, 318))
inner += bez((268, 318), (248, 355), (258, 405), (284, 438))
inner += bez((284, 438), (300, 458), (305, 474), (299, 496))
stroke(inner, INNER_W)
d.ellipse((293 - 30, 510 - 26, 293 + 30, 510 + 34), fill=BLACK)

# ----------------------------------------------------------- letters
T = 56            # stroke thickness
LH = 330          # letter height
Y0 = 285          # top of letters
LW = 160          # letter width
SP = 46           # spacing
X0 = 620          # left edge of wordmark


def rect(x, y, w, h):
    d.rectangle((x, y, x + w, y + h), fill=BLACK)


def poly(points):
    d.polygon(points, fill=BLACK)


x = X0
# L
rect(x, Y0, T, LH)
rect(x, Y0 + LH - T, LW * 0.9, T)
x += LW + SP
# I
rect(x + (LW - T * 1.25) / 2, Y0, T * 1.25, LH)
x += LW + SP
# S
rect(x + 10, Y0, LW - 10, T)
rect(x, Y0 + T * 0.6, T, LH * 0.38)
rect(x + 4, Y0 + LH / 2 - T / 2, LW - 8, T)
rect(x + LW - T, Y0 + LH / 2 + T * 0.3, T, LH * 0.36)
rect(x, Y0 + LH - T, LW - 12, T)
x += LW + SP
# T
rect(x, Y0, LW, T)
rect(x + (LW - T) / 2, Y0, T, LH)
x += LW + SP
# E  (stencil: arms detached from the stem)
rect(x, Y0, T, LH)
ax = x + T + 16
rect(ax, Y0, LW - T - 16, T)
rect(ax, Y0 + LH / 2 - T / 2, (LW - T - 16) * 0.78, T)
rect(ax, Y0 + LH - T, LW - T - 16, T)
x += LW + SP
# N  (diagonal with a white slash through it)
rect(x, Y0, T, LH)
rect(x + LW - T, Y0, T, LH)
poly([(x + 6, Y0), (x + T + 26, Y0), (x + LW - 6, Y0 + LH),
      (x + LW - T - 26, Y0 + LH)])
n_left = x

ART_RIGHT = x + LW

# --------------------------------------------------- stencil cuts
erase = Image.new("L", (W, H), 0)
de = ImageDraw.Draw(erase)

# white slash across the N (like the reference)
de.line((n_left + LW * 0.52, Y0 - 30, n_left + LW * 1.02, Y0 + LH + 30),
        fill=255, width=16)

# ------------------------------------------------------- grunge
alpha = img.split()[3]

def crack(x, y, steps, width):
    px, py = x, y
    ang = random.uniform(0, 6.283)
    for _ in range(steps):
        ang += random.uniform(-1.0, 1.0)
        nx = px + random.uniform(6, 15) * __import__("math").cos(ang)
        ny = py + random.uniform(6, 15) * __import__("math").sin(ang)
        de.line((px, py, nx, ny), fill=255, width=width)
        px, py = nx, ny

placed = 0
while placed < 65:
    cx = random.uniform(140, ART_RIGHT)
    cy = random.uniform(160, 760)
    if alpha.getpixel((int(cx), int(cy))) > 200:
        crack(cx, cy, random.randint(2, 5), random.randint(2, 4))
        placed += 1

# speckle pinholes
for _ in range(260):
    cx = random.uniform(140, ART_RIGHT)
    cy = random.uniform(160, 760)
    if alpha.getpixel((int(cx), int(cy))) > 200:
        r = random.uniform(1.2, 3.2)
        de.ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)

# apply erasure to the alpha channel
from PIL import ImageChops
new_alpha = ImageChops.subtract(alpha, erase)
img.putalpha(new_alpha)

# ------------------------------------------------------- outputs
assets = Path(r"C:\dev\listen\assets")
assets.mkdir(exist_ok=True)

bbox = img.getbbox()
logo = img.crop(bbox)
logo.save(assets / "logo.png")

# ear-only icon, tinted rust, square canvas
ear = img.crop((120, 140, 520, 780))
tint = Image.new("RGBA", ear.size, (232, 86, 63, 255))
tint.putalpha(ear.split()[3])
side = max(ear.size)
icon = Image.new("RGBA", (side, side), (0, 0, 0, 0))
icon.paste(tint, ((side - ear.size[0]) // 2, (side - ear.size[1]) // 2))
icon = icon.resize((256, 256), Image.LANCZOS)
icon.save(assets / "icon.png")

# white-backed preview for inspection
prev = Image.new("RGB", logo.size, (255, 255, 255))
prev.paste(logo, (0, 0), logo)
prev.save(Path(__file__).parent / "logo_preview.png")
print("logo:", logo.size, "-> assets/logo.png, assets/icon.png")
