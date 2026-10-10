#!/usr/bin/env python3
"""Bounded before/after compiler measurements using verified readonly syntax only."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import shutil
import time


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def program(capacity, repetitions):
    values = ",".join("0u8" for _ in range(capacity))
    result = (
        "module readonly_resources;"
        "auto first(builtin::span<const u8> input)->u8{return input.at(0);}"
        f"auto test()->u64{{array<u8,{capacity}> bytes={{{values}}};"
        f"const array<u8,{capacity}> copy=bytes;"
    )
    for _ in range(repetitions):
        result += (
            "{const builtin::span<const u8> view=borrow_bytes(bytes);"
            "if(first(view)!=copy[0]){return 1u64;}"
            f"i64 index=0;while(index<{capacity}){{"
            "if(view.at(index)!=copy[index]){return 2u64;}"
            "index=index+1;}}"
        )
    return result + "return 42u64;}"


def bounded_command(command, output, cap_mib):
    out_path, err_path = output.with_suffix(".stdout"), output.with_suffix(".stderr")
    started = time.monotonic()
    pid = os.fork()
    if pid == 0:
        try:
            resource.setrlimit(resource.RLIMIT_AS, (cap_mib * 1024 * 1024,) * 2)
            resource.setrlimit(resource.RLIMIT_CPU, (4, 5))
            resource.setrlimit(resource.RLIMIT_FSIZE, (8 * 1024 * 1024,) * 2)
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            with out_path.open("wb") as out, err_path.open("wb") as err:
                os.dup2(out.fileno(), 1)
                os.dup2(err.fileno(), 2)
                os.execv(command[0], command)
        except BaseException:
            os._exit(125)
    deadline = False
    while True:
        waited, status, usage = os.wait4(pid, os.WNOHANG)
        if waited:
            break
        if time.monotonic() - started > 10:
            deadline = True
            os.kill(pid, signal.SIGKILL)
            _, status, usage = os.wait4(pid, 0)
            break
        time.sleep(0.01)
    return dict(
        command=command,
        exit_code=os.waitstatus_to_exitcode(status),
        wall_seconds=time.monotonic() - started,
        max_rss_kib=usage.ru_maxrss,
        user_seconds=usage.ru_utime,
        system_seconds=usage.ru_stime,
        harness_deadline_kill=deadline,
        tool_sha256=digest(Path(command[0])),
        stdout_hex=out_path.read_bytes().hex(),
        stderr_hex=err_path.read_bytes().hex(),
    )


def compile_one(compiler, source, output, module_root, cap_mib):
    before = digest(source)
    command = [str(compiler), "--module-root", str(module_root), str(source), "-o", str(output)]
    result = bounded_command(command, output, cap_mib)
    if digest(source) != before:
        raise RuntimeError("compiler changed input")
    result["source_sha256"] = before
    result["assembly_sha256"] = digest(output) if output.exists() else None
    return result


def native_observation(assembly, output, cap_mib):
    assembler = shutil.which("as")
    linker = shutil.which("ld")
    if not assembler or not linker:
        raise RuntimeError("native tools unavailable")
    bridge = output.with_suffix(".entry.s")
    bridge.write_text(
        ".text\n.globl _start\n_start:\n    call test\n    pushq %rax\n"
        "    movq $1,%rax\n    movq $1,%rdi\n    movq %rsp,%rsi\n"
        "    movq $8,%rdx\n    syscall\n    movq $60,%rax\n"
        "    xorq %rdi,%rdi\n    syscall\n"
        '.section .note.GNU-stack,"",@progbits\n'
    )
    code_object = output.with_suffix(".code.o")
    entry_object = output.with_suffix(".entry.o")
    commands = [
        [assembler, "--64", str(assembly), "-o", str(code_object)],
        [assembler, "--64", str(bridge), "-o", str(entry_object)],
        [linker, "--build-id=none", "-e", "_start", str(entry_object), str(code_object), "-o", str(output)],
        [str(output)],
    ]
    observations = []
    for index, command in enumerate(commands):
        observed = bounded_command(command, output.with_name(output.name + f".step{index}"), cap_mib)
        observations.append(observed)
        if observed["exit_code"] != 0 or observed["harness_deadline_kill"]:
            break
    return observations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--memory-mib", type=int, default=256)
    args = parser.parse_args()
    if not 64 <= args.memory_mib <= 512:
        raise RuntimeError("diagnostic memory cap must stay within64..512MiB")
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    output.mkdir(exist_ok=False)
    tools = {"baseline": args.baseline.resolve(), "candidate": args.candidate.resolve()}
    report = dict(
        scope="Readonly source only; no mutable borrowing prerequisite",
        compiler_sha256={name: digest(path) for name, path in tools.items()},
        driver_sha256=digest(Path(__file__)),
        limits={
            "address_space_mib": args.memory_mib,
            "cpu_seconds": [4, 5],
            "wall_seconds": 10,
            "regular_file_mib": 8,
            "core_bytes": 0,
        },
        results=[],
    )
    for capacity, repetitions in [
        (64, 16),
        (512, 16),
        (4096, 0),
        (4096, 4),
        (4096, 8),
        (4096, 16),
        (4096, 64),
        (4096, 96),
    ]:
        name = f"array{capacity}-blocks{repetitions}"
        source = output / (name + ".au")
        source.write_text(program(capacity, repetitions))
        pair = {"name": name, "source_bytes": source.stat().st_size}
        for label, compiler in tools.items():
            pair[label] = compile_one(
                compiler, source, output / (name + "-" + label + ".s"), root / "library", args.memory_mib
            )
            row = pair[label]
            print(name, label, row["exit_code"], row["max_rss_kib"], row["wall_seconds"], flush=True)
        if pair["baseline"]["exit_code"] == 0 and pair["candidate"]["exit_code"] == 0:
            pair["assembly_identical"] = pair["baseline"]["assembly_sha256"] == pair["candidate"]["assembly_sha256"]
        report["results"].append(pair)
        (output / "results.json").write_text(json.dumps(report, indent=2) + "\n")
        candidate = pair["candidate"]
        if (
            candidate["exit_code"] != 0
            or candidate["harness_deadline_kill"]
            or candidate["assembly_sha256"] is None
            or candidate["stdout_hex"]
            or candidate["stderr_hex"]
        ):
            raise RuntimeError("candidate failed valid readonly corpus; complete receipt retained")
        pair["native"] = native_observation(
            output / (name + "-candidate.s"), output / (name + "-native"), args.memory_mib
        )
        (output / "results.json").write_text(json.dumps(report, indent=2) + "\n")
        if (
            len(pair["native"]) != 4
            or any(row["exit_code"] != 0 or row["harness_deadline_kill"] or row["stderr_hex"] for row in pair["native"])
            or any(row["stdout_hex"] for row in pair["native"][:-1])
            or pair["native"][-1]["stdout_hex"] != (42).to_bytes(8, "little").hex()
        ):
            raise RuntimeError("candidate native result is not exact u64 42; complete receipt retained")
        if pair.get("assembly_identical") is False:
            raise RuntimeError("representation-only change altered assembly; complete receipt retained")
    print("PASS bounded measurements; every candidate returns exact u64 42 and all joint assemblies match")


if __name__ == "__main__":
    main()
