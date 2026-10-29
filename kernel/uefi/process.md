# Process image: boot volume, frames and processes

`uefi/process-fixture` is the UEFI test image for running programs as
processes. It carries the boot volume, a physical frame allocator over all
usable conventional memory, kernel mappings beyond the arena's fixed table pages,
a serial export of volume files, and runs static ELF programs from the volume as
CPL 3 processes with their own page tables, a watchdog, and exit and print
through the INT 0x83 gate. Other images and `uefi/production` do not change;
their image bytes are identical with and without this image.

The decisions are Aurora (`examples/kernel-process.au` over
`kernel/policies/kernel/{memory_map,frames,boot_volume,export_text,elf,process_space,process_memory,process_events,process_runs}.au`
and the existing `interrupt_budget`), reached through the private bridge
`process-entry.S`. The build checks every argument record, result class and
enum against the compiler's ABI facts (`PROCESS_POLICY_ABI` in
`scripts/meson_aurora_assembly.py`). Trusted C++ keeps only what the kernel
bridge cannot express yet: firmware file reads in the loader, page-table
writes and their walk, CR3, the frame-record storage and free-list head, the
range table and the memory records, byte copies, the LAPIC timer and serial
output; assembly keeps the
trap entry (`kernel/exceptions.S`) and the CPL 3 transition (`process-user.S`).
Each C++ decoder rejects a result outside its closed encoding before using it.

## Handoff

Version 9 is version 2 (the RSDP, no record word) plus the loader fixture word at
128, the boot volume's page address at 136, its byte length at 144 and the case
word at 152 (header 160). `Handoff::valid` checks the words structurally:
nonzero page address, 1..64 MiB, below the 52-bit limit, case at most 255. Only
the final memory map grants the pages. Every row runs the ACPI discovery of
version 2, whose MADT copy admits the watchdog's LAPIC timer.
The kernel admits the copied map in Aurora (`map_admit`: version 1, stride
40..256 in multiples of 8, at most 512 descriptors, aligned nonempty ranges
below 2^52, no overlap). Every type is admitted, including the OEM and OS
ranges above 15, but only conventional memory is ever used. `volume_grant` then requires the volume
pages to lie wholly inside one non-runtime EfiLoaderData descriptor and outside
the arena. The loader also reserves the arena-owned window path
(`PageTables::prepare_window`). The boot verifier admits it because it has no
leaves.

## Boot volume

The loader opens `\aurora\volume` on its own ESP through the loaded image's
`EFI_SIMPLE_FILE_SYSTEM_PROTOCOL` (`\aurora\compiler` for case words from 3,
whose run lists need the multi-MiB compiler image; every boot checksums its
whole volume). It requires a regular file of 1 byte to
64 MiB and reads it into fresh EfiLoaderData pages. It zeroes the last page's
tail and closes both handles before the final map. The format has one canonical
layout, little-endian (`scripts/kernel_volume.py` writes it):

- header, 64 bytes: magic `AURORAVL`, version 1, header bytes 64, entry count
  (at most 4096), entry bytes 32, names offset (`64 + 32 * count`), names bytes,
  data offset (names end rounded up to 8), data bytes (the rest of the volume),
  CRC32C of bytes 0..56 then 64..end, and a zero reserved word;
- entries in strictly increasing bytewise path order: name offset, name length
  (1..255), zero flags, data offset, size. Names and data follow index order
  without gaps, with each file padded to 8 bytes with zeros;
- paths are relative components of `[A-Za-z0-9._-]` joined by `/`, never empty,
  `.` or `..`. No path may also be the directory of another (`a` with `a/b`):
  such a volume is rejected as `nesting`.

`volume_admit` returns the first violated rule as a closed verdict.
`volume_find` binary-searches an admitted volume and `volume_entry` returns an
entry's absolute extent. The C++ wrapper also checks that extent lies inside the
volume. The kernel maps the volume read-only/NX and admits it before using it.

## Frames

