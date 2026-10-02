#include <algorithm>
#include <cctype>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <limits>
#include <map>
#include <memory>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

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
std::vector<Token> lex(const std::string &s) {
    std::vector<Token> out;
    int line = 1;
    for (std::size_t i = 0; i < s.size();) {
        unsigned char c = s[i];
        if (std::isspace(c)) {
            if (c == '\n')
                ++line;
            ++i;
            continue;
        }
        if (c == '/' && i + 1 < s.size() && s[i + 1] == '/') {
            while (i < s.size() && s[i] != '\n')
                ++i;
            continue;
        }
        if (std::isalpha(c) || c == '_') {
            auto b = i++;
            while (i < s.size() && (std::isalnum(static_cast<unsigned char>(s[i])) || s[i] == '_'))
                ++i;
            out.emplace_back(s.substr(b, i - b), line);
            continue;
        }
        if (std::isdigit(c)) {
            auto b = i++;
            while (i < s.size() && std::isdigit(static_cast<unsigned char>(s[i])))
                ++i;
            out.emplace_back(s.substr(b, i - b), line);
            continue;
        }
        auto two = s.substr(i, 2);
        if (two == "->" || two == "==" || two == "!=" || two == "<=" || two == ">=") {
            out.emplace_back(two, line);
            i += 2;
            continue;
        }
        if (std::string("(){}:;,=+-*<>!.").find(c) != std::string::npos) {
            out.emplace_back(std::string(1, c), line);
            ++i;
            continue;
        }
        throw Error("line " + std::to_string(line) + ": unsupported character");
    }
    out.emplace_back("<eof>", line);
    return out;
}
enum class TypeKind { I64, Bool, Own, Ref, MutRef, Class };
class Type {
  public:
    TypeKind kind = TypeKind::I64;
    std::string className;
    Type() = default;
    explicit Type(TypeKind value) : kind(value) {}
    explicit Type(std::string name) : kind(TypeKind::Class), className(std::move(name)) {}
    bool operator==(const Type &) const = default;
    bool isClass() const {
        return kind == TypeKind::Class;
    }
    static const Type I64, Bool, Own, Ref, MutRef;
};
const Type Type::I64{TypeKind::I64};
const Type Type::Bool{TypeKind::Bool};
const Type Type::Own{TypeKind::Own};
const Type Type::Ref{TypeKind::Ref};
const Type Type::MutRef{TypeKind::MutRef};
std::string typeName(const Type &type) {
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
    }
    return "?";
}
bool scalar(Type t) {
    return t == Type::I64 || t == Type::Bool;
}
class Expression {
  public:
    std::string op;
    Token token;
    std::vector<std::shared_ptr<Expression>> args;
    std::vector<std::string> fieldNames;
    Type reflectedType;
    Expression(std::string o, Token t) : op(std::move(o)), token(std::move(t)) {}
};
using ExpressionPtr = std::shared_ptr<Expression>;
class Statement {
  public:
    std::string kind, name, fieldName;
    Token token;
    Type type = Type::I64;
    bool mutableValue = false;
    ExpressionPtr expr;
    std::vector<std::shared_ptr<Statement>> body, other;
    explicit Statement(Token t) : kind(t.text), token(std::move(t)) {}
};
using StatementPtr = std::shared_ptr<Statement>;
class Param {
  public:
    std::string name;
    Type type;
};
class Function {
  public:
    std::string name;
    Token token;
    Type result;
    std::vector<Param> params;
    std::vector<StatementPtr> body;
    explicit Function(Token t) : name(t.text), token(std::move(t)), result(Type::I64) {}
};
class Field {
  public:
    Token token;
    Type type;
    int offset = 0;
    Field(Token name, Type value) : token(std::move(name)), type(std::move(value)) {}
};
class ClassDefinition {
  public:
    Token token;
    std::vector<Field> fields;
    int id = 0;
    explicit ClassDefinition(Token name) : token(std::move(name)) {}
};
class Program {
  public:
    std::vector<Function> functions;
    std::vector<ClassDefinition> classes;
};
class Parser {
    std::vector<Token> tokens;
    std::size_t position = 0;

