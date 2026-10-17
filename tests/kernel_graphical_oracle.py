"""Independent model for the bounded graphical-console hosted gate.

No production editor, packed font, drawing, clipping or pixel-packing imports.
Visual row specifications are reviewed separately from production bit constants.
Frames are 408x18 raw viewport bytes; pixels is the complete final guarded buffer.
The earlier 67-case hosted result has its own source/evidence scope.
This model and its registration are not an image, guest or aggregate receipt.
"""

FONT = {
    " ": "00000/00000/00000/00000/00000/00000/00000",
    "A": "01110/10001/10001/11111/10001/10001/10001",
    "B": "11110/10001/10001/11110/10001/10001/11110",
    "C": "01111/10000/10000/10000/10000/10000/01111",
    "D": "11110/10001/10001/10001/10001/10001/11110",
    "E": "11111/10000/10000/11110/10000/10000/11111",
    "F": "11111/10000/10000/11110/10000/10000/10000",
    "G": "01111/10000/10000/10111/10001/10001/01111",
    "H": "10001/10001/10001/11111/10001/10001/10001",
    "I": "11111/00100/00100/00100/00100/00100/11111",
    "J": "00111/00010/00010/00010/10010/10010/01100",
    "K": "10001/10010/10100/11000/10100/10010/10001",
    "L": "10000/10000/10000/10000/10000/10000/11111",
    "M": "10001/11011/10101/10101/10001/10001/10001",
    "N": "10001/11001/11001/10101/10011/10011/10001",
    "O": "01110/10001/10001/10001/10001/10001/01110",
    "P": "11110/10001/10001/11110/10000/10000/10000",
    "Q": "01110/10001/10001/10001/10101/10010/01101",
    "R": "11110/10001/10001/11110/10100/10010/10001",
    "S": "01111/10000/10000/01110/00001/00001/11110",
    "T": "11111/00100/00100/00100/00100/00100/00100",
    "U": "10001/10001/10001/10001/10001/10001/01110",
    "V": "10001/10001/10001/10001/10001/01010/00100",
    "W": "10001/10001/10001/10101/10101/11011/10001",
    "X": "10001/10001/01010/00100/01010/10001/10001",
    "Y": "10001/10001/01010/00100/00100/00100/00100",
    "Z": "11111/00001/00010/00100/01000/10000/11111",
    "0": "01110/10001/10011/10101/11001/10001/01110",
    "1": "00100/01100/00100/00100/00100/00100/01110",
    "2": "01110/10001/00001/00010/00100/01000/11111",
    "3": "11110/00001/00001/01110/00001/00001/11110",
    "4": "00010/00110/01010/10010/11111/00010/00010",
    "5": "11111/10000/10000/11110/00001/00001/11110",
    "6": "01110/10000/10000/11110/10001/10001/01110",
    "7": "11111/00001/00010/00100/01000/01000/01000",
    "8": "01110/10001/10001/01110/10001/10001/01110",
    "9": "01110/10001/10001/01111/00001/00001/01110",
    ":": "00000/00100/00100/00000/00100/00100/00000",
    "-": "00000/00000/00000/11111/00000/00000/00000",
    "a": "00000/00000/01110/00001/01111/10001/01111",
    "b": "10000/10000/11110/10001/10001/10001/11110",
    "c": "00000/00000/01111/10000/10000/10000/01111",
    "d": "00001/00001/01111/10001/10001/10001/01111",
    "e": "00000/00000/01110/10001/11111/10000/01111",
    "f": "00110/01000/01000/11100/01000/01000/01000",
    "g": "00000/01111/10001/10001/01111/00001/01110",
    "h": "10000/10000/11110/10001/10001/10001/10001",
    "i": "00100/00000/01100/00100/00100/00100/01110",
    "j": "00010/00000/00110/00010/00010/10010/01100",
    "k": "10000/10000/10001/10010/11100/10010/10001",
    "l": "01100/00100/00100/00100/00100/00100/01110",
    "m": "00000/00000/11010/10101/10101/10001/10001",
    "n": "00000/00000/11110/10001/10001/10001/10001",
    "o": "00000/00000/01110/10001/10001/10001/01110",
    "p": "00000/00000/11110/10001/11110/10000/10000",
    "q": "00000/00000/01111/10001/01111/00001/00001",
    "r": "00000/00000/10110/11001/10000/10000/10000",
    "s": "00000/00000/01111/10000/01110/00001/11110",
    "t": "01000/01000/11100/01000/01000/01001/00110",
    "u": "00000/00000/10001/10001/10001/10011/01101",
    "v": "00000/00000/10001/10001/10001/01010/00100",
    "w": "00000/00000/10001/10001/10101/10101/01010",
    "x": "00000/00000/10001/01010/00100/01010/10001",
    "y": "00000/00000/10001/10001/01111/00001/01110",
    "z": "00000/00000/11111/00010/00100/01000/11111",
    "!": "00100/00100/00100/00100/00100/00000/00100",
    '"': "01010/01010/01010/00000/00000/00000/00000",
    "#": "01010/11111/01010/01010/11111/01010/00000",
    "$": "00100/01111/10100/01110/00101/11110/00100",
    "%": "11000/11001/00010/00100/01000/10011/00011",
    "&": "01100/10010/01100/10101/10010/10010/01101",
    "'": "00100/00100/01000/00000/00000/00000/00000",
    "(": "00010/00100/01000/01000/01000/00100/00010",
    ")": "01000/00100/00010/00010/00010/00100/01000",
    "*": "00000/10101/01110/11111/01110/10101/00000",
    "+": "00000/00100/00100/11111/00100/00100/00000",
    ",": "00000/00000/00000/00000/00000/00100/01000",
    ".": "00000/00000/00000/00000/00000/00000/00100",
    "/": "00001/00001/00010/00100/01000/10000/10000",
    ";": "00000/00100/00000/00000/00100/00100/01000",
    "<": "00001/00010/00100/01000/00100/00010/00001",
    "=": "00000/00000/11111/00000/11111/00000/00000",
    ">": "10000/01000/00100/00010/00100/01000/10000",
    "?": "01110/10001/00001/00010/00100/00000/00100",
    "@": "01110/10001/10111/10101/10111/10000/01111",
    "[": "01110/01000/01000/01000/01000/01000/01110",
    "\\": "10000/10000/01000/00100/00010/00001/00001",
    "]": "01110/00010/00010/00010/00010/00010/01110",
    "^": "00100/01010/10001/00000/00000/00000/00000",
    "_": "00000/00000/00000/00000/00000/00000/11111",
    "`": "01000/00100/00000/00000/00000/00000/00000",
    "{": "00010/00100/00100/01000/00100/00100/00010",
    "|": "00100/00100/00100/00100/00100/00100/00100",
    "}": "01000/00100/00100/00010/00100/00100/01000",
    "~": "00000/00000/01001/10110/00000/00000/00000",
}

