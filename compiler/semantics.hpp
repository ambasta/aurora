#pragma once
#include "ir_layout.hpp"
#include "ir_verify.hpp"
#include "syntax.hpp"
#include <algorithm>
#include <bit>
#include <limits>
#include <map>
#include <set>
namespace aurora {
class Local {
  public:
    std::string name;
    Type type;
    int offset = 0, owner = -1, shared = 0;
    int spanOrigin = -1;
    bool mut = false, live = true, exclusive = false;
};
class SemanticAnalyzer {
    std::vector<Function> sourceFunctions;
    std::vector<ClassDefinition> classes;
    std::vector<EnumDefinition> enums;
    std::map<std::string, std::size_t> enumNames;
    std::map<int, std::set<std::string>> reflectionAccess;
    std::map<std::string, std::size_t> classNames;
    std::map<int, Type> arrayTypes;
    std::map<std::string, std::vector<Type>> classLeaves;
    std::map<std::string, std::vector<ir::ClassField>> classShapes;
    std::map<std::string, ir::ClassStorage> classStorage;
    std::map<std::string, int> layoutStates;
    std::map<std::string, int> classDepths;
    static constexpr int maxFrameSlots = 8192;
    std::map<std::string, std::size_t> functions;
    std::vector<Local> locals;
    std::vector<std::map<std::string, int>> scopes;
    ir::Function lowered;
    int slot = 0, label = 0;
    Type result = Type::I64;
    const Function *currentFunction = nullptr;

