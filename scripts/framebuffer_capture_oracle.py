"""Fail-closed oracle for the admitted 800x600 BGR32 emulator fixture.

No production font or packing helper is imported. The existing independent
row-pattern scene oracle is separately pinned by the capture manifest.
"""

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from kernel_display_oracle import reference, ppm_rgb

BASE, SIZE, WIDTH, HEIGHT, PITCH = 0x80000000, 1921024, 800, 600, 800
VISIBLE = WIDTH * HEIGHT * 4
GATE = f"AURORA_DISPLAY_CAPTURE_GATE: base={BASE} bytes={SIZE}"
RELEASED = "AURORA_DISPLAY_CAPTURE_RELEASED"
READY = "AURORA_DISPLAY_SESSION_READY: width=800 height=600"
MODES = ("framebuffer", "framebuffer-record", "framebuffer-permissions", "framebuffer-stale")


def need(condition, reason):
    if not condition:
        raise ValueError(reason)


def expected():
    raw, stores = reference(WIDTH, HEIGHT, PITCH, 1, guard=False)
    rgb = ppm_rgb(WIDTH, HEIGHT, PITCH, 1, raw)
    need(stores == 484711, "independent store count drift")
    need(
        hashlib.sha256(rgb).hexdigest() == "aa54951e2adf263c9e1c8abe47f85b03165f97cdbb6dd5a6bb8c3d01fc61d74e",
        "independent scene drift",
    )
    return raw[:VISIBLE], rgb, stores


def parse_ppm(data):
    # QEMU's exact P6 writer, deliberately no permissive image conversion.
    match = re.match(rb"P6\n(\d+) (\d+)\n255\n", data)
    need(match is not None, "malformed PPM header")
    need(tuple(map(int, match.groups())) == (WIDTH, HEIGHT), "screenshot geometry")
    body = data[match.end() :]
    need(len(body) == WIDTH * HEIGHT * 3, "screenshot byte extent")
    return body


def serial_lines(raw):
    need(len(raw) <= 1024 * 1024, "serial limit")
    text = raw.decode("ascii", errors="strict").replace("\r", "")
    need(text.endswith("\n"), "incomplete serial line")
    return text.splitlines()


def validate_serial(raw, mode, gate_only=False):
    need(mode in MODES, "unknown case")
    lines = serial_lines(raw)
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
    need(root == arena + 0x11000 and arena + 0x44000 <= stack < arena + 0x48000, "inherited root/stack")
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
        desired, rgb, stores = expected()
        need(after[:VISIBLE] == desired, "visible BGR32 pixel mismatch")
        need(actual_rgb == rgb, "screenshot scene mismatch")
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
