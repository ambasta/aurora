#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>

namespace aurora::iommu_event {
inline constexpr std::uint64_t ring_bytes = 4096, record_bytes = 16, status_mask = 0x1f;

// Private bootstrap ABI. These copied words contain no source authority.
class RawSample final {
public:
    std::uint64_t result{}, word0{}, word1{}, status_low{};
};
class ServiceArgument final {
public:
    const void *grant;
    std::uint64_t generation;
};
enum class PollResult : std::uint64_t {
    empty,
    record,
    overflow,
    transport_failure
};
enum class AckResult : std::uint64_t {
    committed,
    overflow,
    transport_failure
};
enum class Completion : std::uint64_t {
    drained,
    budget_exhausted,
    loss_detected,
    unsupported_event,
    command_error,
    transport_failure,
    output_failure
};

// A fixed, separate owner, never PinLedger or allocator storage. Exposure is
// latched BEFORE the trusted fixture receives the backing for publication.
// No reset, scrub, release or reclamation operation exists, including on failure.
// Other hardware-exposed fixture allocations need their own boot-lifetime owner.
class BootLifetimeRing final {
    alignas(4096) static inline std::array<std::byte, ring_bytes> bytes_{};
    static inline bool exposed_{};
    BootLifetimeRing() = delete;

public:
    [[nodiscard]] static auto expose() -> std::byte * {
        exposed_ = true;
        return bytes_.data();
    }
    [[nodiscard]] static auto identity() -> const void * {
        return bytes_.data();
    }
    [[nodiscard]] static auto exposed() -> bool {
        return exposed_;
    }
};

// Transport supplies full-width reads, never pre-masked register values. `okay`
// includes successful mapping/read admission; `producer_quiet` means the finite
// producer-ready phase remains in force. Neither flag proves physical DMA drain.
class Snapshot final {
public:
    const void *ring{};
    std::uint64_t base{}, control{}, head{}, tail{}, status{};
    bool okay{}, producer_quiet{};
};
class RecordCopy final {
public:
    std::uint64_t word0{}, word1{};
    bool okay{};
};

[[nodiscard]] constexpr auto next_generation(std::uint64_t generation) -> std::uint64_t {
    return generation == std::numeric_limits<std::uint64_t>::max() ? 0 : generation + 1;
}

// Transport::snapshot() performs ordered register observations. copy_record()
// acquires the published 16 bytes at the validated offset. publish_head() makes
// one release-ordered head write and reports whether that attempt was certain.
// A false result may still have written. No transport method may call Aurora.
// The admitted finite producer has stopped before open(): it cannot overwrite
// an unacknowledged slot. Double snapshots alone are NOT a coherence proof and
// this adapter does not admit a concurrent producer profile.
template <class Transport, class Platform> class Session final {
    static constexpr std::uint64_t event_kind = 0x4155524556545301ULL;
    enum class State {
        unbound,
        empty,
        pending,
        ack_attempted,
        lost,
        failed
    };
    class Grant final {
    public:
        std::uint64_t kind{}, generation{};
        bool active{}, operation{};
    };
    static inline Grant grant_{};
    static inline std::uint64_t generation_{};
    static inline bool opening_{};
    // Backing and transport state outlive each revocable source grant. Closing
    // never erases a pending copy or clears a terminal loss/uncertainty state.
    static inline State state_{State::unbound};
    static inline std::uint64_t base_{}, control_{}, head_{}, tail_{};
    static inline RawSample pending_{};

    static auto require(bool valid) -> void {
        if (!valid)
            Platform::fail();
    }
    static auto validate(const void *grant, std::uint64_t generation, bool operation) -> void {
        // Never dereference an incoming pointer, even for the kind check.
        require(grant == &grant_);
        require(grant_.kind == event_kind && grant_.active && grant_.operation == operation && generation != 0 &&
                generation == generation_ && generation == grant_.generation);
        require(Platform::quiet() && BootLifetimeRing::exposed());
    }
    static auto enter(const void *grant, std::uint64_t generation) -> void {
        validate(grant, generation, false);
        require(state_ == State::empty || state_ == State::pending);
        grant_.operation = true;
    }
    static auto leave(const void *grant, std::uint64_t generation) -> void {
        validate(grant, generation, true);
        grant_.operation = false;
    }
    [[nodiscard]] static auto valid_offset(std::uint64_t offset) -> bool {
        return offset < ring_bytes && offset % record_bytes == 0;
    }
    [[nodiscard]] static auto valid_profile(const Snapshot &sample) -> bool {
        // Exactly one 4096-byte log in common 40-bit ordinary memory. The base
        // register's length field is log2(record count) = 8; all other bits deny.
        constexpr auto address_mask = (std::uint64_t{1} << 40) - ring_bytes;
        constexpr auto base_mask = address_mask | (std::uint64_t{0xf} << 56);
        return sample.okay && sample.producer_quiet && sample.ring == BootLifetimeRing::identity() &&
               (sample.base & ~base_mask) == 0 && (sample.base >> 56) == 8 && (sample.base & address_mask) != 0 &&
               (sample.control == 5 || sample.control == 0x1005) &&
               (sample.control != 5 || (sample.status & 16) == 0) && valid_offset(sample.head) &&
               valid_offset(sample.tail) && (sample.status & ~status_mask) == 0;
    }
    [[nodiscard]] static auto inspect(const Snapshot &sample, std::uint64_t expected_head) -> bool {
        if (!valid_profile(sample) || sample.base != base_ || sample.control != control_) {
            state_ = State::failed;
            return false;
        }
        // Overflow is meaningful even when EventLogRun has stopped. Unknown
        // status bits are rejected above before any masking or interpretation.
        // With command enable clear, CmdBufRun must be clear. With it set, both
        // running and stopped are admitted: code 5 can stop command processing,
        // but a sampled stopped bit alone is never a command-error diagnosis.
        if (sample.status & 1) {
            state_ = State::lost;
            return false;
        }
        if (sample.head != expected_head || sample.tail != tail_ || (sample.status & 8) == 0) {
            state_ = State::failed;
            return false;
        }
        return true;
    }
    [[nodiscard]] static auto absent(PollResult result, const Snapshot &sample) -> RawSample {
        // Unsupported full-width status is not laundered into low-bit evidence.
        const auto status = sample.okay && (sample.status & ~status_mask) == 0 ? sample.status : 0;
        return {static_cast<std::uint64_t>(result), 0, 0, status};
    }
    [[nodiscard]] static auto failure_sample(const Snapshot &sample) -> RawSample {
        return absent(state_ == State::lost ? PollResult::overflow : PollResult::transport_failure, sample);
    }
    [[nodiscard]] static auto failure_ack() -> std::uint64_t {
        return static_cast<std::uint64_t>(state_ == State::lost ? AckResult::overflow : AckResult::transport_failure);
    }

public:
    // Entry-only admission: validates exact authority without touching the ring.
    static auto preflight(const void *grant, std::uint64_t generation) -> void {
        validate(grant, generation, false);
        require(state_ == State::empty || state_ == State::pending);
    }
    // Called only after BOTH exact grants authenticate. A Console-first source
    // operation must not run against a stale ring binding admitted at open().
    static auto admit_transport(const void *grant, std::uint64_t generation) -> void {
        enter(grant, generation);
        const auto valid = inspect(Transport::snapshot(), head_);
        leave(grant, generation);
        require(valid);
    }
    [[nodiscard]] static auto open() -> ServiceArgument {
        const auto next = next_generation(generation_);
        // Reject generation exhaustion before any platform/transport hook.
        require(next != 0 && !opening_ && !grant_.active && !grant_.operation &&
                (state_ == State::unbound || state_ == State::empty || state_ == State::pending));
        opening_ = true;
        require(Platform::quiet() && BootLifetimeRing::exposed());
        const auto snapshot = Transport::snapshot();
        if (state_ == State::unbound) {
            require(valid_profile(snapshot));
            base_ = snapshot.base;
            control_ = snapshot.control;
            head_ = snapshot.head;
            tail_ = snapshot.tail;
            state_ = State::empty;
        }
        // The trusted fixture must already present a valid, running ring.
        // Failed admission retains backing and cannot reset transport state.
        require(inspect(snapshot, head_));
        generation_ = next;
        grant_ = {event_kind, generation_, true, false};
        opening_ = false;
        return {&grant_, generation_};
    }
    [[nodiscard]] static auto poll(const void *grant, std::uint64_t generation) -> RawSample {
        enter(grant, generation);
        const auto before = Transport::snapshot();
        RawSample result{};
        if (!inspect(before, head_)) {
            result = failure_sample(before);
        } else if (state_ == State::pending) {
            result = pending_;
        } else if (head_ == before.tail) {
            result = absent(PollResult::empty, before);
        } else {
            const auto copy = Transport::copy_record(head_);
            const auto after = Transport::snapshot();
            if (!inspect(after, head_)) {
                result = failure_sample(after);
            } else if (!copy.okay) {
                state_ = State::failed;
                result = failure_sample(after);
            } else {
                pending_ = {static_cast<std::uint64_t>(PollResult::record), copy.word0, copy.word1, after.status};
                state_ = State::pending;
                result = pending_;
            }
        }
        leave(grant, generation);
        return result;
    }
    [[nodiscard]] static auto acknowledge(const void *grant, std::uint64_t generation) -> std::uint64_t {
        enter(grant, generation);
        require(state_ == State::pending);
        const auto before = Transport::snapshot();
        if (!inspect(before, head_)) {
            const auto result = failure_ack();
            leave(grant, generation);
            return result;
        }
        const auto next = (head_ + record_bytes) % ring_bytes;
        // Consume retry authority before the one write, including transport
        // failures and reentrant attempts from inside the write implementation.
        state_ = State::ack_attempted;
        const auto written = Transport::publish_head(next);
        const auto after = Transport::snapshot();
        const auto verified = inspect(after, next);
        if (!written && state_ != State::lost)
            state_ = State::failed;
        std::uint64_t result;
        if (written && verified) {
            head_ = next;
            pending_ = {};
            state_ = State::empty;
            result = static_cast<std::uint64_t>(AckResult::committed);
        } else {
            result = failure_ack();
        }
        leave(grant, generation);
        return result;
    }
    [[nodiscard]] static auto close(ServiceArgument argument, std::uint64_t result) -> Completion {
        // Closing is the only legal operation in LOST/FAILED. It revokes source
        // access without transport reads/writes or a claim that backing is safe.
        validate(argument.grant, argument.generation, false);
        require(result <= static_cast<std::uint64_t>(Completion::output_failure));
        grant_.active = false;
        return static_cast<Completion>(result);
    }
};

// Packed R11 entry record for the intentional Event, Console formal order.
class IntakeArgument final {
public:
    const void *event_grant;
    std::uint64_t event_generation;
    const void *console_grant;
    std::uint64_t console_generation, poll_budget, record_budget;
};
template <class EventSession, class ConsoleSession, class Platform> class Entry final {
    static inline bool active_{};

public:
    template <class Call>
    [[nodiscard]] static auto invoke(const IntakeArgument *incoming, const IntakeArgument &trusted, Call call)
        -> Completion {
        // Compare before reading any incoming word. Both complete opaque pairs
        // and full-width budgets must pass before any Aurora/Console operation.
        if (active_ || incoming != &trusted)
            Platform::fail();
        active_ = true;
        if (trusted.poll_budget > 256 || trusted.record_budget > 255)
            Platform::fail();
        EventSession::preflight(trusted.event_grant, trusted.event_generation);
        ConsoleSession::preflight(trusted.console_grant, trusted.console_generation);
        EventSession::admit_transport(trusted.event_grant, trusted.event_generation);
        if (!Platform::quiet())
            Platform::fail();
        const auto result = call(incoming);
        if (result > static_cast<std::uint64_t>(Completion::output_failure))
            Platform::fail();
        // The invocation owns revocation, including zero-budget/error returns.
        // Closing neither acknowledges the pending record nor releases backing.
        const auto completion = EventSession::close({trusted.event_grant, trusted.event_generation}, result);
        static_cast<void>(
            ConsoleSession::close({trusted.console_grant, trusted.console_generation},
                                  result == static_cast<std::uint64_t>(Completion::output_failure) ? 1 : 0));
        active_ = false;
        return completion;
    }
};

static_assert(sizeof(RawSample) == 32 && offsetof(RawSample, result) == 0 && offsetof(RawSample, word0) == 8 &&
              offsetof(RawSample, word1) == 16 && offsetof(RawSample, status_low) == 24);
static_assert(sizeof(ServiceArgument) == 16 && offsetof(ServiceArgument, grant) == 0 &&
              offsetof(ServiceArgument, generation) == 8);
static_assert(sizeof(IntakeArgument) == 48 && offsetof(IntakeArgument, event_grant) == 0 &&
              offsetof(IntakeArgument, event_generation) == 8 && offsetof(IntakeArgument, console_grant) == 16 &&
              offsetof(IntakeArgument, console_generation) == 24 && offsetof(IntakeArgument, poll_budget) == 32 &&
              offsetof(IntakeArgument, record_budget) == 40);
} // namespace aurora::iommu_event
