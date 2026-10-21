// Transcript-only host adapters for actual generated scratchpad source. No
// native file algorithm or semantic backing store exists in this fixture.
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace {
struct Record {
    std::uint8_t bytes[64];
    std::uint64_t count, kind;
};
struct Submission {
    Record command;
    std::uint64_t action, after_cr;
};
struct ClientArgument {
    std::uint64_t grant, generation;
    Record command;
    Record result;
};
struct InputArgument {
    std::uint64_t grant, generation, after_cr;
    Submission result;
};
struct OutputArgument {
    std::uint64_t grant, generation;
    Record response;
};
struct CallResult {
    std::uint64_t status, value;
};
struct Sample {
    std::uint64_t present, byte, damaged;
};
static_assert(sizeof(Record) == 80 && sizeof(Submission) == 96);
static_assert(offsetof(Record, count) == 64 && offsetof(Record, kind) == 72);
static_assert(offsetof(Submission, action) == 80 && offsetof(Submission, after_cr) == 88);
static_assert(offsetof(ClientArgument, result) == 96 && offsetof(InputArgument, result) == 24);
std::uint64_t calls{}, nexts{}, put_count{}, limit = UINT64_MAX;
void need(bool value) {
    if (!value)
        std::abort();
}
[[maybe_unused]] void record(const Record &value) {
    std::fprintf(stderr, "record=%lu,%lu,", value.count, value.kind);
    for (auto byte : value.bytes)
        std::fprintf(stderr, "%02x", byte);
    std::fputc('\n', stderr);
}
} // namespace
extern "C" std::uint64_t checked_group_entry(const void *);
extern "C" CallResult __au_runtime_call(std::uint64_t grant, std::uint64_t generation, std::uint64_t request) {
    need(reinterpret_cast<std::uintptr_t>(__builtin_frame_address(0)) % 16 == 0);
    need(grant == 0xC011 && generation == 91);
    std::uint64_t expected{}, status{}, value{};
    need(std::scanf("%lu %lu %lu", &expected, &status, &value) == 3);
    need(request == expected);
    ++calls;
    return {status, value};
}
extern "C" void __au_runtime_console_next(std::uint64_t grant, std::uint64_t generation, Sample *sample) {
    need(reinterpret_cast<std::uintptr_t>(__builtin_frame_address(0)) % 16 == 0);
    need(grant == 0xC051 && generation == 41);
    need(put_count <= limit);
    need(std::scanf("%lu %lu %lu", &sample->present, &sample->byte, &sample->damaged) == 3);
    ++nexts;
}
extern "C" std::uint64_t __au_runtime_console_put(std::uint64_t grant, std::uint64_t generation, std::uint64_t byte) {
    need(reinterpret_cast<std::uintptr_t>(__builtin_frame_address(0)) % 16 == 0);
    need(grant == 0xC051 && generation == 41 && byte <= 255 && put_count <= limit);
    if (put_count++ == limit)
        return 1;
    need(std::putchar(static_cast<int>(byte)) != EOF);
    return 0;
}
int main(int argc, char **argv) {
    need(argc >= 2);
    const auto mode = std::strtoull(argv[1], nullptr, 10);
#if defined(AURORA_SCRATCHPAD_CLIENT_TEST)
    ClientArgument argument{0xC011, 91, {}, {}};
    argument.command.kind = mode;
    if (argc >= 3) {
        argument.command.count = std::strlen(argv[2]);
        need(argument.command.count <= 64);
        std::memcpy(argument.command.bytes, argv[2], argument.command.count);
    }
    if (argc >= 4) {
        const auto mutation = std::strtoull(argv[3], nullptr, 10);
        if (mutation == 1)
            argument.command.bytes[63] = 'x';
        if (mutation == 2)
            argument.command.bytes[0] = 0;
        if (mutation == 3)
            argument.command.count = UINT64_MAX;
    }
    need(checked_group_entry(&argument) == 42);
    record(argument.result);
    std::fprintf(stderr, "calls=%lu\n", calls);
    char remaining{};
    need(std::scanf(" %c", &remaining) == EOF);
#elif defined(AURORA_SCRATCHPAD_INPUT_TEST)
    InputArgument argument{0xC051, 41, mode, {}};
    if (argc >= 3)
        limit = std::strtoull(argv[2], nullptr, 10);
    need(checked_group_entry(&argument) == 42);
    record(argument.result.command);
    std::fprintf(stderr,
                 "action=%lu carry=%lu nexts=%lu puts=%lu\n",
                 argument.result.action,
                 argument.result.after_cr,
                 nexts,
                 put_count);
#else
    OutputArgument argument{0xC051, 41, {}};
    argument.response.kind = mode;
    if (argc >= 3) {
        argument.response.count = std::strlen(argv[2]);
        need(argument.response.count <= 64);
        std::memcpy(argument.response.bytes, argv[2], argument.response.count);
    }
    if (argc >= 4)
        limit = std::strtoull(argv[3], nullptr, 10);
    if (argc >= 5) {
        const auto mutation = std::strtoull(argv[4], nullptr, 10);
        if (mutation == 1)
            argument.response.bytes[63] = 'x';
        if (mutation == 2)
            argument.response.bytes[0] = 0;
        if (mutation == 3)
            argument.response.count = UINT64_MAX;
    }
    const auto result = checked_group_entry(&argument);
    need(result <= 1);
    std::fprintf(stderr, "success=%lu puts=%lu nexts=%lu\n", result, put_count, nexts);
#endif
    return 0;
}
