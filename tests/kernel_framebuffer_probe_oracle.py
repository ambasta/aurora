"""Independent serial oracle for the non-rendering firmware aperture probe."""

import re

PROBE = re.compile(
    r"AURORA_FRAMEBUFFER_MAP_PROBE: attempt=(\d+) base=(\d+) resource=(\d+) mapped=(\d+) "
    r"described=([01]) width=(\d+) height=(\d+) pitch=(\d+) format=([01]) physical_bits=(\d+) "
    r"mode=(\d+) mode_count=(\d+)"
)
OVERLAP = re.compile(r"AURORA_FRAMEBUFFER_MAP_OVERLAP: type=(\d+) begin=(\d+) end=(\d+) attrs=(\d+)")
PRIVATE = re.compile(
    r"AURORA_FRAMEBUFFER_PROBE_PRIVATE_PAGING: width=(\d+) height=(\d+) pitch=(\d+) format=([01]) tables=(\d+)"
)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def validate(status, text):
    require(status == 33, "expected debug-exit 33")
    require("AURORA_UEFI_FAIL" not in text and "AURORA_UEFI_EXCEPTION" not in text, "guest failure")
    lines = text.replace("\r", "").splitlines()
    for marker in (
        "AURORA_UEFI_ENTRY",
        "AURORA_UEFI_EXIT_OK:",
        "AURORA_UEFI_PAYLOAD_ENTRY",
        "AURORA_UEFI_OWNERSHIP_OK:",
        "AURORA_UEFI_PROTECTION_OK:",
        "AURORA_FRAMEBUFFER_PROBE_PRIVATE_PAGING:",
    ):
        require(sum(line.startswith(marker) for line in lines) == 1, "missing/duplicate " + marker)
    exit_position = next(i for i, line in enumerate(lines) if line.startswith("AURORA_UEFI_EXIT_OK:"))
    observations = []
    for position, line in enumerate(lines):
        if line.startswith("AURORA_FRAMEBUFFER_MAP_PROBE:"):
            match = PROBE.fullmatch(line)
            require(match is not None, "malformed probe")
            values = list(map(int, match.groups()))
            attempt, base, size, mapped, described, width, height, pitch, fmt, bits, mode, count = values
            require(attempt == len(observations) + 1 and attempt <= 3, "attempt sequence")
            require(32 <= bits <= 52 and base > 0 and base % 4096 == 0, "base/physical width")
            require(size > 0 and base + size <= 2**bits, "resource extent")
            require(1 <= width <= 1024 and 1 <= height <= 768 and width <= pitch <= 1024, "geometry bounds")
            require(mapped == ((pitch * height * 4 + 4095) // 4096) * 4096, "rounded visible extent")
            require(mapped <= size and mapped <= 3145728 and 0 <= mode < count <= 64, "resource/mode bounds")
            observations.append(dict(position=position, values=values, overlaps=[]))
        elif line.startswith("AURORA_FRAMEBUFFER_MAP_OVERLAP:"):
            match = OVERLAP.fullmatch(line)
            require(match is not None and observations and position < exit_position, "malformed/unbound overlap")
            kind, begin, end, attributes = map(int, match.groups())
            _, base, _, mapped, _, _, _, _, _, bits, _, _ = observations[-1]["values"]
            require(0 <= kind <= 15 and begin % 4096 == 0 and end % 4096 == 0, "descriptor type/alignment")
            require(begin < end <= 2**bits and begin < base + mapped and base < end, "descriptor intersection")
            require(attributes < 2**64, "descriptor attributes")
            for old in observations[-1]["overlaps"]:
                require(end <= old[1] or old[2] <= begin, "overlapping map descriptors")
            observations[-1]["overlaps"].append((kind, begin, end, attributes))
    require(observations, "missing map observations")
    exit_line = next(line for line in lines if line.startswith("AURORA_UEFI_EXIT_OK:"))
    exit_match = re.fullmatch(r"AURORA_UEFI_EXIT_OK: attempts=(\d+)", exit_line)
    require(exit_match is not None and int(exit_match[1]) == len(observations), "exit attempt mismatch")
    rejects = [line for line in lines if line.startswith("AURORA_UEFI_EXIT_REJECTED:")]
    require(
        rejects == [f"AURORA_UEFI_EXIT_REJECTED: attempt={n}" for n in range(1, len(observations))], "retry sequence"
    )
    for n, observation in enumerate(observations[:-1]):
        reject_position = lines.index(f"AURORA_UEFI_EXIT_REJECTED: attempt={n + 1}")
        require(observation["position"] < reject_position < observations[n + 1]["position"], "retry stage order")
    for observation in observations[1:]:
        require(
            observation["values"][1:4] == observations[0]["values"][1:4]
            and observation["values"][5:] == observations[0]["values"][5:],
            "mode changed during retry",
        )
    private_line = next(line for line in lines if line.startswith("AURORA_FRAMEBUFFER_PROBE_PRIVATE_PAGING:"))
    private = PRIVATE.fullmatch(private_line)
    require(private is not None, "malformed private geometry")
    width, height, pitch, fmt, tables = map(int, private.groups())
    final = observations[-1]
    require([width, height, pitch, fmt] == final["values"][5:9] and 5 <= tables <= 16, "private geometry/table budget")
    markers = [
        "AURORA_UEFI_ENTRY",
        "AURORA_FRAMEBUFFER_MAP_PROBE:",
        "AURORA_UEFI_EXIT_OK:",
        "AURORA_UEFI_PAYLOAD_ENTRY",
        "AURORA_UEFI_OWNERSHIP_OK:",
        "AURORA_UEFI_PROTECTION_OK:",
        "AURORA_FRAMEBUFFER_PROBE_PRIVATE_PAGING:",
    ]
    positions = [next(i for i, line in enumerate(lines) if line.startswith(marker)) for marker in markers]
    require(positions == sorted(positions) and final["position"] < positions[2], "stage order")
    for observation in observations:
        _, base, _, mapped, described, *_ = observation["values"]
        overlap_bytes = sum(min(end, base + mapped) - max(begin, base) for _, begin, end, _ in observation["overlaps"])
        allowed = all(
            kind in (0, 11) and attributes & ~0x4001 == 0 for kind, _, _, attributes in observation["overlaps"]
        )
        if described:
            require(overlap_bytes == mapped and allowed, "claimed strict coverage not established")
        observation["mapped_overlap_bytes"] = overlap_bytes
        observation["aperture_absent_from_map"] = not observation["overlaps"]
    return dict(observations=observations, private_tables=tables)


def self_test():
    text = (
        "AURORA_UEFI_ENTRY\n"
        "AURORA_FRAMEBUFFER_MAP_PROBE: attempt=1 base=3221225472 resource=2097152 mapped=1921024 "
        "described=0 width=800 height=600 pitch=800 format=0 physical_bits=36 mode=0 mode_count=2\n"
        "AURORA_UEFI_EXIT_OK: attempts=1\nAURORA_UEFI_PAYLOAD_ENTRY\n"
        "AURORA_UEFI_OWNERSHIP_OK: arena=1000000\nAURORA_UEFI_PROTECTION_OK: root=1000000\n"
        "AURORA_FRAMEBUFFER_PROBE_PRIVATE_PAGING: width=800 height=600 pitch=800 format=0 tables=8\n"
    )
    validate(33, text)
    bad = [
        text.replace("width=800", "width=801", 1),
        text.replace("mapped=1921024", "mapped=1920000"),
        text.replace("attempt=1", "attempt=2", 1),
        text.replace("attempts=1", "attempts=2"),
        text.replace("described=0", "described=1"),
        text.replace("mode_count=2", "mode_count=0"),
        text.replace("tables=8", "tables=17"),
        text + "AURORA_UEFI_ENTRY\n",
        text.replace("physical_bits=36", "physical_bits=31"),
        "AURORA_UEFI_FAIL: injected\n" + text,
    ]
    for sample in bad:
        try:
            validate(33, sample)
        except ValueError:
            continue
        raise AssertionError("oracle accepted malformed evidence")
    try:
        validate(0, text)
    except ValueError:
        pass
    else:
        raise AssertionError("oracle accepted wrong exit")
    print("PASS: independent framebuffer probe oracle, positive + 11 negative cases")


if __name__ == "__main__":
    self_test()
