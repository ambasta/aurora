#pragma once
#include "ir_verify.hpp"
#include "syntax.hpp"
#include <algorithm>
#include <limits>
#include <map>
#include <set>
namespace aurora {
class Local {
  public:
    std::string name;
    Type type;
    int offset = 0, owner = -1, shared = 0;
    bool mut = false, live = true, exclusive = false;
};
class SemanticAnalyzer {
    std::vector<Function> sourceFunctions;
    std::vector<ClassDefinition> classes;
    std::map<int, std::set<std::string>> reflectionAccess;
    std::map<std::string, std::size_t> classNames;
    std::map<int, Type> arrayTypes;
    static constexpr int maxFrameSlots = 8192;
    std::map<std::string, std::size_t> functions;
    std::vector<Local> locals;
    std::vector<std::map<std::string, int>> scopes;
    ir::Function lowered;
    int slot = 0, label = 0;
    Type result = Type::I64;

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
            const int id = 1000000 + type.length * 2 + (type.elementKind == TypeKind::Bool ? 1 : 0);
            arrayTypes[id] = type;
            return id;
        }
        if (type.isClass())
            return classDefinition(type, token).id;
        return static_cast<int>(type.kind) + 1;
    }
    std::int64_t typeSize(const Type &type, const Token &token) {
        if (type.isArray()) {
            typeId(type, token);
            return type.length * 8;
        }
        if (type.isClass())
            return std::max<std::int64_t>(8, classDefinition(type, token).fields.size() * 8);
        return type == Type::Bool ? 1 : 8;
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
                if (!value.publicAccess)
                    fail(token, "private class field is inaccessible");
                return value;
            }
        fail(token, "unknown field '" + token.text + "' in " + typeName(type));
    }
    int fieldOffset(int local, const Field &value) {
        return locals.at(local).offset - value.offset;
    }
    Type payloadType(const Type &type) {
        return type == Type::Own ? Type::I64 : type;
    }
    std::int64_t reflectedValue(ExpressionPtr expression) {
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
    int find(const Token &t) {
        for (auto i = scopes.rbegin(); i != scopes.rend(); ++i) {
            auto v = i->find(t.text);
            if (v != i->end())
                return v->second;
        }
        fail(t, "unknown local '" + t.text + "'");
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
    void push() {
        emit(ir::Push{});
    }
    void pop() {
        emit(ir::Pop{});
    }
    int add(const std::string &n, Type t, bool mut, const Token &tok) {
        if (scopes.back().count(n))
            fail(tok, "duplicate local '" + n + "'");
        Local l;
        l.name = n;
        l.type = t;
        l.mut = mut;
        const auto needed = (t.isClass() || t.isArray()) ? typeSize(t, tok) / 8 : 1;
        if (needed > maxFrameSlots || slot > maxFrameSlots - needed)
            fail(tok, "function local stack frame exceeds 65536 bytes");
        slot += static_cast<int>(needed);
        l.offset = 8 * slot;
        if (t.isClass()) {
            for (const auto &member : classDefinition(t, tok).fields)
                lowered.slots[l.offset - member.offset] = member.type;
        } else if (t.isArray()) {
            for (int index = 0; index < t.length; ++index)
                lowered.slots[l.offset - index * 8] = Type(t.elementKind);
        } else
            lowered.slots[l.offset] = payloadType(t);
        locals.push_back(l);
        int i = static_cast<int>(locals.size()) - 1;
        scopes.back()[n] = i;
        return i;
    }
    int checkedIndex(ExpressionPtr index) {
        if (index->args[0]->op != "name")
            fail(index->token, "indexing currently requires an array local");
        const int local = source(index->args[0]);
        const Type type = locals[local].type;
        if (!type.isArray())
            fail(index->token, "indexing requires an array local");
        match(expression(index->args[1]), Type::I64, index->token);
        // Unsigned comparison rejects negative i64 indices as well as upper-bound violations.
        // No address computation or memory access occurs before the guard.
        emit(ir::BoundsGuard{offset(local), type.length, Type(type.elementKind)});
        return local;
    }
    Type expression(ExpressionPtr e) {
        const auto &n = e->resolvedName.empty() ? e->token.text : e->resolvedName;
        if (e->op == "number") {
            unsigned long long value = 0;
            try {
                std::size_t used;
                auto v = std::stoull(n, &used);
                value = v;
                if (used != n.size() ||
                    v > static_cast<unsigned long long>(std::numeric_limits<std::int64_t>::max()))
                    fail(e->token, "integer literal out of range");
            } catch (const std::exception &) {
                fail(e->token, "integer literal out of range");
            }
            emit(ir::Constant{static_cast<std::int64_t>(value), Type::I64});
            return Type::I64;
        }
        if (e->op == "bool") {
            emit(ir::Constant{n == "true" ? 1 : 0, Type::Bool});
            return Type::Bool;
        }
        if (e->op == "index") {
            const int local = checkedIndex(e);
            emit(ir::IndexLoad{offset(local), locals[local].type.length,
                               Type(locals[local].type.elementKind)});
            return Type(locals[local].type.elementKind);
        }
        if (e->op == "array_literal")
            fail(e->token, "array literals require a typed local initializer");
        if (e->op == "member") {
            if (e->args[0]->op != "name")
                fail(e->token, "field access currently requires a class local");
            int local = source(e->args[0]);
            const auto &member = field(locals[local].type, e->token);
            emit(ir::Load{fieldOffset(local, member), member.type});
            return member.type;
        }
        if (e->op == "construct")
            fail(e->token, "class construction requires a typed local initializer");
        if (e->op == "name") {
            int i = source(e);
            if (locals[i].type.isArray())
                fail(e->token,
                     "array values are only supported in local initializers and indexing");
            if (locals[i].type.isClass())
                fail(e->token,
                     "class values are only supported in local initializers and field accesses");
            if (!scalar(locals[i].type))
                fail(e->token,
                     "owned values cannot be implicitly copied; use move, read, or borrow");
            emit(ir::Load{offset(i), payloadType(locals[i].type)});
            return locals[i].type;
        }
        if (e->op == "unary") {
            // Recognize the minimum signed literal before range-checking its positive magnitude.
            if (n == "-" && e->args[0]->op == "number") {
                try {
                    if (std::stoull(e->args[0]->token.text) == (1ULL << 63)) {
                        emit(ir::Constant{std::numeric_limits<std::int64_t>::min(), Type::I64});
                        return Type::I64;
                    }
                } catch (const std::exception &) {
                    fail(e->token, "integer literal out of range");
                }
            }
            auto t = expression(e->args[0]);
            match(t, n == "!" ? Type::Bool : Type::I64, e->token);
            emit(ir::UnaryValue{n == "!" ? ir::Unary::LogicalNot : ir::Unary::CheckedNegate});
            return t;
        }
        if (e->op == "binary") {
            auto l = expression(e->args[0]);
            push();
            auto r = expression(e->args[1]);
            match(r, l, e->token);
            if (n == "+" || n == "-" || n == "*") {
                match(l, Type::I64, e->token);
                emit(ir::BinaryValue{n == "+"   ? ir::Binary::CheckedAdd
                                     : n == "-" ? ir::Binary::CheckedSubtract
                                                : ir::Binary::CheckedMultiply});
                return Type::I64;
            }
            if (n != "==" && n != "!=")
                match(l, Type::I64, e->token);
            static const std::map<std::string, ir::Comparison> comparisons = {
                {"==", ir::Comparison::Equal},     {"!=", ir::Comparison::NotEqual},
                {"<", ir::Comparison::Less},       {">", ir::Comparison::Greater},
                {"<=", ir::Comparison::LessEqual}, {">=", ir::Comparison::GreaterEqual}};
            emit(ir::Compare{comparisons.at(n), l});
            return Type::Bool;
        }
        if (e->op != "call")
            fail(e->token, "invalid expression");
        if (n == "size_of" || n == "type_id" || n == "field_count") {
            emit(ir::Constant{reflectedValue(e), Type::I64});
            return Type::I64;
        }
        if (n == "len") {
            arity(e, 1);
            const int local = source(e->args[0]);
            if (!locals[local].type.isArray())
                fail(e->token, "len requires an array local");
            emit(ir::Constant{locals[local].type.length, Type::I64});
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
            fail(e->token, "ownership constructors are only supported in typed local initializers");
        auto f = functions.find(n);
        if (f == functions.end())
            fail(e->token, "unknown function '" + n + "'");
        auto &callee = sourceFunctions[f->second];
        arity(e, callee.params.size());
        for (std::size_t i = 0; i < e->args.size(); ++i) {
            match(expression(e->args[i]), callee.params[i].type, e->token);
            push();
        }
        emit(ir::Call{n});
        return callee.result;
    }
    std::int64_t constant(ExpressionPtr e) {
        auto n = e->token.text;
        if (e->op == "bool")
            return n == "true";
        if (e->op == "number") {
            expression(e);
            return std::stoll(n);
        }
        if (e->op == "call" && (n == "size_of" || n == "type_id" || n == "field_count"))
            return reflectedValue(e);
        if (e->op == "binary") {
            auto a = constant(e->args[0]), b = constant(e->args[1]);
            if (n == "==")
                return a == b;
            if (n == "!=")
                return a != b;
            if (n == "<")
                return a < b;
            if (n == ">")
                return a > b;
            if (n == "<=")
                return a <= b;
            if (n == ">=")
                return a >= b;
        }
        if (e->op == "unary" && n == "!")
            return !constant(e->args[0]);
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
        for (const auto &pair : scopes.back()) {
            auto &l = locals[pair.second];
            if (l.type == Type::Ref)
                --locals[l.owner].shared;
            if (l.type == Type::MutRef)
                locals[l.owner].exclusive = false;
        }
        scopes.pop_back();
        return terminal;
    }
    void initializeClass(StatementPtr statement) {
        const auto &definition = classDefinition(statement->type, statement->token);
        const auto expression = statement->expr;
        if (std::any_of(definition.fields.begin(), definition.fields.end(),
                        [](const Field &field) { return !field.publicAccess; }))
            fail(statement->token, "class construction requires public fields; private "
                                   "construction is not implemented");
        if (expression->op == "name") {
            const int original = source(expression);
            match(locals[original].type, statement->type, expression->token);
            const int destination =
                add(statement->name, statement->type, statement->mutableValue, statement->token);
            for (const auto &member : definition.fields) {
                emit(ir::Load{fieldOffset(original, member), member.type});
                emit(ir::Store{fieldOffset(destination, member), member.type});
            }
            return;
        }
        if (expression->op != "construct")
            fail(expression->token,
                 "class local requires named-field construction or same-type class copy");
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
                emit(ir::Load{offset(original) - index * 8, Type(type.elementKind)});
                emit(ir::Store{offset(destination) - index * 8, Type(type.elementKind)});
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
            emit(ir::Store{offset(destination) - index * 8, Type(type.elementKind)});
        }
    }
    bool statement(StatementPtr s) {
        if (s->kind == "return") {
            match(expression(s->expr), result, s->token);
            emit(ir::Return{});
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
            if (!v)
                fail(s->token, "static assertion failed");
            return false;
        }
        if (s->kind == "let") {
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
            if (scalar(s->type)) {
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
            const int local = checkedIndex(s->target);
            if (!locals[local].mut)
                fail(s->token, "index assignment requires a mutable array local");
            push();
            match(expression(s->expr), Type(locals[local].type.elementKind), s->token);
            emit(ir::IndexStore{offset(local), locals[local].type.length,
                                Type(locals[local].type.elementKind)});
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
            // The loop may execute zero times. Body-only return paths cannot invalidate exit state.
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
            match(expression(s->expr), member.type, s->token);
            emit(ir::Store{fieldOffset(local, member), member.type});
            return false;
        }
        if (s->kind == "assign") {
            int i = find(Token(s->name, s->token.line));
            if (!locals[i].mut || !scalar(locals[i].type))
                fail(s->token, "assignment requires a mutable scalar local");
            match(expression(s->expr), locals[i].type, s->token);
            emit(ir::Store{offset(i), payloadType(locals[i].type)});
            return false;
        }
        if (s->kind == "if") {
            match(expression(s->expr), Type::Bool, s->token);
            auto no = fresh(), end = fresh();
            emit(ir::BranchFalse{no}); // Branch-local borrows expire before joining. A moved owner
                                       // remains unavailable
            // on every continuing path; return-only paths do not constrain later uses.
            auto before = locals;
            bool yesReturn = block(s->body);
            auto yes = locals;
            emit(ir::Jump{end});
            emit(ir::Label{no});
            for (std::size_t i = 0; i < before.size(); ++i)
                locals[i] = before[i];
            bool noReturn = block(s->other);
            for (std::size_t i = 0; i < before.size(); ++i) {
                if (noReturn && !yesReturn)
                    locals[i].live = yes[i].live;
                else if (!yesReturn)
                    locals[i].live = locals[i].live && yes[i].live;
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
          reflectionAccess(std::move(program.reflectionAccess)) {}
    ir::ValidatedModule analyze() {
        static const std::set<std::string> builtins = {"own",
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
        if (classes.size() > 999900)
            throw Error("too many class types for bootstrap type IDs");
        for (std::size_t index = 0; index < classes.size(); ++index) {
            auto &definition = classes[index];
            if (definition.fields.size() > maxFrameSlots)
                fail(definition.token, "class layout exceeds 65536 bytes");
            const auto &name = definition.name;
            if (builtins.contains(name) || name == "i64" || name == "bool" || name == "ref" ||
                name == "mutref" || name == "array" || classNames.contains(name))
                fail(definition.token, "duplicate or reserved class name");
            classNames[name] = index;
            definition.id = 100 + static_cast<int>(index);
            std::set<std::string> fields;
            int offset = 0;
            for (auto &member : definition.fields) {
                if (!fields.insert(member.token.text).second)
                    fail(member.token, "duplicate class field");
                member.offset = offset;
                offset += 8;
            }
        }
        for (std::size_t i = 0; i < sourceFunctions.size(); ++i) {
            if (builtins.count(sourceFunctions[i].name) ||
                functions.count(sourceFunctions[i].name) ||
                classNames.count(sourceFunctions[i].name))
                fail(sourceFunctions[i].token, "duplicate or reserved function name");
            if (sourceFunctions[i].params.size() > 6)
                fail(sourceFunctions[i].token, "at most six parameters supported");
            functions[sourceFunctions[i].name] = i;
        }
        ir::Module module;
        for (auto &function : sourceFunctions) {
            locals.clear();
            scopes.clear();
            scopes.emplace_back();
            slot = 0;
            lowered = ir::Function{};
            lowered.name = function.name;
            lowered.moduleScope = function.moduleScope;
            lowered.result = function.result;
            result = function.result;
            for (const auto &parameter : function.params)
                lowered.parameters.push_back(parameter.type);
            for (std::size_t index = 0; index < function.params.size(); ++index) {
                const auto &parameter = function.params[index];
                const int local = add(parameter.name, parameter.type, false, function.token);
                emit(ir::BindParameter{static_cast<int>(index), offset(local), parameter.type});
            }
            if (!block(function.body))
                fail(function.token, "function must return on every path");
            lowered.frameBytes = ((slot * 8 + 15) / 16) * 16;
            module.functions.push_back(std::move(lowered));
        }
        for (int id = 1; id <= 5; ++id)
            module.descriptors[id] = ir::Descriptor{id == 2 ? 1 : 8, 0};
        for (const auto &definition : classes) {
            const Type type(definition.name);
            module.descriptors[definition.id] = ir::Descriptor{typeSize(type, definition.token),
                                                               fieldCount(type, definition.token)};
        }
        for (const auto &[id, type] : arrayTypes)
            module.descriptors[id] = ir::Descriptor{type.length * 8, 0};
        if (reflectionAccess.empty()) {
            auto &own = reflectionAccess[0];
            for (const auto &definition : classes)
                own.insert(definition.name);
        }
        module.descriptorViews.clear();
        for (const auto &[scope, visible] : reflectionAccess) {
            auto &view = module.descriptorViews[scope];
            for (const auto &[id, descriptor] : module.descriptors) {
                (void)descriptor;
                if (id <= 5 || id >= 1000000)
                    view.insert(id);
            }
            for (const auto &name : visible)
                view.insert(classes.at(classNames.at(name)).id);
        }
        return ir::validate(std::move(module));
    }
};

} // namespace aurora
