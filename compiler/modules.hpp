#pragma once
#include "host_sources.hpp"
#include "lexer.hpp"
#include "parser.hpp"
#include "templates.hpp"
#include <filesystem>
#include <fstream>
#include <map>
#include <set>

namespace aurora {
// Keys and snapshot paths are absolute, lexically normalized paths. Overrides
// replace bytes only after the existing source-opening policy authorizes a file.
using SourceOverlays = std::map<std::filesystem::path, std::shared_ptr<const SourceText>>;
// Host bootstrap file reads are limited to named modules beneath explicit
// roots. No source construct performs arbitrary filesystem or network
// operations.
class ModuleLoader {
public:
    class Unit {
    public:
        Program program;
        std::filesystem::path path;
        bool root = false;
        int scope = 0;
    };
    class Graph {
    public:
        std::map<std::string, std::unique_ptr<Unit>> units;
        std::vector<std::string> order;
        std::string root;
        std::set<host::Identity> sourceIdentities;
    };

private:
    static constexpr std::size_t maxFileBytes = 1024 * 1024;
    static constexpr std::size_t maxGraphBytes = 4 * 1024 * 1024;
    std::vector<host::Directory> roots;
    SourceOverlays overlays;
    std::size_t bytesRead = 0;
    Graph graph;
    std::set<std::string> active;
    std::shared_ptr<const SourceText> read(host::SourceFile file) {
        graph.sourceIdentities.insert(file.identity);
        const auto remaining = maxGraphBytes - bytesRead;
        try {
            const auto overlay = overlays.empty()
                                     ? overlays.end()
                                     : overlays.find(std::filesystem::absolute(file.displayPath).lexically_normal());
            std::shared_ptr<const SourceText> snapshot;
            if (overlay != overlays.end()) {
                snapshot = overlay->second;
                if (snapshot->text.size() > std::min(maxFileBytes, remaining))
                    throw host::ReadLimit();
            } else {
                auto contents = file.readAtMost(std::min(maxFileBytes, remaining));
                snapshot = std::make_shared<const SourceText>(file.displayPath.string(), std::move(contents));
            }
            bytesRead += snapshot->text.size();
            return snapshot;
        } catch (const host::ReadLimit &) {
            throw Error(remaining < maxFileBytes ? "module graph exceeds 4194304 bytes"
                                                 : "module file exceeds 1048576 bytes");
        }
    }
    host::SourceFile resolve(const std::string &name) {
        if (roots.empty())
            throw Error("imports require an explicit --module-root");
        std::filesystem::path relative;
        std::size_t start = 0, components = 0;
        while (start < name.size()) {
            auto end = name.find('.', start);
            const auto part = name.substr(start, end == std::string::npos ? name.size() - start : end - start);
            if (part.empty() || part.size() > 128 || ++components > 32)
                throw Error("invalid or excessive module name");
            for (char c : part)
                if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_'))
                    throw Error("invalid module path component");
            relative /= part;
            if (end == std::string::npos)
                break;
            start = end + 1;
        }
        relative += ".au";
        std::vector<host::SourceFile> found;
        for (const auto &root : roots) {
            auto file = root.open(relative);
            if (file)
                found.push_back(std::move(*file));
        }
        if (found.empty())
            throw Error("module not found in explicit roots: " + name);
        if (found.size() != 1)
            throw Error("ambiguous module found in multiple roots: " + name);
        return std::move(found.front());
    }
    void visit(const std::string &name, int depth) {
        if (depth > 16)
            throw Error("module import depth exceeds 16");
        if (active.contains(name))
            throw Error("module import cycle involving " + name);
        if (std::find(graph.order.begin(), graph.order.end(), name) != graph.order.end())
            return;
        active.insert(name);
        auto &unit = *graph.units.at(name);
        std::set<std::string> imports;
        for (const auto &import : unit.program.imports) {
            if (!imports.insert(import.text).second)
                throw Error("duplicate import in " + name + ": " + import.text);
            if (!graph.units.contains(import.text)) {
                if (graph.units.size() >= 64)
                    throw Error("module graph exceeds 64 files");
                auto imported = std::make_unique<Unit>();
                auto file = resolve(import.text);
                imported->path = file.displayPath;
                try {
                    imported->program = Parser(lex(read(std::move(file)))).parse();
                } catch (const Error &error) {
                    throw error.withContext("module " + import.text + ": ");
                }
                if (imported->program.moduleName != import.text)
                    throw Error("module header mismatch: expected " + import.text + ", got " +
                                imported->program.moduleName);
                if (!imported->program.interfaceUnit)
                    throw Error("imported module requires an export module interface: " + import.text);
                graph.units.emplace(import.text, std::move(imported));
            }
            visit(import.text, depth + 1);
        }
        active.erase(name);
        graph.order.push_back(name);
    }

public:
    explicit ModuleLoader(const std::vector<std::filesystem::path> &searchRoots, SourceOverlays sourceOverlays = {})
        : overlays(std::move(sourceOverlays)) {
        if (overlays.size() > 64)
            throw Error("source overlays exceed 64 files");
        std::size_t overlayBytes = 0;
        for (const auto &[path, snapshot] : overlays) {
            if (!snapshot || !path.is_absolute() || path.native() != path.lexically_normal().native() ||
                path.string().find('\0') != std::string::npos || snapshot->path != path.string())
                throw Error("source overlay requires an absolute normalized path matching its snapshot");
            if (snapshot->text.size() > maxFileBytes)
                throw Error("source overlay exceeds 1048576 bytes");
            if (snapshot->text.size() > maxGraphBytes - overlayBytes)
                throw Error("source overlays exceed 4194304 bytes");
            overlayBytes += snapshot->text.size();
        }
        if (searchRoots.size() > 16)
            throw Error("at most 16 explicit module roots are supported");
        std::set<std::pair<std::uint64_t, std::uint64_t>> unique;
        for (const auto &path : searchRoots) {
            host::Directory root(path);
            if (!unique.insert(root.identity).second)
                throw Error("duplicate module search root");
            roots.push_back(std::move(root));
        }
    }
    Graph load(const std::filesystem::path &rootPath) {
        auto root = std::make_unique<Unit>();
        root->root = true;
        root->scope = 0;
        root->path = rootPath;
        root->program = Parser(lex(read(host::SourceFile::explicitPath(rootPath)))).parse();
        graph.root = root->program.moduleName;
        graph.units.emplace(graph.root, std::move(root));
        visit(graph.root, 0);
        int scope = 1;
        for (const auto &name : graph.order)
            if (name != graph.root)
                graph.units.at(name)->scope = scope++;
        return std::move(graph);
    }
};

class ModuleResolver {
    enum class Kind {
        Function,
        Class,
        Template,
        FunctionTemplate,
        Enum,
        Any
    };
    Function *activeFunction = nullptr;
    const ClassDefinition *activeClass = nullptr;
    bool initializingReceiver = false, classTypesResolved = false;
    class Declaration {
    public:
        Kind kind;
        std::string qualified;
        std::string native;
        bool exported;
        std::string module;
        const ClassDefinition *templateDefinition = nullptr;
        const Function *functionTemplateDefinition = nullptr;
        const EnumDefinition *enumDefinition = nullptr;
        std::vector<std::pair<std::string, bool>> overloads{};
    };
    ModuleLoader::Graph graph;
    std::map<std::string, std::map<std::string, Declaration>> declarations;
    std::map<std::string, const Declaration *> nativeClasses;
    std::map<std::string, std::vector<Type>> signatures;
    std::map<std::string, std::vector<TemplateArgument>> instanceArguments;
    std::map<std::string, std::vector<Type>> publicTypes;
    std::vector<std::pair<std::string, Type>> argumentVisibilityChecks;
    std::size_t instanceCount = 0;
    std::map<std::string, int> instanceNesting;
    std::map<std::string, std::string> instanceDisplayNames;
    const std::set<std::string> builtins = {"i64",
                                            "u64",
                                            "u8",
                                            "own",
                                            "move",
                                            "borrow",
                                            "borrow_mut",
                                            "borrow_bytes",
                                            "read",
                                            "write",
                                            "size_of",
                                            "type_id",
                                            "field_count",
                                            "len",
                                            "reflect_size",
                                            "reflect_field_count",
                                            "aurora_reflect_size",
                                            "aurora_reflect_field_count"};
    static std::string qualify(const std::string &scope, const std::string &name) {
        return scope.empty() ? name : scope + "::" + name;
    }
    static std::vector<std::string> split(const std::string &value, const std::string &separator) {
        std::vector<std::string> result;
        if (value.empty())
            return result;
        std::size_t start = 0;
        while (start < value.size()) {
            auto end = value.find(separator, start);
            result.push_back(value.substr(start, end == std::string::npos ? value.size() - start : end - start));
            if (end == std::string::npos)
                break;
            start = end + separator.size();
        }
        return result;
    }
    static void sourceName(const std::string &name) {
        for (const auto &part : split(name, "::")) {
            if (part.starts_with("__au_"))
                throw Error("reserved compiler identifier prefix: __au_");
            if (part == "builtin")
                throw Error("reserved builtin namespace or identifier: builtin");
        }
    }
    static std::string mangle(char kind, const std::string &module, const std::string &scope, const std::string &name) {
        const auto modules = split(module, "."), spaces = split(scope, "::");
        std::string result = "__au_" + std::string(1, kind) + "_m" + std::to_string(modules.size()) + "_";
        for (const auto &part : modules)
            result += std::to_string(part.size()) + part;
        result += "_n" + std::to_string(spaces.size()) + "_";
        for (const auto &part : spaces)
            result += std::to_string(part.size()) + part;
        return result + "_d" + std::to_string(name.size()) + name;
    }
    void registerMembers(ClassDefinition &definition, const ModuleLoader::Unit &unit) {
        std::set<std::string> members;
        for (const auto &field : definition.fields)
            members.insert(field.token.text);
        const auto classScope = qualify(definition.scope, definition.token.text);
        const auto instanceSuffix = definition.templateArguments.empty()
                                        ? ""
                                        : ClassTemplateExpansion::nativeSuffix(definition.templateArguments);
        for (auto &method : definition.methods) {
            sourceName(method.token.text);
            if (builtins.contains(method.token.text) || (method.token.text == "array" && !method.constructor) ||
                !members.insert(method.token.text).second)
                throw Error("duplicate or reserved class member: " + method.token.text);
            method.name =
                mangle(method.constructor ? 'k' : 'm', unit.program.moduleName, classScope, method.token.text) +
                instanceSuffix;
            method.receiverClass = definition.name;
            method.moduleScope = unit.scope;
        }
    }
    void registerDeclarations() {
        std::size_t templateCount = 0, enumCount = 0;
        for (const auto &name : graph.order) {
            auto &unit = *graph.units.at(name);
            auto &table = declarations[name];
            for (const auto &scope : unit.program.namespaces)
                sourceName(scope);
            auto add = [&](Kind kind,
                           const std::string &scope,
                           const std::string &leaf,
                           bool exported,
                           bool valueBoundary = false) -> std::string {
                sourceName(scope);
                sourceName(leaf);
                const auto qualified = qualify(scope, leaf);
                if (unit.program.namespaces.contains(qualified))
                    throw Error("namespace and declaration name collide: " + qualified);
                if (builtins.contains(leaf) || (leaf == "array" && !(kind == Kind::Template && scope == "std")) ||
                    (kind != Kind::Function && (leaf == "i64" || leaf == "bool" || leaf == "ref" || leaf == "mutref")))
                    throw Error(kind != Kind::Function ? "duplicate or reserved class name"
                                                       : "duplicate or reserved function name");
                const auto native = kind == Kind::Function && unit.root && scope.empty() && !valueBoundary
                                        ? leaf
                                        : mangle(kind == Kind::Function ? (valueBoundary ? 'v' : 'f')
                                                                        : (kind == Kind::FunctionTemplate ? 'g'
                                                                           : kind == Kind::Template       ? 't'
                                                                           : kind == Kind::Enum           ? 'e'
                                                                                                          : 'c'),
                                                 name,
                                                 scope,
                                                 leaf);
                if (!table
                         .emplace(qualified,
                                  Declaration{kind, qualified, native, exported, name, nullptr, nullptr, nullptr, {}})
                         .second)
                    throw Error(std::string(kind != Kind::Function ? "duplicate or reserved class name"
                                                                   : "duplicate or reserved function name") +
                                " in module " + name + ": " + qualified);
                if (kind == Kind::Class || kind == Kind::Enum)
                    nativeClasses.emplace(native, &table.at(qualified));
                return native;
            };
            for (auto &definition : unit.program.enums) {
                if (++enumCount > 64)
                    throw Error("module graph exceeds 64 enum definitions");
                if (definition.cases.empty() || definition.cases.size() > 256)
                    throw Error("enum class requires between 1 and 256 named cases");
                std::set<std::string> cases;
                for (const auto &value : definition.cases) {
                    sourceName(value.text);
                    if (!cases.insert(value.text).second)
                        throw Error("duplicate enum case: " + value.text);
                }
                definition.name = add(Kind::Enum, definition.scope, definition.token.text, definition.exported);
                table.at(qualify(definition.scope, definition.token.text)).enumDefinition = &definition;
            }
            for (auto &definition : unit.program.classes) {
                definition.name = add(Kind::Class, definition.scope, definition.token.text, definition.exported);
                registerMembers(definition, unit);
            }
            for (auto &definition : unit.program.templates) {
                if (++templateCount > 64)
                    throw Error("module graph exceeds 64 class templates and function templates combined");
                ClassTemplateExpansion::validate(definition);
                definition.name = add(Kind::Template, definition.scope, definition.token.text, definition.exported);
                table.at(qualify(definition.scope, definition.token.text)).templateDefinition = &definition;
            }
            for (auto &function : unit.program.functionTemplates) {
                if (++templateCount > 64)
                    throw Error("module graph exceeds 64 class templates and function templates combined");
                FunctionTemplateExpansion::validate(function);
                function.name = add(Kind::FunctionTemplate, function.scope, function.token.text, function.exported);
                table.at(qualify(function.scope, function.token.text)).functionTemplateDefinition = &function;
            }
            std::map<std::string, std::size_t> functionCounts;
            for (const auto &function : unit.program.functions)
                ++functionCounts[qualify(function.scope, function.token.text)];
            for (auto &function : unit.program.functions) {
                const auto qualified = qualify(function.scope, function.token.text);
                const auto count = functionCounts.at(qualified);
                if (count > 32)
                    throw Error("ordinary overload set exceeds 32 declarations: " + qualified);
                if (count > 1 && unit.root && function.scope.empty() && function.token.text == "answer")
                    throw Error("bootstrap answer entrypoint cannot be overloaded");
                if (count > 1) {
                    if (!table.contains(qualified))
                        add(Kind::Function, function.scope, function.token.text, function.exported, true);
                    auto &declaration = table.at(qualified);
                    if (declaration.kind != Kind::Function)
                        throw Error("duplicate or reserved function name: " + qualified);
                    declaration.exported = declaration.exported || function.exported;
                    function.name = mangle('o', name, function.scope, function.token.text) + "_pending" +
                                    std::to_string(declaration.overloads.size());
                    declaration.overloads.emplace_back(function.name, function.exported);
                    continue;
                }
                const bool valueBoundary =
                    function.result.isClass() || function.result.isResource() ||
                    std::any_of(function.params.begin(), function.params.end(), [](const Param &parameter) {
                        return parameter.type.isClass() || parameter.type.isSpan() || parameter.type.isResource();
                    });
                function.name =
                    add(Kind::Function, function.scope, function.token.text, function.exported, valueBoundary);
            }
        }
    }
    std::vector<const Declaration *> visible(const ModuleLoader::Unit &unit, const std::string &qualified) {
        std::vector<const Declaration *> result;
        const auto &own = declarations.at(unit.program.moduleName);
        if (auto found = own.find(qualified); found != own.end())
            result.push_back(&found->second);
        for (const auto &import : unit.program.imports) {
            const auto &symbols = declarations.at(import.text);
            if (auto found = symbols.find(qualified); found != symbols.end() && found->second.exported)
                result.push_back(&found->second);
        }
        return result;
    }
    const Declaration *
    lookup(const ModuleLoader::Unit &unit, const std::string &scope, const std::string &name, Kind kind) {
        sourceName(name);
        std::vector<std::string> candidates;
        std::string parent = scope;
        while (!parent.empty()) {
            candidates.push_back(parent + "::" + name);
            auto end = parent.rfind("::");
            parent = end == std::string::npos ? "" : parent.substr(0, end);
        }
        candidates.push_back(name);
        for (const auto &candidate : candidates) {
            auto choices = visible(unit, candidate);
            if (choices.size() > 1)
                throw Error("ambiguous visible declaration: " + candidate);
            if (!choices.empty()) {
                if (kind != Kind::Any && choices[0]->kind != kind)
                    throw Error("declaration has the wrong kind: " + candidate);
                return choices[0];
            }
        }
        for (const auto &candidate : candidates)
            for (const auto &import : unit.program.imports) {
                const auto &symbols = declarations.at(import.text);
                if (auto found = symbols.find(candidate); found != symbols.end() && !found->second.exported)
                    throw Error(std::string("private ") + (found->second.kind == Kind::Function ? "function" : "type") +
                                " is not imported: " + candidate);
            }
        return nullptr;
    }
    std::vector<TemplateArgument> resolveArguments(const std::vector<TemplateArgument> &arguments,
                                                   const ModuleLoader::Unit &unit,
                                                   const std::string &scope,
                                                   bool expand = false,
                                                   int depth = 1) {
        auto result = arguments;
        for (auto &argument : result) {
            if (argument.kind != TemplateArgumentKind::Type || argument.type != TypeKind::Class)
                continue;
            const auto *declaration =
                argument.resolvedClass ? classDeclaration(ClassTemplateExpansion::argumentType(argument))
                : argument.templateArguments.empty()
                    ? lookup(unit, scope, argument.className, Kind::Any)
                    : specialization(unit, scope, argument.className, argument.templateArguments, expand, depth + 1);
            if (!declaration)
                throw Error("unknown named class or enum template argument: " + argument.className);
            if (declaration->kind != Kind::Class && declaration->kind != Kind::Enum)
                throw Error("template argument requires a named concrete class or enum: " + argument.className);
            argument.type = declaration->kind == Kind::Enum ? TypeKind::Enum : TypeKind::Class;
            argument.className = declaration->native;
            argument.displayName = displayName(*declaration);
            argument.templateArguments.clear();
            argument.resolvedClass = true;
        }
        return result;
    }
    std::string displayName(const Declaration &declaration) const {
        const auto found = instanceDisplayNames.find(declaration.native);
        return found == instanceDisplayNames.end() ? declaration.qualified : found->second;
    }
    class TemplateRequest {
    public:
        std::string module, scope, name;
        std::vector<TemplateArgument> arguments;
        bool expression = false;
    };
    void collectTemplateType(const Type &type,
                             const ModuleLoader::Unit &unit,
                             const std::string &scope,
                             std::vector<TemplateRequest> &requests) {
        if (type.kind == TypeKind::Parameter)
            throw Error("unsubstituted class template parameter: " + type.className);
        if (!type.elementParameter.empty() || !type.lengthParameter.empty())
            throw Error("unsubstituted array element or capacity parameter");
        if (!type.templateArguments.empty())
            requests.push_back({unit.program.moduleName, scope, type.className, type.templateArguments});
    }
    void collectTemplateExpression(const ExpressionPtr &value,
                                   const ModuleLoader::Unit &unit,
                                   const std::string &scope,
                                   std::vector<TemplateRequest> &requests) {
        if (!value)
            return;
        collectTemplateType(value->reflectedType, unit, scope, requests);
        if (!value->templateArguments.empty())
            requests.push_back({unit.program.moduleName, scope, value->token.text, value->templateArguments, true});
        for (const auto &argument : value->args)
            collectTemplateExpression(argument, unit, scope, requests);
    }
    void collectTemplateStatements(const std::vector<StatementPtr> &values,
                                   const ModuleLoader::Unit &unit,
                                   const std::string &scope,
                                   std::vector<TemplateRequest> &requests) {
        for (const auto &value : values) {
            collectTemplateType(value->type, unit, scope, requests);
            collectTemplateExpression(value->expr, unit, scope, requests);
            collectTemplateExpression(value->target, unit, scope, requests);
            collectTemplateStatements(value->body, unit, scope, requests);
            collectTemplateStatements(value->other, unit, scope, requests);
        }
    }
    void collectTemplateFunction(const Function &function,
                                 const ModuleLoader::Unit &unit,
                                 std::vector<TemplateRequest> &requests) {
        collectTemplateType(function.result, unit, function.scope, requests);
        for (const auto &parameter : function.params)
            collectTemplateType(parameter.type, unit, function.scope, requests);
        for (const auto &[field, initializer] : function.initializers) {
            (void)field;
            collectTemplateExpression(initializer, unit, function.scope, requests);
        }
        collectTemplateStatements(function.body, unit, function.scope, requests);
    }
    void validateTemplateType(const Type &type, const ModuleLoader::Unit &unit, const std::string &scope) {
        if (!type.templateArguments.empty()) {
            const auto *target = lookup(unit, scope, type.className, Kind::Template);
            if (!target)
                throw Error("function template requires a statically named class template: " + type.className);
        }
    }
    void
    validateTemplateExpression(const ExpressionPtr &value, const ModuleLoader::Unit &unit, const std::string &scope) {
        if (!value)
            return;
        validateTemplateType(value->reflectedType, unit, scope);
        if (value->op == "call" || value->op == "construct") {
            const bool receiverMember =
                activeClass && value->op == "call" &&
                (std::any_of(activeClass->methods.begin(),
                             activeClass->methods.end(),
                             [&](const auto &method) {
                                 return method.token.text == value->token.text;
                             }) ||
                 std::any_of(activeClass->fields.begin(), activeClass->fields.end(), [&](const auto &field) {
                     return field.token.text == value->token.text;
                 }));
            // Match concrete binding: an implicit receiver member takes
            // precedence over unrelated namespace-level template declarations.
            const auto *target = builtins.contains(value->token.text) || receiverMember
                                     ? nullptr
                                     : lookup(unit, scope, value->token.text, Kind::Any);
            if (target && target->kind == Kind::FunctionTemplate)
                throw Error("function template calls inside template bodies are unsupported");
            if (!value->templateArguments.empty() && (!target || target->kind != Kind::Template))
                throw Error("template body requires a statically named class template");
        }
        for (const auto &argument : value->args)
            validateTemplateExpression(argument, unit, scope);
    }
    void validateTemplateStatements(const std::vector<StatementPtr> &body,
                                    const ModuleLoader::Unit &unit,
                                    const std::string &scope) {
        for (const auto &statement : body) {
            validateTemplateType(statement->type, unit, scope);
            validateTemplateExpression(statement->expr, unit, scope);
            validateTemplateExpression(statement->target, unit, scope);
            validateTemplateStatements(statement->body, unit, scope);
            validateTemplateStatements(statement->other, unit, scope);
        }
    }
    void validateTemplateDefinitions() {
        for (const auto &name : graph.order) {
            const auto &unit = *graph.units.at(name);
            auto validate = [&](const Function &function) {
                validateTemplateType(function.result, unit, function.scope);
                for (const auto &parameter : function.params)
                    validateTemplateType(parameter.type, unit, function.scope);
                for (const auto &[field, expression] : function.initializers) {
                    (void)field;
                    validateTemplateExpression(expression, unit, function.scope);
                }
                validateTemplateStatements(function.body, unit, function.scope);
            };
            for (const auto &function : unit.program.functionTemplates)
                validate(function);
            for (const auto &definition : unit.program.templates) {
                activeClass = &definition;
                for (const auto &method : definition.methods)
                    validate(method);
                activeClass = nullptr;
            }
        }
    }
    void expandTemplates() {
        // Collect before appending classes, so no traversal keeps a pointer into
        // a class vector while concrete definitions are being added to it.
        std::vector<TemplateRequest> requests;
        for (const auto &name : graph.order) {
            const auto &unit = *graph.units.at(name);
            for (const auto &function : unit.program.functions)
                collectTemplateFunction(function, unit, requests);
            for (const auto &definition : unit.program.classes) {
                for (const auto &field : definition.fields)
                    collectTemplateType(field.type, unit, definition.scope, requests);
                for (const auto &method : definition.methods)
                    collectTemplateFunction(method, unit, requests);
            }
        }
        for (const auto &request : requests) {
            const auto &unit = *graph.units.at(request.module);
            const auto *target = lookup(unit, request.scope, request.name, Kind::Any);
            if (request.expression && target && target->kind == Kind::FunctionTemplate)
                (void)functionSpecialization(unit, request.scope, request.name, request.arguments, true);
            else
                (void)specialization(unit, request.scope, request.name, request.arguments, true);
        }
        // The preceding pass only appends immutable function copies. No traversal
        // can be invalidated, and these copies can request only class instances.
        std::vector<TemplateRequest> generated;
        for (const auto &name : graph.order) {
            const auto &unit = *graph.units.at(name);
            for (const auto &function : unit.program.functions)
                if (!function.templateArguments.empty())
                    collectTemplateFunction(function, unit, generated);
        }
        for (const auto &request : generated)
            (void)specialization(*graph.units.at(request.module), request.scope, request.name, request.arguments, true);
    }
    const Declaration *functionSpecialization(const ModuleLoader::Unit &unit,
                                              const std::string &scope,
                                              const std::string &name,
                                              const std::vector<TemplateArgument> &requested,
                                              bool expand = false) {
        const auto *declaration = lookup(unit, scope, name, Kind::FunctionTemplate);
        if (!declaration)
            throw Error("unknown function template: " + name);
        const auto &source = *declaration->functionTemplateDefinition;
        if (requested.size() != source.templateParameters.size())
            throw Error("wrong number of function template arguments for " + name);
        // A function call's outer list does not consume a class-template level.
        const auto arguments = resolveArguments(requested, unit, scope, expand, 0);
        if (expand)
            for (const auto &argument : arguments)
                if (argument.kind == TemplateArgumentKind::Type)
                    argumentVisibilityChecks.emplace_back(unit.program.moduleName,
                                                          ClassTemplateExpansion::argumentType(argument));
        const auto qualified = declaration->qualified + ClassTemplateExpansion::argumentSuffix(arguments);
        auto &table = declarations.at(declaration->module);
        if (const auto found = table.find(qualified); found != table.end())
            return &found->second;
        if (!expand)
            throw Error("unexpanded function template specialization: " + qualified);
        if (++instanceCount > 256)
            throw Error("module graph exceeds 256 class template instantiations and function instances combined");
        auto function = FunctionTemplateExpansion::instantiate(source, arguments);
        function.name = mangle('g', declaration->module, source.scope, source.token.text) +
                        ClassTemplateExpansion::nativeSuffix(arguments);
        const auto inserted =
            table.emplace(qualified, Declaration{Kind::Function, qualified, function.name, false, declaration->module});
        graph.units.at(declaration->module)->program.functions.push_back(std::move(function));
        return &inserted.first->second;
    }
    const Declaration *specialization(const ModuleLoader::Unit &unit,
                                      const std::string &scope,
                                      const std::string &name,
                                      const std::vector<TemplateArgument> &requestedArguments,
                                      bool expand = false,
                                      int depth = 1) {
        if (depth > maximumTemplateNesting)
            throw Error("template-id nesting exceeds " + std::to_string(maximumTemplateNesting));
        const auto *declaration = lookup(unit, scope, name, Kind::Template);
        if (!declaration)
            throw Error("unsupported type or unknown class template; expected a declared template: " + name);
        const auto &source = *declaration->templateDefinition;
        if (requestedArguments.size() != source.templateParameters.size())
            throw Error("wrong number of class template arguments for " + name);
        // No template body can request an instance. This recursion follows only
        // the bounded, fully concrete source tree; children are interned first.
        const auto arguments = resolveArguments(requestedArguments, unit, scope, expand, depth);
        int nominalDepth = 1;
        for (std::size_t index = 0; index < arguments.size(); ++index) {
            const auto &argument = arguments[index];
            if (argument.type == TypeKind::Class) {
                if (const auto child = instanceNesting.find(argument.className); child != instanceNesting.end())
                    nominalDepth = std::max(nominalDepth, child->second + 1);
            }
            if (expand && !requestedArguments[index].resolvedClass && argument.kind == TemplateArgumentKind::Type &&
                (argument.type == TypeKind::Class || argument.type == TypeKind::Enum))
                argumentVisibilityChecks.emplace_back(unit.program.moduleName,
                                                      ClassTemplateExpansion::argumentType(argument));
        }
        if (nominalDepth > maximumTemplateNesting)
            throw Error("template-id nesting exceeds 4 after substitution");
        const auto qualified = declaration->qualified + ClassTemplateExpansion::argumentSuffix(arguments);
        auto &table = declarations.at(declaration->module);
        if (const auto found = table.find(qualified); found != table.end())
            return &found->second;
        if (!expand)
            throw Error("unexpanded class template specialization: " + qualified);
        if (++instanceCount > 256)
            throw Error("module graph exceeds 256 class template instantiations and function instances combined");
        auto definition = ClassTemplateExpansion::instantiate(source, arguments);
        definition.name = mangle('c', declaration->module, definition.scope, definition.token.text) +
                          ClassTemplateExpansion::nativeSuffix(arguments);
        auto &definingUnit = *graph.units.at(declaration->module);
        registerMembers(definition, definingUnit);
        instanceArguments.emplace(definition.name, arguments);
        instanceNesting.emplace(definition.name, nominalDepth);
        instanceDisplayNames.emplace(definition.name,
                                     declaration->qualified + ClassTemplateExpansion::argumentSuffix(arguments, true));
        const auto inserted = table.emplace(
            qualified,
            Declaration{Kind::Class, qualified, definition.name, declaration->exported, declaration->module});
        nativeClasses.emplace(definition.name, &inserted.first->second);
        definingUnit.program.classes.push_back(std::move(definition));
        return &inserted.first->second;
    }
    void resolveType(Type &type, const ModuleLoader::Unit &unit, const std::string &scope) {
        if (type.kind == TypeKind::Parameter)
            throw Error("unsubstituted class template parameter: " + type.className);
        if (!type.elementParameter.empty() || !type.lengthParameter.empty())
            throw Error("unsubstituted array element or capacity parameter");
        if (!type.isClass() && !type.isEnum())
            return;
        if (type.resolvedClass) {
            if (!classDeclaration(type))
                throw Error("unknown resolved class identity: " + type.className);
            if (classTypesResolved && !bodyTypeVisible(type, unit))
                throw Error("resolved class type requires a direct visible import: " + typeName(type));
            recordAuthority(type, unit);
            return;
        }
        if (type.className == "array" || type.className == "builtin::array")
            throw Error("builtin array requires explicit element and length arguments");
        const Declaration *declaration = nullptr;
        if (!type.templateArguments.empty())
            declaration = specialization(unit, scope, type.className, type.templateArguments);
        else if (activeClass && !activeClass->templateArguments.empty() &&
                 (type.className == activeClass->token.text ||
                  type.className == qualify(activeClass->scope, activeClass->token.text))) {
            type.className = activeClass->name;
            type.displayName = qualify(activeClass->scope, activeClass->token.text) +
                               ClassTemplateExpansion::argumentSuffix(activeClass->templateArguments, true);
            type.resolvedClass = true;
            return;
        } else
            declaration = lookup(unit, scope, type.className, Kind::Any);
        if (declaration) {
            if (declaration->kind != Kind::Class && declaration->kind != Kind::Enum)
                throw Error("declaration is not a concrete type: " + type.className);
            if (declaration->kind == Kind::Enum)
                type.kind = TypeKind::Enum;
            type.className = declaration->native;
            type.displayName = displayName(*declaration);
            type.resolvedClass = true;
            type.templateArguments.clear();
            if (classTypesResolved && !bodyTypeVisible(type, unit))
                throw Error("class type requires a direct visible import: " + typeName(type));
            recordAuthority(type, unit);
        }
    }
    const Declaration *classDeclaration(const Type &type) const {
        const auto found = nativeClasses.find(type.className);
        return found == nativeClasses.end() ? nullptr : found->second;
    }
    bool typeAccessible(const Type &type, const ModuleLoader::Unit *unit, const Function *authority = nullptr) const {
        std::vector<Type> pending{type};
        std::set<std::string> visited;
        while (!pending.empty()) {
            const auto current = std::move(pending.back());
            pending.pop_back();
            if ((!current.isClass() && !current.isEnum()) || !visited.insert(current.className).second)
                continue;
            // Authority is limited to exact arguments already checked in the
            // requesting caller. It grants no lookup or private-member access.
            if (authority && std::any_of(authority->templateArguments.begin(),
                                         authority->templateArguments.end(),
                                         [&](const auto &argument) {
                                             return argument.kind == TemplateArgumentKind::Type &&
                                                    argument.type == current.kind &&
                                                    argument.className == current.className;
                                         }))
                continue;
            const auto *declaration = classDeclaration(current);
            if (!declaration)
                return false;
            if (!unit) {
                if (!declaration->exported)
                    return false;
            } else if (declaration->module != unit->program.moduleName) {
                if (!declaration->exported ||
                    std::none_of(unit->program.imports.begin(), unit->program.imports.end(), [&](const Token &import) {
                        return import.text == declaration->module;
                    }))
                    return false;
            }
            // A specialization's exported template alone cannot expose an
            // otherwise private or transitively imported nominal argument.
            if (const auto found = instanceArguments.find(current.className); found != instanceArguments.end())
                for (const auto &argument : found->second)
                    if (argument.kind == TemplateArgumentKind::Type)
                        pending.push_back(ClassTemplateExpansion::argumentType(argument));
            // Iterate instead of recursing: visibility runs before semantic
            // containment validation and also follows non-containment signatures.
            if (const auto found = publicTypes.find(current.className); found != publicTypes.end())
                pending.insert(pending.end(), found->second.begin(), found->second.end());
        }
        return true;
    }
    bool typeVisible(const Type &type, const ModuleLoader::Unit &unit) const {
        return typeAccessible(type, &unit);
    }
    bool bodyTypeVisible(const Type &type, const ModuleLoader::Unit &unit) const {
        if (activeClass && !activeClass->templateArguments.empty()) {
            if (type.isClass() && type.className == activeClass->name)
                return true;
            for (const auto &argument : activeClass->templateArguments)
                if (argument.kind == TemplateArgumentKind::Type && argument.type == type.kind &&
                    argument.className == type.className)
                    return true;
        }
        return typeAccessible(type, &unit, activeFunction);
    }
    void recordAuthority(const Type &type, const ModuleLoader::Unit &unit) {
        if (activeFunction && !activeFunction->templateArguments.empty() && (type.isClass() || type.isEnum()) &&
            bodyTypeVisible(type, unit))
            activeFunction->templateTypeAuthority.insert(type.className);
    }
    bool typeExported(const Type &type) const {
        return typeAccessible(type, nullptr);
    }
    void resolveClassTypes() {
        for (const auto &name : graph.order) {
            auto &unit = *graph.units.at(name);
            for (auto &definition : unit.program.classes) {
                activeClass = &definition;
                auto resolve = [&](Type &type) {
                    resolveType(type, unit, definition.scope);
                    if ((type.isClass() || type.isEnum()) && !classDeclaration(type))
                        throw Error("unknown nominal type in class declaration: " + typeName(type));
                };
                for (auto &field : definition.fields) {
                    resolve(field.type);
                    if (field.publicAccess)
                        publicTypes[definition.name].push_back(field.type);
                }
                for (auto &method : definition.methods) {
                    resolve(method.result);
                    if (method.publicAccess && !method.constructor)
                        publicTypes[definition.name].push_back(method.result);
                    for (auto &parameter : method.params) {
                        resolve(parameter.type);
                        if (!scalarValue(parameter.type) && !parameter.type.isClass() &&
                            !(method.constructor && parameter.type.isResource()))
                            throw Error(method.constructor
                                            ? "only scalar, enum or class constructor parameters "
                                              "are supported"
                                            : "only scalar, enum or class method parameters are supported");
                        if (method.publicAccess)
                            publicTypes[definition.name].push_back(parameter.type);
                    }
                }
                activeClass = nullptr;
            }
        }
        classTypesResolved = true;
        for (const auto &name : graph.order) {
            const auto &unit = *graph.units.at(name);
            for (const auto &definition : unit.program.classes) {
                // Generated instances may legitimately contain a caller-private
                // type. Check their exposure at each source signature/use instead.
                if (!definition.templateArguments.empty())
                    continue;
                auto visibleType = [&](const Type &type) {
                    if (!typeVisible(type, unit))
                        throw Error("class signature type requires a direct visible import: " + typeName(type));
                };
                for (const auto &field : definition.fields)
                    visibleType(field.type);
                for (const auto &method : definition.methods) {
                    if (!method.constructor)
                        visibleType(method.result);
                    for (const auto &parameter : method.params)
                        visibleType(parameter.type);
                }
                if (!definition.exported)
                    continue;
                for (const auto &type : publicTypes[definition.name]) {
                    if (!typeExported(type))
                        throw Error("exported class public signature exposes private type: " + typeName(type));
                    if (!typeVisible(type, unit))
                        throw Error("class signature type requires a direct visible import: " + typeName(type));
                }
            }
        }
        for (const auto &[module, type] : argumentVisibilityChecks)
            if (!typeVisible(type, *graph.units.at(module)))
                throw Error("template argument type requires a direct visible import: " + typeName(type));
    }
    void
    validateFunctionTemplateSignatureType(const Type &type, const ModuleLoader::Unit &unit, const Function &function) {
        if (!type.isClass() && !type.isEnum())
            return;
        const auto *target = lookup(unit, function.scope, type.className, Kind::Any);
        if (!target)
            throw Error("unknown fixed type in function template signature: " + typeName(type));
        if (!type.templateArguments.empty()) {
            if (target->kind != Kind::Template)
                throw Error("function template signature requires a class template");
            if (function.exported && !target->exported)
                throw Error("exported function template signature exposes private template: " + typeName(type));
            for (const auto &argument : type.templateArguments) {
                if (argument.kind != TemplateArgumentKind::Type || argument.type == TypeKind::Parameter)
                    continue;
                Type child(argument.type);
                child.className = argument.className;
                child.templateArguments = argument.templateArguments;
                validateFunctionTemplateSignatureType(child, unit, function);
            }
        } else {
            if (target->kind != Kind::Class && target->kind != Kind::Enum)
                throw Error("function template signature requires a concrete fixed type");
            Type fixed(target->native);
            if (target->kind == Kind::Enum)
                fixed.kind = TypeKind::Enum;
            if (!typeVisible(fixed, unit))
                throw Error("function template signature type requires a direct visible import: " + typeName(type));
            if (function.exported && !typeExported(fixed))
                throw Error("exported function template signature exposes private type: " + typeName(type));
        }
    }
    void validateFunctionTemplateSignatures() {
        // Fixed signature privacy is a declaration invariant, including unused
        // exported definitions. Dependent tuples remain checked per request.
        for (const auto &name : graph.order) {
            const auto &unit = *graph.units.at(name);
            for (const auto &function : unit.program.functionTemplates) {
                validateFunctionTemplateSignatureType(function.result, unit, function);
                for (const auto &parameter : function.params)
                    validateFunctionTemplateSignatureType(parameter.type, unit, function);
            }
        }
    }
    void resolveSignatures() {
        for (const auto &name : graph.order) {
            auto &unit = *graph.units.at(name);
            for (auto &function : unit.program.functions) {
                activeFunction = &function;
                auto resolve = [&](Type &type) {
                    resolveType(type, unit, function.scope);
                    if (type.isClass() || type.isEnum()) {
                        const auto *declaration = classDeclaration(type);
                        if (!declaration)
                            throw Error("unknown class type in function signature: " + typeName(type));
                        if (!bodyTypeVisible(type, unit))
                            throw Error("function signature type requires a direct visible import: " + typeName(type));
                        if (function.exported && !typeExported(type))
                            throw Error("exported function signature exposes private type: " + typeName(type));
                    }
                };
                resolve(function.result);
                for (auto &parameter : function.params)
                    resolve(parameter.type);
                if (function.templateArguments.empty()) {
                    auto &declaration = declarations.at(name).at(qualify(function.scope, function.token.text));
                    if (!declaration.overloads.empty()) {
                        const auto previous = function.name;
                        std::string identity = mangle('o', name, function.scope, function.token.text) + "_p" +
                                               std::to_string(function.params.size()) + "_";
                        for (const auto &parameter : function.params) {
                            const auto &type = parameter.type;
                            if (!scalarValue(type) && !type.isClass() && !type.isSpan())
                                throw Error("ordinary overload parameters require scalar, enum, class or readonly byte "
                                            "span types");
                            const auto component = std::to_string(static_cast<int>(type.kind)) + "_" + type.className;
                            identity += std::to_string(component.size()) + component;
                        }
                        if (signatures.contains(identity))
                            throw Error("duplicate or reserved function name in module " + name + ": " +
                                        declaration.qualified);
                        function.name = identity;
                        for (auto &[native, exported] : declaration.overloads) {
                            (void)exported;
                            if (native == previous)
                                native = identity;
                        }
                    }
                }
                auto &signature = signatures[function.name];
                signature.push_back(function.result);
                for (const auto &parameter : function.params)
                    signature.push_back(parameter.type);
                activeFunction = nullptr;
            }
        }
    }
    void expression(const ExpressionPtr &value, const ModuleLoader::Unit &unit, const std::string &scope) {
        if (!value)
            return;
        if ((value->op == "call" || value->op == "construct") &&
            (value->token.text == "array" || value->token.text == "builtin::array"))
            throw Error("builtin array does not provide a class constructor");
        if (!value->templateArguments.empty()) {
            if (value->op != "call" && value->op != "construct")
                throw Error("template arguments require a class construction");
            const auto *target = lookup(unit, scope, value->token.text, Kind::Any);
            if (target && target->kind == Kind::FunctionTemplate) {
                if (activeClass || (activeFunction && !activeFunction->templateArguments.empty())) {
                    if ((activeClass && !activeClass->templateArguments.empty()) ||
                        (activeFunction && !activeFunction->templateArguments.empty()))
                        throw Error("function template calls inside template bodies are unsupported");
                }
                if (value->op != "call")
                    throw Error("function template arguments require a call");
                const auto *declaration =
                    functionSpecialization(unit, scope, value->token.text, value->templateArguments);
                for (const auto &type : signatures.at(declaration->native))
                    if (!bodyTypeVisible(type, unit))
                        throw Error("function signature type requires a direct visible import: " + typeName(type));
                value->resolvedName = declaration->native;
                value->templateArguments.clear();
                for (const auto &argument : value->args)
                    expression(argument, unit, scope);
                return;
            }
            const auto *declaration = specialization(unit, scope, value->token.text, value->templateArguments);
            value->resolvedName = declaration->native;
            value->reflectedType = Type(declaration->native);
            value->reflectedType.displayName = displayName(*declaration);
            value->reflectedType.resolvedClass = true;
            if (!bodyTypeVisible(value->reflectedType, unit))
                throw Error("class construction type requires a direct visible import: " +
                            typeName(value->reflectedType));
            recordAuthority(value->reflectedType, unit);
            if (value->op == "call")
                value->op = "constructor_call";
            value->templateArguments.clear();
            for (const auto &argument : value->args)
                expression(argument, unit, scope);
            return;
        }
        if (value->op == "call") {
            if (value->token.text == "size_of" || value->token.text == "type_id" || value->token.text == "field_count")
                resolveType(value->reflectedType, unit, scope);
            else if (!builtins.contains(value->token.text)) {
                if (activeClass) {
                    for (const auto &member : activeClass->fields)
                        if (member.token.text == value->token.text)
                            throw Error("class field is not callable: " + value->token.text);
                    for (const auto &method : activeClass->methods) {
                        if (!method.constructor && method.token.text == value->token.text) {
                            if (initializingReceiver)
                                throw Error("constructor initializer cannot access receiver methods");
                            value->op = "implicit_method_call";
                            value->resolvedName = method.name;
                            break;
                        }
                    }
                }
                if (value->op == "implicit_method_call") {
                    for (const auto &argument : value->args)
                        expression(argument, unit, scope);
                    return;
                }
                const auto *declaration =
                    activeClass && !activeClass->templateArguments.empty() &&
                            (value->token.text == activeClass->token.text ||
                             value->token.text == qualify(activeClass->scope, activeClass->token.text))
                        ? classDeclaration(Type(activeClass->name))
                        : lookup(unit, scope, value->token.text, Kind::Any);
                if (!declaration)
                    throw Error(DiagnosticCode::Module,
                                "unknown function '" + value->token.text + "' in defining module " +
                                    unit.program.moduleName,
                                value->token.span);
                if (declaration->kind == Kind::Template || declaration->kind == Kind::FunctionTemplate)
                    throw Error(std::string(declaration->kind == Kind::Template
                                                ? "class template requires explicit type arguments: "
                                                : "function template requires explicit type arguments: ") +
                                value->token.text);
                if (declaration->kind == Kind::Enum)
                    throw Error("enum values require a named case: " + value->token.text);
                value->resolvedName = declaration->native;
                if (declaration->kind == Kind::Function && !declaration->overloads.empty()) {
                    for (const auto &[native, exported] : declaration->overloads) {
                        if (!exported && declaration->module != unit.program.moduleName)
                            continue;
                        value->overloadCandidates.push_back(native);
                        for (const auto &type : signatures.at(native))
                            if (!bodyTypeVisible(type, unit))
                                value->inaccessibleOverloads.insert(native);
                    }
                    if (value->overloadCandidates.empty())
                        throw Error("private function is not imported: " + declaration->qualified);
                } else if (declaration->kind == Kind::Function) {
                    for (const auto &type : signatures.at(declaration->native))
                        if (!bodyTypeVisible(type, unit))
                            throw Error("function signature type requires a direct visible import: " + typeName(type));
                }
                if (declaration->kind == Kind::Class) {
                    value->op = "constructor_call";
                    value->reflectedType = Type(declaration->native);
                    value->reflectedType.displayName = displayName(*declaration);
                    value->reflectedType.resolvedClass = true;
                    const bool generatedSelf = activeClass && !activeClass->templateArguments.empty() &&
                                               declaration->native == activeClass->name;
                    if (!generatedSelf && !bodyTypeVisible(value->reflectedType, unit))
                        throw Error("class construction type requires a direct visible import: " +
                                    typeName(value->reflectedType));
                }
            }
        } else if (value->op == "construct") {
            Type type(value->token.text);
            resolveType(type, unit, scope);
            if (type.isEnum())
                throw Error("enum values require a named case: " + value->token.text);
            value->reflectedType = type;

        } else if (value->op == "name") {
            sourceName(value->token.text);
            const auto separator = value->token.text.rfind("::");
            if (separator != std::string::npos) {
                const auto enumName = value->token.text.substr(0, separator);
                const auto caseName = value->token.text.substr(separator + 2);
                const auto *declaration = lookup(unit, scope, enumName, Kind::Enum);
                if (declaration) {
                    const auto &cases = declaration->enumDefinition->cases;
                    const auto found = std::find_if(cases.begin(), cases.end(), [&](const Token &candidate) {
                        return candidate.text == caseName;
                    });
                    if (found == cases.end())
                        throw Error("unknown enum case: " + value->token.text);
                    value->op = "enum_case";
                    value->resolvedName = declaration->native;
                    value->reflectedType = Type::enumeration(declaration->native);
                    value->reflectedType.displayName = declaration->qualified;
                    value->reflectedType.resolvedClass = true;
                    value->enumOrdinal = static_cast<int>(found - cases.begin());
                }
            }
        }
        for (const auto &argument : value->args)
            expression(argument, unit, scope);
    }
    void statements(const std::vector<StatementPtr> &values, const ModuleLoader::Unit &unit, const std::string &scope) {
        for (const auto &statement : values) {
            resolveType(statement->type, unit, scope);
            expression(statement->expr, unit, scope);
            expression(statement->target, unit, scope);
            statements(statement->body, unit, scope);
            statements(statement->other, unit, scope);
        }
    }

public:
    explicit ModuleResolver(ModuleLoader::Graph value) : graph(std::move(value)) {
    }
    Program resolve() {
        registerDeclarations();
        validateTemplateDefinitions();
        expandTemplates();
        resolveClassTypes();
        validateFunctionTemplateSignatures();
        resolveSignatures();
        Program result;
        result.moduleName = graph.root;
        for (const auto &name : graph.order) {
            auto &unit = *graph.units.at(name);
            // Ambiguity is rejected even if the conflicting name is never used.
            std::set<std::string> names;
            for (const auto &[qualified, declaration] : declarations.at(name)) {
                (void)declaration;
                names.insert(qualified);
            }
            for (const auto &import : unit.program.imports)
                for (const auto &[qualified, declaration] : declarations.at(import.text))
                    if (declaration.exported)
                        names.insert(qualified);
            std::set<std::string> visibleNamespaces = unit.program.namespaces;
            for (const auto &qualified : names) {
                std::size_t end = 0;
                while ((end = qualified.find("::", end)) != std::string::npos) {
                    visibleNamespaces.insert(qualified.substr(0, end));
                    end += 2;
                }
            }
            for (const auto &qualified : names) {
                if (visible(unit, qualified).size() > 1)
                    throw Error("ambiguous visible declaration in " + name + ": " + qualified);
                if (visibleNamespaces.contains(qualified))
                    throw Error("namespace and declaration name collide: " + qualified);
            }
            for (auto &function : unit.program.functions) {
                function.moduleScope = unit.scope;
                activeFunction = &function;
                statements(function.body, unit, function.scope);
                activeFunction = nullptr;
                result.functions.push_back(std::move(function));
            }
            for (auto &definition : unit.program.classes) {
                activeClass = &definition;
                for (auto &method : definition.methods) {
                    initializingReceiver = method.constructor;
                    for (const auto &[field, initializer] : method.initializers) {
                        (void)field;
                        expression(initializer, unit, definition.scope);
                    }
                    statements(method.body, unit, definition.scope);
                }
                activeClass = nullptr;
                initializingReceiver = false;
                result.classes.push_back(std::move(definition));
            }
            auto &reflected = result.reflectionAccess[unit.scope];
            for (const auto &qualified : names)
                for (const auto *declaration : visible(unit, qualified))
                    if ((declaration->kind == Kind::Class || declaration->kind == Kind::Enum) &&
                        typeVisible(Type(declaration->native), unit))
                        reflected.insert(declaration->native);
        }
        for (const auto &name : graph.order)
            for (auto &definition : graph.units.at(name)->program.enums)
                result.enums.push_back(std::move(definition));
        if (result.functions.empty())
            throw Error("module graph must contain a function");
        return result;
    }
};
} // namespace aurora
