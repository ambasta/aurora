// One driver: real emitter input, malformed ELF data, allocation failure, and
// semantic comparison against GNU ld -r. ELF decoding here is test observation,
// not a second composer or a production admission path.
#include "../tools/air_cases.hpp"
#include "hosted_private_object.hpp"
#include "hosted_frontend_abi.hpp"
#include "ir_verify.hpp"
#include "x86.hpp"
#include <algorithm>
#include <cstdlib>
#include <cstring>
#include <elf.h>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <set>
#include <sstream>
#include <tuple>

using namespace aurora;
namespace {
void require(bool condition, const std::string &message) {
    if (!condition)
        throw Error(message);
}
std::string readFile(const std::string &path) {
    std::ifstream input(path, std::ios::binary);
    require(bool(input), "cannot open fixture " + path);
    return {std::istreambuf_iterator<char>(input), {}};
}
void writeFile(const std::string &path, std::string_view bytes) {
    std::ofstream output(path, std::ios::binary);
    output.write(bytes.data(), bytes.size());
    require(bool(output), "cannot write fixture " + path);
}
template <class T> T read(std::string_view bytes, std::size_t offset) {
    require(offset <= bytes.size() && sizeof(T) <= bytes.size() - offset, "fixture ELF range");
    T result;
    std::memcpy(&result, bytes.data() + offset, sizeof(T));
    return result;
}
class Elf {
    std::string_view bytes;

public:
    explicit Elf(std::string_view input) : bytes(input) {
    }
    Elf64_Ehdr header() const {
        return read<Elf64_Ehdr>(bytes, 0);
    }
    Elf64_Shdr section(std::size_t index) const {
        require(index < header().e_shnum, "fixture section index");
        return read<Elf64_Shdr>(bytes, header().e_shoff + index * sizeof(Elf64_Shdr));
    }
    std::string_view payload(Elf64_Shdr section) const {
        require(section.sh_offset <= bytes.size() && section.sh_size <= bytes.size() - section.sh_offset,
                "fixture section range");
        return bytes.substr(section.sh_offset, section.sh_size);
    }
    std::string name(Elf64_Shdr strings, std::size_t offset) const {
        const auto text = payload(strings);
        require(offset < text.size(), "fixture string range");
        const auto end = text.find('\0', offset);
        require(end != text.npos, "fixture string terminator");
        return std::string(text.substr(offset, end - offset));
    }
    std::string sectionName(std::size_t index) const {
        return index == SHN_UNDEF ? "UND" : name(section(header().e_shstrndx), section(index).sh_name);
    }
    std::size_t sectionIndex(const std::string &wanted) const {
        for (std::size_t index = 1; index < header().e_shnum; ++index)
            if (sectionName(index) == wanted)
                return index;
        throw Error("missing fixture section " + wanted);
    }
    Elf64_Shdr section(const std::string &wanted) const {
        return section(sectionIndex(wanted));
    }
    Elf64_Sym symbol(std::size_t index) const {
        return read<Elf64_Sym>(payload(section(".symtab")), index * sizeof(Elf64_Sym));
    }
    std::string symbolName(Elf64_Sym symbol) const {
        return name(section(".strtab"), symbol.st_name);
    }
    std::size_t symbolIndex(const std::string &wanted) const {
        for (std::size_t index = 1; index < section(".symtab").sh_size / sizeof(Elf64_Sym); ++index)
            if (symbolName(symbol(index)) == wanted)
                return index;
        throw Error("missing fixture symbol " + wanted);
    }
    auto symbols() const {
        using Value = std::tuple<unsigned, unsigned, std::string, std::uint64_t, std::uint64_t>;
        std::map<std::string, Value> result;
        for (std::size_t index = 1; index < section(".symtab").sh_size / sizeof(Elf64_Sym); ++index) {
            const auto entry = symbol(index);
            if (ELF64_ST_TYPE(entry.st_info) == STT_SECTION || ELF64_ST_TYPE(entry.st_info) == STT_FILE)
                continue;
            require(
                result
                    .emplace(
                        symbolName(entry),
                        Value{
                            entry.st_info, entry.st_other, sectionName(entry.st_shndx), entry.st_value, entry.st_size})
                    .second,
                "duplicate observed symbol");
        }
        return result;
    }
    auto relocations() const {
        using Value = std::tuple<std::uint64_t, unsigned, std::string, std::uint64_t>;
        std::multiset<Value> result;
        const auto records = payload(section(".rela.text"));
        for (std::size_t offset = 0; offset < records.size(); offset += sizeof(Elf64_Rela)) {
            const auto entry = read<Elf64_Rela>(records, offset);
            const auto target = symbol(ELF64_R_SYM(entry.r_info));
            // GNU may replace a local symbol with its section symbol and fold
            // st_value into the addend. Compare the resulting symbolic term.
            const auto identity =
                target.st_shndx == SHN_UNDEF ? "UND:" + symbolName(target) : sectionName(target.st_shndx);
            result.emplace(
                entry.r_offset, ELF64_R_TYPE(entry.r_info), identity, target.st_value + std::uint64_t(entry.r_addend));
        }
        return result;
    }
};
void compare(const std::string &source, const std::string &actual, const std::string &reference) {
    const Elf before(source), composed(actual), gnu(reference);
    require(composed.header().e_shnum == 8, "composition changed the fixed eight-section output");
    require(composed.payload(composed.section(".text")) == gnu.payload(gnu.section(".text")), "GNU text differs");
    require(composed.payload(composed.section(".rodata")) == gnu.payload(gnu.section(".rodata")),
            "GNU readonly data differs");
    require(composed.symbols() == gnu.symbols(), "GNU normalized symbols differ");
    require(composed.relocations() == gnu.relocations(), "GNU normalized relocations differ");
    for (const auto *section : {".symtab", ".rela.text", ".strtab"}) {
        const auto original = before.payload(before.section(section));
        require(composed.payload(composed.section(section)).starts_with(original),
                std::string("source indices or bytes changed in ") + section);
    }
    require(before.section(".symtab").sh_info == composed.section(".symtab").sh_info,
            "source LOCAL symbol prefix changed");
    std::cout << "PASS private object normalized GNU text/data/symbols/relocations and source-index preservation\n";
}
void mutations(const std::string &source,
               const std::string &wrapper,
               const std::string &selected,
               const std::string &path) {
    std::istringstream cases(readFile(path));
    std::string line;
    std::size_t count = 0;
    while (std::getline(cases, line)) {
        if (line.empty() || line[0] == '#')
            continue;
        std::istringstream fields(line);
        std::string description, input, location, record, valueText, expected;
        std::size_t offset, width;
        require(bool(fields >> description >> input >> location >> record >> offset >> width >> valueText >> expected),
                "malformed private object case " + line);
        require(expected == "reject", "unknown private object expectation");
        auto changedSource = source, changedWrapper = wrapper, changedSelected = selected;
        auto &changed = input == "source" ? changedSource : input == "wrapper" ? changedWrapper : changedSelected;
        if (location == "selection") {
            changed = record == "empty"          ? ""
                      : record == "missing"      ? "object_missing\n"
                      : record == "duplicate"    ? selected + selected
                      : record == "unterminated" ? "object_loop"
                      : record == "unsorted"     ? "object_loop\nobject_literal\n"
                                                 : "object-loop\n";
        } else if (location == "truncate") {
            changed.resize(offset);
        } else if (location == "symbol-name") {
            const Elf elf(changed);
            const auto symbol = elf.symbol(elf.symbolIndex(record));
            const auto original = elf.symbolName(symbol);
            require(valueText.size() <= original.size(), "replacement name exceeds fixture symbol");
            const auto base = elf.section(".strtab").sh_offset + symbol.st_name;
            changed.replace(base, original.size(), valueText + std::string(original.size() - valueText.size(), '\0'));
        } else {
            const Elf elf(changed);
            const std::uint64_t value = valueText.starts_with("name:")
                                            ? elf.symbol(elf.symbolIndex(valueText.substr(5))).st_name
                                            : std::stoull(valueText);
            std::size_t base = 0;
            if (location == "section")
                base = elf.header().e_shoff + elf.sectionIndex(record) * sizeof(Elf64_Shdr);
            else if (location == "symbol")
                base = elf.section(".symtab").sh_offset + elf.symbolIndex(record) * sizeof(Elf64_Sym);
            else if (location == "payload")
                base = elf.section(record).sh_offset;
            else if (location == "payload-last") {
                base = elf.section(record).sh_offset + elf.section(record).sh_size - 1;
            } else
                require(location == "header", "unknown private object mutation");
            require(width <= 8 && base + offset + width <= changed.size(), "mutation out of fixture bounds");
            for (std::size_t byte = 0; byte < width; ++byte)
                changed[base + offset + byte] = static_cast<char>(value >> (byte * 8));
        }
        bool rejected = false;
        try {
            (void)composePrivateObject(changedSource, changedWrapper, changedSelected);
        } catch (const Error &) {
            rejected = true;
        }
        require(rejected, description + ": malformed private object accepted");
        ++count;
    }
    std::cout << "PASS private object " << count << " malformed input data cases\n";
}
void repeatedRun(const std::string &source, const std::string &wrapper, const std::string &selected) {
    hosted::bytes::Region region(64 * 1024 * 1024);
    require(region.is_open(), "repeated-run region allocation failed");
    hosted_abi::PrivateObjectRelease owner{};
    owner.region = region.id();
    hosted_abi::PrivateObjectCreate create{};
    create.region = region.id();
    auto *workspace = owner.workspace.storage.data();
    aurora_hosted_private_object_create(&create, workspace);
    hosted_abi::PrivateObjectRun input{};
    input.source.backing = source.data();
    input.source.length = source.size();
    input.wrapper.backing = wrapper.data();
    input.wrapper.length = wrapper.size();
    input.selected.backing = selected.data();
    input.selected.length = selected.size();
    const auto first = aurora_hosted_private_object_run(workspace, &input);
    input.source.length = 1; // A completed workspace cannot expose stale output on reuse.
    const auto again = aurora_hosted_private_object_run(workspace, &input);
    const auto size = aurora_hosted_private_object_size(workspace);
    hosted_abi::compiler_x86::EmitChunk chunk{};
    aurora_hosted_private_object_chunk(workspace, 0, &chunk);
    aurora_hosted_private_object_release(&owner);
    require(first == static_cast<std::int64_t>(hosted_abi::compiler_x86::EmitStatus::complete) &&
                again == static_cast<std::int64_t>(hosted_abi::compiler_x86::EmitStatus::invalid) && size == -1 &&
                chunk.byteCount == -1 && region.metrics().live_allocations == 0,
            "repeated run exposed sealed output or retained owners");
    std::cout << "PASS private object repeated run invalidates sealed output\n";
}
class AllocationFailure {
public:
    std::size_t calls = 0, fail = 0, live = 0;
    static void *allocate(void *opaque, std::size_t bytes) noexcept {
        auto &state = *static_cast<AllocationFailure *>(opaque);
        if (++state.calls == state.fail)
            return nullptr;
        auto *result = std::malloc(bytes);
        if (result)
            ++state.live;
        return result;
    }
    static void deallocate(void *opaque, void *address) noexcept {
        --static_cast<AllocationFailure *>(opaque)->live;
        std::free(address);
    }
    auto allocator() {
        return hosted::bytes::Allocator{this, allocate, deallocate};
    }
};
void allocationFailures(const std::string &source,
                        const std::string &wrapper,
                        const std::string &selected,
                        const std::string &expected) {
    AllocationFailure successful;
    require(composePrivateObject(source, wrapper, selected, successful.allocator()) == expected,
            "allocator transport changed output");
    require(successful.live == 0 && successful.calls > 0, "successful composition leaked allocation");
    for (std::size_t fail = 1; fail <= successful.calls; ++fail) {
        AllocationFailure failing;
        failing.fail = fail;
        bool rejected = false;
        try {
            (void)composePrivateObject(source, wrapper, selected, failing.allocator());
        } catch (const Error &error) {
            rejected = std::string(error.what()).find("allocation failed") != std::string::npos;
        }
        require(rejected && failing.live == 0, "allocation failure did not close all workspace owners");
    }
    std::cout << "PASS private object every allocation failure releases owners\n";
}
} // namespace
int main(int argc, char **argv) {
    try {
        if (argc == 5 && std::string_view(argv[1]) == "--compare") {
            compare(readFile(argv[2]), readFile(argv[3]), readFile(argv[4]));
        } else {
            require(argc == 5, "expected IR CASES WRAPPER OUTPUT-DIRECTORY or --compare SOURCE ACTUAL GNU");
            const auto module = validate(test::air::loadCase(argv[1], "native object values"));
            const auto source =
                X86Emitter{}.emit(module, SymbolBinding::Local, ReflectionEmission::Referenced, CodeEmission::Object);
            const auto wrapper = readFile(argv[3]);
            const std::string selected = "object_literal\nobject_loop\nobject_six_arguments\n";
            const auto composed = composePrivateObject(source, wrapper, selected);
            mutations(source, wrapper, selected, argv[2]);
            allocationFailures(source, wrapper, selected, composed);
            repeatedRun(source, wrapper, selected);
            const std::string directory = argv[4];
            writeFile(directory + "/source.o", source);
            writeFile(directory + "/composed.o", composed);
            writeFile(directory + "/selected", selected);
        }
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "FAIL private object: " << error.what() << '\n';
        return 1;
    }
}
