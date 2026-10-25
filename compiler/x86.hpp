#pragma once
#include "ir.hpp"
#include <memory>
#include <string>

namespace aurora {
// These choices affect symbol visibility and retained reflection helpers only.
enum class SymbolBinding {
    Default,
    Local
};
enum class ReflectionEmission {
    All,
    Referenced
};
enum class CodeEmission {
    Assembly,
    Object
};
class AbiDeclarations;
// Aurora owns validated-IR-to-x86 assembly and object policy. This host object only lends
// the two already-published owners, transports retained IDs/optional names,
// copies sealed output chunks. Optional JSON requires the same live module.
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
