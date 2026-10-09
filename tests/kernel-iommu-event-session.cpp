#include "../kernel/console-session.hpp"
#include "../kernel/iommu-event-session.hpp"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <sys/wait.h>
#include <unistd.h>

namespace {
using namespace aurora::iommu_event;
class Counts final {
public:
    unsigned reads{}, copies{}, writes{}, console{}, entries{};
    auto operator==(const Counts &) const -> bool = default;
};
Counts counts{}, expected{};
Snapshot registers{};
ServiceArgument argument{};
aurora::console::ServiceArgument console_argument{};
std::byte *ring{};
bool quiescent = true, fail_expected{}, copy_okay = true, write_okay = true, change_head = true;
bool reenter_copy{}, reenter_write{}, reenter_open{};
std::uint64_t last_written{};
enum class Fault {
    none,
    overflow,
    unknown_status,
    invalid_head,
    drift_head,
    invalid_tail,
    drift_tail,
    drift_identity,
    drift_base,
    drift_control,
    stopped_log,
    read_failure,
    producer_active
};
Fault fault{};
unsigned fault_on_read{};

auto need(bool condition, const char *message) -> void {
    if (!condition) {
        std::fprintf(stderr, "FAIL: %s\n", message);
        std::abort();
    }
}
auto inject() -> void {
    switch (fault) {
    case Fault::none:
        break;
    case Fault::overflow:
        registers.status |= 1;
        break;
    case Fault::unknown_status:
        registers.status |= std::uint64_t{1} << 63;
        break;
    case Fault::invalid_head:
        registers.head = 1;
        break;
    case Fault::drift_head:
        registers.head = (registers.head + 16) % ring_bytes;
        break;
    case Fault::invalid_tail:
        registers.tail = ring_bytes;
        break;
    case Fault::drift_tail:
        registers.tail = (registers.tail + 16) % ring_bytes;
        break;
    case Fault::drift_identity:
        registers.ring = &registers;
        break;
    case Fault::drift_base:
        registers.base += ring_bytes;
        break;
    case Fault::drift_control:
        registers.control ^= 0x1000;
        break;
    case Fault::stopped_log:
        registers.status &= ~std::uint64_t{8};
        break;
    case Fault::read_failure:
        registers.okay = false;
        break;
    case Fault::producer_active:
        registers.producer_quiet = false;
        break;
    }
}
class Transport final {
public:
    [[nodiscard]] static auto snapshot() -> Snapshot;
    [[nodiscard]] static auto copy_record(std::uint64_t head) -> RecordCopy;
    [[nodiscard]] static auto publish_head(std::uint64_t head) -> bool;
};
class Platform final {
public:
    [[nodiscard]] static auto quiet() -> bool {
        return quiescent;
    }
    [[noreturn]] static auto fail() -> void {
        if (!fail_expected || !(counts == expected)) {
            std::fprintf(stderr,
                         "unexpected fail/effects: reads=%u copies=%u writes=%u console=%u entries=%u\n",
                         counts.reads,
                         counts.copies,
                         counts.writes,
                         counts.console,
                         counts.entries);
            std::_Exit(78);
        }
        std::_Exit(77);
    }
};
using Service = Session<Transport, Platform>;
auto Transport::snapshot() -> Snapshot {
    ++counts.reads;
    if (reenter_open)
        static_cast<void>(Service::open());
    if (counts.reads == fault_on_read)
        inject();
    return registers;
}
auto Transport::copy_record(std::uint64_t head) -> RecordCopy {
    ++counts.copies;
    need(head == registers.head && head <= ring_bytes - record_bytes && head % record_bytes == 0,
         "copy uses only the validated pending slot");
    if (reenter_copy)
        static_cast<void>(Service::poll(argument.grant, argument.generation));
    RecordCopy result{};
    std::memcpy(&result.word0, ring + head, 8);
    std::memcpy(&result.word1, ring + head + 8, 8);
    result.okay = copy_okay;
    return result;
}
auto Transport::publish_head(std::uint64_t head) -> bool {
    ++counts.writes;
    last_written = head;
    if (change_head)
        registers.head = head;
    if (reenter_write)
        static_cast<void>(Service::acknowledge(argument.grant, argument.generation));
    return write_okay;
}
class ConsoleTransport final {
public:
    [[nodiscard]] static auto try_put(std::uint8_t) -> aurora::console::PutResult {
        ++counts.console;
        return aurora::console::PutResult::success;
    }
};
using Console = aurora::console::Session<ConsoleTransport, Platform>;
using Intake = Entry<Service, Console, Platform>;

auto seed(std::uint64_t head = 0, std::uint64_t tail = 16) -> void {
    need(!BootLifetimeRing::exposed(), "each hosted case starts with unexposed static backing");
    ring = BootLifetimeRing::expose();
    need(BootLifetimeRing::exposed() && ring == BootLifetimeRing::identity(), "exposure pins the exact backing");
    need(reinterpret_cast<std::uintptr_t>(ring) % ring_bytes == 0, "fixed backing is page aligned");
    registers = {ring, (std::uint64_t{8} << 56) | 0x100000, 5, head, tail, 0xa, true, true};
}
auto record(std::uint64_t offset, std::uint64_t word0, std::uint64_t word1) -> void {
    need(offset <= ring_bytes - record_bytes && offset % record_bytes == 0, "hosted fixture record offset");
    std::memcpy(ring + offset, &word0, 8);
    std::memcpy(ring + offset + 8, &word1, 8);
}
auto open(std::uint64_t head = 0, std::uint64_t tail = 16) -> void {
    seed(head, tail);
    record(head, 0x2000000000000042ULL, 0xfedcba9876543210ULL);
    argument = Service::open();
}
auto poll() -> RawSample {
    return Service::poll(argument.grant, argument.generation);
}
auto acknowledge() -> std::uint64_t {
    return Service::acknowledge(argument.grant, argument.generation);
}
auto is_result(const RawSample &sample, PollResult result) -> bool {
    return sample.result == static_cast<std::uint64_t>(result) && sample.status_low <= status_mask &&
           (result == PollResult::record || (sample.word0 == 0 && sample.word1 == 0));
}
template <class Test>
auto rejects(Test test, unsigned reads = 0, unsigned copies = 0, unsigned writes = 0, unsigned entries = 0) -> void {
    const auto child = fork();
    need(child >= 0, "fork hostile operation");
    if (child == 0) {
        fail_expected = true;
        expected = counts;
        expected.reads += reads;
        expected.copies += copies;
        expected.writes += writes;
        expected.entries += entries;
        test();
        std::_Exit(1);
    }
    int status{};
    need(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 77,
         "hostile operation fails before forbidden effects");
}
template <class Test> auto isolated(Test test) -> void {
    const auto child = fork();
    need(child >= 0, "fork isolated hosted case");
    if (child == 0) {
        test();
        std::_Exit(0);
    }
    int status{};
    need(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0,
         "isolated hosted case passed");
}
auto terminal(Completion completion) -> void {
    const auto previous = counts;
    std::array<std::byte, ring_bytes> preserved{};
    std::memcpy(preserved.data(), ring, ring_bytes);
    rejects([] {
        static_cast<void>(poll());
    });
    rejects([] {
        static_cast<void>(acknowledge());
    });
    need(Service::close(argument, static_cast<std::uint64_t>(completion)) == completion, "terminal close succeeds");
    need(counts == previous && BootLifetimeRing::exposed() && ring == BootLifetimeRing::identity(),
         "terminal close retains exact exposed backing without transport effects");
    need(std::memcmp(preserved.data(), ring, ring_bytes) == 0, "terminal close never scrubs exposed records");
    rejects([] {
        static_cast<void>(Service::open());
    });
    rejects([] {
        static_cast<void>(Service::close(argument, 0));
    });
}

auto copied_fifo_and_wrap() -> void {
    open(4080, 32);
    record(4080, 11, 111);
    record(0, 22, 222);
    record(16, 33, 333);
    for (const auto expected_word : {11ULL, 22ULL, 33ULL}) {
        auto sample = poll();
        need(is_result(sample, PollResult::record) && sample.word0 == expected_word &&
                 sample.word1 == expected_word * 10 + expected_word / 11,
             "copied FIFO record survives physical wrap");
        const auto copies = counts.copies;
        sample.word0 = sample.word1 = sample.status_low = sample.result = ~std::uint64_t{0};
        registers.status ^= 4;
        const auto repeat = poll();
        need(repeat.word0 == expected_word && repeat.word1 == expected_word * 10 + expected_word / 11 &&
                 counts.copies == copies,
             "repeated poll revalidates then returns the same private copied sample");
        need(acknowledge() == static_cast<std::uint64_t>(AckResult::committed), "single acknowledgement commits");
        rejects([] {
            static_cast<void>(acknowledge());
        });
    }
    need(registers.head == 32 && last_written == 32 && counts.writes == 3, "each head advanced exactly sixteen once");
    const auto before = counts;
    const auto empty = poll();
    need(is_result(empty, PollResult::empty) && counts.writes == before.writes && counts.copies == before.copies,
         "empty polling emits canonical absence and never copies or acknowledges");
    const auto old = argument;
    need(Service::close(argument, 0) == Completion::drained, "normal closure");
    argument = Service::open();
    need(argument.grant == old.grant && argument.generation == old.generation + 1, "fresh generation exact address");
    rejects([&] {
        static_cast<void>(Service::poll(old.grant, old.generation));
    });
    need(is_result(poll(), PollResult::empty), "reopening does not reset ring progress");
}
auto grant_rejections() -> void {
    open();
    rejects([] {
        static_cast<void>(Service::poll(reinterpret_cast<const void *>(1), argument.generation));
    });
    rejects([] {
        static_cast<void>(Service::poll(argument.grant, 0));
    });
    rejects([] {
        static_cast<void>(Service::poll(argument.grant, argument.generation + 1));
    });
    rejects([] {
        static_cast<void>(Service::open());
    });
    rejects([] {
        static_cast<void>(acknowledge());
    });
    rejects([] {
        const RawSample forged{static_cast<std::uint64_t>(PollResult::record), 0x1234, 0x5678, 0x1a};
        need(is_result(forged, PollResult::record), "forged copied report is data, not authority");
        static_cast<void>(acknowledge());
    });
    rejects([] {
        quiescent = false;
        static_cast<void>(poll());
    });
    rejects([] {
        const std::uint64_t foreign_kind = 0x415552434f4e5301ULL;
        std::memcpy(const_cast<void *>(argument.grant), &foreign_kind, sizeof(foreign_kind));
        static_cast<void>(poll());
    });
    rejects([] {
        const auto wrong_generation = argument.generation + 1;
        std::memcpy(static_cast<std::byte *>(const_cast<void *>(argument.grant)) + 8, &wrong_generation, 8);
        static_cast<void>(poll());
    });
    rejects([] {
        static_cast<void>(Service::close(argument, 7));
    });
    rejects([] {
        static_cast<void>(Service::close(argument, std::uint64_t{1} << 32));
    });
    need(Service::close(argument, 6) == Completion::output_failure, "output failure can revoke a live grant");
    rejects([] {
        static_cast<void>(poll());
    });
    rejects([] {
        static_cast<void>(acknowledge());
    });
}
auto source_owns_record_policy() -> void {
    seed();
    registers.control = 0x1005;
    argument = Service::open();
    // Synthetic code 5 is opaque to the adapter. Only the Aurora consumer owns
    // the decision to print it and close without acknowledging it.
    record(0, std::uint64_t{5} << 60, 0x8000);
    registers.status &= ~std::uint64_t{16};
    const auto command_error = poll();
    need(command_error.word0 == (std::uint64_t{5} << 60) && command_error.word1 == 0x8000 && counts.writes == 0,
         "code five and stopped commands remain copied data");
    const auto before_close = counts;
    need(Service::close(argument, 4) == Completion::command_error && counts == before_close,
         "command error close leaves pending slot untouched");
    argument = Service::open();
    need(poll().word0 == command_error.word0 && counts.copies == 1 && counts.writes == 0,
         "closure does not discard the unacknowledged private record");
    // The capability does not enforce report-before-ack or classify code 5.
    // This positive host control proves those are audited source properties.
    need(acknowledge() == 0 && registers.head == 16, "adapter authority is independent of copied event classification");
}
auto pair_admission() -> void {
    open();
    console_argument = Console::open();
    IntakeArgument input{
        argument.grant, argument.generation, console_argument.grant, console_argument.generation, 256, 255};
    auto entry = [](const IntakeArgument *incoming) -> std::uint64_t {
        ++counts.entries;
        need(incoming->event_grant == argument.grant && incoming->console_grant == console_argument.grant,
             "entry sees both separately admitted exact grants");
        if (incoming->poll_budget == 0 || incoming->record_budget == 0)
            return 1;
        static_cast<void>(Console::put(incoming->console_grant, incoming->console_generation, 'x'));
        return 0;
    };
    rejects([&] {
        static_cast<void>(Intake::invoke(reinterpret_cast<const IntakeArgument *>(1), input, entry));
    });
    rejects([&] {
        const auto copied = input;
        static_cast<void>(Intake::invoke(&copied, input, entry));
    });
    for (const auto invalid_budget : {257ULL, 0x100000000ULL, ~0ULL}) {
        rejects([&] {
            input.poll_budget = invalid_budget;
            static_cast<void>(Intake::invoke(&input, input, entry));
        });
    }
    rejects([&] {
        input.record_budget = 256;
        static_cast<void>(Intake::invoke(&input, input, entry));
    });
    rejects([&] {
        input.event_grant = console_argument.grant;
        static_cast<void>(Intake::invoke(&input, input, entry));
    });
    rejects([&] {
        input.console_grant = argument.grant;
        static_cast<void>(Intake::invoke(&input, input, entry));
    });
    rejects([&] {
        ++input.event_generation;
        static_cast<void>(Intake::invoke(&input, input, entry));
    });
    rejects([&] {
        ++input.console_generation;
        static_cast<void>(Intake::invoke(&input, input, entry));
    });
    rejects([&] {
        static_cast<void>(Console::close(console_argument, 0));
        static_cast<void>(Intake::invoke(&input, input, entry));
    });
    for (const auto drift : {Fault::drift_identity,
                             Fault::drift_base,
                             Fault::drift_control,
                             Fault::invalid_tail,
                             Fault::producer_active,
                             Fault::overflow}) {
        rejects(
            [&] {
                fault = drift;
                inject();
                static_cast<void>(Intake::invoke(&input, input, entry));
            },
            1);
    }
    const auto reads = counts.reads;
    need(Intake::invoke(&input, input, entry) == Completion::drained && counts.console == 1 && counts.entries == 1 &&
             counts.reads == reads + 1 && counts.writes == 0,
         "atomic admission reads live transport only after both exact grants pass");
    rejects([&] {
        static_cast<void>(Intake::invoke(&input, input, entry));
    });
    rejects([] {
        static_cast<void>(poll());
    });
    rejects([] {
        static_cast<void>(Console::put(console_argument.grant, console_argument.generation, 'x'));
    });
    for (unsigned zero = 0; zero != 2; ++zero) {
        argument = Service::open();
        console_argument = Console::open();
        input.event_generation = argument.generation;
        input.console_generation = console_argument.generation;
        input.poll_budget = zero == 0 ? 0 : 256;
        input.record_budget = zero == 1 ? 0 : 255;
        const auto previous = counts;
        need(Intake::invoke(&input, input, entry) == Completion::budget_exhausted &&
                 counts.console == previous.console && counts.reads == previous.reads + 1 &&
                 counts.copies == previous.copies && counts.writes == previous.writes,
             "zero-budget source control has no poll, copy, acknowledgement or Console operation");
        rejects([&] {
            static_cast<void>(Intake::invoke(&input, input, entry));
        });
    }
    argument = Service::open();
    console_argument = Console::open();
    input.event_generation = argument.generation;
    input.console_generation = console_argument.generation;
    rejects(
        [&] {
            static_cast<void>(Intake::invoke(&input, input, [](const IntakeArgument *) {
                return std::uint64_t{7};
            }));
        },
        1);
    rejects(
        [&] {
            static_cast<void>(Intake::invoke(&input, input, [&](const IntakeArgument *) -> std::uint64_t {
                static_cast<void>(Intake::invoke(&input, input, entry));
                return 0;
            }));
        },
        1);
}
} // namespace

