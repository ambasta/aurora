# Verifier resource regression: maximum array initialization

## Reproduced failure

An extra ASan+UBSan compiler run hit the existing five-second test-command timeout on the supported 4096-element array case. There was no address/undefined-behavior sanitizer diagnostic before the timeout. The failed receipt is retained in `docs/evidence/milestone-003/compiler-sanitizers.log` rather than replaced with a passing result.

Investigation showed a real resource defect, not just instrumentation overhead: the first typed-IR verifier retained complete operand-stack and initialized-slot-set snapshots at every instruction. A straight-line array initializer grows and shrinks these structures over thousands of instructions, retaining quadratic history. Release compilation peaked around 4.3 GiB; instrumentation magnified the cost enough to exceed the unchanged timeout.

## Exact same-input, same-flags sanitizer comparison

Environment: x86-64 Linux; `g++ (Debian 14.2.0-19) 14.2.0`.

Both binaries were built with:

```sh
g++ -std=c++23 -O1 -g -fsanitize=address,undefined \
    -fno-omit-frame-pointer -Wall -Wextra -Wpedantic -Werror \
    compiler/main.cpp -o COMPILER
```

The same source input was supplied to both compiler binaries, with the same `-o` assembly output operation. Python `time.monotonic()` measured elapsed time and `os.wait4()` supplied that compiler process's own peak RSS and CPU usage; memory values below are Linux KiB. Both runs used `ASAN_OPTIONS=detect_leaks=0` and exited zero without diagnostics.

| Version | Elapsed seconds | Peak RSS KiB | User seconds | System seconds |
| --- | ---: | ---: | ---: | ---: |
| Per-instruction snapshots | 14.6024 | 6,054,528 | 11.581846 | 3.015268 |
| Basic-block-entry snapshots | 0.0809 | 46,448 | 0.065564 | 0.015181 |

Binary SHA-256 values:

- Before: `eca41bff079801c02c39af4395fcc77766409f0cc365b1f6e24e5622411e3b9e`
- After: `f336d8269b9f4de441e3b39a163b6d4e1721ea8b2792a0ae0e1902bc1330bd91`
- Input: `3d657ad1858edba2998703b8d24a244eeef722fae7f1a26df614817411c9932e`

The input is exactly reproducible without a trailing newline:

```python
from pathlib import Path
values = ','.join('1' for _ in range(4096))
Path('array4096.au').write_text(
    'module test; auto test() -> i64 { const array<i64,4096> a={'
    + values + '}; return a[4095]+41; }'
)
```

A separate release measurement went from 2.661 seconds / 4,468,364 KiB to below 0.051 seconds / 10,764 KiB (the latter timing used 50 ms polling, so it is only a coarse upper bound). Independent synchronous release measurement reported 0.011 seconds / 10,768 KiB after the fix. These are observations on this machine, not portable performance promises.

LeakSanitizer itself is disabled because this executor's tracing environment causes its documented ptrace incompatibility. An initial unrestricted measurement reached exit and then produced that LeakSanitizer fatal-environment message; it was not a leak finding. AddressSanitizer and UndefinedBehaviorSanitizer remained enabled for the reported comparison and test gate. The pre-fix binary and original failed receipt were preserved.

## Repair and permanent tests

The worklist now retains abstract states only at basic-block entries: function entry, labels and conditional fallthrough. It walks each straight-line block with one mutable state and records per-instruction reachability separately. Branch/loop joins still intersect initialization facts and merge current-value provenance; bounds tokens, structural legality, parameter prefixes and unreachable-code policy are unchanged.

The direct IR suite includes a portable resource regression for 4096 elements. Instead of loosening timeouts or setting a fragile machine-specific latency threshold, it measures retained-state snapshots/facts and peak operand depth. Observed: one retained entry snapshot, 4096 peak operand values, zero retained entry-value facts for the straight-line initializer. The test permits generous small snapshot/fact bounds but rejects retention of the growing per-instruction history.

Additional cases test an initialization fact removed by a later predecessor, a checked-index token lost on a loop backedge, and identical checked tokens safely joined from both branches. All 203 existing source tests and 46 direct IR tests pass. A stronger nonrecovering ASan+UBSan compiler also passed all 203 source tests under the existing five-second timeout. Final aggregate/oracle/kernel receipts are recorded separately by the integration owner.

## Remaining limitation

This fixes the demonstrated quadratic straight-line history. It does not make the entire verifier linear or provide a compiler-wide resource bound. Initialized-slot sets are still copied at block entries, so retained memory grows with block count times live slot facts.

Independent release measurements for a 4096-element initialized array followed by branches:

- 0 branches: 0.011 seconds, 10,768 KiB peak RSS
- 64 if/else branches: 0.087 seconds, 48,512 KiB
- 128 if/else branches: 0.153 seconds, 85,988 KiB

Compact fact representations and explicit compiler-wide resource budgets remain future hardening. The current regression is evidence for this particular repair, not a general denial-of-service or complexity proof.
