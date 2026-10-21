# Bounded AMD-Vi diagnostic model

This directory holds three reviewed QEMU patches, not Aurora production DMA code.
No QEMU source tree, executable, package, raw transcript or build directory is
vendored. The default Aurora runtime is unchanged. See the
[diagnostic contract and results](../../docs/iommu-dma-conformance.md) for the exact
claim, preserved failures and remaining gates.

## Exact inputs and patch order

Base: QEMU 10.0.13, upstream commit
`98f88efe8f07067667b8d9b1a5ce9551d34036c1`, using Debian source version
`1:10.0.13+ds-0+deb13u1`. The historical provenance review independently verified
Debian InRelease with the archive keyring, matched its Sources-index digest, and
matched these downloaded archive hashes. The standalone `.dsc` signature was not
verified. These are retained historical input identities, not a claim that a new
machine has authenticated its downloads.

| Source input | SHA-256 |
|---|---|
| qemu_10.0.13+ds.orig.tar.xz | 6a0888e806c2ffc0c5f0733e974f9aea55491950d3c47c98669c8b236dde59ae |
| qemu_10.0.13+ds-0+deb13u1.debian.tar.xz | da73c092f5684c551b0334d675eb16a3dec91e1edea94759cfb1102fa4a0364e |
| qemu_10.0.13+ds-0+deb13u1.dsc | a426c892e5369058c3423816c8625bc8010bb5a58ece57261f62b64ee4d765ad |
| Authenticated uncompressed Sources index | ae99131b13c7e61c53a52c33a2f9088a1bc5db15a664f5d90cc3753ad9b65606 |

Obtain/authenticate the exact source package from Debian, unpack it into a new
external working directory, and retain provenance. Do not patch a stock evidence
tree. `artifacts.json` identifies the exact patch/fixture bytes in this repository.
The scoped Git whitespace attribute allows mandatory space-only unified-diff
context lines; the static gate separately checks added source lines.
`verify_source.py` reads only two external source files and reconstructs all
patches in memory with exact hunk matching and final hashes; it writes no source.
That check does not authenticate or verify the rest of an upstream tree. The
default static gate needs no external QEMU source or network and uses only a
two-line synthetic input for its patch-parser controls.

```sh
python3 -B tools/qemu-amdvi/verify_source.py --qemu-source "$QEMU_SOURCE"
```

Set `QEMU_SOURCE` and `QEMU_BUILD` to absolute external paths. Apply the patches
to the new external source tree in this order:

```sh
AURORA_SOURCE="$PWD"
cd "$QEMU_SOURCE"
patch --fuzz=0 -p1 < "$AURORA_SOURCE/tools/qemu-amdvi/patches/0001-event-record-transport.patch"
patch --fuzz=0 -p1 < "$AURORA_SOURCE/tools/qemu-amdvi/patches/0002-mode1-requester-permissions-v2.patch"
patch --fuzz=0 -p1 < "$AURORA_SOURCE/tools/qemu-amdvi/patches/0003-command-stop-v1.patch"
```

Patch 0002-v2 replaces the retired original 0002; do not stack both. Patch 0003
is byte-identical to the reviewed `command-stop-v1.patch`, with a sequence-number
filename only. Patch 0001 repairs event-record transport. Patch 0002-v2 adds the
bounded requester/Mode1/permissions slice. Patch 0003 stops only dispatch-default
opcodes 0 and 9–15. All corrections remain emulator-only.

Final `hw/i386/amd_iommu.c` SHA-256:
`a506dccf0c112cc791208724651b3aaca300f8b713362dfd07af2308e6f5a2d9`.
Final `hw/i386/amd_iommu.h` SHA-256:
`94d50d0dd0548c533252b4fdff7ec3cf800aed8655ce38db24de837adf1785e4`.
The verifier also pins the unmodified base and the combined-v2 intermediate.

## Explicit external build recipe

A build requires its own capacity allocation and review. These instructions do
not run as part of Make or Meson. Use a fresh external build directory, a supported
C toolchain, Python, Meson/Ninja, pkg-config, and QEMU's GLib/pixman/zlib/libffi/PCRE
build dependencies. The recorded build used GCC 14.2.0, GNU binutils 2.44,
Python 3.12.14, Meson 1.12.1 and Ninja 1.13.2.git.kitware.jobserver-pipe-1.
Dependency and shared-library identities belong in the new build receipt.
No byte-reproducible binary guarantee is made by this recipe.

```sh
printf '%s\n' 'CONFIG_Q35=y' 'CONFIG_AMD_IOMMU=y' 'CONFIG_EDU=y' 'CONFIG_ISA_DEBUG=y' \
  > "$QEMU_SOURCE/configs/devices/x86_64-softmmu/aurora-dma.mak"
mkdir "$QEMU_BUILD"
cd "$QEMU_BUILD"
"$QEMU_SOURCE/configure" \
  --target-list=x86_64-softmmu --without-default-features \
  --without-default-devices --with-devices-x86_64=aurora-dma \
  --enable-tcg --disable-debug-info --disable-download --disable-docs \
  --disable-tools --disable-guest-agent --disable-install-blobs
ninja -j1 qemu-system-x86_64
sha256sum qemu-system-x86_64
```

