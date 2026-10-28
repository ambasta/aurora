// Lexer and parser of the seed: modules, namespaces, enums, classes and
// functions with C++-like statements and expressions. Anything else is
// rejected; there is no recovery.
#include "seed.hpp"

#include <cstring>

namespace seed {
namespace {

bool letter(char c) {
    return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c == '_';
}
bool digit(char c) {
    return c >= '0' && c <= '9';
}
int hex_value(char c) {
    if (digit(c)) {
        return c - '0';
    }
    if (c >= 'a' && c <= 'f') {
        return c - 'a' + 10;
    }
    if (c >= 'A' && c <= 'F') {
        return c - 'A' + 10;
    }
    return -1;
}

class Lexer {
public:
    explicit Lexer(const Source &source) : source_(source), text_(source.text) {
    }

    std::vector<Token> run() {
        std::vector<Token> tokens;
        while (true) {
            skip();
            Token token;
            token.line = line_;
            if (at_ >= text_.size()) {
                tokens.push_back(token);
                return tokens;
            }
            const size_t start = at_;
            const char c = text_[at_];
            if (letter(c)) {
                while (at_ < text_.size() && (letter(text_[at_]) || digit(text_[at_]))) {
                    ++at_;
                }
                token.kind = Tk::identifier;
            } else if (digit(c)) {
                number(token);
            } else if (c == '\'') {
                character(token);
            } else if (c == '"') {
                string(token);
            } else {
                static constexpr const char *pairs[] = {"->", "==", "!=", "<=", ">=", "::", "<<", ">>", "&&", "||"};
                token.kind = Tk::punctuation;
                at_ += 1;
                for (const char *pair : pairs) {
                    if (text_.compare(start, 2, pair) == 0) {
                        at_ = start + 2;
                        break;
                    }
                }
                if (at_ == start + 1 && !std::strchr("(){}[]:;,=+-*/%<>!.&|^~", c)) {
                    error("unexpected character");
                }
            }
            token.text = std::string_view(text_).substr(start, at_ - start);
            tokens.push_back(std::move(token));
        }
    }

private:
    [[noreturn]] void error(const std::string &message) {
        fail(Loc{&source_, line_}, message);
    }

    void skip() {
        while (at_ < text_.size()) {
            const char c = text_[at_];
            if (c == '\n') {
                ++line_;
                ++at_;
            } else if (c == ' ' || c == '\t' || c == '\r') {
                ++at_;
            } else if (c == '/' && at_ + 1 < text_.size() && text_[at_ + 1] == '/') {
                while (at_ < text_.size() && text_[at_] != '\n') {
                    ++at_;
                }
            } else {
                return;
            }
        }
    }

    // Decimal, or binary with 0b/0B and apostrophes between digits, with an
    // optional u64 or u8 suffix. The magnitude must fit u64.
    void number(Token &token) {
        token.kind = Tk::integer;
        uint64_t value = 0;
        const bool binary =
            text_[at_] == '0' && at_ + 1 < text_.size() && (text_[at_ + 1] == 'b' || text_[at_ + 1] == 'B');
        const uint64_t base = binary ? 2 : 10;
        at_ += binary ? 2 : 0;
        const size_t first = at_;
        while (at_ < text_.size() &&
               (binary ? text_[at_] == '0' || text_[at_] == '1' || text_[at_] == '\'' : digit(text_[at_]))) {
            // A separator stands between two binary digits.
            if (text_[at_] == '\'' &&
                (at_ == first || at_ + 1 >= text_.size() || (text_[at_ + 1] != '0' && text_[at_ + 1] != '1'))) {
                error("invalid digit separator");
            }
            if (text_[at_] != '\'' &&
                (__builtin_mul_overflow(value, base, &value) ||
                 __builtin_add_overflow(value, static_cast<uint64_t>(text_[at_] - '0'), &value))) {
                error("integer literal out of range");
            }
            ++at_;
        }
        if (at_ == first) {
            error("integer literal without digits");
        }
        token.value = value;
        if (text_.compare(at_, 3, "u64") == 0) {
            token.suffix = Suffix::u64;
            at_ += 3;
        } else if (text_.compare(at_, 2, "u8") == 0) {
            token.suffix = Suffix::u8;
            at_ += 2;
            if (token.value > 255) {
                error("u8 literal out of range");
            }
        }
        if (at_ < text_.size() && (letter(text_[at_]) || digit(text_[at_]))) {
            error("invalid integer literal");
        }
    }

