#pragma once
#include <cstddef>
#include <cstdint>
#include <span>
#include <limits>

namespace aurora::bootstrap {
using U64 = std::uint64_t;
enum class Effect : U64 {
    staged,
    failed
};
enum class Progress : U64 {
    pending,
    complete,
    failed
};
enum class Finish : U64 {
    publish,
    abandon
};
enum class Result : U64 {
    ready,
    unavailable
};
// Byte validity alone is not a publication receipt. The native caller must
// separately authenticate the bound service, outstanding transaction and source.
enum class Reply : U64 {
    invalid,
    ready,
    disk_unavailable
};
[[nodiscard]] inline auto inspect_reply(U64 operation, std::span<const std::byte> bytes) -> Reply {
    if (bytes.size() != 64 || (operation != 1 && operation != 2 && operation != 3 && operation != 15))
        return Reply::invalid;
    const auto status = std::to_integer<unsigned>(bytes[0]);
    if (status != 0 && !(operation == 15 && status == 2))
        return Reply::invalid;
    for (std::size_t at = 1; at < bytes.size(); ++at)
        if (bytes[at] != std::byte{0})
            return Reply::invalid;
    return status == 2 ? Reply::disk_unavailable : Reply::ready;
}
class alignas(16) Lease final {
public:
    const void *binding;
    U64 generation;
};
class Preparation final {
public:
    U64 loaded = 0, volume_bytes = 0, chunk_bytes = 0, storage_required = 0;
};
class Argument final {
public:
    const void *grant;
    U64 generation;
};
// This grant and private binding are separate from every execution issuer.
// Consuming publication or abort discharges one unpublished startup obligation.
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
    [[nodiscard]] static auto begin(const void *grant, U64 generation) -> Lease {
        enter_grant(grant, generation);
        require(!grant_.issued && !lease_.active);
        grant_.issued = true;
        lease_ = {};
        lease_.generation = generation;
        lease_.active = true;
        lease_.preparation = Transport::begin(lease_.physical);
        leave();
        return {&lease_, generation};
    }
    [[nodiscard]] static auto preparation(const void *binding, U64 generation) -> Preparation {
        enter_lease(binding, generation);
        const auto result = lease_.preparation;
        leave();
        return result;
    }
    [[nodiscard]] static auto begin_volume(const void *binding, U64 generation) -> U64 {
        enter_lease(binding, generation);
        const auto result = Transport::begin_volume(lease_.physical);
        leave();
        return static_cast<U64>(result);
    }
    [[nodiscard]] static auto copy_volume(const void *binding, U64 generation, U64 offset) -> U64 {
        enter_lease(binding, generation);
        const auto result = Transport::copy_volume(lease_.physical, offset);
        leave();
        return static_cast<U64>(result);
    }
    [[nodiscard]] static auto seal_volume(const void *binding, U64 generation) -> U64 {
        enter_lease(binding, generation);
        const auto result = Transport::seal_volume(lease_.physical);
        leave();
        return static_cast<U64>(result);
    }
    [[nodiscard]] static auto admit_storage(const void *binding, U64 generation) -> U64 {
        enter_lease(binding, generation);
        const auto result = Transport::admit_storage(lease_.physical);
        leave();
        return static_cast<U64>(result);
    }
    [[nodiscard]] static auto advance(const void *binding, U64 generation) -> U64 {
        enter_lease(binding, generation);
        const auto result = Transport::advance(lease_.physical);
        leave();
        return static_cast<U64>(result);
    }
    [[nodiscard]] static auto finish(const void *binding, U64 generation, U64 disposition) -> U64 {
        enter_lease(binding, generation);
        require(disposition <= static_cast<U64>(Finish::abandon));
        const auto result = Transport::finish(lease_.physical, static_cast<Finish>(disposition));
        // The consume guard spans all native cleanup, including a failed close.
        require(Transport::settled(lease_.physical));
        lease_.active = false;
        lease_.physical = {};
        leave();
        return static_cast<U64>(result);
    }
};
static_assert(sizeof(Lease) == 16 && alignof(Lease) == 16 && sizeof(Preparation) == 32 && sizeof(Argument) == 16);
} // namespace aurora::bootstrap
