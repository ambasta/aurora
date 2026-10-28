// aurora-seed: the bootstrap interpreter for the Aurora subset the compiler is
// written in. GCC builds it; it runs the compiler's sources once to produce the
// first compiler (see compiler/README.md, "Source bootstrap"). It is host-only
// bootstrap machinery and is never shipped.
#pragma once

#include <cstdint>
#include <deque>
#include <string>
#include <string_view>
#include <unordered_map>
#include <vector>

namespace seed {

struct Source {
    std::string path;
    std::string text;
};

struct Loc {
    const Source *source = nullptr;
    int line = 0;
};

// Fail closed: an unsupported or invalid construct ends the run (status 3).
[[noreturn]] void fail(const Loc &loc, const std::string &message);

enum class Tk : uint8_t {
    end,
    identifier,
    integer,
    string,
    punctuation
};

// Integer literal types; a character literal is a u8.
enum class Suffix : uint8_t {
    i64,
    u64,
    u8
};

struct Token {
    Tk kind = Tk::end;
    std::string_view text;
    int line = 0;
    uint64_t value = 0;
    Suffix suffix = Suffix::i64;
    std::string bytes; // decoded string literal
};

struct TypeSyntax;
struct TypeArgument {
    TypeSyntax *type = nullptr;
    int64_t number = 0;
};
struct TypeSyntax {
    Loc loc;
    std::vector<std::string> path;
    bool global = false;
    bool constant = false; // const T, as in span<const u8> or const T&
    bool reference = false;
    std::vector<TypeArgument> arguments;
};

enum class Ek : uint8_t {
    integer,
    boolean,
    string,
    name,
    unary,
    binary,
    call,
    member,
    method,
    index,
    construct
};

struct Expr {
    Expr(Ek k, Loc l) : kind(k), loc(l) {
    }
    Ek kind;
    Loc loc;
    std::string op;     // unary/binary operator
    uint64_t value = 0; // integer value, boolean
    Suffix suffix = Suffix::i64;
    std::string text;              // string bytes, member or method name
    std::vector<std::string> path; // name, call or constructed type
    bool global = false;
    Expr *a = nullptr;
    Expr *b = nullptr;
    std::vector<Expr *> arguments;
    std::vector<std::string> fields; // designated construction field names
};

enum class Sk : uint8_t {
    block,
    local,
    ret,
    branch,
    loop,
    expression,
    assign
};

struct Stmt {
    Stmt(Sk k, Loc l) : kind(k), loc(l) {
    }
    Sk kind;
    Loc loc;
    TypeSyntax *type = nullptr;
    bool constant = false;
    std::string name;
    Expr *value = nullptr;
    Expr *target = nullptr;
    Stmt *then = nullptr;
    Stmt *otherwise = nullptr;
    std::vector<Stmt *> body;
};

struct Module;
struct ClassDecl;
struct Type;
struct Node;

struct Param {
    TypeSyntax *type;
    std::string name;
};

struct Init {
    Loc loc;
    std::string field;
    std::vector<Expr *> arguments;
    bool braces = false;
};

enum class Mode : uint8_t {
    value,
    reference
};

struct Function {
    // What a call reads, first, so that it touches few cache lines.
    Node *code = nullptr;
    int64_t frame_size = 0;
    int64_t calls = 0;
    int64_t object_size = -1;        // a constructor's class size, else -1
    std::vector<int64_t> entry_null; // owner words of locals, cleared on entry
    std::vector<int64_t> exit_drop;  // every owner word of the frame
    // Declaration.
    std::string name;
    Loc loc;
    Module *module = nullptr;
    std::string space;
    bool exported = false;
    ClassDecl *owner = nullptr;
    bool constructor = false;
    bool constant = false;
    std::vector<Param> params;
    TypeSyntax *result = nullptr;
    std::vector<Init> inits;
    Stmt *body = nullptr;
    // Semantic state, filled lazily.
    bool signed_up = false;
    std::vector<Type *> param_types;
    std::vector<Mode> modes;
    std::vector<int64_t> param_offsets;
    int64_t params_size = 0;
    Type *result_type = nullptr;
    int getter = 0;       // 0 unknown, 1 a plain field getter, 2 not one
    int inline_state = 0; // 0 unknown, 1 an expression body, 2 not one, 3 being lowered
    Node *inline_body = nullptr;
    int64_t getter_offset = 0;
    Type *getter_type = nullptr;
    bool compiling = false;
};

struct FieldDecl {
    Loc loc;
    TypeSyntax *type = nullptr;
    std::string name;
};

struct ClassDecl {
    std::string name;
    Loc loc;
    Module *module = nullptr;
    std::string space;
    bool exported = false;
    std::vector<FieldDecl> fields;
    std::vector<Function *> constructors;
    std::vector<Function *> methods;
    // Layout, filled lazily.
    int state = 0; // 0 none, 1 laying out, 2 done
    std::vector<Type *> field_types;
    std::vector<int64_t> offsets;
    int64_t size = 0;
    Type *type = nullptr;
};

struct EnumDecl {
    std::string name;
    Loc loc;
    Module *module = nullptr;
    std::string space;
    bool exported = false;
    std::vector<std::string> cases;
    Type *type = nullptr;
};

struct Module {
    std::string name;
    Source *source = nullptr;
    std::vector<std::string> imports;
    std::vector<Function *> functions;
    std::vector<ClassDecl *> classes;
    std::vector<EnumDecl *> enums;
};

// Parses one module source; the result and its nodes live as long as the run.
Module *parse_module(Source *source);

} // namespace seed
