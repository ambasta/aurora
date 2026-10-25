#include "event-intake.hpp"
#include "event-backing.hpp"
#include "event-profile-policy.hpp"
#include "tables.hpp"
#include "../console-session.hpp"
#include "../iommu-event-session.hpp"
#include "fw-cfg-fixture.hpp"

#ifndef AURORA_UEFI_IOMMU_EVENT
#error "The finite Event bootstrap adapter requires its explicit image profile"
#endif

namespace aurora::uefi {
EventTerminal terminal asm("uefi_event_terminal") __attribute__((visibility("hidden"))){};
namespace {
using U64 = std::uint64_t;
using Policy = EventBackingPolicy;
using hardware::Io;
using Serial = console::Uart<Io>;
enum class Phase : U64 {
    cold,
    initialized,
    producing,
    quiet,
    source,
    closed,
    failed
};
enum class Failure : U64 {
    none,
    entry,
    backing,
    mapping,
    cold_registers,
    publication,
    producer,
    readiness,
    evidence,
    output,
    authority,
    final_state
};
// The case (0 denial, 1 success, 2 overflow, 3 command error) arrives in the
// fw_cfg fixture file before any device is touched.
U64 selector{};
[[nodiscard]] auto control_value() -> U64 {
    return selector == 3 ? 0x1005 : 5;
}
[[nodiscard]] auto edu_command_value() -> U64 {
    return selector == 3 ? 2 : 6;
}
constexpr U64 leaf_flags = 3 | PageTables::nx;
constexpr U64 io_flags = 1 | 8 | 16 | PageTables::nx;
constexpr U64 offsets[] = {0, 8, 0x10, 0x18, 0x30, 0x2000, 0x2008, 0x2010, 0x2018, 0x2020};
EventBacking backing asm("uefi_event_backing");
alignas(4096) std::array<std::byte, 4096> before_ring asm("uefi_event_before_ring"){};
alignas(4096) std::array<std::byte, 4096> after_ring asm("uefi_event_after_ring"){};
std::array<std::byte, Handoff::header> handoff_copy{};
std::array<U64, 12> fixed_registers{};
U64 owned_arena{}, kernel_root{}, table_pages{}, iommu_base{}, edu_base{}, edu_config{};
U64 expected_head{};
volatile U64 *window_slot{};
Phase phase{Phase::cold};
bool begun{}, window_live{}, producer_quiet{}, published{}, head_attempted{};

[[nodiscard]] auto address(const void *value) -> U64 {
    return reinterpret_cast<U64>(value);
}
[[nodiscard]] auto root() -> U64 {
    U64 value;
    asm volatile("mov %%cr3, %0" : "=r"(value));
    return value;
}
[[nodiscard]] auto interrupts_off() -> bool {
    U64 value;
    asm volatile("pushfq; pop %0" : "=r"(value));
    return (value & 0x202) == 2;
}
[[nodiscard]] auto tables() -> PageTables {
    return PageTables{kernel_root, static_cast<std::size_t>(table_pages)};
}
[[nodiscard]] auto mapping_closed() -> bool {
    return !window_live && window_slot && *window_slot == 0 && root() == kernel_root && interrupts_off();
}
[[nodiscard]] auto mapping_verified() -> bool {
    return mapping_closed() && tables().verify(owned_arena, Bytes{handoff_copy});
}
auto set_phase(Phase next) -> void {
    phase = next;
    terminal.phase = static_cast<U64>(next);
    asm volatile("" : : : "memory");
}
[[nodiscard]] auto emit_byte(std::uint8_t value) -> bool {
    if (terminal.serial_failed)
        return false;
    if (Serial::try_put(value) != console::PutResult::success) {
        terminal.serial_failed = 1;
        return false;
    }
    return true;
}
[[nodiscard]] auto emit(std::string_view text) -> bool {
    for (const auto value : text)
        if (!emit_byte(static_cast<std::uint8_t>(value)))
            return false;
    return true;
}
[[nodiscard]] auto hex(U64 value) -> bool {
    constexpr std::string_view digits = "0123456789abcdef";
    for (unsigned index = 16; index != 0; --index)
        if (!emit_byte(digits[(value >> ((index - 1) * 4)) & 15]))
            return false;
    return true;
}
[[noreturn]] auto halt() -> void {
    // This model has no debug-exit device. The supervisor must read copied
    // evidence, stop/quit QMP, and reap its exact child before claiming a result.
    asm volatile("mfence" : : "m"(terminal) : "memory");
    for (;;)
        asm volatile("cli; hlt");
}
[[nodiscard]] auto capture(bool after) -> bool;
[[nodiscard]] auto report_evidence(bool after) -> bool;
[[noreturn]] auto fail(Failure reason) -> void {
    terminal.failure = static_cast<U64>(reason);
    set_phase(Phase::failed);
    // A failed producer may have left partial data or an unexpected raw event.
    // Preserve a best-effort stable readback without another DMA submission,
    // head write, reset or release. If the device never became quiet, this is
    // only a double-read observation and retains producer_quiet=0 in RAM.
    if (published && terminal.exposed && !terminal.after_valid && mapping_closed() && capture(true))
        static_cast<void>(report_evidence(true));
    static_cast<void>(emit("AURORA_IOMMU_EVENT_FAIL: reason="));
    static_cast<void>(hex(terminal.failure));
    static_cast<void>(emit(" exposed="));
    static_cast<void>(hex(terminal.exposed));
    static_cast<void>(emit(" terminal="));
    static_cast<void>(hex(address(&terminal)));
    static_cast<void>(emit("\r\n"));
    halt();
}
auto require(bool valid, Failure reason) -> void {
    if (!valid)
        fail(reason);
}

// Only this translation unit can create a temporary mapping. Every caller
// below supplies one separately enumerated register and width. The slot is
// revoked before returning, including a failed readback; no pointer escapes.
class RegisterWindow final {
    [[nodiscard]] static auto begin(U64 physical, bool write) -> bool {
        if (!mapping_closed() || physical % 4096 || physical >= (1ULL << 40))
            return false;
        window_live = true;
        *window_slot = physical | io_flags | (write ? 2 : 0);
        asm volatile("invlpg (%0)" : : "r"(PageTables::window_address) : "memory");
        return true;
    }
    [[nodiscard]] static auto end(U64 physical, bool write) -> bool {
        const auto expected = physical | io_flags | (write ? 2 : 0);
        const auto valid = window_live && (*window_slot & ~0x60ULL) == expected;
        *window_slot = 0;
        asm volatile("invlpg (%0)" : : "r"(PageTables::window_address) : "memory");
        window_live = false;
        return valid && mapping_closed();
    }

public:
    [[nodiscard]] static auto read(U64 physical, unsigned width, U64 &value) -> bool {
        if ((width != 2 && width != 4 && width != 8) || physical % width || (physical & 4095) > 4096 - width ||
            !begin(physical & ~U64{4095}, false))
            return false;
        const auto pointer = PageTables::window_address + (physical & 4095);
        asm volatile("lfence" : : : "memory");
        if (width == 2)
            value = *reinterpret_cast<volatile const std::uint16_t *>(pointer);
        else if (width == 4)
            value = *reinterpret_cast<volatile const std::uint32_t *>(pointer);
        else
            value = *reinterpret_cast<volatile const U64 *>(pointer);
        asm volatile("lfence" : : : "memory");
        return end(physical & ~U64{4095}, false);
    }
    [[nodiscard]] static auto write(U64 physical, unsigned width, U64 value) -> bool {
        if ((width != 2 && width != 8) || physical % width || (width == 2 && value > 65535) ||
            (physical & 4095) > 4096 - width || !begin(physical & ~U64{4095}, true))
            return false;
        const auto pointer = PageTables::window_address + (physical & 4095);
        asm volatile("mfence" : : : "memory");
        if (width == 2)
            *reinterpret_cast<volatile std::uint16_t *>(pointer) = static_cast<std::uint16_t>(value);
        else
            *reinterpret_cast<volatile U64 *>(pointer) = value;
        asm volatile("mfence" : : : "memory");
        return end(physical & ~U64{4095}, true);
    }
};

[[nodiscard]] auto iommu_read(U64 offset, U64 &value) -> bool {
    return Policy::iommu_read(offset) && RegisterWindow::read(iommu_base + offset, 8, value);
}
[[nodiscard]] auto edu_read(U64 offset, U64 &value) -> bool {
    return (offset == 0 || offset == 0x80 || offset == 0x88 || offset == 0x90 || offset == 0x98) &&
           RegisterWindow::read(edu_base + offset, offset == 0 ? 4 : 8, value);
}
[[nodiscard]] auto registers(std::array<U64, 12> &result) -> bool {
    for (unsigned index = 0; index < 10; ++index)
        if (!iommu_read(offsets[index], result[index]))
            return false;
    return edu_read(0x98, result[10]) && edu_read(0x90, result[11]);
}
[[nodiscard]] auto fixed_profile(const std::array<U64, 12> &value) -> bool {
    if ((value[9] & ~iommu_event::status_mask) || value[0] != (address(backing.device_table.data()) | 1) ||
        value[1] != (selector == 3 ? address(backing.command_ring.data()) | (8ULL << 56) : 0) ||
        value[2] != (address(iommu_event::BootLifetimeRing::identity()) | (8ULL << 56)) ||
        value[3] != control_value() || value[4] != 0x29d3 || value[7] >= 4096 || value[7] % 16 || value[8] >= 4096 ||
        value[8] % 16 || (value[10] & 1))
        return false;
    return selector == 3 ? value[5] == 0 && value[6] == 16 && value[10] == 0 && value[11] == 0
                         : value[5] == 0 && value[6] == 0 && (value[9] & 16) == 0 && value[10] == 2 && value[11] == 4;
}

auto copy_ring(std::array<std::byte, 4096> &destination) -> void {
    const auto *source = reinterpret_cast<volatile const std::byte *>(iommu_event::BootLifetimeRing::identity());
    asm volatile("lfence" : : : "memory");
    for (std::size_t index = 0; index < destination.size(); ++index)
        destination[index] = source[index];
    asm volatile("lfence" : : : "memory");
}
auto copy_data(std::array<std::byte, 144> &destination) -> void {
    const std::byte *pages[] = {
        backing.secret.data(), backing.target.data(), backing.helper.data(), backing.sink.data()};
    std::size_t cursor = 0;
    asm volatile("lfence" : : : "memory");
    for (const auto *page : pages)
        for (unsigned index = 0; index < 36; ++index)
            destination[cursor++] = reinterpret_cast<volatile const std::byte *>(page)[0xf0 + index];
    asm volatile("lfence" : : : "memory");
}
[[nodiscard]] auto capture(bool after) -> bool {
    auto &saved = after ? terminal.after_registers : terminal.before_registers;
    auto &data = after ? terminal.after_data : terminal.before_data;
    auto &ring = after ? after_ring : before_ring;
    std::array<U64, 12> second{};
    if (!registers(saved))
        return false;
    copy_ring(ring);
    copy_data(data);
    if (!registers(second) || saved != second || !mapping_verified())
        return false;
    (after ? terminal.after_valid : terminal.before_valid) = 1;
    return true;
}
[[nodiscard]] auto dump_bytes(std::span<const std::byte> data) -> bool {
    constexpr std::string_view digits = "0123456789abcdef";
    for (const auto value : data) {
        const auto byte = std::to_integer<unsigned>(value);
        if (!emit_byte(digits[byte >> 4]) || !emit_byte(digits[byte & 15]))
            return false;
    }
    return true;
}
[[nodiscard]] auto report_evidence(bool after) -> bool {
    const auto label = after ? std::string_view{"post"} : std::string_view{"pre"};
    const auto &saved = after ? terminal.after_registers : terminal.before_registers;
    if (!emit("AURORA_IOMMU_EVENT_REGISTERS: phase=") || !emit(label) || !emit(" producer_quiet=") ||
        !hex(terminal.producer_quiet) || !emit(" words="))
        return false;
    for (const auto value : saved)
        if (!hex(value) || !emit("/"))
            return false;
    if (!emit("\r\nAURORA_IOMMU_EVENT_DATA: phase=") || !emit(label) || !emit(" guarded=") ||
        !dump_bytes(after ? terminal.after_data : terminal.before_data) || !emit("\r\n"))
        return false;
    const auto &ring = after ? after_ring : before_ring;
    // Print all 256 raw slots, including poison and unexpected writes. Never
    // construct a positive record from a predicted tail or transfer count.
    for (unsigned offset = 0; offset < 4096; offset += 16)
        if (!emit("AURORA_IOMMU_EVENT_RAW: phase=") || !emit(label) || !emit(" offset=") || !hex(offset) ||
            !emit(" bytes=") || !dump_bytes(std::span{ring}.subspan(offset, 16)) || !emit("\r\n"))
            return false;
    return true;
}

[[nodiscard]] auto extent_pages(U64 object, U64 bytes) -> bool {
    const Bytes handoff{handoff_copy};
    const auto start = owned_arena + Handoff::payload_offset + handoff.get(72);
    const auto length = handoff.get(80) - handoff.get(72);
    if (!Policy::page_extent(start, length, object, bytes))
        return false;
    for (U64 offset = 0; offset < bytes; offset += 4096)
        if ((tables().entry(object + offset) & ~0x60ULL) != ((object + offset) | leaf_flags))
            return false;
    return true;
}
auto establish_backing() -> void {
    const auto ring = address(iommu_event::BootLifetimeRing::identity());
    const U64 locations[] = {address(&backing), ring, address(before_ring.data()), address(after_ring.data())};
    const U64 sizes[] = {sizeof(backing), 4096, 4096, 4096};
    for (unsigned index = 0; index < 4; ++index) {
        require(extent_pages(locations[index], sizes[index]), Failure::backing);
        for (unsigned prior = 0; prior < index; ++prior)
            require(Policy::disjoint(locations[index], sizes[index], locations[prior], sizes[prior]), Failure::backing);
    }
    const Bytes handoff{handoff_copy};
    const auto begin = owned_arena + Handoff::payload_offset + handoff.get(72);
    require(Policy::contains(begin, handoff.get(80) - handoff.get(72), address(&terminal), sizeof(terminal)),
            Failure::backing);
    terminal.backing = address(&backing);
    terminal.ring = ring;
    terminal.before_ring = address(before_ring.data());
    terminal.after_ring = address(after_ring.data());
    terminal.ring_bytes = 4096;
    // Ownership is latched before the first possible device publication. From
    // this point, every failure retains the complete allocation boot-long.
    auto *ring_bytes = iommu_event::BootLifetimeRing::expose();
    terminal.exposed = 1;
    for (unsigned index = 0; index < 256; ++index) {
        put({ring_bytes, 4096}, index * 16, Policy::poison_word0 | index);
        put({ring_bytes, 4096}, index * 16 + 8, Policy::poison_word1 | (index * 16));
    }
    auto *bytes = reinterpret_cast<std::byte *>(&backing);
    for (std::size_t index = 0; index < sizeof(backing); ++index)
        bytes[index] = std::byte{0};
    put(backing.device_table,
        Policy::requester * 32,
        address(backing.page_table.data()) | 3 | (1ULL << 9) | Policy::read_permission | Policy::write_permission);
    put(backing.device_table, Policy::requester * 32 + 8, Policy::domain);
    put(backing.page_table, 3 * 8, address(backing.secret.data()) | 1 | Policy::write_permission);
    put(backing.page_table, 4 * 8, address(backing.target.data()) | 1 | Policy::read_permission);
    put(backing.page_table,
        5 * 8,
        address(backing.helper.data()) | 1 | Policy::read_permission | Policy::write_permission);
    put(backing.page_table,
        6 * 8,
        address(backing.sink.data()) | 1 | Policy::read_permission | Policy::write_permission);
    // Opcode 0 is the retained model's default-illegal command, never an
    // invalidation, completion wait, or reclamation mechanism.
    put(backing.command_ring, 0, 0);
    put(backing.command_ring, 8, 0);
    std::array<std::byte, 4096> *pages[] = {&backing.secret, &backing.target, &backing.helper, &backing.sink};
    constexpr U64 values[] = {0xe8c6a482, 0xa7856341, 0x192b4d6f, 0x7896b4d2};
    for (unsigned page = 0; page < 4; ++page) {
        for (unsigned index = 0; index < 16; ++index) {
            (*pages[page])[0xf0 + index] = std::byte(0xa0 + index);
            (*pages[page])[0x104 + index] = std::byte(0x50 + index);
        }
        put(*pages[page], 0x100, values[page], 4);
    }
    set_phase(Phase::initialized);
}

auto publish_profile() -> void {
    require(phase == Phase::initialized && !published && mapping_verified(), Failure::publication);
    U64 value{};
    require(edu_read(0, value) && value == 0x010000ed && edu_read(0x98, value) && value == 0 && edu_read(0x90, value) &&
                value == 0 && RegisterWindow::read(edu_config + 4, 2, value) && value == 2,
            Failure::cold_registers);
    for (const auto offset : offsets)
        require(iommu_read(offset, value) && value == (offset == 0x30 ? 0x29d3 : 0), Failure::cold_registers);
    published = true;
    require(RegisterWindow::write(iommu_base, 8, address(backing.device_table.data()) | 1) &&
                RegisterWindow::write(iommu_base + 0x10, 8, terminal.ring | (8ULL << 56)),
            Failure::publication);
    if (selector == 3)
        require(RegisterWindow::write(iommu_base + 8, 8, address(backing.command_ring.data()) | (8ULL << 56)),
                Failure::publication);
    require(RegisterWindow::write(iommu_base + 0x18, 8, control_value()), Failure::publication);
    // The only PCI configuration write is the exact admitted EDU command word.
    // No status DWORD is overwritten and no generic configuration API escapes.
    if (selector != 3)
        require(RegisterWindow::write(edu_config + 4, 2, edu_command_value()), Failure::publication);
    require(RegisterWindow::read(edu_config + 4, 2, value) && value == edu_command_value(), Failure::publication);
    set_phase(Phase::producing);
}
auto transfer(U64 iova, bool write) -> void {
    require(phase == Phase::producing && !producer_quiet && Policy::producer_iova(iova, write) &&
                terminal.dma_submitted == terminal.dma_completed && terminal.dma_submitted < 258,
            Failure::producer);
    U64 value{};
    require(edu_read(0x98, value) && (value == 0 || value == 2), Failure::producer);
    const auto source = write ? 0x40000 : iova;
    const auto destination = write ? iova : 0x40000;
    require(RegisterWindow::write(edu_base + 0x80, 8, source) &&
                RegisterWindow::write(edu_base + 0x88, 8, destination) &&
                RegisterWindow::write(edu_base + 0x90, 8, 4) && edu_read(0x80, value) && value == source &&
                edu_read(0x88, value) && value == destination && edu_read(0x90, value) && value == 4,
            Failure::producer);
    ++terminal.dma_submitted;
    require(RegisterWindow::write(edu_base + 0x98, 8, write ? 3 : 1), Failure::producer);
    bool completed = false;
    for (U64 attempt = 0; attempt < Policy::readiness_attempts; ++attempt) {
        ++terminal.readiness_reads;
        require(edu_read(0x98, value) && (value == (write ? 3U : 1U) || value == (write ? 2U : 0U)), Failure::producer);
        if ((value & 1) == 0) {
            completed = true;
            break;
        }
        asm volatile("pause" : : : "memory");
    }
    require(completed && edu_read(0x90, value) && value == 4, Failure::readiness);
    ++terminal.dma_completed;
}
auto produce() -> void {
    if (selector == 3) {
        require(phase == Phase::producing && RegisterWindow::write(iommu_base + 0x2008, 8, 16), Failure::producer);
        bool stopped = false;
        U64 status{};
        for (U64 attempt = 0; attempt < Policy::readiness_attempts; ++attempt) {
            ++terminal.readiness_reads;
            require(iommu_read(0x2020, status) && (status & ~iommu_event::status_mask) == 0, Failure::producer);
            if ((status & 16) == 0) {
                stopped = true;
                break;
            }
            asm volatile("pause" : : : "memory");
        }
        require(stopped, Failure::readiness);
    } else {
        transfer(Policy::helper_iova, false);
        if (selector == 0) {
            transfer(Policy::secret_iova, false);
            transfer(Policy::sink_iova, true);
            transfer(Policy::helper_iova, false);
            transfer(Policy::target_iova, true);
        } else if (selector == 1) {
            transfer(Policy::sink_iova, true);
        } else {
            // Fill with actual model-produced denials. Never fabricate valid
            // records or move tail/head to imitate a full ring.
            for (unsigned index = 0; index < 256; ++index)
                transfer(Policy::target_iova, true);
        }
    }
    require(terminal.dma_completed == terminal.dma_submitted && mapping_verified(), Failure::producer);
    require(registers(fixed_registers) && fixed_profile(fixed_registers), Failure::producer);
    producer_quiet = true;
    terminal.producer_quiet = 1;
    set_phase(Phase::quiet);
}

[[nodiscard]] auto quiet() -> bool {
    return producer_quiet && (phase == Phase::quiet || phase == Phase::source || phase == Phase::closed) &&
           terminal.dma_completed == terminal.dma_submitted && mapping_verified() && Io::read(0x3f9) == 0;
}
class EventTransport final {
public:
    [[nodiscard]] static auto snapshot() -> iommu_event::Snapshot {
        std::array<U64, 12> value{};
        U64 command{};
        const bool okay = producer_quiet && mapping_closed() && registers(value) && fixed_profile(value) &&
                          RegisterWindow::read(edu_config + 4, 2, command) && command == edu_command_value() &&
                          Policy::frozen_registers_match(value, fixed_registers);
        return {iommu_event::BootLifetimeRing::identity(),
                value[2],
                value[3],
                value[7],
                value[8],
                value[9],
                okay,
                producer_quiet};
    }
    [[nodiscard]] static auto copy_record(U64 offset) -> iommu_event::RecordCopy {
        if (!quiet() || phase != Phase::source || offset != expected_head || offset >= 4096 || offset % 16)
            return {};
        const auto *words = reinterpret_cast<volatile const U64 *>(terminal.ring + offset);
        asm volatile("lfence" : : : "memory");
        const auto first = words[0], second = words[1];
        asm volatile("lfence" : : : "memory");
        return {first, second, true};
    }
    [[nodiscard]] static auto publish_head(U64 next) -> bool {
        if (!quiet() || phase != Phase::source || head_attempted || !Policy::head_step(expected_head, next))
            return false;
        // Consume the one attempt before MMIO. Failure never restores retry
        // authority, scrubs pending bytes, or submits further producer work.
        head_attempted = true;
        if (!RegisterWindow::write(iommu_base + 0x2010, 8, next))
            return false;
        U64 observed{};
        if (!iommu_read(0x2010, observed) || observed != next)
            return false;
        expected_head = next;
        head_attempted = false;
        ++terminal.acknowledgements;
        return true;
    }
};
class ServicePlatform final {
public:
    [[nodiscard]] static auto quiet() -> bool {
        return aurora::uefi::quiet();
    }
    [[noreturn]] static auto wait() -> void {
        aurora::uefi::fail(Failure::authority);
    }
    [[noreturn]] static auto fail() -> void {
        aurora::uefi::fail(Failure::authority);
    }
};
class OutputTransport final {
public:
    [[nodiscard]] static auto try_put(std::uint8_t value) -> console::PutResult {
        if (!emit_byte(value))
            return console::PutResult::timeout;
        ++terminal.output_bytes;
        return console::PutResult::success;
    }
    [[nodiscard]] static auto next() -> console::Sample {
        ServicePlatform::fail();
    }
};
using EventSession = iommu_event::Session<EventTransport, ServicePlatform>;
using ConsoleSession = console::Session<OutputTransport, ServicePlatform>;
using Entry = iommu_event::Entry<EventSession, ConsoleSession, ServicePlatform>;

[[nodiscard]] auto validate_pre_evidence() -> bool {
    const auto &raw = terminal.before_registers;
    if (!fixed_profile(raw) || raw[7] != 0 || terminal.before_data[16] != std::byte{0x82} ||
        Bytes{backing.secret}.get(0x100, 4) != 0xe8c6a482 || Bytes{backing.target}.get(0x100, 4) != 0xa7856341 ||
        Bytes{backing.helper}.get(0x100, 4) != 0x192b4d6f)
        return false;
    for (unsigned page = 0; page < 4; ++page)
        for (unsigned index = 0; index < 16; ++index)
            if (terminal.before_data[page * 36 + index] != std::byte(0xa0 + index) ||
                terminal.before_data[page * 36 + 20 + index] != std::byte(0x50 + index))
                return false;
    const unsigned count = selector == 0 ? 2 : selector == 1 ? 0 : selector == 2 ? 255 : 1;
    if (raw[8] != count * 16 || raw[9] != (selector == 2 ? 0xb : selector == 1 ? 8 : 0xa))
        return false;
    for (unsigned index = 0; index < 256; ++index) {
        U64 first = Policy::poison_word0 | index, second = Policy::poison_word1 | (index * 16);
        if (index < count) {
            first = selector == 3 ? 5ULL << 60 : Policy::fault_word(selector == 2 || index == 1);
            second = selector == 3                 ? address(backing.command_ring.data())
                     : selector == 2 || index == 1 ? Policy::target_iova
                                                   : Policy::secret_iova;
        }
        if (Bytes{before_ring}.get(index * 16) != first || Bytes{before_ring}.get(index * 16 + 8) != second)
            return false;
    }
    if (selector == 0) {
        for (unsigned index = 0; index < 4; ++index)
            if (backing.sink[0x100 + index] == backing.secret[0x100 + index] ||
                backing.sink[0x100 + index] == std::byte(0x7896b4d2ULL >> (index * 8)))
                return false;
    } else if (selector == 1) {
        if (Bytes{backing.sink}.get(0x100, 4) != 0x192b4d6f)
            return false;
    } else if (Bytes{backing.sink}.get(0x100, 4) != 0x7896b4d2)
        return false;
    return true;
}
[[nodiscard]] auto validate_post_evidence(iommu_event::Completion completion) -> bool {
    if (before_ring != after_ring || terminal.before_data != terminal.after_data ||
        !fixed_profile(terminal.after_registers))
        return false;
    for (unsigned index = 0; index < 12; ++index)
        if (index != 7 && terminal.before_registers[index] != terminal.after_registers[index])
            return false;
    const auto committed = selector == 0 ? 2U : 0U;
    const auto expected = selector == 3 ? iommu_event::Completion::command_error : iommu_event::Completion::drained;
    return completion == expected && terminal.acknowledgements == committed &&
           terminal.after_registers[7] == committed * 16 && terminal.polls == (selector == 0 ? 3U : 1U);
}
} // namespace

auto event_entry(const iommu_event::IntakeArgument *) -> U64 asm("__au_runtime_iommu_event_entry")
    __attribute__((visibility("hidden")));
auto event_poll(const void *, U64, iommu_event::RawSample *) -> void asm("__au_runtime_iommu_event_poll")
    __attribute__((visibility("hidden")));
auto event_poll(const void *grant, U64 generation, iommu_event::RawSample *output) -> void {
    ++terminal.polls;
    *output = EventSession::poll(grant, generation);
}
auto event_acknowledge(const void *, U64) -> U64 asm("__au_runtime_iommu_event_acknowledge")
    __attribute__((visibility("hidden")));
auto event_acknowledge(const void *grant, U64 generation) -> U64 {
    return EventSession::acknowledge(grant, generation);
}
auto event_output(const void *, U64, U64) -> U64 asm("__au_runtime_console_put") __attribute__((visibility("hidden")));
auto event_output(const void *grant, U64 generation, U64 byte) -> U64 {
    return ConsoleSession::put(grant, generation, byte);
}

[[noreturn]] auto run_event_intake(U64 arena, const Bytes &handoff, const EventAdmission &admission) -> void {
    require(!begun && phase == Phase::cold && !iommu_event::BootLifetimeRing::exposed(), Failure::entry);
    begun = true;
    terminal.magic = 0x41554556494e5431ULL;
    terminal.version = 1;
    using fw_cfg::Fixture;
    const auto fixture = fw_cfg::FwCfg::read(Fixture::event_denial, Fixture::event_command_error);
    require(fixture.has_value(), Failure::entry);
    selector = static_cast<U64>(*fixture) - static_cast<U64>(Fixture::event_denial);
    terminal.selector = selector;
    terminal.completion = UINT64_MAX;
    owned_arena = arena;
    kernel_root = handoff.get(88);
    table_pages = handoff.get(96);
    iommu_base = admission.iommu_base();
    edu_base = admission.edu_base();
    edu_config = admission.edu_config_address();
    for (unsigned offset = 0; offset < Handoff::header; offset += 8)
        put(handoff_copy, offset, handoff.get(offset));
    require(Handoff::valid(handoff_copy, arena) && handoff.get(8, 4) == 4 && root() == kernel_root &&
                interrupts_off() && admission.edu_initial_command() == 2 && iommu_base == 0xfed80000 &&
                edu_config == 0xe0020000 && admission.physical_bits() >= 40,
            Failure::entry);
    const Bytes record{{reinterpret_cast<const std::byte *>(handoff.get(120)), 4096}};
    require(record.get(0) == 0x3154564541525541ULL, Failure::entry);
    const auto map_bytes = std::span<const std::byte>{reinterpret_cast<const std::byte *>(arena + Handoff::map_offset),
                                                      static_cast<std::size_t>(handoff.get(32))};
    const MemoryMap map{
        map_bytes, static_cast<std::size_t>(handoff.get(40)), static_cast<std::uint32_t>(handoff.get(48, 4))};
    require(map.owns(arena, Handoff::arena_bytes) && tables().verify(arena, handoff), Failure::entry);
    U64 stack, cr0, cr4;
    asm volatile("mov %%rsp, %0; mov %%cr0, %1; mov %%cr4, %2" : "=r"(stack), "=r"(cr0), "=r"(cr4));
    require(stack % 8 == 0 && stack >= arena + Handoff::stack_bottom + 4096 && stack <= arena + Handoff::stack_top &&
                (cr0 & (1ULL << 16)) &&
                (cr4 & ((1ULL << 7) | (1ULL << 12) | (1ULL << 16) | (1ULL << 17) | (1ULL << 18) | (1ULL << 20))) == 0,
            Failure::entry);
    std::uint32_t low, high;
    asm volatile("rdmsr" : "=a"(low), "=d"(high) : "c"(0x277));
    require((low & 255) == 6 && (low >> 24) == 0, Failure::mapping);
    asm volatile("rdmsr" : "=a"(low), "=d"(high) : "c"(0xc0000080));
    require((low & (1U << 11)) != 0, Failure::mapping);
    window_slot = tables().window_slot();
    require(mapping_verified() && (Io::read(0x3fb) & 0x80) == 0, Failure::mapping);
    Io::write(0x3f9, 0);
    require(Io::read(0x3f9) == 0, Failure::entry);
    establish_backing();
    require(emit("AURORA_IOMMU_EVENT_BACKING: terminal=") && hex(address(&terminal)) && emit(" data=") &&
                hex(terminal.backing) && emit(" ring=") && hex(terminal.ring) && emit(" pre=") &&
                hex(terminal.before_ring) && emit(" post=") && hex(terminal.after_ring) && emit("\r\n"),
            Failure::output);
    publish_profile();
    produce();
    require(capture(false), Failure::evidence);
    require(report_evidence(false), Failure::output);
    // Preserve both raw evidence and failed protected/sink bytes before judging
    // model expectations. A mismatch cannot hide behind a source success marker.
    require(validate_pre_evidence(), Failure::evidence);
    terminal.checks |= 1;
    if (selector == 2) {
        // The existing session deliberately rejects overflow at initial open.
        // Keep that boundary: report a pre-entry loss with no fabricated grant.
        terminal.completion = static_cast<U64>(iommu_event::Completion::loss_detected);
        require(capture(true) && report_evidence(true) && before_ring == after_ring &&
                    terminal.before_registers == terminal.after_registers &&
                    terminal.before_data == terminal.after_data,
                Failure::evidence);
        terminal.checks |= 2;
    } else {
        require(quiet(), Failure::authority);
        const auto events = EventSession::open();
        const auto console = ConsoleSession::open();
        const iommu_event::IntakeArgument argument{
            events.grant, events.generation, console.grant, console.generation, 256, 255};
        set_phase(Phase::source);
        terminal.entered = 1;
        const auto completion = Entry::invoke(&argument, argument, [](const auto *incoming) {
            return event_entry(incoming);
        });
        terminal.completion = static_cast<U64>(completion);
        set_phase(Phase::closed);
        require(capture(true), Failure::evidence);
        if (completion == iommu_event::Completion::output_failure)
            fail(Failure::output);
        require(report_evidence(true), Failure::output);
        require(validate_post_evidence(completion), Failure::final_state);
        terminal.checks |= 2;
    }
    set_phase(Phase::closed);
    require(quiet() && emit("AURORA_IOMMU_EVENT_TERMINAL: case=") && hex(selector) && emit(" completion=") &&
                hex(terminal.completion) && emit(" checks=") && hex(terminal.checks) && emit(" submitted=") &&
                hex(terminal.dma_submitted) && emit(" completed=") && hex(terminal.dma_completed) && emit(" polls=") &&
                hex(terminal.polls) && emit(" acknowledged=") && hex(terminal.acknowledgements) &&
                emit(" readiness=") && hex(terminal.readiness_reads) && emit(" entered=") && hex(terminal.entered) &&
                emit("\r\n"),
            Failure::output);
    halt();
}
} // namespace aurora::uefi
