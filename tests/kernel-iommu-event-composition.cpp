// Real generated Aurora consumer + sealed bootstrap sessions, with explicitly
// synthetic ring/register/UART transport. This is not a guest or MMIO test.
#include "../kernel/console-session.hpp"
#include "../kernel/iommu-event-session.hpp"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <string>
#include <sys/wait.h>
#include <unistd.h>
#include <vector>

namespace {
using namespace aurora::iommu_event;
using Word = std::uint64_t;
class Counts final {
public:
    unsigned reads{}, copies{}, writes{}, polls{}, acknowledgements{}, output_attempts{};
    auto operator==(const Counts &) const -> bool = default;
};
Counts counts{}, expected_failure{};
Snapshot registers{};
ServiceArgument event_argument{};
aurora::console::ServiceArgument console_argument{};
std::byte *ring{};
std::string mode, output;
std::vector<RawSample> records;
std::size_t fail_at = std::numeric_limits<std::size_t>::max();
bool fail_expected{};

auto need(bool valid, const char *message) -> void {
    if (!valid) {
        std::fprintf(stderr,
                     "FAIL composition %s: %s (poll=%u ack=%u head-write=%u output=%zu/%u)\n",
                     mode.c_str(),
                     message,
                     counts.polls,
                     counts.acknowledgements,
                     counts.writes,
                     output.size(),
                     counts.output_attempts);
        std::abort();
    }
}
auto report(const RawSample &sample) -> std::string {
    // Independent expected bytes from the copied raw fields, not Aurora output.
    const auto fault = (sample.word0 >> 60) == 2 && (sample.word0 & ~Word{0x20f0ffff0000ffffULL}) == 0;
    const auto command = sample.word0 == 0x5000000000000000ULL && (sample.word1 & 15) == 0;
    const char tag = fault ? 'F' : command ? 'C' : 'U';
    char bytes[193];
    const auto size =
        fault ? std::snprintf(bytes,
                              sizeof(bytes),
                              "IOMMU %c raw=%016llx/%016llx rid=%04llx dom=%04llx dva=%016llx status=%02llx\r\n",
                              tag,
                              static_cast<unsigned long long>(sample.word0),
                              static_cast<unsigned long long>(sample.word1),
                              static_cast<unsigned long long>(sample.word0 & 0xffff),
                              static_cast<unsigned long long>((sample.word0 >> 32) & 0xffff),
                              static_cast<unsigned long long>(sample.word1),
                              static_cast<unsigned long long>(sample.status_low))
              : std::snprintf(bytes,
                              sizeof(bytes),
                              "IOMMU %c raw=%016llx/%016llx status=%02llx\r\n",
                              tag,
                              static_cast<unsigned long long>(sample.word0),
                              static_cast<unsigned long long>(sample.word1),
                              static_cast<unsigned long long>(sample.status_low));
    need(size > 0 && size <= 192, "independent report has the fixed output bound");
    return std::string(bytes, static_cast<std::size_t>(size));
}
class Transport final {
public:
    [[nodiscard]] static auto snapshot() -> Snapshot {
        ++counts.reads;
        return registers;
    }
    [[nodiscard]] static auto copy_record(Word head) -> RecordCopy {
        ++counts.copies;
        need(head == registers.head && head < ring_bytes && head % record_bytes == 0, "validated ring copy offset");
        RecordCopy copy{};
        std::memcpy(&copy.word0, ring + head, 8);
        std::memcpy(&copy.word1, ring + head + 8, 8);
        copy.okay = true;
        return copy;
    }
    [[nodiscard]] static auto publish_head(Word head) -> bool {
        ++counts.writes;
        need(head == (registers.head + record_bytes) % ring_bytes, "publication advances exactly one record");
        std::string complete_reports;
        for (unsigned i = 0; i < counts.writes; ++i) {
            need(i < records.size(), "no duplicate head publication");
            complete_reports += report(records[i]);
        }
        need(output == complete_reports && counts.output_attempts == output.size(),
             "actual head write follows the complete bounded source report");
        registers.head = head;
        if (mode == "ack-overflow")
            registers.status |= 1;
        // The uncertain case deliberately advances the head before failure.
        return mode != "ack-transport";
    }
};
class Platform final {
public:
    [[nodiscard]] static auto quiet() -> bool {
        return true;
    }
    [[noreturn]] static auto fail() -> void {
        if (fail_expected && counts == expected_failure)
            std::_Exit(77);
        std::fprintf(stderr, "unexpected composition grant failure (%s)\n", mode.c_str());
        std::_Exit(78);
    }
};
class ConsoleTransport final {
public:
    [[nodiscard]] static auto try_put(std::uint8_t byte) -> aurora::console::PutResult {
        need(counts.copies > counts.writes, "source reports only its current copied pending record");
        if (counts.output_attempts++ == fail_at)
            return aurora::console::PutResult::timeout;
        output += static_cast<char>(byte);
        return aurora::console::PutResult::success;
    }
};
using Service = Session<Transport, Platform>;
using Console = aurora::console::Session<ConsoleTransport, Platform>;
using Intake = Entry<Service, Console, Platform>;

template <class Test> auto rejects(Test test) -> void {
    const auto child = fork();
    need(child >= 0, "fork revoked-grant control");
    if (child == 0) {
        fail_expected = true;
        expected_failure = counts;
        test();
        std::_Exit(1);
    }
    int status{};
    need(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 77,
         "revoked operation fails before transport or output effects");
}
auto aligned() -> void {
    need(reinterpret_cast<std::uintptr_t>(__builtin_frame_address(0)) % 16 == 0, "host ABI stack alignment");
}
auto fault(Word requester = 0x18, Word address = 0x12345000) -> RawSample {
    return {1, 0x20b0000700000000ULL | requester, address, 0xa};
}
} // namespace

