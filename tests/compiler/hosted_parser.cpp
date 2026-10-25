// Parser cases are data: hosted_parser.cases holds the sources and their
// parse steps, golden/hosted_parser.golden the reviewed canonical dump of every
// tree, record and diagnostic (--update rewrites it). The C++ below keeps only
// what is not a parse-this-text case: raw ABI envelopes, growth limits,
// representative allocation failures, ownership and typed-module controls.
#include "lexer.hpp"
#include "parser.hpp"
#include "hosted_parser.hpp"
#include "hosted_resolver.hpp"
#include "x86.hpp"
#include "../../runtime/hosted_bytes.hpp"
#include <algorithm>
#include <array>
#include <bit>
#include <cerrno>
#include <csignal>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
#include <limits>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <tuple>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/wait.h>
#include <unistd.h>

#if !defined(AURORA_HOSTED_PARSER) || !defined(AURORA_HOSTED_LEXER)
#error The hosted parser fixture must link the real Aurora frontend
#endif
extern "C" {
void checked_hosted_parser_create(const void *, void *);
void checked_hosted_parser_parse(void *, const void *, void *);
void checked_hosted_parser_admit(void *, const void *, void *);
std::int64_t checked_hosted_parser_count(const void *);
void checked_hosted_parser_read(const void *, std::int64_t, void *);
std::int64_t checked_hosted_parser_edges(const void *);
void checked_hosted_parser_edge(const void *, std::int64_t, void *);
std::int64_t checked_hosted_parser_types(const void *);
void checked_hosted_parser_type(const void *, std::int64_t, void *);
std::int64_t checked_hosted_parser_syntax_count(const void *);
void checked_hosted_parser_syntax(const void *, std::int64_t, void *);
void checked_hosted_parser_release(void *);
void checked_hosted_resolver_create(const void *, void *);
void checked_hosted_resolver_ingest(void *, void *);
void checked_hosted_resolver_release(void *);
void checked_hosted_resolver_release_pair(void *);
std::int64_t checked_hosted_resolver_append_source(void *, const void *);
std::int64_t checked_hosted_resolver_count(const void *, std::int64_t);
std::int64_t checked_hosted_resolver_read_source(const void *, std::int64_t);
void checked_hosted_resolver_read_meta(const void *, std::int64_t, void *);
void checked_hosted_resolver_status(const void *, void *);
void aurora_hosted_metadata_create(const void *, void *) noexcept;
void aurora_hosted_metadata_flag_masks(void *) noexcept;
std::int64_t aurora_hosted_metadata_initialize(void *, const void *) noexcept;
void aurora_hosted_metadata_release(void *) noexcept;
std::int64_t aurora_hosted_metadata_allocated(const void *) noexcept;
std::int64_t aurora_hosted_metadata_run(void *) noexcept;
std::int64_t aurora_hosted_metadata_error(const void *) noexcept;
void aurora_hosted_instructions_create(const void *, void *) noexcept;
void aurora_hosted_instructions_release(void *) noexcept;
std::int64_t aurora_hosted_instructions_allocated(const void *) noexcept;
std::int64_t aurora_hosted_instructions_admit(const void *) noexcept;
std::int64_t aurora_hosted_instructions_error(const void *) noexcept;
std::int64_t aurora_hosted_instructions_structure(const void *) noexcept;
std::int64_t aurora_hosted_instructions_publish(void *) noexcept;
}

using AbiEntry = void (*)(const void *, const void *, void *);
extern "C" {
void checked_hosted_parser_call(const void *, const void *, void *, AbiEntry);
void hosted_parser_clobber_rbp(const void *, const void *, void *);
void hosted_parser_clobber_rbx(const void *, const void *, void *);
void hosted_parser_clobber_r12(const void *, const void *, void *);
void hosted_parser_clobber_r13(const void *, const void *, void *);
void hosted_parser_clobber_r14(const void *, const void *, void *);
void hosted_parser_clobber_r15(const void *, const void *, void *);
void hosted_parser_clobber_canary(const void *, const void *, void *);
void hosted_parser_shift_stack(const void *, const void *, void *);
void hosted_parser_misaligned_call(const void *, const void *, void *, AbiEntry);
}