RESPONSES = {
    b"help": "copy S D; write N TEXT; cat N; ls; rm N; help status exit",
    b"status": "Boot self-tests passed; UEFI; timer polling; line capacity=64",
    b"exit": "AURORA_CONSOLE_EXIT",
    b"": " ",
}
READY = "AURORA graphical console: help for commands"
REJECTED = "Line rejected: too long, non-ASCII/control byte, or UART error."
UNKNOWN = "Unknown command. Type help."
BOUNDED = "INPUT BUDGET EXHAUSTED"


def byte_samples(data):
    return [(1, byte, 0) for byte in data]


def file_response(command, slots):
    """Model the named-file commands with four optional (name, contents) pairs.

    The legacy note is dispatched separately by the console. Validation finishes
    before any directory change, and replacement preserves its existing slot.
    """
    if command == b"ls":
        names = [entry[0].decode("ascii") for entry in slots if entry is not None]
        return "files:" + "".join(" " + name for name in names) if names else "files: empty (RAM-only)."
    operation, separated, argument = command.partition(b" ")
    if operation == b"copy":
        names = argument.split(b" ")
        allowed = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-"
        if (
            not separated
            or len(names) != 2
            or any(
                not 1 <= len(name) <= 8 or name in (b".", b"..") or any(byte not in allowed for byte in name)
                for name in names
            )
        ):
            return "files: invalid name or content."
        source, destination = names
        if b"note" in names:
            return "files: note is reserved."
        contents = next((entry[1] for entry in slots if entry is not None and entry[0] == source), None)
        if contents is None:
            return "files: not found (RAM-only)."
        target = next((i for i, entry in enumerate(slots) if entry is not None and entry[0] == destination), None)
        if target is None:
            target = next((i for i, entry in enumerate(slots) if entry is None), None)
        if target is None:
            return "files: full (4 files)."
        slots[target] = (destination, contents)
        return f"wrote {destination.decode('ascii')}: {len(contents)} byte" + ("s" if len(contents) != 1 else "")
    if operation not in (b"write", b"cat", b"rm", b"ls"):
        return UNKNOWN
    if not separated or operation == b"ls":
        return "files: invalid name or content."
    name = argument
    contents = b""
    if operation == b"write":
        name, separated, contents = argument.partition(b" ")
    allowed = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-"
    if (
        not separated
        or not 1 <= len(name) <= 8
        or name in (b".", b"..")
        or any(byte not in allowed for byte in name)
        or len(contents) > 49
        or any(not 32 <= byte <= 126 for byte in contents)
    ):
        return "files: invalid name or content."
    if name == b"note":
        return "files: note is reserved."
    found = next((index for index, entry in enumerate(slots) if entry is not None and entry[0] == name), None)
    if operation == b"write":
        if found is None:
            found = next((index for index, entry in enumerate(slots) if entry is None), None)
        if found is None:
            return "files: full (4 files)."
        slots[found] = (name, contents)
        return f"wrote {name.decode('ascii')}: {len(contents)} byte" + ("s" if len(contents) != 1 else "")
    if found is None:
        return "files: not found (RAM-only)."
    if operation == b"cat":
        return slots[found][1].decode("ascii")
    slots[found] = None
    return "files: removed (RAM-only)."


