#pragma once
#include "handoff.hpp"
#include <array>
namespace aurora::uefi {
inline auto expected_flags(std::uint64_t offset,const Bytes& h) -> std::uint64_t;
class PageTables final {
    std::uint64_t base_;
    std::size_t used_=1;
    [[nodiscard]] auto table(std::uint64_t physical) const -> std::uint64_t* {
        return reinterpret_cast<std::uint64_t*>(physical);
    }
public:
    static constexpr std::uint64_t nx=1ULL<<63;
    explicit PageTables(std::uint64_t base,std::size_t used=1) : base_(base),used_(used) {}
    [[nodiscard]] auto used() const -> std::size_t { return used_; }
    [[nodiscard]] auto map(std::uint64_t page,std::uint64_t flags) -> bool {
        if (page%4096 || page>=0x100000000ULL || (flags!=1 && flags!=(1|nx) && flags!=(3|nx))) return false;
        auto current=base_;
        for (const auto shift : {39U,30U,21U}) {
            auto& entry=table(current)[(page>>shift)&511];
            if (entry==0) {
                if (used_==Handoff::table_pages) return false;
                entry=(base_+used_++*4096)|3;
            }
            current=entry&0x000ffffffffff000ULL;
            if (current<base_ || current>=base_+used_*4096) return false;
        }
        auto& leaf=table(current)[(page>>12)&511];
        if (leaf!=0) return false;
        leaf=page|flags; return true;
    }
    [[nodiscard]] auto verify(std::uint64_t arena,const Bytes& h) const -> bool {
        if (used_==0 || used_>Handoff::table_pages || base_!=arena+Handoff::tables_offset) return false;
        std::array<bool,Handoff::table_pages> visited{};
        const auto walk=[&](auto&& self,std::uint64_t physical,unsigned level,std::uint64_t prefix) -> bool {
            if (physical<base_ || physical>=base_+used_*4096 || physical%4096) return false;
            const auto slot=(physical-base_)/4096;
            if (visited[slot]) return false;
            visited[slot]=true;
            for (std::uint64_t i=0;i<512;++i) {
                const auto value=table(physical)[i]&~0x60ULL;
                if (!value) continue;
                const auto address=prefix|(i<<(12+9*level));
                if (level!=0) {
                    if ((value&~0x000ffffffffff000ULL)!=3
                        || !self(self,value&0x000ffffffffff000ULL,level-1,address)) return false;
                } else {
                    if (address<arena || address>=arena+Handoff::arena_bytes) return false;
                    const auto flags=expected_flags(address-arena,h);
                    if (!flags || value!=(address|flags)) return false;
                }
            }
            return true;
        };
        if (!walk(walk,base_,3,0)) return false;
        for (std::size_t i=0;i<used_;++i) if (!visited[i]) return false;
        for (std::uint64_t offset=0;offset<Handoff::arena_bytes;offset+=4096) {
            const auto flags=expected_flags(offset,h);
            const auto expected=flags ? (arena+offset)|flags : 0;
            if ((entry(arena+offset)&~0x60ULL)!=expected) return false;
        }
        return true;
    }
    [[nodiscard]] auto entry(std::uint64_t page) const -> std::uint64_t {
        auto current=base_;
        for (const auto shift : {39U,30U,21U}) {
            const auto link=table(current)[(page>>shift)&511];
            if ((link&~0x000ffffffffff060ULL)!=3) return 0;
            current=link&0x000ffffffffff000ULL;
            if (current<base_ || current>=base_+used_*4096) return 0;
        }
        return table(current)[(page>>12)&511];
    }
};
inline auto expected_flags(std::uint64_t offset,const Bytes& h) -> std::uint64_t {
    if (offset==0 || (offset>=Handoff::map_offset && offset<Handoff::tables_offset)) return 1|PageTables::nx;
    if ((offset>=Handoff::tables_offset && offset<Handoff::tables_offset+Handoff::table_pages*4096)
        || offset==Handoff::idt_offset || (offset>=Handoff::stack_bottom && offset<Handoff::stack_top)
        || (offset>=Handoff::pool_offset && offset<Handoff::pool_offset+16*4096)) return 3|PageTables::nx;
    if (offset==Handoff::transition_offset) return 1;
    if (offset>=Handoff::payload_offset && offset<Handoff::payload_offset+h.get(80)) {
        const auto relative=offset-Handoff::payload_offset;
        return relative<h.get(64) ? 1 : relative<h.get(72) ? 1|PageTables::nx : 3|PageTables::nx;
    }
    return 0;
}
}
