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
    std::size_t bytesRead = 0;
    Graph graph;
    std::set<std::string> active;
    std::string read(host::SourceFile file) {
        graph.sourceIdentities.insert(file.identity);
        const auto remaining = maxGraphBytes - bytesRead;
        try {
            auto contents = file.readAtMost(std::min(maxFileBytes, remaining));
            bytesRead += contents.size();
            return contents;
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
            const auto part =
                name.substr(start, end == std::string::npos ? name.size() - start : end - start);
            if (part.empty() || part.size() > 128 || ++components > 32)
                throw Error("invalid or excessive module name");
            for (char c : part)
                if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') ||
                      c == '_'))
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
                    throw Error("module " + import.text + ": " + error.what());
                }
                if (imported->program.moduleName != import.text)
                    throw Error("module header mismatch: expected " + import.text + ", got " +
                                imported->program.moduleName);
                if (!imported->program.interfaceUnit)
                    throw Error("imported module requires an export module interface: " +
                                import.text);
                graph.units.emplace(import.text, std::move(imported));
            }
            visit(import.text, depth + 1);
        }
        active.erase(name);
        graph.order.push_back(name);
    }

  public:
    explicit ModuleLoader(const std::vector<std::filesystem::path> &searchRoots) {
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
    enum class Kind { Function, Class, Template, Any };
    const ClassDefinition *activeClass = nullptr;
    bool initializingReceiver = false;
    class Declaration {
      public:
        Kind kind;
        std::string qualified;
        std::string native;
        bool exported;
        std::string module;
        const ClassDefinition *templateDefinition = nullptr;
    };
    ModuleLoader::Graph graph;
    std::map<std::string, std::map<std::string, Declaration>> declarations;
    std::map<std::string, std::vector<Type>> signatures;
    const std::set<std::string> builtins = {"i64",
                                            "u64",
                                            "own",
                                            "move",
                                            "borrow",
                                            "borrow_mut",
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
            result.push_back(
                value.substr(start, end == std::string::npos ? value.size() - start : end - start));
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
    static std::string mangle(char kind, const std::string &module, const std::string &scope,
                              const std::string &name) {
        const auto modules = split(module, "."), spaces = split(scope, "::");
        std::string result =
            "__au_" + std::string(1, kind) + "_m" + std::to_string(modules.size()) + "_";
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
        const auto instanceSuffix =
            definition.templateArguments.empty()
                ? ""
                : ClassTemplateExpansion::nativeSuffix(definition.templateArguments);
        for (auto &method : definition.methods) {
            sourceName(method.token.text);
            if (builtins.contains(method.token.text) ||
                (method.token.text == "array" && !method.constructor) ||
                !members.insert(method.token.text).second)
                throw Error("duplicate or reserved class member: " + method.token.text);
            method.name = mangle(method.constructor ? 'k' : 'm', unit.program.moduleName,
                                 classScope, method.token.text) +
                          instanceSuffix;
            method.receiverClass = definition.name;
            method.moduleScope = unit.scope;
        }
    }
    void registerDeclarations() {
        std::size_t templateCount = 0;
        for (const auto &name : graph.order) {
            auto &unit = *graph.units.at(name);
            auto &table = declarations[name];
            for (const auto &scope : unit.program.namespaces)
                sourceName(scope);
            auto add = [&](Kind kind, const std::string &scope, const std::string &leaf,
                           bool exported, bool valueBoundary = false) -> std::string {
                sourceName(scope);
                sourceName(leaf);
                const auto qualified = qualify(scope, leaf);
                if (unit.program.namespaces.contains(qualified))
                    throw Error("namespace and declaration name collide: " + qualified);
                if (builtins.contains(leaf) ||
                    (leaf == "array" && !(kind == Kind::Template && scope == "std")) ||
                    (kind != Kind::Function &&
                     (leaf == "i64" || leaf == "bool" || leaf == "ref" || leaf == "mutref")))
                    throw Error(kind != Kind::Function ? "duplicate or reserved class name"
                                                       : "duplicate or reserved function name");
                const auto native =
                    kind == Kind::Function && unit.root && scope.empty() && !valueBoundary
                        ? leaf
                        : mangle(kind == Kind::Function ? (valueBoundary ? 'v' : 'f')
                                                        : (kind == Kind::Template ? 't' : 'c'),
                                 name, scope, leaf);
                if (!table.emplace(qualified, Declaration{kind, qualified, native, exported, name})
                         .second)
                    throw Error(std::string(kind != Kind::Function
                                                ? "duplicate or reserved class name"
                                                : "duplicate or reserved function name") +
                                " in module " + name + ": " + qualified);
                return native;
            };
            for (auto &definition : unit.program.classes) {
                definition.name =
                    add(Kind::Class, definition.scope, definition.token.text, definition.exported);
                registerMembers(definition, unit);
            }
            for (auto &definition : unit.program.templates) {
                if (++templateCount > 64)
                    throw Error("module graph exceeds 64 class templates");
                ClassTemplateExpansion::validate(definition);
                definition.name = add(Kind::Template, definition.scope, definition.token.text,
                                      definition.exported);
                table.at(qualify(definition.scope, definition.token.text)).templateDefinition =
                    &definition;
            }
            for (auto &function : unit.program.functions) {
                const bool valueBoundary =
                    function.result.isClass() ||
                    std::any_of(function.params.begin(), function.params.end(),
                                [](const Param &parameter) { return parameter.type.isClass(); });
                function.name = add(Kind::Function, function.scope, function.token.text,
                                    function.exported, valueBoundary);
            }
        }
    }
    std::vector<const Declaration *> visible(const ModuleLoader::Unit &unit,
                                             const std::string &qualified) {
        std::vector<const Declaration *> result;
        const auto &own = declarations.at(unit.program.moduleName);
        if (auto found = own.find(qualified); found != own.end())
            result.push_back(&found->second);
        for (const auto &import : unit.program.imports) {
            const auto &symbols = declarations.at(import.text);
            if (auto found = symbols.find(qualified);
                found != symbols.end() && found->second.exported)
                result.push_back(&found->second);
        }
        return result;
    }
    const Declaration *lookup(const ModuleLoader::Unit &unit, const std::string &scope,
                              const std::string &name, Kind kind) {
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
                if (auto found = symbols.find(candidate);
                    found != symbols.end() && !found->second.exported)
                    throw Error(
                        std::string("private ") +
                        (kind == Kind::Class || kind == Kind::Template ? "type" : "function") +
                        " is not imported: " + candidate);
            }
        return nullptr;
    }
    class TemplateRequest {
      public:
        std::string module, scope, name;
        std::vector<TemplateArgument> arguments;
    };
    void collectTemplateType(const Type &type, const ModuleLoader::Unit &unit,
                             const std::string &scope, std::vector<TemplateRequest> &requests) {
        if (type.kind == TypeKind::Parameter)
            throw Error("unsubstituted class template parameter: " + type.className);
        if (!type.elementParameter.empty() || !type.lengthParameter.empty())
            throw Error("unsubstituted array element or capacity parameter");
        if (!type.templateArguments.empty())
            requests.push_back(
                {unit.program.moduleName, scope, type.className, type.templateArguments});
    }
    void collectTemplateExpression(const ExpressionPtr &value, const ModuleLoader::Unit &unit,
                                   const std::string &scope,
                                   std::vector<TemplateRequest> &requests) {
        if (!value)
            return;
        collectTemplateType(value->reflectedType, unit, scope, requests);
        if (!value->templateArguments.empty())
            requests.push_back(
                {unit.program.moduleName, scope, value->token.text, value->templateArguments});
        for (const auto &argument : value->args)
            collectTemplateExpression(argument, unit, scope, requests);
    }
    void collectTemplateStatements(const std::vector<StatementPtr> &values,
                                   const ModuleLoader::Unit &unit, const std::string &scope,
                                   std::vector<TemplateRequest> &requests) {
        for (const auto &value : values) {
            collectTemplateType(value->type, unit, scope, requests);
            collectTemplateExpression(value->expr, unit, scope, requests);
            collectTemplateExpression(value->target, unit, scope, requests);
            collectTemplateStatements(value->body, unit, scope, requests);
            collectTemplateStatements(value->other, unit, scope, requests);
        }
    }
    void collectTemplateFunction(const Function &function, const ModuleLoader::Unit &unit,
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
        std::size_t instanceCount = 0;
        for (const auto &request : requests) {
            const auto &usingUnit = *graph.units.at(request.module);
            const auto *declaration =
                lookup(usingUnit, request.scope, request.name, Kind::Template);
            if (!declaration)
                throw Error("unsupported type or unknown class template: " + request.name);
            const auto &source = *declaration->templateDefinition;
            if (request.arguments.size() != source.templateParameters.size())
                throw Error("wrong number of class template arguments for " + request.name);
            const auto suffix = ClassTemplateExpansion::argumentSuffix(request.arguments);
            const auto qualified = declaration->qualified + suffix;
            auto &table = declarations.at(declaration->module);
            if (table.contains(qualified))
                continue;
            if (++instanceCount > 256)
                throw Error("module graph exceeds 256 class template instantiations");
            auto definition = ClassTemplateExpansion::instantiate(source, request.arguments);
            definition.name =
                mangle('c', declaration->module, definition.scope, definition.token.text) +
                ClassTemplateExpansion::nativeSuffix(request.arguments);
            auto &definingUnit = *graph.units.at(declaration->module);
            registerMembers(definition, definingUnit);
            table.emplace(qualified, Declaration{Kind::Class, qualified, definition.name,
                                                 declaration->exported, declaration->module});
            definingUnit.program.classes.push_back(std::move(definition));
        }
    }
    const Declaration *specialization(const ModuleLoader::Unit &unit, const std::string &scope,
                                      const std::string &name,
                                      const std::vector<TemplateArgument> &arguments) {
        const auto *declaration = lookup(unit, scope, name, Kind::Template);
        if (!declaration)
            throw Error("unsupported type or unknown class template: " + name);
        const auto qualified =
            declaration->qualified + ClassTemplateExpansion::argumentSuffix(arguments);
        const auto &table = declarations.at(declaration->module);
        const auto found = table.find(qualified);
        if (found == table.end())
            throw Error("unexpanded class template specialization: " + qualified);
        return &found->second;
    }
    void resolveType(Type &type, const ModuleLoader::Unit &unit, const std::string &scope) {
        if (type.kind == TypeKind::Parameter)
            throw Error("unsubstituted class template parameter: " + type.className);
        if (!type.elementParameter.empty() || !type.lengthParameter.empty())
            throw Error("unsubstituted array element or capacity parameter");
        if (!type.isClass())
            return;
        if (type.className == "array" || type.className == "builtin::array")
            throw Error("builtin array requires explicit element and length arguments");
        const Declaration *declaration = nullptr;
        if (!type.templateArguments.empty())
            declaration = specialization(unit, scope, type.className, type.templateArguments);
        else if (activeClass && !activeClass->templateArguments.empty() &&
                 (type.className == activeClass->token.text ||
                  type.className == qualify(activeClass->scope, activeClass->token.text))) {
            type.className = activeClass->name;
            type.displayName =
                qualify(activeClass->scope, activeClass->token.text) +
                ClassTemplateExpansion::argumentSuffix(activeClass->templateArguments);
            return;
        } else
            declaration = lookup(unit, scope, type.className, Kind::Class);
        if (declaration) {
            type.className = declaration->native;
            type.displayName = declaration->qualified;
            type.templateArguments.clear();
        }
    }
    const Declaration *classDeclaration(const Type &type) const {
        for (const auto &[module, table] : declarations) {
            (void)module;
            for (const auto &[name, declaration] : table) {
                (void)name;
                if (declaration.kind == Kind::Class && declaration.native == type.className)
                    return &declaration;
            }
        }
        return nullptr;
    }
    bool typeVisible(const Type &type, const ModuleLoader::Unit &unit) const {
        if (!type.isClass())
            return true;
        const auto contains = [&](const std::string &module, bool imported) {
            for (const auto &[name, declaration] : declarations.at(module)) {
                (void)name;
                if (declaration.kind == Kind::Class && declaration.native == type.className &&
                    (!imported || declaration.exported))
                    return true;
            }
            return false;
        };
        if (contains(unit.program.moduleName, false))
            return true;
        for (const auto &import : unit.program.imports)
            if (contains(import.text, true))
                return true;
        return false;
    }
    void resolveSignatures() {
        for (const auto &name : graph.order) {
            auto &unit = *graph.units.at(name);
            for (auto &function : unit.program.functions) {
                auto resolve = [&](Type &type) {
                    resolveType(type, unit, function.scope);
                    if (type.isClass()) {
                        const auto *declaration = classDeclaration(type);
                        if (!declaration)
                            throw Error("unknown class type in function signature: " +
                                        typeName(type));
                        if (function.exported && !declaration->exported)
                            throw Error("exported function signature exposes private type: " +
                                        typeName(type));
                    }
                    signatures[function.name].push_back(type);
                };
                resolve(function.result);
                for (auto &parameter : function.params)
                    resolve(parameter.type);
            }
        }
    }
    void expression(const ExpressionPtr &value, const ModuleLoader::Unit &unit,
                    const std::string &scope) {
        if (!value)
            return;
        if ((value->op == "call" || value->op == "construct") &&
            (value->token.text == "array" || value->token.text == "builtin::array"))
            throw Error("builtin array does not provide a class constructor");
        if (!value->templateArguments.empty()) {
            if (value->op != "call" && value->op != "construct")
                throw Error("template arguments require a class construction");
            const auto *declaration =
                specialization(unit, scope, value->token.text, value->templateArguments);
            value->resolvedName = declaration->native;
            value->reflectedType = Type(declaration->native);
            value->reflectedType.displayName = declaration->qualified;
            if (value->op == "call")
                value->op = "constructor_call";
            value->templateArguments.clear();
            for (const auto &argument : value->args)
                expression(argument, unit, scope);
            return;
        }
        if (value->op == "call") {
            if (value->token.text == "size_of" || value->token.text == "type_id" ||
                value->token.text == "field_count")
                resolveType(value->reflectedType, unit, scope);
            else if (!builtins.contains(value->token.text)) {
                if (activeClass) {
                    for (const auto &member : activeClass->fields)
                        if (member.token.text == value->token.text)
                            throw Error("class field is not callable: " + value->token.text);
                    for (const auto &method : activeClass->methods) {
                        if (!method.constructor && method.token.text == value->token.text) {
                            if (initializingReceiver)
                                throw Error(
                                    "constructor initializer cannot access receiver methods");
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
                             value->token.text ==
                                 qualify(activeClass->scope, activeClass->token.text))
                        ? classDeclaration(Type(activeClass->name))
                        : lookup(unit, scope, value->token.text, Kind::Any);
                if (!declaration)
                    throw Error("line " + std::to_string(value->token.line) +
                                ": unknown function '" + value->token.text +
                                "' in defining module " + unit.program.moduleName);
                if (declaration->kind == Kind::Template)
                    throw Error("class template requires explicit type arguments: " +
                                value->token.text);
                value->resolvedName = declaration->native;
                if (declaration->kind == Kind::Function) {
                    for (const auto &type : signatures.at(declaration->native))
                        if (!typeVisible(type, unit))
                            throw Error(
                                "function signature type requires a direct visible import: " +
                                typeName(type));
                }
                if (declaration->kind == Kind::Class) {
                    value->op = "constructor_call";
                    value->reflectedType = Type(declaration->native);
                    value->reflectedType.displayName = declaration->qualified;
                }
            }
        } else if (value->op == "construct") {
            Type type(value->token.text);
            resolveType(type, unit, scope);
            value->reflectedType = type;

        } else if (value->op == "name")
            sourceName(value->token.text);
        for (const auto &argument : value->args)
            expression(argument, unit, scope);
    }
    void statements(const std::vector<StatementPtr> &values, const ModuleLoader::Unit &unit,
                    const std::string &scope) {
        for (const auto &statement : values) {
            resolveType(statement->type, unit, scope);
            expression(statement->expr, unit, scope);
            expression(statement->target, unit, scope);
            statements(statement->body, unit, scope);
            statements(statement->other, unit, scope);
        }
    }

  public:
    explicit ModuleResolver(ModuleLoader::Graph value) : graph(std::move(value)) {}
    Program resolve() {
        registerDeclarations();
        expandTemplates();
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
                statements(function.body, unit, function.scope);
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
                    if (declaration->kind == Kind::Class)
                        reflected.insert(declaration->native);
        }
        if (result.functions.empty())
            throw Error("module graph must contain a function");
        return result;
    }
};
} // namespace aurora
