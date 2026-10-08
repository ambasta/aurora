#include "../kernel/display-session.hpp"
#include "../kernel/console-session.hpp"
#include <cstddef>
#include <utility>
#include <initializer_list>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <sys/wait.h>
#include <unistd.h>

namespace {
using U64 = std::uint64_t;
unsigned calls{}, stores{}, expected_calls{}, expected_stores{};
U64 identity = 0x123000, width = 7, height = 5, transport_result{};
bool quiescent = true, reenter{};
aurora::display::ServiceArgument argument{};
class Transport {
public:
    static auto identity() -> U64 {
        return ::identity;
    }
    static auto width() -> U64 {
        return ::width;
    }
    static auto height() -> U64 {
        return ::height;
    }
    static auto pixel(U64, U64, std::uint8_t, std::uint8_t, std::uint8_t) -> U64;
};
class Platform {
public:
    static auto quiet() -> bool {
        return quiescent;
    }
    [[noreturn]] static auto fail() -> void {
        std::_Exit(calls == expected_calls && stores == expected_stores ? 77 : 78);
    }
};
class ConsoleTransport final {
public:
    static auto next() -> aurora::console::Sample {
        return {};
    }
    static auto try_put(std::uint8_t) -> aurora::console::PutResult {
        return aurora::console::PutResult::success;
    }
};
using ConsoleService = aurora::console::Session<ConsoleTransport, Platform>;
using Service = aurora::display::Session<Transport, Platform>;
auto Transport::pixel(U64, U64, std::uint8_t, std::uint8_t, std::uint8_t) -> U64 {
    ++calls;
    if (reenter)
        static_cast<void>(Service::pixel(argument.grant, argument.generation, 0, 0, 1, 2, 3));
    ++stores;
    return transport_result;
}
auto need(bool value) -> void {
    if (!value)
        std::abort();
}
template <class Test> auto rejects(Test test) -> void {
    const auto child = fork();
    need(child >= 0);
    if (child == 0) {
        calls = stores = expected_calls = expected_stores = 0;
        test();
        std::_Exit(1);
    }
    int status{};
    need(waitpid(child, &status, 0) == child);
    need(WIFEXITED(status) && WEXITSTATUS(status) == 77);
}
auto pixel(U64 x = 0, U64 y = 0, U64 r = 1, U64 g = 2, U64 b = 3) -> U64 {
    return Service::pixel(argument.grant, argument.generation, x, y, r, g, b);
}
} // namespace
int main() {
    static_assert(aurora::display::next_generation(0) == 1);
    static_assert(aurora::display::next_generation(UINT64_MAX - 1) == UINT64_MAX);
    static_assert(aurora::display::next_generation(UINT64_MAX) == 0);
    argument = Service::open();
    need(argument.width == 7 && argument.height == 5);
    need(pixel() == 0 && calls == 1 && stores == 1);
    for (const auto &point : {std::pair<U64, U64>{7, 0}, {0, 5}, {UINT64_MAX, 0}, {0, UINT64_MAX}})
        need(pixel(point.first, point.second) == 1 && calls == 1 && stores == 1);
    const auto console = ConsoleService::open();
    rejects([&] {
        static_cast<void>(Service::pixel(console.grant, console.generation, 0, 0, 1, 2, 3));
    });
    rejects([&] {
        static_cast<void>(ConsoleService::put(argument.grant, argument.generation, 1));
    });
    need(ConsoleService::close(console, 0) == aurora::console::Completion::requested_exit);
    const auto old = argument;
    need(Service::close(argument, 0) == aurora::display::Completion::rendered);
    argument = Service::open();
    need(argument.generation == old.generation + 1);
    rejects([&] {
        static_cast<void>(Service::pixel(old.grant, old.generation, 0, 0, 1, 2, 3));
    });
    rejects([&] {
        static_cast<void>(Service::pixel(reinterpret_cast<const void *>(1), argument.generation, 0, 0, 1, 2, 3));
    });
    rejects([&] {
        static_cast<void>(Service::pixel(argument.grant, 0, 0, 0, 1, 2, 3));
    });
    for (U64 bad : {U64{256}, U64{0x100000001}, UINT64_MAX}) {
        rejects([&] {
            static_cast<void>(pixel(0, 0, bad, 2, 3));
        });
        rejects([&] {
            static_cast<void>(pixel(0, 0, 1, bad, 3));
        });
        rejects([&] {
            static_cast<void>(pixel(0, 0, 1, 2, bad));
        });
        rejects([&] {
            static_cast<void>(pixel(UINT64_MAX, UINT64_MAX, 1, 2, bad));
        });
    }
    rejects([&] {
        static_cast<void>(Service::open());
    });
    rejects([&] {
        quiescent = false;
        static_cast<void>(pixel());
    });
    rejects([&] {
        identity += 4096;
        static_cast<void>(pixel());
    });
    rejects([&] {
        width += 1;
        static_cast<void>(pixel());
    });
    rejects([&] {
        height += 1;
        static_cast<void>(pixel());
    });
    rejects([&] {
        const U64 console_kind = 0x415552434f4e5301ULL;
        std::memcpy(const_cast<void *>(argument.grant), &console_kind, 8);
        static_cast<void>(pixel());
    });
    rejects([&] {
        const U64 forged_console[2]{0x415552434f4e5301ULL, argument.generation};
        static_cast<void>(Service::pixel(forged_console, argument.generation, 0, 0, 1, 2, 3));
    });
    rejects([&] {
        const U64 changed = argument.generation + 1;
        std::memcpy(static_cast<std::byte *>(const_cast<void *>(argument.grant)) + 8, &changed, 8);
        static_cast<void>(pixel());
    });
    rejects([&] {
        reenter = true;
        expected_calls = 1;
        static_cast<void>(pixel());
    });
    rejects([&] {
        transport_result = 2;
        expected_calls = expected_stores = 1;
        static_cast<void>(pixel());
    });
    rejects([&] {
        static_cast<void>(Service::close(argument, 2));
    });
    rejects([&] {
        auto wrong = argument;
        ++wrong.width;
        static_cast<void>(Service::close(wrong, 0));
    });
    rejects([&] {
        auto wrong = argument;
        ++wrong.height;
        static_cast<void>(Service::close(wrong, 0));
    });
    need(Service::close(argument, 1) == aurora::display::Completion::output_failure);
    rejects([&] {
        static_cast<void>(Service::close(argument, 0));
    });
    rejects([&] {
        static_cast<void>(pixel());
    });
    std::puts("PASS: display session raw channels, coordinates, kind/generation, mapping, reentry and lifetime");
}