    // One escape after a backslash; quote is the delimiter being read.
    uint8_t escape(char quote) {
        const char c = text_[at_++];
        switch (c) {
        case '\'':
        case '\\':
            return static_cast<uint8_t>(c);
        case '0':
            return 0;
        case 'a':
            return 7;
        case 'b':
            return 8;
        case 'f':
            return 12;
        case 'n':
            return 10;
        case 'r':
            return 13;
        case 't':
            return 9;
        case 'v':
            return 11;
        case 'x': {
            if (at_ + 2 > text_.size() || hex_value(text_[at_]) < 0 || hex_value(text_[at_ + 1]) < 0) {
                error("invalid hexadecimal escape");
            }
            const int value = hex_value(text_[at_]) * 16 + hex_value(text_[at_ + 1]);
            at_ += 2;
            return static_cast<uint8_t>(value);
        }
        default:
            if (c == '"' && quote == '"') {
                return '"';
            }
            error("invalid escape");
        }
    }

    void character(Token &token) {
        token.kind = Tk::integer;
        token.suffix = Suffix::u8;
        ++at_;
        if (at_ >= text_.size()) {
            error("unterminated character literal");
        }
        const char c = text_[at_++];
        if (c == '\\') {
            token.value = escape('\'');
        } else if (c >= ' ' && c <= '~' && c != '\'') {
            token.value = static_cast<uint8_t>(c);
        } else {
            error("invalid character literal");
        }
        if (at_ >= text_.size() || text_[at_] != '\'') {
            error("unterminated character literal");
        }
        ++at_;
    }

    // Raw bytes other than controls are copied (the compiler checks UTF-8).
    void string(Token &token) {
        token.kind = Tk::string;
        ++at_;
        while (true) {
            if (at_ >= text_.size() || text_[at_] == '\n') {
                error("unterminated string literal");
            }
            const char c = text_[at_++];
            if (c == '"') {
                return;
            }
            if (c == '\\') {
                token.bytes.push_back(static_cast<char>(escape('"')));
            } else if (static_cast<uint8_t>(c) < 0x20 || c == 0x7f) {
                error("control byte in string literal");
            } else {
                token.bytes.push_back(c);
            }
        }
    }

    const Source &source_;
    const std::string &text_;
    size_t at_ = 0;
    int line_ = 1;
};

// Binary operator precedence, lowest first; 0 is not a binary operator.
int precedence(std::string_view op) {
    static const std::pair<std::string_view, int> table[] = {
        {"||", 1},
        {"&&", 2},
        {"|", 3},
        {"^", 4},
        {"&", 5},
        {"==", 6},
        {"!=", 6},
        {"<", 7},
        {"<=", 7},
        {">", 7},
        {">=", 7},
        {"<<", 8},
        {">>", 8},
        {"+", 9},
        {"-", 9},
        {"*", 10},
        {"/", 10},
        {"%", 10},
    };
    for (const auto &[name, level] : table) {
        if (name == op) {
            return level;
        }
    }
    return 0;
}

class Parser {
public:
    Parser(Source *source, std::vector<Token> tokens) : source_(source), tokens_(std::move(tokens)) {
    }

    Module *module() {
        auto *result = new Module;
        result->source = source_;
        accept("export");
        expect("module");
        result->name = dotted();
        expect(";");
        while (accept("import")) {
            result->imports.push_back(dotted());
            expect(";");
        }
        while (peek().kind != Tk::end) {
            declaration(result, "", false);
        }
        return result;
    }

private:
    const Token &peek(size_t ahead = 0) const {
        const size_t at = pos_ + ahead;
        return tokens_[at < tokens_.size() ? at : tokens_.size() - 1];
    }
    Loc loc() const {
        return Loc{source_, peek().line};
    }
    bool is(std::string_view text, size_t ahead = 0) const {
        const Token &token = peek(ahead);
        return (token.kind == Tk::punctuation || token.kind == Tk::identifier) && token.text == text;
    }
    bool accept(std::string_view text) {
        if (is(text)) {
            ++pos_;
            return true;
        }
        return false;
    }
    [[noreturn]] void error(const std::string &message) const {
        fail(loc(), message + " near '" + std::string(peek().text) + "'");
    }
    void expect(std::string_view text) {
        if (!accept(text)) {
            error("expected '" + std::string(text) + "'");
        }
    }
    std::string identifier() {
        if (peek().kind != Tk::identifier) {
            error("expected an identifier");
        }
        return std::string(tokens_[pos_++].text);
    }
    std::string dotted() {
        std::string name = identifier();
        while (accept(".")) {
            name += "." + identifier();
        }
        return name;
    }

