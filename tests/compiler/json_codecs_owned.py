#!/usr/bin/env python3
"""Exercise owner-backed codec windows and the shipped JSON codec example."""

import argparse, hashlib, json, pathlib, shutil, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
if "--repo-root" in sys.argv:
    ROOT = pathlib.Path(sys.argv[sys.argv.index("--repo-root") + 1]).resolve()
sys.path.insert(0, str(ROOT / "tests/compiler"))
import owned_bytes as host
from unsigned_oracle import require

p = argparse.ArgumentParser()
p.add_argument("--repo-root", type=pathlib.Path, default=ROOT)
p.add_argument("compiler", type=pathlib.Path)
p.add_argument("--artifacts", type=pathlib.Path, required=True)
a = p.parse_args()
a.compiler = a.compiler.resolve(strict=True)
compiler_digest = hashlib.sha256(a.compiler.read_bytes()).hexdigest()
a.artifacts.mkdir(parents=True, exist_ok=False)
commands = []
cases = []
original_command = host.command


def recorded_command(argv, *args, **kwargs):
    result = original_command(argv, *args, **kwargs)
    commands.append(
        {
            "argv": [str(x) for x in argv],
            "kwargs": {k: str(v) for k, v in kwargs.items()},
            "returncode": result.returncode,
            "stdout_hex": result.stdout.hex(),
            "stderr_hex": result.stderr.hex(),
        }
    )
    (a.artifacts / "commands.json").write_text(json.dumps(commands, indent=2) + "\n")
    return result


host.command = recorded_command


class AuditedSuite(host.Suite):
    def run(self, executable, quota, length, flag, expected, allocations, peak, fail_after=None, release_order=None):
        case = {
            "executable": str(executable),
            "quota": quota,
            "length": length,
            "flag": flag,
            "expected": expected,
            "allocations": allocations,
            "peak": peak,
            "fail_after": fail_after,
            "release_order": release_order,
        }
        cases.append(case)
        (a.artifacts / "cases.json").write_text(json.dumps(cases, indent=2) + "\n")
        super().run(executable, quota, length, flag, expected, allocations, peak, fail_after, release_order)
        case["observed"] = [int(x) for x in self.last_observation.stdout.split()]
        case["passed"] = True
        (a.artifacts / "cases.json").write_text(json.dumps(cases, indent=2) + "\n")


lib = a.artifacts / "library"
shutil.copytree(ROOT / "library", lib)
identities = {str(f.relative_to(a.artifacts)): hashlib.sha256(f.read_bytes()).hexdigest() for f in lib.rglob("*.au")}
bound_files = [
    pathlib.Path(__file__).resolve(),
    ROOT / "tests/compiler/owned_bytes.py",
    ROOT / "tests/compiler/unsigned_oracle.py",
    ROOT / "runtime/hosted_bytes.cpp",
    ROOT / "runtime/hosted_bytes.hpp",
    ROOT / "library/examples/json_codecs.au",
]
bound = {str(f): hashlib.sha256(f.read_bytes()).hexdigest() for f in bound_files}
host.ROOT = ROOT
s = AuditedSuite(a.compiler, a.artifacts, lib, entry_name="json_codecs_example")
example = (ROOT / "library/examples/json_codecs.au").read_text()
e = s.compile("owned-example-roundtrip", example)
raw = b'"A\\u0000\\n\\/\\"\\\\\xc3\xa9\\uD83D\\uDE00"'
decoded = json.loads(raw).encode()
encoded = json.dumps(json.loads(raw), ensure_ascii=False, separators=(",", ":")).encode()
for index, value in [(-1, len(decoded)), (-2, len(encoded)), (-(2**63), 256), *enumerate(decoded + encoded)]:
    s.run(e, 128, 64, index, value, 2, 2, release_order=[2, 1])
source = """module large_json_scalar;
import std.json; import std.array;
auto entry(builtin::ByteRegion region,i64 n,i64 flag)->i64 {
    builtin::OwnedBytes input=region.try_allocate(n);
    if(!input.ok()){ return -1; }
    input.set(0,65u8);
    input.set(n-1,92u8);
    const builtin::span<const u8> all=borrow_bytes(input);
    const std::JsonScalarResult first=std::decode_json_string_scalar(all,0,n);
    if(first.status()!=std::JsonStatus::success || first.scalar_or(0u64)!=65u64 ||
       first.consumed_bytes()!=1){ return -2; }
    const std::JsonScalarResult cut=std::decode_json_string_scalar(all,n-1,1);
    if(cut.status()!=std::JsonStatus::truncated || cut.error_offset()!=n){ return -3; }
    const builtin::span<const u8> tail=all.subspan(n-1,1);
    const std::JsonScalarResult nested=std::decode_json_string_scalar(tail,0,1);
    if(nested.status()!=std::JsonStatus::truncated || nested.error_offset()!=1){ return -4; }
    return 42;
}"""
e = s.compile("large-owned-window", source, entry_name="entry")
for n in [4096, 4097, 5000, 8192]:
    s.run(e, n, n, 0, 42, 1, 1)
for f, digest in bound.items():
    require(hashlib.sha256(pathlib.Path(f).read_bytes()).hexdigest() == digest, "bound source changed")
for f, digest in identities.items():
    require(hashlib.sha256((a.artifacts / f).read_bytes()).hexdigest() == digest, "library changed")
require(hashlib.sha256(a.compiler.read_bytes()).hexdigest() == compiler_digest, "compiler changed")
result = {
    "optimized": not __debug__,
    "programs": s.programs,
    "native_cases": s.native,
    "compiler_sha256": compiler_digest,
    "library": identities,
    "bound_inputs": bound,
    "generated_inputs": {
        str(f.relative_to(a.artifacts)): hashlib.sha256(f.read_bytes()).hexdigest()
        for f in a.artifacts.rglob("input.au")
    },
    "decoded_hex": decoded.hex(),
    "escaped_hex": encoded.hex(),
    "runtime": {
        str(f): hashlib.sha256(f.read_bytes()).hexdigest() for f in (host.ROOT / "runtime").glob("hosted_bytes.*")
    },
    "scope": "actual owner-backed codec windows and example revalidation; no full aggregate or kernel claim",
}
(a.artifacts / "result.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result))
