#pragma once
#include "acpi-policy.hpp"
#include "../user-program.hpp"
#include <array>
#include <optional>
#include <span>

namespace aurora::uefi {
// An address in MADT is a description, not MMIO authority. This narrow grant
// combines the tested q35 resource contract with CPU and final-map evidence.
// It owns no mapped view and performs no CPUID, MSR, or hardware access.
class LocalApicAdmission final {
    const std::uint64_t arena_;
    const unsigned physical_bits_;
    const std::uint32_t apic_id_;

    constexpr LocalApicAdmission(std::uint64_t arena,unsigned bits,std::uint32_t id)
        : arena_(arena),physical_bits_(bits),apic_id_(id) {}
public:
    static constexpr std::uint64_t physical_address=0xfee00000;
    static constexpr std::uint64_t virtual_address=0xffff900000000000ULL;
    static constexpr std::uint64_t page_size=4096;
    static constexpr std::uint64_t leaf_flags=(1ULL<<63)|0x1b;
    static constexpr unsigned pat_index=3;
    static constexpr std::uint64_t timer_vector=64;

    [[nodiscard]] static auto authorize(const Topology& topology,
        std::span<const std::byte> map,std::size_t stride,std::uint32_t version,
        std::uint64_t arena,unsigned physical_bits,std::uint32_t cpuid_edx,
        std::uint32_t cpuid_ebx,std::uint64_t apic_base,std::uint64_t pat)
        -> std::optional<LocalApicAdmission> {
        constexpr auto required_features=(1U<<5)|(1U<<9)|(1U<<16); // MSR, APIC, PAT.
        if (physical_bits<32 || physical_bits>52 || !RuntimeLayout::valid(arena)
            || (cpuid_edx&required_features)!=required_features
            || ((cpuid_ebx>>16)&255)>1 || topology.apic()!=physical_address
            // Exact base, BSP and global-enable; x2APIC and reserved bits deny.
            || apic_base!=(physical_address|0x900)
            || ((pat>>(pat_index*8))&255)!=0) return std::nullopt;
        const auto limit=1ULL<<physical_bits;
        if (physical_address>limit-page_size || arena>limit-Handoff::arena_bytes
            || (arena<physical_address+page_size && physical_address<arena+Handoff::arena_bytes))
            return std::nullopt;
        const MemoryMap final_map{map,stride,version};
        if (!final_map.owns(arena,Handoff::arena_bytes)) return std::nullopt;
        const auto bsp_id=cpuid_ebx>>24;
        std::size_t enabled=0;
        for (const auto& processor:topology.processors()) {
            // Disabled and merely online-capable records do not add running CPUs.
            if (!processor.enabled) continue;
            if (++enabled!=1 || processor.extended || processor.id!=bsp_id) return std::nullopt;
        }
        if (enabled!=1) return std::nullopt;
        for (std::size_t at=0;at<map.size();at+=stride) {
            const Bytes descriptor{map.subspan(at,stride)};
            const auto begin=descriptor.get(8),end=begin+descriptor.get(24)*page_size;
            if (end>limit) return std::nullopt;
            if (begin>=physical_address+page_size || end<=physical_address) continue;
            const auto type=descriptor.get(0,4),attributes=descriptor.get(32);
            // A missing descriptor is allowed by this explicit q35 contract.
            // Described overlap must be reserved or MMIO, with only UC/XP
            // attributes. RAM, NV, runtime, other caching and protection deny.
            if ((type!=0 && type!=11) || (attributes&~(1ULL|0x4000ULL))) return std::nullopt;
        }
        return LocalApicAdmission{arena,physical_bits,bsp_id};
    }
    [[nodiscard]] constexpr auto owned_arena() const -> std::uint64_t { return arena_; }
    [[nodiscard]] constexpr auto physical_bits() const -> unsigned { return physical_bits_; }
    [[nodiscard]] constexpr auto apic_id() const -> std::uint32_t { return apic_id_; }
    [[nodiscard]] constexpr auto admits(std::uint64_t va,std::uint64_t pa,
        std::uint64_t bytes,std::uint64_t flags) const -> bool {
        return va==virtual_address && pa==physical_address && bytes==page_size && flags==leaf_flags;
    }
    [[nodiscard]] constexpr auto mapping(std::uint64_t va) const -> std::uint64_t {
        return va==virtual_address ? physical_address|leaf_flags : 0;
    }
    // Only call after the grant has authorized the sole MMIO mapping. Register
    // evidence completes hardware identification; it never broadens the grant.
    [[nodiscard]] constexpr auto matches_registers(std::uint32_t id,std::uint32_t version) const -> bool {
        const auto revision=version&255,max_lvt=(version>>16)&255;
        return id==(apic_id_<<24) && (version&~0x01ff00ffU)==0
            && revision>=0x10 && revision<=0x15 && max_lvt>=5 && max_lvt<=6;
    }
};

// Exact integer-only assembly snapshot. The mapper/dispatcher supplies a span
// only after establishing that its backing is readable supervisor RSP0 memory.
// Copying here prevents later mutation of either frame or caller-owned metadata.
// SIMD/FPU state is deliberately absent; the adapter must retain CR0.TS.
// Domain incarnation, active run and current root remain dispatcher obligations.
class ServiceContext final {
    const std::array<std::uint64_t,22> words_;
    const std::uint64_t frame_;
    const user::ProgramContract contract_;

