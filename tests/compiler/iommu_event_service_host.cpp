// Synthetic compiler/consumer ABI seam. No device, MMIO or native grant admission.
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <string>
#include <vector>
namespace {
using Word = std::uint64_t;
Word eventGrant = 0xE713, consoleGrant = 0xC059;
struct Arguments {
    const void *event;
    Word eventGeneration;
    const void *console;
    Word consoleGeneration;
    Word pollBudget, recordBudget;
};
struct Sample {
    Word result, word0, word1, status;
};
static_assert(sizeof(Arguments) == 48 && offsetof(Arguments, eventGeneration) == 8 &&
              offsetof(Arguments, console) == 16 && offsetof(Arguments, consoleGeneration) == 24 &&
              offsetof(Arguments, pollBudget) == 32 && offsetof(Arguments, recordBudget) == 40);
static_assert(sizeof(Sample) == 32 && offsetof(Sample, result) == 0 && offsetof(Sample, word0) == 8 &&
              offsetof(Sample, word1) == 16 && offsetof(Sample, status) == 24);
constexpr Word eventGeneration = 0x1020304050607067ULL, consoleGeneration = 0x887766554433222fULL;
constexpr Word abiWord0 = 0x0123456789abcdefULL, abiWord1 = 0xfedcba9876543210ULL;
std::string mode, output, trace;
std::vector<Sample> records;
std::size_t cursor{}, polls{}, acknowledgements{}, outputAttempts{};
std::size_t failAt = std::numeric_limits<std::size_t>::max();
bool pending{};
void need(bool value, const char *message = "IOMMU service host assertion") {
    if (!value) {
        std::fprintf(stderr,
                     "%s (%s): polls=%zu acknowledgements=%zu output=%zu attempts=%zu\n",
                     message,
                     mode.c_str(),
                     polls,
                     acknowledgements,
                     output.size(),
                     outputAttempts);
        std::abort();
    }
}
void aligned() {
    need(reinterpret_cast<std::uintptr_t>(__builtin_frame_address(0)) % 16 == 0, "host stack alignment");
}
Sample fault(Word requester = 0x18, Word address = 0x12345000) {
    return {1, 0x20b0000700000000ULL | requester, address, 0x1c};
}
std::string report(const Sample &sample) {
    const Word code = sample.word0 >> 60;
    char tag = 'U';
    if (code == 2 && (sample.word0 & ~Word{0x20f0ffff0000ffffULL}) == 0)
        tag = 'F';
    if (sample.word0 == 0x5000000000000000ULL && (sample.word1 & 15) == 0)
        tag = 'C';
    char buffer[193];
    const int size =
        tag == 'F' ? std::snprintf(buffer,
                                   sizeof(buffer),
                                   "IOMMU %c raw=%016llx/%016llx rid=%04llx dom=%04llx dva=%016llx status=%02llx\r\n",
                                   tag,
                                   static_cast<unsigned long long>(sample.word0),
                                   static_cast<unsigned long long>(sample.word1),
                                   static_cast<unsigned long long>(sample.word0 & 65535),
                                   static_cast<unsigned long long>((sample.word0 >> 32) & 65535),
                                   static_cast<unsigned long long>(sample.word1),
                                   static_cast<unsigned long long>(sample.status))
                   : std::snprintf(buffer,
                                   sizeof(buffer),
                                   "IOMMU %c raw=%016llx/%016llx status=%02llx\r\n",
                                   tag,
                                   static_cast<unsigned long long>(sample.word0),
                                   static_cast<unsigned long long>(sample.word1),
                                   static_cast<unsigned long long>(sample.status));
    need(size > 0 && size <= 192, "fixed report output bound");
    return std::string(buffer, static_cast<std::size_t>(size));
}
void reset() {
    output.clear();
    trace.clear();
    cursor = polls = acknowledgements = outputAttempts = 0;
    pending = false;
}
} // namespace
extern "C" Word checked_iommu_event_entry(const Arguments *);
extern "C" void __au_runtime_iommu_event_poll(const void *grant, Word generation, Sample *sample) {
    aligned();
    need(grant == &eventGrant && generation == eventGeneration, "wrong Event grant/generation");
    need(sample && sample->result == 0 && sample->word0 == 0 && sample->word1 == 0 && sample->status == 0,
         "raw report was not fully initialized before host call");
    ++polls;
    trace += 'P';
    if (mode == "abi" || mode == "ir") {
        *sample = {1, abiWord0, abiWord1, 31};
        return;
    }
    if (mode == "partial")
        return; // Compiler initialization supplies an exact empty report.
    if (mode == "poll-overflow") {
        *sample = {2, 0, 0, 1};
        return;
    }
    if (mode == "poll-transport") {
        *sample = {3, 0, 0, 0};
        return;
    }
    if (mode == "poll-enum-4") {
        sample->result = 4;
        return;
    }
    if (mode == "poll-enum-wide") {
        sample->result = Word{1} << 32;
        return;
    }
    if (mode == "status-32") {
        sample->status = 32;
        return;
    }
    if (mode == "status-wide") {
        sample->status = Word{1} << 32;
        return;
    }
    if (mode == "status-all-ones") {
        sample->status = ~Word{0};
        return;
    }
    for (Word result : {Word{0}, Word{2}, Word{3}}) {
        const auto prefix = "payload-" + std::to_string(result) + "-";
        if (mode == prefix + "word0") {
            *sample = {result, Word{1} << 63, 0, 0};
            return;
        }
        if (mode == prefix + "word1") {
            *sample = {result, 0, Word{1} << 63, 0};
            return;
        }
    }
    if (cursor == records.size()) {
        *sample = {0, 0, 0, 0x1c};
        return;
    }
    need(!pending, "consumer polled again without resolving pending record");
    *sample = records[cursor];
    pending = true;
}
extern "C" Word __au_runtime_iommu_event_acknowledge(const void *grant, Word generation) {
    aligned();
    need(grant == &eventGrant && generation == eventGeneration, "wrong acknowledgement grant/generation");
    ++acknowledgements;
    trace += 'A';
    if (mode == "abi")
        return 0;
    need(pending && cursor < records.size(), "acknowledgement without pending copied record");
    std::string expected;
    for (std::size_t index = 0; index <= cursor; ++index)
        expected += report(records[index]);
    need(output == expected && outputAttempts == output.size(), "acknowledgement preceded complete report");
    if (mode == "ack-enum-3")
        return 3;
    if (mode == "ack-enum-wide")
        return Word{1} << 32;
    if (mode == "ack-overflow")
        return 1;
    if (mode == "ack-transport")
        return 2;
    ++cursor;
    pending = false;
    return 0;
}
extern "C" Word __au_runtime_console_put(const void *grant, Word generation, Word byte) {
    aligned();
    need(grant == &consoleGrant && generation == consoleGeneration && byte <= 255,
         "wrong Console grant/generation or byte");
    trace += 'W';
    if (mode == "abi" || mode == "ir") {
        need(byte == (mode == "abi" ? 'Q' : 'A'), "unexpected ABI fixture byte");
        output += static_cast<char>(byte);
        ++outputAttempts;
        return 0;
    }
    need(pending, "output without a copied event");
    if (outputAttempts++ == failAt)
        return 1;
    output += static_cast<char>(byte);
    return 0;
}
int main(int argc, char **argv) {
    need(argc == 2, "expected exactly one fixture case name");
    mode = argv[1];
    Arguments arguments{&eventGrant, eventGeneration, &consoleGrant, consoleGeneration, 256, 255};
    Word expected = 0;
    std::size_t expectedPolls = 2, expectedAcks = 1;
    records = {fault()};
    if (mode == "abi" || mode == "ir") {
        arguments.pollBudget = 19;
        arguments.recordBudget = 23;
        const auto result = checked_iommu_event_entry(&arguments);
        if (mode == "abi")
            need(result == 42 && polls == 3 && acknowledgements == 2 && output == "QQ" && trace == "WPWPPAA",
                 "source reordered/helper report ABI");
        else
            need(result == abiWord1 && polls == 1 && acknowledgements == 0 && output == "A" && trace == "WP",
                 "independent IR reordered/helper report ABI");
        std::puts("PASS IOMMU event copied report/helper ABI");
        return 0;
    }
    if (mode == "finite") {
        records.push_back(fault(0x19, 0xfffffff0));
        expectedPolls = 3;
        expectedAcks = 2;
    } else if (mode == "empty" || mode == "partial") {
        records.clear();
        expectedPolls = 1;
        expectedAcks = 0;
    } else if (mode == "zero-poll" || mode == "zero-record") {
        if (mode == "zero-poll")
            arguments.pollBudget = 0;
        else
            arguments.recordBudget = 0;
        expected = 1;
        expectedPolls = expectedAcks = 0;
    } else if (mode == "invalid-poll-budget" || mode == "invalid-record-budget") {
        if (mode == "invalid-poll-budget")
            arguments.pollBudget = Word{1} << 32;
        else
            arguments.recordBudget = Word{1} << 32;
        expected = 5;
        expectedPolls = expectedAcks = 0;
    } else if (mode == "poll-budget" || mode == "record-budget") {
        if (mode == "poll-budget")
            arguments.pollBudget = 1;
        else
            arguments.recordBudget = 1;
        expected = 1;
        expectedPolls = 1;
    } else if (mode == "maximum-budget") {
        records.assign(255, fault());
        expected = 1;
        expectedPolls = expectedAcks = 255;
    } else if (mode == "code5" || mode == "code6" || mode == "unsupported" || mode == "malformed-code2") {
        records = {{1,
                    mode == "code5"             ? 0x5000000000000000ULL
                    : mode == "code6"           ? 0x6000000000000000ULL
                    : mode == "malformed-code2" ? 0x2000000000010000ULL
                                                : 0xf000000000000000ULL,
                    0x12345670,
                    0x1c}};
        expected = mode == "code5" ? 4 : 3;
        expectedPolls = 1;
        expectedAcks = 0;
    } else if (mode == "poll-overflow" || mode == "poll-transport") {
        expected = mode == "poll-overflow" ? 2 : 5;
        expectedPolls = 1;
        expectedAcks = 0;
    } else if (mode == "ack-overflow" || mode == "ack-transport") {
        expected = mode == "ack-overflow" ? 2 : 5;
        expectedPolls = 1;
    } else if (mode == "output") {
        const auto full = report(records[0]);
        for (failAt = 0; failAt < full.size(); ++failAt) {
            reset();
            need(checked_iommu_event_entry(&arguments) == 6 && polls == 1 && acknowledgements == 0 && pending &&
                     output == full.substr(0, failAt) && outputAttempts == failAt + 1,
                 "output prefix failure acknowledged or retried");
        }
        std::printf("PASS IOMMU event output failure at all %zu prefixes\n", full.size());
        return 0;
    } else if (mode.starts_with("poll-enum-") || mode.starts_with("status-") || mode.starts_with("payload-") ||
               mode.starts_with("ack-enum-")) {
        (void)checked_iommu_event_entry(&arguments);
        need(false, "malformed full-width host channel escaped compiler trap");
    } else if (mode != "fault") {
        need(false, "unknown fixture case");
    }
    const auto result = checked_iommu_event_entry(&arguments);
    need(result == expected && polls == expectedPolls && acknowledgements == expectedAcks, "consumer terminal outcome");
    std::string expectedOutput;
    const bool reported =
        expectedAcks != 0 || mode == "code5" || mode == "code6" || mode == "unsupported" || mode == "malformed-code2";
    if (reported) {
        const std::size_t count = expectedAcks == 0 ? 1 : expectedAcks;
        for (std::size_t index = 0; index < count; ++index)
            expectedOutput += report(records[index]);
    }
    need(output == expectedOutput && outputAttempts == output.size(), "copied event telemetry bytes");
    if (mode == "ack-overflow" || mode == "ack-transport" || mode == "code5" || mode == "code6" ||
        mode == "unsupported" || mode == "malformed-code2")
        need(pending && cursor == 0, "terminal failure lost pending slot or retried");
    std::printf("PASS IOMMU event consumer %s\n", mode.c_str());
}
