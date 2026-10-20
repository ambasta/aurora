// Host-only admission tests: no real IN/OUT instruction is reachable.
#include "../kernel/source-uart.hpp"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <limits>
#include <sys/wait.h>
#include <unistd.h>
#include <utility>

namespace {
using aurora::hardware::PortArgument;
unsigned effects{}, quiet_checks{}, ownership_checks{};
unsigned last_port{};
std::uint8_t last_byte{};
bool quiescent = true, owned = true, forbid_platform_hooks = false;
std::function<void()> before_io, before_source_return;
unsigned source_calls{}, expected_source_calls{};
bool check_source_calls{};
PortArgument argument{};
aurora::console::UartTransfer copied_result{0, 0, 0, 0, 0, 1};
void need(bool value) {
    if (!value)
        std::abort();
}
class Ports {
public:
    static auto read(unsigned port) -> std::uint8_t {
        if (before_io)
            before_io();
        ++effects;
        last_port = port;
        return 0xa5;
    }
    static auto write(unsigned port, std::uint8_t byte) -> void {
        if (before_io)
            before_io();
        ++effects;
        last_port = port;
        last_byte = byte;
    }
};
class Platform {
public:
    static auto quiet() -> bool {
        ++quiet_checks;
        return quiescent;
    }
    static auto owns_uart() -> bool {
        ++ownership_checks;
        return owned;
    }
    [[noreturn]] static auto fail() -> void {
        std::_Exit(effects == 0 && (!check_source_calls || source_calls == expected_source_calls) &&
                           (!forbid_platform_hooks || (quiet_checks == 0 && ownership_checks == 0))
                       ? 77
                       : 78);
    }
};
using Service = aurora::hardware::PortRange<Platform, Ports>;
template <class Test> void rejects(Test test) {
    const auto child = fork();
    need(child >= 0);
    if (child == 0) {
        effects = 0;
        before_io = {};
        before_source_return = {};
        source_calls = 0;
        test();
        std::_Exit(1);
    }
    int status{};
    need(waitpid(child, &status, 0) == child);
    need(WIFEXITED(status) && WEXITSTATUS(status) == 77);
}
auto read(std::uint64_t offset) -> std::uint64_t {
    return Service::read8(argument.grant, argument.generation, offset);
}
auto write(std::uint64_t offset, std::uint64_t byte) -> std::uint64_t {
    return Service::write8(argument.grant, argument.generation, offset, byte);
}
} // namespace
// Deliberately malformed copied result channels exercise the production adapter.
// The separate generated-UART test executes the actual Aurora implementation.
namespace aurora::console {
static auto copied_source_return(UartTransfer *result) -> void {
    ++source_calls;
    auto hook = std::move(before_source_return);
    if (hook)
        hook();
    *result = copied_result;
}
auto uart_initialize(const UartArguments *, UartTransfer *result) -> void {
    copied_source_return(result);
}
auto uart_next(const UartArguments *, UartTransfer *result) -> void {
    copied_source_return(result);
}
auto uart_put(const UartArguments *, UartTransfer *result) -> void {
    copied_source_return(result);
}
} // namespace aurora::console
int main() {
    argument = Service::open();
    need(effects == 0 && argument.grant != nullptr && argument.generation != 0);
    for (const auto offset : {0u, 2u, 5u}) {
        effects = 0;
        need(read(offset) == 0xa5 && effects == 1 && last_port == 0x3f8 + offset);
    }
    for (const auto offset : {0u, 2u}) {
        for (const auto byte : {0u, 1u, 255u}) {
            effects = 0;
            need(write(offset, byte) == 0 && effects == 1 && last_port == 0x3f8 + offset && last_byte == byte);
        }
    }
    for (std::uint64_t offset = 0; offset < 16; ++offset) {
        if (offset != 0 && offset != 2 && offset != 5)
            rejects([=] {
                static_cast<void>(read(offset));
            });
        if (offset != 0 && offset != 2)
            rejects([=] {
                static_cast<void>(write(offset, 65));
            });
    }
    for (const auto offset : {std::uint64_t{65535}, std::uint64_t{65536}, UINT64_MAX}) {
        rejects([=] {
            static_cast<void>(read(offset));
        });
        rejects([=] {
            static_cast<void>(write(offset, 65));
        });
    }
    for (const auto byte : {std::uint64_t{256}, UINT64_MAX})
        rejects([=] {
            static_cast<void>(write(0, byte));
        });
    for (const auto pointer : {static_cast<const void *>(nullptr),
                               reinterpret_cast<const void *>(1),
                               reinterpret_cast<const void *>(UINTPTR_MAX)}) {
        rejects([=] {
            static_cast<void>(Service::read8(pointer, argument.generation, 0));
        });
        rejects([=] {
            static_cast<void>(Service::write8(pointer, argument.generation, 0, 65));
        });
        rejects([=] {
            Service::revoke({pointer, argument.generation});
        });
    }
    for (const auto generation : {std::uint64_t{0}, argument.generation + 1, UINT64_MAX}) {
        rejects([=] {
            static_cast<void>(Service::read8(argument.grant, generation, 0));
        });
        rejects([=] {
            static_cast<void>(Service::write8(argument.grant, generation, 0, 65));
        });
    }
    rejects([] {
        static_cast<void>(Service::open());
    });
    for (const bool ownership : {false, true}) {
        rejects([=] {
            if (ownership)
                owned = false;
            else
                quiescent = false;
            static_cast<void>(read(0));
        });
        rejects([=] {
            if (ownership)
                owned = false;
            else
                quiescent = false;
            static_cast<void>(write(0, 65));
        });
        rejects([=] {
            if (ownership)
                owned = false;
            else
                quiescent = false;
            Service::revoke(argument);
        });
    }
    // This corruption targets only the native admission header, never an Aurora layout.
    rejects([] {
        const std::uint64_t wrong_kind = 0;
        std::memcpy(const_cast<void *>(argument.grant), &wrong_kind, sizeof(wrong_kind));
        static_cast<void>(read(0));
    });
    rejects([] {
        const std::uint64_t wrong_generation = argument.generation + 1;
        std::memcpy(static_cast<char *>(const_cast<void *>(argument.grant)) + sizeof(std::uint64_t),
                    &wrong_generation,
                    sizeof(wrong_generation));
        static_cast<void>(write(0, 65));
    });
    rejects([] {
        std::uint64_t copied_header[2]{};
        std::memcpy(copied_header, argument.grant, sizeof(copied_header));
        static_cast<void>(Service::read8(copied_header, argument.generation, 0));
    });
    for (unsigned action = 0; action < 4; ++action) {
        for (const bool outer_write : {false, true}) {
            rejects([=] {
                before_io = [=] {
                    switch (action) {
                    case 0:
                        static_cast<void>(read(0));
                        break;
                    case 1:
                        static_cast<void>(write(0, 65));
                        break;
                    case 2:
                        Service::revoke(argument);
                        break;
                    default:
                        static_cast<void>(Service::open());
                        break;
                    }
                };
                if (outer_write)
                    static_cast<void>(write(0, 65));
                else
                    static_cast<void>(read(0));
            });
        }
    }
    const auto revoked = argument;
    Service::revoke(argument);
    rejects([] {
        static_cast<void>(read(0));
    });
    rejects([] {
        static_cast<void>(write(0, 65));
    });
    rejects([] {
        Service::revoke(argument);
    });
    argument = Service::open();
    need(argument.grant == revoked.grant && argument.generation == revoked.generation + 1);
    rejects([=] {
        static_cast<void>(Service::read8(revoked.grant, revoked.generation, 0));
    });
    rejects([=] {
        static_cast<void>(Service::write8(revoked.grant, revoked.generation, 0, 65));
    });
    rejects([=] {
        Service::revoke(revoked);
    });
    Service::revoke(argument);
    for (const bool ownership : {false, true})
        rejects([=] {
            if (ownership)
                owned = false;
            else
                quiescent = false;
            static_cast<void>(Service::open());
        });
    using Exhaustible = aurora::hardware::PortRange<Platform, Ports, 2>;
    for (std::uint64_t generation = 1; generation <= 2; ++generation) {
        const auto grant = Exhaustible::open();
        need(grant.generation == generation);
        Exhaustible::revoke(grant);
    }
    rejects([] {
        // Exhaustion must reject before platform hooks as well as before I/O.
        quiet_checks = ownership_checks = 0;
        forbid_platform_hooks = true;
        static_cast<void>(Exhaustible::open());
    });
    using Adapter = aurora::console::SourceUart<Service, Platform>;
    Adapter::initialize_input();
    rejects([] {
        check_source_calls = true;
        expected_source_calls = 0;
        Adapter::initialize_input(); // Never reset a live source carry or grant.
    });
    for (unsigned operation = 0; operation < 3; ++operation) {
        for (unsigned action = 0; action < 6; ++action) {
            rejects([=] {
                if (operation == 0)
                    Adapter::close();
                check_source_calls = true;
                expected_source_calls = 1;
                before_source_return = [=] {
                    switch (action) {
                    case 0:
                        quiescent = false;
                        break;
                    case 1:
                        owned = false;
                        break;
                    case 2:
                        static_cast<void>(Adapter::next());
                        break;
                    case 3:
                        static_cast<void>(Adapter::try_put(65));
                        break;
                    case 4:
                        Adapter::initialize_input();
                        break;
                    default:
                        Adapter::close();
                        break;
                    }
                };
                if (operation == 0)
                    Adapter::initialize_input();
                else if (operation == 1)
                    static_cast<void>(Adapter::next());
                else
                    static_cast<void>(Adapter::try_put(65));
            });
        }
    }
    for (const auto field : {&aurora::console::UartTransfer::receive_error,
                             &aurora::console::UartTransfer::present,
                             &aurora::console::UartTransfer::damaged,
                             &aurora::console::UartTransfer::success}) {
        for (const auto bad : {std::uint64_t{2}, UINT64_MAX}) {
            rejects([=] {
                copied_result.*field = bad;
                static_cast<void>(Adapter::next());
            });
            rejects([=] {
                copied_result.*field = bad;
                static_cast<void>(Adapter::try_put(65));
            });
            rejects([=] {
                Adapter::close();
                copied_result.*field = bad;
                Adapter::initialize_input();
            });
        }
    }
    for (const auto bad : {std::uint64_t{1}, std::uint64_t{192}, UINT64_MAX})
        rejects([=] {
            copied_result.trigger = bad;
            static_cast<void>(Adapter::next());
        });
    for (const auto bad : {std::uint64_t{256}, UINT64_MAX}) {
        rejects([=] {
            copied_result.value = bad;
            static_cast<void>(Adapter::try_put(65));
        });
        rejects([=] {
            copied_result.value = bad;
            copied_result.present = 1;
            static_cast<void>(Adapter::next());
        });
    }
    rejects([] {
        copied_result.value = 65;
        static_cast<void>(Adapter::next());
    });
    Adapter::close();
    rejects([] {
        static_cast<void>(Adapter::next());
    });
    rejects([] {
        static_cast<void>(Adapter::try_put(65));
    });
    std::puts("PASS PortRange: exact byte operations; direction, bounds, value, identity, lifetime, ownership, "
              "IF, overlap, exhaustion and reentry reject without target I/O; copied UART results fail closed");
}
