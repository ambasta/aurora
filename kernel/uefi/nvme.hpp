#pragma once
#include "event-profile-policy.hpp"
namespace aurora::uefi {
// Only the process dispatcher may mint a context after authenticating its
// designated service incarnation, independent block grant and shared root.
class ProcessBlockBroker;
class NvmeReadContext final {
    friend class ProcessBlockBroker;
    std::uint64_t root_, generation_;
    NvmeReadContext(std::uint64_t verified_root, std::uint64_t generation)
        : root_(verified_root), generation_(generation) {
    }

public:
    [[nodiscard]] auto root() const -> std::uint64_t {
        return root_;
    }
    [[nodiscard]] auto generation() const -> std::uint64_t {
        return generation_;
    }
};
// Immutable namespace authority minted only by the authenticated set broker.
class ProcessBlocksBroker;
class NvmeVolumeContext final {
    friend class ProcessBlocksBroker;
    std::uint64_t root_, generation_, controller_, nsid_, sectors_;
    NvmeVolumeContext(std::uint64_t root,
                      std::uint64_t generation,
                      std::uint64_t controller,
                      std::uint64_t nsid,
                      std::uint64_t sectors)
        : root_(root), generation_(generation), controller_(controller), nsid_(nsid), sectors_(sectors) {
    }

public:
    auto root() const -> std::uint64_t {
        return root_;
    }
    auto generation() const -> std::uint64_t {
        return generation_;
    }
    auto controller() const -> std::uint64_t {
        return controller_;
    }
    auto nsid() const -> std::uint64_t {
        return nsid_;
    }
    auto sectors() const -> std::uint64_t {
        return sectors_;
    }
};
class ProcessRecoveryBroker;
class NvmeRecoveryContext final {
    friend class ProcessRecoveryBroker;
    std::uint64_t root_, generation_;
    NvmeRecoveryContext(std::uint64_t root, std::uint64_t generation) : root_(root), generation_(generation) {
    }

public:
    [[nodiscard]] auto root() const -> std::uint64_t {
        return root_;
    }
    [[nodiscard]] auto generation() const -> std::uint64_t {
        return generation_;
    }
};
class ProcessMountedBroker;
class NvmeMountedContext final {
    friend class ProcessMountedBroker;
    std::uint64_t root_, generation_;
    NvmeMountedContext(std::uint64_t root, std::uint64_t generation) : root_(root), generation_(generation) {
    }

public:
    [[nodiscard]] auto root() const -> std::uint64_t {
        return root_;
    }
    [[nodiscard]] auto generation() const -> std::uint64_t {
        return generation_;
    }
};
enum class NvmeReadStatus : std::uint64_t {
    success,
    out_of_range,
    failed,
    unavailable
};
#ifdef AURORA_PRODUCTION
using NvmeControllerAdmission = NvmeGraphicsAdmission;
#else
using NvmeControllerAdmission = NvmeAdmission;
#endif
// Startup errors fail-stop before any process can receive the block grant.
auto initialize_nvme_readonly(std::uint64_t arena, const Bytes &handoff, const NvmeControllerAdmission &admission)
    -> void;
[[nodiscard]] auto nvme_sector_count() -> std::uint64_t;
[[nodiscard]] auto nvme_sector_count(const NvmeReadContext &context) -> std::uint64_t;
[[nodiscard]] auto nvme_read_sector(const NvmeReadContext &context, std::uint64_t lba, std::span<std::byte, 512> output)
    -> NvmeReadStatus;

auto initialize_nvme_dual_readonly(std::uint64_t arena, const Bytes &handoff, const NvmeControllerAdmission &admission)
    -> void;
[[nodiscard]] auto nvme_volume_count() -> unsigned;
[[nodiscard]] auto nvme_volume_identity(unsigned slot, unsigned field) -> std::uint64_t;
[[nodiscard]] auto nvme_volume_count(const NvmeVolumeContext &context) -> std::uint64_t;
[[nodiscard]] auto nvme_volume_budget(const NvmeVolumeContext &context) -> unsigned;
[[nodiscard]] auto nvme_volume_read(const NvmeVolumeContext &context,
                                    std::uint64_t lba,
                                    std::span<std::byte, 512> output) -> NvmeReadStatus;

// These entrypoints are only used by the separately authenticated boot recovery
// role. Existing readonly compositions never call initialization or mint it.
auto initialize_nvme_recovery(std::uint64_t arena, const Bytes &handoff, const NvmeControllerAdmission &admission)
    -> void;
[[nodiscard]] auto nvme_recovery_sector_count() -> std::uint64_t;
[[nodiscard]] auto nvme_recovery_sector_count(const NvmeRecoveryContext &context) -> std::uint64_t;
[[nodiscard]] auto nvme_recovery_admitted_writes() -> unsigned;
[[nodiscard]] auto nvme_recovery_admitted_flushes() -> unsigned;
[[nodiscard]] auto nvme_recovery_budget(const NvmeRecoveryContext &context) -> unsigned;
[[nodiscard]] auto nvme_recovery_read(const NvmeRecoveryContext &context,
                                      std::uint64_t lba,
                                      std::span<std::byte, 512> output) -> NvmeReadStatus;
[[nodiscard]] auto nvme_recovery_write(const NvmeRecoveryContext &context,
                                       std::uint64_t lba,
                                       std::span<const std::byte, 512> input) -> NvmeReadStatus;
[[nodiscard]] auto nvme_recovery_flush(const NvmeRecoveryContext &context) -> NvmeReadStatus;
// Seal runs under the kernel root after clean exit, before freeing the writer.
// Retired is called only after its address space and grant have been destroyed.
[[nodiscard]] auto nvme_recovery_seal() -> bool;
[[nodiscard]] auto nvme_recovery_retired() -> bool;
auto nvme_recovery_abandon() -> void;

// A separate clean mounted service. This cannot follow recovery sealing, and
// neither service restart nor a completed transaction remints its authority.
auto initialize_nvme_mounted(std::uint64_t arena, const Bytes &handoff, const NvmeControllerAdmission &admission)
    -> void;
[[nodiscard]] auto nvme_mounted_sector_count() -> std::uint64_t;
[[nodiscard]] auto nvme_mounted_sector_count(const NvmeMountedContext &context) -> std::uint64_t;
[[nodiscard]] auto nvme_mounted_arm() -> bool;
[[nodiscard]] auto nvme_mounted_admitted_writes() -> unsigned;
[[nodiscard]] auto nvme_mounted_admitted_flushes() -> unsigned;
[[nodiscard]] auto nvme_mounted_budget(const NvmeMountedContext &context) -> unsigned;
[[nodiscard]] auto nvme_mounted_read(const NvmeMountedContext &context,
                                     std::uint64_t lba,
                                     std::span<std::byte, 512> output) -> NvmeReadStatus;
[[nodiscard]] auto nvme_mounted_write(const NvmeMountedContext &context,
                                      std::uint64_t lba,
                                      std::span<const std::byte, 512> input) -> NvmeReadStatus;
[[nodiscard]] auto nvme_mounted_flush(const NvmeMountedContext &context) -> NvmeReadStatus;
// Committed means only that all five physical Flushes completed, not that the
// source filesystem confirmed the transaction. The dispatcher authenticates
// healthy source completion and orderly shutdown independently before sealing.
[[nodiscard]] auto nvme_mounted_committed() -> bool;
[[nodiscard]] auto nvme_mounted_committed(const NvmeMountedContext &context) -> bool;
// Seal revokes only the write-data IOVA under the kernel root. All DMA backing
// remains boot-pinned. Retired follows actual process/grant reclamation and is
// the only transition that exposes the transport to a fresh readonly service.
[[nodiscard]] auto nvme_mounted_seal() -> bool;
[[nodiscard]] auto nvme_mounted_retired() -> bool;
[[nodiscard]] auto nvme_mounted_readonly() -> bool;
auto nvme_mounted_abandon() -> void;

#if !defined(AURORA_PROCESS_FIXTURE) && !defined(AURORA_PRODUCTION)
[[noreturn]] auto run_nvme(std::uint64_t arena, const Bytes &handoff, const NvmeAdmission &admission) -> void;
#endif
} // namespace aurora::uefi
