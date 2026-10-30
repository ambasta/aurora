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
    output_failed,
    cancelled
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
    pending,
    cancel_requested
};
enum class Finish : U64 {
    complete,
    output_failed,
    cancelled,
    service_lost,
    cancel_requested
};
enum class Cancel : U64 {
    settled,
    draining,
    service_lost
};
class alignas(16) Lease final {
public:
    const void *binding;
    U64 generation;
};
class Preparation final {
public:
    Prepared state = Prepared::refused;
    Status status = Status::unavailable;
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

// The issuer and lease have distinct private identities. The one preparation
// remains spent for the issuer epoch even after its lease has been consumed.
// Transport::Binding contains the actual command resources/effect evidence;
// no copied source observation can select another binding or revive this one.
template <class Transport, class Platform> class Session final {
    class Grant final {
    public:
        U64 generation = 0;
        bool active = false, operation = false, issued = false;
    };
    class LeaseBinding final {
    public:
        U64 generation = 0;
        bool active = false;
        typename Transport::Binding physical{};
        Preparation preparation{};
    };
    static inline Grant grant_{};
    static inline LeaseBinding lease_{};
    static inline U64 generation_ = 0;
    static auto require(bool valid) -> void {
        if (!valid)
            Platform::fail();
    }
    static auto enter_grant(const void *grant, U64 generation) -> void {
        require(grant == &grant_ && generation != 0 && generation == generation_ && grant_.generation == generation &&
                grant_.active && !grant_.operation);
        grant_.operation = true;
        require(Platform::quiet());
    }
    static auto leave() -> void {
        require(grant_.active && grant_.operation && Platform::quiet());
        grant_.operation = false;
    }
    static auto enter_lease(const void *binding, U64 generation) -> void {
        // Compare addresses before dereference. An issuer address is not a lease.
        require(binding == &lease_ && lease_.active && generation != 0 && lease_.generation == generation &&
                grant_.issued);
        enter_grant(&grant_, generation);
    }

public:
    [[nodiscard]] static auto open() -> Argument {
        require(!grant_.active && !grant_.operation && !lease_.active &&
                generation_ != std::numeric_limits<U64>::max() && Platform::quiet());
        ++generation_;
        grant_ = {generation_, true, false, false};
        return {&grant_, generation_};
    }
    static auto release(Argument argument) -> void {
        require(!lease_.active);
        enter_grant(argument.grant, argument.generation);
        leave();
        grant_.active = false;
    }
    [[nodiscard]] static auto prepare(const void *grant, U64 generation) -> Lease {
        enter_grant(grant, generation);
        require(!grant_.issued && !lease_.active);
        grant_.issued = true;
        lease_ = {};
        lease_.generation = generation;
        lease_.active = true;
        lease_.preparation = Transport::prepare(lease_.physical);
        leave();
        return {&lease_, generation};
    }
    [[nodiscard]] static auto preparation(const void *binding, U64 generation) -> Preparation {
        enter_lease(binding, generation);
        const auto result = lease_.preparation;
        leave();
        return result;
    }
    [[nodiscard]] static auto advance(const void *binding, U64 generation) -> Observation {
        enter_lease(binding, generation);
        const auto result = Transport::advance(lease_.physical);
        leave();
        return result;
    }
    [[nodiscard]] static auto output(const void *binding, U64 generation) -> U64 {
        enter_lease(binding, generation);
        const auto result = Transport::output(lease_.physical);
        leave();
        return static_cast<U64>(result);
    }
    [[nodiscard]] static auto request(const void *binding, U64 generation) -> U64 {
        enter_lease(binding, generation);
        const auto result = Transport::request(lease_.physical);
        leave();
        return static_cast<U64>(result);
    }
    [[nodiscard]] static auto cancel(const void *binding, U64 generation) -> U64 {
        enter_lease(binding, generation);
        const auto result = Transport::cancel(lease_.physical);
        leave();
        return static_cast<U64>(result);
    }
    [[nodiscard]] static auto finish(const void *binding, U64 generation, U64 disposition) -> U64 {
        enter_lease(binding, generation);
        require(disposition <= static_cast<U64>(Finish::cancel_requested));
        const auto result = Transport::finish(lease_.physical, static_cast<Finish>(disposition));
        // The consume guard spans all native cleanup, including a failed close.
        require(Transport::settled(lease_.physical));
        lease_.active = false;
        lease_.physical = {};
        leave();
        return static_cast<U64>(result);
    }
};
static_assert(sizeof(Lease) == 16 && sizeof(Preparation) == 16 && sizeof(Observation) == 24 && sizeof(Result) == 16 &&
              sizeof(Argument) == 16);
} // namespace aurora::execution
