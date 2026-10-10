#include "snapshot.hpp"

#if !defined(AURORA_UEFI_SNAPSHOT) || !defined(AURORA_UEFI_RUNTIME) || !defined(AURORA_UEFI_IPC) ||                    \
    !defined(AURORA_UEFI_ACPI) || !defined(AURORA_UEFI_PCI) || defined(AURORA_UEFI_OWNED_BYTES) ||                     \
    defined(AURORA_UEFI_DISPATCH) || defined(AURORA_UEFI_SERVICE_BUDGET) || defined(AURORA_UEFI_USER_BUDGET) ||        \
    defined(AURORA_UEFI_PROGRAM_CONSOLE) || defined(AURORA_UEFI_CONSOLE) || defined(AURORA_UEFI_GRAPHICAL_CONSOLE) ||  \
    defined(AURORA_UEFI_FRAMEBUFFER) || defined(AURORA_UEFI_PINS) || defined(AURORA_UEFI_TABLES) ||                    \
    defined(AURORA_UEFI_IVRS) || defined(AURORA_UEFI_NVME_PREPARE) || defined(AURORA_UEFI_IOMMU_EVENT) ||              \
    defined(AURORA_UEFI_BAR_CAPTURE) || defined(AURORA_UEFI_BAR_ADMISSION) || defined(AURORA_UEFI_BAR_EDK2) ||         \
    defined(AURORA_KERNEL_BYTES_TESTING)
#error "Snapshot producer requires its exact CPU-only protected IPC profile"
#endif

#include "../owned-bytes.hpp"
#include "handoff.hpp"

#include <array>
#include <optional>
#include <span>
#include <utility>

extern "C" void __au_runtime_snapshot_produce(std::uint64_t, std::int64_t, void *) noexcept;

namespace aurora::uefi {
namespace {
using kernel::bytes::Region;
constinit Region producer_region;
constexpr auto malformed = ipc::SnapshotPublication::malformed;
} // namespace

[[gnu::noinline]] ipc::SnapshotPublication prepare_snapshot(std::uint64_t arena,
                                                            memory::PhysicalPages &pool,
                                                            ipc::SnapshotSlot &slot,
                                                            SnapshotProducerCase scenario) noexcept {
    slot.clear();
    if (pool.used() != 0 ||
        (scenario != SnapshotProducerCase::normal && scenario != SnapshotProducerCase::invalid_selector &&
         scenario != SnapshotProducerCase::quota && scenario != SnapshotProducerCase::pages)) {
        return malformed;
    }
    const auto base = arena + Handoff::pool_offset;
    std::span<std::byte> backing{reinterpret_cast<std::byte *>(base), Region::backing_bytes};
    volatile std::byte *data = backing.data();
    for (std::size_t byte = 0; byte < backing.size(); ++byte) {
        data[byte] = std::byte{0xa5};
    }
    std::array<std::optional<memory::PageLease>, Region::pool_pages> holders;
    const std::size_t held = scenario == SnapshotProducerCase::pages ? Region::pool_pages : 0;
    for (std::size_t page = 0; page < held; ++page) {
        auto lease = pool.acquire();
        if (!lease || pool.address(*lease) != base + page * Region::page_bytes) {
            return malformed;
        }
        holders[page].emplace(std::move(*lease));
    }
    const std::uint64_t quota = scenario == SnapshotProducerCase::quota ? 511 : 512;
    if (!producer_region.open(pool, backing, base, quota)) {
        return malformed;
    }
    alignas(16) std::array<std::uint64_t, 12> output;
    output.fill(0xa5a5a5a5a5a5a5a5);
    __au_runtime_snapshot_produce(
        producer_region.id(), scenario == SnapshotProducerCase::invalid_selector ? 1 : 0, output.data() + 2);
    const bool allocated =
        scenario == SnapshotProducerCase::normal || scenario == SnapshotProducerCase::invalid_selector;
    const auto metrics = producer_region.metrics();
    kernel::bytes::Metrics expected;
    expected.quota = quota;
    if (allocated) {
        expected.successful_allocations = 1;
        expected.releases = 1;
        expected.peak_live_allocations = 1;
        expected.peak_used = 512;
        expected.last_allocation_id = metrics.last_allocation_id;
        expected.last_released_id = metrics.last_allocation_id;
        expected.peak_held_pages = 1;
        if (metrics.last_allocation_id == 0) {
            return malformed;
        }
    }
    // Inspect no output until ownership, pool and region have actually closed.
    if (metrics != expected || pool.used() != held || !producer_region.close() || producer_region.is_open() ||
        producer_region.faulted()) {
        return malformed;
    }
    for (std::size_t byte = 0; byte < backing.size(); ++byte) {
        const auto wanted = allocated && byte < Region::page_bytes ? std::byte{0} : std::byte{0xa5};
        if (data[byte] != wanted) {
            return malformed;
        }
    }
    for (std::size_t page = 0; page < held; ++page) {
        if (pool.address(*holders[page]) != base + page * Region::page_bytes || !pool.release(*holders[page])) {
            return malformed;
        }
        holders[page].reset();
    }
    auto reused = pool.acquire();
    if (!reused || pool.address(*reused) != base) {
        return malformed;
    }
    for (std::size_t byte = 0; byte < Region::page_bytes; ++byte) {
        data[byte] = std::byte{0xdd};
    }
    for (std::size_t byte = 0; byte < Region::page_bytes; ++byte) {
        if (data[byte] != std::byte{0xdd}) {
            return malformed;
        }
    }
    if (!pool.release(*reused) || pool.used() != 0 || output[0] != 0xa5a5a5a5a5a5a5a5 ||
        output[1] != 0xa5a5a5a5a5a5a5a5 || output[11] != 0xa5a5a5a5a5a5a5a5) {
        return malformed;
    }
    const auto result =
        slot.publish(std::span<const std::byte, 72>{reinterpret_cast<const std::byte *>(output.data() + 2), 72});
    // A dead-local fill can disappear. Match the existing Region scrub's
    // volatile store/readback idiom for this explicitly promised output buffer.
    volatile std::byte *copied = reinterpret_cast<volatile std::byte *>(output.data());
    for (std::size_t byte = 0; byte < sizeof(output); ++byte) {
        copied[byte] = std::byte{0};
    }
    for (std::size_t byte = 0; byte < sizeof(output); ++byte) {
        if (copied[byte] != std::byte{0}) {
            slot.clear();
            return malformed;
        }
    }
    return result;
}

} // namespace aurora::uefi
