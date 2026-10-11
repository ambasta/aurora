#pragma once
#include "syntax.hpp"
#include "hosted_parser.hpp"
#include <algorithm>
#include <cctype>
#include <set>
namespace aurora {
class Parser {
    std::vector<Token> tokens;
    std::size_t position = 0;
    std::set<std::string> templateParameters;
    std::set<std::string> capacityParameters;
    bool functionTemplate = false;
    std::vector<Token> templateParameterTokens, capacityParameterTokens;

public:
    explicit Parser(std::vector<Token> t) : tokens(std::move(t)) {
    }
    Token peek() const {
        return tokens.at(position);
    }
    Token take() {
        const auto token = tokens.at(position);
        // Keep EOF available for a located rejection in truncated declarations.
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
    hosted_parser::Context expressionContext() const {
        hosted_parser::Context context;
        context.typeParameters = templateParameterTokens;
        context.capacityParameters = capacityParameterTokens;
        context.functionTemplate = functionTemplate;
        return context;
    }
    ExpressionPtr statementExpression(hosted_parser::Stop stop) {
        return parseHostedExpression(tokens, position, stop, expressionContext());
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
                    const auto parameterToken = ident();
                    const auto &parameter = parameterToken.text;
                    if (parameter == "i64" || parameter == "u64" || parameter == "u8" || parameter == "bool" ||
                        parameter == "own" || parameter == "ref" || parameter == "mutref" || parameter == "array" ||
                        templateParameters.contains(parameter) || capacityParameters.contains(parameter))
                        fail("duplicate or reserved template parameter");
                    if (kind != TemplateParameterKind::Capacity) {
                        templateParameters.insert(parameter);
                        templateParameterTokens.push_back(parameterToken);
                    } else {
                        capacityParameters.insert(parameter);
                        capacityParameterTokens.push_back(parameterToken);
                    }
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
                        const auto stop =
                            peek().text == "auto" ? hosted_parser::Stop::method : hosted_parser::Stop::constructor;
                        const auto context = expressionContext();
                        auto parsed = parseHostedCallable(tokens, {position}, stop, context);
                        admitHostedCallable(parsed, stop, context, definition.token.text);
                        parsed.function.scope = scope;
                        parsed.function.publicAccess = publicAccess;
                        definition.methods.push_back(std::move(parsed.function));
                        position = parsed.next.ordinal;
                        continue;
                    }
                    auto parsed = parseHostedField(tokens, {position}, expressionContext());
                    admitHostedField(parsed, publicAccess, !declaredParameters.empty());
                    parsed.field.publicAccess = publicAccess;
                    definition.fields.push_back(std::move(parsed.field));
                    position = parsed.next.ordinal;
                }
                need(";");
                if (declaredParameters.empty())
                    program.classes.push_back(std::move(definition));
                else
                    program.templates.push_back(std::move(definition));
                templateParameters.clear();
                capacityParameters.clear();
                templateParameterTokens.clear();
                capacityParameterTokens.clear();
                continue;
            }
            const auto context = expressionContext();
            auto parsed = parseHostedCallable(tokens, {position}, hosted_parser::Stop::function, context);
            admitHostedCallable(parsed, hosted_parser::Stop::function, context);
            parsed.function.scope = scope;
            parsed.function.exported = exported;
            parsed.function.templateParameters = declaredParameters;
            if (declaredParameters.empty())
                program.functions.push_back(std::move(parsed.function));
            else
                program.functionTemplates.push_back(std::move(parsed.function));
            position = parsed.next.ordinal;
            templateParameters.clear();
            capacityParameters.clear();
            templateParameterTokens.clear();
            capacityParameterTokens.clear();
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
