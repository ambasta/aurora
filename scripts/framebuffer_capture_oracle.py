"""Fail-closed oracle for the admitted 800x600 BGR32 emulator fixture.

The expected scene is the native display renderer's reviewed golden output
(tests/kernel-display-renderer.golden): the captured pixels, placed in the
renderer's guarded 0xA5 buffer, must reproduce its store count and digest.
"""

import hashlib
import re
from pathlib import Path
from kernel_layout import LAYOUT  # noqa: E402
from kernel_uefi_oracle import loader_selection  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests/kernel-display-renderer.golden"
BASE, SIZE, WIDTH, HEIGHT, PITCH = 0x80000000, 1921024, 800, 600, 800
VISIBLE = WIDTH * HEIGHT * 4
GATE = f"AURORA_DISPLAY_CAPTURE_GATE: base={BASE} bytes={SIZE}"
RELEASED = "AURORA_DISPLAY_CAPTURE_RELEASED"
READY = "AURORA_DISPLAY_SESSION_READY: width=800 height=600"
MODES = ("framebuffer", "framebuffer-record", "framebuffer-permissions", "framebuffer-stale")


def need(condition, reason):
    if not condition:
        raise ValueError(reason)


def ppm_rgb(width, height, pitch, pixel_format, pixels):
    rgb = bytearray()
    for y in range(height):
        for x in range(width):
            offset = (y * pitch + x) * 4
            a, g, c, _ = pixels[offset : offset + 4]
            rgb.extend((a, g, c) if pixel_format == 0 else (c, g, a))
    return bytes(rgb)


def fnv1a(data):
    value = 0xCBF29CE484222325
    for byte in data:
        value = ((value ^ byte) * 0x100000001B3) & ((1 << 64) - 1)
    return value


def golden():
    """The renderer's (stores, digest) for this geometry, over its 32-byte guards and page-rounded buffer."""
    for line in GOLDEN.read_text().splitlines():
        arguments, _, result = line.partition("\t")
        if arguments == f"{WIDTH} {HEIGHT} {PITCH} 1":
            match = re.fullmatch(r"exit 0 \| stdout: stores=(\d+) bytes=(\d+) digest=([0-9a-f]+)", result)
            need(match is not None and int(match[2]) == SIZE + 64, "renderer golden geometry")
            return int(match[1]), int(match[3], 16)
    raise ValueError("renderer golden lacks the fixture geometry")


def parse_ppm(data):
    # QEMU's exact P6 writer, deliberately no permissive image conversion.
    match = re.match(rb"P6\n(\d+) (\d+)\n255\n", data)
    need(match is not None, "malformed PPM header")
    need(tuple(map(int, match.groups())) == (WIDTH, HEIGHT), "screenshot geometry")
    body = data[match.end() :]
    need(len(body) == WIDTH * HEIGHT * 3, "screenshot byte extent")
    return body


def serial_lines(raw, mode):
    need(len(raw) <= 1024 * 1024, "serial limit")
    text = raw.decode("ascii", errors="strict").replace("\r", "")
    need(text.endswith("\n"), "incomplete serial line")
    # The display fixture echoes the mode's fw_cfg row right after loader entry.
    return loader_selection(text, mode).splitlines()


def validate_serial(raw, mode, gate_only=False):
    need(mode in MODES, "unknown case")
    lines = serial_lines(raw, mode)
    prefixes = (
        "AURORA_UEFI_ENTRY",
        "AURORA_UEFI_EXIT_OK:",
        "AURORA_UEFI_PAYLOAD_ENTRY",
        "AURORA_UEFI_OWNERSHIP_OK:",
        "AURORA_UEFI_PROTECTION_OK:",
        "AURORA_DISPLAY_CAPTURE_GATE:",
    )
    positions = []
    for prefix in prefixes:
        matches = [n for n, line in enumerate(lines) if line.startswith(prefix)]
        need(len(matches) == 1, "missing/duplicate " + prefix)
        positions.append(matches[0])
    need(positions == sorted(positions), "boot stage order")
    need(
        lines[positions[0]] == "AURORA_UEFI_ENTRY"
        and lines[positions[1]] == "AURORA_UEFI_EXIT_OK: attempts=1"
        and lines[positions[2]] == "AURORA_UEFI_PAYLOAD_ENTRY",
        "malformed entry/exit marker",
    )
    owned = re.fullmatch(r"AURORA_UEFI_OWNERSHIP_OK: arena=(\d+) bytes=(\d+) descriptors=(\d+)", lines[positions[3]])
    protected = re.fullmatch(r"AURORA_UEFI_PROTECTION_OK: root=(\d+) stack=(\d+)", lines[positions[4]])
    need(owned is not None and protected is not None, "malformed ownership/protection marker")
    arena, size, count = map(int, owned.groups())
    root, stack = map(int, protected.groups())
    need(
        arena >= 0x100000
        and arena % 4096 == 0
        and size == 0x100000
        and arena + size <= 0x100000000
        and 1 <= count <= 512,
        "invalid arena/map",
    )
    need(
        root == arena + 0x11000 and arena + LAYOUT.kernel_stack_bottom <= stack < arena + LAYOUT.kernel_stack_top,
        "inherited root/stack",
    )
    need(lines[positions[-1]] == GATE, "gate geometry")
    need(
        all(line.startswith(prefixes + ("AURORA_DISPLAY_",)) for line in lines if "AURORA_" in line),
        "unexpected Aurora marker",
    )
    need(
        not any(
            "_FAIL" in x or "EXCEPTION" in x or "EXIT_REJECTED" in x
            for x in lines
            if not x.startswith("AURORA_DISPLAY_FAIL:")
        ),
        "unexpected guest failure",
    )
    display = [line for line in lines if line.startswith("AURORA_DISPLAY_")]
    if gate_only:
        need(display == [GATE], "pre-release output/order")
        return
    wanted = [GATE, RELEASED]
    if mode in ("framebuffer", "framebuffer-stale"):
        wanted.append(READY)
    if mode == "framebuffer":
        wanted.append(f"AURORA_DISPLAY_FRAME_COMPLETE: base={BASE} bytes={SIZE} stores=484711")
    else:
        wanted.append("AURORA_DISPLAY_FAIL: stores=0")
    need(display == wanted, "display stage/order/stores mismatch")
    need(lines[-1] == wanted[-1], "output after terminal marker")


def validate_capture(mode, baseline, after, screenshot, baseline_screenshot):
    need(mode in MODES, "unknown case")
    need(len(baseline) == SIZE and len(after) == SIZE, "physical capture extent")
    before_rgb = parse_ppm(baseline_screenshot)
    actual_rgb = parse_ppm(screenshot)
    need(before_rgb == ppm_rgb(WIDTH, HEIGHT, PITCH, 1, baseline), "baseline scanout mismatch")
    need(actual_rgb == ppm_rgb(WIDTH, HEIGHT, PITCH, 1, after), "physical/screenshot mismatch")
    if mode == "framebuffer":
        stores, digest = golden()
        guarded = b"\xa5" * 32 + after[:VISIBLE] + b"\xa5" * (SIZE - VISIBLE + 32)
        need(fnv1a(guarded) == digest, "visible BGR32 pixels differ from the native renderer")
        need(after[VISIBLE:] == baseline[VISIBLE:], "1024-byte resource tail modified")
    else:
        stores = 0
        need(after == baseline, "rejected case wrote framebuffer resource")
    return dict(
        stores=stores,
        physical_bytes=SIZE,
        unchanged_tail_bytes=1024,
        screenshot_rgb_sha256=hashlib.sha256(actual_rgb).hexdigest(),
        native_row_padding=False,
    )
