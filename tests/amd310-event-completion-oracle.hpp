#ifndef AURORA_TEST_AMD310_EVENT_COMPLETION_ORACLE_HPP
#define AURORA_TEST_AMD310_EVENT_COMPLETION_ORACLE_HPP

#include <cstddef>
#include <cstdint>
#include <optional>
#include <span>
#include <variant>

// Test assumptions over stable copied values, never hardware-observed authority.
// AMD 48882-PUB rev 3.10: Tables 34/57/61/62, sections 2.4/2.4.11/2.5/3.4.15/3.4.16.
// See docs/iommu-models.md for the intentionally bounded profile.
namespace amd310_event_oracle {

enum class UnsupportedCause {
    input_size,
    event_code,
    event_profile,
    ring_geometry,
    model_profile
};
class Unsupported {
public:
    UnsupportedCause cause{};
};

// Every flag here is an encoded bit, not a claim that its meaning is applicable.
class RawIoPageFault {
public:
    std::uint16_t requester{};
    std::uint16_t domain{};
    std::uint64_t address{};
    bool present{};
    bool permission_denied{};
    bool write{};
    bool reserved_bit{};
    bool interrupt{};
    bool translation_request{};
    bool guest{};
};

enum class CommandErrorKind {
    illegal,
    hardware
};
class CommandError {
public:
    CommandErrorKind kind{};
    std::uint64_t raw_address{}; // Table 62 validity depends on external SR context.
    std::optional<std::uint8_t> hardware_type{};
};
using Event = std::variant<RawIoPageFault, CommandError>;
using EventResult = std::variant<RawIoPageFault, CommandError, Unsupported>;

namespace detail {
inline auto word(std::span<const std::byte> bytes, std::size_t offset) -> std::uint32_t {
    std::uint32_t value = 0;
    for (std::size_t i = 0; i != 4; ++i) {
        value |= std::uint32_t{std::to_integer<unsigned char>(bytes[offset + i])} << (i * 8);
    }
    return value;
}
inline auto matches(std::optional<bool> expected, bool raw) -> bool {
    return !expected.has_value() || *expected == raw;
}
} // namespace detail

[[nodiscard]] inline auto decode_event(std::span<const std::byte> bytes) -> EventResult {
    if (bytes.size() != 16) {
        return Unsupported{UnsupportedCause::input_size};
    }
    const auto a = detail::word(bytes, 0);
    const auto b = detail::word(bytes, 4);
    const auto address = std::uint64_t{detail::word(bytes, 8)} | (std::uint64_t{detail::word(bytes, 12)} << 32);
    const auto code = b >> 28;
    if (code == 2) {
        RawIoPageFault value;
        value.requester = static_cast<std::uint16_t>(a);
        value.domain = static_cast<std::uint16_t>(b);
        value.address = address;
        value.present = (b & (1U << 20)) != 0;
        value.permission_denied = (b & (1U << 22)) != 0;
        value.write = (b & (1U << 21)) != 0;
        value.reserved_bit = (b & (1U << 23)) != 0;
        value.interrupt = (b & (1U << 19)) != 0;
        value.translation_request = (b & (1U << 24)) != 0;
        value.guest = (b & (1U << 16)) != 0;
        if ((a & 0xffff0000U) != 0 || (b & ~0x20f0ffffU) != 0 || value.interrupt || value.translation_request ||
            value.guest) {
            return Unsupported{UnsupportedCause::event_profile};
        }
        return value;
    }
    if (code == 5 || code == 6) {
        const auto allowed = code == 5 ? 0x50000000U : 0x66000000U;
        const auto type = static_cast<std::uint8_t>((b >> 25) & 3);
        if (a != 0 || (b & ~allowed) != 0 || (address & 15) != 0 || (code == 6 && type == 0)) {
            return Unsupported{UnsupportedCause::event_profile};
        }
        return CommandError{code == 5 ? CommandErrorKind::illegal : CommandErrorKind::hardware,
                            address,
                            code == 6 ? std::optional<std::uint8_t>{type} : std::nullopt};
    }
    return Unsupported{UnsupportedCause::event_code};
}

// The caller supplies definedness from a known single-cause fixture. Raw records
// alone cannot identify causes, partial walks, invalid rights, or fault priority.
class FaultExpectation {
public:
    std::uint16_t requester{};
    std::uint16_t domain{};
    std::uint64_t address{};
    std::optional<bool> present{};
    std::optional<bool> permission_denied{};
    std::optional<bool> write{};
    std::optional<bool> reserved_bit{};
};
[[nodiscard]] inline auto matches_fault(const RawIoPageFault &raw, const FaultExpectation &expected) -> bool {
    return raw.requester == expected.requester && raw.domain == expected.domain && raw.address == expected.address &&
           !raw.interrupt && !raw.translation_request && !raw.guest && detail::matches(expected.present, raw.present) &&
           detail::matches(expected.permission_denied, raw.permission_denied) &&
           detail::matches(expected.write, raw.write) && detail::matches(expected.reserved_bit, raw.reserved_bit);
}

inline constexpr std::uint64_t event_overflow = 1;
inline constexpr std::uint64_t event_interrupt = 2;
inline constexpr std::uint64_t completion_interrupt = 4;
inline constexpr std::uint64_t event_running = 8;
inline constexpr std::uint64_t command_running = 16;

class Status {
public:
    std::uint64_t raw{};
    [[nodiscard]] auto overflow() const -> bool {
        return (raw & event_overflow) != 0;
    }
    [[nodiscard]] auto event_pending() const -> bool {
        return (raw & event_interrupt) != 0;
    }
    [[nodiscard]] auto completion_pending() const -> bool {
        return (raw & completion_interrupt) != 0;
    }
    [[nodiscard]] auto logging() const -> bool {
        return (raw & event_running) != 0;
    }
    [[nodiscard]] auto fetching() const -> bool {
        return (raw & command_running) != 0;
    }
};

class EventRing {
public:
    std::uint8_t length{}; // Architectural EventLen exponent, 8 through 15.
    std::uint32_t head{};  // Byte offsets, not entry indices or physical addresses.
    std::uint32_t tail{};
};
class Append {
public:
    EventRing ring{};
    Status status{};
    bool written{}; // Modeled effect only; no buffer bytes are read or written.
};
using AppendResult = std::variant<Append, Unsupported>;
[[nodiscard]] inline auto append_event(EventRing ring, Status status) -> AppendResult {
    if ((status.raw & ~31ULL) != 0) {
        return Unsupported{UnsupportedCause::model_profile};
    }
    if (ring.length < 8 || ring.length > 15) {
        return Unsupported{UnsupportedCause::ring_geometry};
    }
    const auto bytes = std::uint32_t{16} << ring.length;
    if (ring.head >= bytes || ring.tail >= bytes || (ring.head & 15) != 0 || (ring.tail & 15) != 0) {
        return Unsupported{UnsupportedCause::ring_geometry};
    }
    const auto next = ring.tail + 16 == bytes ? 0U : ring.tail + 16;
    if (!status.logging() || status.overflow() || next == ring.head) {
        // EventLogRun can lag overflow; retaining the copied run bit is deliberate.
        status.raw |= event_overflow;
        return Append{ring, status, false};
    }
    ring.tail = next;
    status.raw |= event_interrupt;
    return Append{ring, status, true};
}

enum class Command {
    device_table,
    pages,
    completion_wait
};
enum class Fact {
    device_cache_invalidated,
    page_cache_invalidated,
    reads_drained,
    writes_drained
};
enum class Step {
    advanced,
    blocked,
    unsupported
};
class Wait {
public:
    bool store{};
    bool interrupt{};
    std::uint64_t address{};
    std::uint64_t data{};
    // f=1 is fixed; there are no later commands or device-IOTLB/guest operations.
};
class Store {
public:
    std::uint64_t address{};
    std::uint64_t data{};
    auto operator==(const Store &) const -> bool = default;
};

// One modeled batch. Facts are caller-authored test assumptions about *all*
// matching pre-invalidation traffic, never deductions from a snapshot or event.
class Batch {
    Wait wait_{};
    Status status_{};
    unsigned fetched_{};
    bool supported_{};
    bool halted_{};
    bool device_cache_{};
    bool page_cache_{};
    bool reads_{};
    bool writes_{};
    bool completed_{};
    std::optional<Store> store_{};

public:
    explicit Batch(Wait wait, Status initial = {}) : wait_(wait), status_(initial) {
        const bool special = (wait.address >= 0xfee00000ULL && wait.address <= 0xfeefffffULL) ||
                             (wait.address >= 0xfd00000000ULL && wait.address <= 0xffffffffffULL);
        supported_ = (initial.raw & ~31ULL) == 0 &&
                     (!wait.store || ((wait.address & 7) == 0 && wait.address <= 0x000fffffffffffffULL && !special));
        status_.raw |= command_running;
    }
    [[nodiscard]] auto status() const -> Status {
        return status_;
    }
    [[nodiscard]] auto completed() const -> bool {
        return completed_;
    }
    [[nodiscard]] auto store() const -> std::optional<Store> {
        return store_;
    }
    [[nodiscard]] auto fetched() const -> unsigned {
        return fetched_;
    }

