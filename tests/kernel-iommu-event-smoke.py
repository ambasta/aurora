#!/usr/bin/env python3
"""Compiler-free real-pipe/fake-child controls. These do not exercise QEMU."""

import json
import io
import os
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import kernel_iommu_event_smoke as smoke

transport = smoke.transport

fixtures = smoke.admission.load("event_smoke_test_fixtures", Path(__file__).with_name("kernel-iommu-event-oracle.py"))

FAKE = """#!{python}
import json, os, pathlib, re, shutil, signal, sys, time
root = pathlib.Path(__file__).parent
kind = {kind!r}
fd = int(re.search(r'fd=([0-9]+)', sys.argv[sys.argv.index('-add-fd') + 1])[1])
if kind == 'early': sys.exit(9)
if kind == 'stderr': os.write(2, b'bad stderr')
if kind == 'stderr-cap': os.write(2, b'x' * (2 * 1024 * 1024))
serial = (root / 'serial.bin').read_bytes()
if kind == 'failure': serial = serial[:serial.index(b'AURORA_EVENT_ADMISSION_OK')] + b'AURORA_EVENT_FAIL: failed\\r\\n'
if kind == 'ownership': serial = serial.replace(b'bytes=1048576', b'bytes=2048')
os.write(fd, serial)
os.close(fd)
if kind == 'stall':
 signal.signal(signal.SIGTERM, signal.SIG_IGN)
 time.sleep(20)
if kind == 'signal-int': os.kill(os.getppid(), signal.SIGINT)
if kind == 'signal-term': os.kill(os.getppid(), signal.SIGTERM)
if kind == 'eof': sys.exit(0)
if kind == 'qmp-cap':
 os.write(1, b'x' * 65537)
 time.sleep(20)
print(json.dumps({{'QMP': {{'version': {{}}, 'capabilities': []}}}}), flush=True)
for line in sys.stdin:
 request = json.loads(line)
 name = request['execute']; result = {{}}
 if name == 'stop': print(json.dumps({{'event': 'STOP'}}), flush=True)
 if name == 'query-status':
  result = {{'status': 'running' if kind == 'unpaused' else 'paused', 'running': kind == 'unpaused'}}
 if name == 'human-monitor-command':
  text = request['arguments']['command-line']; filename = text.split('"')[1]
  data = (root / filename).read_bytes()
  pathlib.Path(filename).write_bytes(data[:-1] if kind == 'short' else data)
  result = ''
 if name == 'quit': print(json.dumps({{'event': 'SHUTDOWN'}}), flush=True)
 response = {{'return': result, 'id': request['id'] + (1 if kind == 'wrong-id' else 0)}}
 if kind == 'nonobject': response = []
 if kind == 'error': response = {{'error': {{'class': 'GenericError'}}, 'id': request['id']}}
 print(json.dumps(response), flush=True)
 if name == 'quit': break
"""


