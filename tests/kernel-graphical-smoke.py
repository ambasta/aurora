#!/usr/bin/env python3
"""Compiler-free parser, pixel, choreography and cleanup controls; never guests."""

from contextlib import contextmanager
import copy
import io
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import kernel_graphical_smoke as smoke
from kernel_graphical_oracle import file_response


def transcript(rows):
    lines = [
        "AURORA_UEFI_ENTRY\r\nAURORA_UEFI_EXIT_OK: attempts=1\r\nAURORA_UEFI_PAYLOAD_ENTRY\r\n"
        "AURORA_UEFI_OWNERSHIP_OK: arena=16777216 bytes=1048576 descriptors=111\r\n"
        "AURORA_UEFI_PROTECTION_OK: root=16846848 stack=17068032\r\n"
        "AURORA_UEFI_LANGUAGE_OK: value=42\r\nAURORA_UEFI_OK\r\n"
    ]
    for kind, row in rows:
        reason = row.get("reason", "")
        body = " ".join(f"{key}={value}" for key, value in row.items() if key != "reason")
        lines.append(smoke.PREFIX + kind + ": " + (reason + " " if reason else "") + body + "\r\n")
    return "".join(lines).encode()


def expected(case):
    name, selector, data = case
    model = smoke.reference(smoke.byte_samples(data or b"exit\r"), fail_after={b"F": 0, b"I": 55}.get(selector))
    rows = [("CAPTURE_GATE", dict(base=smoke.BASE, bytes=smoke.SIZE))]
    if selector != b"?":
        rows += [("CAPTURE_RELEASED", dict(selector=b"GCDcdFI".index(selector) + 1))]
    idle = name == "idle4096"
    if selector == b"G":
        rows += [
            ("PRE_SAMPLE", dict(completed=n, stores=model["frame_stores"][n]))
            for n in ([0] if idle else range(model["consumed"]))
        ]
    if selector in (b"?", b"C", b"D", b"c", b"d"):
        terminal = dict.fromkeys(smoke.FIELDS["CONSOLE_FAIL"], 0)
        terminal["reason"] = "capture selector" if selector == b"?" else "paired service authority"
        rows += [("CONSOLE_FAIL", terminal)]
    elif idle:
        stores = model["frame_stores"][0]
        rows += [
            (
                "CONSOLE_FAIL",
                dict(
                    entries=1,
                    samples=4097,
                    output_attempts=0,
                    stores=stores,
                    completed=0,
                    wakes=4096,
                    pixel_attempts=stores,
                    reason="NATIVE_IDLE_WAKE_DEADLINE: limit=4096",
                ),
            )
        ]
    else:
        stores = len(model["stores"])
        rows += [
            (
                "CONSOLE_COMPLETE",
                dict(
                    completion=model["completion"],
                    wakes=0 if selector in (b"F", b"I") else 2,
                    stores=stores,
                    entries=1,
                    samples=model["consumed"] + (0 if selector in (b"F", b"I") else 2),
                    output_attempts=0,
                    completed=model["consumed"],
                    pixel_attempts=stores + (model["completion"] == 2),
                ),
            )
        ]
    return model, rows


