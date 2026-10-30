#pragma once
#include <cstdint>
#include <limits>

namespace aurora::execution {
using U64 = std::uint64_t;
// Private native records checked against emitted compiler ABI facts. A copied
// report is an observation, never authority to select or resume a process.
enum class Status : U64 {
    exited,
    fault,
    watchdog,
    missing,
    malformed,
    quota,
    unavailable,
    output_failed
};
enum class Prepared : U64 {
    loaded,
    refused,
    service_lost
};
enum class Step : U64 {
    retired,
    output,
    request,
    parked
};
enum class Effect : U64 {
    success,
    failed
};
enum class Request : U64 {
    ready,
    cancelled,
    service_lost,
    pending
};
enum class Finish : U64 {
    complete,
    output_failed,
    cancelled,
    service_lost
};
class Preparation final {
public:
    Prepared state = Prepared::refused;
    Status status = Status::unavailable;
    U64 finish_required = 0;
};
class Observation final {
public:
    Step state = Step::parked;
    Status status = Status::unavailable;
    U64 value = 0;
};
class Result final {
public:
    Status status = Status::unavailable;
    U64 value = 0;
};
class Argument final {
public:
    const void *grant;
    U64 generation;
};

// Authentication only, not a second command state machine. Transport holds
// actual native resources; Aurora chooses command ordering and disposition.
// Like the console adapter, one exclusive synchronous loan authenticates each
// effect. Neither a report nor a source-supplied integer can create that loan.
template <class Transport, class Platform> class Session final {
    class Grant final {
    public:
        U64 generation = 0;
        bool active = false, operation = false;
    };
    static inline Grant grant_{};
    static inline U64 generation_ = 0;
    static auto require(bool valid) -> void {
        if (!valid)
            Platform::fail();
    }
    static auto validate(const void *grant, U64 generation, bool operation) -> void {
        // Compare the untrusted address before inspecting the retained grant.
        require(grant == &grant_ && generation != 0 && generation == generation_ && grant_.generation == generation &&
                grant_.active && grant_.operation == operation);
        require(Platform::quiet());
    }
    static auto enter(const void *grant, U64 generation) -> void {
        validate(grant, generation, false);
        grant_.operation = true;
    }
    static auto leave(const void *grant, U64 generation) -> void {
        validate(grant, generation, true);
        grant_.operation = false;
    }

public:
    [[nodiscard]] static auto open() -> Argument {
        require(!grant_.active && !grant_.operation && generation_ != std::numeric_limits<U64>::max() &&
                Platform::quiet());
        ++generation_;
        grant_ = {generation_, true, false};
        return {&grant_, generation_};
    }
    static auto release(Argument argument) -> void {
        enter(argument.grant, argument.generation);
        leave(argument.grant, argument.generation);
        grant_.active = false;
    }
    [[nodiscard]] static auto prepare(const void *grant, U64 generation) -> Preparation {
        enter(grant, generation);
        const auto result = Transport::prepare();
        leave(grant, generation);
        return result;
    }
    [[nodiscard]] static auto advance(const void *grant, U64 generation) -> Observation {
        enter(grant, generation);
        const auto result = Transport::advance();
        leave(grant, generation);
        return result;
    }
    [[nodiscard]] static auto output(const void *grant, U64 generation) -> U64 {
        enter(grant, generation);
        const auto result = Transport::output();
        leave(grant, generation);
        return static_cast<U64>(result);
    }
    [[nodiscard]] static auto request(const void *grant, U64 generation) -> U64 {
        enter(grant, generation);
        const auto result = Transport::request();
        leave(grant, generation);
        return static_cast<U64>(result);
    }
    [[nodiscard]] static auto finish(const void *grant, U64 generation, U64 disposition) -> U64 {
        enter(grant, generation);
        require(disposition <= static_cast<U64>(Finish::service_lost));
        const auto result = Transport::finish(static_cast<Finish>(disposition));
        leave(grant, generation);
        return static_cast<U64>(result);
    }
};
static_assert(sizeof(Preparation) == 24 && sizeof(Observation) == 24 && sizeof(Result) == 16 && sizeof(Argument) == 16);
} // namespace aurora::execution
