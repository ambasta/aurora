#!/usr/bin/env bash
set -euo pipefail
cd "/workspace/scratch/48c5de6446f8/aurora"
mkdir -p /workspace/scratch/48c5de6446f8/pin-lifetime-review
flags=(-std=c++23 -O1 -g -Wall -Wextra -Wpedantic -Werror)
if [[ "${SANITIZE:-0}" == 1 ]]; then
    flags+=(-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer)
fi
for bound in full 3; do
    definitions=(-DAURORA_PIN_LEDGER_TESTING=1)
    if [[ "$bound" != full ]]; then
        definitions+=(-DAURORA_PIN_LEDGER_TEST_GENERATION_LIMIT="$bound")
    fi
    g++ "${flags[@]}" "${definitions[@]}" tests/kernel-pin-ledger.cpp -o "/workspace/scratch/48c5de6446f8/pin-lifetime-review/kernel-pin-ledger-$bound-test"
    ASAN_OPTIONS="${ASAN_OPTIONS:-detect_leaks=0}" "/workspace/scratch/48c5de6446f8/pin-lifetime-review/kernel-pin-ledger-$bound-test"
done
# The normal header must not contain the fault-injection interface, and clients
# cannot mint bindings, publish frames, import leases, or report completion.
g++ "${flags[@]}" -I. -x c++ - -o /workspace/scratch/48c5de6446f8/pin-lifetime-review/kernel-pin-production-api-test <<'CPP'
#include "kernel/pin-ledger.hpp"
#include <type_traits>
using aurora::memory::PinHandle;
using aurora::memory::PinLedger;
using aurora::user::DomainHandle;
template <class T> concept HasInjection = requires(T& ledger, PinHandle pin, DomainHandle domain) {
    ledger.inject_uncertainty(pin, domain);
};
template <class T> concept HasPublication = requires(T& ledger, PinHandle pin) { ledger.publish(pin); };
template <class T> concept HasCompletion = requires(T& ledger, PinHandle pin) { ledger.complete(pin); };
static_assert(!HasInjection<PinLedger> && !HasPublication<PinLedger> && !HasCompletion<PinLedger>);
static_assert(!std::is_constructible_v<PinHandle, PinLedger&, unsigned long, unsigned long, unsigned long>);
auto main() -> int { return 0; }
CPP
ASAN_OPTIONS="${ASAN_OPTIONS:-detect_leaks=0}" /workspace/scratch/48c5de6446f8/pin-lifetime-review/kernel-pin-production-api-test
if g++ "${flags[@]}" -DAURORA_PIN_LEDGER_TEST_GENERATION_LIMIT=3 -I. -x c++ - -fsyntax-only \
        >/workspace/scratch/48c5de6446f8/pin-lifetime-review/kernel-pin-illegal-test-configuration.log 2>&1 <<'CPP'
#include "kernel/pin-ledger.hpp"
CPP
then
    echo 'FAIL: production accepted test generation configuration' >&2
    exit 1
fi
rg -q 'A small pin generation limit is only available in explicit test builds' /workspace/scratch/48c5de6446f8/pin-lifetime-review/kernel-pin-illegal-test-configuration.log
if g++ "${flags[@]}" -DAURORA_PIN_LEDGER_TESTING=0 -I. -x c++ - -fsyntax-only \
        >/workspace/scratch/48c5de6446f8/pin-lifetime-review/kernel-pin-disabled-test-configuration.log 2>&1 <<'CPP'
#include "kernel/pin-ledger.hpp"
CPP
then
    echo 'FAIL: non-enabled test macro exposed pin test interfaces' >&2
    exit 1
fi
rg -q 'Pin test interfaces require explicit AURORA_PIN_LEDGER_TESTING=1' /workspace/scratch/48c5de6446f8/pin-lifetime-review/kernel-pin-disabled-test-configuration.log
for invalid_bound in 0 -1; do
    if g++ "${flags[@]}" -DAURORA_PIN_LEDGER_TESTING=1 -DAURORA_PIN_LEDGER_TEST_GENERATION_LIMIT="$invalid_bound" \
            -I. -x c++ - -fsyntax-only >/workspace/scratch/48c5de6446f8/pin-lifetime-review/kernel-pin-invalid-generation.log 2>&1 <<'CPP'
#include "kernel/pin-ledger.hpp"
CPP
    then
        echo "FAIL: accepted invalid generation bound $invalid_bound" >&2
        exit 1
    fi
    rg -q 'A generation limit must be a positive representable integer' /workspace/scratch/48c5de6446f8/pin-lifetime-review/kernel-pin-invalid-generation.log
done
echo 'PASS: production pin API excludes publication/completion/injection; four invalid test configurations rejected'
