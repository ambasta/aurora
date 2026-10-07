# Hosted owned-byte results — 2026-10-07

The [owned-byte contract](../compiler/OWNED-BYTES.md) has independent source review
and a passing focused native composite. This is an initial runtime allocation and
lifetime prerequisite, backed by an explicit trusted host adapter. It is not
kernel allocation, a complete native runtime, general resource classes or a
memory-safety proof. Final retained-evidence review is recorded separately.

## Exact source and compiler scope

The feature started from PR67 main
`90b905a6ec31a4d0b24c4ae7f0d14814fe758f4d`, tree
`cf82bbfa2a9620a1d07267c472dcf8a1e382fc84` (759 files).
Before dependency qualification it incorporated all nineteen independently
accepted PR68 paths, based on main
`e1075c60cb8af83c453fb1dfac910743ac903655`, tree
`b0cd4aef217ec39b0a2cb04dfcaf5ed7ffdc2760` (771 files).
Only the completeness-matrix text overlapped. Compiler, runtime and owned-byte
fixtures were unchanged by that join.

The final tested implementation has 777 files, tree
`6a8fba76e0df24df263034239361b5527bb5c269`, manifest SHA256
`78a3ee963fdbab3d3a09a2d47f12078fab3b14c5e6d9f86f935e3f4770dd851a`.
The results/acceptance documentation is a later leaf overlay, not an unrecorded
implementation change.

Two fresh warning-clean GNU C++23 release builds are retained:

- Initial feature compiler:
  `5351143f6cfd90fb5d8b274dde68c8f0f715698be97e5d2e8003516e31f35d31`.
  It executed the owned-byte corpus and current PR68 core/byte dependencies.
- Final compiler after restoring the existing span diagnostic:
  `b7b3de01cf86910650f9da9324549e36c388896a04a0fcbb31d5b89b13acdd1d`.
  The only compiler change was separating span/resource reflection rejection
  messages. All fifteen feature assemblies are byte-identical to those already
  executed. Source admission/rejection and affected frontend/IR dependencies
  were rerun with this compiler.

The final fresh formatter is
`f05fabe1edb3bc91f0c0373974bde99f875d966346703e2c051cdbc8ad93a3af`.
This is a reviewed composite of focused runs, not a fresh full aggregate or an
externally pinned `make test-acceptance` run.

## Observable results

- Owned-byte native runner: 29 native cases, four exact bounds-UD2 observations
  and 29 rejection fixtures in each of normal and optimized Python. Each rejection
  preserves both an absent output and a preexisting output. These are overlapping
  executions of one corpus, not distinct coverage counts to add together.
- The same generated function accepts runtime lengths 0, 1, 65, 513 and 4097.
  Real host allocation/free observations distinguish two simultaneous owners,
  track actual release order, and verify that moves do not allocate again.
  Tests cover initialized bytes, copied access, local/function transfer, returned
  allocation failure, multiple owning parameters, normal scope/return/branch/loop
  cleanup, quota reuse and injected host failure preserving an existing owner.
- Direct typed IR: 61 accepted and 263 rejected cases, including malformed
  storage, identity/lifetime, provenance, call/return and control-flow fixtures,
  plus resource-graph local linkage and scalar-only linkage controls.
- Isolated hosted adapter: 19,453 checks and 36 expected fail-stop child cases
  normally and with fatal AddressSanitizer/UndefinedBehaviorSanitizer. These
  finite checks include zero-length identity, allocation failure, quota accounting,
  stale/forged descriptors, close refusal and nonwrapping identity exhaustion.
- Current PR68 dependency graph: all eleven preexisting Meson core tests and all
  twelve byte tests passed. The expanded XFS-file runner passed 841 native cases
  and eleven rejections with the initial feature compiler.
- Final-compiler dependencies: 91 readonly-span native cases/25 exact bounds traps
  and 69 rejection fixtures; 132 window cases/66 exact traps and 21 rejections;
  all 320 short-circuit fixtures; 117 scalar-template checks; complete function
  template and overload runners; 964 base typed-IR checks; ten exhaustive-dispatch
  controls; the existing native array/value/enum/u8/packed/span ABI oracles;
  47 stack-probe cases and fifteen isolated stack-guard cases.
- Formatter: one C++ unit-suite run passed 84 corpus sources and 128 trivia
  variants. Separately, thirty CLI cases passed in each Python mode. All fifteen
  owned-byte programs format, recompile and retain identical assembly. Semantic
  lint passes 62 cases per mode, including its retained native initializer side
  effect.
- All 29 current scalar-only examples have byte-identical assembly and identical
  global/undefined symbols versus the retained pre-feature compiler. None gains
  a hosted-byte runtime dependency. Resource graphs separately execute source
  helpers named malloc/free/memset/abort/fputs/fflush/printf while those symbols
  remain local, preventing host-adapter interposition.

Commands, exact statuses, source manifests, compiler identities, native artifacts
and preserved failure records accompany the private source/evidence checkpoint.
Source hashes were checked across every implementation-qualified phase. Native
sessions reached their actual terminal statuses before the next shared build.
Retained native outputs measured approximately 46.9 MB before final evidence
packaging, below 256 MiB per phase and 1 GiB across the invocation. A 1 GiB
free-space floor remained in place; no cap was raised to make a run pass.
The initial phase began under the 1 GiB invocation guard before its explicit
256 MiB phase clarification; stricter observations confirmed it stayed below that
phase bound. Subsequent wrappers encode both limits. These are sampled output
checks, not filesystem quotas or a whole-program memory bound.

## Preserved corrections and limits

Source review caught and corrected misplaced frontend dispatch and the possibility
of scalar helper symbols interposing the trusted allocator. Both were fixed before
any generated owned-byte program ran. Source/IR-reserved test bridge names and
module-wide local linkage are part of the resulting contract.

The first native attempt stopped on a host fixture that changed a failed
allocation descriptor's region to zero. That accidentally created the valid inert
all-zero moved/pristine descriptor. The corrected fixture uses a nonzero ungranted
ID and retains separate all-zero cleanup coverage. No production adapter change
was needed; the original exit-one source and receipt remain preserved.

LeakSanitizer reported a fatal ptrace-environment incompatibility and aborted its
first instrumented run. The same binary then passed with:

```text
ASAN_OPTIONS=abort_on_error=1:halt_on_error=1:detect_leaks=0
UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1
```

Leak detection is not qualified. Explicit allocation/free ledger tests establish
only their stated cases, not a general leak proof. Generated Aurora assembly is
not sanitizer-instrumented, and no full compiler sanitizer regression is claimed.

Dependency preparation also caught a changed span reflection diagnostic before
that runner executed. Restoring its original text, with a separate resource
rejection branch, preserved the existing oracle and changed no accepted-source
lowering. The correction was independently reviewed, rebuilt and checked as above.

No full native aggregate, emulator/kernel image, physical hardware, performance,
resize, payload view, arbitrary destructor, general process entry ABI or native
JSON/library completeness claim is added. Fail-stop traps still do not unwind
owned resources; service/process reclamation remains a separate prerequisite.
