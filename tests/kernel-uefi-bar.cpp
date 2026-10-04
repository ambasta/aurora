#include "../kernel/uefi/bar-policy.hpp"
#include <cstdlib>
#include <iostream>
#include <source_location>
#include <type_traits>
#include <vector>
using namespace aurora::uefi;
using Buffer=std::vector<std::byte>;
using Header=std::array<std::byte,64>;
unsigned checks=0;
auto check(bool value,const std::source_location location=std::source_location::current()) -> void {
    ++checks; if (!value) { std::cerr << "FAIL at line " << location.line() << ", check " << checks << '\n'; std::abort(); }
}
auto resource(unsigned type,std::uint64_t begin,std::uint64_t length,unsigned granularity=64,unsigned specific=0,unsigned flags=0) -> Buffer {
    Buffer bytes(46);
    put(bytes,0,0x8a,1); put(bytes,1,43,2); put(bytes,3,type,1); put(bytes,4,flags,1); put(bytes,5,specific,1);
    put(bytes,6,granularity); put(bytes,14,begin); put(bytes,22,begin+length-1); put(bytes,38,length);
    return bytes;
}
auto list(std::initializer_list<Buffer> records) -> Buffer {
    Buffer result;
    for (const auto& record:records) result.insert(result.end(),record.begin(),record.end());
    result.push_back(std::byte{0x79}); result.push_back(std::byte{}); return result;
}
auto config(std::uint64_t base=0xc0000000,unsigned command=2) -> Header {
    Header result{};
    put(result,0,0x00101b36,4); put(result,4,command,2); put(result,9,0x010802,3);
    put(result,16,(base&0xfffffff0)|4,4); put(result,20,base>>32,4); return result;
}
auto other_config(unsigned index,std::uint64_t base,bool wide,bool prefetch=false) -> Header {
    if (index>=6) std::abort();
    Header result{};
    put(result,0,0x11111234,4); put(result,4,2,2); put(result,9,0x030000,3);
    put(result,16+index*4,(base&0xfffffff0)|(wide ? 4 : 0)|(prefetch ? 8 : 0),4);
    if (wide && index<5) put(result,20+index*4,base>>32,4);
    return result;
}
auto reservation_bytes(std::uint64_t base,std::uint64_t length,bool wide,bool prefetch=false) -> Buffer {
    auto bytes=list({resource(0,base,length,wide ? 64 : 32,prefetch ? 6 : 0)});
    put(bytes,22,length-1); return bytes;
}
auto snapshot(const Header& header,unsigned segment=0,unsigned bus=0,unsigned device=3,unsigned function=0) -> PciBarSnapshot {
    auto value=PciBarSnapshot::parse(segment,bus,device,function,header); if (!value) std::abort(); return *value;
}
auto memory(unsigned type=1,std::uint64_t begin=0x400000,std::uint64_t pages=256,std::uint64_t attributes=0) -> Buffer {
    Buffer result(40); put(result,0,type,4); put(result,8,begin); put(result,24,pages); put(result,32,attributes); return result;
}
auto hex_bytes(std::string_view text) -> Buffer {
    if (text.size()%2!=0) std::abort();
    Buffer result;
    const auto nibble=[](char value) -> unsigned {
        if (!((value>='0' && value<='9') || (value>='a' && value<='f'))) std::abort();
        return value<='9' ? static_cast<unsigned>(value-'0') : static_cast<unsigned>(value-'a'+10);
    };
    for (std::size_t i=0;i<text.size();i+=2) result.push_back(std::byte((nibble(text[i])<<4)|nibble(text[i+1])));
    return result;
}
// Literal, independently entered reference bytes exercise the published wire
// offsets without using the fixture writer. BAR [0xc0000000,0xc0004000).
constexpr std::array<std::byte,48> reference_bar{
    std::byte{0x8a},std::byte{0x2b},std::byte{0},std::byte{0},std::byte{0},std::byte{0},
    std::byte{0x40},std::byte{0},std::byte{0},std::byte{0},std::byte{0},std::byte{0},std::byte{0},std::byte{0},
    std::byte{0},std::byte{0},std::byte{0},std::byte{0xc0},std::byte{0},std::byte{0},std::byte{0},std::byte{0},
    std::byte{0xff},std::byte{0x3f},std::byte{0},std::byte{0xc0},std::byte{0},std::byte{0},std::byte{0},std::byte{0},
    std::byte{0},std::byte{0},std::byte{0},std::byte{0},std::byte{0},std::byte{0},std::byte{0},std::byte{0},
    std::byte{0},std::byte{0x40},std::byte{0},std::byte{0},std::byte{0},std::byte{0},std::byte{0},std::byte{0},
    std::byte{0x79},std::byte{0}
};
auto main() -> int {
    static_assert(!std::is_default_constructible_v<PciResources>);
    static_assert(!std::is_default_constructible_v<PciBarSnapshot>);
    static_assert(!std::is_default_constructible_v<NvmeBarProbe>);
    static_assert(!std::is_default_constructible_v<NvmeBarGrant>);
    static_assert(!std::is_default_constructible_v<PciBarReservation>);
    static_assert(!std::is_convertible_v<PciBarReservation,PciResources>);
    static_assert(!std::is_convertible_v<PciBarReservation,NvmeBarProbe>);
    static_assert(!std::is_convertible_v<PciBarReservation,NvmeBarGrant>);
    static_assert(std::is_same_v<decltype(std::declval<const PciResources&>().resources()),std::span<const PciResource>>);
    constexpr std::uint64_t base=0xc0000000,length=16384,cap=(1ULL<<37)|(4ULL<<52)|0x01010007;
    auto bar_bytes=list({resource(0,base,length)});
    check(std::equal(bar_bytes.begin(),bar_bytes.end(),reference_bar.begin()));
    const auto bar=PciResources::parse(reference_bar,40);
    check(bar && bar->count()==1 && bar->resources()[0].begin()==base && bar->resources()[0].length()==length);
    auto root_bytes=list({resource(1,0x6000,0xa000,0,3),resource(0,0x80000000,0x60000000,32),resource(2,0,256,0)});
    const auto root=PciResources::parse(root_bytes,40);
    check(root && root->count()==3 && root->resources()[1].end()==0xe0000000);
    for (auto bits:{0U,31U,53U,64U,255U}) check(!PciResources::parse(bar_bytes,bits));
    for (auto bits:{32U,36U,40U,48U,52U}) check(PciResources::parse(bar_bytes,bits).has_value());
    for (std::size_t n=0;n<bar_bytes.size();++n) check(!PciResources::parse(std::span{bar_bytes}.first(n),40));
    for (std::size_t n=1;n<47;++n) {
        auto invalid=bar_bytes; invalid.insert(invalid.end(),n,std::byte{}); check(!PciResources::parse(invalid,40));
    }
    for (unsigned field:{0U,1U,2U,46U,47U}) for (unsigned bit=0;bit<8;++bit) {
        auto invalid=bar_bytes; invalid[field]^=std::byte{static_cast<unsigned char>(1U<<bit)};
        check(!PciResources::parse(invalid,40));
    }
    for (unsigned type=1;type<256;++type) {
        auto invalid=bar_bytes; put(invalid,3,type,1); check(!PciResources::parse(invalid,40));
    }
    for (unsigned flags=0;flags<256;++flags) {
        auto bytes=bar_bytes; put(bytes,4,flags,1);
        const bool supported=flags==0 || flags==1 || flags==12 || flags==13;
        check(PciResources::parse(bytes,40).has_value()==supported);
    }
    for (unsigned flags=0;flags<256;++flags) {
        auto bytes=bar_bytes; put(bytes,5,flags,1); check(PciResources::parse(bytes,40).has_value()==(flags<8));
        auto io=list({resource(1,0x1000,0x1000,0,flags)});
        check(PciResources::parse(io,40).has_value()==(flags==3));
        auto bus=list({resource(2,0,256,0,flags)}); check(PciResources::parse(bus,40).has_value()==(flags==0));
    }
    for (auto value:{0ULL,1ULL,31ULL,33ULL,63ULL,65ULL,~0ULL}) {
        auto invalid=bar_bytes; put(invalid,6,value); check(!PciResources::parse(invalid,40));
    }
    for (unsigned bit=0;bit<64;++bit) {
        auto invalid=bar_bytes; put(invalid,30,1ULL<<bit); check(!PciResources::parse(invalid,40));
    }
    for (unsigned offset:{14U,22U,38U}) for (auto value:{0ULL,1ULL,0x4000ULL,0xffffffffffffffffULL}) {
        auto invalid=bar_bytes; put(invalid,offset,value);
        check(PciResources::parse(invalid,40).has_value()==(offset==38 && value==length));
    }
    auto alignment_in_max=bar_bytes; put(alignment_in_max,22,length-1);
    check(!PciResources::parse(alignment_in_max,40)); // EDK2's alignment-mask layout is explicitly unsupported.
    for (auto bits:{32U,36U,40U,48U,52U}) {
        const auto limit=1ULL<<bits;
        check(PciResources::parse(list({resource(0,limit-4096,4096)}),bits).has_value());
        check(!PciResources::parse(list({resource(0,limit-4096,8192)}),bits));
        check(!PciResources::parse(list({resource(0,limit,4096)}),bits));
    }
    check(!PciResources::parse(list({resource(0,0x100000000,4096,32)}),40));
    check(!PciResources::parse(list({resource(0,~0ULL-4095,4096)}),52));
    check(!PciResources::parse(list({resource(0,~0ULL-4095,8192)}),52));
    check(!PciResources::parse(list({resource(1,0xffff,2,0,3)}),40));
    check(!PciResources::parse(list({resource(2,255,2,0)}),40));
    check(!PciResources::parse(list({resource(2,0,256,32)}),40));
    check(!PciResources::parse(list({resource(0,base,4096),resource(0,base,4096)}),40));
    check(!PciResources::parse(list({resource(0,base,8192),resource(0,base+4096,8192)}),40));
    check(!PciResources::parse(list({resource(2,0,10,0),resource(2,9,10,0)}),40));
    check(PciResources::parse(list({resource(0,base,4096),resource(0,base+4096,4096)}),40).has_value());
    Buffer many;
    for (unsigned count=1;count<=17;++count) {
        const auto item=resource(0,base+count*4096,4096);
        many.insert(many.end(),item.begin(),item.end()); auto ended=many;
        ended.push_back(std::byte{0x79}); ended.push_back(std::byte{});
        check(PciResources::parse(ended,40).has_value()==(count<=16));
    }
    // Firmware-data mutation cannot change a successful immutable description.
    auto independent=PciResources::parse(bar_bytes,40); bar_bytes.assign(48,std::byte{});
    check(independent && independent->resources()[0].begin()==base && independent->resources()[0].end()==base+length);
    auto header=config(); const auto copied=snapshot(header); const auto current=snapshot(header);
    header.fill(std::byte{0xff}); check(copied.same(current) && copied.base()==base);
    for (std::size_t n=0;n<64;++n) check(!PciBarSnapshot::parse(0,0,3,0,std::span{header}.first(n)));
    for (auto location:{std::array{65536U,0U,0U,0U},std::array{0U,256U,0U,0U},std::array{0U,0U,32U,0U},std::array{0U,0U,0U,8U}})
        check(!PciBarSnapshot::parse(location[0],location[1],location[2],location[3],config()));
    for (unsigned vendor:{0U,65535U}) {
        auto bad=config(); put(bad,0,vendor,2); check(!PciBarSnapshot::parse(0,0,3,0,bad));
    }
    WindowAuthority authority,foreign;
    const auto ticket=authority.acquire(),foreign_ticket=foreign.acquire(); check(ticket && foreign_ticket);
    auto map=memory();
    auto admit=[&](const PciBarSnapshot& prior,const PciBarSnapshot& now,const PciResources& bar_resource,const PciResources& root_resource,
        const Buffer& memory_map,std::uint64_t arena=0x400000,std::uint64_t apic=0xfee00000,unsigned root_segment=0) {
        return NvmeBarProbe::authorize(prior,now,bar_resource,root_resource,root_segment,memory_map,40,arena,apic,authority,*ticket);
    };
    const auto probe=admit(copied,current,*bar,*root,map);
    check(probe && probe->page(authority)==base && probe->length()==length);
    check(!probe->page(foreign));
    check(!NvmeBarProbe::authorize(copied,current,*bar,*root,0,map,40,0x400000,0xfee00000,authority,*foreign_ticket));
    for (std::uint64_t offset=0;offset<0x1100;++offset) for (unsigned width:{0U,1U,2U,3U,4U,8U,16U}) {
        const bool expected=(width==8 && (offset==0 || offset==40 || offset==48))
            || (width==4 && (offset==8 || offset==20 || offset==28 || offset==36));
        check(probe->read_address(authority,current,offset,width).has_value()==expected);
    }
    for (auto offset:{0xfffffff8ULL,~0ULL}) check(!probe->read_address(authority,current,offset,8));
    check(!probe->read_address(foreign,current,0,8));
    for (unsigned byte=0;byte<64;++byte) for (unsigned bit=0;bit<8;++bit) {
        auto mutated=config(); mutated[byte]^=std::byte{static_cast<unsigned char>(1U<<bit)};
        const auto changed=PciBarSnapshot::parse(0,0,3,0,mutated);
        if (!changed) continue;
        check(!admit(copied,*changed,*bar,*root,map));
        check(!probe->read_address(authority,*changed,0,8));
        check(!probe->finish(authority,*changed,cap,0x10400,0,0,0,0,0));
    }
    for (auto location:{std::array{1U,0U,3U,0U},std::array{0U,1U,3U,0U},std::array{0U,0U,4U,0U},std::array{0U,0U,3U,1U}}) {
        const auto changed=snapshot(config(),location[0],location[1],location[2],location[3]);
        check(!admit(copied,changed,*bar,*root,map));
    }
    for (unsigned command=0;command<65536;command+=1) {
        const auto candidate=snapshot(config(base,command));
        const auto admitted=admit(candidate,candidate,*bar,*root,map);
        const bool readable=(command&2) && !(command&0xf800);
        check(admitted.has_value()==readable);
        if (admitted) check(admitted->finish(authority,candidate,cap,0x10400,0,0,0,0,0).has_value()==((command&4)==0));
    }
    for (unsigned field:{0U,2U,9U,10U,11U,14U}) {
        auto bad=config(); put(bad,field,7,1); const auto candidate=snapshot(bad);
        check(!admit(candidate,candidate,*bar,*root,map));
    }
    for (unsigned low=0;low<16;++low) {
        auto bad=config(); put(bad,16,base|low,4); const auto candidate=snapshot(bad);
        check(admit(candidate,candidate,*bar,*root,map).has_value()==(low==4));
    }
    for (auto span:{1ULL,4095ULL,4096ULL,8192ULL,16384ULL,24576ULL,0x100000ULL,0x200000ULL}) {
        const auto described=PciResources::parse(list({resource(0,base,span)}),40); check(described.has_value());
        check(admit(copied,current,*described,*root,map).has_value()==(span>=4096 && span<=0x100000 && !(span&(span-1))));
    }
    for (unsigned flags=0;flags<8;++flags) {
        const auto described=PciResources::parse(list({resource(0,base,length,64,flags)}),40);
        check(described && admit(copied,current,*described,*root,map).has_value()==(flags<2));
        const auto changed_root=PciResources::parse(list({resource(0,0x80000000,0x60000000,32,flags),resource(2,0,256,0)}),40);
        check(changed_root && admit(copied,current,*bar,*changed_root,map).has_value()==(flags<2));
    }
    check(!admit(copied,current,*bar,*root,map,0x400000,0xfee00000,1));
    const auto bits32=PciResources::parse(reference_bar,32); check(bits32 && !admit(copied,current,*bits32,*root,map));
    const auto no_bus=PciResources::parse(list({resource(0,base,length)}),40); check(no_bus && !admit(copied,current,*bar,*no_bus,map));
    const auto wrong_bus=PciResources::parse(list({resource(0,base,length),resource(2,1,255,0)}),40);
    check(wrong_bus && !admit(copied,current,*bar,*wrong_bus,map));
    const auto truncated_root=PciResources::parse(list({resource(0,base,length-1),resource(2,0,256,0)}),40);
    check(truncated_root && !admit(copied,current,*bar,*truncated_root,map));
    const auto two_bars=PciResources::parse(list({resource(0,base,4096),resource(0,base+4096,4096)}),40);
    check(two_bars && !admit(copied,current,*two_bars,*root,map));
    const auto mem32=PciResources::parse(list({resource(0,base,length,32)}),40); check(mem32 && !admit(copied,current,*mem32,*root,map));
    const auto high_base=1ULL<<39;
    const auto high_bar=PciResources::parse(list({resource(0,high_base,length)}),40);
    const auto high_root=PciResources::parse(list({resource(0,high_base,0x100000),resource(2,0,256,0)}),40);
    const auto high_snapshot=snapshot(config(high_base));
    check(high_bar && high_root && admit(high_snapshot,high_snapshot,*high_bar,*high_root,map).has_value());
    for (auto stride:{0U,8U,39U,41U,264U})
        check(!NvmeBarProbe::authorize(copied,current,*bar,*root,0,map,stride,0x400000,0xfee00000,authority,*ticket));
    // Each RAM/firmware type and every attribute bit is independently exercised.
    for (unsigned type=0;type<=15;++type) for (unsigned bit=0;bit<64;++bit) {
        const auto candidate=memory(type,base+4096,1,1ULL<<bit);
        const bool expected=(type==0 || type==11) && (bit==0 || bit==14 || bit==17);
        check(admit(copied,current,*bar,*root,candidate).has_value()==expected);
    }
    for (auto attributes:{0ULL,1ULL,0x24001ULL,9ULL,0x2000ULL,0x8000000000000000ULL})
        check(admit(copied,current,*bar,*root,memory(11,base,4,attributes)).has_value()==(attributes==0 || attributes==1 || attributes==0x24001));
    for (unsigned type:{0U,11U,1U,7U,9U,10U}) {
        check(admit(copied,current,*bar,*root,memory(type,base-4096,1)).has_value());
        check(admit(copied,current,*bar,*root,memory(type,base+length,1)).has_value());
        check(admit(copied,current,*bar,*root,memory(type,base-4096,2)).has_value()==(type==0 || type==11));
    }
    auto overlapping=memory(0,base,2); const auto overlap=memory(11,base+4096,2);
    overlapping.insert(overlapping.end(),overlap.begin(),overlap.end()); check(!admit(copied,current,*bar,*root,overlapping));
    check(!admit(copied,current,*bar,*root,{}));
    check(!admit(copied,current,*bar,*root,memory(0,1ULL<<40,1)));
    for (auto arena:std::array<std::uint64_t,6>{base,base-Handoff::arena_bytes+4096,base+length-4096,~0ULL-4095,1ULL<<40,0x400001ULL})
        check(!admit(copied,current,*bar,*root,map,arena));
    check(admit(copied,current,*bar,*root,map,base-Handoff::arena_bytes).has_value());
    check(admit(copied,current,*bar,*root,map,base+length).has_value());
    for (auto apic:std::array<std::uint64_t,6>{base,base+4096,0ULL,1ULL,1ULL<<40,~0ULL-4095}) check(!admit(copied,current,*bar,*root,map,0x400000,apic));
    // Independent page-index interval model around all exclusions. The model
    // uses set membership, not the implementation's byte-range overlap helper.
    const auto all_memory=PciResources::parse(list({resource(0,0,0x100000000ULL),resource(2,0,256,0)}),40); check(all_memory.has_value());
    for (auto anchor:{0x400000ULL,0xe0000000ULL,0xf0000000ULL,0xfec00000ULL,0xfee00000ULL}) {
        for (int delta=-8;delta<=8;++delta) for (unsigned pages:{1U,2U,4U,8U}) {
            const auto address=anchor+std::int64_t{delta}*4096;
            const auto described=PciResources::parse(list({resource(0,address,pages*4096)}),40);
            check(described.has_value()); const auto identity=snapshot(config(address));
            bool expected=(address%(pages*4096)==0);
            for (std::uint64_t page=address/4096;page<address/4096+pages;++page)
                if ((page>=1024 && page<1280) || (page>=0xe0000 && page<0xf0000) || page==0xfec00 || page==0xfee00) expected=false;
            check(admit(identity,identity,*described,*all_memory,map).has_value()==expected);
        }
    }
    const auto grant=probe->finish(authority,current,cap,0x10400,0,0,0,0,0);
    check(grant && grant->capabilities()==cap && grant->version()==0x10400);
    check(grant->read_address(authority,current,0,8)==base);
    check(!grant->read_address(authority,current,0x1000,4));
    for (unsigned bit=0;bit<32;++bit) {
        check(!probe->finish(authority,current,cap,0x10400,1U<<bit,0,0,0,0));
        check(!probe->finish(authority,current,cap,0x10400,0,1U<<bit,0,0,0));
        check(!probe->finish(authority,current,cap,0x10400,0,0,1U<<bit,0,0));
    }
    for (unsigned bit=0;bit<64;++bit) {
        check(!probe->finish(authority,current,cap,0x10400,0,0,0,1ULL<<bit,0));
        check(!probe->finish(authority,current,cap,0x10400,0,0,0,0,1ULL<<bit));
    }
    check(!grant->read_address(authority,current,0x24,4));
    check(!grant->read_address(authority,current,0x28,8));
    check(!grant->read_address(authority,current,0x30,8));
    for (auto version:{0U,0x10300U,0x10401U,0x20000U,~0U}) check(!probe->finish(authority,current,cap,version,0,0,0,0,0));
    for (auto capabilities:{0ULL,~0ULL,cap&~0xffffULL,cap&~(1ULL<<37),cap|(15ULL<<48)})
        check(!probe->finish(authority,current,capabilities,0x10400,0,0,0,0,0));
    // Exact raw OVMF capture from the namespace-free q35 NVMe fixture. The
    // approved producer is edk2-stable202502, commit fbe0805b2091393406952e84724188f8c1941837.
    // Tests retain the wire bytes, not a parser-generated equivalent.
    const auto captured_bar=hex_bytes(
        "8a2b00000000400000000000000000000000c0000000ff3f000000000000000000000000000000400000000000007900");
    const auto captured_root=hex_bytes(
        "8a2b0001000000000000000000000060000000000000ff6f00000000000000000000000000000010000000000000"
        "8a2b0000000020000000000000000000008000000000ffff0f810000000000000000000000000000100100000000"
        "8a2b00000000400000000000000000000000c0000000ffff0f00c000000000000000000000000000100000000000"
        "8a2b00020000000000000000000000000000000000000000000000000000000000000000000001000000000000007900");
    check(captured_bar.size()==48 && captured_root.size()==186);
    check(!PciResources::parse(captured_bar,40) && !PciResources::parse(captured_root,40));
    const auto edk2_bar=PciResources::parse_edk2_bar(captured_bar,40);
    const auto edk2_root=PciResources::parse_edk2_root(captured_root,40);
    check(edk2_bar && edk2_root && edk2_bar->count()==1 && edk2_root->count()==4);
    check(edk2_bar->source()==PciResourceSource::Edk2Stable202502Bar);
    check(edk2_root->source()==PciResourceSource::Edk2Stable202502Root);
    check(bar->source()==PciResourceSource::Uefi && root->source()==PciResourceSource::Uefi);
    constexpr std::uint64_t captured_base=0xc000000000;
    check(edk2_bar->resources()[0].begin()==captured_base && edk2_bar->resources()[0].end()==captured_base+0x4000);
    const auto edk2_snapshot=snapshot(config(captured_base),0,0,2,0);
    const auto edk2_probe=admit(edk2_snapshot,edk2_snapshot,*edk2_bar,*edk2_root,map);
    check(edk2_probe && edk2_probe->read_address(authority,edk2_snapshot,0x28,8)==captured_base+0x28);
    const auto edk2_grant=edk2_probe->finish(authority,edk2_snapshot,cap,0x10400,0,0,0,0,0);
    check(edk2_grant.has_value());
    const auto inherited=snapshot(config(captured_base,7),0,0,2,0);
    const auto inherited_probe=admit(inherited,inherited,*edk2_bar,*edk2_root,map);
    check(inherited_probe && !inherited_probe->finish(authority,inherited,cap,0x10400,0,0,0,0,0));
    auto strict_bar_bytes=captured_bar; put(strict_bar_bytes,22,captured_base+0x3fff);
    auto strict_root_bytes=captured_root; put(strict_root_bytes,5,3,1);
    const auto strict_bar=PciResources::parse(strict_bar_bytes,40),strict_root=PciResources::parse(strict_root_bytes,40);
    check(strict_bar && strict_root && admit(edk2_snapshot,edk2_snapshot,*strict_bar,*strict_root,map).has_value());
    check(!admit(edk2_snapshot,edk2_snapshot,*edk2_bar,*strict_root,map));
    check(!admit(edk2_snapshot,edk2_snapshot,*strict_bar,*edk2_root,map));
    check(!admit(edk2_snapshot,edk2_snapshot,*edk2_root,*edk2_bar,map));
    check(!PciResources::parse_edk2_bar(strict_bar_bytes,40));
    check(!PciResources::parse_edk2_bar(captured_root,40));
    check(!PciResources::parse_edk2_root(captured_bar,40));
    // A normative memory-only record is valid root syntax, but root provenance
    // cannot be supplied as a BAR even if every normalized extent is identical.
    const auto disguised_bar=PciResources::parse_edk2_root(strict_bar_bytes,40);
    check(disguised_bar && !admit(edk2_snapshot,edk2_snapshot,*disguised_bar,*edk2_root,map));
    for (std::size_t n=0;n<captured_bar.size();++n) check(!PciResources::parse_edk2_bar(std::span{captured_bar}.first(n),40));
    for (std::size_t n=0;n<captured_root.size();++n) check(!PciResources::parse_edk2_root(std::span{captured_root}.first(n),40));
    for (unsigned byte=0;byte<48;++byte) for (unsigned bit=0;bit<8;++bit) {
        auto changed=captured_bar; changed[byte]^=std::byte{static_cast<unsigned char>(1U<<bit)};
        const auto parsed=PciResources::parse_edk2_bar(changed,40);
        // Only a different, still-aligned base could survive this one-bit
        // mutation. Its mismatch with the unchanged PCI snapshot must deny.
        check(!parsed || (byte>=14 && byte<22));
        if (parsed) check(!admit(edk2_snapshot,edk2_snapshot,*parsed,*edk2_root,map));
    }
    for (unsigned record=0;record<4;++record) for (unsigned field:{14U,22U,30U,38U}) for (unsigned bit=0;bit<64;++bit) {
        auto changed=captured_root; changed[record*46+field+bit/8]^=std::byte{static_cast<unsigned char>(1U<<(bit%8))};
        check(!PciResources::parse_edk2_root(changed,40));
    }
    for (unsigned record=0;record<4;++record) for (unsigned bit=0;bit<8;++bit) {
        auto changed=captured_root; changed[record*46+4]^=std::byte{static_cast<unsigned char>(1U<<bit)};
        check(!PciResources::parse_edk2_root(changed,40));
    }
    for (auto span:{0ULL,1ULL,4095ULL,4096ULL,8192ULL,16384ULL,24576ULL,0x100000ULL,0x200000ULL}) {
        auto candidate=list({resource(0,captured_base,span)}); put(candidate,22,span-1);
        check(PciResources::parse_edk2_bar(candidate,40).has_value()==(span>=4096 && span<=0x100000 && !(span&(span-1))));
    }
    for (auto bits:{32U,36U,40U,48U,52U}) {
        const auto limit=1ULL<<bits;
        auto candidate=captured_bar; put(candidate,14,limit-0x4000);
        check(PciResources::parse_edk2_bar(candidate,bits).has_value());
        put(candidate,14,limit); check(!PciResources::parse_edk2_bar(candidate,bits));
        put(candidate,14,~0ULL-0x3fff); check(!PciResources::parse_edk2_bar(candidate,bits));
    }
    auto altered_root=captured_root;
    put(altered_root,2*46+22,captured_base+4095); put(altered_root,2*46+38,4096);
    auto parsed_root=PciResources::parse_edk2_root(altered_root,40);
    check(parsed_root && !admit(edk2_snapshot,edk2_snapshot,*edk2_bar,*parsed_root,map));
    altered_root=captured_root; put(altered_root,2*46+5,6,1);
    parsed_root=PciResources::parse_edk2_root(altered_root,40);
    check(parsed_root && !admit(edk2_snapshot,edk2_snapshot,*edk2_bar,*parsed_root,map));
    auto duplicate_window=list({resource(0,captured_base,0x100000),resource(0,captured_base,0x4000),resource(2,0,1,0)});
    check(!PciResources::parse_edk2_root(duplicate_window,40));
    auto mutable_bar=captured_bar,mutable_root=captured_root;
    const auto immutable_bar=PciResources::parse_edk2_bar(mutable_bar,40),immutable_root=PciResources::parse_edk2_root(mutable_root,40);
    mutable_bar.assign(48,std::byte{}); mutable_root.assign(186,std::byte{});
    check(immutable_bar && immutable_root && admit(edk2_snapshot,edk2_snapshot,*immutable_bar,*immutable_root,map).has_value());
    // Other endpoints supply reservations only. VGA's prefetchable 16MiB
    // memory32 BAR intentionally exceeds the target controller's size ceiling.
    const auto vga=snapshot(other_config(0,0x80000000,0,1),0,0,1,0);
    auto vga_bytes=reservation_bytes(0x80000000,0x1000000,0,1);
    const auto reserved=PciBarReservation::parse_edk2(vga,vga,0,vga_bytes,40);
    check(reserved && reserved->begin()==0x80000000 && reserved->length()==0x1000000);
    check(!reserved->overlaps(0x7ffff000,4096)); check(!reserved->overlaps(0x81000000,4096));
    check(reserved->overlaps(0x7ffff000,8192)); check(reserved->overlaps(0x80fff000,8192));
    check(reserved->overlaps(0x80000000,0x1000000)); check(reserved->overlaps(0x80800000,1));
    check(reserved->overlaps(0,0)); check(reserved->overlaps(~0ULL-7,16));
    check(!PciResources::parse_edk2_bar(vga_bytes,40)); check(!PciResources::parse_edk2_root(vga_bytes,40));
    for (unsigned index=0;index<6;++index) for (bool wide:{false,true}) for (bool prefetch:{false,true}) {
        const std::uint64_t address=wide ? 0xb000000000 : 0xb0000000;
        const auto identity=snapshot(other_config(index,address,wide,prefetch),0,0,1,0);
        const auto described=reservation_bytes(address,0x1000,wide,prefetch);
        check(PciBarReservation::parse_edk2(identity,identity,index,described,40).has_value()==(!wide || index<5));
    }
    for (unsigned index:{6U,7U,255U,~0U}) check(!PciBarReservation::parse_edk2(vga,vga,index,vga_bytes,40));
    for (auto bits:{0U,31U,53U,64U}) check(!PciBarReservation::parse_edk2(vga,vga,0,vga_bytes,bits));
    for (std::size_t n=0;n<vga_bytes.size();++n) check(!PciBarReservation::parse_edk2(vga,vga,0,std::span{vga_bytes}.first(n),40));
    auto excess=vga_bytes; excess.push_back(std::byte{}); check(!PciBarReservation::parse_edk2(vga,vga,0,excess,40));
    for (unsigned byte=0;byte<48;++byte) for (unsigned bit=0;bit<8;++bit) {
        auto changed=vga_bytes; changed[byte]^=std::byte{static_cast<unsigned char>(1U<<bit)};
        check(!PciBarReservation::parse_edk2(vga,vga,0,changed,40));
    }
    for (unsigned byte=0;byte<64;++byte) for (unsigned bit=0;bit<8;++bit) {
        auto changed=other_config(0,0x80000000,0,1); changed[byte]^=std::byte{static_cast<unsigned char>(1U<<bit)};
        const auto identity=PciBarSnapshot::parse(0,0,1,0,changed);
        if (identity) check(!PciBarReservation::parse_edk2(vga,*identity,0,vga_bytes,40));
    }
    for (auto location:{std::array{1U,0U,1U,0U},std::array{0U,1U,1U,0U},std::array{0U,0U,2U,0U},std::array{0U,0U,1U,1U}}) {
        const auto changed=snapshot(other_config(0,0x80000000,0,1),location[0],location[1],location[2],location[3]);
        check(!PciBarReservation::parse_edk2(vga,changed,0,vga_bytes,40));
    }
    for (unsigned header_kind:{0U,0x80U,1U,0x81U,2U,0xffU}) {
        auto changed=other_config(0,0x80000000,0,1); put(changed,14,header_kind,1);
        const auto identity=snapshot(changed);
        check(PciBarReservation::parse_edk2(identity,identity,0,vga_bytes,40).has_value()==(header_kind==0 || header_kind==0x80));
    }
    for (unsigned low=0;low<16;++low) {
        auto changed=other_config(0,0x80000000,0,1); put(changed,16,0x80000000|low,4);
        const auto identity=snapshot(changed);
        check(PciBarReservation::parse_edk2(identity,identity,0,vga_bytes,40).has_value()==(low==8));
    }
    for (auto bits:{32U,40U,52U}) {
        const auto limit=1ULL<<bits;
        auto described=reservation_bytes(limit-4096,4096,true);
        auto identity=snapshot(other_config(0,limit-4096,true));
        check(PciBarReservation::parse_edk2(identity,identity,0,described,bits).has_value());
        described=reservation_bytes(limit,4096,true); identity=snapshot(other_config(0,limit,true));
        check(!PciBarReservation::parse_edk2(identity,identity,0,described,bits));
    }
    for (auto extent:{0ULL,1ULL,8ULL,16ULL,256ULL,4096ULL,6144ULL,0x1000000ULL,0x100000000ULL,~0ULL}) {
        const auto identity=snapshot(other_config(0,0x8000000000,true));
        const auto described=reservation_bytes(0x8000000000,extent,true);
        check(PciBarReservation::parse_edk2(identity,identity,0,described,40).has_value()==
            (extent>=16 && extent!=~0ULL && !(extent&(extent-1))));
    }
    const auto highest32=snapshot(other_config(5,0xfffff000,false));
    check(PciBarReservation::parse_edk2(highest32,highest32,5,reservation_bytes(0xfffff000,4096,false),40).has_value());
    const auto zero_base=snapshot(other_config(0,0,true));
    check(!PciBarReservation::parse_edk2(zero_base,zero_base,0,reservation_bytes(0,4096,true),40));
    auto preceding=other_config(2,0x80000000,false); put(preceding,16,4,4); put(preceding,20,0xc0,4);
    const auto after_wide=snapshot(preceding);
    check(PciBarReservation::parse_edk2(after_wide,after_wide,2,reservation_bytes(0x80000000,4096,false),40).has_value());
    check(!PciBarReservation::parse_edk2(after_wide,after_wide,1,reservation_bytes(0xc0,16,false),40));
    for (unsigned kind:{2U,6U}) {
        put(preceding,16,kind,4); const auto unsupported=snapshot(preceding);
        check(!PciBarReservation::parse_edk2(unsupported,unsupported,2,reservation_bytes(0x80000000,4096,false),40));
    }
    // Per-byte set membership is an independent oracle around both reservation
    // edges; zero/overflow caller ranges above deliberately fail closed.
    for (std::uint64_t boundary:{0x80000000ULL,0x81000000ULL}) for (int delta=-32;delta<=32;++delta) for (unsigned bytes=1;bytes<=64;++bytes) {
        const auto address=boundary+delta;
        bool intersects=false;
        for (unsigned i=0;i<bytes;++i) if (address+i>=0x80000000 && address+i<0x81000000) intersects=true;
        check(reserved->overlaps(address,bytes)==intersects);
    }
    vga_bytes.assign(vga_bytes.size(),std::byte{});
    check(reserved->begin()==0x80000000 && reserved->length()==0x1000000);
    // Retained identity and lease cannot be revived by a fresh acquisition.
    check(authority.revoke(*ticket)); check(!probe->page(authority));
    check(!probe->read_address(authority,current,0,8)); check(!grant->read_address(authority,current,0,8));
    check(!probe->finish(authority,current,cap,0x10400,0,0,0,0,0));
    const auto replacement=authority.acquire(); check(replacement.has_value());
    check(!probe->page(authority) && !probe->read_address(authority,current,8,4));
    check(!grant->read_address(authority,current,0,8));
    check(!edk2_probe->read_address(authority,edk2_snapshot,0x28,8));
    check(!edk2_grant->read_address(authority,edk2_snapshot,0,8));
    check(!NvmeBarProbe::authorize(copied,current,*bar,*root,0,map,40,0x400000,0xfee00000,authority,*ticket));
    auto fresh=NvmeBarProbe::authorize(copied,current,*bar,*root,0,map,40,0x400000,0xfee00000,authority,*replacement);
    check(fresh && fresh->read_address(authority,current,0,8)==base);
    // A deterministic independent state model checks interleaved acquisition,
    // copied grants, failed foreign revocation and repeated retirement.
    WindowAuthority model_authority,other_authority;
    std::optional<WindowTicket> live;
    std::vector<NvmeBarProbe> history;
    std::vector<unsigned> generations;
    unsigned generation=0,active=0; std::uint64_t random=0x1964f203;
    for (unsigned step=0;step<10000;++step) {
        random^=random<<13; random^=random>>7; random^=random<<17;
        switch (random%4) {
        case 0: {
            const auto acquired=model_authority.acquire(); check(acquired.has_value()==(active==0));
            if (acquired) {
                live=acquired; active=++generation;
                const auto accepted=NvmeBarProbe::authorize(copied,current,*bar,*root,0,map,40,0x400000,0xfee00000,model_authority,*acquired);
                check(accepted.has_value()); history.push_back(*accepted); generations.push_back(active);
            }
            break;
        }
        case 1: if (live) { check(model_authority.revoke(*live)==(active!=0)); active=0; } break;
        case 2: if (live) check(!other_authority.revoke(*live)); break;
        default: break;
        }
        if (!history.empty()) {
            const auto index=static_cast<std::size_t>(random%history.size());
            check(history[index].read_address(model_authority,current,0,8).has_value()==(active && generations[index]==active));
            check(!history[index].read_address(other_authority,current,0,8));
        }
    }
    std::cout << "PASS: " << checks << " PCI BAR descriptor, exclusion, exact-read, mutation and revocation checks\n";
}
