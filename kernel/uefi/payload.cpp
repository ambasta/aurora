#include "handoff.hpp"
#include "tables.hpp"
#include "../console.hpp"
#include "../pages.hpp"
using aurora::hardware::Serial;
using aurora::uefi::Bytes;
using aurora::uefi::Handoff;
using U64=std::uint64_t;
auto payload_entry() -> void asm("uefi_payload_entry") __attribute__((visibility("hidden")));
auto generic_fault() -> void asm("uefi_payload_fault") __attribute__((visibility("hidden")));
auto page_fault() -> void asm("uefi_payload_page_fault") __attribute__((visibility("hidden")));
auto language_value() -> long long asm("aurora_kernel_value");
namespace {
constinit aurora::memory::PhysicalPages pool;
[[noreturn]] auto fail(std::string_view reason) -> void {
    Serial::text("AURORA_UEFI_PAYLOAD_FAIL: "); Serial::text(reason); Serial::text("\r\n");
    aurora::hardware::Io::write(0xf4,0x11); for (;;) asm volatile("cli; hlt");
}
auto span(U64 address,std::size_t bytes) -> std::span<std::byte> { return {reinterpret_cast<std::byte*>(address),bytes}; }
auto install_idt(U64 base) -> void {
    for (unsigned vector=0;vector<256;++vector) {
        const auto target=reinterpret_cast<U64>(vector==14 ? &page_fault : &generic_fault);
        auto descriptor=span(base+vector*16,16);
        aurora::uefi::put(descriptor,0,target,2); aurora::uefi::put(descriptor,2,8,2);
        aurora::uefi::put(descriptor,4,0,1); aurora::uefi::put(descriptor,5,0x8e,1);
        aurora::uefi::put(descriptor,6,target>>16,2); aurora::uefi::put(descriptor,8,target>>32,4);
    }
}
}
auto payload_fail(U64,U64,U64) -> void asm("uefi_payload_fail");
auto payload_fail(U64 vector,U64 error,U64 rip) -> void {
    U64 cr2; asm volatile("mov %%cr2, %0" : "=r"(cr2));
    Serial::text("AURORA_UEFI_EXCEPTION: vector="); Serial::number(vector); Serial::text(" error="); Serial::number(error);
    Serial::text(" rip="); Serial::number(rip); Serial::text(" cr2="); Serial::number(cr2); Serial::text("\r\n");
    fail("exception");
}
auto payload_main(U64,U64) -> void asm("uefi_payload_main");
auto payload_main(U64 arena,U64 size) -> void {
    Serial::text("AURORA_UEFI_PAYLOAD_ENTRY\r\n");
    if (size!=Handoff::header || arena%4096 || arena<0x100000 || arena>0x100000000ULL-Handoff::arena_bytes) fail("handoff transport");
    install_idt(arena+Handoff::idt_offset);
    const auto handoff=span(arena,Handoff::header);
    if (!Handoff::valid(handoff,arena)) fail("handoff validation");
    const Bytes h{handoff};
    if (reinterpret_cast<U64>(&payload_entry)!=arena+Handoff::payload_offset) fail("position independent entry");
    const aurora::uefi::MemoryMap map{span(arena+Handoff::map_offset,h.get(32)),h.get(40),static_cast<std::uint32_t>(h.get(48,4))};
    if (!map.owns(arena,Handoff::arena_bytes)) fail("map ownership");
    U64 cr4; asm volatile("mov %%cr4, %0" : "=r"(cr4));
    if (cr4&((1ULL<<7)|(1ULL<<12)|(1ULL<<17))) fail("inherited paging modes");
    U64 root,stack,cr0,flags;
    asm volatile("mov %%cr3, %0; mov %%rsp, %1; mov %%cr0, %2; pushfq; pop %3" : "=r"(root),"=r"(stack),"=r"(cr0),"=r"(flags));
    if (root!=h.get(88) || stack<arena+Handoff::stack_bottom || stack>=arena+Handoff::stack_top
        || !(cr0&(1ULL<<16)) || (flags&0x200)) fail("private machine state");
    std::uint32_t low,high; asm volatile("rdmsr" : "=a"(low),"=d"(high) : "c"(0xc0000080));
    if (!(low&(1U<<11))) fail("NXE missing");
    const aurora::uefi::PageTables tables{root,static_cast<std::size_t>(h.get(96))};
    if (!tables.verify(arena,h)) fail("complete mapping tree");
    for (U64 offset=0;offset<Handoff::arena_bytes;offset+=4096) {
        const auto flags=aurora::uefi::expected_flags(offset,h);
        const auto expected=flags ? (arena+offset)|flags : 0;
        if ((tables.entry(arena+offset)&~0x60ULL)!=expected) fail("mapping permissions");
    }
    if (tables.entry(0)!=0 || tables.entry(0x10000)!=0 || tables.entry(0xfee00000)!=0) fail("inherited mapping");
    Serial::text("AURORA_UEFI_OWNERSHIP_OK: arena="); Serial::number(arena); Serial::text(" bytes="); Serial::number(Handoff::arena_bytes);
    Serial::text(" descriptors="); Serial::number(h.get(32)/h.get(40)); Serial::text("\r\n");
    Serial::text("AURORA_UEFI_PROTECTION_OK: root="); Serial::number(root); Serial::text(" stack="); Serial::number(stack); Serial::text("\r\n");
#ifdef AURORA_UEFI_WP
    *reinterpret_cast<volatile std::uint8_t*>(arena+Handoff::payload_offset)=0;
#endif
#ifdef AURORA_UEFI_NX
    *reinterpret_cast<volatile std::uint8_t*>(arena+Handoff::pool_offset)=0xc3;
    reinterpret_cast<void(*)()>(arena+Handoff::pool_offset)();
#endif
    if (!pool.initialize(arena+Handoff::pool_offset,16)) fail("owned pool initialization");
    auto page=pool.acquire();
    if (!page) fail("owned page allocation");
    const auto physical=pool.address(*page);
    if (!physical || *physical!=arena+Handoff::pool_offset) fail("owned page location");
    for (U64 i=0;i<4096;++i) *reinterpret_cast<volatile std::uint8_t*>(*physical+i)=static_cast<std::uint8_t>(i);
    for (U64 i=0;i<4096;++i) if (*reinterpret_cast<volatile std::uint8_t*>(*physical+i)!=static_cast<std::uint8_t>(i)) fail("owned page readback");
    if (!pool.release(*page) || pool.used()!=0) fail("owned page release");
    if (language_value()!=42) fail("compiled language result");
    Serial::text("AURORA_UEFI_LANGUAGE_OK: value=42\r\nAURORA_UEFI_OK\r\n");
    aurora::hardware::Io::write(0xf4,0x10); for (;;) asm volatile("cli; hlt");
}