namespace {
using aurora::hosted_parser::AdmissionStatus;
using aurora::hosted_parser::Context;
using aurora::hosted_parser::Cursor;
using aurora::hosted_parser::NodeKind;
using aurora::hosted_parser::Status;
using aurora::hosted_parser::Stop;
using Words = std::array<std::int64_t, 6>;
using AdmissionWords = std::array<std::int64_t, 5>;
using AdmissionConfigWords = std::array<std::int64_t, 6>;
constexpr AdmissionConfigWords admissionConfiguration{64, 512, 62, 1, 2, 4};
using NodeWords = std::array<std::int64_t, 7>;
using EdgeWords = std::array<std::int64_t, 5>;
using TypeWords = std::array<std::int64_t, 8>;
using SyntaxWords = std::array<std::int64_t, 12>;
using aurora::hosted_parser::SyntaxKind;
using ContextWords = std::array<std::int64_t, 7>;
constexpr std::int64_t wire(NodeKind value) {
    return static_cast<std::int64_t>(value);
}
constexpr std::int64_t wire(SyntaxKind value) {
    return static_cast<std::int64_t>(value);
}
constexpr std::int64_t wire(Status value) {
    return static_cast<std::int64_t>(value);
}
constexpr std::int64_t wire(AdmissionStatus value) {
    return static_cast<std::int64_t>(value);
}
constexpr std::uint64_t canary = 0xa3159f274c86be02ULL;
std::size_t cases = 0;
std::string context;
void require(bool value, const std::string &message) {
    if (!value)
        throw std::runtime_error(context + ": " + message);
}

class Allocations {
public:
    std::size_t allowed = std::numeric_limits<std::size_t>::max(), successful = 0, released = 0;
    std::size_t attempted = 0;
    std::array<std::size_t, 25> initialBytes{};
    std::array<void *, 11> initialOwners{}, releasedOwners{};
    static void *allocate(void *context, std::size_t bytes) noexcept {
        auto &state = *static_cast<Allocations *>(context);
        if (state.attempted < state.initialBytes.size())
            state.initialBytes[state.attempted] = bytes;
        ++state.attempted;
        auto *result = state.successful < state.allowed ? std::malloc(bytes) : nullptr;
        if (state.attempted <= state.initialOwners.size())
            state.initialOwners[state.attempted - 1] = result;
        if (result)
            ++state.successful;
        return result;
    }
    static void deallocate(void *context, void *address) noexcept {
        auto &state = *static_cast<Allocations *>(context);
        if (state.released < state.releasedOwners.size())
            state.releasedOwners[state.released] = address;
        ++state.released;
        std::free(address);
    }
    aurora::hosted::bytes::Allocator allocator() {
        return {this, allocate, deallocate};
    }
};
template <std::size_t N> class GuardedWords {
public:
    std::uint64_t before = canary;
    std::array<std::int64_t, N> value{};
    std::uint64_t after = canary;
    void check() const {
        require(before == canary && after == canary, "result write escaped its ABI extent");
    }
};
static_assert(sizeof(Words) == 48 && sizeof(GuardedWords<6>) == 64 && sizeof(GuardedWords<5>) == 56 &&
              sizeof(GuardedWords<7>) == 72 && sizeof(EdgeWords) == 40 && sizeof(TypeWords) == 64 &&
              sizeof(GuardedWords<8>) == 80 && sizeof(ContextWords) == 56 && sizeof(GuardedWords<19>) == 168 &&
              sizeof(SyntaxWords) == 96 && sizeof(GuardedWords<12>) == 112);
static_assert(sizeof(AdmissionWords) == sizeof(aurora::hosted_abi::compiler_parser::AdmissionResult) &&
              sizeof(AdmissionConfigWords) == sizeof(aurora::hosted_abi::compiler_parser::AdmissionConfig) &&
              sizeof(std::array<std::int64_t, 14>) == sizeof(aurora::hosted_abi::AdmissionInput) &&
              sizeof(AdmissionWords) == 40 && sizeof(AdmissionConfigWords) == 48);
static_assert(offsetof(aurora::hosted_abi::AdmissionInput, root) == 56 &&
              offsetof(aurora::hosted_abi::AdmissionInput, configuration) == 64);
static_assert(sizeof(Words) == sizeof(aurora::hosted_abi::compiler_parser::ParseResult) &&
              sizeof(NodeWords) == sizeof(aurora::hosted_abi::compiler_parser::AstNode) &&
              sizeof(EdgeWords) == sizeof(aurora::hosted_abi::compiler_parser::ChildEdge) &&
              sizeof(TypeWords) == sizeof(aurora::hosted_abi::compiler_parser::TypeSyntax) &&
              sizeof(SyntaxWords) == sizeof(aurora::hosted_abi::compiler_parser::SyntaxNode) &&
              sizeof(std::array<std::int64_t, 19>) == sizeof(aurora::hosted_abi::ParserInput));
static_assert(sizeof(ContextWords) == offsetof(aurora::hosted_abi::ParserInput, enum_count) -
                                          offsetof(aurora::hosted_abi::ParserInput, context));
class RawArena {
    aurora::hosted::bytes::Region region;
    // This storage is never copied or inspected as an owner descriptor. Aurora
    // constructs and consumes it; the host only supplies region identity.
    std::uint64_t before = canary;
    aurora::hosted_abi::ParserRelease record;
    std::uint64_t after = canary;
    bool active = true;

public:
    explicit RawArena(Allocations &allocations, std::uint64_t quota = 1048576, std::int64_t initial = 0)
        : region(quota, allocations.allocator()) {
        record.region = region.id();
        aurora::hosted_abi::ParserCreate input;
        input.region = region.id();
        input.capacity = initial;
        checked_hosted_parser_create(&input, data());
        guards();
    }
    ~RawArena() {
        if (active)
            checked_hosted_parser_release(&record);
    }
    RawArena(const RawArena &) = delete;
    RawArena &operator=(const RawArena &) = delete;
    void *data() {
        return record.arena.storage.data();
    }
    void guards() const {
        require(before == canary && after == canary, "arena write escaped its ABI extent");
    }
    Words parse(const std::string &source,
                Stop stop = Stop::semicolon,
                std::int64_t offset = 0,
                ContextWords typeContext = {},
                std::int64_t enumCount = 0) {
        GuardedWords<19> input;
        input.value = {0,
                       static_cast<std::int64_t>(reinterpret_cast<std::uintptr_t>(source.data())),
                       0,
                       0,
                       0,
                       0,
                       static_cast<std::int64_t>(source.size()),
                       offset,
                       1,
                       0,
                       static_cast<std::int64_t>(stop)};
        static_assert(sizeof(input.value) == 152);
        input.value[18] = enumCount;
        const auto beforeSource = source;
        for (std::size_t index = 0; index < typeContext.size(); ++index)
            input.value[11 + index] = typeContext[index];
        const auto beforeInput = input.value;
        GuardedWords<6> output;
        checked_hosted_parser_parse(data(), input.value.data(), output.value.data());
        input.check();
        require(input.value == beforeInput && source == beforeSource,
                "parse changed its copied input/source/context record");
        output.check();
        guards();
        require(output.value[2] == checked_hosted_parser_count(data()),
                "reported arena count differs from real storage");
        if (stop == Stop::semicolon || stop == Stop::close_parenthesis || stop == Stop::assignment ||
            stop == Stop::constructor_braces || stop == Stop::type)
            require(syntaxCount() == 0, "expression/type profile acquired syntax records");
        if (stop == Stop::type)
            require(output.value[2] == 0 && edges() == 0, "type-only profile acquired expression/edge records");
        return output.value;
    }
    AdmissionWords admit(const std::string &source,
                         std::int64_t root,
                         const AdmissionConfigWords &configuration = admissionConfiguration) {
        GuardedWords<14> input;
        input.value = {0,
                       static_cast<std::int64_t>(reinterpret_cast<std::uintptr_t>(source.data())),
                       0,
                       0,
                       0,
                       0,
                       static_cast<std::int64_t>(source.size()),
                       root};
        std::copy(configuration.begin(), configuration.end(), input.value.begin() + 8);
        const auto beforeInput = input.value;
        const auto beforeSource = source;
        GuardedWords<5> output;
        checked_hosted_parser_admit(data(), input.value.data(), output.value.data());
        input.check();
        output.check();
        guards();
        require(input.value == beforeInput && source == beforeSource,
                "admission changed its copied source/root/configuration record");
        return output.value;
    }
    NodeWords read(std::int64_t index) {
        GuardedWords<7> output;
        checked_hosted_parser_read(data(), index, output.value.data());
        output.check();
        guards();
        return output.value;
    }
    std::int64_t edges() {
        return checked_hosted_parser_edges(data());
    }
    EdgeWords edge(std::int64_t index) {
        GuardedWords<5> output;
        checked_hosted_parser_edge(data(), index, output.value.data());
        output.check();
        guards();
        return output.value;
    }
    std::int64_t types() {
        const auto count = checked_hosted_parser_types(data());
        guards();
        return count;
    }
    TypeWords type(std::int64_t index) {
        GuardedWords<8> output;
        checked_hosted_parser_type(data(), index, output.value.data());
        output.check();
        guards();
        return output.value;
    }
    std::int64_t syntaxCount() {
        const auto count = checked_hosted_parser_syntax_count(data());
        guards();
        return count;
    }
    SyntaxWords syntax(std::int64_t index) {
        GuardedWords<12> output;
        checked_hosted_parser_syntax(data(), index, output.value.data());
        output.check();
        guards();
        return output.value;
    }
    aurora::hosted::bytes::Metrics metrics() const {
        return region.metrics();
    }
    void finish() {
        checked_hosted_parser_release(&record);
        active = false;
        guards();
        const auto final = region.metrics();
        require(final.used == 0 && final.live_allocations == 0 && final.releases == final.successful_allocations,
                "Aurora cleanup leaked payload or ownership metadata");
        require(region.close(), "empty parser region did not close");
    }
};

// ---- Canonical dump. Every span is checked against the case snapshot (byte
// bounds, line/column, owning source) and every expression depth against its
// tree; the dump then records offsets, spellings and all non-default fields.
using Snapshot = std::shared_ptr<const aurora::SourceText>;
Snapshot dumpSource;
std::vector<aurora::SourcePosition> dumpPositions;

std::vector<aurora::SourcePosition> positionsOf(const std::string &text) {
    std::vector<aurora::SourcePosition> out;
    out.reserve(text.size() + 1);
    aurora::SourcePosition at;
    out.push_back(at);
    for (const unsigned char byte : text) {
        ++at.offset;
        if (byte == '\n') {
            ++at.line;
            at.column = 1;
        } else {
            ++at.column;
        }
        out.push_back(at);
    }
    return out;
}
// Strings longer than a review line are recorded by length and FNV-1a digest.
std::string printable(const std::string &text, std::size_t limit = 96, bool spaces = false) {
    if (text.size() > limit) {
        std::uint64_t hash = 0xcbf29ce484222325ULL;
        for (const unsigned char byte : text)
            hash = (hash ^ byte) * 0x100000001b3ULL;
        std::ostringstream out;
        out << '<' << text.size() << " bytes " << std::hex << hash << '>';
        return out.str();
    }
    std::string out;
    for (const unsigned char byte : text) {
        if (byte < ' ' || byte == 0x7f || (byte == ' ' && !spaces)) {
            constexpr char digits[] = "0123456789abcdef";
            out += "\\x";
            out += digits[byte >> 4];
            out += digits[byte & 15];
        } else {
            out += static_cast<char>(byte);
        }
    }
    return out;
}
std::string join(const std::vector<std::string> &items, const std::string &separator) {
    std::string out;
    for (std::size_t index = 0; index < items.size(); ++index)
        out += (index ? separator : "") + items[index];
    return out;
}
bool defaultPosition(const aurora::SourcePosition &position) {
    return position.offset == 0 && position.line == 1 && position.column == 1;
}
std::string span(const aurora::SourceSpan &value) {
    const auto range = std::to_string(value.begin.offset) + "-" + std::to_string(value.end.offset);
    if (!value.source)
        return defaultPosition(value.begin) && defaultPosition(value.end)
                   ? "@none"
                   : "@none:" + range + ":" + std::to_string(value.begin.line) + "." +
                         std::to_string(value.begin.column) + "-" + std::to_string(value.end.line) + "." +
                         std::to_string(value.end.column);
    const bool local = value.source == dumpSource;
    const auto foreign = local ? std::vector<aurora::SourcePosition>{} : positionsOf(value.source->text);
    const auto &table = local ? dumpPositions : foreign;
    require(value.begin.offset <= value.end.offset && value.end.offset <= value.source->text.size(),
            "span escapes its source");
    for (const auto *position : {&value.begin, &value.end})
        require(position->line == table[position->offset].line && position->column == table[position->offset].column,
                "span line/column differs from its byte offset");
    return "@" + (local ? "" : printable(value.source->path) + ":") + range;
}
bool defaultSpan(const aurora::SourceSpan &value) {
    return !value.source && defaultPosition(value.begin) && defaultPosition(value.end);
}
// A token is its spelling and begin offset when it is exactly that source
// slice; qualified spellings joined across trivia and >> halves show the span.
std::string token(const aurora::Token &value) {
    const auto &where = value.span;
    if (!where.source)
        return printable(value.text) + span(where) + "/" + std::to_string(value.line);
    require(value.line == where.begin.line, "token line differs from its span");
    const auto range = span(where);
    if (where.source == dumpSource && where.end.offset - where.begin.offset == value.text.size() &&
        dumpSource->text.compare(where.begin.offset, value.text.size(), value.text) == 0)
        return printable(value.text) + "@" + std::to_string(where.begin.offset);
    return printable(value.text) + range;
}
std::string diagnostic(const aurora::Diagnostic &value) {
    return std::string(value.severity == aurora::DiagnosticSeverity::Error ? "error " : "warning ") +
           std::string(aurora::diagnosticCode(value.code)) + " " + span(value.span) + " " +
           printable(value.message, 240, true);
}

constexpr std::array<const char *, 22> typeKinds{"I64",
                                                 "Bool",
                                                 "Own",
                                                 "Ref",
                                                 "MutRef",
                                                 "Class",
                                                 "Array",
                                                 "U64",
                                                 "Parameter",
                                                 "Enum",
                                                 "U8",
                                                 "ByteSpan",
                                                 "ByteRegion",
                                                 "OwnedBytes",
                                                 "ConsoleSession",
                                                 "DisplaySession",
                                                 "IommuEventSession",
                                                 "OwnedValues",
                                                 "CallSession",
                                                 "Com1UartGrant",
                                                 "ServeSession",
                                                 "ValueSpan"};
static_assert(static_cast<std::size_t>(aurora::TypeKind::ValueSpan) + 1 == typeKinds.size());
std::string kind(aurora::TypeKind value) {
    const auto index = static_cast<std::size_t>(value);
    return index < typeKinds.size() ? typeKinds[index] : "Kind" + std::to_string(index);
}
std::string arguments(const std::vector<aurora::TemplateArgument> &values);
std::string nominal(const std::string &name, const std::string &display, bool resolved) {
    return (name.empty() ? "" : ":" + printable(name)) + (display.empty() ? "" : "/" + printable(display)) +
           (resolved ? "!" : "");
}
std::string argument(const aurora::TemplateArgument &value) {
    const bool capacity = value.kind == aurora::TemplateArgumentKind::Value;
    std::string out = capacity ? "#" + std::to_string(value.value) : kind(value.type);
    if (capacity && value.type != aurora::TypeKind::I64)
        out += "@" + kind(value.type);
    if (!capacity && value.value)
        out += "=" + std::to_string(value.value);
    return out + nominal(value.className, value.displayName, value.resolvedClass) + arguments(value.templateArguments);
}
std::string arguments(const std::vector<aurora::TemplateArgument> &values) {
    if (values.empty())
        return {};
    std::vector<std::string> out;
    for (const auto &value : values)
        out.push_back(argument(value));
    return "<" + join(out, ",") + ">";
}
std::string type(const aurora::Type &value) {
    std::string out = kind(value.kind) + nominal(value.className, value.displayName, value.resolvedClass);
    if (value.isArray() || value.elementKind != aurora::TypeKind::I64 || value.length ||
        !value.elementParameter.empty() || !value.lengthParameter.empty())
        out += "[" + kind(value.elementKind) + "," + std::to_string(value.length) +
               (value.elementParameter.empty() ? "" : ",elem=" + printable(value.elementParameter)) +
               (value.lengthParameter.empty() ? "" : ",len=" + printable(value.lengthParameter)) + "]";
    return out + arguments(value.templateArguments);
}
bool plain(const aurora::Type &value, const aurora::Type &expected) {
    return value == expected && value.displayName.empty() && !value.resolvedClass;
}
std::string names(const std::vector<std::string> &values) {
    std::vector<std::string> out;
    for (const auto &value : values)
        out.push_back(printable(value));
    return join(out, ",");
}
std::string names(const std::set<std::string> &values) {
    return names(std::vector<std::string>(values.begin(), values.end()));
}

int expression(std::string &out, const aurora::ExpressionPtr &value) {
    require(bool(value), "expression is missing");
    out += "(" + value->op + " " + token(value->token);
    if (!value->fieldNames.empty())
        out += " {" + names(value->fieldNames) + "}";
    if (!value->templateArguments.empty())
        out += " " + arguments(value->templateArguments);
    if (!plain(value->reflectedType, aurora::Type{}))
        out += " :" + type(value->reflectedType);
    if (!value->resolvedName.empty())
        out += " resolved=" + printable(value->resolvedName);
    if (!value->overloadCandidates.empty())
        out += " overloads=" + names(value->overloadCandidates);
    if (!value->inaccessibleOverloads.empty())
        out += " inaccessible=" + names(value->inaccessibleOverloads);
    if (value->enumOrdinal != -1)
        out += " ordinal=" + std::to_string(value->enumOrdinal);
    int depth = 1;
    for (const auto &child : value->args) {
        out += " ";
        depth = std::max(depth, expression(out, child) + 1);
    }
    out += ")";
    require(value->depth == depth, "expression depth differs from its tree");
    return depth;
}
std::string expression(const aurora::ExpressionPtr &value) {
    std::string out;
    expression(out, value);
    return out;
}
void statements(std::string &out, const std::vector<aurora::StatementPtr> &values);
void statement(std::string &out, const aurora::StatementPtr &value) {
    require(bool(value), "statement is missing");
    out += "[" + value->kind + " " + token(value->token);
    if (!value->name.empty())
        out += " name=" + printable(value->name);
    if (!value->fieldName.empty())
        out += " field=" + printable(value->fieldName);
    if (value->kind == "let" || !plain(value->type, aurora::Type::I64))
        out += " type=" + type(value->type);
    if (!defaultSpan(value->bindingSpan))
        out += " bind" + span(value->bindingSpan);
    if (value->mutableValue)
        out += " mut";
    if (value->target)
        out += " target=" + expression(value->target);
    if (value->expr)
        out += " " + expression(value->expr);
    if (!value->body.empty()) {
        out += " {";
        statements(out, value->body);
        out += "}";
    }
    if (!value->other.empty()) {
        out += " else{";
        statements(out, value->other);
        out += "}";
    }
    out += "]";
}
void statements(std::string &out, const std::vector<aurora::StatementPtr> &values) {
    for (std::size_t index = 0; index < values.size(); ++index) {
        if (index)
            out += " ";
        statement(out, values[index]);
    }
}
using Lines = std::vector<std::string>;
std::string templateParameters(const std::vector<aurora::TemplateParameter> &values) {
    std::vector<std::string> out;
    for (const auto &value : values)
        out.push_back(std::string(value.kind == aurora::TemplateParameterKind::Scalar  ? "Scalar "
                                  : value.kind == aurora::TemplateParameterKind::Value ? "Value "
                                                                                       : "Capacity ") +
                      printable(value.name));
    return values.empty() ? "" : " template<" + join(out, ",") + ">";
}
void function(Lines &lines, const std::string &indent, const std::string &keyword, const aurora::Function &value) {
    std::string out = indent + keyword + " " + token(value.token);
    if (value.name != value.token.text)
        out += " name=" + printable(value.name);
    if (!value.scope.empty())
        out += " scope=" + printable(value.scope);
    for (const auto &[set, word] : std::array<std::pair<bool, const char *>, 4>{{{value.exported, " export"},
                                                                                 {value.publicAccess, " public"},
                                                                                 {value.constructor, " constructor"},
                                                                                 {value.receiverConst, " const"}}})
        if (set)
            out += word;
    if (!value.receiverClass.empty())
        out += " receiver=" + printable(value.receiverClass);
    if (value.moduleScope)
        out += " module-scope=" + std::to_string(value.moduleScope);
    out += templateParameters(value.templateParameters);
    if (!value.templateArguments.empty())
        out += " arguments" + arguments(value.templateArguments);
    if (!value.templateTypeAuthority.empty())
        out += " authority={" + names(value.templateTypeAuthority) + "}";
    std::vector<std::string> parameters;
    for (const auto &parameter : value.params)
        parameters.push_back(printable(parameter.name) + " " + type(parameter.type) + (parameter.borrowed ? " &" : "") +
                             (parameter.borrowConst ? " const" : "") +
                             (defaultSpan(parameter.borrowSpan) ? "" : " " + span(parameter.borrowSpan)));
    lines.push_back(out + " (" + join(parameters, ", ") + ") -> " + type(value.result));
    for (const auto &[field, initializer] : value.initializers)
        lines.push_back(indent + "  init " + token(field) + " " + expression(initializer));
    for (const auto &item : value.body) {
        std::string text = indent + "  ";
        statement(text, item);
        lines.push_back(text);
    }
}
std::string field(const aurora::Field &value) {
    return "field " + token(value.token) + " " + type(value.type) + (value.publicAccess ? " public" : "") +
           (value.offset ? " offset=" + std::to_string(value.offset) : "") +
           (value.index ? " index=" + std::to_string(value.index) : "");
}
std::string declaration(const std::string &keyword,
                        const aurora::Token &name,
                        const std::string &spelling,
                        const std::string &scope,
                        bool exported,
                        int id) {
    return keyword + " " + token(name) + (spelling != name.text ? " name=" + printable(spelling) : "") +
           (scope.empty() ? "" : " scope=" + printable(scope)) + (exported ? " export" : "") +
           (id ? " id=" + std::to_string(id) : "");
}
void definition(Lines &lines, const std::string &keyword, const aurora::ClassDefinition &value) {
    lines.push_back(declaration(keyword, value.token, value.name, value.scope, value.exported, value.id) +
                    templateParameters(value.templateParameters) +
                    (value.templateArguments.empty() ? "" : " arguments" + arguments(value.templateArguments)));
    for (const auto &item : value.fields)
        lines.push_back("  " + field(item));
    for (const auto &method : value.methods)
        function(lines, "  ", "method", method);
}
std::string enumeration(const aurora::EnumDefinition &value) {
    std::vector<std::string> cases;
    for (const auto &item : value.cases)
        cases.push_back(token(item));
    return declaration("enum", value.token, value.name, value.scope, value.exported, value.id) + " {" +
           join(cases, ",") + "}";
}
void program(Lines &lines, const aurora::Program &value) {
    lines.push_back("module " + printable(value.moduleName) + (value.interfaceUnit ? " interface" : ""));
    for (const auto &item : value.imports)
        lines.push_back("import " + token(item));
    if (!value.namespaces.empty())
        lines.push_back("namespaces " + names(value.namespaces));
    for (const auto &[scope, access] : value.reflectionAccess)
        lines.push_back("reflection " + std::to_string(scope) + " {" + names(access) + "}");
    for (const auto &item : value.functions)
        function(lines, "", "function", item);
    for (const auto &item : value.functionTemplates)
        function(lines, "", "function-template", item);
    for (const auto &item : value.classes)
        definition(lines, "class", item);
    for (const auto &item : value.templates)
        definition(lines, "class-template", item);
    for (const auto &item : value.enums)
        lines.push_back(enumeration(item));
}
std::string cursor(const Cursor &value) {
    return "next=" + std::to_string(value.ordinal) + (value.half ? " half=" + std::to_string(value.half) : "");
}
template <std::size_t N> std::string words(const std::array<std::int64_t, N> &values) {
    std::string out;
    for (std::size_t index = 0; index < N; ++index)
        out += (index ? " " : "") + std::to_string(values[index]);
    return out;
}

// ---- Cases from the cases file, keyed by name in one reviewed golden file.
class Step {
public:
    std::string mode;
    std::map<std::string, std::string> options;
};
class Case {
public:
    std::string name, source;
    std::size_t snippet = 0;
    std::vector<std::size_t> markers;
    std::vector<Step> steps;
};
std::vector<std::string> split(const std::string &text, char separator) {
    std::vector<std::string> out;
    std::string item;
    std::istringstream input(text);
    while (std::getline(input, item, separator))
        out.push_back(item);
    return out;
}
Step step(const std::string &text) {
    const auto parts = split(text, ' ');
    require(!parts.empty() && !parts[0].empty(), "empty @step");
    Step out{parts[0], {}};
    for (std::size_t index = 1; index < parts.size(); ++index) {
        const auto equal = parts[index].find('=');
        const auto key = parts[index].substr(0, equal);
        require(!key.empty() && !out.options.contains(key), "malformed or repeated step option: " + parts[index]);
        out.options[key] = equal == std::string::npos ? "" : parts[index].substr(equal + 1);
    }
    return out;
}
// Remove U+2038 markers, recording their source offsets.
void finish(Case &item) {
    constexpr std::string_view marker = "\xe2\x80\xb8";
    std::string source;
    std::size_t snippet = item.snippet;
    for (std::size_t at = 0; at < item.source.size();) {
        if (item.source.compare(at, marker.size(), marker) == 0) {
            item.markers.push_back(source.size());
            if (at < item.snippet)
                snippet -= marker.size();
            at += marker.size();
        } else {
            source += item.source[at++];
        }
    }
    item.source = std::move(source);
    item.snippet = snippet;
    require(!item.steps.empty(), item.name + ": case has no steps");
}
// Variant wrappers may spell a newline, carriage return or tab as \n, \r, \t.
std::string unescape(const std::string &text) {
    std::string out;
    for (std::size_t at = 0; at < text.size(); ++at) {
        const auto escape = at + 1 < text.size() && text[at] == '\\' ? std::string_view("nrt").find(text[at + 1])
                                                                     : std::string_view::npos;
        if (escape == std::string_view::npos) {
            out += text[at];
        } else {
            out += "\n\r\t"[escape];
            ++at;
        }
    }
    return out;
}
// «N|TEXT» is N copies of TEXT and «N,|TEXT» joins them with commas; '#' in
// TEXT is the copy ordinal. Names keep the unexpanded line.
std::string expand(const std::string &line) {
    constexpr std::string_view open = "\xc2\xab", close = "\xc2\xbb";
    std::string out;
    for (std::size_t at = 0; at < line.size();) {
        if (line.compare(at, open.size(), open) != 0) {
            out += line[at++];
            continue;
        }
        const auto bar = line.find('|', at), end = line.find(close, at);
        require(bar < end && end != std::string::npos, "malformed repetition");
        auto count = line.substr(at + open.size(), bar - at - open.size());
        const bool comma = count.ends_with(',');
        if (comma)
            count.pop_back();
        const auto text = line.substr(bar + 1, end - bar - 1);
        for (std::size_t copy = 0, copies = std::stoul(count); copy < copies; ++copy) {
            if (comma && copy)
                out += ',';
            for (const char byte : text)
                out += byte == '#' ? std::to_string(copy) : std::string(1, byte);
        }
        at = end + close.size();
    }
    return out;
}
std::vector<Case> readCases(const std::string &path) {
    std::ifstream file(path);
    require(file.good(), "cannot open cases file " + path);
    class Variant {
    public:
        std::string name, prefix, suffix;
        std::vector<Step> steps;
    };
    std::vector<Case> out;
    enum class Mode {
        none,
        single,
        group
    } mode = Mode::none;
    Case single;
    std::vector<std::string> body;
    std::string label;
    std::vector<Variant> variants;
    bool consumed = false;
    const auto flush = [&] {
        if (mode == Mode::single) {
            single.source = join(body, "\n");
            finish(single);
            out.push_back(std::move(single));
        }
        single = {};
        body.clear();
    };
    std::size_t number = 0;
    for (std::string line; std::getline(file, line);) {
        context = path + ":" + std::to_string(++number);
        if (line.empty() || line[0] == '#')
            continue;
        const auto rest = [&](std::size_t size) {
            return line.substr(std::min(size, line.size()));
        };
        if (line.starts_with("@case ")) {
            flush();
            mode = Mode::single;
            single.name = rest(6);
        } else if (line.starts_with("@cases ")) {
            flush();
            mode = Mode::group;
            label = rest(7);
            variants.clear();
            consumed = false;
        } else if (line.starts_with("@variant ")) {
            require(mode == Mode::group, "@variant outside @cases");
            if (consumed)
                variants.clear();
            consumed = false;
            const auto text = rest(9);
            const auto space = text.find(' ');
            Variant variant{text.substr(0, space), {}, {}, {}};
            if (space != std::string::npos) {
                const auto wrap = text.substr(space + 1);
                const auto bar = wrap.find('|');
                require(bar != std::string::npos, "@variant wrapper lacks '|'");
                variant.prefix = unescape(wrap.substr(0, bar));
                variant.suffix = unescape(wrap.substr(bar + 1));
            }
            variants.push_back(std::move(variant));
        } else if (line.starts_with("@step ")) {
            if (mode == Mode::single) {
                require(body.empty(), "@step after source lines");
                single.steps.push_back(step(rest(6)));
            } else {
                require(mode == Mode::group, "@step outside a case");
                if (consumed) {
                    variants.clear();
                    consumed = false;
                }
                if (variants.empty())
                    variants.push_back({});
                variants.back().steps.push_back(step(rest(6)));
            }
        } else {
            require(line[0] != '@', "unknown directive");
            if (mode == Mode::single) {
                body.push_back(expand(line));
                continue;
            }
            require(mode == Mode::group && !variants.empty(), "source line outside a configured case");
            consumed = true;
            for (const auto &variant : variants) {
                Case item;
                item.name = label + (variant.name.empty() ? "" : "/" + variant.name) + " " + line;
                item.source = variant.prefix + expand(line) + variant.suffix;
                item.snippet = variant.prefix.size();
                item.steps = variant.steps;
                finish(item);
                out.push_back(std::move(item));
            }
        }
    }
    flush();
    return out;
}

Stop stopNamed(const std::string &name) {
    static const std::map<std::string, Stop> stops{{"semicolon", Stop::semicolon},
                                                   {"close_parenthesis", Stop::close_parenthesis},
                                                   {"assignment", Stop::assignment},
                                                   {"constructor_braces", Stop::constructor_braces},
                                                   {"body", Stop::body},
                                                   {"type", Stop::type},
                                                   {"function", Stop::function},
                                                   {"method", Stop::method},
                                                   {"constructor", Stop::constructor},
                                                   {"field", Stop::field},
                                                   {"preamble", Stop::preamble},
                                                   {"enum_definition", Stop::enum_definition},
                                                   {"module_definition", Stop::module_definition}};
    if (const auto found = stops.find(name); found != stops.end())
        return found->second;
    // Raw steps may name an out-of-range wire value.
    require(!name.empty() && name.find_first_not_of("-0123456789") == std::string::npos, "unknown stop " + name);
    return static_cast<Stop>(std::stoll(name));
}
class Options {
    const Step &step;
    std::set<std::string> used;

public:
    explicit Options(const Step &value) : step(value) {
    }
    std::optional<std::string> get(const std::string &key) {
        used.insert(key);
        const auto found = step.options.find(key);
        return found == step.options.end() ? std::nullopt : std::optional(found->second);
    }
    std::string text(const std::string &key, const std::string &fallback) {
        return get(key).value_or(fallback);
    }
    std::int64_t integer(const std::string &key, std::int64_t fallback = 0) {
        const auto value = get(key);
        return value ? std::stoll(*value) : fallback;
    }
    bool flag(const std::string &key) {
        const auto value = get(key);
        require(!value || value->empty(), "flag " + key + " takes no value");
        return bool(value);
    }
    template <std::size_t N> std::array<std::int64_t, N> integers(const std::string &key) {
        std::array<std::int64_t, N> out{};
        if (const auto value = get(key)) {
            const auto parts = split(*value, ',');
            require(parts.size() == N, "option " + key + " needs " + std::to_string(N) + " words");
            for (std::size_t index = 0; index < N; ++index)
                out[index] = std::stoll(parts[index]);
        }
        return out;
    }
    void done() const {
        for (const auto &[key, value] : step.options)
            require(used.contains(key), "unknown option " + key + " for " + step.mode);
    }
};
std::size_t tokenFrom(const std::vector<aurora::Token> &tokens, std::size_t offset) {
    for (std::size_t index = 0; index < tokens.size(); ++index)
        if (tokens[index].span.begin.offset >= offset)
            return index;
    throw std::runtime_error(context + ": no token at offset " + std::to_string(offset));
}
Context capture(Options &options, const std::vector<aurora::Token> &tokens) {
    Context out;
    const auto find = [&](const std::string &key, std::vector<aurora::Token> &into) {
        if (const auto value = options.get(key))
            for (const auto &name : split(*value, ',')) {
                const auto found = std::find_if(tokens.begin(), tokens.end(), [&](const auto &token) {
                    return token.text == name;
                });
                require(found != tokens.end(), "context names no source token " + name);
                into.push_back(*found);
            }
    };
    find("types", out.typeParameters);
    find("caps", out.capacityParameters);
    out.functionTemplate = options.flag("fn");
    return out;
}
bool sameTokens(const std::vector<aurora::Token> &a, const std::vector<aurora::Token> &b) {
    const auto position = [](const aurora::SourcePosition &left, const aurora::SourcePosition &right) {
        return left.offset == right.offset && left.line == right.line && left.column == right.column;
    };
    return a.size() == b.size() && std::equal(a.begin(), a.end(), b.begin(), [&](const auto &left, const auto &right) {
               return left.text == right.text && left.line == right.line && left.span.source == right.span.source &&
                      position(left.span.begin, right.span.begin) && position(left.span.end, right.span.end);
           });
}

// Raw step: the copied private ABI record through the checked entry, every
// copied record, optional admission and arena re-entry, then exact cleanup.
void rawStep(Lines &lines, const Case &item, Options &options) {
    const auto stop = stopNamed(options.text("stop", "semicolon"));
    const auto offset = options.integer("offset");
    const auto typeContext = options.integers<7>("rawctx");
    const auto enumCount = options.integer("count");
    const bool admit = options.flag("admit"), reuse = options.flag("reuse");
    const auto configuration = options.get("config") ? options.integers<6>("config") : admissionConfiguration;
    options.done();
    Allocations allocations;
    RawArena arena(allocations);
    const auto result = arena.parse(item.source, stop, offset, typeContext, enumCount);
    const auto records = [&] {
        Lines out;
        for (std::int64_t index = 0; index < result[2]; ++index)
            out.push_back("  node " + words(arena.read(index)));
        for (std::int64_t index = 0; index < arena.edges(); ++index)
            out.push_back("  edge " + words(arena.edge(index)));
        for (std::int64_t index = 0; index < arena.types(); ++index)
            out.push_back("  type " + words(arena.type(index)));
        for (std::int64_t index = 0; index < arena.syntaxCount(); ++index)
            out.push_back("  syntax " + words(arena.syntax(index)));
        return out;
    };
    const auto committed = records();
    lines.push_back("raw " + words(result));
    lines.insert(lines.end(), committed.begin(), committed.end());
    if (result[0] == wire(Status::success)) {
        const auto metrics = arena.metrics();
        require(metrics.live_allocations == 5 && metrics.peak_live_allocations == 5,
                "raw parse changed the five arena owners");
        if (admit)
            lines.push_back("  admit " + words(arena.admit(item.source, result[1], configuration)));
        if (reuse) {
            const auto before = arena.metrics().successful_allocations;
            lines.push_back("  reuse " + words(arena.parse(item.source, stop, offset, typeContext, enumCount)));
            require(records() == committed && arena.metrics().successful_allocations == before,
                    "rejected arena re-entry changed or grew committed records");
        }
    }
    arena.finish();
    require(allocations.successful == allocations.released, "raw parse leaked an owner");
}

void runStep(Lines &lines,
             const Case &item,
             const Step &step,
             const std::vector<aurora::Token> &tokens,
             Cursor &next,
             bool &haveNext) {
    Options options(step);
    if (step.mode == "raw") {
        rawStep(lines, item, options);
        return;
    }
    Cursor start;
    const auto at = options.text("at", "0");
    if (at == "next") {
        require(haveNext, "at=next without a previous cursor");
        start = next;
    } else if (at == "snippet") {
        start.ordinal = tokenFrom(tokens, item.snippet);
    } else if (at.starts_with("^")) {
        start.ordinal = tokenFrom(tokens, item.markers.at(std::stoul(at.substr(1)) - 1));
    } else {
        start.ordinal = std::stoul(at);
    }
    const auto typeContext = capture(options, tokens);
    const auto stop = options.get("stop");
    const auto enumCount = options.get("count");
    options.done();
    const auto &mode = step.mode;
    require((!stop || mode == "expr" || mode == "callable") && (!enumCount || mode == "enum"),
            "stop or count option does not apply to this step");
    const auto advance = [&](const Cursor &value) {
        next = value;
        haveNext = true;
        return cursor(value);
    };
    try {
        if (mode == "expr" || mode == "body") {
            require(start.half == 0, "expression or body cursor cannot begin at a half token");
            std::size_t position = start.ordinal;
            try {
                if (mode == "expr") {
                    const auto parsed = aurora::parseHostedExpression(
                        tokens, position, stopNamed(stop.value_or("semicolon")), typeContext);
                    lines.push_back("expr " + advance(Cursor{position}) + " " + expression(parsed));
                } else {
                    require(!stop, "body takes no stop");
                    const auto parsed = aurora::parseHostedBody(tokens, position, typeContext);
                    lines.push_back("body " + advance(Cursor{position}));
                    for (const auto &value : parsed) {
                        std::string text = "  ";
                        statement(text, value);
                        lines.push_back(text);
                    }
                }
            } catch (const aurora::Error &) {
                require(position == start.ordinal, "rejected parse committed its caller cursor");
                throw;
            }
        } else if (mode == "type") {
            const auto parsed = aurora::parseHostedType(tokens, start, typeContext);
            lines.push_back("type " + advance(parsed.next) + " " + type(parsed.type));
        } else if (mode == "callable") {
            const auto parsed = aurora::parseHostedCallable(tokens, start, stopNamed(stop.value()), typeContext);
            lines.push_back("callable " + advance(parsed.next));
            function(lines, "  ", "function", parsed.function);
        } else if (mode == "field") {
            const auto parsed = aurora::parseHostedField(tokens, start, typeContext);
            lines.push_back("field " + advance(parsed.next));
            lines.push_back("  " + field(parsed.field));
        } else if (mode == "preamble") {
            const auto parsed = aurora::parseHostedPreamble(tokens, start);
            lines.push_back("preamble " + advance(parsed.next));
            Lines body;
            program(body, parsed.program);
            for (const auto &line : body)
                lines.push_back("  " + line);
        } else if (mode == "enum") {
            const auto parsed = aurora::parseHostedEnum(tokens, start, std::stoul(enumCount.value_or("0")));
            lines.push_back("enum " + advance(parsed.next) + " " + enumeration(parsed.definition));
        } else if (mode == "program" || mode == "parser") {
            const auto parsed = mode == "program" ? aurora::parseHostedProgram(tokens) : aurora::Parser(tokens).parse();
            lines.push_back(mode);
            Lines body;
            program(body, parsed);
            for (const auto &line : body)
                lines.push_back("  " + line);
        } else if (mode == "resolve") {
            aurora::HostedResolution resolution;
            const auto module = resolution.add(dumpSource);
            static_cast<void>(resolution.resolve({module.id}, module.id));
            lines.push_back("resolve ok");
        } else {
            require(false, "unknown step mode " + mode);
        }
    } catch (const aurora::Error &error) {
        lines.push_back(mode + " " + diagnostic(error.diagnostic));
    }
}

Lines run(const Case &item) {
    dumpSource = std::make_shared<const aurora::SourceText>("case.au", item.source);
    dumpPositions = positionsOf(item.source);
    Lines lines;
    std::vector<aurora::Token> tokens;
    try {
        tokens = aurora::lex(dumpSource);
    } catch (const aurora::Error &error) {
        lines.push_back("lex " + diagnostic(error.diagnostic));
        return lines;
    }
    const auto before = tokens;
    Cursor next;
    bool haveNext = false;
    for (const auto &step : item.steps) {
        context = item.name + " [" + step.mode + "]";
        runStep(lines, item, step, tokens, next, haveNext);
        require(sameTokens(tokens, before), "parse changed its caller tokens");
    }
    require(dumpSource->text == item.source, "parse changed its source snapshot");
    return lines;
}

std::string chain(std::size_t count) {
    std::string out = "1";
    while (--count)
        out += "+1";
    return out;
}
std::string enumSource(std::size_t width) {
    std::string source = "enum class Wide{";
    for (std::size_t index = 0; index < width; ++index)
        source += (index ? "," : "") + std::string("case_") + std::to_string(index);
    return source + "};";
}
// Golden file: a case name line, then its dump lines indented by two spaces.
class Golden {
    std::map<std::string, Lines> expected;
    std::vector<std::pair<std::string, Lines>> produced;
    std::set<std::string> names;
    std::vector<std::string> failures;
    bool updating;

public:
    Golden(const std::string &path, bool update) : updating(update) {
        if (updating)
            return;
        std::ifstream file(path);
        require(file.good(), "cannot open golden file " + path);
        Lines *current = nullptr;
        for (std::string line; std::getline(file, line);) {
            if (line.starts_with("  ")) {
                require(current, "golden dump line before its case name");
                current->push_back(line.substr(2));
            } else {
                require(!line.empty() && !expected.contains(line), "empty or repeated golden case " + line);
                current = &expected[line];
            }
        }
    }
    void check(const std::string &name, Lines lines) {
        context = name;
        require(names.insert(name).second, "repeated case name");
        ++cases;
        if (!updating) {
            const auto found = expected.find(name);
            if (found == expected.end())
                failures.push_back(name + ": missing from the golden file");
            else if (found->second != lines) {
                std::size_t index = 0;
                while (index < lines.size() && index < found->second.size() && lines[index] == found->second[index])
                    ++index;
                failures.push_back(name + ": line " + std::to_string(index + 1) + " got '" +
                                   (index < lines.size() ? lines[index] : "<end>") + "', expected '" +
                                   (index < found->second.size() ? found->second[index] : "<end>") + "'");
            }
        }
        produced.emplace_back(name, std::move(lines));
    }
    void finish(const std::string &path) {
        context = "golden";
        if (updating) {
            std::ofstream file(path);
            for (const auto &[name, lines] : produced) {
                file << name << '\n';
                for (const auto &line : lines)
                    file << "  " << line << '\n';
            }
            require(file.good(), "cannot write golden file " + path);
            return;
        }
        for (const auto &[name, lines] : expected)
            if (!names.contains(name))
                failures.push_back(name + ": golden case was not produced");
        for (std::size_t index = 0; index < failures.size() && index < 20; ++index)
            std::cerr << "FAIL " << failures[index] << '\n';
        require(failures.empty(), std::to_string(failures.size()) + " cases differ from the golden file");
    }
};

// Unresolved syntax comparisons stay above. The production boundary below is
// independently checked typed IR, optional ABI observations and source-backed
// diagnostics; no fixture reconstructs a resolved Program.
template <class Module>
const aurora::ir::FunctionBody &
typedFunction(const Module &module, const aurora::ir::Metadata &metadata, const std::string &name) {
    const auto found = std::find_if(module.functions.begin(), module.functions.end(), [&](const auto &function) {
        return metadata.callable(function.callableId).name() == name;
    });
    require(found != module.functions.end(), "typed function was omitted: " + name);
    return *found;
}
template <class Instruction> std::vector<Instruction> typedInstructions(const aurora::ir::FunctionBody &function) {
    std::vector<Instruction> result;
    for (const auto &instruction : function.code)
        if (const auto *value = std::get_if<Instruction>(&instruction))
            result.push_back(*value);
    return result;
}
std::string spanText(const aurora::SourceSpan &span) {
    require(span.source && span.begin.offset <= span.end.offset && span.end.offset <= span.source->text.size(),
            "diagnostic source span escaped its immutable source");
    return span.source->text.substr(span.begin.offset, span.end.offset - span.begin.offset);
}
bool nominalViews(const aurora::ir::Metadata &metadata, const std::map<int, std::set<int>> &expected) {
    if (metadata.scopeCount() != expected.size())
        return false;
    auto scope = expected.begin();
    for (std::size_t index = 0; index < metadata.scopeCount(); ++index, ++scope) {
        if (metadata.scopeAt(index) != scope->first)
            return false;
        auto descriptor = scope->second.begin();
        for (const auto id : metadata.visibleDescriptors(scope->first))
            if (id >= 100 && id < 1000000) {
                if (descriptor == scope->second.end() || *descriptor != id)
                    return false;
                ++descriptor;
            }
        if (descriptor != scope->second.end())
            return false;
    }
    return true;
}
void constantReturn(const aurora::ir::FunctionBody &function, aurora::ir::CallableView callable, std::int64_t value) {
    require(callable.result() == aurora::Type::I64 && callable.parameters().empty() && function.code.size() == 2 &&
                std::holds_alternative<aurora::ir::Constant>(function.code[0]) &&
                std::get<aurora::ir::Constant>(function.code[0]).value == value &&
                std::get<aurora::ir::Constant>(function.code[0]).type == aurora::Type::I64 &&
                std::holds_alternative<aurora::ir::Return>(function.code[1]),
            "concrete value/reflection return differs");
}
void resolvedModules() {
    context = "typed module instances, nominal authority, layout and source ownership";
    auto dependency =
        std::make_shared<const aurora::SourceText>("definitions.au",
                                                   "// unused trivia keeps sparse source requests apart\n"
                                                   "export module dep;\n"
                                                   "export namespace lib {\n"
                                                   "enum class Flag {cold,hot};\n"
                                                   "class Leaf {public:i64 value;};\n"
                                                   "template<Scalar T,i64 N> class Buffer {\n"
                                                   "  builtin::array<T,N> data;\n"
                                                   "public:Buffer():data{}{}\n"
                                                   "  auto size()const->i64 {return N;}\n"
                                                   "  auto own_size()const->i64 {return size_of(Buffer);}\n"
                                                   "};\n"
                                                   "template<Value T> auto measure()->i64 {return size_of(T);}\n"
                                                   "}\n");
    auto root = std::make_shared<const aurora::SourceText>(
        "requests.au",
        "module root;import dep // import gap\n ;\n"
        "class Hidden {public:i64 value;};\n"
        "enum class State {zero,one};\n"
        "auto answer()->i64 {\n"
        "  const lib::Buffer<u8,3> first=lib // call gap\n :: Buffer<u8,3>();\n"
        "  const lib::Buffer<u8,4> second=lib::Buffer<u8,4>();\n"
        "  const lib::Buffer<u8,3> again=lib::Buffer<u8,3>();\n"
        "  const State state=State::one;\n"
        "  return lib::measure<Hidden>()+lib::measure<State>()+lib::measure<Hidden>();\n"
        "}\n");
    auto rootTokens = aurora::lex(root);
    const auto resolved = [&] {
        aurora::HostedResolution resolution;
        // Arrival order deliberately differs from dependency/output order.
        const auto main = resolution.add(root), imported = resolution.add(dependency);
        require(main.id != imported.id && main.moduleName == "root" && !main.interfaceUnit &&
                    main.imports.size() == 1 && main.imports.front().text == "dep" && imported.moduleName == "dep" &&
                    imported.interfaceUnit && imported.imports.empty(),
                "copied module header/import identity differs");
        require(sameTokens({main.imports.front()}, {rootTokens.at(4)}), "copied import token differs from its source");
        return resolution.resolve({imported.id, main.id}, main.id, aurora::AnalysisMode::Lint, true);
    }();
    const auto &module = resolved.module.get();
    const auto &metadata = resolved.module.metadata();
    const auto &abi = resolved.abiDeclarations;
    const std::string hidden = "__au_c_m1_4root_n0__d6Hidden", state = "__au_e_m1_4root_n0__d5State";
    const std::string leaf = "__au_c_m1_3dep_n1_3lib_d4Leaf", flag = "__au_e_m1_3dep_n1_3lib_d4Flag";
    const std::array<std::string, 2> buffers{"__au_c_m1_3dep_n1_3lib_d6Buffer_t2_u8_v3",
                                             "__au_c_m1_3dep_n1_3lib_d6Buffer_t2_u8_v4"};
    const std::array<std::string, 2> measures{"__au_g_m1_3dep_n1_3lib_d7measure_t1_c28__au_c_m1_4root_n0__d6Hidden",
                                              "__au_g_m1_3dep_n1_3lib_d7measure_t1_e27__au_e_m1_4root_n0__d5State"};
    // Validated IR prunes unused imported implementations; source ABI metadata
    // retains every resolved declaration of this fixture.
    const std::array<std::string, 5> retained{measures[0],
                                              measures[1],
                                              "answer",
                                              "__au_k_m1_3dep_n2_3lib6Buffer_d6Buffer_t2_u8_v3",
                                              "__au_k_m1_3dep_n2_3lib6Buffer_d6Buffer_t2_u8_v4"};
    require(module.functions.size() == retained.size() && metadata.classCount() == 4 && metadata.enumCount() == 2 &&
                abi.records.size() == 4 && abi.enums.size() == 2 && abi.functions.size() == 9,
            "typed output duplicated concrete instances or lost declarations");
    for (std::size_t index = 0; index < retained.size(); ++index)
        require(metadata.callable(module.functions[index].callableId).name() == retained[index],
                "retained concrete function order differs");
    for (std::size_t index = 0; index < metadata.classCount(); ++index)
        require(!metadata.isCarrier(metadata.classAt(index)), "typed output added an array carrier");
    const auto definitionSyntax = aurora::parseHostedProgram(aurora::lex(dependency));
    const auto &bufferSyntax = definitionSyntax.templates.at(0);
    require(bufferSyntax.methods.size() == 3, "source Buffer method inventory differs");
    require(abi.records.at(leaf).sourceName == "lib::Leaf" && abi.records.at(hidden).sourceName == "Hidden" &&
                abi.records.at(leaf).members == std::vector<std::string>{"value"} &&
                abi.records.at(hidden).members == std::vector<std::string>{"value"} &&
                abi.enums.at(flag).members == std::vector<std::string>{"cold", "hot"} &&
                abi.enums.at(state).members == std::vector<std::string>{"zero", "one"} &&
                metadata.enumCases(metadata.findEnum(flag).value()) == 2 &&
                metadata.enumCases(metadata.findEnum(state).value()) == 2,
            "source ABI field/case order or concrete enum identity differs");
    for (std::size_t index = 0; index < measures.size(); ++index) {
        const auto &function = module.functions.at(index);
        const auto callable = metadata.callable(function.callableId);
        require(callable.name() == measures[index] && callable.moduleScope() == 1 && !callable.receiver() &&
                    abi.functions.at(callable.name()).sourceName == "lib::measure",
                "function instance order, exact nominal identity or defining module differs");
        constantReturn(function, callable, 8);
    }
    for (std::size_t index = 0; index < buffers.size(); ++index) {
        const auto capacity = static_cast<int>(index + 3);
        const auto id = metadata.findClass(buffers[index]).value();
        const auto fields = metadata.fields(id);
        const auto leaves = metadata.leaves(id);
        const auto storage = metadata.storage(id);
        require(abi.records.at(buffers[index]).sourceName == "lib::Buffer" &&
                    abi.records.at(buffers[index]).members == std::vector<std::string>{"data"} &&
                    leaves.size() == static_cast<std::size_t>(capacity) &&
                    std::all_of(leaves.begin(),
                                leaves.end(),
                                [](const auto &type) {
                                    return type == aurora::Type::U8;
                                }) &&
                    fields.size() == 1 && fields[0].elementType == aurora::Type::U8 && fields[0].firstLeaf == 0 &&
                    fields[0].length == capacity && fields[0].array && fields[0].elementCount == 1 &&
                    storage.sizeBytes == capacity && storage.alignment == 1 && storage.reservedBytes == 8 &&
                    storage.fieldOffsets.size() == 1 && storage.fieldOffsets.at(0) == 0,
                "concrete array instance lost its packed byte layout or ordered field metadata");
        const std::array<std::string, 3> names{
            "__au_k_m1_3dep_n2_3lib6Buffer_d6Buffer_t2_u8_v" + std::to_string(capacity),
            "__au_m_m1_3dep_n2_3lib6Buffer_d4size_t2_u8_v" + std::to_string(capacity),
            "__au_m_m1_3dep_n2_3lib6Buffer_d8own_size_t2_u8_v" + std::to_string(capacity)};
        const std::array<std::string, 3> sourceNames{"lib::Buffer", "lib::size", "lib::own_size"};
        for (std::size_t method = 0; method < names.size(); ++method) {
            const auto &source = bufferSyntax.methods[method];
            require(abi.functions.at(names[method]).sourceName == sourceNames[method] &&
                        abi.functions.at(names[method]).members.empty() && source.params.empty() &&
                        source.result == aurora::Type::I64 && source.constructor == (method == 0) &&
                        source.receiverConst == (method != 0) && source.publicAccess,
                    "method/constructor ABI identity or original source signature differs");
            if (method)
                require(std::none_of(module.functions.begin(),
                                     module.functions.end(),
                                     [&](const auto &function) {
                                         return metadata.callable(function.callableId).name() == names[method];
                                     }),
                        "unused imported getter escaped validated-IR pruning");
        }
        const auto &constructor = typedFunction(module, metadata, names[0]);
        const auto callable = metadata.callable(constructor.callableId);
        require(callable.moduleScope() == 1 && callable.receiver() &&
                    callable.receiver()->className == buffers[index] && callable.receiver()->constructor &&
                    callable.receiver()->mutableValue && callable.receiver()->publicAccess &&
                    callable.parameters().empty() && callable.result() == aurora::Type::I64 &&
                    constructor.code.size() == 3 &&
                    std::holds_alternative<aurora::ir::ReceiverArrayZero>(constructor.code[0]) &&
                    std::get<aurora::ir::ReceiverArrayZero>(constructor.code[0]).fieldIndex == 0 &&
                    std::holds_alternative<aurora::ir::Constant>(constructor.code[1]) &&
                    std::get<aurora::ir::Constant>(constructor.code[1]).value == 0 &&
                    std::holds_alternative<aurora::ir::Return>(constructor.code[2]),
                "concrete constructor lost its empty-array initialization");
    }
    const auto &answer = module.functions.at(2);
    const auto answerCallable = metadata.callable(answer.callableId);
    require(answerCallable.name() == "answer" && answerCallable.moduleScope() == 0 && !answerCallable.receiver(),
            "root callable identity or dependency order differs");
    const auto constructors = typedInstructions<aurora::ir::MethodCallObservation>(answer);
    require(constructors.size() == 3 && constructors[0].callee == constructors[2].callee &&
                constructors[0].callee == "__au_k_m1_3dep_n2_3lib6Buffer_d6Buffer_t2_u8_v3" &&
                constructors[1].callee == "__au_k_m1_3dep_n2_3lib6Buffer_d6Buffer_t2_u8_v4" &&
                constructors[0].receiverOffset != constructors[2].receiverOffset,
            "repeated constructions lost interned targets or independent object storage");
    const auto calls = typedInstructions<aurora::ir::Call>(answer);
    require(calls.size() == 3 && calls[0].callee == measures[0] && calls[1].callee == measures[1] &&
                calls[2].callee == measures[0],
            "typed calls lost repeated concrete-instance identity or source order");
    const auto enumValues = typedInstructions<aurora::ir::EnumConstant>(answer);
    require(enumValues.size() == 1 && enumValues[0].type.isEnum() && enumValues[0].type.className == state &&
                enumValues[0].caseIndex == 1,
            "typed enum expression lost its nominal identity or declaration ordinal");
    require(nominalViews(metadata, {{0, {100, 101, 102, 103, 104, 105}}, {1, {100, 101, 102, 104}}}),
            "template argument authority leaked into runtime reflection views");
    require(resolved.lintDiagnostics.size() == 1 &&
                resolved.lintDiagnostics[0].code == aurora::DiagnosticCode::UnreadLocal &&
                resolved.lintDiagnostics[0].message == "local binding 'state' is never read" &&
                resolved.lintDiagnostics[0].severity == aurora::DiagnosticSeverity::Warning,
            "typed root-only lint lost its scalar binding or diagnostic contract");
    const std::weak_ptr<const aurora::SourceText> retainedRoot = root;
    root.reset();
    rootTokens.clear();
    require(!retainedRoot.expired() && resolved.lintDiagnostics[0].span.source == retainedRoot.lock() &&
                spanText(resolved.lintDiagnostics[0].span) == "state",
            "typed lint lost immutable source ownership after Session cleanup");
    ++cases;
}

void resolvedVisibility() {
    context = "typed overload selection and direct-import reflection views";
    const auto resolved = [] {
        aurora::HostedResolution resolution;
        const auto root = resolution.add(std::make_shared<const aurora::SourceText>(
            "call.au", "module caller;import functions;auto answer()->i64{return choose(42);}"));
        const auto functions = resolution.add(
            std::make_shared<const aurora::SourceText>("functions.au",
                                                       "export module functions;import types;"
                                                       "export auto choose(Leaf value)->i64{return 1;}"
                                                       "export auto choose(i64 value)->i64{return value;}"
                                                       "auto choose(bool value)->i64{return 2;}"));
        const auto types = resolution.add(std::make_shared<const aurora::SourceText>(
            "types.au", "export module types;export class Leaf{public:i64 value;};class Hidden{public:i64 value;};"));
        return resolution.resolve({types.id, functions.id, root.id}, root.id, aurora::AnalysisMode::Check, true);
    }();
    const auto &module = resolved.module.get();
    const auto &metadata = resolved.module.metadata();
    const std::array<std::string, 3> overloads{"__au_o_m1_9functions_n0__d6choose_p1_295___au_c_m1_5types_n0__d4Leaf",
                                               "__au_o_m1_9functions_n0__d6choose_p1_20_",
                                               "__au_o_m1_9functions_n0__d6choose_p1_21_"};
    require(module.functions.size() == 2, "selected overload/root count differs");
    const auto selected = metadata.callable(module.functions[0].callableId);
    const auto answer = metadata.callable(module.functions[1].callableId);
    require(selected.name() == overloads[1] && selected.moduleScope() == 2 && selected.parameters().size() == 1 &&
                selected.parameters().front() == aurora::Type::I64 && answer.name() == "answer" &&
                answer.moduleScope() == 0 && resolved.abiDeclarations.functions.size() == 4 &&
                resolved.abiDeclarations.functions.at("answer").sourceName == "answer",
            "selected overload/root order or pre-pruning ABI inventory differs");
    for (std::size_t index = 0; index < overloads.size(); ++index) {
        require(resolved.abiDeclarations.functions.at(overloads[index]).sourceName == "choose",
                "overload parameter-tuple ABI identity differs");
        if (index != 1)
            require(std::none_of(module.functions.begin(),
                                 module.functions.end(),
                                 [&](const auto &function) {
                                     return metadata.callable(function.callableId).name() == overloads[index];
                                 }),
                    "unselected imported overload escaped validated-IR pruning");
    }
    const auto calls = typedInstructions<aurora::ir::Call>(module.functions.back());
    require(calls.size() == 1 && calls[0].callee == overloads[1],
            "typed overload selection chose a hidden or signature-inaccessible candidate");
    require(nominalViews(metadata, {{0, {}}, {1, {100, 101}}, {2, {100}}}),
            "reflection views lost an empty scope or granted private/transitive nominal types");
    ++cases;

    context = "private overload is not callable through a direct import";
    const auto rootSource = std::make_shared<const aurora::SourceText>(
        "private-call.au", "module caller;import functions;auto answer()->i64{return choose(true);}");
    std::optional<aurora::Diagnostic> rejected;
    try {
        aurora::HostedResolution resolution;
        const auto root = resolution.add(rootSource);
        const auto functions = resolution.add(std::make_shared<const aurora::SourceText>(
            "private-functions.au",
            "export module functions;export auto choose(i64 value)->i64{return value;}"
            "auto choose(bool value)->i64{return 2;}"));
        static_cast<void>(resolution.resolve({functions.id, root.id}, root.id));
    } catch (const aurora::Error &error) {
        rejected = error.diagnostic;
    }
    require(rejected && rejected->code == aurora::DiagnosticCode::Semantic &&
                rejected->message == "no exact ordinary overload for choose" && rejected->span.source == rootSource &&
                spanText(rejected->span) == "choose",
            "private overload rejection lost its exact typed decision or caller span");
    ++cases;

    context = "empty module views and returned lint source lifetime";
    std::weak_ptr<const aurora::SourceText> retained;
    const auto empty = [&] {
        aurora::HostedResolution resolution;
        auto source = std::make_shared<const aurora::SourceText>(
            "empty-view-root.au", "module caller;import empty;auto answer()->i64{const i64 unused=7;return 42;}");
        retained = source;
        const auto root = resolution.add(source);
        const auto imported =
            resolution.add(std::make_shared<const aurora::SourceText>("empty.au", "export module empty;"));
        return resolution.resolve({imported.id, root.id}, root.id, aurora::AnalysisMode::Lint);
    }();
    require(nominalViews(empty.module.metadata(), {{0, {}}, {1, {}}}) && empty.abiDeclarations.records.empty() &&
                empty.abiDeclarations.enums.empty() && empty.abiDeclarations.functions.empty() &&
                empty.lintDiagnostics.size() == 1 && !retained.expired() &&
                empty.lintDiagnostics[0].span.source == retained.lock() &&
                spanText(empty.lintDiagnostics[0].span) == "unused" &&
                empty.lintDiagnostics[0].span.source->path == "empty-view-root.au",
            "typed cleanup omitted empty views, ignored optional ABI collection or invalidated lint sources");
    ++cases;

    context = "instantiated template diagnostic retains its definition source";
    std::weak_ptr<const aurora::SourceText> definition;
    rejected.reset();
    try {
        aurora::HostedResolution resolution;
        auto source = std::make_shared<const aurora::SourceText>(
            "template-error.au", "export module dep;export template<Value T> auto bad()->i64{return true;}");
        definition = source;
        const auto imported = resolution.add(source);
        const auto root = resolution.add(
            std::make_shared<const aurora::SourceText>("template-request.au",
                                                       "module caller;import dep;class Hidden{public:i64 value;};"
                                                       "auto answer()->i64{return bad<Hidden>();}"));
        static_cast<void>(resolution.resolve({imported.id, root.id}, root.id));
    } catch (const aurora::Error &error) {
        rejected = error.diagnostic;
    }
    require(rejected && rejected->code == aurora::DiagnosticCode::Semantic &&
                rejected->message == "expected i64, got bool" && !definition.expired() &&
                rejected->span.source == definition.lock() && spanText(rejected->span) == "return" &&
                rejected->span.source->path == "template-error.au",
            "template semantic diagnostic lost original definition ownership or exact span");
    ++cases;
}

void resolvedLinkageNames() {
    context = "exact linkage ordinals, ordered overload tuples and nested nominal suffixes";
    const auto resolved = [] {
        aurora::HostedResolution resolution;
        const auto root = resolution.add(std::make_shared<const aurora::SourceText>(
            "linkage.au",
            "module alpha // module gap\n . beta;namespace ns {"
            "enum class E {one};class C {public:i64 value;};"
            "template<Value T,Value U> class Pair {public:T first;U second;"
            "Pair(T a,U b):first(a),second(b){}};"
            "template<Value T> class Box {public:T value;Box(T item):value(item){}};"
            "template<Value T> auto measure()->i64{return size_of(T);}"
            "auto choose(i64 value)->i64{return 0;}auto choose(bool value)->i64{return 0;}"
            "auto choose(u64 value)->i64{return 0;}auto choose(u8 value)->i64{return 0;}"
            "auto choose(C value)->i64{return 0;}auto choose(E value)->i64{return 0;}"
            "auto choose(builtin::span<const u8> value)->i64{return 0;}"
            "auto order(i64 a,bool b)->i64{return a;}auto order(bool a,i64 b)->bool{return a;}"
            "}auto answer()->i64{return ns::measure<ns::Box<ns::Pair<ns::C,ns::E>>>();}"));
        return resolution.resolve({root.id}, root.id, aurora::AnalysisMode::Check, true);
    }();
    const auto &abi = resolved.abiDeclarations;
    const std::string base = "_m2_5alpha4beta_n1_2ns_d";
    const std::string className = "__au_c" + base + "1C", enumName = "__au_e" + base + "1E";
    for (const auto &component :
         std::vector<std::string>{"0_", "1_", "7_", "10_", "5_" + className, "9_" + enumName, "11_"}) {
        const auto name = "__au_o" + base + "6choose_p1_" + std::to_string(component.size()) + component;
        require(abi.functions.contains(name),
                "overload serialized a resolved-kind ordinal or changed nominal spelling");
    }
    require(abi.functions.contains("__au_o" + base + "5order_p2_20_21_") &&
                abi.functions.contains("__au_o" + base + "5order_p2_21_20_"),
            "overload reordered parameters or serialized its return type");
    const auto nominal = [](const std::string &name) {
        return "_c" + std::to_string(name.size()) + name;
    };
    const auto enumeration = "_e" + std::to_string(enumName.size()) + enumName;
    const auto pair = "__au_c" + base + "4Pair_t2" + nominal(className) + enumeration;
    const auto box = "__au_c" + base + "3Box_t1" + nominal(pair);
    const auto measure = "__au_g" + base + "7measure_t1" + nominal(box);
    require(abi.records.contains(pair) && abi.records.contains(box) && abi.functions.contains(measure) &&
                abi.functions.contains("answer"),
            "nested instance inherited prototype cache or changed root spelling");
    ++cases;
}

template <class Record> class GuardedRecord {
public:
    std::uint64_t before = canary;
    Record value;
    std::uint64_t after = canary;
    void check() const {
        require(before == canary && after == canary, "generated record write escaped its ABI extent");
    }
};

// Both owning inputs are constructed directly in their final transfer slots.
// Only generated scalar fields and copied readbacks are inspected by the host.
class RawResolution {
    aurora::hosted::bytes::Region region;
    std::array<GuardedRecord<aurora::hosted_abi::ResolverIngest>, 2> slots;
    std::size_t active = 0;
    bool owner = false, pair = false;

public:
    bool transferred = false;
    explicit RawResolution(Allocations &allocations) : region(32 * 1024 * 1024, allocations.allocator()) {
        static_assert(
            offsetof(aurora::hosted_abi::ResolverRelease, session) ==
                offsetof(aurora::hosted_abi::ResolverIngest, session) &&
            sizeof(aurora::hosted_abi::ResolverRelease) == offsetof(aurora::hosted_abi::ResolverIngest, parsed) &&
            offsetof(aurora::hosted_abi::ResolverReleasePair, parsed) ==
                offsetof(aurora::hosted_abi::ResolverIngest, parsed) &&
            sizeof(aurora::hosted_abi::ResolverReleasePair) == offsetof(aurora::hosted_abi::ResolverIngest, module));
        for (auto &slot : slots)
            slot.value.region = region.id();
        aurora::hosted_abi::ResolverCreate input;
        input.region = region.id();
        checked_hosted_resolver_create(&input, data());
        owner = true;
        guards();
    }
    ~RawResolution() {
        if (owner) {
            if (pair)
                checked_hosted_resolver_release_pair(&slots[active].value);
            else
                checked_hosted_resolver_release(&slots[active].value);
        }
    }
    RawResolution(const RawResolution &) = delete;
    RawResolution &operator=(const RawResolution &) = delete;
    void *data() {
        return slots[active].value.session.storage.data();
    }
    void guards() const {
        for (const auto &slot : slots)
            slot.check();
    }
    aurora::hosted_abi::compiler_resolver::SessionStatus status() {
        GuardedRecord<aurora::hosted_abi::compiler_resolver::SessionStatus> output;
        checked_hosted_resolver_status(data(), &output.value);
        output.check();
        guards();
        return output.value;
    }
    aurora::hosted_abi::compiler_resolver::MetaRow meta(std::int64_t index) {
        GuardedRecord<aurora::hosted_abi::compiler_resolver::MetaRow> output;
        checked_hosted_resolver_read_meta(data(), index, &output.value);
        output.check();
        guards();
        return output.value;
    }
    bool ingest(const std::string &source, bool invalidModule = false, bool invalidRoot = false) {
        using Storage = aurora::hosted_abi::compiler_resolver::StorageStatus;
        if (status().storage != Storage::none)
            return false;
        aurora::hosted_abi::ResolverSourceInput sourceInput;
        sourceInput.source.backing = source.data();
        sourceInput.source.length = static_cast<std::int64_t>(source.size());
        const auto module = checked_hosted_resolver_append_source(data(), &sourceInput);
        if (module < 0)
            return false;
        auto &record = slots[active].value;
        aurora::hosted_abi::ParserCreate create;
        create.region = region.id();
        create.capacity = 0;
        checked_hosted_parser_create(&create, record.parsed.storage.data());
        pair = true;
        aurora::hosted_abi::ParserInput input;
        input.source = sourceInput.source;
        input.cursor.line = 1;
        input.stop = Stop::module_definition;
        GuardedWords<6> parsed;
        checked_hosted_parser_parse(record.parsed.storage.data(), &input, parsed.value.data());
        parsed.check();
        guards();
        if (parsed.value[0] != wire(Status::success))
            return false;
        GuardedWords<14> admission;
        admission.value = {0,
                           static_cast<std::int64_t>(reinterpret_cast<std::uintptr_t>(source.data())),
                           0,
                           0,
                           0,
                           0,
                           static_cast<std::int64_t>(source.size()),
                           parsed.value[1]};
        std::copy(admissionConfiguration.begin(), admissionConfiguration.end(), admission.value.begin() + 8);
        GuardedWords<5> admitted;
        checked_hosted_parser_admit(record.parsed.storage.data(), admission.value.data(), admitted.value.data());
        admission.check();
        admitted.check();
        if (admitted.value[0] != wire(AdmissionStatus::success))
            return false;
        record.module = invalidModule ? module + 1 : module;
        record.root = invalidRoot ? -1 : parsed.value[1];
        const auto next = active ^ 1U;
        // A consuming call never has an armed input after transfer begins.
        owner = pair = false;
        checked_hosted_resolver_ingest(&record, slots[next].value.session.storage.data());
        active = next;
        owner = true;
        transferred = true;
        guards();
        return status().storage == Storage::none;
    }
    void finish() {
        require(owner, "resolution cleanup had no active returned owner");
        if (pair)
            checked_hosted_resolver_release_pair(&slots[active].value);
        else
            checked_hosted_resolver_release(&slots[active].value);
        owner = pair = false;
        guards();
        const auto final = region.metrics();
        require(final.used == 0 && final.live_allocations == 0 && final.releases == final.successful_allocations,
                "resolution transfer or pair cleanup leaked payload or owner metadata");
        require(region.close(), "released resolution region did not close");
    }
};

void rawModuleTraversal() {
    namespace Wire = aurora::hosted_abi::compiler_resolver;
    context = "source module traversal order, scratch and allocation cleanup";
    const auto execute = [](std::size_t allowance) {
        Allocations allocations;
        RawResolution resolution(allocations);
        for (const auto &text : {"module root;import alpha // import trivia\n . beta;import gamma;",
                                 "export module alpha.beta;import shared;",
                                 "export module shared;",
                                 "export module gamma;import shared;"})
            require(resolution.ingest(text), "graph fixture ingestion failed");
        const auto baseline = allocations.successful;
        if (allowance != std::numeric_limits<std::size_t>::max())
            allocations.allowed = baseline + allowance;
        GuardedRecord<Wire::WorkRow> result;
        aurora_hosted_resolver_graph_step(resolution.data(), 0, &result.value);
        result.check();
        const auto status = resolution.status();
        const auto used = allocations.successful - baseline;
        require(checked_hosted_resolver_count(resolution.data(), 4) == 0,
                "graph step retained scratch across host ingestion boundary");
        if (status.storage == Wire::StorageStatus::allocation) {
            require(result.value.value0 == -1, "graph allocation failure published completion");
        } else {
            require(status.storage == Wire::StorageStatus::none && result.value.value0 == 0,
                    "valid diamond graph did not complete");
            const std::array<std::int64_t, 4> orders{3, 1, 0, 2}, scopes{0, 2, 1, 3};
            for (std::size_t index = 0; index < orders.size(); ++index) {
                const auto unit = resolution.meta(static_cast<std::int64_t>(index));
                require(unit.value12 == orders[index] && unit.value13 == scopes[index] && unit.value14 == (index == 0),
                        "source graph changed dependency postorder or scope identity");
            }
        }
        resolution.finish();
        require(allocations.successful == allocations.released, "graph step leaked an owner");
        ++cases;
        return used;
    };
    // One representative out-of-memory case: refuse the step's final allocation.
    const auto allocations = execute(std::numeric_limits<std::size_t>::max());
    require(allocations > 0, "graph step performed no allocation");
    execute(allocations - 1);

    aurora::HostedResolution resolution;
    const auto root =
        resolution.add(std::make_shared<const aurora::SourceText>("root.au", "module root;auto f()->i64{return 0;}"));
    require(!resolution.nextImport(root.id), "empty graph requested an import");
    bool rejected = false;
    try {
        resolution.add(std::make_shared<const aurora::SourceText>("late.au", "export module late;"));
    } catch (const aurora::Error &) {
        rejected = true;
    }
    require(rejected, "completed source graph accepted a late module");
    ++cases;
}

void rawLinkageModes() {
    namespace Wire = aurora::hosted_abi::compiler_resolver;
    context = "every linkage mode including sealed seeds and cloned template names";
    Allocations allocations;
    RawResolution resolution(allocations);
    const auto text = [&](const std::string &spelling) {
        aurora::hosted_abi::ResolverTextInput input{};
        input.text.backing = spelling.data();
        input.text.length = static_cast<std::int64_t>(spelling.size());
        return aurora_hosted_resolver_append_text(resolution.data(), &input);
    };
    aurora::hosted_abi::ResolverSeedBuiltinInput seed{};
    seed.definition.value1 = text("builtin::Frozen");
    seed.definition.value3 = text("frozen_name");
    seed.definition.concrete_tag = Wire::ResolvedTypeKind::class_value;
    require(aurora_hosted_resolver_seed_builtin(resolution.data(), &seed) >= 0, "linkage seed rejected");
    require(resolution.ingest("module mode;namespace n {"
                              "enum class E{one};class C{i64 value;public:C():value(0){}"
                              "auto m()->i64{return value;}};"
                              "template<Scalar T> class Box{public:T value;};"
                              "template<Scalar T> auto g(T value)->T{return value;}"
                              "auto f()->i64{return 0;}auto v(C value)->i64{return 0;}"
                              "auto choose(i64 value)->i64{return 0;}auto choose(bool value)->i64{return 0;}"
                              "}auto answer()->i64{return n::g<i64>(1)+size_of(n::Box<i64>);}"),
            "linkage modes fixture failed ingestion");
    aurora::hosted_abi::ResolverOrderInput order{};
    order.root = 1;
    require(aurora_hosted_resolver_order_module(resolution.data(), &order) == 1 &&
                aurora_hosted_resolver_run(resolution.data()) == 0,
            "linkage modes fixture failed resolution");
    std::map<Wire::NativeMode, std::set<std::string>> actual;
    const auto count = checked_hosted_resolver_count(resolution.data(), 2);
    for (std::int64_t index = 0; index < count; ++index) {
        const auto symbol = resolution.meta(index);
        if (symbol.tag != Wire::MetaTag::symbol)
            continue;
        GuardedRecord<Wire::LinkageChunk> chunk;
        aurora_hosted_resolver_linkage_chunk(resolution.data(), index, 0, &chunk.value);
        chunk.check();
        require(chunk.value.byteCount > 0 && chunk.value.byteCount < 512, "mode cache was not finalized");
        actual[symbol.native_tag].emplace(reinterpret_cast<const char *>(chunk.value.payload.data()),
                                          static_cast<std::size_t>(chunk.value.byteCount));
    }
    const std::string base = "_m1_4mode_n1_1n_d";
    const std::map<Wire::NativeMode, std::set<std::string>> expected{
        {Wire::NativeMode::root_entry, {"answer"}},
        {Wire::NativeMode::function, {"__au_f" + base + "1f"}},
        {Wire::NativeMode::value_function, {"__au_v" + base + "1v"}},
        {Wire::NativeMode::ordinary_overload, {"__au_o" + base + "6choose_p1_20_", "__au_o" + base + "6choose_p1_21_"}},
        {Wire::NativeMode::class_value, {"__au_c" + base + "1C", "__au_c" + base + "3Box_t1_i64"}},
        {Wire::NativeMode::class_template, {"__au_t" + base + "3Box"}},
        {Wire::NativeMode::function_template, {"__au_g" + base + "1g", "__au_g" + base + "1g_t1_i64"}},
        {Wire::NativeMode::enumeration, {"__au_e" + base + "1E"}},
        {Wire::NativeMode::method, {"__au_m_m1_4mode_n2_1n1C_d1m"}},
        {Wire::NativeMode::constructor, {"__au_k_m1_4mode_n2_1n1C_d1C"}},
        {Wire::NativeMode::sealed_builtin, {"frozen_name"}}};
    require(actual == expected, "source linkage changed a native mode or inherited a prototype cache");
    resolution.finish();
    require(allocations.successful == allocations.released, "linkage mode caches leaked");
    ++cases;
}

void rawLinkageCaches() {
    namespace Wire = aurora::hosted_abi::compiler_resolver;
    context = "immutable linkage caches, copied chunk bounds and failed-session reads";
    const std::string scope(513, 'n');
    const std::string prefix = "module alpha // module trivia\n . beta;namespace " + scope +
                               " { class C { public: i64 value; };auto f()->i64{return 1;} }";
    const auto execute = [&](bool fail, std::size_t allowance) {
        Allocations allocations;
        RawResolution resolution(allocations);
        require(resolution.ingest(prefix +
                                  (fail ? "auto answer()->i64{return absent();}" : "auto answer()->i64{return 0;}")),
                "linkage fixture failed before resolver entry");
        aurora::hosted_abi::ResolverOrderInput order{};
        order.module = order.order = order.scope = 0;
        order.root = 1;
        require(aurora_hosted_resolver_order_module(resolution.data(), &order) == 1,
                "linkage fixture module order rejected");
        const auto baseline = allocations.successful;
        if (allowance != std::numeric_limits<std::size_t>::max())
            allocations.allowed = baseline + allowance;
        const auto result = aurora_hosted_resolver_run(resolution.data());
        const auto status = resolution.status();
        const auto used = allocations.successful - baseline;
        if (status.storage == Wire::StorageStatus::allocation) {
            require(result == -1 && status.diagnostic == Wire::SemanticError::none,
                    "allocation failure published resolver success");
            const auto count = checked_hosted_resolver_count(resolution.data(), 2);
            for (std::int64_t index = 0; index < count; ++index) {
                const auto symbol = resolution.meta(index);
                if (symbol.tag != Wire::MetaTag::symbol || symbol.value0 == -1)
                    continue;
                const auto name = resolution.meta(symbol.value0);
                require(name.tag == Wire::MetaTag::source_reference && name.value9 == index && name.value1 >= 0 &&
                            name.value2 > name.value1,
                        "failed fragment published a partial cache reference");
                std::int64_t copied = 0;
                std::string bytes;
                while (copied < name.value2 - name.value1) {
                    GuardedRecord<Wire::LinkageChunk> chunk;
                    aurora_hosted_resolver_linkage_chunk(resolution.data(), index, copied, &chunk.value);
                    chunk.check();
                    require(chunk.value.byteCount == std::min<std::int64_t>(512, name.value2 - name.value1 - copied),
                            "allocation failure invalidated an earlier completed cache");
                    bytes.append(reinterpret_cast<const char *>(chunk.value.payload.data()),
                                 static_cast<std::size_t>(chunk.value.byteCount));
                    copied += chunk.value.byteCount;
                }
                const auto base = "_m2_5alpha4beta_n1_513" + scope + "_d1";
                const std::map<Wire::NativeMode, std::string> expected{
                    {Wire::NativeMode::class_value, "__au_c" + base + "C"},
                    {Wire::NativeMode::function, "__au_f" + base + "f"},
                    {Wire::NativeMode::root_entry, "answer"}};
                require(expected.contains(symbol.native_tag) && bytes == expected.at(symbol.native_tag),
                        "failed fragment corrupted an earlier immutable cache");
            }
        } else {
            require(status.storage == Wire::StorageStatus::none &&
                        status.diagnostic ==
                            (fail ? Wire::SemanticError::unknown_function : Wire::SemanticError::none) &&
                        result == (fail ? -1 : 0),
                    "linkage writer replaced resolver outcome");
            std::int64_t nominal = -1;
            const auto count = checked_hosted_resolver_count(resolution.data(), 2);
            for (std::int64_t index = 0; index < count; ++index) {
                const auto row = resolution.meta(index);
                if (row.tag == Wire::MetaTag::symbol && row.declaration_tag == Wire::DeclarationKind::class_value)
                    nominal = index;
            }
            require(nominal >= 0, "linkage fixture lost its nominal");
            const std::string expected = "__au_c_m2_5alpha4beta_n1_513" + scope + "_d1C";
            const auto reference = resolution.meta(resolution.meta(nominal).value0);
            require(reference.tag == Wire::MetaTag::source_reference && reference.value9 == nominal &&
                        reference.value2 - reference.value1 == static_cast<std::int64_t>(expected.size()),
                    "symbol published an incomplete or inherited cache");
            std::string copied;
            for (std::int64_t offset = 0; offset < static_cast<std::int64_t>(expected.size()); offset += 512) {
                GuardedRecord<Wire::LinkageChunk> chunk;
                aurora_hosted_resolver_linkage_chunk(resolution.data(), nominal, offset, &chunk.value);
                chunk.check();
                const auto remaining = static_cast<std::int64_t>(expected.size()) - offset;
                require(chunk.value.byteCount == std::min<std::int64_t>(512, remaining),
                        "linkage chunk lost its exact bounded extent");
                copied.append(reinterpret_cast<const char *>(chunk.value.payload.data()),
                              static_cast<std::size_t>(chunk.value.byteCount));
            }
            require(copied == expected, "module trivia or long namespace changed exact linkage bytes");
            for (const auto &[symbol, offset, expectedSize] :
                 std::vector<std::tuple<std::int64_t, std::int64_t, std::int64_t>>{
                     {nominal, -1, -1},
                     {nominal, static_cast<std::int64_t>(expected.size()), 0},
                     {nominal, static_cast<std::int64_t>(expected.size()) + 1, -1},
                     {-1, 0, -1},
                     {0, 0, -1}}) {
                GuardedRecord<Wire::LinkageChunk> chunk;
                aurora_hosted_resolver_linkage_chunk(resolution.data(), symbol, offset, &chunk.value);
                chunk.check();
                require(chunk.value.byteCount == expectedSize, "linkage reader accepted an invalid selector");
            }
            if (fail) {
                const auto attempts = allocations.attempted;
                aurora::hosted_abi::ResolverTextInput text{};
                text.text.backing = "x";
                text.text.length = 1;
                require(aurora_hosted_resolver_append_text(resolution.data(), &text) == -1 &&
                            allocations.attempted == attempts && resolution.status().diagnostic == status.diagnostic &&
                            resolution.status().node == status.node && resolution.status().first == status.first &&
                            resolution.status().second == status.second,
                        "failed-session writer changed the selected diagnostic or allocated");
            }
        }
        resolution.finish();
        require(allocations.successful == allocations.released, "linkage cache or failure prefix leaked");
        ++cases;
        return used;
    };
    // One representative out-of-memory case: refuse the final allocation, after
    // earlier caches completed.
    const auto allocations = execute(false, std::numeric_limits<std::size_t>::max());
    execute(true, std::numeric_limits<std::size_t>::max());
    require(allocations > 0, "linkage resolution performed no allocation");
    execute(false, allocations - 1);
}

void rawCatalogueControls() {
    context = "exact historical and optional Call/Port/Serve lowering preludes";
    namespace Wire = aurora::hosted_abi::compiler_resolver;
    namespace Lowering = aurora::hosted_abi::compiler_lowering;
    for (const std::int64_t groups :
         std::vector<std::int64_t>{62, 318, 65598, 65854, 4294967358, 4294967614, 4295032894, 4295033150}) {
        std::vector<std::int64_t> operations{0, 1, 2, 3, 4};
        if ((groups & 256) != 0)
            operations.push_back(5);
        if ((groups & 65536) != 0)
            operations.insert(operations.end(), {6, 7});
        if ((groups & (std::int64_t{1} << 32)) != 0)
            operations.push_back(8);
        const auto count = static_cast<std::int64_t>(operations.size());
        for (int delta : {-1, 0, 1}) {
            Allocations allocations;
            RawResolution resolution(allocations);
            aurora::hosted_abi::LoweringBeginInput begin{};
            begin.configuration = {4096, 512, 4096, 65536, 4096, 512, 0, groups};
            require(aurora_hosted_lowering_begin(resolution.data(), &begin) == 1, "catalogue begin failed");
            const std::array kinds{Wire::ResolvedTypeKind::i64_value,
                                   Wire::ResolvedTypeKind::bool_value,
                                   Wire::ResolvedTypeKind::owner,
                                   Wire::ResolvedTypeKind::reference,
                                   Wire::ResolvedTypeKind::mutable_reference,
                                   Wire::ResolvedTypeKind::u64_value,
                                   Wire::ResolvedTypeKind::u8_value};
            const std::array<std::int64_t, 7> identities{1, 2, 3, 4, 5, 8, 11};
            for (std::size_t at = 0; at < kinds.size(); ++at) {
                aurora::hosted_abi::LoweringScalarInput scalar{};
                scalar.seed = {kinds[at], identities[at], at == 1 || at == 6 ? 1 : 8};
                require(aurora_hosted_lowering_seed_scalar(resolution.data(), &scalar) ==
                            static_cast<std::int64_t>(at) + 2,
                        "catalogue scalar prefix failed");
            }
            Lowering::OutputRow scalarRow;
            Lowering::OperandRow scalarType;
            aurora_hosted_lowering_read_output(resolution.data(), 2, &scalarRow);
            aurora_hosted_lowering_read_operand(resolution.data(), scalarRow.operandBegin, &scalarType);
            const std::string spelling = "operation";
            aurora::hosted_abi::ResolverTextInput text{};
            text.text.backing = spelling.data();
            text.text.length = static_cast<std::int64_t>(spelling.size());
            const auto name = aurora_hosted_resolver_append_text(resolution.data(), &text);
            const std::array receivers{Wire::ResolvedTypeKind::console_session,
                                       Wire::ResolvedTypeKind::console_session,
                                       Wire::ResolvedTypeKind::display_session,
                                       Wire::ResolvedTypeKind::event_session,
                                       Wire::ResolvedTypeKind::event_session,
                                       Wire::ResolvedTypeKind::call_session,
                                       Wire::ResolvedTypeKind::port_range,
                                       Wire::ResolvedTypeKind::port_range,
                                       Wire::ResolvedTypeKind::serve_session};
            const std::array<std::int64_t, 9> serviceKinds{0, 0, 1, 2, 2, 3, 4, 4, 5};
            for (std::int64_t at = 0; at < count + delta; ++at) {
                aurora::hosted_abi::LoweringServiceInput service{};
                const auto index =
                    static_cast<std::size_t>(operations[static_cast<std::size_t>(std::min(at, count - 1))]);
                service.seed.receiverKind = receivers[index];
                service.seed.kindId = serviceKinds[index];
                service.seed.operationId = operations[static_cast<std::size_t>(std::min(at, count - 1))];
                service.seed.spellingSource = name;
                service.seed.resultType = scalarType.signedValue;
                const auto accepted = aurora_hosted_lowering_seed_service(resolution.data(), &service);
                require(accepted == (at < count ? at + 9 : -1), "catalogue accepted an extra operation");
            }
            Lowering::LoweringResult result;
            aurora_hosted_lowering_run(resolution.data(), &result);
            // This deliberately lacks a resolved graph: it tests only whether
            // exact setup can seal, never claims a valid semantic module.
            const auto rows = aurora_hosted_lowering_count(resolution.data(), 0);
            require(rows == 9 + count + (delta == -1 ? -1 : delta == 0 ? 1 : 0), "wrong catalogue/prelude extent");
            if (delta == 0) {
                Lowering::OutputRow layout;
                aurora_hosted_lowering_read_output(resolution.data(), 9 + count, &layout);
                require(layout.recordKind == Lowering::RecordKind::InitialLayoutOrder,
                        "exact catalogue failed to seal");
            }
            resolution.finish();
            ++cases;
        }
    }
    for (const std::int64_t groups : std::vector<std::int64_t>{0,
                                                               54,
                                                               61,
                                                               63,
                                                               317,
                                                               319,
                                                               65535,
                                                               4294967296,
                                                               4294967357,
                                                               4294967359,
                                                               62 | (std::int64_t{1} << 31),
                                                               62 | (std::int64_t{1} << 33),
                                                               62 | (std::int64_t{1} << 48),
                                                               std::numeric_limits<std::int64_t>::max(),
                                                               -1}) {
        Allocations allocations;
        RawResolution resolution(allocations);
        aurora::hosted_abi::LoweringBeginInput begin{};
        begin.configuration = {4096, 512, 4096, 65536, 4096, 512, 0, groups};
        require(aurora_hosted_lowering_begin(resolution.data(), &begin) == -1 &&
                    resolution.status().storage == Wire::StorageStatus::invalid,
                "noncanonical catalogue bitmap accepted");
        resolution.finish();
        ++cases;
    }
}

void rawResolutionOwnership() {
    namespace Wire = aurora::hosted_abi::compiler_resolver;
    using Index = Wire::IndexRow;
    static_assert(sizeof(Index) == 96 && alignof(Index) == 8);
    static_assert(offsetof(Index, domain) == 0 && offsetof(Index, key0) == 8 && offsetof(Index, key1) == 16 &&
                  offsetof(Index, key2) == 24 && offsetof(Index, key3) == 32 && offsetof(Index, payload) == 40 &&
                  offsetof(Index, left) == 48 && offsetof(Index, right) == 56 && offsetof(Index, parent) == 64 &&
                  offsetof(Index, height) == 72 && offsetof(Index, chain) == 80 && offsetof(Index, bucket) == 88);
    static_assert(
        std::is_same_v<decltype(Index::domain), std::int64_t> && std::is_same_v<decltype(Index::key0), std::int64_t> &&
        std::is_same_v<decltype(Index::key1), std::int64_t> && std::is_same_v<decltype(Index::key2), std::int64_t> &&
        std::is_same_v<decltype(Index::key3), std::int64_t> && std::is_same_v<decltype(Index::payload), std::int64_t> &&
        std::is_same_v<decltype(Index::left), std::int64_t> && std::is_same_v<decltype(Index::right), std::int64_t> &&
        std::is_same_v<decltype(Index::parent), std::int64_t> &&
        std::is_same_v<decltype(Index::height), std::int64_t> && std::is_same_v<decltype(Index::chain), std::int64_t> &&
        std::is_same_v<decltype(Index::bucket), std::int64_t>);
    namespace Lowering = aurora::hosted_abi::compiler_lowering;
    using Output = Lowering::OutputRow;
    using Operand = Lowering::OperandRow;
    using Local = Lowering::LocalRow;
    using Snapshot = Lowering::SnapshotRow;
    using Lane = Lowering::ArgumentLane;
    using Continuation = Lowering::ContinuationRow;
    using Result = Lowering::LoweringResult;
    // Literal physical expectations are independent of generated header checks.
    // Session remains opaque; copied rows expose only their named typed fields.
    static_assert(sizeof(Wire::Session) == 520 && alignof(Wire::Session) == 8);
    static_assert(sizeof(Output) == 64 && alignof(Output) == 8 && offsetof(Output, recordKind) == 0 &&
                  offsetof(Output, instructionForm) == 8 && offsetof(Output, unaryOperation) == 16 &&
                  offsetof(Output, binaryOperation) == 24 && offsetof(Output, comparisonOperation) == 32 &&
                  offsetof(Output, queryOperation) == 40 && offsetof(Output, operandBegin) == 48 &&
                  offsetof(Output, operandCount) == 56);
    static_assert(sizeof(Operand) == 40 && alignof(Operand) == 8 && offsetof(Operand, operandRole) == 0 &&
                  offsetof(Operand, signedValue) == 8 && offsetof(Operand, unsignedValue) == 16 &&
                  offsetof(Operand, sliceBegin) == 24 && offsetof(Operand, sliceCount) == 32);
    static_assert(sizeof(Snapshot) == 48 && alignof(Snapshot) == 8 && offsetof(Snapshot, sharedCount) == 0 &&
                  offsetof(Snapshot, objectSharedCount) == 8 && offsetof(Snapshot, liveValue) == 16 &&
                  offsetof(Snapshot, exclusiveValue) == 24 && offsetof(Snapshot, resourceActiveValue) == 32 &&
                  offsetof(Snapshot, objectExclusiveValue) == 40);
    static_assert(sizeof(Local) == 160 && alignof(Local) == 8 && offsetof(Local, nameSourceId) == 0 &&
                  offsetof(Local, concreteTypeId) == 8 && offsetof(Local, storageOffset) == 16 &&
                  offsetof(Local, scopeId) == 24 && offsetof(Local, previousBinding) == 32 &&
                  offsetof(Local, mutableValue) == 40 && offsetof(Local, borrowedObject) == 48 &&
                  offsetof(Local, lintEligible) == 56 && offsetof(Local, readValue) == 64 &&
                  offsetof(Local, ownerId) == 72 && offsetof(Local, spanOriginKind) == 80 &&
                  offsetof(Local, originLocalId) == 88 && offsetof(Local, spanFieldIndex) == 96 &&
                  offsetof(Local, temporaryParent) == 104 && offsetof(Local, sharedCount) == 112 &&
                  offsetof(Local, objectSharedCount) == 120 && offsetof(Local, liveValue) == 128 &&
                  offsetof(Local, exclusiveValue) == 136 && offsetof(Local, resourceActiveValue) == 144 &&
                  offsetof(Local, objectExclusiveValue) == 152);
    static_assert(sizeof(Lane) == 56 && alignof(Lane) == 8 && offsetof(Lane, argumentIndex) == 0 &&
                  offsetof(Lane, argumentKind) == 8 && offsetof(Lane, concreteTypeId) == 16 &&
                  offsetof(Lane, localId) == 24 && offsetof(Lane, loanId) == 32 &&
                  offsetof(Lane, serviceKindId) == 40 && offsetof(Lane, cleanupKind) == 48);
    static_assert(sizeof(Continuation) == 496 && alignof(Continuation) == 8 &&
                  offsetof(Continuation, continuationKind) == 0 && offsetof(Continuation, continuationPhase) == 8 &&
                  offsetof(Continuation, syntaxNode) == 16 && offsetof(Continuation, childCursor) == 24 &&
                  offsetof(Continuation, scopeHead) == 32 && offsetof(Continuation, localPrefixLength) == 40 &&
                  offsetof(Continuation, incomingSnapshotBase) == 48 &&
                  offsetof(Continuation, thenSnapshotBase) == 56 && offsetof(Continuation, firstLabel) == 64 &&
                  offsetof(Continuation, secondLabel) == 72 && offsetof(Continuation, childTypeId) == 80 &&
                  offsetof(Continuation, childLocalId) == 88 && offsetof(Continuation, callTarget) == 96 &&
                  offsetof(Continuation, capabilityRootLocal) == 104 &&
                  offsetof(Continuation, receiverFieldIndex) == 112 && offsetof(Continuation, nextArgument) == 120 &&
                  offsetof(Continuation, argumentCount) == 128 && offsetof(Continuation, outputMark) == 136 &&
                  offsetof(Continuation, operandMark) == 144 && offsetof(Continuation, cleanupCursor) == 152 &&
                  offsetof(Continuation, firstArgument) == 160 && offsetof(Continuation, secondArgument) == 216 &&
                  offsetof(Continuation, thirdArgument) == 272 && offsetof(Continuation, fourthArgument) == 328 &&
                  offsetof(Continuation, fifthArgument) == 384 && offsetof(Continuation, sixthArgument) == 440);
    static_assert(sizeof(Result) == 32 && alignof(Result) == 8 && offsetof(Result, result_status) == 0 &&
                  offsetof(Result, result_reason) == 8 && offsetof(Result, diagnostic_row) == 16 &&
                  offsetof(Result, root_row) == 24);
    static_assert(std::is_same_v<decltype(Output::instructionForm), Lowering::InstructionForm> &&
                  std::is_same_v<decltype(Operand::operandRole), Lowering::OperandRole> &&
                  std::is_same_v<decltype(Operand::unsignedValue), std::uint64_t> &&
                  std::is_same_v<decltype(Continuation::firstArgument), Lane> &&
                  std::is_same_v<decltype(Result::result_status), Lowering::LoweringStatus> &&
                  std::is_same_v<decltype(Result::result_reason), Lowering::LoweringError>);
    context = "resolved transfer allocation failure and generated cleanup records";
    std::string source = "export module raw;";
    for (std::size_t index = 0; index < 32; ++index)
        source += "auto f" + std::to_string(index) + "()->i64{return 1+2;}";
    std::array<std::size_t, 11> initialBytes{};
    std::size_t firstIngestAllocations = 0;
    {
        Allocations allocations;
        RawResolution resolution(allocations);
        std::copy_n(allocations.initialBytes.begin(), initialBytes.size(), initialBytes.begin());
        const auto emptyOwner = initialBytes[0];
        require(allocations.attempted == 11 && allocations.successful == 11 &&
                    initialBytes == std::array<std::size_t, 11>{emptyOwner,
                                                                emptyOwner,
                                                                emptyOwner + 64 * sizeof(Wire::MetaRow),
                                                                emptyOwner,
                                                                emptyOwner,
                                                                emptyOwner,
                                                                emptyOwner,
                                                                emptyOwner,
                                                                emptyOwner,
                                                                emptyOwner,
                                                                emptyOwner} &&
                    resolution.status().storage == Wire::StorageStatus::none,
                "Session creation did not retain six original owners followed by five empty typed pools");
        require(resolution.ingest(source) && resolution.transferred, "valid parser/session transfer failed");
        firstIngestAllocations = allocations.successful;
        const auto first = resolution.meta(0);
        require(first.tag == Wire::MetaTag::module_unit && first.value10 >= 0,
                "successful transfer did not publish exactly one module root");
        require(resolution.ingest("export module second;auto next()->i64{return 3;}") &&
                    resolution.meta(0).value10 == first.value10 &&
                    resolution.meta(1).tag == Wire::MetaTag::module_unit &&
                    checked_hosted_resolver_count(resolution.data(), 5) == 2,
                "alternating owner slots lost an earlier module or the second transfer");
        require(checked_hosted_resolver_read_source(resolution.data(), 0) == 'e' &&
                    checked_hosted_resolver_read_source(resolution.data(), -1) == -1 &&
                    checked_hosted_resolver_read_source(resolution.data(),
                                                        checked_hosted_resolver_count(resolution.data(), 0)) == -1,
                "copied source bytes lost their checked bounds");
        resolution.finish();
        require(allocations.successful == allocations.released, "successful two-owner transfer leaked allocations");
    }
    {
        Allocations allocations;
        RawResolution resolution(allocations);
        require(std::equal(initialBytes.begin(), initialBytes.end(), allocations.initialBytes.begin()) &&
                    allocations.successful == 11,
                "fresh Session did not repeat its eleven initial owner attempts");
        resolution.finish();
        require(allocations.released == 11, "fresh Session did not release all eleven owners");
        for (std::size_t index = 0; index < initialBytes.size(); ++index)
            require(allocations.releasedOwners[index] == allocations.initialOwners[10 - index],
                    "fresh Session did not release its eleven owners in reverse field order");
    }
    {
        // One representative out-of-memory case: refuse the first Session owner.
        Allocations allocations;
        allocations.allowed = 0;
        RawResolution resolution(allocations);
        require(allocations.attempted == 11 && allocations.successful == 0 &&
                    std::equal(initialBytes.begin(), initialBytes.end(), allocations.initialBytes.begin()) &&
                    resolution.status().storage == Wire::StorageStatus::allocation,
                "initial owner failure skipped a declared allocation or published a usable Session");
        require(!resolution.ingest(source), "failed Session accepted a source");
        resolution.finish();
        require(allocations.successful == allocations.released, "failed Session retained an owner");
    }
    {
        // Fail the final allocation of a real consuming ingest, not just Session creation.
        require(firstIngestAllocations > 0, "successful ingest made no allocations");
        Allocations allocations;
        allocations.allowed = firstIngestAllocations - 1;
        RawResolution resolution(allocations);
        require(!resolution.ingest(source) && resolution.transferred &&
                    resolution.status().storage == Wire::StorageStatus::allocation &&
                    resolution.meta(0).tag == Wire::MetaTag::module_source && resolution.meta(0).value10 == -1,
                "allocation failure after transfer published a root or lost its returned owner");
        resolution.finish();
        require(allocations.successful == allocations.released, "failed consuming ingest leaked an owner");
    }
    for (const auto &[badModule, badRoot] : {std::pair{true, false}, std::pair{false, true}}) {
        Allocations allocations;
        RawResolution resolution(allocations);
        require(!resolution.ingest(source, badModule, badRoot) && resolution.transferred &&
                    resolution.status().storage == Wire::StorageStatus::invalid &&
                    resolution.meta(0).tag == Wire::MetaTag::module_source && resolution.meta(0).value10 == -1,
                "invalid consumed transfer published a root or lost its returned owner");
        resolution.finish();
        require(allocations.successful == allocations.released, "invalid transfer leaked one of its owning inputs");
    }
    {
        Allocations allocations;
        RawResolution resolution(allocations);
        require(!resolution.ingest("module broken;auto f()->i64{") && !resolution.transferred,
                "parser failure crossed the consuming transfer boundary");
        resolution.finish();
        require(allocations.successful == allocations.released, "parse failure did not release the live owner pair");
    }
    ++cases;
}

void createMetadata(std::uint64_t region, const aurora::hosted_abi::MetadataInitialize &input, void *store) {
    aurora::hosted_abi::MetadataCreate create{};
    create.region = region;
    aurora_hosted_metadata_create(&create, store);
    aurora_hosted_metadata_initialize(store, &input);
}

void rawMetadataOwnership() {
    namespace Wire = aurora::hosted_abi::compiler_ir_metadata;
    context = "metadata frame owner allocation failure and consuming cleanup";
    std::size_t successful = 0;
    const auto exercise = [&](std::size_t allowed, std::uint64_t quota, bool expected, bool invalidCounts = false) {
        Allocations allocations;
        allocations.allowed = allowed;
        aurora::hosted::bytes::Region region(quota, allocations.allocator());
        struct GuardedOwner {
            std::uint64_t before = canary;
            aurora::hosted_abi::MetadataRelease value{};
            std::uint64_t after = canary;
        } record;
        record.value.region = region.id();
        aurora::hosted_abi::MetadataInitialize input{};
        input.counts.coreCounts.bytes = 1;
        input.counts.coreCounts.types = 3;
        input.counts.mapCounts.indices = 1;
        input.counts.mapCounts.views = 1;
        input.callableCount = 1;
        input.slotCount = invalidCounts ? -1 : 2;
        input.instructionBegin = input.counts.coreCounts.types;
        aurora::hosted_abi::MetadataCreate create{};
        create.region = region.id();
        auto *store = record.value.store.storage.data();
        aurora_hosted_metadata_create(&create, store);
        require(aurora_hosted_metadata_allocated(store) == 0, "uninitialized metadata owner was published");
        require((aurora_hosted_metadata_initialize(store, &input) != 0) == expected,
                "metadata initialization status differs");
        if (invalidCounts)
            require(aurora_hosted_metadata_error(store) == static_cast<std::int64_t>(Wire::MetadataError::integrity),
                    "invalid metadata counts lost their integrity diagnostic");
        const auto attempted = allocations.attempted;
        require(aurora_hosted_metadata_initialize(store, &input) == 0 && allocations.attempted == attempted,
                "metadata initialization was repeated or retried after a terminal result");
        const bool allocated = aurora_hosted_metadata_allocated(store) != 0;
        require(allocated == expected, "metadata owner allocation status differs");
        if (expected) {
            successful = allocations.successful;
            require(successful == 19 && allocations.attempted == 19 && region.metrics().live_allocations == 13 &&
                        region.metrics().peak_live_allocations == 13 &&
                        allocations.initialBytes[18] == allocations.initialBytes[10] + 2 * sizeof(Wire::SlotRow),
                    "metadata initialization did not retain thirteen exact owners after six resizes");
        }
        aurora_hosted_metadata_release(&record.value);
        const auto metrics = region.metrics();
        require(record.before == canary && record.after == canary,
                "metadata creation or release escaped its generated owner extent");
        require(allocations.successful == allocations.released && metrics.used == 0 && metrics.live_allocations == 0 &&
                    metrics.releases == metrics.successful_allocations && region.close(),
                "metadata allocation failure or release leaked a frame owner");
        ++cases;
    };
    exercise(std::numeric_limits<std::size_t>::max(), 1048576, true);
    // One representative out-of-memory case: refuse the final slot resize.
    exercise(successful - 1, 1048576, false);
    exercise(std::numeric_limits<std::size_t>::max(), 0, false);
    exercise(std::numeric_limits<std::size_t>::max(), 1048576, false, true);
}

void rawInstructionOwnership() {
    namespace wire = aurora::hosted_abi::compiler_ir_instructions;
    context = "instruction owner allocation failure and consuming cleanup";
    const auto exercise = [&](std::size_t allowed, std::uint64_t quota, bool expected) {
        Allocations allocations;
        allocations.allowed = allowed;
        aurora::hosted::bytes::Region region(quota, allocations.allocator());
        struct GuardedOwner {
            std::uint64_t before = canary;
            aurora::hosted_abi::InstructionsRelease value{};
            std::uint64_t after = canary;
        } record;
        record.value.region = region.id();
        aurora::hosted_abi::InstructionsCreate input{};
        input.region = region.id();
        input.instructionCount = 3;
        input.operandCount = 5;
        input.literalCount = 4;
        input.bodyCount = 2;
        aurora_hosted_instructions_create(&input, record.value.store.storage.data());
        require((aurora_hosted_instructions_allocated(record.value.store.storage.data()) != 0) == expected,
                "instruction owner allocation status differs");
        if (expected)
            require(allocations.successful == 5 && allocations.attempted == 5 && sizeof(wire::CodeRow) == 32 &&
                        allocations.initialBytes[3] + 3 * sizeof(wire::RawInstructionRow) ==
                            allocations.initialBytes[0] + 3 * sizeof(wire::CodeRow),
                    "instruction rows and CFG facts were not allocated as five exact owners");
        aurora_hosted_instructions_release(&record.value);
        const auto metrics = region.metrics();
        require(record.before == canary && record.after == canary,
                "instruction creation or release escaped its generated owner extent");
        require(allocations.successful == allocations.released && metrics.used == 0 && metrics.live_allocations == 0 &&
                    metrics.releases == metrics.successful_allocations && region.close(),
                "instruction allocation failure or release leaked an owner");
        ++cases;
    };
    exercise(std::numeric_limits<std::size_t>::max(), 1048576, true);
    exercise(4, 1048576, false);
    exercise(std::numeric_limits<std::size_t>::max(), 0, false);
}

void rawInstructionAdmission() {
    namespace abi = aurora::hosted_abi;
    namespace meta = abi::compiler_ir_metadata;
    namespace wire = abi::compiler_ir_instructions;
    namespace lower = abi::compiler_lowering;
    namespace bytes = aurora::hosted::bytes;
    using Form = lower::InstructionForm;
    using Reason = wire::InstructionError;
    using Kind = aurora::TypeKind;
    meta::FlagMasks masks{};
    aurora_hosted_metadata_flag_masks(&masks);
    require(std::has_single_bit(masks.flowLeader) && std::has_single_bit(masks.flowFallthrough) &&
                std::has_single_bit(masks.flowReached) && (masks.flowLeader & masks.flowFallthrough) == 0 &&
                (masks.flowLeader & masks.flowReached) == 0 && (masks.flowFallthrough & masks.flowReached) == 0,
            "source flow masks must be distinct single-bit u64 flags");
    const auto reachedLeader = masks.flowLeader | masks.flowFallthrough | masks.flowReached;
    const auto reachedFallthrough = masks.flowFallthrough | masks.flowReached;
    struct ScalarCase {
        Form form;
        Kind type;
        std::int64_t value;
        std::int64_t operation;
        Reason error;
    };
    const std::vector<ScalarCase> scalars{
        {Form::Constant, Kind::Ref, 0, 0, Reason::constant_type},
        {Form::Constant, Kind::Bool, -1, 0, Reason::constant_bool},
        {Form::Constant, Kind::Bool, 2, 0, Reason::constant_bool},
        {Form::Constant, Kind::U8, -1, 0, Reason::constant_u8},
        {Form::Constant, Kind::U8, 256, 0, Reason::constant_u8},
        {Form::EnumConstant, Kind::I64, 0, 0, Reason::enum_constant_type},
        {Form::EnumConstant, Kind::Enum, -1, 0, Reason::enum_constant_case},
        {Form::EnumConstant, Kind::Enum, 2, 0, Reason::enum_constant_case},
        {Form::UnaryValue, Kind::Ref, 0, -1, Reason::unary_operation},
        {Form::UnaryValue, Kind::I64, 0, INT64_MAX, Reason::unary_operation},
        {Form::UnaryValue, Kind::U8, 0, 0, Reason::unary_operand},
        {Form::BinaryValue, Kind::Ref, 0, -1, Reason::binary_operation},
        {Form::BinaryValue, Kind::I64, 0, INT64_MAX, Reason::binary_operation},
        {Form::BinaryValue, Kind::I64, 0, 5, Reason::binary_operand},
        {Form::Convert, Kind::I64, 0, 0, Reason::conversion_types},
        {Form::Compare, Kind::Ref, 0, -1, Reason::comparison_operation},
        {Form::Compare, Kind::I64, 0, INT64_MAX, Reason::comparison_operation},
        {Form::Compare, Kind::Ref, 0, 0, Reason::comparison_scalar},
        {Form::Compare, Kind::Bool, 0, 2, Reason::comparison_ordered},
        {Form::Compare, Kind::Enum, 0, 2, Reason::comparison_ordered},
        {Form::Constant, Kind::Bool, 0, 0, Reason::none},
        {Form::Constant, Kind::Bool, 1, 0, Reason::none},
        {Form::Constant, Kind::U8, 0, 0, Reason::none},
        {Form::Constant, Kind::U8, 255, 0, Reason::none},
        {Form::Constant, Kind::U64, INT64_MIN, 0, Reason::none},
        {Form::Constant, Kind::U64, -1, 0, Reason::none},
        {Form::EnumConstant, Kind::Enum, 1, 0, Reason::none},
        // Static admission does not inspect current values or operand stacks.
        {Form::UnaryValue, Kind::I64, 0, 0, Reason::none},
        {Form::BinaryValue, Kind::U8, 0, 8, Reason::none},
        {Form::Convert, Kind::U8, 0, 0, Reason::none},
        {Form::Compare, Kind::Enum, 0, 0, Reason::none},
    };
    // Reuse one operation/return body for transport and semantic failures.
    // Scalar rows are transport-valid, including unknown raw operator values.
    constexpr std::size_t nonScalarCases = 24;
    for (std::size_t mutation = 0; mutation < nonScalarCases + scalars.size(); ++mutation) {
        const auto *scalar = mutation < nonScalarCases ? nullptr : &scalars[mutation - nonScalarCases];
        context = "raw instruction admission case " + std::to_string(mutation);
        const bool conversion = scalar && scalar->form == Form::Convert;
        const bool singleOperand = scalar && (scalar->form == Form::UnaryValue || scalar->form == Form::BinaryValue ||
                                              scalar->form == Form::Compare);
        const bool missingBinding = mutation == 14;
        const bool missingCall = mutation == 15;
        const bool missingSlot = mutation == 16;
        // Canonical metadata is not executable admission: an uncalled constructor
        // still requires a mutable receiver and I64 result before publication.
        // Cases: readonly/I64, mutable/U64, mutable/Bool, then mutable/I64 control.
        const bool constructor = mutation >= 20 && mutation < nonScalarCases;
        const bool invalidConstructor = constructor && mutation != 23;
        const bool invalidBody = missingBinding || missingCall || missingSlot || invalidConstructor ||
                                 (scalar && scalar->error != Reason::none);
        const bool admitted = mutation == 0 || invalidBody || scalar || constructor;
        const std::int64_t operandCount = missingCall || singleOperand ? 1 : 2;
        Allocations allocations;
        bytes::Region region(1048576, allocations.allocator());
        {
            struct Owners {
                abi::MetadataRelease metadata{};
                abi::InstructionsRelease instructions{};
                ~Owners() {
                    aurora_hosted_instructions_release(&instructions);
                    aurora_hosted_metadata_release(&metadata);
                }
            } owners;
            owners.metadata.region = owners.instructions.region = region.id();
            abi::MetadataInitialize metadata{};
            metadata.counts.coreCounts.bytes = missingCall || scalar || constructor ? 2 : 1;
            metadata.counts.coreCounts.types = missingCall ? 1 : missingBinding || conversion ? 3 : 2;
            metadata.counts.coreCounts.classes = constructor ? 1 : 0;
            metadata.counts.mapCounts.enums = scalar ? 1 : 0;
            metadata.counts.mapCounts.indices = 1;
            metadata.counts.mapCounts.views = 1;
            metadata.callableCount = 1;
            metadata.instructionBegin = missingBinding ? 2 : 1;
            auto *declarations = owners.metadata.store.storage.data();
            createMetadata(region.id(), metadata, declarations);
            abi::InstructionsCreate instructions{};
            instructions.region = region.id();
            instructions.instructionCount = 2;
            instructions.operandCount = operandCount;
            instructions.literalCount = mutation == 10 ? 1 : 0;
            instructions.bodyCount = 1;
            auto *storage = owners.instructions.store.storage.data();
            aurora_hosted_instructions_create(&instructions, storage);
            const std::array<const void *, 2> roots{storage, declarations};
            require(aurora_hosted_metadata_allocated(declarations) == 1 &&
                        aurora_hosted_instructions_allocated(storage) == 1,
                    "raw admission allocation failed");
            require(aurora_hosted_instructions_structure(roots.data()) ==
                            static_cast<std::int64_t>(wire::InstructionStatus::pending) &&
                        aurora_hosted_instructions_publish(storage) == 0,
                    "pending instruction storage normalized or published before admission");
            const auto descriptor = [](const std::byte *owner, std::size_t offset) {
                bytes::NativeOwner result;
                std::memcpy(&result, owner + offset, sizeof(result));
                return result;
            };
            const auto set = [&](const std::byte *owner, std::size_t pool, std::int64_t index, const auto &row) {
                auto target = descriptor(owner, pool);
                require(bytes::__au_runtime_values_set(&target, index, sizeof(row), &row) == 1,
                        "raw admission row escaped its generated owner pool");
            };
            auto names = descriptor(declarations, abi::metadataStore_bytesOffset);
            require(bytes::__au_runtime_bytes_set(&names, 0, 'f') == 1, "raw admission name write failed");
            if (missingCall || scalar || constructor)
                require(bytes::__au_runtime_bytes_set(&names,
                                                      1,
                                                      scalar        ? 'E'
                                                      : constructor ? 'C'
                                                                    : 'g') == 1,
                        "raw secondary name write failed");
            if (scalar)
                set(declarations, abi::metadataStore_enumsOffset, 0, meta::EnumRow{{1, 1}, 2});
            if (constructor) {
                meta::ClassRow receiver{};
                receiver.nameRange = {1, 1};
                receiver.suppliedStorage = -1;
                receiver.membershipBits = masks.classLayout;
                set(declarations, abi::metadataStore_classesOffset, 0, receiver);
            }
            meta::RawTypeRow type{};
            if (mutation == 21 || mutation == 22)
                type.typeKind = static_cast<std::int64_t>(mutation == 21 ? Kind::U64 : Kind::Bool);
            set(declarations, abi::metadataStore_typesOffset, 0, type);
            type = {};
            if (mutation == 7)
                type.rawTail.templateArgumentCount = 1;
            if (scalar) {
                type.typeKind = static_cast<std::int64_t>(scalar->type);
                if (scalar->type == Kind::Enum)
                    type.nameRange = {1, 1};
            }
            if (!missingCall)
                set(declarations, abi::metadataStore_typesOffset, 1, type);
            if (missingBinding || conversion)
                set(declarations, abi::metadataStore_typesOffset, 2, meta::RawTypeRow{});
            meta::CallableRow callable{};
            callable.nameRange = {0, 1};
            callable.typeRange = {0, missingBinding ? 2 : 1};
            if (constructor) {
                callable.flags = masks.callableReceiver;
                callable.receiver.nameRange = {1, 1};
                callable.receiver.flags = masks.receiverConstructor | (mutation == 20 ? 0 : masks.receiverMutable);
            }
            set(declarations, abi::metadataStore_callablesOffset, 0, callable);
            set(declarations, abi::metadataStore_indicesOffset, 0, meta::IndexRow{0});
            set(declarations, abi::metadataStore_viewsOffset, 0, meta::ViewRow{});
            require(aurora_hosted_metadata_run(declarations) ==
                        static_cast<std::int64_t>(meta::MetadataStatus::success),
                    "instruction raw tail escaped its metadata admission boundary");
            wire::RawInstructionRow constant{};
            constant.recordKind = mutation == 1 ? -1 : static_cast<std::int64_t>(lower::RecordKind::Instruction);
            constant.instructionForm = mutation == 2 ? -1
                                                     : static_cast<std::int64_t>(scalar        ? scalar->form
                                                                                 : missingCall ? Form::Call
                                                                                 : missingSlot ? Form::Load
                                                                                               : Form::Constant);
            if (scalar) {
                if (scalar->form == Form::UnaryValue)
                    constant.unaryOperation = scalar->operation;
                if (scalar->form == Form::BinaryValue)
                    constant.binaryOperation = scalar->operation;
                if (scalar->form == Form::Compare)
                    constant.comparisonOperation = scalar->operation;
            }
            constant.operandBegin = mutation == 3 ? std::numeric_limits<std::int64_t>::max() : 0;
            constant.operandCount = operandCount;
            set(storage, abi::instructionStore_instructionsOffset, 0, constant);
            wire::RawInstructionRow terminal{};
            terminal.recordKind = static_cast<std::int64_t>(lower::RecordKind::Instruction);
            terminal.instructionForm = static_cast<std::int64_t>(lower::InstructionForm::Return);
            terminal.operandBegin = operandCount;
            set(storage, abi::instructionStore_instructionsOffset, 1, terminal);
            wire::RawOperandRow value{};
            value.operandRole = mutation == 4
                                    ? -1
                                    : static_cast<std::int64_t>(missingCall   ? lower::OperandRole::CalleeName
                                                                : missingSlot ? lower::OperandRole::Offset
                                                                              : lower::OperandRole::SignedConstant);
            value.signedValue = missingCall ? 0 : 42;
            value.sliceBegin = missingCall ? 1 : 0;
            value.sliceCount = mutation == 5 || missingCall ? 1 : 0;
            if (scalar) {
                value.signedValue = scalar->value;
                if (singleOperand || conversion || scalar->form == Form::EnumConstant) {
                    value.operandRole = static_cast<std::int64_t>(singleOperand ? lower::OperandRole::OperandTypeId
                                                                  : conversion  ? lower::OperandRole::SourceTypeId
                                                                                : lower::OperandRole::TypeId);
                    value.signedValue = 1;
                } else if (scalar->type == Kind::U64) {
                    value.operandRole = static_cast<std::int64_t>(lower::OperandRole::UnsignedConstant);
                    value.signedValue = 0;
                    value.unsignedValue = static_cast<std::uint64_t>(scalar->value);
                }
            }
            set(storage, abi::instructionStore_operandsOffset, 0, value);
            wire::RawOperandRow typeOperand{};
            typeOperand.operandRole = static_cast<std::int64_t>(lower::OperandRole::TypeId);
            typeOperand.signedValue = mutation == 6 ? 0 : missingBinding ? 2 : 1;
            if (conversion) {
                typeOperand.operandRole = static_cast<std::int64_t>(lower::OperandRole::ResultTypeId);
                typeOperand.signedValue = 2;
            } else if (scalar && scalar->form == Form::EnumConstant) {
                typeOperand.operandRole = static_cast<std::int64_t>(lower::OperandRole::CaseIndex);
                typeOperand.signedValue = scalar->value;
            }
            if (operandCount == 2)
                set(storage, abi::instructionStore_operandsOffset, 1, typeOperand);
            set(storage,
                abi::instructionStore_codeOrderOffset,
                0,
                wire::CodeRow{1, mutation == 11 ? 0 : -1, mutation == 12 ? 1u : 0u, mutation == 13 ? 1 : 0});
            set(storage, abi::instructionStore_codeOrderOffset, 1, wire::CodeRow{mutation == 8 ? 1 : 2, -1, 0, 0});
            wire::BodyRow rawBody{mutation == 9 ? 1 : 0, 2, 2, 0};
            // Raw ingress cannot manufacture the source-derived unreachable boundary.
            if (mutation == 17)
                rawBody.unreachableAfter = 1;
            else if (mutation == 18)
                rawBody.unreachableAfter = -1;
            else if (mutation == 19)
                rawBody.unreachableAfter = std::numeric_limits<std::int64_t>::max();
            set(storage, abi::instructionStore_bodiesOffset, 0, rawBody);
            const auto status = aurora_hosted_instructions_admit(roots.data());
            require(status == static_cast<std::int64_t>(admitted ? wire::InstructionStatus::admitted
                                                                 : wire::InstructionStatus::invalid),
                    "malformed instruction storage status differs");
            const auto expectedError = admitted        ? wire::InstructionError::none
                                       : mutation == 7 ? wire::InstructionError::noncanonical_type
                                                       : wire::InstructionError::integrity;
            require(aurora_hosted_instructions_error(storage) == static_cast<std::int64_t>(expectedError),
                    "malformed instruction storage reason differs");
            if (admitted) {
                const auto metadataSnapshot = [&] {
                    std::vector<std::byte> snapshot(owners.metadata.store.storage.begin(),
                                                    owners.metadata.store.storage.end());
                    for (const auto pool : {abi::metadataStore_bytesOffset,
                                            abi::metadataStore_typesOffset,
                                            abi::metadataStore_classesOffset,
                                            abi::metadataStore_fieldsOffset,
                                            abi::metadataStore_storageOffset,
                                            abi::metadataStore_indicesOffset,
                                            abi::metadataStore_descriptorsOffset,
                                            abi::metadataStore_viewsOffset,
                                            abi::metadataStore_enumsOffset,
                                            abi::metadataStore_callablesOffset,
                                            abi::metadataStore_slotsOffset,
                                            abi::metadataStore_resultsOffset,
                                            abi::metadataStore_framesOffset}) {
                        const auto owner = descriptor(declarations, pool);
                        require(owner.region == region.id(), "metadata snapshot escaped its fixture region");
                        const auto length = bytes::__au_runtime_bytes_borrow_length(&owner);
                        for (std::int64_t at = 0; at < length; ++at)
                            snapshot.push_back(static_cast<std::byte>(bytes::__au_runtime_bytes_at(&owner, at)));
                    }
                    return snapshot;
                };
                const auto declarationsBefore = metadataSnapshot();
                require(aurora_hosted_instructions_publish(storage) == 0,
                        "admitted instruction storage published before CFG normalization");
                const auto attempted = allocations.attempted;
                require(aurora_hosted_instructions_structure(roots.data()) ==
                                static_cast<std::int64_t>(invalidBody ? wire::InstructionStatus::invalid
                                                                      : wire::InstructionStatus::structured) &&
                            allocations.attempted == attempted,
                        "instruction static admission status differs or allocated another owner");
                const auto codeOrder = descriptor(storage, abi::instructionStore_codeOrderOffset);
                for (std::int64_t position = 0; position < 2; ++position) {
                    wire::CodeRow code{};
                    bytes::__au_runtime_values_at(&codeOrder, position, sizeof(code), &code);
                    require(code.instructionId == position + 1 && code.targetPosition == -1 &&
                                code.flowFlags == (position == 0 ? reachedLeader : masks.flowReached) &&
                                code.scratchValue == 0,
                            "normalized instruction facts lost stable identity or retained scratch");
                }
                if (invalidBody) {
                    const auto staticError = invalidConstructor ? wire::InstructionError::constructor_signature
                                             : scalar           ? scalar->error
                                             : missingCall      ? wire::InstructionError::call_target
                                             : missingSlot      ? wire::InstructionError::scalar_slot
                                                                : wire::InstructionError::scalar_prefix;
                    require(aurora_hosted_instructions_error(storage) == static_cast<std::int64_t>(staticError) &&
                                aurora_hosted_instructions_publish(storage) == 0 &&
                                aurora_hosted_instructions_admit(roots.data()) ==
                                    static_cast<std::int64_t>(wire::InstructionStatus::invalid) &&
                                aurora_hosted_instructions_structure(roots.data()) ==
                                    static_cast<std::int64_t>(wire::InstructionStatus::invalid) &&
                                aurora_hosted_instructions_error(storage) == static_cast<std::int64_t>(staticError) &&
                                aurora_hosted_instructions_publish(storage) == 0 && allocations.attempted == attempted,
                            "failed static admission published, reopened or allocated another owner");
                } else {
                    require(aurora_hosted_instructions_publish(storage) == 1 &&
                                aurora_hosted_instructions_structure(roots.data()) ==
                                    static_cast<std::int64_t>(wire::InstructionStatus::published) &&
                                aurora_hosted_instructions_publish(storage) == 0,
                            "instruction publication failed to require normalized structure or close mutation");
                }
                require(metadataSnapshot() == declarationsBefore,
                        "instruction static admission mutated its immutable metadata root");
            } else {
                const auto attempted = allocations.attempted;
                require(aurora_hosted_instructions_publish(storage) == 0 &&
                            aurora_hosted_instructions_admit(roots.data()) ==
                                static_cast<std::int64_t>(wire::InstructionStatus::invalid) &&
                            aurora_hosted_instructions_structure(roots.data()) ==
                                static_cast<std::int64_t>(wire::InstructionStatus::invalid) &&
                            aurora_hosted_instructions_error(storage) == static_cast<std::int64_t>(expectedError) &&
                            aurora_hosted_instructions_publish(storage) == 0 && allocations.attempted == attempted,
                        "failed transport admission published, reopened, changed reason or allocated another owner");
            }
        }
        require(allocations.successful == allocations.released && region.metrics().used == 0 && region.close(),
                "raw instruction admission leaked either owner");
        ++cases;
    }
    // Service admission uses the same raw owners and publication boundary. These
    // rows deliberately omit live values/calls: only static facts belong here.
    using Role = lower::OperandRole;
    struct ServiceSite {
        Form form;
        std::vector<std::pair<Role, std::int64_t>> fields;
    };
    const auto acquire = [](std::int64_t id, std::int64_t offset = 16, std::int64_t kind = 0) {
        return ServiceSite{Form::AcquireServiceLoan,
                           {{Role::LoanId, id}, {Role::Offset, offset}, {Role::ServiceKindId, kind}}};
    };
    const auto release = [](std::int64_t id, std::int64_t kind = 0) {
        return ServiceSite{Form::ReleaseServiceLoan, {{Role::LoanId, id}, {Role::ServiceKindId, kind}}};
    };
    const auto operation = [](std::int64_t op, std::int64_t kind, std::int64_t offset = 16, std::int64_t result = 0) {
        return ServiceSite{Form::ServiceOperation,
                           {{Role::Offset, offset},
                            {Role::ServiceOperationId, op},
                            {Role::ResultOffset, result},
                            {Role::ServiceKindId, kind}}};
    };
    struct ServiceCase {
        std::vector<std::vector<ServiceSite>> bodies;
        Reason error = Reason::none;
        std::int64_t firstKind = 0;
        bool enums = true;
    };
    std::vector<ServiceCase> services{
        {{{}}},
        {{{acquire(1)}}},
        {{{release(1)}}}, // No lexical acquisition or completed call is required statically.
        {{{release(1, 1),
           release(INT64_MAX, 2),
           release(2, 3),
           release(3, 4),
           release(4, 5)}}}, // Closed kinds need no matching entry or live loan here.
        {{{acquire(1), release(1), acquire(1)}}},
        {{{acquire(7), acquire(7), acquire(7)}}},
        {{{acquire(1), acquire(1, 32, 1)}}, Reason::service_loan_identity},
        // Independently pin both identity components before entry-site admission.
        {{{acquire(1), acquire(1, 32, 0)}}, Reason::service_loan_identity},
        {{{acquire(1), acquire(1, 16, 1)}}, Reason::service_loan_identity},
        // A module-wide static failure precedes the first body's dynamic failure.
        {{{release(1)}, {acquire(0)}}, Reason::service_loan_identity},
        // Loan identity is scoped to a body, even with reused IDs and other roots.
        {{{acquire(7)}, {acquire(7, 32, 1)}}},
        {{{operation(0, 0, 16, 40)}}, Reason::service_sample_result},
        {{{operation(3, 2, 16, 40)}}, Reason::service_sample_result, 2},
    };
    for (const auto id : {INT64_MIN, std::int64_t{-1}, std::int64_t{0}}) {
        services.push_back({{{acquire(id)}}, Reason::service_loan_identity});
        services.push_back({{{release(id)}}, Reason::service_release});
    }
    for (const auto kind : {std::int64_t{-1}, std::int64_t{6}, INT64_MAX}) {
        services.push_back({{{acquire(1, 16, kind)}}, Reason::service_loan_root});
        services.push_back({{{release(1, kind)}}, Reason::service_release});
        services.push_back({{{operation(1, kind)}}, Reason::service_operation_kind});
    }
    for (const auto offset : {INT64_MIN, std::int64_t{0}, std::int64_t{8}, std::int64_t{32}, INT64_MAX}) {
        services.push_back({{{acquire(1, offset)}}, Reason::service_loan_root});
        services.push_back({{{operation(1, 0, offset)}}, Reason::service_operation_root});
    }
    services.push_back({{{acquire(1, 16, 5)}}, Reason::service_loan_root});
    services.push_back({{{operation(1, 5)}}, Reason::service_operation_kind});
    services.push_back({{{operation(8, 0)}}, Reason::service_operation_kind});
    for (const auto op : {INT64_MIN, std::int64_t{-1}, std::int64_t{9}, INT64_MAX})
        services.push_back({{{operation(op, 0)}}, Reason::service_operation});
    for (const auto &[op, kind, offset, reason] :
         std::vector<std::tuple<std::int64_t, std::int64_t, std::int64_t, Reason>>{
             {1, 0, 16, Reason::service_put_result},
             {2, 1, 32, Reason::service_pixel_result},
             {4, 2, 16, Reason::service_ack_result}}) {
        const std::int64_t first = kind == 2 ? 2 : 0;
        services.push_back({{{operation(op, kind, offset)}}, Reason::none, first});
        services.push_back({{{operation(op, kind, offset)}}, reason, first, false});
        services.push_back({{{operation(op, kind, offset, 40)}}, reason, first});
    }
    for (const auto &ids : std::vector<std::vector<std::int64_t>>{{INT64_MAX},
                                                                  {9, 3},
                                                                  {INT64_MAX, 17, 1},
                                                                  {99, 17, 3, 1},
                                                                  {INT64_MAX, 4, 4, 3, 1},
                                                                  {8, 7, 6, 5, 4, 3, 2, 1}}) {
        std::vector<ServiceSite> sites;
        for (const auto id : ids)
            sites.push_back(acquire(id));
        services.push_back({{sites}});
        // Reject only after collection/sort, and clean every borrowed scratch lane.
        sites.push_back(acquire(ids.front(), 32, 1));
        services.push_back({{sites}, Reason::service_loan_identity});
    }
    for (std::size_t mutation = 0; mutation < services.size(); ++mutation) {
        context = "raw service instruction admission case " + std::to_string(mutation);
        const auto &test = services[mutation];
        const auto bodyCount = static_cast<std::int64_t>(test.bodies.size());
        std::vector<wire::RawInstructionRow> instructions;
        std::vector<wire::RawOperandRow> operands;
        std::vector<wire::BodyRow> bodies;
        std::vector<wire::CodeRow> expected;
        const auto append = [&](const ServiceSite &site) {
            wire::RawInstructionRow row{};
            row.recordKind = static_cast<std::int64_t>(lower::RecordKind::Instruction);
            row.instructionForm = static_cast<std::int64_t>(site.form);
            row.operandBegin = static_cast<std::int64_t>(operands.size());
            row.operandCount = static_cast<std::int64_t>(site.fields.size());
            instructions.push_back(row);
            for (const auto &[role, value] : site.fields) {
                wire::RawOperandRow operand{};
                operand.operandRole = static_cast<std::int64_t>(role);
                operand.signedValue = value;
                operands.push_back(operand);
            }
        };
        for (const auto &sites : test.bodies) {
            const auto begin = static_cast<std::int64_t>(instructions.size());
            append({Form::BindServiceParameter,
                    {{Role::Index, 0}, {Role::Offset, 16}, {Role::ServiceKindId, test.firstKind}}});
            append({Form::BindServiceParameter,
                    {{Role::Index, 1}, {Role::Offset, 32}, {Role::ServiceKindId, test.firstKind == 2 ? 0 : 1}}});
            for (const auto &site : sites)
                append(site);
            const auto target = static_cast<std::int64_t>(instructions.size()) - begin + 1;
            append({Form::Jump, {{Role::LabelId, 77}}});
            append({Form::Label, {{Role::LabelId, 77}}});
            append({Form::Return, {}});
            const auto retained = static_cast<std::int64_t>(instructions.size()) - begin;
            // Normalize away an unreachable label/jump tail before loan sorting.
            append({Form::Label, {{Role::LabelId, 88}}});
            append({Form::Jump, {{Role::LabelId, 88}}});
            bodies.push_back({begin, retained + 2, retained, 0});
            for (std::int64_t at = 0; at < retained; ++at)
                expected.push_back({begin + at + 1,
                                    at == target - 1 ? target : -1,
                                    at == 0 || at == target                  ? reachedLeader
                                    : at == target - 1 || at == retained - 1 ? masks.flowReached
                                                                             : reachedFallthrough,
                                    0});
        }
        Allocations allocations;
        bytes::Region region(1048576, allocations.allocator());
        {
            struct Owners {
                abi::MetadataRelease metadata{};
                abi::InstructionsRelease instructions{};
                ~Owners() {
                    aurora_hosted_instructions_release(&instructions);
                    aurora_hosted_metadata_release(&metadata);
                }
            } owners;
            owners.metadata.region = owners.instructions.region = region.id();
            const std::array<std::string, 3> enumNames{
                "__au_console_put_result", "__au_display_put_result", "__au_event_ack_result"};
            std::string names = "fg";
            std::vector<meta::EnumRow> enums;
            if (test.enums)
                for (std::size_t i = 0; i < enumNames.size(); ++i) {
                    enums.push_back(
                        {{static_cast<std::int64_t>(names.size()), static_cast<std::int64_t>(enumNames[i].size())},
                         i == 2 ? 3 : 2});
                    names += enumNames[i];
                }
            abi::MetadataInitialize metadata{};
            metadata.counts.coreCounts.bytes = static_cast<std::int64_t>(names.size());
            metadata.counts.coreCounts.types = bodyCount * 3;
            metadata.counts.mapCounts.enums = static_cast<std::int64_t>(enums.size());
            metadata.counts.mapCounts.indices = bodyCount;
            metadata.counts.mapCounts.views = 1;
            metadata.callableCount = bodyCount;
            metadata.slotCount = bodyCount * 2;
            metadata.instructionBegin = bodyCount * 3;
            auto *declarations = owners.metadata.store.storage.data();
            createMetadata(region.id(), metadata, declarations);
            abi::InstructionsCreate create{};
            create.region = region.id();
            create.instructionCount = static_cast<std::int64_t>(instructions.size());
            create.operandCount = static_cast<std::int64_t>(operands.size());
            create.literalCount = 0;
            create.bodyCount = bodyCount;
            auto *storage = owners.instructions.store.storage.data();
            aurora_hosted_instructions_create(&create, storage);
            const auto descriptor = [](const std::byte *owner, std::size_t offset) {
                bytes::NativeOwner result;
                std::memcpy(&result, owner + offset, sizeof(result));
                return result;
            };
            const auto set = [&](const std::byte *owner, std::size_t pool, std::int64_t at, const auto &row) {
                auto target = descriptor(owner, pool);
                require(bytes::__au_runtime_values_set(&target, at, sizeof(row), &row) == 1,
                        "raw service row escaped its generated owner pool");
            };
            require(aurora_hosted_metadata_allocated(declarations) == 1 &&
                        aurora_hosted_instructions_allocated(storage) == 1,
                    "raw service allocation failed");
            auto nameOwner = descriptor(declarations, abi::metadataStore_bytesOffset);
            for (std::size_t at = 0; at < names.size(); ++at)
                require(bytes::__au_runtime_bytes_set(&nameOwner, at, names[at]) == 1, "service name write failed");
            for (std::size_t at = 0; at < enums.size(); ++at)
                set(declarations, abi::metadataStore_enumsOffset, at, enums[at]);
            for (std::int64_t body = 0; body < bodyCount; ++body) {
                for (std::int64_t lane = 0; lane < 3; ++lane) {
                    meta::RawTypeRow type{};
                    type.typeKind = lane == 0 ? 0 : lane == 1 ? 14 + test.firstKind : test.firstKind == 2 ? 14 : 15;
                    set(declarations, abi::metadataStore_typesOffset, body * 3 + lane, type);
                }
                meta::CallableRow callable{};
                callable.nameRange = {body, 1};
                callable.typeRange = {body * 3, 3};
                callable.frameBytes = 32;
                callable.slotRange = {body * 2, 2};
                set(declarations, abi::metadataStore_callablesOffset, body, callable);
                for (std::int64_t lane = 0; lane < 2; ++lane)
                    set(declarations,
                        abi::metadataStore_slotsOffset,
                        body * 2 + lane,
                        meta::SlotRow{14, (lane + 1) * 16, 0, 0, 0});
                set(declarations, abi::metadataStore_indicesOffset, body, meta::IndexRow{body});
                auto declared = bodies[body];
                declared.retainedCount = declared.codeCapacity;
                set(storage, abi::instructionStore_bodiesOffset, body, declared);
            }
            set(declarations, abi::metadataStore_viewsOffset, 0, meta::ViewRow{});
            require(aurora_hosted_metadata_run(declarations) ==
                        static_cast<std::int64_t>(meta::MetadataStatus::success),
                    "raw service declarations failed metadata admission");
            for (std::size_t at = 0; at < instructions.size(); ++at) {
                set(storage, abi::instructionStore_instructionsOffset, at, instructions[at]);
                set(storage,
                    abi::instructionStore_codeOrderOffset,
                    at,
                    wire::CodeRow{static_cast<std::int64_t>(at + 1), -1, 0, 0});
            }
            for (std::size_t at = 0; at < operands.size(); ++at)
                set(storage, abi::instructionStore_operandsOffset, at, operands[at]);
            const auto metadataSnapshot = [&] {
                std::vector<std::byte> snapshot(owners.metadata.store.storage.begin(),
                                                owners.metadata.store.storage.end());
                for (const auto pool : {abi::metadataStore_bytesOffset,
                                        abi::metadataStore_typesOffset,
                                        abi::metadataStore_classesOffset,
                                        abi::metadataStore_fieldsOffset,
                                        abi::metadataStore_storageOffset,
                                        abi::metadataStore_indicesOffset,
                                        abi::metadataStore_descriptorsOffset,
                                        abi::metadataStore_viewsOffset,
                                        abi::metadataStore_enumsOffset,
                                        abi::metadataStore_callablesOffset,
                                        abi::metadataStore_slotsOffset,
                                        abi::metadataStore_resultsOffset,
                                        abi::metadataStore_framesOffset}) {
                    const auto owner = descriptor(declarations, pool);
                    require(owner.region == region.id(), "service metadata snapshot escaped its fixture region");
                    const auto length = bytes::__au_runtime_bytes_borrow_length(&owner);
                    for (std::int64_t at = 0; at < length; ++at)
                        snapshot.push_back(static_cast<std::byte>(bytes::__au_runtime_bytes_at(&owner, at)));
                }
                return snapshot;
            };
            const auto before = metadataSnapshot();
            const auto attempted = allocations.attempted;
            const std::array<const void *, 2> roots{storage, declarations};
            require(aurora_hosted_instructions_admit(roots.data()) ==
                            static_cast<std::int64_t>(wire::InstructionStatus::admitted) &&
                        aurora_hosted_instructions_publish(storage) == 0,
                    "raw service transport was not admitted");
            const bool invalid = test.error != Reason::none;
            const auto status = static_cast<std::int64_t>(invalid ? wire::InstructionStatus::invalid
                                                                  : wire::InstructionStatus::structured);
            require(aurora_hosted_instructions_structure(roots.data()) == status &&
                        aurora_hosted_instructions_error(storage) == static_cast<std::int64_t>(test.error),
                    "raw service static status or diagnostic differs");
            const auto codeOwner = descriptor(storage, abi::instructionStore_codeOrderOffset);
            std::size_t expectedAt = 0;
            for (const auto &body : bodies) {
                for (std::int64_t at = 0; at < body.retainedCount; ++at) {
                    wire::CodeRow code{};
                    bytes::__au_runtime_values_at(&codeOwner, body.codeBegin + at, sizeof(code), &code);
                    const auto &wanted = expected[expectedAt++];
                    require(code.instructionId == wanted.instructionId &&
                                code.targetPosition == wanted.targetPosition && code.flowFlags == wanted.flowFlags &&
                                code.scratchValue == 0,
                            "service sort changed retained identity/order/target/flags or retained scratch");
                }
                for (std::int64_t tail = 0; tail < 2; ++tail) {
                    wire::CodeRow code{};
                    bytes::__au_runtime_values_at(
                        &codeOwner, body.codeBegin + body.retainedCount + tail, sizeof(code), &code);
                    require(code.instructionId == body.codeBegin + body.retainedCount + tail + 1 &&
                                code.targetPosition == (tail == 0 ? -1 : body.retainedCount) &&
                                code.flowFlags == (tail == 0 ? masks.flowLeader | masks.flowFallthrough : 0u) &&
                                code.scratchValue == -1,
                            "service sort touched the discarded post-CFG capacity tail");
                }
            }
            require(allocations.attempted == attempted && metadataSnapshot() == before,
                    "service static admission allocated or mutated metadata");
            if (invalid)
                require(aurora_hosted_instructions_publish(storage) == 0 &&
                            aurora_hosted_instructions_admit(roots.data()) == status &&
                            aurora_hosted_instructions_structure(roots.data()) == status &&
                            aurora_hosted_instructions_publish(storage) == 0 && allocations.attempted == attempted,
                        "failed service static admission published, reopened or allocated");
            else
                require(aurora_hosted_instructions_publish(storage) == 1 &&
                            aurora_hosted_instructions_structure(roots.data()) ==
                                static_cast<std::int64_t>(wire::InstructionStatus::published) &&
                            aurora_hosted_instructions_publish(storage) == 0,
                        "service publication failed to close normalized storage");
            require(metadataSnapshot() == before && allocations.attempted == attempted,
                    "service publication or terminal retry allocated or mutated metadata");
        }
        require(allocations.successful == allocations.released && region.metrics().used == 0 && region.close(),
                "raw service admission leaked an owner");
        ++cases;
    }
}

void rawModules() {
    static_assert(static_cast<std::int64_t>(Stop::module_definition) == 12 &&
                  wire(SyntaxKind::module_definition) == 21 && wire(SyntaxKind::namespace_definition) == 22 &&
                  wire(SyntaxKind::class_definition) == 23 && wire(SyntaxKind::declaration) == 24 &&
                  wire(SyntaxKind::template_scalar) == 25 && wire(SyntaxKind::template_value) == 26 &&
                  wire(SyntaxKind::template_capacity) == 27);
    context = "whole-module independent-owner growth and failure cleanup";
    constexpr std::int64_t width = 33, nesting = 9;
    std::string source = "export module wide;";
    for (std::int64_t index = 0; index < nesting; ++index)
        source += "namespace n{";
    for (std::int64_t index = 0; index < width; ++index)
        source += "auto f_" + std::to_string(index) + "()->i64{return g(1,2);}";
    source += std::string(nesting, '}');
    const auto tokens = aurora::lex(source, "module-growth.au");
    const auto end = static_cast<std::int64_t>(tokens.size() - 1), syntaxCount = 2 + 2 * nesting + 4 * width;
    std::size_t successful = 0;
    {
        Allocations allocations;
        RawArena arena(allocations);
        require(arena.parse(source, Stop::module_definition) == Words{wire(Status::success),
                                                                      syntaxCount - 1,
                                                                      3 * width,
                                                                      end,
                                                                      static_cast<std::int64_t>(source.size()),
                                                                      0} &&
                    arena.syntaxCount() == syntaxCount && arena.edges() == 2 * width && arena.types() == width,
                "module growth omitted a declaration forest or failed to consume EOF");
        const auto root = arena.syntax(syntaxCount - 1);
        require(root == SyntaxWords{21, 0, end, -1, -1, -1, -1, -1, 0, syntaxCount - 2, 0, -1},
                "module growth root did not own its complete preamble/declaration forest");
        const auto metrics = arena.metrics();
        require(metrics.live_allocations == 5 && metrics.peak_live_allocations == 5 &&
                    metrics.successful_allocations > 10,
                "module growth changed the five independent owners");
        successful = allocations.successful;
        arena.finish();
        require(allocations.successful == allocations.released, "module growth leaked an owner");
        ++cases;
    }
    {
        // One representative out-of-memory case: refuse the final allocation.
        const auto allowed = successful - 1;
        Allocations allocations;
        allocations.allowed = allowed;
        RawArena arena(allocations);
        const auto result = arena.parse(source, Stop::module_definition);
        require(result[0] == wire(Status::allocation_failure) && result[1] == -1,
                "module partial allocation exposed a complete root");
        if (arena.syntaxCount() > 0)
            require(arena.syntax(0) == SyntaxWords{17, 2, 4, -1, -1, -1, -1, 2, -1, -1, 1, -1},
                    "module growth failure changed a committed preamble");
        arena.finish();
        require(allocations.successful == allocations.released, "failed module parse leaked an owner");
        ++cases;
    }
}

void rawAdmission() {
    // Independent copied configuration controls exercise the private entry,
    // while production policy messages stay in the existing whole-module tables.
    struct Fixture {
        const char *source;
        AdmissionConfigWords configuration;
        AdmissionWords expected;
    };
    for (const auto &fixture : std::vector<Fixture>{
             {"export module admitted;class C{array<i64,65> values;};",
              admissionConfiguration,
              {wire(AdmissionStatus::array_capacity), 14, 15, -1, 64}},
             {"export module admitted;class C{array<i64,65> values;};",
              {65, 512, 62, 1, 2, 4},
              {wire(AdmissionStatus::success), -1, -1, -1, 0}},
             {"module admitted;auto f(builtin::ConsoleSession& first,builtin::DisplaySession& second)->i64{}",
              admissionConfiguration,
              {wire(AdmissionStatus::success), -1, -1, -1, 0}},
             {"module admitted;auto f(builtin::ConsoleSession& first,builtin::DisplaySession& second)->i64{}",
              {64, 512, 54, 1, 2, 4},
              {wire(AdmissionStatus::borrowed_parameter), 16, 17, -1, 0}}}) {
        context = "copied declaration admission configuration";
        Allocations allocations;
        RawArena arena(allocations);
        const auto parsed = arena.parse(fixture.source, Stop::module_definition);
        require(parsed[0] == wire(Status::success), "configuration fixture failed grammar before admission");
        require(arena.admit(fixture.source, parsed[1], fixture.configuration) == fixture.expected,
                "admission ignored its copied scalar limit or supported service-group mask");
        arena.finish();
        require(allocations.successful == allocations.released, "configuration admission leaked an owner");
        ++cases;
    }
    // Raw parser policies may narrow the closed group set, but may not
    // authorize a new mixed Serve group or an unknown high-bit identity.
    for (const auto groups : std::vector<std::int64_t>{0,
                                                       54,
                                                       62,
                                                       4294967296,
                                                       4295033150,
                                                       -1,
                                                       1,
                                                       64,
                                                       std::int64_t{1} << 31,
                                                       std::int64_t{1} << 33,
                                                       std::int64_t{1} << 48,
                                                       std::int64_t{1} << 62}) {
        const std::string source = "module admitted;auto f()->u64{return 0u64;}";
        Allocations allocations;
        RawArena arena(allocations);
        const auto parsed = arena.parse(source, Stop::module_definition);
        require(parsed[0] == wire(Status::success), "raw group fixture failed grammar");
        const auto result = arena.admit(source, parsed[1], {64, 512, groups, 1, 2, 4});
        const bool allowed = groups >= 0 && (groups & 4295033150LL) == groups;
        require(result[0] == wire(allowed ? AdmissionStatus::success : AdmissionStatus::invalid),
                "parser group policy lost closed full-width admission");
        arena.finish();
        require(allocations.successful == allocations.released, "raw group admission leaked an owner");
        ++cases;
    }
    {
        const std::string source = "module admitted;auto f(builtin::ServeSession& s)->u64{return 0u64;}";
        Allocations allocations;
        RawArena arena(allocations);
        const auto parsed = arena.parse(source, Stop::module_definition);
        require(parsed[0] == wire(Status::success), "Serve raw group fixture failed grammar");
        require(arena.admit(source, parsed[1], {64, 512, 4294967296, 1, 2, 4})[0] == wire(AdmissionStatus::success),
                "exact Serve singleton group bit was narrowed or truncated");
        arena.finish();
        require(allocations.successful == allocations.released, "Serve group admission leaked an owner");
        ++cases;
    }
    context = "post-grammar admission scratch growth and allocation failure";
    constexpr std::size_t width = 513;
    std::string source = "module admitted;auto wide(";
    for (std::size_t index = 0; index < width; ++index)
        source += (index ? "," : "") + std::string("i64 p") + std::to_string(index);
    source += ")->i64{return p0;}auto later()->i64{return 0;}";
    // The later declaration remains pending while wide parameter scratch grows.
    // Only admission allocations are denied: one representative out-of-memory
    // case refuses the first scratch allocation, then admission completes.
    // Each iteration first establishes a complete valid grammar forest and then
    // checks that all records survive.
    for (const bool limited : {true, false}) {
        Allocations allocations;
        RawArena arena(allocations);
        const auto parsed = arena.parse(source, Stop::module_definition);
        require(parsed[0] == wire(Status::success), "wide admission fixture did not complete grammar");
        std::vector<NodeWords> nodes;
        std::vector<TypeWords> types;
        std::vector<SyntaxWords> syntax;
        for (std::int64_t index = 0; index < parsed[2]; ++index)
            nodes.push_back(arena.read(index));
        for (std::int64_t index = 0; index < arena.types(); ++index)
            types.push_back(arena.type(index));
        for (std::int64_t index = 0; index < arena.syntaxCount(); ++index)
            syntax.push_back(arena.syntax(index));
        const auto grammarAllocations = allocations.successful;
        if (limited)
            allocations.allowed = grammarAllocations;
        const auto admitted = arena.admit(source, parsed[1]);
        const bool success = admitted[0] == wire(AdmissionStatus::success);
        require(success != limited, "admission allocation outcome differs");
        require(admitted ==
                    AdmissionWords{
                        wire(success ? AdmissionStatus::success : AdmissionStatus::allocation_failure), -1, -1, -1, 0},
                "admission allocation failure published policy metadata or imposed a parameter limit");
        require(checked_hosted_parser_count(arena.data()) == parsed[2] &&
                    arena.types() == static_cast<std::int64_t>(types.size()) &&
                    arena.syntaxCount() == static_cast<std::int64_t>(syntax.size()) && arena.edges() == 0,
                "admission changed grammar forest counts");
        for (std::size_t index = 0; index < nodes.size(); ++index)
            require(arena.read(index) == nodes[index], "admission changed a committed expression");
        for (std::size_t index = 0; index < types.size(); ++index)
            require(arena.type(index) == types[index], "admission changed a committed type");
        for (std::size_t index = 0; index < syntax.size(); ++index)
            require(arena.syntax(index) == syntax[index], "admission changed a committed declaration");
        const auto metrics = arena.metrics();
        require(metrics.live_allocations == 5 && metrics.peak_live_allocations == 5,
                "admission acquired a sixth owner or lost an existing owner");
        if (success) {
            require(allocations.successful > grammarAllocations, "admission never grew scratch");
            const auto beforeRepeat = allocations.successful;
            require(arena.admit(source, parsed[1]) == admitted && allocations.successful == beforeRepeat,
                    "repeated admission retained stale scratch context or regrew completed storage");
        }
        arena.finish();
        require(allocations.successful == allocations.released, "admission scratch failure leaked an existing owner");
        ++cases;
    }
}

void rawBodies() {
    static_assert(sizeof(SyntaxWords) == 96 && static_cast<std::int64_t>(Stop::body) == 4);
    static_assert(wire(SyntaxKind::block) == 1 && wire(SyntaxKind::local) == 2 && wire(SyntaxKind::return_value) == 3 &&
                  wire(SyntaxKind::static_assertion) == 4 && wire(SyntaxKind::conditional) == 5 &&
                  wire(SyntaxKind::loop) == 6 && wire(SyntaxKind::expression) == 7 && wire(SyntaxKind::assign) == 8 &&
                  wire(SyntaxKind::field_assign) == 9 && wire(SyntaxKind::index_assign) == 10);
    // Wide bodies grow independently of expression AST depth. Empty nested
    // blocks also force body frames/storage to grow with zero expression nodes.
    for (const bool nested : {false, true}) {
        constexpr std::int64_t width = 513;
        const auto source = nested ? std::string(128, '{') + std::string(128, '}') : "{" + std::string{};
        std::string text = source;
        if (!nested) {
            for (std::int64_t i = 0; i < width; ++i)
                text += "1;";
            text += "}";
        }
        context = nested ? "raw nested body growth" : "raw wide body growth";
        std::size_t successful = 0;
        {
            Allocations allocations;
            RawArena arena(allocations);
            const auto result = arena.parse(text, Stop::body);
            require(result == Words{wire(Status::success),
                                    nested ? 127 : width,
                                    nested ? 0 : width,
                                    nested ? 256 : 2 * width + 2,
                                    static_cast<std::int64_t>(text.size()),
                                    0} &&
                        arena.syntaxCount() == (nested ? 128 : width + 1),
                    "body growth result differs");
            if (nested) {
                for (std::int64_t i = 0; i < 128; ++i)
                    require(arena.syntax(i) == SyntaxWords{1, 127 - i, 129 + i, -1, -1, -1, -1, -1, i - 1, -1, 0, -1},
                            "nested block ABI differs");
            } else {
                for (std::int64_t i = 0; i < width; ++i) {
                    require(arena.syntax(i) ==
                                SyntaxWords{7, 1 + 2 * i, 3 + 2 * i, i - 1, i, -1, -1, -1, -1, -1, 0, -1},
                            "wide sibling order/end/root differs");
                    require(arena.read(i) == NodeWords{1, 1 + 2 * i, -1, -1, 1, 1 + 2 * i, 1 + 2 * i},
                            "wide body expression forest differs");
                }
                require(arena.syntax(width) ==
                            SyntaxWords{1, 0, 2 * width + 2, -1, -1, -1, -1, -1, width - 1, -1, 0, -1},
                        "wide root differs");
            }
            const auto metrics = arena.metrics();
            require(metrics.live_allocations == 5 && metrics.peak_live_allocations == 5 &&
                        metrics.successful_allocations > 10 && metrics.peak_used > 8 * 96,
                    "body did not grow its real fifth owner");
            successful = allocations.successful;
            arena.finish();
            require(allocations.released == successful, "body growth leaked an owner");
        }
        {
            // One representative out-of-memory case: refuse the final allocation.
            const auto allowed = successful - 1;
            Allocations allocations;
            allocations.allowed = allowed;
            RawArena arena(allocations);
            const auto result = arena.parse(text, Stop::body);
            require(result[0] == wire(Status::allocation_failure) && result[1] == -1,
                    "body initial/growth failure did not fail closed");
            if (arena.syntaxCount() > 0)
                require(arena.syntax(0) == (nested ? SyntaxWords{1, 127, 129, -1, -1, -1, -1, -1, -1, -1, 0, -1}
                                                   : SyntaxWords{7, 1, 3, -1, 0, -1, -1, -1, -1, -1, 0, -1}),
                        "body failed growth damaged a committed record");
            arena.finish();
            require(allocations.released == allocations.successful, "body failed growth leaked owner metadata");
            ++cases;
        }
        ++cases;
    }
}

void rawPreambleEnums() {
    context = "explicit enum-count ABI isolation";
    for (std::int64_t stop = 0; stop <= static_cast<std::int64_t>(Stop::module_definition); ++stop)
        for (const std::int64_t count :
             std::array<std::int64_t, 4>{-1, 1, 65, std::numeric_limits<std::int64_t>::max()}) {
            if (stop == static_cast<std::int64_t>(Stop::enum_definition) && count == 1)
                continue;
            Allocations allocations;
            RawArena arena(allocations);
            const auto result = arena.parse("enum class E{a};", static_cast<Stop>(stop), 0, {}, count);
            require(result == Words{wire(Status::invalid), -1, 0, 0, 0, 0} && arena.syntaxCount() == 0 &&
                        arena.types() == 0 && arena.edges() == 0,
                    "invalid or cross-profile enum count acquired syntax authority");
            arena.finish();
            require(allocations.successful == allocations.released, "invalid enum-count input leaked an owner");
            ++cases;
        }
    for (const auto stop : {Stop::preamble, Stop::enum_definition}) {
        context = "preamble/enum fifth-owner growth and allocation failure";
        const std::int64_t width = stop == Stop::preamble ? 513 : 256;
        std::string source = stop == Stop::preamble ? "export module wide;" : enumSource(width);
        std::vector<SyntaxWords> expected;
        for (std::int64_t index = 0; index < width; ++index) {
            if (stop == Stop::preamble)
                source += "import item_" + std::to_string(index) + ";";
            const auto ordinal = stop == Stop::preamble ? 5 + 3 * index : 4 + 2 * index;
            expected.push_back(
                {stop == Stop::preamble ? 18 : 20, ordinal, ordinal + 1, index - 1, -1, -1, -1, -1, -1, -1, 0, -1});
        }
        const auto tokens = aurora::lex(source, "preamble-enum-growth.au");
        const auto end = static_cast<std::int64_t>(tokens.size() - 1);
        expected.push_back({stop == Stop::preamble ? 17 : 19,
                            2,
                            end,
                            -1,
                            -1,
                            -1,
                            -1,
                            stop == Stop::preamble ? 2 : -1,
                            width - 1,
                            -1,
                            stop == Stop::preamble ? 1 : 0,
                            -1});
        std::size_t successful = 0;
        // Complete once, then one representative out-of-memory case that
        // refuses the final growth allocation.
        for (const bool limited : {false, true}) {
            Allocations allocations;
            allocations.allowed = limited ? successful - 1 : std::numeric_limits<std::size_t>::max();
            RawArena arena(allocations);
            const auto result = arena.parse(source, stop, 0, {}, stop == Stop::enum_definition ? 63 : 0);
            const bool accepted = result[0] == wire(Status::success);
            require(accepted != limited, "preamble/enum allocation outcome differs");
            if (accepted) {
                require(result == Words{wire(Status::success),
                                        width,
                                        0,
                                        end,
                                        static_cast<std::int64_t>(tokens.back().span.begin.offset),
                                        0} &&
                            arena.syntaxCount() == width + 1,
                        "wide preamble/enum root or cursor differs");
                const auto metrics = arena.metrics();
                require(metrics.live_allocations == 5 && metrics.peak_live_allocations == 5 &&
                            metrics.successful_allocations > 5 && metrics.peak_used > 8 * 96,
                        "preamble/enum growth added an owner or bypassed syntax storage");
                successful = allocations.successful;
            } else {
                require(result[0] == wire(Status::allocation_failure) && result[1] == -1 && result[2] == 0 &&
                            arena.syntaxCount() >= 0 && arena.syntaxCount() <= width,
                        "preamble/enum allocation failure published a root");
            }
            require(arena.types() == 0 && arena.edges() == 0, "preamble/enum acquired unrelated graph records");
            for (std::int64_t index = 0; index < arena.syntaxCount(); ++index)
                require(arena.syntax(index) == expected.at(index), "preamble/enum growth changed its committed prefix");
            arena.finish();
            require(allocations.successful == allocations.released, "preamble/enum failed growth leaked an owner");
            ++cases;
        }
    }
}

void rawCallableGrowth() {
    constexpr std::int64_t width = 513;
    for (const auto stop : {Stop::function, Stop::method, Stop::constructor}) {
        const bool constructor = stop == Stop::constructor;
        std::string source = constructor ? "Box(i64 p):" : "auto wide(";
        for (std::int64_t index = 0; index < width; ++index) {
            if (index)
                source += ',';
            source += constructor ? "f" + std::to_string(index) + "(make(p))" : "i64 p" + std::to_string(index);
        }
        source += constructor ? "{}" : ")->i64{return 1;}";
        context = constructor ? "constructor initializer growth/failure" : "callable parameter growth/failure";
        std::vector<SyntaxWords> expected;
        if (constructor) {
            expected.push_back({11, 2, 4, -1, -1, -1, 0, 3, -1, -1, 0, -1});
            for (std::int64_t index = 0; index < width; ++index)
                expected.push_back({12,
                                    6 + 8 * index,
                                    13 + 8 * index,
                                    index == 0 ? -1 : index,
                                    2 * index + 1,
                                    -1,
                                    -1,
                                    -1,
                                    -1,
                                    -1,
                                    0,
                                    -1});
            expected.push_back({15, 0, 8 * width + 7, -1, -1, -1, -1, -1, width, 0, 0, -1});
        } else {
            for (std::int64_t index = 0; index < width; ++index)
                expected.push_back(
                    {11, 3 + 3 * index, 5 + 3 * index, index - 1, -1, -1, index, 4 + 3 * index, -1, -1, 0, -1});
            expected.push_back({3, 3 * width + 6, 3 * width + 9, -1, 0, -1, -1, -1, -1, -1, 0, -1});
            expected.push_back({1, 3 * width + 5, 3 * width + 10, -1, -1, -1, -1, -1, width, -1, 0, -1});
            expected.push_back({stop == Stop::function ? 13 : 14,
                                1,
                                3 * width + 10,
                                -1,
                                -1,
                                -1,
                                width,
                                -1,
                                width + 1,
                                width - 1,
                                0,
                                -1});
        }
        const auto expressions = constructor ? 2 * width : 1;
        const auto next = constructor ? 8 * width + 7 : 3 * width + 10;
        std::size_t successful = 0;
        {
            Allocations allocations;
            RawArena arena(allocations);
            const auto result = arena.parse(source, stop);
            require(result == Words{wire(Status::success),
                                    static_cast<std::int64_t>(expected.size() - 1),
                                    expressions,
                                    next,
                                    static_cast<std::int64_t>(source.size()),
                                    0} &&
                        arena.syntaxCount() == static_cast<std::int64_t>(expected.size()) &&
                        arena.types() == (constructor ? 1 : width + 1) && arena.edges() == (constructor ? width : 0),
                    "wide callable lost a parameter, initializer, type, expression or closing boundary");
            for (std::size_t index = 0; index < expected.size(); ++index)
                require(arena.syntax(index) == expected[index], "wide callable syntax prefix differs");
            const auto metrics = arena.metrics();
            require(metrics.live_allocations == 5 && metrics.peak_live_allocations == 5 &&
                        metrics.successful_allocations > 10 && metrics.peak_used > 8 * 96,
                    "wide callable did not grow the existing five-owner arena");
            successful = allocations.successful;
            arena.finish();
            require(allocations.released == successful, "wide callable leaked a successful allocation");
        }
        {
            // One representative out-of-memory case: refuse the final allocation.
            const auto allowed = successful - 1;
            Allocations allocations;
            allocations.allowed = allowed;
            RawArena arena(allocations);
            const auto result = arena.parse(source, stop);
            require(result[0] == wire(Status::allocation_failure) && result[1] == -1 && arena.syntaxCount() >= 0 &&
                        arena.syntaxCount() <= static_cast<std::int64_t>(expected.size()),
                    "callable allocation/growth failure did not fail closed");
            for (std::int64_t index = 0; index < arena.syntaxCount(); ++index)
                require(arena.syntax(index) == expected[static_cast<std::size_t>(index)],
                        "callable failed growth damaged a committed syntax prefix");
            arena.finish();
            require(allocations.successful == allocations.released, "callable failed growth leaked an arena owner");
            ++cases;
        }
    }
}

void rawTypeGrowth() {
    context = "independent type/candidate growth and allocation failure";
    constexpr std::int64_t count = 257;
    std::string source = "{";
    for (std::int64_t index = 0; index < count; ++index) {
        if (index)
            source += ',';
        source += "f<i64>(size_of(array<u8, 4>))";
    }
    source += "};";
    std::vector<TypeWords> expected;
    for (std::int64_t index = 0; index < count; ++index) {
        const auto token = 1 + 16 * index, first = 5 * index;
        expected.push_back({1, token + 2, token + 2, 2 * (token + 2), -1, -1, -1, 0});
        expected.push_back({5, token, token, 2 * (token + 3), first, -1, token, 1});
        expected.push_back({3, token + 9, token + 9, 2 * (token + 9), -1, -1, -1, 0});
        expected.push_back({7, token + 11, token + 11, 2 * (token + 11), -1, -1, -1, 0});
        expected.push_back({9, token + 7, token + 7, 2 * (token + 12), first + 2, first + 3, token + 5, 2});
    }
    std::size_t successful = 0;
    {
        Allocations allocations;
        RawArena arena(allocations);
        const auto result = arena.parse(source);
        require(result[0] == wire(Status::success) && result[2] == 2 * count + 1 && arena.types() == 5 * count &&
                    arena.edges() == 2 * count,
                "wide typed root omitted expression/type records");
        for (std::int64_t index = 0; index < arena.types(); ++index)
            require(arena.type(index) == expected[static_cast<std::size_t>(index)],
                    "type growth changed committed topology/provenance/ownership");
        const auto metrics = arena.metrics();
        require(metrics.successful_allocations > 15 && metrics.live_allocations == 5 &&
                    metrics.peak_live_allocations == 5 && metrics.peak_used > 5 * count * 64,
                "typed parse did not grow all independent storage owners");
        successful = allocations.successful;
        arena.finish();
        require(allocations.successful == allocations.released, "typed growth cleanup mismatch");
    }
    {
        // One representative out-of-memory case: refuse the final allocation.
        const auto allowed = successful - 1;
        Allocations allocations;
        allocations.allowed = allowed;
        RawArena arena(allocations);
        const auto result = arena.parse(source);
        require(result[0] == wire(Status::allocation_failure) && result[1] == -1,
                "type/prepass allocation failure did not fail closed");
        require(arena.types() >= 0 && arena.types() <= static_cast<std::int64_t>(expected.size()),
                "type failure exposed an impossible prefix count");
        for (std::int64_t index = 0; index < arena.types(); ++index)
            require(arena.type(index) == expected[static_cast<std::size_t>(index)],
                    "type failure damaged a previously committed record");
        arena.finish();
        require(allocations.successful == allocations.released, "partial type/candidate graph leaked an owner");
    }
    ++cases;
}

// Build a stated complete binary type tree and its independent wire layout.
// Spaced closers deliberately keep this growth test orthogonal to >> tokenization.
std::string rawDeclarationTree(int depth, std::int64_t &token, std::vector<TypeWords> &records) {
    const auto first = token++;
    if (!depth) {
        records.push_back({1, first, first, 2 * first, -1, -1, -1, 0});
        return "i64";
    }
    ++token; // '<'
    const auto left = rawDeclarationTree(depth - 1, token, records);
    const auto leftRoot = static_cast<std::int64_t>(records.size() - 1);
    ++token; // ','
    const auto right = rawDeclarationTree(depth - 1, token, records);
    const auto rightRoot = static_cast<std::int64_t>(records.size() - 1);
    const auto close = token++;
    records.push_back({5, first, first, 2 * close, leftRoot, rightRoot, -1, 0});
    return "Pair < " + left + " , " + right + " >";
}
void rawDeclarationTypeGrowth() {
    context = "standalone type growth, exact prefix preservation and allocation cleanup";
    std::int64_t next = 0;
    std::vector<TypeWords> expected;
    const auto type = rawDeclarationTree(4, next, expected);
    const auto source = type + " next";
    require(expected.size() == 31 && next == 76, "independent binary type fixture changed shape");
    expected.back()[6] = 0;
    expected.back()[7] = 3;
    std::size_t successful = 0;
    for (int cycle = 0; cycle < 3; ++cycle) {
        Allocations allocations;
        RawArena arena(allocations);
        require(arena.parse(source, Stop::type) ==
                        Words{wire(Status::success), 30, 0, 76, static_cast<std::int64_t>(type.size() + 1), 0} &&
                    arena.types() == 31,
                "31-record standalone type growth lost its root/cursor");
        for (std::size_t index = 0; index < expected.size(); ++index)
            require(arena.type(static_cast<std::int64_t>(index)) == expected[index],
                    "standalone type growth changed child-before-parent records");
        const auto metrics = arena.metrics();
        require(metrics.live_allocations == 5 && metrics.peak_live_allocations == 5 &&
                    metrics.successful_allocations >= 7 && metrics.peak_used >= 32 * 64,
                "standalone type did not grow existing type storage while retaining five owners");
        if (cycle)
            require(successful == allocations.successful, "fresh type lifecycle acquired stale storage state");
        successful = allocations.successful;
        arena.finish();
        require(allocations.released == successful, "fresh type lifecycle leaked storage");
        ++cases;
    }
    {
        // One representative out-of-memory case: refuse the final allocation.
        const auto allowed = successful - 1;
        Allocations allocations;
        allocations.allowed = allowed;
        RawArena arena(allocations);
        const auto result = arena.parse(source, Stop::type);
        require(result[0] == wire(Status::allocation_failure) && result[1] == -1 && result[2] == 0 &&
                    arena.types() >= 0 && arena.types() < static_cast<std::int64_t>(expected.size()),
                "standalone type allocation failure did not fail closed");
        for (std::int64_t index = 0; index < arena.types(); ++index)
            require(arena.type(index) == expected[static_cast<std::size_t>(index)],
                    "failed standalone type growth damaged a committed prefix");
        arena.finish();
        require(allocations.successful == allocations.released, "failed standalone type lifecycle leaked an owner");
        ++cases;
    }
    {
        Allocations allocations;
        RawArena arena(allocations, 0);
        require(arena.parse("i64 next", Stop::type)[0] == wire(Status::allocation_failure),
                "zero-quota standalone type parse was accepted");
        arena.finish();
        require(allocations.successful == allocations.released, "zero-quota standalone type leaked storage");
        ++cases;
    }
}

void rawFields() {
    context = "field type growth and allocation failure";
    std::int64_t next = 0;
    std::vector<TypeWords> types;
    const auto source = rawDeclarationTree(4, next, types) + " value;";
    require(types.size() == 31 && next == 76, "field growth fixture changed its independent topology");
    auto owned = types.back();
    owned[6] = 0;
    owned[7] = 3;
    std::size_t allocationsNeeded = 0;
    for (std::size_t allowed = std::numeric_limits<std::size_t>::max();;) {
        Allocations allocations;
        allocations.allowed = allowed;
        RawArena arena(allocations);
        const auto result = arena.parse(source, Stop::field);
        const bool success = allowed == std::numeric_limits<std::size_t>::max();
        if (success) {
            require(result == Words{wire(Status::success), 0, 0, 78, static_cast<std::int64_t>(source.size()), 0} &&
                        arena.syntaxCount() == 1 && arena.types() == 31 && arena.edges() == 0 &&
                        arena.syntax(0) == SyntaxWords{16, 0, 78, -1, -1, -1, 30, 76, -1, -1, 0, -1} &&
                        arena.type(30) == owned,
                    "wide field lost its type graph or closing delimiter");
            const auto metrics = arena.metrics();
            allocationsNeeded = allocations.successful;
            require(metrics.live_allocations == 5 && metrics.peak_live_allocations == 5 && allocationsNeeded > 5,
                    "field type did not grow within the five-owner arena");
        } else
            require(result[0] == wire(Status::allocation_failure) && result[1] == -1 && arena.syntaxCount() == 0,
                    "field allocation failure published a declaration");
        require(arena.types() >= 0 && arena.types() <= 31, "field failure returned an impossible type prefix");
        for (std::int64_t index = 0; index < arena.types(); ++index)
            require(arena.type(index) == types[index] || (index == 30 && arena.type(index) == owned),
                    "field allocation failure corrupted a committed type prefix");
        arena.finish();
        require(allocations.successful == allocations.released, "partial field leaked an owner");
        ++cases;
        // One representative out-of-memory case: refuse the final allocation.
        if (!success)
            break;
        allowed = allocationsNeeded - 1;
    }
}

void abiControls() {
    context = "independent ABI envelope controls";
    const rlimit noCore{0, 0};
    require(setrlimit(RLIMIT_CORE, &noCore) == 0, "cannot disable negative-control core dumps");
    const std::array<AbiEntry, 8> controls{hosted_parser_clobber_rbp,
                                           hosted_parser_clobber_rbx,
                                           hosted_parser_clobber_r12,
                                           hosted_parser_clobber_r13,
                                           hosted_parser_clobber_r14,
                                           hosted_parser_clobber_r15,
                                           hosted_parser_clobber_canary,
                                           hosted_parser_shift_stack};
    for (std::size_t i = 0; i <= controls.size(); ++i) {
        const auto child = fork();
        require(child >= 0, "cannot fork ABI control");
        if (child == 0) {
            // A pipe core_pattern ignores RLIMIT_CORE; a non-dumpable child skips the dump.
            prctl(PR_SET_DUMPABLE, 0);
            if (i < controls.size())
                checked_hosted_parser_call(nullptr, nullptr, nullptr, controls[i]);
            else
                hosted_parser_misaligned_call(nullptr, nullptr, nullptr, controls[0]);
            _exit(0);
        }
        int status = 0;
        pid_t observed;
        do {
            observed = waitpid(child, &status, 0);
        } while (observed < 0 && errno == EINTR);
        require(observed == child && WIFSIGNALED(status) && WTERMSIG(status) == SIGILL,
                "ABI corruption did not produce SIGILL: " + std::to_string(i));
    }
}
void rawGrowth() {
    context = "real Aurora growth and ABI node records";
    const auto source = chain(100) + ";";
    std::size_t successful = 0;
    {
        Allocations allocations;
        RawArena arena(allocations);
        const auto result = arena.parse(source);
        require(result == Words{wire(Status::success), 198, 199, 199, 199, 0},
                "100-term raw parse did not return exact graph/cursor");
        for (std::int64_t i = 0; i < 199; ++i) {
            const auto node = arena.read(i);
            if (i == 0)
                require(node == NodeWords{wire(NodeKind::literal), 0, -1, -1, 1, 0, 0}, "first literal ABI differs");
            else if (i % 2 == 1)
                require(node == NodeWords{wire(NodeKind::literal), i + 1, -1, -1, 1, i + 1, i + 1},
                        "literal ABI differs");
            else
                require(node == NodeWords{wire(NodeKind::binary), i - 1, i - 2, i - 1, i / 2 + 1, i - 1, i - 1},
                        "binary ABI/topology/depth differs");
        }
        const auto used = arena.metrics();
        require(used.successful_allocations > 5 && used.peak_live_allocations == 5 && used.live_allocations == 5,
                "parser did not grow its node/frame stores while retaining the empty edge/type/statement owners");
        successful = allocations.successful;
        arena.finish();
        require(allocations.released == successful, "success cleanup mismatch");
    }
    {
        Allocations allocations;
        allocations.allowed = 0;
        RawArena arena(allocations);
        require(arena.parse("size_of(i64);")[0] == wire(Status::allocation_failure),
                "failed arena allocation did not reject before typed parsing");
        arena.finish();
    }
    // A partial graph still leaves all five owners releasable exactly once.
    {
        // One representative out-of-memory case: refuse the final allocation.
        const auto allowed = successful - 1;
        Allocations allocations;
        allocations.allowed = allowed;
        RawArena arena(allocations);
        const auto result = arena.parse(source);
        require(result[0] == static_cast<std::int64_t>(Status::allocation_failure) && result[1] == -1,
                "injected allocation/growth failure did not fail closed");
        if (result[2] > 0)
            require(arena.read(0) == NodeWords{wire(NodeKind::literal), 0, -1, -1, 1, 0, 0},
                    "failed growth changed an already committed node");
        arena.finish();
        require(allocations.successful == allocations.released, "failure cleanup mismatch");
    }
    {
        Allocations allocations;
        RawArena arena(allocations, 0);
        require(arena.parse("1;")[0] == static_cast<std::int64_t>(Status::allocation_failure),
                "quota failure accepted");
        arena.finish();
    }
    {
        Allocations allocations;
        RawArena arena(allocations);
        require(arena.parse("1;", Stop::semicolon, 3)[0] == wire(Status::invalid),
                "invalid lexer cursor did not return the named Invalid status");
        arena.finish();
    }
    ++cases;
}
void rawFrameGrowth() {
    context = "real Aurora explicit-frame growth and failure cleanup";
    const auto source = std::string(127, '(') + "1" + std::string(127, ')') + ";";
    const NodeWords literal{wire(NodeKind::literal), 127, -1, -1, 1, 127, 127};
    std::size_t successful = 0;
    {
        Allocations allocations;
        RawArena arena(allocations);
        const auto result = arena.parse(source);
        require(result == Words{wire(Status::success), 0, 1, 255, 255, 0} && arena.read(0) == literal,
                "127 nested groups did not return the exact leaf graph/cursor");
        const auto used = arena.metrics();
        // One leaf needs only the first eight-node capacity. Payload above the
        // first eight-frame plus eight-node capacities therefore proves actual
        // explicit-frame growth, independently of the allocation count.
        require(used.peak_used > 8 * 40 + 8 * 56 && used.successful_allocations > 5 &&
                    used.peak_live_allocations == 5 && used.live_allocations == 5,
                "nested parser did not grow its explicit frame owner");
        successful = allocations.successful;
        arena.finish();
        require(allocations.released == successful, "nested success cleanup mismatch");
    }
    {
        // One representative out-of-memory case: refuse the final allocation.
        const auto allowed = successful - 1;
        Allocations allocations;
        allocations.allowed = allowed;
        RawArena arena(allocations);
        const auto result = arena.parse(source);
        require(result[0] == wire(Status::allocation_failure) && result[1] == -1,
                "injected frame-growth failure did not fail closed");
        if (result[2] > 0)
            require(arena.read(0) == literal, "failed frame growth changed an already committed node");
        arena.finish();
        require(allocations.successful == allocations.released, "frame-growth failure cleanup mismatch");
    }
    ++cases;
}
void rawArguments() {
    context = "real argument-edge growth and failure cleanup";
    constexpr std::int64_t count = 257;
    std::string source = "f(";
    for (std::int64_t index = 0; index < count; ++index) {
        if (index)
            source += ',';
        source += '1';
    }
    source += ");";
    std::size_t successful = 0;
    {
        Allocations allocations;
        RawArena arena(allocations);
        const auto result = arena.parse(source);
        require(result == Words{wire(Status::success), count, count + 1, 2 * count + 2, 2 * count + 2, 0},
                "wide call did not return the complete graph/cursor");
        require(arena.edges() == count &&
                    arena.read(count) == NodeWords{wire(NodeKind::call), 0, count - 1, count, 2, 0, 2 * count + 1},
                "call ABI, arity or closing-token provenance differs");
        for (std::int64_t index = 0; index < count; ++index)
            require(arena.edge(index) == EdgeWords{index, index - 1, index + 1, 2, -1},
                    "reverse-linked argument ABI differs");
        const auto metrics = arena.metrics();
        require(metrics.successful_allocations > 10 && metrics.live_allocations == 5 &&
                    metrics.peak_live_allocations == 5,
                "wide call did not grow independent node and argument owners");
        successful = allocations.successful;
        arena.finish();
    }
    {
        // One representative out-of-memory case: refuse the final allocation.
        const auto allowed = successful - 1;
        Allocations allocations;
        allocations.allowed = allowed;
        RawArena arena(allocations);
        const auto result = arena.parse(source);
        require(result[0] == wire(Status::allocation_failure) && result[1] == -1,
                "injected argument allocation failure did not reject");
        arena.finish();
        require(allocations.successful == allocations.released, "partial argument graph leaked an owner");
    }
    ++cases;
}
void rawAggregates() {
    constexpr std::int64_t count = 257;
    for (const auto kind : {NodeKind::array_literal, NodeKind::construct, NodeKind::array_zero}) {
        // ArrayZero selects the constructor profile; its nonempty result must
        // be ArrayLiteral. No input profile imposes a fixed arity ceiling.
        const bool designated = kind == NodeKind::construct, constructor = kind == NodeKind::array_zero;
        const auto stop = constructor ? Stop::constructor_braces : Stop::semicolon;
        std::string source = designated ? "ns::Box{" : constructor ? "values{" : "{";
        for (std::int64_t index = 0; index < count; ++index) {
            if (index)
                source += ',';
            if (designated)
                source += ".f" + std::to_string(index) + "=";
            source += '1';
        }
        source += "};";
        context = "wide aggregate ABI " + source;
        const auto first = designated ? 7 : constructor ? 2 : 1;
        const auto step = designated ? 5 : 2;
        const auto close = designated ? 5 * count + 3 : constructor ? 2 * count + 1 : 2 * count;
        std::size_t successful = 0;
        {
            Allocations allocations;
            RawArena arena(allocations);
            require(arena.parse(source, stop) == Words{wire(Status::success),
                                                       count,
                                                       count + 1,
                                                       close + 1,
                                                       static_cast<std::int64_t>(source.size() - 1),
                                                       0} &&
                        arena.read(count) == NodeWords{wire(designated ? NodeKind::construct : NodeKind::array_literal),
                                                       0,
                                                       count - 1,
                                                       count,
                                                       2,
                                                       designated ? 2 : 0,
                                                       close} &&
                        arena.edges() == count,
                    "wide aggregate did not return the exact complete graph/cursor");
            for (std::int64_t index = 0; index < count; ++index) {
                const auto token = first + step * index;
                require(arena.read(index) == NodeWords{wire(NodeKind::literal), token, -1, -1, 1, token, token},
                        "wide aggregate child order/token differs");
                require(arena.edge(index) == EdgeWords{index, index - 1, index + 1, 2, designated ? 5 + 5 * index : -1},
                        "wide aggregate edge/field-label ABI differs");
            }
            const auto metrics = arena.metrics();
            require(metrics.successful_allocations > 10 && metrics.live_allocations == 5 &&
                        metrics.peak_live_allocations == 5,
                    "wide aggregate did not grow independent node/edge owners");
            successful = allocations.successful;
            arena.finish();
            require(allocations.successful == allocations.released, "wide aggregate cleanup mismatch");
        }
        {
            // One representative out-of-memory case: refuse the final allocation.
            const auto allowed = successful - 1;
            Allocations allocations;
            allocations.allowed = allowed;
            RawArena arena(allocations);
            const auto result = arena.parse(source, stop);
            require(result[0] == wire(Status::allocation_failure) && result[1] == -1,
                    "aggregate allocation/growth failure did not fail closed");
            if (result[2] > 0)
                require(arena.read(0) == NodeWords{wire(NodeKind::literal), first, -1, -1, 1, first, first},
                        "failed aggregate growth changed a committed node");
            arena.finish();
            require(allocations.successful == allocations.released, "partial aggregate graph leaked an owner");
        }
        ++cases;
    }
}

} // namespace

