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
int main(int argc, char **argv) {
    mode = argc == 2 ? std::atoi(argv[1]) : 0;
    const Grant grant{0x45584543555445ULL, 91};
    return checked_group_entry(&grant) == 42 && calls == (mode == 17 ? 9u : 7u) ? 0 : 1;
}
