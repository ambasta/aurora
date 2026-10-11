#pragma once
#include "syntax.hpp"
#include "services.hpp"
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
    bool scalarOrParameter(const Type &value) const {
        return scalar(value) || value.kind == TypeKind::Parameter;
    }
    Type type() {
        return parseHostedType(tokens, position, expressionContext());
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
                    const bool distinctServiceContinuation =
                        parameter.type.isService() && function.params.size() == 1 && function.params.front().borrowed &&
                        function.params.front().type.isService() && function.params.front().type != parameter.type &&
                        service::supportedGroup(
                            {service::kind(function.params.front().type), service::kind(parameter.type)});
                    if (!allowBorrow || (!function.params.empty() && !distinctServiceContinuation) ||
                        !templateParameters.empty() || (!parameter.type.isClass() && !parameter.type.isService()) ||
                        !parameter.type.templateArguments.empty())
                        fail("borrowed parameters require one leading concrete owning class on an ordinary function");
                } else if (parameter.borrowConst)
                    fail("const parameter spelling requires a leading owning-class reference");
                parameter.name = ident().text;
                // Nominal names are unresolved here; module resolution permits
                // enum method arguments and class constructor/function arguments.
                if (!scalarOrParameter(parameter.type) && !parameter.type.isClass() && !parameter.type.isSpan() &&
                    !(allowClass && parameter.type.isResource()) && !parameter.type.isService() &&
                    !parameter.type.isEnum())
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
                                    const auto fieldPosition = position;
                                    auto fieldName = ident();
                                    ExpressionPtr value;
                                    if (peek().text == "{") {
                                        auto candidate = fieldPosition;
                                        value = parseHostedExpression(tokens,
                                                                      candidate,
                                                                      hosted_parser::Stop::constructor_braces,
                                                                      expressionContext());
                                        position = candidate;
                                    } else {
                                        need("(");
                                        value = statementExpression(hosted_parser::Stop::close_parenthesis);
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
                                !method.result.isSpan() && !method.result.isEnum())
                                fail("only scalar, enum, class or readonly span method results are supported");
                            method.body = parseHostedBody(tokens, position, expressionContext());
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
                             fieldType.length > maximumClassArrayLength(fieldType.arrayElement())))
                            fail("class array field capacity must be between 1 and " +
                                 std::to_string(maximumClassArrayLength(fieldType.arrayElement())));
                    } else if (fieldType.isOwnerStorage()) {
                        if (publicAccess)
                            fail("owned byte fields must be private");
                        if (!declaredParameters.empty())
                            fail("owning class templates are unsupported");
                    } else if (!scalarOrParameter(fieldType) && !fieldType.isClass() && !fieldType.isEnum())
                        throw Error(DiagnosticCode::UnsupportedFieldType,
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
                templateParameterTokens.clear();
                capacityParameterTokens.clear();
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
            if (!scalarOrParameter(function.result) && !function.result.isClass() &&
                !function.result.isOwnerStorage() && !function.result.isEnum())
                fail("only scalar function results or scalar-field class values are supported");
            function.body = parseHostedBody(tokens, position, expressionContext());
            if (declaredParameters.empty())
                program.functions.push_back(std::move(function));
            else
                program.functionTemplates.push_back(std::move(function));
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
