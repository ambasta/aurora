# Client-disposal recovery-plan port — unfinished

This candidate begins from accepted PR84, commit
`2427806afcd64afc0871cda78130a388a32cc1f8`, and uses its accepted compiler
SHA256 `512050d547be364fe859031417994fe5c2de69814eed4fffd801ba1e2e92fe7c`.
The accepted resize PR85 delta has been reconciled against current main
`36219aef05cf74db710b50fae9011190f3bfcee1`, tree
`d1acfbd64ca74af747f8bdf5faa19cfc85bd2f87`. Its independently accepted
owned-byte behavior is preserved; its results are not inherited by this port.

Initial production code calls Aurora before selecting the actual recovery plan.
The existing ordinary user-run/disposal host suite passed on the initial source:
20,611 user authority/frame checks, 65,536 four-operation disposal sequences,
4,096 128-operation model traces, and existing image/transcript controls.
The two new transcript profiles subsequently passed 38 positive and 26,362
negative synthetic receipt controls. These are provisional focused results,
not final frozen-source or guest qualification.

Independent new oracle/substituted-producer controls, fatal host sanitizer,
exact linked stack/image review, changed actual guest gates, current-main join
and independent final acceptance remain pending. This checkpoint is unverified.

## Preserved development corrections

The first independent runner passed new producer/decoder/hostile adapter checks,
then GCC14 rejected the unchanged historical disposal regression at `-O2` with
`-Werror=array-bounds`. That regression's established public recipe uses `-O1`.
Only this old regression's runner flags were corrected to its historical level;
new tests retain `-O2`, warnings remain fatal, and the old test source is unchanged.
Fresh corrected complete runner execution remains required.

Initial emulator clock controls exposed two stale numeric inventories after
adding the two new modes. Counts were extended by exactly two, preserving the
original modes and clocks; corrected controls passed. The original 17-mode
user-phase synthetic fixture corpus is now pinned independently across both
client-interrupt variants; the new profiles cannot redefine those fixtures.

The build-routing control suite also exposed a pre-existing overly positional
check for `test: test-round-robin`: accepted main already lists `test-console`
before that prerequisite. The original failure was reproduced on PR84. The
check now accepts the exact round-robin prerequisite anywhere on a test target
line, without dropping it or changing the aggregate.
