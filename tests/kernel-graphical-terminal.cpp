// Runs the production graphical terminal: the real native cell grid
// (kernel/terminal-grid.hpp) feeding the real generated Aurora painter through
// the real DisplaySession, into a guarded host framebuffer.
//
//   graphical-terminal-host W H PITCH FORMAT EVERY TOKEN...
//       Console bytes from TOKENs (x:HEX literal, r:COUNT:HEX repeated), painted
//       after every EVERY bytes (0: once at the end). Prints the store count,
//       cursor cell and an FNV-1a digest of the whole guarded buffer; equal
//       digests across schedules show the painted frame is schedule-independent.
//   graphical-terminal-host --rows W H PITCH FORMAT EVERY TOKEN...
//       The same run, also printing every non-blank grid row between bars.
//   graphical-terminal-host --cell W H POSITION GLYPH
//       One direct painter call: prints whether it painted and its stores.
//   graphical-terminal-host --foreign-console
//       A Console grant offered as the Display grant must fail (exit 77) before any store.
//   graphical-terminal-host --viewport INPUT OUTPUT
//       800x600 pitch-800 BGR (the q35 std-VGA mode): paints INPUT's Console bytes
//       and writes the 480x216 viewport at (32,32) as raw framebuffer bytes.
#include "../kernel/display-session.hpp"
#include "../kernel/console-session.hpp"
#include "../kernel/terminal-grid.hpp"
#include "../kernel/uefi/framebuffer-pixels.hpp"
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <iterator>
#include <optional>
#include <string>
#include <vector>

namespace {
using U64 = std::uint64_t;
using namespace aurora::uefi;
constexpr U64 guard = 32;
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
            bytes[guard + offset + i] = std::byte(value >> (8 * i));
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
class PaintArgument final {
public:
    const void *grant;
    U64 generation, width, height, position, glyph;
};
static_assert(sizeof(PaintArgument) == 48);
} // namespace
extern "C" auto __au_runtime_terminal_paint(const void *) -> U64;
extern "C" auto __au_runtime_display_pixel(const void *grant, U64 generation, U64 x, U64 y, U64 r, U64 g, U64 b)
    -> U64 {
    return Session::pixel(grant, generation, x, y, r, g, b);
}
namespace {
auto surface(U64 width, U64 height, U64 pitch, U64 format) -> void {
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
    bytes.assign(size + 2 * guard, std::byte{0xa5});
}
auto paint(aurora::terminal::Grid &grid) -> void {
    if (!grid.any_dirty())
        return;
    const auto argument = Session::open();
    grid.prepare();
    for (unsigned index = 0; index < aurora::terminal::Grid::cells; ++index) {
        if (!grid.dirty(index))
            continue;
        const PaintArgument record{
            argument.grant, argument.generation, argument.width, argument.height, index, grid.glyph(index)};
        const auto before = stores;
        need(__au_runtime_terminal_paint(&record) == 1);
        need(stores - before <= 94); // The supervisor's per-cell store bound.
        grid.commit(index);
    }
    need(Session::close(argument, 0) == aurora::display::Completion::rendered && !grid.any_dirty());
}
auto hex(const std::string &text) -> std::vector<std::uint8_t> {
    need(text.size() % 2 == 0);
    std::vector<std::uint8_t> result;
    for (std::size_t at = 0; at < text.size(); at += 2)
        result.push_back(static_cast<std::uint8_t>(std::stoul(text.substr(at, 2), nullptr, 16)));
    return result;
}
auto feed(aurora::terminal::Grid &grid, const std::vector<std::uint8_t> &data, U64 every) -> void {
    U64 count = 0;
    for (const auto byte : data) {
        grid.apply(byte);
        if (every && ++count % every == 0)
            paint(grid);
    }
    paint(grid);
}
auto digest() -> U64 {
    U64 value = 0xcbf29ce484222325ULL;
    for (const auto byte : bytes)
        value = (value ^ static_cast<U64>(byte)) * 0x100000001b3ULL;
    return value;
}
} // namespace
int main(int argc, char **argv) {
    need(argc >= 2);
    const std::string first = argv[1];
    if (first == "--foreign-console") {
        surface(800, 600, 800, 1);
        foreign_test = true;
        const auto console = Console::open();
        const PaintArgument record{console.grant, console.generation, 800, 600, 0, 'A'};
        static_cast<void>(__au_runtime_terminal_paint(&record));
        return 1;
    }
    if (first == "--cell") {
        need(argc == 6);
        const auto width = std::stoul(argv[2]), height = std::stoul(argv[3]);
        surface(width, height, width, 1);
        const auto argument = Session::open();
        const PaintArgument record{
            argument.grant, argument.generation, width, height, std::stoull(argv[4]), std::stoull(argv[5])};
        const auto painted = __au_runtime_terminal_paint(&record);
        need(painted <= 1 && Session::close(argument, 0) == aurora::display::Completion::rendered);
        std::cout << "painted=" << painted << " stores=" << stores << " digest=" << std::hex << digest() << '\n';
        return 0;
    }
    if (first == "--viewport") {
        need(argc == 4);
        std::ifstream input(argv[2], std::ios::binary);
        need(input.good());
        const std::vector<std::uint8_t> data{std::istreambuf_iterator<char>(input), {}};
        surface(800, 600, 800, 1);
        aurora::terminal::Grid grid;
        feed(grid, data, 0);
        std::ofstream output(argv[3], std::ios::binary);
        for (U64 y = 32; y < 32 + 216; ++y)
            output.write(reinterpret_cast<const char *>(bytes.data() + guard + (y * 800 + 32) * 4), 480 * 4);
        need(output.good());
        return 0;
    }
    const bool rows = first == "--rows";
    if (rows) {
        --argc;
        ++argv;
    }
    need(argc >= 7);
    surface(std::stoul(argv[1]), std::stoul(argv[2]), std::stoul(argv[3]), std::stoul(argv[4]));
    const auto every = std::stoull(argv[5]);
    std::vector<std::uint8_t> data;
    for (int index = 6; index < argc; ++index) {
        const std::string token = argv[index];
        if (token.starts_with("x:")) {
            const auto part = hex(token.substr(2));
            data.insert(data.end(), part.begin(), part.end());
        } else {
            need(token.starts_with("r:"));
            const auto colon = token.find(':', 2);
            need(colon != std::string::npos);
            const auto part = hex(token.substr(colon + 1));
            for (auto count = std::stoul(token.substr(2, colon - 2)); count; --count)
                data.insert(data.end(), part.begin(), part.end());
        }
    }
    aurora::terminal::Grid grid;
    feed(grid, data, every);
    std::cout << "stores=" << stores << " cursor=" << grid.cursor() << " digest=" << std::hex << digest() << '\n';
    for (unsigned row = 0; rows && row < aurora::terminal::Grid::rows; ++row) {
        std::string text;
        for (unsigned column = 0; column < aurora::terminal::Grid::columns; ++column) {
            const auto byte = grid.byte(row * aurora::terminal::Grid::columns + column);
            text += byte >= 32 && byte < 127 ? static_cast<char>(byte) : '?';
        }
        if (text.find_last_not_of(' ') != std::string::npos)
            std::cout << std::dec << row << '|' << text.substr(0, text.find_last_not_of(' ') + 1) << "|\n";
    }
}
