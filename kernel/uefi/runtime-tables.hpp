#pragma once
#include "runtime-layout.hpp"
#include <array>
#include <span>

namespace aurora::uefi {
// The caller exclusively lends table storage, separate from its physical base.
// Only the hardware adapter translates a physical allocation to this host span.
// Reset/reuse is allowed only while this root is inactive on every CPU.
class RuntimeTables final {
public:
    static constexpr std::uint64_t present=1;
    static constexpr std::uint64_t writable=2;
    static constexpr std::uint64_t user=4;
    static constexpr std::uint64_t nx=1ULL<<63;
    static constexpr std::uint64_t address_mask=0x000ffffffffff000ULL;
    static constexpr std::uint64_t accessed_dirty=0x60;
    static constexpr std::size_t words_per_page=512;
    static constexpr std::size_t max_pages=RuntimeLayout::table_pages;
private:
    std::span<std::uint64_t> storage_;
    std::uint64_t base_;
    std::size_t used_=0;
    [[nodiscard]] auto capacity() const -> std::size_t { return storage_.size()/words_per_page; }
    [[nodiscard]] static constexpr auto physical_page(std::uint64_t address) -> bool {
        return (address&~address_mask)==0;
    }
    [[nodiscard]] static constexpr auto leaf_flags(std::uint64_t flags) -> bool {
        return ((flags&present)!=0 && (flags&~(present|writable|user|nx))==0)
            || flags==(present|writable|nx|0x18); // Explicit supervisor UC MMIO; adapter supplies authority.
    }
    [[nodiscard]] auto table_index(std::uint64_t physical,std::size_t& index) const -> bool {
        if (!physical_page(physical) || physical<base_) return false;
        const auto delta=physical-base_;
        if (delta/RuntimeLayout::page_size>=used_) return false;
        index=static_cast<std::size_t>(delta/RuntimeLayout::page_size);
        return true;
    }
    [[nodiscard]] static auto parent_flags(std::uint64_t value) -> bool {
        const auto flags=value&~(address_mask|accessed_dirty);
        return flags==(present|writable) || flags==(present|writable|user);
    }
    template<class Expected>
    [[nodiscard]] auto inspect(Expected&& expected) const -> bool {
        if (!valid()) return false;
        std::array<bool,max_pages> visited{};
        const auto walk=[&](auto&& self,std::size_t table,unsigned level,std::uint64_t prefix,
                            bool& contains_user,bool& populated) -> bool {
            if (table>=used_ || visited[table]) return false;
            visited[table]=true;
            contains_user=false;
            populated=false;
            for (std::uint64_t slot=0;slot<words_per_page;++slot) {
                const auto raw=storage_[table*words_per_page+slot];
                if (raw==0) continue;
                const auto value=raw&~accessed_dirty;
                const auto address=prefix|(slot<<(12+9*level));
                if (level!=0) {
                    std::size_t child=0;
                    bool child_user=false;
                    bool child_populated=false;
                    if (!parent_flags(raw) || !table_index(value&address_mask,child)
                        || !self(self,child,level-1,address,child_user,child_populated)
                        || !child_populated
                        || ((value&user)!=0)!=child_user) return false;
                    contains_user=contains_user || child_user;
                    populated=true;
                } else {
                    const auto va=(address&(1ULL<<47))!=0 ? address|0xffff000000000000ULL : address;
                    if (!leaf_flags(value&~address_mask) || !expected(va,value)) return false;
                    contains_user=contains_user || (value&user)!=0;
                    populated=true;
                }
            }
            return true;
        };
        bool contains_user=false,populated=false;
        if (!walk(walk,0,3,0,contains_user,populated)) return false;
        for (std::size_t i=0;i<used_;++i) if (!visited[i]) return false;
        // Unallocated storage is scrubbed, including on construction and reuse.
        for (std::size_t i=used_*words_per_page;i<storage_.size();++i) if (storage_[i]!=0) return false;
        return true;
    }
public:
    RuntimeTables(std::span<std::uint64_t> storage,std::uint64_t physical_base)
        : storage_(storage),base_(physical_base) { (void)reset(); }
    RuntimeTables(const RuntimeTables&)=delete;
    auto operator=(const RuntimeTables&) -> RuntimeTables& = delete;
    RuntimeTables(RuntimeTables&&)=delete;
    auto operator=(RuntimeTables&&) -> RuntimeTables& = delete;
    [[nodiscard]] static constexpr auto canonical(std::uint64_t address) -> bool {
        return address<0x0000800000000000ULL || address>=0xffff800000000000ULL;
    }
    [[nodiscard]] auto valid() const -> bool {
        return used_!=0 && storage_.size()%words_per_page==0 && capacity()<=max_pages
            && used_<=capacity() && physical_page(base_)
            && capacity()*RuntimeLayout::page_size<=(1ULL<<52)-base_;
    }
    [[nodiscard]] auto reset() -> bool {
        for (auto& value : storage_) value=0;
        used_=0;
        if (storage_.empty() || storage_.size()%words_per_page!=0 || capacity()>max_pages
            || !physical_page(base_) || capacity()*RuntimeLayout::page_size>(1ULL<<52)-base_) return false;
        used_=1;
        return true;
    }
    [[nodiscard]] auto root() const -> std::uint64_t { return valid() ? base_ : 0; }
    [[nodiscard]] auto used() const -> std::size_t { return used_; }
    [[nodiscard]] auto map(std::uint64_t va,std::uint64_t physical,std::uint64_t flags) -> bool {
        if (!canonical(va) || va%RuntimeLayout::page_size!=0 || !physical_page(physical)
            || !leaf_flags(flags) || !inspect([](std::uint64_t,std::uint64_t) { return true; })) return false;
        std::array<std::size_t,3> parents{};
        std::size_t table=0,depth=0;
        // Preflight the complete path and allocation count before changing a bit.
        for (const auto shift : {39U,30U,21U}) {
            const auto at=table*words_per_page+((va>>shift)&511);
            parents[depth]=at;
            const auto link=storage_[at];
            if (link==0) {
                if (3-depth>capacity()-used_) return false;
                break;
            }
            if (!parent_flags(link) || !table_index(link&address_mask,table)) return false;
            ++depth;
        }
        if (depth==3 && storage_[table*words_per_page+((va>>12)&511)]!=0) return false;
        table=0;
        depth=0;
        for (const auto shift : {39U,30U,21U}) {
            const auto at=table*words_per_page+((va>>shift)&511);
            parents[depth++]=at;
            auto& link=storage_[at];
            if (link==0) link=(base_+used_++*RuntimeLayout::page_size)|present|writable;
            // All links and required capacity were checked above.
            table=static_cast<std::size_t>(((link&address_mask)-base_)/RuntimeLayout::page_size);
        }
        storage_[table*words_per_page+((va>>12)&511)]=physical|flags;
        if ((flags&user)!=0) for (const auto at : parents) storage_[at]|=user;
        return true;
    }
    [[nodiscard]] auto entry(std::uint64_t va) const -> std::uint64_t {
        if (!valid() || !canonical(va) || va%RuntimeLayout::page_size!=0) return 0;
        std::array<bool,max_pages> visited{};
        std::size_t table=0;
        bool user_path=true;
        for (const auto shift : {39U,30U,21U}) {
            if (visited[table]) return 0;
            visited[table]=true;
            const auto link=storage_[table*words_per_page+((va>>shift)&511)];
            if (!parent_flags(link) || !table_index(link&address_mask,table)) return 0;
            user_path=user_path && (link&user)!=0;
        }
        if (visited[table]) return 0;
        const auto leaf=storage_[table*words_per_page+((va>>12)&511)];
        if (!leaf_flags((leaf&~accessed_dirty)&~address_mask) || ((leaf&user)!=0 && !user_path)) return 0;
        return leaf;
    }
    // Checks every actual leaf, every link, and ownership of every allocated table.
    // The caller must also check its expected ranges with entry() to detect holes.
    // Deliberate physical leaf aliases (supervisor and user views) are policy-owned.
    template<class Expected>
    [[nodiscard]] auto verify(Expected&& expected) const -> bool {
        return inspect([&](std::uint64_t va,std::uint64_t value) { return expected(va)==value; });
    }
};
}
