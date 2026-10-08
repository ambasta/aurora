#pragma once
#include "syntax.hpp"
#include <algorithm>
#include <cctype>
#include <set>
namespace aurora {
class Parser {
    std::vector<Token> tokens;
    std::size_t position = 0;
    int expressionNesting = 0, blockNesting = 0, typeNesting = 0, templateNesting = 0;
    std::set<std::string> templateParameters;
    std::set<std::string> capacityParameters;
    bool functionTemplate = false;
    class Nesting {
        int &depth;

    public:
        Nesting(int &value, int limit, const Token &token, const std::string &kind) : depth(value) {
            if (depth >= limit)
                throw Error(
                    DiagnosticCode::NestingLimit, kind + " nesting exceeds " + std::to_string(limit), token.span);
            ++depth;
        }
        Nesting(const Nesting &) = delete;
        Nesting &operator=(const Nesting &) = delete;
        ~Nesting() {
            --depth;
        }
    };
    void attach(const ExpressionPtr &parent, const ExpressionPtr &child) {
        // Check before attaching: error cleanup must never own an over-deep tree.
        if (child->depth >= 128)
            fail("expression AST depth exceeds 128");
        parent->depth = std::max(parent->depth, child->depth + 1);
        parent->args.push_back(child);
    }

public:
    explicit Parser(std::vector<Token> t) : tokens(std::move(t)) {
    }
    Token peek() const {
        return tokens.at(position);
    }
    Token take() {
        const auto token = tokens.at(position);
        // Keep EOF available for a located rejection in truncated expressions,
        // types and array lengths, instead of peeking past the token vector.
        if (position + 1 < tokens.size())
            ++position;
        return token;
    }
    [[noreturn]] void fail(const std::string &m) const {
        throw Error(DiagnosticCode::UnexpectedToken, m + " (found '" + peek().text + "')", peek().span);
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
    Token ident(bool allowArray = false) {
        auto t = peek();
        if (t.text.empty() || !(std::isalpha(static_cast<unsigned char>(t.text[0])) || t.text[0] == '_'))
            fail("expected identifier");
        static const std::set<std::string> reserved = {
            "fn",        "module",        "let",       "mut",    "if",     "else",     "return", "true",
            "false",     "static_assert", "class",     "while",  "break",  "continue", "auto",   "const",
            "public",    "private",       "protected", "unsafe", "extern", "struct",   "export", "import",
            "namespace", "this",          "template",  "Scalar", "enum"};
        if (t.text == "builtin" || (t.text == "array" && !allowArray))
            fail("reserved builtin storage name");
        if (t.text.starts_with("__au_"))
            fail("reserved compiler identifier prefix: __au_");
        if (reserved.count(t.text))
            fail("reserved identifier");
        return take();
    }
    Token qualifiedTail(Token token, bool allowArray = false) {
        while (eat("::")) {
            const auto next = ident(allowArray);
            token.text += "::" + next.text;
            token.span.end = next.span.end;
        }
        return token;
    }
    Token qualifiedIdent() {
        return qualifiedTail(ident());
    }
    Token moduleIdent() {
        auto token = ident();
        while (eat(".")) {
            const auto next = ident(true);
            token.text += "." + next.text;
            token.span.end = next.span.end;
        }
        return token;
    }
    bool scalarOrParameter(const Type &value) const {
        return scalar(value) || value.kind == TypeKind::Parameter;
    }
    void templateClose() {
        if (eat(">"))
            return;
        if (peek().text == ">>") {
            // Split only the parser-owned copy. Retained lexical tokens and the
            // immutable source snapshot still describe the original two bytes.
            tokens[position].text = ">";
            if (tokens[position].span.source) {
                ++tokens[position].span.begin.offset;
                ++tokens[position].span.begin.column;
            }
            return;
        }
        fail("expected '>'");
    }
    // Locate an entire explicit argument list without changing tokens. Only this
    // type/construction lookahead treats >> as two closers; arithmetic keeps it.
    std::size_t templateArgumentEnd(std::size_t start) const {
        if (start >= tokens.size() || tokens[start].text != "<")
            return tokens.size();
        int depth = 0;
        for (std::size_t index = start; index < tokens.size(); ++index) {
            const auto &token = tokens[index].text;
            if (token == "<")
                ++depth;
            else if (token == ">" || token == ">>") {
                depth -= token == ">>" ? 2 : 1;
                if (depth < 0)
                    return tokens.size();
                if (depth == 0)
                    return index + 1;
            } else if (token == ";" || token == "}" || token == "<eof>" || token == "(" || token == "{" || token == "=")
                return tokens.size();
        }
        return tokens.size();
    }
    std::vector<TemplateArgument> templateArguments(int callAllowance = 0) {
        // Calls are kind-resolved later. Their outer argument list is not a
        // class-template level; class construction depth is checked in resolution.
        Nesting nesting(templateNesting, maximumTemplateNesting + callAllowance, peek(), "template-id");
        if (!templateParameters.empty() && !functionTemplate)
            fail("template-id references inside template definitions are not supported");
        need("<");
        std::vector<TemplateArgument> arguments;
        do {
            if (arguments.size() >= 2)
                fail("template arguments are limited to one or two types or capacity literals");
            // Concrete named types and nested template-ids bind in the requesting
            // module. Resource, reference and builtin storage arguments stay closed.
            if (eat("i64"))
                arguments.push_back(TypeKind::I64);
            else if (eat("u64"))
                arguments.push_back(TypeKind::U64);
            else if (eat("u8"))
                arguments.push_back(TypeKind::U8);
            else if (eat("bool"))
                arguments.push_back(TypeKind::Bool);
            else if (!peek().text.empty() && std::isdigit(static_cast<unsigned char>(peek().text[0]))) {
                const auto argument = take();
                try {
                    std::size_t used = 0;
                    const auto value = std::stoull(argument.text, &used);
                    if (used != argument.text.size() || value < 1 || value > 64)
                        fail("capacity template arguments must be decimal literals from 1 to 64");
                    arguments.push_back(TemplateArgument::capacity(static_cast<std::int64_t>(value)));
                } catch (const std::exception &) {
                    fail("capacity template arguments must be decimal literals from 1 to 64");
                }
            } else if (peek().text != "own" && peek().text != "ref" && peek().text != "mutref" &&
                       peek().text != "array" && peek().text != "builtin" && peek().text != "true" &&
                       peek().text != "false") {
                const auto argument = qualifiedTail(ident(), true);
                TemplateArgument value(argument.text);
                if (templateParameters.contains(argument.text)) {
                    if (templateNesting != 1 || peek().text == "<")
                        fail("nested dependent template arguments are not supported");
                    value.type = TypeKind::Parameter;
                }
                if (peek().text == "<")
                    value.templateArguments = templateArguments(callAllowance);
                arguments.push_back(std::move(value));
            } else
                fail("template arguments require scalar, named class or enum types, or capacities "
                     "from 1 to 64");
        } while (eat(","));
        templateClose();
        return arguments;
    }
    bool templateExpressionAhead() const {
        const auto end = templateArgumentEnd(position);
        return end < tokens.size() && (tokens[end].text == "(" || tokens[end].text == "{");
    }
    Type type() {
        Nesting nesting(typeNesting, 64, peek(), "type");
        static const std::set<std::string> forbidden = {"fn",
                                                        "let",
                                                        "mut",
                                                        "auto",
                                                        "const",
                                                        "class",
                                                        "unsafe",
                                                        "struct",
                                                        "extern",
                                                        "int",
                                                        "void",
                                                        "char",
                                                        "float",
                                                        "double",
                                                        "new",
                                                        "delete",
                                                        "enum"};
        if (forbidden.contains(peek().text))
            fail("unsupported or reserved type spelling");
        if (eat("i64"))
            return Type::I64;
        if (eat("u64"))
            return Type::U64;
        if (eat("u8"))
            return Type::U8;
        if (eat("bool"))
            return Type::Bool;
        auto t = take();
        if (t.text == "builtin") {
            need("::");
            if (eat("span")) {
                // This is one dedicated borrow type, not a generic template-id.
                need("<");
                need("const");
                need("u8");
                need(">");
                return Type::ByteSpan;
            }
            if (eat("ByteRegion"))
                return Type::ByteRegion;
            if (eat("OwnedBytes"))
                return Type::OwnedBytes;
            need("array");
            t.text = "array";
        }
        if (templateParameters.contains(t.text)) {
            Type parameter(TypeKind::Parameter);
            parameter.className = t.text;
            return parameter;
        }
        if (t.text == "array") {
            need("<");
            const auto element = type();
            if (!scalarOrParameter(element))
                fail("array elements currently require i64, u64, u8 or bool");
            need(",");
            const auto count = take();
            Type result = Type::array(element.kind, 0);
            if (element.kind == TypeKind::Parameter)
                result.elementParameter = element.className;
            if (capacityParameters.contains(count.text))
                result.lengthParameter = count.text;
            else {
                try {
                    std::size_t used = 0;
                    const auto length = std::stoull(count.text, &used);
                    if (used != count.text.size())
                        fail("array length requires a decimal integer literal");
                    if (length < 1 || length > 4096)
                        fail("array length must be between 1 and 4096");
                    result.length = static_cast<int>(length);
                } catch (const std::exception &) {
                    fail("array length requires a decimal integer literal between 1 and 4096");
                }
            }
            need(">");
            return result;
        }
        Type v;
        if (t.text == "own")
            v = Type::Own;
        else if (t.text == "ref")
            v = Type::Ref;
        else if (t.text == "mutref")
            v = Type::MutRef;
        else {
            if (t.text.empty() || !(std::isalpha(static_cast<unsigned char>(t.text[0])) || t.text[0] == '_'))
                fail("expected type name");
            t = qualifiedTail(std::move(t), true);
            Type result(t.text);
            if (peek().text == "<")
                result.templateArguments = templateArguments();
            return result;
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
                attach(member, expression);
                if (eat("(")) {
                    member->op = "method_call";
                    if (!eat(")")) {
                        do {
                            attach(member, expr());
                        } while (eat(","));
                        need(")");
                    }
                }
                expression = member;
            } else if (eat("[")) {
                auto index = std::make_shared<Expression>("index", expression->token);
                attach(index, expression);
                attach(index, expr());
                need("]");
                expression = index;
            } else
                return expression;
        }
    }
    ExpressionPtr primary() {
        Nesting nesting(expressionNesting, 128, peek(), "expression parser");
        auto t = take();
        auto e = std::make_shared<Expression>("name", t);
        if (t.text == "{") {
            e->op = "array_literal";
            if (!eat("}")) {
                do {
                    attach(e, expr());
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
        if (t.text == "-" || t.text == "!" || t.text == "~") {
            e->op = "unary";
            attach(e, primary());
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
        t = qualifiedTail(std::move(t), true);
        e->token = t;
        if (templateExpressionAhead())
            e->templateArguments = templateArguments(1);
        if (eat("(")) {
            e->op = "call";
            if (t.text == "size_of" || t.text == "type_id" || t.text == "field_count") {
                e->reflectedType = type();
                need(")");
            } else if (!eat(")")) {
                do {
                    attach(e, expr());
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
                    attach(e, expr());
                } while (eat(","));
                need("}");
            }
        }
        return postfix(e);
    }
    int precedence(const std::string &s) {
        if (s == "||")
            return 1;
        if (s == "&&")
            return 2;
        if (s == "|")
            return 3;
        if (s == "^")
            return 4;
        if (s == "&")
            return 5;
        if (s == "==" || s == "!=")
            return 6;
        if (s == "<" || s == ">" || s == "<=" || s == ">=")
            return 7;
        if (s == "<<" || s == ">>")
            return 8;
        if (s == "+" || s == "-")
            return 9;
        if (s == "*" || s == "/" || s == "%")
            return 10;
        return 0;
    }
    ExpressionPtr expr(int min = 1) {
        auto e = primary();
        while (precedence(peek().text) >= min) {
            auto t = take();
            auto x = std::make_shared<Expression>("binary", t);
            attach(x, e);
            attach(x, expr(precedence(t.text) + 1));
            e = x;
        }
        return e;
    }
    std::vector<StatementPtr> block() {
        Nesting nesting(blockNesting, 128, peek(), "block");
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
        if (name == "const" || name == "i64" || name == "u64" || name == "u8" || name == "bool" || name == "own" ||
            name == "ref" || name == "mutref" || name == "array")
            return true;
        std::size_t look = position + 1;
        while (look + 1 < tokens.size() && tokens[look].text == "::")
            look += 2;
        if (look < tokens.size() && tokens[look].text == "<") {
            look = templateArgumentEnd(look);
        }
        const auto &next = tokens.at(std::min(look, tokens.size() - 1)).text;
        return !next.empty() && (std::isalpha(static_cast<unsigned char>(next[0])) || next[0] == '_') &&
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
            const auto binding = ident();
            s->name = binding.text;
            s->bindingSpan = binding.span;
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
    void parameters(Function &function, bool allowClass = false, bool allowBorrow = false) {
        need("(");
        if (!eat(")")) {
            do {
                Param parameter;
                parameter.borrowConst = eat("const");
                parameter.type = type();
                if (peek().text == "&") {
                    parameter.borrowSpan = take().span;
                    parameter.borrowed = true;
                    if (!allowBorrow || !function.params.empty() || !templateParameters.empty() ||
                        !parameter.type.isClass() || !parameter.type.templateArguments.empty())
                        fail("borrowed parameters require one leading concrete owning class on an ordinary function");
                } else if (parameter.borrowConst)
                    fail("const parameter spelling requires a leading owning-class reference");
                parameter.name = ident().text;
                // Nominal names are unresolved here; module resolution permits
                // enum method arguments and class constructor/function arguments.
                if (!scalarOrParameter(parameter.type) && !parameter.type.isClass() && !parameter.type.isSpan() &&
                    !(allowClass && parameter.type.isResource()))
                    fail(allowClass ? "only scalar function parameters or scalar-field class values are "
                                      "supported"
                                    : "only scalar or enum method parameters are supported");
                function.params.push_back(parameter);
            } while (eat(","));
            need(")");
        }
    }
    void declarations(Program &program, const std::string &scope, bool exportScope, bool nested) {
        if (std::count(scope.begin(), scope.end(), ':') > 62)
            fail("namespace nesting exceeds 32 components");
        while (peek().text != "<eof>" && (!nested || peek().text != "}")) {
            const bool explicitlyExported = eat("export");
            if (explicitlyExported && !program.interfaceUnit)
                fail("export declarations require an export module interface");
            const bool exported = explicitlyExported || exportScope;
            if (peek().text == "import")
                fail(explicitlyExported ? "module reexports are not supported" : "imports must precede declarations");
            if (eat("namespace")) {
                const auto name = qualifiedIdent().text;
                const auto fullScope = scope.empty() ? name : scope + "::" + name;
                std::size_t end = 0;
                while (true) {
                    end = fullScope.find("::", end);
                    program.namespaces.insert(end == std::string::npos ? fullScope : fullScope.substr(0, end));
                    if (end == std::string::npos)
                        break;
                    end += 2;
                }
                need("{");
                declarations(program, fullScope, exported, true);
                need("}");
                continue;
            }
            if (eat("enum")) {
                need("class");
                EnumDefinition definition(ident());
                definition.scope = scope;
                definition.exported = exported;
                if (program.enums.size() >= 64)
                    fail("module exceeds 64 enum definitions");
                need("{");
                if (peek().text == "}")
                    fail("enum class requires at least one named case");
                std::set<std::string> cases;
                do {
                    if (definition.cases.size() >= 256)
                        fail("enum class exceeds 256 named cases");
                    auto name = ident();
                    if (!cases.insert(name.text).second)
                        fail("duplicate enum case: " + name.text);
                    if (peek().text == "=")
                        fail("enum cases cannot have explicit values");
                    definition.cases.push_back(std::move(name));
                    if (!eat(",") || peek().text == "}")
                        break;
                } while (true);
                need("}");
                need(";");
                program.enums.push_back(std::move(definition));
                continue;
            }
            std::vector<TemplateParameter> declaredParameters;
            if (eat("template")) {
                need("<");
                do {
                    if (declaredParameters.size() >= 2)
                        fail("templates require one or two Scalar or Value parameters");
                    TemplateParameterKind kind;
                    if (eat("Scalar"))
                        kind = TemplateParameterKind::Scalar;
                    else if (eat("Value"))
                        kind = TemplateParameterKind::Value;
                    else if (eat("i64"))
                        kind = TemplateParameterKind::Capacity;
                    else
                        fail("template parameters require Scalar, Value or bounded i64 capacity");
                    const auto parameter = ident().text;
                    if (parameter == "i64" || parameter == "u64" || parameter == "u8" || parameter == "bool" ||
                        parameter == "own" || parameter == "ref" || parameter == "mutref" || parameter == "array" ||
                        templateParameters.contains(parameter) || capacityParameters.contains(parameter))
                        fail("duplicate or reserved template parameter");
                    if (kind != TemplateParameterKind::Capacity)
                        templateParameters.insert(parameter);
                    else
                        capacityParameters.insert(parameter);
                    declaredParameters.emplace_back(kind, parameter);
                } while (eat(","));
                need(">");
                if (!capacityParameters.empty() && (declaredParameters.size() != 2 ||
                                                    declaredParameters.front().kind != TemplateParameterKind::Scalar ||
                                                    declaredParameters.back().kind != TemplateParameterKind::Capacity))
                    fail("template capacity requires a preceding Scalar parameter");
                if (peek().text != "class" && peek().text != "auto")
                    fail("only class or namespace-level function templates are supported");
                functionTemplate = peek().text == "auto";
                if (functionTemplate && !capacityParameters.empty())
                    fail("function templates require only Scalar or Value type parameters");
            }
            if (eat("class")) {
                ClassDefinition definition(ident(scope == "std"));
                if (templateParameters.contains(definition.name) || capacityParameters.contains(definition.name))
                    fail("class name cannot shadow a template parameter");
                definition.templateParameters = declaredParameters;
                definition.scope = scope;
                definition.exported = exported;
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
                    if ((peek().text == definition.token.text && tokens.at(position + 1).text == "(") ||
                        peek().text == "auto") {
                        const bool constructor = peek().text != "auto";
                        if (!constructor)
                            take();
                        Function method(ident(constructor && definition.token.text == "array"));
                        if (!constructor && method.token.text == definition.token.text)
                            fail("constructor cannot have a return type");
                        method.scope = scope;
                        method.publicAccess = publicAccess;
                        method.constructor = constructor;
                        parameters(method, constructor);
                        if (constructor) {
                            if (eat(":")) {
                                do {
                                    auto fieldName = ident();
                                    ExpressionPtr value;
                                    if (eat("{")) {
                                        need("}");
                                        value = std::make_shared<Expression>("array_zero", fieldName);
                                    } else {
                                        need("(");
                                        value = expr();
                                        need(")");
                                    }
                                    method.initializers.emplace_back(fieldName, value);
                                } while (eat(","));
                            }
                            need("{");
                            need("}");
                        } else {
                            method.receiverConst = eat("const");
                            need("->");
                            method.result = type();
                            if (!scalarOrParameter(method.result) && !method.result.isClass() &&
                                !method.result.isSpan())
                                fail("only scalar, enum, class or readonly span method results are supported");
                            method.body = block();
                        }
                        definition.methods.push_back(std::move(method));
                        continue;
                    }
                    auto fieldTypeSpan = peek().span;
                    auto fieldType = type();
                    fieldTypeSpan.end = tokens.at(position - 1).span.end;
                    auto fieldName = ident();
                    if (fieldType.isArray()) {
                        if (publicAccess)
                            fail("array fields must be private");
                        if (fieldType.lengthParameter.empty() &&
                            (fieldType.length < 1 ||
                             fieldType.length > maximumClassArrayLength(Type(fieldType.elementKind))))
                            fail("class array field capacity must be between 1 and " +
                                 std::to_string(maximumClassArrayLength(Type(fieldType.elementKind))));
                    } else if (fieldType.isBytes()) {
                        if (publicAccess)
                            fail("owned byte fields must be private");
                        if (!declaredParameters.empty())
                            fail("owning class templates are unsupported");
                    } else if (!scalarOrParameter(fieldType) && !fieldType.isClass())
                        throw Error(DiagnosticCode::UnexpectedToken,
                                    "unsupported class field type '" + typeName(fieldType) +
                                        "': class fields require scalar, class, private fixed-array or private "
                                        "owned-byte storage",
                                    fieldTypeSpan);
                    need(";");
                    definition.fields.emplace_back(fieldName, fieldType);
                    definition.fields.back().publicAccess = publicAccess;
                }
                need(";");
                if (declaredParameters.empty())
                    program.classes.push_back(std::move(definition));
                else
                    program.templates.push_back(std::move(definition));
                templateParameters.clear();
                capacityParameters.clear();
                continue;
            }
            need("auto");
            Function function(ident());
            function.scope = scope;
            function.exported = exported;
            function.templateParameters = declaredParameters;
            if (templateParameters.contains(function.token.text))
                fail("function name cannot shadow a template parameter");
            parameters(function, true, true);
            need("->");
            function.result = type();
            if (!scalarOrParameter(function.result) && !function.result.isClass() && !function.result.isBytes())
                fail("only scalar function results or scalar-field class values are supported");
            function.body = block();
            if (declaredParameters.empty())
                program.functions.push_back(std::move(function));
            else
                program.functionTemplates.push_back(std::move(function));
            templateParameters.clear();
            capacityParameters.clear();
            functionTemplate = false;
        }
    }
    Program parse() {
        Program program;
        program.interfaceUnit = eat("export");
        need("module");
        program.moduleName = moduleIdent().text;
        if (program.moduleName.size() > 4096)
            fail("module name exceeds 4096 bytes");
        need(";");
        while (eat("import")) {
            program.imports.push_back(moduleIdent());
            need(";");
        }
        declarations(program, "", false, false);
        if (program.functions.empty() && program.imports.empty() && !program.interfaceUnit)
            fail("module must contain a function");
        return program;
    }
};
} // namespace aurora
