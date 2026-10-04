#!/bin/bash
# Record of official-source acquisition, local extraction, and fixture editing.
# Existing parent source: https://github.com/tianocore/edk2.git
# Expected edk2-stable202502 commit: fbe0805b2091393406952e84724188f8c1941837
set -euo pipefail
mkdir -p /tmp/aurora-clean-ovmf/provenance /tmp/aurora-clean-ovmf/deps
cp -a /tmp/aurora-edk2-stable202502 /tmp/aurora-clean-ovmf/edk2
git -C /tmp/aurora-clean-ovmf/edk2 submodule update --init --depth 1 BaseTools/Source/C/BrotliCompress/brotli MdeModulePkg/Library/BrotliCustomDecompressLib/brotli MdePkg/Library/BaseFdtLib/libfdt CryptoPkg/Library/OpensslLib/openssl CryptoPkg/Library/MbedTlsLib/mbedtls MdeModulePkg/Universal/RegularExpressionDxe/oniguruma
git -C /tmp/aurora-clean-ovmf/edk2 submodule update --init --depth 1 MdePkg/Library/MipiSysTLib/mipisyst SecurityPkg/DeviceSecurity/SpdmLib/libspdm RedfishPkg/Library/JsonLib/jansson UnitTestFrameworkPkg/Library/CmockaLib/cmocka UnitTestFrameworkPkg/Library/GoogleTestLib/googletest UnitTestFrameworkPkg/Library/SubhookLib/subhook
curl -fsSL --max-time 60 https://deb.debian.org/debian/pool/main/n/nasm/nasm_2.16.03-1_amd64.deb -o /tmp/aurora-clean-ovmf/deps/nasm_2.16.03-1_amd64.deb
curl -fsSL --max-time 60 https://deb.debian.org/debian/pool/main/a/acpica-unix/acpica-tools_20250404-1_amd64.deb -o /tmp/aurora-clean-ovmf/deps/acpica-tools_20250404-1_amd64.deb
curl -fsSL --max-time 50 https://deb.debian.org/debian/pool/main/u/util-linux/uuid-dev_2.41.5-0+deb13u1_amd64.deb -o /tmp/aurora-clean-ovmf/deps/uuid-dev_2.41.5-0+deb13u1_amd64.deb
dpkg-deb -x /tmp/aurora-clean-ovmf/deps/nasm_2.16.03-1_amd64.deb /tmp/aurora-clean-ovmf/deps/root
dpkg-deb -x /tmp/aurora-clean-ovmf/deps/acpica-tools_20250404-1_amd64.deb /tmp/aurora-clean-ovmf/deps/root
dpkg-deb -x /tmp/aurora-clean-ovmf/deps/uuid-dev_2.41.5-0+deb13u1_amd64.deb /tmp/aurora-clean-ovmf/deps/root
mkdir -p /tmp/aurora-clean-ovmf/deps/lib
ln -s /usr/lib/x86_64-linux-gnu/libuuid.so.1 /tmp/aurora-clean-ovmf/deps/lib/libuuid.so
python3 /tmp/aurora-clean-ovmf/provenance/apply-fixture.py
bash /tmp/aurora-clean-ovmf/provenance/build.sh
