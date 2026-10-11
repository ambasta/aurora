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
    int typeNesting = 0, templateNesting = 0;
    std::set<std::string> templateParameters;
    std::set<std::string> capacityParameters;
    bool functionTemplate = false;
    std::vector<Token> templateParameterTokens, capacityParameterTokens;
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
    std::vector<TemplateArgument> templateArguments() {
        Nesting nesting(templateNesting, maximumTemplateNesting, peek(), "template-id");
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
                    value.templateArguments = templateArguments();
                arguments.push_back(std::move(value));
            } else
                fail("template arguments require scalar, named class or enum types, or capacities "
                     "from 1 to 64");
        } while (eat(","));
        templateClose();
        return arguments;
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
            if (eat("IommuEventSession"))
                return Type::IommuEventSession;
            if (eat("IommuEventSample"))
                return service::eventSampleType();
            if (eat("EventPollResult"))
                return service::eventPollResultType();
            if (eat("EventAckResult"))
                return service::eventAckResultType();
            if (eat("EventIntakeCompletion"))
                return service::eventIntakeCompletionType();
            if (eat("DisplaySession"))
                return Type::DisplaySession;
            if (eat("DisplayPutResult"))
                return service::displayPutResultType();
            if (eat("DisplayCompletion"))
                return service::displayCompletionType();
            if (eat("ConsoleSession"))
                return Type::ConsoleSession;
            if (eat("ConsoleSample"))
                return service::sampleType();
            if (eat("ConsolePutResult"))
                return service::putResultType();
            if (eat("ConsoleCompletion"))
                return service::completionType();
            if (eat("ByteRegion"))
                return Type::ByteRegion;
            if (eat("OwnedBytes"))
                return Type::OwnedBytes;
            if (eat("OwnedValues")) {
                need("<");
                const auto element = type();
                if (!element.isClass() || !element.templateArguments.empty())
                    fail("owned values require a named concrete copied class");
                templateClose();
                return Type::ownedValues(element);
            }
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
            if (!scalarOrParameter(element) && !element.isClass())
                fail("array elements require i64, u64, u8, bool or a concrete copied class");
            need(",");
            const auto count = take();
            Type result = Type::array(element, 0);
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
            templateClose();
            if (element.isClass() && result.lengthParameter.empty() && result.length > maximumClassScalarArrayLength)
                fail("class-element array capacity must be between 1 and 64");
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
                                                                      hosted_parser::Stop::ConstructorBraces,
                                                                      expressionContext());
                                        position = candidate;
                                    } else {
                                        need("(");
                                        value = statementExpression(hosted_parser::Stop::CloseParenthesis);
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
