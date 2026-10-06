# Local developer-command verification — 2026-10-06

## Change and source scope

The local shortcuts are based directly on accepted main
`772b9c8a6291aa3cc656b409ce0263f73d45b034`. They do not depend on draft PR28's
IPC/clock changes. They reuse existing compiler-build, image-build and serial
validation mechanisms; they do not add a kernel or language feature.

The tested v3 source-only snapshot has 578 files. The accepted repository also
contains historical evidence outside that snapshot; those Git entries are
preserved unchanged. The snapshot path/hash/mode/length manifest SHA-256 is
`7a733f6314d1e1fecef2f33a70043d13f035b7fe3e49f4e56e688fc5e850bec2`.
Source inventories before and after the synthetic and real integration runs
match that manifest. Product scripts, tests and Makefile remain unchanged in
this publication; this results document and its links are a documentation-only
overlay, not a claim that another source revision was executed.

## Completed checks

- Each of the four changed/new shell scripts passed its own `bash -n` invocation
  inside one fail-fast loop. Python AST parsing of the new test file passed.
- `make --no-print-directory -j1 test-developer-commands` passed all 17 synthetic
  tests under normal Python and all 17 under optimized Python. These tests use
  fake tools; they establish routing/error behavior, not real emulator success.
- `./scripts/compiler-test.sh` completed the fresh-source, complete compiler-only
  suite with command exit 0. The new `run.json` records `entry=compiler`,
  `goal=test`, `scope=compiler-suite`, `status=passed`, build and Make return codes
  0, and `native_complete=false`. It is not the root native aggregate.
- `make --no-print-directory -j1 run` built and passed one actual normal BIOS
  QEMU gate. The existing serial validator accepted QEMU status 33 and the
  expected compiled-language/boot self-test transcript; the public command
  exited 0.
- `make --no-print-directory -j1 run-uefi` built and passed one actual normal
  UEFI QEMU gate using the combined OVMF ROM. Its existing serial validator
  accepted QEMU status 33 and the expected handoff/language transcript; the
  public command exited 0.

The compiler-only command took about 400 seconds; build-plus-BIOS about 28
seconds; build-plus-UEFI about 4 seconds on this host. These are observed timings,
not performance targets or promises for another machine. Commands ran serially
in a fresh checkout with bounded time, disk and logs. Boot-only Bash tracing on
a separate owned descriptor retained the actual QEMU status assignments and
validator arguments without altering the source or guest serial logs. All
owned sessions closed, and source, selected tools and runtime inputs remained
unchanged. Peak observed checkout/evidence allocation was 391,323,648 bytes;
no physical disk or user data was attached.

The compiler-only run and the ordinary compiler subsequently built for both
boot commands produced the same observed SHA-256:
`66bb719d0ad1622e97b7e448a724d153bb370080f0ce4aa1e5a0b6b322a4a298`.
This is an observed result, never a required developer bootstrap checksum.

## Host and runtime

The checked host used GNU C++ 14.2.0, GNU binutils 2.44, GNU Make 4.4.1,
Bash 5.2.37, Python 3.13.5 and QEMU 10.0.13. `CXX` explicitly selected the GNU
compiler executable. BIOS used the existing `pc`/TCG/qemu64 profile; UEFI used
q35/TCG/qemu64 with the installed combined OVMF image.

Runtime identities:
- QEMU executable SHA-256:
  `d3c1a558ad220e77a4412048c8d96b44f8c2b41c7ad2a4ecfe522a4b122fe067`
- Combined OVMF ROM SHA-256:
  `14954040cc754ade0c625ac3470ea46d4c14318b5b1396de4ef77090203d76db`

Installed runtime/data/library inputs were verified against the previously
closed runtime inventory, including declared symlink identities and directory
membership. No downloads, installation, optional-module injection or default
QEMU configuration change was made.

## Preserved failures and corrections

The v2 synthetic attempt remains failed: 16 of 17 normal tests passed, but the
isolated fake PATH omitted `printf`, which GNU Make directly executed for the
help recipe. Optimized tests did not run, nor did the failed method's later
selector assertions. V3 adds the resolved host `printf` to that fixture.

The earlier syntax command incorrectly supplied several filenames to one
`bash -n`; it parsed only the first. That incomplete coverage remains recorded.
The accepted v3 rerun explicitly parsed all four scripts separately.

Two real-integration admissions stopped before any project command:
1. The initial clean PATH omitted the existing `rg` executable. Appending its
   installed directory fixed discovery; no package was installed.
2. The runtime preflight adapter omitted declared keymap descendants beneath a
   directory symlink. Its correction checks the exact accepted declarations,
   full records and immediate membership, with runtime-root confinement.

The successful third attempt used a fresh execution directory. Both blocked
attempts have zero compiler or emulator credit. Their source and failure
records remain preserved rather than relabeled as passing runs.

## Evidence identities and limits

Retained receipt SHA-256 values:
- Successful synthetic LIGHT result:
  `72b6bb8409f266c92e8f02dd4ee677e871a97b126cf54859c1b7789f6d39568e`
- Complete real-integration result:
  `3680e48930e089ec81997ee4e1fbf4baf516fb781ef3bba3a27e9875bda5342a`
- Compiler-only `run.json`:
  `74bfcc3b8350215ad5bcc47a2ac1042481886e08fa0e19911cef8cd9a119b637`
- BIOS serial log:
  `801f096508d53e381fc4c101196db0ccb8a4915d6c0bce3620269eda70304806`
- UEFI serial log:
  `1e685f1cfd14f102b5ae935cd8cf2a9d8a0a8d5ed6e0b42d7a30266d76f10254`

This change did not rerun the full root native aggregate, externally pinned
acceptance, full fault-mode emulator matrix or sanitizers. It does not qualify
Gentoo/GCC16, physical AMD/Framework hardware, an interactive shell/desktop or
broad-host portability. Historical broader results retain their own source
scope. See [local development](local-development.md) for supported commands and
[the shared test contract](developer-test-contract.md) for receipt interpretation.
