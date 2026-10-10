#pragma once
#include "ir_layout.hpp"
#include "ir_verify.hpp"
#include "syntax.hpp"
#include "byte_literal.hpp"
#include "integer_literal.hpp"
#include <algorithm>
#include <bit>
#include <limits>
#include <map>
#include <set>
namespace aurora {
enum class AnalysisMode {
    Check,
    Lint
};
class Local {
public:
    std::string name;
    Type type;
    int offset = 0, owner = -1, shared = 0, objectShared = 0;
    // -1 is an incoming span parameter; -2 is the implicit receiver.
    int spanOrigin = -1, spanField = -1;
    bool spanTemporaryParent = false;
    bool mut = false, live = true, exclusive = false;
    bool resourceActive = false, borrowedObject = false, objectExclusive = false;
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
    std::map<std::string, int> receiverSpanFields;
    std::vector<Local> locals;
    std::vector<std::map<std::string, int>> scopes;
    ir::Function lowered;
    int slot = 0, label = 0, nextObjectLoan = 1;
    Type result = Type::I64;
    const Function *currentFunction = nullptr;
    AnalysisMode mode;
    bool lintFunction = false;
    // Syntactic reads are monotonic, unlike the ownership state copied at joins.
    // Indices are the analyzer's resolved Local identities, never source names.
    std::set<int> readLocals;
    std::vector<std::pair<int, SourceSpan>> lintBindings;
    std::vector<Diagnostic> lintDiagnostics;

