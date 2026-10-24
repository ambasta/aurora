// Test-only observation of a kernel policy over fixed full-width vector families.
// A family prints one summary line: its vector count, how many results were all
// zero, how many led with each small word (a status or action) or a larger word,
// and an FNV-1a digest of every (input words, result words) pair in order; small
// relations also print each row, or each row with a nonzero result. Drivers compare the output with a
// reviewed golden file, so a changed result anywhere changes the digest.
#pragma once
#include <cstdint>
#include <cstdio>
#include <initializer_list>
#include <map>
#include <random>
#include <string>

namespace policy_vectors {
using U64 = std::uint64_t;
inline constexpr U64 maximum = ~U64{0};

enum class Rows { none, all, nonzero };

class Family final {
public:
    explicit Family(const char *name, Rows rows = Rows::none) : name_(name), rows_(rows) {}
    Family(const Family &) = delete;
    auto operator=(const Family &) -> Family & = delete;
    ~Family() {
        std::printf("%s: %llu vectors", name_, static_cast<unsigned long long>(count_));
        for (const auto &[result, count] : histogram_)
            std::printf(" %s=%llu", result.c_str(), static_cast<unsigned long long>(count));
        std::printf(" digest=%016llx\n", static_cast<unsigned long long>(digest_));
    }
    auto observe(std::initializer_list<U64> input, std::initializer_list<U64> result) -> void {
        ++count_;
        for (const auto word : input)
            add(word);
        std::string text;
        bool zero = true;
        for (const auto word : result) {
            add(word);
            zero = zero && word == 0;
            char buffer[24];
            std::snprintf(buffer, sizeof(buffer), "%s%#llx", text.empty() ? "" : ",", static_cast<unsigned long long>(word));
            text += buffer;
        }
        const auto lead = *result.begin();
        ++histogram_[zero ? "zero" : lead < 16 ? "lead" + std::to_string(lead) : "word"];
        if (rows_ == Rows::all || (rows_ == Rows::nonzero && !zero)) {
            std::printf("%s", name_);
            for (const auto word : input)
                std::printf(" %#llx", static_cast<unsigned long long>(word));
            std::printf(" -> %s\n", text.c_str());
        }
    }

private:
    auto add(U64 word) -> void {
        for (unsigned i = 0; i < 8; ++i)
            digest_ = (digest_ ^ ((word >> (8 * i)) & 0xff)) * 0x100000001b3ULL;
    }
    const char *name_;
    Rows rows_;
    U64 count_{};
    U64 digest_ = 0xcbf29ce484222325ULL;
    std::map<std::string, U64> histogram_;
};

// Deterministic full-width samples; std::mt19937_64's sequence is fixed by the standard.
class Random final {
public:
    explicit Random(U64 seed) : engine_(seed) {}
    auto operator()() -> U64 {
        return engine_();
    }

private:
    std::mt19937_64 engine_;
};
} // namespace policy_vectors
