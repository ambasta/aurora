#include "owned-bytes.hpp"

#if !defined(AURORA_UEFI_OWNED_BYTES) || defined(AURORA_UEFI_ACPI) || defined(AURORA_UEFI_PCI) ||                      \
    defined(AURORA_UEFI_RUNTIME) || defined(AURORA_UEFI_CONSOLE) || defined(AURORA_UEFI_BAR_CAPTURE) ||                \
    defined(AURORA_UEFI_BAR_ADMISSION) || defined(AURORA_UEFI_BAR_EDK2) || defined(AURORA_UEFI_IVRS) ||                \
    defined(AURORA_UEFI_NVME_PREPARE) || defined(AURORA_UEFI_PINS) || defined(AURORA_UEFI_TABLES) ||                   \
    defined(AURORA_UEFI_IPC) || defined(AURORA_UEFI_SERVICE_BUDGET) || defined(AURORA_UEFI_DISPATCH) ||                \
    defined(AURORA_UEFI_USER_BUDGET) || defined(AURORA_EARLY_FIXTURE) || defined(AURORA_KERNEL_BYTES_TESTING)
#error "Owned bytes require the exclusive normal CPU allocation profile"
#endif

#include "../console.hpp"
#include "../owned-bytes.hpp"
#include "handoff.hpp"

#include <array>
#include <span>
#include <optional>
#include <utility>

extern "C" std::int64_t
__au_runtime_bytes_kernel_entry(std::uint64_t region, std::int64_t length, std::int64_t selector) noexcept;
extern "C" void __au_runtime_bytes_kernel_produce(std::uint64_t region, std::int64_t selector, void *result) noexcept;

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

[[gnu::noinline]] bool run_copied_record(std::uint64_t arena, memory::PhysicalPages &pool) noexcept {
    const auto base = arena + Handoff::pool_offset;
    std::span<std::byte> backing{reinterpret_cast<std::byte *>(base), Region::backing_bytes};
    volatile std::byte *data = backing.data();
    std::array<std::optional<memory::PageLease>, Region::pool_pages> holders;
    for (std::size_t scenario = 0; scenario < 4; ++scenario) {
        if (pool.used() != 0) {
            return false;
        }
        for (std::size_t index = 0; index < backing.size(); ++index) {
            data[index] = std::byte{0xa5};
        }
        const std::size_t held = scenario == 3 ? Region::pool_pages : 0;
        for (std::size_t index = 0; index < held; ++index) {
            auto lease = pool.acquire();
            if (!lease || pool.address(*lease) != base + index * Region::page_bytes) {
                return false;
            }
            holders[index].emplace(std::move(*lease));
        }
        const std::uint64_t quota = scenario == 2 ? 511 : 512;
        if (!byte_region.open(pool, backing, base, quota)) {
            return false;
        }
        // Nine canonical words: status followed by all 64 record bytes. Fresh
        // poisoned storage has two leading and one trailing canary words. It is
        // disjoint from the bridge's private aligned region/selector record.
        alignas(16) std::array<std::uint64_t, 12> output;
        output.fill(0xa5a5a5a5a5a5a5a5);
        __au_runtime_bytes_kernel_produce(byte_region.id(), scenario == 1 ? 1 : 0, output.data() + 2);
        kernel::bytes::Metrics expected;
        expected.quota = quota;
        if (scenario < 2) {
            expected.successful_allocations = 1;
            expected.releases = 1;
            expected.peak_live_allocations = 1;
            expected.peak_used = 512;
            expected.last_allocation_id = 28 + scenario;
            expected.last_released_id = 28 + scenario;
            expected.peak_held_pages = 1;
        }
        // No returned status or payload is inspected until every owner has
        // ended, all accounting is exact and the actual region has closed.
        if (byte_region.metrics() != expected || pool.used() != held || !byte_region.close() || byte_region.is_open() ||
            byte_region.faulted()) {
            return false;
        }
        for (std::size_t index = 0; index < backing.size(); ++index) {
            const auto byte = scenario < 2 && index < Region::page_bytes ? std::byte{0} : std::byte{0xa5};
            if (data[index] != byte) {
                return false;
            }
        }
        for (std::size_t index = 0; index < held; ++index) {
            if (pool.address(*holders[index]) != base + index * Region::page_bytes || !pool.release(*holders[index])) {
                return false;
            }
            holders[index].reset();
        }
        auto reused = pool.acquire();
        if (!reused || pool.address(*reused) != base) {
            return false;
        }
        for (std::size_t index = 0; index < Region::page_bytes; ++index) {
            data[index] = std::byte{0xdd};
        }
        for (std::size_t index = 0; index < Region::page_bytes; ++index) {
            if (data[index] != std::byte{0xdd}) {
                return false;
            }
        }
        const std::uint64_t status = scenario == 0 ? 0 : scenario == 1 ? 1 : 3;
        if (output[0] != 0xa5a5a5a5a5a5a5a5 || output[1] != 0xa5a5a5a5a5a5a5a5 || output[11] != 0xa5a5a5a5a5a5a5a5 ||
            output[2] != status) {
            return false;
        }
        const auto *record = reinterpret_cast<const unsigned char *>(output.data() + 3);
        for (std::size_t index = 0; index < 64; ++index) {
            const auto byte = scenario == 0 ? static_cast<unsigned char>((index * 53 + 7) % 256) : 0;
            if (record[index] != byte) {
                return false;
            }
        }
        if (!pool.release(*reused) || pool.used() != 0) {
            return false;
        }
        Serial::text("AURORA_UEFI_OWNED_BYTES_COPY: case=");
        Serial::number(scenario);
        Serial::text(" status=");
        Serial::number(status);
        Serial::text(" bytes=64 closed=1 reused=1 canaries=1 allocations=");
        Serial::number(expected.successful_allocations);
        Serial::text(" releases=");
        Serial::number(expected.releases);
        Serial::text(" used=0\r\n");
    }
    return true;
}

