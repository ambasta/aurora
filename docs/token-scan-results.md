# Bounded ASCII token scanner qualification — 2026-10-06

The Aurora-authored `std.token_scan` scanner passed a fresh complete root release
native aggregate and a separate focused fatal host ASan/UBSan scanner gate, with
independent source and retained-evidence review. It consumes readonly final byte
windows and returns independent lexical kinds, coordinates, consumption and LF
counts. See the [exact contract and dated scope amendment](token-scan-contract.md)
and [compact receipt identities](../evidence/token-scan/qualification.json).

The accepted baseline was main `ca178a69ef1895f5ca7ce635c7761318039ff775`, tree
`de129c66e63b36eac321be0bd9f6808bc75a6918`. Each executed candidate contained
584 source files. The later publication overlay updates only documentation and
adds this results document plus the compact evidence record. All tested library,
example, compiler Make and test bytes are unchanged. The compiler implementation,
parser, host lexer and kernel are unchanged from the baseline.

## What is implemented

`std::next_token(span, offset, count)` scans a final window in a readonly byte span
bounded at 4096 bytes. Explicit ASCII whitespace, identifiers, digit-started
alphanumeric/underscore words, opaque `//` comments, existing punctuation and ten
two-byte operators follow the host lexer's C-locale profile. Only skipped LF bytes
increment the report's LF count. A window starts with no inherited lexical state.

The copied `TokenResult` retains no source borrow. Success gives exact token
coordinates; EOF accounts for remaining trivia; unsupported bytes consume one
byte after trivia so recovery progresses; invalid windows expose no payload.
Public constructed reports check shape only and are not parsing certificates.
A lexical digit word is not a validated integer or a parser-accepted expression.

The example `examples/token_scan.au` returns 42 and retains a report after the
owner can be mutated. No dynamic allocation, returned reference, runtime import,
compiler/parser integration, string layer or general native toolchain is added.

## Actual release execution

The command was `/usr/bin/make --jobs=1 test`, with a clean owned environment and
`CXX=/usr/bin/g++-14`. The shared build-once route built the current compiler once,
then routed the complete root native graph through its read-only executable.
Both the outer terminal and fresh `run.json` passed, with `scope: native-aggregate`
and `native_complete: true`. The two normal/optimized 70-test compiler-contract
suites reached OK; existing compiler, IR, ABI, module, native kernel/image/model,
storage, semantic, package and test-contract gates remained in the graph.

Observed release compiler SHA256:
`66bb719d0ad1622e97b7e448a724d153bb370080f0ce4aa1e5a0b6b322a4a298`.
The shared run is a fresh developer build, not a claim of independently pinned
prebuilt acceptance. Its run SHA256 is
`5950a6e597b607afb3c706e6efe43c336e209c85456936a0a542499569fc49fa`.

Elapsed time was 2652.792 seconds. Maximum observed owned allocation was
614,510,592 bytes; TMP was 14,131,200 bytes; tracked text logs were 1,401,357 bytes.
All 584 source hashes, lengths and modes, 357 recorded bootstrap headers and
recorded host tool identities remained unchanged. Owned cleanup was quiescent;
two observed zombie descendants were reaped, with no live process remaining.
The bounded software observations are not kernel disk quotas or global peak proofs.

## Actual focused fatal host sanitizer execution

A separate fresh source copy ran `make -C compiler test-token-scan` with both
`CXXFLAGS` and `IR_TEST_CXXFLAGS` set to:

    -std=c++23 -O1 -g1 -Wall -Wextra -Wpedantic -Werror
    -fno-omit-frame-pointer -fno-optimize-sibling-calls
    -fsanitize=address,undefined -fno-sanitize-recover=all -fno-pie -no-pie

The environment used `ASAN_OPTIONS=detect_leaks=0:halt_on_error=1:abort_on_error=1`
and `UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1`. Both inherited address-space
limits were verified unlimited before launch; the instrumented compiler and host
adapter had no incompatible small AS cap. Existing ordinary native/tool caps
remained in place. Sanitizer failures and unexpected stderr were fatal.

