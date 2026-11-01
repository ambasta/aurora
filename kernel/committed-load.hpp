#pragma once
#include <cstddef>
#include <cstdint>

namespace aurora::load {
using U64 = std::uint64_t;
enum class Action : U64 {
    open,
    reserve,
    read,
    fill,
    seal,
    discard_close,
    close,
    load,
    discard_done,
    done
};
enum class Result : U64 {
    loaded,
    missing,
    malformed,
    quota,
    unavailable
};
class Request final {
public:
    Action action;
    U64 id, size, offset, count;
    Result result;
};
static_assert(sizeof(Request) == 48);
extern "C" {
void __au_runtime_load_create(void *);
void __au_runtime_load_next(const void *, Request *);
bool __au_runtime_load_accept(void *, Action, bool, U64, U64, U64);
}
// Local, noncopyable policy storage. Neither it nor copied requests convey
// snapshot/endpoint authority. Every loan closes before its caller runs an effect.
template <class Platform> class Operation final {
    alignas(16) std::byte storage_[48]{};
    mutable bool borrowed_ = false;
    void enter() const {
        if (borrowed_)
            Platform::fail();
        borrowed_ = true;
        Platform::enter();
    }
    void leave() const {
        Platform::leave();
        borrowed_ = false;
    }

public:
    Operation() {
        enter();
        __au_runtime_load_create(storage_);
        leave();
    }
    Operation(const Operation &) = delete;
    Operation(Operation &&) = delete;
    auto operator=(const Operation &) -> Operation & = delete;
    auto operator=(Operation &&) -> Operation & = delete;
    auto next() const -> Request {
        enter();
        Request result{};
        __au_runtime_load_next(storage_, &result);
        leave();
        return result;
    }
    auto accept(Action action, bool ok, U64 status = 0, U64 value = 0, U64 count = 0) -> bool {
        enter();
        const auto result = __au_runtime_load_accept(storage_, action, ok, status, value, count);
        leave();
        return result;
    }
};
} // namespace aurora::load
