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
// stdout is compared with the golden file beside the cases.
#include "../kernel/uefi/frames.hpp"
#include "../kernel/uefi/kernel-space.hpp"
#include <cstdio>
#include <fstream>
#include <iostream>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

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
constexpr const char *call_names[] = {"invalid", "exit", "print", "read", "map", "remap", "unmap"};
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

auto run_operations(const MapCase &item, frames::Table &table) -> void {
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
    run_operations(item, table);
}

auto number(const std::string &text) -> U64 {
    std::size_t used = 0;
    const auto value = std::stoull(text, &used, 0);
    if (used != text.size())
        usage("bad number: " + text);
    return value;
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
        if (verb == "case") {
            if (current || rest.size() != 1)
                usage("unterminated or unnamed case");
            current = MapCase{};
            current->name = rest[0];
        } else if (!current) {
            usage("row outside a case: " + line);
        } else if (verb == "end") {
            run_map(*current);
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
        } else if (verb == "call" && values.size() == 4) {
            const auto call = process::call(values[0], values[1], values[2], values[3]);
            std::cout << text << " -> ";
            if (!call)
                std::cout << "malformed\n";
            else
                std::cout << call_names[call->action] << " value=" << hex(call->value) << " length=" << call->length
                          << " base=" << hex(call->base) << "\n";
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
} // namespace

auto main(int argc, char **argv) -> int {
    if (argc == 3 && std::string{argv[1]} == "frames")
        return frames_mode(argv[2]);
    if (argc == 3 && std::string{argv[1]} == "volumes")
        return volumes_mode(argv[2]);
    if (argc == 3 && std::string{argv[1]} == "events")
        return events_mode(argv[2]);
    usage("usage: kernel-process frames CASES | volumes BUNDLE | events CASES");
}
