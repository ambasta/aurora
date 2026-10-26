// One driver: real emitter input, closed wrapper recipes, malformed data, and
// semantic comparison against GNU ld -r. ELF decoding here is test observation,
// not a second composer or a production admission path.
#include "../tools/air_cases.hpp"
#include "hosted_private_object.hpp"
#include "hosted_frontend_abi.hpp"
#include "ir_verify.hpp"
#include "x86.hpp"
#include <algorithm>
#include <array>
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
void compareWrapper(const std::string &actual, const std::string &reference) {
    const Elf wrapper(actual), gnu(reference);
    require(wrapper.header().e_shnum == 8 && wrapper.section(".symtab").sh_info == 1 &&
                wrapper.section(".rodata").sh_size == 0,
            "native wrapper changed its closed ELF profile");
    require(wrapper.payload(wrapper.section(".text")) == gnu.payload(gnu.section(".text")), "GNU wrapper text differs");
    require(wrapper.symbols() == gnu.symbols(), "GNU wrapper symbols differ");
    require(wrapper.relocations() == gnu.relocations(), "GNU wrapper relocations differ");
    for (std::size_t index = 1; index < wrapper.header().e_shnum; ++index)
        require((wrapper.section(index).sh_flags & SHF_WRITE) == 0, "native wrapper has writable section");
    require(wrapper.section(".note.GNU-stack").sh_flags == 0, "native wrapper requests executable stack");
    const auto relocations = wrapper.payload(wrapper.section(".rela.text"));
    std::size_t exports = 0;
    for (std::size_t index = 1; index < wrapper.section(".symtab").sh_size / sizeof(Elf64_Sym); ++index) {
        const auto symbol = wrapper.symbol(index);
        if (symbol.st_shndx == SHN_UNDEF)
            continue;
        require(symbol.st_info == ELF64_ST_INFO(STB_GLOBAL, STT_FUNC) && symbol.st_other == STV_HIDDEN,
                "native wrapper export is not a hidden global function");
        std::size_t found = 0;
        for (std::size_t offset = 0; offset < relocations.size(); offset += sizeof(Elf64_Rela)) {
            const auto relocation = read<Elf64_Rela>(relocations, offset);
            if (relocation.r_offset < symbol.st_value || relocation.r_offset >= symbol.st_value + symbol.st_size)
                continue;
            require(ELF64_R_TYPE(relocation.r_info) == R_X86_64_PLT32 && relocation.r_addend == -4 &&
                        relocation.r_offset + 4 == symbol.st_value + symbol.st_size &&
                        wrapper.symbol(ELF64_R_SYM(relocation.r_info)).st_shndx == SHN_UNDEF,
                    "native wrapper lacks a terminal selected-target PLT32 relocation");
            ++found;
        }
        require(found == 1, "native wrapper must have one tail relocation per export");
        ++exports;
    }
    require(exports > 0 && exports * sizeof(Elf64_Rela) == relocations.size(),
            "native wrapper relocation count differs from exports");
    std::cout << "PASS frontend wrapper normalized GNU text/symbols/relocations and closed ELF profile\n";
}
void writeLittle(std::string &bytes, std::size_t offset, std::size_t width, std::uint64_t value) {
    require(width <= 8 && offset <= bytes.size() && width <= bytes.size() - offset, "mutation out of fixture bounds");
    for (std::size_t byte = 0; byte < width; ++byte)
        bytes[offset + byte] = static_cast<char>(value >> (byte * 8));
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
            writeLittle(changed, base + offset, width, value);
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
template <class Operation>
void allocationFailures(Operation operation, const std::string &expected, std::string_view component) {
    AllocationFailure successful;
    require(operation(successful.allocator()) == expected, "allocator transport changed output");
    require(successful.live == 0 && successful.calls > 0, "successful operation leaked allocation");
    for (std::size_t fail = 1; fail <= successful.calls; ++fail) {
        AllocationFailure failing;
        failing.fail = fail;
        bool rejected = false;
        try {
            (void)operation(failing.allocator());
        } catch (const Error &error) {
            rejected = std::string(error.what()).find("allocation failed") != std::string::npos;
        }
        require(rejected && failing.live == 0, "allocation failure did not close all workspace owners");
    }
    std::cout << "PASS " << component << " every allocation failure releases owners\n";
}
void wrapperRepeatedRun(const std::string &recipe) {
    using Status = hosted_abi::compiler_x86::EmitStatus;
    const std::array cases = {
        std::tuple{std::uint64_t(64 * 1024 * 1024), false, Status::invalid},
        std::tuple{std::uint64_t(64 * 1024 * 1024), true, Status::complete},
        std::tuple{std::uint64_t(0), true, Status::allocation},
        std::tuple{std::uint64_t(4096), true, Status::allocation},
    };
    for (const auto &[quota, initiallyValid, expected] : cases) {
        hosted::bytes::Region region(quota);
        require(region.is_open(), "wrapper repeated-run region allocation failed");
        hosted_abi::EmitterObjectRelease owner{};
        owner.region = region.id();
        hosted_abi::EmitterObjectCreate create{};
        create.region = region.id();
        auto *workspace = owner.workspace.storage.data();
        aurora_hosted_emitter_object_create(&create, workspace);
        hosted_abi::EmitterWrapperInput input{};
        input.recipe.backing = recipe.data();
        input.recipe.length = initiallyValid ? recipe.size() : 1;
        const auto first = aurora_hosted_emitter_wrapper_run(workspace, &input);
        input.recipe.length = recipe.size();
        const auto again = aurora_hosted_emitter_wrapper_run(workspace, &input);
        const auto size = aurora_hosted_emitter_object_size(workspace);
        hosted_abi::compiler_x86::EmitChunk chunk{};
        aurora_hosted_emitter_object_chunk(workspace, 0, &chunk);
        aurora_hosted_emitter_object_release(&owner);
        require(first == static_cast<std::int64_t>(expected) &&
                    again == static_cast<std::int64_t>(expected == Status::complete ? Status::invalid : expected) &&
                    size == -1 && chunk.byteCount == -1 && region.metrics().live_allocations == 0,
                "wrapper repeated run exposed output or retained owners");
    }
    std::cout << "PASS frontend wrapper invalid/quota failure stays sticky and completed workspace cannot be reused\n";
}
// Recipe offsets below describe the versioned transport, not generated code.
// Mutation cases select real table entries, so additions do not re-pin ordinals.
void wrapperMutations(const std::string &recipe,
                      const std::string &source,
                      const std::string &selected,
                      const std::string &path) {
    const auto count = read<std::uint32_t>(recipe, 8);
    const std::size_t strings = 16 + count * 48;
    const auto selectedRow = [&](const std::string &selector) -> std::size_t {
        if (selector == "first")
            return 16;
        if (selector == "last")
            return 16 + (count - 1) * 48;
        for (std::size_t index = 0; index < count; ++index) {
            const auto row = 16 + index * 48;
            const auto moves = read<std::uint32_t>(recipe, row + 16);
            if (selector == "copied" && moves == 2 && recipe[row + 26] == 8)
                return row;
            for (std::size_t move = 0; move < moves; ++move)
                if (selector == "record" && recipe[row + 24 + move * 4] == 1)
                    return row;
        }
        throw Error("missing recipe mutation selector " + selector);
    };
    std::istringstream cases(readFile(path));
    std::string line;
    std::size_t checked = 0;
    while (std::getline(cases, line)) {
        if (line.empty() || line[0] == '#')
            continue;
        std::istringstream fields(line);
        std::string description, location, selector, expected;
        std::size_t offset, width;
        std::uint64_t value;
        require(bool(fields >> description >> location >> selector >> offset >> width >> value >> expected),
                "malformed wrapper recipe case " + line);
        auto changed = recipe;
        if (location == "truncate") {
            changed.resize(offset);
        } else if (location == "append") {
            changed.push_back(static_cast<char>(value));
        } else if (location == "collision") {
            const auto targetRow = selector == "earlier" ? 16 + (count - 1) * 48 : 16;
            const auto hostRow = selector == "later" ? 16 + (count - 1) * 48 : 16;
            const auto host = read<std::uint32_t>(recipe, hostRow);
            const auto hostSize = read<std::uint32_t>(recipe, hostRow + 4);
            const auto target = read<std::uint32_t>(recipe, targetRow + 8);
            const auto targetSize = read<std::uint32_t>(recipe, targetRow + 12);
            const auto delta = std::int64_t(hostSize) - targetSize;
            changed.replace(strings + target, targetSize, recipe.substr(strings + host, hostSize));
            writeLittle(changed, targetRow + 12, 4, hostSize);
            for (std::size_t index = 0; index < count; ++index)
                for (const std::size_t field : {0, 8}) {
                    const auto at = 16 + index * 48 + field;
                    const auto before = read<std::uint32_t>(recipe, at);
                    if (before > target)
                        writeLittle(changed, at, 4, std::int64_t(before) + delta);
                }
            writeLittle(changed, 12, 4, changed.size() - strings);
        } else if (location == "duplicate") {
            bool found = false;
            for (std::size_t first = 0; first < count && !found; ++first) {
                const auto a = 16 + first * 48;
                const auto field = selector == "target" ? 8 : 0;
                const auto length = read<std::uint32_t>(recipe, a + field + 4);
                for (std::size_t second = first + 1; second < count; ++second) {
                    const auto b = 16 + second * 48;
                    if (length == read<std::uint32_t>(recipe, b + field + 4)) {
                        changed.replace(strings + read<std::uint32_t>(recipe, b + field),
                                        length,
                                        recipe.substr(strings + read<std::uint32_t>(recipe, a + field), length));
                        found = true;
                        break;
                    }
                }
            }
            require(found, "fixture needs equal-width exports for duplicate-name case");
        } else {
            std::size_t base = 0;
            if (location != "header") {
                base = selectedRow(selector);
                if (location == "export" || location == "target") {
                    const auto field = base + (location == "target" ? 8 : 0);
                    base = strings + read<std::uint32_t>(recipe, field);
                } else if (location == "load") {
                    const auto moves = read<std::uint32_t>(recipe, base + 16);
                    const auto first = base + 24;
                    base = 0;
                    for (std::size_t move = 0; move < moves; ++move)
                        if (recipe[first + move * 4] == 1) {
                            base = first + move * 4;
                            break;
                        }
                    require(base != 0, "fixture needs a record load");
                } else
                    require(location == "row", "unknown recipe mutation location");
            }
            writeLittle(changed, base + offset, width, value);
        }
        require(expected == "reject" || expected == "compose-reject", "unknown recipe mutation expectation");
        bool rejected = false;
        if (expected == "reject") {
            try {
                (void)emitFrontendWrapper(changed);
            } catch (const Error &) {
                rejected = true;
            }
        } else {
            const auto wrapper = emitFrontendWrapper(changed);
            try {
                (void)composePrivateObject(source, wrapper, selected);
            } catch (const Error &) {
                rejected = true;
            }
        }
        require(rejected, description + ": malformed wrapper recipe or foreign target accepted");
        ++checked;
    }
    std::cout << "PASS frontend wrapper " << checked << " malformed recipe and foreign-target data cases\n";
}
} // namespace
int main(int argc, char **argv) {
    try {
        if (argc == 5 && std::string_view(argv[1]) == "--compare") {
            compare(readFile(argv[2]), readFile(argv[3]), readFile(argv[4]));
        } else if (argc == 5 && std::string_view(argv[1]) == "--wrapper-boundaries") {
            const auto wrapper = emitFrontendWrapper(readFile(argv[2]));
            compareWrapper(wrapper, readFile(argv[3]));
            writeFile(argv[4], wrapper);
        } else if (argc == 9 && std::string_view(argv[1]) == "--wrapper") {
            const auto recipe = readFile(argv[2]), source = readFile(argv[6]), selected = readFile(argv[7]);
            const auto wrapper = emitFrontendWrapper(recipe);
            compareWrapper(wrapper, readFile(argv[5]));
            wrapperMutations(recipe, source, selected, argv[3]);
            mutations(source, wrapper, selected, argv[4]);
            allocationFailures(
                [&](auto allocator) {
                    return emitFrontendWrapper(recipe, allocator);
                },
                wrapper,
                "frontend wrapper");
            wrapperRepeatedRun(recipe);
            writeFile(argv[8], wrapper);
        } else {
            require(argc == 5,
                    "expected IR CASES WRAPPER OUTPUT-DIRECTORY, --compare SOURCE ACTUAL GNU or "
                    "--wrapper RECIPE RECIPE-CASES ELF-CASES GNU SOURCE SELECTED OUTPUT");
            const auto module = validate(test::air::loadCase(argv[1], "native object values"));
            const auto source =
                X86Emitter{}.emit(module, SymbolBinding::Local, ReflectionEmission::Referenced, CodeEmission::Object);
            const auto wrapper = readFile(argv[3]);
            const std::string selected = "object_literal\nobject_loop\nobject_six_arguments\n";
            const auto composed = composePrivateObject(source, wrapper, selected);
            mutations(source, wrapper, selected, argv[2]);
            allocationFailures(
                [&](auto allocator) {
                    return composePrivateObject(source, wrapper, selected, allocator);
                },
                composed,
                "private object");
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
