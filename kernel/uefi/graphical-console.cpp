#include "graphical-profile.hpp"
#include "graphical-console.hpp"
#include "framebuffer-payload.hpp"
#include "framebuffer-pixels.hpp"
#include "../display-session.hpp"
#include "../graphical-session.hpp"
#include "acpi.hpp"
#include "apic-timer-io.hpp"
#include "console-context.hpp"
#include "tables.hpp"
#include "../console-session.hpp"
#include "../console-uart.hpp"

namespace aurora::uefi {
namespace {
using U64 = std::uint64_t;
using hardware::Io;
// QEMU caps backend reads at the FIFO trigger even with UART IRQs disabled.
// Polling uses fourteen-byte batches; the BIOS IRQ adapter keeps its one-byte trigger.
using Serial = console::Uart<hardware::Io, console::FifoTrigger::fourteen>;
using Timer = LocalApicTimerIo;
constexpr std::uint32_t polling_count = 1250000;
// A session may complete at most 4096 admitted timer wakes, total across all next() calls.
// Reject the following arm; this is not a wall-clock duration or an input sample.
constexpr U64 wake_limit = 4096;
U64 owned_arena{}, kernel_root{}, wait_stack{}, wakes{}, expected_wake{}, table_count{}, stores{};
unsigned active_operation{};
// Consumer effects only; diagnostic UART writes below are deliberately excluded.
U64 consumer_entries{}, sample_calls{}, output_attempts{}, completed_samples{};
std::optional<FramebufferAdmission> graphics;
[[nodiscard]] auto timer_mapping() -> bool;
bool ready{}, waiting{};
std::optional<LocalApicAdmission> admission;
extern const std::byte wait_begin asm("uefi_console_poll_begin");
extern const std::byte wait_end asm("uefi_console_poll_end");

[[nodiscard]] auto root() -> U64 {
    U64 value;
    asm volatile("mov %%cr3, %0" : "=r"(value));
    return value;
}
[[nodiscard]] auto read_msr(std::uint32_t index) -> U64 {
    std::uint32_t low, high;
    asm volatile("rdmsr" : "=a"(low), "=d"(high) : "c"(index));
    return (U64{high} << 32) | low;
}
[[nodiscard]] auto view(U64 address, std::size_t count) -> std::span<std::byte> {
    return {reinterpret_cast<std::byte*>(address), count};
}
[[noreturn]] auto fail(std::string_view reason) -> void {
    asm volatile("cli" : : : "memory");
    ready = false;
    // Never touch MMIO through a drifted or unauthenticated mapping, including cleanup.
    if (timer_mapping()) static_cast<void>(Timer::stop());
    FramebufferMmio::complete();
    Serial::text("AURORA_GRAPHICAL_CONSOLE_FAIL: "); Serial::text(reason);
    Serial::text(" entries="); Serial::number(consumer_entries);
    Serial::text(" samples="); Serial::number(sample_calls);
    Serial::text(" output_attempts="); Serial::number(output_attempts);
    Serial::text(" stores="); Serial::number(stores); Serial::text("\r\n");
#ifndef AURORA_UEFI_GRAPHICAL_CAPTURE
    Io::write(0xf4, 0x11);
#endif
    for (;;) { asm volatile("cli; hlt"); }
}
auto require(bool okay, std::string_view reason) -> void {
    if (!okay) { fail(reason); }
}
[[nodiscard]] auto timer_mapping() -> bool {
    if (!admission || !owned_arena || root() != kernel_root) return false;
    const PageTables tables{kernel_root, static_cast<std::size_t>(table_count)};
    return admission->owned_arena() == owned_arena && kernel_root == owned_arena + Handoff::tables_offset &&
        table_count > 0 && table_count <= Handoff::table_pages &&
        (tables.entry(LocalApicAdmission::virtual_address) & ~0x60ULL) ==
            admission->mapping(LocalApicAdmission::virtual_address);
}
[[nodiscard]] auto quiet() -> bool {
    U64 stack;
    asm volatile("mov %%rsp,%0" : "=r"(stack));
    // Observational only. In particular, this must never normalize timer drift.
    return ready && !waiting && Timer::irq_off() && stack >= owned_arena + Handoff::stack_bottom &&
        stack < owned_arena + Handoff::stack_top && timer_mapping() &&
        Timer::read(0x320) == (0x10000 | Timer::vector) && Timer::read(0x380) == 0 &&
        Timer::read(0x390) == 0 && Timer::quiet(0x100, false) && Timer::quiet(0x200, false) &&
        (Io::read(0x3fb) & 0x80) == 0 && Io::read(0x3f9) == 0;
}

__attribute__((noinline)) auto wait_for_sample() -> void {
    require(quiet() && active_operation == 1, "poll boundary");
    if (wakes >= wake_limit) fail("NATIVE_IDLE_WAKE_DEADLINE: limit=4096");
    expected_wake = wakes + 1;
    waiting = true;
    require(Timer::arm(polling_count), "poll one-shot arm");
    asm volatile("mov %%rsp, %0" : "=m"(wait_stack) : : "memory");
    require(wait_stack % 8 == 0 && wait_stack <= owned_arena + Handoff::stack_top
        && ConsoleWakeContext::frame_valid((wait_stack & ~U64{15}) - ConsoleWakeContext::byte_count, owned_arena),
        "poll stack ownership");
    asm volatile(".global uefi_console_poll_begin\nuefi_console_poll_begin:\n"
                 "sti\nhlt\ncli\n.global uefi_console_poll_end\nuefi_console_poll_end:" : : : "memory");
    require(timer_mapping() && Timer::stop(), "poll explicit stop");
    waiting = false;
    wait_stack = 0;
    require(wakes == expected_wake && wakes <= wake_limit && quiet(), "poll completion");
}

#ifdef AURORA_UEFI_GRAPHICAL_CAPTURE
// Qualification-only baseline handshake. This byte never enters Console:
// it is consumed here before initialize_input resets the UART input FIFO.
// No framebuffer write or service grant exists yet.
auto capture_gate() -> void {
    Serial::text("AURORA_GRAPHICAL_CAPTURE_GATE: base=");
    Serial::number(graphics->geometry().base());
    Serial::text(" bytes="); Serial::number(graphics->geometry().mapped_bytes());
    Serial::text("\r\n");
    for (unsigned remaining = 10000000; remaining != 0; --remaining) {
        const auto status = Io::read(0x3fd);
        require((status & 0x1e) == 0, "capture UART status");
        if (status & 1) {
            require(Io::read(0x3f8) == 0x47, "capture release byte");
            Serial::text("AURORA_GRAPHICAL_CAPTURE_RELEASED\r\n");
            return;
        }
        asm volatile("pause" : : : "memory");
    }
    fail("capture release deadline");
}
#endif

class ServiceTransport final {
public:
    static auto next() -> console::Sample {
        require(sample_calls != UINT64_MAX, "sample counter overflow");
        ++sample_calls;
        return Serial::next();
    }
    static auto try_put(std::uint8_t byte) -> console::PutResult {
        require(output_attempts != UINT64_MAX, "output counter overflow");
        ++output_attempts;
        return Serial::try_put(byte);
    }
};
class ServicePlatform final {
public:
    static auto quiet() -> bool { return aurora::uefi::quiet(); }
    static auto wait() -> void { wait_for_sample(); }
    [[noreturn]] static auto fail() -> void { aurora::uefi::fail("paired service authority"); }
};
using Service = console::Session<ServiceTransport, ServicePlatform>;
class DisplayTransport final {
public:
    static auto identity() -> U64 { return kernel_root; }
    static auto width() -> U64 { return graphics->geometry().width(); }
    static auto height() -> U64 { return graphics->geometry().height(); }
    static auto pixel(U64 x, U64 y, std::uint8_t red, std::uint8_t green, std::uint8_t blue) -> U64 {
        require(quiet() && active_operation == 2, "display boundary");
        const auto offset = graphics->geometry().pixel_offset(x, y);
        require(offset.has_value(), "pixel coordinates");
        const auto page = FramebufferAdmission::virtual_address + (*offset & ~U64{4095});
        require((PageTables{kernel_root, static_cast<std::size_t>(table_count)}.entry(page) & ~0x60ULL)
            == graphics->mapping(page), "pixel mapping");
        require(stores < 1000000, "pixel lifetime budget");
        const auto result = FramebufferPixels<FramebufferMmio>::pixel(*graphics, x, y, red, green, blue);
        if (result == FramebufferPixelResult::success) ++stores;
        return static_cast<U64>(result);
    }
};
using Display = display::Session<DisplayTransport, ServicePlatform>;
using Entry = graphical::Entry<Service, Display, ServicePlatform>;

auto establish_timer(const Bytes& handoff) -> void {
    require(Timer::irq_off() && root() == kernel_root && discovered_topology().has_value(), "timer discovery");
    std::uint32_t a, b, c, d;
    asm volatile("cpuid" : "=a"(a), "=b"(b), "=c"(c), "=d"(d) : "a"(1), "c"(0));
    const auto leaf_ebx = b, leaf_edx = d;
    constexpr auto features = (1U << 5) | (1U << 9) | (1U << 16);
    require((leaf_edx & features) == features, "timer features");
    asm volatile("cpuid" : "=a"(a), "=b"(b), "=c"(c), "=d"(d) : "a"(0x80000008U), "c"(0));
    const auto admitted = LocalApicAdmission::authorize(*discovered_topology(),
        view(owned_arena + Handoff::map_offset, handoff.get(32)), handoff.get(40),
        static_cast<std::uint32_t>(handoff.get(48, 4)), owned_arena, a & 255, leaf_edx, leaf_ebx,
        read_msr(0x1b), read_msr(0x277));
    require(admitted.has_value(), "timer aperture admission");
    admission.emplace(*admitted);
    PageTables tables{kernel_root, static_cast<std::size_t>(handoff.get(96))};
    const auto slot = tables.interrupt_slot();
    require(slot && *slot == 0, "empty timer aperture");
    *slot = LocalApicAdmission::physical_address | LocalApicAdmission::leaf_flags;
    asm volatile("invlpg (%0)" : : "r"(LocalApicAdmission::virtual_address) : "memory");
    require(tables.install_framebuffer(*graphics), "graphics leaf installation");
    asm volatile("mov %0,%%cr3" : : "r"(kernel_root) : "memory");
    require(tables.verify_graphical(owned_arena, handoff, &*admission, &*graphics), "private paired mapping");
    require(admission->matches_registers(Timer::read(0x20), Timer::read(0x30)), "timer hardware identity");
    require(Timer::initialize(Timer::read(0x30)), "timer initial quiescence");
    require(Timer::stop(), "explicit initial timer stop");
}
} // namespace

auto service_entry(const graphical::ServiceArgument *) -> U64 asm("__au_runtime_graphical_entry")
    __attribute__((visibility("hidden")));

auto service_next(const void *, U64, console::RawSample *) -> void asm("__au_runtime_console_next")
    __attribute__((visibility("hidden")));
auto service_next(const void *grant, U64 generation, console::RawSample *output) -> void {
    require(active_operation == 0 && quiet(), "console next exclusion");
    Service::preflight(grant, generation);
#ifdef AURORA_UEFI_GRAPHICAL_CAPTURE
    // At most 96 markers. Prior synchronous Aurora painting has returned;
    // complete those stores before announcing a pre-sampling observation point.
    if (completed_samples < 96) {
        FramebufferMmio::complete();
        Serial::text("AURORA_GRAPHICAL_PRE_SAMPLE: completed=");
        Serial::number(completed_samples);
        Serial::text(" stores="); Serial::number(stores); Serial::text("\r\n");
    }
#endif
    active_operation = 1;
    *output = Service::next(grant, generation);
    require(completed_samples != UINT64_MAX, "completed sample counter overflow");
    ++completed_samples;
    active_operation = 0;
}
auto service_put(const void *, U64, U64) -> U64 asm("__au_runtime_console_put") __attribute__((visibility("hidden")));
auto service_put(const void *grant, U64 generation, U64 byte) -> U64 {
    require(active_operation == 0 && quiet(), "console put exclusion");
    active_operation = 1;
    const auto result = Service::put(grant, generation, byte);
    active_operation = 0;
    return result;
}

auto display_pixel(const void *, U64, U64, U64, U64, U64, U64) -> U64
    asm("__au_runtime_display_pixel") __attribute__((visibility("hidden")));
auto display_pixel(const void *grant, U64 generation, U64 x, U64 y, U64 red, U64 green, U64 blue) -> U64 {
    require(active_operation == 0 && quiet(), "display exclusion");
    active_operation = 2;
    const auto result = Display::pixel(grant, generation, x, y, red, green, blue);
    active_operation = 0;
    return result;
}

auto interrupt_entry() -> void asm("uefi_console_interrupt") __attribute__((visibility("hidden")));
auto interrupt_dispatch(U64) -> void asm("uefi_console_interrupt_dispatch") __attribute__((visibility("hidden")));
auto interrupt_dispatch(U64 frame) -> void {
    require(ready && admission && waiting && active_operation == 1 && timer_mapping() && Timer::irq_off()
        && wakes < expected_wake && expected_wake - wakes == 1
        && ConsoleWakeContext::frame_valid(frame, owned_arena), "poll interrupt origin");
    const Bytes captured{view(frame, ConsoleWakeContext::byte_count)};
    std::array<U64, ConsoleWakeContext::word_count> words{};
    for (std::size_t index = 0; index < words.size(); ++index) { words[index] = captured.get(index * 8); }
    require(ConsoleWakeContext::valid(words, frame, owned_arena,
        reinterpret_cast<U64>(&wait_begin), reinterpret_cast<U64>(&wait_end), wait_stack), "poll frame authority");
    require(Timer::acknowledge(), "poll ISR authority");
    ++wakes;
}

[[noreturn]] auto graphical_console_fault() -> void { fail("synchronous payload fault"); }

[[noreturn]] auto run_graphical_console(U64 arena, const Bytes& handoff) -> void {
    // No runtime/user image path is compiled in this profile. The loader has
    // completed its normal private-memory/ACPI/language tests before this call.
    require(!ready && !waiting && !admission && !graphics && stores == 0 && wakes == 0 &&
        handoff.get(8, 4) == 6 && handoff.get(120) == arena + Handoff::framebuffer_record_offset
        && RuntimeLayout::valid(arena) && root() == handoff.get(88) && Timer::irq_off(), "entry authority");
    owned_arena = arena;
    kernel_root = handoff.get(88);
    table_count = handoff.get(96);
    U64 stack, flags, cr0, cr4;
    asm volatile("mov %%rsp, %0; pushfq; pop %1; mov %%cr0, %2; mov %%cr4, %3"
        : "=r"(stack), "=r"(flags), "=r"(cr0), "=r"(cr4));
    require(stack % 8 == 0 && stack >= arena + Handoff::stack_bottom + 4096 + 176
        && stack <= arena + Handoff::stack_top && (flags & 0x202) == 2 && (flags & ~U64{0x10ad7}) == 0,
        "entry stack/flags");
    require((cr4 & ((1ULL << 7) | (1ULL << 12) | (1ULL << 16) | (1ULL << 17) | (1ULL << 18)
        | (1ULL << 20))) == 0, "integer paging profile");
    require((cr0 & (1ULL << 16)) != 0, "write protection");
    cr0 |= 8;
    asm volatile("mov %0, %%cr0" : : "r"(cr0) : "memory");
    require(PageTables{kernel_root, static_cast<std::size_t>(handoff.get(96))}.verify(arena, handoff),
        "entry mapping tree");
    std::array<std::byte, 10> idtr{};
    asm volatile("sidt %0" : "=m"(idtr) : : "memory");
    require(Bytes{idtr}.get(0, 2) == 4095 && Bytes{idtr}.get(2) == arena + Handoff::idt_offset, "owned IDT");
    const auto target = reinterpret_cast<U64>(&interrupt_entry);
    const auto begin = reinterpret_cast<U64>(&wait_begin), end = reinterpret_cast<U64>(&wait_end);
    require(target >= arena + Handoff::payload_offset && target < arena + Handoff::payload_offset + handoff.get(64)
        && begin >= arena + Handoff::payload_offset && end > begin && end - begin == 3
        && end < arena + Handoff::payload_offset + handoff.get(64), "interrupt RX interval");
    auto gate = view(arena + Handoff::idt_offset + Timer::vector * 16, 16);
    put(gate, 0, target, 2); put(gate, 2, 8, 2); put(gate, 4, 0, 1); put(gate, 5, 0x8e, 1);
    put(gate, 6, target >> 16, 2); put(gate, 8, target >> 32, 4); put(gate, 12, 0, 4);
    graphics = FramebufferPayload::restore_graphical_fixture(arena);
    require(graphics.has_value(), "graphics restoration");
    require(graphics->geometry().width() >= 440 && graphics->geometry().height() >= 146, "viewport geometry");
#ifdef AURORA_UEFI_GRAPHICAL_CAPTURE
    capture_gate();
#endif
    establish_timer(handoff);
    require((Io::read(0x3fb) & 0x80) == 0, "UART register bank");
    Io::write(0x3f9, 0);
    require(Io::read(0x3f9) == 0, "UART interrupts disabled");
    Serial::initialize_input();
    ready = true;
    require(quiet() && active_operation == 0, "paired ready boundary");
    // Neither service is opened until both mappings and common quiet state pass.
    const auto console_argument = Service::open();
    const auto display_argument = Display::open();
    const graphical::ServiceArgument argument{console_argument.grant, console_argument.generation,
        display_argument.grant, display_argument.generation, display_argument.width, display_argument.height};
    const auto completion = Entry::invoke(&argument, argument, [](const graphical::ServiceArgument *record) {
        require(consumer_entries == 0, "single consumer entry");
        ++consumer_entries;
        return service_entry(record);
    });
    require(active_operation == 0 && quiet() &&
        PageTables{kernel_root, static_cast<std::size_t>(table_count)}.verify_graphical(
            arena, handoff, &*admission, &*graphics), "paired return boundary");
    const auto mapped = graphical::service_completion(completion);
    static_cast<void>(Service::close(console_argument, mapped));
    static_cast<void>(Display::close(display_argument, mapped));
    require(quiet() && PageTables{kernel_root, static_cast<std::size_t>(table_count)}.verify_graphical(
        arena, handoff, &*admission, &*graphics), "paired final quiescence");
    FramebufferMmio::complete();
    ready = false;
    // Bootstrap diagnostics are distinct from consumer Console output.
    Serial::text("AURORA_GRAPHICAL_CONSOLE_COMPLETE: completion=");
    Serial::number(static_cast<U64>(completion));
    Serial::text(" wakes="); Serial::number(wakes);
    Serial::text(" stores="); Serial::number(stores); Serial::text("\r\n");
#ifndef AURORA_UEFI_GRAPHICAL_CAPTURE
    Io::write(0xf4, mapped == 0 ? 0x10 : 0x11);
#endif
    for (;;) { asm volatile("cli; hlt"); }
}
}
