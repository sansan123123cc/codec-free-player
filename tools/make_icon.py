"""앱 아이콘(app.ico) 생성 — 빌드할 때 GitHub Actions 에서 실행."""
import sys
from PIL import Image, ImageDraw


def draw(size):
    s = size * 4
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    grad = Image.new("RGBA", (s, s))
    px = grad.load()
    a, b = (0xff, 0x7a, 0xa2), (0x8a, 0x5c, 0xff)
    for y in range(s):
        for x in range(s):
            t = (x + y) / (2 * s - 2)
            px[x, y] = tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3)) + (255,)
    mask = Image.new("L", (s, s), 0)
    m = int(s * 0.04)
    ImageDraw.Draw(mask).rounded_rectangle([m, m, s - m, s - m], radius=int(s * 0.24), fill=255)
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    d.polygon([(s * 0.38, s * 0.27), (s * 0.75, s * 0.5), (s * 0.38, s * 0.73)], fill=(255, 255, 255, 255))
    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "app.ico"
    big = draw(256)
    big.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("icon ->", out)
