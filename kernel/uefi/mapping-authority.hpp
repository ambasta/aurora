#pragma once
#include "kernel-space.hpp"

namespace aurora::uefi {
// Privileged physical effects of one retained MemoryManager. The source owns
// policy and all mutable ledgers; this issuer retains only immutable boot facts,
// source-field offsets admitted against emitted ABI facts, and an operation scope.
class MappingAuthority final {
public:
    using U64 = std::uint64_t;
    enum class Domain : U64 {
        slot0 = 0,
        slot1 = 1,
        snapshot = 2,
        global = 3
    };
    class SharedEvidence final {
    public:
        std::array<U64, 256> upper{};
        std::array<U64, 2> slot{}, entry{};
        U64 slots = 0, reserved_first = 0, reserved_end = 0;
    };
    // The complete named field order is independently matched to compiler facts
    // before this image is admitted. These are not caller-supplied offsets.
    static constexpr std::size_t root_bytes = 496, slot0_offset = 160, slot_stride = 104;
    static constexpr std::size_t snapshot_offset = 368, staged_offset = 472, active_offset = 480,
                                 operation_offset = 488;
    static constexpr U64 reservation_words = 2 * process::memory_records * 3;
    static constexpr U64 stage_base = reservation_words + 396, stage_limit = 19;
    static constexpr U64 snapshot_base = KernelSpace::extension + (U64{2} << 30);
    static constexpr U64 invalid = ~U64{0}, count_mask = U64{1023} << 4;

private:
    words::Binding *binding_ = nullptr;
    KernelSpace *space_ = nullptr;
    const frames::Ranges *ranges_ = nullptr;
    SharedEvidence shared_{};
    U64 physical_limit_ = 0, kernel_root_ = 0;
    Domain domain_ = Domain::global;
    U64 expected_epoch_ = 0;
    bool scoped_ = false, beginning_ = false, parser_pinned_ = false;
    enum class SourceKind {
        none,
        boot,
        snapshot,
        arguments,
        chunk
    };
    SourceKind source_kind_ = SourceKind::none;
    const std::byte *source_ = nullptr;
    U64 source_bytes_ = 0, source_epoch_ = 0, source_ticket_ = 0, boot_bytes_ = 0;
    static inline MappingAuthority *owner_ = nullptr;
    static void require(bool condition) {
        if (!condition)
            words::fail();
    }
    [[nodiscard]] static auto bound(MappingAuthority &authority) -> words::Binding & {
        require(authority.binding_ && owner_ == &authority);
        return *authority.binding_;
    }
    [[nodiscard]] auto scalar(std::size_t offset) const -> U64 {
        require(binding_ && offset % sizeof(U64) == 0 && offset <= binding_->root_bytes_ - sizeof(U64));
        U64 value;
        __builtin_memcpy(&value, binding_->root_ + offset, sizeof(value));
        return value;
    }
    [[nodiscard]] auto bank(std::size_t number, U64 index) const -> U64 {
        require(number < binding_->bank_count_ && binding_->banks_[number].live &&
                index < binding_->banks_[number].count);
        return binding_->banks_[number].backing[index];
    }
    auto scratch(U64 index, U64 value) -> void {
        require(binding_->banks_[3].live && binding_->banks_[3].count == 512 && index < 512);
        binding_->banks_[3].backing[index] = value;
    }
    [[nodiscard]] static auto current_root() -> U64 {
        U64 value;
        asm volatile("mov %%cr3, %0" : "=r"(value));
        return value;
    }
    [[nodiscard]] static auto interrupts_off() -> bool {
        U64 value;
        asm volatile("pushfq; popq %0" : "=r"(value));
        return (value & (U64{1} << 9)) == 0;
    }
    static auto invalidate(U64 address) -> void {
        asm volatile("invlpg (%0)" : : "r"(address) : "memory");
    }
    static auto flush() -> void {
        const U64 root = current_root();
        asm volatile("mov %0, %%cr3" : : "r"(root) : "memory");
    }
    [[nodiscard]] auto offset(U64 domain) const -> std::size_t {
        require(domain <= 2);
        return domain == 2 ? snapshot_offset : slot0_offset + domain * slot_stride;
    }
    [[nodiscard]] auto selected() const -> U64 {
        const auto selected = scalar(active_offset);
        require(selected <= 2 && (domain_ == Domain::global || selected == static_cast<U64>(domain_)));
        const auto at = offset(selected);
        const auto phase = scalar(at + 16), epoch = scalar(at + 8);
        require(phase >= 1 && phase <= 3 && epoch && scalar(at) >= frames::first_owner);
        if (domain_ != Domain::global)
            require(epoch == expected_epoch_ + (beginning_ ? 1 : 0));
        const U64 root_ticket = scalar(at + 24);
        // During the first staged root allocation there is no published root
        // identity yet. Every later effect authenticates its canonical generation.
        if (root_ticket || phase != 1) {
            const U64 index = root_ticket & 0xffffffff, record = bank(0, index);
            require((root_ticket >> 60) == 0 && frames::state(record) == 2 &&
                    frames::generation(record) == root_ticket >> 32 && frames::word(record) == scalar(at) &&
                    bank(1, index) == (selected == 2 ? snapshot_base | 5 : 12));
        }
        return selected;
    }
    class Frame final {
    public:
        U64 index, physical, mapping;
    };
    [[nodiscard]] auto frame(U64 ticket) const -> Frame {
        require((ticket >> 60) == 0);
        const U64 index = ticket & 0xffffffff, generation = ticket >> 32;
        const U64 record = bank(0, index);
        const auto domain = selected();
        require(frames::state(record) == static_cast<U64>(frames::State::allocated) &&
                frames::generation(record) == generation && frames::word(record) == scalar(offset(domain)));
        const auto physical = ranges_->address(index);
        require(physical && *physical < physical_limit_ && *physical % frames::page == 0);
        return {index, *physical, bank(1, index)};
    }
    [[nodiscard]] auto staged(U64 ticket) const -> U64 {
        const U64 count = scalar(staged_offset);
        require(count <= stage_limit);
        for (U64 index = 0; index < count; ++index)
            if (bank(2, stage_base + index * 2) == ticket)
                return bank(2, stage_base + index * 2 + 1);
        fail();
    }
    [[noreturn]] static auto fail() -> void {
        words::fail();
    }
    class Table final {
    public:
        Frame frame;
        U64 level, prefix;
        bool snapshot;
    };
    [[nodiscard]] auto table(U64 ticket) const -> Table {
        const auto value = frame(ticket);
        const U64 tag = value.mapping & 15;
        if (tag >= 9 && tag <= 12) {
            require(selected() < 2);
            const U64 level = tag - 8, prefix = value.mapping & ~U64{16383};
            require(((value.mapping & count_mask) >> 4) <= 512 && prefix < (U64{1} << 47) &&
                    (level == 4 ? prefix == 0 : prefix % (U64{1} << (12 + 9 * level)) == 0));
            if (level == 4)
                require(scalar(offset(selected()) + 24) == ticket);
            return {value, level, prefix, false};
        }
        require(selected() == 2 && (tag == 4 || tag == 5));
        const U64 prefix = value.mapping & ~U64{4095};
        require((tag == 5 && value.mapping == (snapshot_base | 5)) ||
                (tag == 4 && prefix >= snapshot_base && prefix < snapshot_base + (U64{1} << 26) &&
                 prefix % (U64{1} << 21) == 0 && value.mapping == (prefix | 4)));
        return {value, tag == 5 ? U64{2} : U64{1}, prefix, true};
    }
    [[nodiscard]] static auto address(const Table &table, U64 slot) -> U64 {
        require(slot < 512);
        return table.prefix + (slot << (12 + 9 * (table.level - 1)));
    }
    [[nodiscard]] auto shared_value(const Table &table, U64 slot) const -> std::optional<U64> {
        if (table.snapshot)
            return std::nullopt;
        if (table.level == 4 && slot >= 256)
            return shared_.upper[slot - 256];
        if (table.level == 2)
            for (U64 index = 0; index < shared_.slots; ++index)
                if (shared_.slot[index] == address(table, slot))
                    return shared_.entry[index];
        return std::nullopt;
    }
    [[nodiscard]] auto legal_entry(const Table &table, U64 slot, U64 value) const -> bool {
        if (!value)
            return true;
        if (const auto shared = shared_value(table, slot))
            return (value & ~KernelSpace::hardware_bits) == (*shared & ~KernelSpace::hardware_bits);
        const U64 physical = value & KernelSpace::address_mask;
        if (physical >= physical_limit_ || !physical || !(value & 1))
            return false;
        const U64 flags = value & ~KernelSpace::address_mask & ~KernelSpace::hardware_bits;
        if (table.snapshot)
            return table.level == 2 ? flags == KernelSpace::table_flags
                                    : flags == KernelSpace::data_flags || flags == KernelSpace::read_flags;
        if (table.level == 4 && slot >= 256)
            return false;
        if (table.level > 1)
            return flags == 7;
        const auto va = address(table, slot);
        return va < (U64{1} << 47) && !(va >= shared_.reserved_first && va < shared_.reserved_end) &&
               (flags == process::leaf_read || flags == process::leaf_write || flags == process::leaf_execute);
    }
    auto authenticate_child(const Table &parent, U64 slot, U64 value, U64 ticket) const -> void {
        require(!shared_value(parent, slot) && legal_entry(parent, slot, value) && value);
        const auto child = frame(ticket);
        require((value & KernelSpace::address_mask) == child.physical);
        const auto va = address(parent, slot);
        const auto expected =
            parent.snapshot ? va | (parent.level == 1 ? 3 : 4) : va | (parent.level == 1 ? 1 : 8 + parent.level - 1);
        const U64 mask = !parent.snapshot && parent.level > 1 ? ~count_mask : ~U64{0};
        require((child.mapping & mask) == expected);
        if (parent.level > 1 && !parent.snapshot)
            require(((child.mapping & count_mask) >> 4) <= 512);
    }
    auto invalidate_translation(const Table &parent, U64 slot) const -> void {
        if (parent.snapshot) {
            invalidate(address(parent, slot));
            return;
        }
        const auto selected_slot = selected();
        const auto root_ticket = scalar(offset(selected_slot) + 24);
        const auto root = frame(root_ticket);
        const auto current = current_root();
        if (current == root.physical)
            invalidate(address(parent, slot));
        else
            // The supported kernel has no PCID/global user mappings. A real
            // flushing CR3 switch preceded any operation on this inactive root.
            require(current == kernel_root_);
    }
    [[nodiscard]] static auto admitted(const void *token, U64 epoch, bool state = true) -> MappingAuthority & {
        auto &binding = words::Binding::admitted_authority(token, epoch);
        require(owner_ && owner_->binding_ == &binding && owner_->scoped_ && owner_->space_->closed() &&
                interrupts_off() && owner_->accessible_root(current_root()));
        if (state) {
            require(owner_->scalar(operation_offset) == 1 || owner_->scalar(operation_offset) == 2);
            static_cast<void>(owner_->selected());
        }
        return *owner_;
    }
    auto mutation() const -> void {
        require(scalar(operation_offset) == 1);
        const auto domain = selected();
        const auto current = current_root();
        if (current == kernel_root_)
            return;
        // Reject a mismatched address space before opening any physical window.
        // INVLPG under some other live root cannot invalidate this translation.
        require(domain < 2 && scalar(offset(domain) + 16) == 2);
        const U64 root_ticket = scalar(offset(domain) + 24);
        const auto physical = ranges_->address(root_ticket & 0xffffffff);
        require(physical.has_value() && *physical == current);
    }
    auto pin_ready() const -> void {
        require(binding_ && owner_ == this && binding_->live_ && binding_->attached_ && !words::Binding::current_ &&
                !scoped_ && !parser_pinned_ && source_kind_ == SourceKind::none && space_->closed() &&
                interrupts_off() && current_root() == kernel_root_ && binding_->identity());
    }
    auto validate_snapshot_identity(U64 epoch) const -> void {
        const U64 ticket = scalar(snapshot_offset + 24), index = ticket & 0xffffffff;
        const U64 record = bank(0, index);
        const auto directory = ranges_->address(index);
        require(epoch && scalar(snapshot_offset + 8) == epoch && scalar(snapshot_offset + 16) == 2 &&
                scalar(snapshot_offset + 32) != 0 && scalar(snapshot_offset + 32) <= (U64{1} << 26) &&
                (ticket >> 60) == 0 && directory.has_value() && *directory < physical_limit_ &&
                frames::state(record) == 2 && frames::word(record) == scalar(snapshot_offset) &&
                frames::generation(record) == ticket >> 32 && bank(1, index) == (snapshot_base | 5) &&
                (KernelSpace::table_view(0)[2] & ~KernelSpace::hardware_bits) ==
                    (*directory | KernelSpace::table_flags));
    }
    auto validate_snapshot_source(U64 first, U64 count) const -> void {
        require(source_kind_ == SourceKind::snapshot && scalar(snapshot_offset + 8) == source_epoch_ &&
                scalar(snapshot_offset + 16) == 2 && scalar(snapshot_offset + 24) == source_ticket_ &&
                source_bytes_ == scalar(snapshot_offset + 32));
        const U64 owner = scalar(snapshot_offset), index = source_ticket_ & 0xffffffff;
        const U64 record = bank(0, index);
        const auto directory = ranges_->address(index);
        require((source_ticket_ >> 60) == 0 && directory.has_value() && frames::state(record) == 2 &&
                frames::word(record) == owner && frames::generation(record) == source_ticket_ >> 32 &&
                bank(1, index) == (snapshot_base | 5) &&
                (KernelSpace::table_view(0)[2] & ~KernelSpace::hardware_bits) ==
                    (*directory | KernelSpace::table_flags));
        for (U64 at = first; at < first + count;) {
            const U64 page = at / frames::page;
            auto *view = space_->open(*directory);
            require(view);
            const U64 parent = reinterpret_cast<volatile U64 *>(view)[page / 512];
            space_->close();
            require((parent & ~KernelSpace::address_mask & ~KernelSpace::hardware_bits) == KernelSpace::table_flags);
            const auto table = ranges_->index(parent & KernelSpace::address_mask);
            require(table.has_value());
            const U64 table_record = bank(0, *table);
            require(frames::state(table_record) == 2 && frames::word(table_record) == owner &&
                    bank(1, *table) == ((snapshot_base + (page / 512) * (U64{1} << 21)) | 4));
            view = space_->open(parent & KernelSpace::address_mask);
            require(view);
            const U64 leaf = reinterpret_cast<volatile U64 *>(view)[page % 512];
            space_->close();
            require((leaf & ~KernelSpace::address_mask & ~KernelSpace::hardware_bits) == KernelSpace::read_flags);
            const auto data = ranges_->index(leaf & KernelSpace::address_mask);
            require(data.has_value());
            const U64 data_record = bank(0, *data);
            require(frames::state(data_record) == 2 && frames::word(data_record) == owner &&
                    bank(1, *data) == ((snapshot_base + page * frames::page) | 3));
            at = (page + 1) * frames::page;
        }
    }

public:
    MappingAuthority() = default;
    MappingAuthority(const MappingAuthority &) = delete;
    auto operator=(const MappingAuthority &) -> MappingAuthority & = delete;
    [[nodiscard]] auto attach(words::Binding &binding,
                              KernelSpace &space,
                              const frames::Ranges &ranges,
                              const SharedEvidence &shared,
                              U64 physical_bits,
                              U64 kernel_root) -> bool {
        if (binding_ || owner_ || !binding.live_ || !binding.attached_ || !binding.identity() ||
            binding.root_bytes_ != root_bytes || binding.bank_count_ != 4 || !binding.has_authority_ ||
            binding.authority_offset_ != 64 || binding.banks_[0].count != ranges.frames() ||
            binding.banks_[1].count != ranges.frames() || binding.banks_[2].count != reservation_words + 512 ||
            binding.banks_[3].count != 512 || physical_bits < 36 || physical_bits > 52 || shared.slots > 2 ||
            !space.closed() || !interrupts_off() || current_root() != kernel_root || kernel_root % frames::page)
            return false;
        for (std::size_t bank = 0; bank < 4; ++bank)
            if (binding.banks_[bank].field_offset != bank * 16)
                return false;
        std::array<words::Binding::Backing, 4> backing{};
        for (std::size_t index = 0; index < backing.size(); ++index)
            backing[index] = {binding.banks_[index].backing, binding.banks_[index].count};
        if (!space.owns_banks(backing, ranges.frames()))
            return false;
        binding_ = &binding;
        space_ = &space;
        ranges_ = &ranges;
        shared_ = shared;
        physical_limit_ = U64{1} << physical_bits;
        kernel_root_ = kernel_root;
        owner_ = this;
        return true;
    }
    [[nodiscard]] auto attached() const -> bool {
        return binding_ != nullptr;
    }
    [[nodiscard]] auto empty_epoch(Domain domain) const -> U64 {
        pin_ready();
        require(domain != Domain::global);
        const auto at = offset(static_cast<U64>(domain));
        require(scalar(at + 16) == 0);
        return scalar(at + 8);
    }
    auto attach_boot_volume(std::span<const std::byte> volume) -> void {
        require(binding_ && !scoped_ && !parser_pinned_ && source_kind_ == SourceKind::none && !boot_bytes_ &&
                reinterpret_cast<std::uintptr_t>(volume.data()) == KernelSpace::volume_base &&
                space_->volume(volume.size()).size() == volume.size());
        boot_bytes_ = volume.size();
    }
    // Native-only bounded input pin. No source constructor, pointer conversion,
    // or callback is admitted. Each physical copy rechecks its source identity.
    class SourcePin final {
        MappingAuthority &authority_;
        friend class MappingAuthority;
        SourcePin(MappingAuthority &authority, SourceKind kind, std::span<const std::byte> bytes, U64 epoch)
            : authority_(authority) {
            authority.pin_ready();
            if (kind == SourceKind::arguments || kind == SourceKind::chunk) {
                const auto first = reinterpret_cast<std::uintptr_t>(bytes.data());
                require(first && bytes.size() <= std::numeric_limits<std::uintptr_t>::max() - first &&
                        words::Binding::disjoint(first,
                                                 bytes.size(),
                                                 reinterpret_cast<std::uintptr_t>(authority.binding_->root_),
                                                 authority.binding_->root_bytes_) &&
                        words::Binding::disjoint(first, bytes.size(), KernelSpace::window_base, frames::page));
                for (std::size_t index = 0; index < 4; ++index)
                    require(words::Binding::disjoint(
                        first,
                        bytes.size(),
                        reinterpret_cast<std::uintptr_t>(authority.binding_->banks_[index].backing),
                        authority.binding_->banks_[index].count * sizeof(U64)));
            }
            authority.source_kind_ = kind;
            authority.source_ = bytes.data();
            authority.source_bytes_ = bytes.size();
            authority.source_epoch_ = epoch;
            authority.source_ticket_ = kind == SourceKind::snapshot ? authority.scalar(snapshot_offset + 24) : 0;
        }

