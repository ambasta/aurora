// Test the trusted host adapter independently of generated Aurora code. Each
// malformed return must fail closed before host slicing, narrowing or progress.
#include "lexer.hpp"
#include <array>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <limits>
#include <stdexcept>

namespace {
using Words = std::array<std::int64_t, 4>;
Words reply;
bool normal = false;
int calls = 0;
void require(bool value, const char *message) {
    if (!value)
        throw std::runtime_error(message);
}
} // namespace

extern "C" void aurora_hosted_lexer_invoke(const void *input, void *output) {
    std::array<std::int64_t, 10> record;
    std::memcpy(record.data(), input, sizeof(record));
    ++calls;
    Words next = reply;
    if (normal)
        next = {record[7] == record[6] ? 3 : 0, record[6], 1, 0};
    std::memcpy(output, next.data(), sizeof(next));
}

int main() {
    try {
        const auto source = std::make_shared<const aurora::SourceText>("invalid-return.au", "abc");
        normal = true;
        const auto accepted = aurora::lexSource(source);
        require(calls == 2 && accepted.tokens.size() == 2 && accepted.tokens.front().text == "abc" &&
                    accepted.tokens.back().text == "<eof>",
                "valid stub must traverse token and EOF");
        normal = false;
        constexpr auto maximum = std::numeric_limits<std::int64_t>::max();
        constexpr auto minimum = std::numeric_limits<std::int64_t>::min();
        const std::array<Words, 20> invalid{{
            {-1, 1, 1, 0},      {7, 1, 1, 0},       {8, 1, 1, 0},       {0, -1, 1, 0}, {0, 0, 1, 0},
            {0, 4, 1, 0},       {0, minimum, 1, 0}, {0, maximum, 1, 0}, {0, 1, 0, 0},  {0, 1, maximum, 0},
            {0, 1, minimum, 0}, {1, 1, 3, 1},       {1, 1, 2, 0},       {1, 1, 1, 1},  {0, 1, 2, 1},
            {1, 1, 2, -1},      {1, 1, 2, 2},       {1, 1, 2, maximum}, {3, 0, 1, 0},  {3, 3, 1, 0},
        }};
        for (const auto &value : invalid) {
            reply = value;
            calls = 0;
            bool rejected = false;
            try {
                static_cast<void>(aurora::lexSource(source));
            } catch (const aurora::Error &error) {
                rejected = error.diagnostic.code == aurora::DiagnosticCode::Internal &&
                           error.diagnostic.message == "hosted lexer returned an invalid event";
            }
            require(rejected && calls == 1, "invalid return must fail closed on first call");
            require(source->text == "abc", "source backing changed");
        }
        std::cout << "PASS hosted adapter valid control and " << invalid.size() << " malformed-result controls\n";
    } catch (const std::exception &error) {
        std::cerr << "FAIL " << error.what() << '\n';
        return 1;
    }
}
