// A native driver is one translation unit that includes several kernel model
// tests compiled with the same flags and link inputs, each wrapped in its own
// namespace, so their headers are parsed once. `driver CASE` runs one case.
#pragma once
#include <cstdio>
#include <initializer_list>
#include <string_view>

namespace native_driver {
class Case {
public:
    std::string_view name;
    int (*run)();
};

inline auto run(int argc, char **argv, std::initializer_list<Case> cases) -> int {
    if (argc == 2)
        for (const auto &entry : cases)
            if (entry.name == argv[1])
                return entry.run();
    std::fprintf(stderr, "usage: %s CASE\ncases:", argv[0]);
    for (const auto &entry : cases)
        std::fprintf(stderr, " %.*s", static_cast<int>(entry.name.size()), entry.name.data());
    std::fputc('\n', stderr);
    return 2;
}
} // namespace native_driver
