#pragma once
#include <cstddef>
#include <cstdint>
namespace aurora::graphical {
class ServiceArgument final {
public:
    const void *console_grant;
    std::uint64_t console_generation;
    const void *display_grant;
    std::uint64_t display_generation, width, height;
};
enum class Completion : std::uint64_t {
    requested_exit,
    bounded_end,
    output_failure,
    invalid_geometry,
    state_failure
};
[[nodiscard]] constexpr auto service_completion(Completion result) -> std::uint64_t {
    return result == Completion::requested_exit || result == Completion::bounded_end ? 0 : 1;
}
template <class ConsoleSession, class DisplaySession, class Platform> class Entry final {
    static inline bool active_{};

public:
    template <class Call>
    [[nodiscard]] static auto invoke(const ServiceArgument *incoming, const ServiceArgument &trusted, Call call)
        -> Completion {
        // Compare the exact host-owned record before reading any incoming word.
        if (active_ || incoming != &trusted)
            Platform::fail();
        ConsoleSession::preflight(trusted.console_grant, trusted.console_generation);
        DisplaySession::preflight(trusted.display_grant, trusted.display_generation, trusted.width, trusted.height);
        if (trusted.width < 440 || trusted.width > 1024 || trusted.height < 146 || trusted.height > 768 ||
            !Platform::quiet())
            Platform::fail();
        active_ = true;
        const auto result = call(incoming);
        if (result > static_cast<std::uint64_t>(Completion::state_failure))
            Platform::fail();
        active_ = false;
        return static_cast<Completion>(result);
    }
};
static_assert(sizeof(ServiceArgument) == 48);
static_assert(offsetof(ServiceArgument, console_grant) == 0 && offsetof(ServiceArgument, console_generation) == 8 &&
              offsetof(ServiceArgument, display_grant) == 16 && offsetof(ServiceArgument, display_generation) == 24 &&
              offsetof(ServiceArgument, width) == 32 && offsetof(ServiceArgument, height) == 40);
} // namespace aurora::graphical