    public:
        SourcePin(const SourcePin &) = delete;
        SourcePin(SourcePin &&) = delete;
        ~SourcePin() {
            require(!authority_.scoped_ && !authority_.parser_pinned_ && authority_.space_->closed());
            authority_.source_kind_ = SourceKind::none;
            authority_.source_ = nullptr;
            authority_.source_bytes_ = authority_.source_epoch_ = authority_.source_ticket_ = 0;
        }
    };
    [[nodiscard]] auto boot_source(std::span<const std::byte> bytes) -> SourcePin {
        const auto first = reinterpret_cast<std::uintptr_t>(bytes.data());
        require(first >= KernelSpace::volume_base && first - KernelSpace::volume_base <= boot_bytes_ &&
                bytes.size() <= boot_bytes_ - (first - KernelSpace::volume_base));
        return SourcePin(*this, SourceKind::boot, bytes, 0);
    }
    [[nodiscard]] auto snapshot_source(U64 epoch) -> SourcePin {
        pin_ready();
        validate_snapshot_identity(epoch);
        return SourcePin(*this,
                         SourceKind::snapshot,
                         {reinterpret_cast<const std::byte *>(snapshot_base), scalar(snapshot_offset + 32)},
                         epoch);
    }
    [[nodiscard]] auto arguments_source(std::span<const std::byte> bytes) -> SourcePin {
        require(!bytes.empty() && bytes.size() <= 65536);
        return SourcePin(*this, SourceKind::arguments, bytes, 0);
    }
    [[nodiscard]] auto loader_chunk_source(std::span<const std::byte> bytes, U64 epoch) -> SourcePin {
        pin_ready();
        require(!bytes.empty() && bytes.size() <= 65536 && epoch && scalar(snapshot_offset + 8) == epoch &&
                scalar(snapshot_offset + 16) == 1);
        return SourcePin(*this, SourceKind::chunk, bytes, epoch);
    }
    class SnapshotReadPin final {
        MappingAuthority &authority_;
        U64 epoch_;
        friend class MappingAuthority;
        SnapshotReadPin(MappingAuthority &authority, U64 epoch) : authority_(authority), epoch_(epoch) {
            authority.pin_ready();
            authority.validate_snapshot_identity(epoch);
            authority.parser_pinned_ = true;
        }

