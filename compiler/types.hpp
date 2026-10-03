#pragma once
#include <cstdint>
#include <stdexcept>
#include <string>
#include <utility>
namespace aurora {
class Error : public std::runtime_error {
  public:
    using std::runtime_error::runtime_error;
};
class Token {
  public:
    std::string text;
    int line;
    Token(std::string t, int l) : text(std::move(t)), line(l) {}
};
enum class TypeKind { I64, Bool, Own, Ref, MutRef, Class, Array };
class Type {
  public:
    TypeKind kind = TypeKind::I64;
    std::string className;
    TypeKind elementKind = TypeKind::I64;
    int length = 0;
    Type() = default;
    explicit Type(TypeKind value) : kind(value) {}
    explicit Type(std::string name) : kind(TypeKind::Class), className(std::move(name)) {}
    bool operator==(const Type &) const = default;
    bool isClass() const {
        return kind == TypeKind::Class;
    }
    bool isArray() const {
        return kind == TypeKind::Array;
    }
    static Type array(TypeKind element, int count) {
        Type type(TypeKind::Array);
        type.elementKind = element;
        type.length = count;
        return type;
    }
    static const Type I64, Bool, Own, Ref, MutRef;
};
inline const Type Type::I64{TypeKind::I64};
inline const Type Type::Bool{TypeKind::Bool};
inline const Type Type::Own{TypeKind::Own};
inline const Type Type::Ref{TypeKind::Ref};
inline const Type Type::MutRef{TypeKind::MutRef};
inline std::string typeName(const Type &type) {
    switch (type.kind) {
    case TypeKind::I64:
        return "i64";
    case TypeKind::Bool:
        return "bool";
    case TypeKind::Own:
        return "own<i64>";
    case TypeKind::Ref:
        return "ref<i64>";
    case TypeKind::MutRef:
        return "mutref<i64>";
    case TypeKind::Class:
        return type.className;
    case TypeKind::Array:
        return "array<" + typeName(Type(type.elementKind)) + ", " + std::to_string(type.length) +
               ">";
    }
    return "?";
}
inline bool scalar(Type t) {
    return t == Type::I64 || t == Type::Bool;
}

} // namespace aurora
