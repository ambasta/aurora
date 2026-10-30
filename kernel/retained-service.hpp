#pragma once
#include <cstddef>
#include <cstdint>

namespace aurora::service {
using U64 = std::uint64_t;
enum class Action : U64 {
    refused,
    reuse,
    start
};
enum class Phase : U64 {
    absent,
    starting,
    ready,
    stopping,
    retiring
};
enum class Reason : U64 {
    none,
    invalid_reply,
    consumer_rejected,
    exited,
    watchdog,
    invalid_call,
    fault,
    caller_expired,
    unavailable,
    shutdown
};
// These are private bridge entries admitted against emitted nominal/layout facts.
// A copied ordinal or report is not authority to bind a process or an endpoint.
extern "C" {
void __au_runtime_service_create(void *);
bool __au_runtime_service_open_operation(void *);
bool __au_runtime_service_close_operation(void *);
Action __au_runtime_service_admit(void *, U64, bool);
bool __au_runtime_service_mark_ready(void *, U64, bool);
bool __au_runtime_service_begin_shutdown(void *, U64);
bool __au_runtime_service_lose(void *, U64, Reason, U64);
bool __au_runtime_service_normal_exit(void *, U64);
bool __au_runtime_service_cleaned(void *, U64);
U64 __au_runtime_service_generation(const void *);
Phase __au_runtime_service_phase(const void *);
bool __au_runtime_service_disk_ready(const void *, U64);
Reason __au_runtime_service_reason(const void *);
U64 __au_runtime_service_detail(const void *);
}

// One stable complete source object owns lifecycle policy across API operations.
// Native storage guards lifetime/exclusion only, never a mirrored lifecycle phase.
// No source loan survives a loader, process, device or cleanup effect.
template <class Platform> class Root final {
    alignas(16) std::byte storage_[128]{};
    bool live_ = false;
    mutable bool borrowed_ = false;
    static void require(bool valid) {
        if (!valid)
            Platform::fail();
    }
    void enter(bool live) const {
        require(live_ == live && !borrowed_);
        borrowed_ = true;
        require(Platform::quiet());
    }
    void leave() const {
        require(borrowed_ && Platform::quiet());
        borrowed_ = false;
    }

public:
    constexpr Root() = default;
    Root(const Root &) = delete;
    Root(Root &&) = delete;
    auto operator=(const Root &) -> Root & = delete;
    auto operator=(Root &&) -> Root & = delete;
    void create() {
        enter(false);
        __au_runtime_service_create(storage_);
        live_ = true;
        leave();
    }
    auto open_operation() -> bool {
        enter(true);
        const auto result = __au_runtime_service_open_operation(storage_);
        leave();
        return result;
    }
    auto close_operation() -> bool {
        enter(true);
        const auto result = __au_runtime_service_close_operation(storage_);
        leave();
        return result;
    }
    auto admit(U64 expected, bool permit_start) -> Action {
        enter(true);
        const auto result = __au_runtime_service_admit(storage_, expected, permit_start);
        leave();
        return result;
    }
    auto mark_ready(U64 generation, bool disk) -> bool {
        enter(true);
        const auto result = __au_runtime_service_mark_ready(storage_, generation, disk);
        leave();
        return result;
    }
    auto begin_shutdown(U64 generation) -> bool {
        enter(true);
        const auto result = __au_runtime_service_begin_shutdown(storage_, generation);
        leave();
        return result;
    }
    auto lose(U64 generation, Reason reason, U64 detail) -> bool {
        enter(true);
        const auto result = __au_runtime_service_lose(storage_, generation, reason, detail);
        leave();
        return result;
    }
    auto normal_exit(U64 generation) -> bool {
        enter(true);
        const auto result = __au_runtime_service_normal_exit(storage_, generation);
        leave();
        return result;
    }
    auto cleaned(U64 generation) -> bool {
        enter(true);
        const auto result = __au_runtime_service_cleaned(storage_, generation);
        leave();
        return result;
    }
    auto generation() const -> U64 {
        enter(true);
        const auto result = __au_runtime_service_generation(storage_);
        leave();
        return result;
    }
    auto phase() const -> Phase {
        enter(true);
        const auto result = __au_runtime_service_phase(storage_);
        leave();
        return result;
    }
    auto disk_ready(U64 expected) const -> bool {
        enter(true);
        const auto result = __au_runtime_service_disk_ready(storage_, expected);
        leave();
        return result;
    }
    auto reason() const -> Reason {
        enter(true);
        const auto result = __au_runtime_service_reason(storage_);
        leave();
        return result;
    }
    auto detail() const -> U64 {
        enter(true);
        const auto result = __au_runtime_service_detail(storage_);
        leave();
        return result;
    }
};
} // namespace aurora::service
