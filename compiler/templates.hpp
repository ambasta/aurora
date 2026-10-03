#pragma once
#include "syntax.hpp"
#include <algorithm>
#include <map>
#include <set>

namespace aurora {
// Source templates never enter semantic analysis or IR. Each concrete class is
// a deep copy: substituting one specialization cannot mutate another one.
class ClassTemplateExpansion {
    std::map<std::string, TypeKind> substitutions;

    Type type(Type value) const {
        if (!value.templateArguments.empty())
            throw Error("class template bodies cannot name template specializations");
        if (value.kind == TypeKind::Parameter) {
            const auto found = substitutions.find(value.className);
            if (found == substitutions.end())
                throw Error("unknown class template parameter: " + value.className);
            return Type(found->second);
        }
        return value;
    }
    ExpressionPtr expression(const ExpressionPtr &value) const {
        if (!value)
            return nullptr;
        if (!value->templateArguments.empty())
            throw Error("class template bodies cannot name template specializations");
        if (value->op == "call" && substitutions.contains(value->token.text))
            throw Error("dependent scalar conversions are not supported: " + value->token.text);
        auto result = std::make_shared<Expression>(*value);
        result->reflectedType = type(value->reflectedType);
        result->args.clear();
        for (const auto &argument : value->args)
            result->args.push_back(expression(argument));
        return result;
    }
    StatementPtr statement(const StatementPtr &value) const {
        auto result = std::make_shared<Statement>(*value);
        result->type = type(value->type);
        result->expr = expression(value->expr);
        result->target = expression(value->target);
        result->body.clear();
        result->other.clear();
        for (const auto &child : value->body)
            result->body.push_back(statement(child));
        for (const auto &child : value->other)
            result->other.push_back(statement(child));
        return result;
    }

  public:
    static std::string argumentSuffix(const std::vector<TypeKind> &arguments) {
        std::string result = "<";
        for (std::size_t index = 0; index < arguments.size(); ++index) {
            if (index)
                result += ",";
            result += typeName(Type(arguments[index]));
        }
        return result + ">";
    }
    static std::string nativeSuffix(const std::vector<TypeKind> &arguments) {
        std::string result = "_t" + std::to_string(arguments.size());
        for (const auto argument : arguments) {
            if (!scalar(Type(argument)))
                throw Error("class template arguments require i64, u64 or bool");
            result += "_" + typeName(Type(argument));
        }
        return result;
    }
    static void validate(const ClassDefinition &definition) {
        if (definition.templateParameters.empty() || definition.templateParameters.size() > 2)
            throw Error("class templates require one or two Scalar parameters");
        std::set<std::string> parameters;
        for (const auto &parameter : definition.templateParameters)
            if (!parameters.insert(parameter).second)
                throw Error("duplicate class template parameter: " + parameter);
        // Checking a disposable scalar copy catches malformed dependent type
        // references even when the source template is never instantiated.
        std::vector<TypeKind> arguments(definition.templateParameters.size(), TypeKind::I64);
        (void)instantiate(definition, arguments);
    }
    static ClassDefinition instantiate(const ClassDefinition &definition,
                                       const std::vector<TypeKind> &arguments) {
        if (arguments.size() != definition.templateParameters.size())
            throw Error("wrong number of class template arguments for " + definition.token.text);
        ClassTemplateExpansion expansion;
        for (std::size_t index = 0; index < arguments.size(); ++index) {
            if (!scalar(Type(arguments[index])))
                throw Error("class template arguments require i64, u64 or bool");
            expansion.substitutions.emplace(definition.templateParameters[index], arguments[index]);
        }
        ClassDefinition result = definition;
        result.templateParameters.clear();
        result.templateArguments = arguments;
        for (auto &field : result.fields)
            field.type = expansion.type(field.type);
        for (auto &method : result.methods) {
            method.result = expansion.type(method.result);
            for (auto &parameter : method.params)
                parameter.type = expansion.type(parameter.type);
            for (auto &[field, initializer] : method.initializers) {
                (void)field;
                initializer = expansion.expression(initializer);
            }
            for (auto &value : method.body)
                value = expansion.statement(value);
        }
        return result;
    }
};
} // namespace aurora