  public:
    explicit Parser(std::vector<Token> t) : tokens(std::move(t)) {}
    Token peek() const {
        return tokens.at(position);
    }
    Token take() {
        return tokens.at(position++);
    }
    [[noreturn]] void fail(const std::string &m) const {
        throw Error("line " + std::to_string(peek().line) + ": " + m + " (found '" + peek().text +
                    "')");
    }
    bool eat(const std::string &s) {
        if (peek().text == s) {
            ++position;
            return true;
        }
        return false;
    }
    void need(const std::string &s) {
        // A generic type terminator can directly precede its initializer: own<i64>=own(1).
        if (s == ">" && peek().text == ">=") {
            tokens[position].text = "=";
            return;
        }
        if (!eat(s))
            fail("expected '" + s + "'");
    }
    Token ident() {
        auto t = peek();
        if (t.text.empty() ||
            !(std::isalpha(static_cast<unsigned char>(t.text[0])) || t.text[0] == '_'))
            fail("expected identifier");
        static const std::set<std::string> reserved = {"fn",    "module",        "let",    "mut",
                                                       "if",    "else",          "return", "true",
                                                       "false", "static_assert", "class"};
        if (reserved.count(t.text))
            fail("reserved identifier");
        return take();
    }
    Type type() {
        if (eat("i64"))
            return Type::I64;
        if (eat("bool"))
            return Type::Bool;
        auto t = take();
        Type v;
        if (t.text == "own")
            v = Type::Own;
        else if (t.text == "ref")
            v = Type::Ref;
        else if (t.text == "mutref")
            v = Type::MutRef;
        else {
            if (t.text.empty() ||
                !(std::isalpha(static_cast<unsigned char>(t.text[0])) || t.text[0] == '_'))
                fail("expected type name");
            if (peek().text == "<")
                fail("unsupported type " + t.text);
            return Type(t.text);
        }
        need("<");
        need("i64");
        need(">");
        return v;
    }
    ExpressionPtr postfix(ExpressionPtr expression) {
        while (eat(".")) {
            auto member = std::make_shared<Expression>("member", ident());
            member->args.push_back(expression);
            expression = member;
        }
        return expression;
    }
    ExpressionPtr primary() {
        auto t = take();
        auto e = std::make_shared<Expression>("name", t);
        if (t.text == "(") {
            e = expr();
            need(")");
            return postfix(e);
        }
        if (t.text == "-" || t.text == "!") {
            e->op = "unary";
            e->args.push_back(primary());
            return e;
        }
        if (std::isdigit(static_cast<unsigned char>(t.text[0]))) {
            e->op = "number";
            return e;
        }
        if (t.text == "true" || t.text == "false") {
            e->op = "bool";
            return e;
        }
        if (!(std::isalpha(static_cast<unsigned char>(t.text[0])) || t.text[0] == '_'))
            fail("expected expression");
        if (eat("(")) {
            e->op = "call";
            if (t.text == "size_of" || t.text == "type_id" || t.text == "field_count") {
                e->reflectedType = type();
                need(")");
            } else if (!eat(")")) {
                do {
                    e->args.push_back(expr());
                } while (eat(","));
                need(")");
            }
        }
        if (e->op == "name" && eat("{")) {
            e->op = "construct";
            if (!eat("}")) {
                do {
                    e->fieldNames.push_back(ident().text);
                    need(":");
                    e->args.push_back(expr());
                } while (eat(","));
                need("}");
            }
        }
        return postfix(e);
    }
    int precedence(const std::string &s) {
        if (s == "==" || s == "!=")
            return 1;
        if (s == "<" || s == ">" || s == "<=" || s == ">=")
            return 2;
        if (s == "+" || s == "-")
            return 3;
        if (s == "*")
            return 4;
        return 0;
    }
    ExpressionPtr expr(int min = 1) {
        auto e = primary();
        while (precedence(peek().text) >= min) {
            auto t = take();
            auto x = std::make_shared<Expression>("binary", t);
            x->args = {e, expr(precedence(t.text) + 1)};
            e = x;
        }
        return e;
    }
    std::vector<StatementPtr> block() {
        need("{");
        std::vector<StatementPtr> b;
        while (!eat("}")) {
            if (peek().text == "<eof>")
                fail("unterminated block");
            b.push_back(statement());
        }
        return b;
    }
    StatementPtr statement() {
        auto t = peek();
        auto s = std::make_shared<Statement>(t);
        if (t.text == "{") {
            s->kind = "block";
            s->body = block();
            return s;
        }
        take();
        if (t.text == "let") {
            s->mutableValue = eat("mut");
            s->name = ident().text;
            need(":");
            s->type = type();
            need("=");
            s->expr = expr();
            need(";");
        } else if (t.text == "return" || t.text == "static_assert") {
            if (t.text == "static_assert")
                need("(");
            s->expr = expr();
            if (t.text == "static_assert")
                need(")");
            need(";");
        } else if (t.text == "if") {
            need("(");
            s->expr = expr();
            need(")");
            s->body = block();
            if (eat("else"))
                s->other = block();
        } else {
            --position;
            s->kind = "expression";
            s->expr = expr();
            if (eat("=")) {
                if (s->expr->op == "member" && s->expr->args[0]->op == "name") {
                    s->kind = "field_assign";
                    s->fieldName = s->expr->token.text;
                    s->name = s->expr->args[0]->token.text;
                } else if (s->expr->op == "name") {
                    s->kind = "assign";
                    s->name = s->expr->token.text;
                } else
                    fail("assignment requires a local or local field");
                s->expr = expr();
            }
            need(";");
        }
        return s;
    }
    Program parse() {
        need("module");
        ident();
        while (eat("."))
            ident();
        need(";");
        Program program;
        while (peek().text != "<eof>") {
            if (eat("class")) {
                ClassDefinition definition(ident());
                need("{");
                while (!eat("}")) {
                    auto fieldName = ident();
                    need(":");
                    auto fieldType = type();
                    if (!scalar(fieldType))
                        fail("class fields currently require i64 or bool");
                    need(";");
                    definition.fields.emplace_back(fieldName, fieldType);
                }
                program.classes.push_back(std::move(definition));
                continue;
            }
            need("fn");
            Function f(ident());
            need("(");
            if (!eat(")")) {
                do {
                    Param a;
                    a.name = ident().text;
                    need(":");
                    a.type = type();
                    if (!scalar(a.type))
                        fail("only scalar function parameters are supported");
                    f.params.push_back(a);
                } while (eat(","));
                need(")");
            }
            need("->");
            f.result = type();
            if (!scalar(f.result))
                fail("only scalar function results are supported");
            f.body = block();
            program.functions.push_back(std::move(f));
        }
        if (program.functions.empty())
            fail("module must contain a function");
        return program;
    }
};
class Local {
  public:
    std::string name;
    Type type;
    int offset = 0, owner = -1, shared = 0;
    bool mut = false, live = true, exclusive = false;
};
class Compiler {
    std::vector<Function> fs;
    std::vector<ClassDefinition> classes;
    std::map<std::string, std::size_t> classNames;
    std::map<std::string, std::size_t> functions;
    std::vector<Local> locals;
    std::vector<std::map<std::string, int>> scopes;
    std::ostringstream out;
    int slot = 0, label = 0, depth = 0;
    Type result = Type::I64;
    std::string returnLabel;
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
        if (type.isClass())
            return classDefinition(type, token).id;
        return static_cast<int>(type.kind) + 1;
    }
    std::int64_t typeSize(const Type &type, const Token &token) {
        if (type.isClass())
            return std::max<std::int64_t>(8, classDefinition(type, token).fields.size() * 8);
        return type == Type::Bool ? 1 : 8;
    }
    std::int64_t fieldCount(const Type &type, const Token &token) {
        if (type.isClass())
            return classDefinition(type, token).fields.size();
        return 0;
    }
    const Field &field(const Type &type, const Token &token) {
        const auto &definition = classDefinition(type, token);
        for (const auto &value : definition.fields)
            if (value.token.text == token.text)
                return value;
        fail(token, "unknown field '" + token.text + "' in " + typeName(type));
    }
    std::string fieldAddress(int local, const Field &value) {
        return std::to_string(-locals.at(local).offset + value.offset) + "(%rbp)";
    }
    std::int64_t reflectedValue(ExpressionPtr expression) {
        if (expression->token.text == "type_id")
            return typeId(expression->reflectedType, expression->token);
        if (expression->token.text == "field_count")
            return fieldCount(expression->reflectedType, expression->token);
        return typeSize(expression->reflectedType, expression->token);
    }
    void emit(const std::string &s) {
        out << "    " << s << '\n';
    }
    std::string fresh() {
        return ".Lau" + std::to_string(label++);
    }
    std::string addr(int i) {
        return "-" + std::to_string(locals.at(i).offset) + "(%rbp)";
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
        emit("pushq %rax");
        ++depth;
    }
    void pop(const std::string &r) {
        emit("popq " + r);
        --depth;
    }
    void call(const std::string &n) {
        if (depth % 2)
            emit("subq $8, %rsp");
        emit("call " + n);
        if (depth % 2)
            emit("addq $8, %rsp");
    }
    int add(const std::string &n, Type t, bool mut, const Token &tok) {
        if (scopes.back().count(n))
            fail(tok, "duplicate local '" + n + "'");
        Local l;
        l.name = n;
        l.type = t;
        l.mut = mut;
        slot += t.isClass() ? static_cast<int>(typeSize(t, tok) / 8) : 1;
        l.offset = 8 * slot;
        locals.push_back(l);
        int i = static_cast<int>(locals.size()) - 1;
        scopes.back()[n] = i;
        return i;
    }
    Type expression(ExpressionPtr e) {
        const auto &n = e->token.text;
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
            emit("movabsq $" + std::to_string(value) + ", %rax");
            return Type::I64;
        }
        if (e->op == "bool") {
            emit(std::string("movq $") + (n == "true" ? "1" : "0") + ", %rax");
            return Type::Bool;
        }
        if (e->op == "member") {
            if (e->args[0]->op != "name")
                fail(e->token, "field access currently requires a class local");
            int local = source(e->args[0]);
            const auto &member = field(locals[local].type, e->token);
            emit("movq " + fieldAddress(local, member) + ", %rax");
            return member.type;
        }
        if (e->op == "construct")
            fail(e->token, "class construction requires a typed local initializer");
        if (e->op == "name") {
            int i = source(e);
            if (locals[i].type.isClass())
                fail(e->token,
                     "class values are only supported in local initializers and field accesses");
            if (!scalar(locals[i].type))
                fail(e->token,
                     "owned values cannot be implicitly copied; use move, read, or borrow");
            emit("movq " + addr(i) + ", %rax");
            return locals[i].type;
        }
        if (e->op == "unary") {
            auto t = expression(e->args[0]);
            match(t, n == "!" ? Type::Bool : Type::I64, e->token);
            emit(n == "!" ? "xorq $1, %rax" : "negq %rax");
            return t;
        }
        if (e->op == "binary") {
            auto l = expression(e->args[0]);
            push();
            auto r = expression(e->args[1]);
            pop("%rcx");
            match(r, l, e->token);
            if (n == "+" || n == "-" || n == "*") {
                match(l, Type::I64, e->token);
                if (n == "+")
                    emit("addq %rcx, %rax");
                if (n == "*")
                    emit("imulq %rcx, %rax");
                if (n == "-") {
                    emit("subq %rax, %rcx");
                    emit("movq %rcx, %rax");
                }
                return Type::I64;
            }
            if (n != "==" && n != "!=")
                match(l, Type::I64, e->token);
            emit("cmpq %rax, %rcx");
            std::map<std::string, std::string> cc = {{"==", "e"}, {"!=", "ne"}, {"<", "l"},
                                                     {">", "g"},  {"<=", "le"}, {">=", "ge"}};
            emit("set" + cc.at(n) + " %al");
            emit("movzbq %al, %rax");
            return Type::Bool;
        }
        if (e->op != "call")
            fail(e->token, "invalid expression");
        if (n == "size_of" || n == "type_id" || n == "field_count") {
            emit("movq $" + std::to_string(reflectedValue(e)) + ", %rax");
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
            emit("movq " + addr(i) + ", %rax");
            return Type::I64;
        }
        if (n == "write") {
            arity(e, 2);
            int i = source(e->args[0]);
            match(locals[i].type, Type::MutRef, e->token);
            auto t = expression(e->args[1]);
            match(t, Type::I64, e->token);
            emit("movq %rax, " + addr(locals[i].owner));
            return Type::I64;
        }
        if (n == "reflect_size" || n == "reflect_field_count") {
            arity(e, 1);
            match(expression(e->args[0]), Type::I64, e->token);
            emit("movq %rax, %rdi");
            call("aurora_" + n);
            return Type::I64;
        }
        if (n == "own" || n == "move" || n == "borrow" || n == "borrow_mut")
            fail(e->token, "ownership constructors are only supported in typed local initializers");
        auto f = functions.find(n);
        if (f == functions.end())
            fail(e->token, "unknown function '" + n + "'");
        auto &callee = fs[f->second];
        arity(e, callee.params.size());
        for (std::size_t i = 0; i < e->args.size(); ++i) {
            match(expression(e->args[i]), callee.params[i].type, e->token);
            push();
        }
        static const std::vector<std::string> regs = {"%rdi", "%rsi", "%rdx", "%rcx", "%r8", "%r9"};
        for (std::size_t i = e->args.size(); i > 0; --i)
            pop(regs[i - 1]);
        call(n);
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
        if (expression->op == "name") {
            const int original = source(expression);
            match(locals[original].type, statement->type, expression->token);
            const int destination =
                add(statement->name, statement->type, statement->mutableValue, statement->token);
            for (const auto &member : definition.fields) {
                emit("movq " + fieldAddress(original, member) + ", %rax");
                emit("movq %rax, " + fieldAddress(destination, member));
            }
            return;
        }
        if (expression->op != "construct")
            fail(expression->token,
                 "class local requires named-field construction or same-type class copy");
        match(Type(expression->token.text), statement->type, expression->token);
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
            pop("%rax");
            emit("movq %rax, " + fieldAddress(destination, member));
        }
    }
    bool statement(StatementPtr s) {
        if (s->kind == "return") {
            match(expression(s->expr), result, s->token);
            emit("jmp " + returnLabel);
            return true;
        }
        if (s->kind == "block")
            return block(s->body);
        if (s->kind == "static_assert") {
            std::ostringstream saved;
            saved.swap(out);
            auto t = expression(s->expr);
            match(t, Type::Bool, s->token);
            auto v = constant(s->expr);
            out.swap(saved);
            if (!v)
                fail(s->token, "static assertion failed");
            return false;
        }
        if (s->kind == "let") {
            if (s->type.isClass()) {
                initializeClass(s);
                return false;
            }
            auto e = s->expr;
            int owner = -1;
            if (scalar(s->type)) {
                match(expression(e), s->type, s->token);
            } else {
                if (s->mutableValue)
                    fail(s->token, "ownership bindings cannot be mutable; use a mutable borrow");
                if (e->op != "call")
                    fail(s->token, "ownership binding requires explicit constructor");
                arity(e, 1);
                auto op = e->token.text;
                if (s->type == Type::Own && op == "own") {
                    match(expression(e->args[0]), Type::I64, s->token);
                } else if (s->type == Type::Own && op == "move") {
                    int i = source(e->args[0]);
                    match(locals[i].type, Type::Own, s->token);
                    if (locals[i].shared || locals[i].exclusive)
                        fail(s->token, "cannot move a borrowed owner");
                    locals[i].live = false;
                    emit("movq " + addr(i) + ", %rax");
                } else if ((s->type == Type::Ref && op == "borrow") ||
                           (s->type == Type::MutRef && op == "borrow_mut")) {
                    owner = source(e->args[0]);
                    match(locals[owner].type, Type::Own, s->token);
                    if (locals[owner].exclusive ||
                        (s->type == Type::MutRef && locals[owner].shared))
                        fail(s->token, "conflicting borrow");
                    if (s->type == Type::Ref)
                        ++locals[owner].shared;
                    else
                        locals[owner].exclusive = true;
                    emit("leaq " + addr(owner) + ", %rax");
                } else
                    fail(s->token, "constructor does not match ownership type");
            }
            int i = add(s->name, s->type, s->mutableValue, s->token);
            locals[i].owner = owner;
            emit("movq %rax, " + addr(i));
            return false;
        }
        if (s->kind == "field_assign") {
            const int local = find(Token(s->name, s->token.line));
            if (!locals[local].mut)
                fail(s->token, "field assignment requires a mutable class local");
            const auto &member = field(locals[local].type, Token(s->fieldName, s->token.line));
            match(expression(s->expr), member.type, s->token);
            emit("movq %rax, " + fieldAddress(local, member));
            return false;
        }
        if (s->kind == "assign") {
            int i = find(Token(s->name, s->token.line));
            if (!locals[i].mut || !scalar(locals[i].type))
                fail(s->token, "assignment requires a mutable scalar local");
            match(expression(s->expr), locals[i].type, s->token);
            emit("movq %rax, " + addr(i));
            return false;
        }
        if (s->kind == "if") {
            match(expression(s->expr), Type::Bool, s->token);
            auto no = fresh(), end = fresh();
            emit("testq %rax, %rax");
            emit("jz " + no); // Branch-local borrows expire before joining. A moved owner remains
                              // unavailable
            // on every continuing path; return-only paths do not constrain later uses.
            auto before = locals;
            bool yesReturn = block(s->body);
            auto yes = locals;
            emit("jmp " + end);
            out << no << ":\n";
            for (std::size_t i = 0; i < before.size(); ++i)
                locals[i] = before[i];
            bool noReturn = block(s->other);
            for (std::size_t i = 0; i < before.size(); ++i) {
                if (noReturn && !yesReturn)
                    locals[i].live = yes[i].live;
                else if (!yesReturn)
                    locals[i].live = locals[i].live && yes[i].live;
            }
            out << end << ":\n";
            return yesReturn && noReturn;
        }
        expression(s->expr);
        return false;
    }

  public:
    explicit Compiler(Program program)
        : fs(std::move(program.functions)), classes(std::move(program.classes)) {}
    std::string compile() {
        static const std::set<std::string> builtins = {"own",
                                                       "move",
                                                       "borrow",
                                                       "borrow_mut",
                                                       "read",
                                                       "write",
                                                       "size_of",
                                                       "type_id",
                                                       "field_count",
                                                       "reflect_size",
                                                       "reflect_field_count",
                                                       "aurora_reflect_size",
                                                       "aurora_reflect_field_count"};
        for (std::size_t index = 0; index < classes.size(); ++index) {
            auto &definition = classes[index];
            const auto &name = definition.token.text;
            if (builtins.contains(name) || name == "i64" || name == "bool" || name == "ref" ||
                name == "mutref" || classNames.contains(name))
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
        for (std::size_t i = 0; i < fs.size(); ++i) {
            if (builtins.count(fs[i].name) || functions.count(fs[i].name) ||
                classNames.count(fs[i].name))
                fail(fs[i].token, "duplicate or reserved function name");
            if (fs[i].params.size() > 6)
                fail(fs[i].token, "at most six parameters supported");
            functions[fs[i].name] = i;
        }
        std::ostringstream all;
        all << "# Aurora compiler output: x86-64, scalar bootstrap ABI\n.text\n";
        for (auto &f : fs) {
            locals.clear();
            scopes.clear();
            scopes.emplace_back();
            slot = 0;
            depth = 0;
            out.str("");
            out.clear();
            result = f.result;
            returnLabel = fresh();
            static const std::vector<std::string> regs = {"%rdi", "%rsi", "%rdx",
                                                          "%rcx", "%r8",  "%r9"};
            for (std::size_t j = 0; j < f.params.size(); ++j) {
                int i = add(f.params[j].name, f.params[j].type, false, f.token);
                emit("movq " + regs[j] + ", " + addr(i));
            }
            if (!block(f.body))
                fail(f.token, "function must return on every path");
            all << ".globl " << f.name << "\n.type " << f.name << ", @function\n"
                << f.name << ":\n    pushq %rbp\n    movq %rsp, %rbp\n    subq $"
                << ((slot * 8 + 15) / 16) * 16 << ", %rsp\n"
                << out.str() << returnLabel << ":\n    leave\n    ret\n.size " << f.name << ", .-"
                << f.name << "\n";
        }
        for (const auto &query : {std::string("size"), std::string("field_count")}) {
            const std::string symbol = "aurora_reflect_" + query;
            all << ".globl " << symbol << "\n.type " << symbol << ", @function\n"
                << symbol << ":\n";
            for (int id = 1; id <= 5; ++id) {
                all << "    cmpq $" << id << ", %rdi\n    je .L" << query << id << "\n";
            }
            for (const auto &definition : classes) {
                all << "    cmpq $" << definition.id << ", %rdi\n    je .L" << query
                    << definition.id << "\n";
            }
            all << "    xorq %rax, %rax\n    ret\n";
            for (int id = 1; id <= 5; ++id) {
                all << ".L" << query << id << ":\n    movq $"
                    << (query == "size" ? (id == 2 ? 1 : 8) : 0) << ", %rax\n    ret\n";
            }
            for (const auto &definition : classes) {
                auto value = query == "size"
                                 ? std::max<std::size_t>(8, definition.fields.size() * 8)
                                 : definition.fields.size();
                all << ".L" << query << definition.id << ":\n    movq $" << value
                    << ", %rax\n    ret\n";
            }
            all << ".size " << symbol << ", .-" << symbol << "\n";
        }
        all << ".section .note.GNU-stack,\"\",@progbits\n";
        return all.str();
    }
};
} // namespace aurora
int main(int argc, char **argv) {
    try {
        if (argc != 4 || std::string(argv[2]) != "-o") {
            std::cerr << "usage: aurorac INPUT.au -o OUTPUT.s\n";
            return 2;
        }
        std::ifstream in(argv[1]);
        if (!in)
            throw aurora::Error("cannot open input");
        std::ostringstream source;
        source << in.rdbuf();
        aurora::Parser parser(aurora::lex(source.str()));
        aurora::Compiler compiler(parser.parse());
        auto result = compiler.compile();
        std::ofstream out(argv[3]);
        if (!out)
            throw aurora::Error("cannot open output");
        out << result;
        if (!out)
            throw aurora::Error("cannot write output");
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "aurorac: " << e.what() << '\n';
        return 1;
    }
}
