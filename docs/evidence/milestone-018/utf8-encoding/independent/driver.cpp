#include <cstdint>
#include <cstdio>
extern "C" std::uint64_t observe(std::uint64_t);
int main() {
    std::uint64_t items[4096];
    for (;;) {
        const auto n = std::fread(items, sizeof(items[0]), 4096, stdin);
        if (n == 0) return std::ferror(stdin) ? 2 : 0;
        for (std::size_t i = 0; i < n; ++i) items[i] = observe(items[i]);
        if (std::fwrite(items, sizeof(items[0]), n, stdout) != n) return 3;
    }
}
