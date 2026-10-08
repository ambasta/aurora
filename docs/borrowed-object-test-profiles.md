# Borrowed-object test profiles

`tests/compiler/borrowed_objects.py` defaults to the complete source/native gate.
Its coverage is 18 compiled programs, 74 hosted runtime observations and
68 rejection fixtures, each checked with both absent and pre-existing output.
One of the compiled programs checks that importing only `std.json` and validating
a builtin byte span emits no owning-runtime reference. Fresh focused execution and its limits are recorded in
[the results](borrowed-objects-results.md).

The full shared-alias program also checks copied and scalar borrowed-call result
bindings that shadow their source formal, a scalar method-result shadow, and
shared forwarding of the formal with its own temporary byte span. A later write
and complete byte observation check that the forwarded span and loan ended.

The opt-in `--smoke` profile selects two existing real native programs:

- `forwarding-and-independent-result`
- `json-forwarded-borrow-copied-result`

These retain the complete byte, copied-result, allocation-identity and normal
cleanup assertions from the full gate. The profile also checks seven existing
rejection fixtures with both output states:

- `mutable-later-mutation`
- `named-empty-self-span`
- `shared-later-mutation`
- `const-owner-escalation`
- `formal-move-to-local`
- `borrowed-span-result`
- `json-writer-later-read-of-output`

Use `python3 tests/compiler/borrowed_objects.py <compiler> --smoke` for this partial
developer feedback, or omit `--smoke` for the full runner. Add `--artifacts <new
directory>` to retain receipts after success. `--compile-only` is orthogonal:
it skips native linking/execution and cannot establish the full native gate.

Inputs and summaries state the profile. `selection.json` records selected and
omitted program/rejection names; `cases.json` records every selected runtime
invocation and its observations. A smoke summary always has
`partial_coverage: true` and `full_borrowed_objects_gate: false`. The same full-gate
flag is false for compile-only runs. Missing named smoke fixtures, an uncompiled
selected program, an incomplete rejection or missing runtime-case accounting
prevent a passing summary. Failed runs retain their artifacts.

Smoke success is not full borrowed-object, complete root-native, sanitizer,
kernel or hardware qualification. The public full routes must keep the runner's
default exhaustive selection.
