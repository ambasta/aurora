#pragma once
#include "syntax.hpp"
#include <algorithm>
#include <cctype>
#include <set>
namespace aurora {
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
        if (!eat(s))
            fail("expected '" + s + "'");
    }
    Token ident() {
        auto t = peek();
        if (t.text.empty() ||
            !(std::isalpha(static_cast<unsigned char>(t.text[0])) || t.text[0] == '_'))
            fail("expected identifier");
        static const std::set<std::string> reserved = {
            "fn",        "module",   "let",    "mut",           "if",     "else",
            "return",    "true",     "false",  "static_assert", "class",  "while",
            "break",     "continue", "auto",   "const",         "public", "private",
            "protected", "unsafe",   "extern", "struct"};
        if (reserved.count(t.text))
            fail("reserved identifier");
        return take();
    }
    Type type() {
        static const std::set<std::string> forbidden = {
            "fn",     "let", "mut",  "auto", "const", "class",  "unsafe", "struct",
            "extern", "int", "void", "char", "float", "double", "new",    "delete"};
        if (forbidden.contains(peek().text))
            fail("unsupported or reserved type spelling");
        if (eat("i64"))
            return Type::I64;
        if (eat("bool"))
            return Type::Bool;
        auto t = take();
        if (t.text == "array") {
            need("<");
            const auto element = type();
            if (!scalar(element))
                fail("array elements currently require i64 or bool");
            need(",");
            const auto count = take();
            unsigned long long length = 0;
            try {
                std::size_t used = 0;
                length = std::stoull(count.text, &used);
                if (used != count.text.size())
                    fail("array length requires a decimal integer literal");
            } catch (const std::exception &) {
                fail("array length requires a decimal integer literal");
            }
            if (length < 1 || length > 4096)
                fail("array length must be between 1 and 4096");
            need(">");
            return Type::array(element.kind, static_cast<int>(length));
        }
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
        while (true) {
            if (eat(".")) {
                auto member = std::make_shared<Expression>("member", ident());
                member->args.push_back(expression);
                expression = member;
            } else if (eat("[")) {
                auto index = std::make_shared<Expression>("index", expression->token);
                index->args = {expression, expr()};
                need("]");
                expression = index;
            } else
                return expression;
        }
    }
    ExpressionPtr primary() {
        auto t = take();
        auto e = std::make_shared<Expression>("name", t);
        if (t.text == "{") {
            e->op = "array_literal";
            if (!eat("}")) {
                do {
                    e->args.push_back(expr());
                } while (eat(","));
                need("}");
            }
            return postfix(e);
        }
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
                    need(".");
                    e->fieldNames.push_back(ident().text);
                    need("=");
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
    bool startsDeclaration() const {
        const auto name = peek().text;
        if (name == "const" || name == "i64" || name == "bool" || name == "own" || name == "ref" ||
            name == "mutref" || name == "array")
            return true;
        const auto &next = tokens.at(std::min(position + 1, tokens.size() - 1)).text;
        return !next.empty() &&
               (std::isalpha(static_cast<unsigned char>(next[0])) || next[0] == '_') &&
               name != "return" && name != "if" && name != "while";
    }
    StatementPtr statement() {
        auto t = peek();
        auto s = std::make_shared<Statement>(t);
        if (t.text == "{") {
            s->kind = "block";
            s->body = block();
            return s;
        }
        if (startsDeclaration()) {
            s->kind = "let";
            const bool immutable = eat("const");
            s->type = type();
            s->name = ident().text;
            s->mutableValue = !immutable;
            need("=");
            s->expr = expr();
            need(";");
            return s;
        }
        take();
        if (t.text == "return" || t.text == "static_assert") {
            if (t.text == "static_assert")
                need("(");
            s->expr = expr();
            if (t.text == "static_assert")
                need(")");
            need(";");
        } else if (t.text == "if" || t.text == "while") {
            need("(");
            s->expr = expr();
            need(")");
            s->body = block();
            if (t.text == "if" && eat("else"))
                s->other = block();
        } else {
            --position;
            s->kind = "expression";
            s->expr = expr();
            if (eat("=")) {
                if (s->expr->op == "index") {
                    s->kind = "index_assign";
                    s->target = s->expr;
                } else if (s->expr->op == "member" && s->expr->args[0]->op == "name") {
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
                bool publicAccess = false;
                while (!eat("}")) {
                    if (eat("public")) {
                        need(":");
                        publicAccess = true;
                        continue;
                    }
                    if (eat("private")) {
                        need(":");
                        publicAccess = false;
                        continue;
                    }
                    auto fieldType = type();
                    auto fieldName = ident();
                    if (!scalar(fieldType))
                        fail("class fields currently require i64 or bool");
                    need(";");
                    definition.fields.emplace_back(fieldName, fieldType);
                    definition.fields.back().publicAccess = publicAccess;
                }
                need(";");
                program.classes.push_back(std::move(definition));
                continue;
            }
            need("auto");
            Function f(ident());
            need("(");
            if (!eat(")")) {
                do {
                    Param a;
                    a.type = type();
                    a.name = ident().text;
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

} // namespace aurora
