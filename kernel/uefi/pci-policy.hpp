#pragma once
#include "acpi-policy.hpp"

namespace aurora::uefi {
class EcamAllocation final {
public:
    std::uint64_t base{};
    std::uint16_t segment{};
    std::uint8_t start_bus{}, end_bus{};
};

// MCFG is an address description. Parsing it never grants access to MMIO.
class Mcfg final {
    std::array<EcamAllocation, 4> allocations_{};
    std::size_t count_{};
    unsigned physical_bits_{};
    Mcfg() = default;

public:
    [[nodiscard]] auto count() const -> std::size_t {
        return count_;
    }
    [[nodiscard]] auto allocations() const -> std::span<const EcamAllocation> {
        return {allocations_.data(), count_};
    }
    [[nodiscard]] auto physical_bits() const -> unsigned {
        return physical_bits_;
    }
    [[nodiscard]] static auto parse(std::span<const std::byte> bytes, unsigned physical_bits) -> std::optional<Mcfg> {
        if (physical_bits < 32 || physical_bits > 52 || !Acpi::table(bytes, "MCFG") || bytes.size() < 60 ||
            Bytes{bytes}.get(8, 1) != 1 || Bytes{bytes}.get(36) != 0 || (bytes.size() - 44) % 16 ||
            (bytes.size() - 44) / 16 > 4)
            return std::nullopt;
        const auto limit = 1ULL << physical_bits;
        Mcfg result;
        result.physical_bits_ = physical_bits;
        for (std::size_t at = 44; at < bytes.size(); at += 16) {
            const Bytes entry{bytes.subspan(at, 16)};
            EcamAllocation allocation{entry.get(0),
                                      static_cast<std::uint16_t>(entry.get(8, 2)),
                                      static_cast<std::uint8_t>(entry.get(10, 1)),
                                      static_cast<std::uint8_t>(entry.get(11, 1))};
            // The base addresses bus zero, even for an allocation whose first bus is nonzero.
            const auto first = std::uint64_t{allocation.start_bus} << 20;
            const auto after = (std::uint64_t{allocation.end_bus} + 1) << 20;
            if (entry.get(12, 4) != 0 || allocation.base % 0x10000000ULL || allocation.start_bus > allocation.end_bus ||
                allocation.base >= limit || after > limit - allocation.base)
                return std::nullopt;
            const auto begin = allocation.base + first, end = allocation.base + after;
            for (const auto &previous : result.allocations()) {
                const auto previous_begin = previous.base + (std::uint64_t{previous.start_bus} << 20);
                const auto previous_end = previous.base + ((std::uint64_t{previous.end_bus} + 1) << 20);
                if ((begin < previous_end && previous_begin < end) ||
                    (allocation.segment == previous.segment && allocation.start_bus <= previous.end_bus &&
                     previous.start_bus <= allocation.end_bus))
                    return std::nullopt;
            }
            result.allocations_[result.count_++] = allocation;
        }
        return result;
    }
    [[nodiscard]] auto address(unsigned segment, unsigned bus, unsigned device, unsigned function) const
        -> std::optional<std::uint64_t> {
        if (segment > 65535 || bus > 255 || device > 31 || function > 7)
            return std::nullopt;
        for (const auto &allocation : allocations()) {
            if (segment != allocation.segment || bus < allocation.start_bus || bus > allocation.end_bus)
                continue;
            const auto offset =
                (std::uint64_t{bus} << 20) + (std::uint64_t{device} << 15) + (std::uint64_t{function} << 12);
            const auto limit = 1ULL << physical_bits_;
            if (allocation.base >= limit || offset > limit - allocation.base || 4096 > limit - allocation.base - offset)
                return std::nullopt;
            return allocation.base + offset;
        }
        return std::nullopt;
    }
};

// This explicit emulator contract, plus exclusion of owned/firmware memory, is
// the authority for read-only ECAM. It is not a general firmware resource grant.
class Q35Ecam final {
    Q35Ecam() = default;

public:
    // OVMF programs the Q35 PCIEXBAR to this aperture after QEMU reset.
    static constexpr std::uint64_t base = 0xe0000000ULL;
    static constexpr std::uint64_t bytes = 0x10000000ULL;
    static constexpr std::uint64_t end = base + bytes;
    [[nodiscard]] static auto
    authorize(const Mcfg &mcfg, std::span<const std::byte> map, std::size_t stride, std::uint64_t arena)
        -> std::optional<Q35Ecam> {
        if (mcfg.count() != 1 || !MemoryMap{map, stride, 1}.valid())
            return std::nullopt;
        const auto &allocation = mcfg.allocations()[0];
        const auto limit = 1ULL << mcfg.physical_bits();
        if (allocation.base != base || allocation.segment != 0 || allocation.start_bus != 0 ||
            allocation.end_bus != 255 || arena % 4096 || arena >= limit || Handoff::arena_bytes > limit - arena ||
            (arena < end && base < arena + Handoff::arena_bytes))
            return std::nullopt;
        for (std::size_t at = 0; at < map.size(); at += stride) {
            const Bytes entry{map.subspan(at, stride)};
            const auto begin = entry.get(8), after = begin + entry.get(24) * 4096, type = entry.get(0, 4);
            if (after > limit)
                return std::nullopt;
            if (begin >= end || after <= base)
                continue;
            if ((type != 0 && type != 11) || (entry.get(32) & ((1ULL << 63) | 0x8000ULL)))
                return std::nullopt;
        }
        return Q35Ecam{};
    }
    [[nodiscard]] auto contains(std::uint64_t physical, std::uint64_t size) const -> bool {
        return physical >= base && physical < end && size > 0 && size <= end - physical;
    }
    [[nodiscard]] auto admits_page(std::uint64_t physical) const -> bool {
        return physical % 4096 == 0 && contains(physical, 4096);
    }
    [[nodiscard]] auto address(unsigned segment, unsigned bus, unsigned device, unsigned function) const
        -> std::optional<std::uint64_t> {
        if (segment != 0 || bus > 255 || device > 31 || function > 7)
            return std::nullopt;
        const auto physical =
            base + (std::uint64_t{bus} << 20) + (std::uint64_t{device} << 15) + (std::uint64_t{function} << 12);
        return admits_page(physical) ? std::optional<std::uint64_t>{physical} : std::nullopt;
    }
};

class PciFunction final {
public:
    std::uint16_t segment{}, vendor{}, device_id{}, command{};
    std::uint8_t bus{}, device{}, function{}, class_code{}, subclass{}, programming_interface{}, revision{},
        header_type{};
    std::uint8_t secondary_bus{}, subordinate_bus{};
};

class PciInventory final {
    class Route final {
    public:
        unsigned bus{}, last{}, parent{};
    };
    std::array<PciFunction, 256> functions_{};
    std::size_t count_{}, bus_count_{};
    PciInventory() = default;

public:
    static constexpr std::size_t maximum_functions = 256;
    static constexpr std::size_t maximum_buses = 64;
    [[nodiscard]] auto count() const -> std::size_t {
        return count_;
    }
    [[nodiscard]] auto bus_count() const -> std::size_t {
        return bus_count_;
    }
    [[nodiscard]] auto functions() const -> std::span<const PciFunction> {
        return {functions_.data(), count_};
    }
    // Reader returns an independent optional<array<byte,64>> snapshot, never a
    // mapped view or write capability. No partial inventory escapes failure.
    template <class Reader>
    [[nodiscard]] static auto scan(const Q35Ecam &aperture, Reader &&reader) -> std::optional<PciInventory> {
        PciInventory result;
        std::array<Route, maximum_buses> routes{};
        routes[0] = Route{0, 255, maximum_buses};
        std::size_t scheduled = 1;
        for (std::size_t current = 0; current < scheduled; ++current) {
            const auto bus = routes[current].bus;
            ++result.bus_count_;
            for (unsigned device = 0; device < 32; ++device) {
                unsigned function_limit = 1;
                for (unsigned function = 0; function < function_limit; ++function) {
                    const auto physical = aperture.address(0, bus, device, function);
                    if (!physical)
                        return std::nullopt;
                    const std::optional<std::array<std::byte, 64>> snapshot = reader(*physical);
                    if (!snapshot)
                        return std::nullopt;
                    const Bytes header{*snapshot};
                    const auto vendor = header.get(0, 2);
                    if (vendor == 0xffff)
                        continue;
                    const auto kind = header.get(14, 1) & 0x7f;
                    if (vendor == 0 || kind > 1 || result.count_ == maximum_functions)
                        return std::nullopt;
                    const bool bridge_class = header.get(11, 1) == 6 && header.get(10, 1) == 4;
                    if ((kind == 1) != bridge_class)
                        return std::nullopt;
                    if (function == 0 && (header.get(14, 1) & 0x80))
                        function_limit = 8;
                    PciFunction found{};
                    found.vendor = static_cast<std::uint16_t>(vendor);
                    found.device_id = static_cast<std::uint16_t>(header.get(2, 2));
                    found.command = static_cast<std::uint16_t>(header.get(4, 2));
                    found.bus = static_cast<std::uint8_t>(bus);
                    found.device = static_cast<std::uint8_t>(device);
                    found.function = static_cast<std::uint8_t>(function);
                    found.class_code = static_cast<std::uint8_t>(header.get(11, 1));
                    found.subclass = static_cast<std::uint8_t>(header.get(10, 1));
                    found.programming_interface = static_cast<std::uint8_t>(header.get(9, 1));
                    found.revision = static_cast<std::uint8_t>(header.get(8, 1));
                    found.header_type = static_cast<std::uint8_t>(kind);
                    if (kind == 1) {
                        const auto primary = header.get(24, 1), secondary = header.get(25, 1),
                                   subordinate = header.get(26, 1);
                        if (primary != bus)
                            return std::nullopt;
                        found.secondary_bus = static_cast<std::uint8_t>(secondary);
                        found.subordinate_bus = static_cast<std::uint8_t>(subordinate);
                        // Firmware may leave a bridge unconfigured. Inventory it,
                        // but never assign buses or probe beyond its current route.
                        if (secondary != 0 || subordinate != 0) {
                            if (secondary <= bus || subordinate < secondary || subordinate > routes[current].last ||
                                !aperture.address(0, secondary, 0, 0) || !aperture.address(0, subordinate, 31, 7) ||
                                scheduled == maximum_buses)
                                return std::nullopt;
                            for (std::size_t previous = 0; previous < scheduled; ++previous) {
                                if (secondary == routes[previous].bus)
                                    return std::nullopt;
                                bool ancestor = false;
                                for (auto at = current; at < scheduled; at = routes[at].parent) {
                                    if (at == previous) {
                                        ancestor = true;
                                        break;
                                    }
                                }
                                if (!ancestor && secondary <= routes[previous].last &&
                                    routes[previous].bus <= subordinate)
                                    return std::nullopt;
                            }
                            routes[scheduled++] = Route{static_cast<unsigned>(secondary),
                                                        static_cast<unsigned>(subordinate),
                                                        static_cast<unsigned>(current)};
                        }
                    }
                    result.functions_[result.count_++] = found;
                }
            }
        }
        return result;
    }
};
static_assert(sizeof(PciFunction) == 18);
static_assert(sizeof(PciInventory) < 8192);
} // namespace aurora::uefi
