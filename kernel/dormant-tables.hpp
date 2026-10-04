#pragma once
#include "pin-ledger.hpp"
#include <span>
#include <limits>

#if defined(AURORA_DORMANT_TABLE_TESTING) && AURORA_DORMANT_TABLE_TESTING != 1
#error "Dormant-table test access requires explicit value1"
#endif
namespace aurora::memory {
#if defined(AURORA_DORMANT_TABLE_TESTING)
class DormantTableTestAccess;
#endif
// Trusted CPU-memory constructor only. Never installed in an IOMMU. The arena
// view is a kernel-supplied exclusive WB mapping; its virtual/physical relation,
// absence of incompatible aliases and lifetime are trusted adapter preconditions.
// No method accepts device completion, exports a base register or publishes bytes.
class DormantTables final {
#if defined(AURORA_DORMANT_TABLE_TESTING)
    friend class DormantTableTestAccess;
#endif
    static constexpr std::uint64_t page_size = 4096;
    static constexpr std::uint64_t denied = 3;
    static constexpr std::uint64_t read_bit = std::uint64_t{1} << 61;
    static constexpr std::uint64_t write_bit = std::uint64_t{1} << 62;
    static constexpr std::size_t target_rid = 16;
    PinLedger& ledger_;
    std::span<std::byte> arena_;
    std::uint64_t arena_base_;
    std::array<std::optional<PinHandle>,3> groups_{};
    std::array<std::uint64_t,5> pages_{};
    std::array<std::uint64_t,2> iovas_{};
    std::array<bool,2> writable_{};
    user::DomainHandle owner_{};
    std::size_t data_count_{};
    std::uint8_t physical_bits_{};
    bool bound_{};
    bool sealed_{};

    [[nodiscard]] auto owner_live(user::DomainHandle supplied) const -> bool {
        const auto actual=ledger_.registry_.index(owner_);
        const auto candidate=ledger_.registry_.index(supplied);
        return actual && candidate && *actual==*candidate;
    }
    [[nodiscard]] auto page_admitted(std::uint64_t pa) const -> bool {
        if (physical_bits_<32 || physical_bits_>52 || pa%page_size!=0
            || pa<arena_base_ || arena_base_%page_size!=0
            || arena_.size()%page_size!=0 || arena_.size()<page_size
            || arena_base_>UINT64_MAX-arena_.size()) return false;
        const auto limit=std::uint64_t{1}<<physical_bits_;
        return pa<=limit-page_size && pa-arena_base_<=arena_.size()-page_size;
    }
    [[nodiscard]] auto page(std::size_t index) const -> std::span<std::byte> {
        if(index>=pages_.size() || !page_admitted(pages_[index])) return {};
        return arena_.subspan(static_cast<std::size_t>(pages_[index]-arena_base_),page_size);
    }
    [[nodiscard]] auto ownership() -> bool {
        if (!bound_ || ledger_.busy_ || !owner_live(owner_) || !ledger_.validate_ownership()) return false;
        std::size_t physical_index=0;
        for(std::size_t group=0;group<groups_.size();++group) {
            if(!groups_[group]) return false;
            const auto* entry=ledger_.find(*groups_[group],owner_);
            const auto expected=group==0 ? 2U : (group==1 ? 1U : data_count_);
            if(!entry || entry->state!=PinLedger::State::reserved || entry->count!=expected) return false;
            for(std::size_t i=0;i<expected;++i) {
                const auto pa=entry->pages[i] ? ledger_.pool_.address(*entry->pages[i]) : std::nullopt;
                if(!pa || *pa!=pages_[physical_index] || !page_admitted(*pa)) return false;
                for(std::size_t earlier=0;earlier<physical_index;++earlier)
                    if(pages_[earlier]==*pa) return false;
                ++physical_index;
            }
        }
        return pages_[0]<=UINT64_MAX-page_size && pages_[1]==pages_[0]+page_size;
    }
    static auto put(std::span<std::byte> bytes,std::size_t offset,std::uint64_t word) -> void {
        for(std::size_t b=0;b<8;++b) bytes[offset+b]=std::byte((word>>(b*8))&255);
    }
    [[nodiscard]] static auto get(std::span<const std::byte> bytes,std::size_t offset) -> std::uint64_t {
        std::uint64_t word=0;
        for(std::size_t b=0;b<8;++b) word|=std::uint64_t(std::to_integer<unsigned char>(bytes[offset+b]))<<(b*8);
        return word;
    }
    [[nodiscard]] auto dte_word(std::size_t rid,std::size_t word) const -> std::uint64_t {
        if(rid!=target_rid) return word==0 ? denied : 0;
        if(word==0) return pages_[2]|read_bit|write_bit|0x203;
        return word==1 ? 1 : 0;
    }
    [[nodiscard]] auto leaf_word(std::size_t index) const -> std::uint64_t {
        for(std::size_t n=0;n<data_count_;++n)
            if(index==iovas_[n]/page_size) return pages_[3+n]|read_bit|(writable_[n]?write_bit:0)|1;
        return 0;
    }
    [[nodiscard]] auto bytes_match() const -> bool {
        for(std::size_t rid=0;rid<256;++rid) {
            const auto bytes=page(rid/128);
            if(bytes.size()!=page_size) return false;
            for(std::size_t word=0;word<4;++word)
                if(get(bytes,(rid%128)*32+word*8)!=dte_word(rid,word)) return false;
        }
        const auto root=page(2);
        if(root.size()!=page_size) return false;
        for(std::size_t index=0;index<512;++index)
            if(get(root,index*8)!=leaf_word(index)) return false;
        return true;
    }
    // Used for failed preparation too. No published state exists in this class.
    [[nodiscard]] auto release() -> bool {
        sealed_=false;
        bool complete=true;
        for(auto& handle:groups_) if(handle) {
            if(ledger_.cancel(*handle,owner_)) handle.reset();
            else complete=false; // Retain bookkeeping for quarantine/stale state.
        }
        if(complete) {
            bound_=false; pages_={};iovas_={};writable_={};owner_={};data_count_=0;physical_bits_=0;
        }
        return complete;
    }
public:
    DormantTables(PinLedger& ledger,std::span<std::byte> arena,std::uint64_t arena_base)
        :ledger_(ledger),arena_(arena),arena_base_(arena_base) {}
    ~DormantTables()=default; // Never releases or recovers quarantined pages.
    DormantTables(const DormantTables&)=delete;
    auto operator=(const DormantTables&)->DormantTables& = delete;
    DormantTables(DormantTables&&)=delete;
    auto operator=(DormantTables&&)->DormantTables& = delete;

