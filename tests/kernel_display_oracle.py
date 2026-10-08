"""Independent desired pixels for the Aurora status-page consumer.

Rows are written independently of the production module's packed glyph constants;
this oracle imports no kernel packing, clipping or font helper.
"""

FONT = {
    "A": "01110/10001/10001/11111/10001/10001/10001",
    "B": "11110/10001/10001/11110/10001/10001/11110",
    "C": "01111/10000/10000/10000/10000/10000/01111",
    "D": "11110/10001/10001/10001/10001/10001/11110",
    "E": "11111/10000/10000/11110/10000/10000/11111",
    "F": "11111/10000/10000/11110/10000/10000/10000",
    "G": "01111/10000/10000/10111/10001/10001/01111",
    "H": "10001/10001/10001/11111/10001/10001/10001",
    "I": "11111/00100/00100/00100/00100/00100/11111",
    "L": "10000/10000/10000/10000/10000/10000/11111",
    "N": "10001/11001/11001/10101/10011/10011/10001",
    "O": "01110/10001/10001/10001/10001/10001/01110",
    "P": "11110/10001/10001/11110/10000/10000/10000",
    "R": "11110/10001/10001/11110/10100/10010/10001",
    "S": "01111/10000/10000/01110/00001/00001/11110",
    "T": "11111/00100/00100/00100/00100/00100/00100",
    "U": "10001/10001/10001/10001/10001/10001/01110",
    "V": "10001/10001/10001/10001/10001/01010/00100",
    "X": "10001/10001/01010/00100/01010/10001/10001",
    "Y": "10001/10001/01010/00100/00100/00100/00100",
    " ": "00000/00000/00000/00000/00000/00000/00000",
}


def reference(width, height, pitch, pixel_format, guard=True, fill=0xA5):
    size = ((pitch * height * 4 + 4095) // 4096) * 4096
    margin = 32 if guard else 0
    pixels = bytearray([fill]) * (size + 2 * margin)
    stores = 0

    def plot(x, y, rgb):
        nonlocal stores
        if x < 0 or y < 0 or x >= width or y >= height:
            return
        offset = margin + (y * pitch + x) * 4
        r, g, b = rgb
        pixels[offset : offset + 4] = bytes((r, g, b, 0) if pixel_format == 0 else (b, g, r, 0))
        stores += 1

    for y in range(height):
        for x in range(width):
            color = (18, 30, 46) if y < 96 else (13, 20, 32)
            if 32 <= x < 768 and 88 <= y < 90:
                color = (52, 188, 220)
            if 16 <= x < 22 and any(top <= y < top + 6 for top in (184, 202, 220)):
                color = (103, 211, 151)
            plot(x, y, color)

    def text(words, baseline, cursor=False):
        x, y = 32, baseline
        for ch in words:
            scale = 3 if y < 96 else 2
            if ch == "\n":
                x, y = 32, y + 9 * scale
                continue
            color = (222, 237, 247) if y < 96 else (52, 188, 220) if y >= 520 else (204, 226, 235)
            for row, line in enumerate(FONT[ch].split("/")):
                for col, bit in enumerate(line):
                    if bit == "1":
                        for dy in range(scale):
                            for dx in range(scale):
                                plot(x + col * scale + dx, y + row * scale + dy, color)
            x += 6 * scale
        if cursor:
            for dy in range(2):
                for dx in range(10):
                    plot(x + dx, y + 14 + dy, (52, 188, 220))

    text("AURORA", 28)
    text("BOOT STATUS", 128)
    text("UEFI EXITED\nPRIVATE PAGING\nDISPLAY SESSION", 180)
    text("GRAPHICS OUTPUT", 540, True)
    return bytes(pixels), stores


def ppm_rgb(width, height, pitch, pixel_format, pixels):
    rgb = bytearray()
    for y in range(height):
        for x in range(width):
            offset = (y * pitch + x) * 4
            a, g, c, _ = pixels[offset : offset + 4]
            rgb.extend((a, g, c) if pixel_format == 0 else (c, g, a))
    return bytes(rgb)
