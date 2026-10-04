#!/bin/bash
set -euo pipefail
export LC_ALL=C
export TZ=UTC
export SOURCE_DATE_EPOCH=1740096000
export PYTHON_COMMAND=python3
export LIBRARY_PATH=/tmp/aurora-clean-ovmf/deps/lib
export C_INCLUDE_PATH=/tmp/aurora-clean-ovmf/deps/root/usr/include
export PATH=/tmp/aurora-clean-ovmf/deps/root/usr/bin:/usr/local/bin:/usr/bin:/bin
cd /tmp/aurora-clean-ovmf/edk2
{
  date -u
  git rev-parse HEAD
  git remote -v
  git submodule status --recursive
  printf 'LC_ALL=%s\nTZ=%s\nSOURCE_DATE_EPOCH=%s\nPYTHON_COMMAND=%s\nPATH=%s\n' "$LC_ALL" "$TZ" "$SOURCE_DATE_EPOCH" "$PYTHON_COMMAND" "$PATH"
  printf "LIBRARY_PATH=%s\n" "$LIBRARY_PATH"
  sha256sum /usr/lib/x86_64-linux-gnu/libuuid.so.1
  printf "C_INCLUDE_PATH=%s\n" "$C_INCLUDE_PATH"
  gcc --version
  g++ --version
  ld --version
  make --version
  python3 --version
  nasm -v
  iasl -v
} > /tmp/aurora-clean-ovmf/provenance/build-environment.txt
make -C BaseTools -j4 > /tmp/aurora-clean-ovmf/provenance/basetools-build.log 2>&1
set +u
source edksetup.sh
set -u
build -a X64 -t GCC5 -b DEBUG -p OvmfPkg/OvmfPkgX64.dsc -n 4 > /tmp/aurora-clean-ovmf/provenance/ovmf-build.log 2>&1
sha256sum Build/OvmfX64/DEBUG_GCC5/FV/OVMF* > /tmp/aurora-clean-ovmf/provenance/firmware-sha256.txt