    public:
        SnapshotReadPin(const SnapshotReadPin &) = delete;
        SnapshotReadPin(SnapshotReadPin &&) = delete;
        [[nodiscard]] auto bytes() const -> std::span<const std::byte> {
            require(authority_.parser_pinned_ && authority_.binding_->live_ && authority_.binding_->attached_ &&
                    authority_.space_->closed() && interrupts_off() && current_root() == authority_.kernel_root_ &&
                    authority_.binding_->identity());
            authority_.validate_snapshot_identity(epoch_);
            return {reinterpret_cast<const std::byte *>(snapshot_base), authority_.scalar(snapshot_offset + 32)};
        }
        ~SnapshotReadPin() {
            require(authority_.parser_pinned_ && !authority_.scoped_ && authority_.space_->closed());
            authority_.parser_pinned_ = false;
        }
    };
    [[nodiscard]] auto snapshot_read(U64 epoch) -> SnapshotReadPin {
        return SnapshotReadPin(*this, epoch);
    }
    [[nodiscard]] auto idle() const -> bool {
        return binding_ && !scoped_ && !parser_pinned_ && source_kind_ == SourceKind::none && space_->closed() &&
               scalar(operation_offset) == 0;
    }
    // No source call or temporary word loan: usable inside words::accessible.
    [[nodiscard]] auto accessible_root(U64 root) const -> bool {
        if (!binding_ || !space_->closed())
            return false;
        if (root == kernel_root_)
            return true;
        if (!binding_->live_ || !binding_->attached_)
            return false;
        for (U64 slot = 0; slot < 2; ++slot) {
            const auto at = slot0_offset + slot * slot_stride;
            if (scalar(at + 16) != 2 || scalar(at + 8) == 0)
                continue;
            const auto ticket = scalar(at + 24), index = ticket & 0xffffffff;
            if ((ticket >> 60) || index >= binding_->banks_[0].count)
                continue;
            const auto record = bank(0, index);
            const auto physical = ranges_->address(index);
            if (physical && *physical == root && frames::state(record) == 2 &&
                frames::generation(record) == ticket >> 32 && frames::word(record) == scalar(at) &&
                bank(1, index) == 12)
                return true;
        }
        return false;
    }
    [[nodiscard]] auto activation_root(Domain domain, U64 epoch) const -> U64 {
        require(domain == Domain::slot0 || domain == Domain::slot1);
        require(idle() && binding_->live_ && binding_->attached_ && binding_->identity() &&
                current_root() == kernel_root_ && interrupts_off() && scalar(staged_offset) == 0);
        const auto at = offset(static_cast<U64>(domain));
        const U64 owner = scalar(at), ticket = scalar(at + 24), index = ticket & 0xffffffff;
        require(epoch && scalar(at + 8) == epoch && scalar(at + 16) == 2 && owner >= frames::first_owner &&
                (ticket >> 60) == 0 && index < binding_->banks_[0].count && bank(1, index) == 12 &&
                (scalar(snapshot_offset + 16) == 0 || scalar(snapshot_offset) != owner));
        const U64 record = bank(0, index);
        const auto physical = ranges_->address(index);
        require(physical.has_value() && *physical < physical_limit_ && frames::state(record) == 2 &&
                frames::generation(record) == ticket >> 32 && frames::word(record) == owner);
        return *physical;
    }
    class Scope final {
        MappingAuthority &authority_;
        words::Binding::Scope words_;

