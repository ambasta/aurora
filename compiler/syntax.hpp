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
    int depth = 1;
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
    std::vector<Param> params;
    std::vector<StatementPtr> body;
    explicit Function(Token t) : name(t.text), token(std::move(t)), result(Type::I64) {}
};
class Field {
  public:
    Token token;
    Type type;
    int offset = 0;
    bool publicAccess = false;
    Field(Token name, Type value) : token(std::move(name)), type(std::move(value)) {}
};
class ClassDefinition {
  public:
    std::string name;
    std::string scope;
    bool exported = false;
    Token token;
    std::vector<Field> fields;
    int id = 0;
    explicit ClassDefinition(Token token) : name(token.text), token(std::move(token)) {}
};
class Program {
  public:
    std::string moduleName;
    bool interfaceUnit = false;
    std::vector<Token> imports;
    std::set<std::string> namespaces;
    std::map<int, std::set<std::string>> reflectionAccess;
    std::vector<Function> functions;
    std::vector<ClassDefinition> classes;
};

} // namespace aurora
