#include "../kernel/console-session.hpp"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <sys/wait.h>
#include <unistd.h>

namespace {
using namespace aurora::console;
unsigned effects{}, expected_effects{}, waits{};
bool quiescent = true, reenter{}, release_during_operation{};
Sample sample{};
ServiceArgument argument{};
class Ports {
public:
    static auto next() -> Sample {
        ++effects;
        return sample;
    }
    static auto try_put(std::uint8_t) -> PutResult {
        ++effects;
        return PutResult::success;
    }
};
class Platform {
public:
    static auto quiet() -> bool {
        return quiescent;
    }
    static auto wait() -> void;
    [[noreturn]] static auto fail() -> void {
        std::_Exit(effects == expected_effects ? 77 : 78);
    }
};
using Service = Session<Ports, Platform>;
auto Platform::wait() -> void {
    ++waits;
    if (reenter) {
        static_cast<void>(Service::put(argument.grant, argument.generation, 65));
    }
    if (release_during_operation) {
        Service::release(argument);
    }
    sample = {false, 0, true};
}
void need(bool value) {
    if (!value)
        std::abort();
}
template <class Test> void rejects(Test test) {
    const auto child = fork();
    need(child >= 0);
    if (child == 0) {
        effects = expected_effects = 0;
        test();
        std::_Exit(1);
    }
    int status{};
    need(waitpid(child, &status, 0) == child);
    need(WIFEXITED(status) && WEXITSTATUS(status) == 77);
}
} // namespace
int main() {
    using namespace aurora::console;
    argument = Service::open();
    sample = {};
    const auto empty = Service::poll(argument.grant, argument.generation);
    need(empty.byte_present == 0 && empty.byte == 0 && empty.damaged == 0 && waits == 0 && effects == 1);
    sample = {true, 65, true};
    const auto first = Service::next(argument.grant, argument.generation);
    need(first.byte_present == 1 && first.byte == 65 && first.damaged == 1);
    sample = {};
    const auto damage = Service::next(argument.grant, argument.generation);
    need(damage.byte_present == 0 && damage.byte == 0 && damage.damaged == 1 && waits == 1);
    need(Service::put(argument.grant, argument.generation, 255) == 0);
    const auto old = argument;
    need(Service::close(argument, 0) == Completion::requested_exit);
    argument = Service::open();
    need(argument.grant == old.grant && argument.generation == old.generation + 1);
    rejects([&] {
        static_cast<void>(Service::poll(old.grant, old.generation));
    });
    rejects([&] {
        static_cast<void>(Service::next(old.grant, old.generation));
    });
    rejects([&] {
        static_cast<void>(Service::next(reinterpret_cast<const void *>(1), argument.generation));
    });
    rejects([&] {
        static_cast<void>(Service::put(argument.grant, 0, 1));
    });
    rejects([&] {
        static_cast<void>(Service::put(argument.grant, argument.generation, 256));
    });
    rejects([&] {
        static_cast<void>(Service::open());
    });
    rejects([&] {
        quiescent = false;
        static_cast<void>(Service::put(argument.grant, argument.generation, 1));
    });
    rejects([&] {
        std::uint64_t wrong = 0;
        std::memcpy(const_cast<void *>(argument.grant), &wrong, sizeof(wrong));
        static_cast<void>(Service::put(argument.grant, argument.generation, 1));
    });
    rejects([&] {
        std::uint64_t wrong = argument.generation + 1;
        std::memcpy(static_cast<char *>(const_cast<void *>(argument.grant)) + 8, &wrong, sizeof(wrong));
        static_cast<void>(Service::put(argument.grant, argument.generation, 1));
    });
    rejects([&] {
        sample = {};
        reenter = true;
        expected_effects = 1;
        static_cast<void>(Service::next(argument.grant, argument.generation));
    });
    rejects([&] {
        static_cast<void>(Service::close(argument, 2));
    });
    rejects([&] {
        sample = {};
        release_during_operation = true;
        expected_effects = 1;
        static_cast<void>(Service::next(argument.grant, argument.generation));
    });
    need(Service::close(argument, 1) == Completion::output_failure);
    rejects([&] {
        static_cast<void>(Service::close(argument, 0));
    });
    rejects([&] {
        static_cast<void>(Service::put(argument.grant, argument.generation, 1));
    });
    argument = Service::open();
    const auto released = argument;
    Service::release(argument);
    rejects([&] {
        Service::release(released);
    });
    rejects([&] {
        Service::preflight(released.grant, released.generation);
    });
    rejects([&] {
        static_cast<void>(Service::next(released.grant, released.generation));
    });
    rejects([&] {
        static_cast<void>(Service::put(released.grant, released.generation, 65));
    });
    argument = Service::open();
    need(argument.grant == released.grant && argument.generation == released.generation + 1);
    rejects([&] {
        Service::release(released);
    });
    Service::release(argument);
    std::puts("PASS console session grant: canonical reports, generations, kind, release, active lifetime, "
              "reentry and quiescence");
}
