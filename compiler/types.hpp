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
    Token(std::string t, int l) : text(std::move(t)), line(l) {
    }
    Token(std::string t, SourceSpan location)
        : text(std::move(t)), line(location.begin.line), span(std::move(location)) {
    }
};
// Append new kinds so existing IR and template identity ordinals remain stable.
enum class TypeKind {
    I64,
    Bool,
    Own,
    Ref,
    MutRef,
    Class,
    Array,
    U64,
    Parameter,
    Enum,
    U8,
    ByteSpan,
    ByteRegion,
    OwnedBytes,
    ConsoleSession,
    DisplaySession,
    IommuEventSession,
    OwnedValues,
    CallSession,
    Com1UartGrant,
    ServeSession
};
enum class TemplateArgumentKind {
    Type,
    Value
};
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
    TemplateArgument(TypeKind value) : type(value) {
    }
    explicit TemplateArgument(std::string name) : type(TypeKind::Class), className(std::move(name)) {
    }
    static TemplateArgument capacity(std::int64_t value) {
        TemplateArgument argument;
        argument.kind = TemplateArgumentKind::Value;
        argument.value = value;
        return argument;
    }
    bool operator==(const TemplateArgument &) const = default;
};
enum class TemplateParameterKind {
    Scalar,
    Value,
    Capacity
};
class TemplateParameter {
public:
    TemplateParameterKind kind = TemplateParameterKind::Scalar;
    std::string name;
    TemplateParameter(std::string value) : name(std::move(value)) {
    }
    TemplateParameter(TemplateParameterKind kind, std::string value) : kind(kind), name(std::move(value)) {
    }
};
class Type {
public:
    TypeKind kind = TypeKind::I64;
    std::string className;
    std::string displayName;
    // Resolved class/enum types and class array elements keep their nominal
    // identity across substitutions. Array types reuse this nominal metadata
    // for their element; arrayElement() reconstructs its complete type.
    bool resolvedClass = false;
    std::vector<TemplateArgument> templateArguments;
    TypeKind elementKind = TypeKind::I64;
    int length = 0;
    std::string elementParameter, lengthParameter;
    Type() = default;
    explicit Type(TypeKind value) : kind(value) {
    }
    explicit Type(std::string name) : kind(TypeKind::Class), className(std::move(name)) {
    }
    bool operator==(const Type &other) const {
        return kind == other.kind && className == other.className && elementKind == other.elementKind &&
               length == other.length && elementParameter == other.elementParameter &&
               lengthParameter == other.lengthParameter && templateArguments == other.templateArguments;
    }
    bool isClass() const {
        return kind == TypeKind::Class;
    }
    bool isEnum() const {
        return kind == TypeKind::Enum;
    }
    bool isArray() const {
        return kind == TypeKind::Array;
    }
    Type arrayElement() const {
        Type element(elementKind);
        element.className = elementParameter.empty() ? className : elementParameter;
        element.displayName = displayName;
        element.resolvedClass = resolvedClass;
        element.templateArguments = templateArguments;
        return element;
    }
    void setArrayElement(const Type &element) {
        elementKind = element.kind;
        elementParameter = element.kind == TypeKind::Parameter ? element.className : "";
        className = element.kind == TypeKind::Parameter ? "" : element.className;
        displayName = element.displayName;
        resolvedClass = element.resolvedClass;
        templateArguments = element.templateArguments;
    }
    bool isSpan() const {
        return kind == TypeKind::ByteSpan;
    }
    bool isRegion() const {
        return kind == TypeKind::ByteRegion;
    }
    bool isService() const {
        return kind == TypeKind::ConsoleSession || kind == TypeKind::DisplaySession ||
               kind == TypeKind::IommuEventSession || kind == TypeKind::CallSession ||
               kind == TypeKind::Com1UartGrant || kind == TypeKind::ServeSession;
    }
    bool isBytes() const {
        return kind == TypeKind::OwnedBytes;
    }
    bool isOwnedValues() const {
        return kind == TypeKind::OwnedValues;
    }
    bool isOwnerStorage() const {
        return isBytes() || isOwnedValues();
    }
    Type ownedElement() const {
        Type element(className);
        element.displayName = displayName;
        element.resolvedClass = resolvedClass;
        element.templateArguments = templateArguments;
        return element;
    }
    static Type ownedValues(const Type &element) {
        Type type = element;
        type.kind = TypeKind::OwnedValues;
        return type;
    }
    bool isResource() const {
        return isRegion() || isOwnerStorage();
    }
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
    static Type array(const Type &element, int count) {
        Type type = array(element.kind, count);
        type.setArrayElement(element);
        return type;
    }
    static const Type I64, U64, U8, Bool, Own, Ref, MutRef, ByteSpan, ByteRegion, OwnedBytes, ConsoleSession,
        DisplaySession, IommuEventSession, CallSession, Com1UartGrant, ServeSession;
};
inline const Type Type::I64{TypeKind::I64};
inline const Type Type::U64{TypeKind::U64};
inline const Type Type::U8{TypeKind::U8};
inline const Type Type::Bool{TypeKind::Bool};
inline const Type Type::Own{TypeKind::Own};
inline const Type Type::Ref{TypeKind::Ref};
inline const Type Type::MutRef{TypeKind::MutRef};
inline const Type Type::ByteSpan{TypeKind::ByteSpan};
inline const Type Type::ByteRegion{TypeKind::ByteRegion};
inline const Type Type::OwnedBytes{TypeKind::OwnedBytes};
inline const Type Type::ConsoleSession{TypeKind::ConsoleSession};
inline const Type Type::DisplaySession{TypeKind::DisplaySession};
inline const Type Type::IommuEventSession{TypeKind::IommuEventSession};
inline const Type Type::CallSession{TypeKind::CallSession};
inline const Type Type::Com1UartGrant{TypeKind::Com1UartGrant};
inline const Type Type::ServeSession{TypeKind::ServeSession};
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
    case TypeKind::ByteRegion:
        return "builtin::ByteRegion";
    case TypeKind::CallSession:
        return "builtin::CallSession";
    case TypeKind::ServeSession:
        return "builtin::ServeSession";
    case TypeKind::Com1UartGrant:
        return "builtin::Com1UartGrant";
    case TypeKind::IommuEventSession:
        return "builtin::IommuEventSession";
    case TypeKind::DisplaySession:
        return "builtin::DisplaySession";
    case TypeKind::ConsoleSession:
        return "builtin::ConsoleSession";
    case TypeKind::OwnedBytes:
        return "builtin::OwnedBytes";
    case TypeKind::OwnedValues:
        return "builtin::OwnedValues<" + typeName(type.ownedElement()) + ">";
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
        return "array<" + typeName(type.arrayElement()) + ", " +
               (type.lengthParameter.empty() ? std::to_string(type.length) : type.lengthParameter) + ">";
    }
    return "?";
}
inline bool scalar(Type t) {
    return t == Type::I64 || t == Type::U64 || t == Type::U8 || t == Type::Bool;
}
inline bool scalarValue(const Type &type) {
    return scalar(type) || type.isEnum();
}

// Sector-sized owned byte storage does not widen general scalar-array templates.
inline constexpr int maximumClassByteArrayLength = 512;
inline constexpr int maximumClassScalarArrayLength = 64;
inline constexpr int maximumCopiedByteLeaves = 512;
inline constexpr int maximumCopiedNonByteLeaves = 64;
inline constexpr int maximumCopiedClassLeaves = 513;
inline constexpr int maximumCopiedClassBytes = 520;
inline int maximumClassArrayLength(const Type &element) {
    return element == Type::U8 ? maximumClassByteArrayLength : maximumClassScalarArrayLength;
}

} // namespace aurora
