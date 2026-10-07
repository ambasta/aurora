#include "console.hpp"
#include "acpi.hpp"
#include "apic-timer-io.hpp"
#include "console-context.hpp"
#include "tables.hpp"
#include "../console-presentation.hpp"
#include "../console-uart.hpp"

namespace aurora::uefi {
namespace {
using U64 = std::uint64_t;
using hardware::Io;
// QEMU caps backend reads at the FIFO trigger even with UART IRQs disabled.
// Polling uses fourteen-byte batches; the BIOS IRQ adapter keeps its one-byte trigger.
using Serial = console::Uart<hardware::Io, console::FifoTrigger::fourteen>;
using Timer = LocalApicTimerIo;
using Display = console::Presentation<Serial>;
constexpr auto platform = console::Platform::uefi;
constexpr std::uint32_t polling_count = 1250000;
U64 owned_arena{}, kernel_root{}, wait_stack{}, wakes{}, expected_wake{};
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
    Serial::text("AURORA_UEFI_CONSOLE_FAIL: "); Serial::text(reason); Serial::text("\r\n");
    Io::write(0xf4, 0x11);
    for (;;) { asm volatile("cli; hlt"); }
}
auto require(bool okay, std::string_view reason) -> void {
    if (!okay) { fail(reason); }
}
[[nodiscard]] auto quiet() -> bool {
    return ready && admission && root() == kernel_root && Timer::irq_off() && !waiting
        && Timer::stop() && Timer::quiet(0x100, false) && Timer::quiet(0x200, false);
}

__attribute__((noinline)) auto wait_for_sample() -> void {
    require(quiet() && wakes != UINT64_MAX, "poll boundary");
    expected_wake = wakes + 1;
    waiting = true;
    require(Timer::arm(polling_count), "poll one-shot arm");
    asm volatile("mov %%rsp, %0" : "=m"(wait_stack) : : "memory");
    require(wait_stack % 8 == 0 && wait_stack <= owned_arena + Handoff::stack_top
        && ConsoleWakeContext::frame_valid((wait_stack & ~U64{15}) - ConsoleWakeContext::byte_count, owned_arena),
        "poll stack ownership");
    asm volatile(".global uefi_console_poll_begin\nuefi_console_poll_begin:\n"
                 "sti\nhlt\ncli\n.global uefi_console_poll_end\nuefi_console_poll_end:" : : : "memory");
    waiting = false;
    wait_stack = 0;
    require(wakes == expected_wake && quiet(), "poll completion");
}

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
    const PageTables tables{kernel_root, static_cast<std::size_t>(handoff.get(96))};
    const auto slot = tables.interrupt_slot();
    require(slot && *slot == 0, "empty timer aperture");
    *slot = LocalApicAdmission::physical_address | LocalApicAdmission::leaf_flags;
    asm volatile("invlpg (%0)" : : "r"(LocalApicAdmission::virtual_address) : "memory");
    require(tables.verify(owned_arena, handoff, &*admission), "private timer mapping");
    require(admission->matches_registers(Timer::read(0x20), Timer::read(0x30)), "timer hardware identity");
    require(Timer::initialize(Timer::read(0x30)), "timer initial quiescence");
    ready = true;
}
}

auto interrupt_entry() -> void asm("uefi_console_interrupt") __attribute__((visibility("hidden")));
auto interrupt_dispatch(U64) -> void asm("uefi_console_interrupt_dispatch") __attribute__((visibility("hidden")));
auto interrupt_dispatch(U64 frame) -> void {
    require(ready && admission && waiting && root() == kernel_root && Timer::irq_off()
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

[[noreturn]] auto run_console(U64 arena, const Bytes& handoff) -> void {
    // No runtime/user image path is compiled in this profile. The loader has
    // completed its normal private-memory/ACPI/language tests before this call.
    require(!ready && !waiting && !admission && handoff.get(8, 4) == 2 && handoff.get(120) == 0
        && RuntimeLayout::valid(arena) && root() == handoff.get(88) && Timer::irq_off(), "entry authority");
    owned_arena = arena;
    kernel_root = handoff.get(88);
    U64 stack, flags, cr0, cr4;
    asm volatile("mov %%rsp, %0; pushfq; pop %1; mov %%cr0, %2; mov %%cr4, %3"
        : "=r"(stack), "=r"(flags), "=r"(cr0), "=r"(cr4));
    require(stack % 8 == 0 && stack >= arena + Handoff::stack_bottom + 4096 + 176
        && stack <= arena + Handoff::stack_top && (flags & 0x202) == 2 && (flags & ~U64{0x10ad7}) == 0,
        "entry stack/flags");
    require((cr4 & ((1ULL << 7) | (1ULL << 12) | (1ULL << 16) | (1ULL << 17) | (1ULL << 18)
        | (1ULL << 20))) == 0, "integer paging profile");
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
    establish_timer(handoff);
    require((Io::read(0x3fb) & 0x80) == 0, "UART register bank");
    Io::write(0x3f9, 0);
    require(Io::read(0x3f9) == 0, "UART interrupts disabled");
    Serial::initialize_input();
    Serial::text("AURORA_UEFI_CONSOLE_TIMER_READY: polling_count=1250000 uart_irq=0\r\n");
    console::Line line;
    Display::ready(platform);
    for (;;) {
        require(quiet(), "receive quiescence");
        const auto byte = Serial::poll(line);
        if (!byte) {
            wait_for_sample();
            continue;
        }
        const auto event = line.consume(*byte);
        if (event == console::Event::exit) {
            require(quiet() && Io::read(0x3f9) == 0, "exit quiescence");
            Serial::text("AURORA_UEFI_CONSOLE_QUIET: wakes="); Serial::number(wakes);
            Serial::text(" timer=masked isr=0 irr=0 uart_irq=0\r\n");
        }
        if (!Display::render(event, *byte, platform)) {
            Io::write(0xf4, 0x10);
            for (;;) { asm volatile("cli; hlt"); }
        }
    }
}
}