class Controls(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="event-smoke-controls-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.fixture = fixtures.fixture()
        for name, data in self.fixture[3].items():
            (self.root / name).write_bytes(data)
        (self.root / "serial.bin").write_bytes(self.fixture[2])
        for name in ("code", "vars", "master"):
            (self.root / name).write_bytes(b"small owned fixture")
        (self.root / "data").mkdir()
        self.runtime = dict(
            qemu=str(self.root / "fake-qemu"),
            code=str(self.root / "code"),
            vars=str(self.root / "vars"),
            data=str(self.root / "data"),
            library_path="",
            files={str(self.root / "vars"): smoke.identity(self.root / "vars")},
        )

    def guest(self, kind="success", name="run"):
        fake = Path(self.runtime["qemu"])
        fake.write_text(FAKE.format(python=sys.executable, kind=kind))
        fake.chmod(0o700)
        with patch.object(smoke, "verify_runtime"), patch.object(smoke, "verify_dependencies"):
            return smoke.capture_guest(
                self.fixture[0],
                self.fixture[1],
                self.runtime,
                self.root / "master",
                self.root / name,
                master_sha256=smoke.esp.sha256(self.root / "master"),
            )

    def test_packaged_tools_use_fixed_prefix_without_runtime_hash_records(self):
        prefix = self.root / "package"
        for name in (
            "bin/qemu-system-x86_64",
            *("model/" + name for name in smoke.MODEL),
            "model/configs/devices/x86_64-softmmu/aurora-dma.mak",
        ):
            path = prefix / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("packaged dependency")
        (prefix / "bin/qemu-system-x86_64").chmod(0o700)
        (prefix / "share/qemu").mkdir(parents=True)
        (prefix / "firmware").mkdir()
        for role, name in (("code", "OVMF_CODE_4M.fd"), ("vars", "OVMF_VARS_4M.fd")):
            with (prefix / "firmware" / name).open("wb") as file:
                file.truncate(smoke.FIRMWARE[role][0])
        marker = prefix / "runtime.json"
        smoke.write_json(marker, smoke.PACKAGE_MARKER)

        def version(argv, output, **options):
            self.assertEqual(argv, [str(prefix / "bin/qemu-system-x86_64"), "--version"])
            output.write(b"QEMU emulator version 10.0.13\n")
            return 0

        with (
            patch.object(smoke.transport, "run_logged", side_effect=version) as run,
            patch.object(smoke, "identity", side_effect=AssertionError("packaged tools must not be rehashed")),
        ):
            runtime = smoke.packaged_runtime(prefix)
            smoke.verify_runtime(runtime)
            smoke.verify_dependencies(runtime, self.root)
            run.assert_called_once()
            self.assertTrue(runtime["packaged"])
            self.assertNotIn("files", runtime)
            self.assertNotIn("library_bindings", runtime)
        smoke.write_json(marker, dict(smoke.PACKAGE_MARKER, model="stock"))
        with self.assertRaisesRegex(ValueError, "model/version"):
            smoke.packaged_runtime(prefix)
        smoke.write_json(marker, smoke.PACKAGE_MARKER)
        with patch.object(smoke.transport, "run_logged", side_effect=lambda argv, output, **kw: output.write(b"wrong")):
            with self.assertRaisesRegex(ValueError, "QEMU version"):
                smoke.packaged_runtime(prefix)

    def test_original_clock_and_explicit_devices(self):
        expected = [
            "qemu",
            "-L",
            "/data",
            "-machine",
            "q35",
            "-accel",
            "tcg",
            "-cpu",
            "qemu64",
            "-smp",
            "1",
            "-m",
            "128M",
            "-bios",
            "/firmware",
            "-drive",
            "format=raw,file=fat:ro:/esp,snapshot=on",
            "-nic",
            "none",
            "-display",
            "none",
            "-serial",
            "stdio",
            "-monitor",
            "none",
            "-no-reboot",
            "-device",
            "isa-debug-exit,iobase=0xf4,iosize=0x04",
        ]
        self.assertEqual(
            transport.command("qemu", "/data", firmware=["-bios", "/firmware"], boot=transport.fat_boot("/esp")),
            expected,
        )
        capture = transport.command("qemu", peripherals=["-vga", "std"], extra=["-qmp", "stdio", "-S"])
        self.assertEqual(capture[-3:], ["-qmp", "stdio", "-S"])
        self.assertIn("-vga", capture)
        self.assertNotIn("-icount", capture)
        self.assertNotIn("amd-iommu", capture)

    def test_firmware_is_explicit_and_snapshot_is_preserved(self):
        self.assertEqual(transport.firmware_args("/combined"), ["-bios", "/combined"])
        self.assertEqual(
            transport.firmware_args("", "/code,raw.fd", "/vars.qcow2"),
            [
                "-drive",
                "if=pflash,unit=0,format=raw,readonly=on,file=/code,,raw.fd",
                "-drive",
                "if=pflash,unit=1,format=qcow2,snapshot=on,file=/vars.qcow2",
            ],
        )
        for args in (("", "", ""), ("/combined", "/code", "/vars"), ("", "/same", "/same")):
            with self.subTest(args=args), self.assertRaises(ValueError):
                transport.firmware_args(*args)

    def test_missing_is_blocked_but_present_invalid_is_failed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaises(transport.MissingPrerequisite) as absent:
                transport.input_path(root / "absent", "QEMU")
            self.assertEqual(transport.failure_label(absent.exception), "BLOCKED")
            with self.assertRaises(ValueError) as invalid:
                transport.input_path(root, "QEMU")
            self.assertEqual(transport.failure_label(invalid.exception), "FAIL")
            self.assertEqual(transport.failure_label(ValueError("tampered digest")), "FAIL")
            # A missing file after a guest starts must not become a prerequisite skip.
            self.assertEqual(transport.failure_label(FileNotFoundError("lost output")), "FAIL")

    def test_shared_serial_timeout_preserves_output(self):
        log = self.root / "serial-timeout.log"
        status = transport.run_logged(
            [sys.executable, "-c", "import time; print('started', flush=True); time.sleep(20)"],
            log,
            timeout=0.2,
        )
        self.assertEqual(status, 124)
        self.assertEqual(log.read_bytes(), b"started\n")
        self.assertFalse(transport.retain_artifacts(0))
        self.assertTrue(transport.retain_artifacts(0, True))
        self.assertTrue(transport.retain_artifacts(124))

    def test_complete_owned_pipe_capture_and_closed_argv(self):
        result = self.guest()
        self.assertEqual(result["selector"], 0)
        recorded = smoke.read_json(self.root / "run/result.json")
        self.assertEqual(recorded["reason"], "terminal-captured")
        self.assertTrue(recorded["owned_process_reaped"])
        self.assertFalse(recorded["forced_cleanup"])
        argv = smoke.read_json(self.root / "run/launch.json")["argv"]
        self.assertEqual(argv.count("-device"), 4)
        self.assertEqual(argv.count("-no-user-config"), 1)
        self.assertNotIn("-readconfig", argv)
        self.assertNotIn("-icount", argv)
        self.assertEqual(argv[argv.index("-accel") + 1], "tcg")
        self.assertEqual(argv[argv.index("-nic") + 1], "none")
        self.assertIn("path=/dev/fdset/1,append=on", argv[-1])
        for name in ("vars.fd", "esp.raw"):
            self.assertEqual((self.root / "run" / name).stat().st_mode & 0o777, 0o600)
        with self.assertRaises(ValueError):
            smoke.command(self.runtime, self.root / "run", 2)
        bad = dict(self.runtime, data=str(self.root / "data,unsafe"))
        with self.assertRaises(ValueError):
            smoke.command(bad, self.root / "run", 9)

    def test_actual_child_failures_remain_failed_and_reaped(self):
        for kind in (
            "early",
            "eof",
            "wrong-id",
            "nonobject",
            "error",
            "unpaused",
            "short",
            "failure",
            "ownership",
            "stderr",
            "stderr-cap",
            "qmp-cap",
        ):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.guest(kind, kind)
            recorded = smoke.read_json(self.root / kind / "result.json")
            self.assertTrue(recorded["owned_process_reaped"], kind)
            self.assertTrue(recorded["errors"], kind)
            self.assertFalse((self.root / kind / "oracle.json").exists())
            if kind in ("unpaused", "ownership"):
                self.assertFalse(recorded["captures"])

    def test_response_stall_force_kill_and_interrupt(self):
        with self.assertRaisesRegex(ValueError, "QMP response timeout"):
            self.guest("stall", "stall")
        recorded = smoke.read_json(self.root / "stall/result.json")
        self.assertTrue(recorded["owned_process_reaped"])
        self.assertTrue(recorded["forced_cleanup"])
        self.assertLess(recorded["elapsed_seconds"], 8)
        with patch.object(smoke, "Qmp", side_effect=KeyboardInterrupt("synthetic interrupt")):
            with self.assertRaisesRegex(ValueError, "KeyboardInterrupt"):
                self.guest(name="interrupt")
        self.assertTrue(smoke.read_json(self.root / "interrupt/result.json")["owned_process_reaped"])

    def test_actual_sigint_sigterm_settle_owned_child(self):
        import signal

        def interrupted(_signum, _frame):
            raise KeyboardInterrupt("test signal")

        for kind, sig in (("signal-int", signal.SIGINT), ("signal-term", signal.SIGTERM)):
            previous = signal.signal(sig, interrupted)
            try:
                with self.assertRaisesRegex(ValueError, "KeyboardInterrupt"):
                    self.guest(kind, kind)
            finally:
                signal.signal(sig, previous)
            self.assertTrue(smoke.read_json(self.root / kind / "result.json")["owned_process_reaped"])

    def test_stream_cap_launch_failure_and_descriptors(self):
        before = len(list(Path("/proc/self/fd").iterdir()))
        with patch.object(smoke.subprocess, "Popen", side_effect=OSError("launch denied")):
            with self.assertRaisesRegex(ValueError, "launch denied"):
                self.guest(name="launch-failed")
        self.assertEqual(before, len(list(Path("/proc/self/fd").iterdir())))
        with patch.object(smoke, "STREAM_LIMIT", 128), self.assertRaisesRegex(ValueError, "serial size limit"):
            self.guest(name="capped")
        self.assertEqual((self.root / "capped/serial.log").stat().st_size, 128)
        self.assertEqual(before, len(list(Path("/proc/self/fd").iterdir())))

    def test_event_deadline_and_stalled_qmp_write(self):
        import io
        import time

        real_time = time.monotonic
        ticks = iter([real_time() - 100])
        with patch.object(smoke.time, "monotonic", side_effect=lambda: next(ticks, real_time())):
            with self.assertRaisesRegex(ValueError, "deadline expired"):
                self.guest(name="deadline")
        self.assertTrue(smoke.read_json(self.root / "deadline/result.json")["owned_process_reaped"])
        reader, writer = os.pipe()
        os.set_blocking(writer, False)
        try:
            while True:
                os.write(writer, b"x" * 4096)
        except BlockingIOError:
            pass
        channel = smoke.Qmp.__new__(smoke.Qmp)
        channel.deadline = time.monotonic() + 0.05
        channel.log, channel.total, channel.sequence = io.BytesIO(), 0, 0
        channel.timeout, channel.log_limit = 2, 65536
        channel.writer = os.fdopen(writer, "wb", buffering=0)
        try:
            with self.assertRaisesRegex(ValueError, "QMP request timeout"):
                channel.command("stop")
        finally:
            channel.writer.close()
            os.close(reader)

    def test_bounded_builder_failure_and_output_limit(self):
        with self.assertRaisesRegex(ValueError, "Child exited 7"):
            smoke.bounded_child([sys.executable, "-c", "raise SystemExit(7)"], self.root / "exit.log")
        with self.assertRaisesRegex(ValueError, "Child output limit"):
            smoke.bounded_child([sys.executable, "-c", "print('x'*4096)"], self.root / "cap.log", limit=128)
        self.assertEqual((self.root / "cap.log").stat().st_size, 128)
        with self.assertRaisesRegex(ValueError, "deadline"):
            smoke.bounded_child(
                [sys.executable, "-c", "import time; time.sleep(20)"], self.root / "deadline.log", timeout=0.05
            )

    def test_successful_wrapper_cannot_leave_running_descendant(self):
        import time

        sentinel = self.root / "descendant-write"
        descendant = (
            "import time; from pathlib import Path; time.sleep(.4); Path(" + repr(str(sentinel)) + ").write_text('bad')"
        )
        parent = (
            "import subprocess,sys; subprocess.Popen([sys.executable,'-c',"
            + repr(descendant)
            + "], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)"
        )
        with self.assertRaisesRegex((ValueError, smoke.ChildNotReaped), "descendants"):
            smoke.bounded_child([sys.executable, "-c", parent], self.root / "descendant.log", timeout=1)
        time.sleep(0.5)
        self.assertFalse(sentinel.exists())

    def test_owned_cleanup_never_signals_unrelated_group(self):
        class Child:
            pid = 123
            returncode = None

            def poll(self):
                return None

        with patch.object(transport.os, "getpgid", return_value=456), patch.object(transport.os, "killpg") as kill:
            with self.assertRaisesRegex(ValueError, "group changed"):
                transport.cleanup(Child())
            kill.assert_not_called()

    def test_strict_json_and_regular_paths(self):
        for raw in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', '{"x":1e999}', '{"x":[-1e999]}', "[]", "null"):
            with self.assertRaises(ValueError):
                smoke.json_object(raw)
        link = self.root / "link"
        link.symlink_to(self.root / "code")
        with self.assertRaises(ValueError):
            smoke.safe_path(link)
        fifo = self.root / "fifo"
        os.mkfifo(fifo)
        with self.assertRaises(ValueError):
            smoke.safe_path(fifo)
        with self.assertRaises(ValueError):
            smoke.copy_private(self.root / "code", self.root / "vars")

    def test_native_build_handoff_keeps_diagnostics_separate_and_binds_original(self):
        mode = smoke.MODES[0]
        native = self.root / "meson/kernel-images/uefi" / mode
        native.mkdir(parents=True)
        normal = native.parent / "normal"
        normal.mkdir()
        (normal / "payload.bin").write_bytes(b"keep normal")

        def child(argv, selection, **kwargs):
            self.assertEqual(argv[-5:], ["--kernel", "uefi", "--profile", mode, "--print-image-dir"])
            selection.write_text(str(native) + "\n")
            kwargs["stderr"].write(b"native build diagnostics\n")
            return 0

        with (
            patch.object(transport, "run_logged", side_effect=child),
            patch.object(smoke.admission, "configure_paths") as bind,
        ):
            smoke.build(mode, self.root)
        bind.assert_called_once_with(native, smoke.ROOT)
        self.assertEqual((self.root / ("build-" + mode + ".log")).read_bytes(), b"native build diagnostics\n")
        self.assertEqual((normal / "payload.bin").read_bytes(), b"keep normal")

    def test_separate_stdout_and_stderr_share_one_output_bound(self):
        log, diagnostics = self.root / "stdout.log", self.root / "stderr.log"
        with diagnostics.open("xb") as stderr:
            status = transport.run_logged(
                [sys.executable, "-c", "import sys; print('/profile'); print('diagnostic', file=sys.stderr)"],
                log,
                stderr=stderr,
                expected=0,
            )
        self.assertEqual(status, 0)
        self.assertEqual(log.read_bytes(), b"/profile\n")
        self.assertEqual(diagnostics.read_bytes(), b"diagnostic\n")
        with (self.root / "capped-stderr.log").open("xb") as stderr, self.assertRaisesRegex(ValueError, "output limit"):
            transport.run_logged(
                [sys.executable, "-c", "import sys; print('x'*4096, file=sys.stderr)"],
                self.root / "capped-stdout.log",
                stderr=stderr,
                limit=128,
            )
        self.assertEqual((self.root / "capped-stderr.log").stat().st_size, 128)

    def test_supported_runtime_identity_and_rejection_before_launch(self):
        from types import SimpleNamespace
        import copy

        source = self.root / "source"
        model = {}
        for name in smoke.MODEL:
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(name.encode())
            model[name] = smoke.esp.sha256(path)
        config = source / "configs/devices/x86_64-softmmu/aurora-dma.mak"
        config.parent.mkdir(parents=True)
        config.write_text(smoke.DEVICE_CONFIG)
        binary, library = self.root / "binary", self.root / "libfixture.so"
        binary.write_bytes(b"not executed")
        binary.chmod(0o700)
        library.write_bytes(b"fake library")
        libraries = self.root / "libraries.json"
        smoke.write_json(
            libraries,
            dict(
                LD_LIBRARY_PATH="",
                libraries={str(library): dict(resolved_path=str(library), **smoke.identity(library))},
            ),
        )
        (self.root / "data/kvmvapic.bin").write_bytes(b"data")
        record = dict(
            source_path=str(source),
            binary_path=str(binary),
            binary_bytes=binary.stat().st_size,
            binary_sha256=smoke.esp.sha256(binary),
            runtime_library_manifest=dict(path=str(libraries), sha256=smoke.esp.sha256(libraries)),
        )
        manifest = self.root / "build.json"
        smoke.write_json(manifest, record)
        args = SimpleNamespace(
            build_receipt=str(manifest),
            code=str(self.root / "code"),
            vars=str(self.root / "vars"),
            data=str(self.root / "data"),
        )
        firmware = {role: tuple(smoke.identity(getattr(args, role)).values()) for role in ("code", "vars")}
        real_which = smoke.shutil.which
        esps = self.root / "esps"
        esps.mkdir()
        for mode in smoke.MODES:
            (esps / (mode + ".raw")).write_bytes(b"fake ESP")
        argv = [
            "event-smoke",
            "--build-receipt",
            str(manifest),
            "--code",
            args.code,
            "--vars",
            args.vars,
            "--data",
            args.data,
            "--esp-dir",
            str(esps),
            "--output-parent",
            str(self.root),
            "--normal-qemu",
            sys.executable,
            "--normal-firmware",
            args.code,
        ]

        def reject(message):
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    smoke.runtime_inputs(args)
                with (
                    patch.dict(os.environ, {"PATH": os.defpath}, clear=True),
                    patch.object(sys, "argv", argv),
                    patch.object(smoke.shutil, "which", return_value=sys.executable),
                    patch.object(smoke.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")),
                    patch.object(smoke.shutil, "disk_usage", return_value=SimpleNamespace(free=4 * 1024**3)),
                    patch.object(smoke.tempfile, "mkdtemp") as allocate,
                    patch.object(smoke, "window") as window,
                    patch.object(sys, "stderr", new_callable=io.StringIO) as stderr,
                ):
                    self.assertEqual(smoke.cli(), 1, stderr.getvalue())
                    self.assertIn("FAIL: Event developer smoke: " + message, stderr.getvalue())
                    self.assertNotIn("BLOCKED:", stderr.getvalue())
                    allocate.assert_not_called()
                    window.assert_not_called()

        with (
            patch.object(smoke, "MODEL", model),
            patch.object(smoke, "FIRMWARE", firmware),
            patch.object(smoke.subprocess, "Popen") as launch,
        ):
            runtime = smoke.runtime_inputs(args)
            smoke.verify_runtime(runtime)
            broken = copy.deepcopy(record)
            broken["binary_sha256"] = "0" * 64
            smoke.write_json(manifest, broken)
            reject("Custom QEMU binary/build record mismatch")
            smoke.write_json(manifest, record)
            for path in [source / name for name in model] + [config]:
                original = path.read_bytes()
                path.write_bytes(b"unsupported source/configuration")
                reject("Custom model device configuration changed" if path == config else "Custom model source changed")
                path.write_bytes(original)
            library.write_bytes(b"drift")
            reject("Dependency bytes changed")
            library.write_bytes(b"fake library")
            (self.root / "code").write_bytes(b"wrong firmware")
            reject("Unsupported default split")
            (self.root / "code").write_bytes(b"small owned fixture")
            runtime = smoke.runtime_inputs(args)
            (self.root / "data/new.bin").write_bytes(b"added")
            with self.assertRaisesRegex(ValueError, "data changed"):
                smoke.verify_runtime(runtime)
            launch.assert_not_called()

    def test_data_directory_links_are_bounded_and_bind_resolved_files(self):
        data, keymaps = self.root / "data", self.root / "keymaps"
        keymaps.mkdir()
        (keymaps / "en-us").write_bytes(b"keymap")
        (data / "keymaps").symlink_to(keymaps, target_is_directory=True)
        recorded = smoke.data_files(data)
        self.assertEqual(recorded["keymaps/en-us"]["path"], str(keymaps / "en-us"))
        (keymaps / "en-us").write_bytes(b"changed")
        self.assertNotEqual(smoke.data_files(data), recorded)
        for alias, target in ((keymaps / "cycle", data), (data / "duplicate", keymaps)):
            alias.symlink_to(target, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "cycle or repeated alias"):
                smoke.data_files(data)
            alias.unlink()
        for bad in (keymaps / "fifo", keymaps / "broken"):
            if bad.name == "fifo":
                os.mkfifo(bad)
            else:
                bad.symlink_to(keymaps / "absent")
            with self.assertRaises((ValueError, FileNotFoundError)):
                smoke.data_files(data)
            bad.unlink()
        with (keymaps / "large").open("wb") as stream:
            stream.truncate(32 * 1024**2 + 1)
        with patch.object(smoke, "identity", wraps=smoke.identity) as identity:
            with self.assertRaisesRegex(ValueError, "size limit"):
                smoke.data_files(data)
        self.assertNotIn(keymaps / "large", [call.args[0] for call in identity.call_args_list])
        (keymaps / "large").unlink()
        nested = data
        for _ in range(9):
            nested /= "nested"
            nested.mkdir()
        with self.assertRaisesRegex(ValueError, "directory limit"):
            smoke.data_files(data)

    def test_low_space_staged_drift_and_master_copy_are_prelaunch_failures(self):
        from types import SimpleNamespace

        with (
            patch.object(smoke, "verify_runtime"),
            patch.object(smoke.shutil, "disk_usage", return_value=SimpleNamespace(free=1)),
        ):
            with self.assertRaisesRegex(ValueError, "disk reservation"):
                smoke.capture_guest(
                    *self.fixture[:2],
                    self.runtime,
                    self.root / "master",
                    self.root / "low-space",
                    master_sha256="0" * 64,
                )
        self.assertFalse((self.root / "low-space").exists())
        with patch.object(smoke, "verify_runtime"), patch.object(smoke.subprocess, "Popen") as launch:
            with self.assertRaisesRegex(ValueError, "identity mismatch"):
                smoke.capture_guest(
                    *self.fixture[:2],
                    self.runtime,
                    self.root / "master",
                    self.root / "bad-master",
                    master_sha256="0" * 64,
                )
            launch.assert_not_called()
        image = self.root / "staged"
        image.mkdir()
        (image / "loader").write_bytes(b"loader")
        record = dict(mode="normal", files={"loader": smoke.identity(image / "loader")})
        smoke.write_json(image / "image.json", record)
        smoke.verify_stage(image, record)
        (image / "loader").write_bytes(b"changed loader")
        with self.assertRaisesRegex(ValueError, "Staged image changed"):
            smoke.verify_stage(image, record)

    def test_make_empty_exports_keep_launcher_defaults(self):
        from types import SimpleNamespace

        probe = subprocess.run(
            ["make", "--no-print-directory", "-s", "-f", "Makefile", "-f", "-", "event-environment-probe"],
            cwd=smoke.ROOT,
            env={"PATH": os.defpath},
            input=(
                "event-environment-probe:\n\t@"
                + sys.executable
                + " -c 'import json,os; print(json.dumps(dict(os.environ)))'\n"
            ),
            text=True,
            capture_output=True,
            timeout=10,
            check=True,
        )
        environment = json.loads(probe.stdout)
        real_which = smoke.shutil.which
        self.assertEqual(environment["QEMU"], "")
        self.assertEqual(environment["EVENT_OUTPUT_PARENT"], "")
        source = self.root / "source"
        source.mkdir()
        (source / "scripts").mkdir()
        (source / "scripts/uefi-linker.sh").write_bytes((smoke.ROOT / "scripts/uefi-linker.sh").read_bytes())
        for mode in smoke.MODES:
            (self.root / (mode + ".raw")).write_bytes(b"fake ESP")
        runs = []
        for failed in (False, True):

            def window(args, directory, runtime):
                runs.append(directory)
                (directory / "evidence").write_text("retained Event output")
                self.assertEqual(args.normal_qemu, "qemu-system-x86_64")
                self.assertEqual(args.output_parent, str(source / "build"))
                if failed:
                    raise ValueError("guest fixture failed")

            with (
                self.subTest(failed=failed),
                patch.dict(os.environ, environment, clear=True),
                patch.object(
                    smoke.shutil,
                    "which",
                    side_effect=lambda tool: sys.executable if tool in ("meson", "ninja") else real_which(tool),
                ),
                patch.object(sys, "argv", ["event-smoke", "--build-only", "--esp-dir", str(self.root)]),
                patch.object(smoke, "ROOT", source),
                patch.object(smoke.shutil, "disk_usage", return_value=SimpleNamespace(free=4 * 1024**3)),
                patch.object(smoke.signal, "signal"),
                patch.object(smoke, "window", side_effect=window),
                patch.object(sys, "stdout", new_callable=io.StringIO) as stdout,
                patch.object(sys, "stderr", new_callable=io.StringIO),
            ):
                self.assertEqual(smoke.cli(), int(failed))
                self.assertIn("Event smoke evidence: " + str(runs[-1]), stdout.getvalue())
            self.assertEqual(runs[-1].parent, source / "build")
            self.assertEqual((runs[-1] / "evidence").read_text(), "retained Event output")
        self.assertNotEqual(runs[0], runs[1])
        self.assertTrue(all((directory / "evidence").exists() for directory in runs))

    def test_tracked_source_output_is_rejected_before_allocation(self):
        source = self.root / "source"
        (source / "tests").mkdir(parents=True)
        for mode in smoke.MODES:
            (self.root / (mode + ".raw")).write_bytes(b"fake ESP")
        for parent in (source, source / "tests"):
            with (
                self.subTest(parent=parent),
                patch.dict(os.environ, {}, clear=True),
                patch.object(smoke, "ROOT", source),
                patch.object(
                    sys,
                    "argv",
                    ["event-smoke", "--build-only", "--esp-dir", str(self.root), "--output-parent", str(parent)],
                ),
                patch.object(smoke.shutil, "which", return_value=sys.executable),
                patch.object(smoke.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")),
                patch.object(smoke.tempfile, "mkdtemp") as allocate,
                patch.object(smoke, "window") as window,
                patch.object(sys, "stderr", new_callable=io.StringIO) as stderr,
            ):
                self.assertEqual(smoke.cli(), 1)
                self.assertIn("Event output must be in build/ or outside the source tree", stderr.getvalue())
                allocate.assert_not_called()
                window.assert_not_called()

    def test_missing_prerequisites_are_blocked_before_build_or_evidence(self):
        for mode in smoke.MODES:
            (self.root / (mode + ".raw")).write_bytes(b"fake ESP")
        for arguments, message in (
            ([], "Set EVENT_BUILD_RECEIPT"),
            (["--build-only"], "Install supported GNU mtools"),
            (["--build-only", "--esp-dir", str(self.root / "missing")], "missing"),
            (["--build-only", "--mtools-dir", str(self.root / "missing-mtools")], "missing-mtools"),
            (["--build-only", "--esp-dir", str(self.root)], "Missing dependency: g++"),
        ):
            with (
                self.subTest(arguments=arguments),
                patch.dict(os.environ, {}, clear=True),
                patch.object(sys, "argv", ["event-smoke", *arguments]),
                patch.object(smoke.shutil, "which", return_value=None),
                patch.object(smoke.tempfile, "mkdtemp") as allocate,
                patch.object(smoke, "window") as window,
                patch.object(sys, "stderr", new_callable=io.StringIO) as stderr,
            ):
                self.assertEqual(smoke.cli(), 2)
                self.assertIn("BLOCKED: Event developer smoke: ", stderr.getvalue())
                self.assertIn(message, stderr.getvalue())
                self.assertNotIn("FAIL:", stderr.getvalue())
                allocate.assert_not_called()
                window.assert_not_called()

    def test_public_make_reports_missing_event_inputs_and_firmware_as_blocked(self):
        for firmware, message in (
            (self.root / "code", "Set EVENT_BUILD_RECEIPT"),
            (self.root / "missing", "requires ordinary OVMF"),
        ):
            with self.subTest(firmware=firmware):
                result = subprocess.run(
                    ["make", "--no-print-directory", "-s", "smoke-iommu-event"],
                    cwd=smoke.ROOT,
                    env={"PATH": os.defpath, "OVMF": str(firmware), "EVENT_OUTPUT_PARENT": str(self.root)},
                    text=True,
                    capture_output=True,
                    timeout=10,
                )
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn("BLOCKED: Event developer smoke", result.stderr)
                self.assertIn(message, result.stderr)
                self.assertNotIn("FAIL:", result.stderr)
                self.assertFalse(list(self.root.glob("aurora-event-smoke-*")))

    def test_missing_inputs_block_but_malformed_receipts_fail_before_allocation(self):
        from types import SimpleNamespace

        real_which = smoke.shutil.which
        esps = self.root / "esps"
        esps.mkdir()
        for mode in smoke.MODES:
            (esps / (mode + ".raw")).write_bytes(b"fake ESP")
        missing = esps / (smoke.MODES[-1] + ".raw")
        receipt = self.root / "receipt.json"
        for kind, message in (
            ("esp", missing.name),
            ("linker", "Missing UEFI PE linker"),
            ("data", "missing-data"),
            ("normal-firmware", "Supply ordinary OVMF"),
            ("space", "Event run requires 1 GiB reservation"),
            ("receipt-key", "Invalid custom runtime receipt"),
            ("receipt-type", "Invalid custom runtime receipt"),
            ("receipt-json", "Expecting property name"),
            ("receipt-missing", "receipt.json"),
        ):
            with self.subTest(kind=kind):
                if kind == "esp":
                    missing.unlink()
                else:
                    missing.write_bytes(b"fake ESP")
                receipt.write_text("{}" if kind == "receipt-key" else '{"source_path": null}')
                if kind == "receipt-json":
                    receipt.write_text("{")
                if kind == "receipt-missing":
                    receipt.unlink()
                args = ["event-smoke", "--esp-dir", str(esps), "--output-parent", str(self.root)]
                if kind in ("esp", "linker", "space"):
                    args += ["--build-only"]
                else:
                    args += [
                        "--build-receipt",
                        str(receipt),
                        "--code",
                        str(self.root / "code"),
                        "--vars",
                        str(self.root / "vars"),
                        "--data",
                        str(self.root / "data"),
                        "--normal-qemu",
                        sys.executable,
                        "--normal-firmware",
                        str(self.root / "code"),
                    ]
                if kind == "data":
                    args += ["--normal-data", str(self.root / "missing-data")]
                if kind == "normal-firmware":
                    args = args[:-2]
                with (
                    patch.dict(
                        os.environ,
                        {"PATH": os.defpath, "UEFI_LD": str(self.root / "missing-ld")}
                        if kind == "linker"
                        else {"PATH": os.defpath},
                        clear=True,
                    ),
                    patch.object(sys, "argv", args),
                    patch.object(
                        smoke.shutil,
                        "which",
                        side_effect=lambda tool: sys.executable if tool in ("meson", "ninja") else real_which(tool),
                    ),
                    patch.object(
                        smoke.shutil,
                        "disk_usage",
                        return_value=SimpleNamespace(free=1 if kind == "space" else 4 * 1024**3),
                    ),
                    patch.object(smoke.tempfile, "mkdtemp") as allocate,
                    patch.object(smoke, "window") as window,
                    patch.object(sys, "stderr", new_callable=io.StringIO) as stderr,
                ):
                    malformed = kind in ("receipt-key", "receipt-type", "receipt-json")
                    self.assertEqual(smoke.cli(), 1 if malformed else 2, stderr.getvalue())
                    self.assertIn(("FAIL" if malformed else "BLOCKED") + ": Event developer smoke: ", stderr.getvalue())
                    self.assertNotIn("BLOCKED:" if malformed else "FAIL:", stderr.getvalue())
                    self.assertIn(message, stderr.getvalue())
                    allocate.assert_not_called()
                    window.assert_not_called()

    def test_post_preflight_build_guest_and_interruption_defects_remain_failed(self):
        for error in (
            ValueError("build admission failed"),
            FileNotFoundError("missing guest output"),
            KeyboardInterrupt("guest interrupted"),
        ):
            with (
                self.subTest(error=error),
                patch.object(sys, "argv", ["event-smoke"]),
                patch.object(smoke, "ROOT", self.root),
                patch.object(smoke, "prerequisites", return_value=(self.root, None)),
                patch.object(smoke.signal, "signal"),
                patch.object(smoke, "window", side_effect=error),
                patch.object(sys, "stderr", new_callable=io.StringIO) as stderr,
            ):
                self.assertEqual(smoke.cli(), 1)
                self.assertIn("FAIL: Event developer smoke: " + str(error), stderr.getvalue())
                self.assertNotIn("BLOCKED:", stderr.getvalue())

    def test_staged_worker_binds_original_admission_and_never_builds(self):
        mode = smoke.MODES[0]
        build = self.root / "kernel-images/uefi" / mode
        build.mkdir(parents=True)
        image = self.root / "staged"
        image.mkdir()
        admitted = {"image": {"value": "current"}}
        staged = {"mode": mode, "checked": {"image": {"value": "current", "payload_layout": {}}}}
        smoke.write_json(image / "image.json", staged)
        loader = image / "esp/EFI/BOOT/BOOTX64.EFI"
        loader.parent.mkdir(parents=True)
        loader.write_bytes(b"admitted staged loader")
        for changed in (False, True):
            with (
                self.subTest(changed=changed),
                patch.object(smoke.admission, "configure_paths") as configure,
                patch.object(smoke.admission, "checked", side_effect=[admitted, {} if changed else admitted]),
                patch.object(smoke, "verify_stage") as verify,
                patch.object(smoke, "capture_guest") as capture,
                patch.object(
                    smoke.esp, "validate_image", return_value={"image_sha256": "bound digest"}
                ) as validate_fat,
                patch.object(smoke, "build") as compile_image,
                patch.object(smoke.signal, "signal"),
            ):
                arguments = (mode, build, image, {}, self.root / "master", self.root / "guest")
                if changed:
                    with self.assertRaisesRegex(ValueError, "changed after launch"):
                        smoke.capture_staged(*arguments, master_sha256="bound digest")
                else:
                    smoke.capture_staged(*arguments, master_sha256="bound digest")
                    self.assertEqual(verify.call_count, 2)
                configure.assert_called_once_with(build, smoke.ROOT)
                capture.assert_called_once_with(
                    mode, staged["checked"], {}, self.root / "master", self.root / "guest", master_sha256="bound digest"
                )
                validate_fat.assert_called_once_with(
                    self.root / "master", smoke.esp.sha256(loader), loader.stat().st_size
                )
                compile_image.assert_not_called()

        with (
            patch.object(smoke.admission, "configure_paths"),
            patch.object(smoke.admission, "checked", return_value=admitted),
            patch.object(smoke, "verify_stage"),
            patch.object(smoke.esp, "validate_image", return_value={"image_sha256": "different master"}),
            patch.object(smoke, "capture_guest") as capture,
        ):
            with self.assertRaisesRegex(ValueError, "master differs"):
                smoke.capture_staged(
                    mode, build, image, {}, self.root / "master", self.root / "guest", master_sha256="bound digest"
                )
            with self.assertRaisesRegex(ValueError, "cannot modify"):
                smoke.capture_staged(
                    mode, build, image, {}, self.root / "master", image / "guest", master_sha256="bound digest"
                )
            capture.assert_not_called()

    def test_build_only_checks_isolated_profiles_and_never_launches(self):
        from types import SimpleNamespace

        run, esps = self.root / "build-only", self.root / "esps"
        run.mkdir()
        esps.mkdir()
        for mode in smoke.MODES:
            (esps / (mode + ".raw")).write_bytes(b"tiny fake ESP")
        args = SimpleNamespace(build_only=True, esp_dir=str(esps))
        calls = []

        def stage(mode, image):
            loader = image / "esp/EFI/BOOT/BOOTX64.EFI"
            loader.parent.mkdir(parents=True)
            loader.write_bytes(b"fresh loader")
            return {"files": {}}

        with (
            patch.object(smoke, "build", side_effect=lambda mode, *_: calls.append(mode)),
            patch.object(smoke, "stage", side_effect=stage),
            patch.object(smoke, "verify_stage"),
            patch.object(
                smoke.esp, "validate_image", side_effect=lambda path, *_: {"image_sha256": smoke.esp.sha256(path)}
            ),
            patch.object(smoke, "normal_boot") as normal_boot,
            patch.object(smoke, "capture_guest") as guest,
        ):
            smoke.window(args, run, None)
        self.assertEqual(calls, ["normal", *smoke.MODES])
        normal_boot.assert_not_called()
        guest.assert_not_called()
        self.assertFalse(smoke.read_json(run / "summary.json")["errors"])

    def test_normal_restoration_also_disables_ambient_qemu_config(self):
        from types import SimpleNamespace

        args = SimpleNamespace(
            normal_qemu=str(self.root / "code"),
            normal_firmware=str(self.root / "vars"),
            normal_code="",
            normal_vars="",
            normal_data="",
        )

        def child(argv, log, **kwargs):
            self.assertEqual(argv.count("-no-user-config"), 1)
            self.assertNotIn("-readconfig", argv)
            log.write_text("normal fixture")
            return 33

        with (
            patch.object(smoke, "bounded_child", side_effect=child),
            patch.object(smoke.normal, "validate") as validate,
        ):
            smoke.normal_boot(args, self.root, self.root / "normal-image")
        validate.assert_called_once_with(33, "normal fixture", "normal")

    def test_window_restores_once_after_failure_and_keeps_both_errors(self):
        args = type("Args", (), dict(build_only=False))()
        run = self.root / "window"
        run.mkdir()
        calls = []

        def build(mode, *_args, **_kwargs):
            calls.append(mode)
            if mode != "normal":
                raise ValueError("Event build failed after child reaped")

        with (
            patch.object(smoke, "build", side_effect=build),
            patch.object(smoke, "stage", return_value={"files": {}}),
            patch.object(smoke, "normal_boot", side_effect=ValueError("normal boot failed")),
            patch.object(smoke, "verify_stage"),
            patch.object(smoke, "BUILD", self.root / "absent"),
        ):
            with self.assertRaises(ValueError):
                smoke.window(args, run, None)
        self.assertEqual(calls, ["normal", "iommu-event-denial"])
        errors = smoke.read_json(run / "summary.json")["errors"]
        self.assertEqual(len(errors), 2)
        self.assertIn("Event build failed", errors[0])
        self.assertIn("normal boot failed", errors[1])
        run = self.root / "unreaped"
        run.mkdir()
        with (
            patch.object(smoke, "build", side_effect=smoke.ChildNotReaped("unreaped")),
            patch.object(smoke, "normal_boot") as restore,
        ):
            with self.assertRaises(ValueError):
                smoke.window(args, run, None)
            restore.assert_not_called()
        self.assertIn("restoration blocked", smoke.read_json(run / "summary.json")["errors"][-1])


if __name__ == "__main__":
    unittest.main()