    void declaration(Module *module, const std::string &space, bool exported) {
        const bool exporting = accept("export") || exported;
        if (accept("namespace")) {
            if (!space.empty()) {
                error("nested namespaces are not supported");
            }
            const std::string name = identifier();
            expect("{");
            while (!accept("}")) {
                declaration(module, name, exporting);
            }
            return;
        }
        if (accept("enum")) {
            expect("class");
            auto *decl = new EnumDecl;
            decl->loc = loc();
            decl->name = identifier();
            decl->module = module;
            decl->space = space;
            decl->exported = exporting;
            expect("{");
            while (!accept("}")) {
                decl->cases.push_back(identifier());
                if (!accept(",")) {
                    expect("}");
                    break;
                }
            }
            expect(";");
            module->enums.push_back(decl);
            return;
        }
        if (accept("class")) {
            class_body(module, space, exporting);
            return;
        }
        if (is("auto")) {
            Function *function = callable(module, space, exporting, nullptr);
            module->functions.push_back(function);
            return;
        }
        error("unsupported declaration");
    }

    void class_body(Module *module, const std::string &space, bool exported) {
        auto *decl = new ClassDecl;
        decl->loc = loc();
        decl->name = identifier();
        decl->module = module;
        decl->space = space;
        decl->exported = exported;
        expect("{");
        while (!accept("}")) {
            if ((is("public") || is("private")) && is(":", 1)) {
                pos_ += 2;
                continue;
            }
            if (is("auto")) {
                decl->methods.push_back(callable(module, space, exported, decl));
                continue;
            }
            if (is(decl->name) && is("(", 1)) {
                decl->constructors.push_back(constructor(module, space, exported, decl));
                continue;
            }
            FieldDecl field;
            field.loc = loc();
            field.type = type();
            field.name = identifier();
            expect(";");
            decl->fields.push_back(field);
        }
        expect(";");
        module->classes.push_back(decl);
    }

    void parameters(Function *function) {
        expect("(");
        if (!accept(")")) {
            do {
                Param param;
                param.type = type();
                param.name = identifier();
                function->params.push_back(param);
            } while (accept(","));
            expect(")");
        }
    }

    Function *callable(Module *module, const std::string &space, bool exported, ClassDecl *owner) {
        expect("auto");
        auto *function = new Function;
        function->loc = loc();
        function->name = identifier();
        function->module = module;
        function->space = space;
        function->exported = exported;
        function->owner = owner;
        parameters(function);
        function->constant = accept("const");
        expect("->");
        function->result = type();
        function->body = block();
        return function;
    }

    Function *constructor(Module *module, const std::string &space, bool exported, ClassDecl *owner) {
        auto *function = new Function;
        function->loc = loc();
        function->name = identifier();
        function->module = module;
        function->space = space;
        function->exported = exported;
        function->owner = owner;
        function->constructor = true;
        parameters(function);
        if (accept(":")) {
            do {
                Init init;
                init.loc = loc();
                init.field = identifier();
                if (accept("{")) {
                    expect("}");
                    init.braces = true;
                } else {
                    init.arguments = arguments();
                }
                function->inits.push_back(init);
            } while (accept(","));
        }
        function->body = block();
        return function;
    }

    // [const] [::] name {:: name} [<arguments>] [&]
    TypeSyntax *type() {
        auto *result = new TypeSyntax;
        result->loc = loc();
        result->constant = accept("const");
        result->global = accept("::");
        result->path.push_back(identifier());
        while (accept("::")) {
            result->path.push_back(identifier());
        }
        if (accept("<")) {
            do {
                TypeArgument argument;
                if (peek().kind == Tk::integer) {
                    argument.number = static_cast<int64_t>(tokens_[pos_++].value);
                } else {
                    argument.type = type();
                }
                result->arguments.push_back(argument);
            } while (accept(","));
            close_angle();
        }
        result->reference = accept("&");
        return result;
    }

    // Closes a type argument list, splitting a '>>' token.
    void close_angle() {
        if (is(">>")) {
            tokens_[pos_].text = ">";
            return;
        }
        expect(">");
    }

    // Whether a local declaration starts here: a type, a name and '='.
    bool declaration_ahead() {
        if (is("const")) {
            return true;
        }
        if (peek().kind != Tk::identifier && !is("::")) {
            return false;
        }
        const size_t saved = pos_;
        size_t depth = 0;
        if (is("::")) {
            ++pos_;
        }
        bool ok = peek().kind == Tk::identifier;
        while (ok) {
            ++pos_;
            if (is("::") && peek(1).kind == Tk::identifier) {
                ++pos_;
                continue;
            }
            break;
        }
        if (ok && is("<")) {
            ++pos_;
            depth = 1;
            while (depth > 0 && peek().kind != Tk::end && !is(";") && !is("{") && !is("(")) {
                if (is("<")) {
                    ++depth;
                } else if (is(">")) {
                    --depth;
                } else if (is(">>")) {
                    depth = depth >= 2 ? depth - 2 : 0;
                }
                ++pos_;
            }
            ok = depth == 0;
        }
        if (ok) {
            accept("&");
            ok = peek().kind == Tk::identifier && is("=", 1);
        }
        pos_ = saved;
        return ok;
    }