extern "C" Word checked_iommu_event_entry(const IntakeArgument *);
extern "C" auto __au_runtime_iommu_event_poll(const void *grant, Word generation, RawSample *sample) -> void {
    aligned();
    need(sample && sample->result == 0 && sample->word0 == 0 && sample->word1 == 0 && sample->status_low == 0,
         "generated code initializes all four report qwords");
    ++counts.polls;
    if (mode == "poll-overflow")
        registers.status |= 1;
    *sample = Service::poll(grant, generation);
}
extern "C" auto __au_runtime_iommu_event_acknowledge(const void *grant, Word generation) -> Word {
    aligned();
    ++counts.acknowledgements;
    return Service::acknowledge(grant, generation);
}
extern "C" auto __au_runtime_console_put(const void *grant, Word generation, Word byte) -> Word {
    aligned();
    return Console::put(grant, generation, byte);
}

namespace {
auto run() -> void {
    records = {fault()};
    Word expected_result = 0, poll_budget = 256, record_budget = 255;
    unsigned expected_polls = 2, expected_writes = 1;
    const Word start_head = mode == "wrap" ? 4080 : 0;
    if (mode == "wrap") {
        records.push_back(fault(0x19, 0x12345004));
        records.push_back(fault(0x20, 0x12345008));
        expected_polls = 4;
        expected_writes = 3;
    } else if (mode == "empty") {
        records.clear();
        expected_polls = 1;
        expected_writes = 0;
    } else if (mode == "code5" || mode == "code6" || mode == "unsupported" || mode == "malformed-code2") {
        const Word word0 = mode == "code5"         ? 0x5000000000000000ULL
                           : mode == "code6"       ? 0x6000000000000000ULL
                           : mode == "unsupported" ? 0xf000000000000000ULL
                                                   : 0x2000000000010000ULL;
        records = {{1, word0, 0x12345670, 0xa}};
        expected_result = mode == "code5" ? 4 : 3;
        expected_polls = 1;
        expected_writes = 0;
    } else if (mode == "output") {
        expected_result = 6;
        expected_polls = 1;
        expected_writes = 0;
    } else if (mode == "poll-overflow") {
        expected_result = 2;
        expected_polls = 1;
        expected_writes = 0;
    } else if (mode == "ack-overflow" || mode == "ack-transport") {
        expected_result = mode == "ack-overflow" ? 2 : 5;
        expected_polls = 1;
    } else if (mode == "zero-poll" || mode == "zero-record") {
        if (mode == "zero-poll")
            poll_budget = 0;
        else
            record_budget = 0;
        expected_result = 1;
        expected_polls = expected_writes = 0;
    } else if (mode == "poll-budget" || mode == "record-budget") {
        if (mode == "poll-budget")
            poll_budget = 1;
        else
            record_budget = 1;
        expected_result = 1;
        expected_polls = 1;
    } else if (mode == "maximum-budget") {
        records.assign(255, fault());
        expected_result = 1;
        expected_polls = expected_writes = 255;
    } else {
        need(mode == "fault", "known composition mode");
    }

    need(!BootLifetimeRing::exposed(), "fresh boot-lifetime backing in each process");
    ring = BootLifetimeRing::expose();
    const auto tail = (start_head + records.size() * record_bytes) % ring_bytes;
    registers = {
        ring, (Word{8} << 56) | 0x100000, mode == "code5" ? Word{0x1005} : Word{5}, start_head, tail, 0xa, true, true};
    for (std::size_t i = 0; i < records.size(); ++i) {
        const auto at = (start_head + i * record_bytes) % ring_bytes;
        std::memcpy(ring + at, &records[i].word0, 8);
        std::memcpy(ring + at + 8, &records[i].word1, 8);
    }
    std::array<std::byte, ring_bytes> retained{};
    std::memcpy(retained.data(), ring, ring_bytes);
    event_argument = Service::open();
    // Deliberately make generation values unequal across distinct capabilities.
    const auto console_first = Console::open();
    static_cast<void>(Console::close(console_first, 0));
    console_argument = Console::open();
    need(event_argument.grant != console_argument.grant && event_argument.generation != console_argument.generation,
         "entry carries unequal, independently sealed grants and generations");
    const IntakeArgument input{event_argument.grant,
                               event_argument.generation,
                               console_argument.grant,
                               console_argument.generation,
                               poll_budget,
                               record_budget};
    const auto result = Intake::invoke(&input, input, [](const IntakeArgument *arguments) {
        return checked_iommu_event_entry(arguments);
    });
    need(static_cast<Word>(result) == expected_result && counts.polls == expected_polls &&
             counts.writes == expected_writes && counts.acknowledgements == expected_writes,
         "real consumer reaches the expected bounded outcome through real sessions");
    need(registers.head == (start_head + expected_writes * record_bytes) % ring_bytes,
         "independent raw head agrees with exactly the attempted publications");
    need(BootLifetimeRing::exposed() && ring == BootLifetimeRing::identity() &&
             std::memcmp(retained.data(), ring, ring_bytes) == 0,
         "entry closure retains all backing bytes and identity");

    std::string expected_output;
    if (mode == "output") {
        expected_output = report(records.front()).substr(0, fail_at);
        need(counts.output_attempts == fail_at + 1 && counts.copies == 1,
             "failed output prefix is not retried and its record is not acknowledged");
    } else if (expected_writes != 0 || expected_result == 3 || expected_result == 4) {
        const auto reports = expected_writes != 0 ? expected_writes : 1;
        for (unsigned i = 0; i < reports; ++i)
            expected_output += report(records[i]);
    }
    need(output == expected_output && (mode == "output" || counts.output_attempts == output.size()),
         "full source telemetry agrees byte-for-byte with independent raw records");
    if (expected_polls == 0)
        need(counts.copies == 0 && counts.output_attempts == 0 && counts.acknowledgements == 0,
             "zero budget reaches generated return with zero service operations");

    rejects([] {
        static_cast<void>(Service::poll(event_argument.grant, event_argument.generation));
    });
    rejects([] {
        static_cast<void>(Service::acknowledge(event_argument.grant, event_argument.generation));
    });
    rejects([] {
        static_cast<void>(Console::put(console_argument.grant, console_argument.generation, 'x'));
    });
    rejects([&] {
        static_cast<void>(Intake::invoke(&input, input, [](const IntakeArgument *arguments) {
            return checked_iommu_event_entry(arguments);
        }));
    });
    if (mode == "poll-overflow" || mode == "ack-overflow" || mode == "ack-transport") {
        rejects([] {
            static_cast<void>(Service::open());
        });
    } else if (expected_result == 3 || expected_result == 4 || expected_result == 6) {
        const auto copies = counts.copies;
        event_argument = Service::open();
        const auto pending = Service::poll(event_argument.grant, event_argument.generation);
        need(pending.word0 == records.front().word0 && pending.word1 == records.front().word1 &&
                 counts.copies == copies && registers.head == start_head && counts.writes == 0,
             "real source error leaves its exact copied pending record retained");
        static_cast<void>(Service::close(event_argument, expected_result));
    }
}
} // namespace

int main(int argc, char **argv) {
    need(argc == 2, "one composition mode required");
    mode = argv[1];
    if (mode == "output") {
        const auto size = report(fault()).size();
        for (fail_at = 0; fail_at < size; ++fail_at) {
            const auto child = fork();
            need(child >= 0, "fork fresh output-failure adapter");
            if (child == 0) {
                run();
                std::_Exit(0);
            }
            int status{};
            need(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0,
                 "real composition passed each output-failure prefix");
        }
        std::printf("PASS IOMMU event composition output: all %zu failure prefixes retain pending record\n", size);
    } else {
        run();
        std::printf("PASS IOMMU event composition %s\n", mode.c_str());
    }
}
