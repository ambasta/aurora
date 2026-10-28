#pragma once
#include "hosted_pipeline.hpp"
#include "ir.hpp"
#include <map>
#include <memory>
#include <string>

namespace aurora {
// Source declarations are observations only. Physical extents remain authority
// of the independently validated module and backend.
class AbiDeclaration {
public:
    std::string sourceName;
    std::vector<std::string> members;
};
class AbiDeclarations {
public:
    std::map<std::string, AbiDeclaration> records, enums, functions;
};
// Textual-IR fixtures only: compilations emit through runHostedPipeline. This
// host object lends a fixture's two already-published owners to the Aurora
// emitter, transports retained IDs/optional names and copies sealed output
// chunks. Optional JSON requires the same live module.
class X86Emitter final {
    class State;
    std::unique_ptr<State> state_;

public:
    X86Emitter();
    ~X86Emitter();
    X86Emitter(const X86Emitter &) = delete;
    X86Emitter &operator=(const X86Emitter &) = delete;
    std::string stackFactsJson(const ir::ValidatedModule &validated) const;
    std::string abiFactsJson(const ir::ValidatedModule &validated, const AbiDeclarations &declarations) const;
    std::string emit(const ir::ValidatedModule &validated,
                     SymbolBinding binding = SymbolBinding::Default,
                     ReflectionEmission reflection = ReflectionEmission::All,
                     CodeEmission format = CodeEmission::Assembly);
};
} // namespace aurora
