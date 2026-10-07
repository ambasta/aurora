#pragma once
#include "types.hpp"
#include <map>
#include <memory>
#include <set>
#include <vector>
namespace aurora {
class Expression {
  public:
    std::string op;
    std::string resolvedName;
    // Resolver-owned visible ordinary overloads; unavailable signature authority
    // is recorded per candidate and checked only after exact argument selection.
    std::vector<std::string> overloadCandidates;
    std::set<std::string> inaccessibleOverloads;
    int depth = 1;
    Token token;
    std::vector<std::shared_ptr<Expression>> args;
    std::vector<std::string> fieldNames;
    std::vector<TemplateArgument> templateArguments;
    Type reflectedType;
    int enumOrdinal = -1;
    Expression(std::string o, Token t) : op(std::move(o)), token(std::move(t)) {}
};
using ExpressionPtr = std::shared_ptr<Expression>;
class Statement {
  public:
    std::string kind, name, fieldName;
    Token token;
    Type type = Type::I64;
    // Lexical provenance of a declaration's identifier, not its type/const token.
    SourceSpan bindingSpan;
    bool mutableValue = false;
    ExpressionPtr expr, target;
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
    std::string scope;
    bool exported = false;
    int moduleScope = 0;
    Token token;
    Type result;
    std::string receiverClass;
    bool receiverConst = false, constructor = false, publicAccess = false;
    std::vector<std::pair<Token, ExpressionPtr>> initializers;
    std::vector<TemplateParameter> templateParameters;
    std::vector<TemplateArgument> templateArguments;
    // Exact compile-time authority only. Runtime reflection keeps moduleScope.
    std::set<std::string> templateTypeAuthority;
    std::vector<Param> params;
    std::vector<StatementPtr> body;
    explicit Function(Token t) : name(t.text), token(std::move(t)), result(Type::I64) {}
};
class Field {
  public:
    Token token;
    Type type;
    int offset = 0;
    int index = 0;
    bool publicAccess = false;
    Field(Token name, Type value) : token(std::move(name)), type(std::move(value)) {}
};
class ClassDefinition {
  public:
    std::string name;
    std::string scope;
    bool exported = false;
    Token token;
    std::vector<TemplateParameter> templateParameters;
    std::vector<TemplateArgument> templateArguments;
    std::vector<Field> fields;
    std::vector<Function> methods;
    int id = 0;
    explicit ClassDefinition(Token token) : name(token.text), token(std::move(token)) {}
};
class EnumDefinition {
  public:
    std::string name;
    std::string scope;
    bool exported = false;
    Token token;
    std::vector<Token> cases;
    int id = 0;
    explicit EnumDefinition(Token token) : name(token.text), token(std::move(token)) {}
};
class Program {
  public:
    std::string moduleName;
    bool interfaceUnit = false;
    std::vector<Token> imports;
    std::set<std::string> namespaces;
    std::map<int, std::set<std::string>> reflectionAccess;
    std::vector<Function> functions;
    std::vector<Function> functionTemplates;
    std::vector<ClassDefinition> classes;
    std::vector<ClassDefinition> templates;
    std::vector<EnumDefinition> enums;
};

} // namespace aurora
