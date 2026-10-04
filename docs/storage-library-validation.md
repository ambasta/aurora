# Storage-library integration validation

The independently reviewed library-only delta is integrated after the verified
milestone014 archive. All 36 copied baseline file hashes were checked before the
patch; all five reviewed executable/test files match their isolated hashes after
integration. The binary reader change appends the four reviewed readers and
preserves the prior body. No compiler grammar, backend or kernel source changed.

Both complete compiler targets passed with the integrated library:

```sh
make -C compiler test OUT=/tmp/aurora-m015-release/aurorac
ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 make -C compiler test \
  OUT=/tmp/aurora-m015-sanitizer/aurorac \
  CXXFLAGS='-std=c++23 -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer -fno-sanitize-recover=all -Wall -Wextra -Wpedantic -Werror'
```

The release compiler was rebuilt and exactly matched corrected M014's SHA256
`2d86780c0082d861e7031955737eef81bb36936c7971d5032b6a1abbb4a24bf8`.
The instrumented compiler was reused by its exact SHA256
`ca87388b07dd39207ab3342bed2b9cd4ad5212362b435289e7f97b93574476fa`
after checking all 13 compiler input hashes. The targets rebuilt their IR and
host-I/O test executables using the selected flags.

The targets include all prior source suites, signed/unsigned native oracles,
950 direct IR cases, exhaustive backend handling and native IR observations,
module resolution/depth checks and source/artifact host adapters. They now also
run 254 native storage cases and replay 15 observations against the real offline
mkfs-generated header. The scalar semantic harness and default 630/stress 1526
cases additionally passed with both compiler pins. The integrated storage_fields
example executes 42 with both compilers.

Sanitizer mode omits only the scalar harness compiler address-space limit for
shadow-memory reservation; native-program limits remain unchanged. The 8 MiB file
limit covers regular files, not captured stdout/stderr pipes. Leak detection is
disabled because the environment traces processes. Generated Aurora machine code
uses its native checks and is not itself ASan-instrumented.

[Integrated receipts](evidence/milestone-015/storage-library/integrated/results.json)
record actual exit codes, source identities and executable hashes. The neighboring
isolated author and independent records retain the prior review's commands and
paths unchanged. The public constructors remain ordinary reports, and a good
checksum never establishes mountability, clean-log state or feature compatibility.

[Offline fixture provenance](offline-xfs-fixture.md) preserves two limitations:
the original mkfs exit code was not retained, and the initial author sanitizer
attempt stopped in LeakSanitizer before executing cases. Successful read-only
xfs_db and native replay evidence is separately recorded. No image was mounted or
physical device accessed.

This completes compiler/library integration gates. Parent milestone015 combined
kernel acceptance remains separate and pending.


## Text fixture transport correction

After the integrated targets above, packaging changed only the fixture harness:
it now strictly decodes the unchanged canonical hex transport and checks the
original raw512-byte identity. The binary was preserved outside the versioned
tree, with no new mkfs invocation. The original receipts remain historical.
Focused normal/-O decoder controls and15 native observations on both compiler
pins passed; independent review also passed17,604 corner checks in each mode; see `evidence/milestone-015/storage-library/transport` and the
transport update in `offline-xfs-fixture.md`. Compiler and Aurora library source
remain byte-identical to the independently reviewed implementation.
