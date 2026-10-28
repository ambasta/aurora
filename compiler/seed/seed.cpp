// The seed interpreter: module loading, name and type resolution, lowering of
// each function (on its first call) to a tree of typed nodes with resolved
// frame offsets, and their evaluation. Values have one flat byte layout: u8 and
// bool take one byte, other scalars, enums and owner words eight, classes their
// fields in order, spans a (pointer, count) pair. Integer arithmetic, indexing,
// conversions and owner access are checked as the compiled language checks
// them, and every failure traps (status 4).
//
// builtin::ByteRegion and its owners are native here, with the observable
// behaviour of runtime/linux/aurora/memory.au: the 4 GiB payload quota, at most
// 16383 live allocations, zeroed or filled new storage, prefix-preserving
// resize and inert failures. builtin::HostFiles is the interpreted
// runtime/linux/aurora/host.au over native primitives: the 16384-byte session
// block and the Linux system calls the compiler emits inline for it.
#include "seed.hpp"

#include <algorithm>
#include <cerrno>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <map>
#include <sstream>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <unistd.h>

namespace seed {

[[noreturn]] void fail(const Loc &loc, const std::string &message) {
    std::fprintf(stderr,
                 "aurora-seed: %s:%d: %s\n",
                 loc.source != nullptr ? loc.source->path.c_str() : "<seed>",
                 loc.line,
                 message.c_str());
    std::fflush(stderr);
    std::_Exit(3);
}

// ---------------------------------------------------------------- types

enum class K : uint8_t {
    i64,
    u64,
    u8,
    boolean,
    enumeration,
    object,
    array,
    span,
    bytes,
    values,
    region,
    files
};

struct Type {
    K kind;
    int64_t size = 8;
    EnumDecl *enumeration = nullptr;
    ClassDecl *object = nullptr;
    Type *element = nullptr;
    int64_t count = 0;
    std::vector<int64_t> owners; // offsets of the owner words inside a value
    std::string name;
};

namespace {

Type i64_type{K::i64, 8, nullptr, nullptr, nullptr, 0, {}, "i64"};
Type u64_type{K::u64, 8, nullptr, nullptr, nullptr, 0, {}, "u64"};
Type u8_type{K::u8, 1, nullptr, nullptr, nullptr, 0, {}, "u8"};
Type bool_type{K::boolean, 1, nullptr, nullptr, nullptr, 0, {}, "bool"};
Type bytes_type{K::bytes, 8, nullptr, nullptr, nullptr, 0, {0}, "builtin::OwnedBytes"};
Type region_type{K::region, 8, nullptr, nullptr, nullptr, 0, {}, "builtin::ByteRegion"};
Type files_type{K::files, 8, nullptr, nullptr, nullptr, 0, {}, "builtin::HostFiles"};

bool scalar(const Type *type) {
    return type->kind != K::object && type->kind != K::array && type->kind != K::span;
}
uint8_t width(const Type *type) {
    return type->size == 1 ? 1 : 8;
}

std::map<std::pair<Type *, int64_t>, Type *> arrays;
std::map<Type *, Type *> spans;
std::map<Type *, Type *> value_owners;

Type *array_of(Type *element, int64_t count, const Loc &loc) {
    if (!element->owners.empty() || count < 0 || count > 4096) {
        fail(loc, "unsupported array type");
    }
    Type *&slot = arrays[{element, count}];
    if (slot == nullptr) {
        slot = new Type{K::array, element->size * count, nullptr, nullptr, element, count, {}, ""};
        slot->name = "array<" + element->name + ", " + std::to_string(count) + ">";
    }
    return slot;
}
Type *span_of(Type *element, const Loc &loc) {
    if (element->kind != K::u8 && element->kind != K::object) {
        fail(loc, "unsupported span element");
    }
    Type *&slot = spans[element];
    if (slot == nullptr) {
        slot = new Type{K::span, 16, nullptr, nullptr, element, 0, {}, "builtin::span<const " + element->name + ">"};
    }
    return slot;
}
Type *values_of(Type *element, const Loc &loc) {
    if (element->kind != K::object || !element->owners.empty()) {
        fail(loc, "unsupported OwnedValues element");
    }
    Type *&slot = value_owners[element];
    if (slot == nullptr) {
        slot = new Type{K::values, 8, nullptr, nullptr, element, 0, {0}, "builtin::OwnedValues<" + element->name + ">"};
    }
    return slot;
}

// ---------------------------------------------------------------- names

struct Entity {
    enum class Kind : uint8_t {
        function,
        object,
        enumeration
    } kind;
    Function *function = nullptr;
    ClassDecl *object = nullptr;
    EnumDecl *enumeration = nullptr;
    Module *module = nullptr;
    bool exported = false;
};

std::unordered_map<std::string, std::unordered_map<std::string, std::vector<Entity>>> spaces;
std::map<std::string, Module *> modules;

void declare(const std::string &space, const std::string &name, const Entity &entity) {
    spaces[space][name].push_back(entity);
}

// Whether an entity is visible from a module: its own, a builtin, or exported
// by a module it imports directly.
bool visible_from(const Entity &entity, const Module *module) {
    if (entity.module == module || entity.module == nullptr) {
        return true;
    }
    return entity.exported &&
           std::find(module->imports.begin(), module->imports.end(), entity.module->name) != module->imports.end();
}

// The visible entities a possibly qualified name denotes, searched from the
// innermost namespace outwards.
std::vector<const Entity *>
find(const std::vector<std::string> &path, size_t count, bool global, const Module *module, const std::string &space) {
    std::vector<std::string> scopes;
    if (!global && !space.empty()) {
        scopes.push_back(space);
    }
    scopes.emplace_back();
    for (const std::string &scope : scopes) {
        std::string key = scope;
        bool found = true;
        for (size_t at = 0; at + 1 < count; ++at) {
            key = key.empty() ? path[at] : key + "::" + path[at];
            if (!spaces.contains(key)) {
                found = false;
                break;
            }
        }
        if (!found) {
            continue;
        }
        const auto names = spaces.find(key);
        if (names == spaces.end()) {
            continue;
        }
        const auto entry = names->second.find(path[count - 1]);
        if (entry == names->second.end()) {
            continue;
        }
        std::vector<const Entity *> visible;
        for (const Entity &entity : entry->second) {
            if (visible_from(entity, module)) {
                visible.push_back(&entity);
            }
        }
        if (!visible.empty()) {
            return visible;
        }
    }
    return {};
}

std::string spelled(const std::vector<std::string> &path, size_t count) {
    std::string result;
    for (size_t at = 0; at < count; ++at) {
        result += (at == 0 ? "" : "::") + path[at];
    }
    return result;
}

Type *class_type(ClassDecl *decl);
Type *enum_type(EnumDecl *decl);

const Entity *find_type(const std::vector<std::string> &path,
                        size_t count,
                        bool global,
                        const Module *module,
                        const std::string &space,
                        const Loc &loc) {
    const std::vector<const Entity *> found = find(path, count, global, module, space);
    if (found.size() != 1 || found[0]->kind == Entity::Kind::function) {
        fail(loc, "unknown or ambiguous type " + spelled(path, count));
    }
    return found[0];
}

Type *resolve(const TypeSyntax *syntax, const Module *module, const std::string &space) {
    const std::vector<std::string> &path = syntax->path;
    const Loc &loc = syntax->loc;
    const bool builtin = path.size() == 2 && path[0] == "builtin" && !syntax->global;
    const std::string leaf = path.back();
    const auto argument = [&](size_t at) -> Type * {
        if (syntax->arguments.size() <= at || syntax->arguments[at].type == nullptr) {
            fail(loc, "expected a type argument");
        }
        return resolve(syntax->arguments[at].type, module, space);
    };
    if (path.size() == 1 && syntax->arguments.empty() && !syntax->global) {
        if (leaf == "i64") {
            return &i64_type;
        }
        if (leaf == "u64") {
            return &u64_type;
        }
        if (leaf == "u8") {
            return &u8_type;
        }
        if (leaf == "bool") {
            return &bool_type;
        }
    }
    if ((builtin || (path.size() == 1 && !syntax->global)) && leaf == "array") {
        if (syntax->arguments.size() != 2 || syntax->arguments[1].type != nullptr) {
            fail(loc, "invalid array type");
        }
        return array_of(argument(0), syntax->arguments[1].number, loc);
    }
    if (builtin) {
        if (leaf == "span" && syntax->arguments.size() == 1 && syntax->arguments[0].type != nullptr &&
            syntax->arguments[0].type->constant) {
            return span_of(argument(0), loc);
        }
        if (leaf == "OwnedValues" && syntax->arguments.size() == 1) {
            return values_of(argument(0), loc);
        }
        if (!syntax->arguments.empty()) {
            fail(loc, "unsupported builtin type " + leaf);
        }
        if (leaf == "OwnedBytes") {
            return &bytes_type;
        }
        if (leaf == "ByteRegion") {
            return &region_type;
        }
        if (leaf == "HostFiles") {
            return &files_type;
        }
    }
    if (!syntax->arguments.empty()) {
        fail(loc, "unsupported type arguments");
    }
    const Entity *entity = find_type(path, path.size(), syntax->global, module, space, loc);
    return entity->kind == Entity::Kind::object ? class_type(entity->object) : enum_type(entity->enumeration);
}

Type *enum_type(EnumDecl *decl) {
    if (decl->type == nullptr) {
        decl->type = new Type{K::enumeration, 8, decl, nullptr, nullptr, 0, {}, decl->name};
    }
    return decl->type;
}

// Lays a class out on first use: its fields in declaration order, packed.
Type *class_type(ClassDecl *decl) {
    if (decl->state == 2) {
        return decl->type;
    }
    if (decl->state == 1) {
        fail(decl->loc, "class contains itself");
    }
    decl->state = 1;
    auto *type = new Type{K::object, 0, nullptr, decl, nullptr, 0, {}, decl->name};
    for (const FieldDecl &field : decl->fields) {
        Type *field_type = resolve(field.type, decl->module, decl->space);
        if (field.type->reference || field_type->kind == K::region || field_type->kind == K::files ||
            field_type->kind == K::span) {
            fail(field.loc, "unsupported field type");
        }
        decl->field_types.push_back(field_type);
        decl->offsets.push_back(type->size);
        for (const int64_t owner : field_type->owners) {
            type->owners.push_back(type->size + owner);
        }
        type->size += field_type->size;
    }
    if (type->size == 0) {
        type->size = 8; // an empty class still has eight bytes of storage
    }
    decl->size = type->size;
    decl->type = type;
    decl->state = 2;
    return type;
}

int field_index(const ClassDecl *decl, const std::string &name) {
    for (size_t at = 0; at < decl->fields.size(); ++at) {
        if (decl->fields[at].name == name) {
            return static_cast<int>(at);
        }
    }
    return -1;
}

// The builtin namespace: the hosted result classes and status enums.
void declare_builtins() {
    const auto enumeration = [](const std::string &name, std::vector<std::string> cases) {
        auto *decl = new EnumDecl;
        decl->name = name;
        decl->space = "builtin";
        decl->exported = true;
        decl->cases = std::move(cases);
        declare("builtin", name, Entity{Entity::Kind::enumeration, nullptr, nullptr, decl, nullptr, true});
        return enum_type(decl);
    };
    Type *status = enumeration("HostStatus",
                               {"success",
                                "invalid_handle",
                                "not_found",
                                "denied",
                                "escape",
                                "not_regular",
                                "exhausted",
                                "too_large",
                                "invalid_path",
                                "failed"});
    enumeration("HostExit", {"success", "failure", "usage"});
    enumeration("HostStream", {"stdout", "stderr"});
    const auto object = [&](const std::string &name, const std::vector<std::string> &fields, Type *last) {
        auto *decl = new ClassDecl;
        decl->name = name;
        decl->space = "builtin";
        decl->exported = true;
        auto *type = new Type{K::object, 0, nullptr, decl, nullptr, 0, {}, name};
        for (size_t at = 0; at < fields.size(); ++at) {
            Type *field_type = at == 0 ? status : (at + 1 == fields.size() && last != nullptr ? last : &u64_type);
            decl->fields.push_back(FieldDecl{Loc{}, nullptr, fields[at]});
            decl->field_types.push_back(field_type);
            decl->offsets.push_back(type->size);
            type->size += field_type->size;
        }
        decl->size = type->size;
        decl->type = type;
        decl->state = 2;
        declare("builtin", name, Entity{Entity::Kind::object, nullptr, decl, nullptr, nullptr, true});
    };
    object("HostDirectoryResult", {"status", "id", "device", "inode"}, nullptr);
    object("HostFileResult", {"status", "id", "size", "device", "inode"}, nullptr);
    object("HostOutputResult", {"status", "id", "device", "inode", "directory_device", "directory_inode"}, nullptr);
    object("HostChunk", {"status", "count", "bytes"}, array_of(&u8_type, 504, Loc{}));
}

// ---------------------------------------------------------------- nodes

} // namespace

// How a call passes one argument, or a construction one field.
enum class Pass : uint8_t {
    scalar8,
    scalar1,
    object,
    reference
};

// The frame of one call: its slots, the receiver, a copied result's
// destination and a scalar result.
struct Frame {
    uint8_t *base;
    uint8_t *self;
    uint8_t *result;
    int64_t value;
};

struct Node;
using Run = int64_t (*)(const Node *, Frame &, uint8_t *);

// One argument of a call: its value and the callee's slot for it.
struct Argument {
    const Node *node;
    int64_t offset;
    Pass pass;
};

struct Node {
    Run run;
    uint8_t width = 8;
    Loc loc;
    int64_t offset = 0;
    int64_t value = 0;
    Node *a = nullptr;
    Node *b = nullptr;
    Node *c = nullptr;
    Function *function = nullptr;
    std::vector<Node *> list;
    std::vector<int64_t> words;      // owner words
    std::vector<Argument> arguments; // of a call, or a designated construction's fields
    const uint8_t *data = nullptr;
};

namespace {

std::deque<Node> nodes;

Node *make(Run run, const Loc &loc) {
    Node &node = nodes.emplace_back();
    node.run = run;
    node.loc = loc;
    return &node;
}

// ---------------------------------------------------------------- runtime

[[noreturn]] void trap(const Node *node, const char *what) {
    std::fprintf(stderr,
                 "aurora-seed: trap: %s at %s:%d\n",
                 what,
                 node->loc.source != nullptr ? node->loc.source->path.c_str() : "<seed>",
                 node->loc.line);
    std::fflush(stderr);
    std::_Exit(4);
}

inline int64_t read8(const uint8_t *at) {
    int64_t value;
    std::memcpy(&value, at, 8);
    return value;
}
inline void write8(uint8_t *at, int64_t value) {
    std::memcpy(at, &value, 8);
}

// A runtime owner: count elements of stride bytes. Failed owners share one
// inert record; a cleared owner word (moved or dropped) is zero.
struct Owner {
    uint8_t *data;
    int64_t count;
    int64_t stride;
    bool ok;
};
Owner failed_owner{nullptr, 0, 1, false};

// memory.au: a 4 GiB payload quota and slots 1..16383.
constexpr uint64_t quota = 4294967296ULL;
constexpr int64_t slot_limit = 16383;
uint64_t used_bytes = 0;
int64_t live_owners = 0;

[[noreturn]] void trap(const Node *node, const char *what);

inline Owner *owner_at(const Node *node, const uint8_t *word) {
    Owner *owner = reinterpret_cast<Owner *>(read8(word));
    if (owner == nullptr) {
        trap(node, "use of a moved owner");
    }
    return owner;
}

// The byte length of count elements, or -1.
int64_t byte_length(int64_t count, int64_t stride) {
    if (count < 0 || count > INT64_MAX / stride) {
        return -1;
    }
    return count * stride;
}

Owner *allocate(int64_t count, int64_t stride, const uint8_t *fill) {
    const int64_t length = byte_length(count, stride);
    if (length < 0 || static_cast<uint64_t>(length) > quota - used_bytes || live_owners == slot_limit) {
        return &failed_owner;
    }
    uint8_t *data = nullptr;
    if (length > 0) {
        data = static_cast<uint8_t *>(fill == nullptr ? std::calloc(static_cast<size_t>(length), 1)
                                                      : std::malloc(static_cast<size_t>(length)));
        if (data == nullptr) {
            return &failed_owner;
        }
        if (fill != nullptr) {
            for (int64_t at = 0; at < count; ++at) {
                std::memcpy(data + at * stride, fill, static_cast<size_t>(stride));
            }
        }
    }
    used_bytes += static_cast<uint64_t>(length);
    ++live_owners;
    return new Owner{data, count, stride, true};
}

bool resize(Owner *owner, int64_t count, const uint8_t *fill) {
    if (!owner->ok) {
        return false;
    }
    const int64_t length = byte_length(count, owner->stride);
    if (length < 0) {
        return false;
    }
    if (count == owner->count) {
        return true;
    }
    const uint64_t old_length = static_cast<uint64_t>(owner->count * owner->stride);
    if (static_cast<uint64_t>(length) > quota - (used_bytes - old_length)) {
        return false;
    }
    uint8_t *data = nullptr;
    if (length > 0) {
        data = static_cast<uint8_t *>(std::realloc(owner->data, static_cast<size_t>(length)));
        if (data == nullptr) {
            return false;
        }
        for (int64_t at = owner->count; at < count; ++at) {
            if (fill == nullptr) {
                data[at] = 0;
            } else {
                std::memcpy(data + at * owner->stride, fill, static_cast<size_t>(owner->stride));
            }
        }
    } else {
        std::free(owner->data);
    }
    used_bytes = used_bytes - old_length + static_cast<uint64_t>(length);
    owner->data = data;
    owner->count = count;
    return true;
}

void drop_word(uint8_t *word) {
    Owner *owner = reinterpret_cast<Owner *>(read8(word));
    if (owner != nullptr && owner != &failed_owner) {
        used_bytes -= static_cast<uint64_t>(owner->count * owner->stride);
        --live_owners;
        std::free(owner->data);
        delete owner;
    }
    write8(word, 0);
}

// The interpreter's stack of frames.
uint8_t *stack_top = nullptr;
uint8_t *stack_end = nullptr;

enum class Flow : uint8_t {
    normal,
    returned
};

void compile(Function *function);

int64_t run_constant(const Node *node, Frame &, uint8_t *) {
    return node->value;
}
int64_t run_load_local8(const Node *node, Frame &frame, uint8_t *) {
    return read8(frame.base + node->offset);
}

// Locals and constants, the commonest operands, skip the indirect call.
inline int64_t eval(const Node *node, Frame &frame) {
    if (node->run == run_load_local8) {
        return read8(frame.base + node->offset);
    }
    if (node->run == run_constant) {
        return node->value;
    }
    return node->run(node, frame, nullptr);
}
inline void eval_into(const Node *node, Frame &frame, uint8_t *destination) {
    node->run(node, frame, destination);
}
inline uint8_t *place(const Node *node, Frame &frame) {
    return reinterpret_cast<uint8_t *>(node->run(node, frame, nullptr));
}
inline Flow exec(const Node *node, Frame &frame) {
    return static_cast<Flow>(node->run(node, frame, nullptr));
}
inline int64_t address(const uint8_t *at) {
    return reinterpret_cast<int64_t>(at);
}

// Evaluates values left to right into their slots at base + offset.
void pass_arguments(const std::vector<Argument> &arguments, Frame &frame, uint8_t *base) {
    for (const Argument &argument : arguments) {
        uint8_t *slot = base + argument.offset;
        switch (argument.pass) {
        case Pass::scalar8:
            write8(slot, eval(argument.node, frame));
            break;
        case Pass::scalar1:
            *slot = static_cast<uint8_t>(eval(argument.node, frame));
            break;
        case Pass::object:
            eval_into(argument.node, frame, slot);
            break;
        case Pass::reference:
            write8(slot, address(place(argument.node, frame)));
            break;
        }
    }
}

// Calls a function: reserves its frame, passes the arguments left to right,
// runs the body and drops every owner still held.
int64_t invoke(const Node *node, Frame &frame, uint8_t *destination) {
    Function *function = node->function;
    if (function->code == nullptr) {
        compile(function);
    }
    ++function->calls;
    uint8_t *base = stack_top;
    stack_top += function->frame_size;
    if (stack_top > stack_end) {
        trap(node, "interpreter stack exhausted");
    }
    uint8_t *self = node->a != nullptr ? place(node->a, frame) : destination;
    pass_arguments(node->arguments, frame, base);
    if (function->object_size >= 0) {
        std::memset(destination, 0, static_cast<size_t>(function->object_size));
    }
    for (const int64_t word : function->entry_null) {
        write8(base + word, 0);
    }
    Frame callee{base, self, destination, 0};
    if (exec(function->code, callee) == Flow::normal && function->result_type != nullptr) {
        trap(node, "function ended without a return");
    }
    for (const int64_t word : function->exit_drop) {
        drop_word(base + word);
    }
    stack_top = base;
    return callee.value;
}

int64_t run_call(const Node *node, Frame &frame, uint8_t *destination) {
    return invoke(node, frame, destination);
}

// A method whose body is one expression over its receiver's fields: the
// expression runs with the receiver as self, without a frame of its own.
int64_t run_receiver_expression(const Node *node, Frame &frame, uint8_t *) {
    uint8_t *receiver = place(node->a, frame);
    uint8_t *saved = frame.self;
    frame.self = receiver;
    const int64_t value = eval(node->b, frame);
    frame.self = saved;
    return value;
}

// ---- host primitives

constexpr uint64_t session_bytes = 16384;

void check_session(const Node *node, uint64_t offset, uint64_t length) {
    if (offset > session_bytes || length > session_bytes || offset + length > session_bytes) {
        trap(node, "session bounds");
    }
}

// A NUL-terminated session path [offset, offset + length).
const char *session_path(const Node *node, uint8_t *session, uint64_t offset, uint64_t length) {
    const uint64_t last = session_bytes - 1;
    if (offset > last || length > last || offset + length > last) {
        trap(node, "session path bounds");
    }
    session[offset + length] = 0;
    return reinterpret_cast<const char *>(session + offset);
}

int64_t system_result(long result) {
    return result == -1 ? -static_cast<int64_t>(errno) : static_cast<int64_t>(result);
}

// openat2 flags of the six open modes (x86_helpers.au host_open_flags).
int64_t open_flags(uint64_t mode) {
    switch (mode) {
    case 0:
        return 589824;
    case 1:
    case 5:
        return 526336;
    case 2:
        return 2752512;
    case 3:
        return 655553;
    default:
        return 2;
    }
}

int64_t run_primitive(const Node *node, Frame &frame, uint8_t *) {
    uint8_t *session = reinterpret_cast<uint8_t *>(eval(node->a, frame));
    int64_t args[5] = {};
    for (size_t at = 0; at < node->list.size(); ++at) {
        args[at] = eval(node->list[at], frame);
    }
    const auto u = [&](int at) {
        return static_cast<uint64_t>(args[at]);
    };
    switch (node->value) {
    case 9:
        check_session(node, u(0), 8);
        return read8(session + u(0));
    case 10:
        check_session(node, u(0), 8);
        write8(session + u(0), args[1]);
        return args[1];
    case 11:
        check_session(node, u(0), 1);
        return session[u(0)];
    case 12:
        check_session(node, u(0), 1);
        session[u(0)] = static_cast<uint8_t>(args[1]);
        return args[1];
    case 13: {
        if (u(3) > 5) {
            trap(node, "open mode");
        }
        const char *path = session_path(node, session, u(1), u(2));
        struct {
            uint64_t flags;
            uint64_t mode;
            uint64_t resolve;
        } how{};
        how.flags = static_cast<uint64_t>(open_flags(u(3)));
        how.mode = (how.flags & 64) != 0 ? 0600 : 0;
        how.resolve = 6 + (u(3) >= 1 && u(3) <= 3 ? 8 : 0);
        constexpr long openat2 = 437;
        return system_result(syscall(openat2, static_cast<int>(args[0]), path, &how, sizeof how));
    }
    case 15:
        check_session(node, u(1), u(2));
        return system_result(syscall(SYS_write, static_cast<int>(args[0]), session + u(1), u(2)));
    case 16: {
        const char *from = session_path(node, session, u(1), u(2));
        const char *to = session_path(node, session, u(3), u(4));
        return system_result(syscall(SYS_renameat, static_cast<int>(args[0]), from, static_cast<int>(args[0]), to));
    }
    case 17: {
        const char *path = session_path(node, session, u(1), u(2));
        return system_result(syscall(SYS_unlinkat, static_cast<int>(args[0]), path, 0));
    }
    case 18:
        return system_result(syscall(SYS_close, static_cast<int>(args[0])));
    case 19:
        if (u(1) > session_bytes - 144) {
            trap(node, "session bounds");
        }
        return system_result(syscall(SYS_fstat, static_cast<int>(args[0]), session + u(1)));
    case 20:
        return system_result(syscall(SYS_getpid));
    default:
        trap(node, "unknown primitive");
    }
}

// pread64 of 504 bytes into a cleared HostChunk: status failed (9) and count 0
// on an error, otherwise success and the count.
int64_t run_chunk(const Node *node, Frame &frame, uint8_t *destination) {
    const int64_t descriptor = eval(node->list[0], frame);
    const int64_t offset = eval(node->list[1], frame);
    std::memset(destination, 0, 520);
    const int64_t result =
        system_result(syscall(SYS_pread64, static_cast<int>(descriptor), destination + 16, 504, offset));
    if (result > 504) {
        trap(node, "read count");
    }
    write8(destination, result < 0 ? 9 : 0);
    write8(destination + 8, result < 0 ? 0 : result);
    return 0;
}

// ---- scalars

int64_t run_load_local1(const Node *node, Frame &frame, uint8_t *) {
    return frame.base[node->offset];
}
int64_t run_load_self8(const Node *node, Frame &frame, uint8_t *) {
    return read8(frame.self + node->offset);
}
int64_t run_load_self1(const Node *node, Frame &frame, uint8_t *) {
    return frame.self[node->offset];
}
int64_t run_load8(const Node *node, Frame &frame, uint8_t *) {
    return read8(place(node->a, frame) + node->offset);
}
int64_t run_load1(const Node *node, Frame &frame, uint8_t *) {
    return place(node->a, frame)[node->offset];
}

[[noreturn]] void overflow(const Node *node) {
    trap(node, "arithmetic overflow");
}

int64_t run_add_i(const Node *node, Frame &frame, uint8_t *) {
    const int64_t a = eval(node->a, frame);
    const int64_t b = eval(node->b, frame);
    int64_t r = 0;
    if (__builtin_add_overflow(a, b, &r)) {
        overflow(node);
    }
    return r;
}
int64_t run_sub_i(const Node *node, Frame &frame, uint8_t *) {
    const int64_t a = eval(node->a, frame);
    const int64_t b = eval(node->b, frame);
    int64_t r = 0;
    if (__builtin_sub_overflow(a, b, &r)) {
        overflow(node);
    }
    return r;
}
int64_t run_mul_i(const Node *node, Frame &frame, uint8_t *) {
    const int64_t a = eval(node->a, frame);
    const int64_t b = eval(node->b, frame);
    int64_t r = 0;
    if (__builtin_mul_overflow(a, b, &r)) {
        overflow(node);
    }
    return r;
}
int64_t run_div_i(const Node *node, Frame &frame, uint8_t *) {
    const int64_t a = eval(node->a, frame);
    const int64_t b = eval(node->b, frame);
    if (b == 0) {
        trap(node, "division by zero");
    }
    if (a == INT64_MIN && b == -1) {
        overflow(node);
    }
    return a / b;
}
int64_t run_rem_i(const Node *node, Frame &frame, uint8_t *) {
    const int64_t a = eval(node->a, frame);
    const int64_t b = eval(node->b, frame);
    if (b == 0) {
        trap(node, "division by zero");
    }
    return b == -1 ? 0 : a % b;
}
int64_t run_neg_i(const Node *node, Frame &frame, uint8_t *) {
    const int64_t a = eval(node->a, frame);
    if (a == INT64_MIN) {
        overflow(node);
    }
    return -a;
}
int64_t run_add_u(const Node *node, Frame &frame, uint8_t *) {
    const uint64_t a = static_cast<uint64_t>(eval(node->a, frame));
    const uint64_t b = static_cast<uint64_t>(eval(node->b, frame));
    uint64_t r = 0;
    if (__builtin_add_overflow(a, b, &r)) {
        overflow(node);
    }
    return static_cast<int64_t>(r);
}
int64_t run_sub_u(const Node *node, Frame &frame, uint8_t *) {
    const uint64_t a = static_cast<uint64_t>(eval(node->a, frame));
    const uint64_t b = static_cast<uint64_t>(eval(node->b, frame));
    if (b > a) {
        overflow(node);
    }
    return static_cast<int64_t>(a - b);
}
int64_t run_mul_u(const Node *node, Frame &frame, uint8_t *) {
    const uint64_t a = static_cast<uint64_t>(eval(node->a, frame));
    const uint64_t b = static_cast<uint64_t>(eval(node->b, frame));
    uint64_t r = 0;
    if (__builtin_mul_overflow(a, b, &r)) {
        overflow(node);
    }
    return static_cast<int64_t>(r);
}
int64_t run_div_u(const Node *node, Frame &frame, uint8_t *) {
    const uint64_t a = static_cast<uint64_t>(eval(node->a, frame));
    const uint64_t b = static_cast<uint64_t>(eval(node->b, frame));
    if (b == 0) {
        trap(node, "division by zero");
    }
    return static_cast<int64_t>(a / b);
}
int64_t run_rem_u(const Node *node, Frame &frame, uint8_t *) {
    const uint64_t a = static_cast<uint64_t>(eval(node->a, frame));
    const uint64_t b = static_cast<uint64_t>(eval(node->b, frame));
    if (b == 0) {
        trap(node, "division by zero");
    }
    return static_cast<int64_t>(a % b);
}
int64_t run_and_u(const Node *node, Frame &frame, uint8_t *) {
    const int64_t a = eval(node->a, frame);
    return a & eval(node->b, frame);
}
int64_t run_or_u(const Node *node, Frame &frame, uint8_t *) {
    const int64_t a = eval(node->a, frame);
    return a | eval(node->b, frame);
}
int64_t run_xor_u(const Node *node, Frame &frame, uint8_t *) {
    const int64_t a = eval(node->a, frame);
    return a ^ eval(node->b, frame);
}
int64_t run_not_u(const Node *node, Frame &frame, uint8_t *) {
    return ~eval(node->a, frame);
}
int64_t run_shl_u(const Node *node, Frame &frame, uint8_t *) {
    const uint64_t a = static_cast<uint64_t>(eval(node->a, frame));
    const int64_t b = eval(node->b, frame);
    if (b < 0 || b > 63) {
        trap(node, "shift count");
    }
    const uint64_t r = a << b;
    if ((r >> b) != a) {
        overflow(node);
    }
    return static_cast<int64_t>(r);
}
int64_t run_shr_u(const Node *node, Frame &frame, uint8_t *) {
    const uint64_t a = static_cast<uint64_t>(eval(node->a, frame));
    const int64_t b = eval(node->b, frame);
    if (b < 0 || b > 63) {
        trap(node, "shift count");
    }
    return static_cast<int64_t>(a >> b);
}
int64_t byte_result(const Node *node, int64_t value) {
    if (value < 0 || value > 255) {
        overflow(node);
    }
    return value;
}
int64_t run_add_b(const Node *node, Frame &frame, uint8_t *) {
    const int64_t a = eval(node->a, frame);
    return byte_result(node, a + eval(node->b, frame));
}
int64_t run_sub_b(const Node *node, Frame &frame, uint8_t *) {
    const int64_t a = eval(node->a, frame);
    return byte_result(node, a - eval(node->b, frame));
}
int64_t run_mul_b(const Node *node, Frame &frame, uint8_t *) {
    const int64_t a = eval(node->a, frame);
    return byte_result(node, a * eval(node->b, frame));
}
int64_t run_not_b(const Node *node, Frame &frame, uint8_t *) {
    return 255 - eval(node->a, frame);
}
int64_t run_shl_b(const Node *node, Frame &frame, uint8_t *) {
    const int64_t a = eval(node->a, frame);
    const int64_t b = eval(node->b, frame);
    if (b < 0 || b > 7) {
        trap(node, "shift count");
    }
    return byte_result(node, a << b);
}
int64_t run_shr_b(const Node *node, Frame &frame, uint8_t *) {
    const int64_t a = eval(node->a, frame);
    const int64_t b = eval(node->b, frame);
    if (b < 0 || b > 7) {
        trap(node, "shift count");
    }
    return a >> b;
}
int64_t run_eq(const Node *node, Frame &frame, uint8_t *) {
    const int64_t a = eval(node->a, frame);
    return a == eval(node->b, frame);
}
int64_t run_ne(const Node *node, Frame &frame, uint8_t *) {
    const int64_t a = eval(node->a, frame);
    return a != eval(node->b, frame);
}
int64_t run_lt_i(const Node *node, Frame &frame, uint8_t *) {
    const int64_t a = eval(node->a, frame);
    return a < eval(node->b, frame);
}
int64_t run_le_i(const Node *node, Frame &frame, uint8_t *) {
    const int64_t a = eval(node->a, frame);
    return a <= eval(node->b, frame);
}
int64_t run_gt_i(const Node *node, Frame &frame, uint8_t *) {
    const int64_t a = eval(node->a, frame);
    return a > eval(node->b, frame);
}
int64_t run_ge_i(const Node *node, Frame &frame, uint8_t *) {
    const int64_t a = eval(node->a, frame);
    return a >= eval(node->b, frame);
}
int64_t run_lt_u(const Node *node, Frame &frame, uint8_t *) {
    const uint64_t a = static_cast<uint64_t>(eval(node->a, frame));
    return a < static_cast<uint64_t>(eval(node->b, frame));
}
int64_t run_le_u(const Node *node, Frame &frame, uint8_t *) {
    const uint64_t a = static_cast<uint64_t>(eval(node->a, frame));
    return a <= static_cast<uint64_t>(eval(node->b, frame));
}
int64_t run_gt_u(const Node *node, Frame &frame, uint8_t *) {
    const uint64_t a = static_cast<uint64_t>(eval(node->a, frame));
    return a > static_cast<uint64_t>(eval(node->b, frame));
}
int64_t run_ge_u(const Node *node, Frame &frame, uint8_t *) {
    const uint64_t a = static_cast<uint64_t>(eval(node->a, frame));
    return a >= static_cast<uint64_t>(eval(node->b, frame));
}
int64_t run_logic_and(const Node *node, Frame &frame, uint8_t *) {
    return eval(node->a, frame) != 0 && eval(node->b, frame) != 0;
}
int64_t run_logic_or(const Node *node, Frame &frame, uint8_t *) {
    return eval(node->a, frame) != 0 || eval(node->b, frame) != 0;
}
int64_t run_logic_not(const Node *node, Frame &frame, uint8_t *) {
    return eval(node->a, frame) == 0;
}
// u64(i64) and i64(u64) both require the sign bit clear.
int64_t run_to_u64(const Node *node, Frame &frame, uint8_t *) {
    const int64_t a = eval(node->a, frame);
    if (a < 0) {
        overflow(node);
    }
    return a;
}
int64_t run_to_u8_signed(const Node *node, Frame &frame, uint8_t *) {
    return byte_result(node, eval(node->a, frame));
}
int64_t run_to_u8_unsigned(const Node *node, Frame &frame, uint8_t *) {
    const uint64_t a = static_cast<uint64_t>(eval(node->a, frame));
    if (a > 255) {
        overflow(node);
    }
    return static_cast<int64_t>(a);
}

// ---- owners and spans

int64_t run_owner_ok(const Node *node, Frame &frame, uint8_t *) {
    return owner_at(node, place(node->a, frame))->ok;
}
int64_t run_owner_size(const Node *node, Frame &frame, uint8_t *) {
    return owner_at(node, place(node->a, frame))->count;
}
int64_t run_bytes_at(const Node *node, Frame &frame, uint8_t *) {
    const uint8_t *word = place(node->a, frame);
    const int64_t index = eval(node->b, frame);
    const Owner *owner = owner_at(node, word);
    if (!owner->ok || index < 0 || index >= owner->count) {
        trap(node, "owner index");
    }
    return owner->data[index];
}
int64_t run_bytes_set(const Node *node, Frame &frame, uint8_t *) {
    uint8_t *word = place(node->a, frame);
    const int64_t index = eval(node->b, frame);
    const int64_t value = eval(node->c, frame);
    Owner *owner = owner_at(node, word);
    if (!owner->ok || index < 0 || index >= owner->count) {
        return 0;
    }
    owner->data[index] = static_cast<uint8_t>(value);
    return 1;
}
int64_t run_bytes_resize(const Node *node, Frame &frame, uint8_t *) {
    uint8_t *word = place(node->a, frame);
    const int64_t count = eval(node->b, frame);
    return resize(owner_at(node, word), count, nullptr);
}
int64_t run_allocate_bytes(const Node *node, Frame &frame, uint8_t *) {
    return address(reinterpret_cast<const uint8_t *>(allocate(eval(node->a, frame), 1, nullptr)));
}
// The value is snapshotted after the index, then checked and copied.
int64_t run_values_set(const Node *node, Frame &frame, uint8_t *) {
    uint8_t *word = place(node->a, frame);
    const int64_t index = eval(node->b, frame);
    uint8_t *snapshot = frame.base + node->offset;
    eval_into(node->c, frame, snapshot);
    Owner *owner = owner_at(node, word);
    if (!owner->ok || index < 0 || index >= owner->count) {
        return 0;
    }
    std::memcpy(owner->data + index * owner->stride, snapshot, static_cast<size_t>(owner->stride));
    return 1;
}
int64_t run_values_resize(const Node *node, Frame &frame, uint8_t *) {
    uint8_t *word = place(node->a, frame);
    const int64_t count = eval(node->b, frame);
    uint8_t *fill = frame.base + node->offset;
    eval_into(node->c, frame, fill);
    return resize(owner_at(node, word), count, fill);
}
int64_t run_allocate_values(const Node *node, Frame &frame, uint8_t *) {
    const int64_t count = eval(node->a, frame);
    uint8_t *fill = frame.base + node->offset;
    eval_into(node->b, frame, fill);
    return address(reinterpret_cast<const uint8_t *>(allocate(count, node->value, fill)));
}
int64_t run_span_size(const Node *node, Frame &frame, uint8_t *) {
    return read8(place(node->a, frame) + 8);
}
const uint8_t *span_element(const Node *node, Frame &frame) {
    const uint8_t *span = place(node->a, frame);
    const int64_t index = eval(node->b, frame);
    if (index < 0 || index >= read8(span + 8)) {
        trap(node, "span index");
    }
    return reinterpret_cast<const uint8_t *>(read8(span)) + index * node->value;
}
int64_t run_span_at1(const Node *node, Frame &frame, uint8_t *) {
    return *span_element(node, frame);
}
// move(owner): the word moves and the source no longer holds it.
int64_t run_take(const Node *node, Frame &frame, uint8_t *) {
    uint8_t *word = place(node->a, frame);
    const int64_t value = read8(word);
    write8(word, 0);
    return value;
}

// ---- objects

int64_t run_copy(const Node *node, Frame &frame, uint8_t *destination) {
    std::memmove(destination, place(node->a, frame), static_cast<size_t>(node->value));
    return 0;
}
int64_t run_zero(const Node *node, Frame &, uint8_t *destination) {
    std::memset(destination, 0, static_cast<size_t>(node->value));
    return 0;
}
int64_t run_designated(const Node *node, Frame &frame, uint8_t *destination) {
    std::memset(destination, 0, static_cast<size_t>(node->value));
    pass_arguments(node->arguments, frame, destination);
    return 0;
}
int64_t run_values_at(const Node *node, Frame &frame, uint8_t *destination) {
    const uint8_t *word = place(node->a, frame);
    const int64_t index = eval(node->b, frame);
    const Owner *owner = owner_at(node, word);
    if (!owner->ok || index < 0 || index >= owner->count) {
        trap(node, "owner index");
    }
    std::memcpy(destination, owner->data + index * owner->stride, static_cast<size_t>(owner->stride));
    return 0;
}
int64_t run_span_at(const Node *node, Frame &frame, uint8_t *destination) {
    std::memcpy(destination, span_element(node, frame), static_cast<size_t>(node->value));
    return 0;
}
// A failed owner cannot be borrowed; an empty one gives an empty view.
int64_t run_borrow_owner(const Node *node, Frame &frame, uint8_t *destination) {
    const Owner *owner = owner_at(node, place(node->a, frame));
    if (!owner->ok) {
        trap(node, "borrow of a failed owner");
    }
    write8(destination, address(owner->data));
    write8(destination + 8, owner->count);
    return 0;
}
int64_t run_borrow_array(const Node *node, Frame &frame, uint8_t *destination) {
    write8(destination, address(place(node->a, frame)));
    write8(destination + 8, node->value);
    return 0;
}
int64_t run_subspan(const Node *node, Frame &frame, uint8_t *destination) {
    const uint8_t *span = place(node->a, frame);
    const int64_t offset = eval(node->b, frame);
    const int64_t count = eval(node->c, frame);
    const int64_t size = read8(span + 8);
    if (offset < 0 || offset > size || count < 0 || count > size - offset) {
        trap(node, "subspan bounds");
    }
    write8(destination, read8(span) + offset * node->value);
    write8(destination + 8, count);
    return 0;
}
int64_t run_literal_span(const Node *node, Frame &, uint8_t *destination) {
    write8(destination, address(node->data));
    write8(destination + 8, node->value);
    return 0;
}
int64_t run_literal_bytes(const Node *node, Frame &, uint8_t *destination) {
    std::memcpy(destination, node->data, static_cast<size_t>(node->value));
    return 0;
}
int64_t run_move_object(const Node *node, Frame &frame, uint8_t *destination) {
    uint8_t *source = place(node->a, frame);
    std::memmove(destination, source, static_cast<size_t>(node->value));
    for (const int64_t word : node->words) {
        write8(source + word, 0);
    }
    return 0;
}

// ---- places

int64_t run_local(const Node *node, Frame &frame, uint8_t *) {
    return address(frame.base + node->offset);
}
int64_t run_self(const Node *node, Frame &frame, uint8_t *) {
    return address(frame.self + node->offset);
}
int64_t run_reference(const Node *node, Frame &frame, uint8_t *) {
    return read8(frame.base + node->offset) + node->value;
}
int64_t run_field(const Node *node, Frame &frame, uint8_t *) {
    return address(place(node->a, frame) + node->offset);
}
int64_t run_element(const Node *node, Frame &frame, uint8_t *) {
    uint8_t *base = place(node->a, frame);
    const int64_t index = eval(node->b, frame);
    if (index < 0 || index >= node->offset) {
        trap(node, "array index");
    }
    return address(base + index * node->value);
}
int64_t run_temporary(const Node *node, Frame &frame, uint8_t *) {
    uint8_t *slot = frame.base + node->offset;
    eval_into(node->a, frame, slot);
    return address(slot);
}

// ---- statements

int64_t run_block(const Node *node, Frame &frame, uint8_t *) {
    for (const Node *child : node->list) {
        if (exec(child, frame) == Flow::returned) {
            return static_cast<int64_t>(Flow::returned);
        }
    }
    for (const int64_t word : node->words) {
        drop_word(frame.base + word);
    }
    return static_cast<int64_t>(Flow::normal);
}
int64_t run_init_scalar(const Node *node, Frame &frame, uint8_t *) {
    if (node->width == 1) {
        frame.base[node->offset] = static_cast<uint8_t>(eval(node->b, frame));
    } else {
        write8(frame.base + node->offset, eval(node->b, frame));
    }
    return static_cast<int64_t>(Flow::normal);
}
int64_t run_init_object(const Node *node, Frame &frame, uint8_t *) {
    eval_into(node->b, frame, frame.base + node->offset);
    return static_cast<int64_t>(Flow::normal);
}
// The target address first, then the value: an index is checked before the
// right-hand side runs.
int64_t run_store_scalar(const Node *node, Frame &frame, uint8_t *) {
    uint8_t *target = place(node->a, frame);
    const int64_t value = eval(node->b, frame);
    if (node->width == 1) {
        *target = static_cast<uint8_t>(value);
    } else {
        write8(target, value);
    }
    return static_cast<int64_t>(Flow::normal);
}
int64_t run_store_object(const Node *node, Frame &frame, uint8_t *) {
    uint8_t *target = place(node->a, frame);
    if (node->offset < 0) {
        eval_into(node->b, frame, target);
    } else {
        uint8_t *staged = frame.base + node->offset;
        eval_into(node->b, frame, staged);
        std::memcpy(target, staged, static_cast<size_t>(node->value));
    }
    return static_cast<int64_t>(Flow::normal);
}
int64_t run_branch(const Node *node, Frame &frame, uint8_t *) {
    if (eval(node->a, frame) != 0) {
        return static_cast<int64_t>(exec(node->b, frame));
    }
    return static_cast<int64_t>(node->c != nullptr ? exec(node->c, frame) : Flow::normal);
}
int64_t run_loop(const Node *node, Frame &frame, uint8_t *) {
    while (eval(node->a, frame) != 0) {
        if (exec(node->b, frame) == Flow::returned) {
            return static_cast<int64_t>(Flow::returned);
        }
    }
    return static_cast<int64_t>(Flow::normal);
}
int64_t run_return_scalar(const Node *node, Frame &frame, uint8_t *) {
    frame.value = eval(node->a, frame);
    return static_cast<int64_t>(Flow::returned);
}
int64_t run_return_object(const Node *node, Frame &frame, uint8_t *) {
    eval_into(node->a, frame, frame.result);
    return static_cast<int64_t>(Flow::returned);
}
int64_t run_evaluate(const Node *node, Frame &frame, uint8_t *) {
    eval(node->a, frame);
    return static_cast<int64_t>(Flow::normal);
}
int64_t run_evaluate_object(const Node *node, Frame &frame, uint8_t *) {
    eval_into(node->a, frame, frame.base + node->offset);
    return static_cast<int64_t>(Flow::normal);
}

// ---------------------------------------------------------------- lowering

enum class Cat : uint8_t {
    scalar, // evaluates to a value
    object, // evaluates into a destination
    place   // evaluates to an address
};

struct Value {
    Node *node = nullptr;
    Type *type = nullptr;
    Cat cat = Cat::scalar;
    bool copy = false; // a place standing for a copied result, never bound by reference
};

struct Local {
    Type *type;
    int64_t offset;
    bool reference;
};

struct Scope {
    std::vector<std::pair<std::string, Local>> names;
    std::vector<int64_t> owners;
};

struct Context {
    Function *function;
    Module *module;
    std::string space;
    ClassDecl *self;
    std::vector<Scope> scopes;
    int64_t frame = 0;
};

int64_t reserve(Context &context, int64_t size) {
    const int64_t offset = (context.frame + 7) / 8 * 8;
    context.frame = offset + std::max<int64_t>(size, 1);
    return offset;
}

const Local *find_local(const Context &context, const std::string &name) {
    for (auto scope = context.scopes.rbegin(); scope != context.scopes.rend(); ++scope) {
        for (auto entry = scope->names.rbegin(); entry != scope->names.rend(); ++entry) {
            if (entry->first == name) {
                return &entry->second;
            }
        }
    }
    return nullptr;
}

void add_local(Context &context, const std::string &name, const Local &local, const Loc &loc, bool parameter) {
    for (const auto &[declared, unused] : context.scopes.back().names) {
        if (declared == name) {
            fail(loc, "redeclared local " + name);
        }
    }
    context.scopes.back().names.emplace_back(name, local);
    if (!local.reference) {
        for (const int64_t owner : local.type->owners) {
            if (!parameter) {
                context.scopes.back().owners.push_back(local.offset + owner);
                context.function->entry_null.push_back(local.offset + owner);
            }
            context.function->exit_drop.push_back(local.offset + owner);
        }
    }
}

void signature(Function *function) {
    if (function->signed_up) {
        return;
    }
    for (const Param &param : function->params) {
        Type *type = resolve(param.type, function->module, function->space);
        Mode mode = param.type->reference ? Mode::reference : Mode::value;
        if (type->kind == K::files || type->kind == K::region) {
            mode = Mode::value;
        } else if (mode == Mode::value && param.type->constant) {
            fail(param.type->loc, "unsupported const value parameter");
        }
        function->param_types.push_back(type);
        function->modes.push_back(mode);
        // Parameters lead the frame, each at its own eight-byte aligned slot.
        const int64_t offset = (function->params_size + 7) / 8 * 8;
        function->param_offsets.push_back(offset);
        function->params_size = offset + std::max<int64_t>(mode == Mode::reference ? 8 : type->size, 1);
    }
    if (function->constructor) {
        function->object_size = class_type(function->owner)->size;
    } else {
        function->result_type = resolve(function->result, function->module, function->space);
        if (function->result_type->kind == K::region || function->result_type->kind == K::files) {
            fail(function->loc, "unsupported result type");
        }
    }
    function->signed_up = true;
}

Value lower(const Expr *expr, Context &context, Type *expected);
Type *probe_type(const Expr *expr, const Context &context, Type *expected);

// A scalar load from a place, fused with a local, receiver or field place.
Node *load(Node *place, Type *type) {
    const bool one = width(type) == 1;
    Node *node = nullptr;
    if (place->run == run_local) {
        node = make(one ? run_load_local1 : run_load_local8, place->loc);
        node->offset = place->offset;
    } else if (place->run == run_self) {
        node = make(one ? run_load_self1 : run_load_self8, place->loc);
        node->offset = place->offset;
    } else if (place->run == run_field) {
        node = make(one ? run_load1 : run_load8, place->loc);
        node->a = place->a;
        node->offset = place->offset;
    } else {
        node = make(one ? run_load1 : run_load8, place->loc);
        node->a = place;
    }
    return node;
}

// The place of a field at offset inside a place, folding the offset into a
// local, receiver, reference or field place.
Node *field_place(Node *place, int64_t offset) {
    const bool folds =
        place->run == run_local || place->run == run_self || place->run == run_reference || place->run == run_field;
    Node *node = make(folds ? place->run : run_field, place->loc);
    if (!folds) {
        node->a = place;
        node->offset = offset;
    } else if (place->run == run_reference) {
        node->offset = place->offset;
        node->value = place->value + offset;
    } else {
        node->a = place->a;
        node->offset = place->offset + offset;
    }
    return node;
}

Node *as_scalar(const Value &value, const Loc &loc) {
    if (!scalar(value.type)) {
        fail(loc, "expected a scalar, found " + value.type->name);
    }
    if (value.cat == Cat::place && !value.type->owners.empty()) {
        fail(loc, "an owner moves only by move()");
    }
    return value.cat == Cat::place ? load(value.node, value.type) : value.node;
}

Node *as_object(const Value &value, const Loc &loc) {
    if (scalar(value.type)) {
        fail(loc, "expected an object, found " + value.type->name);
    }
    if (value.cat != Cat::place) {
        return value.node;
    }
    if (!value.type->owners.empty()) {
        fail(loc, "an owner moves only by move()");
    }
    Node *node = make(run_copy, loc);
    node->a = value.node;
    node->value = value.type->size;
    return node;
}

Node *as_place(const Value &value, Context &context, const Loc &loc) {
    if (value.cat == Cat::place) {
        return value.node;
    }
    if (scalar(value.type)) {
        fail(loc, "expected a place");
    }
    if (!value.type->owners.empty()) {
        fail(loc, "unsupported temporary owner");
    }
    Node *node = make(run_temporary, loc);
    node->a = value.node;
    node->offset = reserve(context, value.type->size);
    return node;
}

void expect_type(const Value &value, const Type *type, const Loc &loc) {
    if (value.type != type) {
        fail(loc, "type mismatch: expected " + type->name + ", found " + value.type->name);
    }
}

Node *constant(int64_t value, const Loc &loc) {
    Node *node = make(run_constant, loc);
    node->value = value;
    return node;
}

// A value of the expected type, converting a string literal or {} as needed.
Value lower_as(const Expr *expr, Context &context, Type *type) {
    Value value = lower(expr, context, type);
    expect_type(value, type, expr->loc);
    return value;
}

// Lowers call arguments into the callee's parameter slots, after the first
// skip parameters (the HostFiles grant of a host binding call).
void arguments(
    Node *call, Function *callee, const std::vector<Expr *> &args, Context &context, const Loc &loc, size_t skip = 0) {
    signature(callee);
    if (args.size() + skip != callee->param_types.size()) {
        fail(loc, "argument count mismatch calling " + callee->name);
    }
    for (size_t at = 0; at < args.size(); ++at) {
        Type *type = callee->param_types[at + skip];
        Value value = lower_as(args[at], context, type);
        const int64_t offset = callee->param_offsets[at + skip];
        if (callee->modes[at + skip] == Mode::reference) {
            Node *place = value.copy ? as_place(Value{as_object(value, loc), type, Cat::object}, context, loc)
                                     : as_place(value, context, loc);
            call->arguments.push_back(Argument{place, offset, Pass::reference});
        } else if (scalar(type)) {
            call->arguments.push_back(
                Argument{as_scalar(value, loc), offset, width(type) == 1 ? Pass::scalar1 : Pass::scalar8});
        } else {
            call->arguments.push_back(Argument{as_object(value, loc), offset, Pass::object});
        }
    }
}

Value call_value(Node *call, Function *callee) {
    if (callee->constructor) {
        return Value{call, class_type(callee->owner), Cat::object};
    }
    return Value{call, callee->result_type, scalar(callee->result_type) ? Cat::scalar : Cat::object};
}

// Whether a method is `return field;` with no parameters: its call is lowered
// to the field's place, as a copy.
bool getter(Function *method) {
    if (method->getter == 0) {
        method->getter = 2;
        const Stmt *body = method->body;
        if (!method->constructor && method->params.empty() && body->body.size() == 1 &&
            body->body[0]->kind == Sk::ret && body->body[0]->value->kind == Ek::name &&
            body->body[0]->value->path.size() == 1 && !body->body[0]->value->global) {
            const int index = field_index(method->owner, body->body[0]->value->path[0]);
            if (index >= 0) {
                class_type(method->owner);
                signature(method);
                if (method->owner->field_types[index] == method->result_type) {
                    method->getter = 1;
                    method->getter_offset = method->owner->offsets[index];
                    method->getter_type = method->result_type;
                }
            }
        }
    }
    return method->getter == 1;
}

// Chooses among same-named callables by argument count, then exact types.
Function *choose(const std::vector<Function *> &candidates,
                 const std::vector<Expr *> &args,
                 Context &context,
                 const Loc &loc,
                 const std::string &name) {
    std::vector<Function *> fitting;
    for (Function *candidate : candidates) {
        if (candidate->params.size() == args.size()) {
            fitting.push_back(candidate);
        }
    }
    if (fitting.size() == 1) {
        return fitting[0];
    }
    if (fitting.empty()) {
        fail(loc, "no callable " + name + " takes " + std::to_string(args.size()) + " arguments");
    }
    // Overloads: compare the argument types (a probe lowering whose nodes are dropped).
    std::vector<Function *> exact;
    for (Function *candidate : fitting) {
        signature(candidate);
        bool same = true;
        for (size_t at = 0; at < args.size() && same; ++at) {
            if (args[at]->kind == Ek::string) {
                same = candidate->param_types[at]->kind == K::span;
                continue;
            }
            same = probe_type(args[at], context, candidate->param_types[at]) == candidate->param_types[at];
        }
        if (same) {
            exact.push_back(candidate);
        }
    }
    if (exact.size() != 1) {
        fail(loc, "ambiguous call to " + name);
    }
    return exact[0];
}

// The type an expression would have, lowered in a throwaway context.
Type *probe_type(const Expr *expr, const Context &context, Type *expected) {
    Context probe = context;
    Function scratch;
    probe.function = &scratch;
    return lower(expr, probe, expected).type;
}

std::vector<Function *> methods_named(const ClassDecl *decl, const std::string &name) {
    std::vector<Function *> result;
    for (Function *method : decl->methods) {
        if (method->name == name) {
            result.push_back(method);
        }
    }
    return result;
}

// A method without parameters whose body is `return E;` with a scalar E that
// needs no frame slots: E, lowered once, to run with the receiver as self.
Node *expression_body(Function *method) {
    if (method->inline_state == 0) {
        method->inline_state = 2;
        const Stmt *body = method->body;
        signature(method);
        if (!method->constructor && method->params.empty() && body->body.size() == 1 &&
            body->body[0]->kind == Sk::ret && scalar(method->result_type)) {
            Context context{method, method->module, method->space, method->owner, {}, 0};
            context.scopes.emplace_back();
            method->inline_state = 3; // in progress: a recursive use is a plain call
            const Value value = lower_as(body->body[0]->value, context, method->result_type);
            Node *node = as_scalar(value, body->body[0]->loc);
            method->inline_state = 2;
            if (context.frame == 0) {
                method->inline_body = node;
                method->inline_state = 1;
            }
        }
    }
    return method->inline_state == 1 ? method->inline_body : nullptr;
}

// A method call on a class value; a method that may write its receiver gets a
// copy when the receiver stands for a copied result.
Value method_call(const Value &object, const Expr *expr, Context &context) {
    const Loc &loc = expr->loc;
    Type *type = object.type;
    const std::vector<Function *> found = methods_named(type->object, expr->text);
    if (found.empty()) {
        fail(loc, "no method " + expr->text + " in " + type->name);
    }
    Function *method = choose(found, expr->arguments, context, loc, expr->text);
    Node *receiver = object.copy && !method->constant
                         ? as_place(Value{as_object(object, loc), type, Cat::object}, context, loc)
                         : as_place(object, context, loc);
    if (getter(method)) {
        const Value field{field_place(receiver, method->getter_offset), method->getter_type, Cat::place, true};
        return scalar(field.type) ? field : Value{as_object(field, loc), field.type, Cat::object};
    }
    if (Node *body = expression_body(method)) {
        Node *node = make(run_receiver_expression, loc);
        node->a = receiver;
        node->b = body;
        return Value{node, method->result_type, Cat::scalar};
    }
    Node *call = make(run_call, loc);
    call->function = method;
    call->a = receiver;
    arguments(call, method, expr->arguments, context, loc);
    return call_value(call, method);
}

Function *host_function(const std::string &name, const Loc &loc) {
    const auto module = modules.find("aurora.host");
    if (module != modules.end()) {
        for (Function *function : module->second->functions) {
            if (function->space == "host" && function->name == name) {
                return function;
            }
        }
    }
    fail(loc, "the runtime root lacks host::" + name);
}

// The Linux binding's primitives: name, operation number, parameter count.
struct Primitive {
    const char *name;
    int64_t operation;
    size_t count;
};
constexpr Primitive primitives[] = {
    {"load", 9, 1},
    {"store", 10, 2},
    {"load8", 11, 1},
    {"store8", 12, 2},
    {"system_open", 13, 4},
    {"system_chunk", 14, 2},
    {"system_write", 15, 3},
    {"system_rename", 16, 5},
    {"system_unlink", 17, 3},
    {"system_close", 18, 1},
    {"system_stat", 19, 2},
    {"system_identity", 20, 0},
};

Type *primitive_parameter(int64_t operation, size_t index) {
    if (operation == 12 && index == 1) {
        return &u8_type;
    }
    if (operation > 12 && operation < 20 && index == 0) {
        return &i64_type;
    }
    return &u64_type;
}

Type *chunk_type() {
    return class_type(spaces["builtin"]["HostChunk"][0].object);
}

Value files_call(Node *files, const Expr *expr, Context &context) {
    const Loc &loc = expr->loc;
    static const char *const public_operations[] = {"open_directory",
                                                    "open_beneath",
                                                    "read",
                                                    "create_output",
                                                    "write",
                                                    "commit",
                                                    "discard",
                                                    "print",
                                                    "close",
                                                    "open_file"};
    for (const char *name : public_operations) {
        if (expr->text == name) {
            Function *callee = host_function(std::string("files_") + name, loc);
            Node *call = make(run_call, loc);
            call->function = callee;
            signature(callee);
            if (callee->param_types.empty() || callee->param_types[0]->kind != K::files) {
                fail(loc, "invalid host binding");
            }
            call->arguments.push_back(Argument{files, callee->param_offsets[0], Pass::scalar8});
            arguments(call, callee, expr->arguments, context, loc, 1);
            return call_value(call, callee);
        }
    }
    for (const Primitive &primitive : primitives) {
        if (expr->text != primitive.name) {
            continue;
        }
        if (context.module->name != "aurora.host") {
            fail(loc, "HostFiles primitives belong to aurora.host");
        }
        if (expr->arguments.size() != primitive.count) {
            fail(loc, "argument count mismatch calling " + expr->text);
        }
        Node *node = make(primitive.operation == 14 ? run_chunk : run_primitive, loc);
        node->value = primitive.operation;
        node->a = files;
        for (size_t at = 0; at < primitive.count; ++at) {
            node->list.push_back(
                as_scalar(lower_as(expr->arguments[at], context, primitive_parameter(primitive.operation, at)), loc));
        }
        if (primitive.operation == 14) {
            return Value{node, chunk_type(), Cat::object};
        }
        Type *result = &i64_type;
        if (primitive.operation == 9 || primitive.operation == 10) {
            result = &u64_type;
        } else if (primitive.operation == 11 || primitive.operation == 12) {
            result = &u8_type;
        }
        return Value{node, result, Cat::scalar};
    }
    fail(loc, "unsupported HostFiles operation " + expr->text);
}

Value builtin_method(const Value &receiver, const Expr *expr, Context &context) {
    const Loc &loc = expr->loc;
    const std::string &name = expr->text;
    const std::vector<Expr *> &args = expr->arguments;
    Type *type = receiver.type;
    const auto arity = [&](size_t count) {
        if (args.size() != count) {
            fail(loc, "argument count mismatch calling " + name);
        }
    };
    const auto index = [&](size_t at) {
        return as_scalar(lower_as(args[at], context, &i64_type), loc);
    };
    if (type->kind == K::files) {
        return files_call(as_scalar(receiver, loc), expr, context);
    }
    if (type->kind == K::region) {
        if (name != "try_allocate" || args.empty() || args.size() > 2) {
            fail(loc, "unsupported ByteRegion operation " + name);
        }
        if (args.size() == 1) {
            Node *node = make(run_allocate_bytes, loc);
            node->a = index(0);
            return Value{node, &bytes_type, Cat::scalar};
        }
        Node *node = make(run_allocate_values, loc);
        node->a = index(0);
        const Value fill = lower(args[1], context, nullptr);
        node->b = as_object(fill, loc);
        node->value = fill.type->size;
        node->offset = reserve(context, fill.type->size);
        return Value{node, values_of(fill.type, loc), Cat::scalar};
    }
    if (receiver.cat != Cat::place || receiver.copy) {
        fail(loc, "unsupported temporary receiver of " + name);
    }
    Node *place = receiver.node;
    if (type->kind == K::bytes || type->kind == K::values) {
        const bool bytes = type->kind == K::bytes;
        Node *node = nullptr;
        if (name == "ok" || name == "size") {
            arity(0);
            node = make(name == "ok" ? run_owner_ok : run_owner_size, loc);
            node->a = place;
            return Value{node, name == "ok" ? &bool_type : &i64_type, Cat::scalar};
        }
        if (name == "at") {
            arity(1);
            node = make(bytes ? run_bytes_at : run_values_at, loc);
            node->a = place;
            node->b = index(0);
            node->value = bytes ? 1 : type->element->size;
            return Value{node, bytes ? &u8_type : type->element, bytes ? Cat::scalar : Cat::object};
        }
        if (name == "set") {
            arity(2);
            node = make(bytes ? run_bytes_set : run_values_set, loc);
            node->a = place;
            node->b = index(0);
            if (bytes) {
                node->c = as_scalar(lower_as(args[1], context, &u8_type), loc);
            } else {
                node->c = as_object(lower_as(args[1], context, type->element), loc);
                node->value = type->element->size;
                node->offset = reserve(context, type->element->size);
            }
            return Value{node, &bool_type, Cat::scalar};
        }
        if (name == "try_resize") {
            arity(bytes ? 1 : 2);
            node = make(bytes ? run_bytes_resize : run_values_resize, loc);
            node->a = place;
            node->b = index(0);
            if (!bytes) {
                node->c = as_object(lower_as(args[1], context, type->element), loc);
                node->value = type->element->size;
                node->offset = reserve(context, type->element->size);
            }
            return Value{node, &bool_type, Cat::scalar};
        }
        fail(loc, "unsupported owner operation " + name);
    }
    if (type->kind == K::span) {
        const bool bytes = type->element->kind == K::u8;
        if (name == "size") {
            arity(0);
            Node *node = make(run_span_size, loc);
            node->a = place;
            return Value{node, &i64_type, Cat::scalar};
        }
        if (name == "at") {
            arity(1);
            Node *node = make(bytes ? run_span_at1 : run_span_at, loc);
            node->a = place;
            node->b = index(0);
            node->value = type->element->size;
            return Value{node, type->element, bytes ? Cat::scalar : Cat::object};
        }
        if (name == "subspan") {
            arity(2);
            Node *node = make(run_subspan, loc);
            node->a = place;
            node->b = index(0);
            node->c = index(1);
            node->value = type->element->size;
            return Value{node, type, Cat::object};
        }
        fail(loc, "unsupported span operation " + name);
    }
    fail(loc, "no method " + name + " on " + type->name);
}

// move(name), borrow_bytes(name), borrow_values(name) and the conversions.
bool special_call(const Expr *expr, Context &context, Value &result) {
    if (expr->path.size() != 1 || expr->global) {
        return false;
    }
    const std::string &name = expr->path[0];
    const Loc &loc = expr->loc;
    const auto single = [&]() -> const Expr * {
        if (expr->arguments.size() != 1) {
            fail(loc, name + " takes one argument");
        }
        return expr->arguments[0];
    };
    if (name == "move") {
        const Expr *source = single();
        if (source->kind != Ek::name || source->path.size() != 1 || find_local(context, source->path[0]) == nullptr) {
            fail(loc, "move requires a named local");
        }
        const Value value = lower(source, context, nullptr);
        if (value.type->owners.empty()) {
            fail(loc, "unsupported move of a copied value");
        }
        if (scalar(value.type)) {
            Node *node = make(run_take, loc);
            node->a = value.node;
            result = Value{node, value.type, Cat::scalar};
        } else {
            Node *node = make(run_move_object, loc);
            node->a = value.node;
            node->value = value.type->size;
            node->words = value.type->owners;
            result = Value{node, value.type, Cat::object};
        }
        return true;
    }
    if (name == "borrow_bytes" || name == "borrow_values") {
        const Value value = lower(single(), context, nullptr);
        if (value.cat != Cat::place || value.copy) {
            fail(loc, name + " requires a named owner or array");
        }
        Node *node = nullptr;
        if (name == "borrow_bytes" && value.type->kind == K::bytes) {
            node = make(run_borrow_owner, loc);
            result = Value{node, span_of(&u8_type, loc), Cat::object};
        } else if (name == "borrow_bytes" && value.type->kind == K::array && value.type->element->kind == K::u8) {
            node = make(run_borrow_array, loc);
            node->value = value.type->count;
            result = Value{node, span_of(&u8_type, loc), Cat::object};
        } else if (name == "borrow_values" && value.type->kind == K::values) {
            node = make(run_borrow_owner, loc);
            node->value = value.type->element->size;
            result = Value{node, span_of(value.type->element, loc), Cat::object};
        } else {
            fail(loc, "invalid " + name + " operand");
        }
        node->a = value.node;
        return true;
    }
    if (name == "i64" || name == "u64" || name == "u8") {
        const Value value = lower(single(), context, nullptr);
        Node *operand = as_scalar(value, loc);
        const K from = value.type->kind;
        Run op = run_constant;
        Type *type = &i64_type;
        if (name == "i64" && from == K::u64) {
            op = run_to_u64;
        } else if (name == "u64" && from == K::i64) {
            op = run_to_u64;
            type = &u64_type;
        } else if (name == "u8" && from == K::i64) {
            op = run_to_u8_signed;
            type = &u8_type;
        } else if (name == "u8" && from == K::u64) {
            op = run_to_u8_unsigned;
            type = &u8_type;
        } else if ((name == "i64" || name == "u64") && from == K::u8) {
            result = Value{operand, name == "i64" ? &i64_type : &u64_type, Cat::scalar};
            return true;
        } else {
            fail(loc, "unsupported conversion to " + name + " from " + value.type->name);
        }
        Node *node = make(op, loc);
        node->a = operand;
        result = Value{node, type, Cat::scalar};
        return true;
    }
    return false;
}

Value construct(ClassDecl *decl, const Expr *expr, Context &context) {
    Type *type = class_type(decl);
    const Loc &loc = expr->loc;
    if (expr->kind == Ek::call) {
        Function *ctor = choose(decl->constructors, expr->arguments, context, loc, decl->name);
        Node *call = make(run_call, loc);
        call->function = ctor;
        arguments(call, ctor, expr->arguments, context, loc);
        return call_value(call, ctor);
    }
    // Braces build only classes without constructors: zeroed, or designated.
    if (!decl->constructors.empty()) {
        fail(loc, "unsupported braced construction of " + decl->name);
    }
    if (expr->fields.empty()) {
        Node *node = make(run_zero, loc);
        node->value = type->size;
        return Value{node, type, Cat::object};
    }
    // Designated: each named field in order, the rest zero.
    Node *node = make(run_designated, loc);
    node->value = type->size;
    int last = -1;
    for (size_t at = 0; at < expr->fields.size(); ++at) {
        const int index = field_index(decl, expr->fields[at]);
        if (index <= last) {
            fail(loc, "invalid designated field " + expr->fields[at]);
        }
        last = index;
        Type *field_type = decl->field_types[index];
        if (!field_type->owners.empty()) {
            fail(loc, "unsupported owner field initializer");
        }
        const Value value = lower_as(expr->arguments[at], context, field_type);
        const int64_t offset = decl->offsets[index];
        if (scalar(field_type)) {
            node->arguments.push_back(
                Argument{as_scalar(value, loc), offset, width(field_type) == 1 ? Pass::scalar1 : Pass::scalar8});
        } else {
            node->arguments.push_back(Argument{as_object(value, loc), offset, Pass::object});
        }
    }
    return Value{node, type, Cat::object};
}

Value lower_call(const Expr *expr, Context &context) {
    Value special;
    if (special_call(expr, context, special)) {
        return special;
    }
    const Loc &loc = expr->loc;
    // An unqualified name in a method may name a method of its class.
    if (expr->path.size() == 1 && !expr->global && context.self != nullptr) {
        const std::vector<Function *> found = methods_named(context.self, expr->path[0]);
        if (!found.empty()) {
            Expr method = *expr;
            method.kind = Ek::method;
            method.text = expr->path[0];
            return method_call(Value{make(run_self, loc), class_type(context.self), Cat::place}, &method, context);
        }
    }
    const std::vector<const Entity *> found =
        find(expr->path, expr->path.size(), expr->global, context.module, context.space);
    if (found.empty()) {
        fail(loc, "unknown callable " + spelled(expr->path, expr->path.size()));
    }
    if (found.size() == 1 && found[0]->kind == Entity::Kind::object) {
        return construct(found[0]->object, expr, context);
    }
    std::vector<Function *> functions;
    for (const Entity *entity : found) {
        if (entity->kind != Entity::Kind::function) {
            fail(loc, "ambiguous callable " + spelled(expr->path, expr->path.size()));
        }
        functions.push_back(entity->function);
    }
    Function *callee = choose(functions, expr->arguments, context, loc, spelled(expr->path, expr->path.size()));
    Node *call = make(run_call, loc);
    call->function = callee;
    arguments(call, callee, expr->arguments, context, loc);
    return call_value(call, callee);
}

Value lower_name(const Expr *expr, Context &context) {
    const Loc &loc = expr->loc;
    if (expr->path.size() == 1 && !expr->global) {
        const std::string &name = expr->path[0];
        if (const Local *local = find_local(context, name)) {
            Node *node = make(local->reference ? run_reference : run_local, loc);
            node->offset = local->offset;
            return Value{node, local->type, Cat::place};
        }
        if (context.self != nullptr) {
            const int index = field_index(context.self, name);
            if (index >= 0) {
                class_type(context.self);
                Node *node = make(run_self, loc);
                node->offset = context.self->offsets[index];
                return Value{node, context.self->field_types[index], Cat::place};
            }
        }
        fail(loc, "unknown name " + name);
    }
    // An enum case: Enum::case, qualified as needed.
    const size_t count = expr->path.size() - 1;
    const Entity *entity = find_type(expr->path, count, expr->global, context.module, context.space, loc);
    if (entity->kind != Entity::Kind::enumeration) {
        fail(loc, "unsupported qualified name " + spelled(expr->path, expr->path.size()));
    }
    const std::vector<std::string> &cases = entity->enumeration->cases;
    const auto found = std::find(cases.begin(), cases.end(), expr->path.back());
    if (found == cases.end()) {
        fail(loc, "unknown enum case " + spelled(expr->path, expr->path.size()));
    }
    return Value{constant(found - cases.begin(), loc), enum_type(entity->enumeration), Cat::scalar};
}

Value lower_binary(const Expr *expr, Context &context) {
    const Loc &loc = expr->loc;
    const std::string &op = expr->op;
    if (op == "&&" || op == "||") {
        Node *node = make(op == "&&" ? run_logic_and : run_logic_or, loc);
        node->a = as_scalar(lower_as(expr->a, context, &bool_type), loc);
        node->b = as_scalar(lower_as(expr->b, context, &bool_type), loc);
        return Value{node, &bool_type, Cat::scalar};
    }
    const Value left = lower(expr->a, context, nullptr);
    Node *a = as_scalar(left, loc);
    const bool shift = op == "<<" || op == ">>";
    const Value right = lower(expr->b, context, shift ? &i64_type : left.type);
    Node *b = as_scalar(right, loc);
    const K kind = left.type->kind;
    if (shift ? right.type != &i64_type : right.type != left.type) {
        fail(loc, "operand types of " + op + " differ: " + left.type->name + " and " + right.type->name);
    }
    Run code = run_constant;
    Type *type = left.type;
    const bool signed_kind = kind == K::i64;
    const bool unsigned_kind = kind == K::u64 || kind == K::u8;
    if (op == "==" || op == "!=") {
        if (kind == K::bytes || kind == K::values || kind == K::region || kind == K::files) {
            fail(loc, "unsupported comparison of " + left.type->name);
        }
        code = op == "==" ? run_eq : run_ne;
        type = &bool_type;
    } else if (op == "<" || op == "<=" || op == ">" || op == ">=") {
        if (!signed_kind && !unsigned_kind) {
            fail(loc, "unsupported ordering of " + left.type->name);
        }
        const int which = op == "<" ? 0 : op == "<=" ? 1 : op == ">" ? 2 : 3;
        static constexpr Run ordered[2][4] = {{run_lt_i, run_le_i, run_gt_i, run_ge_i},
                                              {run_lt_u, run_le_u, run_gt_u, run_ge_u}};
        code = ordered[signed_kind ? 0 : 1][which];
        type = &bool_type;
    } else if (signed_kind) {
        static const std::map<std::string, Run> table = {
            {"+", run_add_i}, {"-", run_sub_i}, {"*", run_mul_i}, {"/", run_div_i}, {"%", run_rem_i}};
        const auto found = table.find(op);
        if (found == table.end()) {
            fail(loc, "unsupported i64 operator " + op);
        }
        code = found->second;
    } else if (kind == K::u64) {
        static const std::map<std::string, Run> table = {{"+", run_add_u},
                                                         {"-", run_sub_u},
                                                         {"*", run_mul_u},
                                                         {"/", run_div_u},
                                                         {"%", run_rem_u},
                                                         {"&", run_and_u},
                                                         {"|", run_or_u},
                                                         {"^", run_xor_u},
                                                         {"<<", run_shl_u},
                                                         {">>", run_shr_u}};
        const auto found = table.find(op);
        if (found == table.end()) {
            fail(loc, "unsupported u64 operator " + op);
        }
        code = found->second;
    } else if (kind == K::u8) {
        static const std::map<std::string, Run> table = {{"+", run_add_b},
                                                         {"-", run_sub_b},
                                                         {"*", run_mul_b},
                                                         {"/", run_div_u},
                                                         {"%", run_rem_u},
                                                         {"&", run_and_u},
                                                         {"|", run_or_u},
                                                         {"^", run_xor_u},
                                                         {"<<", run_shl_b},
                                                         {">>", run_shr_b}};
        const auto found = table.find(op);
        if (found == table.end()) {
            fail(loc, "unsupported u8 operator " + op);
        }
        code = found->second;
    } else {
        fail(loc, "unsupported operator " + op + " on " + left.type->name);
    }
    Node *node = make(code, loc);
    node->a = a;
    node->b = b;
    return Value{node, type, Cat::scalar};
}

Value lower(const Expr *expr, Context &context, Type *expected) {
    const Loc &loc = expr->loc;
    switch (expr->kind) {
    case Ek::integer: {
        if (expr->suffix == Suffix::i64 && expr->value > static_cast<uint64_t>(INT64_MAX)) {
            fail(loc, "i64 literal out of range");
        }
        Type *type = expr->suffix == Suffix::u64 ? &u64_type : expr->suffix == Suffix::u8 ? &u8_type : &i64_type;
        return Value{constant(static_cast<int64_t>(expr->value), loc), type, Cat::scalar};
    }
    case Ek::boolean:
        return Value{constant(static_cast<int64_t>(expr->value), loc), &bool_type, Cat::scalar};
    case Ek::string: {
        if (expected != nullptr && expected->kind == K::span && expected->element->kind == K::u8) {
            Node *node = make(run_literal_span, loc);
            node->data = reinterpret_cast<const uint8_t *>(expr->text.data());
            node->value = static_cast<int64_t>(expr->text.size());
            return Value{node, expected, Cat::object};
        }
        if (expected != nullptr && expected->kind == K::array && expected->element->kind == K::u8 &&
            expected->count == static_cast<int64_t>(expr->text.size())) {
            Node *node = make(run_literal_bytes, loc);
            node->data = reinterpret_cast<const uint8_t *>(expr->text.data());
            node->value = static_cast<int64_t>(expr->text.size());
            return Value{node, expected, Cat::object};
        }
        fail(loc, "unsupported string literal use");
    }
    case Ek::name:
        return lower_name(expr, context);
    case Ek::unary: {
        if (expr->op == "-" && expr->a->kind == Ek::integer && expr->a->suffix == Suffix::i64 &&
            expr->a->value <= static_cast<uint64_t>(INT64_MAX) + 1) {
            return Value{constant(static_cast<int64_t>(0 - expr->a->value), loc), &i64_type, Cat::scalar};
        }
        const Value operand = lower(expr->a, context, nullptr);
        Run op = run_constant;
        if (expr->op == "!" && operand.type == &bool_type) {
            op = run_logic_not;
        } else if (expr->op == "-" && operand.type == &i64_type) {
            op = run_neg_i;
        } else if (expr->op == "~" && operand.type == &u64_type) {
            op = run_not_u;
        } else if (expr->op == "~" && operand.type == &u8_type) {
            op = run_not_b;
        } else {
            fail(loc, "unsupported unary " + expr->op + " on " + operand.type->name);
        }
        Node *node = make(op, loc);
        node->a = as_scalar(operand, loc);
        return Value{node, operand.type, Cat::scalar};
    }
    case Ek::binary:
        return lower_binary(expr, context);
    case Ek::call:
        return lower_call(expr, context);
    case Ek::construct: {
        if (expr->path.size() == 0) {
            fail(loc, "invalid construction");
        }
        const Entity *entity =
            find_type(expr->path, expr->path.size(), expr->global, context.module, context.space, loc);
        if (entity->kind != Entity::Kind::object) {
            fail(loc, "unsupported construction");
        }
        return construct(entity->object, expr, context);
    }
    case Ek::member: {
        const Value object = lower(expr->a, context, nullptr);
        if (object.type->kind != K::object) {
            fail(loc, "no field " + expr->text + " in " + object.type->name);
        }
        const int index = field_index(object.type->object, expr->text);
        if (index < 0) {
            fail(loc, "no field " + expr->text + " in " + object.type->name);
        }
        Node *place = as_place(object, context, loc);
        return Value{field_place(place, object.type->object->offsets[index]),
                     object.type->object->field_types[index],
                     Cat::place,
                     object.copy || object.cat != Cat::place};
    }
    case Ek::method: {
        const Value receiver = lower(expr->a, context, nullptr);
        if (receiver.type->kind == K::object) {
            return method_call(receiver, expr, context);
        }
        return builtin_method(receiver, expr, context);
    }
    case Ek::index: {
        const Value array = lower(expr->a, context, nullptr);
        if (array.type->kind != K::array) {
            fail(loc, "cannot index " + array.type->name);
        }
        Node *node = make(run_element, loc);
        node->a = as_place(array, context, loc);
        node->b = as_scalar(lower_as(expr->b, context, &i64_type), loc);
        node->value = array.type->element->size;
        node->offset = array.type->count;
        return Value{node, array.type->element, Cat::place, array.copy || array.cat != Cat::place};
    }
    }
    fail(loc, "unsupported expression");
}

Node *lower_statement(const Stmt *stmt, Context &context);

Node *lower_block(const Stmt *stmt, Context &context) {
    context.scopes.emplace_back();
    Node *node = make(run_block, stmt->loc);
    for (const Stmt *child : stmt->body) {
        node->list.push_back(lower_statement(child, context));
    }
    node->words.assign(context.scopes.back().owners.rbegin(), context.scopes.back().owners.rend());
    context.scopes.pop_back();
    if (node->list.size() == 1 && node->words.empty()) {
        return node->list[0];
    }
    return node;
}

// A nested statement that is not a block still gets its own scope.
Node *lower_nested(const Stmt *stmt, Context &context) {
    if (stmt->kind == Sk::block) {
        return lower_block(stmt, context);
    }
    Stmt wrapper{Sk::block, stmt->loc};
    wrapper.body.push_back(const_cast<Stmt *>(stmt));
    return lower_block(&wrapper, context);
}

Node *store(Node *place, const Value &value, Type *type, Context &context, const Loc &loc, bool fresh) {
    if (scalar(type)) {
        Node *node = make(run_store_scalar, loc);
        node->a = place;
        node->b = as_scalar(value, loc);
        node->width = width(type);
        return node;
    }
    Node *node = make(run_store_object, loc);
    node->a = place;
    node->b = as_object(value, loc);
    node->value = type->size;
    node->offset = fresh ? -1 : reserve(context, type->size);
    return node;
}

Node *lower_statement(const Stmt *stmt, Context &context) {
    const Loc &loc = stmt->loc;
    switch (stmt->kind) {
    case Sk::block:
        return lower_block(stmt, context);
    case Sk::local: {
        Type *type = resolve(stmt->type, context.module, context.space);
        if (stmt->type->reference || type->kind == K::region || type->kind == K::files) {
            fail(loc, "unsupported local type");
        }
        const Value value = lower_as(stmt->value, context, type);
        const int64_t offset = reserve(context, type->size);
        Node *node = nullptr;
        if (scalar(type)) {
            node = make(run_init_scalar, loc);
            node->b = as_scalar(value, loc);
            node->width = width(type);
        } else {
            node = make(run_init_object, loc);
            node->b = as_object(value, loc);
        }
        node->offset = offset;
        add_local(context, stmt->name, Local{type, offset, false}, loc, false);
        return node;
    }
    case Sk::ret: {
        Type *type = context.function->result_type;
        if (type == nullptr) {
            fail(loc, "return in a constructor");
        }
        const Value value = lower_as(stmt->value, context, type);
        Node *node = make(scalar(type) ? run_return_scalar : run_return_object, loc);
        node->a = scalar(type) ? as_scalar(value, loc) : as_object(value, loc);
        return node;
    }
    case Sk::branch: {
        Node *node = make(run_branch, loc);
        node->a = as_scalar(lower_as(stmt->value, context, &bool_type), loc);
        node->b = lower_nested(stmt->then, context);
        node->c = stmt->otherwise != nullptr ? lower_nested(stmt->otherwise, context) : nullptr;
        return node;
    }
    case Sk::loop: {
        Node *node = make(run_loop, loc);
        node->a = as_scalar(lower_as(stmt->value, context, &bool_type), loc);
        node->b = lower_nested(stmt->then, context);
        return node;
    }
    case Sk::expression: {
        const Value value = lower(stmt->value, context, nullptr);
        if (!value.type->owners.empty()) {
            fail(loc, "unsupported discarded owner");
        }
        if (scalar(value.type)) {
            Node *node = make(run_evaluate, loc);
            node->a = as_scalar(value, loc);
            return node;
        }
        Node *node = make(run_evaluate_object, loc);
        node->a = as_object(value, loc);
        node->offset = reserve(context, value.type->size);
        return node;
    }
    case Sk::assign: {
        const Value target = lower(stmt->target, context, nullptr);
        if (target.cat != Cat::place || target.copy) {
            fail(loc, "invalid assignment target");
        }
        if (!target.type->owners.empty()) {
            fail(loc, "unsupported owner assignment");
        }
        const Value value = lower_as(stmt->value, context, target.type);
        return store(target.node, value, target.type, context, loc, false);
    }
    }
    fail(loc, "unsupported statement");
}

// Lowers a function on its first call: parameters first in the frame, then
// locals and temporaries, each at its own offset.
void compile(Function *function) {
    if (function->code != nullptr) {
        return;
    }
    if (function->compiling) {
        fail(function->loc, "recursive lowering");
    }
    function->compiling = true;
    signature(function);
    Context context{function, function->module, function->space, function->owner, {}, 0};
    context.scopes.emplace_back();
    context.frame = function->params_size;
    for (size_t at = 0; at < function->params.size(); ++at) {
        add_local(context,
                  function->params[at].name,
                  Local{function->param_types[at], function->param_offsets[at], function->modes[at] == Mode::reference},
                  function->params[at].type->loc,
                  true);
    }
    Node *code = make(run_block, function->loc);
    if (function->constructor) {
        ClassDecl *decl = function->owner;
        class_type(decl);
        for (size_t field = 0; field < decl->fields.size(); ++field) {
            const Init *init = nullptr;
            for (const Init &candidate : function->inits) {
                if (candidate.field == decl->fields[field].name) {
                    if (init != nullptr) {
                        fail(candidate.loc, "repeated initializer of field " + candidate.field);
                    }
                    init = &candidate;
                }
            }
            Type *type = decl->field_types[field];
            if (init == nullptr) {
                fail(function->loc, "constructor leaves field " + decl->fields[field].name + " uninitialized");
            }
            if (init->braces) {
                if (!type->owners.empty() || (type->kind == K::object && !type->object->constructors.empty())) {
                    fail(init->loc, "unsupported braced field of a class with constructors");
                }
                continue; // the constructed value starts zeroed
            }
            Node *place = make(run_self, init->loc);
            place->offset = decl->offsets[field];
            Value value;
            if (init->arguments.size() == 1 &&
                (type->kind != K::object || probe_type(init->arguments[0], context, type) == type)) {
                value = lower_as(init->arguments[0], context, type);
            } else if (type->kind == K::object) {
                Expr call{Ek::call, init->loc};
                call.arguments = init->arguments;
                value = construct(type->object, &call, context);
            } else {
                fail(init->loc, "invalid field initializer");
            }
            code->list.push_back(store(place, value, type, context, init->loc, true));
        }
        for (const Init &init : function->inits) {
            if (field_index(decl, init.field) < 0) {
                fail(init.loc, "no field " + init.field);
            }
        }
    }
    code->list.push_back(lower_block(function->body, context));
    function->frame_size = (context.frame + 15) / 16 * 16;
    function->code = code->list.size() == 1 ? code->list[0] : code;
    function->compiling = false;
}

// ---------------------------------------------------------------- loading

Source *read_source(const std::string &path) {
    std::ifstream file(path, std::ios::binary);
    if (!file) {
        return nullptr;
    }
    std::ostringstream text;
    text << file.rdbuf();
    return new Source{path, text.str()};
}

[[noreturn]] void usage_error(const std::string &message) {
    std::fprintf(stderr, "aurora-seed: %s\n", message.c_str());
    std::_Exit(3);
}

struct Roots {
    std::vector<std::string> modules;
    std::string runtime;
};

// aurora.* names other than the compiler's own sources load only from the
// runtime root; others from exactly one module root.
std::string module_path(const std::string &name, const Roots &roots) {
    std::string relative = name;
    std::replace(relative.begin(), relative.end(), '.', '/');
    relative += ".au";
    const bool reserved =
        name.starts_with("aurora.") && !name.starts_with("aurora.compiler.") && !name.starts_with("aurora.tests.");
    if (reserved) {
        if (roots.runtime.empty()) {
            usage_error("module " + name + " needs --runtime-root");
        }
        return roots.runtime + "/" + relative;
    }
    std::string found;
    for (const std::string &root : roots.modules) {
        const std::string candidate = root + "/" + relative;
        if (::access(candidate.c_str(), R_OK) == 0) {
            if (!found.empty()) {
                usage_error("module " + name + " is ambiguous between module roots");
            }
            found = candidate;
        }
    }
    if (found.empty()) {
        usage_error("module " + name + " not found");
    }
    return found;
}

void load(Module *module, const Roots &roots) {
    modules[module->name] = module;
    for (const std::string &name : module->imports) {
        if (modules.contains(name)) {
            continue;
        }
        const std::string path = module_path(name, roots);
        Source *source = read_source(path);
        if (source == nullptr) {
            usage_error("cannot read " + path);
        }
        Module *imported = parse_module(source);
        if (imported->name != name) {
            fail(Loc{source, 1}, "module declares " + imported->name + ", imported as " + name);
        }
        load(imported, roots);
    }
}

void declare_module(Module *module) {
    for (Function *function : module->functions) {
        declare(function->space,
                function->name,
                Entity{Entity::Kind::function, function, nullptr, nullptr, module, function->exported});
    }
    for (ClassDecl *decl : module->classes) {
        declare(decl->space, decl->name, Entity{Entity::Kind::object, nullptr, decl, nullptr, module, decl->exported});
    }
    for (EnumDecl *decl : module->enums) {
        declare(
            decl->space, decl->name, Entity{Entity::Kind::enumeration, nullptr, nullptr, decl, module, decl->exported});
    }
}

Function *find_function(Module *module, const std::string &space, const std::string &name) {
    for (Function *function : module->functions) {
        if (function->space == space && function->name == name) {
            return function;
        }
    }
    return nullptr;
}

std::vector<Function *> all_functions() {
    std::vector<Function *> result;
    for (const auto &[name, module] : modules) {
        for (Function *function : module->functions) {
            result.push_back(function);
        }
        for (ClassDecl *decl : module->classes) {
            result.insert(result.end(), decl->methods.begin(), decl->methods.end());
            result.insert(result.end(), decl->constructors.begin(), decl->constructors.end());
        }
    }
    return result;
}

// With AURORA_SEED_PROFILE set, the most called functions are listed at exit
// or on SIGTERM, for work on the interpreter itself.
void profile() {
    std::vector<Function *> functions = all_functions();
    std::sort(functions.begin(), functions.end(), [](Function *a, Function *b) {
        return a->calls > b->calls;
    });
    for (size_t at = 0; at < functions.size() && at < 60; ++at) {
        std::fprintf(stderr,
                     "%12lld %s%s%s (%s:%d)\n",
                     static_cast<long long>(functions[at]->calls),
                     functions[at]->owner != nullptr ? functions[at]->owner->name.c_str() : "",
                     functions[at]->owner != nullptr ? "::" : "",
                     functions[at]->name.c_str(),
                     functions[at]->loc.source->path.c_str(),
                     functions[at]->loc.line);
    }
}

// Runs one function from the entry with scalar or span arguments.
int64_t run_entry(Function *function, const std::vector<int64_t> &scalars, const uint8_t *span) {
    compile(function);
    Node *call = make(run_call, function->loc);
    call->function = function;
    size_t next = 0;
    for (size_t at = 0; at < function->param_types.size(); ++at) {
        if (function->param_types[at]->kind == K::span) {
            Node *argument = make(run_literal_span, function->loc);
            argument->data = reinterpret_cast<const uint8_t *>(read8(span));
            argument->value = read8(span + 8);
            call->arguments.push_back(Argument{argument, function->param_offsets[at], Pass::object});
        } else {
            call->arguments.push_back(
                Argument{constant(scalars.at(next++), function->loc), function->param_offsets[at], Pass::scalar8});
        }
    }
    Frame frame{stack_top, nullptr, nullptr, 0};
    return invoke(call, frame, nullptr);
}

} // namespace
} // namespace seed

