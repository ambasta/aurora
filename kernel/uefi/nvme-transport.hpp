#pragma once
#include "handoff.hpp"
#include <array>
#include <optional>

namespace aurora::uefi {
// Copied Identify Namespace data, not a mount or filesystem grant. The first
// transport supports one ordinary namespace, 512-byte LBAs, no metadata/PI.
class NvmeNamespace final {
    std::uint64_t blocks_{};
    explicit NvmeNamespace(std::uint64_t blocks) : blocks_(blocks) {
    }

public:
    [[nodiscard]] static auto parse(std::span<const std::byte> bytes) -> std::optional<NvmeNamespace> {
        if (bytes.size() != 4096)
            return std::nullopt;
        const Bytes b{bytes};
        const auto blocks = b.get(0);
        const auto format = b.get(26, 1);
        // QEMU advertises DULBE support plus both optional performance-field
        // bits (ns.c / NVME_ID_NS_NSFEAT_OPTPERF_ALL); none is enabled by this
        // driver. Thin provisioning and every other behavior remain rejected.
        if (!blocks || b.get(8) != blocks || b.get(16) > blocks || (b.get(24, 1) & ~0x34ULL) || format ||
            b.get(29, 1) || b.get(30, 1) || b.get(31, 1) || b.get(128, 2) || b.get(130, 1) != 9)
            return std::nullopt;
        return NvmeNamespace{blocks};
    }
    [[nodiscard]] auto blocks() const -> std::uint64_t {
        return blocks_;
    }
    [[nodiscard]] auto contains(std::uint64_t lba, unsigned count) const -> bool {
        return count >= 1 && count <= 8 && lba < blocks_ && count <= blocks_ - lba;
    }
};

// One outstanding command, two entries, monotonically increasing CID. Queue
// backing is borrowed from the boot owner and never released by this object.
// Every malformed completion/error/timeout is absorbing: no retry or reset.
class NvmePolledQueue final {
public:
    enum class Result {
        pending,
        complete,
        quarantined
    };

private:
    std::span<std::byte> submission_, completion_;
    unsigned id_, tail_{}, head_{}, phase_{1}, next_cid_{1}, active_cid_{};
    bool pending_{}, quarantined_{};
    std::uint16_t status_{};
    [[nodiscard]] auto valid_pages() const -> bool {
        return submission_.size() == 4096 && completion_.size() == 4096 &&
               reinterpret_cast<std::uintptr_t>(submission_.data()) % 4096 == 0 &&
               reinterpret_cast<std::uintptr_t>(completion_.data()) % 4096 == 0 &&
               submission_.data() != completion_.data() && id_ <= 1;
    }

public:
    NvmePolledQueue(std::span<std::byte> submission, std::span<std::byte> completion, unsigned id)
        : submission_(submission), completion_(completion), id_(id) {
    }
    NvmePolledQueue(const NvmePolledQueue &) = delete;
    auto operator=(const NvmePolledQueue &) -> NvmePolledQueue & = delete;
    [[nodiscard]] auto submit(std::array<std::byte, 64> command) -> bool {
        if (quarantined_ || pending_ || next_cid_ > 65535 || !valid_pages() || Bytes{command}.get(2, 2)) {
            quarantine();
            return false;
        }
        active_cid_ = next_cid_++;
        put(command, 2, active_cid_, 2);
        for (unsigned i = 0; i < 64; ++i)
            submission_[tail_ * 64 + i] = command[i];
        tail_ ^= 1;
        pending_ = true;
        asm volatile("mfence" ::: "memory");
        return true;
    }
    [[nodiscard]] auto observe() -> Result {
        if (quarantined_ || !pending_ || !valid_pages())
            return quarantine();
        const auto *entry = reinterpret_cast<volatile const std::uint32_t *>(completion_.data() + head_ * 16);
        const auto last = entry[3];
        if (((last >> 16) & 1) != phase_)
            return Result::pending;
        asm volatile("lfence" ::: "memory");
        const auto reserved = entry[1], position = entry[2];
        status_ = static_cast<std::uint16_t>(last >> 17);
        if (entry[0] || entry[3] != last || reserved || (position >> 16) != id_ || (position & 65535) != tail_ ||
            (last & 65535) != active_cid_ || status_)
            return quarantine();
        pending_ = false;
        head_ ^= 1;
        if (!head_)
            phase_ ^= 1;
        return Result::complete;
    }
    auto quarantine() -> Result {
        quarantined_ = true;
        return Result::quarantined;
    }
    [[nodiscard]] auto remaining_commands() const -> unsigned {
        return quarantined_ || pending_ || !valid_pages() || next_cid_ > 65535 ? 0 : 65536 - next_cid_;
    }
    [[nodiscard]] auto quarantined() const -> bool {
        return quarantined_;
    }
    [[nodiscard]] auto status() const -> unsigned {
        return status_;
    }
    [[nodiscard]] auto tail() const -> unsigned {
        return tail_;
    }
    [[nodiscard]] auto head() const -> unsigned {
        return head_;
    }
};

// Boot-only writer lifecycle. Neither a copied source budget nor a caller's
// generation can reset this owner. Lifecycle/budget and transport failures are
// terminal. A rejected LBA does not submit I/O or change this lifecycle.
class NvmeRecoveryPhase final {
public:
    enum class Phase {
        cold,
        writer,
        sealing,
        readonly,
        failed
    };
    // One 64 MiB log scan costs 16384 cached reads. Reserve another 16384
    // commands for mount metadata and subsequent bounded service activity.
    static constexpr unsigned readonly_reserve = 32768, completion_commands = 21;

private:
    Phase phase_{Phase::cold};
    bool dirty_{}, flushed_{}, reserved_{}, flush_pending_{};
    unsigned writes_{}, flushes_{};

public:
    NvmeRecoveryPhase() = default;
    NvmeRecoveryPhase(const NvmeRecoveryPhase &) = delete;
    auto operator=(const NvmeRecoveryPhase &) -> NvmeRecoveryPhase & = delete;
    [[nodiscard]] auto phase() const -> Phase {
        return phase_;
    }
    [[nodiscard]] auto admitted_writes() const -> unsigned {
        return writes_;
    }
    [[nodiscard]] auto admitted_flushes() const -> unsigned {
        return flushes_;
    }
    [[nodiscard]] auto permits_readonly() const -> bool {
        return phase_ == Phase::cold || phase_ == Phase::readonly;
    }
    [[nodiscard]] auto begin() -> bool {
        if (phase_ != Phase::cold)
            return fail();
        phase_ = Phase::writer;
        return true;
    }
    [[nodiscard]] auto fail() -> bool {
        phase_ = Phase::failed;
        return false;
    }
    [[nodiscard]] auto permit_read(unsigned remaining) -> bool {
        if (phase_ != Phase::writer || flush_pending_ || !remaining || (reserved_ && remaining <= readonly_reserve))
            return fail();
        return true;
    }
    [[nodiscard]] auto permit_write(unsigned remaining) -> bool {
        if (phase_ != Phase::writer || flush_pending_ || writes_ >= 18 || remaining <= readonly_reserve + 1 ||
            (!reserved_ && remaining < readonly_reserve + completion_commands))
            return fail();
        reserved_ = true;
        ++writes_;
        dirty_ = true;
        flushed_ = false;
        return true;
    }
    [[nodiscard]] auto permit_flush(unsigned remaining) -> bool {
        if (phase_ != Phase::writer || flush_pending_ || flushes_ >= 3 || remaining <= readonly_reserve)
            return fail();
        ++flushes_;
        flush_pending_ = true;
        flushed_ = false;
        return true;
    }
    [[nodiscard]] auto flushed() -> bool {
        if (phase_ != Phase::writer || !flush_pending_)
            return fail();
        flush_pending_ = false;
        flushed_ = true;
        dirty_ = false;
        return true;
    }
    [[nodiscard]] auto seal(unsigned remaining) -> bool {
        if (phase_ != Phase::writer || dirty_ || !flushed_ || remaining < readonly_reserve)
            return fail();
        phase_ = Phase::sealing;
        return true;
    }
    [[nodiscard]] auto retired() -> bool {
        if (phase_ != Phase::sealing)
            return fail();
        phase_ = Phase::readonly;
        return true;
    }
};

// A clean mounted service has one independently consumed transaction. Arming
// follows its authenticated mount reply; it is not a recovery-to-writer
// promotion. Outstanding writes and fences remain reserved even across reads.
class NvmeMountedPhase final {
public:
    enum class Phase {
        cold,
        mounting,
        armed,
        committing,
        committed,
        failed
    };
    static constexpr unsigned write_limit = 16, flush_limit = 5;
    // A post-commit mount can scan the 64 MiB log once, with bounded metadata
    // and subsequent one-block reads. This does not renew command identifiers.
    static constexpr unsigned read_reserve = 16896;

private:
    Phase phase_{Phase::cold};
    unsigned writes_{}, flushes_{};
    bool pending_{};
    [[nodiscard]] auto outstanding() const -> unsigned {
        return write_limit - writes_ + flush_limit - flushes_;
    }
    [[nodiscard]] auto fence_writes() const -> unsigned {
        return flushes_ == 0 ? 10 : flushes_ == 1 ? 12 : flushes_ == 2 ? 14 : flushes_ == 3 ? 15 : 16;
    }

public:
    NvmeMountedPhase() = default;
    NvmeMountedPhase(const NvmeMountedPhase &) = delete;
    auto operator=(const NvmeMountedPhase &) -> NvmeMountedPhase & = delete;
    [[nodiscard]] auto phase() const -> Phase {
        return phase_;
    }
    [[nodiscard]] auto admitted_writes() const -> unsigned {
        return writes_;
    }
    [[nodiscard]] auto admitted_flushes() const -> unsigned {
        return flushes_;
    }
    [[nodiscard]] auto available() const -> bool {
        return phase_ == Phase::mounting || phase_ == Phase::armed || phase_ == Phase::committing ||
               phase_ == Phase::committed;
    }
    [[nodiscard]] auto fail() -> bool {
        phase_ = Phase::failed;
        return false;
    }
    [[nodiscard]] auto begin() -> bool {
        if (phase_ != Phase::cold)
            return fail();
        phase_ = Phase::mounting;
        return true;
    }
    [[nodiscard]] auto arm() -> bool {
        if (phase_ != Phase::mounting)
            return fail();
        phase_ = Phase::armed;
        return true;
    }
    [[nodiscard]] auto permit_read(unsigned remaining, bool submits) -> bool {
        if (!available() || pending_ || (submits && !remaining))
            return fail();
        if (phase_ == Phase::committing && remaining < read_reserve + outstanding() + (submits ? 1U : 0U))
            return fail();
        return true;
    }
    [[nodiscard]] auto permit_write(unsigned remaining) -> bool {
        if ((phase_ != Phase::armed && phase_ != Phase::committing) || pending_ || writes_ >= fence_writes() ||
            remaining < read_reserve + outstanding())
            return fail();
        // The first admitted mutation spends the boot's sole reservation before
        // submission. Range and user-copy checks precede this call.
        phase_ = Phase::committing;
        ++writes_;
        return true;
    }
    [[nodiscard]] auto permit_flush(unsigned remaining) -> bool {
        if (phase_ != Phase::committing || pending_ || flushes_ >= flush_limit || writes_ != fence_writes() ||
            remaining < read_reserve + outstanding())
            return fail();
        ++flushes_;
        pending_ = true;
        return true;
    }
    [[nodiscard]] auto flushed() -> bool {
        if (phase_ != Phase::committing || !pending_)
            return fail();
        pending_ = false;
        if (flushes_ == flush_limit)
            phase_ = Phase::committed;
        return true;
    }
};

class NvmeCommand final {
public:
    [[nodiscard]] static auto identify(bool controller) -> std::array<std::byte, 64> {
        std::array<std::byte, 64> command{};
        put(command, 0, 6, 1);
        put(command, 4, controller ? 0 : 1, 4);
        put(command, 24, 0x6000);
        put(command, 40, controller ? 1 : 0, 4);
        return command;
    }
    [[nodiscard]] static auto active_namespaces() -> std::array<std::byte, 64> {
        auto command = identify(true);
        put(command, 40, 2, 4);
        return command;
    }
    [[nodiscard]] static auto create_queue(bool submission) -> std::array<std::byte, 64> {
        std::array<std::byte, 64> command{};
        put(command, 0, submission ? 1 : 5, 1);
        put(command, 24, submission ? 0x4000 : 0x5000);
        put(command, 40, 0x10001, 4);                  // QID1, two entries.
        put(command, 44, submission ? 0x10001 : 1, 4); // Contiguous, no interrupts, CQ1.
        return command;
    }
    [[nodiscard]] static auto io(const NvmeNamespace &ns, std::uint64_t lba, bool write, unsigned count = 1)
        -> std::optional<std::array<std::byte, 64>> {
        if (!ns.contains(lba, count) || (write && count != 1))
            return std::nullopt;
        std::array<std::byte, 64> command{};
        put(command, 0, write ? 1 : 2, 1);
        put(command, 4, 1, 4);
        put(command, 24, write ? 0x7000 : 0x6000);
        put(command, 40, lba);
        put(command, 48, count - 1, 4);
        return command;
    }
    [[nodiscard]] static auto flush() -> std::array<std::byte, 64> {
        std::array<std::byte, 64> command{};
        put(command, 4, 1, 4);
        return command;
    }
};
} // namespace aurora::uefi