    [[noreturn]] void fail(const Token &t, const std::string &m) {
        throw Error("line " + std::to_string(t.line) + ": " + m);
    }
    const ClassDefinition &classDefinition(const Type &type, const Token &token) {
        auto found = classNames.find(type.className);
        if (!type.isClass() || found == classNames.end())
            fail(token, "unknown class type '" + typeName(type) + "'");
        return classes[found->second];
    }
    std::int64_t typeId(const Type &type, const Token &token) {
        if (type.isArray()) {
            const int id =
                type.elementKind == TypeKind::U8 ? 3000000 + type.length
                : type.elementKind == TypeKind::U64
                    ? 2000000 + type.length
                    : 1000000 + type.length * 2 + (type.elementKind == TypeKind::Bool ? 1 : 0);
            arrayTypes[id] = type;
            return id;
        }
        if (type.isEnum()) {
            const auto found = enumNames.find(type.className);
            if (found == enumNames.end())
                fail(token, "unknown enum type '" + typeName(type) + "'");
            return enums[found->second].id;
        }
        if (type.isClass())
            return classDefinition(type, token).id;
        return static_cast<int>(type.kind) + 1;
    }
    std::int64_t classWords(const ClassDefinition &definition) const {
        return static_cast<std::int64_t>(classLeaves.at(definition.name).size());
    }
    void buildClassLayout(const std::string &name, int nesting = 1) {
        const auto found = classNames.find(name);
        if (found == classNames.end())
            throw Error("unknown nested class type '" + name + "'");
        auto &definition = classes[found->second];
        if (layoutStates[name] == 1)
            fail(definition.token, "recursive class containment is unsupported");
        if (nesting > 4)
            fail(definition.token, "class containment depth exceeds four");
        if (layoutStates[name] == 2)
            return;
        layoutStates[name] = 1;
        auto &leaves = classLeaves[name];
        classShapes.try_emplace(name);
        std::set<std::string> names;
        bool needsConstructor = false, composed = false;
        int depth = 1, logicalIndex = 0;
        for (auto &member : definition.fields) {
            if (!names.insert(member.token.text).second)
                fail(member.token, "duplicate class field");
            member.index = logicalIndex++;
            const int firstLeaf = static_cast<int>(leaves.size());
            if (member.type.isClass()) {
                composed = needsConstructor = true;
                buildClassLayout(member.type.className, nesting + 1);
                const auto &child = classLeaves.at(member.type.className);
                leaves.insert(leaves.end(), child.begin(), child.end());
                depth = std::max(depth, 1 + classDepths.at(member.type.className));
            } else if (member.type.isArray()) {
                needsConstructor = true;
                if (member.publicAccess || member.type.length < 1 || member.type.length > 64 ||
                    !scalar(Type(member.type.elementKind)) ||
                    !member.type.elementParameter.empty() || !member.type.lengthParameter.empty())
                    fail(member.token, "class array fields require private concrete scalar "
                                       "storage of length 1 to 64");
                typeId(member.type, member.token);
                leaves.insert(leaves.end(), member.type.length, Type(member.type.elementKind));
            } else {
                if (!scalarValue(member.type))
                    fail(member.token,
                         "class field must be concrete scalar, enum, class or private array");
                leaves.push_back(member.type);
            }
            classShapes[name].push_back(ir::ClassField{
                member.type.isArray() ? Type(member.type.elementKind) : member.type, firstLeaf,
                static_cast<int>(leaves.size()) - firstLeaf, member.type.isArray()});
            if (leaves.size() > maxFrameSlots)
                fail(definition.token, "class layout exceeds 65536 bytes");
            if (composed && leaves.size() > 64)
                fail(definition.token, "composed classes are limited to 64 scalar leaves");
        }
        if (composed && (depth > 4 || leaves.size() > 64))
            fail(definition.token, "composed class exceeds depth four or 64 scalar leaves");
        if (needsConstructor &&
            std::none_of(definition.methods.begin(), definition.methods.end(),
                         [](const Function &method) { return method.constructor; }))
            fail(definition.token, "array or class fields require a declared complete constructor");
        classDepths[name] = depth;
        layoutStates[name] = 2;
    }
    std::int64_t typeSize(const Type &type, const Token &token) {
        if (type.isArray()) {
            typeId(type, token);
            return type.length * ir::storageWidth(Type(type.elementKind));
        }
        if (type.isClass())
            return classStorage.at(classDefinition(type, token).name).sizeBytes;
        return type == Type::Bool || type == Type::U8 ? 1 : 8;
    }
    std::int64_t fieldCount(const Type &type, const Token &token) {
        if (type.isClass()) {
            const auto &fields = classDefinition(type, token).fields;
            return std::count_if(fields.begin(), fields.end(),
                                 [](const Field &field) { return field.publicAccess; });
        }
        return 0;
    }
    const Field &field(const Type &type, const Token &token) {
        const auto &definition = classDefinition(type, token);
        for (const auto &value : definition.fields)
            if (value.token.text == token.text) {
                if (!value.publicAccess &&
                    (!currentFunction || currentFunction->receiverClass != type.className))
                    fail(token, "private class field is inaccessible");
                requireVisibleType(value.type, token);
                return value;
            }
        fail(token, "unknown field '" + token.text + "' in " + typeName(type));
    }
    int fieldOffset(int local, const Field &value) {
        return locals.at(local).offset - value.offset;
    }
    void copyClass(int original, int destination, const ClassDefinition &) {
        emit(ir::CopyObject{offset(original), offset(destination)});
    }
    Type payloadType(const Type &type) { return type == Type::Own ? Type::I64 : type; }
    std::int64_t reflectedValue(ExpressionPtr expression) {
        if (expression->reflectedType.isSpan())
            fail(expression->token, "span capabilities are unavailable to reflection");
        if (expression->token.text == "type_id")
            return typeId(expression->reflectedType, expression->token);
        if (expression->token.text == "field_count")
            return fieldCount(expression->reflectedType, expression->token);
        return typeSize(expression->reflectedType, expression->token);
    }
    template <class Operation> void emit(Operation operation) {
        lowered.code.emplace_back(std::move(operation));
    }
    int fresh() { return label++; }
    int offset(int local) { return locals.at(local).offset; }
    int lookupLocal(const Token &t) const {
        for (auto i = scopes.rbegin(); i != scopes.rend(); ++i) {
            auto v = i->find(t.text);
            if (v != i->end())
                return v->second;
        }
        return -1;
    }
    int find(const Token &t) {
        const int local = lookupLocal(t);
        if (local < 0)
            fail(t, "unknown local '" + t.text + "'");
        return local;
    }
    const Field *receiverField(const Token &token) {
        if (!currentFunction || currentFunction->receiverClass.empty())
            return nullptr;
        const auto &definition = classDefinition(Type(currentFunction->receiverClass), token);
        for (const auto &member : definition.fields)
            if (member.token.text == token.text) {
                if (currentFunction->constructor)
                    fail(token, "constructor initializer cannot access receiver fields");
                return &member;
            }
        return nullptr;
    }
    int source(ExpressionPtr e) {
        if (e->op != "name")
            fail(e->token, "ownership operation requires a local name");
        int i = find(e->token);
        if (!locals[i].live)
            fail(e->token, "use after move of '" + e->token.text + "'");
        return i;
    }
    void arity(ExpressionPtr e, std::size_t n) {
        if (e->args.size() != n)
            fail(e->token, "wrong argument count for " + e->token.text);
    }
    void match(Type got, Type want, const Token &t) {
        if (got != want)
            fail(t, "expected " + typeName(want) + ", got " + typeName(got));
    }
    void push() { emit(ir::Push{}); }
    void pop() { emit(ir::Pop{}); }
    int add(const std::string &n, Type t, bool mut, const Token &tok, bool bind = true,
            bool begin = true) {
        if (bind && scopes.back().count(n))
            fail(tok, "duplicate local '" + n + "'");
        Local l;
        l.name = n;
        l.type = t;
        l.mut = mut;
        const auto needed = t.isSpan() ? 2
                            : (t.isClass() || t.isArray())
                                ? ir::roundedStorage(static_cast<int>(typeSize(t, tok))) / 8
                                : 1;
        if (needed > maxFrameSlots || slot > maxFrameSlots - needed)
            fail(tok, "function local stack frame exceeds 65536 bytes");
        slot += static_cast<int>(needed);
        l.offset = 8 * slot;
        if (t.isSpan()) {
            lowered.spanSlots.insert(l.offset);
        } else if (t.isClass()) {
            lowered.objectSlots[l.offset] = ir::ObjectSlot{t.className, mut};
            if (begin)
                emit(ir::BeginObject{l.offset});
            const auto &leaves = classLeaves.at(t.className);
            for (std::size_t index = 0; index < leaves.size(); ++index)
                lowered.slots[l.offset - classStorage.at(t.className).leafOffsets[index]] =
                    leaves[index];
        } else if (t.isArray()) {
            if (t.elementKind == TypeKind::U8) {
                lowered.arraySlots[l.offset] = t.length;
                emit(ir::BeginArray{l.offset});
            }
            for (int index = 0; index < t.length; ++index)
                lowered.slots[l.offset - index * ir::storageWidth(Type(t.elementKind))] =
                    Type(t.elementKind);
        } else
            lowered.slots[l.offset] = payloadType(t);
        locals.push_back(l);
        int i = static_cast<int>(locals.size()) - 1;
        if (bind)
            scopes.back()[n] = i;
        return i;
    }
    static bool byteArray(const Type &type) {
        return type.isArray() && type.elementKind == TypeKind::U8;
    }
    int acquireSpan(ExpressionPtr expression, const std::string &name = "", bool bind = false) {
        int parent = -1, origin = -1;
        if (expression->op == "call" && expression->token.text == "borrow_bytes") {
            arity(expression, 1);
            origin = source(expression->args[0]);
            if (!byteArray(locals[origin].type))
                fail(expression->token, "borrow_bytes requires a named local byte array");
        } else if (expression->op == "name") {
            parent = source(expression);
            if (!locals[parent].type.isSpan())
                fail(expression->token, "span initializer requires borrow_bytes or a live span");
            origin = locals[parent].spanOrigin;
        } else {
            fail(expression->token, "span initializer requires borrow_bytes or a live span");
        }
        const int destination = add(name, Type::ByteSpan, false, expression->token, bind);
        locals[destination].owner = parent;
        locals[destination].spanOrigin = origin;
        if (parent >= 0) {
            ++locals[parent].shared;
            emit(ir::ReborrowSpan{offset(parent), offset(destination)});
        } else {
            emit(ir::BorrowSpan{offset(origin), offset(destination)});
        }
        if (origin >= 0)
            ++locals[origin].shared;
        return destination;
    }
    void releaseSpan(int local, bool instructions) {
        auto &span = locals[local];
        if (span.shared)
            throw Error("span lifetime ended before a dependent reborrow");
        if (instructions)
            emit(ir::EndSpan{span.offset});
        if (span.owner >= 0)
            --locals[span.owner].shared;
        if (span.spanOrigin >= 0)
            --locals[span.spanOrigin].shared;
        span.live = false;
    }
    void endReturnBorrows() {
        // Emit in reverse creation order without mutating the analyzer's branch
        // state: returning paths do not constrain continuing siblings.
        for (std::size_t index = locals.size(); index > 0; --index)
            if (locals[index - 1].live && locals[index - 1].type.isSpan())
                emit(ir::EndSpan{locals[index - 1].offset});
        for (std::size_t index = locals.size(); index > 0; --index)
            if (locals[index - 1].live && byteArray(locals[index - 1].type))
                emit(ir::EndArray{locals[index - 1].offset});
    }
    class IndexedStorage {
      public:
        int local = -1;
        const Field *member = nullptr;
        Type type;
    };
    IndexedStorage checkedIndex(ExpressionPtr index) {
        if (index->args[0]->op != "name")
            fail(index->token,
                 "indexing requires an array local or implicit private receiver field");
        IndexedStorage storage;
        const auto &name = index->args[0]->token;
        if (lookupLocal(name) < 0)
            storage.member = receiverField(name);
        if (storage.member)
            storage.type = storage.member->type;
        else {
            storage.local = source(index->args[0]);
            storage.type = locals[storage.local].type;
        }
        if (!storage.type.isArray())
            fail(index->token, "indexing requires an array local or receiver field");
        match(expression(index->args[1]), Type::I64, index->token);
        if (storage.member)
            emit(ir::ReceiverBoundsGuard{storage.member->index});
        else
            emit(ir::BoundsGuard{offset(storage.local), storage.type.length,
                                 Type(storage.type.elementKind)});
        return storage;
    }
    const Function &method(const Type &type, const Token &token, bool constructor = false) {
        const auto &definition = classDefinition(type, token);
        for (const auto &candidate : definition.methods)
            if (candidate.constructor == constructor &&
                (constructor || candidate.token.text == token.text)) {
                if (!candidate.publicAccess &&
                    (!currentFunction || currentFunction->receiverClass != type.className))
                    fail(token, constructor ? "private constructor is inaccessible"
                                            : "private method is inaccessible");
                return candidate;
            }
        fail(token, constructor ? "class has no declared constructor" : "unknown class method");
    }
    void requireVisibleType(const Type &type, const Token &token) {
        if ((!type.isClass() && !type.isEnum()) || reflectionAccess.empty())
            return;
        if (currentFunction->templateTypeAuthority.contains(type.className))
            return;
        if (!currentFunction->receiverClass.empty()) {
            const auto &definition = classDefinition(Type(currentFunction->receiverClass), token);
            // A generated body retains only its fixed instance and exact nominal
            // arguments, not arbitrary names from the instantiating module.
            if (!definition.templateArguments.empty()) {
                if (type.isClass() && type.className == definition.name)
                    return;
                for (const auto &argument : definition.templateArguments)
                    if (argument.kind == TemplateArgumentKind::Type &&
                        (argument.type == TypeKind::Class || argument.type == TypeKind::Enum) &&
                        argument.type == type.kind && argument.className == type.className)
                        return;
            }
        }
        const auto found = reflectionAccess.find(currentFunction->moduleScope);
        if (found == reflectionAccess.end() || !found->second.contains(type.className))
            fail(token, "method signature type requires a direct visible import");
    }
    Type callMethod(ExpressionPtr value, const StatementPtr &resultBinding = nullptr) {
        const bool implicit = value->op == "implicit_method_call";
        if (implicit && lookupLocal(value->token) >= 0)
            fail(value->token, "local binding shadows method and is not callable");
        int receiver = -1;
        if (!implicit) {
            if (value->args[0]->op != "name")
                fail(value->token, "method receiver requires a class local");
            receiver = source(value->args[0]);
        }
        const auto type = implicit ? Type(currentFunction->receiverClass) : locals[receiver].type;
        if (type.isSpan()) {
            if (resultBinding || implicit)
                fail(value->token, "span operation requires a named live span");
            if (value->token.text == "size") {
                if (value->args.size() != 1)
                    fail(value->token, "span size expects no arguments");
                emit(ir::SpanLength{offset(receiver)});
                return Type::I64;
            }
            if (value->token.text == "at") {
                if (value->args.size() != 2)
                    fail(value->token, "span at expects one index");
                match(expression(value->args[1]), Type::I64, value->token);
                emit(ir::SpanLoad{offset(receiver)});
                return Type::U8;
            }
            fail(value->token, "span supports only readonly size and at operations");
        }
        const auto &callee = method(type, value->token);
        requireVisibleType(callee.result, value->token);
        for (const auto &parameter : callee.params)
            requireVisibleType(parameter.type, value->token);
        if (callee.result.isClass() && !resultBinding)
            fail(value->token, "class-returning method requires a typed local initializer");
        if (resultBinding)
            match(callee.result, resultBinding->type, value->token);
        const bool mutableReceiver =
            implicit ? !currentFunction->receiverConst : locals[receiver].mut;
        if (!callee.receiverConst && !mutableReceiver)
            fail(value->token, "mutable method requires a mutable receiver");
        const std::size_t first = implicit ? 0 : 1;
        if (value->args.size() - first != callee.params.size())
            fail(value->token, "wrong argument count for method");
        // Evaluate scalar arguments before acquiring the synchronous receiver
        // capability.
        for (std::size_t index = 0; index < callee.params.size(); ++index) {
            match(expression(value->args[index + first]), callee.params[index].type, value->token);
            push();
        }
        int destination = 0;
        if (resultBinding)
            destination = offset(add(resultBinding->name, resultBinding->type,
                                     resultBinding->mutableValue, resultBinding->token));
        emit(ir::MethodCall{callee.name, implicit ? 0 : offset(receiver), {}, destination});
        return callee.result;
    }
    Type callFunction(ExpressionPtr expression, const Function &callee,
                      const StatementPtr &resultBinding = nullptr) {
        if (callee.result.isClass() && !resultBinding)
            fail(expression->token, "class-returning call requires a typed local initializer");
        if (resultBinding)
            match(callee.result, resultBinding->type, expression->token);
        arity(expression, callee.params.size());
        std::vector<int> arguments(callee.params.size(), 0);
        std::vector<int> spanArguments(callee.params.size(), 0), spanBorrows;
        std::vector<int> snapshots;
        bool aggregate = callee.result.isClass();
        for (std::size_t index = 0; index < callee.params.size(); ++index) {
            const auto &type = callee.params[index].type;
            const auto &argument = expression->args[index];
            if (type.isSpan()) {
                aggregate = true;
                const int borrowed = acquireSpan(argument);
                spanArguments[index] = offset(borrowed);
                spanBorrows.push_back(borrowed);
            } else if (type.isClass()) {
                aggregate = true;
                if (argument->op != "name")
                    fail(argument->token, "class argument requires a complete local name");
                const int original = source(argument);
                match(locals[original].type, type, argument->token);
                const int snapshot = add("", type, false, argument->token, false);
                copyClass(original, snapshot, classDefinition(type, argument->token));
                arguments[index] = offset(snapshot);
                snapshots.push_back(offset(snapshot));
            } else {
                match(this->expression(argument), type, argument->token);
                push();
            }
        }
        int destination = 0;
        if (resultBinding)
            destination = offset(add(resultBinding->name, resultBinding->type,
                                     resultBinding->mutableValue, resultBinding->token));
        if (aggregate)
            emit(ir::AggregateCall{callee.name, arguments, destination, spanArguments});
        else
            emit(ir::Call{callee.name});
        for (int snapshot : snapshots)
            emit(ir::EndObject{snapshot});
        for (auto it = spanBorrows.rbegin(); it != spanBorrows.rend(); ++it)
            releaseSpan(*it, true);
        return callee.result;
    }
    ir::Constant literal(const Token &token) {
        const bool byteValue = token.text.ends_with("u8");
        const bool unsignedValue = byteValue || token.text.ends_with("u64");
        const auto suffixLength = byteValue ? 2 : unsignedValue ? 3 : 0;
        const auto digits = token.text.substr(0, token.text.size() - suffixLength);
        try {
            if (digits.empty() || !std::all_of(digits.begin(), digits.end(), [](unsigned char c) {
                    return c >= '0' && c <= '9';
                }))
                fail(token, "integer literal out of range or invalid suffix");
            std::size_t used = 0;
            const auto value = std::stoull(digits, &used);
            if (used != digits.size() || (byteValue && value > 255) ||
                (!unsignedValue &&
                 value > static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max())))
                fail(token, "integer literal out of range");
            return {std::bit_cast<std::int64_t>(static_cast<std::uint64_t>(value)),
                    byteValue       ? Type::U8
                    : unsignedValue ? Type::U64
                                    : Type::I64};
        } catch (const std::exception &) {
            fail(token, "integer literal out of range or invalid suffix");
        }
    }
    Type expression(ExpressionPtr e) {
        const auto &n = e->resolvedName.empty() ? e->token.text : e->resolvedName;
        if (e->op == "enum_case") {
            const auto found = enumNames.find(e->reflectedType.className);
            if (!e->reflectedType.isEnum() || found == enumNames.end() || e->enumOrdinal < 0 ||
                static_cast<std::size_t>(e->enumOrdinal) >= enums[found->second].cases.size())
                fail(e->token, "unknown enum case");
            emit(ir::EnumConstant{e->reflectedType, e->enumOrdinal});
            return e->reflectedType;
        }
        if (e->op == "number") {
            const auto value = literal(e->token);
            emit(ir::Constant{value.value, value.type});
            return value.type;
        }
        if (e->op == "bool") {
            emit(ir::Constant{n == "true" ? 1 : 0, Type::Bool});
            return Type::Bool;
        }
        if (e->op == "index") {
            const auto storage = checkedIndex(e);
            if (storage.member)
                emit(ir::ReceiverIndexLoad{storage.member->index});
            else
                emit(ir::IndexLoad{offset(storage.local), storage.type.length,
                                   Type(storage.type.elementKind)});
            return Type(storage.type.elementKind);
        }
        if (e->op == "array_literal")
            fail(e->token, "array literals require a typed local initializer");
        if (e->op == "member") {
            if (e->args[0]->op != "name")
                fail(e->token, "field access currently requires a class local");
            int local = source(e->args[0]);
            const auto &member = field(locals[local].type, e->token);
            if (member.type.isArray() || member.type.isClass())
                fail(e->token,
                     "aggregate fields require a fresh typed class projection or checked indexing");
            emit(ir::Load{fieldOffset(local, member), member.type});
            return member.type;
        }
        if (e->op == "method_call" || e->op == "implicit_method_call")
            return callMethod(e);
        if (e->op == "construct" || e->op == "constructor_call")
            fail(e->token, "class construction requires a typed local initializer");
        if (e->op == "name") {
            if (lookupLocal(e->token) < 0)
                if (const auto *member = receiverField(e->token)) {
                    if (member->type.isArray() || member->type.isClass())
                        fail(e->token, "aggregate fields require a fresh typed class projection or "
                                       "checked indexing");
                    emit(ir::ReceiverLoad{member->index, member->type});
                    return member->type;
                }
            int i = source(e);
            if (locals[i].type.isArray())
                fail(e->token, "array values are only supported in local initializers "
                               "and indexing");
            if (locals[i].type.isClass())
                fail(e->token, "class values are only supported in local initializers "
                               "and field accesses");
            if (!scalarValue(locals[i].type))
                fail(e->token, "owned values cannot be implicitly copied; use move, "
                               "read, or borrow");
            if (locals[i].type.isSpan())
                fail(e->token, "span capability cannot be used as a scalar value");
            emit(ir::Load{offset(i), payloadType(locals[i].type)});
            return locals[i].type;
        }
        if (e->op == "unary") {
            // Recognize the minimum signed literal before range-checking its positive
            // magnitude.
            if (n == "-" && e->args[0]->op == "number" &&
                !e->args[0]->token.text.ends_with("u64") &&
                !e->args[0]->token.text.ends_with("u8")) {
                try {
                    std::size_t used = 0;
                    if (std::stoull(e->args[0]->token.text, &used) == (1ULL << 63) &&
                        used == e->args[0]->token.text.size()) {
                        emit(ir::Constant{std::numeric_limits<std::int64_t>::min(), Type::I64});
                        return Type::I64;
                    }
                } catch (const std::exception &) {
                    fail(e->token, "integer literal out of range");
                }
            }
            auto t = expression(e->args[0]);
            if (n == "~") {
                if (t != Type::U64 && t != Type::U8)
                    fail(e->token, "expected u64 or u8 bitwise operand");
            } else
                match(t, n == "!" ? Type::Bool : Type::I64, e->token);
            emit(ir::UnaryValue{n == "!"   ? ir::Unary::LogicalNot
                                : n == "~" ? ir::Unary::BitNot
                                           : ir::Unary::CheckedNegate,
                                t});
            return t;
        }
        if (e->op == "binary") {
            const auto left = expression(e->args[0]);
            push();
            const auto right = expression(e->args[1]);
            if (n == "<<" || n == ">>") {
                if (left != Type::U64 && left != Type::U8)
                    fail(e->token, "expected u64 or u8 shift operand");
                match(right, Type::I64, e->token);
                emit(ir::BinaryValue{n == "<<" ? ir::Binary::ShiftLeft : ir::Binary::ShiftRight,
                                     left});
                return left;
            }
            match(right, left, e->token);
            static const std::map<std::string, ir::Binary> operations = {
                {"+", ir::Binary::CheckedAdd},
                {"-", ir::Binary::CheckedSubtract},
                {"*", ir::Binary::CheckedMultiply},
                {"/", ir::Binary::CheckedDivide},
                {"%", ir::Binary::CheckedRemainder},
                {"&", ir::Binary::BitAnd},
                {"|", ir::Binary::BitOr},
                {"^", ir::Binary::BitXor}};
            if (operations.contains(n)) {
                if (n == "&" || n == "|" || n == "^") {
                    if (left != Type::U64 && left != Type::U8)
                        fail(e->token, "expected u64 or u8 bitwise operands");
                } else if (left != Type::I64 && left != Type::U64 && left != Type::U8)
                    fail(e->token, "expected i64, u64 or u8 arithmetic operands");
                emit(ir::BinaryValue{operations.at(n), left});
                return left;
            }
            if (n != "==" && n != "!=" && left != Type::I64 && left != Type::U64 &&
                left != Type::U8)
                fail(e->token, "expected i64, u64 or u8 ordered comparison operands");
            static const std::map<std::string, ir::Comparison> comparisons = {
                {"==", ir::Comparison::Equal},     {"!=", ir::Comparison::NotEqual},
                {"<", ir::Comparison::Less},       {">", ir::Comparison::Greater},
                {"<=", ir::Comparison::LessEqual}, {">=", ir::Comparison::GreaterEqual}};
            emit(ir::Compare{comparisons.at(n), left});
            return Type::Bool;
        }
        if (e->op != "call")
            fail(e->token, "invalid expression");
        if (n == "borrow_bytes")
            fail(e->token, "borrow_bytes requires a span binding or span argument");
        if (n == "size_of" || n == "type_id" || n == "field_count") {
            emit(ir::Constant{reflectedValue(e), Type::I64});
            return Type::I64;
        }
        if (n == "u64" || n == "i64" || n == "u8") {
            arity(e, 1);
            const auto sourceType = expression(e->args[0]);
            const auto resultType = n == "u64" ? Type::U64 : n == "u8" ? Type::U8 : Type::I64;
            if ((sourceType != Type::I64 && sourceType != Type::U64 && sourceType != Type::U8) ||
                sourceType == resultType)
                fail(e->token, "expected distinct i64, u64 or u8 conversion types");
            emit(ir::Convert{sourceType, resultType});
            return resultType;
        }
        if (n == "len") {
            arity(e, 1);
            if (e->args[0]->op != "name")
                fail(e->token, "len requires an array local or receiver field");
            const Field *member =
                lookupLocal(e->args[0]->token) < 0 ? receiverField(e->args[0]->token) : nullptr;
            const Type type = member ? member->type : locals[source(e->args[0])].type;
            if (!type.isArray())
                fail(e->token, "len requires an array local or receiver field");
            emit(ir::Constant{type.length, Type::I64});
            return Type::I64;
        }
        if (n == "read") {
            arity(e, 1);
            int i = source(e->args[0]);
            auto t = locals[i].type;
            if (t != Type::Own && t != Type::Ref && t != Type::MutRef)
                fail(e->token, "read requires own, ref, or mutref");
            if (t == Type::Own && locals[i].exclusive)
                fail(e->token, "owner is exclusively borrowed");
            if (t != Type::Own)
                i = locals[i].owner;
            emit(ir::Load{offset(i), payloadType(locals[i].type)});
            return Type::I64;
        }
        if (n == "write") {
            arity(e, 2);
            int i = source(e->args[0]);
            match(locals[i].type, Type::MutRef, e->token);
            if (!locals[i].mut)
                fail(e->token, "write requires a non-const mutable reference binding");
            auto t = expression(e->args[1]);
            match(t, Type::I64, e->token);
            emit(ir::Store{offset(locals[i].owner), Type::I64});
            return Type::I64;
        }
        if (n == "reflect_size" || n == "reflect_field_count") {
            arity(e, 1);
            match(expression(e->args[0]), Type::I64, e->token);
            emit(ir::MetadataQuery{n == "reflect_size" ? ir::Query::Size
                                                       : ir::Query::PublicFieldCount,
                                   lowered.moduleScope});
            return Type::I64;
        }
        if (n == "own" || n == "move" || n == "borrow" || n == "borrow_mut")
            fail(e->token, "ownership constructors are only supported in typed local "
                           "initializers");
        auto f = functions.find(n);
        if (f == functions.end())
            fail(e->token, "unknown function '" + n + "'");
        return callFunction(e, sourceFunctions[f->second]);
    }
    ir::Constant constant(ExpressionPtr e) {
        const auto &name = e->token.text;
        if (e->op == "bool")
            return {name == "true", Type::Bool};
        if (e->op == "enum_case")
            return {e->enumOrdinal, e->reflectedType};
        if (e->op == "number")
            return literal(e->token);
        if (e->op == "call" && (name == "size_of" || name == "type_id" || name == "field_count"))
            return {reflectedValue(e), Type::I64};
        if (e->op == "binary") {
            const auto left = constant(e->args[0]), right = constant(e->args[1]);
            match(right.type, left.type, e->token);
            auto compare = [&](auto a, auto b) -> bool {
                if (name == "==")
                    return a == b;
                if (name == "!=")
                    return a != b;
                if (name == "<")
                    return a < b;
                if (name == ">")
                    return a > b;
                if (name == "<=")
                    return a <= b;
                if (name == ">=")
                    return a >= b;
                fail(e->token,
                     "static_assert supports literals, reflection, comparisons, and ! only");
            };
            const bool result = left.type == Type::U64
                                    ? compare(std::bit_cast<std::uint64_t>(left.value),
                                              std::bit_cast<std::uint64_t>(right.value))
                                    : compare(left.value, right.value);
            return {result, Type::Bool};
        }
        if (e->op == "unary" && name == "!") {
            const auto operand = constant(e->args[0]);
            match(operand.type, Type::Bool, e->token);
            return {!operand.value, Type::Bool};
        }
        fail(e->token, "static_assert supports literals, reflection, comparisons, and ! only");
    }
    bool block(const std::vector<StatementPtr> &body) {
        scopes.emplace_back();
        bool terminal = false;
        for (auto s : body) {
            if (terminal)
                fail(s->token, "unreachable statement");
            terminal = statement(s);
        }
        std::vector<int> leaving;
        for (const auto &[name, local] : scopes.back()) {
            (void)name;
            leaving.push_back(local);
        }
        std::sort(leaving.rbegin(), leaving.rend());
        for (int local : leaving) {
            auto &l = locals[local];
            if (l.type.isSpan()) {
                releaseSpan(local, !terminal);
                continue;
            }
            if (byteArray(l.type)) {
                if (l.shared)
                    fail(Token(l.name, 0), "byte array lifetime ends while borrowed");
                if (!terminal)
                    emit(ir::EndArray{l.offset});
                l.live = false;
            }
            if (l.type == Type::Ref)
                --locals[l.owner].shared;
            if (l.type == Type::MutRef)
                locals[l.owner].exclusive = false;
            if (l.type.isClass() && !terminal)
                emit(ir::EndObject{l.offset});
        }
        scopes.pop_back();
        return terminal;
    }
    void initializeClass(StatementPtr statement) {
        const auto &definition = classDefinition(statement->type, statement->token);
        const auto expression = statement->expr;
        if (expression->op == "method_call" || expression->op == "implicit_method_call") {
            callMethod(expression, statement);
            return;
        }
        if (expression->op == "member" ||
            (expression->op == "name" && lookupLocal(expression->token) < 0)) {
            int original = 0;
            const Field *member = nullptr;
            if (expression->op == "member") {
                if (expression->args[0]->op != "name")
                    fail(expression->token, "class projection requires a named local receiver");
                const int local = source(expression->args[0]);
                original = offset(local);
                member = &field(locals[local].type, expression->token);
            } else {
                member = receiverField(expression->token);
                if (!member)
                    fail(expression->token, "class projection requires a class field");
            }
            match(member->type, statement->type, expression->token);
            const int destination =
                add(statement->name, statement->type, statement->mutableValue, statement->token);
            emit(ir::ObjectFieldCopy{original, member->index, offset(destination)});
            return;
        }
        if (expression->op == "name") {
            const int original = source(expression);
            match(locals[original].type, statement->type, expression->token);
            const int destination =
                add(statement->name, statement->type, statement->mutableValue, statement->token);
            copyClass(original, destination, definition);
            return;
        }
        if (expression->op == "call") {
            const auto found = functions.find(expression->resolvedName);
            if (found == functions.end())
                fail(expression->token, "class initializer requires a class-returning function");
            callFunction(expression, sourceFunctions[found->second], statement);
            return;
        }
        if (expression->op == "constructor_call") {
            match(expression->reflectedType, statement->type, expression->token);
            const auto &constructor = method(statement->type, expression->token, true);
            arity(expression, constructor.params.size());
            std::vector<int> arguments(constructor.params.size(), 0), snapshots;
            bool aggregate = false;
            for (std::size_t index = 0; index < constructor.params.size(); ++index) {
                const auto &type = constructor.params[index].type;
                const auto &argument = expression->args[index];
                if (type.isClass()) {
                    aggregate = true;
                    const int original = source(argument);
                    match(locals[original].type, type, argument->token);
                    const int snapshot = add("", type, false, argument->token, false);
                    copyClass(original, snapshot, classDefinition(type, argument->token));
                    arguments[index] = offset(snapshot);
                    snapshots.push_back(offset(snapshot));
                } else {
                    match(this->expression(argument), type, expression->token);
                    push();
                }
            }
            const int destination =
                add(statement->name, statement->type, statement->mutableValue, statement->token);
            emit(ir::MethodCall{constructor.name, offset(destination),
                                aggregate ? arguments : std::vector<int>{}});
            for (const int snapshot : snapshots)
                emit(ir::EndObject{snapshot});
            return;
        }
        if (std::any_of(definition.methods.begin(), definition.methods.end(),
                        [](const Function &method) { return method.constructor; }))
            fail(expression->token, "constructor-bearing class rejects designated initialization");
        if (std::any_of(definition.fields.begin(), definition.fields.end(),
                        [](const Field &field) { return !field.publicAccess; }))
            fail(statement->token, "class construction requires public fields; private "
                                   "construction requires a declared constructor");
        if (expression->op != "construct")
            fail(expression->token, "class local requires named-field construction "
                                    "or same-type class copy");
        match(expression->reflectedType.isClass() ? expression->reflectedType
                                                  : Type(expression->token.text),
              statement->type, expression->token);
        std::set<std::string> initialized;
        for (std::size_t index = 0; index < expression->args.size(); ++index) {
            const Token token(expression->fieldNames[index], expression->token.line);
            const auto &member = field(statement->type, token);
            if (!initialized.insert(token.text).second)
                fail(token, "duplicate field initializer");
            match(this->expression(expression->args[index]), member.type, token);
            push();
        }
        if (initialized.size() != definition.fields.size())
            fail(expression->token, "every class field must be initialized exactly once");
        const int destination =
            add(statement->name, statement->type, statement->mutableValue, statement->token);
        for (std::size_t index = expression->args.size(); index > 0; --index) {
            const auto &member = field(
                statement->type, Token(expression->fieldNames[index - 1], expression->token.line));
            pop();
            emit(ir::Store{fieldOffset(destination, member), member.type});
        }
    }
    void initializeArray(StatementPtr statement) {
        const auto expression = statement->expr;
        const auto type = statement->type;
        if (expression->op == "name") {
            const int original = source(expression);
            match(locals[original].type, type, expression->token);
            const int destination =
                add(statement->name, type, statement->mutableValue, statement->token);
            for (int index = 0; index < type.length; ++index) {
                emit(ir::Load{offset(original) - index * ir::storageWidth(Type(type.elementKind)),
                              Type(type.elementKind)});
                emit(ir::Store{offset(destination) -
                                   index * ir::storageWidth(Type(type.elementKind)),
                               Type(type.elementKind)});
            }
            return;
        }
        if (expression->op != "array_literal")
            fail(expression->token,
                 "array local requires an array literal or same-type array copy");
        if (expression->args.size() != static_cast<std::size_t>(type.length))
            fail(expression->token, "array initializer length does not match its declared type");
        for (const auto &value : expression->args) {
            match(this->expression(value), Type(type.elementKind), value->token);
            push();
        }
        const int destination =
            add(statement->name, type, statement->mutableValue, statement->token);
        for (int index = type.length - 1; index >= 0; --index) {
            pop();
            emit(ir::Store{offset(destination) - index * ir::storageWidth(Type(type.elementKind)),
                           Type(type.elementKind)});
        }
    }
    bool statement(StatementPtr s) {
        if (s->kind == "return") {
            if (result.isClass()) {
                if (s->expr->op != "name")
                    fail(s->token, "class return requires a complete local name");
                const int local = source(s->expr);
                match(locals[local].type, result, s->token);
                endReturnBorrows();
                emit(ir::ReturnObject{offset(local)});
            } else {
                match(expression(s->expr), result, s->token);
                endReturnBorrows();
                emit(ir::Return{});
            }
            return true;
        }
        if (s->kind == "block")
            return block(s->body);
        if (s->kind == "static_assert") {
            auto saved = std::move(lowered.code);
            lowered.code.clear();
            auto t = expression(s->expr);
            match(t, Type::Bool, s->token);
            auto v = constant(s->expr);
            lowered.code = std::move(saved);
            if (!v.value)
                fail(s->token, "static assertion failed");
            return false;
        }
        if (s->kind == "let") {
            if (s->type.isSpan()) {
                if (s->mutableValue)
                    fail(s->token, "span bindings must be const and cannot be rebound");
                acquireSpan(s->expr, s->name, true);
                return false;
            }
            if (s->type.isArray()) {
                initializeArray(s);
                return false;
            }
            if (s->type.isClass()) {
                initializeClass(s);
                return false;
            }
            auto e = s->expr;
            int owner = -1;
            if (scalarValue(s->type)) {
                match(expression(e), s->type, s->token);
            } else {
                if (e->op != "call")
                    fail(s->token, "ownership binding requires explicit constructor");
                arity(e, 1);
                auto op = e->token.text;
                if (s->type == Type::Own && op == "own") {
                    match(expression(e->args[0]), Type::I64, s->token);
                } else if (s->type == Type::Own && op == "move") {
                    int i = source(e->args[0]);
                    match(locals[i].type, Type::Own, s->token);
                    if (!locals[i].mut && s->mutableValue)
                        fail(s->token, "cannot move a const owner into a mutable binding");
                    if (locals[i].shared || locals[i].exclusive)
                        fail(s->token, "cannot move a borrowed owner");
                    locals[i].live = false;
                    emit(ir::Load{offset(i), payloadType(locals[i].type)});
                } else if ((s->type == Type::Ref && op == "borrow") ||
                           (s->type == Type::MutRef && op == "borrow_mut")) {
                    owner = source(e->args[0]);
                    match(locals[owner].type, Type::Own, s->token);
                    if (s->type == Type::MutRef && !locals[owner].mut)
                        fail(s->token, "cannot mutably borrow a const owner");
                    if (locals[owner].exclusive ||
                        (s->type == Type::MutRef && locals[owner].shared))
                        fail(s->token, "conflicting borrow");
                    if (s->type == Type::Ref)
                        ++locals[owner].shared;
                    else
                        locals[owner].exclusive = true;
                    emit(ir::BorrowHandle{offset(owner), s->type});
                } else
                    fail(s->token, "constructor does not match ownership type");
            }
            int i = add(s->name, s->type, s->mutableValue, s->token);
            locals[i].owner = owner;
            emit(ir::Store{offset(i), payloadType(locals[i].type)});
            return false;
        }
        if (s->kind == "index_assign") {
            const auto storage = checkedIndex(s->target);
            if (storage.member) {
                if (currentFunction->receiverConst)
                    fail(s->token, "const method cannot write receiver arrays");
            } else {
                if (!locals[storage.local].mut)
                    fail(s->token, "index assignment requires a mutable array local");
                if (locals[storage.local].shared)
                    fail(s->token, "cannot mutate a byte array while a span is live");
            }
            push();
            match(expression(s->expr), Type(storage.type.elementKind), s->token);
            if (storage.member)
                emit(ir::ReceiverIndexStore{storage.member->index});
            else
                emit(ir::IndexStore{offset(storage.local), storage.type.length,
                                    Type(storage.type.elementKind)});
            return false;
        }
        if (s->kind == "while") {
            const auto start = fresh(), done = fresh();
            const auto incoming = locals;
            emit(ir::Label{start});
            match(expression(s->expr), Type::Bool, s->token);
            emit(ir::BranchFalse{done});
            const bool alwaysReturns = block(s->body);
            if (!alwaysReturns) {
                for (std::size_t index = 0; index < incoming.size(); ++index) {
                    if (incoming[index].live != locals[index].live)
                        fail(s->token, "loop backedge cannot move an outer owner; moves require a "
                                       "returning path");
                    if (incoming[index].shared != locals[index].shared ||
                        incoming[index].exclusive != locals[index].exclusive)
                        fail(s->token, "loop backedge must preserve outer borrow state");
                }
                emit(ir::Jump{start});
            }
            // The loop may execute zero times. Body-only return paths cannot
            // invalidate exit state.
            for (std::size_t index = 0; index < incoming.size(); ++index)
                locals[index] = incoming[index];
            emit(ir::Label{done});
            return false;
        }
        if (s->kind == "field_assign") {
            const int local = find(Token(s->name, s->token.line));
            if (!locals[local].mut)
                fail(s->token, "field assignment requires a mutable class local");
            const auto &member = field(locals[local].type, Token(s->fieldName, s->token.line));
            if (member.type.isArray() || member.type.isClass())
                fail(s->token, "whole aggregate field assignment is unsupported");
            match(expression(s->expr), member.type, s->token);
            emit(ir::Store{fieldOffset(local, member), member.type});
            return false;
        }
        if (s->kind == "assign") {
            const Token target(s->name, s->token.line);
            if (lookupLocal(target) < 0)
                if (const auto *member = receiverField(target)) {
                    if (currentFunction->receiverConst)
                        fail(target, "const method cannot write receiver fields");
                    if (member->type.isArray() || member->type.isClass())
                        fail(target, "whole aggregate field assignment is unsupported");
                    match(expression(s->expr), member->type, target);
                    emit(ir::ReceiverStore{member->index, member->type});
                    return false;
                }
            int i = find(Token(s->name, s->token.line));
            if (!locals[i].mut || !scalarValue(locals[i].type))
                fail(s->token, "assignment requires a mutable scalar local");
            match(expression(s->expr), locals[i].type, s->token);
            emit(ir::Store{offset(i), payloadType(locals[i].type)});
            return false;
        }
        if (s->kind == "if") {
            match(expression(s->expr), Type::Bool, s->token);
            auto no = fresh(), end = fresh();
            emit(ir::BranchFalse{no}); // Branch-local borrows expire before joining.
                                       // A moved owner remains unavailable
            // on every continuing path; return-only paths do not constrain later
            // uses.
            auto before = locals;
            bool yesReturn = block(s->body);
            auto yes = locals;
            emit(ir::Jump{end});
            emit(ir::Label{no});
            for (std::size_t i = 0; i < before.size(); ++i)
                locals[i] = before[i];
            bool noReturn = block(s->other);
            for (std::size_t i = 0; i < before.size(); ++i) {
                if (noReturn && !yesReturn) {
                    locals[i] = yes[i];
                } else if (!yesReturn && !noReturn) {
                    if (locals[i].shared != yes[i].shared ||
                        locals[i].exclusive != yes[i].exclusive ||
                        locals[i].spanOrigin != yes[i].spanOrigin ||
                        locals[i].owner != yes[i].owner)
                        fail(s->token, "continuing branches must preserve the same borrow state");
                    locals[i].live = locals[i].live && yes[i].live;
                }
            }
            emit(ir::Label{end});
            return yesReturn && noReturn;
        }
        expression(s->expr);
        return false;
    }

