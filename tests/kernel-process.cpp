// Hosted driver for the process image's frame allocator, boot volume, programs
// and process events: the generated Aurora policies (examples/kernel-process.au
// and its bridge) linked with the kernel's own storage and transport headers.
// Cases are data:
//   kernel-process frames CASES   memory-map and record cases (frames.cases)
//   kernel-process volumes BUNDLE volume cases built by scripts/kernel_volume.py;
//                                 a query program:ARGUMENTS:RESERVED:PATH admits
//                                 the entry as a program, budget:ARGUMENTS:
//                                 REQUESTED:FREE:PATH charges its load, runs:PATH
//                                 admits a run list
//   kernel-process events CASES   trap frames, kernel calls and memory decisions
//                                 (events.cases, memory.cases)
//   kernel-process files VOLUME CASES  file-service scripts over a volume
//                                 (files.cases), one fresh service per line
// stdout is compared with the golden file beside the cases.
#include "../kernel/execution-session.hpp"
#include "../kernel/service-bootstrap.hpp"
#include "../kernel/resident-owner.hpp"
#include "../kernel/retained-budget.hpp"
#include "../kernel/retained-service.hpp"
#include "../kernel/uefi/frames.hpp"
#include "../kernel/uefi/kernel-space.hpp"
#include "kernel-process-files.hpp"
#include <algorithm>
#include <cstring>
#include <cstdio>
#include <cstdlib>
#include <csignal>
#include <fstream>
#include <iterator>
#include <limits>
#include <iostream>
#include <memory>
#include <sstream>
#include <string>
#include <vector>
#include <sys/wait.h>
#include <sys/mman.h>
#include <unistd.h>

namespace aurora::words {
inline bool hosted_reachable = true;
auto accessible() -> bool {
    return hosted_reachable;
}
[[noreturn]] auto fail() -> void {
    std::abort();
}
} // namespace aurora::words
extern "C" {
void __au_runtime_word_view_construct(void *, aurora::words::Descriptor *);
auto __au_runtime_word_view_read(const void *, std::int64_t) -> std::uint64_t;
auto __au_runtime_word_view_finish(void *) -> bool;
auto __au_runtime_owned_words_borrow_span(const void *binding,
                                          std::uint64_t epoch,
                                          aurora::hosted::bytes::NativeSpan *output) -> void {
    *output = aurora::words::Binding::borrow_span(binding, epoch);
}
auto __au_runtime_owned_words_size(const void *binding, std::uint64_t epoch) -> std::uint64_t {
    return aurora::words::Binding::size(binding, epoch);
}
auto __au_runtime_owned_words_at(const void *binding, std::uint64_t epoch, std::uint64_t index) -> std::uint64_t {
    return aurora::words::Binding::at(binding, epoch, index);
}
auto __au_runtime_owned_words_set(const void *binding, std::uint64_t epoch, std::uint64_t index, std::uint64_t value)
    -> std::uint64_t {
    return aurora::words::Binding::set(binding, epoch, index, value);
}
auto __au_runtime_owned_words_finish(const void *binding, std::uint64_t epoch) -> std::uint64_t {
    return aurora::words::Binding::finish(binding, epoch);
}
}