`--disable-install-blobs` handles the Debian `+ds` omission of bundled firmware;
it does not substitute runtime firmware. Each historical fixture constructs an
owned 64 KiB halt/reset ROM, SHA-256
`4752c6521258b1d2025a81605797c8a76b4ffc27589c812ff267c1d0e649ce15`.
The historical runs retained a missing `kvmvapic.bin` warning. A clean firmware
environment or new successful build is not implied.

## Historical fixtures and future runtime preparation

The three files under `tests/iommu/fixtures/` are immutable evidence inputs:

- `frozen-import.py`: original corrected 17-case suite and unchanged expectations
- `transport-import-v1.py`: separately accepted 13-case aligned-access fixture,
  also imported as transport by the command fixture
- `command-stop-diagnostic.py`: separately versioned 30-case command fixture

The filenames are retained where exact import pins depend on them. Do not format,
refactor or change these frozen files to make a newer run pass. This is an explicit
exception to ordinary source formatting for preserved historical inputs. The
portable offline mocks alongside them are newly adapted and are not the original
preparation checks or historical runtime evidence.

The access fixture hard-pins the historical combined-v2 binary
`81eb4ea516d85888112356f6a371c72e8fb1aa6c68a5819ecb5ec4fef8286ea7`.
The command fixture requires a separate `TARGET-BINARY.json` with a reviewed
absolute local path, source/profile and binary hash. No runtime target is installed
in this repository. `TARGET-BINARY.example.json` contains historical public
identities and a deliberately unusable path placeholder. It is not execution
approval, a relocatable runtime receipt or a substitute for a new build receipt.

For a future replay, copy the exact three fixtures into a newly admitted external
run directory, prepare the matching target and complete process/resource/lifecycle
supervision there, and pin every executable, dependency, fixture and launch input
before execution. The `--qemu` and `--output` arguments belong to those reviewed
fixtures; no default test launches them. If a rebuilt binary has different bytes,
a separately versioned fixture/admission is needed; never replace the historical
pin and claim its acceptance carries over. A changed path, wrapper or supervision
plan also creates new preparation requiring review. No historical single-use
release, absolute workspace path or raw environment is included here.

## Developer Event runtime

The opt-in `make smoke-iommu-event` route uses the command-stop-v1 model above.
It is separate from the immutable historical fixture commands. Supply
`EVENT_BUILD_RECEIPT`, `EVENT_CODE`, `EVENT_VARS` and `EVENT_DATA`; the launcher
constructs and records its closed runtime contract instead of asking for a new
handwritten method or review pin on each run.

The supplied build record binds `binary_path`, `binary_sha256`, `binary_bytes`,
`source_path`, and `runtime_library_manifest` (`path` and `sha256`). Its descriptive
profile/commit/patch/review labels confer no authority. Actual final model-file
hashes and the four-line `configs/devices/x86_64-softmmu/aurora-dma.mak` content
must match the recipe above. Keep those source inputs available at `source_path`.
The dependency JSON records `LD_LIBRARY_PATH` and a `libraries` map from selected
loader/library paths to `resolved_path`, `bytes` and `sha256`; the actual ELF
interpreter dependency list is checked before launch. Duplicate-key/nonfinite
JSON, mismatched bytes/links and unsupported actual model/configuration fail closed.

The executable and build record are trusted user-supplied toolchain inputs.
These checks bind current identities; they cannot cryptographically prove
source-to-binary correspondence or authenticate an intentionally forged record.
A newly built supported binary may have different bytes and gains only its newly
measured local scope. A version string or historical status never grants approval.

Initial firmware support is the default, non-Secure-Boot Debian OVMF
2025.02-8+deb13u1 split pair:

- CODE: 3,653,632 bytes; SHA-256 `624e06de18b4fa535e90db7160d00d3d07d206422b89999bf1e27d920264e4e0`
- VARS: 540,672 bytes; SHA-256 `5d2ac383371b408398accee7ec27c8c09ea5b74a0de0ceea6513388b15be5d1e`

`EVENT_DATA` is the complete supplied QEMU data directory. Its bounded inventory,
resolved file mappings and current hashes are recorded and rechecked, including
symlink targets. The runner does not download firmware, install tools, alter host
configuration or fall back to stock QEMU after failure. The historical binary pin
and fixture admission instructions above apply to historical replay only.
See [developer execution](../../docs/iommu-dma-conformance.md#supported-local-developer-execution)
for mtools/config support, exact captures, cleanup and normal restoration.

### Debian source packaging correction

`ci/build-event.py` applies the byte-pinned official Debian
`skip-unpack-edk2-blobs.patch` after the three model patches. It only disables
unpacking EDK2 blobs stripped from the pinned `10.0.13+ds` source; it does not
change the model, device configuration, runtime identity or six-artifact inventory.
The builder verifies the patch and complete `pc-bios/meson.build` pre/post images,
and installs the attributed patch and separate provenance under
`share/source/packaging/`. That record includes source/package URLs, sizes and
hashes, application order and the builder digest. Source-chain provenance is
imported from the pinned Debian source package, not a fresh signature check by
the builder. Debian's `debian/copyright` is in the identified packaging archive;
QEMU's source license files remain in the installed source archive and `COPYING`
is also installed separately. Offline diff/recipe checks are not source-to-binary
attestation or fresh Event guest qualification.