def reference(
    samples, width=800, height=600, pitch=800, pixel_format=1, fail_after=None, sessions=1, initial_pixels=None
):
    """Model completed paints and ordered writes, without executing any source.

    Input exhaustion is an oracle error; production next() blocks rather than
    inventing EOF. Clean absent samples are likewise not copied to Aurora by the
    real Session and are excluded here. Offset/value store pairs exclude guards.
    Failure is a recoverable host pixel status after exactly fail_after stores.
    Two-session reset checks retain framebuffer bytes while resetting application
    state; failure injection is kept in the existing single-session cases.
    """
    samples = list(samples)
    if pitch < width or pitch > 1024 or pixel_format not in (0, 1):
        raise ValueError("Invalid test framebuffer")
    mapped = ((pitch * height * 4 + 4095) // 4096) * 4096
    if sessions not in (1, 2) or (sessions == 2 and fail_after is not None):
        raise ValueError("Expected one session, or two sessions without failure injection")
    pixels = bytearray(b"\xa5") * (mapped + 64) if initial_pixels is None else bytearray(initial_pixels)
    if len(pixels) != mapped + 64:
        raise ValueError("Initial framebuffer size mismatch")
    frames, stores, frame_stores = [], [], []
    consumed = 0

    def capture():
        return (
            b"".join(pixels[32 + (y * pitch + 32) * 4 : 32 + (y * pitch + 440) * 4] for y in range(128, 146))
            if width >= 440 and height >= 146
            else b""
        )

    def finish(completion):
        frames.append(capture())
        frame_stores.append(len(stores))
        if sessions == 2:
            if completion != 0:
                raise ValueError("First reset session must exit normally")
            following = reference(samples[consumed:], width, height, pitch, pixel_format, initial_pixels=pixels)
            return dict(
                following,
                consumed=consumed + following["consumed"],
                frames=frames + following["frames"],
                stores=stores + following["stores"],
                frame_stores=frame_stores + [len(stores) + n for n in following["frame_stores"]],
            )
        return {
            "completion": completion,
            "consumed": consumed,
            "frames": frames,
            "stores": stores,
            "frame_stores": frame_stores,
            "pixels": bytes(pixels),
        }

    if not (440 <= width <= 1024 and 146 <= height <= 768):
        return finish(3)

    class PixelFailure(Exception):
        pass

    def plot(x, y, rgb):
        if not (0 <= x < width and 0 <= y < height):
            return
        if fail_after is not None and len(stores) == fail_after:
            raise PixelFailure
        r, g, b = rgb
        packed = bytes((r, g, b, 0) if pixel_format == 0 else (b, g, r, 0))
        offset = (y * pitch + x) * 4
        stores.append((offset, int.from_bytes(packed, "little")))
        pixels[32 + offset : 36 + offset] = packed

    def paint_cell(index, char, cursor_here):
        x, y = 32 + (index % 68) * 6, 128 + (index // 68) * 9
        for dy in range(9):
            for dx in range(6):
                plot(x + dx, y + dy, (13, 20, 32))
        for dy, row in enumerate(FONT[char].split("/")):
            for dx, bit in enumerate(row):
                if bit == "1":
                    plot(x + dx, y + dy, (204, 226, 235))
        if cursor_here:
            for dx in range(5):
                plot(x + dx, y + 7, (52, 188, 220))

    desired = list("> " + " " * 66 + READY.ljust(68))
    committed = None
    cursor, previous_cursor = 2, -1
    line = bytearray()
    rejected, previous_cr = False, False
    event_count = 0
    terminal = None
    note = None
    files = [None] * 4

    def respond(text):
        nonlocal desired, cursor
        if len(text) > 68:
            raise AssertionError("Response exceeds viewport")
        desired = list("> " + " " * 66 + text.ljust(68))
        cursor = 2

    while True:
        try:
            for index, char in enumerate(desired):
                if (
                    committed is None
                    or committed[index] != char
                    or (cursor != previous_cursor and index in (cursor, previous_cursor))
                ):
                    paint_cell(index, char, index == cursor)
        except PixelFailure:
            return finish(2)
        committed = desired.copy()
        previous_cursor = cursor
        if terminal is not None:
            return finish(terminal)
        if event_count == 80 or consumed == 96:
            respond(BOUNDED)
            cursor, terminal = -1, 1
            continue
        frames.append(capture())
        frame_stores.append(len(stores))
        if consumed >= len(samples):
            raise ValueError("Script exhausted while native next() would still wait")
        present, byte, damaged = samples[consumed]
        if present not in (0, 1) or damaged not in (0, 1) or not 0 <= byte <= 255 or (not present and byte):
            raise ValueError("Noncanonical samples require a separate malformed-host gate")
        if not present and not damaged:
            raise ValueError("Production Session filters absent undamaged UART polls")
        consumed += 1
        rejected |= bool(damaged)
        if not present:
            continue
        event_count += 1
        suppress = previous_cr and byte == 10
        previous_cr = byte == 13
        if suppress:
            continue
        if byte in (10, 13):
            command = bytes(line)
            response = REJECTED if rejected else RESPONSES.get(command, UNKNOWN)
            if not rejected:
                if command == b"cat note":
                    response = "note: not found (RAM-only)." if note is None else note.decode("ascii")
                elif command.startswith(b"write note "):
                    note = command[11:]
                    response = "note: RAM-only; lost when session exits."
                elif command not in RESPONSES:
                    response = file_response(command, files)
            respond(response)
            if not rejected and command == b"exit":
                cursor, terminal = -1, 0
            line.clear()
            rejected = False
        elif not rejected:
            if byte in (8, 127):
                if line:
                    line.pop()
                    cursor -= 1
                    desired[cursor] = " "
            elif not 32 <= byte <= 126 or len(line) == 64:
                rejected = True
            else:
                line.append(byte)
                desired[cursor] = chr(byte)
                cursor += 1