Usable frames come from conventional descriptors without the runtime or
specific-purpose (`EFI_MEMORY_SP`, soft-reserved as Linux treats it) attribute,
above the first MiB (reserved, as Linux reserves it on x86). Each
must be disjoint from the arena and the volume (`frame_range`) and below the
CPU's physical width. Boot-services memory is not reclaimed. Ranges are sorted
and indexed densely. Each frame has one 8-byte record: bits 0..3 state (free,
allocated, kernel, retired), 4..31 generation, 32..63 owner, or for a free frame
its free-list link (next index + 1). `frame_transition` decides every record
change: initialize free or kernel, allocate, or release with the holder's owner
and generation. A release with a stale generation, the wrong owner, a kernel
owner, a kernel, free or retired frame, or a noncanonical record is rejected with
its reason and leaves the record unchanged. A generation that would wrap retires
the frame. Owners 1..15 are kernel uses (1 tables, 2 metadata); allocation
starts at 16. `Table::audit` walks every record and the free list.

## Kernel space

The window table at `0xffff800000000000` lives in the arena. Slot 0 is the
transient frame window, unmapped before reuse. Slot 1 is an absent guard, and
slots 2.. are RW/NX views of dynamic table pages. Root slot 384 (`0xffffc00000000000`) maps the frame
metadata RW/NX at its base and the volume read-only/NX at +1 GiB. Its tables
come from the lowest frame indices, followed by the metadata pages; all are kernel
frames. `KernelSpace::verify` walks the complete extension. Every entry must be
exact, every table and metadata page must be a kernel frame of its owner, volume
pages must lie outside the inventory, the window must be closed and the other
root entries must be the boot-verified ones. It runs after construction and after
the frame cases. The baseline row then checks that it rejects four single-entry
edits: a user bit on a table link, an executable metadata leaf, a writable volume
leaf and an open window.

The metadata is one 8-byte record per frame and, from the next page, one
8-byte mapping word per frame (`KernelSpace::mappings`), zero unless a process maps the
frame, then 96 pages for the running process's 16384 memory records.

## Export

```
AURORA_EXPORT_BEGIN: path=<volume path> bytes=<n>
AURORA_EXPORT_DATA: <padded base64 of the next 57 bytes, or fewer on the last line>
AURORA_EXPORT_END: path=<volume path> lines=<k>
```

`base64_group` encodes each group of 3 bytes. `kernel_uefi_oracle.exports`
decodes the records and rejects stray, truncated, misframed or duplicate ones.

## Processes

A row with a nonzero case word runs the run list `runs/<case>` of the volume,
one program after another, after the volume is admitted; case 0 runs the frame
and export cases above. Each run: the program path's entry is admitted as an ELF
program, its layout and regions are mapped into a fresh address space, the
complete walk checks it, the process runs until it exits, faults, makes an
invalid call or exhausts its watchdog budget, the walk runs again, every frame
of the process is released and the frame table is audited (no frame allocated).
The kernel reports each step:

```
AURORA_PROCESS_RUN: run=<n> path=<volume path> ticks=<budget>
AURORA_PROCESS_REJECTED: run=<n> reason=<missing | ELF verdict | layout verdict>
AURORA_PROCESS_LOADED: run=<n> regions=<r> pages=<p> tables=<t> quota=<memory frames>
AURORA_STDOUT: run=<n> <padded base64 of one print>   (AURORA_STDERR likewise)
AURORA_PROCESS_END: run=<n> reason=exit status=<s> | reason=watchdog ticks=<t>
  | reason=call operation=<rax> rip=<a> | reason=<trap class> vector= error= rip= cr2=
AURORA_PROCESS_RELEASED: run=<n> frames=<all> memory=<memory pages + tables>
  calls=<memory calls> commits=<committing faults>
AURORA_PROCESS_RUNS_OK: runs=<n> free=<frames>
```

A fault with a frame the kernel does not verify as the running process's own
(any kernel-mode fault) prints `AURORA_PROCESS_KERNEL_FAULT: vector= error= rip=
cs= cr2=` and stops the machine; only a verified process frame ends just that
process.

### Programs

`kernel.elf` admits ELF64 little-endian x86-64 `ET_EXEC` images (System V ABI 0,
64-byte header, 56-byte program headers, 1..16 of them) and returns the first
violated rule: `truncated`, `magic`, `format`, `type`, `machine`, `header`, then
per program header `interpreter` (PT_INTERP), `dynamic`, `tls`, `stack` (an
executable or second PT_GNU_STACK) or `segment` (any other type), then per
PT_LOAD (at most 8) `permissions` (not readable, unknown flag bits),
`writable_executable`, `alignment` (alignment not a power of two of at least a
page, offset not congruent to the address), `file` (bytes beyond the image),
`memory` (zero size or file size above memory size), `address` (outside [4 MiB,
64 TiB)), then `overlap` (two segments sharing a page) and `entry` (outside
every executable segment), or `empty` without load segments.

