#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build/uefi
flags=(-std=c++23 -O1 -g -Wall -Wextra -Wpedantic -Werror -DNDEBUG)
if [[ "${SANITIZE:-0}" == 1 ]]; then
    flags+=(-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer)
fi
for bound in full 3; do
    definitions=(-DAURORA_NVME_QUEUE_TESTING=1)
    if [[ "$bound" != full ]]; then
        definitions+=(-DAURORA_NVME_QUEUE_GENERATION_LIMIT="$bound")
    fi
    g++ "${flags[@]}" "${definitions[@]}" tests/kernel-nvme-queues.cpp -o "build/uefi/nvme-queues-$bound-test"
    ASAN_OPTIONS="${ASAN_OPTIONS:-detect_leaks=0}" "build/uefi/nvme-queues-$bound-test"
done
# The shipping type exports only copied identity/counts and CPU preparation checks.
g++ "${flags[@]}" -I. -x c++ - -o build/uefi/nvme-queues-api-test <<'CPP'
#include "kernel/uefi/nvme-queues.hpp"
#include <type_traits>
using namespace aurora::uefi;
template <class T> concept Inject = requires(T& q) { q.fail_scrub_for_test(0); };
template <class T> concept Address = requires(T& q, NvmeQueueHandle h) { q.address(h); };
template <class T> concept Publish = requires(T& q, NvmeQueueHandle h) { q.publish(h); };
template <class T> concept Complete = requires(T& q, NvmeQueueHandle h) { q.complete(h); };
template <class T> concept Activate = requires(T& q) { q.activate(); };
static_assert(!Inject<NvmeQueueBundle> && !Address<NvmeQueueBundle> && !Publish<NvmeQueueBundle>);
static_assert(!Complete<NvmeQueueBundle> && !Activate<NvmeQueueBundle>);
static_assert(!std::is_convertible_v<NvmeQueueHandle, aurora::memory::PageLease>);
static_assert(!std::is_default_constructible_v<NvmeQueueBundle>);
auto main() -> int { return 0; }
CPP
ASAN_OPTIONS="${ASAN_OPTIONS:-detect_leaks=0}" build/uefi/nvme-queues-api-test
for invalid in production disabled zero negative; do
    case "$invalid" in
        production) definitions=(-DAURORA_NVME_QUEUE_GENERATION_LIMIT=3)
            message='A small queue generation limit is only available in explicit test builds' ;;
        disabled) definitions=(-DAURORA_NVME_QUEUE_TESTING=0)
            message='Queue test interfaces require explicit AURORA_NVME_QUEUE_TESTING=1' ;;
        zero) definitions=(-DAURORA_NVME_QUEUE_TESTING=1 -DAURORA_NVME_QUEUE_GENERATION_LIMIT=0)
            message='A generation limit must be a positive representable integer' ;;
        negative) definitions=(-DAURORA_NVME_QUEUE_TESTING=1 -DAURORA_NVME_QUEUE_GENERATION_LIMIT=-1)
            message='A generation limit must be a positive representable integer' ;;
    esac
    if g++ "${flags[@]}" "${definitions[@]}" -I. -x c++ - -fsyntax-only \
        >"build/uefi/nvme-queues-invalid-$invalid.log" 2>&1 <<'CPP'
#include "kernel/uefi/nvme-queues.hpp"
CPP
    then
        echo "FAIL: invalid queue configuration $invalid was accepted" >&2
        exit 1
    fi
    grep -q "$message" "build/uefi/nvme-queues-invalid-$invalid.log"
done
for incompatible in RUNTIME IVRS TABLES; do
    if g++ "${flags[@]}" -DAURORA_UEFI_NVME_PREPARE -DAURORA_UEFI_ACPI -DAURORA_UEFI_PCI \
        -DAURORA_UEFI_BAR_CAPTURE -DAURORA_UEFI_BAR_EDK2 \
        "-DAURORA_UEFI_$incompatible" -fsyntax-only kernel/uefi/pci.cpp \
        >"build/uefi/nvme-queues-profile-$incompatible.log" 2>&1
    then
        echo "FAIL: incompatible preparation profile $incompatible was accepted" >&2
        exit 1
    fi
    grep -q 'NVMe preparation requires the standalone BAR profile' "build/uefi/nvme-queues-profile-$incompatible.log"
done
for missing in ACPI PCI BAR_CAPTURE BAR_EDK2; do
    definitions=(-DAURORA_UEFI_NVME_PREPARE)
    for required in ACPI PCI BAR_CAPTURE BAR_EDK2; do
        if [[ "$missing" != "$required" ]]; then definitions+=("-DAURORA_UEFI_$required"); fi
    done
    if g++ "${flags[@]}" "${definitions[@]}" -fsyntax-only kernel/uefi/pci.cpp \
        >"build/uefi/nvme-queues-missing-$missing.log" 2>&1
    then
        echo "FAIL: incomplete preparation profile without $missing was accepted" >&2
        exit 1
    fi
    grep -q 'NVMe preparation requires the standalone BAR profile' "build/uefi/nvme-queues-missing-$missing.log"
done
echo 'PASS: production queue API and invalid configuration/profile controls'
python3 tests/kernel-uefi-nvme-stack.py --self-test
python3 -O tests/kernel-uefi-nvme-stack.py --self-test
