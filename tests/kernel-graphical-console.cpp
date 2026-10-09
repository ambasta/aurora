// Hosted generated-consumer observer, driven by kernel-graphical-console.py.
// Hosted evidence does not establish linked-image or guest qualification.
// Real generated Aurora consumer + private assembly entry + production Sessions.
#include "../kernel/graphical-session.hpp"
#include "../kernel/console-session.hpp"
#include "../kernel/display-session.hpp"
#include "../kernel/uefi/framebuffer-pixels.hpp"
#include "../kernel/uefi/graphical-capture-policy.hpp"
#include <array>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <limits>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace {
using U64 = std::uint64_t;
using namespace aurora::uefi;
std::optional<FramebufferAdmission> admission;
U64 row_pitch{}, visible_width{}, visible_height{};
std::vector<std::byte> bytes;
std::vector<aurora::console::Sample> script;
std::filesystem::path output;
std::ofstream trace;
U64 stores{}, consumed{}, entries{}, next_calls{}, put_calls{}, pixel_calls{}, frames{};
U64 fail_after = std::numeric_limits<U64>::max();
bool quiet = true, denied = false;
auto need(bool value) -> void {
    if (!value)
        std::abort();
}
auto check_capture_policy() -> void {
    namespace policy = aurora::uefi::graphical_capture;
    using Scenario = policy::Scenario;
    for (unsigned byte = 0; byte < 256; ++byte) {
        auto expected = Scenario::invalid;
        unsigned expected_code = 0;
        std::string_view expected_name = "invalid";
        switch (byte) {
        case 'G':
            expected = Scenario::normal;
            expected_code = 1;
            expected_name = "normal";
            break;
        case 'C':
            expected = Scenario::cross_console;
            expected_code = 2;
            expected_name = "cross-console";
            break;
        case 'D':
            expected = Scenario::cross_display;
            expected_code = 3;
            expected_name = "cross-display";
            break;
        case 'c':
            expected = Scenario::stale_console;
            expected_code = 4;
            expected_name = "stale-console";
            break;
        case 'd':
            expected = Scenario::stale_display;
            expected_code = 5;
            expected_name = "stale-display";
            break;
        case 'F':
            expected = Scenario::first_pixel_error;
            expected_code = 6;
            expected_name = "first-pixel-error";
            break;
        case 'I':
            expected = Scenario::interior_pixel_error;
            expected_code = 7;
            expected_name = "interior-pixel-error";
            break;
        }
        const auto actual = policy::select(static_cast<std::uint8_t>(byte));
        need(actual == expected && static_cast<unsigned>(actual) == expected_code &&
             policy::name(actual) == expected_name);
        // Expected ordinals come from the reviewed fixture contract, never the
        // policy under test. Check every nearby count and wide boundary values.
        for (U64 successful_stores = 0; successful_stores <= 256; ++successful_stores)
            need(policy::fail_pixel(actual, successful_stores) ==
                 ((byte == 'F' && successful_stores == 0) || (byte == 'I' && successful_stores == 55)));
        for (const U64 successful_stores : {U64{999999}, U64{1000000}, std::numeric_limits<U64>::max()})
            need(!policy::fail_pixel(actual, successful_stores));
    }
}
auto word(std::ostream &stream, U64 value, unsigned count) -> void {
    for (unsigned i = 0; i < count; ++i)
        stream.put(static_cast<char>(value >> (8 * i)));
    need(stream.good());
}
auto checkpoint() -> void {
    auto name = std::to_string(frames++);
    name.insert(0, 3 - name.size(), '0');
    std::ofstream file(output / ("frame-" + name + ".bin"), std::ios::binary);
    for (U64 i = 0; i < bytes.size(); ++i) {
        bool in_view = false;
        if (i >= 32 && i < bytes.size() - 32) {
            const auto offset = i - 32, y = offset / (row_pitch * 4), x = (offset % (row_pitch * 4)) / 4;
            in_view = y >= 128 && y < 146 && x >= 32 && x < 440;
        }
        if (!in_view)
            need(bytes[i] == std::byte{0xa5});
    }
    need(visible_width >= 440 && visible_height >= 146);
    for (U64 y = 128; y < 146; ++y)
        file.write(reinterpret_cast<const char *>(bytes.data() + 32 + (y * row_pitch + 32) * 4), 408 * 4);
    need(file.good());
}
class Store final {
public:
    static auto write(U64 offset, std::uint32_t value) -> void {
        need(offset % 4 == 0 && offset + 4 <= admission->geometry().mapped_bytes());
        for (unsigned i = 0; i < 4; ++i)
            bytes[32 + offset + i] = std::byte(value >> (8 * i));
        word(trace, offset, 8);
        word(trace, value, 4);
        ++stores;
    }
};
class DisplayTransport final {
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
        if (stores == fail_after)
            return 1;
        return static_cast<U64>(FramebufferPixels<Store>::pixel(*admission, x, y, r, g, b));
    }
};
class Platform final {
public:
    static auto quiet() -> bool {
        return ::quiet;
    }
    static auto wait() -> void {
        std::abort();
    } // scripts never include clean absent observations
    [[noreturn]] static auto fail() -> void {
        bool untouched = true;
        for (auto byte : bytes)
            untouched = untouched && byte == std::byte{0xa5};
        std::_Exit(denied && untouched && entries == 0 && next_calls == 0 && put_calls == 0 && pixel_calls == 0 &&
                           stores == 0 && consumed == 0 && frames == 0
                       ? 77
                       : 78);
    }
};
class ConsoleTransport final {
public:
    static auto next() -> aurora::console::Sample {
        need(consumed < script.size());
        return script[consumed++];
    }
    static auto try_put(std::uint8_t) -> aurora::console::PutResult {
        ++put_calls;
        return aurora::console::PutResult::success;
    }
};
using Console = aurora::console::Session<ConsoleTransport, Platform>;
using Display = aurora::display::Session<DisplayTransport, Platform>;
using Entry = aurora::graphical::Entry<Console, Display, Platform>;
} // namespace
extern "C" auto __au_runtime_graphical_entry(const aurora::graphical::ServiceArgument *) -> U64;
extern "C" auto __au_runtime_console_next(const void *grant, U64 generation, aurora::console::RawSample *result)
    -> void {
    checkpoint();
    ++next_calls;
    *result = Console::next(grant, generation);
}
extern "C" auto __au_runtime_console_put(const void *grant, U64 generation, U64 byte) -> U64 {
    return Console::put(grant, generation, byte);
}
extern "C" auto __au_runtime_display_pixel(const void *grant, U64 generation, U64 x, U64 y, U64 r, U64 g, U64 b)
    -> U64 {
    ++pixel_calls;
    return Display::pixel(grant, generation, x, y, r, g, b);
}
int main(int argc, char **argv) {
    check_capture_policy();
    need(argc == 9 || argc == 10);
    const U64 sessions = argc == 10 ? std::stoull(argv[9]) : 1;
    need(sessions == 1 || sessions == 2);
    const U64 width = std::stoull(argv[1]), height = std::stoull(argv[2]), pitch = std::stoull(argv[3]);
    const U64 format = std::stoull(argv[4]);
    row_pitch = pitch;
    visible_width = width;
    visible_height = height;
    output = argv[5];
    fail_after = std::stoull(argv[7]);
    const std::string mode = argv[8];
    denied = mode != "normal";
    need(sessions == 1 || !denied);
    std::filesystem::create_directories(output);
    trace.open(output / "stores.bin", std::ios::binary);
    std::ifstream input(argv[6]);
    U64 present{}, byte{}, damage{};
    while (input >> present >> byte >> damage) {
        need(present <= 1 && byte <= 255 && damage <= 1 && (present || damage));
        need(present || byte == 0);
        script.push_back({present != 0, static_cast<std::uint8_t>(byte), damage != 0});
    }
    need(input.eof());
    const auto size = (pitch * height * 4 + 4095) & ~U64{4095};
    const auto geometry = FramebufferGeometry::parse(0xc0000000, size, width, height, pitch, format, 36);
    need(geometry.has_value());
    std::array<std::byte, 80> map{};
    put(map, 0, 1, 4);
    put(map, 8, 0x1000000);
    put(map, 24, 256);
    put(map, 40, 11, 4);
    put(map, 48, 0xc0000000);
    put(map, 64, size / 4096);
    put(map, 72, 1);
    admission = FramebufferAdmission::authorize_described(
        *geometry, map, 40, 1, 0x1000000, 36, (1U << 5) | (1U << 16), 0x0007040600070406ULL);
    need(admission.has_value());
    bytes.assign(size + 64, std::byte{0xa5});
    U64 raw{};
    for (U64 session = 0; session < sessions; ++session) {
        auto console = Console::open();
        auto display = Display::open();
        aurora::graphical::ServiceArgument record{
            console.grant, console.generation, display.grant, display.generation, width, height};
        auto copied = record;
        const auto *incoming = &record;
        if (mode == "null-record")
            incoming = nullptr;
        else if (mode == "copied-record")
            incoming = &copied;
        else if (mode == "null-console")
            record.console_grant = nullptr;
        else if (mode == "null-display")
            record.display_grant = nullptr;
        else if (mode == "forged-console")
            record.console_grant = reinterpret_cast<const void *>(1);
        else if (mode == "forged-display")
            record.display_grant = reinterpret_cast<const void *>(1);
        else if (mode == "crossed") {
            record.console_grant = display.grant;
            record.display_grant = console.grant;
        } else if (mode == "duplicate-console")
            record.display_grant = console.grant;
        else if (mode == "duplicate-display")
            record.console_grant = display.grant;
        else if (mode == "zero-console")
            record.console_generation = 0;
        else if (mode == "zero-display")
            record.display_generation = 0;
        else if (mode == "max-console")
            record.console_generation = std::numeric_limits<U64>::max();
        else if (mode == "max-display")
            record.display_generation = std::numeric_limits<U64>::max();
        else if (mode == "width")
            ++record.width;
        else if (mode == "height")
            ++record.height;
        else if (mode == "not-quiet")
            quiet = false;
        else if (mode == "stale-console" || mode == "stale-display" || mode == "stale-both") {
            if (mode != "stale-display") {
                static_cast<void>(Console::close(console, 0));
                console = Console::open();
            }
            if (mode != "stale-console") {
                static_cast<void>(Display::close(display, 0));
                display = Display::open();
            }
        } else if (mode != "normal" && mode != "geometry" && mode != "reentry")
            std::abort();
        const auto completion = Entry::invoke(incoming, record, [&](const auto *argument) -> U64 {
            if (mode == "reentry") {
                return static_cast<U64>(Entry::invoke(argument, record, [](const auto *nested) -> U64 {
                    ++entries;
                    return __au_runtime_graphical_entry(nested);
                }));
            }
            ++entries;
            return __au_runtime_graphical_entry(argument);
        });
        need(!denied);
        checkpoint();
        raw = static_cast<U64>(completion);
        // Never forward raw graphical completion into either legacy closed enum.
        const U64 legacy = raw <= 1 ? 0 : 1;
        static_cast<void>(Console::close(console, legacy));
        static_cast<void>(Display::close(display, legacy));
        need(sessions == 1 || raw == 0);
    }
    trace.close();
    need(!trace.fail());
    std::ofstream final_pixels(output / "pixels.bin", std::ios::binary);
    final_pixels.write(reinterpret_cast<const char *>(bytes.data()), static_cast<std::streamsize>(bytes.size()));
    need(final_pixels.good());
    std::ofstream report(output / "report.json");
    report << "{\"completion\":" << raw << ",\"consumed\":" << consumed << ",\"entries\":" << entries
           << ",\"next_calls\":" << next_calls << ",\"put_calls\":" << put_calls << ",\"pixel_calls\":" << pixel_calls
           << ",\"stores\":" << stores << ",\"frames\":" << frames << "}\n";
    need(report.good());
}
