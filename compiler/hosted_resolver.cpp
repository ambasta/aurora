// Trusted projection boundary for one Aurora-owned resolution session. The host
// retains source snapshots and file-opening authority, never semantic lookup.
#include "hosted_resolver.hpp"
#include "hosted_parser.hpp"
#include "lexer.hpp"
#include "services.hpp"
#include "../runtime/hosted_bytes.hpp"
#include <algorithm>
#include <array>
#include <limits>
#include <optional>
#include <set>
#include <utility>
#include <type_traits>

extern "C" {
void aurora_hosted_parser_create(const void *, void *);
void aurora_hosted_resolver_create(const void *, void *);
void aurora_hosted_resolver_ingest(void *, void *);
void aurora_hosted_resolver_release(void *);
void aurora_hosted_resolver_release_pair(void *);
std::int64_t aurora_hosted_resolver_append_source(void *, const void *);
std::int64_t aurora_hosted_resolver_append_text(void *, const void *);
std::int64_t aurora_hosted_resolver_order_module(void *, const void *);
std::int64_t aurora_hosted_resolver_bind_import(void *, const void *);
std::int64_t aurora_hosted_resolver_seed_builtin(void *, const void *);
std::int64_t aurora_hosted_resolver_seed_member(void *, const void *);
std::int64_t aurora_hosted_resolver_run(void *);
std::int64_t aurora_hosted_resolver_count(const void *, std::int64_t);
std::int64_t aurora_hosted_resolver_read_source(const void *, std::int64_t);
void aurora_hosted_resolver_read_syntax(const void *, std::int64_t, void *);
void aurora_hosted_resolver_read_meta(const void *, std::int64_t, void *);
void aurora_hosted_resolver_read_resolved(const void *, std::int64_t, void *);
void aurora_hosted_resolver_status(const void *, void *);
}

