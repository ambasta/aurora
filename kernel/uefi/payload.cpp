#include "graphical-profile.hpp"
#include "handoff.hpp"
#include "tables.hpp"
#include "acpi.hpp"
#include "runtime.hpp"
#ifdef AURORA_UEFI_GRAPHICAL_CONSOLE
#include "graphical-console.hpp"
#endif
#ifdef AURORA_UEFI_FRAMEBUFFER_FIXTURE
#include "framebuffer.hpp"
#endif
#ifdef AURORA_UEFI_CONSOLE
#include "console.hpp"
#endif
#include "../console.hpp"
#include "../pages.hpp"
#ifdef AURORA_UEFI_OWNED_BYTES
#include "owned-bytes.hpp"
#endif
using aurora::hardware::Serial;
using aurora::uefi::Bytes;
using aurora::uefi::Handoff;
using U64 = std::uint64_t;
auto payload_entry() -> void asm("uefi_payload_entry") __attribute__((visibility("hidden")));
auto generic_fault() -> void asm("uefi_payload_fault") __attribute__((visibility("hidden")));
auto page_fault() -> void asm("uefi_payload_page_fault") __attribute__((visibility("hidden")));
#if defined(AURORA_UEFI_IOMMU_EVENT) && AURORA_IOMMU_EVENT_CASE != 4
auto language_value() -> long long asm("__au_runtime_iommu_event_value");
#elif defined(AURORA_UEFI_GRAPHICAL_CONSOLE)
auto language_value() -> long long asm("__au_runtime_graphical_value");
#elif defined(AURORA_UEFI_FRAMEBUFFER_FIXTURE)
auto language_value() -> long long asm("__au_runtime_display_value");
#elif defined(AURORA_UEFI_CONSOLE)
auto language_value() -> long long asm("__au_runtime_console_value");
#elif !defined(AURORA_UEFI_OWNED_BYTES)
auto language_value() -> long long asm("aurora_kernel_value");
#endif
namespace {
constinit aurora::memory::PhysicalPages pool;
[[noreturn]] auto fail(std::string_view reason) -> void {
    Serial::text("AURORA_UEFI_PAYLOAD_FAIL: ");
    Serial::text(reason);
    Serial::text("\r\n");
    aurora::hardware::Io::write(0xf4, 0x11);
    for (;;)
        asm volatile("cli; hlt");
}
auto span(U64 address, std::size_t bytes) -> std::span<std::byte> {
    return {reinterpret_cast<std::byte *>(address), bytes};
}
auto install_idt(U64 base) -> void {
    for (unsigned vector = 0; vector < 256; ++vector) {
        const auto target = reinterpret_cast<U64>(vector == 14 ? &page_fault : &generic_fault);
        auto descriptor = span(base + vector * 16, 16);
        aurora::uefi::put(descriptor, 0, target, 2);
        aurora::uefi::put(descriptor, 2, 8, 2);
        aurora::uefi::put(descriptor, 4, 0, 1);
        aurora::uefi::put(descriptor, 5, 0x8e, 1);
        aurora::uefi::put(descriptor, 6, target >> 16, 2);
        aurora::uefi::put(descriptor, 8, target >> 32, 4);
    }
}
} // namespace
auto payload_fail(U64, U64, U64) -> void asm("uefi_payload_fail");
auto payload_fail(U64 vector, U64 error, U64 rip) -> void {
    U64 cr2;
    asm volatile("mov %%cr2, %0" : "=r"(cr2));
    Serial::text("AURORA_UEFI_EXCEPTION: vector=");
    Serial::number(vector);
    Serial::text(" error=");
    Serial::number(error);
    Serial::text(" rip=");
    Serial::number(rip);
    Serial::text(" cr2=");
    Serial::number(cr2);
    Serial::text("\r\n");
#ifdef AURORA_UEFI_GRAPHICAL_CONSOLE
    aurora::uefi::graphical_console_fault();
#else
    fail("exception");
#endif
}
auto payload_main(U64, U64) -> void asm("uefi_payload_main");
auto payload_main(U64 arena, U64 size) -> void {
    Serial::text("AURORA_UEFI_PAYLOAD_ENTRY\r\n");
    if (size != Handoff::header || arena % 4096 || arena < 0x100000 || arena > 0x100000000ULL - Handoff::arena_bytes)
        fail("handoff transport");
    install_idt(arena + Handoff::idt_offset);
    const auto handoff = span(arena, Handoff::header);
    if (!Handoff::valid(handoff, arena))
        fail("handoff validation");
    const Bytes h{handoff};
    if (reinterpret_cast<U64>(&payload_entry) != arena + Handoff::payload_offset)
        fail("position independent entry");
    const aurora::uefi::MemoryMap map{
        span(arena + Handoff::map_offset, h.get(32)), h.get(40), static_cast<std::uint32_t>(h.get(48, 4))};
    if (!map.owns(arena, Handoff::arena_bytes))
        fail("map ownership");
    U64 cr4;
    asm volatile("mov %%cr4, %0" : "=r"(cr4));
    if (cr4 & ((1ULL << 7) | (1ULL << 12) | (1ULL << 17)))
        fail("inherited paging modes");
    U64 root, stack, cr0, flags;
    asm volatile("mov %%cr3, %0; mov %%rsp, %1; mov %%cr0, %2; pushfq; pop %3"
                 : "=r"(root), "=r"(stack), "=r"(cr0), "=r"(flags));
    if (root != h.get(88) || stack < arena + Handoff::stack_bottom || stack >= arena + Handoff::stack_top ||
        !(cr0 & (1ULL << 16)) || (flags & 0x200))
        fail("private machine state");
    std::uint32_t low, high;
    asm volatile("rdmsr" : "=a"(low), "=d"(high) : "c"(0xc0000080));
    if (!(low & (1U << 11)))
        fail("NXE missing");
    const aurora::uefi::PageTables tables{root, static_cast<std::size_t>(h.get(96))};
    if (!tables.verify(arena, h))
        fail("complete mapping tree");
    for (U64 offset = 0; offset < Handoff::arena_bytes; offset += 4096) {
        const auto flags = aurora::uefi::expected_flags(offset, h);
        const auto expected = flags ? (arena + offset) | flags : 0;
        if ((tables.entry(arena + offset) & ~0x60ULL) != expected)
            fail("mapping permissions");
    }
    if (tables.entry(0) != 0 || tables.entry(0x10000) != 0 || tables.entry(0xfee00000) != 0)
        fail("inherited mapping");
    Serial::text("AURORA_UEFI_OWNERSHIP_OK: arena=");
    Serial::number(arena);
    Serial::text(" bytes=");
    Serial::number(Handoff::arena_bytes);
    Serial::text(" descriptors=");
    Serial::number(h.get(32) / h.get(40));
    Serial::text("\r\n");
    Serial::text("AURORA_UEFI_PROTECTION_OK: root=");
    Serial::number(root);
    Serial::text(" stack=");
    Serial::number(stack);
    Serial::text("\r\n");
#ifdef AURORA_UEFI_WP
    *reinterpret_cast<volatile std::uint8_t *>(arena + Handoff::payload_offset) = 0;
#endif
#ifdef AURORA_UEFI_NX
    *reinterpret_cast<volatile std::uint8_t *>(arena + Handoff::pool_offset) = 0xc3;
    reinterpret_cast<void (*)()>(arena + Handoff::pool_offset)();
#endif
#ifdef AURORA_UEFI_FRAMEBUFFER_PROBE
    std::uint32_t graphics_a, graphics_b, graphics_c, graphics_d;
    asm volatile("cpuid"
                 : "=a"(graphics_a), "=b"(graphics_b), "=c"(graphics_c), "=d"(graphics_d)
                 : "a"(0x80000000U), "c"(0));
    if (graphics_a < 0x80000008U)
        fail("framebuffer physical width unavailable");
    asm volatile("cpuid"
                 : "=a"(graphics_a), "=b"(graphics_b), "=c"(graphics_c), "=d"(graphics_d)
                 : "a"(0x80000008U), "c"(0));
    const auto graphics = aurora::uefi::FramebufferRecord::parse(
        span(arena + Handoff::framebuffer_record_offset, aurora::uefi::FramebufferRecord::bytes), graphics_a & 255);
    if (!graphics || h.get(8, 4) != 5)
        fail("framebuffer probe record");
    Serial::text("AURORA_FRAMEBUFFER_PROBE_PRIVATE_PAGING: width=");
    Serial::number(graphics->geometry().width());
    Serial::text(" height=");
    Serial::number(graphics->geometry().height());
    Serial::text(" pitch=");
    Serial::number(graphics->geometry().pitch());
    Serial::text(" format=");
    Serial::number(graphics->geometry().format());
    Serial::text(" tables=");
    Serial::number(h.get(96));
    Serial::text("\r\n");
    aurora::hardware::Io::write(0xf4, 0x10);
    for (;;)
        asm volatile("cli; hlt");
#endif
#ifdef AURORA_UEFI_FRAMEBUFFER_FIXTURE
    aurora::uefi::run_framebuffer(arena);
#endif
    if (!pool.initialize(arena + Handoff::pool_offset, 16))
        fail("owned pool initialization");
#ifdef AURORA_UEFI_OWNED_BYTES
    if (!aurora::uefi::run_owned_bytes(arena, pool))
        fail("owned byte allocation profile");
#endif
#ifdef AURORA_UEFI_IOMMU_EVENT
    if (language_value() != 42)
        fail("compiled event language result");
    Serial::text("AURORA_UEFI_LANGUAGE_OK: value=42\r\n");
#endif
#ifdef AURORA_UEFI_ACPI
    if (!aurora::uefi::discover_acpi(arena, h, pool))
        fail("ACPI discovery");
#endif
#ifdef AURORA_UEFI_RUNTIME
#ifdef AURORA_UEFI_SNAPSHOT
    if (!aurora::uefi::run_protected(arena, h, pool))
#else
    if (!aurora::uefi::run_protected(arena, h))
#endif
        fail("protected runtime");
#endif
    auto page = pool.acquire();
    if (!page)
        fail("owned page allocation");
    const auto physical = pool.address(*page);
    if (!physical || *physical != arena + Handoff::pool_offset)
        fail("owned page location");
    for (U64 i = 0; i < 4096; ++i)
        *reinterpret_cast<volatile std::uint8_t *>(*physical + i) = static_cast<std::uint8_t>(i);
    for (U64 i = 0; i < 4096; ++i)
        if (*reinterpret_cast<volatile std::uint8_t *>(*physical + i) != static_cast<std::uint8_t>(i))
            fail("owned page readback");
    if (!pool.release(*page) || pool.used() != 0)
        fail("owned page release");
#ifndef AURORA_UEFI_OWNED_BYTES
    if (language_value() != 42)
        fail("compiled language result");
#endif
    Serial::text("AURORA_UEFI_LANGUAGE_OK: value=42\r\nAURORA_UEFI_OK\r\n");
#ifdef AURORA_UEFI_GRAPHICAL_CONSOLE
    aurora::uefi::run_graphical_console(arena, h);
#endif
#ifdef AURORA_UEFI_CONSOLE
    aurora::uefi::run_console(arena, h);
#endif
    aurora::hardware::Io::write(0xf4, 0x10);
    for (;;)
        asm volatile("cli; hlt");
}
