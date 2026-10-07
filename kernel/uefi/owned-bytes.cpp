#include "owned-bytes.hpp"

#if !defined(AURORA_UEFI_OWNED_BYTES) || defined(AURORA_UEFI_ACPI) || defined(AURORA_UEFI_PCI) ||                      \
    defined(AURORA_UEFI_RUNTIME) || defined(AURORA_UEFI_CONSOLE) || defined(AURORA_UEFI_BAR_CAPTURE) ||                \
    defined(AURORA_UEFI_BAR_ADMISSION) || defined(AURORA_UEFI_BAR_EDK2) || defined(AURORA_UEFI_IVRS) ||                \
    defined(AURORA_UEFI_NVME_PREPARE) || defined(AURORA_UEFI_PINS) || defined(AURORA_UEFI_TABLES) ||                   \
    defined(AURORA_UEFI_IPC) || defined(AURORA_UEFI_SERVICE_BUDGET) || defined(AURORA_UEFI_DISPATCH) ||                \
    defined(AURORA_UEFI_USER_BUDGET) || defined(AURORA_UEFI_WP) || defined(AURORA_UEFI_NX) ||                          \
    defined(AURORA_UEFI_STALE) || defined(AURORA_UEFI_EXHAUSTED) || defined(AURORA_UEFI_BAD_HANDOFF) ||                \
    defined(AURORA_UEFI_BAD_TABLE) || defined(AURORA_UEFI_BAD_MAP) || defined(AURORA_KERNEL_BYTES_TESTING)
#error "Owned bytes require the exclusive normal CPU allocation profile"
#endif

#include "../console.hpp"
#include "../owned-bytes.hpp"
#include "handoff.hpp"

#include <array>
#include <span>

extern "C" std::int64_t
__au_runtime_bytes_kernel_entry(std::uint64_t region, std::int64_t length, std::int64_t selector) noexcept;

namespace aurora::uefi {
namespace {
using hardware::Serial;
using kernel::bytes::Region;

constinit Region byte_region;
constexpr std::uint64_t payload_quota = 8194;

bool zero(std::span<std::byte> backing, std::size_t size) noexcept {
    const volatile std::byte *data = backing.data();
    for (std::size_t index = 0; index < size; ++index) {
        if (data[index] != std::byte{0}) {
            return false;
        }
    }
    return true;
}
} // namespace

[[gnu::noinline]] bool run_owned_bytes(std::uint64_t arena, memory::PhysicalPages &pool) noexcept {
    // The caller has verified owned handoff/map/page tables and IF=0. This is
    // the exact supervisor RW/NX identity mapping, never the user-stack pool.
    const auto base = arena + Handoff::pool_offset;
    std::span<std::byte> backing{reinterpret_cast<std::byte *>(base), Region::backing_bytes};
    if (pool.used() != 0 || !byte_region.open(pool, backing, base, payload_quota)) {
        return false;
    }
    std::uint64_t completed = 0;
    for (const std::int64_t length : std::array<std::int64_t, 3>{65, 513, 4097}) {
        const auto pages =
            2 * (static_cast<std::size_t>(length) / Region::page_bytes + (length % Region::page_bytes != 0 ? 1 : 0));
        // No leases are live. PhysicalPages' existing first-fit behavior makes
        // this an independent guest poison/readback check, not an exported view.
        volatile std::byte *data = backing.data();
        for (std::size_t index = 0; index < pages * Region::page_bytes; ++index) {
            data[index] = std::byte{0xa5};
        }
        const auto result = __au_runtime_bytes_kernel_entry(byte_region.id(), length, 0);
        ++completed;
        const auto state = byte_region.metrics();
        if (result != 42 || pool.used() != 0 || state.used != 0 || state.live_allocations != 0 ||
            state.held_pages != 0 || state.retained_pages != 0 || state.successful_allocations != completed * 2 ||
            state.releases != completed * 2 || state.peak_live_allocations != 2 ||
            state.peak_used != static_cast<std::uint64_t>(2 * length) || state.peak_held_pages != pages ||
            !zero(backing, pages * Region::page_bytes)) {
            return false;
        }
        Serial::text("AURORA_UEFI_OWNED_BYTES: length=");
        Serial::number(static_cast<std::uint64_t>(length));
        Serial::text(" owners=2 pages=");
        Serial::number(pages);
        Serial::text(" releases=");
        Serial::number(state.releases);
        Serial::text(" used=0\r\n");
    }
    if (!byte_region.close() || byte_region.is_open() || byte_region.faulted() || pool.used() != 0) {
        return false;
    }
    Serial::text("AURORA_UEFI_OWNED_BYTES_CLOSED: quota=8194 used=0 allocations=6 releases=6\r\n");
    return true;
}
} // namespace aurora::uefi

extern "C" [[noreturn]] void __au_runtime_bytes_kernel_fault(std::uint64_t reason) noexcept {
    aurora::hardware::Serial::text("AURORA_UEFI_OWNED_BYTES_FAIL: reason=");
    aurora::hardware::Serial::number(reason);
    aurora::hardware::Serial::text("\r\n");
    aurora::hardware::Io::write(0xf4, 0x11);
    for (;;) {
        asm volatile("cli; hlt");
    }
}