// aurora-seed [--module-root DIR]... [--runtime-root DIR] PROGRAM.au [ARGUMENT]...
// interprets the hosted program PROGRAM.au: its main receives HostFiles, a
// ByteRegion when it takes one, and PROGRAM.au and the arguments as its
// command line.
int main(int argc, char **argv) {
    using namespace seed;
    Roots roots;
    int at = 1;
    while (at + 1 < argc &&
           (std::strcmp(argv[at], "--module-root") == 0 || std::strcmp(argv[at], "--runtime-root") == 0)) {
        if (argv[at][2] == 'm') {
            roots.modules.emplace_back(argv[at + 1]);
        } else {
            roots.runtime = argv[at + 1];
        }
        at += 2;
    }
    if (at >= argc) {
        usage_error("usage: aurora-seed [--module-root DIR]... [--runtime-root DIR] PROGRAM.au [ARGUMENT]...");
    }
    Source *source = read_source(argv[at]);
    if (source == nullptr) {
        usage_error(std::string("cannot read ") + argv[at]);
    }
    declare_builtins();
    Module *root = parse_module(source);
    load(root, roots);
    for (const auto &[name, module] : modules) {
        declare_module(module);
    }
    Function *entry = find_function(root, "", "main");
    if (entry == nullptr) {
        usage_error("the program has no main");
    }
    signature(entry);
    const size_t count = entry->param_types.size();
    if ((count != 2 && count != 3) || entry->param_types[0]->kind != K::files ||
        (count == 3 && entry->param_types[1]->kind != K::region) || entry->param_types[count - 1]->kind != K::span ||
        entry->param_types[count - 1]->element->kind != K::u8 || entry->result_type->kind != K::enumeration ||
        entry->result_type->enumeration->name != "HostExit") {
        fail(entry->loc,
             "main must be main(builtin::HostFiles&, [builtin::ByteRegion,] builtin::span<const u8>) -> "
             "builtin::HostExit");
    }
    Module *host = modules.contains("aurora.host") ? modules["aurora.host"] : nullptr;
    Function *start = host != nullptr ? find_function(host, "host", "start") : nullptr;
    Function *finish = host != nullptr ? find_function(host, "host", "finish") : nullptr;
    if (start == nullptr || finish == nullptr) {
        usage_error("the program does not import a runtime root's aurora.host");
    }

    const bool profiling = std::getenv("AURORA_SEED_PROFILE") != nullptr;
    if (profiling) {
        std::signal(SIGTERM, [](int) {
            profile();
            std::_Exit(143);
        });
    }
    constexpr size_t stack_bytes = size_t{1} << 32;
    void *stack =
        mmap(nullptr, stack_bytes, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE, -1, 0);
    if (stack == MAP_FAILED) {
        usage_error("cannot map the interpreter stack");
    }
    stack_top = static_cast<uint8_t *>(stack);
    stack_end = stack_top + stack_bytes;
    alignas(16) static uint8_t session[session_bytes];
    const int64_t files = reinterpret_cast<int64_t>(session);

    std::string arguments;
    for (int argument = at; argument < argc; ++argument) {
        arguments.append(argv[argument]);
        arguments.push_back('\0');
    }
    uint8_t span[16];
    write8(span, reinterpret_cast<int64_t>(arguments.data()));
    write8(span + 8, static_cast<int64_t>(arguments.size()));

    int64_t status = 1;
    if (run_entry(start, {files}, nullptr) == 0) {
        std::vector<int64_t> scalars{files};
        if (count == 3) {
            scalars.push_back(0);
        }
        status = run_entry(entry, scalars, span);
        if (live_owners != 0) {
            std::fprintf(
                stderr, "aurora-seed: trap: %lld allocations outlived main\n", static_cast<long long>(live_owners));
            std::_Exit(4);
        }
    }
    run_entry(finish, {files}, nullptr);
    if (profiling) {
        profile();
    }
    std::_Exit(static_cast<int>(status));
}