    [[nodiscard]] auto fetch(Command command) -> Step {
        if (!supported_) {
            return Step::unsupported;
        }
        if (halted_ || completed_ || fetched_ == 3) {
            return Step::blocked;
        }
        const auto expected = fetched_ == 0   ? Command::device_table
                              : fetched_ == 1 ? Command::pages
                                              : Command::completion_wait;
        if (command != expected) {
            return Step::unsupported;
        }
        ++fetched_;
        return Step::advanced;
    }
    [[nodiscard]] auto assume(Fact fact) -> Step {
        if (!supported_) {
            return Step::unsupported;
        }
        if (halted_ || completed_) {
            return Step::blocked;
        }
        switch (fact) {
        case Fact::device_cache_invalidated:
            if (fetched_ < 1 || device_cache_) {
                return Step::blocked;
            }
            device_cache_ = true;
            return Step::advanced;
        case Fact::page_cache_invalidated:
            if (fetched_ < 2 || !device_cache_ || page_cache_) {
                return Step::blocked;
            }
            page_cache_ = true;
            return Step::advanced;
        case Fact::reads_drained:
            if (!page_cache_ || reads_) {
                return Step::blocked;
            }
            reads_ = true;
            return Step::advanced;
        case Fact::writes_drained:
            if (!page_cache_ || writes_) {
                return Step::blocked;
            }
            writes_ = true;
            return Step::advanced;
        }
        return Step::unsupported;
    }
    [[nodiscard]] auto finish_wait() -> Step {
        if (!supported_) {
            return Step::unsupported;
        }
        if (halted_ || completed_ || fetched_ != 3 || !device_cache_ || !page_cache_ || !reads_ || !writes_) {
            return Step::blocked;
        }
        completed_ = true;
        if (wait_.store) {
            store_ = Store{wait_.address, wait_.data};
        }
        if (wait_.interrupt) {
            status_.raw |= completion_interrupt;
        }
        return Step::advanced;
    }
    [[nodiscard]] auto report_event(const Event &event, EventRing ring) -> AppendResult {
        if (!supported_ || completed_ || (std::holds_alternative<CommandError>(event) && fetched_ == 3)) {
            // Error after wait fetch needs a concurrent-command model, outside this profile.
            return Unsupported{UnsupportedCause::model_profile};
        }
        const auto *fault = std::get_if<RawIoPageFault>(&event);
        if (fault && (fault->interrupt || fault->translation_request || fault->guest)) {
            return Unsupported{UnsupportedCause::event_profile};
        }
        auto effect = append_event(ring, status_);
        auto *append = std::get_if<Append>(&effect);
        if (!append) {
            return effect;
        }
        if (std::holds_alternative<CommandError>(event)) {
            halted_ = true;
            append->status.raw &= ~command_running;
        }
        status_ = append->status;
        return effect;
    }
};

} // namespace amd310_event_oracle
#endif
