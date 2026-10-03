#pragma once
#include "syntax.hpp"
#include <algorithm>
#include <map>
#include <set>

namespace aurora {
// Source templates never enter semantic analysis or IR. Each concrete class is
// a deep copy: substituting one specialization cannot mutate another one.
class ClassTemplateExpansion {
    std::map<std::string, Type> substitutions;
    std::map<std::string, std::int64_t> capacities;

    void cannotShadowCapacity(const std::string &name) const {
        if (capacities.contains(name))
            throw Error("declaration cannot shadow capacity parameter: " + name);
    }

    Type type(Type value) const {
        if (!value.templateArguments.empty())
            throw Error("class template bodies cannot name template specializations");
        if (value.kind == TypeKind::Parameter) {
            const auto found = substitutions.find(value.className);
            if (found == substitutions.end())
                throw Error("unknown class template parameter: " + value.className);
            return found->second;
        }
        if (value.isArray()) {
            if (!value.elementParameter.empty()) {
                const auto found = substitutions.find(value.elementParameter);
                if (found == substitutions.end())
                    throw Error("unknown scalar array element parameter: " +
                                value.elementParameter);
                value.elementKind = found->second.kind;
                value.elementParameter.clear();
            }
            if (!value.lengthParameter.empty()) {
                const auto found = capacities.find(value.lengthParameter);
                if (found == capacities.end())
                    throw Error("unknown array capacity parameter: " + value.lengthParameter);
                value.length = static_cast<int>(found->second);
                value.lengthParameter.clear();
            }
            if (!scalar(Type(value.elementKind)) || value.length < 1 || value.length > 4096)
                throw Error("invalid scalar array type after template substitution");
        } else if (!value.elementParameter.empty() || !value.lengthParameter.empty())
            throw Error("dependent array metadata requires an array type");
        return value;
    }
    ExpressionPtr expression(const ExpressionPtr &value) const {
        if (!value)
            return nullptr;
        if (!value->templateArguments.empty())
            throw Error("class template bodies cannot name template specializations");
        if (value->op == "call" && substitutions.contains(value->token.text))
            throw Error("dependent scalar conversions are not supported: " + value->token.text);
        if (value->op == "call" && capacities.contains(value->token.text))
            throw Error("capacity parameter is not callable: " + value->token.text);
        if (value->op == "call" && value->token.text == "move")
            for (const auto &argument : value->args)
                if (argument->op == "name" && capacities.contains(argument->token.text))
                    throw Error("cannot move a capacity parameter: " + argument->token.text);
        auto result = std::make_shared<Expression>(*value);
        if (value->op == "name")
            if (const auto found = capacities.find(value->token.text); found != capacities.end()) {
                result->op = "number";
                result->token.text = std::to_string(found->second);
                result->resolvedName.clear();
            }
        result->reflectedType = type(value->reflectedType);
        result->args.clear();
        for (const auto &argument : value->args)
            result->args.push_back(expression(argument));
        return result;
    }
    StatementPtr statement(const StatementPtr &value) const {
        if (value->kind == "let")
            cannotShadowCapacity(value->name);
        if (value->kind == "assign" && capacities.contains(value->name))
            throw Error("cannot assign to a capacity parameter: " + value->name);
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
    static Type argumentType(const TemplateArgument &argument) {
        Type result(argument.type);
        if (argument.type == TypeKind::Class || argument.type == TypeKind::Enum) {
            result.className = argument.className;
            result.displayName = argument.displayName;
            result.resolvedClass = true;
        }
        return result;
    }
    static std::string argumentSuffix(const std::vector<TemplateArgument> &arguments,
                                      bool display = false) {
        std::string result = "<";
        for (std::size_t index = 0; index < arguments.size(); ++index) {
            if (index)
                result += ",";
            const auto &argument = arguments[index];
            if (argument.kind == TemplateArgumentKind::Value)
                result += std::to_string(argument.value);
            else if (argument.type == TypeKind::Class || argument.type == TypeKind::Enum)
                result += display && !argument.displayName.empty() ? argument.displayName
                                                                   : argument.className;
            else
                result += typeName(Type(argument.type));
        }
        return result + ">";
    }
    static std::string nativeSuffix(const std::vector<TemplateArgument> &arguments) {
        std::string result = "_t" + std::to_string(arguments.size());
        for (const auto &argument : arguments) {
            if (argument.kind == TemplateArgumentKind::Type) {
                if (argument.type == TypeKind::Class && !argument.className.empty())
                    result += "_c" + std::to_string(argument.className.size()) + argument.className;
                else if (argument.type == TypeKind::Enum && !argument.className.empty())
                    result += "_e" + std::to_string(argument.className.size()) + argument.className;
                else if (scalar(Type(argument.type)))
                    result += "_" + typeName(Type(argument.type));
                else
                    throw Error(
                        "class template type arguments require scalar, named class or enum values");
            } else {
                if (argument.value < 1 || argument.value > 64)
                    throw Error("class template capacity must be between 1 and 64");
                result += "_v" + std::to_string(argument.value);
            }
        }
        return result;
    }
    static void validate(const ClassDefinition &definition) {
        if (definition.templateParameters.empty() || definition.templateParameters.size() > 2)
            throw Error(
                "class templates require one or two Scalar or Value parameters, or Scalar and i64");
        std::set<std::string> parameters;
        std::vector<TemplateArgument> arguments;
        for (std::size_t index = 0; index < definition.templateParameters.size(); ++index) {
            const auto &parameter = definition.templateParameters[index];
            if (!parameters.insert(parameter.name).second)
                throw Error("duplicate class template parameter: " + parameter.name);
            if (parameter.kind == TemplateParameterKind::Capacity) {
                if (index != 1 ||
                    definition.templateParameters[0].kind != TemplateParameterKind::Scalar)
                    throw Error("capacity templates require Scalar followed by i64");
                arguments.push_back(TemplateArgument::capacity(1));
            } else
                arguments.push_back(TypeKind::I64);
        }
        // Checking a disposable scalar copy catches malformed dependent type
        // references even when the source template is never instantiated.
        (void)instantiate(definition, arguments);
    }
    static ClassDefinition instantiate(const ClassDefinition &definition,
                                       const std::vector<TemplateArgument> &arguments) {
        if (arguments.size() != definition.templateParameters.size())
            throw Error("wrong number of class template arguments for " + definition.token.text);
        ClassTemplateExpansion expansion;
        for (std::size_t index = 0; index < arguments.size(); ++index) {
            const auto &parameter = definition.templateParameters[index];
            const auto &argument = arguments[index];
            if (parameter.kind == TemplateParameterKind::Scalar) {
                if (argument.kind != TemplateArgumentKind::Type || !scalar(Type(argument.type)))
                    throw Error("class template Scalar argument requires i64, u64, u8 or bool");
                expansion.substitutions.emplace(parameter.name, argumentType(argument));
            } else if (parameter.kind == TemplateParameterKind::Value) {
                if (argument.kind != TemplateArgumentKind::Type ||
                    (!scalar(Type(argument.type)) &&
                     ((argument.type != TypeKind::Class && argument.type != TypeKind::Enum) ||
                      argument.className.empty())))
                    throw Error("class template Value argument requires scalar, named class or "
                                "enum values");
                expansion.substitutions.emplace(parameter.name, argumentType(argument));
            } else {
                if (argument.kind != TemplateArgumentKind::Value || argument.value < 1 ||
                    argument.value > 64)
                    throw Error("class template capacity requires an i64 value between 1 and 64");
                expansion.capacities.emplace(parameter.name, argument.value);
            }
        }
        ClassDefinition result = definition;
        result.templateParameters.clear();
        result.templateArguments = arguments;
        for (auto &field : result.fields) {
            expansion.cannotShadowCapacity(field.token.text);
            field.type = expansion.type(field.type);
        }
        for (auto &method : result.methods) {
            expansion.cannotShadowCapacity(method.token.text);
            method.result = expansion.type(method.result);
            for (auto &parameter : method.params) {
                expansion.cannotShadowCapacity(parameter.name);
                parameter.type = expansion.type(parameter.type);
            }
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
