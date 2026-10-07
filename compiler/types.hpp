#pragma once
#include "diagnostics.hpp"
#include <cstdint>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>
namespace aurora {
class Token {
  public:
    std::string text;
    int line;
    SourceSpan span;
    Token(std::string t, int l) : text(std::move(t)), line(l) {}
    Token(std::string t, SourceSpan location)
        : text(std::move(t)), line(location.begin.line), span(std::move(location)) {}
};
// Append new kinds so existing IR and template identity ordinals remain stable.
enum class TypeKind { I64, Bool, Own, Ref, MutRef, Class, Array, U64, Parameter, Enum, U8, ByteSpan };
enum class TemplateArgumentKind { Type, Value };
inline constexpr int maximumTemplateNesting = 4;
class TemplateArgument {
  public:
    TemplateArgumentKind kind = TemplateArgumentKind::Type;
    TypeKind type = TypeKind::I64;
    std::int64_t value = 0;
    std::string className, displayName;
    // Trusted frontend substitution provenance; never grants source name lookup.
    bool resolvedClass = false;
    // Frontend-only unresolved concrete template-id. Resolution interns children
    // first and clears this tree before substitution or the concrete IR boundary.
    std::vector<TemplateArgument> templateArguments;
    TemplateArgument() = default;
    TemplateArgument(TypeKind value) : type(value) {}
    explicit TemplateArgument(std::string name)
        : type(TypeKind::Class), className(std::move(name)) {}
    static TemplateArgument capacity(std::int64_t value) {
        TemplateArgument argument;
        argument.kind = TemplateArgumentKind::Value;
        argument.value = value;
        return argument;
    }
    bool operator==(const TemplateArgument &) const = default;
};
enum class TemplateParameterKind { Scalar, Value, Capacity };
class TemplateParameter {
  public:
    TemplateParameterKind kind = TemplateParameterKind::Scalar;
    std::string name;
    TemplateParameter(std::string value) : name(std::move(value)) {}
    TemplateParameter(TemplateParameterKind kind, std::string value)
        : kind(kind), name(std::move(value)) {}
};
class Type {
  public:
    TypeKind kind = TypeKind::I64;
    std::string className;
    std::string displayName;
    // Resolved class and enum types keep their nominal identity across substitutions.
    bool resolvedClass = false;
    std::vector<TemplateArgument> templateArguments;
    TypeKind elementKind = TypeKind::I64;
    int length = 0;
    std::string elementParameter, lengthParameter;
    Type() = default;
    explicit Type(TypeKind value) : kind(value) {}
    explicit Type(std::string name) : kind(TypeKind::Class), className(std::move(name)) {}
    bool operator==(const Type &other) const {
        return kind == other.kind && className == other.className &&
               elementKind == other.elementKind && length == other.length &&
               elementParameter == other.elementParameter &&
               lengthParameter == other.lengthParameter &&
               templateArguments == other.templateArguments;
    }
    bool isClass() const { return kind == TypeKind::Class; }
    bool isEnum() const { return kind == TypeKind::Enum; }
    bool isArray() const { return kind == TypeKind::Array; }
    bool isSpan() const { return kind == TypeKind::ByteSpan; }
    static Type enumeration(std::string name) {
        Type type(TypeKind::Enum);
        type.className = std::move(name);
        return type;
    }
    static Type array(TypeKind element, int count) {
        Type type(TypeKind::Array);
        type.elementKind = element;
        type.length = count;
        return type;
    }
    static const Type I64, U64, U8, Bool, Own, Ref, MutRef, ByteSpan;
};
inline const Type Type::I64{TypeKind::I64};
inline const Type Type::U64{TypeKind::U64};
inline const Type Type::U8{TypeKind::U8};
inline const Type Type::Bool{TypeKind::Bool};
inline const Type Type::Own{TypeKind::Own};
inline const Type Type::Ref{TypeKind::Ref};
inline const Type Type::MutRef{TypeKind::MutRef};
inline const Type Type::ByteSpan{TypeKind::ByteSpan};
inline std::string typeName(const Type &type) {
    switch (type.kind) {
    case TypeKind::I64:
        return "i64";
    case TypeKind::U64:
        return "u64";
    case TypeKind::U8:
        return "u8";
    case TypeKind::Bool:
        return "bool";
    case TypeKind::Own:
        return "own<i64>";
    case TypeKind::Ref:
        return "ref<i64>";
    case TypeKind::MutRef:
        return "mutref<i64>";
    case TypeKind::ByteSpan:
        return "builtin::span<const u8>";
    case TypeKind::Parameter:
        return type.className;
    case TypeKind::Enum:
        return type.displayName.empty() ? type.className : type.displayName;
    case TypeKind::Class: {
        std::string name = type.displayName.empty() ? type.className : type.displayName;
        if (!type.templateArguments.empty()) {
            name += "<";
            for (std::size_t index = 0; index < type.templateArguments.size(); ++index) {
                if (index)
                    name += ", ";
                const auto &argument = type.templateArguments[index];
                if (argument.kind == TemplateArgumentKind::Value)
                    name += std::to_string(argument.value);
                else {
                    Type argumentType(argument.type);
                    argumentType.className = argument.className;
                    argumentType.displayName = argument.displayName;
                    argumentType.templateArguments = argument.templateArguments;
                    name += typeName(argumentType);
                }
            }
            name += ">";
        }
        return name;
    }
    case TypeKind::Array:
        return "array<" +
               (type.elementParameter.empty() ? typeName(Type(type.elementKind))
                                              : type.elementParameter) +
               ", " +
               (type.lengthParameter.empty() ? std::to_string(type.length) : type.lengthParameter) +
               ">";
    }
    return "?";
}
inline bool scalar(Type t) {
    return t == Type::I64 || t == Type::U64 || t == Type::U8 || t == Type::Bool;
}
inline bool scalarValue(const Type &type) { return scalar(type) || type.isEnum(); }

} // namespace aurora
