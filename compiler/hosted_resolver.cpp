// Trusted projection boundary for one Aurora-owned resolution session. The host
// retains source snapshots and file-opening authority, never semantic lookup.
#include "hosted_resolver.hpp"
#include "hosted_parser.hpp"
#include "hosted_lowering_diagnostics.hpp"
#include "ir_verify.hpp"
#include "lexer.hpp"
#include "../runtime/hosted_bytes.hpp"
#include <algorithm>
#include <array>
#include <charconv>
#include <limits>
#include <iterator>
#include <optional>
#include <set>
#include <utility>
#include <type_traits>

namespace aurora {
namespace {
namespace wire = hosted_abi::compiler_resolver;
namespace lowering = hosted_abi::compiler_lowering;
using hosted_parser::SyntaxKind;
using wire::DeclarationKind;
using wire::MetaTag;
using wire::NativeMode;
using wire::ResolvedTypeKind;
using wire::SemanticError;
using wire::StorageStatus;
using wire::SyntaxTag;
[[noreturn]] void invalidResolution() {
    throw Error(DiagnosticCode::Internal, "invalid hosted resolution result");
}
std::size_t sizeValue(std::int64_t value) {
    if (value < 0 || static_cast<std::uint64_t>(value) > std::numeric_limits<std::size_t>::max())
        invalidResolution();
    return static_cast<std::size_t>(value);
}
int intValue(std::int64_t value) {
    if (value < std::numeric_limits<int>::min() || value > std::numeric_limits<int>::max())
        invalidResolution();
    return static_cast<int>(value);
}
auto words(const wire::MetaRow &row) {
    return std::array{row.value0,
                      row.value1,
                      row.value2,
                      row.value3,
                      row.value4,
                      row.value5,
                      row.value6,
                      row.value7,
                      row.value8,
                      row.value9,
                      row.value10,
                      row.value11,
                      row.value12,
                      row.value13,
                      row.value14};
}
struct ModuleSource {
    std::shared_ptr<const SourceText> source;
    HostedModule header;
    std::vector<std::int64_t> imports;
    std::int64_t sourceBegin = 0;
    int scope = 0;
};
Token retainedSourceToken(const void *session,
                          const std::vector<ModuleSource> &sources,
                          std::int64_t sourceBytes,
                          const wire::MetaRow &value) {
    if (value.tag != MetaTag::source_reference)
        invalidResolution();
    if (value.value1 < 0 || value.value2 < value.value1 || value.value2 > sourceBytes)
        invalidResolution();
    if (value.value0 == -1) {
        std::string text;
        text.reserve(sizeValue(value.value2 - value.value1));
        for (auto at = value.value1; at < value.value2; ++at) {
            const auto byte = aurora_hosted_resolver_read_source(session, at);
            if (byte < 0 || byte > 255)
                invalidResolution();
            text.push_back(static_cast<char>(byte));
        }
        return Token(std::move(text), 0);
    }
    if (value.value0 < 0 || sizeValue(value.value0) >= sources.size())
        invalidResolution();
    const auto &unit = sources[sizeValue(value.value0)];
    if (value.value1 < unit.sourceBegin ||
        value.value2 - unit.sourceBegin > static_cast<std::int64_t>(unit.source->text.size()))
        invalidResolution();
    const auto begin = sizeValue(value.value1 - unit.sourceBegin), end = sizeValue(value.value2 - unit.sourceBegin);
    SourceSpan span;
    span.source = unit.source;
    span.begin = {begin, intValue(value.value3), intValue(value.value4)};
    span.end = {end, intValue(value.value7), intValue(value.value8)};
    if (span.begin.line < 1 || span.begin.column < 1 || span.end.line < span.begin.line || span.end.column < 1)
        invalidResolution();
    return Token(unit.source->text.substr(begin, end - begin), std::move(span));
}
class Projection {
    const void *session;
    const std::vector<ModuleSource> &sources;
    std::int64_t sourceBytes;
    std::int64_t syntaxCount = 0;
    std::vector<wire::MetaRow> metadata;
    std::vector<std::optional<Type>> types;
    std::vector<std::optional<std::string>> natives;
    std::vector<bool> activeType;
    int constructionDepth = 0;
    class Depth {
        int &count;