  public:
    explicit SemanticAnalyzer(Program program)
        : sourceFunctions(std::move(program.functions)), classes(std::move(program.classes)),
          enums(std::move(program.enums)), reflectionAccess(std::move(program.reflectionAccess)) {
        for (const auto &definition : classes)
            for (const auto &method : definition.methods)
                sourceFunctions.push_back(method);
    }
    ir::ValidatedModule analyze() {
        static const std::set<std::string> builtins = {"i64",
                                                       "u64",
                                                       "u8",
                                                       "borrow_bytes",
                                                       "own",
                                                       "move",
                                                       "borrow",
                                                       "borrow_mut",
                                                       "read",
                                                       "write",
                                                       "size_of",
                                                       "type_id",
                                                       "field_count",
                                                       "len",
                                                       "reflect_size",
                                                       "reflect_field_count",
                                                       "aurora_reflect_size",
                                                       "aurora_reflect_field_count"};
        if (classes.size() + enums.size() > 999900)
            throw Error("too many class types for bootstrap type IDs");
        if (enums.size() > 64)
            throw Error("module graph exceeds 64 enum declarations");
        for (std::size_t index = 0; index < enums.size(); ++index) {
            auto &definition = enums[index];
            if (enumNames.contains(definition.name) || definition.cases.empty() ||
                definition.cases.size() > 256)
                fail(definition.token, "enum requires a unique name and 1 to 256 cases");
            std::set<std::string> caseNames;
            for (const auto &name : definition.cases)
                if (!caseNames.insert(name.text).second)
                    fail(name, "duplicate enum case");
            definition.id = 100 + static_cast<int>(classes.size() + index);
            enumNames[definition.name] = index;
        }
        for (std::size_t index = 0; index < classes.size(); ++index) {
            auto &definition = classes[index];
            const auto &name = definition.name;
            if (builtins.contains(name) || name == "i64" || name == "u64" || name == "bool" ||
                name == "ref" || name == "mutref" || name == "array" || classNames.contains(name))
                fail(definition.token, "duplicate or reserved class name");
            classNames[name] = index;
            definition.id = 100 + static_cast<int>(index);
        }
        for (const auto &definition : classes)
            buildClassLayout(definition.name);
        classStorage = ir::computeClassStorageLayouts(classLeaves, classShapes);
        for (auto &definition : classes)
            for (auto &member : definition.fields)
                member.offset = classStorage.at(definition.name).fieldOffsets.at(member.index);
        for (std::size_t i = 0; i < sourceFunctions.size(); ++i) {
            if (builtins.count(sourceFunctions[i].name) ||
                functions.count(sourceFunctions[i].name) ||
                classNames.count(sourceFunctions[i].name))
                fail(sourceFunctions[i].token, "duplicate or reserved function name");
            if (sourceFunctions[i].params.size() > 6)
                fail(sourceFunctions[i].token, "at most six parameters supported");
            if (!sourceFunctions[i].receiverClass.empty()) {
                if (!scalarValue(sourceFunctions[i].result) && !sourceFunctions[i].result.isClass())
                    fail(sourceFunctions[i].token, "methods require scalar, enum or class results");
                if (!sourceFunctions[i].constructor)
                    for (const auto &parameter : sourceFunctions[i].params)
                        if (!scalarValue(parameter.type))
                            fail(sourceFunctions[i].token,
                                 "methods require scalar or enum parameters");
            }
            auto checkBoundaryType = [&](const Type &type) {
                if (type.isClass() &&
                    classWords(classDefinition(type, sourceFunctions[i].token)) > 64)
                    fail(sourceFunctions[i].token, "function-boundary classes are limited to 64 "
                                                   "scalar fields or flattened leaf words");
            };
            checkBoundaryType(sourceFunctions[i].result);
            for (const auto &parameter : sourceFunctions[i].params)
                checkBoundaryType(parameter.type);
            functions[sourceFunctions[i].name] = i;
        }
        ir::Module module;
        for (const auto &definition : enums)
            module.enumCases[definition.name] = static_cast<int>(definition.cases.size());
        module.classLayouts = classLeaves;
        module.classFields = classShapes;
        module.classStorage = classStorage;
        for (auto &function : sourceFunctions) {
            currentFunction = &function;
            locals.clear();
            scopes.clear();
            scopes.emplace_back();
            slot = 0;
            lowered = ir::Function{};
            lowered.name = function.name;
            lowered.moduleScope = function.moduleScope;
            lowered.result = function.result;
            if (!function.receiverClass.empty())
                lowered.receiver = ir::Receiver{function.receiverClass, !function.receiverConst,
                                                function.constructor};
            result = function.result;
            for (const auto &parameter : function.params)
                lowered.parameters.push_back(parameter.type);
            for (std::size_t index = 0; index < function.params.size(); ++index) {
                const auto &parameter = function.params[index];
                const int local = add(parameter.name, parameter.type, false, function.token, true,
                                      !parameter.type.isClass());
                if (parameter.type.isSpan())
                    emit(ir::BindSpanParameter{static_cast<int>(index), offset(local)});
                else if (parameter.type.isClass())
                    emit(ir::BindObjectParameter{static_cast<int>(index), offset(local),
                                                 parameter.type.className});
                else
                    emit(ir::BindParameter{static_cast<int>(index), offset(local), parameter.type});
            }
            if (function.constructor) {
                const auto &definition =
                    classDefinition(Type(function.receiverClass), function.token);
                std::map<std::string, ExpressionPtr> initializers;
                for (const auto &[field, value] : function.initializers) {
                    const auto found = std::find_if(
                        definition.fields.begin(), definition.fields.end(),
                        [&](const Field &member) { return member.token.text == field.text; });
                    if (found == definition.fields.end())
                        fail(field, "unknown constructor field initializer");
                    if (!initializers.emplace(field.text, value).second)
                        fail(field, "duplicate constructor field initializer");
                }
                if (initializers.size() != definition.fields.size())
                    fail(function.token, "constructor must initialize every field exactly once");
                for (const auto &member : definition.fields) {
                    const auto &initializer = initializers.at(member.token.text);
                    if (member.type.isClass()) {
                        if (initializer->op != "name")
                            fail(initializer->token,
                                 "class field initializer requires a complete named class value");
                        const int original = source(initializer);
                        match(locals[original].type, member.type, initializer->token);
                        emit(ir::InitializeObjectField{0, member.index, offset(original)});
                    } else if (member.type.isArray()) {
                        if (initializer->op != "array_zero")
                            fail(member.token,
                                 "array fields require explicit empty-brace zero initialization");
                        emit(ir::ReceiverArrayZero{member.index});
                    } else {
                        if (initializer->op == "array_zero")
                            fail(member.token, "empty-brace constructor initialization is "
                                               "restricted to array fields");
                        match(expression(initializer), member.type, member.token);
                        emit(ir::ReceiverStore{member.index, member.type});
                    }
                }
                emit(ir::Constant{0, Type::I64});
                emit(ir::Return{});
            } else if (!block(function.body))
                fail(function.token, "function must return on every path");
            lowered.frameBytes = ((slot * 8 + 15) / 16) * 16;
            module.functions.push_back(std::move(lowered));
        }
        for (int id = 1; id <= 5; ++id)
            module.descriptors[id] = ir::Descriptor{id == 2 ? 1 : 8, 0};
        module.descriptors[8] = ir::Descriptor{8, 0};
        module.descriptors[static_cast<int>(TypeKind::U8) + 1] = ir::Descriptor{1, 0};
        for (const auto &definition : classes) {
            const Type type(definition.name);
            module.descriptors[definition.id] = ir::Descriptor{typeSize(type, definition.token),
                                                               fieldCount(type, definition.token)};
        }
        for (const auto &definition : enums)
            module.descriptors[definition.id] = ir::Descriptor{8, 0};
        for (const auto &[id, type] : arrayTypes)
            module.descriptors[id] =
                ir::Descriptor{type.length * ir::storageWidth(Type(type.elementKind)), 0};
        if (reflectionAccess.empty()) {
            auto &own = reflectionAccess[0];
            for (const auto &definition : classes)
                own.insert(definition.name);
            for (const auto &definition : enums)
                own.insert(definition.name);
        }
        module.descriptorViews.clear();
        for (const auto &[scope, visible] : reflectionAccess) {
            auto &view = module.descriptorViews[scope];
            for (const auto &[id, descriptor] : module.descriptors) {
                (void)descriptor;
                if (id <= 5 || id == 8 || id == static_cast<int>(TypeKind::U8) + 1 || id >= 1000000)
                    view.insert(id);
            }
            for (const auto &name : visible) {
                if (classNames.contains(name))
                    view.insert(classes.at(classNames.at(name)).id);
                else if (enumNames.contains(name))
                    view.insert(enums.at(enumNames.at(name)).id);
                else
                    throw Error("unknown nominal type in reflection view");
            }
        }
        return ir::validate(std::move(module));
    }
};

} // namespace aurora