[[gnu::noinline]] bool run_ram_sectors(std::uint64_t arena, memory::PhysicalPages &pool) noexcept {
    const auto base = arena + Handoff::pool_offset;
    std::span<std::byte> backing{reinterpret_cast<std::byte *>(base), Region::backing_bytes};
    std::array<std::optional<memory::PageLease>, Region::pool_pages> holders;
    volatile std::byte *data = backing.data();
    for (std::size_t scenario = 0; scenario < 4; ++scenario) {
        if (pool.used() != 0) {
            return false;
        }
        for (std::size_t page = 0; page < holders.size(); ++page) {
            holders[page].reset();
            for (std::size_t offset = 0; offset < Region::page_bytes; ++offset) {
                data[page * Region::page_bytes + offset] = std::byte{static_cast<unsigned char>(0xa0 + page)};
            }
            auto lease = pool.acquire();
            if (!lease || pool.address(*lease) != base + page * Region::page_bytes) {
                return false;
            }
            holders[page].emplace(std::move(*lease));
        }
        const std::size_t held = scenario == 1 ? 0 : scenario == 3 ? 14 : 8;
        for (std::size_t page = 0; page < holders.size(); ++page) {
            const bool available = scenario == 1 || (scenario == 3 ? page == 1 || page == 3 : page % 2 == 1);
            if (available) {
                if (!pool.release(*holders[page])) {
                    return false;
                }
                holders[page].reset();
            }
        }
        if (pool.used() != held || !byte_region.open(pool, backing, base, payload_quota) ||
            __au_runtime_bytes_kernel_entry(byte_region.id(), 16, static_cast<std::int64_t>(scenario + 4)) != 42) {
            return false;
        }
        kernel::bytes::Metrics expected;
        expected.quota = payload_quota;
        expected.successful_allocations = 1;
        expected.releases = 1;
        expected.peak_live_allocations = 1;
        expected.peak_used = 8192;
        expected.last_allocation_id = 24 + scenario;
        expected.last_released_id = 24 + scenario;
        expected.peak_held_pages = 2;
        if (byte_region.metrics() != expected || pool.used() != held) {
            return false;
        }
        for (std::size_t page = 0; page < holders.size(); ++page) {
            const bool touched = scenario == 1 ? page < 2 : page == 1 || page == 3;
            const auto expected_byte = touched ? std::byte{0} : std::byte{static_cast<unsigned char>(0xa0 + page)};
            for (std::size_t offset = 0; offset < Region::page_bytes; ++offset) {
                if (data[page * Region::page_bytes + offset] != expected_byte) {
                    return false;
                }
            }
            if (holders[page] && pool.address(*holders[page]) != base + page * Region::page_bytes) {
                return false;
            }
        }
        if (!byte_region.close() || byte_region.is_open() || byte_region.faulted()) {
            return false;
        }
        for (auto &holder : holders) {
            if (holder && !pool.release(*holder)) {
                return false;
            }
        }
        if (pool.used() != 0) {
            return false;
        }
        if (scenario == 0) {
            Serial::text("AURORA_UEFI_OWNED_BYTES_RECORD: sectors=16 pages=1,3 holders=8 snapshot=1 scrubbed=1 "
                         "allocations=1 releases=1 used=0\r\n");
        } else {
            Serial::text("AURORA_UEFI_OWNED_BYTES_STORAGE: case=");
            Serial::number(scenario - 1);
            Serial::text(" sectors=16 written=0,7,8,15 boundary=4095,4096 pages=");
            Serial::text(scenario == 1 ? "0,1" : "1,3");
            Serial::text(" holders=");
            Serial::number(held);
            Serial::text(" snapshot=1 bounds=1 readonly=1 visibility=1 durable=0 failure=");
            Serial::text(scenario == 3 ? "pages" : "quota");
            Serial::text(" preserved=1 scrubbed=1 allocations=1 releases=1 used=0\r\n");
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
    // Real alternating leases force owners onto pages 1/3 and 5/7.
    std::array<std::optional<memory::PageLease>, Region::pool_pages> holders;
    volatile std::byte *data = backing.data();
    for (std::size_t index = 0; index < backing.size(); ++index) {
        data[index] = std::byte{0xa5};
    }
    for (std::size_t index = 0; index < holders.size(); ++index) {
        auto lease = pool.acquire();
        if (!lease || pool.address(*lease) != base + index * Region::page_bytes) {
            return false;
        }
        holders[index].emplace(std::move(*lease));
    }
    for (std::size_t index = 1; index < holders.size(); index += 2) {
        if (!pool.release(*holders[index])) {
            return false;
        }
        holders[index].reset();
    }
    const auto fragmented = __au_runtime_bytes_kernel_entry(byte_region.id(), 4097, 0);
    const auto state = byte_region.metrics();
    if (fragmented != 42 || pool.used() != 8 || state.used != 0 || state.live_allocations != 0 ||
        state.held_pages != 0 || state.retained_pages != 0 || state.successful_allocations != 8 ||
        state.releases != 8 || state.peak_live_allocations != 2 || state.peak_used != payload_quota ||
        state.peak_held_pages != 4) {
        return false;
    }
    for (std::size_t index = 0; index < holders.size(); ++index) {
        const auto expected = (index == 1 || index == 3 || index == 5 || index == 7) ? std::byte{0} : std::byte{0xa5};
        for (std::size_t byte = 0; byte < Region::page_bytes; ++byte) {
            if (data[index * Region::page_bytes + byte] != expected) {
                return false;
            }
        }
        if (index % 2 == 0 && pool.address(*holders[index]) != base + index * Region::page_bytes) {
            return false;
        }
    }
    for (std::size_t index = 0; index < holders.size(); index += 2) {
        if (!pool.release(*holders[index])) {
            return false;
        }
    }
    if (pool.used() != 0) {
        return false;
    }
    Serial::text("AURORA_UEFI_OWNED_BYTES_FRAGMENTED: length=4097 owners=2 pages=1,3,5,7 holders=8 preserved=1 "
                 "releases=8 used=0\r\n");
    const auto empty = __au_runtime_bytes_kernel_entry(byte_region.id(), 0, 0);
    const auto final = byte_region.metrics();
    if (empty != 42 || pool.used() != 0 || final.used != 0 || final.live_allocations != 0 || final.held_pages != 0 ||
        final.retained_pages != 0 || final.successful_allocations != 9 || final.releases != 9 ||
        final.peak_live_allocations != 2 || final.peak_used != payload_quota || final.peak_held_pages != 4) {
        return false;
    }
    Serial::text("AURORA_UEFI_OWNED_BYTES_VIEWS: crossing=4095,4096 empty=1 allocations=9 releases=9 used=0\r\n");
    std::uint64_t total = 9;
    for (std::size_t scenario = 0; scenario < 4; ++scenario) {
        // Acquire actual independent holders before freeing the exact pages
        // available to this transaction. No copied address grants authority.
        for (std::size_t index = 0; index < backing.size(); ++index) {
            data[index] = std::byte{0xa5};
        }
        for (std::size_t index = 0; index < holders.size(); ++index) {
            holders[index].reset();
            auto lease = pool.acquire();
            if (!lease || pool.address(*lease) != base + index * Region::page_bytes) {
                return false;
            }
            holders[index].emplace(std::move(*lease));
        }
        const std::size_t held = scenario == 0 ? 0 : scenario == 1 ? 8 : scenario == 2 ? 14 : 13;
        for (std::size_t index = 0; index < holders.size(); ++index) {
            const bool available = scenario == 0 || (scenario == 1 ? index % 2 == 1 : index >= held);
            if (available) {
                if (!pool.release(*holders[index])) {
                    return false;
                }
                holders[index].reset();
            }
        }
        const auto selector = scenario < 2 ? 1 : static_cast<std::int64_t>(scenario);
        if (__au_runtime_bytes_kernel_entry(byte_region.id(), 4097, selector) != 42) {
            return false;
        }
        total += scenario < 2 ? 6 : 1;
        const auto resized = byte_region.metrics();
        if (pool.used() != held || resized.used != 0 || resized.live_allocations != 0 || resized.held_pages != 0 ||
            resized.retained_pages != 0 || resized.successful_allocations != total || resized.releases != total ||
            resized.peak_live_allocations != 2 || resized.peak_used != payload_quota || resized.peak_held_pages != 4) {
            return false;
        }
        for (std::size_t index = 0; index < holders.size(); ++index) {
            const bool touched = scenario == 0   ? index < 4
                                 : scenario == 1 ? (index == 1 || index == 3 || index == 5 || index == 7)
                                                 : index >= held;
            const auto expected = touched ? std::byte{0} : std::byte{0xa5};
            for (std::size_t byte = 0; byte < Region::page_bytes; ++byte) {
                if (data[index * Region::page_bytes + byte] != expected) {
                    return false;
                }
            }
            if (holders[index] && pool.address(*holders[index]) != base + index * Region::page_bytes) {
                return false;
            }
        }
        for (auto &holder : holders) {
            if (holder && !pool.release(*holder)) {
                return false;
            }
        }
        if (pool.used() != 0) {
            return false;
        }
        Serial::text("AURORA_UEFI_OWNED_BYTES_RESIZE: case=");
        Serial::number(scenario);
        Serial::text(" prefix=1 zero=1 preserved=1 allocations=");
        Serial::number(total);
        Serial::text(" releases=");
        Serial::number(total);
        Serial::text(" used=0\r\n");
    }
    if (!byte_region.close() || byte_region.is_open() || byte_region.faulted() || pool.used() != 0) {
        return false;
    }
    Serial::text("AURORA_UEFI_OWNED_BYTES_CLOSED: quota=8194 used=0 allocations=23 releases=23\r\n");
    return run_ram_sectors(arena, pool) && run_copied_record(arena, pool);
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
