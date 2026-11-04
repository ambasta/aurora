// Literal private records, independent of production bridge helpers.
// Actual kernel copy source and one generated language probe share this driver.
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <limits>

extern "C" std::uint64_t __au_runtime_process_snapshot_copy(const void *);
extern "C" std::uint64_t invocation_bytes_probe(const void *);
extern "C" long aurora_install_integer_signal_observer();
namespace {
using U64 = std::uint64_t;
using I64 = std::int64_t;
using Bytes = std::array<unsigned char, 4112>;
std::size_t checks = 0;
void need(bool value, const char *reason) {
    if (!value) {
        std::fprintf(stderr, "FAIL invocation byte views: %s\n", reason);
        std::exit(1);
    }
    ++checks;
}
// kind, contiguous address, three unused owner words, logical start, length.
void view(U64 *record, unsigned char *data, std::size_t start, std::size_t count) {
    const std::array<U64, 7> words{0, reinterpret_cast<U64>(data + start), 0, 0, 0, 0, count};
    std::copy(words.begin(), words.end(), record);
}
} // namespace
int main(int argc, char **argv) {
    Bytes source{}, destination{};
    for (std::size_t i = 0; i < source.size(); ++i)
        source[i] = static_cast<unsigned char>((i * 37 + 129) % 256);
    const auto original_source = source;
    if (argc == 3) {
        alignas(16) std::array<U64, 16> record{};
        view(record.data(), destination.data(), 0, 1);
        view(record.data() + 7, source.data(), 0, 0);
        const auto field = std::strtoul(argv[1], nullptr, 10);
        need(field < 14, "malformed record field");
        record[field] = std::strtoull(argv[2], nullptr, 10);
        need(aurora_install_integer_signal_observer() == 0, "install exact fault observer");
        static_cast<void>(invocation_bytes_probe(record.data()));
        need(false, "noncanonical record entered body");
    }
    need(argc == 1, "native test arguments");
    for (const std::size_t count : {0U, 1U, 7U, 255U, 4095U, 4096U}) {
        for (const std::size_t offset : {0U, 1U, 8U}) {
            destination.fill(0xa5);
            auto expected = destination;
            std::copy_n(source.begin() + 3, count, expected.begin() + offset);
            alignas(16) std::array<U64, 14> record{};
            view(record.data(), destination.data(), offset, count);
            view(record.data() + 7, source.data(), 3, count);
            const auto original_record = record;
            need(__au_runtime_process_snapshot_copy(record.data()) == 1, "copy result");
            need(record == original_record, "invocation descriptor unchanged");
            need(destination == expected, "whole destination including prefix/suffix canaries");
            need(source == original_source, "readonly source unchanged");
            need(__au_runtime_process_snapshot_copy(record.data()) == 1, "repeat copy");
            need(destination == expected, "repeat copy unchanged boundaries");
        }
    }
    for (const auto sizes : {std::array<std::size_t, 2>{0, 1}, {1, 0}, {3, 4}, {4096, 4095}}) {
        destination.fill(0x6b);
        const auto expected = destination;
        alignas(16) std::array<U64, 14> record{};
        view(record.data(), destination.data(), 2, sizes[0]);
        view(record.data() + 7, source.data(), 3, sizes[1]);
        need(!__au_runtime_process_snapshot_copy(record.data()), "mismatched extent refused");
        need(destination == expected, "mismatch refused before first write");
    }
    for (const std::size_t count : {0U, 1U, 4096U}) {
        const std::array<I64, 7> indices{std::numeric_limits<I64>::min(),
                                         -1,
                                         0,
                                         1,
                                         static_cast<I64>(count) - 1,
                                         static_cast<I64>(count),
                                         std::numeric_limits<I64>::max()};
        for (const auto index : indices) {
            destination.fill(0xa5);
            auto expected = destination;
            const bool valid = index >= 0 && static_cast<U64>(index) < count;
            if (valid)
                expected[8 + static_cast<std::size_t>(index)] = 255;
            alignas(16) std::array<U64, 16> record{};
            view(record.data(), destination.data(), 8, count);
            view(record.data() + 7, source.data(), 0, 0);
            record[14] = static_cast<U64>(index);
            record[15] = 255;
            const auto original_record = record;
            need(invocation_bytes_probe(record.data()) == (valid ? 255 : 256), "checked set/read result");
            need(record == original_record, "probe descriptor unchanged");
            need(destination == expected, "checked set whole-buffer canaries");
        }
    }
    std::printf("PASS invocation byte views: %zu checks\n", checks);
}
