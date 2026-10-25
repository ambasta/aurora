# Sequential protected programs after UEFI handoff

This slice brings the existing compiled-program isolation contract onto the
real OVMF handoff path. After ExitBootServices, owned paging and read-only
ACPI/PCI discovery, the payload runs two compiled Aurora programs at CPL3 under
separate CR3 roots. A known bounds trap is contained, clean execution follows,
and retired stack frames are scrubbed and reused. There is no scheduler, IPC,
controller activation, DMA ownership or general process lifecycle in this slice.

The clean fixture executes `std::pair<i64,u64>` template-generated code and,
in the next candidate, stores and reads that result through `std::array<i64,2>`
`set`/`at`, returning 42 through the same scalar transition. Trusted C++/assembly remains
temporary bootstrap machinery; this is not a language-native complete kernel.

## Relocation and ownership

[Bootstrap dimensions](../bootstrap-layout-values.inc) and
[image page policies](image-page-policies.inc) are shared tables for C++ and the
generated profile metadata. Host image and boot checks use the same metadata loader.

Handoff version 3 retains the allocated 1 MiB arena and adds an exact metadata
pointer at arena + 0x81000. Version 1 and 2 profiles remain valid with their
original layouts. The final firmware map must own the whole arena below 4 GiB.
Every runtime interval is checked for page alignment, overflow, overlap and
bounds. The domain builder receives only those owned physical frames.

Protected user images have 16 KiB virtual slots beginning at 0x10000000000.
Each slot contains at most three RX code pages followed by an unmapped guard.
These are chosen canonical lower-half virtual addresses, not physical load
addresses or BIOS constants. Their immutable, boot-owned physical slots occupy three pages each, beginning
at arena + 0xb0000 (then +0xb3000 and, for dispatch, +0xb6000). `runtime-fixture`
installs a five-slot bank up to +0xbf000 (clean, bounds, span, two multipage) and
each row selects the two slots acting as images 0 and 1; `service-fixture`
installs eleven one-page slots packed one page apart up to +0xbb000, and each
row selects the slots acting as its two or three images. Link metadata, exact entry, segment permissions and every trap site
are validated before installation. `runtime-fixture` admits three pages per
image, which its multipage row needs; its other bank images are linked at one page. Blocking-call profiles admit two pages for the caller and one for the
service; owned-text profiles (including console-region) admit three pages for
the first image and one for the second. Other profiles retain one-page image
allowances. Metadata cannot select its own allowance. The linker, image validator, loader and runtime independently
enforce the selected bound; BIOS remains one page. The loader zeros all slots
before publication. User roots map only the rounded validated byte extent, and
verification checks every required leaf plus absent unused/guard/foreign pages.
Trap authority remains bounded by actual bytes, not mapped padding. The UEFI payload is independently position
independent and relocates its trusted pointers from the actual arena address.

The GDT/TSS page is at +0x82000; RSP0 uses +0x84000..+0x88000 with an unmapped
lower guard; double-fault IST uses +0x89000..+0x8d000 with its own lower guard.
Two private table pools occupy +0x90000..+0xb0000, with at most 16 pages per
root. Sixteen allocator-owned stack frames occupy +0xc0000..+0xd0000. Each
active domain leases four frames. Its virtual stack begins at
0x10000200000 + domain_index * 0x200000 and spans four pages; surrounding pages
are absent. Metadata is supervisor RO/NX, image frames RX, and tables/stacks
supervisor RW/NX in the kernel mapping.

`ProgramLayout` is an immutable validated value copied into each contract.
Image metadata supplies no code/stack ranges and cannot widen the layout.
The original BIOS constructor still chooses its original profile; UEFI supplies
its separate checked profile and arena-owned entry stack.

## Page tables and privilege transitions