    Stmt *block() {
        auto *result = new Stmt{Sk::block, loc()};
        expect("{");
        while (!accept("}")) {
            result->body.push_back(statement());
        }
        return result;
    }

    Stmt *statement() {
        const Loc at = loc();
        if (is("{")) {
            return block();
        }
        if (accept("return")) {
            auto *result = new Stmt{Sk::ret, at};
            result->value = expression();
            expect(";");
            return result;
        }
        if (accept("if")) {
            auto *result = new Stmt{Sk::branch, at};
            expect("(");
            result->value = expression();
            expect(")");
            result->then = statement();
            if (accept("else")) {
                result->otherwise = statement();
            }
            return result;
        }
        if (accept("while")) {
            auto *result = new Stmt{Sk::loop, at};
            expect("(");
            result->value = expression();
            expect(")");
            result->then = statement();
            return result;
        }
        if (is("for") || is("break") || is("continue") || is("switch") || is("static_assert") || is("template")) {
            error("unsupported statement");
        }
        if (declaration_ahead()) {
            auto *result = new Stmt{Sk::local, at};
            result->constant = accept("const");
            result->type = type();
            result->name = identifier();
            expect("=");
            result->value = expression();
            expect(";");
            return result;
        }
        Expr *value = expression();
        if (accept("=")) {
            auto *result = new Stmt{Sk::assign, at};
            result->target = value;
            result->value = expression();
            expect(";");
            return result;
        }
        auto *result = new Stmt{Sk::expression, at};
        result->value = value;
        expect(";");
        return result;
    }

    std::vector<Expr *> arguments() {
        std::vector<Expr *> result;
        expect("(");
        if (accept(")")) {
            return result;
        }
        do {
            result.push_back(expression());
        } while (accept(","));
        expect(")");
        return result;
    }

    Expr *expression(int minimum = 1) {
        Expr *left = unary();
        while (peek().kind == Tk::punctuation) {
            const int level = precedence(peek().text);
            if (level < minimum || level == 0) {
                break;
            }
            auto *node = new Expr{Ek::binary, loc()};
            node->op = std::string(tokens_[pos_++].text);
            node->a = left;
            node->b = expression(level + 1);
            left = node;
        }
        return left;
    }

    Expr *unary() {
        if (is("!") || is("-") || is("~")) {
            auto *node = new Expr{Ek::unary, loc()};
            node->op = std::string(tokens_[pos_++].text);
            node->a = unary();
            return node;
        }
        return postfix(primary());
    }

    Expr *postfix(Expr *value) {
        while (true) {
            if (accept(".")) {
                const Loc at = loc();
                const std::string name = identifier();
                if (is("(")) {
                    auto *node = new Expr{Ek::method, at};
                    node->a = value;
                    node->text = name;
                    node->arguments = arguments();
                    value = node;
                } else {
                    auto *node = new Expr{Ek::member, at};
                    node->a = value;
                    node->text = name;
                    value = node;
                }
            } else if (is("[")) {
                auto *node = new Expr{Ek::index, loc()};
                ++pos_;
                node->a = value;
                node->b = expression();
                expect("]");
                value = node;
            } else {
                return value;
            }
        }
    }

    Expr *primary() {
        const Loc at = loc();
        const Token &token = peek();
        if (token.kind == Tk::integer) {
            auto *node = new Expr{Ek::integer, at};
            node->value = token.value;
            node->suffix = token.suffix;
            ++pos_;
            return node;
        }
        if (token.kind == Tk::string) {
            auto *node = new Expr{Ek::string, at};
            node->text = token.bytes;
            ++pos_;
            return node;
        }
        if (accept("(")) {
            Expr *inner = expression();
            expect(")");
            return inner;
        }
        if (is("true") || is("false")) {
            auto *node = new Expr{Ek::boolean, at};
            node->value = is("true") ? 1 : 0;
            ++pos_;
            return node;
        }
        auto *node = new Expr{Ek::name, at};
        node->global = accept("::");
        node->path.push_back(identifier());
        while (accept("::")) {
            node->path.push_back(identifier());
        }
        if (is("(")) {
            node->kind = Ek::call;
            node->arguments = arguments();
        } else if (accept("{")) {
            node->kind = Ek::construct;
            if (!accept("}")) {
                do {
                    expect(".");
                    node->fields.push_back(identifier());
                    expect("=");
                    node->arguments.push_back(expression());
                } while (accept(","));
                expect("}");
            }
        }
        return node;
    }

    Source *source_;
    std::vector<Token> tokens_;
    size_t pos_ = 0;
};

} // namespace

Module *parse_module(Source *source) {
    Parser parser(source, Lexer(*source).run());
    return parser.module();
}

} // namespace seed