    public:
        explicit Depth(int &value) : count(value) {
            if (++count > 128)
                invalidResolution();
        }
        ~Depth() {
            --count;
        }
    };
    const wire::MetaRow &meta(std::int64_t index, MetaTag tag) const {
        if (index < 0 || sizeValue(index) >= metadata.size() || metadata[sizeValue(index)].tag != tag)
            invalidResolution();
        return metadata[sizeValue(index)];
    }
    wire::SyntaxRow syntaxRow(std::int64_t index) const {
        if (index < 0 || index >= syntaxCount)
            invalidResolution();
        wire::SyntaxRow result;
        aurora_hosted_resolver_read_syntax(session, index, &result);
        return result;
    }
    wire::SyntaxRow node(std::int64_t index, SyntaxTag tag) const {
        const auto result = syntaxRow(index);
        if (result.tag != tag)
            invalidResolution();
        return result;
    }
    wire::ResolvedRow decoration(std::int64_t index) const {
        if (index < 0 || index >= syntaxCount)
            invalidResolution();
        wire::ResolvedRow result;
        aurora_hosted_resolver_read_resolved(session, index, &result);
        return result;
    }
    const ModuleSource &module(std::int64_t index) const {
        if (index < 0 || sizeValue(index) >= sources.size())
            invalidResolution();
        return sources[sizeValue(index)];
    }
    std::vector<std::int64_t> list(std::int64_t last, std::int64_t parent, SyntaxTag tag) const {
        std::vector<std::int64_t> result;
        for (auto current = last; current != -1;) {
            if (current < 0 || current >= parent)
                invalidResolution();
            const auto &value = node(current, tag);
            result.push_back(current);
            parent = current;
            current = tag == SyntaxTag::edge ? value.value1 : value.value2;
        }
        std::reverse(result.begin(), result.end());
        return result;
    }
    std::vector<std::int64_t> links(std::int64_t head, MetaTag tag, std::size_t next) const {
        std::vector<std::int64_t> result;
        std::set<std::int64_t> seen;
        for (auto current = head; current != -1;) {
            const auto &value = meta(current, tag);
            if (!seen.insert(current).second)
                invalidResolution();
            result.push_back(current);
            current = words(value).at(next);
        }
        return result;
    }
    Token sourceToken(std::int64_t reference) const {
        return retainedSourceToken(session, sources, sourceBytes, meta(reference, MetaTag::source_reference));
    }
    std::string prefix(std::int64_t index) const {
        std::vector<std::string> parts;
        while (index != -1) {
            const auto &value = meta(index, MetaTag::prefix);
            const auto &atom = meta(value.value1, MetaTag::atom);
            parts.push_back(sourceToken(atom.value2).text);
            if (value.value0 < -1 || value.value0 >= index)
                invalidResolution();
            index = value.value0;
        }
        std::string result;
        for (auto part = parts.rbegin(); part != parts.rend(); ++part) {
            if (!result.empty())
                result += "::";
            result += *part;
        }
        return result;
    }
    std::vector<TemplateArgument> arguments(std::int64_t instance) {
        if (instance == -1)
            return {};
        const auto &value = meta(instance, MetaTag::instance);
        if (value.value1 < 1 || value.value1 > 2)
            invalidResolution();
        std::vector<TemplateArgument> result;
        for (std::int64_t i = 0; i < value.value1; ++i) {
            const auto argument = words(value)[sizeValue(i) + 2];
            if (argument < 0) {
                if (argument < -65 || argument > -2)
                    invalidResolution();
                result.push_back(TemplateArgument::capacity(-argument - 1));
            } else {
                const auto concrete = type(argument);
                TemplateArgument converted(concrete.kind);
                converted.className = concrete.className;
                converted.displayName = concrete.displayName;
                converted.resolvedClass = concrete.resolvedClass;
                result.push_back(std::move(converted));
            }
        }
        return result;
    }
    static std::string argumentSuffix(const std::vector<TemplateArgument> &arguments, bool display) {
        std::string result = "<";
        for (const auto &argument : arguments) {
            if (result.size() > 1)
                result += ",";
            if (argument.kind == TemplateArgumentKind::Value)
                result += std::to_string(argument.value);
            else if (argument.type == TypeKind::Class || argument.type == TypeKind::Enum)
                result += display && !argument.displayName.empty() ? argument.displayName : argument.className;
            else
                result += typeName(Type(argument.type));
        }
        return result + ">";
    }
    std::string rawTypeName(std::int64_t root, int depth = 0) const {
        if (depth >= 128)
            invalidResolution();
        const auto &value = node(root, SyntaxTag::type);
        using Kind = hosted_parser::TypeKind;
        const auto child = [&](std::int64_t index) {
            if (index < 0 || index >= root)
                invalidResolution();
            return rawTypeName(index, depth + 1);
        };
        switch (value.type_tag) {
        case Kind::i64_type:
            return typeName(Type::I64);
        case Kind::u64_type:
            return typeName(Type::U64);
        case Kind::u8_type:
            return typeName(Type::U8);
        case Kind::bool_type:
            return typeName(Type::Bool);
        case Kind::own_type:
            return typeName(Type::Own);
        case Kind::ref_type:
            return typeName(Type::Ref);
        case Kind::mutref_type:
            return typeName(Type::MutRef);
        case Kind::byte_span:
            return typeName(Type::ByteSpan);
        case Kind::parameter:
        case Kind::length_parameter:
            return prefix(decoration(root).value0);
        case Kind::capacity: {
            const auto text = sourceToken(value.value0).text;
            std::int64_t capacity = 0;
            const auto parsed = std::from_chars(text.data(), text.data() + text.size(), capacity);
            if (parsed.ec != std::errc{} || parsed.ptr != text.data() + text.size())
                invalidResolution();
            return std::to_string(capacity);
        }
        case Kind::named: {
            auto result = prefix(decoration(root).value0);
            if (value.value3 >= 0) {
                result += "<" + child(value.value3);
                if (value.value4 >= 0)
                    result += ", " + child(value.value4);
                result += ">";
            }
            return result;
        }
        case Kind::builtin_type:
        case Kind::builtin_class:
            return "builtin::" + sourceToken(value.value1).text;
        case Kind::array_type:
            return "array<" + child(value.value3) + ", " + child(value.value4) + ">";
        case Kind::owned_values:
            return "builtin::OwnedValues<" + child(value.value3) + ">";
        case Kind::value_span:
            return "builtin::span<const " + child(value.value3) + ">";
        default:
            invalidResolution();
        }
    }
    std::string specializationSpelling(std::int64_t prototype, std::int64_t request) {
        const auto &identity = meta(prototype, MetaTag::symbol);
        const auto value = syntaxRow(request);
        const auto root = value.tag == SyntaxTag::expression ? value.value6 : request;
        const auto &syntaxType = node(root, SyntaxTag::type);
        std::vector<TemplateArgument> values;
        for (const auto child : {syntaxType.value3, syntaxType.value4}) {
            if (child == -1)
                continue;
            const auto &argument = node(child, SyntaxTag::type);
            if (argument.type_tag == hosted_parser::TypeKind::capacity) {
                const auto spelling = sourceToken(argument.value0).text;
                std::int64_t capacity = 0;
                const auto parsed = std::from_chars(spelling.data(), spelling.data() + spelling.size(), capacity);
                if (parsed.ec != std::errc{} || parsed.ptr != spelling.data() + spelling.size() || capacity < 1 ||
                    capacity > 64)
                    invalidResolution();
                values.push_back(TemplateArgument::capacity(capacity));
            } else {
                const auto concrete = type(decoration(child).value2);
                TemplateArgument converted(concrete.kind);
                converted.className = concrete.className;
                converted.displayName = concrete.displayName;
                converted.resolvedClass = concrete.resolvedClass;
                values.push_back(std::move(converted));
            }
        }
        return prefix(identity.value3) + argumentSuffix(values, false);
    }
    std::string display(std::int64_t symbol) {
        const auto &value = meta(symbol, MetaTag::symbol);
        if (value.native_tag == NativeMode::sealed_builtin) {
            const auto &descriptor = meta(value.value8, MetaTag::context);
            return prefix(descriptor.value1);
        }
        auto result = prefix(value.value3);
        if (value.value9 >= 0)
            result += argumentSuffix(arguments(value.value9), true);
        return result;
    }
    std::string native(std::int64_t symbol) {
        const auto &value = meta(symbol, MetaTag::symbol);
        if (value.native_tag < NativeMode::root_entry || value.native_tag > NativeMode::sealed_builtin)
            invalidResolution();
        if (value.native_tag != NativeMode::sealed_builtin)
            module(value.value1);
        auto &cached = natives[sizeValue(symbol)];
        if (cached)
            return *cached;
        const auto &name = meta(value.value0, MetaTag::source_reference);
        if (name.value0 != -1 || name.value9 != symbol || name.value1 < 0 || name.value2 <= name.value1 ||
            name.value2 > sourceBytes)
            invalidResolution();
        const auto size = name.value2 - name.value1;
        std::string result(sizeValue(size), '\0');
        for (std::int64_t offset = 0; offset < size;) {
            wire::LinkageChunk chunk{};
            aurora_hosted_resolver_linkage_chunk(session, symbol, offset, &chunk);
            if (chunk.byteCount <= 0 || chunk.byteCount > 512 || chunk.byteCount > size - offset)
                invalidResolution();
            std::copy_n(chunk.payload.begin(), sizeValue(chunk.byteCount), result.begin() + offset);
            offset += chunk.byteCount;
        }
        cached = result;
        return result;
    }
    Type type(std::int64_t index) {
        Depth depth(constructionDepth);
        const auto &value = meta(index, MetaTag::concrete_type);
        auto &cached = types[sizeValue(index)];
        if (cached)
            return *cached;
        if (activeType[sizeValue(index)])
            invalidResolution();
        activeType[sizeValue(index)] = true;
        Type result;
        switch (value.concrete_tag) {
        case ResolvedTypeKind::i64_value:
            result = Type::I64;
            break;
        case ResolvedTypeKind::u64_value:
            result = Type::U64;
            break;
        case ResolvedTypeKind::u8_value:
            result = Type::U8;
            break;
        case ResolvedTypeKind::bool_value:
            result = Type::Bool;
            break;
        case ResolvedTypeKind::owner:
            result = Type::Own;
            break;
        case ResolvedTypeKind::reference:
            result = Type::Ref;
            break;
        case ResolvedTypeKind::mutable_reference:
            result = Type::MutRef;
            break;
        case ResolvedTypeKind::byte_span:
            result = Type::ByteSpan;
            break;
        case ResolvedTypeKind::byte_region:
            result = Type::ByteRegion;
            break;
        case ResolvedTypeKind::owned_bytes:
            result = Type::OwnedBytes;
            break;
        case ResolvedTypeKind::console_session:
            result = Type::ConsoleSession;
            break;
        case ResolvedTypeKind::display_session:
            result = Type::DisplaySession;
            break;
        case ResolvedTypeKind::serve_session:
            result = Type::ServeSession;
            break;
        case ResolvedTypeKind::port_range:
            result = Type::Com1UartGrant;
            break;
        case ResolvedTypeKind::call_session:
            result = Type::CallSession;
            break;
        case ResolvedTypeKind::event_session:
            result = Type::IommuEventSession;
            break;
        case ResolvedTypeKind::class_value:
        case ResolvedTypeKind::enum_value:
            if (value.value1 < 0) {
                if (value.value1 == std::numeric_limits<std::int64_t>::min() || value.value1 == -1)
                    invalidResolution();
                result = Type(prefix(-value.value1 - 2));
            } else {
                const auto expected = value.concrete_tag == ResolvedTypeKind::class_value
                                          ? DeclarationKind::class_value
                                          : DeclarationKind::enumeration;
                if (meta(value.value1, MetaTag::symbol).declaration_tag != expected)
                    invalidResolution();
                result = value.concrete_tag == ResolvedTypeKind::class_value ? Type(native(value.value1))
                                                                             : Type::enumeration(native(value.value1));
                result.displayName = display(value.value1);
                result.resolvedClass = meta(value.value1, MetaTag::symbol).native_tag != NativeMode::sealed_builtin;
            }
            break;
        case ResolvedTypeKind::array_value:
            result = Type::array(type(value.value2), intValue(value.value3));
            break;
        case ResolvedTypeKind::owned_values:
            result = Type::ownedValues(type(value.value2));
            break;
        case ResolvedTypeKind::value_span:
            result = Type::valueSpan(type(value.value2));
            break;
        default:
            invalidResolution();
        }
        activeType[sizeValue(index)] = false;
        cached = result;
        return result;
    }

public:
    Projection(const void *session, const std::vector<ModuleSource> &sources, std::uint64_t payloadBytes)
        : session(session), sources(sources) {
        sourceBytes = aurora_hosted_resolver_count(session, 0);
        if (sourceBytes < 0 || static_cast<std::uint64_t>(sourceBytes) > payloadBytes)
            invalidResolution();
        const auto load = [&](auto &values, std::int64_t pool, auto read) {
            const auto count = sizeValue(aurora_hosted_resolver_count(session, pool));
            if (count > values.max_size() ||
                count > payloadBytes / sizeof(typename std::remove_reference_t<decltype(values)>::value_type))
                invalidResolution();
            values.resize(count);
            for (std::size_t i = 0; i < count; ++i)
                read(session, static_cast<std::int64_t>(i), &values[i]);
        };
        syntaxCount = aurora_hosted_resolver_count(session, 1);
        if (syntaxCount < 0 || syntaxCount != aurora_hosted_resolver_count(session, 3) ||
            static_cast<std::uint64_t>(syntaxCount) > payloadBytes / sizeof(wire::SyntaxRow) ||
            static_cast<std::uint64_t>(syntaxCount) > payloadBytes / sizeof(wire::ResolvedRow))
            invalidResolution();
        load(metadata, 2, aurora_hosted_resolver_read_meta);
        types.resize(metadata.size());
        natives.resize(metadata.size());
        activeType.resize(metadata.size());
    }
    [[noreturn]] void diagnostic(const wire::SessionStatus &status);
    std::vector<std::int64_t> declarations(std::size_t field) const {
        const wire::MetaRow *output = nullptr;
        for (const auto &value : metadata)
            if (value.tag == MetaTag::context && value.value0 == 1) {
                if (output)
                    invalidResolution();
                output = &value;
            }
        if (!output || field < 1 || field > 3)
            invalidResolution();
        std::vector<std::int64_t> result;
        for (const auto link : links(words(*output)[field], MetaTag::link, 1))
            result.push_back(meta(link, MetaTag::link).value0);
        return result;
    }
    std::string callableName(std::int64_t symbol) {
        const auto &identity = meta(symbol, MetaTag::symbol);
        if (identity.declaration_tag != DeclarationKind::function &&
            identity.declaration_tag != DeclarationKind::method &&
            identity.declaration_tag != DeclarationKind::constructor)
            invalidResolution();
        return native(symbol);
    }
    std::string nominalName(std::int64_t symbol, DeclarationKind kind) {
        if (meta(symbol, MetaTag::symbol).declaration_tag != kind)
            invalidResolution();
        return native(symbol);
    }
    AbiDeclarations abiDeclarations() {
        AbiDeclarations result;
        const auto sourceName = [&](std::int64_t symbol) {
            const auto &identity = meta(symbol, MetaTag::symbol);
            if (identity.native_tag == NativeMode::sealed_builtin)
                return native(symbol);
            const auto scope = prefix(identity.value2);
            const auto name = sourceToken(node(identity.value5, SyntaxTag::declaration).value0).text;
            return scope.empty() ? name : scope + "::" + name;
        };
        const auto function = [&](std::int64_t symbol) {
            result.functions.emplace(callableName(symbol), AbiDeclaration{sourceName(symbol), {}});
        };
        for (const auto symbol : declarations(1))
            function(symbol);
        for (const auto symbol : declarations(2)) {
            const auto &identity = meta(symbol, MetaTag::symbol);
            AbiDeclaration record{sourceName(symbol), {}};
            if (identity.native_tag == NativeMode::sealed_builtin) {
                const auto &descriptor = meta(identity.value8, MetaTag::context);
                for (const auto child : links(descriptor.value4, MetaTag::context, 3))
                    record.members.push_back(sourceToken(meta(child, MetaTag::context).value1).text);
            } else {
                const auto root = identity.value5;
                const auto value = node(root, SyntaxTag::declaration);
                if (value.declaration_tag != SyntaxKind::class_definition)
                    invalidResolution();
                for (const auto wrapper : list(value.value7, root, SyntaxTag::declaration)) {
                    const auto member = node(wrapper, SyntaxTag::declaration);
                    if (member.declaration_tag != SyntaxKind::declaration || member.value7 >= wrapper)
                        invalidResolution();
                    const auto declaration = node(member.value7, SyntaxTag::declaration);
                    if (declaration.declaration_tag == SyntaxKind::field)
                        record.members.push_back(sourceToken(declaration.value6).text);
                    else
                        function(decoration(member.value7).value1);
                }
            }
            result.records.emplace(nominalName(symbol, DeclarationKind::class_value), std::move(record));
        }
        for (const auto symbol : declarations(3)) {
            const auto &identity = meta(symbol, MetaTag::symbol);
            AbiDeclaration enumeration{sourceName(symbol), {}};
            if (identity.native_tag == NativeMode::sealed_builtin) {
                const auto &descriptor = meta(identity.value8, MetaTag::context);
                for (const auto child : links(descriptor.value4, MetaTag::context, 3))
                    enumeration.members.push_back(sourceToken(meta(child, MetaTag::context).value1).text);
            } else {
                const auto root = identity.value5;
                const auto value = node(root, SyntaxTag::declaration);
                if (value.declaration_tag != SyntaxKind::enum_definition)
                    invalidResolution();
                for (const auto child : list(value.value7, root, SyntaxTag::declaration)) {
                    const auto item = node(child, SyntaxTag::declaration);
                    if (item.declaration_tag != SyntaxKind::enum_case)
                        invalidResolution();
                    enumeration.members.push_back(sourceToken(item.value0).text);
                }
            }
            result.enums.emplace(nominalName(symbol, DeclarationKind::enumeration), std::move(enumeration));
        }
        return result;
    }
    HostedLoweringDiagnosticServices diagnosticServices() {
        return {[&](auto reference) {
                    return sourceToken(reference);
                },
                [&](auto identity) {
                    return typeName(type(identity));
                },
                [&](auto reason, auto identity) {
                    return diagnosticName(reason, identity);
                }};
    }
    std::string diagnosticName(lowering::LoweringError reason, std::int64_t identity) {
        using lowering::LoweringError;
        if (reason == LoweringError::unknown_nested_class_type)
            return prefix(identity);
        if (identity < 0 || sizeValue(identity) >= metadata.size())
            invalidResolution();
        const auto &value = metadata[sizeValue(identity)];
        switch (reason) {
        case LoweringError::unknown_class_field:
        case LoweringError::unknown_local:
        case LoweringError::use_after_move:
        case LoweringError::duplicate_local:
            if (value.tag == MetaTag::atom)
                return sourceToken(value.value2).text;
            return sourceToken(identity).text;
        case LoweringError::call_argument_count:
        case LoweringError::no_exact_overload:
            return prefix(identity);
        case LoweringError::unknown_function:
            if (value.tag == MetaTag::symbol)
                return callableName(identity);
            return prefix(identity);
        default:
            invalidResolution();
        }
    }
    std::int64_t sourceByteCount() const {
        return sourceBytes;
    }
};
[[noreturn]] void Projection::diagnostic(const wire::SessionStatus &status) {
    std::string message;
    SourceSpan location;
    switch (status.diagnostic) {
    case SemanticError::reserved_prefix:
        message = "reserved compiler identifier prefix: __au_";
        break;
    case SemanticError::reserved_builtin:
        message = "reserved builtin namespace or identifier: builtin";
        break;
    case SemanticError::reserved_class:
        message = "duplicate or reserved class name";
        break;
    case SemanticError::reserved_function:
        message = "duplicate or reserved function name";
        if (status.first >= 0)
            message += ": " + prefix(status.first);
        break;
    case SemanticError::enum_count:
        message = "module graph exceeds 64 enum definitions";
        break;
    case SemanticError::enum_cases:
        message = "enum class requires between 1 and 256 named cases";
        break;
    case SemanticError::template_count:
        message = "module graph exceeds 64 class templates and function templates combined";
        break;
    case SemanticError::answer_overload:
        message = "bootstrap answer entrypoint cannot be overloaded";
        break;
    case SemanticError::owned_named:
        message = "owned values require a named concrete copied class";
        break;
    case SemanticError::span_named:
        message = "typed spans require a named concrete copied class";
        break;
    case SemanticError::unsubstituted_array:
        message = "unsubstituted array element or capacity parameter";
        break;
    case SemanticError::template_function_call:
        message = "function template calls inside template bodies are unsupported";
        break;
    case SemanticError::template_static_body:
        message = "template body requires a statically named class template";
        break;
    case SemanticError::instance_count:
        message = "module graph exceeds 256 class template instantiations and function instances combined";
        break;
    case SemanticError::template_depth:
        message = "template-id nesting exceeds 4";
        break;
    case SemanticError::template_nominal_depth:
        message = "template-id nesting exceeds 4 after substitution";
        break;
    case SemanticError::class_array_capacity:
        message = "class-element array capacity must be between 1 and 64";
        break;
    case SemanticError::array_explicit:
        message = "builtin array requires explicit element and length arguments";
        break;
    case SemanticError::method_parameter:
        message = "only scalar, enum or class method parameters are supported";
        break;
    case SemanticError::constructor_parameter:
        message = "only scalar, enum or class constructor parameters are supported";
        break;
    case SemanticError::function_signature_template:
        message = "function template signature requires a class template";
        break;
    case SemanticError::function_signature_concrete:
        message = "function template signature requires a concrete fixed type";
        break;
    case SemanticError::overload_parameters:
        message = "ordinary overload parameters require scalar, enum, class or readonly byte span types";
        break;
    case SemanticError::array_constructor:
        message = "builtin array does not provide a class constructor";
        break;
    case SemanticError::template_expression:
        message = "template arguments require a class construction";
        break;
    case SemanticError::function_template_arguments:
        message = "function template arguments require a call";
        break;
    case SemanticError::initializer_method:
        message = "constructor initializer cannot access receiver methods";
        break;
    case SemanticError::missing_function:
        message = "module graph must contain a function";
        break;
    case SemanticError::class_parameters:
        message = "class templates require one or two Scalar or Value parameters, or Scalar and i64";
        break;
    case SemanticError::capacity_order:
        message = "capacity templates require Scalar followed by i64";
        break;
    case SemanticError::unresolved_nested_argument:
        message = "unresolved nested class template argument";
        break;
    case SemanticError::class_scalar_argument:
        message = "class template Scalar argument requires i64, u64, u8 or bool";
        break;
    case SemanticError::class_value_argument:
        message = "class template Value argument requires scalar, named class or enum values";
        break;
    case SemanticError::class_capacity:
        message = "class template capacity requires an i64 value between 1 and 64";
        break;
    case SemanticError::class_body_template:
        message = "class template bodies cannot name template specializations";
        break;
    case SemanticError::invalid_substituted_array:
        message = "invalid array type after template substitution";
        break;
    case SemanticError::dependent_array:
        message = "dependent array metadata requires an array type";
        break;
    case SemanticError::function_nested_dependent:
        message = "nested dependent template arguments are not supported";
        break;
    case SemanticError::function_array_scalar:
        message = "function template array element requires a scalar type";
        break;
    case SemanticError::function_capacity:
        message = "function templates do not have capacity parameters";
        break;
    case SemanticError::function_constraint:
        message = "function template argument violates Scalar or Value constraint";
        break;
    case SemanticError::function_parameters:
        message = "function templates require one or two namespace-level type parameters";
        break;
    case SemanticError::function_boundaries:
        message = "function template boundaries require copied Scalar or Value types";
        break;
    case SemanticError::function_parameter_names:
        message = "function templates require distinct Scalar or Value parameters";
        break;
    case SemanticError::duplicate_member:
        message = "duplicate or reserved class member: " + prefix(status.first);
        break;
    case SemanticError::namespace_collision:
        message = "namespace and declaration name collide: " + prefix(status.first);
        break;
    case SemanticError::duplicate_enum_case:
        message = "duplicate enum case: " + prefix(status.first);
        break;
    case SemanticError::overload_count:
        message = "ordinary overload set exceeds 32 declarations: " + prefix(status.first);
        break;
    case SemanticError::borrowed_overload:
        message = "borrowed-object functions cannot be overloaded: " + prefix(status.first);
        break;
    case SemanticError::wrong_kind:
        message = "declaration has the wrong kind: " + prefix(status.first);
        break;
    case SemanticError::private_function:
        message = "private function is not imported: " + prefix(status.first);
        break;
    case SemanticError::private_type:
        message = "private type is not imported: " + prefix(status.first);
        break;
    case SemanticError::unknown_argument:
        message = "unknown named class or enum template argument: " + prefix(status.first);
        break;
    case SemanticError::argument_concrete:
        message = "template argument requires a named concrete class or enum: " + prefix(status.first);
        break;
    case SemanticError::unsubstituted_parameter:
        message = "unsubstituted class template parameter: " + prefix(status.first);
        break;
    case SemanticError::template_static_type:
        message = "function template requires a statically named class template: " + prefix(status.first);
        break;
    case SemanticError::unknown_function_template:
        message = "unknown function template: " + prefix(status.first);
        break;
    case SemanticError::function_arity:
        message = "wrong number of function template arguments for " + prefix(status.first);
        break;
    case SemanticError::unknown_template:
        message = "unsupported type or unknown class template; expected a declared template: " + prefix(status.first);
        break;
    case SemanticError::class_arity:
        message = "wrong number of class template arguments for " + prefix(status.first);
        break;
    case SemanticError::concrete_type:
        message = "declaration is not a concrete type: " + prefix(status.first);
        break;
    case SemanticError::field_callable:
        message = "class field is not callable: " + prefix(status.first);
        break;
    case SemanticError::class_arguments:
        message = "class template requires explicit type arguments: " + prefix(status.first);
        break;
    case SemanticError::function_arguments:
        message = "function template requires explicit type arguments: " + prefix(status.first);
        break;
    case SemanticError::enum_named:
        message = "enum values require a named case: " + prefix(status.first);
        break;
    case SemanticError::unknown_builtin_case:
        message = "unknown sealed service enum case: " + prefix(status.first);
        break;
    case SemanticError::unknown_enum_case:
        message = "unknown enum case: " + prefix(status.first);
        break;
    case SemanticError::duplicate_class_parameter:
        message = "duplicate class template parameter: " + prefix(status.first);
        break;
    case SemanticError::shadow_capacity:
        message = "declaration cannot shadow capacity parameter: " + prefix(status.first);
        break;
    case SemanticError::unknown_class_parameter:
        message = "unknown class template parameter: " + prefix(status.first);
        break;
    case SemanticError::array_scalar_parameter:
        message = "class template array element parameter requires a scalar type: " + prefix(status.first);
        break;
    case SemanticError::unknown_capacity:
        message = "unknown array capacity parameter: " + prefix(status.first);
        break;
    case SemanticError::dependent_conversion:
        message = "dependent scalar conversions are not supported: " + prefix(status.first);
        break;
    case SemanticError::capacity_callable:
        message = "capacity parameter is not callable: " + prefix(status.first);
        break;
    case SemanticError::capacity_move:
        message = "cannot move a capacity parameter: " + prefix(status.first);
        break;
    case SemanticError::capacity_assign:
        message = "cannot assign to a capacity parameter: " + prefix(status.first);
        break;
    case SemanticError::unknown_function_parameter:
        message = "unknown function template parameter: " + prefix(status.first);
        break;
    case SemanticError::dependent_qualified:
        message = "dependent qualified names are not supported: " + prefix(status.first);
        break;
    case SemanticError::dependent_construction:
        message = "dependent construction or conversion is not supported: " + prefix(status.first);
        break;
    case SemanticError::shadow_function_local:
        message = "local cannot shadow a function template parameter: " + prefix(status.first);
        break;
    case SemanticError::array_elements:
        message = "array elements require scalar or concrete copied class types: " + typeName(type(status.first));
        break;
    case SemanticError::unknown_array_element:
        message = "unknown nominal array element type: " + typeName(type(status.first));
        break;
    case SemanticError::resolved_import:
        message = "resolved class type requires a direct visible import: " + typeName(type(status.first));
        break;
    case SemanticError::type_import:
        message = "class type requires a direct visible import: " + typeName(type(status.first));
        break;
    case SemanticError::unknown_class_declaration:
        message = "unknown nominal type in class declaration: " + typeName(type(status.first));
        break;
    case SemanticError::class_signature_import:
        message = "class signature type requires a direct visible import: " + typeName(type(status.first));
        break;
    case SemanticError::export_class_private:
        message = "exported class public signature exposes private type: " + typeName(type(status.first));
        break;
    case SemanticError::argument_import:
        message = "template argument type requires a direct visible import: " + typeName(type(status.first));
        break;
    case SemanticError::function_signature_import:
        message = "function signature type requires a direct visible import: " + typeName(type(status.first));
        break;
    case SemanticError::export_function_private:
        message = "exported function signature exposes private type: " + typeName(type(status.first));
        break;
    case SemanticError::function_template_signature_import:
        message = "function template signature type requires a direct visible import: " + rawTypeName(status.node);
        break;
    case SemanticError::export_function_template_private:
        message = "exported function template signature exposes private type: " + rawTypeName(status.node);
        break;
    case SemanticError::unknown_signature:
        message = "unknown class type in function signature: " + typeName(type(status.first));
        break;
    case SemanticError::construction_import:
        message = "class construction type requires a direct visible import: " + typeName(type(status.first));
        break;
    case SemanticError::duplicate_class:
    case SemanticError::duplicate_function:
    case SemanticError::duplicate_overload:
        message = status.diagnostic == SemanticError::duplicate_class ? "duplicate or reserved class name"
                                                                      : "duplicate or reserved function name";
        message += " in module " + module(status.first).header.moduleName + ": " + prefix(status.second);
        break;
    case SemanticError::ambiguous_visible:
        message = "ambiguous visible declaration";
        if (status.node == -1)
            message += " in " + module(status.second).header.moduleName;
        message += ": " + prefix(status.first);
        break;
    case SemanticError::unknown_resolved_type:
        message = "unknown resolved class identity: " + type(status.first).className;
        break;
    case SemanticError::function_fixed_unknown:
        message = "unknown fixed type in function template signature: " + rawTypeName(status.node);
        break;
    case SemanticError::export_template_private:
        message = "exported function template signature exposes private template: " + rawTypeName(status.node);
        break;
    case SemanticError::shadow_function_parameter: {
        const auto &parameter = node(status.node, SyntaxTag::declaration);
        message = "function parameter cannot shadow a template parameter: " + sourceToken(parameter.value6).text;
        break;
    }
    case SemanticError::unknown_function: {
        const auto &expression = node(status.node, SyntaxTag::expression);
        auto first = sourceToken(expression.value0), last = sourceToken(expression.value4);
        if (first.span.source != last.span.source)
            invalidResolution();
        location = first.span;
        location.end = last.span.end;
        message = "unknown function '" + prefix(status.first) + "' in defining module " +
                  module(status.second).header.moduleName;
        break;
    }
    case SemanticError::unexpanded_function:
    case SemanticError::unexpanded_class:
        message = status.diagnostic == SemanticError::unexpanded_function
                      ? "unexpanded function template specialization: "
                      : "unexpanded class template specialization: ";
        message += specializationSpelling(status.first, status.node);
        break;
    default:
        invalidResolution();
    }
    throw Error(DiagnosticCode::Module, std::move(message), std::move(location));
}
} // namespace
namespace {
std::uint64_t resolutionQuota() {
    const auto add = [](std::uint64_t a, std::uint64_t b) {
        if (b > std::numeric_limits<std::uint64_t>::max() - a)
            invalidResolution();
        return a + b;
    };
    const auto mul = [](std::uint64_t a, std::uint64_t b) {
        if (a && b > std::numeric_limits<std::uint64_t>::max() / a)
            invalidResolution();
        return a * b;
    };
    const auto sum = [&](std::initializer_list<std::uint64_t> values) {
        std::uint64_t result = 0;
        for (const auto value : values)
            result = add(result, value);
        return result;
    };
    const auto &catalog = service::catalog();
    const auto count = [](std::int64_t value) {
        if (value < 0)
            invalidResolution();
        return static_cast<std::uint64_t>(value);
    };
    // Catalog spellings plus the lowerer's retained synthetic "array" name.
    const auto textCount = add(count(catalog.textCount), 1), textBytes = add(count(catalog.textBytes), 5);
    const auto members = count(catalog.memberCount), operations = count(catalog.operationCount);
    const auto serviceParameters = count(catalog.parameterCount), scalars = count(catalog.scalarCount);
    // Existing language/file limits only. This loose ceiling is not allocated
    // eagerly. Each pool grows on demand and reports ordinary allocation failure.
    // Counts charge source projection, interned names/indexes, concrete clones,
    // signatures, public/authority/visibility links and reusable worklists.
    constexpr std::uint64_t B = 4194304, b = 1048576, M = 64, I = 256, H = 4096;
    const auto K = count(catalog.typeCount);
    // No catalog spelling is longer than all catalog text.
    const auto S = mul(4, B), Sx = mul(I + 1, S), U = mul(12, B), D = std::max(b, textBytes);
    const auto L = sum({S, textCount, H}), N = sum({U, L, textCount}), Q = add(B, textBytes);
    const auto P = mul(sum({mul(34, N), S, K}), D);
    const auto storage = sum({64, U, textCount, mul(2, Q), P, L, H});
    const auto storageIndexes = sum({U, mul(2, Q), P, N, L, H, mul(2, M)});
    const auto primitiveKinds = static_cast<std::uint64_t>(ResolvedTypeKind::serve_session) + 1;
    const auto types = sum({mul(2, Sx), K, primitiveKinds}), categories = mul(7, M + 1);
    const auto nominals = add(Sx, K), authority = mul(I, nominals);
    const auto semantic = sum({2,
                               categories,
                               nominals,
                               mul(32, S),
                               S,
                               S,
                               types,
                               I,
                               mul(2, Sx),
                               mul(3, Sx),
                               authority,
                               mul(65, Sx),
                               Sx,
                               nominals,
                               nominals,
                               K,
                               members});
    const auto indexes = sum({types,     S,  categories, 1,  S, authority, mul(32, S),         Sx,       S, S, I,
                              mul(2, K), Sx, Sx,         Sx, S, mul(M, S), mul(mul(32, M), S), nominals, 1, Sx});
    // Shape-only upper bounds for the complete lowering producer ledger.
    // X includes expanded syntax, every discarded static_assert occurrence and
    // failed prefixes. F/fields/carriers/returns are separately named producer
    // substitutions, not new source limits or eagerly reserved storage.
    const auto X = Sx, F = X, fields = add(X, members), carriers = X, returns = add(X, F);
    // The existing six-formal limit bounds the non-frame borrowed identities;
    // borrowed roots (at most four) may supplement the frame-backed local prefix.
    constexpr std::uint64_t maximumFormals = 6, frameBytes = 65536, frameWords = 8192;
    constexpr std::uint64_t localHigh = frameWords + maximumFormals;
    const auto allLocals = mul(F, localHigh);
    // Primitive producers: literal/load/store/operator/index/control/receiver,
    // service/resource operations and <=6 scalar pushes fit 16 per syntax row.
    // A borrowed call has N <= 4 acquisitions, N releases and one call; with
    // tail pushes the bound is 2*N + (6-N) + 1 <= 11, inside that same charge.
    // Array copy/literal/byte-string expansion is <=4*4096 per occurrence;
    // designated/constructor fields <=3 per field/edge; parameter binding <=6/F.
    // Lifetime begins/staging consume <=2/allocation. Every explicit/synthetic
    // return may repeat a full Local prefix; non-return cleanup <=allLocals.
    const auto instructions = sum(
        {mul(16, X), mul(4 * 4096, X), mul(3, X), mul(6, F), mul(2, allLocals), allLocals, mul(returns, localHigh)});
    // A two-service, six-formal call may carry six span positions, six copied
    // snapshot positions and the additional service's two loan/kind items.
    // A borrowed call is a disjoint call kind: its ordered triple list costs
    // 3*N. One-root copied/span calls add two (6-N)-position lists, totaling
    // 13; multi-root scalar-only calls need at most 3*N+(6-N) <= 14.
    // The existing 14-item per-call charge covers both.
    const auto instructionLists = add(mul(14, X), mul(64, X));
    const auto literalBytes = mul(4096, X);
    // Packed u8 leaves make scalar slot count byte-bounded, not word-bounded.
    // Each other durable slot family has its own producer charge, including
    // the OwnedValues subset of owner slots; none is folded into Local scratch.
    const auto scalarSlots = mul(frameBytes, F), objectSlots = mul(frameWords, F);
    const auto arraySlots = mul(frameWords, F), spanSlots = mul(frameWords / 7, F);
    const auto serviceSlots = mul(2, F), regionSlots = F, byteSlots = mul(frameWords / 4, F);
    const auto ownedTypes = byteSlots, spanTypes = spanSlots;
    const auto slots = sum(
        {scalarSlots, objectSlots, arraySlots, spanSlots, serviceSlots, regionSlots, byteSlots, ownedTypes, spanTypes});
    // Only genuine methods/constructors publish Receiver rows; root types are
    // among the existing <=6 explicit ParameterTypes charged below.
    const auto receiverRows = F, classRows = add(nominals, carriers), fieldRows = add(fields, carriers);
    const auto descriptors = sum({7, nominals, X}), views = M, enums = nominals, lint = X;
    const auto outputRows = sum({add(10, operations),
                                 1,
                                 instructions,
                                 slots,
                                 F,
                                 receiverRows,
                                 mul(2, classRows),
                                 fieldRows,
                                 carriers,
                                 descriptors,
                                 views,
                                 enums,
                                 lint});
    // Every fixed role and owning-list item costs a real OperandRow. Code refs
    // charge all generated instructions conservatively, including discarded
    // occurrences. Logical leafless fields retain both Fields and FieldOffsets.
    const auto slotOperands = sum({mul(2, scalarSlots),
                                   mul(3, objectSlots),
                                   mul(2, arraySlots),
                                   spanSlots,
                                   serviceSlots,
                                   regionSlots,
                                   mul(2, byteSlots),
                                   mul(2, ownedTypes),
                                   mul(2, spanTypes)});
    const auto setupOperands = sum({3, 8, mul(3, scalars), mul(6, operations), serviceParameters, nominals, 1});
    const auto metadataOperands = sum({7,
                                       mul(11, F),
                                       mul(6, F),
                                       slots,
                                       mul(4, receiverRows),
                                       mul(4, classRows),
                                       mul(5, classRows),
                                       mul(5, fieldRows),
                                       mul(2, carriers),
                                       mul(3, descriptors),
                                       mul(2, views),
                                       mul(2, enums),
                                       lint,
                                       mul(2 * 8192, classRows),
                                       mul(2, fieldRows),
                                       mul(views, descriptors),
                                       F,
                                       classRows,
                                       carriers,
                                       descriptors,
                                       views,
                                       enums,
                                       lint});
    // BorrowedCall now has five fixed roles; its root triples are charged only
    // in instructionLists, never again as retired fixed second-root fields.
    // A service call adds its copied-snapshot slice as a seventh fixed operand.
    const auto operandRows =
        sum({setupOperands, mul(6, instructions), X, instructions, instructionLists, slotOperands, metadataOperands});
    // Shared resolution owners remain live. Additional type/name/source rows
    // have distinct charges; lowering lookup domains retain nominal/layout,
    // field, function, lexical-binding, forward-list and reflection indexes.
    // Interned spelling/prefix bytes retain the original source-derived P/L/N
    // grants above; no new source-sized coordinate or token array is introduced.
    const auto loweringTypes = sum({nominals, X, primitiveKinds});
    const auto loweringMetadata = sum({loweringTypes, mul(2, X), 1});
    const auto loweringIndexes = sum({loweringTypes,
                                      mul(2, X),
                                      mul(12, nominals),
                                      mul(8, fieldRows),
                                      mul(3, F),
                                      X,
                                      mul(3, X),
                                      mul(3, carriers),
                                      mul(2, descriptors),
                                      32});
    // Cached linkage: length-prefix digits never exceed component bytes. A
    // base name fits 2*D + 2*4096 bytes plus 128 marker/count bytes. Depth-four
    // binary nominal arguments contain <=31 names; a function's two arguments
    // add at most 63. Ordinary overloads separately charge every signature edge
    // (including rejected >6-parameter inputs), not the later lowering limit.
    const auto linkageBase = sum({mul(2, D), 2 * 4096, 128});
    const auto linkageBytes = mul(sum({mul(63, nominals), mul(32, mul(2, Sx))}), linkageBase);
    // Module token normalization adds <=4096 components/module, with a range,
    // coordinate/atom/prefix rows and their indexes. Each symbol adds one cache
    // source-reference; failed unpublished prefixes are within the same charge.
    const auto moduleComponents = mul(M, 4096);
    const auto records = sum({storage, semantic, loweringMetadata, nominals, mul(3, moduleComponents), M});
    const auto indexRecords = sum({storageIndexes, indexes, loweringIndexes, mul(4, moduleComponents), mul(2, M)});
    // Lowering layout DFS uses at most eight WorkRows (two per depth-four
    // logical frame; physical frames use four). Name helpers retain their
    // existing <=2*D scratch above that saved base. The initial class-order
    // sort is a separate phase with two rows per nominal.
    const auto loweringWork = std::max(mul(2, nominals), add(8, mul(2, D)));
    // Linkage's temporary signature/prefix lists restore their caller's base.
    // Ingest holds <=12 request rows per file byte and one row per token ordinal.
    // Graph traversal needs at most 18 transient frames plus name-helper scratch,
    // below the existing ingest/name bounds; no owner or capacity budget is added.
    const auto work = std::max({add(mul(13, b), 1), sum({mul(5, Sx), types, mul(2, D), 4096, 128}), loweringWork});
    const auto capacity = [&](std::uint64_t count) {
        return add(mul(2, count), 8);
    };
    // Snapshot high-water retains incoming + then prefixes at each if and
    // incoming prefixes at while/short-circuit frames: (2*128+128)*localHigh.
    // Continuations are one function + block/control + expression path (384),
    // with all six argument lanes embedded in the generated copied row.
    const auto snapshots = mul(384, localHigh);
    const auto session = sum({capacity(sum({B, textBytes, literalBytes, linkageBytes})),
                              mul(sizeof(wire::SyntaxRow), capacity(Sx)),
                              mul(sizeof(wire::MetaRow), capacity(records)),
                              mul(sizeof(wire::IndexRow), capacity(indexRecords)),
                              mul(sizeof(wire::ResolvedRow), capacity(Sx)),
                              mul(sizeof(wire::WorkRow), capacity(work)),
                              mul(sizeof(lowering::OutputRow), capacity(outputRows)),
                              mul(sizeof(lowering::OperandRow), capacity(operandRows)),
                              mul(sizeof(lowering::LocalRow), capacity(localHigh)),
                              mul(sizeof(lowering::SnapshotRow), capacity(snapshots)),
                              mul(sizeof(lowering::ContinuationRow), capacity(384))});
    const auto parserWidths = sum({sizeof(hosted_abi::compiler_parser::AstNode),
                                   sizeof(hosted_abi::compiler_parser::ChildEdge),
                                   sizeof(hosted_abi::compiler_parser::TypeSyntax),
                                   sizeof(hosted_abi::compiler_parser::SyntaxNode)});
    const auto parser = sum({mul(mul(2, b), add(parserWidths, hosted_abi::frameBytes)),
                             mul(8, parserWidths),
                             mul(2 * hosted_parser::maximumLiveFrames + 8, hosted_abi::frameBytes)});
    // Runtime replacement may momentarily retain an old block and its new
    // allocation. The committed quota remains this sum; physical peak is at
    // most twice it, plus runtime metadata and host snapshots/projected values.
    return add(session, parser);
}
class SessionOwner {
    hosted::bytes::Region region;
    std::array<hosted_abi::ResolverIngest, 2> slots;
    std::size_t active = 0;
    bool sessionLive = false, arenaLive = false;

public:
    SessionOwner() : region(resolutionQuota()) {
        for (auto &slot : slots)
            slot.region = region.id();
        hosted_abi::ResolverCreate input;
        input.region = region.id();
        aurora_hosted_resolver_create(&input, data());
        sessionLive = true;
    }
    ~SessionOwner() {
        release();
    }
    void release() noexcept {
        if (arenaLive)
            aurora_hosted_resolver_release_pair(&slots[active]);
        else if (sessionLive)
            aurora_hosted_resolver_release(&slots[active]);
        arenaLive = false;
        sessionLive = false;
    }
    SessionOwner(const SessionOwner &) = delete;
    SessionOwner &operator=(const SessionOwner &) = delete;
    void *data() {
        return slots[active].session.storage.data();
    }
    void *beginArena() {
        if (!sessionLive || arenaLive)
            invalidResolution();
        hosted_abi::ParserCreate input;
        input.region = region.id();
        aurora_hosted_parser_create(&input, slots[active].parsed.storage.data());
        arenaLive = true;
        return slots[active].parsed.storage.data();
    }
    void ingest(std::int64_t module, std::int64_t root) {
        if (!sessionLive || !arenaLive)
            invalidResolution();
        auto &input = slots[active];
        input.module = module;
        input.root = root;
        const auto next = 1 - active;
        // Callbacks are noexcept and generated faults are fail-stop. Transfer
        // and rearming therefore have no intervening C++ throwing operation.
        sessionLive = false;
        arenaLive = false;
        aurora_hosted_resolver_ingest(&input, slots[next].session.storage.data());
        active = next;
        sessionLive = true;
    }
    std::uint64_t usedBytes() const {
        return region.metrics().used;
    }
};
hosted_abi::BuiltinSpan span(const std::string &text) {
    hosted_abi::BuiltinSpan result;
    if (text.size() > static_cast<std::size_t>(std::numeric_limits<std::int64_t>::max()))
        invalidResolution();
    result.backing = text.data();
    result.length = static_cast<std::int64_t>(text.size());
    return result;
}
} // namespace

class HostedResolution::Impl {
    SessionOwner owner;
    std::vector<ModuleSource> sources;
    bool finished = false, failed = false;
    std::optional<std::size_t> graphRoot;
    bool graphComplete = false;
    wire::SessionStatus status() {
        wire::SessionStatus result;
        aurora_hosted_resolver_status(owner.data(), &result);
        return result;
    }
    void storage() {
        const auto result = status();
        if (result.storage == StorageStatus::allocation)
            throw Error(DiagnosticCode::Internal, "hosted module resolution allocation failed");
        if (result.storage != StorageStatus::none)
            invalidResolution();
    }
    void lowerStorage() {
        const auto value = status().storage;
        if (value == StorageStatus::allocation)
            throw Error(DiagnosticCode::Internal, "hosted lowering allocation failed");
        if (value != StorageStatus::none)
            invalidResolution();
    }
    void configureLowering(AnalysisMode mode) {
        hosted_abi::LoweringBeginInput configuration{};
        auto &limits = configuration.configuration;
        limits.byteLeaves = maximumCopiedByteLeaves;
        limits.nonByteLeaves = maximumCopiedNonByteLeaves;
        limits.totalLeaves = maximumCopiedClassLeaves;
        limits.copiedBytes = maximumCopiedClassBytes;
        limits.byteArrayLength = maximumClassByteArrayLength;
        limits.scalarArrayLength = maximumClassScalarArrayLength;
        switch (mode) {
        case AnalysisMode::Check:
            limits.analysisMode = 0;
            break;
        case AnalysisMode::Lint:
            limits.analysisMode = 1;
            break;
        default:
            invalidResolution();
        }
        // Lowering publishes its scalar, service and layout prelude itself.
        if (aurora_hosted_lowering_begin(owner.data(), &configuration) != 1) {
            lowerStorage();
            invalidResolution();
        }
        lowerStorage();
    }
    HostedResolvedSource lower(AnalysisMode mode, bool collectAbi) {
        AbiDeclarations declarations;
        if (collectAbi) {
            Projection resolved(owner.data(), sources, owner.usedBytes());
            declarations = resolved.abiDeclarations();
        }
        configureLowering(mode);
        lowering::LoweringResult result;
        // Borrowed Session stays armed through execution, private projection
        // and diagnostic rendering, including their exceptional exits.
        aurora_hosted_lowering_run(owner.data(), &result);
        const auto storageStatus = status().storage;
        if (result.result_status == lowering::LoweringStatus::storage_failure) {
            if (storageStatus != StorageStatus::allocation)
                invalidResolution();
            throw Error(DiagnosticCode::Internal, "hosted lowering allocation failed");
        }
        if (storageStatus != StorageStatus::none)
            invalidResolution();
        const bool success = result.result_status == lowering::LoweringStatus::success;
        if (success) {
            lowerStorage();
            if (result.result_reason != lowering::LoweringError::none || result.root_row < 1 ||
                result.diagnostic_row != 0)
                invalidResolution();
        } else if ((result.result_status != lowering::LoweringStatus::semantic_failure &&
                    result.result_status != lowering::LoweringStatus::invalid) ||
                   result.result_reason == lowering::LoweringError::none) {
            invalidResolution();
        }
        if (!success) {
            // Rejections retain their native identity spelling and fixed report
            // transport. No success path loads this diagnostic metadata snapshot.
            Projection projection(owner.data(), sources, owner.usedBytes());
            const auto outputs = aurora_hosted_lowering_count(owner.data(), 0);
            const auto operands = aurora_hosted_lowering_count(owner.data(), 1);
            if (outputs < 1 || operands < 3 ||
                static_cast<std::uint64_t>(outputs) > owner.usedBytes() / sizeof(lowering::OutputRow) ||
                static_cast<std::uint64_t>(operands) > owner.usedBytes() / sizeof(lowering::OperandRow))
                invalidResolution();
            std::array<lowering::OutputRow, 1> rows{};
            std::array<lowering::OperandRow, 3> values{};
            aurora_hosted_lowering_read_output(owner.data(), 0, &rows[0]);
            for (std::size_t index = 0; index < values.size(); ++index)
                aurora_hosted_lowering_read_operand(owner.data(), static_cast<std::int64_t>(index), &values[index]);
            const HostedLoweringInput input{
                rows, values, projection.sourceByteCount(), result.root_row, result.diagnostic_row};
            throw Error(renderHostedLoweringDiagnostic(result, input, projection.diagnosticServices()));
        }
        auto output = projectHostedLowering(owner.data(), owner.usedBytes(), result.root_row, result.diagnostic_row);
        std::vector<Diagnostic> diagnostics;
        diagnostics.reserve(output.lintReferences.size());
        const auto sourceBytes = aurora_hosted_resolver_count(owner.data(), 0);
        const auto metadataCount = aurora_hosted_resolver_count(owner.data(), 2);
        if (sourceBytes < 0 || static_cast<std::uint64_t>(sourceBytes) > owner.usedBytes() || metadataCount < 0 ||
            static_cast<std::uint64_t>(metadataCount) > owner.usedBytes() / sizeof(wire::MetaRow))
            invalidResolution();
        for (const auto reference : output.lintReferences) {
            if (reference < 0 || reference >= metadataCount)
                invalidResolution();
            wire::MetaRow row{};
            aurora_hosted_resolver_read_meta(owner.data(), reference, &row);
            auto identifier = retainedSourceToken(owner.data(), sources, sourceBytes, row);
            diagnostics.push_back({DiagnosticCode::UnreadLocal,
                                   "local binding '" + identifier.text + "' is never read",
                                   std::move(identifier.span),
                                   DiagnosticSeverity::Warning});
        }
        std::sort(diagnostics.begin(), diagnostics.end(), [](const auto &left, const auto &right) {
            return left.span.begin.offset < right.span.begin.offset;
        });
        // The result owns one pending metadata/instruction bundle.
        // Destroy all transport views and free Session before source admission
        // of every signature, the single publication, and native body checks.
        owner.release();
        auto verified = ir::validate(std::move(output.instructions));
        return {std::move(verified), std::move(diagnostics), std::move(declarations)};
    }

public:
    Impl() {
        storage();
        sources.reserve(64);
    }
    HostedModule add(std::shared_ptr<const SourceText> source) {
        if (finished || failed || graphComplete || !source || sources.size() >= 64)
            invalidResolution();
        try {
            const auto tokens = lex(source);
            const auto parsed = parseHostedModuleSyntax(tokens, owner.beginArena());
            hosted_abi::ResolverSourceInput input;
            input.source = span(source->text);
            const auto index = aurora_hosted_resolver_append_source(owner.data(), &input);
            storage();
            if (index < 0 || sizeValue(index) != sources.size())
                invalidResolution();
            wire::MetaRow sourceRow;
            aurora_hosted_resolver_read_meta(owner.data(), index, &sourceRow);
            if (sourceRow.tag != MetaTag::module_source || sourceRow.value0 < 0 ||
                sourceRow.value1 != static_cast<std::int64_t>(source->text.size()))
                invalidResolution();
            owner.ingest(index, parsed.root);
            storage();
            HostedModule header;
            header.id = sizeValue(index);
            header.moduleName = parsed.moduleName;
            header.interfaceUnit = parsed.interfaceUnit;
            header.imports = parsed.imports;
            sources.push_back({std::move(source), header, parsed.importSyntax, sourceRow.value0, 0});
            return header;
        } catch (...) {
            failed = true;
            throw;
        }
    }
    std::optional<std::string> nextImport(std::size_t root) {
        if (finished || failed || root >= sources.size() || (graphRoot && *graphRoot != root))
            invalidResolution();
        graphRoot = root;
        try {
            wire::WorkRow result;
            aurora_hosted_resolver_graph_step(owner.data(), static_cast<std::int64_t>(root), &result);
            storage();
            if (result.value0 == 0) {
                for (std::size_t index = 0; index < sources.size(); ++index) {
                    wire::MetaRow row;
                    aurora_hosted_resolver_read_meta(owner.data(), static_cast<std::int64_t>(index), &row);
                    if (row.tag != MetaTag::module_unit || row.value12 < 0 ||
                        sizeValue(row.value12) >= sources.size() || row.value13 < 0 ||
                        sizeValue(row.value13) >= sources.size() || row.value14 != (index == root))
                        invalidResolution();
                    sources[index].scope = intValue(row.value13);
                }
                graphComplete = true;
                return std::nullopt;
            }
            if (result.value0 == 4)
                throw Error("module import depth exceeds 16");
            if (result.value0 == 5)
                throw Error("module graph exceeds 64 files");
            if (result.value1 < 0 || sizeValue(result.value1) >= sources.size())
                invalidResolution();
            const auto &header = sources[sizeValue(result.value1)].header;
            if (result.value0 == 3)
                throw Error("module import cycle involving " + header.moduleName);
            if (result.value2 < 0 || sizeValue(result.value2) >= header.imports.size())
                invalidResolution();
            const auto &name = header.imports[sizeValue(result.value2)].text;
            if (result.value0 == 2)
                throw Error("duplicate import in " + header.moduleName + ": " + name);
            if (result.value0 != 1)
                invalidResolution();
            return name;
        } catch (...) {
            failed = true;
            owner.release();
            throw;
        }
    }
    HostedResolvedSource resolve(const std::vector<std::size_t> &order,
                                 std::size_t root,
                                 AnalysisMode mode,
                                 bool collectAbi,
                                 bool sourceOrdered = false) {
        if (finished || failed || root >= sources.size() ||
            (sourceOrdered ? (!graphComplete || graphRoot != root) : (graphRoot || order.size() != sources.size())))
            invalidResolution();
        finished = true;
        // The direct API may outlive this call. Release its sole armed native
        // owner on earlier failures; successful projection releases it before
        // independent validation. Releasing an inactive owner is harmless.
        struct Release {
            SessionOwner &owner;
            ~Release() {
                owner.release();
            }
        } release{owner};
        if (!sourceOrdered) {
            std::vector<bool> seen(sources.size());
            std::map<std::string, std::size_t> names;
            for (std::size_t i = 0; i < sources.size(); ++i)
                if (!names.emplace(sources[i].header.moduleName, i).second)
                    invalidResolution();
            std::int64_t nextScope = 1;
            for (std::size_t ordinal = 0; ordinal < order.size(); ++ordinal) {
                const auto index = order[ordinal];
                if (index >= sources.size() || seen[index])
                    invalidResolution();
                seen[index] = true;
                hosted_abi::ResolverOrderInput input;
                input.module = static_cast<std::int64_t>(index);
                input.order = static_cast<std::int64_t>(ordinal);
                input.scope = index == root ? 0 : nextScope++;
                input.root = index == root;
                sources[index].scope = intValue(input.scope);
                if (!aurora_hosted_resolver_order_module(owner.data(), &input)) {
                    storage();
                    invalidResolution();
                }
            }
            for (std::size_t index = 0; index < sources.size(); ++index) {
                const auto &unit = sources[index];
                wire::MetaRow moduleRow;
                aurora_hosted_resolver_read_meta(owner.data(), static_cast<std::int64_t>(index), &moduleRow);
                if (moduleRow.tag != MetaTag::module_unit || unit.imports.size() != unit.header.imports.size())
                    invalidResolution();
                for (std::size_t ordinal = 0; ordinal < unit.imports.size(); ++ordinal) {
                    const auto found = names.find(unit.header.imports[ordinal].text);
                    if (found == names.end() || unit.imports[ordinal] < 0 || moduleRow.value8 < 0 ||
                        unit.imports[ordinal] > std::numeric_limits<std::int64_t>::max() - moduleRow.value8)
                        invalidResolution();
                    hosted_abi::ResolverImportInput input;
                    input.module = static_cast<std::int64_t>(index);
                    input.node = moduleRow.value8 + unit.imports[ordinal];
                    input.target = static_cast<std::int64_t>(found->second);
                    if (!aurora_hosted_resolver_bind_import(owner.data(), &input)) {
                        storage();
                        invalidResolution();
                    }
                }
            }
        }
        const auto result = aurora_hosted_resolver_run(owner.data());
        storage();
        const auto final = status();
        if (final.diagnostic != SemanticError::none) {
            Projection projection(owner.data(), sources, owner.usedBytes());
            projection.diagnostic(final);
        }
        if (result != 0 || final.node != -1 || final.first != -1 || final.second != -1)
            invalidResolution();
        try {
            return lower(mode, collectAbi);
        } catch (const Error &error) {
            throw error.withDefaultCode(DiagnosticCode::Semantic);
        }
    }
};
HostedResolution::HostedResolution() : implementation(std::make_unique<Impl>()) {
}
HostedResolution::~HostedResolution() = default;
HostedModule HostedResolution::add(std::shared_ptr<const SourceText> source) {
    return implementation->add(std::move(source));
}
std::optional<std::string> HostedResolution::nextImport(std::size_t root) {
    return implementation->nextImport(root);
}
HostedResolvedSource HostedResolution::resolve(std::size_t root, AnalysisMode mode, bool collectAbiDeclarations) {
    return implementation->resolve({}, root, mode, collectAbiDeclarations, true);
}
HostedResolvedSource HostedResolution::resolve(const std::vector<std::size_t> &order,
                                               std::size_t root,
                                               AnalysisMode mode,
                                               bool collectAbiDeclarations) {
    return implementation->resolve(order, root, mode, collectAbiDeclarations);
}
} // namespace aurora