Each private root is rebuilt from the exact supervisor kernel leaves and its
own user RX image/RW-NX stack mappings. Firmware and ECAM window branches are
absent from user roots. Kernel-only mappings agree across roots. Image frames
have no writable supervisor alias. The complete table walk rejects foreign
links, cycles, table aliases, orphan/empty branches and incorrect permissions;
the adapter also checks every expected leaf so a missing mapping cannot pass.
PGE and PCID remain disabled; every root switch performs an actual CR3 load.

The payload installs its own GDT, TSS and IDT in owned memory. TSS.RSP0 and IST
are guarded supervisor stacks, the I/O bitmap is beyond the TSS limit, and only
the exact scalar-return interrupt gate is callable from CPL3. The image's
return PC must match its validated `int 0x81`/UD2 trampoline. Exact emitted
bounds/overflow/division/shift UD2 sites are distinct and bounded. Matching an
address alone does not grant fault-containment authority.

Entry scrubs all four stack frames, clears integer registers and enters with
IF and IOPL clear. CR0.TS blocks unsupported extended-state instructions;
FSGSBASE/OSXSAVE and unsupported paging modes are rejected. FS/GS selectors and
bases are cleared. Inherited SYSCALL and SYSENTER entry authority is disabled
and read back before user execution. This remains an integer-only, sequential
controlled-program boundary.

Every event must match the active registry handle, actual CR3, CPL, selectors,
RFLAGS, complete RSP0 frame, user stack range and exact return/trap site. The
trusted saved kernel continuation must lie on the owned main kernel stack.
A contained event loads the kernel CR3 before returning through the saved
kernel stack. The caller verifies both again before retirement. Users never
provide a kernel continuation address. Unexpected events fail-stop.

Retirement requires an inactive domain and actual kernel root. It scrubs and
checks stack pages, clears tables, revokes the generation-stamped handle, and
releases leases. Normal execution tests active/stale retirement rejection,
reuse of the same physical frame with zeros, partial-create rollback after only
two free frames, and final zero outstanding leases.

The exception entry code is shared with BIOS, but the UEFI build omits the
unused BIOS absolute-address vector table. Its active handler table uses
RIP-relative offsets. The strict PIC verifier checks runtime C++, entry glue
and shared exception object relocations; absolute relocations are rejected.

## Gates and honest limits

- `meson test -C build/meson --suite full`: hosted immutable-layout/table checks,
  image metadata and strict transcript controls. Set `SANITIZE=1` for ASan/UBSan.
- `meson test -C build/meson --suite guest-runtime`: fourteen actual OVMF modes using the
  dependency setup from [the UEFI guide](README.md), restoring normal afterward.
- `runtime`: clean42, contained bounds fault, clean42, scrub/retire/reuse, clean42,
  rollback and final cleanup.
- `runtime-code`, `runtime-stack`: cross-domain fetch/read denial.
- `runtime-kernel`, `runtime-window`: supervisor arena and absent ECAM-window
  read denial. The fixture client contains a narrowly validated test-only
  address literal patched to the actual arena before its image becomes RX.
- `runtime-root`: an otherwise valid return under the wrong actual root fails.
- `runtime-kernel-trap`: a known emitted UD2 reached at CPL0 remains fatal.
- `runtime-entry-stack`: a deliberately guarded RSP0 transition reaches double
  fault on the separate IST, with exact instruction and CR2 evidence.
- `runtime-write`, `runtime-nx`: user image write and stack execution denial.
- `runtime-return`, `runtime-unknown`: forged return and unrecognized UD2 denial.
- `runtime-syscall`, `runtime-sysenter`: alternate inherited entry mechanisms
  cannot transfer user execution to firmware/kernel targets.

All runtime, span, multipage, pin and table modes boot the one `runtime-fixture`
image and pick their case from the serial selector; `runtime`, `runtime-span` and
`runtime-multipage` are baseline selectors, and only pin rows run the pin-ledger
supervisor and only table rows the dormant-table one. The ten user-fault cases used to be separate images,
each with a client built for one probe. The fixture's clean client now carries
every probe and the trusted launcher passes the selected one in its first entry
argument (`runtime_probe()`); the bounds client, page tables and every kernel
check that rejects a probe are unchanged. The image generator still admits each
probe address (inside the image, not aliasing a registered site) and records it
as `probes` metadata, and each mode keeps its own guest run and exact transcript.