void callCatalogueIsolation() {
    context = "Call catalogue compilation isolation";
    const auto compile = [](const std::string &body) {
        aurora::HostedResolution resolution;
        const auto source = std::make_shared<const aurora::SourceText>("catalogue.au", "module catalogue;" + body);
        const auto header = resolution.add(source);
        const auto resolved = resolution.resolve({header.id}, header.id, aurora::AnalysisMode::Check, true);
        aurora::X86Emitter emitter;
        return std::array<std::string, 3>{emitter.emit(resolved.module),
                                          emitter.stackFactsJson(resolved.module),
                                          emitter.abiFactsJson(resolved.module, resolved.abiDeclarations)};
    };
    const std::string ordinary = "auto f()->i64{return 7;}";
    const auto before = compile(ordinary);
    const auto enabled = compile("template<Scalar T> auto identity(T value)->T{return value;}"
                                 "auto f()->bool{return identity<i64>(7)==7 && "
                                 "builtin::CallStatus::replied==builtin::CallStatus::replied;}");
    const auto after = compile(ordinary);
    require(before == after && before[2].find("__au_call_result") == std::string::npos &&
                enabled[2].find("__au_call_result") != std::string::npos &&
                enabled[2].find("__au_call_status") != std::string::npos,
            "Call catalogue leaked across compiler instances or failed status-only activation");
    ++cases;
}