int main() {
    need(next_generation(0) == 1 &&
             next_generation(std::numeric_limits<std::uint64_t>::max() - 1) ==
                 std::numeric_limits<std::uint64_t>::max() &&
             next_generation(std::numeric_limits<std::uint64_t>::max()) == 0,
         "generation exhaustion never wraps to a live identity");
    isolated(copied_fifo_and_wrap);
    isolated(grant_rejections);
    isolated(source_owns_record_policy);
    isolated(pair_admission);
    isolated([] {
        open();
        const auto pending = poll();
        const auto previous = counts;
        need(Service::close(argument, 6) == Completion::output_failure && counts == previous && registers.head == 0,
             "output failure closes without acknowledging the current pending record");
        argument = Service::open();
        const auto repeat = poll();
        need(repeat.word0 == pending.word0 && repeat.word1 == pending.word1 && counts.copies == previous.copies &&
                 counts.writes == 0,
             "output failure does not erase or recopy the retained pending record");
    });
    for (const auto unsupported : {std::uint64_t{6} << 60, std::numeric_limits<std::uint64_t>::max()}) {
        isolated([&] {
            open();
            record(0, unsupported, 0x5555);
            need(poll().word0 == unsupported && counts.writes == 0,
                 "code six and unknown records are opaque copied data for source policy");
            need(Service::close(argument, 3) == Completion::unsupported_event && registers.head == 0 &&
                     counts.writes == 0,
                 "source unsupported-event decision leaves its record unacknowledged");
        });
    }
    isolated([] {
        rejects([] {
            static_cast<void>(Service::open());
        });
        need(!BootLifetimeRing::exposed(), "failed unexposed admission publishes nothing");
    });
    isolated([] {
        seed();
        reenter_open = true;
        rejects(
            [] {
                static_cast<void>(Service::open());
            },
            1);
    });
    // Admission rejects malformed full-width geometry rather than masking it.
    for (unsigned invalid = 0; invalid != 11; ++invalid) {
        isolated([&] {
            seed();
            switch (invalid) {
            case 0:
                registers.base |= 1;
                break;
            case 1:
                registers.base |= std::uint64_t{1} << 40;
                break;
            case 2:
                registers.base = std::uint64_t{8} << 56;
                break;
            case 3:
                registers.base ^= std::uint64_t{1} << 56;
                break;
            case 4:
                registers.control |= std::uint64_t{1} << 63;
                break;
            case 5:
                registers.control |= 8;
                break;
            case 6:
                registers.head = std::uint64_t{1} << 32;
                break;
            case 7:
                registers.tail = 17;
                break;
            case 8:
                registers.status |= std::uint64_t{1} << 32;
                break;
            case 9:
                registers.ring = nullptr;
                break;
            case 10:
                registers.status |= 16;
                break;
            }
            rejects(
                [] {
                    static_cast<void>(Service::open());
                },
                1);
            need(BootLifetimeRing::exposed(), "failed profile admission retains boot-lifetime backing");
        });
    }
    for (const auto command_status : {0xaULL, 0x1aULL}) {
        isolated([&] {
            seed(0, 0);
            registers.control = 0x1005;
            registers.status = command_status;
            argument = Service::open();
            need(is_result(poll(), PollResult::empty), "command enable permits either copied CmdBufRun state");
        });
    }
    isolated([] {
        open();
        reenter_copy = true;
        rejects(
            [] {
                static_cast<void>(poll());
            },
            1,
            1);
    });
    isolated([] {
        open();
        static_cast<void>(poll());
        reenter_write = true;
        rejects(
            [] {
                static_cast<void>(acknowledge());
            },
            1,
            0,
            1);
    });
    // Full register values and fixed-profile geometry must be checked before a
    // first record, before a repeated pending report, and after the copy.
    for (const auto invalid : {Fault::unknown_status,
                               Fault::invalid_head,
                               Fault::drift_head,
                               Fault::invalid_tail,
                               Fault::drift_tail,
                               Fault::drift_identity,
                               Fault::drift_base,
                               Fault::drift_control,
                               Fault::stopped_log,
                               Fault::read_failure,
                               Fault::producer_active}) {
        for (unsigned phase = 0; phase != 3; ++phase) {
            isolated([&] {
                open();
                if (phase == 1)
                    static_cast<void>(poll());
                const auto copies = counts.copies;
                fault = invalid;
                fault_on_read = counts.reads + (phase == 2 ? 2 : 1);
                const auto result = poll();
                need(is_result(result, PollResult::transport_failure), "malformed full snapshot fails closed");
                if (invalid == Fault::unknown_status)
                    need(result.status_low == 0, "unknown high status bits are not masked into trusted evidence");
                need(counts.copies == copies + (phase == 2 ? 1 : 0) && counts.writes == 0,
                     "snapshot failure performs no head write or extra copy");
                terminal(Completion::transport_failure);
            });
        }
    }
    for (unsigned phase = 0; phase != 3; ++phase) {
        isolated([&] {
            open();
            if (phase == 1)
                static_cast<void>(poll());
            fault = Fault::overflow;
            fault_on_read = counts.reads + (phase == 2 ? 2 : 1);
            need(is_result(poll(), PollResult::overflow) && counts.writes == 0,
                 "overflow before or after copy dominates a pending report");
            terminal(Completion::loss_detected);
        });
    }
    isolated([] {
        open();
        registers.status = 1;
        need(is_result(poll(), PollResult::overflow), "observed overflow dominates a stopped event log");
        terminal(Completion::loss_detected);
    });
    isolated([] {
        open();
        registers.status = (std::uint64_t{1} << 32) | 1;
        const auto result = poll();
        need(is_result(result, PollResult::transport_failure) && result.status_low == 0,
             "unknown full-width status is rejected before interpreting its overflow bit");
        terminal(Completion::transport_failure);
    });
    isolated([] {
        open();
        copy_okay = false;
        need(is_result(poll(), PollResult::transport_failure) && counts.copies == 1 && counts.writes == 0,
             "uncertain record copy is never exposed");
        terminal(Completion::transport_failure);
    });
    for (const auto injected : {Fault::overflow,
                                Fault::unknown_status,
                                Fault::drift_identity,
                                Fault::invalid_tail,
                                Fault::drift_control,
                                Fault::read_failure}) {
        for (unsigned after_write = 0; after_write != 2; ++after_write) {
            isolated([&] {
                open();
                static_cast<void>(poll());
                fault = injected;
                fault_on_read = counts.reads + 1 + after_write;
                const auto result = acknowledge();
                need(result == static_cast<std::uint64_t>(injected == Fault::overflow ? AckResult::overflow
                                                                                      : AckResult::transport_failure),
                     "ack distinguishes overflow from transport uncertainty");
                need(counts.writes == after_write && registers.head == 16 * after_write,
                     "pre-write failure has zero attempts; post-write failure may already advance head");
                terminal(injected == Fault::overflow ? Completion::loss_detected : Completion::transport_failure);
            });
        }
    }
    for (unsigned advanced = 0; advanced != 2; ++advanced) {
        isolated([&] {
            open();
            static_cast<void>(poll());
            write_okay = false;
            change_head = advanced != 0;
            need(acknowledge() == static_cast<std::uint64_t>(AckResult::transport_failure) && counts.writes == 1 &&
                     registers.head == 16 * advanced,
                 "uncertain write remains terminal whether or not the head changed");
            terminal(Completion::transport_failure);
        });
    }
    isolated([] {
        open();
        static_cast<void>(poll());
        change_head = false;
        need(acknowledge() == static_cast<std::uint64_t>(AckResult::transport_failure) && counts.writes == 1,
             "successful write claim still requires matching readback");
        terminal(Completion::transport_failure);
    });
    isolated([] {
        open();
        static_cast<void>(poll());
        write_okay = change_head = false;
        fault = Fault::overflow;
        fault_on_read = counts.reads + 2;
        need(acknowledge() == static_cast<std::uint64_t>(AckResult::overflow) && counts.writes == 1,
             "post-attempt observed overflow is terminal even when write outcome is uncertain");
        terminal(Completion::loss_detected);
    });
    std::puts("PASS IOMMU event session: copied FIFO, sealed grants, atomic admission, bounded one-shot ack and "
              "retained backing");
}
