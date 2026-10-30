#include <cstdint>
#include <cstdlib>

namespace {
using Word = std::uint64_t;
class Grant {
public:
    Word identity, generation;
};
class Report {
public:
    Word state, status, value;
};
unsigned mode = 0, calls = 0;
void authenticate(Word identity, Word generation, unsigned expected) {
    if (identity != 0x45584543555445ULL || generation != 91 || calls++ != expected)
        std::abort();
}
} // namespace
extern "C" Word checked_group_entry(const Grant *);
extern "C" void __au_runtime_execution_prepare(Word identity, Word generation, Report *result) {
    authenticate(identity, generation, 0);
    *result = {0, 0, 1};
    switch (mode) {
    case 1:
        result->state = 3;
        break;
    case 2:
        result->state = Word{1} << 32;
        break;
    case 3:
        result->status = 8;
        break;
    case 4:
        result->status = Word{1} << 32;
        break;
    case 5:
        result->value = 2;
        break;
    case 6:
        result->value = Word{1} << 32;
        break;
    }
}
extern "C" void __au_runtime_execution_advance(Word identity, Word generation, Report *result) {
    authenticate(identity, generation, 1);
    *result = {1, 0, UINT64_MAX};
    switch (mode) {
    case 7:
        result->state = 4;
        break;
    case 8:
        result->state = Word{1} << 32;
        break;
    case 9:
        result->status = 8;
        break;
    case 10:
        result->status = Word{1} << 32;
        break;
    }
}
extern "C" Word __au_runtime_execution_output(Word identity, Word generation) {
    authenticate(identity, generation, 2);
    return mode == 11 ? 2 : mode == 12 ? Word{1} << 32 : 0;
}
extern "C" Word __au_runtime_execution_request(Word identity, Word generation) {
    authenticate(identity, generation, 3);
    return mode == 13 ? 3 : mode == 14 ? Word{1} << 32 : 0;
}
extern "C" Word __au_runtime_execution_finish(Word identity, Word generation, Word reason) {
    authenticate(identity, generation, 4);
    if (reason != 0)
        std::abort();
    return mode == 15 ? 2 : mode == 16 ? Word{1} << 32 : 0;
}
int main(int argc, char **argv) {
    mode = argc == 2 ? std::atoi(argv[1]) : 0;
    const Grant grant{0x45584543555445ULL, 91};
    return checked_group_entry(&grant) == 42 && calls == 5 ? 0 : 1;
}
