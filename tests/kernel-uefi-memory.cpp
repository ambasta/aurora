#include <array>
#include <cstddef>
#include <cstdio>
#include <cstdlib>

extern "C" void* memcpy(void*, const void*, std::size_t);
extern "C" void* memset(void*, int, std::size_t);
extern "C" void* memmove(void*, const void*, std::size_t);
extern "C" int memcmp(const void*, const void*, std::size_t);

static void need(bool valid) {
    if (!valid) std::abort();
}

using Buffer = std::array<unsigned char, 1100>;

// Independent byte oracle: do not verify a memory primitive using itself.
static void fill(Buffer& buffer, unsigned char value) {
    volatile unsigned char* bytes = buffer.data();
    for (std::size_t i = 0; i < buffer.size(); ++i) bytes[i] = value;
}
static void copy(Buffer& destination, const Buffer& source) {
    volatile unsigned char* out = destination.data();
    const volatile unsigned char* in = source.data();
    for (std::size_t i = 0; i < source.size(); ++i) out[i] = in[i];
}
static void equal(const Buffer& actual, const Buffer& expected) {
    const volatile unsigned char* left = actual.data();
    const volatile unsigned char* right = expected.data();
    for (std::size_t i = 0; i < actual.size(); ++i) need(left[i] == right[i]);
}

int main() {
    Buffer source{}, actual{}, expected{};
    for (std::size_t i = 0; i < source.size(); ++i) source[i] = (i * 37 + 129) & 255;
    unsigned cases = 0;
    for (std::size_t count : {0, 1, 2, 7, 8, 15, 16, 31, 64, 255, 256, 513, 1024}) {
        for (std::size_t offset : {0, 1, 3, 7}) {
            fill(actual, 0xa5); fill(expected, 0xa5);
            need(memcpy(actual.data() + offset, source.data() + 3, count) == actual.data() + offset);
            for (std::size_t i = 0; i < count; ++i) expected[offset + i] = source[3 + i];
            equal(actual, expected);
            for (int value : {0, 0xa5, -1, 0x123}) {
                fill(actual, 0x5a); fill(expected, 0x5a);
                need(memset(actual.data() + offset, value, count) == actual.data() + offset);
                for (std::size_t i = 0; i < count; ++i) expected[offset + i] = static_cast<unsigned char>(value);
                equal(actual, expected); ++cases;
            }
            for (std::size_t from : {0, 1, 8, 32}) {
                copy(actual, source); copy(expected, source);
                need(memmove(actual.data() + offset, actual.data() + from, count) == actual.data() + offset);
                for (std::size_t i = 0; i < count; ++i) expected[offset + i] = source[from + i];
                equal(actual, expected); ++cases;
            }
            need(memcmp(source.data() + offset, source.data() + offset, count) == 0);
            if (count) {
                copy(actual, source); actual[offset + count - 1] ^= 0x80;
                const int wanted = actual[offset + count - 1] < source[offset + count - 1] ? -1 : 1;
                const int result = memcmp(actual.data() + offset, source.data() + offset, count);
                need((result > 0) - (result < 0) == wanted);
            }
            ++cases;
        }
    }
    std::printf("PASS: %u freestanding memory cases (bounds, overlap, byte values, return pointers)\n", cases);
}