    public:
        Scope(MappingAuthority &authority,
              Domain domain,
              U64 epoch,
              bool beginning = false,
              words::Access access = words::Access::write)
            : authority_(authority), words_(bound(authority), access) {
            require(!authority.scoped_ && !authority.parser_pinned_ && authority.space_->closed() && interrupts_off() &&
                    authority.accessible_root(current_root()) && authority.scalar(operation_offset) == 0 &&
                    static_cast<U64>(domain) <= 3);
            if (domain != Domain::global) {
                const auto at = authority.offset(static_cast<U64>(domain));
                require(
                    authority.scalar(at + 8) == epoch &&
                    (beginning ? authority.scalar(at + 16) == 0 && epoch != invalid : authority.scalar(at + 16) != 0));
            }
            authority.domain_ = domain;
            authority.expected_epoch_ = epoch;
            authority.beginning_ = beginning;
            authority.scoped_ = true;
        }
        Scope(const Scope &) = delete;
        ~Scope() {
            require(authority_.scoped_ && authority_.space_->closed() && authority_.scalar(operation_offset) == 0 &&
                    interrupts_off() && authority_.accessible_root(current_root()));
            authority_.scoped_ = false;
        }
    };
#ifdef AURORA_PROCESS_FIXTURE
    // Cold-boot hostile adapter cases only. No descriptor getter or source
    // entrypoint exists; production does not contain this fixture transport.
    static auto fixture_admission(U64 probe) -> void {
        require(owner_ && owner_->idle() && current_root() == owner_->kernel_root_ && interrupts_off());
        auto &self = *owner_;
        const void *token = self.binding_->authority_token();
        const U64 epoch = self.binding_->epoch_;
        if (probe == 45 || probe == 46) {
            Scope scope(self, Domain::global, 0);
            static_cast<void>(frame_address(
                probe == 45 ? reinterpret_cast<const void *>(1) : token, probe == 46 ? epoch + 1 : epoch, 0));
            __builtin_trap(); // A forbidden entry returning is not the expected rejection.
        }
        if (probe == 47) {
            Scope scope(self, Domain::global, 0);
            Scope nested(self, Domain::global, 0);
            __builtin_trap();
        }
        if (probe == 48) {
            asm volatile("sti" : : : "memory");
            Scope scope(self, Domain::global, 0);
            __builtin_trap();
        }
        if (probe == 49) {
            self.binding_->suspend();
            require(self.space_->detach());
            Scope scope(self, Domain::global, 0);
            __builtin_trap();
        }
        __builtin_trap();
    }
#endif
    [[nodiscard]] static auto finish(const void *token, U64 epoch) -> bool {
        auto &binding = words::Binding::admitted_authority(token, epoch, true);
        require(owner_ && owner_->binding_ == &binding && !owner_->scoped_ && !owner_->parser_pinned_ &&
                owner_->source_kind_ == SourceKind::none && owner_->space_->closed() && interrupts_off() &&
                current_root() == owner_->kernel_root_ && owner_->scalar(operation_offset) == 0 &&
                owner_->scalar(staged_offset) == 0 && owner_->scalar(slot0_offset + 16) == 0 &&
                owner_->scalar(slot0_offset + slot_stride + 16) == 0 && owner_->scalar(snapshot_offset + 16) == 0);
        const bool result = words::Binding::finish_authority(token, epoch);
        owner_ = nullptr;
        return result;
    }
    [[nodiscard]] static auto frame_address(const void *token, U64 epoch, U64 index) -> U64 {
        auto &self = admitted(token, epoch, false);
        return self.ranges_->address(index).value_or(invalid);
    }
    [[nodiscard]] static auto frame_index(const void *token, U64 epoch, U64 physical) -> U64 {
        auto &self = admitted(token, epoch, false);
        return self.ranges_->index(physical).value_or(invalid);
    }
    // An immutable inventory translation of each legal private PTE. Address
    // bits become frame-index<<12; flags are unchanged. Admitted shared anchors
    // stay raw. This does not classify ownership, tags, or traversal policy.
    [[nodiscard]] static auto observe_table(const void *token, U64 epoch, U64 ticket) -> bool {
        auto &self = admitted(token, epoch);
        const auto table = self.table(ticket);
        auto *view = self.space_->open(table.frame.physical);
        require(view);
        bool valid = true;
        for (U64 slot = 0; slot < 512; ++slot) {
            const U64 raw = reinterpret_cast<volatile U64 *>(view)[slot];
            if (!self.legal_entry(table, slot, raw)) {
                valid = false;
                break;
            }
            U64 result = raw;
            if (raw && !self.shared_value(table, slot)) {
                const auto index = self.ranges_->index(raw & KernelSpace::address_mask);
                if (!index) {
                    valid = false;
                    break;
                }
                result = (*index << 12) | (raw & ~KernelSpace::address_mask);
            }
            self.scratch(slot, result);
        }
        self.space_->close();
        // A failed observation publishes no success and changes no PTE. The
        // caller must discard scratch and may report an invalid physical walk.
        return valid;
    }
    // Bounded native scan of one table only; the source owns its four cursor
    // frames. scratch[0] is the exact raw PTE, scratch[1] the returned slot.
    [[nodiscard]] static auto observe_next_present(const void *token, U64 epoch, U64 ticket, U64 first) -> U64 {
        auto &self = admitted(token, epoch);
        require(first <= 512);
        const auto table = self.table(ticket);
        auto *view = self.space_->open(table.frame.physical);
        require(view);
        U64 slot = first, raw = 0;
        for (; slot < 512; ++slot) {
            raw = reinterpret_cast<volatile U64 *>(view)[slot];
            require(self.legal_entry(table, slot, raw));
            if (raw)
                break;
        }
        self.space_->close();
        self.scratch(0, raw);
        self.scratch(1, slot);
        return slot;
    }
    [[nodiscard]] static auto
    publish_empty_entry(const void *token, U64 epoch, U64 ticket, U64 slot, U64 value, U64 child) -> bool {
        auto &self = admitted(token, epoch);
        self.mutation();
        require(slot < 512 && (value & KernelSpace::hardware_bits) == 0);
        const auto table = self.table(ticket);
        self.authenticate_child(table, slot, value, child);
        auto *view = self.space_->open(table.frame.physical);
        require(view && reinterpret_cast<volatile U64 *>(view)[slot] == 0);
        reinterpret_cast<volatile U64 *>(view)[slot] = value;
        self.space_->close();
        return true;
    }
    [[nodiscard]] static auto
    clear_expected_entry(const void *token, U64 epoch, U64 ticket, U64 slot, U64 expected, U64 child) -> bool {
        auto &self = admitted(token, epoch);
        self.mutation();
        require(slot < 512);
        const auto table = self.table(ticket);
        self.authenticate_child(table, slot, expected, child);
        auto *view = self.space_->open(table.frame.physical);
        require(view);
        const U64 actual = reinterpret_cast<volatile U64 *>(view)[slot];
        require(self.legal_entry(table, slot, actual) &&
                (actual & ~KernelSpace::hardware_bits) == (expected & ~KernelSpace::hardware_bits));
        reinterpret_cast<volatile U64 *>(view)[slot] = 0;
        self.space_->close();
        self.invalidate_translation(table, slot);
        return true;
    }
    [[nodiscard]] static auto scrub_unpublished_frame(const void *token, U64 epoch, U64 ticket) -> bool {
        auto &self = admitted(token, epoch);
        self.mutation();
        const auto frame = self.frame(ticket);
        static_cast<void>(self.staged(ticket));
        require(frame.mapping == 0);
        auto *view = self.space_->open(frame.physical);
        require(view);
        for (U64 slot = 0; slot < 512; ++slot)
            reinterpret_cast<volatile U64 *>(view)[slot] = 0;
        self.space_->close();
        return true;
    }
    [[nodiscard]] static auto
    copy_source_frame(const void *token, U64 epoch, U64 ticket, U64 destination, U64 source, U64 count) -> bool {
        auto &self = admitted(token, epoch);
        self.mutation();
        const auto frame = self.frame(ticket);
        static_cast<void>(self.staged(ticket));
        require(frame.mapping == 0 && destination <= frames::page && count <= frames::page - destination &&
                source <= self.source_bytes_ && count <= self.source_bytes_ - source &&
                self.source_kind_ != SourceKind::none && self.source_kind_ != SourceKind::chunk);
        if (self.source_kind_ == SourceKind::snapshot)
            self.validate_snapshot_source(source, count);
        auto *view = self.space_->open(frame.physical);
        require(view);
        for (U64 at = 0; at < count; ++at)
            reinterpret_cast<volatile std::byte *>(view)[destination + at] = self.source_[source + at];
        self.space_->close();
        return true;
    }
    [[nodiscard]] static auto
    fill_snapshot_chunk(const void *token, U64 epoch, U64 snapshot_epoch, U64 destination, U64 source, U64 count)
        -> bool {
        auto &self = admitted(token, epoch);
        self.mutation();
        require(self.selected() == 2 && self.source_kind_ == SourceKind::chunk &&
                snapshot_epoch == self.source_epoch_ && self.scalar(snapshot_offset + 8) == snapshot_epoch &&
                self.scalar(snapshot_offset + 16) == 1 && source <= self.source_bytes_ &&
                count <= self.source_bytes_ - source && destination <= self.scalar(snapshot_offset + 32) &&
                count <= self.scalar(snapshot_offset + 32) - destination);
        const auto directory = self.table(self.scalar(snapshot_offset + 24));
        require(directory.snapshot && directory.level == 2 &&
                (KernelSpace::table_view(0)[2] & ~KernelSpace::hardware_bits) ==
                    (directory.frame.physical | KernelSpace::table_flags));
        // The native effect resolves only the exact bounded destination pages;
        // source decides the snapshot extent, construction and lifetime.
        for (U64 copied = 0; copied < count;) {
            const U64 position = destination + copied, page = position / frames::page;
            auto *view = self.space_->open(directory.frame.physical);
            require(view);
            const U64 parent = reinterpret_cast<volatile U64 *>(view)[page / 512];
            self.space_->close();
            require(self.legal_entry(directory, page / 512, parent) && parent);
            const auto table_index = self.ranges_->index(parent & KernelSpace::address_mask);
            require(table_index.has_value());
            const U64 table_ticket = *table_index | (frames::generation(self.bank(0, *table_index)) << 32);
            self.authenticate_child(directory, page / 512, parent, table_ticket);
            const auto table = self.table(table_ticket);
            view = self.space_->open(table.frame.physical);
            require(view);
            const U64 leaf = reinterpret_cast<volatile U64 *>(view)[page % 512];
            self.space_->close();
            require((leaf & ~KernelSpace::address_mask & ~KernelSpace::hardware_bits) == KernelSpace::data_flags);
            const auto frame_index = self.ranges_->index(leaf & KernelSpace::address_mask);
            require(frame_index.has_value());
            const U64 frame_ticket = *frame_index | (frames::generation(self.bank(0, *frame_index)) << 32);
            self.authenticate_child(table, page % 512, leaf, frame_ticket);
            const auto frame = self.frame(frame_ticket);
            const U64 offset = position % frames::page;
            const U64 amount = count - copied < frames::page - offset ? count - copied : frames::page - offset;
            view = self.space_->open(frame.physical);
            require(view);
            for (U64 at = 0; at < amount; ++at)
                reinterpret_cast<volatile std::byte *>(view)[offset + at] = self.source_[source + copied + at];
            self.space_->close();
            copied += amount;
        }
        return true;
    }
    [[nodiscard]] static auto
    downgrade_snapshot_entry(const void *token, U64 epoch, U64 ticket, U64 slot, U64 expected, U64 child) -> bool {
        auto &self = admitted(token, epoch);
        self.mutation();
        require(slot < 512 && self.scalar(snapshot_offset + 16) == 1);
        const auto table = self.table(ticket);
        require(table.snapshot && table.level == 1 &&
                (expected & ~KernelSpace::address_mask & ~KernelSpace::hardware_bits) == KernelSpace::data_flags);
        self.authenticate_child(table, slot, expected, child);
        auto *view = self.space_->open(table.frame.physical);
        require(view);
        const U64 actual = reinterpret_cast<volatile U64 *>(view)[slot];
        require(self.legal_entry(table, slot, actual) &&
                (actual & ~KernelSpace::hardware_bits) == (expected & ~KernelSpace::hardware_bits));
        reinterpret_cast<volatile U64 *>(view)[slot] = actual & ~U64{2};
        self.space_->close();
        self.invalidate_translation(table, slot);
        return true;
    }
    [[nodiscard]] static auto observe_snapshot_anchor(const void *token, U64 epoch, U64 ticket) -> bool {
        auto &self = admitted(token, epoch);
        const auto directory = self.table(ticket);
        require(directory.snapshot && directory.level == 2 && self.scalar(snapshot_offset + 24) == ticket &&
                (self.scalar(snapshot_offset + 16) == 1 || self.scalar(snapshot_offset + 16) == 2));
        return (KernelSpace::table_view(0)[2] & ~KernelSpace::hardware_bits) ==
               (directory.frame.physical | KernelSpace::table_flags);
    }
    [[nodiscard]] static auto snapshot_anchor_publish(const void *token, U64 epoch, U64 ticket) -> bool {
        auto &self = admitted(token, epoch);
        self.mutation();
        const auto directory = self.table(ticket);
        require(directory.snapshot && directory.level == 2 && self.scalar(snapshot_offset + 24) == ticket &&
                self.scalar(snapshot_offset + 16) == 1 && KernelSpace::table_view(0)[2] == 0);
        KernelSpace::table_view(0)[2] = directory.frame.physical | KernelSpace::table_flags;
        flush();
        return true;
    }
    [[nodiscard]] static auto snapshot_anchor_clear(const void *token, U64 epoch, U64 ticket) -> bool {
        auto &self = admitted(token, epoch);
        self.mutation();
        const auto directory = self.table(ticket);
        require(directory.snapshot && directory.level == 2 && self.scalar(snapshot_offset + 24) == ticket &&
                self.scalar(snapshot_offset + 16) == 3 &&
                (KernelSpace::table_view(0)[2] & ~KernelSpace::hardware_bits) ==
                    (directory.frame.physical | KernelSpace::table_flags));
        KernelSpace::table_view(0)[2] = 0;
        flush();
        return true;
    }
    [[nodiscard]] static auto initialize_shared_upper(const void *token, U64 epoch, U64 ticket) -> bool {
        auto &self = admitted(token, epoch);
        self.mutation();
        const auto table = self.table(ticket);
        require(!table.snapshot && table.level == 4 && self.scalar(self.offset(self.selected()) + 16) == 1);
        auto *view = self.space_->open(table.frame.physical);
        require(view);
        for (U64 slot = 256; slot < 512; ++slot)
            require(reinterpret_cast<volatile U64 *>(view)[slot] == 0);
        for (U64 slot = 256; slot < 512; ++slot)
            reinterpret_cast<volatile U64 *>(view)[slot] = self.shared_.upper[slot - 256];
        self.space_->close();
        return true;
    }
    [[nodiscard]] static auto publish_shared_entry(const void *token, U64 epoch, U64 ticket, U64 slot, U64 shared)
        -> bool {
        auto &self = admitted(token, epoch);
        self.mutation();
        require(slot < 512 && shared < self.shared_.slots);
        const auto table = self.table(ticket);
        require(!table.snapshot && table.level == 2 && address(table, slot) == self.shared_.slot[shared] &&
                self.scalar(self.offset(self.selected()) + 16) == 1);
        auto *view = self.space_->open(table.frame.physical);
        require(view && reinterpret_cast<volatile U64 *>(view)[slot] == 0);
        reinterpret_cast<volatile U64 *>(view)[slot] = self.shared_.entry[shared];
        self.space_->close();
        return true;
    }
    [[nodiscard]] static auto clear_shared_entry(const void *token, U64 epoch, U64 ticket, U64 slot, U64 shared)
        -> bool {
        auto &self = admitted(token, epoch);
        self.mutation();
        require(slot < 512 && shared < self.shared_.slots);
        const auto table = self.table(ticket);
        require(!table.snapshot && table.level == 2 && address(table, slot) == self.shared_.slot[shared] &&
                self.scalar(self.offset(self.selected()) + 16) == 3 && current_root() == self.kernel_root_);
        auto *view = self.space_->open(table.frame.physical);
        require(view);
        const U64 actual = reinterpret_cast<volatile U64 *>(view)[slot];
        require((actual & ~KernelSpace::hardware_bits) == self.shared_.entry[shared]);
        reinterpret_cast<volatile U64 *>(view)[slot] = 0;
        self.space_->close();
        self.invalidate_translation(table, slot);
        return true;
    }
    [[nodiscard]] static auto revoke_root(const void *token, U64 epoch, U64 ticket) -> bool {
        auto &self = admitted(token, epoch);
        self.mutation();
        const auto table = self.table(ticket);
        require(!table.snapshot && table.level == 4 && current_root() == self.kernel_root_ &&
                table.frame.physical != self.kernel_root_ && self.scalar(self.offset(self.selected()) + 16) == 3);
        return true;
    }
    [[nodiscard]] static auto shared_upper(const void *token, U64 epoch, U64 slot) -> U64 {
        auto &self = admitted(token, epoch, false);
        require(slot >= 256 && slot < 512);
        return self.shared_.upper[slot - 256];
    }
    [[nodiscard]] static auto shared_slots(const void *token, U64 epoch) -> U64 {
        return admitted(token, epoch, false).shared_.slots;
    }
    [[nodiscard]] static auto shared_slot(const void *token, U64 epoch, U64 index) -> U64 {
        auto &self = admitted(token, epoch, false);
        require(index < self.shared_.slots);
        return self.shared_.slot[index];
    }
    [[nodiscard]] static auto shared_value(const void *token, U64 epoch, U64 index) -> U64 {
        auto &self = admitted(token, epoch, false);
        require(index < self.shared_.slots);
        return self.shared_.entry[index];
    }
    [[nodiscard]] static auto reserved_first(const void *token, U64 epoch) -> U64 {
        return admitted(token, epoch, false).shared_.reserved_first;
    }
    [[nodiscard]] static auto reserved_end(const void *token, U64 epoch) -> U64 {
        return admitted(token, epoch, false).shared_.reserved_end;
    }
};
} // namespace aurora::uefi
