#include "framebuffer.hpp"
#include "framebuffer-payload.hpp"
#include "framebuffer-pixels.hpp"
#include "../display-session.hpp"
#include "../console.hpp"
#include <optional>

namespace aurora::uefi {
namespace {
using U64 = std::uint64_t;
using aurora::hardware::Serial;
std::optional<FramebufferAdmission> admission;
U64 owned_arena{}, kernel_root{}, table_count{}, stores{};
#ifdef AURORA_UEFI_FRAMEBUFFER_CAPTURE
using loader_fixture::Fixture;
// The display fixture's handoff row: the normal frame or one framebuffer fault case.
Fixture fixture{};
#endif
bool ready{};
[[noreturn]] auto fail() -> void {
    FramebufferMmio::complete();
    Serial::text("AURORA_DISPLAY_FAIL: stores=");
    Serial::number(stores);
    Serial::text("\r\n");
#ifndef AURORA_UEFI_FRAMEBUFFER_CAPTURE
    aurora::hardware::Io::write(0xf4, 0x11);
#endif
    for (;;)
        asm volatile("cli; hlt");
}
auto require(bool condition) -> void {
    if (!condition)
        fail();
}
auto root() -> U64 {
    U64 value;
    asm volatile("mov %%cr3,%0" : "=r"(value));
    return value;
}
#ifdef AURORA_UEFI_FRAMEBUFFER_CAPTURE
// Qualification-only debug handshake, never an Aurora input capability.
// The address/length are the pinned pre-exit fixture, not a faulted record.
auto capture_gate() -> void {
    Serial::text("AURORA_DISPLAY_CAPTURE_GATE: base=2147483648 bytes=1921024\r\n");
    for (unsigned remaining = 10000000; remaining != 0; --remaining) {
        const auto status = aurora::hardware::Io::read(0x3fd);
        require((status & 0x1e) == 0);
        if (status & 1) {
            // Only 'G' releases; the handoff row already selected the case.
            require(aurora::hardware::Io::read(0x3f8) == 0x47);
            Serial::text("AURORA_DISPLAY_CAPTURE_RELEASED\r\n");
            return;
        }
        asm volatile("pause" : : : "memory");
    }
    fail();
}
#endif
class Platform final {
public:
    static auto quiet() -> bool {
        U64 flags, stack;
        asm volatile("pushfq; pop %0; mov %%rsp,%1" : "=r"(flags), "=r"(stack));
        return ready && admission && !(flags & 0x200) && root() == kernel_root &&
               stack >= owned_arena + Handoff::stack_bottom && stack < owned_arena + Handoff::stack_top;
    }
    [[noreturn]] static auto fail() -> void {
        aurora::uefi::fail();
    }
};
class Transport final {
public:
    static auto identity() -> U64 {
        return kernel_root;
    }
    static auto width() -> U64 {
        return admission->geometry().width();
    }
    static auto height() -> U64 {
        return admission->geometry().height();
    }
    static auto pixel(U64 x, U64 y, std::uint8_t red, std::uint8_t green, std::uint8_t blue) -> U64 {
        require(Platform::quiet());
        const auto offset = admission->geometry().pixel_offset(x, y);
        require(offset.has_value());
        const auto page = FramebufferAdmission::virtual_address + (*offset & ~U64{4095});
        require((PageTables{kernel_root, static_cast<std::size_t>(table_count)}.entry(page) & ~0x60ULL) ==
                admission->mapping(page));
        // This output-only page has fewer than one million stores at all admitted
        // geometry bounds. Exhaustion fails before the next device write.
        require(stores < 1000000);
        const auto result = FramebufferPixels<FramebufferMmio>::pixel(*admission, x, y, red, green, blue);
        if (result == FramebufferPixelResult::success)
            ++stores;
        return static_cast<U64>(result);
    }
};
using Session = aurora::display::Session<Transport, Platform>;
} // namespace
extern "C" auto __au_runtime_display_entry(const aurora::display::ServiceArgument *) -> U64;
auto framebuffer_display_pixel(const void *grant, U64 generation, U64 x, U64 y, U64 red, U64 green, U64 blue) -> U64 {
    return Session::pixel(grant, generation, x, y, red, green, blue);
}
[[noreturn]] auto run_framebuffer(U64 arena) -> void {
    require(!ready && !admission && stores == 0);
    owned_arena = arena;
#ifdef AURORA_UEFI_FRAMEBUFFER_CAPTURE
    fixture = loader_fixture::row(
        Bytes{{reinterpret_cast<const std::byte *>(arena), Handoff::header}}.get(Handoff::fixture_offset));
    require(loader_fixture::framebuffer(fixture));
    // payload_main already validated firmware exit, active private paging and
    // the complete empty framebuffer tree before calling this profile.
    capture_gate();
#endif
#ifdef AURORA_UEFI_FRAMEBUFFER_CAPTURE
    admission = FramebufferPayload::restore_fixture(arena, fixture == Fixture::framebuffer_record);
#else
    admission = FramebufferPayload::restore_fixture(arena);
#endif
    require(admission.has_value());
    const Bytes handoff{{reinterpret_cast<const std::byte *>(arena), Handoff::header}};
    kernel_root = handoff.get(88);
    table_count = handoff.get(96);
    PageTables tables{kernel_root, static_cast<std::size_t>(table_count)};
    require(tables.install_framebuffer(*admission));
    // No inherited globals/PCID exist. Flush cached non-present translations
    // before use, without altering PAT/MTRRs or creating an identity alias.
    asm volatile("mov %0,%%cr3" : : "r"(kernel_root) : "memory");
#ifdef AURORA_UEFI_FRAMEBUFFER_CAPTURE
    if (fixture == Fixture::framebuffer_permissions) {
        // Controlled negative only: remove NX from the first framebuffer leaf.
        auto current = kernel_root;
        for (unsigned shift : {39U, 30U, 21U}) {
            current = reinterpret_cast<U64 *>(current)[(FramebufferAdmission::virtual_address >> shift) & 511] &
                      0x000ffffffffff000ULL;
            require(current >= kernel_root && current < kernel_root + table_count * 4096);
        }
        reinterpret_cast<U64 *>(current)[(FramebufferAdmission::virtual_address >> 12) & 511] =
            admission->geometry().base() + 0x1b;
    }
#endif
    require(tables.verify(arena, handoff, nullptr, &*admission));
    ready = true;
    auto argument = Session::open();
    Serial::text("AURORA_DISPLAY_SESSION_READY: width=");
    Serial::number(argument.width);
    Serial::text(" height=");
    Serial::number(argument.height);
    Serial::text("\r\n");
#ifdef AURORA_UEFI_FRAMEBUFFER_CAPTURE
    if (fixture == Fixture::framebuffer_stale)
        ++argument.generation;
#endif
    const auto result = __au_runtime_display_entry(&argument);
    require(Session::close(argument, result) == aurora::display::Completion::rendered);
    require(tables.verify(arena, handoff, nullptr, &*admission));
    FramebufferMmio::complete();
    ready = false;
    Serial::text("AURORA_DISPLAY_FRAME_COMPLETE: base=");
    Serial::number(admission->geometry().base());
    Serial::text(" bytes=");
    Serial::number(admission->geometry().mapped_bytes());
    Serial::text(" stores=");
    Serial::number(stores);
    Serial::text("\r\n");
    // Grant is closed. Leave scanout intact for QMP screenshot and byte capture;
    // the dedicated runner stops this disposable guest after both observations.
    for (;;)
        asm volatile("cli; hlt");
}
} // namespace aurora::uefi
