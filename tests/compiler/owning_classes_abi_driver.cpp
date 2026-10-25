// Hosted observer for owning_classes_abi.py: the literal-layout host side of each
// emitted owning-class boundary, linked with the real hosted byte adapter.
#include "runtime/hosted_bytes.hpp"
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
using namespace aurora::hosted::bytes;
extern "C" std::uint64_t __au_runtime_bytes_test_entry(void *, void *);
struct Trace {
    std::vector<void *> allocations;
    std::vector<bool> live;
    std::vector<std::size_t> released;
    static void *allocate(void *context, std::size_t size) noexcept {
        auto &self = *static_cast<Trace *>(context);
        void *p = std::malloc(size);
        if (p) {
            self.allocations.push_back(p);
            self.live.push_back(true);
        }
        return p;
    }
    static void release(void *context, void *p) noexcept {
        auto &self = *static_cast<Trace *>(context);
        for (std::size_t i = 0; i < self.allocations.size(); ++i)
            if (self.live[i] && self.allocations[i] == p) {
                self.live[i] = false;
                self.released.push_back(i + 1);
                std::free(p);
                return;
            }
        std::abort();
    }
};
static void check(bool value, const char *message) {
    if (!value) {
        std::fprintf(stderr, "ABI failure: %s\n", message);
        std::exit(90);
    }
}
static void put(void *p, std::uint64_t value) {
    std::memcpy(p, &value, 8);
}
static std::uint64_t get(const void *p) {
    std::uint64_t value;
    std::memcpy(&value, p, 8);
    return value;
}
static void allocate_field(unsigned char *p, Region &region, std::int64_t length) {
    NativeOwner owner{};
    __au_runtime_bytes_allocate(region.id(), length, &owner);
    check(owner.success == 1, "host fixture allocation succeeded");
    std::memcpy(p, &owner, 32);
}
static void init_parcel(unsigned char *p, Region &region, int n) {
    p[0] = 197 + n;
    put(p + 40, 123456789 + n);
    p[80] = 223 + n;
    allocate_field(p + 8, region, 3 + n);
    allocate_field(p + 48, region, 5 + n);
}
static void padding(const unsigned char *p, unsigned char poison) {
    for (int i = 1; i < 8; ++i)
        check(p[i] == poison, "leading representation padding preserved");
    for (int i = 81; i < 88; ++i)
        check(p[i] == poison, "trailing representation padding preserved");
}
static void consumed(const unsigned char *p, int n) {
    check(p[0] == 197 + n && get(p + 40) == static_cast<unsigned>(123456789 + n) && p[80] == 223 + n,
          "move preserves source scalar bytes");
    for (int base : {8, 48})
        for (int i = 0; i < 32; ++i)
            check(p[base + i] == 0, "source descriptor cleared");
    padding(p, 0xab);
}
static void valid_result(const unsigned char *p, Region &region) {
    check(p[0] == 197 && get(p + 40) == 123456789 && p[80] == 223, "result scalar layout");
    for (int base : {8, 48}) {
        check(get(p + base) == region.id() && get(p + base + 8) != 0 && get(p + base + 24) == 1,
              "result descriptor words survive padding cleanup");
        check(get(p + base + 16) == static_cast<unsigned>(base == 8 ? 3 : 5), "result descriptor length");
    }
    padding(p, 0xcd);
}
static void drop(unsigned char *p) {
    NativeOwner owner{};
    std::memcpy(&owner, p, 32);
    std::memset(p, 0, 32);
    __au_runtime_bytes_drop(&owner);
}
static void seed_parcel(unsigned char *p) {
    for (int base : {8, 48}) {
        NativeOwner owner{};
        std::memcpy(&owner, p + base, 32);
        for (std::int64_t i = 0; i < owner.length; ++i)
            check(__au_runtime_bytes_set(&owner, i, base + i) == 1, "seed copied payload bytes");
    }
}
static void
resized_parcel(const unsigned char *p, const unsigned char *before, int field, Region &region, unsigned char poison) {
    check(p[0] == 197 && get(p + 40) == 123456789 && p[80] == 223, "resize preserves scalar bytes");
    padding(p, poison);
    for (int base : {8, 48}) {
        const int initial = base == 8 ? 3 : 5;
        check(get(p + base) == region.id() && get(p + base + 24) == 1, "resize preserves region and success");
        check(get(p + base + 16) == static_cast<unsigned>(base == field ? 65 : initial),
              "resize targets exact descriptor length");
        if (base == field)
            check(get(p + base + 8) != get(before + base + 8), "changed-size resize replaces allocation identity");
        else
            check(std::memcmp(p + base, before + base, 32) == 0, "resize leaves sibling descriptor unchanged");
        NativeOwner owner{};
        std::memcpy(&owner, p + base, 32);
        for (std::int64_t i = 0; i < initial; ++i)
            check(__au_runtime_bytes_at(&owner, i) == static_cast<unsigned>(base + i),
                  "resize preserves both payload prefixes");
        if (base == field)
            for (std::int64_t i = initial; i < 65; ++i)
                check(__au_runtime_bytes_at(&owner, i) == 0, "resize zeroes every extension byte");
    }
}
int main(int argc, char **argv) {
    check(argc == 2, "one fixture mode");
    const std::string mode = argv[1];
    const bool resize = mode.starts_with("resize-");
    const bool resize_move = mode == "resize-move";
    const bool resize_method = resize && !resize_move;
    const bool copied_resource = mode == "copied-resource";
    const bool six_input = mode == "six" || copied_resource;
    const int resize_field = mode == "resize-odd" || mode == "resize-even" ? 48 : 8;
    Trace trace;
    Region region(1024, Allocator{&trace, Trace::allocate, Trace::release});
    alignas(16) std::array<unsigned char, 208> input;
    alignas(16) std::array<unsigned char, 112> output;
    input.fill(0xab);
    output.fill(0xcd);
    unsigned char *record = input.data() + 8, *result = output.data() + 8;
    // Ordinary resource entry records start with authority. Borrowed methods
    // receive the object directly, so no record header may overwrite padding.
    if (mode != "method" && !resize_method)
        put(record, region.id());
    if (mode == "move" || six_input || resize_move)
        init_parcel(record + 8, region, 0);
    if (six_input)
        init_parcel(record + 96, region, 1);
    if (mode == "method" || resize_method) {
        init_parcel(record, region, 0);
        padding(record, 0xab);
    }
    if (resize)
        seed_parcel(resize_move ? record + 8 : record);
    const auto input_before = input;
    const auto answer = __au_runtime_bytes_test_entry(record, result);
    if (mode.starts_with("construct"))
        check(answer == ((mode == "construct" || mode == "construct-produced") ? 8 : 42),
              "constructor lengths and cleanup preserve result");
    else if (mode == "copied")
        check(answer == 42, "owning receiver with copied args and result");
    else if (copied_resource) {
        consumed(record + 8, 0);
        consumed(record + 96, 1);
        check(result[0] == 201 && get(result + 8) == 0x123456789ULL,
              "copied resource result preserves packed scalar values after cleanup");
        for (int i = 1; i < 8; ++i)
            check(result[i] == 0xcd, "copied resource return preserves result padding");
    } else if (resize_method) {
        if (mode == "resize-failed") {
            check(answer == static_cast<std::uint64_t>(-1000), "failed resize result");
            check(input == input_before, "failed resize preserves every input byte");
            for (int base : {8, 48}) {
                NativeOwner owner{};
                std::memcpy(&owner, record + base, 32);
                for (std::int64_t i = 0; i < owner.length; ++i)
                    check(__au_runtime_bytes_at(&owner, i) == static_cast<unsigned>(base + i),
                          "failed resize preserves both payloads");
            }
        } else {
            const std::uint64_t saved = mode == "resize-odd"    ? 4294967313ULL
                                        : mode == "resize-even" ? 8589934627ULL
                                                                : 0;
            check(answer == 65 + saved, "resize result and saved scalar stack");
            resized_parcel(record, input_before.data() + 8, resize_field, region, 0xab);
            for (std::size_t i = 0; i < input.size(); ++i)
                if (i < static_cast<std::size_t>(8 + resize_field + 8) ||
                    i >= static_cast<std::size_t>(8 + resize_field + 24))
                    check(input[i] == input_before[i], "resize only changes selected identity and length words");
        }
        drop(record + 48);
        drop(record + 8);
    } else if (resize_move) {
        consumed(record + 8, 0);
        resized_parcel(result, input_before.data() + 16, 8, region, 0xcd);
        drop(result + 48);
        drop(result + 8);
    } else if (mode == "method") {
        check(answer == 1, "borrowed payload write result");
        check(input == input_before, "borrowed method does not alter descriptor/scalar/padding bytes");
        NativeOwner owner{};
        std::memcpy(&owner, record + 8, 32);
        check(__au_runtime_bytes_at(&owner, 0) == 42, "borrowed write reaches actual payload");
        drop(record + 48);
        drop(record + 8);
    } else {
        consumed(record + 8, 0);
        if (mode == "six")
            consumed(record + 96, 1);
        valid_result(result, region);
        NativeOwner owner{};
        std::memcpy(&owner, result + 8, 32);
        check(__au_runtime_bytes_at(&owner, 0) == 0, "real zeroed allocated payload survived transfer");
        drop(result + 48);
        drop(result + 8);
    }
    for (int i = 0; i < 8; ++i)
        check(input[i] == 0xab && output[i] == 0xcd, "left canary");
    const int input_extent = six_input                           ? 184
                             : mode == "move" || resize_move     ? 96
                             : mode == "method" || resize_method ? 88
                                                                 : 8;
    for (std::size_t i = 8 + input_extent; i < input.size(); ++i)
        check(input[i] == 0xab, "right input canary");
    for (std::size_t i = copied_resource ? 24 : 96; i < output.size(); ++i)
        check(output[i] == 0xcd, "right result canary");
    if (mode.starts_with("construct") || mode == "method" || mode == "copied" || resize_method)
        for (auto byte : output)
            check(byte == 0xcd, "scalar result does not write hidden destination");
    std::vector<std::size_t> expected =
        resize && mode != "resize-failed"
            ? (resize_field == 8 ? std::vector<std::size_t>{1, 2, 3} : std::vector<std::size_t>{2, 3, 1})
        : mode == "copied" ? std::vector<std::size_t>{1}
        : six_input        ? std::vector<std::size_t>{5, 4, 3, 2, 1}
                           : std::vector<std::size_t>{2, 1};
    check(trace.released == expected, "exact reverse release order, no duplicate release");
    const auto metrics = region.metrics();
    check(metrics.used == 0 && metrics.live_allocations == 0 && metrics.releases == expected.size(),
          "all transferred resources released exactly once");
    check(region.close(), "region closes without leaked owners");
    if (copied_resource) {
        check(result[0] == 201 && get(result + 8) == 0x123456789ULL,
              "copied resource payload remains readable after region close");
        for (int i = 1; i < 8; ++i)
            check(result[i] == 0xcd, "copied resource result padding survives region close");
    }
    std::printf("PASS hosted owning ABI %s", mode.c_str());
    for (auto id : trace.released)
        std::printf(" %zu", id);
    std::puts("");
}