    [[noreturn]] void fail(const Token &t, const std::string &m) {
        throw Error(DiagnosticCode::Semantic, m, t.span);
    }
    const ClassDefinition &classDefinition(const Type &type, const Token &token) {
        auto found = classNames.find(type.className);
        if (!type.isClass() || found == classNames.end())
            fail(token, "unknown class type '" + typeName(type) + "'");
        return classes[found->second];
    }
    bool owningClass(const Type &type) const {
        return type.isClass() && ir::owningClass(classShapes, type.className);
    }
    bool ownerType(const Type &type) const {
        return type.isBytes() || owningClass(type);
    }
    std::int64_t typeId(const Type &type, const Token &token) {
        if (type.isArray()) {
            const int id = type.elementKind == TypeKind::U8 ? 3000000 + type.length
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
                if (owningClass(member.type))
                    fail(member.token, "nested owning class fields are unsupported");
                const auto &child = classLeaves.at(member.type.className);
                leaves.insert(leaves.end(), child.begin(), child.end());
                depth = std::max(depth, 1 + classDepths.at(member.type.className));
            } else if (member.type.isBytes()) {
                needsConstructor = true;
                if (member.publicAccess)
                    fail(member.token, "owned byte fields must be private");
                if (!definition.templateParameters.empty() || !definition.templateArguments.empty())
                    fail(member.token, "owning class templates are unsupported");
            } else if (member.type.isArray()) {
                needsConstructor = true;
                if (member.publicAccess || member.type.length < 1 ||
                    member.type.length > maximumClassArrayLength(Type(member.type.elementKind)) ||
                    !scalar(Type(member.type.elementKind)) || !member.type.elementParameter.empty() ||
                    !member.type.lengthParameter.empty())
                    fail(member.token,
                         "class array fields require private concrete scalar "
                         "storage of length 1 to 64, or 1 to 512 for u8");
                typeId(member.type, member.token);
                leaves.insert(leaves.end(), member.type.length, Type(member.type.elementKind));
            } else {
                if (!scalarValue(member.type))
                    fail(member.token, "class field must be concrete scalar, enum, class or private array");
                leaves.push_back(member.type);
            }
            classShapes[name].push_back(
                ir::ClassField{member.type.isArray() ? Type(member.type.elementKind) : member.type,
                               firstLeaf,
                               static_cast<int>(leaves.size()) - firstLeaf,
                               member.type.isArray()});
            if (leaves.size() > maxFrameSlots)
                fail(definition.token, "class layout exceeds 65536 bytes");
            if (composed && !ir::copiedClassLeavesSupported(leaves))
                fail(definition.token,
                     "composed classes are limited to 64 non-byte scalar leaves, "
                     "512 u8 leaves and 513 total leaves");
        }
        if (composed && depth > 4)
            fail(definition.token, "composed class exceeds depth four");
        if (needsConstructor &&
            std::none_of(definition.methods.begin(), definition.methods.end(), [](const Function &method) {
                return method.constructor;
            }))
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
            return std::count_if(fields.begin(), fields.end(), [](const Field &field) {
                return field.publicAccess;
            });
        }
        return 0;
    }
    const Field &field(const Type &type, const Token &token) {
        const auto &definition = classDefinition(type, token);
        for (const auto &value : definition.fields)
            if (value.token.text == token.text) {
                if (!value.publicAccess && (!currentFunction || currentFunction->receiverClass != type.className))
                    fail(token, "private class field is inaccessible");
                requireVisibleType(value.type, token);
                return value;
            }
        fail(token, "unknown field '" + token.text + "' in " + typeName(type));
    }
    int fieldOffset(int local, const Field &value) {
        return locals.at(local).offset - value.offset;
    }
    void copyClass(int original, int destination, const Token &token) {
        if (owningClass(locals[original].type))
            fail(token, "owning class cannot be copied; use move(named_local)");
        emit(ir::CopyObject{offset(original), offset(destination)});
    }
    Type payloadType(const Type &type) {
        return type == Type::Own ? Type::I64 : type;
    }
    std::int64_t reflectedValue(ExpressionPtr expression) {
        if (expression->reflectedType.isSpan())
            fail(expression->token, "span capabilities are unavailable to reflection");
        if (expression->reflectedType.isResource() || expression->reflectedType.isService())
            fail(expression->token, "resource capabilities are unavailable to reflection");
        if (expression->token.text == "type_id")
            return typeId(expression->reflectedType, expression->token);
        if (expression->token.text == "field_count")
            return fieldCount(expression->reflectedType, expression->token);
        return typeSize(expression->reflectedType, expression->token);
    }
    template <class Operation> void emit(Operation operation) {
        lowered.code.emplace_back(std::move(operation));
    }
    int fresh() {
        return label++;
    }
    int offset(int local) {
        return locals.at(local).offset;
    }
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
        if (locals[i].objectExclusive)
            fail(e->token, "owning object is exclusively borrowed for a call");
        if (lintFunction)
            readLocals.insert(i);
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
    void push() {
        emit(ir::Push{});
    }
    void pop() {
        emit(ir::Pop{});
    }
    int add(const std::string &n, Type t, bool mut, const Token &tok, bool bind = true, bool begin = true) {
        if (bind && scopes.back().count(n))
            fail(tok, "duplicate local '" + n + "'");
        Local l;
        l.name = n;
        l.type = t;
        l.mut = mut;
        const auto needed = t.isService()                  ? service::capabilityBytes / 8
                            : t.isBytes()                  ? 4
                            : t.isSpan()                   ? ir::spanBytes / 8
                            : (t.isClass() || t.isArray()) ? ir::roundedStorage(static_cast<int>(typeSize(t, tok))) / 8
                                                           : 1;
        if (needed > maxFrameSlots || slot > maxFrameSlots - needed)
            fail(tok, "function local stack frame exceeds 65536 bytes");
        slot += static_cast<int>(needed);
        l.offset = 8 * slot;
        if (t.isService()) {
            lowered.serviceSlots.insert(l.offset);
        } else if (t.isRegion()) {
            lowered.regionSlots.insert(l.offset);
        } else if (t.isBytes()) {
            lowered.byteSlots[l.offset] = mut;
            l.resourceActive = true;
            if (begin)
                emit(ir::BeginBytes{l.offset});
        } else if (t.isSpan()) {
            lowered.spanSlots.insert(l.offset);
        } else if (t.isClass()) {
            l.resourceActive = owningClass(t);
            lowered.objectSlots[l.offset] = ir::ObjectSlot{t.className, mut};
            if (begin)
                emit(ir::BeginObject{l.offset});
            const auto &leaves = classLeaves.at(t.className);
            for (std::size_t index = 0; index < leaves.size(); ++index)
                lowered.slots[l.offset - classStorage.at(t.className).leafOffsets[index]] = leaves[index];
        } else if (t.isArray()) {
            if (t.elementKind == TypeKind::U8) {
                lowered.arraySlots[l.offset] = t.length;
                emit(ir::BeginArray{l.offset});
            }
            for (int index = 0; index < t.length; ++index)
                lowered.slots[l.offset - index * ir::storageWidth(Type(t.elementKind))] = Type(t.elementKind);
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
    bool hasSpanBorrow(int root, int fieldIndex = -1) const {
        return std::any_of(locals.begin(), locals.end(), [&](const Local &local) {
            return local.live && local.type.isSpan() && local.spanOrigin == root &&
                   (fieldIndex < 0 || local.spanField == fieldIndex);
        });
    }
    void requireNoObjectLoan(int root, const Token &token) {
        if (root >= 0 && (locals[root].objectShared || locals[root].objectExclusive))
            fail(token, "cannot mutate or move an owning object while borrowed");
    }
    void requireUnborrowed(int root, int fieldIndex, const Token &token) {
        requireNoObjectLoan(root, token);
        if (hasSpanBorrow(root, fieldIndex))
            fail(token, "cannot mutate or move an owner while a readonly span is live");
    }
    bool spanExpression(ExpressionPtr value) {
        if (value->op == "name") {
            const int local = lookupLocal(value->token);
            return local >= 0 && locals[local].type.isSpan();
        }
        if (value->op == "call")
            return value->token.text == "borrow_bytes";
        if (value->op != "method_call" && value->op != "implicit_method_call")
            return false;
        if (value->op == "method_call" && value->token.text == "subspan")
            return !value->args.empty() && spanExpression(value->args[0]);
        Type receiver;
        if (value->op == "implicit_method_call") {
            if (!currentFunction || currentFunction->receiverClass.empty())
                return false;
            receiver = Type(currentFunction->receiverClass);
        } else {
            if (value->args.empty() || value->args[0]->op != "name")
                return false;
            const auto &target = value->args[0];
            const int local = lookupLocal(target->token);
            if (local >= 0)
                receiver = locals[local].type;
            else if (const auto *member = receiverField(target->token))
                receiver = member->type;
            else
                return false;
        }
        if (!receiver.isClass())
            return false;
        return method(receiver, value->token).result.isSpan();
    }
    int acquireSpan(ExpressionPtr value, const std::string &name = "", bool bind = false) {
        int parent = -1, origin = -1, fieldIndex = -1;
        bool temporaryParent = false;
        const bool subspan = value->op == "method_call" && value->token.text == "subspan";
        if (subspan) {
            if (value->args.size() != 3)
                fail(value->token, "span subspan expects offset and count");
            if (value->args[0]->op == "name") {
                parent = source(value->args[0]);
                if (!locals[parent].type.isSpan())
                    fail(value->token,
                         "subspan requires a named live readonly span or a directly derived temporary view");
            } else {
                parent = acquireSpan(value->args[0]);
                const int root = locals[parent].spanOrigin;
                if (root == -1 || (root >= 0 && byteArray(locals[root].type)))
                    fail(value->token,
                         "temporary subspan chains require an owned-byte origin; array and parameter "
                         "views require a named parent span");
                temporaryParent = true;
            }
            origin = locals[parent].spanOrigin;
            fieldIndex = locals[parent].spanField;
            // Acquire the parent before either operand; later expressions must
            // not invalidate the owner while computing the requested window.
            match(expression(value->args[1]), Type::I64, value->token);
            push();
            match(expression(value->args[2]), Type::I64, value->token);
        } else if (value->op == "call" && value->token.text == "borrow_bytes") {
            arity(value, 1);
            const auto &target = value->args[0];
            const Field *member = nullptr;
            if (target->op == "name") {
                if (lookupLocal(target->token) < 0)
                    member = receiverField(target->token);
                origin = member ? -2 : source(target);
            } else if (target->op == "member" && target->args[0]->op == "name") {
                origin = source(target->args[0]);
                if (locals[origin].borrowedObject)
                    fail(target->token, "borrowed object parameters support public methods, not field access");
                member = &field(locals[origin].type, target->token);
            } else
                fail(value->token,
                     "borrow_bytes requires a named local byte array, a named owned-byte value or a direct private "
                     "owned-byte field");
            if (member) {
                if (!member->type.isBytes())
                    fail(value->token, "borrow_bytes fields require direct private owned-byte storage");
                fieldIndex = member->index;
            } else if (!byteArray(locals[origin].type) && !locals[origin].type.isBytes())
                fail(value->token, "borrow_bytes requires a named local byte array or owned bytes");
        } else if (value->op == "name") {
            parent = source(value);
            if (!locals[parent].type.isSpan())
                fail(value->token, "span initializer requires borrow_bytes, a live span or its subspan");
            origin = locals[parent].spanOrigin;
            fieldIndex = locals[parent].spanField;
        } else if (value->op == "method_call" || value->op == "implicit_method_call") {
            auto binding = std::make_shared<Statement>(value->token);
            binding->name = name;
            binding->type = Type::ByteSpan;
            binding->mutableValue = false;
            int destination = -1;
            callMethod(value, binding, bind, &destination);
            return destination;
        } else
            fail(value->token, "span initializer requires borrow_bytes, a live span or its subspan");
        const int destination = add(name, Type::ByteSpan, false, value->token, bind);
        locals[destination].owner = parent;
        locals[destination].spanOrigin = origin;
        locals[destination].spanField = fieldIndex;
        locals[destination].spanTemporaryParent = temporaryParent;
        if (parent >= 0) {
            ++locals[parent].shared;
            if (subspan)
                emit(ir::Subspan{offset(parent), offset(destination)});
            else
                emit(ir::ReborrowSpan{offset(parent), offset(destination)});
        } else if (fieldIndex >= 0 || locals[origin].type.isBytes())
            emit(ir::BorrowOwnedSpan{origin == -2 ? 0 : offset(origin), fieldIndex, offset(destination)});
        else
            emit(ir::BorrowSpan{offset(origin), offset(destination)});
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
        if (span.spanTemporaryParent)
            releaseSpan(span.owner, instructions);
    }
    void endReturnBorrows(int returned = -1) {
        // Keep the returned capability and its parent chain until ReturnSpan
        // copies the record; all unrelated borrows end before resource cleanup.
        std::set<int> retained;
        for (int local = returned; local >= 0; local = locals[local].owner)
            retained.insert(local);
        for (std::size_t index = locals.size(); index > 0; --index)
            if (locals[index - 1].live && locals[index - 1].type.isSpan() &&
                !retained.contains(static_cast<int>(index - 1)))
                emit(ir::EndSpan{locals[index - 1].offset});
        for (std::size_t index = locals.size(); index > 0; --index)
            if (locals[index - 1].live && byteArray(locals[index - 1].type))
                emit(ir::EndArray{locals[index - 1].offset});
    }
    void endReturnObjects() {
        // Named copied locals and readonly copied parameters also end before a
        // span result leaves the invocation. Unnamed call snapshots already end
        // at their call sites and must not be ended twice.
        std::set<int> active;
        for (const auto &scope : scopes)
            for (const auto &[name, local] : scope) {
                (void)name;
                if (locals[local].live && locals[local].type.isClass() && !owningClass(locals[local].type))
                    active.insert(local);
            }
        for (auto local = active.rbegin(); local != active.rend(); ++local)
            emit(ir::EndObject{offset(*local)});
    }
    int movedOwner(ExpressionPtr value, const Type &expected) {
        if (value->op != "call" || value->token.text != "move")
            fail(value->token, "owning transfer requires move(named_local)");
        arity(value, 1);
        const int local = source(value->args[0]);
        match(locals[local].type, expected, value->token);
        if (!ownerType(expected))
            fail(value->token, "move requires an owning value");
        if (locals[local].borrowedObject)
            fail(value->token, "borrowed object parameters cannot transfer ownership");
        if (!locals[local].mut)
            fail(value->token, "cannot move a const owner");
        requireUnborrowed(local, -1, value->token);
        return local;
    }
    int movedBytes(ExpressionPtr value) {
        return movedOwner(value, Type::OwnedBytes);
    }
    void moveOwner(int original, int destination) {
        if (locals[original].type.isBytes())
            emit(ir::MoveBytes{offset(original), offset(destination)});
        else
            emit(ir::MoveObject{offset(original), offset(destination)});
        locals[destination].owner = locals[original].owner;
        locals[original].live = false;
    }
    void endOwner(int local) {
        if (locals[local].type.isBytes())
            emit(ir::EndBytes{offset(local)});
        else
            emit(ir::EndObject{offset(local)});
    }
    void endReturnBytes(int returned = -1) {
        for (std::size_t index = locals.size(); index > 0; --index) {
            const int local = static_cast<int>(index - 1);
            if (local != returned && locals[local].resourceActive)
                endOwner(local);
        }
    }
    Type callResource(ExpressionPtr value, const Function &callee, const StatementPtr &binding) {
        const bool constructor = callee.constructor;
        if ((callee.result.isClass() || callee.result.isBytes() || constructor) && !binding)
            fail(value->token, "resource result requires a typed local initializer");
        if (binding)
            match(constructor ? Type(callee.receiverClass) : callee.result, binding->type, value->token);
        arity(value, callee.params.size());
        const int region = source(value->args[0]);
        match(locals[region].type, Type::ByteRegion, value->token);
        std::vector<int> arguments(callee.params.size(), 0), staged, snapshots;
        for (std::size_t index = 1; index < callee.params.size(); ++index) {
            const auto &argument = value->args[index];
            const auto &type = callee.params[index].type;
            if (ownerType(type)) {
                const int original = movedOwner(argument, type);
                if (locals[original].owner != region)
                    fail(argument->token, "owning value belongs to a different region");
                const int temporary = add("", type, true, argument->token, false);
                moveOwner(original, temporary);
                arguments[index] = offset(temporary);
                staged.push_back(temporary);
            } else if (constructor && type.isClass()) {
                const int original = source(argument);
                match(locals[original].type, type, argument->token);
                const int snapshot = add("", type, false, argument->token, false);
                copyClass(original, snapshot, argument->token);
                arguments[index] = offset(snapshot);
                snapshots.push_back(offset(snapshot));
            } else {
                match(expression(argument), type, argument->token);
                push();
            }
        }
        int destination = 0;
        if (binding) {
            const int local = add(binding->name, binding->type, binding->mutableValue, binding->token);
            if (ownerType(binding->type))
                locals[local].owner = region;
            destination = offset(local);
        }
        emit(ir::ResourceCall{
            callee.name, offset(region), arguments, constructor ? 0 : destination, constructor ? destination : 0});
        for (auto it = staged.rbegin(); it != staged.rend(); ++it) {
            endOwner(*it);
            locals[*it].live = locals[*it].resourceActive = false;
        }
        for (int snapshot : snapshots)
            emit(ir::EndObject{snapshot});
        return constructor ? Type(callee.receiverClass) : callee.result;
    }
    void initializeBytes(StatementPtr binding) {
        const auto value = binding->expr;
        if (value->op == "call" && value->token.text == "move") {
            const int original = movedBytes(value);
            const int local = add(binding->name, binding->type, binding->mutableValue, binding->token);
            emit(ir::MoveBytes{offset(original), offset(local)});
            locals[local].owner = locals[original].owner;
            locals[original].live = false;
            return;
        }
        if (value->op == "method_call" && value->token.text == "try_allocate") {
            arity(value, 2);
            const int region = source(value->args[0]);
            match(locals[region].type, Type::ByteRegion, value->token);
            match(expression(value->args[1]), Type::I64, value->token);
            const int local = add(binding->name, binding->type, binding->mutableValue, binding->token);
            locals[local].owner = region;
            emit(ir::AllocateBytes{offset(region), offset(local)});
            return;
        }
        if (value->op == "call" && value->overloadCandidates.empty()) {
            const auto found = functions.find(value->resolvedName.empty() ? value->token.text : value->resolvedName);
            if (found != functions.end()) {
                const auto &callee = sourceFunctions[found->second];
                if (!callee.params.empty() && callee.params[0].type.isRegion()) {
                    callResource(value, callee, binding);
                    return;
                }
            }
        }
        fail(value->token, "owned bytes require region.try_allocate, move or an owned-result function call");
    }
    class IndexedStorage {
    public:
        int local = -1;
        const Field *member = nullptr;
        Type type;
    };
    IndexedStorage checkedIndex(ExpressionPtr index) {
        if (index->args[0]->op != "name")
            fail(index->token, "indexing requires an array local or implicit private receiver field");
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
            emit(ir::BoundsGuard{offset(storage.local), storage.type.length, Type(storage.type.elementKind)});
        return storage;
    }
    const Function &method(const Type &type, const Token &token, bool constructor = false) {
        const auto &definition = classDefinition(type, token);
        for (const auto &candidate : definition.methods)
            if (candidate.constructor == constructor && (constructor || candidate.token.text == token.text)) {
                if (!candidate.publicAccess && (!currentFunction || currentFunction->receiverClass != type.className))
                    fail(token, constructor ? "private constructor is inaccessible" : "private method is inaccessible");
                return candidate;
            }
        fail(token, constructor ? "class has no declared constructor" : "unknown class method");
    }
    void requireVisibleType(const Type &type, const Token &token) {
        if (service::copiedType(type))
            return;
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
    Type callMethod(ExpressionPtr value,
                    const StatementPtr &resultBinding = nullptr,
                    bool bindResult = true,
                    int *resultLocal = nullptr) {
        const bool implicit = value->op == "implicit_method_call";
        if (implicit && lookupLocal(value->token) >= 0)
            fail(value->token, "local binding shadows method and is not callable");
        int receiver = -1, receiverOffset = 0, receiverFieldIndex = -1;
        Type type = implicit ? Type(currentFunction->receiverClass) : Type::I64;
        bool mutableReceiver = implicit && !currentFunction->receiverConst;
        if (!implicit) {
            const auto &target = value->args[0];
            const Field *member = nullptr;
            if (target->op == "name") {
                if (lookupLocal(target->token) < 0)
                    member = receiverField(target->token);
                if (!member) {
                    receiver = source(target);
                    receiverOffset = offset(receiver);
                    type = locals[receiver].type;
                    mutableReceiver = locals[receiver].mut;
                } else {
                    mutableReceiver = !currentFunction->receiverConst;
                }
            } else if (target->op == "member" && target->args[0]->op == "name") {
                receiver = source(target->args[0]);
                if (locals[receiver].borrowedObject)
                    fail(target->token, "borrowed object parameters support public methods, not field projections");
                receiverOffset = offset(receiver);
                mutableReceiver = locals[receiver].mut;
                member = &field(locals[receiver].type, target->token);
            } else {
                fail(value->token, "method receiver requires a class local or direct owned class field");
            }
            if (member) {
                if (!member->type.isClass() && !member->type.isBytes())
                    fail(target->token, "nested method receiver requires an owned class field or owned byte field");
                requireVisibleType(member->type, target->token);
                type = member->type;
                receiverFieldIndex = member->index;
            }
        }
        if (!bindResult && resultBinding && resultBinding->type.isClass() &&
            (type.isService() || receiverFieldIndex >= 0))
            fail(value->token, "direct copied return requires an ordinary method on a complete receiver");
        auto requireLiveReceiver = [&] {
            if (receiver >= 0 && !locals[receiver].live)
                fail(value->token, "method arguments consumed the receiver or its containing object");
            if (receiver >= 0 && locals[receiver].objectExclusive)
                fail(value->token, "owning object is exclusively borrowed for a call");
        };
        if (type.isService()) {
            if (implicit || receiver < 0 || receiverFieldIndex != -1 || locals[receiver].exclusive)
                fail(value->token, "service operation requires an active named exclusive service parameter");
            if (type == Type::ConsoleSession && value->token.text == "next") {
                arity(value, 1);
                if (!resultBinding)
                    fail(value->token, "next requires a typed ConsoleSample initializer");
                match(resultBinding->type, service::sampleType(), value->token);
                const int destination = add(resultBinding->name,
                                            resultBinding->type,
                                            resultBinding->mutableValue,
                                            resultBinding->token,
                                            bindResult);
                emit(ir::ServiceOperation{receiverOffset, service::Operation::Next, offset(destination)});
                return service::sampleType();
            }
            if (type == Type::IommuEventSession && value->token.text == "poll") {
                arity(value, 1);
                if (!resultBinding)
                    fail(value->token, "poll requires a typed IommuEventSample initializer");
                match(resultBinding->type, service::eventSampleType(), value->token);
                const int destination = add(resultBinding->name,
                                            resultBinding->type,
                                            resultBinding->mutableValue,
                                            resultBinding->token,
                                            bindResult);
                emit(ir::ServiceOperation{
                    receiverOffset, service::Operation::IommuPoll, offset(destination), service::Kind::IommuEvent});
                return service::eventSampleType();
            }
            if (type == Type::IommuEventSession && value->token.text == "acknowledge") {
                arity(value, 1);
                if (resultBinding)
                    fail(value->token, "acknowledge returns a scalar enum, not a copied report");
                emit(ir::ServiceOperation{
                    receiverOffset, service::Operation::IommuAcknowledge, 0, service::Kind::IommuEvent});
                return service::eventAckResultType();
            }
            if (type == Type::ConsoleSession && value->token.text == "put") {
                arity(value, 2);
                if (resultBinding)
                    fail(value->token, "put returns a scalar enum, not a copied report");
                match(expression(value->args[1]), Type::U8, value->token);
                emit(ir::ServiceOperation{receiverOffset, service::Operation::Put, 0});
                return service::putResultType();
            }
            if (type == Type::DisplaySession && value->token.text == "pixel") {
                arity(value, 6);
                if (resultBinding)
                    fail(value->token, "pixel returns a scalar enum, not a copied report");
                for (std::size_t index = 1; index < 6; ++index) {
                    match(expression(value->args[index]), index < 3 ? Type::U64 : Type::U8, value->token);
                    push();
                }
                emit(ir::ServiceOperation{receiverOffset, service::Operation::Pixel, 0, service::Kind::Display});
                return service::displayPutResultType();
            }
            fail(value->token, "unknown operation for sealed service kind");
        }
        if (type.isBytes()) {
            if (resultBinding || implicit)
                fail(value->token, "byte operation requires a named owner");
            const auto &name = value->token.text;
            if (name == "ok" || name == "size") {
                arity(value, 1);
                if (name == "ok") {
                    emit(ir::BytesOk{receiverOffset, receiverFieldIndex});
                    return Type::Bool;
                }
                emit(ir::BytesLength{receiverOffset, receiverFieldIndex});
                return Type::I64;
            }
            if (name == "at" || name == "set" || name == "try_resize") {
                arity(value, name == "set" ? 3 : 2);
                if (name != "at" && !mutableReceiver)
                    fail(value->token, "cannot write a const byte owner");
                match(expression(value->args[1]), Type::I64, value->token);
                if (name == "set") {
                    push();
                    match(expression(value->args[2]), Type::U8, value->token);
                }
                // Scalar operand expressions may themselves consume this owner.
                requireLiveReceiver();
                if (name != "at")
                    requireUnborrowed(receiver >= 0 ? receiver : -2, receiverFieldIndex, value->token);
                if (name == "at") {
                    emit(ir::BytesLoad{receiverOffset, receiverFieldIndex});
                    return Type::U8;
                }
                if (name == "try_resize") {
                    emit(ir::BytesResize{receiverOffset, receiverFieldIndex});
                    return Type::Bool;
                }
                emit(ir::BytesStore{receiverOffset, receiverFieldIndex});
                return Type::Bool;
            }
            fail(value->token, "unknown owned byte operation");
        }
        if (type.isRegion())
            fail(value->token, "region allocation requires an OwnedBytes local initializer");
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
            if (value->token.text == "subspan")
                fail(value->token, "subspan requires a span binding or span argument");
            fail(value->token, "span supports only readonly size, at and subspan operations");
        }
        const auto &callee = method(type, value->token);
        requireVisibleType(callee.result, value->token);
        for (const auto &parameter : callee.params)
            requireVisibleType(parameter.type, value->token);
        if (callee.result.isClass() && !resultBinding)
            fail(value->token, "class-returning method requires a typed local initializer");
        if (callee.result.isSpan() && !resultBinding)
            fail(value->token, "span-returning method requires a typed local initializer or span argument");
        if (callee.result.isSpan()) {
            if (result.isSpan())
                fail(value->token, "span-result methods cannot forward another method's returned view");
            if (receiverFieldIndex >= 0 || !owningClass(type))
                fail(value->token, "returned span requires a named owning receiver or the implicit receiver");
            if (!receiverSpanFields.contains(callee.name))
                fail(value->token, "span-result method requires a verified receiver-field summary");
        }
        if (resultBinding)
            match(callee.result, resultBinding->type, value->token);
        if (!callee.receiverConst && !mutableReceiver)
            fail(value->token, "mutable method requires a mutable receiver");
        const std::size_t first = implicit ? 0 : 1;
        if (value->args.size() - first != callee.params.size())
            fail(value->token, "wrong argument count for method");
        // Resolve receiver identity first, then snapshot each argument at its
        // left-to-right position before acquiring synchronous receiver authority.
        std::vector<int> arguments(callee.params.size(), 0), snapshots;
        std::vector<int> spanArguments(callee.params.size(), 0), spanBorrows;
        bool packed = false;
        for (std::size_t index = 0; index < callee.params.size(); ++index) {
            const auto &parameterType = callee.params[index].type;
            const auto &argument = value->args[index + first];
            if (parameterType.isSpan()) {
                packed = true;
                const int borrowed = acquireSpan(argument);
                spanArguments[index] = offset(borrowed);
                spanBorrows.push_back(borrowed);
            } else if (parameterType.isClass()) {
                packed = true;
                if (argument->op != "name")
                    fail(argument->token, "class argument requires a complete local name");
                const int original = source(argument);
                match(locals[original].type, parameterType, argument->token);
                const int snapshot = add("", parameterType, false, argument->token, false);
                copyClass(original, snapshot, argument->token);
                arguments[index] = offset(snapshot);
                snapshots.push_back(offset(snapshot));
            } else {
                match(expression(argument), parameterType, argument->token);
                push();
            }
        }
        requireLiveReceiver();
        if (!callee.receiverConst)
            requireUnborrowed(receiver >= 0 ? receiver : -2, receiverFieldIndex, value->token);
        int destination = 0;
        if (resultBinding) {
            const int local = add(resultBinding->name,
                                  resultBinding->type,
                                  resultBinding->mutableValue,
                                  resultBinding->token,
                                  bindResult);
            destination = offset(local);
            if (resultLocal)
                *resultLocal = local;
            if (callee.result.isSpan()) {
                locals[local].spanOrigin = receiver >= 0 ? receiver : -2;
                locals[local].spanField = receiverSpanFields.at(callee.name);
                if (receiver >= 0)
                    ++locals[receiver].shared;
            }
        }
        emit(ir::MethodCall{callee.name,
                            receiverOffset,
                            packed ? arguments : std::vector<int>{},
                            destination,
                            receiverFieldIndex,
                            spanBorrows.empty() ? std::vector<int>{} : spanArguments});
        for (int snapshot : snapshots)
            emit(ir::EndObject{snapshot});
        for (auto it = spanBorrows.rbegin(); it != spanBorrows.rend(); ++it)
            releaseSpan(*it, true);
        return callee.result;
    }
    Type callService(ExpressionPtr value, const Function &callee, const StatementPtr &binding) {
        arity(value, callee.params.size());
        if (callee.result.isClass() && !binding)
            fail(value->token, "copied service report requires a typed local initializer");
        if (binding)
            match(callee.result, binding->type, value->token);
        std::vector<int> roots, loans;
        std::size_t serviceCount = 0;
        while (serviceCount < callee.params.size() && callee.params[serviceCount].type.isService()) {
            const auto &argument = value->args[serviceCount];
            if (argument->op != "name")
                fail(argument->token, "service forwarding requires a named exclusive service parameter");
            const int root = source(argument);
            match(locals[root].type, callee.params[serviceCount].type, argument->token);
            if (locals[root].exclusive)
                fail(argument->token, "service authority is suspended during synchronous forwarding");
            locals[root].exclusive = true;
            const int loan = nextObjectLoan++;
            emit(ir::AcquireServiceLoan{loan, offset(root), service::kind(locals[root].type)});
            roots.push_back(root);
            loans.push_back(loan);
            ++serviceCount;
        }
        std::vector<int> spans(callee.params.size(), 0), borrowedSpans;
        for (std::size_t index = serviceCount; index < callee.params.size(); ++index) {
            const auto &argument = value->args[index];
            const auto &type = callee.params[index].type;
            if (type.isSpan()) {
                const int span = acquireSpan(argument);
                spans[index] = offset(span);
                borrowedSpans.push_back(span);
            } else {
                match(expression(argument), type, argument->token);
                push();
            }
        }
        int destination = 0;
        if (binding)
            destination = offset(add(binding->name, binding->type, binding->mutableValue, binding->token));
        ir::ServiceCall call{callee.name, loans.front(), destination, spans, service::kind(locals[roots.front()].type)};
        for (std::size_t index = 1; index < roots.size(); ++index)
            call.additionalServices.push_back({loans[index], service::kind(locals[roots[index]].type)});
        emit(std::move(call));
        for (std::size_t reverse = roots.size(); reverse > 0; --reverse) {
            const auto index = reverse - 1;
            emit(ir::ReleaseServiceLoan{loans[index], service::kind(locals[roots[index]].type)});
            locals[roots[index]].exclusive = false;
        }
        for (auto it = borrowedSpans.rbegin(); it != borrowedSpans.rend(); ++it)
            releaseSpan(*it, true);
        return callee.result;
    }
    Type callFunction(ExpressionPtr expression,
                      const Function &callee,
                      const StatementPtr &resultBinding = nullptr,
                      bool bindResult = true,
                      int *resultLocal = nullptr) {
        if (!bindResult && !callee.params.empty() &&
            (callee.params.front().type.isService() || callee.params.front().type.isRegion() ||
             callee.params.front().borrowed))
            fail(expression->token, "direct copied return requires an ordinary function call");
        if (!callee.params.empty() && callee.params.front().type.isService())
            return callService(expression, callee, resultBinding);
        if (!callee.params.empty() && callee.params[0].type.isRegion())
            return callResource(expression, callee, resultBinding);
        if (callee.result.isClass() && !resultBinding)
            fail(expression->token, "class-returning call requires a typed local initializer");
        if (resultBinding)
            match(callee.result, resultBinding->type, expression->token);
        arity(expression, callee.params.size());
        const bool borrowed = !callee.params.empty() && callee.params.front().borrowed;
        const std::size_t first = borrowed ? 1 : 0;
        int root = -1, loanId = 0;
        if (borrowed) {
            const auto &argument = expression->args.front();
            if (argument->op != "name")
                fail(argument->token, "borrowed object argument requires a complete named owning object");
            root = source(argument);
            match(locals[root].type, callee.params.front().type, argument->token);
            const bool mutableLoan = !callee.params.front().borrowConst;
            if (mutableLoan) {
                if (!locals[root].mut)
                    fail(argument->token, "mutable borrowed parameter requires a mutable owning object");
                requireUnborrowed(root, -1, argument->token);
                locals[root].objectExclusive = true;
            } else
                ++locals[root].objectShared;
            loanId = nextObjectLoan++;
            emit(ir::AcquireObjectLoan{loanId, offset(root), mutableLoan});
        }
        std::vector<int> arguments(callee.params.size() - first, 0);
        std::vector<int> spanArguments(callee.params.size() - first, 0), spanBorrows;
        std::vector<int> snapshots;
        bool aggregate = !borrowed && callee.result.isClass();
        for (std::size_t index = first; index < callee.params.size(); ++index) {
            const auto &type = callee.params[index].type;
            const auto &argument = expression->args[index];
            if (type.isSpan()) {
                aggregate = true;
                const int borrowed = acquireSpan(argument);
                spanArguments[index - first] = offset(borrowed);
                spanBorrows.push_back(borrowed);
            } else if (type.isClass()) {
                aggregate = true;
                if (argument->op != "name")
                    fail(argument->token, "class argument requires a complete local name");
                const int original = source(argument);
                match(locals[original].type, type, argument->token);
                const int snapshot = add("", type, false, argument->token, false);
                copyClass(original, snapshot, argument->token);
                arguments[index - first] = offset(snapshot);
                snapshots.push_back(offset(snapshot));
            } else {
                match(this->expression(argument), type, argument->token);
                push();
            }
        }
        int destination = 0;
        if (resultBinding) {
            const int local = add(resultBinding->name,
                                  resultBinding->type,
                                  resultBinding->mutableValue,
                                  resultBinding->token,
                                  bindResult);
            destination = offset(local);
            if (resultLocal)
                *resultLocal = local;
        }
        if (borrowed) {
            emit(ir::BorrowedCall{callee.name,
                                  offset(root),
                                  loanId,
                                  aggregate ? arguments : std::vector<int>{},
                                  destination,
                                  spanBorrows.empty() ? std::vector<int>{} : spanArguments});
            emit(ir::ReleaseObjectLoan{loanId});
            if (callee.params.front().borrowConst)
                --locals[root].objectShared;
            else
                locals[root].objectExclusive = false;
        } else if (aggregate)
            emit(ir::AggregateCall{callee.name, arguments, destination, spanArguments});
        else
            emit(ir::Call{callee.name});
        for (int snapshot : snapshots)
            emit(ir::EndObject{snapshot});
        for (auto it = spanBorrows.rbegin(); it != spanBorrows.rend(); ++it)
            releaseSpan(*it, true);
        return callee.result;
    }
    Type callOverloadedFunction(ExpressionPtr value,
                                const StatementPtr &resultBinding = nullptr,
                                bool bindResult = true,
                                int *resultLocal = nullptr) {
        // Resolve arity before touching arguments. Candidates are already restricted
        // to one defining declaration set and the caller's export visibility.
        std::vector<const Function *> candidates;
        for (const auto &name : value->overloadCandidates) {
            const auto found = functions.find(name);
            if (found == functions.end())
                fail(value->token, "unknown ordinary overload candidate");
            const auto &candidate = sourceFunctions[found->second];
            if (candidate.params.size() == value->args.size())
                candidates.push_back(&candidate);
        }
        if (candidates.empty())
            fail(value->token, "wrong argument count for " + value->token.text);
        std::vector<Type> types;
        std::vector<int> arguments(value->args.size(), 0), spanArguments(value->args.size(), 0);
        std::vector<int> snapshots, spanBorrows;
        bool aggregate = false;
        for (std::size_t index = 0; index < value->args.size(); ++index) {
            const auto &argument = value->args[index];
            const int local = argument->op == "name" ? lookupLocal(argument->token) : -1;
            const bool span = spanExpression(argument);
            if (span) {
                aggregate = true;
                const int borrowed = acquireSpan(argument);
                types.push_back(Type::ByteSpan);
                spanArguments[index] = offset(borrowed);
                spanBorrows.push_back(borrowed);
            } else if (local >= 0 && locals[local].type.isClass()) {
                aggregate = true;
                const int original = source(argument);
                const Type type = locals[original].type;
                types.push_back(type);
                const int snapshot = add("", type, false, argument->token, false);
                copyClass(original, snapshot, argument->token);
                arguments[index] = offset(snapshot);
                snapshots.push_back(offset(snapshot));
            } else {
                types.push_back(expression(argument));
                push();
            }
        }
        const Function *selected = nullptr;
        for (const auto *candidate : candidates) {
            bool exact = true;
            for (std::size_t index = 0; index < types.size(); ++index)
                exact = exact && types[index] == candidate->params[index].type;
            if (!exact)
                continue;
            if (selected)
                fail(value->token, "ambiguous exact ordinary overload");
            selected = candidate;
        }
        if (!selected)
            fail(value->token, "no exact ordinary overload for " + value->token.text);
        if (value->inaccessibleOverloads.contains(selected->name))
            fail(value->token, "function signature type requires a direct visible import");
        if (selected->result.isClass() && !resultBinding)
            fail(value->token, "class-returning call requires a typed local initializer");
        if (resultBinding)
            match(selected->result, resultBinding->type, value->token);
        int destination = 0;
        if (resultBinding) {
            const int local = add(resultBinding->name,
                                  resultBinding->type,
                                  resultBinding->mutableValue,
                                  resultBinding->token,
                                  bindResult);
            destination = offset(local);
            if (resultLocal)
                *resultLocal = local;
        }
        if (aggregate || selected->result.isClass())
            emit(ir::AggregateCall{selected->name, arguments, destination, spanArguments});
        else
            emit(ir::Call{selected->name});
        for (int snapshot : snapshots)
            emit(ir::EndObject{snapshot});
        for (auto it = spanBorrows.rbegin(); it != spanBorrows.rend(); ++it)
            releaseSpan(*it, true);
        return selected->result;
    }
    ir::Constant literal(const Token &token) {
        if (!token.text.empty() && token.text.front() == '\'') {
            const auto value = decodeByteLiteral(token.text);
            if (!value)
                fail(token, "invalid byte literal");
            return {*value, Type::U8};
        }
        const bool byteValue = token.text.ends_with("u8");
        const bool unsignedValue = byteValue || token.text.ends_with("u64");
        const auto suffixLength = byteValue ? 2 : unsignedValue ? 3 : 0;
        const auto digits = token.text.substr(0, token.text.size() - suffixLength);
        const auto value = decodeIntegerMagnitude(digits);
        if (!value)
            fail(token, "integer literal out of range or invalid suffix");
        if ((byteValue && *value > 255) ||
            (!unsignedValue && *value > static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max())))
            fail(token, "integer literal out of range or invalid suffix");
        return {std::bit_cast<std::int64_t>(*value), byteValue ? Type::U8 : unsignedValue ? Type::U64 : Type::I64};
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
        if (e->op == "number" || e->op == "byte") {
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
                emit(ir::IndexLoad{offset(storage.local), storage.type.length, Type(storage.type.elementKind)});
            return Type(storage.type.elementKind);
        }
        if (e->op == "array_literal")
            fail(e->token, "array literals require a typed local initializer");
        if (e->op == "byte_string")
            fail(e->token, "byte-string literals require a typed local u8 array initializer");
        if (e->op == "member") {
            if (e->args[0]->op != "name")
                fail(e->token, "field access currently requires a class local");
            int local = source(e->args[0]);
            if (locals[local].borrowedObject)
                fail(e->token, "borrowed object parameters support public methods, not field access");
            const auto &member = field(locals[local].type, e->token);
            if (member.type.isArray() || member.type.isClass() || member.type.isResource())
                fail(e->token, "aggregate fields require a fresh typed class projection or checked indexing");
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
                    if (member->type.isArray() || member->type.isClass() || member->type.isResource())
                        fail(e->token,
                             "aggregate fields require a fresh typed class projection or "
                             "checked indexing");
                    emit(ir::ReceiverLoad{member->index, member->type});
                    return member->type;
                }
            int i = source(e);
            if (locals[i].type.isArray())
                fail(e->token,
                     "array values are only supported in local initializers "
                     "and indexing");
            if (locals[i].type.isClass())
                fail(e->token,
                     "class values are only supported in local initializers "
                     "and field accesses");
            if (locals[i].type.isService())
                fail(e->token, "service capability is not a value");
            if (!scalarValue(locals[i].type))
                fail(e->token,
                     "owned values cannot be implicitly copied; use move, "
                     "read, or borrow");
            if (locals[i].type.isSpan())
                fail(e->token, "span capability cannot be used as a scalar value");
            emit(ir::Load{offset(i), payloadType(locals[i].type)});
            return locals[i].type;
        }
        if (e->op == "unary") {
            // Recognize the minimum signed literal before range-checking its positive
            // magnitude.
            if (n == "-" && e->args[0]->op == "number" && !e->args[0]->token.text.ends_with("u64") &&
                !e->args[0]->token.text.ends_with("u8")) {
                const auto &spelling = e->args[0]->token.text;
                std::optional<std::uint64_t> magnitude;
                if (spelling.starts_with("0b") || spelling.starts_with("0B")) {
                    magnitude = decodeIntegerMagnitude(spelling);
                    if (!magnitude)
                        fail(e->token, "integer literal out of range");
                } else {
                    // Preserve decimal diagnostics: a partial parse falls through
                    // to the whole number token, but magnitude overflow names '-'.
                    try {
                        std::size_t used = 0;
                        const auto value = std::stoull(spelling, &used);
                        if (used == spelling.size())
                            magnitude = value;
                    } catch (const std::exception &) {
                        fail(e->token, "integer literal out of range");
                    }
                }
                if (magnitude == (1ULL << 63)) {
                    emit(ir::Constant{std::numeric_limits<std::int64_t>::min(), Type::I64});
                    return Type::I64;
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
            if (n == "&&" || n == "||") {
                match(left, Type::Bool, e->token);
                const auto before = locals;
                const int end = fresh();
                if (n == "&&") {
                    emit(ir::BranchFalse{end});
                } else {
                    const int right = fresh();
                    emit(ir::BranchFalse{right});
                    emit(ir::Jump{end});
                    emit(ir::Label{right});
                }
                // Runtime laziness never suppresses type or lifetime checking.
                // Both paths preserve the existing operand stack; the current
                // bool is either the determining LHS or the evaluated RHS.
                match(expression(e->args[1]), Type::Bool, e->token);
                for (std::size_t index = 0; index < before.size(); ++index) {
                    if (locals[index].shared != before[index].shared ||
                        locals[index].exclusive != before[index].exclusive ||
                        locals[index].objectShared != before[index].objectShared ||
                        locals[index].objectExclusive != before[index].objectExclusive ||
                        locals[index].spanOrigin != before[index].spanOrigin ||
                        locals[index].spanField != before[index].spanField ||
                        locals[index].owner != before[index].owner)
                        fail(e->token, "logical paths must preserve the same borrow state");
                    if (ownerType(locals[index].type) && locals[index].live != before[index].live)
                        fail(e->token, "logical paths must preserve exact byte ownership state");
                    locals[index].live = locals[index].live && before[index].live;
                }
                emit(ir::Label{end});
                return Type::Bool;
            }
            push();
            const auto right = expression(e->args[1]);
            if (n == "<<" || n == ">>") {
                if (left != Type::U64 && left != Type::U8)
                    fail(e->token, "expected u64 or u8 shift operand");
                match(right, Type::I64, e->token);
                emit(ir::BinaryValue{n == "<<" ? ir::Binary::ShiftLeft : ir::Binary::ShiftRight, left});
                return left;
            }
            match(right, left, e->token);
            static const std::map<std::string, ir::Binary> operations = {{"+", ir::Binary::CheckedAdd},
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
            if (n != "==" && n != "!=" && left != Type::I64 && left != Type::U64 && left != Type::U8)
                fail(e->token, "expected i64, u64 or u8 ordered comparison operands");
            static const std::map<std::string, ir::Comparison> comparisons = {{"==", ir::Comparison::Equal},
                                                                              {"!=", ir::Comparison::NotEqual},
                                                                              {"<", ir::Comparison::Less},
                                                                              {">", ir::Comparison::Greater},
                                                                              {"<=", ir::Comparison::LessEqual},
                                                                              {">=", ir::Comparison::GreaterEqual}};
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
            const Field *member = lookupLocal(e->args[0]->token) < 0 ? receiverField(e->args[0]->token) : nullptr;
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
            emit(ir::MetadataQuery{n == "reflect_size" ? ir::Query::Size : ir::Query::PublicFieldCount,
                                   lowered.moduleScope});
            return Type::I64;
        }
        if (n == "own" || n == "move" || n == "borrow" || n == "borrow_mut")
            fail(e->token,
                 "ownership constructors are only supported in typed local "
                 "initializers");
        if (!e->overloadCandidates.empty())
            return callOverloadedFunction(e);
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
        if (e->op == "number" || e->op == "byte")
            return literal(e->token);
        if (e->op == "call" && (name == "size_of" || name == "type_id" || name == "field_count"))
            return {reflectedValue(e), Type::I64};
        if (e->op == "binary") {
            const auto left = constant(e->args[0]), right = constant(e->args[1]);
            match(right.type, left.type, e->token);
            if (name == "&&" || name == "||") {
                match(left.type, Type::Bool, e->token);
                return {name == "&&" ? left.value && right.value : left.value || right.value, Type::Bool};
            }
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
                fail(e->token, "static_assert supports literals, reflection, comparisons, !, && and || only");
            };
            const bool result = left.type == Type::U64 ? compare(std::bit_cast<std::uint64_t>(left.value),
                                                                 std::bit_cast<std::uint64_t>(right.value))
                                                       : compare(left.value, right.value);
            return {result, Type::Bool};
        }
        if (e->op == "unary" && name == "!") {
            const auto operand = constant(e->args[0]);
            match(operand.type, Type::Bool, e->token);
            return {!operand.value, Type::Bool};
        }
        fail(e->token, "static_assert supports literals, reflection, comparisons, !, && and || only");
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
            if (l.borrowedObject)
                continue;
            if (ownerType(l.type)) {
                if (!terminal)
                    endOwner(local);
                l.live = l.resourceActive = false;
                continue;
            }
            if (l.type.isSpan()) {
                if (l.live)
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
    void assignClassField(int receiverOffset, const Field &member, ExpressionPtr value) {
        if (owningClass(member.type))
            fail(value->token, "owning class field reassignment is unsupported");
        if (value->op != "name")
            fail(value->token, "class field assignment requires a complete local name");
        const int original = source(value);
        match(locals[original].type, member.type, value->token);
        emit(ir::AssignObjectField{receiverOffset, member.index, offset(original)});
    }
    // Both local construction and direct copied-value returns use the same
    // left-to-right argument snapshots and complete constructor initialization.
    int initializeCopiedConstructor(ExpressionPtr expression,
                                    const Type &type,
                                    const Token &bindingToken,
                                    const std::string &name = "",
                                    bool mutableValue = false,
                                    bool bind = false) {
        match(expression->reflectedType, type, expression->token);
        const auto &constructor = method(type, expression->token, true);
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
                copyClass(original, snapshot, argument->token);
                arguments[index] = offset(snapshot);
                snapshots.push_back(offset(snapshot));
            } else {
                match(this->expression(argument), type, expression->token);
                push();
            }
        }
        const int destination = add(name, type, mutableValue, bindingToken, bind);
        emit(ir::MethodCall{constructor.name, offset(destination), aggregate ? arguments : std::vector<int>{}});
        for (const int snapshot : snapshots)
            emit(ir::EndObject{snapshot});
        return destination;
    }
    int initializeCopiedCall(ExpressionPtr expression, const Type &type, const Token &token) {
        auto binding = std::make_shared<Statement>(token);
        binding->type = type;
        binding->mutableValue = false;
        int destination = -1;
        if (expression->op == "method_call" || expression->op == "implicit_method_call")
            callMethod(expression, binding, false, &destination);
        else if (!expression->overloadCandidates.empty())
            callOverloadedFunction(expression, binding, false, &destination);
        else {
            const auto found = functions.find(expression->resolvedName);
            if (found == functions.end())
                fail(expression->token, "direct copied return requires a class-returning function");
            callFunction(expression, sourceFunctions[found->second], binding, false, &destination);
        }
        return destination;
    }
    void initializeClass(StatementPtr statement) {
        const auto &definition = classDefinition(statement->type, statement->token);
        const auto expression = statement->expr;
        if (owningClass(statement->type) && expression->op == "call" && expression->token.text == "move") {
            const int original = movedOwner(expression, statement->type);
            const int destination = add(statement->name, statement->type, statement->mutableValue, statement->token);
            moveOwner(original, destination);
            return;
        }
        if (expression->op == "method_call" || expression->op == "implicit_method_call") {
            callMethod(expression, statement);
            return;
        }
        if (expression->op == "member" || (expression->op == "name" && lookupLocal(expression->token) < 0)) {
            int original = 0;
            const Field *member = nullptr;
            if (expression->op == "member") {
                if (expression->args[0]->op != "name")
                    fail(expression->token, "class projection requires a named local receiver");
                const int local = source(expression->args[0]);
                if (locals[local].borrowedObject)
                    fail(expression->token, "borrowed object parameters support public methods, not field projections");
                original = offset(local);
                member = &field(locals[local].type, expression->token);
            } else {
                member = receiverField(expression->token);
                if (!member)
                    fail(expression->token, "class projection requires a class field");
            }
            match(member->type, statement->type, expression->token);
            if (owningClass(member->type))
                fail(expression->token, "owning field extraction is unsupported");
            const int destination = add(statement->name, statement->type, statement->mutableValue, statement->token);
            emit(ir::ObjectFieldCopy{original, member->index, offset(destination)});
            return;
        }
        if (expression->op == "name") {
            const int original = source(expression);
            match(locals[original].type, statement->type, expression->token);
            const int destination = add(statement->name, statement->type, statement->mutableValue, statement->token);
            copyClass(original, destination, expression->token);
            return;
        }
        if (expression->op == "call") {
            if (!expression->overloadCandidates.empty()) {
                callOverloadedFunction(expression, statement);
                return;
            }
            const auto found = functions.find(expression->resolvedName);
            if (found == functions.end())
                fail(expression->token, "class initializer requires a class-returning function");
            callFunction(expression, sourceFunctions[found->second], statement);
            return;
        }
        if (expression->op == "constructor_call") {
            if (owningClass(statement->type)) {
                match(expression->reflectedType, statement->type, expression->token);
                const auto &constructor = method(statement->type, expression->token, true);
                callResource(expression, constructor, statement);
                return;
            }
            initializeCopiedConstructor(
                expression, statement->type, statement->token, statement->name, statement->mutableValue, true);
            return;
        }
        if (std::any_of(definition.methods.begin(), definition.methods.end(), [](const Function &method) {
                return method.constructor;
            }))
            fail(expression->token, "constructor-bearing class rejects designated initialization");
        if (std::any_of(definition.fields.begin(), definition.fields.end(), [](const Field &field) {
                return !field.publicAccess;
            }))
            fail(statement->token,
                 "class construction requires public fields; private "
                 "construction requires a declared constructor");
        if (expression->op != "construct")
            fail(expression->token,
                 "class local requires named-field construction "
                 "or same-type class copy");
        match(expression->reflectedType.isClass() ? expression->reflectedType : Type(expression->token.text),
              statement->type,
              expression->token);
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
        const int destination = add(statement->name, statement->type, statement->mutableValue, statement->token);
        for (std::size_t index = expression->args.size(); index > 0; --index) {
            const auto &member =
                field(statement->type, Token(expression->fieldNames[index - 1], expression->token.line));
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
            const int destination = add(statement->name, type, statement->mutableValue, statement->token);
            for (int index = 0; index < type.length; ++index) {
                emit(ir::Load{offset(original) - index * ir::storageWidth(Type(type.elementKind)),
                              Type(type.elementKind)});
                emit(ir::Store{offset(destination) - index * ir::storageWidth(Type(type.elementKind)),
                               Type(type.elementKind)});
            }
            return;
        }
        if (expression->op == "byte_string") {
            if (type.elementKind != TypeKind::U8)
                fail(expression->token, "byte-string initializers require u8 array elements");
            const auto bytes = decodeByteStringLiteral(expression->token.text);
            if (!bytes)
                fail(expression->token, "invalid byte-string literal");
            if (bytes->size() != static_cast<std::size_t>(type.length))
                fail(expression->token, "array initializer length does not match its declared type");
            for (const auto value : *bytes) {
                emit(ir::Constant{value, Type::U8});
                push();
            }
        } else {
            if (expression->op != "array_literal")
                fail(expression->token, "array local requires an array literal or same-type array copy");
            if (expression->args.size() != static_cast<std::size_t>(type.length))
                fail(expression->token, "array initializer length does not match its declared type");
            for (const auto &value : expression->args) {
                match(this->expression(value), Type(type.elementKind), value->token);
                push();
            }
        }
        const int destination = add(statement->name, type, statement->mutableValue, statement->token);
        for (int index = type.length - 1; index >= 0; --index) {
            pop();
            emit(ir::Store{offset(destination) - index * ir::storageWidth(Type(type.elementKind)),
                           Type(type.elementKind)});
        }
    }
    bool statement(StatementPtr s) {
        if (s->kind == "return") {
            if (result.isSpan()) {
                const int local = s->expr->op == "name" ? source(s->expr) : acquireSpan(s->expr);
                if (!locals[local].type.isSpan() || locals[local].spanOrigin != -2 || locals[local].spanField < 0)
                    fail(s->token, "returned span must derive directly from one private receiver owned-byte field");
                const int fieldIndex = locals[local].spanField;
                if (lowered.receiverSpanField && *lowered.receiverSpanField != fieldIndex)
                    fail(s->token, "all returned spans must derive from the same receiver owned-byte field");
                lowered.receiverSpanField = fieldIndex;
                endReturnBorrows(local);
                endReturnBytes();
                endReturnObjects();
                emit(ir::ReturnSpan{offset(local)});
                for (std::size_t index = locals.size(); index > 0; --index)
                    if (locals[index - 1].live && locals[index - 1].type.isSpan())
                        releaseSpan(static_cast<int>(index - 1), false);
            } else if (result.isBytes()) {
                const int local = movedBytes(s->expr);
                endReturnBorrows();
                endReturnBytes(local);
                emit(ir::ReturnBytes{offset(local)});
            } else if (owningClass(result)) {
                const int local = movedOwner(s->expr, result);
                endReturnBorrows();
                endReturnBytes(local);
                emit(ir::ReturnOwnedObject{offset(local)});
            } else if (result.isClass()) {
                int local;
                if (s->expr->op == "name")
                    local = source(s->expr);
                else if (s->expr->op == "constructor_call")
                    local = initializeCopiedConstructor(s->expr, result, s->token);
                else if (s->expr->op == "call" || s->expr->op == "method_call" || s->expr->op == "implicit_method_call")
                    local = initializeCopiedCall(s->expr, result, s->token);
                else
                    fail(s->token,
                         "class return requires a complete local name, direct copied-class constructor or ordinary "
                         "call");
                match(locals[local].type, result, s->token);
                endReturnBorrows();
                endReturnBytes();
                emit(ir::ReturnObject{offset(local)});
            } else {
                match(expression(s->expr), result, s->token);
                endReturnBorrows();
                endReturnBytes();
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
            if (s->type.isService())
                fail(s->token, "service capability cannot be stored in a local");
            if (s->type.isRegion())
                fail(s->token, "region authority is available only as the first function parameter");
            if (s->type.isBytes()) {
                initializeBytes(s);
                return false;
            }
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
                    if (locals[owner].exclusive || (s->type == Type::MutRef && locals[owner].shared))
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
            if (lintFunction && scalarValue(s->type) && !s->name.starts_with("_") && s->bindingSpan.source)
                lintBindings.emplace_back(i, s->bindingSpan);
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
                emit(ir::IndexStore{offset(storage.local), storage.type.length, Type(storage.type.elementKind)});
            return false;
        }
        if (s->kind == "while") {
            const auto start = fresh(), done = fresh();
            const auto incoming = locals;
            emit(ir::Label{start});
            match(expression(s->expr), Type::Bool, s->token);
            for (std::size_t index = 0; index < incoming.size(); ++index)
                if (ownerType(locals[index].type) && locals[index].live != incoming[index].live)
                    fail(s->token, "loop conditions cannot transfer an outer byte owner");
            emit(ir::BranchFalse{done});
            const bool alwaysReturns = block(s->body);
            if (!alwaysReturns) {
                for (std::size_t index = 0; index < incoming.size(); ++index) {
                    if (incoming[index].live != locals[index].live)
                        fail(s->token,
                             "loop backedge cannot move an outer owner; moves require a "
                             "returning path");
                    if (incoming[index].shared != locals[index].shared ||
                        incoming[index].exclusive != locals[index].exclusive ||
                        incoming[index].objectShared != locals[index].objectShared ||
                        incoming[index].objectExclusive != locals[index].objectExclusive)
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
            if (!locals[local].live)
                fail(s->token, "use after move of '" + s->name + "'");
            if (locals[local].borrowedObject)
                fail(s->token, "borrowed object parameters support public methods, not field assignment");
            if (!locals[local].mut)
                fail(s->token, "field assignment requires a mutable class local");
            requireNoObjectLoan(local, s->token);
            const auto &member = field(locals[local].type, Token(s->fieldName, s->token.line));
            if (member.type.isClass()) {
                assignClassField(offset(local), member, s->expr);
                return false;
            }
            if (member.type.isArray() || member.type.isResource())
                fail(s->token, "whole aggregate or resource field assignment is unsupported");
            match(expression(s->expr), member.type, s->token);
            if (!locals[local].live)
                fail(s->token, "field assignment value consumed the containing object");
            requireNoObjectLoan(local, s->token);
            emit(ir::Store{fieldOffset(local, member), member.type});
            return false;
        }
        if (s->kind == "assign") {
            const Token target(s->name, s->token.line);
            if (lookupLocal(target) < 0)
                if (const auto *member = receiverField(target)) {
                    if (currentFunction->receiverConst)
                        fail(target, "const method cannot write receiver fields");
                    if (member->type.isClass()) {
                        assignClassField(0, *member, s->expr);
                        return false;
                    }
                    if (member->type.isArray() || member->type.isResource())
                        fail(target, "whole aggregate or resource field assignment is unsupported");
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
                    if (locals[i].shared != yes[i].shared || locals[i].exclusive != yes[i].exclusive ||
                        locals[i].objectShared != yes[i].objectShared ||
                        locals[i].objectExclusive != yes[i].objectExclusive ||
                        locals[i].spanOrigin != yes[i].spanOrigin || locals[i].spanField != yes[i].spanField ||
                        locals[i].owner != yes[i].owner)
                        fail(s->token, "continuing branches must preserve the same borrow state");
                    if (ownerType(locals[i].type) && locals[i].live != yes[i].live)
                        fail(s->token, "continuing branches must preserve exact byte ownership state");
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
    explicit SemanticAnalyzer(Program program, AnalysisMode analysisMode = AnalysisMode::Check)
        : sourceFunctions(std::move(program.functions)), classes(std::move(program.classes)),
          enums(std::move(program.enums)), reflectionAccess(std::move(program.reflectionAccess)), mode(analysisMode) {
        for (const auto &definition : classes)
            for (const auto &method : definition.methods)
                sourceFunctions.push_back(method);
    }
    std::vector<Diagnostic> takeLintDiagnostics() {
        std::sort(lintDiagnostics.begin(), lintDiagnostics.end(), [](const auto &left, const auto &right) {
            return left.span.begin.offset < right.span.begin.offset;
        });
        return std::move(lintDiagnostics);
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
            if (enumNames.contains(definition.name) || definition.cases.empty() || definition.cases.size() > 256)
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
            if (builtins.contains(name) || name == "i64" || name == "u64" || name == "bool" || name == "ref" ||
                name == "mutref" || name == "array" || classNames.contains(name))
                fail(definition.token, "duplicate or reserved class name");
            classNames[name] = index;
            definition.id = 100 + static_cast<int>(index);
        }
        for (const auto &definition : classes)
            buildClassLayout(definition.name);
        classStorage = ir::computeClassStorageLayouts(classLeaves, classShapes);
        auto checkTemplateOwners = [&](const std::vector<TemplateArgument> &arguments, const Token &token) {
            for (const auto &argument : arguments)
                if (argument.kind == TemplateArgumentKind::Type && argument.type == TypeKind::Class &&
                    owningClass(Type(argument.className)))
                    fail(token, "owning classes cannot be template arguments");
        };
        for (const auto &definition : classes) {
            checkTemplateOwners(definition.templateArguments, definition.token);
            const bool composed =
                std::any_of(definition.fields.begin(), definition.fields.end(), [](const Field &member) {
                    return member.type.isClass();
                });
            if ((composed || owningClass(Type(definition.name))) &&
                classStorage.at(definition.name).reservedBytes > maximumCopiedClassBytes)
                fail(definition.token, "composed or owning class storage exceeds 520 bytes");
        }
        for (auto &definition : classes)
            for (auto &member : definition.fields)
                member.offset = classStorage.at(definition.name).fieldOffsets.at(member.index);
        // Validate receiver-return summaries before lowering any ordinary caller.
        // Returning through another span-result method is deliberately excluded.
        std::stable_partition(sourceFunctions.begin(), sourceFunctions.end(), [](const Function &function) {
            return function.result.isSpan();
        });
        for (std::size_t i = 0; i < sourceFunctions.size(); ++i) {
            if (builtins.count(sourceFunctions[i].name) || functions.count(sourceFunctions[i].name) ||
                classNames.count(sourceFunctions[i].name))
                fail(sourceFunctions[i].token, "duplicate or reserved function name");
            if (sourceFunctions[i].params.size() > 6)
                fail(sourceFunctions[i].token, "at most six parameters supported");
            const auto &candidate = sourceFunctions[i];
            checkTemplateOwners(candidate.templateArguments, candidate.token);
            const auto borrowedCount =
                std::count_if(candidate.params.begin(), candidate.params.end(), [](const Param &parameter) {
                    return parameter.borrowed;
                });
            const bool serviceFunction = !candidate.params.empty() && candidate.params.front().type.isService();
            if (candidate.result.isService())
                fail(candidate.token, "service capabilities cannot be returned");
            if (serviceFunction) {
                std::set<service::Kind> kinds;
                std::size_t serviceCount = 0;
                while (serviceCount < candidate.params.size() && candidate.params[serviceCount].type.isService()) {
                    const auto &parameter = candidate.params[serviceCount];
                    if (!parameter.borrowed || parameter.borrowConst)
                        fail(candidate.token,
                             "service functions require one leading exclusive sealed service reference and copied "
                             "result");
                    if (!kinds.insert(service::kind(parameter.type)).second)
                        fail(candidate.token, "service group requires distinct leading exclusive sealed references");
                    ++serviceCount;
                }
                if (serviceCount > 2 || !service::supportedGroup(kinds) ||
                    static_cast<std::size_t>(borrowedCount) != serviceCount || !candidate.receiverClass.empty() ||
                    candidate.constructor || !candidate.templateArguments.empty() ||
                    !candidate.templateParameters.empty() ||
                    (!scalarValue(candidate.result) &&
                     !(kinds.contains(service::Kind::Console) && candidate.result == service::sampleType()) &&
                     !(kinds.contains(service::Kind::IommuEvent) && candidate.result == service::eventSampleType())))
                    fail(candidate.token,
                         "service functions require a leading exclusive sealed service group and copied result");
                for (std::size_t index = serviceCount; index < candidate.params.size(); ++index)
                    if (!scalarValue(candidate.params[index].type) && !candidate.params[index].type.isSpan())
                        fail(candidate.token,
                             "service helper parameters require scalars, enums or readonly byte spans");
            } else {
                for (const auto &parameter : candidate.params)
                    if (parameter.type.isService())
                        fail(candidate.token, "service capability must be the leading exclusive parameter");
            }
            if (borrowedCount && !serviceFunction) {
                if (borrowedCount != 1 || candidate.params.empty() || !candidate.params.front().borrowed ||
                    !candidate.receiverClass.empty() || candidate.constructor || !candidate.templateArguments.empty() ||
                    !candidate.templateParameters.empty() || !owningClass(candidate.params.front().type) ||
                    (!scalarValue(candidate.result) && !candidate.result.isClass()) || owningClass(candidate.result))
                    fail(candidate.token,
                         "borrowed functions require one leading concrete owning-class reference "
                         "and a scalar or copied result");
                const auto &definition = classDefinition(candidate.params.front().type, candidate.token);
                if (!definition.templateArguments.empty() || !definition.templateParameters.empty())
                    fail(candidate.token, "borrowed parameters cannot name a class template");
                for (std::size_t index = 1; index < candidate.params.size(); ++index) {
                    const auto &type = candidate.params[index].type;
                    if ((!scalarValue(type) && !type.isClass() && !type.isSpan()) || owningClass(type))
                        fail(candidate.token,
                             "later borrowed-function parameters require scalar, copied class or readonly span values");
                }
            }
            for (const auto &parameter : candidate.params)
                if (parameter.borrowConst && !parameter.borrowed)
                    fail(candidate.token, "const borrowed permission requires a borrowed parameter");
            const bool resourceConstructor = candidate.constructor && owningClass(Type(candidate.receiverClass));
            const bool resource =
                candidate.result.isResource() || owningClass(candidate.result) ||
                std::any_of(candidate.params.begin(), candidate.params.end(), [&](const Param &parameter) {
                    return !parameter.borrowed && (parameter.type.isResource() || owningClass(parameter.type));
                });
            if (resource || resourceConstructor) {
                if ((!candidate.receiverClass.empty() && !resourceConstructor) ||
                    !candidate.templateArguments.empty() || !candidate.templateParameters.empty() ||
                    candidate.params.empty() || !candidate.params[0].type.isRegion() ||
                    (!scalarValue(candidate.result) && !ownerType(candidate.result) && !candidate.result.isClass()))
                    fail(candidate.token,
                         "resource functions and owning constructors require one first region "
                         "parameter and scalar, copied class or owning result");
                for (std::size_t index = 1; index < candidate.params.size(); ++index)
                    if (!scalarValue(candidate.params[index].type) && !candidate.params[index].type.isBytes() &&
                        !(resourceConstructor
                              ? candidate.params[index].type.isClass() && !owningClass(candidate.params[index].type)
                              : owningClass(candidate.params[index].type)))
                        fail(candidate.token, "resource arguments require scalar values or moved owners");
                if (resourceConstructor && candidate.result != Type::I64)
                    fail(candidate.token, "owning constructor requires its internal scalar result");
            }
            if (candidate.result.isSpan() &&
                (candidate.receiverClass.empty() || candidate.constructor || !candidate.receiverConst ||
                 !owningClass(Type(candidate.receiverClass)) || !candidate.templateArguments.empty() ||
                 !candidate.templateParameters.empty()))
                fail(candidate.token, "span results require a const non-template owning-class method");
            if (!candidate.receiverClass.empty() && !resourceConstructor) {
                if ((!scalarValue(candidate.result) && !candidate.result.isClass() && !candidate.result.isSpan()) ||
                    owningClass(candidate.result))
                    fail(candidate.token, "methods require scalar, enum or copyable class results");
                for (const auto &parameter : candidate.params)
                    if ((!scalarValue(parameter.type) && !parameter.type.isClass() && !parameter.type.isSpan()) ||
                        owningClass(parameter.type))
                        fail(candidate.token, "methods require scalar, enum or copyable class parameters");
            }
            auto checkBoundaryType = [&](const Type &type) {
                if (!type.isClass())
                    return;
                const auto &name = classDefinition(type, sourceFunctions[i].token).name;
                if (!ir::copiedClassLeavesSupported(classLeaves.at(name)))
                    fail(sourceFunctions[i].token,
                         "function-boundary classes are limited to 64 "
                         "scalar fields excluding u8, 512 u8 leaves and "
                         "513 total leaves");
                if (classStorage.at(name).reservedBytes > maximumCopiedClassBytes)
                    fail(sourceFunctions[i].token, "function-boundary class storage exceeds 520 bytes");
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
            lintFunction = mode == AnalysisMode::Lint && function.moduleScope == 0 &&
                           function.templateArguments.empty() && !function.constructor;
            if (lintFunction && !function.receiverClass.empty())
                lintFunction = classes.at(classNames.at(function.receiverClass)).templateArguments.empty();
            readLocals.clear();
            lintBindings.clear();
            locals.clear();
            scopes.clear();
            scopes.emplace_back();
            slot = 0;
            nextObjectLoan = 1;
            lowered = ir::Function{};
            lowered.name = function.name;
            lowered.moduleScope = function.moduleScope;
            lowered.result = function.result;
            const bool borrowed = !function.params.empty() && function.params.front().borrowed &&
                                  !function.params.front().type.isService();
            if (!function.receiverClass.empty())
                lowered.receiver = ir::Receiver{
                    function.receiverClass, !function.receiverConst, function.constructor, function.publicAccess};
            else if (borrowed) {
                lowered.receiver =
                    ir::Receiver{function.params.front().type.className, !function.params.front().borrowConst, false};
                lowered.borrowedParameter = true;
            }
            result = function.result;
            for (const auto &parameter : function.params)
                if (!parameter.borrowed || parameter.type.isService())
                    lowered.parameters.push_back(parameter.type);
            for (std::size_t index = 0; index < function.params.size(); ++index) {
                const auto &parameter = function.params[index];
                if (parameter.borrowed && !parameter.type.isService()) {
                    Local alias;
                    alias.name = parameter.name;
                    alias.type = parameter.type;
                    alias.mut = !parameter.borrowConst;
                    alias.borrowedObject = true;
                    scopes.back()[parameter.name] = static_cast<int>(locals.size());
                    locals.push_back(std::move(alias));
                    continue;
                }
                const int parameterIndex = static_cast<int>(index) - (borrowed ? 1 : 0);
                const int local = add(parameter.name,
                                      parameter.type,
                                      ownerType(parameter.type),
                                      function.token,
                                      true,
                                      !parameter.type.isClass() && !parameter.type.isBytes());
                if (parameter.type.isService())
                    emit(ir::BindServiceParameter{parameterIndex, offset(local), service::kind(parameter.type)});
                else if (parameter.type.isRegion())
                    emit(ir::BindRegionParameter{parameterIndex, offset(local)});
                else if (parameter.type.isBytes()) {
                    locals[local].owner = 0;
                    emit(ir::BindBytesParameter{parameterIndex, offset(local)});
                } else if (parameter.type.isSpan())
                    emit(ir::BindSpanParameter{parameterIndex, offset(local)});
                else if (owningClass(parameter.type)) {
                    locals[local].owner = 0;
                    emit(ir::BindOwnedObjectParameter{parameterIndex, offset(local), parameter.type.className});
                } else if (parameter.type.isClass())
                    emit(ir::BindObjectParameter{parameterIndex, offset(local), parameter.type.className});
                else
                    emit(ir::BindParameter{parameterIndex, offset(local), parameter.type});
            }
            if (function.constructor) {
                const auto &definition = classDefinition(Type(function.receiverClass), function.token);
                std::map<std::string, ExpressionPtr> initializers;
                for (const auto &[field, value] : function.initializers) {
                    const auto found =
                        std::find_if(definition.fields.begin(), definition.fields.end(), [&](const Field &member) {
                            return member.token.text == field.text;
                        });
                    if (found == definition.fields.end())
                        fail(field, "unknown constructor field initializer");
                    if (!initializers.emplace(field.text, value).second)
                        fail(field, "duplicate constructor field initializer");
                }
                if (initializers.size() != definition.fields.size())
                    fail(function.token, "constructor must initialize every field exactly once");
                for (const auto &member : definition.fields) {
                    const auto &initializer = initializers.at(member.token.text);
                    if (member.type.isBytes()) {
                        const int original = movedBytes(initializer);
                        if (locals[original].owner != 0)
                            fail(initializer->token, "constructor byte field belongs to a different region");
                        emit(ir::InitializeBytesField{0, member.index, offset(original)});
                        locals[original].live = false;
                    } else if (member.type.isClass()) {
                        if (initializer->op != "name")
                            fail(initializer->token, "class field initializer requires a complete named class value");
                        const int original = source(initializer);
                        match(locals[original].type, member.type, initializer->token);
                        emit(ir::InitializeObjectField{0, member.index, offset(original)});
                    } else if (member.type.isArray()) {
                        if (initializer->op != "array_zero")
                            fail(member.token, "array fields require explicit empty-brace zero initialization");
                        emit(ir::ReceiverArrayZero{member.index});
                    } else {
                        if (initializer->op == "array_zero")
                            fail(member.token,
                                 "empty-brace constructor initialization is "
                                 "restricted to array fields");
                        match(expression(initializer), member.type, member.token);
                        emit(ir::ReceiverStore{member.index, member.type});
                    }
                }
                emit(ir::Constant{0, Type::I64});
                endReturnBytes();
                emit(ir::Return{});
            } else if (!block(function.body))
                fail(function.token, "function must return on every path");
            if (function.result.isSpan()) {
                if (!lowered.receiverSpanField)
                    fail(function.token, "span-result method has no verified receiver-field return");
                receiverSpanFields[function.name] = *lowered.receiverSpanField;
            }
            lowered.frameBytes = ((slot * 8 + 15) / 16) * 16;
            module.functions.push_back(std::move(lowered));
            for (const auto &[local, span] : lintBindings)
                if (!readLocals.contains(local))
                    lintDiagnostics.push_back({DiagnosticCode::UnreadLocal,
                                               "local binding '" + locals[local].name + "' is never read",
                                               span,
                                               DiagnosticSeverity::Warning});
        }
        for (int id = 1; id <= 5; ++id)
            module.descriptors[id] = ir::Descriptor{id == 2 ? 1 : 8, 0};
        module.descriptors[8] = ir::Descriptor{8, 0};
        module.descriptors[static_cast<int>(TypeKind::U8) + 1] = ir::Descriptor{1, 0};
        for (const auto &definition : classes) {
            const Type type(definition.name);
            module.descriptors[definition.id] =
                ir::Descriptor{typeSize(type, definition.token), fieldCount(type, definition.token)};
        }
        for (const auto &definition : enums)
            module.descriptors[definition.id] = ir::Descriptor{8, 0};
        for (const auto &[id, type] : arrayTypes)
            module.descriptors[id] = ir::Descriptor{type.length * ir::storageWidth(Type(type.elementKind)), 0};
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
