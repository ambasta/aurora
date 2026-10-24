// Generic host for tests/compiler/runtime_records.py. It streams fixed-size
// records into one compiled Aurora driver entry and writes every complete
// 64-bit observation. Usage: program <record-bytes> <cases.bin> [options].
// Each case is a little-endian u64 call count followed by one record. Options:
//   segments: the record instead starts zeroed and is followed by a u64 run
//     count and that many (u64 offset, u64 length, bytes) nonzero runs.
//   words=<offset>:<capacity>: each call fills the record's u64 array at that
//     offset and returns how many words it wrote; the host writes that count
//     and then the words, instead of the returned value itself.
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

extern "C" std::uint64_t aurora_record_entry(void *record, std::int64_t field);

namespace {
bool number(const char *text, char stop, unsigned long long &value, const char **rest) {
    char *end = nullptr;
    value = std::strtoull(text, &end, 10);
    if (end == text || *end != stop)
        return false;
    *rest = end;
    return true;
}
} // namespace

int main(int argc, char **argv) {
    if (argc < 3)
        return 1;
    const char *rest = nullptr;
    unsigned long long size = 0;
    if (!number(argv[1], '\0', size, &rest) || size == 0 || size % 8 != 0 || size > (1U << 20))
        return 1;
    bool segmented = false;
    unsigned long long words = 0, capacity = 0;
    for (int option = 3; option < argc; ++option) {
        if (std::strcmp(argv[option], "segments") == 0) {
            segmented = true;
        } else if (std::strncmp(argv[option], "words=", 6) == 0) {
            if (!number(argv[option] + 6, ':', words, &rest) || !number(rest + 1, '\0', capacity, &rest) ||
                capacity == 0 || words % 8 != 0 || capacity > (size - words) / 8)
                return 1;
        } else {
            return 1;
        }
    }
    std::FILE *file = std::fopen(argv[2], "rb");
    if (file == nullptr)
        return 2;
    std::vector<std::uint64_t> record(size / 8);
    while (true) {
        std::uint64_t fields = 0;
        const std::size_t count = std::fread(&fields, 1, sizeof(fields), file);
        if (count == 0)
            break;
        if (count != sizeof(fields) || fields == 0 || fields > 65536)
            return 3;
        if (segmented) {
            std::memset(record.data(), 0, size);
            std::uint64_t runs = 0;
            if (std::fread(&runs, 1, sizeof(runs), file) != sizeof(runs) || runs > size)
                return 3;
            for (std::uint64_t run = 0; run < runs; ++run) {
                std::uint64_t extent[2] = {};
                if (std::fread(extent, 1, sizeof(extent), file) != sizeof(extent) || extent[0] > size ||
                    extent[1] > size - extent[0] ||
                    std::fread(reinterpret_cast<unsigned char *>(record.data()) + extent[0], 1, extent[1], file) !=
                        extent[1])
                    return 3;
            }
        } else if (std::fread(record.data(), 1, size, file) != size) {
            return 3;
        }
        for (std::uint64_t field = 0; field < fields; ++field) {
            const std::uint64_t value = aurora_record_entry(record.data(), static_cast<std::int64_t>(field));
            if (std::fwrite(&value, sizeof(value), 1, stdout) != 1)
                return 4;
            if (capacity == 0)
                continue;
            if (value > capacity)
                return 7;
            if (std::fwrite(record.data() + words / 8, sizeof(std::uint64_t), value, stdout) != value)
                return 4;
        }
    }
    const int result = std::ferror(file) ? 5 : 0;
    if (std::fclose(file) != 0 || std::fflush(stdout) != 0)
        return 6;
    return result;
}
