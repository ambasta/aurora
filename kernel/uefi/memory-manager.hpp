#pragma once
#include "mapping-authority.hpp"
#include <initializer_list>

namespace aurora::uefi {
class ManagerResult final {
public:
    std::uint64_t outcome = 2, value = 0;
};
class ManagerEntry final {
public:
    std::uint64_t table = 0, slot = 0, valid = 0;
};
extern "C" {
void __au_runtime_manager_construct(void *, words::Binding::Grants *);
bool __au_runtime_manager_frames_initialize(void *, const std::uint64_t *);
bool __au_runtime_manager_frames_poisoned(void *, const std::uint64_t *);
bool __au_runtime_manager_attach_shared(void *, const std::uint64_t *);
bool __au_runtime_manager_map_region(void *, const std::uint64_t *);
bool __au_runtime_manager_finish_load(void *, const std::uint64_t *);
bool __au_runtime_manager_commit_fault_block(void *, const std::uint64_t *);
bool __au_runtime_manager_verify_space(void *, const std::uint64_t *);
bool __au_runtime_manager_space_contains(void *, const std::uint64_t *);
bool __au_runtime_manager_space_executable(void *, const std::uint64_t *);
bool __au_runtime_manager_snapshot_fill(void *, const std::uint64_t *);
bool __au_runtime_manager_snapshot_seal(void *, const std::uint64_t *);
bool __au_runtime_manager_snapshot_discard(void *, const std::uint64_t *);
bool __au_runtime_manager_snapshot_verify(void *, const std::uint64_t *);
bool __au_runtime_manager_audit_residents(void *, const std::uint64_t *);
bool __au_runtime_manager_finish(void *, const std::uint64_t *);
std::uint64_t __au_runtime_manager_frames_release(void *, const std::uint64_t *);
std::uint64_t __au_runtime_manager_frames_record(void *, const std::uint64_t *);
std::uint64_t __au_runtime_manager_frames_frames(void *, const std::uint64_t *);
std::uint64_t __au_runtime_manager_frames_reserved(void *, const std::uint64_t *);
std::uint64_t __au_runtime_manager_frames_free(void *, const std::uint64_t *);
std::uint64_t __au_runtime_manager_frames_allocated(void *, const std::uint64_t *);
std::uint64_t __au_runtime_manager_frames_owner_allocated(void *, const std::uint64_t *);
std::uint64_t __au_runtime_manager_prepare_load(void *, const std::uint64_t *);
std::uint64_t __au_runtime_manager_space_value(void *, const std::uint64_t *);
std::uint64_t __au_runtime_manager_fault_access(void *, const std::uint64_t *);
std::uint64_t __au_runtime_manager_validate_access(void *, const std::uint64_t *);
std::uint64_t __au_runtime_manager_retire_space(void *, const std::uint64_t *);
std::uint64_t __au_runtime_manager_snapshot_begin(void *, const std::uint64_t *);
std::uint64_t __au_runtime_manager_snapshot_value(void *, const std::uint64_t *);
void __au_runtime_manager_frames_allocate(void *, const std::uint64_t *, frames::FrameAllocation *);
void __au_runtime_manager_frames_audit(void *, const std::uint64_t *, frames::FrameAudit *);
void __au_runtime_manager_map_memory(void *, const std::uint64_t *, ManagerResult *);
void __au_runtime_manager_remap_memory(void *, const std::uint64_t *, ManagerResult *);
void __au_runtime_manager_unmap_memory(void *, const std::uint64_t *, ManagerResult *);
void __au_runtime_manager_space_entry(void *, const std::uint64_t *, ManagerEntry *);
}
// Native storage is opaque. The emitted MemoryManager ABI must match this exact
// extent and its five descriptor offsets before this image can be admitted.
// There is no native allocation, mapping, region or quota mirror.
class MemoryManager final {
public:
    using U64 = std::uint64_t;
    using Audit = frames::FrameAudit;
    using Result = ManagerResult;
    static constexpr std::size_t root_bytes = 496;

private:
    alignas(16) mutable std::array<std::byte, root_bytes> storage_{};
    mutable words::Binding binding_;
    mutable MappingAuthority authority_;
    const frames::Ranges *ranges_ = nullptr;
    using Domain = MappingAuthority::Domain;
    static auto require(bool condition) -> void {
        if (!condition)
            words::fail();
    }
    [[nodiscard]] static auto domain(U64 slot) -> Domain {
        require(slot < 2);
        return slot == 0 ? Domain::slot0 : Domain::slot1;
    }
    [[nodiscard]] static auto arguments(std::initializer_list<U64> input) -> std::array<U64, 5> {
        require(input.size() <= 5);
        std::array<U64, 5> result{};
        std::size_t index = 0;
        for (const auto value : input)
            result[index++] = value;
        return result;
    }
    template <auto Entry>
    [[nodiscard]] auto frame_call(std::initializer_list<U64> input, words::Access access) const
        -> decltype(Entry(nullptr, nullptr)) {
        require(!authority_.attached() || authority_.idle());
        const auto args = arguments(input);
        words::Binding::Scope scope(binding_, access);
        return Entry(storage_.data(), args.data());
    }
    template <class T, auto Entry>
    [[nodiscard]] auto frame_result(std::initializer_list<U64> input, words::Access access) const -> T {
        require(!authority_.attached() || authority_.idle());
        const auto args = arguments(input);
        words::Binding::Scope scope(binding_, access);
        T result{};
        Entry(storage_.data(), args.data(), &result);
        return result;
    }
    template <auto Entry>
    [[nodiscard]] auto call(std::initializer_list<U64> input,
                            Domain selected,
                            U64 epoch,
                            bool beginning = false,
                            words::Access access = words::Access::write) const -> decltype(Entry(nullptr, nullptr)) {
        const auto args = arguments(input);
        MappingAuthority::Scope scope(authority_, selected, epoch, beginning, access);
        return Entry(storage_.data(), args.data());
    }
    template <class T, auto Entry>
    [[nodiscard]] auto copied(std::initializer_list<U64> input, Domain selected, U64 epoch) const -> T {
        const auto args = arguments(input);
        MappingAuthority::Scope scope(authority_, selected, epoch);
        T result{};
        Entry(storage_.data(), args.data(), &result);
        return result;
    }

public:
    MemoryManager() = default;
    MemoryManager(const MemoryManager &) = delete;
    auto operator=(const MemoryManager &) -> MemoryManager & = delete;
    [[nodiscard]] auto bind(std::span<U64> allocation,
                            std::span<U64> mapping,
                            std::span<U64> reservations,
                            std::span<U64> scratch,
                            const frames::Ranges &ranges,
                            U64 tables,
                            U64 metadata) -> bool {
        if (binding_.created() || allocation.size() != ranges.frames() || mapping.size() != allocation.size() ||
            reservations.size() != 2 * process::memory_records * 3 + 512 || scratch.size() != 512 ||
            allocation.empty() || allocation.size() > 0xffffffffULL || tables >= allocation.size() ||
            metadata >= allocation.size() - tables)
            return false;
        const std::array<words::Binding::BankGrant, 4> banks{
            {{allocation, 0}, {mapping, 16}, {reservations, 32}, {scratch, 48}}};
        auto grants = binding_.bind_set(banks, storage_.data(), storage_.size(), 64);
        __au_runtime_manager_construct(storage_.data(), &grants);
        for (const auto &grant : grants.banks)
            require(!grant.binding && !grant.epoch);
        require(!grants.authority.binding && !grants.authority.epoch);
        ranges_ = &ranges;
        require(frame_call<__au_runtime_manager_frames_initialize>({tables, metadata}, words::Access::write));
        return true;
    }
    auto attach(KernelSpace &space, const MappingAuthority::SharedEvidence &shared, U64 physical_bits, U64 kernel_root)
        -> void {
        require(ranges_);
        require(authority_.attach(binding_, space, *ranges_, shared, physical_bits, kernel_root));
        require(call<__au_runtime_manager_attach_shared>({}, Domain::global, 0));
    }
    [[nodiscard]] auto accessible_root(U64 root) const -> bool {
        return authority_.accessible_root(root);
    }
    [[nodiscard]] auto address(U64 index) const -> std::optional<U64> {
        return ranges_ ? ranges_->address(index) : std::nullopt;
    }
    [[nodiscard]] auto allocate(U64 owner) -> std::optional<frames::Frame> {
        const auto value =
            frame_result<frames::FrameAllocation, __au_runtime_manager_frames_allocate>({owner}, words::Access::write);
        require(value.valid <= 1);
        if (!value.valid)
            return std::nullopt;
        require(ranges_ && value.index < ranges_->frames() && value.generation <= 0x0fffffffULL);
        return frames::Frame{value.index, value.generation};
    }
    [[nodiscard]] auto release(frames::Frame frame, U64 owner) -> frames::Rejection {
        const auto value = frame_call<__au_runtime_manager_frames_release>({frame.index, frame.generation, owner},
                                                                           words::Access::write);
        require(value <= static_cast<U64>(frames::Rejection::stale) ||
                (value >= static_cast<U64>(frames::Rejection::malformed) &&
                 value <= static_cast<U64>(frames::Rejection::exhausted)));
        return static_cast<frames::Rejection>(value);
    }
    [[nodiscard]] auto record(U64 index) const -> U64 {
        return frame_call<__au_runtime_manager_frames_record>({index}, words::Access::read);
    }
    [[nodiscard]] auto frames() const -> U64 {
        return frame_call<__au_runtime_manager_frames_frames>({}, words::Access::read);
    }
    [[nodiscard]] auto reserved() const -> U64 {
        return frame_call<__au_runtime_manager_frames_reserved>({}, words::Access::read);
    }
    [[nodiscard]] auto free() const -> U64 {
        return frame_call<__au_runtime_manager_frames_free>({}, words::Access::read);
    }
    [[nodiscard]] auto allocated() const -> U64 {
        return frame_call<__au_runtime_manager_frames_allocated>({}, words::Access::read);
    }
    [[nodiscard]] auto poisoned() const -> bool {
        return frame_call<__au_runtime_manager_frames_poisoned>({}, words::Access::read);
    }
    [[nodiscard]] auto allocated(U64 owner) const -> U64 {
        return frame_call<__au_runtime_manager_frames_owner_allocated>({owner}, words::Access::read);
    }
    [[nodiscard]] auto audit() const -> Audit {
        const auto value = frame_result<frames::FrameAudit, __au_runtime_manager_frames_audit>({}, words::Access::read);
        require(value.consistent <= 1);
        return value;
    }
    auto suspend() -> void {
        require(!authority_.attached() || authority_.idle());
        binding_.suspend();
    }
    auto resume_set(std::span<const words::Binding::Backing> banks) -> void {
        binding_.resume_set(banks);
    }
    [[nodiscard]] auto finish() -> bool {
        require(!authority_.attached() || authority_.idle());
        require(frame_call<__au_runtime_manager_finish>({}, words::Access::consume) && !binding_.live());
        return true;
    }
    [[nodiscard]] auto prepare_load(U64 slot, U64 owner, U64 requested, U64 charge) -> U64 {
        return call<__au_runtime_manager_prepare_load>(
            {slot, owner, requested, charge}, domain(slot), authority_.empty_epoch(domain(slot)), true);
    }
    [[nodiscard]] auto space_value(U64 slot, U64 epoch, U64 field) const -> U64 {
        const auto value = call<__au_runtime_manager_space_value>(
            {slot, epoch, field}, domain(slot), epoch, false, words::Access::read);
        if (field != 1)
            return value;
        require(ranges_ && (value >> 60) == 0);
        const auto physical = ranges_->address(value & 0xffffffffULL);
        require(physical.has_value());
        return *physical;
    }
    [[nodiscard]] auto finish_load(U64 slot, U64 epoch) const -> bool {
        return call<__au_runtime_manager_finish_load>({slot, epoch}, domain(slot), epoch, false, words::Access::write);
    }
    [[nodiscard]] auto fault_access(U64 slot, U64 epoch, U64 address, U64 error) const -> U64 {
        return call<__au_runtime_manager_fault_access>(
            {slot, epoch, address, error}, domain(slot), epoch, false, words::Access::read);
    }
    [[nodiscard]] auto commit_fault_block(U64 slot, U64 epoch, U64 address) const -> bool {
        return call<__au_runtime_manager_commit_fault_block>(
            {slot, epoch, address}, domain(slot), epoch, false, words::Access::write);
    }
    [[nodiscard]] auto validate_access(U64 slot, U64 epoch, U64 address, U64 length, bool write) const -> U64 {
        return call<__au_runtime_manager_validate_access>(
            {slot, epoch, address, length, write ? 1ULL : 0ULL}, domain(slot), epoch, false, words::Access::write);
    }
    [[nodiscard]] auto verify_space(U64 slot, U64 epoch) const -> bool {
        return call<__au_runtime_manager_verify_space>({slot, epoch}, domain(slot), epoch, false, words::Access::write);
    }
    [[nodiscard]] auto space_contains(U64 slot, U64 epoch, U64 address, U64 length) const -> bool {
        return call<__au_runtime_manager_space_contains>(
            {slot, epoch, address, length}, domain(slot), epoch, false, words::Access::read);
    }
    [[nodiscard]] auto space_executable(U64 slot, U64 epoch, U64 address, U64 length) const -> bool {
        return call<__au_runtime_manager_space_executable>(
            {slot, epoch, address, length}, domain(slot), epoch, false, words::Access::read);
    }
    [[nodiscard]] auto map_memory(U64 slot, U64 epoch, U64 bytes) -> Result {
        const auto value =
            copied<ManagerResult, __au_runtime_manager_map_memory>({slot, epoch, bytes}, domain(slot), epoch);
        require(value.outcome <= 2);
        return value;
    }
    [[nodiscard]] auto remap_memory(U64 slot, U64 epoch, U64 base, U64 bytes, U64 target) -> Result {
        const auto value = copied<ManagerResult, __au_runtime_manager_remap_memory>(
            {slot, epoch, base, bytes, target}, domain(slot), epoch);
        require(value.outcome <= 2);
        return value;
    }
    [[nodiscard]] auto unmap_memory(U64 slot, U64 epoch, U64 base, U64 bytes) -> Result {
        const auto value =
            copied<ManagerResult, __au_runtime_manager_unmap_memory>({slot, epoch, base, bytes}, domain(slot), epoch);
        require(value.outcome <= 2);
        return value;
    }
    [[nodiscard]] auto retire_space(U64 slot, U64 epoch) -> std::optional<U64> {
        const auto value = call<__au_runtime_manager_retire_space>({slot, epoch}, domain(slot), epoch);
        return value == ~U64{0} ? std::nullopt : std::optional<U64>{value};
    }
    [[nodiscard]] auto space_entry(U64 slot, U64 epoch, U64 address, U64 level) -> std::optional<ManagerEntry> {
        const auto value =
            copied<ManagerEntry, __au_runtime_manager_space_entry>({slot, epoch, address, level}, domain(slot), epoch);
        require(value.valid <= 1);
        return value.valid ? std::optional<ManagerEntry>{value} : std::nullopt;
    }
    [[nodiscard]] auto begin_snapshot(U64 owner, U64 bytes) -> U64 {
        return call<__au_runtime_manager_snapshot_begin>(
            {owner, bytes}, Domain::snapshot, authority_.empty_epoch(Domain::snapshot), true);
    }
    [[nodiscard]] auto snapshot_value(U64 epoch, U64 field) const -> U64 {
        return call<__au_runtime_manager_snapshot_value>(
            {epoch, field}, Domain::snapshot, epoch, false, words::Access::read);
    }
    [[nodiscard]] auto verify_snapshot(U64 epoch) -> bool {
        return call<__au_runtime_manager_snapshot_verify>({epoch}, Domain::snapshot, epoch);
    }
    [[nodiscard]] auto seal_snapshot(U64 epoch) -> bool {
        return call<__au_runtime_manager_snapshot_seal>({epoch}, Domain::snapshot, epoch);
    }
    [[nodiscard]] auto discard_snapshot(U64 epoch) -> bool {
        return call<__au_runtime_manager_snapshot_discard>({epoch}, Domain::snapshot, epoch);
    }
    [[nodiscard]] auto audit_residents() -> bool {
        return call<__au_runtime_manager_audit_residents>({}, Domain::global, 0);
    }
    [[nodiscard]] auto activation_root(U64 slot, U64 epoch) const -> U64 {
        return authority_.activation_root(domain(slot), epoch);
    }
    auto attach_boot_volume(std::span<const std::byte> volume) -> void {
        authority_.attach_boot_volume(volume);
    }
    [[nodiscard]] auto boot_source(std::span<const std::byte> bytes) -> MappingAuthority::SourcePin {
        return authority_.boot_source(bytes);
    }
    [[nodiscard]] auto snapshot_source(U64 epoch) -> MappingAuthority::SourcePin {
        return authority_.snapshot_source(epoch);
    }
    [[nodiscard]] auto arguments_source(std::span<const std::byte> bytes) -> MappingAuthority::SourcePin {
        return authority_.arguments_source(bytes);
    }
    [[nodiscard]] auto snapshot_read(U64 epoch) -> MappingAuthority::SnapshotReadPin {
        return authority_.snapshot_read(epoch);
    }
    [[nodiscard]] auto map_region(U64 slot, U64 epoch, const process::ProcessRegion &region, U64 source_kind) -> bool {
        class Arguments final {
        public:
            U64 slot, epoch;
            process::ProcessRegion region;
            U64 kind;
        };
        static_assert(sizeof(Arguments) == 80);
        const Arguments args{slot, epoch, region, source_kind};
        MappingAuthority::Scope scope(authority_, domain(slot), epoch);
        return __au_runtime_manager_map_region(storage_.data(), reinterpret_cast<const U64 *>(&args));
    }
    [[nodiscard]] auto fill_snapshot(U64 epoch, U64 offset, std::span<const std::byte> bytes) -> bool {
        auto input = authority_.loader_chunk_source(bytes, epoch);
        return call<__au_runtime_manager_snapshot_fill>({epoch, offset, bytes.size()}, Domain::snapshot, epoch);
    }
};
static_assert(sizeof(ManagerResult) == 16 && sizeof(ManagerEntry) == 24);
} // namespace aurora::uefi
