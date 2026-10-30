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
#include "../kernel/uefi/frames.hpp"
#include "../kernel/uefi/kernel-space.hpp"
#include "kernel-process-files.hpp"
#include <algorithm>
#include <cstring>
#include <cstdio>
#include <fstream>
#include <iterator>
#include <iostream>
#include <memory>
#include <sstream>
#include <string>
#include <vector>
#include <sys/wait.h>
#include <unistd.h>

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
    "exited", "fault", "watchdog", "missing", "malformed", "quota", "unavailable", "output_failed"};
constexpr const char *preparations[] = {"loaded", "refused", "service_lost"};
constexpr const char *steps[] = {"retired", "output", "request", "parked"};
constexpr const char *effects[] = {"success", "failed"};
constexpr const char *requests[] = {"ready", "cancelled", "service_lost", "pending"};
constexpr const char *finishes[] = {"complete", "output_failed", "cancelled", "service_lost"};
std::vector<std::vector<std::string>> script;
std::size_t cursor{};
std::string trace;
execution::Argument argument{};
unsigned calls{}, expected_calls{};
bool quiet = true, reenter = false, release_inside = false;

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
    static auto prepare() -> execution::Preparation;
    static auto advance() -> execution::Observation {
        const auto &row = next("advance", 4);
        return {static_cast<execution::Step>(named(row[1], steps)),
                static_cast<execution::Status>(named(row[2], statuses)),
                number(row[3])};
    }
    static auto output() -> execution::Effect {
        return static_cast<execution::Effect>(named(next("output", 2)[1], effects));
    }
    static auto request() -> execution::Request {
        return static_cast<execution::Request>(named(next("request", 2)[1], requests));
    }
    static auto finish(execution::Finish disposition) -> execution::Effect {
        const auto &row = next("finish", 3);
        if (static_cast<U64>(disposition) != named(row[1], finishes))
            usage("unexpected execution finish disposition");
        trace += ':' + row[1];
        return static_cast<execution::Effect>(named(row[2], effects));
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
auto Transport::prepare() -> execution::Preparation {
    if (reenter || release_inside) {
        ++calls;
        if (reenter)
            static_cast<void>(Session::prepare(argument.grant, argument.generation));
        else
            Session::release(argument);
        usage("execution adapter accepted reentry");
    }
    const auto &row = next("prepare", 4);
    const auto required = number(row[3]);
    if (required > 1)
        usage("invalid fixture finish flag");
    return {static_cast<execution::Prepared>(named(row[1], preparations)),
            static_cast<execution::Status>(named(row[2], statuses)),
            required};
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
        } else if (kind == "invalid_finish")
            static_cast<void>(Session::finish(argument.grant, argument.generation, 4));
        else if (kind == "reenter" || kind == "release_inside") {
            expected_calls = 1;
            reenter = kind == "reenter";
            release_inside = kind == "release_inside";
            static_cast<void>(Session::prepare(argument.grant, argument.generation));
        } else
            usage("unknown execution denial");
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
extern "C" auto __au_runtime_execution_prepare(const void *grant,
                                               std::uint64_t generation,
                                               aurora::execution::Preparation *result) -> void {
    *result = execution_fixture::Session::prepare(grant, generation);
}
extern "C" auto __au_runtime_execution_advance(const void *grant,
                                               std::uint64_t generation,
                                               aurora::execution::Observation *result) -> void {
    *result = execution_fixture::Session::advance(grant, generation);
}
extern "C" auto __au_runtime_execution_output(const void *grant, std::uint64_t generation) -> std::uint64_t {
    return execution_fixture::Session::output(grant, generation);
}
extern "C" auto __au_runtime_execution_request(const void *grant, std::uint64_t generation) -> std::uint64_t {
    return execution_fixture::Session::request(grant, generation);
}
extern "C" auto __au_runtime_execution_finish(const void *grant, std::uint64_t generation, std::uint64_t disposition)
    -> std::uint64_t {
    return execution_fixture::Session::finish(grant, generation, disposition);
}

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
        fixture::argument = fixture::Session::open();
        aurora::execution::Result result;
        __au_runtime_process_execute_command(&fixture::argument, &result);
        fixture::Session::release(fixture::argument);
        if (fixture::cursor != fixture::script.size() ||
            static_cast<std::uint64_t>(result.status) >= std::size(fixture::statuses))
            usage("execution script not consumed or invalid result");
        std::cout << name << ' ' << fixture::statuses[static_cast<std::size_t>(result.status)] << ':' << result.value
                  << ' ' << fixture::trace << '\n';
    }
    return 0;
}

} // namespace

auto main(int argc, char **argv) -> int {
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
    usage("usage: kernel-process frames CASES | volumes BUNDLE | events CASES | files VOLUME CASES");
}