Observed instrumented compiler SHA256:
`a2655f8e919eadd27006d66430d0b364efae2c86f892b8d0f1775f1a2e4ea75a`.
The focused shared run SHA256 is
`34dd826ccafb4b05245e134de375cb3b14ef13e181484c30dc64ca8752210b04`.
It passed with `scope: focused` and `native_complete: false`.

Retained `readelf`/`nm` output verifies `libasan.so.8`, `libubsan.so.1`,
`__asan_init` and actual `__ubsan_handle_*_abort` symbols on both the host compiler
and the unchanged-host-lexer adapter. Their runtime/tool identities remained
unchanged. Elapsed time was 134.380 seconds; maximum observed owned allocation
was 90,767,360 bytes and sampled owned-descendant RSS was 1,081,344,000 bytes.
All 584 source files remained unchanged and every owned session closed quiescent.

This instruments host compiler/lexer behavior exercised by the scanner gate.
Generated Aurora assembly/native programs are not sanitizer-instrumented. Leak
checking is disabled. This is not complete compiler sanitizer regression or a
full sanitizer native aggregate. The initial contract's broader sanitizer wording
is retained as history, with a dated explicit acceptance-scope amendment.

## Scanner observations independently checked in each successful run

The focused release replay, complete release aggregate and focused host sanitizer
each passed the same gate. These overlapping runs are not summed as disjoint cases:

- 128 batches, 1972 cases and 15,612 complete signed-i64 observations.
- 1129 individual scans, 267 public-report shapes, five copied reports whose
  source owner has expired, and 571 repeated-scan traces.
- All 256 byte values inside/outside comments, clipped words/pairs/comments,
  nested and true zero-length subspans, signed coordinate extremes, maximum
  4096-byte owners, final EOF trivia, recovery, exact spelling reconstruction,
  source preservation and copied reports after borrow release/owner mutation.
- The unchanged C-locale host lexer matches 403 valid spelling/line streams.
  Another 168 invalid streams reject separately from recoverable byte scanning.
- 33 rejection commands return 1 and preserve pre-existing outputs. Unsupported
  span field/return types are distinguished from genuine live-borrow owner-write
  lifetime rejections; they are not falsely credited as lifetime analysis.
- Five deliberate semantic mutants compile, link and execute successfully but
  disagree with full-length oracle output. Compiler failures are not detections.
- The unchanged example returns full-width 42, and declared object/native
  undefined-import checks return no imports.

The author oracle uses byte regexes and slicing. Independent review reconstructed
all retained fixtures with a separate explicit-byte scalar model and checked all
15,612 raw observations for each final stage, plus host/error/mutant/example and
972 command receipts. Release and focused-sanitizer scanner output bytes agree.
Review of older families uses their retained recipes, summaries and artifacts;
not every historical harness retains every raw observation, and no such claim is
made. The final independent terminal disposition SHA256 is
`fbcec9054d6f573a5007932e9d1540792e88ab5a9e50e90311f19c69ad3ae9a3`.

## Preserved failure and exact correction

The first focused attempt remains failed. All 1972 native cases completed, but a
negative fixture expected the word `span` in the compiler's returned-span type
rejection. The actual diagnostic was `only scalar function results or scalar-field
class values are supported`; the compiler correctly rejected it and preserved
its output marker. This occurs before body/lifetime analysis.

The second source changed exactly that fixture's label and expected diagnostic
fragment. Its rejected program and all product bytes were unchanged. A fresh
focused run passed all remaining gates. No prefix of the failed run was reused as
acceptance and its failed product/outer receipts remain preserved. Source failure
and runtime defects are not invented to describe this harness-expectation fix.

Raw failed/focused, full release and narrow fatal-host archives are separately
preserved with verified official Library materialization readbacks. Compact hashes
identify them without implying public repository access to those private backups.

## Limits and publication

No new QEMU run, physical AMD qualification, complete sanitizer regression,
leak-clean result, self-hosting compiler, language-wide safety proof or equivalent-C
performance result follows from these gates. PR28's separate blocked review is
unchanged. This library consumer is one bounded self-hosting dependency.

Publication must use a delta over the verified full baseline tree, preserving
historical blobs omitted from the 584-file source-only test snapshot. Documentation
and evidence overlays receive separate static review; they are not represented as
another native run. Publication/remote CI status is separate from these local gates.
