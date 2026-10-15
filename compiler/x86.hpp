#pragma once
#include "ir.hpp"
#include <map>
#include <memory>
#include <optional>
#include <string>
#include <utility>
#include <vector>

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
class CopiedRecordFacts {
public:
    std::vector<int> parameterBytes;
    int resultBytes;
};
class ServiceRecordFacts {
public:
    std::vector<std::pair<std::string, int>> parameters;
    int resultBytes;
};
class ServiceCallFacts {
public:
    int arguments, resultMax;
};
class FunctionStackFacts {
public:
    int localBytes = 8;
    std::map<std::string, int> calls;
    std::optional<CopiedRecordFacts> copiedRecord;
    std::optional<ServiceRecordFacts> serviceRecord;
    std::map<std::string, ServiceCallFacts> serviceCalls;
};
class AbiDeclarations;
// Aurora owns all validated-IR-to-x86 text policy. This host object only lends
// the two already-published owners, transports retained IDs/optional names,
// copies sealed output chunks and decodes the legacy stack-facts observation.
class X86Emitter final {
    class State;
    std::unique_ptr<State> state_;

public:
    X86Emitter();
    ~X86Emitter();
    X86Emitter(const X86Emitter &) = delete;
    X86Emitter &operator=(const X86Emitter &) = delete;
    const std::map<std::string, FunctionStackFacts> &stackFacts() const;
    std::string stackFactsJson() const;
    std::string abiFactsJson(const ir::ValidatedModule &validated, const AbiDeclarations &declarations) const;
    std::string emit(const ir::ValidatedModule &validated,
                     SymbolBinding binding = SymbolBinding::Default,
                     ReflectionEmission reflection = ReflectionEmission::All);
};
} // namespace aurora