    // Kernel-selected construction request. Scalars convey no device identity,
    // buffer address, completion, callback or activation authority.
    [[nodiscard]] auto prepare(user::DomainHandle owner,std::uint8_t physical_bits,
                               std::span<const std::uint64_t> iovas,
                               std::span<const bool> writable) -> bool {
        if(bound_ || ledger_.busy_ || !ledger_.registry_.index(owner)
            || iovas.empty() || iovas.size()>2 || writable.size()!=iovas.size()
            || physical_bits<32 || physical_bits>52) return false;
        for(std::size_t i=0;i<iovas.size();++i) {
            if(iovas[i]%page_size!=0 || iovas[i]>=0x200000) return false;
            for(std::size_t j=0;j<i;++j) if(iovas[j]==iovas[i]) return false;
        }
        owner_=owner;physical_bits_=physical_bits;data_count_=iovas.size();bound_=true;
        for(std::size_t i=0;i<data_count_;++i){iovas_[i]=iovas[i];writable_[i]=writable[i];}
        std::size_t pi=0;
        for(std::size_t g=0;g<groups_.size();++g) {
            const auto count=g==0 ? 2U : (g==1 ? 1U : data_count_);
            groups_[g]=ledger_.grant(owner,count);
            if(!groups_[g]) {static_cast<void>(release());return false;}
            const auto* entry=ledger_.find(*groups_[g],owner);
            if(!entry) {static_cast<void>(release());return false;}
            for(std::size_t n=0;n<count;++n) {
                const auto pa=ledger_.pool_.address(*entry->pages[n]);
                if(!pa){static_cast<void>(release());return false;}
                pages_[pi++]=*pa;
            }
        }
        if(!ownership()) {static_cast<void>(release());return false;}
        {
            // This synchronous trusted operation never calls a client callback.
            const PinLedger::Mutation mutation(ledger_.busy_);
            for(std::size_t i=0;i<3+data_count_;++i)
                for(auto& byte:page(i)) byte=std::byte{0};
            for(std::size_t rid=0;rid<256;++rid)
                for(std::size_t word=0;word<4;++word)
                    put(page(rid/128),(rid%128)*32+word*8,dte_word(rid,word));
            for(std::size_t index=0;index<512;++index) put(page(2),index*8,leaf_word(index));
        }
        if(!ownership() || !bytes_match()) {static_cast<void>(release());return false;}
        sealed_=true;
        return true;
    }
    [[nodiscard]] auto validate(user::DomainHandle owner) -> bool {
        return sealed_ && owner_live(owner) && ownership() && bytes_match();
    }
    [[nodiscard]] auto cancel(user::DomainHandle owner) -> bool {
        if(!bound_ || !owner_live(owner) || ledger_.busy_) return false;
        return release();
    }
};
}
