// Runs the real generated Aurora status page once for one geometry and prints its
// store count and an FNV-1a digest of the complete guarded framebuffer, compared
// with tests/kernel-display-renderer.golden. A foreign Console grant must be denied
// (exit 77) before any store.
#include "../kernel/display-session.hpp"
#include "../kernel/console-session.hpp"
#include "../kernel/uefi/framebuffer-pixels.hpp"
#include <array>
#include <cstdlib>
#include <iostream>
#include <optional>
#include <string>
#include <vector>

namespace {
using U64 = std::uint64_t;
using namespace aurora::uefi;
std::optional<FramebufferAdmission> admission;
std::vector<std::byte> bytes;
U64 stores{};
bool foreign_test{};
auto need(bool condition) -> void {
    if (!condition)
        std::abort();
}
class Store final {
public:
    static auto write(U64 offset, std::uint32_t value) -> void {
        need(offset % 4 == 0 && offset + 4 <= admission->geometry().mapped_bytes());
        for (unsigned i = 0; i < 4; ++i)
            bytes[32 + offset + i] = std::byte(value >> (8 * i));
        ++stores;
    }
};
class Transport final {
public:
    static auto identity() -> U64 {
        return 0x1000000;
    }
    static auto width() -> U64 {
        return admission->geometry().width();
    }
    static auto height() -> U64 {
        return admission->geometry().height();
    }
    static auto pixel(U64 x, U64 y, std::uint8_t r, std::uint8_t g, std::uint8_t b) -> U64 {
        return static_cast<U64>(FramebufferPixels<Store>::pixel(*admission, x, y, r, g, b));
    }
};
class Platform final {
public:
    static auto quiet() -> bool {
        return true;
    }
    [[noreturn]] static auto fail() -> void {
        std::_Exit(foreign_test && stores == 0 ? 77 : 78);
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
using Session = aurora::display::Session<Transport, Platform>;
using Console = aurora::console::Session<ConsoleTransport, Platform>;
} // namespace
extern "C" auto __au_runtime_display_entry(const aurora::display::ServiceArgument *) -> U64;
extern "C" auto __au_runtime_display_pixel(const void *grant, U64 generation, U64 x, U64 y, U64 r, U64 g, U64 b)
    -> U64 {
    return Session::pixel(grant, generation, x, y, r, g, b);
}
int main(int argc, char **argv) {
    need(argc == 5 || argc == 6);
    const auto width = std::stoul(argv[1]), height = std::stoul(argv[2]), pitch = std::stoul(argv[3]);
    const auto format = std::stoul(argv[4]);
    foreign_test = argc == 6;
    need(!foreign_test || std::string(argv[5]) == "foreign-console");
    const auto size = (pitch * height * 4 + 4095) & ~U64{4095};
    const auto geometry = FramebufferGeometry::parse(0xc0000000, size, width, height, pitch, format, 36);
    need(geometry.has_value());
    std::array<std::byte, 80> map{};
    put(map, 0, 1, 4);
    put(map, 8, 0x1000000);
    put(map, 24, Handoff::arena_bytes / 4096);
    put(map, 40, 11, 4);
    put(map, 48, 0xc0000000);
    put(map, 64, size / 4096);
    put(map, 72, 1);
    admission = FramebufferAdmission::authorize_described(
        *geometry, map, 40, 1, 0x1000000, 36, (1U << 5) | (1U << 16), 0x0007040600070406ULL);
    need(admission.has_value());
    bytes.assign(size + 64, std::byte{0xa5});
    auto argument = Session::open();
    if (foreign_test) {
        const auto console = Console::open();
        argument.grant = console.grant;
        argument.generation = console.generation;
    }
    const auto completion = __au_runtime_display_entry(&argument);
    need(Session::close(argument, completion) == aurora::display::Completion::rendered);
    need(!foreign_test);
    U64 digest = 0xcbf29ce484222325ULL;
    for (const auto byte : bytes)
        digest = (digest ^ static_cast<U64>(byte)) * 0x100000001b3ULL;
    std::cout << "stores=" << stores << " bytes=" << bytes.size() << " digest=" << std::hex << digest << '\n';
}