    constexpr ServiceContext(std::array<std::uint64_t,22> words,std::uint64_t frame,
        const user::ProgramContract& contract) : words_(words),frame_(frame),contract_(contract) {}
    [[nodiscard]] static constexpr auto same_contract(const user::ProgramContract& left,
        const user::ProgramContract& right) -> bool {
        const auto& a=left.layout(); const auto& b=right.layout();
        return left.entry()==right.entry() && left.size()==right.size()
            && left.return_pc()==right.return_pc() && left.bounds_pc()==right.bounds_pc()
            && left.overflow_pc()==right.overflow_pc() && left.division_zero_pc()==right.division_zero_pc()
            && left.shift_count_pc()==right.shift_count_pc()
            && a.code_begin()==b.code_begin() && a.code_end()==b.code_end()
            && a.max_image_pages()==b.max_image_pages()
            && a.user_stack_bottom()==b.user_stack_bottom() && a.user_stack_top()==b.user_stack_top()
            && a.entry_stack_bottom()==b.entry_stack_bottom() && a.entry_stack_top()==b.entry_stack_top();
    }
    [[nodiscard]] static constexpr auto origin_valid(std::span<const std::uint64_t> words,
        std::uint64_t frame,const user::ProgramContract& contract) -> bool {
        if (words.size()!=word_count || !frame_valid(frame,contract)) return false;
        const auto& layout=contract.layout();
        const auto pc=words[17],flags=words[19],sp=words[20];
        return (words[15]==LocalApicAdmission::timer_vector || words[15]==129 || words[15]==6)
            && words[16]==0 && pc>=contract.entry() && pc-contract.entry()<contract.size()
            && words[18]==0x1b && words[21]==0x23 && (flags&0x202)==0x202
            && (flags&~allowed_flags)==0 && sp>=layout.user_stack_bottom()
            && sp<=layout.user_stack_top() && sp%8==0;
    }
public:
    static constexpr std::size_t word_count=22;
    static constexpr std::uint64_t byte_count=word_count*sizeof(std::uint64_t);
    static constexpr std::uint64_t allowed_flags=0x10ed7; // Arithmetic, bit1, IF, DF, RF only.
    static_assert(byte_count==user::ProgramLayout::fault_frame_size);

    [[nodiscard]] static constexpr auto frame_valid(std::uint64_t frame,
        const user::ProgramContract& contract) -> bool {
        if (!contract.valid()) return false;
        const auto& layout=contract.layout();
        return frame>=layout.entry_stack_bottom() && frame<=layout.entry_stack_top()
            && byte_count<=layout.entry_stack_top()-frame && frame%8==0;
    }
    [[nodiscard]] static auto capture(std::span<const std::uint64_t> words,
        std::uint64_t frame,const user::ProgramContract& contract) -> std::optional<ServiceContext> {
        if (!origin_valid(words,frame,contract)) return std::nullopt;
        std::array<std::uint64_t,word_count> copy{};
        for (std::size_t i=0;i<word_count;++i) copy[i]=words[i];
        return ServiceContext{copy,frame,contract};
    }
    [[nodiscard]] constexpr auto words() const -> const std::array<std::uint64_t,word_count>& { return words_; }
    [[nodiscard]] constexpr auto frame() const -> std::uint64_t { return frame_; }
    [[nodiscard]] constexpr auto valid_for(const user::ProgramContract& contract) const -> bool {
        return same_contract(contract_,contract) && origin_valid(words_,frame_,contract_);
    }
    [[nodiscard]] constexpr auto timer_frame(const user::ProgramContract& contract) const -> bool {
        return valid_for(contract) && words_[15]==LocalApicAdmission::timer_vector;
    }
    [[nodiscard]] auto terminal_context(const user::ProgramContract& contract) const
        -> std::optional<user::ProgramContext> {
        if (!valid_for(contract) || words_[15]==LocalApicAdmission::timer_vector) return std::nullopt;
        // Normalize only IF, after checking the complete original snapshot.
        // In particular, DF is preserved and the ordinary terminal contract
        // continues to reject it; IRQ resumption preserves every captured bit.
        return user::ProgramContext{words_[15],words_[16],words_[17],words_[18],words_[21],words_[20],
            words_[19]&~(1ULL<<9),frame_};
    }
    [[nodiscard]] auto terminal(const user::ProgramContract& contract) const -> user::ProgramEvent {
        const auto context=terminal_context(contract);
        return context ? contract.classify(*context) : user::ProgramEvent::rejected;
    }
};
}
