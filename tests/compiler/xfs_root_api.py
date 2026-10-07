#!/usr/bin/env python3
"""Current-source copied-report/layout/privacy checks, with explicit roots/pins."""

import re
import json, pathlib, sys

sys.dont_write_bytecode = True
import xfs_root as r


def main():
    args = r.parser(api=True).parse_args()
    identity = r.configure(args)
    compiler = args.compiler
    directory = r.ARTIFACTS
    suite = r.Suite(compiler, directory, sanitized=args.sanitized_compiler)
    paths = [compiler, *r.input_paths(__file__)]
    pins = {str(p): r.sha(p) for p in paths}
    source = r.PREFIX + r.shared()
    functions = []
    expected = []
    for status in [
        "found",
        "not_found",
        "geometry_rejected",
        "unsupported_profile",
        "invalid_query",
        "invalid_inode",
        "invalid_directory",
    ]:
        name = "api_" + status
        functions.append(name)
        source += (
            f"auto {name}(i64 slot)->u64{{const fs::XfsRootFacts f="
            f"fs::XfsRootFacts(9223372036854775808u64,18446744073709551615u64,3u64,4u64,5u64);"
            f"const fs::XfsRootMatch m=fs::XfsRootMatch(6u64,7u64);"
            f"const fs::XfsRootReport report=fs::XfsRootReport(fs::XfsRootStatus::{status},"
            f"fs::XfsRootIssue::none,f,m);const fs::XfsRootReport copy=report;"
        )
        source += (
            "if(slot==0){return u64(size_of(fs::XfsRootFacts));}if(slot==1){return u64(size_of(fs::XfsRootMatch));}"
            "if(slot==2){return u64(size_of(fs::XfsRootReport));}"
            "if(slot==10){return u64(field_count(fs::XfsRootReport));}return scalar(copy,slot);}\n"
        )
        facts = (2**63, 2**64 - 1, 3, 4, 5) if status in ("found", "not_found") else (0,) * 5
        values = (40, 16, 72, *facts, *((6, 7) if status == "found" else (0, 0)), 0)
        expected.extend(r.Case(name + f"/{i}", "", v) for i, v in enumerate(values))
    report = {
        "status": "running",
        "revision": "current-source root lookup API regression; fresh evidence",
        "pins": pins,
        "compiler_sha256": identity.sha256,
        "compiler_identity": identity.record(),
    }
    try:
        suite.run(source, functions, expected, directory / "values")
        prefix = r.PREFIX + "auto answer()->u64{const array<u8,1> bytes={0u8};"
        rejects = [
            (
                "private helper",
                prefix + "return fs::xr_address(borrow_bytes(bytes),128u64);}",
                ("visible", "unknown", "private"),
            ),
            (
                "private field",
                prefix + "const fs::XfsRootFacts f=fs::XfsRootFacts(1u64,2u64,3u64,4u64,5u64);return f._root;}",
                ("private",),
            ),
            (
                "wrong query type",
                prefix + "const fs::XfsRootReport r="
                "fs::lookup_xfs_v5_512_root(borrow_bytes(bytes),borrow_bytes(bytes),1u64);return 0u64;}",
                ("type", "span"),
            ),
            ("closed enum conversion", prefix + "return u64(fs::XfsRootStatus::found);}", ("enum", "conversion")),
            (
                "private helper remains inaccessible with report argument",
                prefix + "const fs::XfsRootFacts f=fs::XfsRootFacts(1u64,2u64,3u64,4u64,5u64);"
                "return fs::xr_address(f,128u64);}",
                ("unknown", "visible", "private"),
            ),
            (
                "span result excluded by callable type surface",
                r.PREFIX
                + "auto leak()->builtin::span<const u8>{const array<u8,1> bytes={0u8};return borrow_bytes(bytes);}",
                ("result", "return", "supported"),
            ),
        ]
        for i, (label, text, words) in enumerate(rejects):
            for existing in (False, True):
                r.budget(65536)
                d = directory / f"reject-{i}-{int(existing)}"
                d.mkdir()
                path = d / "input.au"
                path.write_text(text)
                out = d / "compiled.s"
                sentinel = b"keep existing artifact\n"
                if existing:
                    out.write_bytes(sentinel)
                try:
                    suite.command([compiler, *r.module_options(), path, "-o", out], d, "compiler", compiler=True)
                except AssertionError:
                    rec = json.loads((d / "compiler.command.json").read_text())
                    diagnostic = (d / "compiler.stderr").read_text()
                    r.require(rec.get("returncode") == 1, "normal rejection exit1")
                    r.require(
                        re.fullmatch(
                            rf"(?:{re.escape(str(path))}:[1-9][0-9]*:[1-9][0-9]*|aurorac): error "
                            r"AU(?:1001|200[12]|3001|4001): [^\n]+\n",
                            diagnostic,
                        )
                        is not None,
                        "compiler diagnostic required",
                    )
                    r.require(any(w in diagnostic.lower() for w in words), "wrong rejection diagnostic")
                    r.require("sanitizer" not in diagnostic.lower(), "sanitizer error not rejection")
                else:
                    raise AssertionError(label + " unexpectedly accepted")
                r.require(out.read_bytes() == sentinel if existing else not out.exists(), "output preservation")
                r.require(path.read_text() == text, "source preservation")
                (d / "receipt.json").write_text(
                    json.dumps(
                        {"status": "passed", "label": label, "existing_output": existing, "diagnostic": diagnostic},
                        indent=2,
                    )
                    + "\n"
                )
        r.require(pins == {str(p): r.sha(p) for p in paths}, "run-stable all inputs")
        identity.verify()
        report.update(status="passed", native_observations=len(expected), source_negative_controls=12)
        print("PASS API77 native observations,12 source negatives")
    except Exception as e:
        report["status"] = "failed"
        report["error"] = str(e)
        raise
    finally:
        report["allocated_bytes"] = r.allocated()
        r.write_checked_receipt(directory / "manifest.json", report, r.budget)


if __name__ == "__main__":
    main()
