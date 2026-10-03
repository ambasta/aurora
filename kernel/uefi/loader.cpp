#include "handoff.hpp"
#ifdef AURORA_UEFI_RUNTIME
#include "uefi-user-images.hpp"
#endif
#include "tables.hpp"
#include "acpi-policy.hpp"
#include "../console.hpp"
#include "uefi-payload.hpp"
#include <span>
using aurora::uefi::Bytes;
using aurora::uefi::Handoff;
using aurora::hardware::Serial;
using U64=std::uint64_t;
using Allocate=U64(__attribute__((ms_abi)) *)(unsigned,unsigned,U64,U64*);
using Map=U64(__attribute__((ms_abi)) *)(U64*,void*,U64*,U64*,std::uint32_t*);
using Exit=U64(__attribute__((ms_abi)) *)(void*,U64);
using Watchdog=U64(__attribute__((ms_abi)) *)(U64,U64,U64,const void*);
extern const std::byte payload_begin asm("uefi_embedded_payload");
extern const std::byte payload_end asm("uefi_embedded_payload_end");
extern const std::byte transition_begin asm("uefi_transition_begin");
extern const std::byte transition_end asm("uefi_transition_end");
extern const std::byte transition_fault asm("uefi_transition_fault");
constinit U64 anchor=Handoff::magic;
constinit U64* volatile relocated_anchor=&anchor;
namespace {
auto span(U64 address,std::size_t bytes) -> std::span<std::byte> { return {reinterpret_cast<std::byte*>(address),bytes}; }
[[noreturn]] auto fail(std::string_view reason) -> void {
    Serial::text("AURORA_UEFI_FAIL: "); Serial::text(reason); Serial::text("\r\n");
    aurora::hardware::Io::write(0xf4,0x11); for (;;) asm volatile("cli; hlt");
}
auto header_valid(U64 address,U64 signature,std::size_t minimum) -> bool {
    if (!address || address%8) return false;
    const Bytes header{span(address,24)};
    const auto size=header.get(12,4);
    if (header.get(0)!=signature || header.get(8,4)<0x20000 || size<minimum || size>4096 || header.get(20,4)!=0) return false;
    const auto bytes=span(address,size);
    std::uint32_t crc=0xffffffffU;
    for (std::size_t i=0;i<size;++i) {
        crc^=(i>=16 && i<20) ? 0 : std::to_integer<unsigned>(bytes[i]);
        for (unsigned bit=0;bit<8;++bit) crc=(crc>>1)^(0xedb88320U & (0U-(crc&1)));
    }
    return (crc^0xffffffffU)==header.get(16,4);
}
}
auto entry(void*,void*) -> U64 asm("aurora_efi_entry") __attribute__((ms_abi));
auto __attribute__((ms_abi)) entry(void* image,void* system) -> U64 {
    Serial::initialize(); Serial::text("AURORA_UEFI_ENTRY\r\n");
    if (relocated_anchor!=&anchor || *relocated_anchor!=Handoff::magic) fail("PE relocation");
    const auto system_address=reinterpret_cast<U64>(system);
    if (!header_valid(system_address,0x5453595320494249ULL,120)) fail("system table");
    const Bytes table{span(system_address,120)};
    const auto services=table.get(96);
    if (!header_valid(services,0x56524553544f4f42ULL,376)) fail("boot services table");
    const Bytes boot{span(services,376)};
    if (!boot.get(40)||!boot.get(56)||!boot.get(232)||!boot.get(256)) fail("missing service");
    const auto allocate=reinterpret_cast<Allocate>(boot.get(40));
    const auto get_map=reinterpret_cast<Map>(boot.get(56));
    const auto exit=reinterpret_cast<Exit>(boot.get(232));
    if (reinterpret_cast<Watchdog>(boot.get(256))(0,0,0,nullptr)!=0) fail("watchdog");
    U64 arena=0xffffffffULL;
    if (allocate(1,1,Handoff::arena_bytes/4096,&arena)!=0 || arena<0x100000 || arena%4096
        || arena>0x100000000ULL-Handoff::arena_bytes) fail("owned arena allocation");
    for (auto& byte:span(arena,Handoff::arena_bytes)) byte=std::byte{0};
    const auto payload_size=reinterpret_cast<U64>(&payload_end)-reinterpret_cast<U64>(&payload_begin);
    const auto transition_size=reinterpret_cast<U64>(&transition_end)-reinterpret_cast<U64>(&transition_begin);
    if (payload_size!=aurora::uefi::payload_size || payload_size>Handoff::payload_limit || transition_size>4096) fail("embedded image bounds");
    for (U64 i=0;i<payload_size;++i) span(arena+Handoff::payload_offset,payload_size)[i]=(&payload_begin)[i];
    for (U64 i=0;i<transition_size;++i) span(arena+Handoff::transition_offset,transition_size)[i]=(&transition_begin)[i];
    const auto fault=arena+Handoff::transition_offset+reinterpret_cast<U64>(&transition_fault)-reinterpret_cast<U64>(&transition_begin);
    for (unsigned vector=0;vector<256;++vector) {
        auto descriptor=span(arena+Handoff::idt_offset+vector*16,16);
        aurora::uefi::put(descriptor,0,fault,2); aurora::uefi::put(descriptor,2,8,2);
        aurora::uefi::put(descriptor,5,0x8e,1); aurora::uefi::put(descriptor,6,fault>>16,2);
        aurora::uefi::put(descriptor,8,fault>>32,4);
    }
    auto handoff=span(arena,Handoff::header);
    using aurora::uefi::put;
    put(handoff,0,Handoff::magic); put(handoff,8,1,4); put(handoff,12,Handoff::header,4);
#ifdef AURORA_UEFI_ACPI
    put(handoff,8,2,4);
#endif
#ifdef AURORA_UEFI_RUNTIME
    using aurora::uefi::RuntimeLayout;
    using namespace aurora::uefi::images;
    if (!RuntimeLayout::valid(arena)) fail("runtime arena layout");
    put(handoff,8,3,4); put(handoff,120,arena+RuntimeLayout::metadata_offset);
    const auto install_user=[&](unsigned index,std::span<const std::byte> image,const auto& fields) {
        if (image.empty() || image.size()>4096 || fields[1]!=image.size()) fail("bounded user image");
        auto target=span(arena+RuntimeLayout::image_offset+index*4096,image.size());
        for (std::size_t i=0;i<image.size();++i) target[i]=image[i];
        auto descriptor=span(arena+RuntimeLayout::metadata_offset+index*64,64);
        for (unsigned i=0;i<8;++i) put(descriptor,i*8,fields[i]);
        if (fields[7]) {
            if (!RuntimeLayout::valid_probe(image.size(),fields[7]) || Bytes{target}.get(fields[7])!=0) fail("controlled probe literal");
            put(target,fields[7],arena);
        }
    };
    install_user(0,clean_bytes,std::array<U64,8>{clean_entry,clean_size,clean_return_pc,clean_bounds_pc,clean_overflow_pc,clean_division_zero_pc,clean_shift_count_pc,clean_probe_offset});
    install_user(1,bounds_bytes,std::array<U64,8>{bounds_entry,bounds_size,bounds_return_pc,bounds_bounds_pc,bounds_overflow_pc,bounds_division_zero_pc,bounds_shift_count_pc,bounds_probe_offset});
#endif
    put(handoff,16,Handoff::arena_bytes); put(handoff,24,arena);
    put(handoff,56,payload_size); put(handoff,64,aurora::uefi::payload_text_end);
    put(handoff,72,aurora::uefi::payload_read_end); put(handoff,80,aurora::uefi::payload_memory_end);
    put(handoff,88,arena+Handoff::tables_offset); put(handoff,104,arena+Handoff::payload_offset);
    aurora::uefi::PageTables tables{arena+Handoff::tables_offset};
    for (U64 offset=0;offset<Handoff::arena_bytes;offset+=4096) {
        const auto flags=aurora::uefi::expected_flags(offset,Bytes{handoff});
        if (flags && !tables.map(arena+offset,flags)) fail("private tables");
    }
#ifdef AURORA_UEFI_BAD_TABLE
    if (!tables.map(0x10000,3|aurora::uefi::PageTables::nx)) fail("bad-table injection");
#endif
#ifdef AURORA_UEFI_ACPI
    if (!tables.prepare_window()) fail("firmware window tables");
#endif
    put(handoff,96,tables.used());
    std::uint32_t a,b,c,d;
    asm volatile("cpuid" : "=a"(a),"=b"(b),"=c"(c),"=d"(d) : "a"(0x80000000U),"c"(0));
    if (a<0x80000001U) fail("NX unavailable");
#ifdef AURORA_UEFI_ACPI
    if (a<0x80000008U) fail("physical address width unavailable");
    asm volatile("cpuid" : "=a"(a),"=b"(b),"=c"(c),"=d"(d) : "a"(0x80000008U),"c"(0));
    const auto firmware_physical_bits=a&255;
    if (firmware_physical_bits<32 || firmware_physical_bits>52) fail("physical address width unsupported");
#endif
    asm volatile("cpuid" : "=a"(a),"=b"(b),"=c"(c),"=d"(d) : "a"(0x80000001U),"c"(0));
    if (!(d&(1U<<20))) fail("NX unavailable");
    U64 cr4; asm volatile("mov %%cr4, %0" : "=r"(cr4));
    if ((cr4&((1ULL<<12)|(1ULL<<17))) || !(cr4&(1ULL<<5))) fail("four-level paging required");
    bool exited=false;
    for (unsigned attempt=1;attempt<=3;++attempt) {
        U64 size=aurora::uefi::MemoryMap::max_bytes,key=0,stride=0; std::uint32_t version=0;
        if (get_map(&size,reinterpret_cast<void*>(arena+Handoff::map_offset),&key,&stride,&version)!=0) fail("bounded memory map");
        if (size==0 || size>aurora::uefi::MemoryMap::max_bytes) fail("returned map length");
        const aurora::uefi::MemoryMap map{span(arena+Handoff::map_offset,size),stride,version};
        if (!map.owns(arena,Handoff::arena_bytes)) fail("final map ownership");
#ifdef AURORA_UEFI_ACPI
        const auto count=table.get(104),configuration=table.get(112);
        const aurora::uefi::FirmwareRanges readable{span(arena+Handoff::map_offset,size),stride,arena,firmware_physical_bits};
        if (count==0 || count>128 || !readable.readable(configuration,count*24)) fail("configuration table range");
        aurora::uefi::AcpiRoots roots;
        for (U64 i=0;i<count;++i) {
            const auto candidate=span(configuration+i*24,24);
            const auto before=roots.root();
            if (!roots.accept(candidate)) fail("duplicate or invalid ACPI roots");
#ifdef AURORA_ACPI_DUPLICATE_ROOT
            if (before==0 && roots.root()!=0 && !roots.accept(candidate)) fail("duplicate or invalid ACPI roots");
#else
            static_cast<void>(before);
#endif
        }
        const auto rsdp=roots.root();
        if (!rsdp || !readable.readable(rsdp,36)) fail("RSDP source range");
        put(handoff,112,rsdp);
#endif
        put(handoff,32,size); put(handoff,40,stride); put(handoff,48,version,4); put(handoff,52,attempt,4);
#ifdef AURORA_UEFI_STALE
        if (attempt==1) key^=1;
#endif
#ifdef AURORA_UEFI_EXHAUSTED
        key^=1;
#endif
        const auto status=exit(image,key);
        if (status==0) { exited=true; break; }
        if (status!=0x8000000000000002ULL) fail("ExitBootServices status");
        Serial::text("AURORA_UEFI_EXIT_REJECTED: attempt="); Serial::number(attempt); Serial::text("\r\n");
    }
    if (!exited) fail("ExitBootServices retry exhausted");
    // No firmware service or pointer is passed to the payload after successful exit.
    Serial::text("AURORA_UEFI_EXIT_OK: attempts="); Serial::number(Bytes{handoff}.get(52,4)); Serial::text("\r\n");
#ifdef AURORA_UEFI_BAD_HANDOFF
    put(handoff,8,2,4);
#endif
#ifdef AURORA_UEFI_BAD_MAP
    const auto map_bytes=span(arena+Handoff::map_offset,Bytes{handoff}.get(32));
    for (U64 offset=0;offset<map_bytes.size();offset+=Bytes{handoff}.get(40)) {
        const Bytes descriptor{map_bytes.subspan(offset,Bytes{handoff}.get(40))};
        if (descriptor.get(8)<=arena && descriptor.get(8)+descriptor.get(24)*4096>=arena+Handoff::arena_bytes)
            put(map_bytes,offset+32,descriptor.get(32)|(1ULL<<63));
    }
#endif
    asm volatile("cli" : : : "memory");
    std::uint32_t low,high; asm volatile("rdmsr" : "=a"(low),"=d"(high) : "c"(0xc0000080));
    low|=1U<<11; asm volatile("wrmsr" : : "a"(low),"d"(high),"c"(0xc0000080) : "memory");
    cr4 &= ~(1ULL<<7); // Flush inherited global TLB translations; leave PGE and PCID disabled.
    asm volatile("mov %0, %%cr4" : : "r"(cr4) : "memory");
    U64 cr0; asm volatile("mov %%cr0, %0" : "=r"(cr0)); cr0|=1ULL<<16;
    asm volatile("mov %0, %%cr0" : : "r"(cr0) : "memory");
    using Transition=void(*)(U64,U64,U64,U64,U64,U64);
    reinterpret_cast<Transition>(arena+Handoff::transition_offset)(arena+Handoff::tables_offset,
        arena+Handoff::stack_top,arena+Handoff::payload_offset,arena,Handoff::header,arena+Handoff::idt_offset);
    fail("transition returned");
}