### Address space

`kernel.process_space` lays out the regions: each load segment's pages with leaf
flags read-only/NX, read-execute or read-write/NX, copied from the image with
the rest zero (BSS); an 8 MiB read-write/NX stack ending at `0x7fffff000000`
above an unmapped guard page; and the argument block (1..64 KiB of
NUL-terminated words, read-only/NX) at `0x7fffff001000`. `process_layout`
rejects a segment entering the kernel's shared 2 MiB slots (`kernel`) or an
empty or oversized argument block (`arguments`).

`process-space.hpp` builds the address space from frames allocated to the
process's own owner (16 + run). The root shares the kernel's root entries
256..511 (frame window, LAPIC, frame metadata and volume) and the
supervisor-only page tables of the arena's one or two 2 MiB slots, so traps and
calls run under the process root. Tables are written and pages filled through the
transient frame window, which is closed before a page's own leaf is written: no
frame is ever reachable writable and executable at once. Each table and page frame
gets a mapping word naming its one place (a page's address, or a table's level
and first address, with a table's count of present entries in bits 4..13). The
walk at load and at exit checks every entry of every table reachable from the
root: shared entries equal to the kernel's, links exactly user-writable to a
table of this owner with the expected mapping word, leaves inside a region or a
memory mapping with its exact flags and a page of this owner with the expected
mapping word, and each table's count; that the memory records are in address
order inside their reservations below the bump address; that the walk saw every
recorded table and region page and every committed page; and that no frame is
allocated anywhere but the ones walked (one process runs at a time, so the
frame table's allocated count must equal them), within the process's charge.
It opens the frame window once per table and once per link, so its cost
follows the space's tables and pages, not its address range. A kernel call's
buffer must lie inside one region (`ProcessSpace::contains`); kernel calls
never read memory mappings. At exit the space is released by walking its
tables.

### Memory

`kernel.process_memory` decides the memory service behind the hosted memory
runtime (`runtime/linux/aurora/memory.au`, the one source both runtime roots
compile, compiler/SERVICES.md#hosted-memory):

- map(bytes) reserves the next power of two of the pages at a bump address in
  the memory area [64 TiB, 96 TiB) and leaves one unmapped page after it; the
  bump address never goes back, so no address is reused within a process;
- remap(base, bytes, new bytes) grows or shrinks in place within the
  reservation (a shrink releases the pages past the new end), and otherwise
  moves the committed pages' entries to a fresh reservation (mremap with
  MREMAP_MAYMOVE; no byte is copied, the old range no longer translates);
- unmap(base, bytes) releases the mapping's pages;
- a base naming no mapping, or a length the mapping does not have, ends the
  process as an invalid call (`length`); the area full (`space`), 16384 live
  mappings (`records`) or the quota (`quota`) refuse with the HostStatus
  `exhausted` (-6) and change nothing, which the runtime turns into a failed
  owner (`ok false`), as an ENOMEM does on Linux. Unlike Linux, the area is
  never reused: every map and move uses up its reservation and a page of the
  32 TiB for the rest of the process (a 4 GiB map and unmap repeated about 8191
  times, or a 1 MiB one about 2^25 times, then refuses with `space`).

Every frame a process may hold is charged against its quota first: the load
(root, regions, two tables per shared kernel slot) and each mapping's pages
plus one page table per 2 MiB, 1 GiB and 512 GiB slot it touches (a move also
needs room for its new tables beside the old ones). The quota is the run's
(`quota` frames, 0 for all) on top of the load, at most the frames free when
the process loads (`memory_budget`; a load that does not fit is `rejected
reason=quota`). A mapping is committed on first touch: a user read or write of
an absent page inside a mapping's pages (`memory_fault`) commits that page and
the other absent pages of its aligned 64 KiB block in the mapping, with frames
the charge already covers, so a touch never fails (but see the limits on
retired frames) and the process sees eager
commit's behaviour without its cost (one memory case maps 4 GiB and touches
one page). Every frame is zeroed through the window before it is mapped, so no
frame reaches a process with an earlier holder's bytes. A page table left
empty by an unmap, shrink or move is released (its parent's count drops, up
to the root); each cleared leaf and released table is invalidated with
INVLPG before the process runs again.

### Entries

The process runs at CPL 3 with IF set: RIP at the entry point, RSP 16 bytes below
the stack top (a zero qword), RDI the argument block and RSI its length, other
registers zero. The GDT and TSS page, the 16 KiB RSP0 stack and the double-fault
IST stack live in the arena between unmapped guard pages. SYSCALL is disabled
(EFER.SCE clear), CR0.TS is set, and FS, GS and kernel GS bases are zero. Every
vector enters `kernel/exceptions.S`; only INT 0x83 is a DPL 3 gate.
`process_trap` (`kernel.process_events`) classifies the copied frame: it must be
the exact RSP0 frame under the process root with CS 0x1b, SS 0x23, RIP below
2^47 and RFLAGS with IF and bit 1 and only CPL 3 bits, or it is `kernel`. Then
vector 64 is `timer`, 0x83 `call`, #UD `system_call` when the two bytes at RIP
(read when executable) are SYSCALL or SYSENTER and `invalid_opcode` otherwise,
#PF `stack_guard` in the guard page and `page_fault` otherwise, and
`protection`, `divide`, `debug`, `breakpoint`, `overflow`, `bound`, `fpu`,
`alignment` and `simd`; NMI, double fault, machine check and the rest are
`kernel`.

`process_call` decodes RAX: 1 exit(RDI status 0..255); 2 print(RDI stream 1 or
2, RSI buffer, RDX length up to 64 KiB), returning 0; 3 read(file, offset,
chunk), returning -1 (`invalid_handle`) because there is no file service yet;
4 map(RDI bytes), 5 remap(RDI base, RSI bytes, RDX new bytes) and 6 unmap(RDI
base, RSI bytes) with whole-page lengths up to 64 TiB, returning the base (0
for unmap) or -6 ([memory](#memory)). Anything else ends the process with
`call`. A page fault the memory service commits resumes the process. The watchdog arms the LAPIC one-shot
timer (2^24 counts, divide by 16) per tick; each timer interrupt is charged by
`kernel.interrupt_budget` and ends the process when its run's 1..128 ticks are
spent. A timer interrupt pending when a process ends is taken in a kernel
`sti; hlt` window before the next process starts.

### Run lists

`kernel.process_runs` admits a run list: header `AURORUNS`, version 2, count
1..64; per run a 24-byte record of ticks 1..128, path bytes 1..255, argument
bytes 1..65536, flags 0..7 and the memory quota in frames (0 for all), then the
path, the NUL-terminated arguments and zero padding to 8
bytes, ending at the entry's end (`truncated`, `magic`, `version`, `count`,
`ticks`, `path`, `arguments`, `flags`, `padding`, `trailing`). The flags are
fixtures: 4 runs the complete walk after every memory call and commit (it
stops the machine if one fails), 1 faults the kernel during the run's first kernel call (the
kernel-fault row), 2 checks after the load walk that it rejects each of four
single-entry edits, each undone before the next: a no-execute code leaf, a code
leaf aliasing the argument page's frame, an extra leaf after the argument block
and a user bit on the shared arena slot's entry (`AURORA_PROCESS_WALK_OK:
rejected=4`).
`scripts/kernel_volume.py --run` writes run lists.

## Tests

`kernel-process` (merge suite) links the generated policies with
`frames.hpp`. Its memory-map, inventory, record and policy cases are
`tests/kernel-process/frames.cases`. The volume cases are built by the writer
from `volumes.cases`; each edits one field of a canonical volume. Program and
run-list cases are `programs.cases`: each edits one field of the writer's
header-only ELF image (or of a run list) and prints the ELF and layout verdicts
and the regions, the load charge and quota, or the run-list verdict and runs.
Trap frames and kernel calls are `events.cases`; memory decisions
(reservation, growth, move, quota, release, record lookup, committed faults,
the memory calls and misuse) are `memory.cases`. Verdicts are compared with the golden files beside them. The `guest-process` family boots the
image's seven rows (`meson test --suite guest-process`, about 2 s each on TCG,
3 s for `process-run`, 11 s for `process-memory`):

- `process-volume` allocates every free frame and writes and reads back a pattern
  and then zero through the window. It checks six misuse rejections, releases
  every frame and audits with zero leaks. It checks that the exit walk rejects the
  four edits above, then exports `examples/host-sort.au`, whose bytes must equal
  the repository file;
- `process-volume-corrupt` boots a volume with an unsorted index and a valid
  checksum (`order`);
- `process-volume-empty` boots an empty file, which the loader rejects;
- `process-volume-map` names the arena as the volume after ExitBootServices
  (`arena`);
- `process-run` (case 1) runs the `--target aurora` host-files probe with `print
  hello eprint oops exit failure` (with the walk probes of flag 2), the Linux build of the probe (ends at its
  first SYSCALL, `system_call`), `recurse` (a GNU as program, since the compiler
  rejects recursion reachable from a HostFiles main; ends at the guard,
  `stack_guard`), `hostile spin` (ended by the watchdog after 4 ticks), the
  eleven isolation programs of `tests/kernel-process/isolation.S` (writing its
  code page, running its stack, `cli`, `in`, reading the kernel half, an unknown
  kernel call, printing a kernel address, `int 14`, touching a mapping's
  reservation past its pages, unmapping with a wrong length and reading a moved
  mapping's old address after checking its byte moved) and the probe with
  `print 'two words' exit success`, which shows the kernel continues after each;
- `process-hostile` (case 2) rejects ELF images with a writable and executable
  segment, an interpreter, an entry outside code and overlapping segments and a
  missing path, runs `hostile` to exit 0, then faults in the kernel during the
  probe's first call, which stops the machine;
- `process-memory` (case 3, 5 GiB guest, the compiler volume) runs the
  `--target aurora` memory probe once per case of
  `tests/host-files/memory.golden` (the first, second and fourth with the walk
  after every memory call), the `--target aurora` compiler with no arguments
  (usage, exit 2), the probe under a 140-frame quota (its 100000-byte owner
  fails, its 10-byte one does not) and the compiler under a 1-frame quota (its
  memory runtime cannot start: exit 1). Guest time per run is about 40 ms,
  4 s for the 768 MiB of triples one case fills and 3.5 s for the case that
  churns 100000 owners; 60 ms for the compiler.

`tests/kernel-process-smoke.py` reduces each run to one line compared with
`tests/kernel-process/<row>.golden` (a fault keeps its vector and architectural
error code, which tell the refusing check: page-fault present/write/user/fetch
bits, or the gate's vector, and the output before it; a refused call keeps its operation); each probe run must also equal its hosted
line in `tests/host-files/cases.golden` without the file tree, each memory
probe run with the whole quota its line in `tests/host-files/memory.golden`
(the runtime's `ud2` trap is SIGILL there) and the compiler with no arguments
the Linux compiler's (`tests/host-files/usage.golden`). Every released run
must return its load's frames plus the memory frames it held. The case word is
the fw_cfg file `opt/aurora/case` (`kernel_profiles.PROCESS_CASES`), read by the
loader beside the fixture selector, so rows that differ only by run list share
one selector and one volume.

Limits:

- one CPU and one process at a time; no SMAP, SMEP or PCID (every kernel entry
  stays under the process root, but every process switch flushes the TLB);
- eager commit of the image, stack and arguments: every region page,
  including the whole 8 MiB stack (about 2050 frames), is allocated, zeroed
  and walked at load; memory mappings commit on first touch; no file service
  yet (M4); kernel calls read only regions, never mappings;
- the frame table is audited after every run, over every frame (about 25 ms
  per run at 5 GiB under TCG);
- the quota holds the frames free at load, but a frame whose generation would
  wrap (its 2^28th release in one boot) retires during the run; a process
  that then uses its whole quota can meet a failing frame allocation at a
  touch, which stops the machine;
- map admission is quadratic over at most 512 descriptors, and boot-services
  memory is not reclaimed;
- the plan stops the boot above about 250 GiB of usable memory (one metadata PD
  for 16 bytes of records and mapping words per frame, 510 table views);
- every process root maps the kernel's arena, frame metadata, mapping words and
  volume supervisor-only, so a Meltdown-class read on an affected Intel CPU
  could expose them (Zen is not affected); SMEP, SMAP and UMIP are not enabled
  (the qemu64 model has none), so `sgdt`/`sidt` reveal the arena's address;
- `int3` and `into` meet DPL 0 gates and end as `protection`, not `breakpoint`
  or `overflow`; SYSENTER on an Intel-vendor CPU (zeroed MSRs) ends as
  `protection`, on AMD as `system_call`;
- the physical width comes from CPUID 0x80000008 alone. On Zen with memory
  encryption, CPUID 0x8000001F EBX[11:6] reduces it, which Zen qualification must
  add;
- CRC32C in `std.checksum` is bitwise;
- no physical device is qualified.