int main(int argc, char **argv) {
    try {
        const bool updating = argc == 4 && std::string_view(argv[1]) == "--update";
        require(argc == 3 || updating, "usage: hosted-parser-test [--update] CASES GOLDEN");
        Golden golden(argv[argc - 1], updating);
        const auto all = readCases(argv[argc - 2]);
        for (const auto &item : all)
            golden.check(item.name, run(item));
        golden.finish(argv[argc - 1]);
        const auto goldenCases = cases;
        callCatalogueIsolation();
        rawCatalogueControls();
        rawLinkageCaches();
        rawLinkageModes();
        rawModuleTraversal();
        rawPreambleEnums();
        rawModules();
        rawAdmission();
        rawCallableGrowth();
        rawFields();
        rawDeclarationTypeGrowth();
        rawBodies();
        rawTypeGrowth();
        abiControls();
        rawGrowth();
        rawFrameGrowth();
        rawArguments();
        rawAggregates();
        resolvedModules();
        resolvedVisibility();
        resolvedLinkageNames();
        rawResolutionOwnership();
        rawMetadataOwnership();
        rawInstructionOwnership();
        rawInstructionAdmission();
        std::cout << "PASS hosted parser: " << goldenCases << " golden cases, " << cases - goldenCases
                  << " ABI, growth, ownership and typed-module controls\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "FAIL " << error.what() << '\n';
        return 1;
    }
}
