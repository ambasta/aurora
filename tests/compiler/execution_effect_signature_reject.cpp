// These deliberately wrong native definitions must conflict with compiler facts.
#include "execution-authority-effects.hpp"
extern "C" bool __au_runtime_execution_authority_retire(const void *, std::uint64_t, const void *, std::uint64_t) {
    return true;
}
extern "C" std::uint32_t __au_runtime_execution_authority_finish(const void *, std::uint64_t, const void *) {
    return 1;
}
extern "C" void __au_runtime_execution_authority_activate(
    const void *, std::uint32_t, const void *, aurora::lifecycle::Observation *, std::uint64_t) {
}
extern "C" void __au_runtime_execution_authority_force(
    const void *, std::uint64_t, const void *, aurora::lifecycle::Observation *, std::uint32_t) {
}
