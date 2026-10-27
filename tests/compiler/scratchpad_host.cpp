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
struct NamespaceBytes {
    std::uint8_t bytes[64];
    std::uint64_t count;
};
struct NamespaceCommand {
    NamespaceBytes name, value;
    std::uint64_t operation;
};
struct NamespaceResult {
    Record content;
    std::uint64_t revision;
};
struct NamespaceSubmission {
    NamespaceCommand command;
    std::uint64_t action, after_cr;
};
struct NamespaceResponse {
    NamespaceBytes name;
    std::uint64_t submitted;
    NamespaceResult result;
    std::uint64_t kind;
};
struct NamespaceClientArgument {
    std::uint64_t grant, generation;
    NamespaceCommand command;
    std::uint64_t probe;
    NamespaceResult result;
};
struct NamespaceInputArgument {
    std::uint64_t grant, generation, after_cr;
    NamespaceSubmission result;
};
struct NamespaceOutputArgument {
    std::uint64_t grant, generation;
    NamespaceResponse response;
};
struct CallResult {
    std::uint64_t status, value;
};
struct Sample {
    std::uint64_t present, byte, damaged;
};
static_assert(sizeof(Record) == 80 && sizeof(Submission) == 96);
static_assert(sizeof(NamespaceCommand) == 152 && sizeof(NamespaceResult) == 88 && sizeof(NamespaceSubmission) == 168 &&
              sizeof(NamespaceResponse) == 176 && offsetof(NamespaceClientArgument, result) == 176 &&
              offsetof(NamespaceInputArgument, result) == 24);
static_assert(offsetof(Record, count) == 64 && offsetof(Record, kind) == 72);
static_assert(offsetof(Submission, action) == 80 && offsetof(Submission, after_cr) == 88);
static_assert(offsetof(ClientArgument, result) == 96 && offsetof(InputArgument, result) == 24);
std::uint64_t calls{}, nexts{}, put_count{}, limit = UINT64_MAX;
void need(bool value) {
    if (!value)
        std::abort();
}
void record(const Record &value) {
    std::fprintf(stderr, "record=%lu,%lu,", value.count, value.kind);
    for (auto byte : value.bytes)
        std::fprintf(stderr, "%02x", byte);
    std::fputc('\n', stderr);
}
} // namespace
extern "C" std::uint64_t checked_group_entry(const void *, std::uint64_t);
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
    need(argc >= 3);
    const bool client = std::strcmp(argv[1], "client") == 0;
    const bool input = std::strcmp(argv[1], "input") == 0;
    need(client || input || std::strcmp(argv[1], "output") == 0);
    --argc;
    ++argv;
    const bool named = std::strcmp(argv[1], "namespace") == 0;
    if (named) {
        --argc;
        ++argv;
        need(argc >= 2);
    }
    const std::uint64_t entry = (named ? 3 : 0) + (client ? 0 : input ? 1 : 2);
    const auto mode = std::strtoull(argv[1], nullptr, 10);
    if (named) {
        if (client) {
            need(argc >= 4);
            NamespaceClientArgument argument{0xC011, 91, {}, 0, {}};
            argument.command.operation = mode;
            argument.command.name.count = std::strlen(argv[2]);
            argument.command.value.count = std::strlen(argv[3]);
            need(argument.command.name.count <= 64 && argument.command.value.count <= 64);
            std::memcpy(argument.command.name.bytes, argv[2], argument.command.name.count);
            std::memcpy(argument.command.value.bytes, argv[3], argument.command.value.count);
            if (argc >= 5) {
                const auto mutation = std::strtoull(argv[4], nullptr, 10);
                if (mutation == 1)
                    argument.command.name.bytes[63] = 'x';
                if (mutation == 2)
                    argument.command.value.bytes[63] = 'x';
                if (mutation == 3)
                    argument.command.name.count = UINT64_MAX;
                if (mutation == 4)
                    argument.command.value.count = UINT64_MAX;
            }
            need(checked_group_entry(&argument, entry) == 42);
            record(argument.result.content);
            std::fprintf(stderr, "revision=%lu calls=%lu\n", argument.result.revision, calls);
            char remaining{};
            need(std::scanf(" %c", &remaining) == EOF);
        } else if (input) {
            NamespaceInputArgument argument{0xC051, 41, mode, {}};
            if (argc >= 3)
                limit = std::strtoull(argv[2], nullptr, 10);
            need(checked_group_entry(&argument, entry) == 42);
            std::fprintf(stderr, "name=%lu,", argument.result.command.name.count);
            for (auto byte : argument.result.command.name.bytes)
                std::fprintf(stderr, "%02x", byte);
            std::fprintf(stderr, "\nvalue=%lu,", argument.result.command.value.count);
            for (auto byte : argument.result.command.value.bytes)
                std::fprintf(stderr, "%02x", byte);
            std::fprintf(stderr,
                         "\noperation=%lu action=%lu carry=%lu nexts=%lu puts=%lu\n",
                         argument.result.command.operation,
                         argument.result.action,
                         argument.result.after_cr,
                         nexts,
                         put_count);
        } else {
            need(argc >= 8);
            NamespaceOutputArgument argument{0xC051, 41, {}};
            argument.response.kind = mode;
            argument.response.name.count = std::strlen(argv[2]);
            need(argument.response.name.count <= 64);
            std::memcpy(argument.response.name.bytes, argv[2], argument.response.name.count);
            argument.response.submitted = std::strtoull(argv[3], nullptr, 10);
            argument.response.result.content.kind = std::strtoull(argv[4], nullptr, 10);
            argument.response.result.revision = std::strtoull(argv[5], nullptr, 10);
            argument.response.result.content.count = std::strlen(argv[6]);
            need(argument.response.result.content.count <= 64);
            std::memcpy(argument.response.result.content.bytes, argv[6], argument.response.result.content.count);
            limit = std::strtoull(argv[7], nullptr, 10);
            if (argc >= 9) {
                const auto mutation = std::strtoull(argv[8], nullptr, 10);
                if (mutation == 1)
                    argument.response.result.content.bytes[63] = 'x';
                if (mutation == 2)
                    argument.response.result.content.bytes[0] = 0;
                if (mutation == 3)
                    argument.response.result.content.count = UINT64_MAX;
            }
            const auto result = checked_group_entry(&argument, entry);
            need(result <= 1);
            std::fprintf(stderr, "success=%lu puts=%lu nexts=%lu\n", result, put_count, nexts);
        }
        return 0;
    }
    if (client) {
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
        need(checked_group_entry(&argument, entry) == 42);
        record(argument.result);
        std::fprintf(stderr, "calls=%lu\n", calls);
        char remaining{};
        need(std::scanf(" %c", &remaining) == EOF);
    } else if (input) {
        InputArgument argument{0xC051, 41, mode, {}};
        if (argc >= 3)
            limit = std::strtoull(argv[2], nullptr, 10);
        need(checked_group_entry(&argument, entry) == 42);
        record(argument.result.command);
        std::fprintf(stderr,
                     "action=%lu carry=%lu nexts=%lu puts=%lu\n",
                     argument.result.action,
                     argument.result.after_cr,
                     nexts,
                     put_count);
    } else {
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
        const auto result = checked_group_entry(&argument, entry);
        need(result <= 1);
        std::fprintf(stderr, "success=%lu puts=%lu nexts=%lu\n", result, put_count, nexts);
    }
    return 0;
}
