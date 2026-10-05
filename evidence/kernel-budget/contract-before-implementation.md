# Bounded kernel policy plan

Before implementation, the parent approved the interrupt-count transition in
`kernel/uefi/service-timer.inc`, implemented in accepted M022 Aurora and reached
by the real UEFI timer path. No pending overload, optional, mutable-byte,
XFS-extent or framebuffer candidate is a dependency. The policy cannot receive
or manufacture domain, frame, root, timer or memory authority.

The complete source/runtime/transport contract and positive/negative acceptance
gates are in `docs/kernel-budget-contract.md`. Final acceptance remains pending
independent review, native checks, fresh aggregate and all baseline/additional
actual emulator gates with normal restoration boots.

Baseline: accepted main `a7a6fcd62466bde283cb99d936383502492a19ef`, tree
`d699abb5250a2b58c98a3d3c331cb02a7650f1a5`, 521 exact sealed product files.
Compiler: M022 SHA256
`e1953ce8446973194a66ba579809c37459466f746f491a53a98b1c910ef4110e`.
Initial preparation disk ceiling: 128 MiB with a 1 GiB free-space floor. Heavy
build/emulator windows are coordinated with the compiler and firmware lanes.
No publication or main writes are authorized before the parent final seal.

The first compile used unsupported logical-or spelling in two source guards and
failed normally before output. The exact first source and compiler diagnostics
are retained under `first-compile`; separate ordered guards fixed this source
mistake without changing the compiler. The corrected module graph compiles with
the accepted compiler. That preflight is not native or kernel acceptance.
