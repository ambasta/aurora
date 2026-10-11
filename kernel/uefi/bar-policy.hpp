#pragma once
#include "pci-policy.hpp"
namespace aurora::uefi {
// Copied firmware descriptions, never an MMIO or DMA capability. UEFI 2.11
// 14.2.18 / 14.4.18 use 46-byte QWORD records, then a two-byte EndTag.
// This first profile supports only zero translation and positively decoded,
// completely allocated ranges. It does not interpret AML resource templates.
class PciResource final {
    friend class PciResources;
    unsigned type_{}, flags_{}, specific_{}, granularity_{};
    std::uint64_t begin_{}, length_{};

public:
    [[nodiscard]] auto type() const -> unsigned {
        return type_;
    }
    [[nodiscard]] auto flags() const -> unsigned {
        return flags_;
    }
    [[nodiscard]] auto specific() const -> unsigned {
        return specific_;
    }
    [[nodiscard]] auto granularity() const -> unsigned {
        return granularity_;
    }
    [[nodiscard]] auto begin() const -> std::uint64_t {
        return begin_;
    }
    [[nodiscard]] auto length() const -> std::uint64_t {
        return length_;
    }
    [[nodiscard]] auto end() const -> std::uint64_t {
        return begin_ + length_;
    }
    [[nodiscard]] auto contains(std::uint64_t begin, std::uint64_t length) const -> bool {
        return length && begin >= begin_ && begin < end() && length <= end() - begin;
    }
};
enum class PciResourceSource {
    Uefi,
    Edk2Stable202502Bar,
    Edk2Stable202502Root
};
class PciResources final {
    std::array<PciResource, 16> resources_{};
    std::size_t count_{};
    unsigned physical_bits_{};
    PciResourceSource source_ = PciResourceSource::Uefi;
    PciResources() = default;
    [[nodiscard]] static auto parse_as(std::span<const std::byte> bytes,
                                       unsigned physical_bits,
                                       PciResourceSource source) -> std::optional<PciResources> {
        if (physical_bits < 32 || physical_bits > 52 || bytes.size() < 48 || bytes.size() > maximum_bytes ||
            (bytes.size() - 2) % descriptor_bytes || Bytes{bytes}.get(bytes.size() - 2, 2) != 0x79)
            return std::nullopt;
        const bool edk2_bar = source == PciResourceSource::Edk2Stable202502Bar;
        const bool edk2_root = source == PciResourceSource::Edk2Stable202502Root;
        if (edk2_bar && bytes.size() != 48)
            return std::nullopt;
        PciResources result;
        result.physical_bits_ = physical_bits;
        result.source_ = source;
        for (std::size_t at = 0; at < bytes.size() - 2; at += descriptor_bytes) {
            const Bytes entry{bytes.subspan(at, descriptor_bytes)};
            PciResource resource;
            resource.type_ = static_cast<unsigned>(entry.get(3, 1));
            resource.flags_ = static_cast<unsigned>(entry.get(4, 1));
            resource.specific_ = static_cast<unsigned>(entry.get(5, 1));
            const auto granularity = entry.get(6), maximum = entry.get(22);
            resource.begin_ = entry.get(14);
            resource.length_ = entry.get(38);
            if (entry.get(0, 1) != 0x8a || entry.get(1, 2) != 43 || resource.type_ > 2 || (resource.flags_ & 0xf2) ||
                ((resource.flags_ & 0xc) != 0 && (resource.flags_ & 0xc) != 0xc) || entry.get(30) != 0 ||
                resource.length_ == 0 || ((edk2_bar || edk2_root) && resource.flags_))
                return std::nullopt;
            if (edk2_bar) {
                // Explicit edk2-stable202502-q35-nvme source contract, never a
                // fallback: PciIo.c returns Alignment instead of ending address.
                const auto limit = 1ULL << physical_bits;
                if (resource.type_ != 0 || resource.specific_ || granularity != 64 || resource.length_ < 4096 ||
                    resource.length_ > 0x100000 || (resource.length_ & (resource.length_ - 1)) ||
                    maximum != resource.length_ - 1 || !resource.begin_ || resource.begin_ % resource.length_ ||
                    resource.begin_ >= limit || resource.length_ > limit - resource.begin_)
                    return std::nullopt;
            } else if (resource.begin_ > maximum || maximum == ~std::uint64_t{0} ||
                       resource.length_ != maximum - resource.begin_ + 1)
                return std::nullopt;
            const auto last = resource.begin_ + resource.length_ - 1;
            if (resource.type_ == 0) {
                if ((resource.specific_ & 0xf8) || (granularity != 32 && granularity != 64) ||
                    last >= (1ULL << physical_bits) || (granularity == 32 && last >= 0x100000000ULL) ||
                    (edk2_root && resource.specific_ != 0 && resource.specific_ != 6))
                    return std::nullopt;
            } else if (resource.type_ == 1) {
                // Only the complete x86 I/O range form is supported. _RNG==0
                // remains reserved in strict parsing. The named EDK2 producer
                // zeroes this unused field; neither form grants any I/O access.
                if (resource.specific_ != (edk2_root ? 0U : 3U) || granularity || last > 65535)
                    return std::nullopt;
            } else if (resource.specific_ || granularity || last > 255)
                return std::nullopt;
            resource.granularity_ = static_cast<unsigned>(granularity);
            for (const auto &previous : result.resources())
                if (previous.type() == resource.type() && previous.begin() < resource.end() &&
                    resource.begin() < previous.end())
                    return std::nullopt;
            result.resources_[result.count_++] = resource;
        }
        return result;
    }

public:
    static constexpr std::size_t descriptor_bytes = 46, maximum_descriptors = 16, maximum_bytes = 738;
    [[nodiscard]] auto count() const -> std::size_t {
        return count_;
    }
    [[nodiscard]] auto physical_bits() const -> unsigned {
        return physical_bits_;
    }
    [[nodiscard]] auto source() const -> PciResourceSource {
        return source_;
    }
    [[nodiscard]] auto resources() const -> std::span<const PciResource> {
        return {resources_.data(), count_};
    }
    [[nodiscard]] static auto parse(std::span<const std::byte> bytes, unsigned physical_bits)
        -> std::optional<PciResources> {
        return parse_as(bytes, physical_bits, PciResourceSource::Uefi);
    }
    // These entry points must be selected by the trusted platform build, never
    // by a label in the handoff or by retrying a failed strict parse. Producer:
    // tianocore/edk2 fbe0805b2091393406952e84724188f8c1941837 (stable202502),
    // PciBusDxe/PciIo.c and PciHostBridgeDxe/PciRootBridgeIo.c.
    [[nodiscard]] static auto parse_edk2_bar(std::span<const std::byte> bytes, unsigned physical_bits)
        -> std::optional<PciResources> {
        return parse_as(bytes, physical_bits, PciResourceSource::Edk2Stable202502Bar);
    }
    [[nodiscard]] static auto parse_edk2_root(std::span<const std::byte> bytes, unsigned physical_bits)
        -> std::optional<PciResources> {
        return parse_as(bytes, physical_bits, PciResourceSource::Edk2Stable202502Root);
    }
};
// An independent immutable config snapshot, including status/other BARs. Exact
// equality deliberately fails closed if firmware or a later reader changed it.
class PciBarSnapshot final {
    friend class PciBarReservation;
    std::array<std::byte, 64> header_{};
    unsigned segment_{}, bus_{}, device_{}, function_{};
    PciBarSnapshot() = default;

public:
    [[nodiscard]] static auto
    parse(unsigned segment, unsigned bus, unsigned device, unsigned function, std::span<const std::byte> header)
        -> std::optional<PciBarSnapshot> {
        if (segment > 65535 || bus > 255 || device > 31 || function > 7 || header.size() != 64 ||
            Bytes{header}.get(0, 2) == 0 || Bytes{header}.get(0, 2) == 65535)
            return std::nullopt;
        PciBarSnapshot result;
        result.segment_ = segment;
        result.bus_ = bus;
        result.device_ = device;
        result.function_ = function;
        for (std::size_t i = 0; i < header.size(); ++i)
            result.header_[i] = header[i];
        return result;
    }
    [[nodiscard]] auto segment() const -> unsigned {
        return segment_;
    }
    [[nodiscard]] auto bus() const -> unsigned {
        return bus_;
    }
    [[nodiscard]] auto device() const -> unsigned {
        return device_;
    }
    [[nodiscard]] auto function() const -> unsigned {
        return function_;
    }
    [[nodiscard]] auto command() const -> std::uint64_t {
        return Bytes{header_}.get(4, 2);
    }
    [[nodiscard]] auto base() const -> std::uint64_t {
        return (Bytes{header_}.get(16, 4) & ~15ULL) | (Bytes{header_}.get(20, 4) << 32);
    }
    [[nodiscard]] auto same(const PciBarSnapshot &other) const -> bool {
        return segment_ == other.segment_ && bus_ == other.bus_ && device_ == other.device_ &&
               function_ == other.function_ && header_ == other.header_;
    }
    [[nodiscard]] auto q35_nvme() const -> bool {
        const Bytes header{header_};
        return segment_ == 0 && header.get(0, 4) == 0x00101b36 && header.get(9, 3) == 0x010802 &&
               header.get(14, 1) == 0 && (header.get(16, 4) & 15) == 4 && base() != 0 && (command() & 2) != 0 &&
               (command() & 0xf800) == 0;
    }
};
// Deny-list evidence for another endpoint's assigned BAR. This deliberately
// cannot be converted into a PciResources or an MMIO/DMA capability. Completeness
// of the inventory and the bound on captured reservations belong to the adapter.
class PciBarReservation final {
    std::uint64_t begin_, length_;
    PciBarReservation(std::uint64_t begin, std::uint64_t length) : begin_(begin), length_(length) {
    }

public:
    [[nodiscard]] auto begin() const -> std::uint64_t {
        return begin_;
    }
    [[nodiscard]] auto length() const -> std::uint64_t {
        return length_;
    }
    [[nodiscard]] auto overlaps(std::uint64_t begin, std::uint64_t length) const -> bool {
        // Invalid caller ranges conflict, so they can never evade a deny-list.
        if (!length || begin > ~std::uint64_t{0} - length)
            return true;
        return begin < begin_ + length_ && begin_ < begin + length;
    }
    [[nodiscard]] static auto parse_edk2(const PciBarSnapshot &copied,
                                         const PciBarSnapshot &current,
                                         unsigned index,
                                         std::span<const std::byte> descriptor,
                                         unsigned physical_bits) -> std::optional<PciBarReservation> {
        if (!copied.same(current) || index > 5 || descriptor.size() != 48 || physical_bits < 32 || physical_bits > 52)
            return std::nullopt;
        const Bytes header{current.header_}, entry{descriptor};
        if ((header.get(14, 1) & 0x7f) != 0)
            return std::nullopt;
        // Locate actual BAR slots rather than treating the upper half of a
        // preceding memory64 BAR as an independent register.
        for (unsigned slot = 0; slot < index;) {
            const auto previous = header.get(16 + slot * 4, 4);
            if (previous & 1) {
                ++slot;
                continue;
            }
            const auto kind = (previous >> 1) & 3;
            if (kind == 1 || kind == 3 || (kind == 2 && slot + 1 == index))
                return std::nullopt;
            slot += kind == 2 ? 2 : 1;
        }
        const auto low = header.get(16 + index * 4, 4), kind = (low >> 1) & 3;
        if ((low & 1) || kind == 1 || kind == 3 || (kind == 2 && index == 5))
            return std::nullopt;
        const bool wide = kind == 2;
        const auto begin = (low & ~15ULL) | (wide ? header.get(20 + index * 4, 4) << 32 : 0);
        const auto length = entry.get(38), limit = std::uint64_t{1} << physical_bits;
        // The same pinned EDK2 producer emits SpecificFlag 6 for prefetchable
        // BARs and 0 otherwise. Memory BAR address bits start at bit4.
        if (entry.get(0, 1) != 0x8a || entry.get(1, 2) != 43 || entry.get(3, 1) != 0 || entry.get(4, 1) != 0 ||
            entry.get(5, 1) != ((low & 8) ? 6U : 0U) || entry.get(6) != (wide ? 64U : 32U) || entry.get(14) != begin ||
            !begin || length < 16 || (length & (length - 1)) || begin % length || entry.get(22) != length - 1 ||
            entry.get(30) != 0 || entry.get(46, 2) != 0x79 || begin >= limit || length > limit - begin ||
            (!wide && length > 0x100000000ULL - begin))
            return std::nullopt;
        return PciBarReservation{begin, length};
    }
};
class NvmeBarGrant;
// This is only permission to inspect seven documented controller registers. It
// accepts an inherited BME bit for diagnosis, but cannot issue writes, queues,
// doorbells, reset, interrupts, or DMA. finish() separately rejects active state.
class NvmeBarProbe final {
    PciBarSnapshot snapshot_;
    std::uint64_t length_;
    WindowTicket ticket_;
    NvmeBarProbe(const PciBarSnapshot &snapshot, std::uint64_t length, WindowTicket ticket)
        : snapshot_(snapshot), length_(length), ticket_(ticket) {
    }
    [[nodiscard]] static auto
    overlaps(std::uint64_t begin, std::uint64_t end, std::uint64_t other, std::uint64_t length) -> bool {
        return begin < other + length && other < end;
    }

public:
    static constexpr std::uint64_t page_bytes = 4096, maximum_bar_bytes = 0x100000;
    [[nodiscard]] static auto authorize(const PciBarSnapshot &copied,
                                        const PciBarSnapshot &current,
                                        const PciResources &bar,
                                        const PciResources &root,
                                        unsigned root_segment,
                                        std::span<const std::byte> map,
                                        std::size_t stride,
                                        std::uint64_t arena,
                                        std::uint64_t apic_page,
                                        const WindowAuthority &authority,
                                        WindowTicket ticket) -> std::optional<NvmeBarProbe> {
        const bool matched_source =
            (bar.source() == PciResourceSource::Uefi && root.source() == PciResourceSource::Uefi) ||
            (bar.source() == PciResourceSource::Edk2Stable202502Bar &&
             root.source() == PciResourceSource::Edk2Stable202502Root);
        if (!matched_source || !authority.accepts(ticket) || !copied.same(current) || !current.q35_nvme() ||
            root_segment != current.segment() || bar.count() != 1 || bar.physical_bits() != root.physical_bits() ||
            !MemoryMap{map, stride, 1}.valid())
            return std::nullopt;
        const auto &resource = bar.resources()[0];
        const auto begin = resource.begin(), length = resource.length(), end = resource.end();
        const auto limit = 1ULL << bar.physical_bits();
        if (resource.type() != 0 || resource.granularity() != 64 || (resource.specific() & ~1U) ||
            begin != current.base() || length < page_bytes || length > maximum_bar_bytes || (length & (length - 1)) ||
            begin % length || arena % page_bytes || arena >= limit || Handoff::arena_bytes > limit - arena ||
            apic_page % page_bytes || !apic_page || apic_page >= limit || page_bytes > limit - apic_page ||
            overlaps(begin, end, arena, Handoff::arena_bytes) || overlaps(begin, end, Q35Ecam::base, Q35Ecam::bytes) ||
            overlaps(begin, end, apic_page, page_bytes) || overlaps(begin, end, 0xfee00000, page_bytes) ||
            overlaps(begin, end, 0xfec00000, page_bytes))
            return std::nullopt;
        unsigned windows = 0, buses = 0;
        for (const auto &candidate : root.resources()) {
            if (candidate.type() == 0 && candidate.contains(begin, length)) {
                if (candidate.specific() & ~1U)
                    return std::nullopt;
                ++windows;
            }
            if (candidate.type() == 2 && candidate.contains(current.bus(), 1))
                ++buses;
        }
        if (windows != 1 || buses != 1)
            return std::nullopt;
        for (std::size_t at = 0; at < map.size(); at += stride) {
            const Bytes entry{map.subspan(at, stride)};
            const auto start = entry.get(8), after = start + entry.get(24) * page_bytes;
            if (after > limit)
                return std::nullopt;
            if (start >= end || after <= begin)
                continue;
            // Absent regions remain constrained by the explicit BAR/root grant.
            // Existing descriptions may only be reserved/MMIO with UC, XP, RO;
            // RAM, runtime, RP, NV, cache conflicts and unknown attributes deny.
            if ((entry.get(0, 4) != 0 && entry.get(0, 4) != 11) || (entry.get(32) & ~0x24001ULL))
                return std::nullopt;
        }
        return NvmeBarProbe{current, length, ticket};
    }
    [[nodiscard]] auto page(const WindowAuthority &authority) const -> std::optional<std::uint64_t> {
        return authority.accepts(ticket_) ? std::optional<std::uint64_t>{snapshot_.base()} : std::nullopt;
    }
    [[nodiscard]] auto length() const -> std::uint64_t {
        return length_;
    }
    [[nodiscard]] auto read_address(const WindowAuthority &authority,
                                    const PciBarSnapshot &current,
                                    std::uint64_t offset,
                                    unsigned width) const -> std::optional<std::uint64_t> {
        const bool precise = (width == 8 && (offset == 0 || offset == 0x28 || offset == 0x30)) ||
                             (width == 4 && (offset == 8 || offset == 0x14 || offset == 0x1c || offset == 0x24));
        if (!precise || !authority.accepts(ticket_) || !snapshot_.same(current))
            return std::nullopt;
        return snapshot_.base() + offset;
    }
    [[nodiscard]] auto finish(const WindowAuthority &authority,
                              const PciBarSnapshot &current,
                              std::uint64_t cap,
                              std::uint32_t version,
                              std::uint32_t cc,
                              std::uint32_t csts,
                              std::uint32_t aqa,
                              std::uint64_t asq,
                              std::uint64_t acq) const -> std::optional<NvmeBarGrant>;
};
// An inactive-controller admission receipt, retaining only the same four reads.
// No descriptor or successful probe ever grants device activation or DMA.
class NvmeBarGrant final {
    friend class NvmeBarProbe;
    NvmeBarProbe probe_;
    std::uint64_t cap_;
    std::uint32_t version_;
    NvmeBarGrant(const NvmeBarProbe &probe, std::uint64_t cap, std::uint32_t version)
        : probe_(probe), cap_(cap), version_(version) {
    }

public:
    [[nodiscard]] auto capabilities() const -> std::uint64_t {
        return cap_;
    }
    [[nodiscard]] auto version() const -> std::uint32_t {
        return version_;
    }
    [[nodiscard]] auto read_address(const WindowAuthority &authority,
                                    const PciBarSnapshot &current,
                                    std::uint64_t offset,
                                    unsigned width) const -> std::optional<std::uint64_t> {
        // Queue-register reads belong to admission only, not the final receipt.
        if (!((offset == 0 && width == 8) || (width == 4 && (offset == 8 || offset == 0x14 || offset == 0x1c))))
            return std::nullopt;
        return probe_.read_address(authority, current, offset, width);
    }
};
inline auto NvmeBarProbe::finish(const WindowAuthority &authority,
                                 const PciBarSnapshot &current,
                                 std::uint64_t cap,
                                 std::uint32_t version,
                                 std::uint32_t cc,
                                 std::uint32_t csts,
                                 std::uint32_t aqa,
                                 std::uint64_t asq,
                                 std::uint64_t acq) const -> std::optional<NvmeBarGrant> {
    // NVMe 1.4c sections 3.1.1, 3.1.2, 3.1.5, 3.1.6. This read-only
    // checkpoint records CAP without interpreting unneeded optional features.
    // Sections 3.1.8-3.1.10 define AQA/ASQ/ACQ; their all-zero values are an
    // additional profile requirement, not a general reset guarantee. ASQ/ACQ
    // reset values are implementation-specific; CC.EN=0 alone does not clear
    // these registers. All retained queues/error/shutdown/unknown status denies.
    if (!read_address(authority, current, 0, 8) || (current.command() & 6) != 2 || cc || csts || aqa || asq || acq ||
        version != 0x00010400 || cap == ~std::uint64_t{0} || (cap & 0xffff) == 0 || !(cap & (1ULL << 37)) ||
        ((cap >> 48) & 15) > ((cap >> 52) & 15))
        return std::nullopt;
    return NvmeBarGrant{*this, cap, version};
}
static_assert(sizeof(PciResources) < 1024);
static_assert(sizeof(NvmeBarProbe) < 128);
} // namespace aurora::uefi