namespace aurora {
namespace {
namespace wire = hosted_abi::compiler_resolver;
using wire::DeclarationKind;
using wire::MetaTag;
using wire::NativeMode;
using wire::ResolvedOperation;
using wire::ResolvedTypeKind;
using wire::SemanticError;
using wire::StorageStatus;
using wire::SyntaxTag;
using hosted_parser::NodeKind;
using hosted_parser::SyntaxKind;
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
auto words(const wire::SyntaxRow &row) {
    return std::array{row.value0, row.value1, row.value2, row.value3, row.value4, row.value5,
                      row.value6, row.value7, row.value8, row.value9, row.value10, row.value11};
}
auto words(const wire::MetaRow &row) {
    return std::array{row.value0, row.value1, row.value2, row.value3, row.value4, row.value5,
                      row.value6, row.value7, row.value8, row.value9, row.value10, row.value11,
                      row.value12, row.value13, row.value14};
}
auto words(const wire::ResolvedRow &row) {
    return std::array{row.value0, row.value1, row.value2, row.value3, row.value4, row.value5, row.value6, row.value7};
}
// This spelling routine is moved from the former resolver. Identity choice and
// complete parameter/instance tuples have already been fixed by Aurora.
std::string mangle(char kind, const std::string &module, const std::string &scope, const std::string &name) {
    const auto split = [](const std::string &value, const std::string &separator) {
        std::vector<std::string> result;
        std::size_t start = 0;
        while (start < value.size()) {
            const auto end = value.find(separator, start);
            result.push_back(value.substr(start, end == std::string::npos ? end : end - start));
            if (end == std::string::npos) break;
            start = end + separator.size();
        }
        return result;
    };
    const auto modules = split(module, "."), spaces = split(scope, "::");
    std::string result = "__au_" + std::string(1, kind) + "_m" + std::to_string(modules.size()) + "_";
    for (const auto &part : modules) result += std::to_string(part.size()) + part;
    result += "_n" + std::to_string(spaces.size()) + "_";
    for (const auto &part : spaces) result += std::to_string(part.size()) + part;
    return result + "_d" + std::to_string(name.size()) + name;
}
struct ModuleSource {
    std::shared_ptr<const SourceText> source;
    HostedModule header;
    std::vector<std::int64_t> imports;
    std::int64_t sourceBegin = 0;
    int scope = 0;
};
class Projection {
    const void *session;
    const std::vector<ModuleSource> &sources;
    std::int64_t sourceBytes;
    std::vector<wire::SyntaxRow> syntax;
    std::vector<wire::MetaRow> metadata;
    std::vector<wire::ResolvedRow> resolved;
    std::vector<bool> used;
    std::vector<std::optional<Type>> types;
    std::vector<std::optional<std::string>> natives;
    std::vector<bool> activeType, activeNative;
    std::map<std::int64_t, std::vector<std::int64_t>> authorities;
    int constructionDepth = 0;
    class Depth {
        int &count;
    public:
        explicit Depth(int &value) : count(value) { if (++count > 128) invalidResolution(); }
        ~Depth() { --count; }
    };
    const wire::MetaRow &meta(std::int64_t index, MetaTag tag) const {
        if (index < 0 || sizeValue(index) >= metadata.size() || metadata[sizeValue(index)].tag != tag)
            invalidResolution();
        return metadata[sizeValue(index)];
    }
    const wire::SyntaxRow &node(std::int64_t index, SyntaxTag tag) const {
        if (index < 0 || sizeValue(index) >= syntax.size() || syntax[sizeValue(index)].tag != tag)
            invalidResolution();
        return syntax[sizeValue(index)];
    }
    const wire::ResolvedRow &decoration(std::int64_t index) const {
        if (index < 0 || sizeValue(index) >= resolved.size()) invalidResolution();
        return resolved[sizeValue(index)];
    }
    void take(std::int64_t index, std::int64_t parent) {
        if (index < 0 || sizeValue(index) >= syntax.size() || index >= parent || used[sizeValue(index)])
            invalidResolution();
        used[sizeValue(index)] = true;
    }
    const ModuleSource &module(std::int64_t index) const {
        if (index < 0 || sizeValue(index) >= sources.size()) invalidResolution();
        return sources[sizeValue(index)];
    }
    std::vector<std::int64_t> list(std::int64_t last, std::int64_t parent, SyntaxTag tag) const {
        std::vector<std::int64_t> result;
        for (auto current = last; current != -1;) {
            if (current < 0 || current >= parent) invalidResolution();
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
            if (!seen.insert(current).second) invalidResolution();
            result.push_back(current);
            current = words(value).at(next);
        }
        return result;
    }
    Token sourceToken(std::int64_t reference) const {
        const auto &value = meta(reference, MetaTag::source_reference);
        if (value.value1 < 0 || value.value2 < value.value1 || value.value2 > sourceBytes)
            invalidResolution();
        if (value.value0 == -1) {
            std::string text;
            text.reserve(sizeValue(value.value2 - value.value1));
            for (auto at = value.value1; at < value.value2; ++at) {
                const auto byte = aurora_hosted_resolver_read_source(session, at);
                if (byte < 0 || byte > 255) invalidResolution();
                text.push_back(static_cast<char>(byte));
            }
            return Token(std::move(text), 0);
        }
        const auto &unit = module(value.value0);
        if (value.value1 < unit.sourceBegin || value.value2 - unit.sourceBegin >
            static_cast<std::int64_t>(unit.source->text.size())) invalidResolution();
        const auto begin = sizeValue(value.value1 - unit.sourceBegin), end = sizeValue(value.value2 - unit.sourceBegin);
        SourceSpan span;
        span.source = unit.source;
        span.begin = {begin, intValue(value.value3), intValue(value.value4)};
        span.end = {end, intValue(value.value7), intValue(value.value8)};
        if (span.begin.line < 1 || span.begin.column < 1 || span.end.line < span.begin.line || span.end.column < 1)
            invalidResolution();
        return Token(unit.source->text.substr(begin, end - begin), std::move(span));
    }
    std::string prefix(std::int64_t index) const {
        std::vector<std::string> parts;
        while (index != -1) {
            const auto &value = meta(index, MetaTag::prefix);
            const auto &atom = meta(value.value1, MetaTag::atom);
            parts.push_back(sourceToken(atom.value2).text);
            if (value.value0 < -1 || value.value0 >= index) invalidResolution();
            index = value.value0;
        }
        std::string result;
        for (auto part = parts.rbegin(); part != parts.rend(); ++part) {
            if (!result.empty()) result += "::";
            result += *part;
        }
        return result;
    }
    std::vector<TemplateArgument> arguments(std::int64_t instance) {
        if (instance == -1) return {};
        const auto &value = meta(instance, MetaTag::instance);
        if (value.value1 < 1 || value.value1 > 2) invalidResolution();
        std::vector<TemplateArgument> result;
        for (std::int64_t i = 0; i < value.value1; ++i) {
            const auto argument = words(value)[sizeValue(i) + 2];
            if (argument < 0) {
                if (argument < -65 || argument > -2) invalidResolution();
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
            if (result.size() > 1) result += ",";
            if (argument.kind == TemplateArgumentKind::Value) result += std::to_string(argument.value);
            else if (argument.type == TypeKind::Class || argument.type == TypeKind::Enum)
                result += display && !argument.displayName.empty() ? argument.displayName : argument.className;
            else result += typeName(Type(argument.type));
        }
        return result + ">";
    }
    static std::string nativeSuffix(const std::vector<TemplateArgument> &arguments) {
        std::string result = "_t" + std::to_string(arguments.size());
        for (const auto &argument : arguments) {
            if (argument.kind == TemplateArgumentKind::Value) result += "_v" + std::to_string(argument.value);
            else if (argument.type == TypeKind::Class || argument.type == TypeKind::Enum)
                result += std::string(argument.type == TypeKind::Class ? "_c" : "_e") +
                          std::to_string(argument.className.size()) + argument.className;
            else result += "_" + typeName(Type(argument.type));
        }
        return result;
    }
    std::string display(std::int64_t symbol) {
        const auto &value = meta(symbol, MetaTag::symbol);
        if (value.native_tag == NativeMode::sealed_builtin) {
            const auto &descriptor = meta(value.value8, MetaTag::context);
            return prefix(descriptor.value1);
        }
        auto result = prefix(value.value3);
        if (value.value9 >= 0) result += argumentSuffix(arguments(value.value9), true);
        return result;
    }
    std::string native(std::int64_t symbol) {
        Depth depth(constructionDepth);
        const auto &value = meta(symbol, MetaTag::symbol);
        auto &cached = natives[sizeValue(symbol)];
        if (cached) return *cached;
        if (activeNative[sizeValue(symbol)]) invalidResolution();
        activeNative[sizeValue(symbol)] = true;
        std::string result;
        if (value.native_tag == NativeMode::sealed_builtin) {
            result = sourceToken(meta(value.value8, MetaTag::context).value3).text;
        } else {
            const auto &unit = module(value.value1);
            const auto name = sourceToken(value.value4).text;
            const auto scope = prefix(value.value2);
            if (value.native_tag == NativeMode::root_entry) result = name;
            else {
                char kind = 0;
                switch (value.native_tag) {
                case NativeMode::function: kind = 'f'; break;
                case NativeMode::value_function: kind = 'v'; break;
                case NativeMode::ordinary_overload: kind = 'o'; break;
                case NativeMode::class_value: kind = 'c'; break;
                case NativeMode::class_template: kind = 't'; break;
                case NativeMode::function_template: kind = 'g'; break;
                case NativeMode::enumeration: kind = 'e'; break;
                case NativeMode::method: kind = 'm'; break;
                case NativeMode::constructor: kind = 'k'; break;
                default: invalidResolution();
                }
                auto nativeScope = scope;
                if (value.native_tag == NativeMode::method || value.native_tag == NativeMode::constructor)
                    nativeScope = prefix(meta(value.value7, MetaTag::symbol).value3);
                result = mangle(kind, unit.header.moduleName, nativeScope, name);
                if (value.native_tag == NativeMode::ordinary_overload) {
                    const auto signature = links(value.value11, MetaTag::signature, 3);
                    if (signature.empty()) invalidResolution();
                    result += "_p" + std::to_string(signature.size() - 1) + "_";
                    for (std::size_t i = 1; i < signature.size(); ++i) {
                        const auto parameter = type(meta(signature[i], MetaTag::signature).value1);
                        const auto component = std::to_string(static_cast<int>(parameter.kind)) + "_" + parameter.className;
                        result += std::to_string(component.size()) + component;
                    }
                }
                auto instance = value.value9;
                if (value.native_tag == NativeMode::method || value.native_tag == NativeMode::constructor)
                    instance = meta(value.value7, MetaTag::symbol).value9;
                if (instance >= 0) result += nativeSuffix(arguments(instance));
            }
        }
        activeNative[sizeValue(symbol)] = false;
        cached = result;
        return result;
    }
    Type type(std::int64_t index) {
        Depth depth(constructionDepth);
        const auto &value = meta(index, MetaTag::concrete_type);
        auto &cached = types[sizeValue(index)];
        if (cached) return *cached;
        if (activeType[sizeValue(index)]) invalidResolution();
        activeType[sizeValue(index)] = true;
        Type result;
        switch (value.concrete_tag) {
        case ResolvedTypeKind::i64_value: result = Type::I64; break;
        case ResolvedTypeKind::u64_value: result = Type::U64; break;
        case ResolvedTypeKind::u8_value: result = Type::U8; break;
        case ResolvedTypeKind::bool_value: result = Type::Bool; break;
        case ResolvedTypeKind::owner: result = Type::Own; break;
        case ResolvedTypeKind::reference: result = Type::Ref; break;
        case ResolvedTypeKind::mutable_reference: result = Type::MutRef; break;
        case ResolvedTypeKind::byte_span: result = Type::ByteSpan; break;
        case ResolvedTypeKind::byte_region: result = Type::ByteRegion; break;
        case ResolvedTypeKind::owned_bytes: result = Type::OwnedBytes; break;
        case ResolvedTypeKind::console_session: result = Type::ConsoleSession; break;
        case ResolvedTypeKind::display_session: result = Type::DisplaySession; break;
        case ResolvedTypeKind::event_session: result = Type::IommuEventSession; break;
        case ResolvedTypeKind::class_value:
        case ResolvedTypeKind::enum_value:
            if (value.value1 < 0) {
                if (value.value1 == std::numeric_limits<std::int64_t>::min() || value.value1 == -1)
                    invalidResolution();
                result = Type(prefix(-value.value1 - 2));
            } else {
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
        default: invalidResolution();
        }
        activeType[sizeValue(index)] = false;
        cached = result;
        return result;
    }
    Type declaredType(std::int64_t syntaxRoot) {
        node(syntaxRoot, SyntaxTag::type);
        return type(decoration(syntaxRoot).value2);
    }
    ExpressionPtr expression(std::int64_t root, std::int64_t parent, int depth = 0) {
        if (depth >= 128) invalidResolution();
        const auto &value = node(root, SyntaxTag::expression);
        take(root, parent);
        const auto &resolvedValue = decoration(root);
        auto token = sourceToken(value.value0);
        std::string op;
        const auto tag = value.expression_tag;
        if (tag == NodeKind::name || tag == NodeKind::call || tag == NodeKind::construct) {
            op = tag == NodeKind::name ? "name" : tag == NodeKind::call ? "call" : "construct";
            if (resolvedValue.value0 < 0) invalidResolution();
            token.text = prefix(resolvedValue.value0);
            const auto last = sourceToken(value.value4);
            if (token.span.source != last.span.source) invalidResolution();
            token.span.end = last.span.end;
        } else if (tag == NodeKind::literal) {
            if (token.text.empty()) invalidResolution();
            op = token.text == "true" || token.text == "false" ? "bool"
                 : token.text.front() == '"' ? "byte_string" : token.text.front() == '\'' ? "byte" : "number";
        } else {
            switch (tag) {
            case NodeKind::unary: op = "unary"; break;
            case NodeKind::binary: op = "binary"; break;
            case NodeKind::member: op = "member"; break;
            case NodeKind::method_call: op = "method_call"; break;
            case NodeKind::index: op = "index"; break;
            case NodeKind::array_literal: op = "array_literal"; break;
            case NodeKind::array_zero: op = "array_zero"; break;
            default: invalidResolution();
            }
        }
        auto result = std::make_shared<Expression>(op, std::move(token));
        const auto append = [&](std::int64_t child) {
            auto argument = expression(child, root, depth + 1);
            result->depth = std::max(result->depth, argument->depth + 1);
            result->args.push_back(std::move(argument));
        };
        if (tag == NodeKind::call || tag == NodeKind::method_call || tag == NodeKind::construct ||
            tag == NodeKind::array_literal || tag == NodeKind::array_zero) {
            const auto edges = list(value.value1, static_cast<std::int64_t>(syntax.size()), SyntaxTag::edge);
            if (edges.size() != sizeValue(value.value2)) invalidResolution();
            for (const auto edge : edges) {
                const auto &argument = node(edge, SyntaxTag::edge);
                take(edge, static_cast<std::int64_t>(syntax.size()));
                append(argument.value0);
                if (argument.value4 >= 0) result->fieldNames.push_back(sourceToken(argument.value4).text);
            }
        } else if (tag == NodeKind::unary || tag == NodeKind::member) append(value.value1);
        else if (tag == NodeKind::binary || tag == NodeKind::index) {
            append(value.value1);
            append(value.value2);
            if (tag == NodeKind::index) result->token = result->args.front()->token;
        }
        if (result->depth > 128) invalidResolution();
        switch (resolvedValue.operation_tag) {
        case ResolvedOperation::unchanged: break;
        case ResolvedOperation::constructor_call: result->op = "constructor_call"; break;
        case ResolvedOperation::implicit_method_call: result->op = "implicit_method_call"; break;
        case ResolvedOperation::enum_case:
            result->op = "enum_case";
            result->enumOrdinal = intValue(resolvedValue.value3);
            break;
        case ResolvedOperation::capacity_constant:
            result->op = "number";
            result->token.text = std::to_string(resolvedValue.value3);
            break;
        default: invalidResolution();
        }
        if (resolvedValue.value1 >= 0) result->resolvedName = native(resolvedValue.value1);
        if (resolvedValue.value2 >= 0) result->reflectedType = type(resolvedValue.value2);
        if (resolvedValue.value4 >= 0) {
            const auto &group = meta(resolvedValue.value4, MetaTag::overload);
            const auto candidates = links(group.value0, MetaTag::link, 1);
            if (candidates.size() > 32 || candidates.size() != sizeValue(group.value2) ||
                resolvedValue.value5 < 0 || resolvedValue.value6 < 0) invalidResolution();
            const auto visible = static_cast<std::uint64_t>(resolvedValue.value5);
            const auto inaccessible = static_cast<std::uint64_t>(resolvedValue.value6);
            if ((visible >> candidates.size()) != 0 || (inaccessible & ~visible) != 0) invalidResolution();
            for (std::size_t i = 0; i < candidates.size(); ++i) {
                if ((visible & (std::uint64_t{1} << i)) == 0) continue;
                auto spelling = native(meta(candidates[i], MetaTag::link).value0);
                if ((inaccessible & (std::uint64_t{1} << i)) != 0) result->inaccessibleOverloads.insert(spelling);
                result->overloadCandidates.push_back(std::move(spelling));
            }
            const auto &first = meta(group.value4, MetaTag::symbol);
            result->resolvedName = mangle('v', module(first.value1).header.moduleName,
                                          prefix(first.value2), sourceToken(first.value4).text);
        }
        return result;
    }
    std::vector<StatementPtr> block(std::int64_t root, std::int64_t parent, int depth = 0) {
        if (depth >= 128) invalidResolution();
        const auto &value = node(root, SyntaxTag::declaration);
        if (value.declaration_tag != SyntaxKind::block) invalidResolution();
        take(root, parent);
        std::vector<StatementPtr> result;
        for (const auto child : list(value.value7, root, SyntaxTag::declaration))
            result.push_back(statement(child, root, depth));
        return result;
    }
    StatementPtr statement(std::int64_t root, std::int64_t parent, int depth) {
        const auto &value = node(root, SyntaxTag::declaration);
        const auto tag = value.declaration_tag;
        auto result = std::make_shared<Statement>(sourceToken(value.value0));
        if (tag == SyntaxKind::block) {
            result->kind = "block";
            result->body = block(root, parent, depth + 1);
            return result;
        }
        take(root, parent);
        result->expr = expression(value.value3, root);
        if (tag == SyntaxKind::conditional || tag == SyntaxKind::loop) {
            result->kind = tag == SyntaxKind::conditional ? "if" : "while";
            result->body = block(value.value7, root, depth + 1);
            if (value.value8 >= 0) result->other = block(value.value8, root, depth + 1);
        } else if (tag == SyntaxKind::local) {
            const auto binding = sourceToken(value.value6);
            result->kind = "let";
            result->type = declaredType(value.value5);
            result->name = binding.text;
            result->bindingSpan = binding.span;
            result->mutableValue = value.value9 == 1;
        } else if (tag == SyntaxKind::return_value) result->kind = "return";
        else if (tag == SyntaxKind::static_assertion) result->kind = "static_assert";
        else if (tag == SyntaxKind::expression) result->kind = "expression";
        else {
            auto target = expression(value.value4, root);
            if (tag == SyntaxKind::assign) {
                if (target->op != "name" || !target->args.empty()) invalidResolution();
                result->kind = "assign";
                result->name = target->token.text;
            } else if (tag == SyntaxKind::field_assign) {
                if (target->op != "member" || target->args.size() != 1 || target->args[0]->op != "name" ||
                    !target->args[0]->args.empty()) invalidResolution();
                result->kind = "field_assign";
                result->name = target->args[0]->token.text;
                result->fieldName = target->token.text;
            } else if (tag == SyntaxKind::index_assign && target->op == "index" && target->args.size() == 2) {
                result->kind = "index_assign";
                result->target = std::move(target);
            } else invalidResolution();
        }
        return result;
    }
    Function function(std::int64_t symbol) {
        const auto &identity = meta(symbol, MetaTag::symbol);
        const auto root = identity.value5;
        const auto &value = node(root, SyntaxTag::declaration);
        const auto tag = value.declaration_tag;
        if (tag != SyntaxKind::function && tag != SyntaxKind::method && tag != SyntaxKind::constructor)
            invalidResolution();
        take(root, static_cast<std::int64_t>(syntax.size()));
        Function result(sourceToken(value.value0));
        result.name = native(symbol);
        result.scope = prefix(identity.value2);
        result.exported = identity.value6 != 0;
        result.moduleScope = module(identity.value1).scope;
        result.constructor = tag == SyntaxKind::constructor;
        result.receiverConst = value.value9 == 1;
        if (identity.value7 >= 0) result.receiverClass = native(identity.value7);
        result.templateArguments = arguments(identity.value9);
        for (const auto child : list(value.value8, root, SyntaxTag::declaration)) {
            const auto &parameter = node(child, SyntaxTag::declaration);
            if (parameter.declaration_tag != SyntaxKind::parameter) invalidResolution();
            take(child, root);
            Param converted;
            converted.type = declaredType(parameter.value5);
            converted.name = sourceToken(parameter.value6).text;
            converted.borrowed = parameter.value10 >= 0;
            converted.borrowConst = parameter.value9 == 1;
            if (converted.borrowed) converted.borrowSpan = sourceToken(parameter.value10).span;
            result.params.push_back(std::move(converted));
        }
        if (result.constructor) {
            for (const auto child : list(value.value7, root, SyntaxTag::declaration)) {
                const auto &initializer = node(child, SyntaxTag::declaration);
                if (initializer.declaration_tag != SyntaxKind::initializer) invalidResolution();
                take(child, root);
                result.initializers.emplace_back(sourceToken(initializer.value0), expression(initializer.value3, child));
            }
        } else {
            result.result = declaredType(value.value5);
            result.body = block(value.value7, root);
        }
        // Exact compile-time authority is published by the resolver, never
        // inferred here from parameter spellings or the runtime visibility view.
        for (const auto nominal : authorities[symbol])
            result.templateTypeAuthority.insert(native(nominal));
        return result;
    }
    ClassDefinition classDefinition(std::int64_t symbol) {
        const auto &identity = meta(symbol, MetaTag::symbol);
        if (identity.native_tag == NativeMode::sealed_builtin) return builtinClass(symbol);
        const auto root = identity.value5;
        const auto &value = node(root, SyntaxTag::declaration);
        if (value.declaration_tag != SyntaxKind::class_definition) invalidResolution();
        take(root, static_cast<std::int64_t>(syntax.size()));
        ClassDefinition result(sourceToken(value.value0));
        result.name = native(symbol);
        result.scope = prefix(identity.value2);
        result.exported = identity.value6 != 0;
        result.templateArguments = arguments(identity.value9);
        for (const auto wrapper : list(value.value7, root, SyntaxTag::declaration)) {
            const auto &member = node(wrapper, SyntaxTag::declaration);
            if (member.declaration_tag != SyntaxKind::declaration) invalidResolution();
            take(wrapper, root);
            const auto child = member.value7;
            const auto &declaration = node(child, SyntaxTag::declaration);
            if (child >= wrapper) invalidResolution();
            if (declaration.declaration_tag == SyntaxKind::field) {
                take(child, wrapper);
                Field field(sourceToken(declaration.value6), declaredType(declaration.value5));
                field.publicAccess = member.value9 != 0;
                result.fields.push_back(std::move(field));
            } else {
                auto method = function(decoration(child).value1);
                method.publicAccess = member.value9 != 0;
                result.methods.push_back(std::move(method));
            }
        }
        return result;
    }
    EnumDefinition enumeration(std::int64_t symbol) {
        const auto &identity = meta(symbol, MetaTag::symbol);
        if (identity.native_tag == NativeMode::sealed_builtin) return builtinEnum(symbol);
        const auto root = identity.value5;
        const auto &value = node(root, SyntaxTag::declaration);
        if (value.declaration_tag != SyntaxKind::enum_definition) invalidResolution();
        take(root, static_cast<std::int64_t>(syntax.size()));
        EnumDefinition result(sourceToken(value.value0));
        result.name = native(symbol);
        result.scope = prefix(identity.value2);
        result.exported = identity.value6 != 0;
        for (const auto child : list(value.value7, root, SyntaxTag::declaration)) {
            const auto &item = node(child, SyntaxTag::declaration);
            if (item.declaration_tag != SyntaxKind::enum_case) invalidResolution();
            take(child, root);
            result.cases.push_back(sourceToken(item.value0));
        }
        return result;
    }
    ClassDefinition builtinClass(std::int64_t symbol) {
        const auto &descriptor = meta(meta(symbol, MetaTag::symbol).value8, MetaTag::context);
        ClassDefinition result(Token(native(symbol), 0));
        for (const auto child : links(descriptor.value4, MetaTag::context, 3)) {
            const auto &member = meta(child, MetaTag::context);
            Field field(sourceToken(member.value1), type(member.value2));
            field.publicAccess = true;
            result.fields.push_back(std::move(field));
        }
        return result;
    }
    EnumDefinition builtinEnum(std::int64_t symbol) {
        const auto &descriptor = meta(meta(symbol, MetaTag::symbol).value8, MetaTag::context);
        EnumDefinition result(Token(native(symbol), 0));
        for (const auto child : links(descriptor.value4, MetaTag::context, 3))
            result.cases.push_back(sourceToken(meta(child, MetaTag::context).value1));
        return result;
    }
public:
    Projection(const void *session, const std::vector<ModuleSource> &sources, std::uint64_t payloadBytes) : session(session), sources(sources) {
        sourceBytes = aurora_hosted_resolver_count(session, 0);
        if (sourceBytes < 0) invalidResolution();
        const auto load = [&](auto &values, std::int64_t pool, auto read) {
            const auto count = sizeValue(aurora_hosted_resolver_count(session, pool));
            if (count > values.max_size() || count > payloadBytes / sizeof(typename std::remove_reference_t<decltype(values)>::value_type)) invalidResolution();
            values.resize(count);
            for (std::size_t i = 0; i < count; ++i) read(session, static_cast<std::int64_t>(i), &values[i]);
        };
        load(syntax, 1, aurora_hosted_resolver_read_syntax);
        load(metadata, 2, aurora_hosted_resolver_read_meta);
        load(resolved, 3, aurora_hosted_resolver_read_resolved);
        if (resolved.size() != syntax.size()) invalidResolution();
        used.resize(syntax.size());
        types.resize(metadata.size()); natives.resize(metadata.size());
        activeType.resize(metadata.size()); activeNative.resize(metadata.size());
        for (const auto &value : metadata) if (value.tag == MetaTag::authority) {
            meta(value.value0, MetaTag::symbol);
            meta(value.value1, MetaTag::symbol);
            authorities[value.value0].push_back(value.value1);
        }
    }
    [[noreturn]] void diagnostic(const wire::SessionStatus &status);
    Program program(std::size_t root) {
        if (root >= sources.size()) invalidResolution();
        const wire::MetaRow *output = nullptr;
        for (const auto &value : metadata)
            if (value.tag == MetaTag::context && value.value0 == 1) {
                if (output) invalidResolution();
                output = &value;
            }
        if (!output) invalidResolution();
        Program result;
        result.moduleName = sources[root].header.moduleName;
        for (const auto &source : sources) result.reflectionAccess[source.scope];
        for (const auto link : links(output->value1, MetaTag::link, 1))
            result.functions.push_back(function(meta(link, MetaTag::link).value0));
        for (const auto link : links(output->value2, MetaTag::link, 1))
            result.classes.push_back(classDefinition(meta(link, MetaTag::link).value0));
        for (const auto link : links(output->value3, MetaTag::link, 1))
            result.enums.push_back(enumeration(meta(link, MetaTag::link).value0));
        for (const auto link : links(output->value4, MetaTag::visibility, 3)) {
            const auto &view = meta(link, MetaTag::visibility);
            if (view.value1 < 0 || view.value1 > UINT32_MAX || view.value2 < 0 || view.value2 > UINT32_MAX)
                invalidResolution();
            const auto bits = static_cast<std::uint64_t>(view.value1) | (static_cast<std::uint64_t>(view.value2) << 32);
            const auto name = native(view.value0);
            for (std::size_t i = 0; i < sources.size(); ++i)
                if (bits & (std::uint64_t{1} << i)) result.reflectionAccess[sources[i].scope].insert(name);
        }
        return result;
    }
};
} // namespace
namespace {
struct BuiltinCatalog {
    std::vector<Type> types{Type::I64, Type::U64, Type::U8, Type::Bool, Type::ByteRegion, Type::OwnedBytes,
                            Type::ConsoleSession, Type::DisplaySession, Type::IommuEventSession};
    Program definitions = service::copiedDefinitions();
    BuiltinCatalog() {
        const auto copied = service::copiedTypes();
        types.insert(types.end(), copied.begin(), copied.end());
    }
};
const BuiltinCatalog &builtinCatalog() {
    static const BuiltinCatalog value;
    return value;
}
std::uint64_t resolutionQuota() {
    const auto add = [](std::uint64_t a, std::uint64_t b) {
        if (b > std::numeric_limits<std::uint64_t>::max() - a) invalidResolution();
        return a + b;
    };
    const auto mul = [](std::uint64_t a, std::uint64_t b) {
        if (a && b > std::numeric_limits<std::uint64_t>::max() / a) invalidResolution();
        return a * b;
    };
    const auto sum = [&](std::initializer_list<std::uint64_t> values) {
        std::uint64_t result = 0;
        for (const auto value : values) result = add(result, value);
        return result;
    };
    const auto &catalog = builtinCatalog();
    std::uint64_t textCount = 0, textBytes = 0, longest = 0, members = 0;
    const auto text = [&](const std::string &value) {
        textCount = add(textCount, 1); textBytes = add(textBytes, value.size());
        longest = std::max(longest, static_cast<std::uint64_t>(value.size()));
    };
    for (const auto &type : catalog.types) {
        text(typeName(type));
        if (type.isClass() || type.isEnum()) text(type.className);
    }
    for (const auto &definition : catalog.definitions.classes)
        for (const auto &field : definition.fields) { text(field.token.text); members = add(members, 1); }
    for (const auto &definition : catalog.definitions.enums)
        for (const auto &value : definition.cases) { text(value.text); members = add(members, 1); }
    // Existing language/file limits only. This loose ceiling is not allocated
    // eagerly. Each pool grows on demand and reports ordinary allocation failure.
    // Counts charge source projection, interned names/indexes, concrete clones,
    // signatures, public/authority/visibility links and reusable worklists.
    constexpr std::uint64_t B = 4194304, b = 1048576, M = 64, I = 256, H = 4096;
    const auto K = static_cast<std::uint64_t>(catalog.types.size());
    const auto S = mul(4, B), Sx = mul(I + 1, S), U = mul(12, B), D = std::max(b, longest);
    const auto L = sum({S, textCount, H}), N = sum({U, L, textCount}), Q = add(B, textBytes);
    const auto P = mul(sum({mul(34, N), S, K}), D);
    const auto storage = sum({64, mul(2, U), textCount, mul(4, Q), mul(2, P), N, mul(2, L), mul(2, H), mul(2, M)});
    const auto primitiveKinds = static_cast<std::uint64_t>(ResolvedTypeKind::owned_values) + 1;
    const auto types = sum({mul(2, Sx), K, primitiveKinds}), categories = mul(7, M + 1);
    const auto nominals = add(Sx, K), authority = mul(I, nominals);
    const auto semantic = sum({2, categories, nominals, mul(32, S), S, S, types, I, mul(2, Sx), mul(3, Sx),
                               authority, mul(65, Sx), Sx, nominals, nominals, K, members});
    const auto indexes = sum({types, S, categories, 1, S, authority, mul(32, S), Sx, S, S, I, mul(2, K),
                              Sx, Sx, Sx, S, mul(M, S), mul(mul(32, M), S), nominals, 1});
    const auto records = sum({storage, semantic, indexes});
    const auto work = std::max(mul(12, b), sum({mul(3, Sx), types, mul(2, D), 128}));
    const auto capacity = [&](std::uint64_t count) { return add(mul(2, count), 8); };
    const auto session = sum({capacity(add(B, textBytes)), mul(sizeof(wire::SyntaxRow), capacity(Sx)),
                               mul(sizeof(wire::MetaRow), capacity(records)), mul(sizeof(wire::ResolvedRow), capacity(Sx)),
                               mul(sizeof(wire::WorkRow), capacity(work))});
    const auto parserWidths = sum({sizeof(hosted_abi::compiler_parser::AstNode), sizeof(hosted_abi::compiler_parser::ChildEdge),
                                    sizeof(hosted_abi::compiler_parser::TypeSyntax), sizeof(hosted_abi::compiler_parser::SyntaxNode)});
    const auto parser = sum({mul(mul(2, b), add(parserWidths, hosted_abi::frameBytes)), mul(8, parserWidths),
                              mul(2 * 1939 + 8, hosted_abi::frameBytes)});
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
        for (auto &slot : slots) slot.region = region.id();
        hosted_abi::ResolverCreate input;
        input.region = region.id();
        aurora_hosted_resolver_create(&input, data());
        sessionLive = true;
    }
    ~SessionOwner() {
        if (arenaLive) aurora_hosted_resolver_release_pair(&slots[active]);
        else if (sessionLive) aurora_hosted_resolver_release(&slots[active]);
    }
    SessionOwner(const SessionOwner &) = delete;
    SessionOwner &operator=(const SessionOwner &) = delete;
    void *data() { return slots[active].session.storage.data(); }
    void *beginArena() {
        if (!sessionLive || arenaLive) invalidResolution();
        hosted_abi::ParserCreate input;
        input.region = region.id();
        aurora_hosted_parser_create(&input, slots[active].parsed.storage.data());
        arenaLive = true;
        return slots[active].parsed.storage.data();
    }
    void ingest(std::int64_t module, std::int64_t root) {
        if (!sessionLive || !arenaLive) invalidResolution();
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
    std::uint64_t usedBytes() const { return region.metrics().used; }
};
hosted_abi::BuiltinSpan span(const std::string &text) {
    hosted_abi::BuiltinSpan result;
    if (text.size() > static_cast<std::size_t>(std::numeric_limits<std::int64_t>::max())) invalidResolution();
    result.backing = text.data();
    result.length = static_cast<std::int64_t>(text.size());
    return result;
}
wire::MetaRow blankMeta() {
    wire::MetaRow value;
    value.tag = MetaTag::context;
    value.concrete_tag = ResolvedTypeKind::invalid;
    value.declaration_tag = DeclarationKind::invalid;
    value.native_tag = NativeMode::invalid;
    value.value0 = value.value1 = value.value2 = value.value3 = value.value4 = value.value5 = value.value6 =
        value.value7 = value.value8 = value.value9 = value.value10 = value.value11 = value.value12 = value.value13 =
            value.value14 = -1;
    return value;
}
ResolvedTypeKind wireKind(const Type &type) {
    switch (type.kind) {
    case TypeKind::I64: return ResolvedTypeKind::i64_value;
    case TypeKind::U64: return ResolvedTypeKind::u64_value;
    case TypeKind::U8: return ResolvedTypeKind::u8_value;
    case TypeKind::Bool: return ResolvedTypeKind::bool_value;
    case TypeKind::ByteRegion: return ResolvedTypeKind::byte_region;
    case TypeKind::OwnedBytes: return ResolvedTypeKind::owned_bytes;
    case TypeKind::ConsoleSession: return ResolvedTypeKind::console_session;
    case TypeKind::DisplaySession: return ResolvedTypeKind::display_session;
    case TypeKind::IommuEventSession: return ResolvedTypeKind::event_session;
    case TypeKind::Class: return ResolvedTypeKind::class_value;
    case TypeKind::Enum: return ResolvedTypeKind::enum_value;
    default: invalidResolution();
    }
}
} // namespace

class HostedResolution::Impl {
    SessionOwner owner;
    std::vector<ModuleSource> sources;
    bool finished = false, failed = false;
    wire::SessionStatus status() {
        wire::SessionStatus result;
        aurora_hosted_resolver_status(owner.data(), &result);
        return result;
    }
    void storage() {
        const auto result = status();
        if (result.storage == StorageStatus::allocation)
            throw Error(DiagnosticCode::Internal, "hosted module resolution allocation failed");
        if (result.storage != StorageStatus::none) invalidResolution();
    }
    std::int64_t text(const std::string &value) {
        hosted_abi::ResolverTextInput input;
        input.text = span(value);
        const auto result = aurora_hosted_resolver_append_text(owner.data(), &input);
        storage();
        if (result < 0) invalidResolution();
        return result;
    }
    void seed() {
        std::map<std::string, std::int64_t> identities;
        const auto add = [&](const Type &type) {
            hosted_abi::ResolverSeedBuiltinInput input;
            input.definition = blankMeta();
            input.definition.concrete_tag = wireKind(type);
            input.definition.value1 = text(typeName(type));
            if (type.isClass() || type.isEnum()) input.definition.value3 = text(type.className);
            const auto result = aurora_hosted_resolver_seed_builtin(owner.data(), &input);
            storage();
            if (result < 0 || !identities.emplace(typeName(type), result).second) invalidResolution();
        };
        const auto &catalog = builtinCatalog();
        for (const auto &type : catalog.types) add(type);
        const auto definitionType = [&](const std::string &native) -> const Type & {
            const auto found = std::find_if(catalog.types.begin(), catalog.types.end(), [&](const Type &type) { return type.className == native; });
            if (found == catalog.types.end()) invalidResolution();
            return *found;
        };
        const auto member = [&](std::int64_t parent, const std::string &name, std::int64_t typeOrOrdinal) {
            hosted_abi::ResolverSeedMemberInput input;
            input.member = blankMeta();
            input.member.value0 = parent;
            input.member.value1 = text(name);
            input.member.value2 = typeOrOrdinal;
            const auto result = aurora_hosted_resolver_seed_member(owner.data(), &input);
            storage();
            if (result < 0) invalidResolution();
        };
        const auto &definitions = catalog.definitions;
        for (const auto &definition : definitions.classes) {
            const auto parent = identities.at(typeName(definitionType(definition.name)));
            for (const auto &field : definition.fields) member(parent, field.token.text, identities.at(typeName(field.type)));
        }
        for (const auto &definition : definitions.enums) {
            const auto parent = identities.at(typeName(definitionType(definition.name)));
            for (std::size_t ordinal = 0; ordinal < definition.cases.size(); ++ordinal)
                member(parent, definition.cases[ordinal].text, static_cast<std::int64_t>(ordinal));
        }
    }
public:
    Impl() {
        storage();
        sources.reserve(64);
        seed();
    }
    HostedModule add(std::shared_ptr<const SourceText> source) {
        if (finished || failed || !source || sources.size() >= 64) invalidResolution();
        try {
            const auto tokens = lex(source);
            const auto parsed = parseHostedModuleSyntax(tokens, owner.beginArena());
            hosted_abi::ResolverSourceInput input;
            input.source = span(source->text);
            const auto index = aurora_hosted_resolver_append_source(owner.data(), &input);
            storage();
            if (index < 0 || sizeValue(index) != sources.size()) invalidResolution();
            wire::MetaRow sourceRow;
            aurora_hosted_resolver_read_meta(owner.data(), index, &sourceRow);
            if (sourceRow.tag != MetaTag::module_source) invalidResolution();
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
    Program resolve(const std::vector<std::size_t> &order, std::size_t root) {
        if (finished || failed || root >= sources.size() || order.size() != sources.size()) invalidResolution();
        finished = true;
        std::vector<bool> seen(sources.size());
        std::map<std::string, std::size_t> names;
        for (std::size_t i = 0; i < sources.size(); ++i)
            if (!names.emplace(sources[i].header.moduleName, i).second) invalidResolution();
        std::int64_t nextScope = 1;
        for (std::size_t ordinal = 0; ordinal < order.size(); ++ordinal) {
            const auto index = order[ordinal];
            if (index >= sources.size() || seen[index]) invalidResolution();
            seen[index] = true;
            hosted_abi::ResolverOrderInput input;
            input.module = static_cast<std::int64_t>(index);
            input.order = static_cast<std::int64_t>(ordinal);
            input.scope = index == root ? 0 : nextScope++;
            input.root = index == root;
            sources[index].scope = intValue(input.scope);
            if (!aurora_hosted_resolver_order_module(owner.data(), &input)) { storage(); invalidResolution(); }
        }
        for (std::size_t index = 0; index < sources.size(); ++index) {
            const auto &unit = sources[index];
            wire::MetaRow moduleRow;
            aurora_hosted_resolver_read_meta(owner.data(), static_cast<std::int64_t>(index), &moduleRow);
            if (moduleRow.tag != MetaTag::module_unit || unit.imports.size() != unit.header.imports.size()) invalidResolution();
            for (std::size_t ordinal = 0; ordinal < unit.imports.size(); ++ordinal) {
                const auto found = names.find(unit.header.imports[ordinal].text);
                if (found == names.end() || unit.imports[ordinal] < 0 || moduleRow.value8 < 0 ||
                    unit.imports[ordinal] > std::numeric_limits<std::int64_t>::max() - moduleRow.value8) invalidResolution();
                hosted_abi::ResolverImportInput input;
                input.module = static_cast<std::int64_t>(index);
                input.node = moduleRow.value8 + unit.imports[ordinal];
                input.target = static_cast<std::int64_t>(found->second);
                if (!aurora_hosted_resolver_bind_import(owner.data(), &input)) { storage(); invalidResolution(); }
            }
        }
        const auto result = aurora_hosted_resolver_run(owner.data());
        storage();
        const auto final = status();
        Projection projection(owner.data(), sources, owner.usedBytes());
        if (final.diagnostic != SemanticError::none) projection.diagnostic(final);
        if (result != 0 || final.node != -1 || final.first != -1 || final.second != -1) invalidResolution();
        return projection.program(root);
    }
};
HostedResolution::HostedResolution() : implementation(std::make_unique<Impl>()) {}
HostedResolution::~HostedResolution() = default;
HostedModule HostedResolution::add(std::shared_ptr<const SourceText> source) { return implementation->add(std::move(source)); }
Program HostedResolution::resolve(const std::vector<std::size_t> &order, std::size_t root) {
    return implementation->resolve(order, root);
}
} // namespace aurora