namespace {
namespace frames = aurora::uefi::frames;
namespace process = aurora::uefi::process;
using U64 = std::uint64_t;

constexpr const char *map_names[] = {"valid", "version", "stride", "length", "alignment", "range", "overlap"};
constexpr const char *grant_names[] = {"granted", "map", "bounds", "arena", "uncovered"};
constexpr const char *volume_names[] = {"valid",
                                        "truncated",
                                        "limit",
                                        "magic",
                                        "version",
                                        "header",
                                        "count",
                                        "layout",
                                        "reserved",
                                        "checksum",
                                        "padding",
                                        "flags",
                                        "name",
                                        "path",
                                        "order",
                                        "data",
                                        "nesting"};
constexpr const char *elf_names[] = {
    "valid",     "truncated",   "magic",   "format",  "type",    "machine",     "header",
    "segment",   "interpreter", "dynamic", "tls",     "stack",   "permissions", "writable_executable",
    "alignment", "file",        "memory",  "address", "overlap", "entry",       "empty"};
constexpr const char *layout_names[] = {"valid", "image", "kernel", "arguments"};
constexpr const char *trap_names[] = {"kernel",
                                      "timer",
                                      "call",
                                      "system_call",
                                      "invalid_opcode",
                                      "stack_guard",
                                      "page_fault",
                                      "protection",
                                      "divide",
                                      "debug",
                                      "breakpoint",
                                      "overflow",
                                      "bound",
                                      "fpu",
                                      "alignment",
                                      "simd"};
constexpr const char *call_names[] = {"invalid",
                                      "exit",
                                      "print",
                                      "read",
                                      "map",
                                      "remap",
                                      "unmap",
                                      "open_directory",
                                      "open_beneath",
                                      "open_file",
                                      "close",
                                      "create_output",
                                      "write",
                                      "commit",
                                      "discard"};
constexpr const char *memory_names[] = {
    "mapped", "resized", "moved", "unmapped", "quota", "space", "records", "length", "malformed"};
constexpr const char *runs_names[] = {
    "valid", "truncated", "magic", "version", "count", "ticks", "path", "arguments", "flags", "padding", "trailing"};
constexpr const char *region_names[] = {"none", "segment", "stack", "arguments"};
constexpr const char *rejection_names[] = {"none",
                                           "operation",
                                           "record",
                                           "owner",
                                           "link",
                                           "not_free",
                                           "not_allocated",
                                           "kernel",
                                           "retired",
                                           "wrong_owner",
                                           "stale"};

auto rejection(frames::Rejection value) -> std::string {
    const auto raw = static_cast<U64>(value);
    if (raw <= static_cast<U64>(frames::Rejection::stale))
        return rejection_names[raw];
    return value == frames::Rejection::malformed ? "malformed" : value == frames::Rejection::index ? "index" : "?";
}
auto hex(U64 value) -> std::string {
    char text[24];
    std::snprintf(text, sizeof text, "%#llx", static_cast<unsigned long long>(value));
    return text;
}
[[noreturn]] auto usage(const std::string &reason) -> void {
    std::cerr << "kernel-process: " << reason << "\n";
    std::exit(2);
}

// One memory-map case: descriptor rows, the arena and volume, then operations.
class MapCase final {
public:
    std::string name;
    U64 stride = 48, version = 1, arena = 0, volume = 0, bytes = 0;
    std::vector<std::byte> map;
    std::vector<std::string> operations;
    auto descriptor(U64 type, U64 start, U64 pages, U64 attribute) -> void {
        const auto at = map.size();
        map.resize(at + stride);
        // A stride below the descriptor's 40 bytes keeps only the fields it holds.
        const auto put = [&](U64 offset, U64 value, unsigned width) {
            for (unsigned i = 0; i < width && offset + i < stride; ++i)
                map[at + offset + i] = std::byte(value >> (8 * i));
        };
        put(0, type, 4);
        put(8, start, 8);
        put(16, start, 8);
        put(24, pages, 8);
        put(32, attribute, 8);
    }
};

auto run_operations(const MapCase &item, frames::Table &table, std::span<U64> records) -> void {
    for (const auto &line : item.operations) {
        std::istringstream words{line};
        std::string verb;
        words >> verb;
        if (verb == "allocate") {
            U64 owner = 0, count = 1;
            words >> owner >> count;
            for (U64 i = 0; i < count; ++i) {
                const auto frame = table.allocate(owner);
                std::cout << "  allocate " << owner << " -> ";
                if (frame)
                    std::cout << "frame " << frame->index << " generation " << frame->generation << " at "
                              << hex(*table.address(frame->index)) << "\n";
                else
                    std::cout << "none\n";
            }
        } else if (verb == "release") {
            U64 index = 0, generation = 0, owner = 0;
            words >> index >> generation >> owner;
            std::cout << "  release " << index << " " << generation << " " << owner << " -> "
                      << rejection(table.release({index, generation}, owner)) << "\n";
        } else if (verb == "owner") {
            U64 owner = 0;
            words >> owner;
            std::cout << "  owner " << owner << " frames=" << table.allocated(owner) << "\n";
        } else if (verb == "corrupt-owner") {
            U64 index = 0, owner = 0;
            words >> index >> owner;
            if (index >= records.size())
                usage("corrupt-owner index");
            records[index] = (records[index] & 0xffffffffULL) | (owner << 32);
            std::cout << "  corrupt-owner " << index << " " << owner << "\n";
        } else if (verb == "corrupt-record") {
            U64 index = 0, value = 0;
            words >> index >> std::hex >> value;
            if (index >= records.size())
                usage("corrupt-record index");
            records[index] = value;
            std::cout << "  corrupt-record " << index << " " << hex(value) << "\n";
        } else if (verb == "finish") {
            std::cout << "  finish -> " << table.finish() << "\n";
        } else if (verb == "audit") {
            const auto audit = table.audit();
            std::cout << "  audit consistent=" << audit.consistent << " free=" << audit.free
                      << " allocated=" << audit.allocated << " kernel=" << audit.kernel << " retired=" << audit.retired
                      << " poisoned=" << table.poisoned() << "\n";
        } else if (verb == "transition") {
            // The policy alone: operation, record, owner, generation, link.
            U64 operation = 0, record = 0, owner = 0, generation = 0, link = 0;
            words >> operation >> std::hex >> record >> std::dec >> owner >> generation >> link;
            const auto decision =
                frames::transition(static_cast<frames::Operation>(operation), record, owner, generation, link);
            std::cout << "  transition " << operation << " " << hex(record) << " " << owner << " " << generation << " "
                      << link << " -> "
                      << (decision.rejection == frames::Rejection::none ? hex(decision.record)
                                                                        : rejection(decision.rejection))
                      << "\n";
        } else {
            usage("unknown operation: " + line);
        }
    }
}

auto run_map(const MapCase &item) -> void {
    auto ranges = std::make_unique<frames::Ranges>();
    const auto found =
        frames::inventory(item.map, item.stride, item.version, item.arena, item.volume, item.bytes, *ranges);
    std::cout << item.name << ": map=" << map_names[static_cast<U64>(found.map)]
              << " grant=" << (found.grant ? grant_names[static_cast<U64>(*found.grant)] : "none")
              << " ranges=" << ranges->count() << " frames=" << ranges->frames();
    if (found.map != process::MapVerdict::valid || (found.grant && found.grant != process::GrantVerdict::granted) ||
        !found.ranges) {
        std::cout << (found.ranges ? "" : " inventory=rejected") << "\n";
        return;
    }
    const auto plan = aurora::uefi::KernelSpace::plan(ranges->frames(), (item.bytes + 4095) / 4096, 0);
    if (!plan) {
        std::cout << " plan=rejected\n";
        return;
    }
    std::cout << " tables=" << plan->tables << " metadata=" << plan->metadata << "\n";
    // Long inventories show their first two and last ranges.
    for (std::size_t i = 0; i < ranges->count(); ++i) {
        if (ranges->count() > 8 && i == 2)
            std::cout << "  ...\n";
        if (ranges->count() > 8 && i >= 2 && i + 1 < ranges->count())
            continue;
        std::cout << "  range " << hex(ranges->range(i).first_page * 4096) << " pages=" << ranges->range(i).pages
                  << " index=" << ranges->range(i).first_index << "\n";
    }
    if (ranges->frames() > (U64{1} << 20)) {
        std::cout << "  table=not-bound\n";
        return;
    }
    std::vector<U64> records(ranges->frames());
    frames::Table table;
    if (!table.bind(records, *ranges, plan->tables, plan->metadata)) {
        std::cout << "  bind=rejected\n";
        return;
    }
    std::cout << "  bound reserved=" << table.reserved() << " free=" << table.free() << "\n";
    run_operations(item, table, records);
    std::cout.flush();
    _exit(0);
}

auto number(const std::string &text) -> U64 {
    std::size_t used = 0;
    const auto value = std::stoull(text, &used, 0);
    if (used != text.size())
        usage("bad number: " + text);
    return value;
}

// Data-selected primitive grant checks. Deliberate bad authority must abort
// before touching backing, not become a recoverable allocator result.
auto grant_case(const std::string &name) -> void {
    std::cout.flush();
    const auto child = fork();
    if (child < 0)
        usage("grant fixture fork");
    if (!child) {
        using aurora::words::Access;
        using aurora::words::Binding;
        using aurora::words::Descriptor;
        std::array<U64, 4> words{};
        alignas(16) Descriptor root{};
        Binding binding;
        if (name == "empty") {
            static_cast<void>(binding.bind({}, &root, sizeof(root)));
            _exit(3);
        }
        if (name == "root-overlap") {
            static_cast<void>(binding.bind(words, words.data(), sizeof(root)));
            _exit(3);
        }
        if (name == "root-overflow") {
            static_cast<void>(binding.bind(words, &root, std::numeric_limits<std::size_t>::max()));
            _exit(3);
        }
        root = binding.bind(words, &root, sizeof(root));
        const auto epoch = root.epoch;
        if (name == "roundtrip") {
            Binding::Scope scope(binding, Access::write);
            if (!Binding::set(root.binding, root.epoch, 2, 0x5678))
                _exit(3);
        }
        if (name == "duplicate") {
            Binding second;
            alignas(16) Descriptor other{};
            static_cast<void>(second.bind(words, &other, sizeof(other)));
            _exit(3);
        }
        if (name == "wrong-root")
            aurora::words::hosted_reachable = false;
        if (name == "detached" || name == "wrong-bank" || name == "wrong-extent" || name == "roundtrip") {
            binding.suspend();
            if (name == "wrong-bank")
                binding.resume(words.data() + 1, words.size());
            if (name == "wrong-extent")
                binding.resume(words.data(), words.size() - 1);
            if (name == "roundtrip") {
                binding.resume(words.data(), words.size());
                Binding::Scope scope(binding, Access::read);
                if (root.epoch != epoch || Binding::at(root.binding, root.epoch, 2) != 0x5678)
                    _exit(3);
            }
        }
        if (name == "revoked" || name == "roundtrip") {
            {
                Binding::Scope scope(binding, Access::consume);
                if (!Binding::set(root.binding, root.epoch, 3, 0x1234) ||
                    Binding::at(root.binding, root.epoch, 3) != 0x1234 ||
                    Binding::size(root.binding, root.epoch) != words.size() ||
                    !Binding::finish(root.binding, root.epoch))
                    _exit(3);
            }
            if (name == "roundtrip")
                _exit(words[3] == 0x1234 ? 0 : 3);
        }
        Binding::Scope scope(binding, Access::read);
        if (name == "reentrant") {
            Binding::Scope nested(binding, Access::read);
        } else if (name == "suspend-live") {
            binding.suspend();
        } else if (name == "readonly-write") {
            static_cast<void>(Binding::set(root.binding, root.epoch, 0, 1));
        } else if (name == "borrowed-finish") {
            static_cast<void>(Binding::finish(root.binding, root.epoch));
        } else if (name == "foreign") {
            static_cast<void>(Binding::at(reinterpret_cast<const void *>(1), root.epoch, 0));
        } else if (name == "stale") {
            static_cast<void>(Binding::at(root.binding, root.epoch + 1, 0));
        } else if (name == "bounds") {
            static_cast<void>(Binding::at(root.binding, root.epoch, words.size()));
        }
        _exit(3);
    }
    int status = 0;
    if (waitpid(child, &status, 0) != child)
        usage("grant fixture wait");
    const bool success = name == "roundtrip";
    if (success ? (!WIFEXITED(status) || WEXITSTATUS(status) != 0)
                : (!WIFSIGNALED(status) || WTERMSIG(status) != SIGABRT))
        usage("grant fixture did not stop before access: " + name);
    std::cout << "grant " << name << " -> " << (success ? "passed" : "denied") << "\n";
}

// The descriptor output is shared only by this hostile adapter fixture. A
// rejected borrow must abort without publishing even one backing-address byte.
auto word_borrow_case(const std::string &name) -> void {
    using aurora::hosted::bytes::NativeSpan;
    using aurora::words::Access;
    using aurora::words::Binding;
    using aurora::words::Descriptor;
    const NativeSpan sentinel{1234, {1234, 1234, 1234, 1234}, 1234, 1234};
    void *shared = mmap(nullptr, sizeof(NativeSpan), PROT_READ | PROT_WRITE, MAP_SHARED | MAP_ANONYMOUS, -1, 0);
    if (shared == MAP_FAILED)
        usage("word borrow fixture mapping");
    auto *output = std::construct_at(static_cast<NativeSpan *>(shared), sentinel);
    std::cout.flush();
    const auto child = fork();
    if (child < 0)
        usage("word borrow fixture fork");
    if (!child) {
        std::array<U64, 4> words{};
        alignas(16) Descriptor root{};
        Binding binding;
        root = binding.bind(words, &root, sizeof(root));
        const auto epoch = root.epoch;
        if (name == "no-scope") {
            __au_runtime_owned_words_borrow_span(root.binding, epoch, output);
            _exit(3);
        }
        if (name == "detached")
            binding.suspend();
        if (name == "revoked") {
            Binding::Scope scope(binding, Access::consume);
            static_cast<void>(Binding::finish(root.binding, epoch));
        }
        if (name == "roundtrip") {
            {
                Binding::Scope scope(binding, Access::write);
                static_cast<void>(Binding::set(root.binding, epoch, 0, U64{1} << 63));
                static_cast<void>(Binding::set(root.binding, epoch, 3, ~U64{0}));
            }
            binding.suspend();
            binding.resume(words.data(), words.size());
        }
        Binding::Scope scope(binding, Access::read);
        if (name == "reentrant") {
            Binding::Scope nested(binding, Access::read);
        }
        if (name == "wrong-root")
            ++root.epoch;
        if (name == "unreachable")
            aurora::words::hosted_reachable = false;
        const void *actual = name == "foreign" ? reinterpret_cast<const void *>(1) : root.binding;
        __au_runtime_owned_words_borrow_span(actual, name == "stale" ? epoch + 1 : epoch, output);
        if (name != "roundtrip")
            _exit(3);
        const auto *values = reinterpret_cast<const U64 *>(output->payload[0]);
        const bool valid = output->kind == 0 && output->payload[1] == 0 && output->payload[2] == 0 &&
                           output->payload[3] == 0 && output->start == 0 && output->length == 4 &&
                           root.epoch == epoch && values == words.data() && values[0] == (U64{1} << 63) &&
                           values[3] == ~U64{0};
        _exit(valid ? 0 : 3);
    }
    int status = 0;
    if (waitpid(child, &status, 0) != child)
        usage("word borrow fixture wait");
    const bool success = name == "roundtrip";
    const bool unchanged = std::memcmp(output, &sentinel, sizeof(sentinel)) == 0;
    std::destroy_at(output);
    if (munmap(shared, sizeof(NativeSpan)))
        usage("word borrow fixture unmap");
    if (success ? (!WIFEXITED(status) || WEXITSTATUS(status) != 0)
                : (!WIFSIGNALED(status) || WTERMSIG(status) != SIGABRT || !unchanged))
        usage("word borrow fixture published invalid authority: " + name);
    std::cout << "word-borrow " << name << " -> " << (success ? "passed" : "denied before publication") << "\n";
}

auto source_word_case(const std::string &name, U64 count, std::int64_t index, U64 expected) -> void {
    using aurora::words::Access;
    using aurora::words::Binding;
    if (count == 0 || count > 16)
        usage("source word fixture extent");
    const bool bounded = index >= 0 && static_cast<U64>(index) < count;
    std::cout.flush();
    const auto child = fork();
    if (child < 0)
        usage("source word fixture fork");
    if (!child) {
        std::vector<U64> backing(count);
        alignas(16) std::array<std::byte, 16> root{};
        Binding binding;
        auto input = binding.bind(backing, root.data(), root.size());
        __au_runtime_word_view_construct(root.data(), &input);
        if (input.binding || input.epoch)
            _exit(3);
        const auto descriptor = std::bit_cast<aurora::words::Descriptor>(root);
        if (bounded) {
            Binding::Scope scope(binding, Access::write);
            static_cast<void>(Binding::set(descriptor.binding, descriptor.epoch, static_cast<U64>(index), expected));
        }
        {
            Binding::Scope scope(binding, Access::read);
            if (__au_runtime_word_view_read(root.data(), index) != expected || !bounded)
                _exit(3);
        }
        {
            Binding::Scope scope(binding, Access::consume);
            if (!__au_runtime_word_view_finish(root.data()))
                _exit(3);
        }
        _exit(!binding.live() && std::all_of(root.begin(),
                                             root.end(),
                                             [](std::byte b) {
                                                 return b == std::byte{0};
                                             })
                  ? 0
                  : 3);
    }
    int status = 0;
    if (waitpid(child, &status, 0) != child)
        usage("source word fixture wait");
    if (bounded ? (!WIFEXITED(status) || WEXITSTATUS(status) != 0)
                : (!WIFSIGNALED(status) || WTERMSIG(status) != SIGILL))
        usage("source word fixture value or bounds: " + name);
    std::cout << "source-word " << name << " -> " << (bounded ? hex(expected) : "bounds trap") << "\n";
}

auto frames_mode(const char *path) -> int {
    std::ifstream input{path};
    if (!input)
        usage("cannot read cases");
    std::optional<MapCase> current;
    std::string line;
    while (std::getline(input, line)) {
        if (const auto hash = line.find('#'); hash != std::string::npos)
            line.resize(hash);
        std::istringstream words{line};
        std::string verb;
        if (!(words >> verb))
            continue;
        std::vector<std::string> rest;
        for (std::string word; words >> word;)
            rest.push_back(word);
        if (verb == "source-word-case" && !current && rest.size() == 4) {
            source_word_case(rest[0], number(rest[1]), std::stoll(rest[2], nullptr, 0), number(rest[3]));
        } else if (verb == "word-borrow-case" && !current && rest.size() == 1) {
            word_borrow_case(rest[0]);
        } else if (verb == "grant-case" && !current && rest.size() == 1) {
            grant_case(rest[0]);
        } else if (verb == "case") {
            if (current || rest.size() != 1)
                usage("unterminated or unnamed case");
            current = MapCase{};
            current->name = rest[0];
        } else if (!current) {
            usage("row outside a case: " + line);
        } else if (verb == "end") {
            std::cout.flush();
            const auto child = fork();
            if (child < 0)
                usage("frame fixture fork");
            if (!child) {
                run_map(*current);
                std::cout.flush();
                // Some adversarial cases deliberately retain live/corrupt
                // allocations. Process termination, not a source destructor or
                // successful consuming finish, ends their private fixture.
                _exit(0);
            }
            int status = 0;
            if (waitpid(child, &status, 0) != child || !WIFEXITED(status) || WEXITSTATUS(status))
                usage("frame fixture child failed");
            current.reset();
        } else if (verb == "stride" && rest.size() == 1) {
            current->stride = number(rest[0]);
        } else if (verb == "version" && rest.size() == 1) {
            current->version = number(rest[0]);
        } else if (verb == "arena" && rest.size() == 1) {
            current->arena = number(rest[0]);
        } else if (verb == "volume" && rest.size() == 2) {
            current->volume = number(rest[0]);
            current->bytes = number(rest[1]);
        } else if (verb == "desc" && (rest.size() == 3 || rest.size() == 4)) {
            current->descriptor(
                number(rest[0]), number(rest[1]), number(rest[2]), rest.size() == 4 ? number(rest[3]) : 0);
        } else if (verb == "repeat" && rest.size() == 5) {
            // COUNT descriptors of TYPE and PAGES from START, STEP bytes apart.
            for (U64 i = 0; i < number(rest[0]); ++i)
                current->descriptor(number(rest[1]), number(rest[2]) + i * number(rest[4]), number(rest[3]), 0);
        } else if (verb == "truncate" && rest.size() == 1) {
            current->map.resize(current->map.size() - number(rest[0]));
        } else if (verb == "op") {
            std::string joined;
            for (const auto &word : rest)
                joined += (joined.empty() ? "" : " ") + word;
            current->operations.push_back(joined);
        } else {
            usage("unknown row: " + line);
        }
    }
    if (current)
        usage("unterminated case");
    return 0;
}

auto bytes_of(const std::string &text) -> std::span<const std::byte> {
    return {reinterpret_cast<const std::byte *>(text.data()), text.size()};
}
auto escaped(std::span<const std::byte> bytes) -> std::string {
    std::string text;
    for (const auto byte : bytes)
        text += byte == std::byte{0} ? std::string{"\\0"} : std::string(1, static_cast<char>(byte));
    return text;
}
auto flags_name(U64 flags) -> std::string {
    return flags == process::leaf_read      ? "read"
           : flags == process::leaf_execute ? "execute"
           : flags == process::leaf_write   ? "write"
                                            : hex(flags);
}

// An entry admitted as a program: verdicts, entry point and regions.
auto program_query(std::span<const std::byte> image, U64 arguments, U64 reserved) -> void {
    const auto elf = process::elf_admit(image);
    std::cout << "elf=" << (elf ? elf_names[static_cast<U64>(*elf)] : "malformed");
    const auto layout = process::layout(image, reserved, reserved + (U64{4} << 20), arguments);
    std::cout << " layout=" << (layout ? layout_names[static_cast<U64>(*layout)] : "malformed");
    if (layout != process::LayoutVerdict::valid) {
        std::cout << "\n";
        return;
    }
    std::cout << " entry=" << hex(process::elf_entry(image)) << "\n";
    for (U64 index = 0;; ++index) {
        const auto region = process::region(image, index, arguments);
        if (!region) {
            std::cout << "    region malformed\n";
            return;
        }
        if (region->kind == 0)
            return;
        std::cout << "    " << region_names[region->kind] << " first=" << hex(region->first)
                  << " pages=" << region->pages << " " << flags_name(region->flags) << " vaddr=" << hex(region->vaddr)
                  << " offset=" << region->offset << " bytes=" << region->bytes << "\n";
    }
}

// The load charge and quota of an entry run with one shared kernel slot.
auto budget_query(std::span<const std::byte> image, U64 arguments, U64 requested, U64 free) -> void {
    const auto budget = process::memory_budget(image, arguments, 1, requested, free);
    if (!budget)
        std::cout << "malformed\n";
    else if (budget->verdict != static_cast<U64>(process::BudgetVerdict::valid))
        std::cout << "quota\n";
    else
        std::cout << "valid quota=" << budget->quota << " charged=" << budget->charged << "\n";
}

// An entry admitted as a run list: the verdict and each run.
auto runs_query(std::span<const std::byte> runs) -> void {
    const auto verdict = process::runs_admit(runs);
    std::cout << (verdict ? runs_names[static_cast<U64>(*verdict)] : "malformed") << "\n";
    if (verdict != process::RunsVerdict::valid)
        return;
    for (U64 index = 0;; ++index) {
        const auto entry = process::run(runs, index);
        if (!entry) {
            std::cout << "    run malformed\n";
            return;
        }
        if (!entry->found)
            return;
        std::cout << "    run " << index + 1 << " ticks=" << entry->ticks << " flags=" << entry->flags
                  << " quota=" << entry->quota << " path=" << escaped(runs.subspan(entry->path, entry->path_bytes))
                  << " arguments=" << escaped(runs.subspan(entry->arguments, entry->argument_bytes)) << "\n";
    }
}

auto volumes_mode(const char *path) -> int {
    std::ifstream input{path, std::ios::binary | std::ios::ate};
    std::vector<char> raw(static_cast<std::size_t>(input.tellg()));
    input.seekg(0);
    if (!input || !input.read(raw.data(), static_cast<std::streamsize>(raw.size())))
        usage("cannot read bundle");
    std::size_t at = 0;
    const auto take = [&](std::size_t size) {
        if (size > raw.size() - at)
            usage("truncated bundle");
        const auto *begin = raw.data() + at;
        at += size;
        return std::string{begin, size};
    };
    const auto word = [&](unsigned width) {
        const auto bytes = take(width);
        U64 value = 0;
        for (unsigned i = 0; i < width; ++i)
            value |= U64(static_cast<unsigned char>(bytes[i])) << (8 * i);
        return value;
    };
    while (at < raw.size()) {
        const auto name = take(word(4));
        std::vector<std::string> queries(word(4));
        for (auto &query : queries)
            query = take(word(4));
        const auto text = take(word(8));
        std::vector<std::byte> bytes(text.size());
        for (std::size_t i = 0; i < text.size(); ++i)
            bytes[i] = std::byte(static_cast<unsigned char>(text[i]));
        const auto verdict = process::volume_admit(bytes);
        std::cout << name << ": " << (verdict ? volume_names[static_cast<U64>(*verdict)] : "malformed") << "\n";
        for (const auto &query : queries) {
            if (query.starts_with("program:") || query.starts_with("budget:") || query.starts_with("runs:")) {
                // program:ARGUMENTS:RESERVED:PATH, budget:ARGUMENTS:REQUESTED:FREE:PATH or runs:PATH.
                std::istringstream parts{query};
                std::string kind, arguments, reserved, free, name;
                std::getline(parts, kind, ':');
                if (kind != "runs") {
                    std::getline(parts, arguments, ':');
                    std::getline(parts, reserved, ':');
                }
                if (kind == "budget")
                    std::getline(parts, free, ':');
                std::getline(parts, name);
                const auto entry = process::volume_lookup(bytes, bytes_of(name));
                std::cout << "  " << kind << " " << name << " -> ";
                if (!entry)
                    std::cout << "absent\n";
                else if (kind == "program")
                    program_query(*entry, number(arguments), number(reserved));
                else if (kind == "budget")
                    budget_query(*entry, number(arguments), number(reserved), number(free));
                else
                    runs_query(*entry);
                continue;
            }
            const auto entry = process::volume_lookup(
                bytes, std::span<const std::byte>{reinterpret_cast<const std::byte *>(query.data()), query.size()});
            std::cout << "  " << query << " -> ";
            if (!entry) {
                std::cout << "absent\n";
                continue;
            }
            std::cout << "offset " << entry->data() - bytes.data() << " bytes " << entry->size() << " base64=";
            for (U64 offset = 0; offset < entry->size(); offset += 3) {
                const auto group = process::base64_group(*entry, offset);
                if (!group)
                    usage("malformed base64 group");
                for (unsigned i = 0; i < 4; ++i)
                    std::cout << static_cast<char>(*group >> (8 * i));
            }
            std::cout << "\n";
        }
    }
    return 0;
}
// A memory decision: its verdict, the mapping it leaves and the next state.
auto decision_text(const std::optional<process::MemoryDecision> &decision) -> std::string {
    if (!decision)
        return "malformed decision";
    std::string text = memory_names[decision->verdict];
    if (decision->pages)
        text += " first=" + hex(decision->first) + " reserved=" + std::to_string(decision->reserved) +
                " pages=" + std::to_string(decision->pages);
    return text + " next=" + hex(decision->next) + " charged=" + std::to_string(decision->charged);
}
// trap VECTOR ERROR RIP CS FLAGS RSP SS CR2 OPCODE, call OPERATION A B C, or a
// memory decision: map STATE BYTES, remap STATE RECORD BYTES TARGET, unmap
// STATE RECORD BYTES (STATE is NEXT CHARGED QUOTA COUNT, RECORD FIRST
// RESERVED PAGES), find BASE RECORD... or fault ADDRESS ERROR RECORD....
auto events_mode(const char *path) -> int {
    std::ifstream input{path};
    if (!input)
        usage("cannot read cases");
    std::string line;
    while (std::getline(input, line)) {
        if (const auto hash = line.find('#'); hash != std::string::npos)
            line.resize(hash);
        std::istringstream words{line};
        std::string verb;
        if (!(words >> verb))
            continue;
        std::vector<U64> values;
        for (std::string word; words >> word;)
            values.push_back(number(word));
        std::string text = verb;
        for (const auto value : values)
            text += " " + hex(value);
        if (verb == "trap" && values.size() == 9) {
            const process::ProcessTrap trap{
                values[0], values[1], values[2], values[3], values[4], values[5], values[6], values[7], values[8]};
            const auto kind = process::trap(trap);
            std::cout << text << " -> " << (kind ? trap_names[static_cast<U64>(*kind)] : "malformed") << "\n";
        } else if (verb == "call" && (values.size() == 4 || values.size() == 5)) {
            const auto call =
                process::call(values[0], values[1], values[2], values[3], values.size() == 5 ? values[4] : 0);
            std::cout << text << " -> ";
            if (!call)
                std::cout << "malformed\n";
            else
                std::cout << call_names[call->action] << " value=" << hex(call->value) << " length=" << call->length
                          << " base=" << hex(call->base) << " record=" << hex(call->record) << "\n";
        } else if ((verb == "map" && values.size() == 5) || (verb == "remap" && values.size() == 9) ||
                   (verb == "unmap" && values.size() == 8)) {
            const process::MemoryState state{values[0], values[1], values[2], values[3]};
            const process::MemoryRecord record{values.size() > 5 ? values[4] : 0,
                                               values.size() > 5 ? values[5] : 0,
                                               values.size() > 6 ? values[6] : 0};
            const auto decision = verb == "map"     ? process::memory_map(state, values[4])
                                  : verb == "remap" ? process::memory_remap(state, record, values[7], values[8])
                                                    : process::memory_unmap(state, record, values[7]);
            std::cout << text << " -> " << decision_text(decision) << "\n";
        } else if ((verb == "find" || verb == "fault") && values.size() >= (verb == "find" ? 1U : 2U) &&
                   (values.size() - (verb == "find" ? 1 : 2)) % 3 == 0) {
            std::vector<process::MemoryRecord> records;
            for (auto at = verb == "find" ? 1U : 2U; at < values.size(); at += 3)
                records.push_back({values[at], values[at + 1], values[at + 2]});
            const auto found = verb == "find" ? process::memory_find(records, values[0])
                                              : process::memory_fault(records, values[0], values[1]);
            std::cout << text << " -> "
                      << (found.malformed ? std::string{"malformed"}
                          : found.index   ? "record " + std::to_string(*found.index)
                                          : std::string{"none"})
                      << "\n";
        } else {
            usage("unknown event: " + line);
        }
    }
    return 0;
}
// The file service over heap pages: frame handles are page numbers + 1, the
// quota is a frame count each case may set.
class HostedStore final {
public:
    std::vector<std::array<std::byte, 4096>> pages;
    std::vector<bool> live;
    U64 quota_frames = 1 << 20, charge_count = 0, files = 0;
    [[nodiscard]] auto take() -> std::optional<U64> {
        if (files >= charge_count)
            return std::nullopt;
        pages.emplace_back();
        live.push_back(true);
        ++files;
        return pages.size();
    }
    [[nodiscard]] auto give(U64 frame) -> bool {
        if (frame == 0 || frame > pages.size() || !live[frame - 1] || files == 0)
            return false;
        live[frame - 1] = false;
        --files;
        return true;
    }
    [[nodiscard]] auto charge(U64 count) -> bool {
        if (count > quota_frames - charge_count)
            return false;
        charge_count += count;
        return true;
    }
    [[nodiscard]] auto uncharge(U64 count) -> bool {
        if (count > charge_count || charge_count - count < files)
            return false;
        charge_count -= count;
        return true;
    }
    [[nodiscard]] auto charged() const -> U64 {
        return charge_count;
    }
    [[nodiscard]] auto quota() const -> U64 {
        return quota_frames;
    }
    [[nodiscard]] auto charged_files() const -> U64 {
        return charge_count;
    }
    [[nodiscard]] auto page(U64 frame) -> std::array<std::byte, 4096> * {
        return frame && frame <= pages.size() && live[frame - 1] ? &pages[frame - 1] : nullptr;
    }
    [[nodiscard]] auto read_word(U64 frame, U64 index) -> U64 {
        auto *held = index < 512 ? page(frame) : nullptr;
        U64 value = 0;
        if (held)
            std::memcpy(&value, held->data() + 8 * index, 8);
        return value;
    }
    [[nodiscard]] auto write_word(U64 frame, U64 index, U64 value) -> bool {
        auto *held = index < 512 ? page(frame) : nullptr;
        if (held)
            std::memcpy(held->data() + 8 * index, &value, 8);
        return held;
    }
    [[nodiscard]] auto copy_in(U64 frame, U64 offset, std::span<const std::byte> bytes) -> bool {
        auto *held = offset <= 4096 && bytes.size() <= 4096 - offset ? page(frame) : nullptr;
        if (held)
            std::copy(bytes.begin(), bytes.end(), held->begin() + static_cast<std::ptrdiff_t>(offset));
        return held;
    }
    [[nodiscard]] auto copy_out(U64 frame, U64 offset, std::span<std::byte> bytes) -> bool {
        auto *held = offset <= 4096 && bytes.size() <= 4096 - offset ? page(frame) : nullptr;
        if (held)
            std::copy_n(held->begin() + static_cast<std::ptrdiff_t>(offset), bytes.size(), bytes.begin());
        return held;
    }
};
using HostedFiles = aurora::uefi::FileService<HostedStore>;
constexpr const char *file_status_names[] = {"success",
                                             "invalid_handle",
                                             "not_found",
                                             "denied",
                                             "escape",
                                             "not_regular",
                                             "exhausted",
                                             "too_large",
                                             "invalid_path",
                                             "failed"};
auto status_name(U64 value) -> std::string {
    const auto status = static_cast<std::int64_t>(value);
    return status <= 0 && status >= -9 ? file_status_names[-status] : "count " + std::to_string(value);
}
// A path word: %XX is a byte, {N} repeats the byte before it to N in all.
auto path_word(const std::string &word) -> std::string {
    std::string bytes;
    for (std::size_t at = 0; at < word.size(); ++at) {
        if (word[at] == '%' && at + 2 < word.size()) {
            bytes += static_cast<char>(std::stoi(word.substr(at + 1, 2), nullptr, 16));
            at += 2;
        } else if (word[at] == '{' && !bytes.empty() && word.find('}', at) != std::string::npos) {
            const auto end = word.find('}', at);
            const auto count = std::stoull(word.substr(at + 1, end - at - 1));
            bytes.append(count - 1, bytes.back());
            at = end;
        } else {
            bytes += word[at];
        }
    }
    return bytes;
}
// One script per line (files.cases): operations as the HostFiles probe names
// them, each printing its ordinal, status and raw result words. An id is @N
// (the id operation N returned), @N+K or a literal.
auto files_script(std::span<const std::byte> volume, const std::string &line) -> void {
    std::istringstream words{line};
    std::vector<std::string> script;
    for (std::string word; words >> word;)
        script.push_back(word == "''" ? std::string{} : word);
    HostedStore store;
    auto files = std::make_unique<HostedFiles>();
    if (!files->begin(volume, store))
        usage("file service start");
    std::vector<U64> ids(1);
    std::cout << line << "\n";
    std::size_t at = 0;
    const auto take = [&]() {
        if (at >= script.size())
            usage("missing operand: " + line);
        return script[at++];
    };
    const auto id = [&]() {
        const auto word = take();
        if (word.starts_with("@")) {
            const auto plus = word.find('+');
            const auto ordinal = number(word.substr(1, plus == std::string::npos ? std::string::npos : plus - 1));
            if (ordinal >= ids.size())
                usage("forward reference: " + line);
            return ids[ordinal] + (plus == std::string::npos ? 0 : number(word.substr(plus + 1)));
        }
        return number(word);
    };
    while (at < script.size()) {
        const auto verb = take();
        HostedFiles::Result result;
        std::string text;
        if (verb == "quota") {
            store.quota_frames = number(take());
            continue;
        }
        if (verb == "dir" || verb == "file") {
            const auto path = path_word(take());
            result = files->open(
                verb == "dir" ? 0 : 2, 0, path.size() > 4095 ? std::span<const std::byte>{} : bytes_of(path));
        } else if (verb == "open") {
            const auto directory = id();
            const auto path = path_word(take());
            result = files->open(1, directory, path.size() > 4095 ? std::span<const std::byte>{} : bytes_of(path));
        } else if (verb == "create") {
            const auto path = path_word(take());
            result = files->create(path.size() > 4095 ? std::span<const std::byte>{} : bytes_of(path));
        } else if (verb == "close" || verb == "commit" || verb == "discard") {
            const auto handle = id();
            result = verb == "close"    ? files->close(handle)
                     : verb == "commit" ? files->commit(handle)
                                        : files->discard(handle);
        } else if (verb == "read") {
            const auto file = id();
            const auto offset = number(take());
            std::array<std::byte, process::file_chunk> chunk{};
            result = files->read(file, offset, chunk);
            if (!result.broken && static_cast<std::int64_t>(result.value) >= 0) {
                text = " " + escaped(std::span{chunk}.first(std::min<U64>(result.value, 32)));
            }
        } else if (verb == "write") {
            const auto output = id();
            const auto bytes = path_word(take());
            result = files->write(output, bytes_of(bytes));
        } else if (verb == "fill") {
            // BYTES bytes of 'x' in writes of at most 4096, to the first failure.
            const auto output = id();
            const auto total = number(take());
            const std::string block(4096, 'x');
            U64 done = 0;
            while (done < total && !result.broken && result.value == 0) {
                const auto count = std::min<U64>(4096, total - done);
                result = files->write(output, bytes_of(block).first(count));
                done += result.value == 0 ? count : 0;
            }
            text = " written=" + std::to_string(done);
        } else if (verb == "frames") {
            std::cout << "  " << ids.size() << " frames charged=" << store.charge_count << " held=" << store.files
                      << "\n";
            ids.push_back(0);
            continue;
        } else if (verb == "finish") {
            const auto finished = files->finish([&](U64 record) {
                std::string path;
                if (!files->path(record, [&](std::uint8_t byte) {
                        const auto encoded = process::path_text(byte);
                        if (encoded)
                            path.append(encoded->characters.data(), encoded->count);
                    }))
                    return false;
                std::string bytes(files->record(record).size, '\0');
                if (!files->bytes(record, 0, std::as_writable_bytes(std::span{bytes})))
                    return false;
                std::cout << "  export " << path << " bytes=" << bytes.size() << " "
                          << escaped(bytes_of(bytes).first(std::min<std::size_t>(bytes.size(), 32))) << "\n";
                return true;
            });
            std::cout << "  " << ids.size() << " finish " << (finished ? "clean" : "broken")
                      << " charged=" << store.charge_count << " held=" << store.files << "\n";
            return;
        } else {
            usage("unknown file operation: " + verb);
        }
        if (result.broken) {
            std::cout << "  " << ids.size() << " " << verb << " broken\n";
            return;
        }
        std::cout << "  " << ids.size() << " " << verb << " "
                  << (verb == "read" && static_cast<std::int64_t>(result.value) >= 0
                          ? "success " + std::to_string(result.value)
                          : status_name(result.value))
                  << text;
        if (verb == "dir" || verb == "open" || verb == "file" || verb == "create") {
            std::cout << " id=" << result.record[0];
            if (verb != "dir" && verb != "create")
                std::cout << " size=" << result.record[1];
            std::cout << " identity=" << result.record[2] << ":" << result.record[3];
            if (verb == "create")
                std::cout << " directory=" << result.record[4] << ":" << result.record[5];
        }
        std::cout << "\n";
        ids.push_back(result.record[0]);
    }
}

auto files_mode(const char *volume_path, const char *cases) -> int {
    std::ifstream image{volume_path, std::ios::binary};
    const std::string raw{std::istreambuf_iterator<char>{image}, {}};
    const auto volume = bytes_of(raw);
    if (process::volume_admit(volume) != process::VolumeVerdict::valid)
        usage("volume not admitted");
    std::ifstream input{cases};
    if (!input)
        usage("cannot read cases");
    for (std::string line; std::getline(input, line);) {
        if (line.empty() || line.starts_with("#"))
            continue;
        files_script(volume, line);
    }
    return 0;
}
// The same process driver checks the closed handoff rows before any machine
// access. Cases only edit copied words; expected acceptance is reviewed data.
auto handoff_mode(const char *cases) -> int {
    using aurora::uefi::Handoff;
    using aurora::uefi::put;
    constexpr U64 arena = 0x1000000;
    std::ifstream input{cases};
    if (!input)
        usage("cannot read cases");
    for (std::string line; std::getline(input, line);) {
        if (line.empty() || line.starts_with("#"))
            continue;
        std::istringstream row{line};
        std::string name, tag;
        row >> name >> tag;
        std::array<std::byte, Handoff::header> h{};
        for (const auto &[offset, value] :
             std::initializer_list<std::pair<std::size_t, U64>>{{0, Handoff::magic},
                                                                {16, Handoff::arena_bytes},
                                                                {24, arena},
                                                                {32, 4800},
                                                                {40, 48},
                                                                {56, 8192},
                                                                {64, 4096},
                                                                {72, 8192},
                                                                {80, 12288},
                                                                {88, arena + Handoff::tables_offset},
                                                                {96, 9},
                                                                {104, arena + Handoff::payload_offset},
                                                                {112, 0xf5e10},
                                                                {136, 0x20000000},
                                                                {144, 8192},
                                                                {168, 252},
                                                                {176, number(tag)}})
            put(h, offset, value);
        put(h, 8, 10, 4);
        put(h, 12, Handoff::header, 4);
        put(h, 48, 1, 4);
        put(h, 52, 1, 4);
        if (number(tag) == 3) {
            put(h, Handoff::case_word, 10);
            put(h, Handoff::bar_record_word, arena + Handoff::bar_record_offset);
        }
        for (std::string edit; row >> edit;) {
            const auto colon = edit.find(':');
            const auto equals = edit.find('=');
            if (colon == std::string::npos || equals == std::string::npos || colon >= equals)
                usage("bad handoff edit");
            const auto offset = number(edit.substr(0, colon));
            const auto width = number(edit.substr(colon + 1, equals - colon - 1));
            if (!width || width > 8 || offset > h.size() || width > h.size() - offset)
                usage("handoff edit bounds");
            put(h, offset, number(edit.substr(equals + 1)), static_cast<unsigned>(width));
        }
        std::cout << name << " " << (Handoff::valid(h, arena) ? "accepted" : "rejected") << "\n";
    }
    return 0;
}
namespace execution_fixture {
namespace execution = aurora::execution;
using U64 = std::uint64_t;
constexpr const char *statuses[] = {
    "exited", "fault", "watchdog", "missing", "malformed", "quota", "unavailable", "output_failed", "cancelled"};
constexpr const char *preparations[] = {"loaded", "refused", "service_lost"};
constexpr const char *steps[] = {"retired", "output", "request", "parked"};
constexpr const char *effects[] = {"success", "failed"};
constexpr const char *requests[] = {"ready", "cancelled", "service_lost", "pending", "cancel_requested"};
constexpr const char *finishes[] = {"complete", "output_failed", "cancelled", "service_lost", "cancel_requested"};
constexpr const char *cancels[] = {"settled", "draining", "service_lost"};
std::vector<std::vector<std::string>> script;
std::size_t cursor{};
std::string trace;
execution::Argument argument{};
execution::Lease lease{};
unsigned calls{}, expected_calls{}, preparation_reads{};
bool quiet = true, reenter = false, release_inside = false, authority_only = false, unsettled = false;
bool owner_reentry = false, finish_release = false;

template <std::size_t N> auto named(const std::string &text, const char *const (&names)[N]) -> U64 {
    for (std::size_t index = 0; index < N; ++index)
        if (text == names[index])
            return index;
    usage("unknown execution case word: " + text);
}
auto next(const char *operation, std::size_t fields) -> const std::vector<std::string> & {
    ++calls;
    if (cursor == script.size() || script[cursor].size() != fields || script[cursor][0] != operation)
        usage("unexpected execution effect: " + std::string{operation});
    if (!trace.empty())
        trace += ',';
    trace += operation;
    return script[cursor++];
}
class Transport {
public:
    class Binding {
    public:
        bool finished = false;
    };
    static auto prepare(Binding &) -> execution::Preparation;
    static auto advance(Binding &) -> execution::Observation;
    static auto output(Binding &) -> execution::Effect {
        return static_cast<execution::Effect>(named(next("output", 2)[1], effects));
    }
    static auto request(Binding &) -> execution::Request {
        return static_cast<execution::Request>(named(next("request", 2)[1], requests));
    }
    static auto cancel(Binding &) -> execution::Cancel {
        return static_cast<execution::Cancel>(named(next("cancel", 2)[1], cancels));
    }
    static auto finish(Binding &, execution::Finish) -> execution::Effect;
    static auto settled(const Binding &binding) -> bool {
        return binding.finished && !unsettled;
    }
};
class Platform {
public:
    static auto quiet() -> bool {
        return execution_fixture::quiet;
    }
    [[noreturn]] static auto fail() -> void {
        std::_Exit(calls == expected_calls ? 77 : 78);
    }
};
using Session = execution::Session<Transport, Platform>;
auto Transport::prepare(Binding &) -> execution::Preparation {
    if (reenter || release_inside || authority_only) {
        ++calls;
        if (reenter)
            static_cast<void>(Session::prepare(argument.grant, argument.generation));
        if (release_inside)
            Session::release(argument);
        return {execution::Prepared::refused, execution::Status::unavailable};
    }
    const auto &row = next("prepare", 3);
    return {static_cast<execution::Prepared>(named(row[1], preparations)),
            static_cast<execution::Status>(named(row[2], statuses))};
}
auto Transport::advance(Binding &) -> execution::Observation {
    if (owner_reentry) {
        ++calls;
        static_cast<void>(Session::preparation(lease.binding, lease.generation));
        usage("execution owner accepted reentry");
    }
    const auto &row = next("advance", 4);
    return {static_cast<execution::Step>(named(row[1], steps)),
            static_cast<execution::Status>(named(row[2], statuses)),
            number(row[3])};
}
auto Transport::finish(Binding &binding, execution::Finish disposition) -> execution::Effect {
    if (authority_only) {
        ++calls;
        if (finish_release)
            Session::release(argument);
        binding.finished = true;
        return execution::Effect::success;
    }
    const auto &row = next("finish", 3);
    if (static_cast<U64>(disposition) != named(row[1], finishes))
        usage("unexpected execution finish disposition");
    trace += ':' + row[1];
    binding.finished = true;
    return static_cast<execution::Effect>(named(row[2], effects));
}
auto denial(const std::string &kind) -> void {
    const auto old = Session::open();
    Session::release(old);
    argument = Session::open();
    const auto child = fork();
    if (child < 0)
        usage("execution fixture fork failed");
    if (!child) {
        calls = expected_calls = 0;
        if (kind == "stale")
            static_cast<void>(Session::prepare(old.grant, old.generation));
        else if (kind == "forged")
            static_cast<void>(Session::prepare(reinterpret_cast<const void *>(1), argument.generation));
        else if (kind == "zero_generation")
            static_cast<void>(Session::prepare(argument.grant, 0));
        else if (kind == "duplicate_open")
            static_cast<void>(Session::open());
        else if (kind == "released") {
            Session::release(argument);
            static_cast<void>(Session::prepare(argument.grant, argument.generation));
        } else if (kind == "not_quiet") {
            quiet = false;
            static_cast<void>(Session::prepare(argument.grant, argument.generation));
        } else if (kind == "reenter" || kind == "release_inside") {
            expected_calls = 1;
            reenter = kind == "reenter";
            release_inside = kind == "release_inside";
            static_cast<void>(Session::prepare(argument.grant, argument.generation));
        } else {
            authority_only = true;
            lease = Session::prepare(argument.grant, argument.generation);
            expected_calls = 1;
            if (kind == "invalid_finish")
                static_cast<void>(Session::finish(lease.binding, lease.generation, 5));
            else if (kind == "issuer_as_owner")
                static_cast<void>(Session::advance(argument.grant, argument.generation));
            else if (kind == "forged_owner")
                static_cast<void>(Session::advance(reinterpret_cast<const void *>(1), lease.generation));
            else if (kind == "stale_owner")
                static_cast<void>(Session::preparation(lease.binding, old.generation));
            else if (kind == "release_live")
                Session::release(argument);
            else if (kind == "second_prepare")
                static_cast<void>(Session::prepare(argument.grant, argument.generation));
            else if (kind == "owner_reentry") {
                expected_calls = 2;
                owner_reentry = true;
                static_cast<void>(Session::advance(lease.binding, lease.generation));
            } else {
                expected_calls = 2;
                unsettled = kind == "unsettled_finish";
                finish_release = kind == "release_during_finish";
                static_cast<void>(Session::finish(lease.binding, lease.generation, 0));
                if (kind == "double_finish")
                    static_cast<void>(Session::finish(lease.binding, lease.generation, 0));
                else if (kind == "use_after_finish")
                    static_cast<void>(Session::preparation(lease.binding, lease.generation));
                else if (kind == "reissue_after_finish")
                    static_cast<void>(Session::prepare(argument.grant, argument.generation));
                else
                    usage("unknown execution denial");
            }
        }
        std::_Exit(1);
    }
    int status{};
    if (waitpid(child, &status, 0) != child || !WIFEXITED(status) || WEXITSTATUS(status) != 77)
        usage("execution authority denial failed");
    Session::release(argument);
}
} // namespace execution_fixture

extern "C" auto __au_runtime_process_execute_command(const aurora::execution::Argument *, aurora::execution::Result *)
    -> void;
extern "C" auto
__au_runtime_execution_prepare(const void *grant, std::uint64_t generation, aurora::execution::Lease *result) -> void {
    *result = execution_fixture::Session::prepare(grant, generation);
}
extern "C" auto __au_runtime_execution_preparation(const void *binding,
                                                   std::uint64_t generation,
                                                   aurora::execution::Preparation *result) -> void {
    if (execution_fixture::preparation_reads++ != 0)
        usage("command construction repeated its preparation observation");
    *result = execution_fixture::Session::preparation(binding, generation);
}
extern "C" auto __au_runtime_execution_advance(const void *grant,
                                               std::uint64_t generation,
                                               aurora::execution::Observation *result) -> void {
    if (execution_fixture::preparation_reads != 1)
        usage("command progressed before constructor preparation");
    *result = execution_fixture::Session::advance(grant, generation);
}
extern "C" auto __au_runtime_execution_output(const void *grant, std::uint64_t generation) -> std::uint64_t {
    if (execution_fixture::preparation_reads != 1)
        usage("command effect before constructor preparation");
    return execution_fixture::Session::output(grant, generation);
}
extern "C" auto __au_runtime_execution_request(const void *grant, std::uint64_t generation) -> std::uint64_t {
    if (execution_fixture::preparation_reads != 1)
        usage("command effect before constructor preparation");
    return execution_fixture::Session::request(grant, generation);
}
extern "C" auto __au_runtime_execution_cancel(const void *binding, std::uint64_t generation) -> std::uint64_t {
    if (execution_fixture::preparation_reads != 1)
        usage("command effect before constructor preparation");
    return execution_fixture::Session::cancel(binding, generation);
}
extern "C" auto __au_runtime_execution_finish(const void *grant, std::uint64_t generation, std::uint64_t disposition)
    -> std::uint64_t {
    if (execution_fixture::preparation_reads != 1)
        usage("command effect before constructor preparation");
    return execution_fixture::Session::finish(grant, generation, disposition);
}

class ExecutionCancelArgument final {
public:
    aurora::execution::Argument issuer;
    std::uint64_t point, padding = 0;
};
extern "C" auto __au_runtime_process_cancel_command(const ExecutionCancelArgument *, aurora::execution::Result *)
    -> void;

auto execution_mode(const char *cases) -> int {
    namespace fixture = execution_fixture;
    std::ifstream input{cases};
    if (!input)
        usage("cannot read execution cases");
    for (std::string line; std::getline(input, line);) {
        if (line.empty() || line.starts_with('#'))
            continue;
        std::istringstream row{line};
        std::string name, token;
        row >> name;
        fixture::script.clear();
        fixture::cursor = fixture::calls = fixture::preparation_reads = 0;
        fixture::trace.clear();
        while (row >> token) {
            std::vector<std::string> fields;
            std::istringstream part{token};
            for (std::string field; std::getline(part, field, ':');)
                fields.push_back(field);
            fixture::script.push_back(std::move(fields));
        }
        if (fixture::script.size() == 1 && fixture::script[0].size() == 2 && fixture::script[0][0] == "deny") {
            fixture::denial(fixture::script[0][1]);
            std::cout << name << " denied\n";
            continue;
        }
        fixture::argument = fixture::Session::open();
        aurora::execution::Result result;
        if (!fixture::script.empty() && fixture::script[0].size() == 2 && fixture::script[0][0] == "point") {
            const auto point = number(fixture::script[0][1]);
            fixture::script.erase(fixture::script.begin());
            const ExecutionCancelArgument arguments{fixture::argument, point};
            __au_runtime_process_cancel_command(&arguments, &result);
        } else {
            __au_runtime_process_execute_command(&fixture::argument, &result);
        }
        fixture::Session::release(fixture::argument);
        if (fixture::preparation_reads != 1 || fixture::cursor != fixture::script.size() ||
            static_cast<std::uint64_t>(result.status) >= std::size(fixture::statuses))
            usage("execution script not consumed or invalid result");
        std::cout << name << ' ' << fixture::statuses[static_cast<std::size_t>(result.status)] << ':' << result.value
                  << ' ' << fixture::trace << '\n';
    }
    return 0;
}

namespace bootstrap_fixture {
namespace bootstrap = aurora::bootstrap;
using U64 = std::uint64_t;
constexpr const char *effects[] = {"staged", "failed"};
constexpr const char *progress[] = {"pending", "complete", "failed"};
constexpr const char *finishes[] = {"publish", "abandon"};
constexpr const char *results[] = {"ready", "unavailable"};
std::vector<std::vector<std::string>> script;
std::size_t cursor{};
std::string trace;
bootstrap::Argument argument{};
bootstrap::Lease lease{};
unsigned calls{}, expected_calls{};
bool quiet = true, authority_only = false, reenter = false, release_inside = false;
bool owner_reentry = false, unsettled = false, finish_release = false;

auto next(const char *operation, std::size_t fields) -> const std::vector<std::string> & {
    ++calls;
    if (cursor == script.size() || script[cursor].size() != fields || script[cursor][0] != operation)
        usage("unexpected bootstrap effect: " + std::string{operation});
    if (!trace.empty())
        trace += ',';
    trace += operation;
    return script[cursor++];
}
class Transport {
public:
    class Binding {
    public:
        bool finished = false;
    };
    static auto begin(Binding &) -> bootstrap::Preparation;
    static auto begin_volume(Binding &) -> bootstrap::Effect {
        return static_cast<bootstrap::Effect>(execution_fixture::named(next("volume", 2)[1], effects));
    }
    static auto copy_volume(Binding &, U64 offset) -> bootstrap::Effect {
        const auto &row = next("copy", 3);
        if (offset != number(row[1]))
            usage("unexpected bootstrap copy cursor");
        trace += ':' + row[1];
        return static_cast<bootstrap::Effect>(execution_fixture::named(row[2], effects));
    }
    static auto seal_volume(Binding &) -> bootstrap::Effect {
        return static_cast<bootstrap::Effect>(execution_fixture::named(next("seal", 2)[1], effects));
    }
    static auto admit_storage(Binding &) -> bootstrap::Effect {
        return static_cast<bootstrap::Effect>(execution_fixture::named(next("storage", 2)[1], effects));
    }
    static auto advance(Binding &) -> bootstrap::Progress;
    static auto finish(Binding &, bootstrap::Finish) -> bootstrap::Result;
    static auto settled(const Binding &binding) -> bool {
        return binding.finished && !unsettled;
    }
};
class Platform {
public:
    static auto quiet() -> bool {
        return bootstrap_fixture::quiet;
    }
    [[noreturn]] static auto fail() -> void {
        std::_Exit(calls == expected_calls ? 77 : 78);
    }
};
using Session = bootstrap::Session<Transport, Platform>;
auto Transport::begin(Binding &) -> bootstrap::Preparation {
    if (reenter || release_inside || authority_only) {
        ++calls;
        if (reenter)
            static_cast<void>(Session::begin(argument.grant, argument.generation));
        if (release_inside)
            Session::release(argument);
        return {0, 0, 1, 0};
    }
    const auto &row = next("begin", 5);
    const auto loaded = number(row[1]), storage = number(row[4]);
    if (loaded > 1 || storage > 1)
        usage("noncanonical bootstrap fixture boolean");
    return {loaded, number(row[2]), number(row[3]), storage};
}
auto Transport::advance(Binding &) -> bootstrap::Progress {
    if (owner_reentry) {
        ++calls;
        static_cast<void>(Session::preparation(lease.binding, lease.generation));
        usage("bootstrap owner accepted reentry");
    }
    return static_cast<bootstrap::Progress>(execution_fixture::named(next("advance", 2)[1], progress));
}
auto Transport::finish(Binding &binding, bootstrap::Finish disposition) -> bootstrap::Result {
    if (authority_only) {
        ++calls;
        if (finish_release)
            Session::release(argument);
        binding.finished = true;
        return bootstrap::Result::unavailable;
    }
    const auto &row = next("finish", 3);
    if (static_cast<U64>(disposition) != execution_fixture::named(row[1], finishes))
        usage("unexpected bootstrap disposition");
    trace += ':' + row[1];
    binding.finished = true;
    return static_cast<bootstrap::Result>(execution_fixture::named(row[2], results));
}
auto denial(const std::string &kind) -> void {
    const auto old = Session::open();
    Session::release(old);
    argument = Session::open();
    const auto child = fork();
    if (child < 0)
        usage("bootstrap fixture fork failed");
    if (!child) {
        calls = expected_calls = 0;
        if (kind == "stale")
            static_cast<void>(Session::begin(old.grant, old.generation));
        else if (kind == "forged")
            static_cast<void>(Session::begin(reinterpret_cast<const void *>(1), argument.generation));
        else if (kind == "zero_generation")
            static_cast<void>(Session::begin(argument.grant, 0));
        else if (kind == "duplicate_open")
            static_cast<void>(Session::open());
        else if (kind == "released") {
            Session::release(argument);
            static_cast<void>(Session::begin(argument.grant, argument.generation));
        } else if (kind == "not_quiet") {
            quiet = false;
            static_cast<void>(Session::begin(argument.grant, argument.generation));
        } else if (kind == "cross_issuer" || kind == "cross_lease") {
            const auto foreign = execution_fixture::Session::open();
            if (kind == "cross_issuer")
                static_cast<void>(Session::begin(foreign.grant, foreign.generation));
            execution_fixture::authority_only = true;
            const auto owner = execution_fixture::Session::prepare(foreign.grant, foreign.generation);
            static_cast<void>(Session::advance(owner.binding, owner.generation));
        } else if (kind == "reenter" || kind == "release_inside") {
            expected_calls = 1;
            reenter = kind == "reenter";
            release_inside = kind == "release_inside";
            static_cast<void>(Session::begin(argument.grant, argument.generation));
        } else {
            authority_only = true;
            lease = Session::begin(argument.grant, argument.generation);
            expected_calls = 1;
            if (kind == "invalid_finish")
                static_cast<void>(Session::finish(lease.binding, lease.generation, 2));
            else if (kind == "issuer_as_owner")
                static_cast<void>(Session::advance(argument.grant, argument.generation));
            else if (kind == "forged_owner")
                static_cast<void>(Session::advance(reinterpret_cast<const void *>(1), lease.generation));
            else if (kind == "stale_owner")
                static_cast<void>(Session::preparation(lease.binding, old.generation));
            else if (kind == "reverse_cross_lease") {
                execution_fixture::calls = execution_fixture::expected_calls = 0;
                static_cast<void>(execution_fixture::Session::preparation(lease.binding, lease.generation));
            } else if (kind == "release_live")
                Session::release(argument);
            else if (kind == "second_begin")
                static_cast<void>(Session::begin(argument.grant, argument.generation));
            else if (kind == "owner_reentry") {
                expected_calls = 2;
                owner_reentry = true;
                static_cast<void>(Session::advance(lease.binding, lease.generation));
            } else {
                expected_calls = 2;
                unsettled = kind == "unsettled_finish";
                finish_release = kind == "release_during_finish";
                static_cast<void>(Session::finish(lease.binding, lease.generation, 1));
                if (kind == "double_finish")
                    static_cast<void>(Session::finish(lease.binding, lease.generation, 1));
                else if (kind == "use_after_finish")
                    static_cast<void>(Session::preparation(lease.binding, lease.generation));
                else if (kind == "reissue_after_finish")
                    static_cast<void>(Session::begin(argument.grant, argument.generation));
                else
                    usage("unknown bootstrap denial");
            }
        }
        std::_Exit(1);
    }
    int status{};
    if (waitpid(child, &status, 0) != child || !WIFEXITED(status) || WEXITSTATUS(status) != 77)
        usage("bootstrap authority denial failed");
    Session::release(argument);
}
} // namespace bootstrap_fixture

extern "C" auto __au_runtime_process_bootstrap_service(const aurora::bootstrap::Argument *) -> std::uint64_t;
extern "C" auto __au_runtime_service_bootstrap_begin(const void *grant,
                                                     std::uint64_t generation,
                                                     aurora::bootstrap::Lease *result) -> void {
    *result = bootstrap_fixture::Session::begin(grant, generation);
}
extern "C" auto __au_runtime_service_bootstrap_preparation(const void *binding,
                                                           std::uint64_t generation,
                                                           aurora::bootstrap::Preparation *result) -> void {
    *result = bootstrap_fixture::Session::preparation(binding, generation);
}
extern "C" auto __au_runtime_service_bootstrap_begin_volume(const void *binding, std::uint64_t generation)
    -> std::uint64_t {
    return bootstrap_fixture::Session::begin_volume(binding, generation);
}
extern "C" auto __au_runtime_service_bootstrap_copy_volume(const void *binding,
                                                           std::uint64_t generation,
                                                           std::uint64_t offset) -> std::uint64_t {
    return bootstrap_fixture::Session::copy_volume(binding, generation, offset);
}
extern "C" auto __au_runtime_service_bootstrap_seal_volume(const void *binding, std::uint64_t generation)
    -> std::uint64_t {
    return bootstrap_fixture::Session::seal_volume(binding, generation);
}
extern "C" auto __au_runtime_service_bootstrap_admit_storage(const void *binding, std::uint64_t generation)
    -> std::uint64_t {
    return bootstrap_fixture::Session::admit_storage(binding, generation);
}
extern "C" auto __au_runtime_service_bootstrap_advance(const void *binding, std::uint64_t generation) -> std::uint64_t {
    return bootstrap_fixture::Session::advance(binding, generation);
}
extern "C" auto __au_runtime_service_bootstrap_finish(const void *binding,
                                                      std::uint64_t generation,
                                                      std::uint64_t disposition) -> std::uint64_t {
    return bootstrap_fixture::Session::finish(binding, generation, disposition);
}

auto bootstrap_mode(const char *cases) -> int {
    namespace fixture = bootstrap_fixture;
    std::ifstream input{cases};
    if (!input)
        usage("cannot read bootstrap cases");
    for (std::string line; std::getline(input, line);) {
        if (line.empty() || line.starts_with('#'))
            continue;
        std::istringstream row{line};
        std::string name, token;
        row >> name;
        fixture::script.clear();
        fixture::cursor = fixture::calls = 0;
        fixture::trace.clear();
        while (row >> token) {
            std::vector<std::string> fields;
            std::istringstream part{token};
            for (std::string field; std::getline(part, field, ':');)
                fields.push_back(field);
            fixture::script.push_back(std::move(fields));
        }
        if (fixture::script.size() == 1 && fixture::script[0].size() == 2 && fixture::script[0][0] == "deny") {
            fixture::denial(fixture::script[0][1]);
            std::cout << name << " denied\n";
            continue;
        }
        if (fixture::script.size() == 1 && fixture::script[0].size() == 5 && fixture::script[0][0] == "reply") {
            const auto &fields = fixture::script[0];
            const auto operation = number(fields[1]), length = number(fields[2]);
            const auto offset = number(fields[3]), value = number(fields[4]);
            std::array<std::byte, 65> bytes{};
            if (length > bytes.size() || offset >= bytes.size() || value > 255)
                usage("invalid bootstrap reply test input");
            bytes[offset] = std::byte(value);
            const auto result = aurora::bootstrap::inspect_reply(operation, {bytes.data(), length});
            constexpr const char *names[] = {"invalid", "ready", "disk_unavailable"};
            std::cout << name << ' ' << names[static_cast<std::size_t>(result)] << '\n';
            continue;
        }
        fixture::argument = fixture::Session::open();
        const auto result = __au_runtime_process_bootstrap_service(&fixture::argument);
        fixture::Session::release(fixture::argument);
        if (fixture::cursor != fixture::script.size() || result >= std::size(fixture::results))
            usage("bootstrap script not consumed or invalid result");
        std::cout << name << ' ' << fixture::results[result] << ' ' << fixture::trace << '\n';
    }
    return 0;
}

namespace budget_fixture {
using U64 = std::uint64_t;
bool excluded = true, reenter = false;
class Platform {
public:
    static auto quiet() -> bool;
    [[noreturn]] static auto fail() -> void {
        std::_Exit(77);
    }
};
using Root = aurora::budget::Root<Platform>;
Root *entered = nullptr;
auto Platform::quiet() -> bool {
    if (reenter) {
        reenter = false;
        if (!entered)
            usage("missing budget reentry target");
        static_cast<void>(entered->used());
    }
    return excluded;
}
auto charge_name(aurora::budget::Charge charge) -> const char * {
    switch (charge) {
    case aurora::budget::Charge::rejected:
        return "rejected";
    case aurora::budget::Charge::available:
        return "available";
    case aurora::budget::Charge::exhausted:
        return "exhausted";
    }
    usage("invalid source budget charge result");
}
auto denial(const std::string &kind) -> void {
    const auto child = fork();
    if (child < 0)
        usage("budget fixture fork failed");
    if (!child) {
        Root root;
        if (kind == "before_create") {
            static_cast<void>(root.available());
        } else {
            if (!root.create(3, 0))
                std::_Exit(1);
            if (kind == "stopped") {
                root.stop();
                static_cast<void>(root.used());
            } else if (kind == "not_excluded") {
                excluded = false;
                static_cast<void>(root.available());
            } else if (kind == "reentrant") {
                entered = &root;
                reenter = true;
                static_cast<void>(root.used());
            } else
                usage("unknown budget denial");
        }
        std::_Exit(1);
    }
    int status{};
    if (waitpid(child, &status, 0) != child || !WIFEXITED(status) || WEXITSTATUS(status) != 77)
        usage("budget lifetime denial failed");
}
} // namespace budget_fixture

auto budget_mode(const char *cases) -> int {
    std::ifstream input{cases};
    if (!input)
        usage("cannot read budget cases");
    for (std::string line; std::getline(input, line);) {
        if (line.empty() || line.starts_with('#'))
            continue;
        std::istringstream row{line};
        std::string name, token;
        row >> name;
        budget_fixture::Root first, second;
        std::array<budget_fixture::Root *, 2> roots{&first, &second};
        std::array<bool, 2> live{};
        std::ostringstream result;
        result << name;
        while (row >> token) {
            std::vector<std::string> fields;
            std::istringstream part{token};
            for (std::string field; std::getline(part, field, ':');)
                fields.push_back(field);
            if (fields.size() == 2 && fields[0] == "deny") {
                budget_fixture::denial(fields[1]);
                result << " denied";
                continue;
            }
            if (fields.size() < 2 || (fields[0] != "a" && fields[0] != "b"))
                usage("invalid budget operation");
            const auto index = fields[0] == "a" ? 0 : 1;
            auto &root = *roots[index];
            const auto &operation = fields[1];
            if (operation == "observe" && fields.size() == 2) {
                result << ' ' << fields[0] << '=' << root.available() << ':' << root.quantum() << ':' << root.used();
                continue;
            }
            result << ' ' << fields[0] << ':' << operation << '=';
            if (operation == "create" && fields.size() == 4) {
                live[index] = root.create(number(fields[2]), number(fields[3]));
                result << live[index];
            } else if (operation == "reset" && fields.size() == 4) {
                result << root.reset(number(fields[2]), number(fields[3]));
            } else if (operation == "configure" && fields.size() == 4) {
                result << root.configure_next(number(fields[2]), number(fields[3]));
            } else if (operation == "restart" && fields.size() == 2) {
                result << root.restart();
            } else if (operation == "charge" && fields.size() == 3) {
                result << budget_fixture::charge_name(root.charge(number(fields[2])));
            } else if (operation == "progress" && fields.size() == 3) {
                result << budget_fixture::charge_name(root.progress(number(fields[2])));
            } else if (operation == "stop" && fields.size() == 2) {
                root.stop();
                live[index] = false;
                result << '1';
            } else
                usage("invalid budget operation arguments");
        }
        for (std::size_t index = 0; index < roots.size(); ++index)
            if (live[index])
                roots[index]->stop();
        std::cout << result.str() << '\n';
    }
    return 0;
}

namespace service_fixture {
namespace service = aurora::service;
using U64 = std::uint64_t;
constexpr const char *actions[] = {"refused", "reuse", "start"};
constexpr const char *phases[] = {"absent", "starting", "ready", "stopping", "retiring"};
constexpr const char *reasons[] = {"none",
                                   "invalid_reply",
                                   "consumer_rejected",
                                   "exited",
                                   "watchdog",
                                   "invalid_call",
                                   "fault",
                                   "caller_expired",
                                   "unavailable",
                                   "shutdown"};
bool excluded = true, reenter = false;
class Platform {
public:
    static auto quiet() -> bool;
    [[noreturn]] static auto fail() -> void {
        std::_Exit(77);
    }
};
using Root = service::Root<Platform>;
Root *entered = nullptr;
auto Platform::quiet() -> bool {
    if (reenter) {
        reenter = false;
        if (!entered)
            usage("missing service reentry target");
        static_cast<void>(entered->generation());
    }
    return excluded;
}
template <class Value, std::size_t N> auto word(Value value, const char *const (&names)[N]) -> const char * {
    const auto index = static_cast<U64>(value);
    if (index >= N)
        usage("invalid source service observation");
    return names[index];
}
auto reason(const std::string &name) -> service::Reason {
    for (std::size_t index = 0; index < std::size(reasons); ++index)
        if (name == reasons[index])
            return static_cast<service::Reason>(index);
    return static_cast<service::Reason>(number(name));
}
auto view(Root &root, std::ostream &result) -> void {
    result << " view=" << word(root.phase(), phases) << ':' << root.generation() << ':' << root.disk_ready(0) << ':'
           << word(root.reason(), reasons) << ':' << root.detail();
}
auto denial(const std::string &kind) -> void {
    const auto child = fork();
    if (child < 0)
        usage("service fixture fork failed");
    if (!child) {
        Root root;
        if (kind == "before_create") {
            static_cast<void>(root.open_operation());
        } else {
            root.create();
            if (kind == "duplicate_create") {
                root.create();
            } else if (kind == "not_excluded") {
                excluded = false;
                static_cast<void>(root.generation());
            } else if (kind == "reentrant") {
                entered = &root;
                reenter = true;
                static_cast<void>(root.generation());
            } else
                usage("unknown service denial");
        }
        std::_Exit(1);
    }
    int status{};
    if (waitpid(child, &status, 0) != child || !WIFEXITED(status) || WEXITSTATUS(status) != 77)
        usage("service root denial failed");
}
extern "C" auto __au_runtime_service_saturation_create(void *) -> void;
auto saturation(std::ostream &result) -> void {
    // Complete source construction, no private field reads or production hook.
    // This local root is policy data, not bound to a process or endpoint.
    alignas(16) std::array<std::byte, 128> storage{};
    auto *root = storage.data();
    constexpr auto maximum = std::numeric_limits<U64>::max();
    __au_runtime_service_saturation_create(root);
    result << " open=" << service::__au_runtime_service_open_operation(root)
           << " admit=" << word(service::__au_runtime_service_admit(root, 0, true), actions)
           << " generation=" << service::__au_runtime_service_generation(root)
           << " ready=" << service::__au_runtime_service_mark_ready(root, maximum, true)
           << " admit=" << word(service::__au_runtime_service_admit(root, 0, true), actions)
           << " close=" << service::__au_runtime_service_close_operation(root)
           << " open=" << service::__au_runtime_service_open_operation(root)
           << " admit=" << word(service::__au_runtime_service_admit(root, maximum, false), actions)
           << " loss=" << service::__au_runtime_service_lose(root, maximum, service::Reason::fault, 14)
           << " clean=" << service::__au_runtime_service_cleaned(root, maximum)
           << " close=" << service::__au_runtime_service_close_operation(root)
           << " open=" << service::__au_runtime_service_open_operation(root)
           << " admit=" << word(service::__au_runtime_service_admit(root, 0, true), actions)
           << " view=" << word(service::__au_runtime_service_phase(root), phases) << ':'
           << service::__au_runtime_service_generation(root) << ':' << service::__au_runtime_service_disk_ready(root, 0)
           << ':' << word(service::__au_runtime_service_reason(root), reasons) << ':'
           << service::__au_runtime_service_detail(root)
           << " close=" << service::__au_runtime_service_close_operation(root);
}
} // namespace service_fixture

auto service_incarnation_mode(const char *cases) -> int {
    namespace fixture = service_fixture;
    std::ifstream input{cases};
    if (!input)
        usage("cannot read service-incarnation cases");
    for (std::string line; std::getline(input, line);) {
        if (line.empty() || line.starts_with('#'))
            continue;
        std::istringstream row{line};
        std::string name, token;
        row >> name;
        std::ostringstream result;
        result << name;
        fixture::Root root;
        root.create();
        while (row >> token) {
            std::vector<std::string> fields;
            std::istringstream part{token};
            for (std::string field; std::getline(part, field, ':');)
                fields.push_back(field);
            const auto &operation = fields[0];
            if (operation == "deny" && fields.size() == 2) {
                fixture::denial(fields[1]);
                result << " denied";
            } else if (operation == "saturation" && fields.size() == 1) {
                fixture::saturation(result);
            } else if (operation == "view" && fields.size() == 1) {
                fixture::view(root, result);
            } else if (operation == "open" && fields.size() == 1) {
                result << " open=" << root.open_operation();
            } else if (operation == "close" && fields.size() == 1) {
                result << " close=" << root.close_operation();
            } else if (operation == "admit" && fields.size() == 3) {
                const auto permit = number(fields[2]);
                if (permit > 1)
                    usage("invalid service fixture permit flag");
                result << " admit=" << fixture::word(root.admit(number(fields[1]), permit != 0), fixture::actions);
            } else if (operation == "ready" && fields.size() == 3) {
                const auto disk = number(fields[2]);
                if (disk > 1)
                    usage("invalid service fixture disk flag");
                result << " ready=" << root.mark_ready(number(fields[1]), disk != 0);
            } else if (operation == "shutdown" && fields.size() == 2) {
                result << " shutdown=" << root.begin_shutdown(number(fields[1]));
            } else if (operation == "loss" && fields.size() == 4) {
                result << " loss=" << root.lose(number(fields[1]), fixture::reason(fields[2]), number(fields[3]));
            } else if (operation == "exit" && fields.size() == 2) {
                result << " exit=" << root.normal_exit(number(fields[1]));
            } else if (operation == "clean" && fields.size() == 2) {
                result << " clean=" << root.cleaned(number(fields[1]));
            } else if (operation == "disk" && fields.size() == 2) {
                result << " disk=" << root.disk_ready(number(fields[1]));
            } else
                usage("invalid service-incarnation operation");
        }
        std::cout << result.str() << '\n';
    }
    return 0;
}

#include "kernel-process-resident.hpp"

} // namespace

auto main(int argc, char **argv) -> int {
    if (argc == 3 && std::string{argv[1]} == "resident")
        return resident_mode(argv[2]);
    if (argc == 3 && std::string{argv[1]} == "bootstrap")
        return bootstrap_mode(argv[2]);
    if (argc == 3 && std::string{argv[1]} == "service-incarnation")
        return service_incarnation_mode(argv[2]);
    if (argc == 3 && std::string{argv[1]} == "budget")
        return budget_mode(argv[2]);
    if (argc == 3 && std::string{argv[1]} == "execution")
        return execution_mode(argv[2]);
    if (argc == 3 && std::string{argv[1]} == "handoff")
        return handoff_mode(argv[2]);
    if (argc == 3 && std::string{argv[1]} == "frames")
        return frames_mode(argv[2]);
    if (argc == 3 && std::string{argv[1]} == "volumes")
        return volumes_mode(argv[2]);
    if (argc == 3 && std::string{argv[1]} == "events")
        return events_mode(argv[2]);
    if (argc == 4 && std::string{argv[1]} == "files")
        return files_mode(argv[2], argv[3]);
    usage("usage: kernel-process frames CASES | volumes BUNDLE | events CASES | files VOLUME CASES | budget CASES");
}
