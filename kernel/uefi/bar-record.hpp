#pragma once
#include "bar-policy.hpp"
namespace aurora::uefi {
// A read-only view of the owned, supervisor-RO handoff page. This view itself
// grants no access and must not outlive the caller's immutable backing storage.
class BarRecord final {
    std::span<const std::byte> bytes_;
public:
    explicit BarRecord(std::span<const std::byte> bytes) : bytes_(bytes) {}
    [[nodiscard]] auto valid() const -> bool {
        if (bytes_.size()!=4096) return false;
        const Bytes h{bytes_};
        return h.get(0)==0x3152414241525541ULL && h.get(8,4)==1 && h.get(12,4)==4096
            && h.get(16)==0 && h.get(24)==0 && h.get(32)==2 && h.get(40)==0 && h.get(48)==0
            && h.get(56)==48 && h.get(64)>=48 && h.get(64)<=738 && (h.get(64)-2)%46==0
            && h.get(72)==64 && h.get(88)<=8;
    }
    template<class Reader>
    [[nodiscard]] auto reservations(std::span<const PciFunction> functions,const PciResource& target,unsigned bits,Reader&& reader) const -> std::optional<unsigned> {
        if (!valid() || functions.empty() || functions.size()>PciInventory::maximum_functions) return std::nullopt;
        const Bytes record{bytes_}; const auto count=record.get(88);
        std::array<bool,8> seen{}; unsigned total=0,targets=0;
        for (std::size_t position=0;position<functions.size();++position) {
            const auto& function=functions[position];
            for (std::size_t prior=0;prior<position;++prior)
                if (functions[prior].segment==function.segment && functions[prior].bus==function.bus
                    && functions[prior].device==function.device && functions[prior].function==function.function) return std::nullopt;
            const auto raw=reader(function); if (!raw) return std::nullopt;
            const auto now=PciBarSnapshot::parse(function.segment,function.bus,function.device,function.function,*raw); if (!now) return std::nullopt;
            const Bytes header{*raw}; const auto kind=header.get(14,1)&127;
            if (header.get(0,2)!=function.vendor || header.get(2,2)!=function.device_id || header.get(4,2)!=function.command
                || header.get(9,1)!=function.programming_interface || header.get(10,1)!=function.subclass
                || header.get(11,1)!=function.class_code || kind!=function.header_type || kind>1) return std::nullopt;
            const bool is_target=function.segment==0 && function.bus==0 && function.device==2 && function.function==0;
            if (is_target) { if (!now->q35_nvme()) return std::nullopt; ++targets; }
            const unsigned slots=kind==0 ? 6 : 2;
            for (unsigned index=0;index<slots;++index) {
                const auto low=header.get(16+index*4,4); if (!low || (low&1)) continue;
                const auto type=(low>>1)&3;
                if ((type!=0 && type!=2) || (type==2 && index+1>=slots)) return std::nullopt;
                if (!(is_target && index==0)) {
                    unsigned matches=0;
                    for (unsigned candidate=0;candidate<count;++candidate) {
                        const auto bytes=bytes_.subspan(2048+candidate*256,256); const Bytes saved{bytes};
                        if (saved.get(0)!=function.segment || saved.get(8)!=function.bus || saved.get(16)!=function.device
                            || saved.get(24)!=function.function || saved.get(32)!=index) continue;
                        if (++matches!=1 || seen[candidate] || saved.get(40)!=48) return std::nullopt;
                        const auto prior=PciBarSnapshot::parse(function.segment,function.bus,function.device,function.function,bytes.subspan(64,64));
                        const auto reservation=prior ? PciBarReservation::parse_edk2(*prior,*now,index,bytes.subspan(128,48),bits) : std::nullopt;
                        if (!reservation || reservation->overlaps(target.begin(),target.length())) return std::nullopt;
                        seen[candidate]=true; ++total;
                    }
                    if (matches!=1) return std::nullopt;
                }
                if (type==2) ++index;
            }
        }
        return targets==1 && total==count ? std::optional<unsigned>{total} : std::nullopt;
    }
};
}