class Controls(unittest.TestCase):
    def test_shell_keeps_native_profiles_and_finishes_run(self):
        import time

        builder = """#!/usr/bin/env bash
set -eu
echo "build:$UEFI_MODE" >> events
out="$PWD/build/native profiles/$UEFI_MODE"
mkdir -p "$out/esp/EFI/BOOT" "$out/objects"
echo "$UEFI_MODE" > "$out/esp/EFI/BOOT/BOOTX64.EFI"
touch "$out/objects/payload.o"
[[ ${FAIL_BUILD:-} != "$UEFI_MODE" ]] || exit 17
if [[ ${INTERRUPT_AT:-} == "build:$UEFI_MODE" ]]; then
    sleep 0.2
    echo 'late-builder-write' > "$out/esp/EFI/BOOT/BOOTX64.EFI"
fi
printf '%s\\n' "$out"
"""
        runner = """import os, pathlib, signal, sys, time
p = pathlib.Path
args = sys.argv
if any(flag in args for flag in ('--start-run', '--finish-run')):
    sys.path.insert(0, REAL_SCRIPTS)
    import kernel_graphical_smoke as real
    real.ROOT = p.cwd()
    real.main()
    sys.exit()
if '--stage' in args:
    mode = args[args.index('--stage') + 1]
    out = p(args[args.index('--images') + 1]) / mode
    out.mkdir(parents=True)
    (out / 'image').write_bytes((p(args[args.index('--build-dir') + 1]) / 'esp/EFI/BOOT/BOOTX64.EFI').read_bytes())
    action = 'stage:' + mode
else:
    image = p(args[args.index('--images') + 1]) / 'normal/image'
    assert image.read_bytes() == b'normal\\n'
    evidence = p(args[args.index('--evidence') + 1])
    (evidence / 'production').mkdir(parents=True)
    (evidence / 'production/state-00.bin').write_bytes(b'physical capture')
    (evidence / 'production/state-00.ppm').write_bytes(b'screen capture')
    (evidence / 'production/serial.log').write_bytes(b'guest serial')
    if os.environ.get('GUEST_PIN'): (evidence.parent / '.keep').touch()
    action = 'guest'
with open('events', 'a') as f: f.write(action + '\\n')
if os.environ.get('INTERRUPT_AT') == action:
    time.sleep(0.2)
    with open('events', 'a') as f: f.write('child-finished\\n')
if os.environ.get('FAIL_STAGE') == action: sys.exit(23)
if action == 'guest':
    with open('events', 'a') as f: f.write('staged-normal-boot\\n')
    sys.exit(int(os.environ.get('GUEST_STATUS', '0')))
"""
        runner = runner.replace("REAL_SCRIPTS", repr(str(ROOT / "scripts")))
        cases = [
            ([], {}, 0),
            ([], {"AURORA_GRAPHICAL_KEEP_RUNS": "all"}, 0),
            ([], {"GUEST_PIN": "1"}, 0),
            (["--build-only"], {}, 0),
            ([], {"FAIL_BUILD": "normal"}, 17),
            ([], {"FAIL_BUILD": "graphical-console-capture"}, 17),
            ([], {"FAIL_STAGE": "stage:graphical-console"}, 23),
            ([], {"GUEST_STATUS": "31"}, 31),
            (["--invalid"], {}, 2),
        ]
        for path in ("build", "build/uefi", "build/graphical-smoke"):
            cases.append(([], {"SYMLINK": path}, 2))
        for action in ("build:graphical-console", "stage:graphical-console", "guest"):
            for sig, status in (("INT", 130), ("TERM", 143)):
                cases.append(([], {"INTERRUPT_AT": action, "INTERRUPT_SIGNAL": sig}, status))
        for arguments, overrides, status in cases:
            with self.subTest(arguments=arguments, overrides=overrides), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "scripts").mkdir()
                if "SYMLINK" in overrides:
                    (root / "outside").mkdir()
                    (root / "outside/sentinel").write_bytes(b"unchanged")
                    link = root / overrides["SYMLINK"]
                    link.parent.mkdir(parents=True, exist_ok=True)
                    link.symlink_to(root / "outside", target_is_directory=True)
                elif arguments != ["--invalid"]:
                    (root / "build/uefi/esp/EFI/BOOT").mkdir(parents=True)
                    (root / "build/uefi/esp/EFI/BOOT/BOOTX64.EFI").write_bytes(b"previous")
                    (root / "build/uefi/legacy.o").write_bytes(b"evidence")
                for name in ("kernel-graphical-smoke.sh", "kernel-run.sh"):
                    shutil.copy(ROOT / "scripts" / name, root / "scripts")
                (root / "scripts/kernel-uefi-build.sh").write_text(builder)
                (root / "scripts/kernel-uefi-build.sh").chmod(0o755)
                (root / "scripts/kernel_graphical_smoke.py").write_text(runner)
                (root / "scripts/uefi-firmware.sh").write_text(
                    "uefi_firmware_select() { UEFI_FIRMWARE_COMBINED=rom; UEFI_FIRMWARE_CODE=; UEFI_FIRMWARE_VARS=; }\n"
                )
                (root / "scripts/uefi-linker.sh").write_text("uefi_linker_select() { :; }\n")
                (root / "bin").mkdir()
                for name in ("make", "as", "ld", "objcopy", "objdump", "nm", "readelf"):
                    (root / "bin" / name).symlink_to("/bin/true")
                (root / "bin/python3").symlink_to(sys.executable)
                env = {k: v for k, v in os.environ.items() if not k.startswith("KERNEL_TEST_")}
                for name in (
                    "KERNEL_USER_PROBE_MODE",
                    "KERNEL_CONSOLE",
                    "UEFI_MODE",
                    "UEFI_CONSOLE_HANDOFF",
                    "AURORA_GRAPHICAL_KEEP_RUNS",
                ):
                    env.pop(name, None)
                env.update(
                    PATH=str(root / "bin") + os.pathsep + env["PATH"], QEMU="/bin/true", CXX="/bin/true", **overrides
                )
                command = ["bash", "scripts/kernel-graphical-smoke.sh", *arguments]
                if "INTERRUPT_AT" in overrides:
                    process = subprocess.Popen(
                        command, cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                    )
                    try:
                        deadline = time.monotonic() + 5
                        while process.poll() is None:
                            events_path = root / "events"
                            events = events_path.read_text().splitlines() if events_path.exists() else []
                            if overrides["INTERRUPT_AT"] in events:
                                process.send_signal(getattr(signal, "SIG" + overrides["INTERRUPT_SIGNAL"]))
                                break
                            self.assertLess(time.monotonic(), deadline)
                            time.sleep(0.005)
                        stdout, stderr = process.communicate(timeout=10)
                        result = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
                    finally:
                        if process.poll() is None:
                            process.kill()
                            process.communicate(timeout=5)
                else:
                    result = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, status, result.stdout + result.stderr)
                if "SYMLINK" in overrides:
                    self.assertTrue(link.is_symlink())
                    self.assertEqual((root / "outside/sentinel").read_bytes(), b"unchanged")
                    self.assertFalse((root / "events").exists())
                    continue
                if arguments == ["--invalid"]:
                    self.assertFalse((root / "build").exists())
                    continue
                events = (root / "events").read_text().splitlines()
                self.assertEqual(events.count("build:normal"), 1)
                self.assertEqual((root / "build/uefi/esp/EFI/BOOT/BOOTX64.EFI").read_bytes(), b"previous")
                self.assertEqual((root / "build/uefi/legacy.o").read_bytes(), b"evidence")
                self.assertEqual("staged-normal-boot" in events, "guest" in events)
                self.assertFalse(list((root / "build/graphical-smoke").glob("*/build-normal-restoration.log")))
                for event in events:
                    if event.startswith("build:"):
                        profile = root / "build/native profiles" / event.removeprefix("build:")
                        self.assertTrue((profile / "objects/payload.o").exists())
                window = next((root / "build/graphical-smoke").glob("run-*"))
                if "guest" in events:
                    kept = (
                        status != 0
                        or overrides.get("AURORA_GRAPHICAL_KEEP_RUNS") == "all"
                        or overrides.get("GUEST_PIN")
                    )
                    for suffix in ("bin", "ppm"):
                        self.assertEqual((window / f"guests/production/state-00.{suffix}").exists(), bool(kept))
                    self.assertEqual((window / "guests/production/serial.log").read_bytes(), b"guest serial")
                    self.assertFalse((window / "guests/screen-captures.json").exists())
                self.assertFalse((window / "previous-build").exists())
                self.assertFalse((window / "last-build").exists())
                self.assertEqual(
                    json.loads((window / smoke.RUN_MARKER).read_text())["status"], "passed" if status == 0 else "failed"
                )
                self.assertFalse((window / "failed-build").exists())
                self.assertFalse((window / "failed-restoration").exists())
                self.assertTrue((window / "build-normal.log").is_file())

    def test_successful_capture_cleanup_is_scoped(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"AURORA_GRAPHICAL_KEEP_RUNS": "2"}):
            root = Path(tmp)
            window = root / "build/graphical-smoke/run-current"
            guests = window / "guests"
            dumps = (
                "production/state-00.bin",
                "production/state-00.ppm",
                "production/probe-00-01.bin",
                "editing/baseline.bin",
                "editing/sample-63.ppm",
                "editing/terminal.bin",
            )
            preserved = (
                "summary.json",
                "production/serial.log",
                "production/qmp.jsonl",
                "production/qemu.stderr",
                "production/review.bin",
                "review/baseline.bin",
                "production/review/terminal.bin",
                "screen-captures.json",
            )
            for name in (*dumps, *preserved):
                path = guests / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(name.encode())
            (window / "images").mkdir()
            (window / "images/payload.bin").write_bytes(b"staged image")
            with patch.object(smoke, "ROOT", root), patch("builtins.print"):
                smoke.start_run(window)
                smoke.finish_run(window, 0)
            self.assertFalse(any((guests / name).exists() for name in dumps))
            for name in preserved:
                self.assertEqual((guests / name).read_bytes(), name.encode())
            self.assertEqual((window / "images/payload.bin").read_bytes(), b"staged image")

    def test_cleanup_validates_paths_before_deletion_and_preserves_errors(self):
        for failure in ("guests-link", "case-link", "dump-link", "unlink"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                window = root / "build/graphical-smoke/run-current"
                case = window / "guests/production"
                case.mkdir(parents=True)
                outside = root / "review"
                outside.mkdir()
                (outside / "state-01.bin").write_bytes(b"review evidence")
                (case / "state-00.bin").write_bytes(b"owned capture")
                raw = case / "state-01.bin"
                if failure == "dump-link":
                    raw.symlink_to(outside / raw.name)
                else:
                    raw.write_bytes(b"owned capture")
                if failure in ("guests-link", "case-link"):
                    target = window / "guests" if failure == "guests-link" else case
                    target.rename(root / "owned")
                    target.symlink_to(outside, target_is_directory=True)
                with patch.object(smoke, "ROOT", root), patch("builtins.print") as output:
                    smoke.start_run(window)
                    if failure == "unlink":
                        with patch.object(smoke.os, "unlink", side_effect=PermissionError("read-only capture")):
                            smoke.finish_run(window, 0)
                    else:
                        smoke.finish_run(window, 0)
                    self.assertEqual(json.loads((window / smoke.RUN_MARKER).read_text())["status"], "passed")
                    self.assertTrue(
                        any(str(call.args[0]).startswith("WARN: could not discard") for call in output.call_args_list)
                    )
                self.assertEqual((outside / "state-01.bin").read_bytes(), b"review evidence")
                if failure in ("dump-link", "unlink"):
                    self.assertEqual((case / "state-00.bin").read_bytes(), b"owned capture")

    def test_failed_and_kept_runs_preserve_captures(self):
        for status, keep in ((31, False), (0, True)):
            with self.subTest(status=status, keep=keep), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                window = root / "build/graphical-smoke/run-current"
                case = window / "guests/production"
                case.mkdir(parents=True)
                dump = case / "state-00.bin"
                dump.write_bytes(b"capture")
                with patch.object(smoke, "ROOT", root), patch("builtins.print"):
                    smoke.start_run(window)
                    if keep:
                        (window / ".keep").touch()
                    smoke.finish_run(window, status)
                self.assertEqual(dump.read_bytes(), b"capture")

    def test_retention_bounds_and_preserves_unowned_evidence(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"AURORA_GRAPHICAL_KEEP_RUNS": "2"}):
            root = Path(tmp)
            base = root / "build/graphical-smoke"
            base.mkdir(parents=True)
            outside = root / "outside"
            outside.mkdir()
            (outside / "evidence").write_text("unchanged")
            (base / "run-link").symlink_to(outside, target_is_directory=True)
            protected = ("run-legacy", "run-invalid", "run-active", "run-pinned", "run-markerlink")
            for name in protected:
                (base / name).mkdir()
                (base / name / "evidence").write_text("unchanged")
            (base / "run-invalid" / smoke.RUN_MARKER).write_text('{"status": []}')
            (base / "run-markerlink" / smoke.RUN_MARKER).symlink_to(outside / "evidence")
            with patch.object(smoke, "ROOT", root), patch("builtins.print"):
                smoke.start_run(base / "run-active")
                smoke.start_run(base / "run-pinned")
                (base / "run-pinned/.keep").touch()
                smoke.finish_run(base / "run-pinned", 0)
                windows = []
                for index, status in enumerate((0, 31, 0, 31, 0, 31, 0, 31)):
                    folder = base / f"run-{index}"
                    folder.mkdir()
                    smoke.start_run(folder)
                    smoke.finish_run(folder, status)
                    self.assertTrue(folder.is_dir(), "the current run must survive")
                    windows.append(folder)
                self.assertEqual(
                    [p.name for p in windows if p.exists()], ["run-1", "run-3", "run-4", "run-5", "run-6", "run-7"]
                )
                for name in protected:
                    self.assertEqual((base / name / "evidence").read_text(), "unchanged")
                self.assertEqual((outside / "evidence").read_text(), "unchanged")
                self.assertTrue((base / "run-link").is_symlink())

    def test_concurrent_retention_keeps_active_windows(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"AURORA_GRAPHICAL_KEEP_RUNS": "2"}):
            root = Path(tmp)
            base = root / "build/graphical-smoke"
            base.mkdir(parents=True)
            with patch.object(smoke, "ROOT", root):
                for name in ("active", *map(str, range(8))):
                    folder = base / ("run-" + name)
                    folder.mkdir()
                    smoke.start_run(folder)
            command = (
                "import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); "
                "import kernel_graphical_smoke as s; s.ROOT=Path(sys.argv[2]); "
                "s.finish_run(Path(sys.argv[3]), int(sys.argv[4]))"
            )
            children = [
                subprocess.Popen(
                    [
                        sys.executable,
                        "-B",
                        "-c",
                        command,
                        str(ROOT / "scripts"),
                        str(root),
                        str(base / f"run-{i}"),
                        str(i % 2),
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                for i in range(8)
            ]
            for child in children:
                stdout, stderr = child.communicate(timeout=20)
                self.assertEqual(child.returncode, 0, stdout + stderr)
            statuses = [json.loads(path.read_text())["status"] for path in base.glob("run-*/" + smoke.RUN_MARKER)]
            self.assertCountEqual(statuses, ["running", "passed", "passed", "failed", "failed", "failed", "failed"])
            self.assertTrue((base / "run-active").exists())

    def test_reused_images_do_not_create_persistent_pins(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for owner in (root, root / "another-checkout"):
                with self.subTest(owner=owner):
                    old = owner / "build/graphical-smoke/run-review"
                    (old / "images").mkdir(parents=True)
                    marker = old / smoke.RUN_MARKER
                    contents = json.dumps(dict(schema="aurora-graphical-smoke-run-v1", status="passed", finished_ns=1))
                    marker.write_text(contents)
                    argv = [
                        "runner",
                        "--images",
                        str(old / "images"),
                        "--evidence",
                        str(old / "guests"),
                        "qemu",
                        "firmware",
                        "",
                        "",
                        "",
                    ]
                    with (
                        patch.object(smoke, "ROOT", root),
                        patch.object(sys, "argv", argv),
                        patch.object(smoke.transport, "firmware_args", return_value=[]),
                        patch.object(smoke, "verify_images") as verify,
                        patch.object(smoke.signal, "signal"),
                        patch.object(smoke, "window") as window,
                    ):
                        smoke.main()
                    verify.assert_called_once()
                    window.assert_called_once()
                    self.assertFalse((old / ".keep").exists())
                    self.assertEqual(marker.read_text(), contents)

    def test_older_markers_use_completion_mtime_without_schema_migration(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"AURORA_GRAPHICAL_KEEP_RUNS": "2"}):
            root = Path(tmp)
            base = root / "build/graphical-smoke"
            base.mkdir(parents=True)
            # Name and the retired timestamp disagree with mtime deliberately.
            for name, modified, finished in (("run-a", 2, 1), ("run-z", 1, 2)):
                folder = base / name
                folder.mkdir()
                marker = folder / smoke.RUN_MARKER
                marker.write_text(
                    json.dumps(dict(schema="aurora-graphical-smoke-run-v1", status="passed", finished_ns=finished))
                )
                os.utime(marker, ns=(modified, modified))
            current = base / "run-current"
            current.mkdir()
            with patch.object(smoke, "ROOT", root), patch("builtins.print"):
                smoke.start_run(current)
                smoke.finish_run(current, 0)
            self.assertFalse((base / "run-z").exists())
            self.assertTrue((base / "run-a").exists())
            self.assertEqual(json.loads((current / smoke.RUN_MARKER).read_text()), dict(status="passed"))

    def test_run_remains_active_until_its_capture_cleanup_finishes(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"AURORA_GRAPHICAL_KEEP_RUNS": "1"}):
            root = Path(tmp)
            current = root / "build/graphical-smoke/run-current"
            current.mkdir(parents=True)
            with patch.object(smoke, "ROOT", root), patch("builtins.print"):
                smoke.start_run(current)

                def discard(directory):
                    self.assertEqual(json.loads((directory / smoke.RUN_MARKER).read_text()), dict(status="running"))
                    other = current.parent / "run-other"
                    other.mkdir()
                    smoke.start_run(other)
                    smoke.output_policy().finish(other, 0, lambda _: None)
                    self.assertTrue(current.is_dir())

                with patch.object(smoke, "discard_captures", side_effect=discard):
                    smoke.finish_run(current, 0)
                self.assertEqual(json.loads((current / smoke.RUN_MARKER).read_text()), dict(status="passed"))
                self.assertFalse((current.parent / "run-other").exists())

    def test_pruning_failure_warns_without_changing_execution_result(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"AURORA_GRAPHICAL_KEEP_RUNS": "1"}):
            root = Path(tmp)
            base = root / "build/graphical-smoke"
            base.mkdir(parents=True)
            with patch.object(smoke, "ROOT", root), patch("builtins.print") as output:
                old = base / "run-old"
                old.mkdir()
                smoke.start_run(old)
                smoke.finish_run(old, 0)
                current = base / "run-current"
                current.mkdir()
                smoke.start_run(current)
                with patch.object(smoke.shutil, "rmtree", side_effect=PermissionError("read-only evidence")):
                    smoke.finish_run(current, 0)
                self.assertTrue(old.exists())
                self.assertTrue(current.exists())
                self.assertEqual(json.loads((current / smoke.RUN_MARKER).read_text())["status"], "passed")
                self.assertTrue(
                    any(str(call.args[0]).startswith("WARN: could not prune") for call in output.call_args_list)
                )

    def test_retention_controls_preserve_failed_native_products(self):
        with tempfile.TemporaryDirectory() as tmp, patch("builtins.print"):
            root = Path(tmp)
            base = root / "build/graphical-smoke"
            base.mkdir(parents=True)
            folder = base / "run-review"
            folder.mkdir()
            source = root / "build/kernel-images/uefi/graphical-console"
            (source / "objects").mkdir(parents=True)
            (source / "objects/future.o").write_text("partial object")
            (source / "payload.elf").write_text("partial link")
            (source / "unrelated.log").write_text("old evidence")
            outside = root / "outside"
            outside.write_text("unchanged")
            (source / "objects/alias.o").symlink_to(outside)
            object_inode = (source / "objects").stat().st_ino
            with patch.object(smoke, "ROOT", root), patch.dict(os.environ, {"AURORA_GRAPHICAL_KEEP_RUNS": "all"}):
                smoke.start_run(folder)
                smoke.finish_run(folder, 31)
                self.assertTrue((folder / ".keep").is_file())
            self.assertEqual((source / "objects").stat().st_ino, object_inode)
            self.assertEqual((source / "objects/future.o").read_text(), "partial object")
            self.assertEqual((source / "payload.elf").read_text(), "partial link")
            self.assertEqual((source / "unrelated.log").read_text(), "old evidence")
            self.assertEqual(outside.read_text(), "unchanged")
            with patch.object(smoke, "ROOT", root), patch.dict(os.environ, {"AURORA_GRAPHICAL_KEEP_RUNS": "1"}):
                for index in range(3):
                    current = base / f"run-new{index}"
                    current.mkdir()
                    smoke.start_run(current)
                    smoke.finish_run(current, 31)
                self.assertTrue(folder.exists())
                self.assertTrue((base / "run-new0").exists())
                self.assertTrue((base / "run-new1").exists())
                self.assertTrue((base / "run-new2").exists())
            for value in ("0", "-1", "1.5", "1000", "", "ALL"):
                with patch.dict(os.environ, {"AURORA_GRAPHICAL_KEEP_RUNS": value}), self.assertRaises(ValueError):
                    smoke.retained_runs()

    def test_stage_copies_only_required_current_artifacts(self):
        for mode in ("normal", *smoke.admission.MODES):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                build = root / "build/kernel-images/uefi" / mode
                with (
                    patch.object(smoke, "ROOT", root),
                    patch.object(smoke.admission, "BUILD", build),
                    patch.object(smoke.admission, "configure_paths"),
                    patch.object(smoke.admission.common, "verify_object_exports"),
                    patch.object(smoke.admission, "RECEIPT", build / "graphical-console-admission.json"),
                    patch.object(smoke.admission, "checked", return_value=None) as admission_check,
                    patch.object(smoke.admission.common, "BUILD", build),
                ):
                    files = smoke.admission.build_files(mode)
                    if mode != "normal":
                        files += [build / "graphical-console-admission.json"]
                    for path in files:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text("current")
                    (build / "legacy.o").write_text("unrelated")
                    (build / "historical.log").write_text("unrelated")
                    (build / "old-captures").mkdir()
                    (build / "old-captures/evidence").write_text("unrelated")
                    images = root / "images"
                    smoke.stage(mode, images, build)
                    args = SimpleNamespace(images=images)
                    smoke.verify_images(args, mode)
                    saved = {str(p.relative_to(images / mode)) for p in (images / mode).rglob("*") if p.is_file()}
                    self.assertEqual(saved, {str(p.relative_to(build)) for p in files} | {"smoke-image.json"})
                    if mode != "normal":
                        admitted = smoke.admission.common.hashes(smoke.admission.build_files(mode))
                        admission_check.return_value = {"sha256": admitted}
                        files[0].write_text("changed after admission")
                        with self.assertRaisesRegex(ValueError, "Admitted image changed"):
                            smoke.stage(mode, root / "changed", build)
                        self.assertFalse((root / "changed").exists())
                        files[0].write_text("current")
                    (images / mode / "payload.bin").write_text("changed")
                    with self.assertRaisesRegex(ValueError, "staged image drift"):
                        smoke.verify_images(args, mode)
                    files[0].unlink()
                    with self.assertRaisesRegex(ValueError, "missing artifact"):
                        smoke.stage(mode, root / "missing", build)
                    files[0].symlink_to(build / "historical.log")
                    with self.assertRaisesRegex(ValueError, "symlink"):
                        smoke.stage(mode, root / "symlink", build)

    def test_primary_and_restoration_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = SimpleNamespace(evidence=Path(tmp) / "new")
            with (
                patch("builtins.print"),
                patch.object(smoke, "production_case", side_effect=ValueError("primary")),
                patch.object(smoke, "restoration", side_effect=ValueError("restoration")),
            ):
                with self.assertRaisesRegex(ValueError, "primary"):
                    smoke.window(args)
            rows = json.loads((args.evidence / "summary.json").read_text())
            self.assertEqual([row["error"] for row in rows], ["ValueError: primary", "ValueError: restoration"])
            self.assertTrue(all(row["status"] == "failed" for row in rows))

    def test_matrix_and_mutations(self):
        self.assertEqual(len(smoke.CASES), 19)
        for case in smoke.CASES:
            model, rows = expected(case)
            raw = transcript(rows)
            self.assertEqual(smoke.markers(raw, final=True), rows)
            smoke.validate(rows, case[1], model, case[0] == "idle4096")
            for index in range(len(rows)):
                for changed in (rows[:index] + rows[index + 1 :], rows[:index] + [rows[index]] + rows[index:]):
                    with self.assertRaises((ValueError, IndexError)):
                        smoke.validate(changed, case[1], model, case[0] == "idle4096")
            for key, value in rows[-1][1].items():
                if key in ("reason", "wakes"):
                    continue
                bad = copy.deepcopy(rows)
                bad[-1][1][key] = value + 1
                with self.assertRaises(ValueError):
                    smoke.validate(bad, case[1], model, case[0] == "idle4096")
            for bad in (
                raw[:-1],
                raw + b"junk",
                raw + b"junk\r\n",
                raw + raw[-10:],
                raw.replace(b"base=", b"base=0"),
                raw.replace(b"stores=", b"sto\rres="),
                raw.replace(b"CAPTURE_GATE", b"UNKNOWN"),
                raw.replace(b"AURORA_UEFI_OK\r\n", b"AURORA_UEFI_OK\r\noutput> unexpected text\r\n"),
                raw.replace(b"AURORA_UEFI_ENTRY\r\n", b""),
                raw.replace(b"bytes=1921024", b"bytes=-1"),
            ):
                with self.assertRaises(ValueError):
                    smoke.markers(bad, final=True)
        model = smoke.reference(smoke.byte_samples(b"".join(smoke.PRODUCTION)))
        rows = [("CONSOLE_COMPLETE", dict(completion=0, wakes=4, stores=len(model["stores"])))]
        smoke.validate(smoke.markers(transcript(rows), production=True, final=True), b"G", model, production=True)

    def test_named_file_reference_state(self):
        slots = [None] * 4
        self.assertEqual(file_response(b"ls", slots), "files: empty (RAM-only).")
        for name in (b"a", b"b", b"c", b"d"):
            self.assertEqual(
                file_response(b"write " + name + b" old suffix", slots), f"wrote {name.decode()}: 10 bytes"
            )
        saved = slots.copy()
        for command, response in (
            (b"write e x", "files: full (4 files)."),
            (b"rm note", "files: note is reserved."),
            (b"write note", "files: invalid name or content."),
            (b"cat note x", "files: invalid name or content."),
            (b"write a " + b"x" * 50, "files: invalid name or content."),
            (b"write a bad\x01", "files: invalid name or content."),
            (b"write a bad\xff", "files: invalid name or content."),
            (b"write 123456789 x", "files: invalid name or content."),
            (b"write . x", "files: invalid name or content."),
            (b"write .. x", "files: invalid name or content."),
            (b"rm a/b", "files: invalid name or content."),
            (b"ls a", "files: invalid name or content."),
            (b"cat A", "files: not found (RAM-only)."),
            (b"rm e", "files: not found (RAM-only)."),
            (b"writeX a x", "Unknown command. Type help."),
        ):
            with self.subTest(command=command):
                self.assertEqual(file_response(command, slots), response)
                self.assertEqual(slots, saved)
        self.assertEqual(file_response(b"write b X", slots), "wrote b: 1 byte")
        self.assertEqual(file_response(b"cat b", slots), "X")
        self.assertEqual(file_response(b"write b ", slots), "wrote b: 0 bytes")
        self.assertEqual(file_response(b"cat b", slots), "")
        self.assertEqual(file_response(b"rm a", slots), "files: removed (RAM-only).")
        self.assertEqual(file_response(b"write A._-0123 " + b"x" * 49, slots), "wrote A._-0123: 49 bytes")
        self.assertEqual(file_response(b"cat A._-0123", slots), "x" * 49)
        self.assertEqual(file_response(b"ls", slots), "files: A._-0123 b c d")

    def test_named_file_guest_bounds_and_semantic_pixel_mutations(self):
        baseline = b"\xa5" * smoke.SIZE
        for name, consumed, before, after, observed in (
            ("files-demo", 75, b"cat todo\n", b"cat ideas\n", b"cat todo\n"),
            ("files-capacity", 79, b"rm a\n", b"rm c\n", b"ls\n"),
        ):
            case = next(case for case in smoke.CASES if case[0] == name)
            model, _ = expected(case)
            self.assertEqual(model["completion"], 0)
            self.assertEqual(model["consumed"], consumed)
            self.assertEqual(case[2][consumed:], b"!")
            prefix = case[2][: case[2].index(observed) + len(observed)]
            changed = prefix.replace(before, after)
            self.assertNotEqual(prefix, changed)
            original = smoke.reference(smoke.byte_samples(prefix + b"exit\n"))
            mutant = smoke.reference(smoke.byte_samples(changed + b"exit\n"))
            frame = original["frames"][len(prefix)]
            wrong_frame = mutant["frames"][len(changed)]
            self.assertNotEqual(frame, wrong_frame)
            raw = bytearray(baseline)
            for row, y in enumerate(range(128, 146)):
                raw[(y * smoke.PITCH + 32) * 4 : (y * smoke.PITCH + 440) * 4] = frame[row * 1632 : (row + 1) * 1632]
            ppm = b"P6\n800 600\n255\n" + smoke.ppm_rgb(800, 600, 800, 1, raw)
            smoke.compare(baseline, raw, ppm, frame=frame)
            with self.assertRaisesRegex(ValueError, "pixels differ"):
                smoke.compare(baseline, raw, ppm, frame=wrong_frame)

    def test_real_baseline_and_pixel_prefix(self):
        baseline = bytes(range(256)) * (smoke.SIZE // 256)
        for count in (0, 55):
            model = smoke.reference([], fail_after=count)
            raw = bytearray(baseline)
            for offset, value in model["stores"]:
                raw[offset : offset + 4] = value.to_bytes(4, "little")
            ppm = b"P6\n800 600\n255\n" + smoke.ppm_rgb(800, 600, 800, 1, raw)
            smoke.compare(baseline, raw, ppm, stores=model["stores"])
            for offset in (0, smoke.VISIBLE, (128 * 800 + 32) * 4):
                bad = bytearray(raw)
                bad[offset] ^= 1
                with self.assertRaises(ValueError):
                    smoke.compare(baseline, bad, ppm, stores=model["stores"])
            with self.assertRaises(ValueError):
                smoke.compare(baseline, raw, ppm[:-1] + bytes([ppm[-1] ^ 1]), stores=model["stores"])
            with self.assertRaises(ValueError):
                smoke.compare(baseline, model["pixels"][32:-32], ppm, stores=model["stores"])

    def test_selector_then_samples_and_sentinel(self):
        case = next(case for case in smoke.CASES if case[0] == "fixture-G")
        model, rows = expected(case)
        events, index = [], 0
        channel = SimpleNamespace(serial_bytes=transcript(rows[:1]), proc=SimpleNamespace(wait=lambda **kw: 0))
        channel.stop = lambda: events.append("stop")
        channel.capture = lambda name: (events.append(name) or b"", b"")
        channel.drain_serial = lambda: None
        channel.command = lambda name: events.append(name)

        def write(channel, data):
            nonlocal index
            events.append(data)
            index += 2 if index == 0 else 1
            channel.serial_bytes = transcript(rows[: index + 1])

        @contextmanager
        def fake_guest(*args):
            yield channel

        with (
            patch.object(smoke, "guest", fake_guest),
            patch.object(smoke.transport, "wait_exit", return_value=0),
            patch.object(smoke, "send", write),
            patch.object(smoke, "compare"),
            patch.object(smoke, "wait", lambda ch, pred: self.assertTrue(pred(smoke.markers(ch.serial_bytes)))),
        ):
            smoke.capture_case(None, case, None, {})
        sent = [event for event in events if isinstance(event, bytes)]
        self.assertEqual(sent, [b"G", b"e", b"x", b"i", b"t", b"\r!"])
        self.assertLess(events.index("baseline"), events.index(b"G"))
        self.assertLess(events.index("sample-00"), events.index(b"e"))

    def test_window_failure_restores_once(self):
        for fail_at in ("production", "case", None):
            with tempfile.TemporaryDirectory() as temporary:
                args = SimpleNamespace(evidence=Path(temporary) / "new")
                events = []

                def action(name):
                    def run(*args):
                        events.append(name)
                        if name == fail_at:
                            raise ValueError("injected")

                    return run

                with (
                    patch("builtins.print"),
                    patch.object(smoke, "production_case", action("production")),
                    patch.object(smoke, "capture_case", action("case")),
                    patch.object(smoke, "restoration", action("restore")),
                ):
                    if fail_at:
                        with self.assertRaises(ValueError):
                            smoke.window(args)
                    else:
                        smoke.window(args)
                self.assertEqual(events.count("restore"), 1)
                self.assertEqual(events[-1], "restore")
                if fail_at:
                    self.assertEqual(events.count("case"), int(fail_at == "case"))
                self.assertEqual(json.loads((args.evidence / "summary.json").read_text())[-1]["status"], "passed")

    def test_idle_has_no_intermediate_pause_or_input(self):
        case = next(case for case in smoke.CASES if case[0] == "idle4096")
        model, rows = expected(case)
        events = []
        channel = SimpleNamespace(serial_bytes=transcript(rows[:1]), proc=SimpleNamespace(wait=lambda **kw: 0))
        channel.stop = lambda: events.append("stop")
        channel.capture = lambda name: (events.append(name) or b"", b"")
        channel.drain_serial = lambda: None
        channel.command = lambda name: events.append(name)

        @contextmanager
        def fake_guest(*args):
            yield channel

        def wait(ch, predicate):
            if events.count("cont"):
                ch.serial_bytes = transcript(rows[:3] if len(events) == 4 else rows)
                events.append("wait")
            self.assertTrue(predicate(smoke.markers(ch.serial_bytes)))

        with (
            patch.object(smoke, "guest", fake_guest),
            patch.object(smoke.transport, "wait_exit", return_value=0),
            patch.object(smoke, "wait", wait),
            patch.object(smoke, "send", lambda ch, data: events.append(data)),
            patch.object(smoke, "compare"),
        ):
            smoke.capture_case(None, case, None, {})
        self.assertEqual(events, ["stop", "baseline", b"G", "cont", "wait", "wait", "stop", "terminal", "quit"])

    def test_capture_drift_still_boots_normal_then_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            args = SimpleNamespace(images=Path(temporary), qemu="qemu", data="", firmware=["-bios", "firmware"])

            def verify(args, mode=None):
                if mode != "normal":
                    raise ValueError("capture drift")

            with (
                patch.object(smoke, "verify_images", side_effect=verify) as checks,
                patch.object(
                    smoke.transport, "run_logged", side_effect=lambda argv, log, **kw: log.touch() or 33
                ) as launch,
                patch.object(smoke.normal, "validate") as validate,
            ):
                with self.assertRaisesRegex(ValueError, "capture drift"):
                    smoke.restoration(args, Path(temporary) / "restore", {})
                launch.assert_called_once()
                validate.assert_called_once_with(33, "", "normal")
                self.assertEqual(checks.call_args_list[0].args, (args, "normal"))

    def test_bounds_and_cleanup(self):
        stream = io.BytesIO()
        log = smoke.transport.Qmp.__new__(smoke.transport.Qmp)
        log.log, log.total, log.log_limit = stream, 4 * 1024 * 1024, 4 * 1024 * 1024
        with self.assertRaises(ValueError):
            log.record(b"x")
        self.assertEqual(stream.getvalue(), b"")
        proc = SimpleNamespace(stdin=io.BytesIO(), stdout=io.BytesIO(), returncode=0)
        channel = SimpleNamespace(
            qlog=io.BytesIO(),
            slog=io.BytesIO(),
            receive=lambda: {"QMP": {}},
            command=lambda *args: None,
            drain_serial=lambda: (_ for _ in ()).throw(ValueError("drain")),
        )
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.object(smoke, "verify_images"),
            patch.object(smoke.os, "openpty", return_value=(10, 11)),
            patch.object(smoke.tty, "setraw"),
            patch.object(smoke.os, "ttyname", return_value="/dev/pts/test"),
            patch.object(smoke.os, "close") as close,
            patch.object(smoke.subprocess, "Popen", return_value=proc),
            patch.object(smoke.capture, "Channel", return_value=channel),
            patch.object(smoke.transport, "cleanup", side_effect=ValueError("reap")) as terminate,
        ):
            args = SimpleNamespace(images=Path(temporary), qemu="qemu", data="", firmware=["-bios", "firmware"])
            record = {}
            with self.assertRaises(ValueError):
                with smoke.guest(args, "normal", Path(temporary) / "case", record):
                    raise ValueError("body")
            terminate.assert_called_once_with(proc)
            self.assertEqual(close.call_count, 2)
            self.assertTrue(proc.stdin.closed and proc.stdout.closed and channel.slog.closed)
            self.assertEqual(record["guest_error"], "body")
            self.assertEqual(record["cleanup_errors"], ["cleanup: ValueError: reap", "ValueError: drain"])


if __name__ == "__main__":
    unittest.main()