The 66 earlier modes remain acceptance gates. These tests establish this
bounded emulator mechanism, not arbitrary firmware correctness, DMA quiescence,
physical AMD support, SMP, hotplug, preemption, extended-state switching or
service APIs. Resource reservation, IOMMU isolation and interrupt ownership must
precede actual device activation.

The SYSENTER negative fixture selects
`qemu64,vendor=GenuineIntel,+sep` so that the instruction reaches the architectural
zero-CS check and produces #GP(0). QEMU's default AMD-vendor long-mode profile
rejects SYSENTER with #UD before that check. The separate fixture therefore
checks the disabled entry mechanism, rather than treating an unsupported
instruction as proof of the CS reset. This is an emulator-only CPU profile,
not an Intel or AMD physical qualification claim. See QEMU's
[decode check](https://github.com/qemu/qemu/blob/v10.0.0/target/i386/tcg/decode-new.c.inc)
and [SYSENTER helper](https://github.com/qemu/qemu/blob/v10.0.0/target/i386/tcg/seg_helper.c).

The independent corrected-source run on compiler
`351a46e42c1ad2e0b224d01a57f249039c37ffe44e051a5d67b420eae54c9174`
passed all fourteen runtime modes. Hosted checks include 1,274 arena/table cases
and immutable-layout policy tests under ASan/UBSan; image validation has three
positive and 64 negative cases, and transcript validation has fourteen positive
and 716 negative cases. The transcript policy independently constrains metadata
shape, integer types, fixed virtual layout, bounded/distinct sites and test
probe ranges before comparing events.

Development caught and fixed a stale stack word on repeated entry, an unused
absolute BIOS vector table rejected by the strict PIC gate, a short-image probe
patch subtraction underflow, and a receipt validator that previously allowed a
zero return PC when both metadata and event text were changed. These findings
remain recorded in the review evidence; earlier failed runs are not counted as
acceptance.

## Bounded multi-page consumer

`runtime-multipage` runs allocation-free incremental CRC32C over `123456789`
and decodes, counts and re-encodes a fixed UTF-8 array. Both images use the same
source; the second deliberately indexes past its array after completing the
work. The existing driver contains its emitted bounds trap, runs the healthy
image again, retires both domains, recreates one and checks zero outstanding
leases. Admission requires real called code and the bounds trap on page three.
Linked stack checks reuse the existing compiler-fact and disassembly validators.
Image backing is retained by the boot arena; teardown clears every mapping before
releasing stack leases. Hosted controls cover incomplete page construction and
reset/recreation. No executable allocator, writable executable alias, larger
stack, page-table pool, arena or kernel payload limit is introduced.

Protected runtime profiles end ACPI parsing temporaries before PCI discovery,
using the existing noinline preparation route and arena-owned MCFG snapshot.
For multipage, Call and snapshot admission, the shared linked discovery gate
rejects a parser-to-PCI call path and bounds the wrapper, parser and PCI frames.
Stack and fault-reserve caps are unchanged.

## Bounded retained volatile RAM file

The merged opt-in `user-ram-file` implementation keeps one unnamed binary file
of at most 49 bytes in one compiled CPL3 service's ordinary private stack locals.
The file is either missing or present (including present-empty). A retired writer
and fresh reader communicate actual bytes through the existing scalar Call ABI;
there is no supervisor file copy. A second replacement, bytes 0/128/255, empty and
49-byte transfers, caller precommit abort and postcommit failure are separate
compiled scenarios. This is not the console namespace, durability, a general
filesystem or a daemon/scheduler API. Its bounded implementation was locally
qualified in [#234](https://github.com/ambasta/aurora/pull/234);
that receipt does not qualify subsequent source changes or the separate interactive consumer.

The singleton `builtin::ServeSession.exchange(reply)` returns copied status/value
qwords. Domain 0 admits only the exact Call `INT 0x82; ret` site; domain 1 admits
only the distinct Serve site. A stable lifetime handle/grant/root/contract binds
all four original move-only stack leases. Every service activation revalidates
allocator ownership and exact mappings, consumes its dormant integer context,
and mints a new immutable run authority for startup, exchange or abort cleanup.
`ProgramRunAuthority::authorize_retained_session` reuses the immutable bounded-run
record with the retained-only 128/120/8 admission rules; ordinary Call admission
still requires a nonzero service transaction. Only exact contract equality and
INT82/RET frame/site capture are shared, not Call/Serve lifecycle or settlement.
The RAM and scratchpad transcript oracles share their run/IRQ/debit/drain grammar
while retaining independent host-owned scenario/command plans and output checks.
This deletion-first cleanup awaits exact-source build, native, guest and review gates.
No pointer or caller-supplied endpoint/ticket/budget crosses the Serve ABI.

Read, Replace and Append rights are fixed at native command admission, not selected by a
request word. Transport enforces closed framing, lengths, sequential offsets,
reply shapes and a maximum 51 exchanges; only source owns existence, committed
bytes/length, staging, commit and read results. APPEND_BEGIN (tag 8) carries a
suffix count; source rejects missing files and totals above 49, stages the existing
prefix, and accepts sequential suffix-relative DATA offsets. COMMIT publishes the
whole result atomically; an empty suffix succeeds only for a present file. Append
has its own admission right and cannot be requested through Read or Replace.
Service startup has one 8-unit
allowance per incarnation. Each command has cumulative caller 128 and service
120 normal units, plus an exclusive 8-unit abort reserve. Every exchange boundary
is charged conservatively: parking charges the discarded partial timer interval,
while synchronous refusal adds a debit without rearming the timer. Neither a new
exchange nor resumption renews a command budget. A cleanup epoch is reserved
before admitting its caller.

On precommit disposal, execution is disabled, the original mailbox receipt is
settled once while its original handles are live, transport is revoked/scrubbed,
and the caller is retired. ABORTING admits no new caller. The same service is
resumed only with cancelled/zero and must acknowledge ABORTED after source staging
cleanup. A pending COMMITTED receipt is consumed without reviving a disposed
caller. After COMMIT delivery, an undecidable result is indeterminate, never a
false cancelled result. Authenticated service faults reset the incarnation and
lose all data; restart begins missing. Unknown trap/grant/frame/root/mapping
failures remain fail-stop, with no unsafe reclamation or new command admission.

`user-ram-file-fixture` consolidates known source service faults, a pending committed
receipt with a logically disposed caller, a post-COMMIT pre-reply fault, caller and
service/cleanup allowance exhaustion, pending interrupt drain, and final-epoch
cleanup. The source-fault case repeats reset, proves missing in each new
incarnation, and checks naturally reused service frames reject the original owner.
`user-ram-file-grant`, `user-ram-file-site`, `user-ram-file-frame` and
`user-ram-file-root` are fail-stop controls, not recoverable data errors. Existing native authority/IPC and image/transcript
harnesses carry the corresponding negative controls. The source file class has
an actual generated-code protocol runner, not a native content-store model. A
bounded fixture-only source loop exercises real compiled-PC timer interrupts;
conservative boundary-withholding controls separately exercise quota exhaustion.

The profile retains the Call envelope: caller at most two RX pages, service one,
four private stack pages per domain, and the existing 15,360-byte effective stack
cap. Both role graphs, copied ABI facts, exact handwritten wrappers/stubs and the
complete kernel/IRQ/drain paths must pass linked admission. Native image tests do
not run QEMU. The bounded [#234 qualification](https://github.com/ambasta/aurora/pull/234)
completed actual guest controls, final GCC 16 full/normal restoration and independent
exact-source review; subsequent source changes must pass those gates again.
Legacy `program-file-call` profiles retain their scrubbed-reentry and supervisor-store semantics unchanged.


## Opt-in interactive RAM scratchpad

The separate `ram-scratchpad-console` composition accepts actual `put [text]`,
`append [text]`, `get`, `crc`, `help`, `status` and `exit` input. It is implemented with focused source,
native, linked-image and real-PTY evidence; bounded local qualification is recorded
in [#235](https://github.com/ambasta/aurora/pull/235). That receipt applies only to its
recorded source, tools and profiles. Run
`scripts/kernel-run.sh --ram-scratchpad-console` for an explicitly bounded
five-minute session, or add `--smoke` for the strict PTY oracle. External
timeout/kill is an interrupted, unverified teardown, not a clean exit.

The unnamed file starts missing; bare `put` creates a present-empty file. It
contains at most 49 printable ASCII bytes and is lost on service reset or session
exit. `append [text]` adds a printable suffix only to a present file and rejects
a result above 49 bytes without changing it. Bare `append` is a successful no-op
on a present file, but rejects a missing file. One separator after `put` or `append`
is grammar; remaining spaces are file bytes. At most 64 protected commands are admitted; local help/status and
rejected input do not reset that count. This is not the legacy four-file console,
a mounted filesystem, persistence or a general shell.

`crc` computes CRC32C inside the compiled caller using the existing read-only
request stream and `std.checksum`. It publishes exactly eight lowercase hex digits
only after authenticated EOF and caller retirement; missing remains distinct from
present-empty (`00000000`). No partial digest survives read failure or service
reset. Digest results have their own closed kind, canonical width and zero suffix;
ordinary `get` still requires its result length to equal the accepted DATA count.
The supervisor never computes the checksum, and no service opcode or limit changes.

Aurora owns the line grammar, exact client scalar requests, result bytes and
presentation. Native code stages an 80-byte command and captures an 80-byte
result at fixed disjoint locations in the existing caller stack; no user pointer,
new capability, general copied transport or native file store is introduced.
The supervisor releases its Console loan before creating each fresh Call-only
caller. The retained Serve-only service owns all file mutation. Its original
four stack leases and live source locals survive prompt waits and Console turns.
The new strict-idle predicate authenticates that dormant service while requiring
no caller, endpoint, transaction, active run, timer owner or pending result
authority. Legacy zero-stack boundaries remain unchanged.

Only a clean exact caller return after final timer drain can yield a candidate.
Its operation and result must match authenticated EOF/DATA count, MISSING,
COMMITTED or REJECTED framing. Original identity remains bound until receipt
settlement, revocation and physical caller retirement; a one-way promotion then
produces ordinary response data. No Console publication occurs before verified
idle, and no partial read is printed. Precommit caller loss requires the same
service's reserved ABORTED cleanup. Accepted COMMITTED with failed caller/result
reports commitment without retry. An unresolved delivered COMMIT resets as
indeterminate/data-lost. Reset invalidates even an already captured candidate.
Stale authority or reclamation uncertainty fails closed before publication.

The single `ram-scratchpad-console-fixture` image adds explicit test-only disposal,
malformed-copy, captured-reset, saved-backing and Console timeout selectors. Its
alternate source Serve program faults after actual COMMIT publication but before
reply. Fixture Console timeout is a source transport return, not physical UART
fault qualification. The production image contains none of these selectors.
Both new compositions use the existing protected Console size-optimization recipe
and retain the two-page caller, one-page service, 15,360-byte stack, 51-exchange,
128/120+8 budget and 64-command limits. The handwritten native adapter grows the
bootstrap trusted surface; this is not native-code retirement or a general safety
proof. The bounded [#235 qualification](https://github.com/ambasta/aurora/pull/235)
completed exact linked poll/IRQ/drain graphs, adversarial transcripts, legacy
regressions, final GCC 16 full/normal boots and independent review. Subsequent
source changes must pass those gates again.
