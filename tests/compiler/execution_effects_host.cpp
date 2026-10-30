#include <cstdint>
#include <cstdlib>

namespace {
using Word = std::uint64_t;
class Grant {
public:
    Word identity, generation;
};
class Preparation {
public:
    Word state, status;
};
class Report {
public:
    Word state, status, value;
};
unsigned mode = 0, calls = 0, requests = 0;
void authenticate(Word identity, Word generation, unsigned expected) {
    if (identity != 0x45584543555445ULL || generation != 91 || calls++ != expected)
        std::abort();
}
} // namespace
extern "C" Word checked_group_entry(const Grant *);
extern "C" void __au_runtime_execution_prepare(Word identity, Word generation, Grant *result) {
    authenticate(identity, generation, 0);
    *result = {mode == 23 ? 0 : 0x4c45415345ULL, mode == 24 ? 0 : generation};
}
void authenticate_lease(Word identity, Word generation, unsigned expected) {
    if (identity != 0x4c45415345ULL)
        std::abort();
    authenticate(0x45584543555445ULL, generation, expected);
}
extern "C" void __au_runtime_execution_preparation(Word identity, Word generation, Preparation *result) {
    authenticate_lease(identity, generation, 1);
    *result = {0, mode == 18 ? 8u : 0u};
    switch (mode) {
    case 1:
        result->state = 3;
        break;
    case 2:
        result->state = Word{1} << 32;
        break;
    case 3:
        result->status = 9;
        break;
    case 4:
        result->status = Word{1} << 32;
        break;
    }
}
extern "C" void __au_runtime_execution_advance(Word identity, Word generation, Report *result) {
    authenticate_lease(identity, generation, 2);
    *result = {1, mode == 19 ? 8u : 0u, UINT64_MAX};
    switch (mode) {
    case 7:
        result->state = 4;
        break;
    case 8:
        result->state = Word{1} << 32;
        break;
    case 9:
        result->status = 9;
        break;
    case 10:
        result->status = Word{1} << 32;
        break;
    }
}
extern "C" Word __au_runtime_execution_output(Word identity, Word generation) {
    authenticate_lease(identity, generation, 3);
    return mode == 11 ? 2 : mode == 12 ? Word{1} << 32 : 0;
}
extern "C" Word __au_runtime_execution_request(Word identity, Word generation) {
    authenticate_lease(identity, generation, 4 + requests);
    ++requests;
    if (mode == 17 && requests < 3)
        return 3;
    return mode == 13 ? 5 : mode == 14 ? Word{1} << 32 : mode == 20 ? 4 : 0;
}
extern "C" Word __au_runtime_execution_cancel(Word identity, Word generation) {
    authenticate_lease(identity, generation, 4 + requests);
    return mode == 5 ? 3 : mode == 6 ? Word{1} << 32 : mode == 21 ? 1 : mode == 22 ? 2 : 0;
}
extern "C" Word __au_runtime_execution_finish(Word identity, Word generation, Word reason) {
    authenticate_lease(identity, generation, 5 + requests);
    if (reason != 4)
        std::abort();
    return mode == 15 ? 2 : mode == 16 ? Word{1} << 32 : 0;
}
class BootstrapPreparation {
public:
    Word loaded, volume_bytes, chunk_bytes, storage_required;
};
void authenticate_bootstrap(Word identity, Word generation, unsigned expected, bool issuer = false) {
    if (identity != (issuer ? 0x424f4f54495353ULL : 0x424f4f544c4541ULL) || generation != 92 || calls++ != expected)
        std::abort();
}
extern "C" void __au_runtime_service_bootstrap_begin(Word identity, Word generation, Grant *result) {
    authenticate_bootstrap(identity, generation, 0, true);
    *result = {mode == 111 ? 0 : 0x424f4f544c4541ULL, mode == 112 ? 0 : generation};
}
extern "C" void
__au_runtime_service_bootstrap_preparation(Word identity, Word generation, BootstrapPreparation *result) {
    authenticate_bootstrap(identity, generation, 1);
    *result = {mode == 101   ? 2
               : mode == 102 ? Word{1} << 32
               : mode == 117 ? 0
                             : 1,
               UINT64_MAX,
               42,
               mode == 103   ? 2
               : mode == 104 ? Word{1} << 32
               : mode == 117 ? 0
                             : 1};
}
extern "C" Word __au_runtime_service_bootstrap_begin_volume(Word identity, Word generation) {
    authenticate_bootstrap(identity, generation, 2);
    return mode == 105 ? 2 : mode == 106 ? Word{1} << 32 : mode == 113 ? 1 : 0;
}
extern "C" Word __au_runtime_service_bootstrap_copy_volume(Word identity, Word generation, Word offset) {
    authenticate_bootstrap(identity, generation, 3);
    if (offset != UINT64_MAX)
        std::abort();
    return mode == 113 ? 1 : 0;
}
extern "C" Word __au_runtime_service_bootstrap_seal_volume(Word identity, Word generation) {
    authenticate_bootstrap(identity, generation, 4);
    return mode == 113 ? 1 : 0;
}
extern "C" Word __au_runtime_service_bootstrap_admit_storage(Word identity, Word generation) {
    authenticate_bootstrap(identity, generation, 5);
    return mode == 113 ? 1 : 0;
}
extern "C" Word __au_runtime_service_bootstrap_advance(Word identity, Word generation) {
    authenticate_bootstrap(identity, generation, 6);
    return mode == 107 ? 3 : mode == 108 ? Word{1} << 32 : mode == 114 ? 0 : mode == 115 ? 2 : 1;
}
extern "C" Word __au_runtime_service_bootstrap_finish(Word identity, Word generation, Word disposition) {
    authenticate_bootstrap(identity, generation, 7);
    if (disposition != 0)
        std::abort();
    return mode == 109 ? 2 : mode == 110 ? Word{1} << 32 : mode == 116 ? 1 : 0;
}
int main(int argc, char **argv) {
    mode = argc == 2 ? std::atoi(argv[1]) : 0;
    if (mode >= 100) {
        const Grant grant{0x424f4f54495353ULL, 92};
        return checked_group_entry(&grant) == 42 && calls == 8 ? 0 : 1;
    }
    const Grant grant{0x45584543555445ULL, 91};
    return checked_group_entry(&grant) == 42 && calls == (mode == 17 ? 9u : 7u) ? 0 : 1;
}
