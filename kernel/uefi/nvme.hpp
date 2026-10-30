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
[[nodiscard]] auto nvme_read_sector(const NvmeReadContext &context, std::uint64_t lba, std::span<std::byte, 512> output)
    -> NvmeReadStatus;

// These entrypoints are only used by the separately authenticated boot recovery
// role. Existing readonly compositions never call initialization or mint it.
auto initialize_nvme_recovery(std::uint64_t arena, const Bytes &handoff, const NvmeControllerAdmission &admission)
    -> void;
[[nodiscard]] auto nvme_recovery_sector_count() -> std::uint64_t;
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
auto nvme_mounted_abandon() -> void;

#if !defined(AURORA_PROCESS_FIXTURE) && !defined(AURORA_PRODUCTION)
[[noreturn]] auto run_nvme(std::uint64_t arena, const Bytes &handoff, const NvmeAdmission &admission) -> void;
#endif
} // namespace aurora::uefi
