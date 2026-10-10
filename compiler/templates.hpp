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
                if (found == substitutions.end() || !scalar(found->second))
                    throw Error("class template array element parameter requires a scalar type: " +
                                value.elementParameter);
                value.setArrayElement(found->second);
            }
            if (!value.lengthParameter.empty()) {
                const auto found = capacities.find(value.lengthParameter);
                if (found == capacities.end())
                    throw Error("unknown array capacity parameter: " + value.lengthParameter);
                value.length = static_cast<int>(found->second);
                value.lengthParameter.clear();
            }
            const auto element = value.arrayElement();
            if ((!scalar(element) && !element.isClass()) || value.length < 1 ||
                value.length > (element.isClass() ? maximumClassScalarArrayLength : 4096))
                throw Error("invalid array type after template substitution");
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
        if (!argument.templateArguments.empty())
            throw Error("unresolved nested class template argument");
        Type result(argument.type);
        if (argument.type == TypeKind::Class || argument.type == TypeKind::Enum) {
            result.className = argument.className;
            result.displayName = argument.displayName;
            result.resolvedClass = true;
        }
        return result;
    }
    static std::string argumentSuffix(const std::vector<TemplateArgument> &arguments, bool display = false) {
        std::string result = "<";
        for (std::size_t index = 0; index < arguments.size(); ++index) {
            if (index)
                result += ",";
            const auto &argument = arguments[index];
            if (!argument.templateArguments.empty())
                throw Error("unresolved nested class template argument");
            if (argument.kind == TemplateArgumentKind::Value)
                result += std::to_string(argument.value);
            else if (argument.type == TypeKind::Class || argument.type == TypeKind::Enum)
                result += display && !argument.displayName.empty() ? argument.displayName : argument.className;
            else
                result += typeName(Type(argument.type));
        }
        return result + ">";
    }
    static std::string nativeSuffix(const std::vector<TemplateArgument> &arguments) {
        std::string result = "_t" + std::to_string(arguments.size());
        for (const auto &argument : arguments) {
            if (!argument.templateArguments.empty())
                throw Error("unresolved nested class template argument");
            if (argument.kind == TemplateArgumentKind::Type) {
                if (argument.type == TypeKind::Class && !argument.className.empty())
                    result += "_c" + std::to_string(argument.className.size()) + argument.className;
                else if (argument.type == TypeKind::Enum && !argument.className.empty())
                    result += "_e" + std::to_string(argument.className.size()) + argument.className;
                else if (scalar(Type(argument.type)))
                    result += "_" + typeName(Type(argument.type));
                else
                    throw Error("class template type arguments require scalar, named class or enum values");
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
            throw Error("class templates require one or two Scalar or Value parameters, or Scalar and i64");
        std::set<std::string> parameters;
        std::vector<TemplateArgument> arguments;
        for (std::size_t index = 0; index < definition.templateParameters.size(); ++index) {
            const auto &parameter = definition.templateParameters[index];
            if (!parameters.insert(parameter.name).second)
                throw Error("duplicate class template parameter: " + parameter.name);
            if (parameter.kind == TemplateParameterKind::Capacity) {
                if (index != 1 || definition.templateParameters[0].kind != TemplateParameterKind::Scalar)
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
            if (!argument.templateArguments.empty())
                throw Error("unresolved nested class template argument");
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
                if (argument.kind != TemplateArgumentKind::Value || argument.value < 1 || argument.value > 64)
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

// This distinct expander intentionally does not relax class-template bodies.
// Its only generated requests are statically named class specializations.
class FunctionTemplateExpansion {
    std::map<std::string, Type> substitutions;
    std::vector<TemplateArgument> arguments(const std::vector<TemplateArgument> &source, bool nested = false) const {
        auto result = source;
        for (auto &argument : result) {
            name(argument.className);
            if (argument.type == TypeKind::Parameter) {
                if (nested || !argument.templateArguments.empty())
                    throw Error("nested dependent template arguments are not supported");
                const auto found = substitutions.find(argument.className);
                if (found == substitutions.end())
                    throw Error("unknown function template parameter: " + argument.className);
                argument.type = found->second.kind;
                argument.className = found->second.className;
                argument.displayName = found->second.displayName;
                argument.resolvedClass = found->second.resolvedClass;
            } else
                argument.templateArguments = arguments(argument.templateArguments, true);
        }
        return result;
    }
    Type type(Type value) const {
        name(value.className);
        if (value.kind == TypeKind::Parameter) {
            const auto found = substitutions.find(value.className);
            if (found == substitutions.end())
                throw Error("unknown function template parameter: " + value.className);
            return found->second;
        }
        value.templateArguments = arguments(value.templateArguments);
        if (!value.elementParameter.empty()) {
            const auto found = substitutions.find(value.elementParameter);
            if (found == substitutions.end() || !scalar(found->second))
                throw Error("function template array element requires a scalar type");
            value.setArrayElement(found->second);
        }
        if (!value.lengthParameter.empty())
            throw Error("function templates do not have capacity parameters");
        return value;
    }
    void name(const std::string &value) const {
        for (const auto &[parameter, unused] : substitutions) {
            (void)unused;
            if (value.starts_with(parameter + "::"))
                throw Error("dependent qualified names are not supported: " + value);
        }
    }
    ExpressionPtr expression(const ExpressionPtr &source) const {
        if (!source)
            return nullptr;
        name(source->token.text);
        if ((source->op == "call" || source->op == "construct") && substitutions.contains(source->token.text))
            throw Error("dependent construction or conversion is not supported: " + source->token.text);
        auto result = std::make_shared<Expression>(*source);
        result->templateArguments = arguments(source->templateArguments);
        result->reflectedType = type(source->reflectedType);
        result->args.clear();
        for (const auto &argument : source->args)
            result->args.push_back(expression(argument));
        return result;
    }
    StatementPtr statement(const StatementPtr &source) const {
        if (source->kind == "let" && substitutions.contains(source->name))
            throw Error("local cannot shadow a function template parameter: " + source->name);
        auto result = std::make_shared<Statement>(*source);
        result->type = type(source->type);
        result->expr = expression(source->expr);
        result->target = expression(source->target);
        result->body.clear();
        result->other.clear();
        for (const auto &child : source->body)
            result->body.push_back(statement(child));
        for (const auto &child : source->other)
            result->other.push_back(statement(child));
        return result;
    }

public:
    static Function instantiate(const Function &source, const std::vector<TemplateArgument> &arguments) {
        if (arguments.size() != source.templateParameters.size())
            throw Error("wrong number of function template arguments for " + source.token.text);
        FunctionTemplateExpansion expansion;
        for (std::size_t index = 0; index < arguments.size(); ++index) {
            const auto &parameter = source.templateParameters[index];
            const auto &argument = arguments[index];
            const auto value = ClassTemplateExpansion::argumentType(argument);
            if (argument.kind != TemplateArgumentKind::Type ||
                (parameter.kind == TemplateParameterKind::Scalar && !scalar(value)) ||
                (parameter.kind == TemplateParameterKind::Value && !scalarValue(value) && !value.isClass()) ||
                parameter.kind == TemplateParameterKind::Capacity)
                throw Error("function template argument violates Scalar or Value constraint");
            expansion.substitutions.emplace(parameter.name, value);
        }
        Function result = source;
        result.templateParameters.clear();
        result.templateArguments = arguments;
        result.exported = false;
        result.result = expansion.type(source.result);
        for (auto &parameter : result.params) {
            if (expansion.substitutions.contains(parameter.name))
                throw Error("function parameter cannot shadow a template parameter: " + parameter.name);
            parameter.type = expansion.type(parameter.type);
        }
        result.body.clear();
        for (const auto &statement : source.body)
            result.body.push_back(expansion.statement(statement));
        return result;
    }
    static void validate(const Function &source) {
        if (source.templateParameters.empty() || source.templateParameters.size() > 2 ||
            !source.receiverClass.empty() || source.constructor)
            throw Error("function templates require one or two namespace-level type parameters");
        auto boundary = [](const Type &type) {
            if (!scalarValue(type) && !type.isClass() && type.kind != TypeKind::Parameter)
                throw Error("function template boundaries require copied Scalar or Value types");
        };
        boundary(source.result);
        for (const auto &parameter : source.params)
            boundary(parameter.type);
        std::set<std::string> names;
        std::vector<TemplateArgument> arguments;
        for (const auto &parameter : source.templateParameters) {
            if (parameter.kind == TemplateParameterKind::Capacity || !names.insert(parameter.name).second)
                throw Error("function templates require distinct Scalar or Value parameters");
            arguments.push_back(TypeKind::I64);
        }
        // Disposable scalar substitution checks structural restrictions even for
        // unrequested definitions, without claiming universal body validity.
        (void)instantiate(source, arguments);
    }
};

} // namespace aurora
