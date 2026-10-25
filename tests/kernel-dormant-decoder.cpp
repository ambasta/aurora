#include "../kernel/dormant-decoder.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <limits>

namespace kernel_dormant_decoder {
namespace {

std::size_t checks = 0;
std::size_t failures = 0;

void check(bool condition, const char *description) {
    ++checks;
    if (!condition) {
        ++failures;
        std::fprintf(stderr, "FAIL: %s\n", description);
    }
}

void put(std::span<std::byte> bytes, std::size_t offset, std::uint64_t value) {
    for (std::size_t byte = 0; byte != 8; ++byte) {
        bytes[offset + byte] = std::byte((value >> (byte * 8)) & 255);
    }
}

// Known-answer bytes authored from AMD 3.10, not from a production encoder.
// Metadata and its corresponding bytes are intentionally maintained separately.
class Fixture {
public:
    std::array<std::byte, 8192> dte{};
    std::array<std::byte, 4096> root{};
    independent::Input input{};

    Fixture() {
        input.dte = dte;
        input.root = root;
        input.pages = {0x1000, 0x2000, 0x5000, 0x9000, 0xb000};
        input.data_count = 2;
        input.physical_bits = 32;
        input.iovas = {0x3000, 0x4000};
        input.writable = {false, true};
        for (std::size_t rid = 0; rid != 256; ++rid) {
            dte[rid * 32] = std::byte{3};
        }
        dte[0x10 * 32 + 1] = std::byte{0x52};
        dte[0x10 * 32 + 7] = std::byte{0x60};
        dte[0x10 * 32 + 8] = std::byte{1};
        root[3 * 8] = std::byte{1};
        root[3 * 8 + 1] = std::byte{0x90};
        root[3 * 8 + 7] = std::byte{0x20};
        root[4 * 8] = std::byte{1};
        root[4 * 8 + 1] = std::byte{0xb0};
        root[4 * 8 + 7] = std::byte{0x60};
    }

    Fixture(const Fixture &) = delete;
    Fixture &operator=(const Fixture &) = delete;

    void single_page() {
        input.data_count = 1;
        input.pages[4] = 0;
        input.iovas[1] = 0;
        input.writable[1] = false;
        put(root, 4 * 8, 0);
    }
};

template <class Mutation> void rejects(Mutation mutation, const char *description) {
    Fixture fixture;
    mutation(fixture);
    check(!independent::validate(fixture.input), description);
    check(!independent::permits(fixture.input, 0x10, 0x3000, 1, false),
          "invalid snapshot cannot authorize even an otherwise mapped byte");
}

void known_answers() {
    Fixture fixture;
    const auto &in = fixture.input;
    check(independent::validate(in), "literal little-endian two-page snapshot");
    check(independent::permits(in, 0x10, 0x3000, 4096, false), "entire RO page read");
    check(!independent::permits(in, 0x10, 0x3000, 1, true), "RO leaf denies write");
    check(independent::permits(in, 0x10, 0x4fff, 1, true), "last RW byte writes");
    check(!independent::permits(in, 0x10, 0x4fff, 2, false), "end crosses into absent page");
    check(independent::permits(in, 0x10, 0x3fff, 2, false), "cross-page read");
    check(independent::permits(in, 0x10, 0x3000, 8192, false), "whole contiguous IOVA pair");
    check(!independent::permits(in, 0x10, 0x3fff, 2, true), "cross-page mixed-rights write");
    check(!independent::permits(in, 0x10, 0x2fff, 2, false), "start is absent");
    check(!independent::permits(in, 0x10, 0x3000, 0, false), "zero-length denied");
    check(!independent::permits(in, 0x10, 0x203000, 1, false), "upper IOVA cannot alias");
    check(!independent::permits(in, 0x10, 0xfffffffffffff000ULL, 4096, false), "wrapping request denied");
    check(!independent::permits(in, 0x10, 0x3000, std::numeric_limits<std::uint64_t>::max(), false),
          "overflowing length denied");
    check(!independent::permits(in, 0x10, 0x3000, 0x200000, false), "whole interval cannot exceed root range");
    for (std::uint32_t rid = 0; rid <= 65535; ++rid) {
        if (rid != 0x10) {
            check(!independent::permits(in, static_cast<std::uint16_t>(rid), 0x3000, 1, false),
                  "every other requester denied");
        }
    }
    fixture.input.writable[0] = true;
    fixture.root[3 * 8 + 7] = std::byte{0x60};
    check(independent::permits(in, 0x10, 0x3ffe, 4, true), "cross-page RW pair writes");

    Fixture single;
    single.single_page();
    check(independent::validate(single.input), "canonical one-page snapshot");
    check(independent::permits(single.input, 0x10, 0x3000, 4096, false), "one-page read");
    check(!independent::permits(single.input, 0x10, 0x3fff, 2, false), "one-page boundary denial");

    Fixture edges;
    put(edges.root, 3 * 8, 0);
    put(edges.root, 4 * 8, 0);
    edges.input.iovas = {0, 0x1ff000};
    put(edges.root, 0, 0x2000000000009001ULL);
    put(edges.root, 511 * 8, 0x600000000000b001ULL);
    check(independent::validate(edges.input), "first and last root slots");
    check(independent::permits(edges.input, 0x10, 0, 4096, false), "IOVA zero valid");
    check(independent::permits(edges.input, 0x10, 0x1fffff, 1, true), "last root byte valid");
    check(!independent::permits(edges.input, 0x10, 0x1fffff, 2, true), "last root byte overflow");
    check(!independent::permits(edges.input, 0x10, 0, 0x200000, false), "holes reject whole range");

    Fixture reversed;
    reversed.input.iovas = {0x4000, 0x3000};
    put(reversed.root, 3 * 8, 0x600000000000b001ULL);
    put(reversed.root, 4 * 8, 0x2000000000009001ULL);
    check(independent::validate(reversed.input), "mapping descriptions need not be sorted");
    check(independent::permits(reversed.input, 0x10, 0x3fff, 2, false),
          "walker follows root indexes rather than description order");
}

void description_mutations() {
    rejects(
        [](Fixture &f) {
            f.input.dte = f.input.dte.first(8191);
        },
        "short DTE span");
    rejects(
        [](Fixture &f) {
            f.input.root = f.input.root.first(4095);
        },
        "short root span");
    rejects(
        [](Fixture &f) {
            f.input.dte = {};
        },
        "empty DTE span");
    rejects(
        [](Fixture &f) {
            f.input.root = {};
        },
        "empty root span");
    rejects(
        [](Fixture &f) {
            f.input.data_count = 0;
        },
        "zero data pages");
    rejects(
        [](Fixture &f) {
            f.input.data_count = 3;
        },
        "excess data pages");
    rejects(
        [](Fixture &f) {
            f.input.data_count = std::size_t(-1);
        },
        "huge data count");
    rejects(
        [](Fixture &f) {
            f.input.iovas[0] = 0x3001;
        },
        "unaligned IOVA");
    rejects(
        [](Fixture &f) {
            f.input.iovas[0] = 0x200000;
        },
        "IOVA outside level one");
    rejects(
        [](Fixture &f) {
            f.input.iovas[0] = 0xfffffffffffff000ULL;
        },
        "overlarge IOVA");
    rejects(
        [](Fixture &f) {
            f.input.iovas[1] = f.input.iovas[0];
        },
        "duplicate IOVAs");
    rejects(
        [](Fixture &f) {
            f.input.writable[0] = true;
        },
        "description grants absent right");
    rejects(
        [](Fixture &f) {
            f.input.writable[1] = false;
        },
        "unexpected encoded write right");
    rejects(
        [](Fixture &f) {
            f.input.pages[1] = 0x3000;
        },
        "fragmented DTE backing");
    rejects(
        [](Fixture &f) {
            f.single_page();
            f.input.pages[4] = 0xb000;
        },
        "unused physical role");
    rejects(
        [](Fixture &f) {
            f.single_page();
            f.input.iovas[1] = 0x4000;
        },
        "unused IOVA");
    rejects(
        [](Fixture &f) {
            f.single_page();
            f.input.writable[1] = true;
        },
        "unused right");
    for (std::size_t role = 0; role != 5; ++role) {
        rejects(
            [role](Fixture &f) {
                ++f.input.pages[role];
            },
            "misaligned physical role");
        rejects(
            [role](Fixture &f) {
                f.input.pages[role] = 1ULL << 32;
            },
            "physical role too wide");
        rejects(
            [role](Fixture &f) {
                f.input.pages[role] = 0xfffffffffffff000ULL;
            },
            "physical interval near integer overflow");
        for (std::size_t other = 0; other != role; ++other) {
            rejects(
                [role, other](Fixture &f) {
                    f.input.pages[role] = f.input.pages[other];
                },
                "every overlapping role pair rejected");
        }
    }
    for (unsigned width = 0; width != 256; ++width) {
        Fixture fixture;
        fixture.input.physical_bits = static_cast<std::uint8_t>(width);
        check(independent::validate(fixture.input) == (width >= 32 && width <= 52),
              "only trusted physical widths 32 through 52 accepted");
    }
}

void physical_boundaries() {
    for (unsigned width = 32; width <= 52; ++width) {
        Fixture fixture;
        fixture.input.physical_bits = static_cast<std::uint8_t>(width);
        const auto end = std::uint64_t{1} << width;
        fixture.input.pages = {end - 5 * 4096, end - 4 * 4096, end - 3 * 4096, end - 2 * 4096, end - 4096};
        put(fixture.dte, 0x10 * 32, fixture.input.pages[2] | 0x6000000000000203ULL);
        put(fixture.root, 3 * 8, fixture.input.pages[3] | 0x2000000000000001ULL);
        put(fixture.root, 4 * 8, fixture.input.pages[4] | 0x6000000000000001ULL);
        check(independent::validate(fixture.input), "last physical page fits entire interval");
        check(independent::permits(fixture.input, 0x10, 0x4fff, 1, true), "last physical byte allowed at each width");
        fixture.input.pages[4] = end;
        put(fixture.root, 4 * 8, end | 0x6000000000000001ULL);
        check(!independent::validate(fixture.input), "first over-width page rejected");
        fixture.input.pages[0] = end - 4096;
        fixture.input.pages[1] = end;
        check(!independent::validate(fixture.input), "DTE complete pair must fit width");
    }
}

void byte_mutations() {
    rejects(
        [](Fixture &f) {
            put(f.dte, 0x10 * 32 + 8, 0);
        },
        "mapped domain zero conflicts");
    rejects(
        [](Fixture &f) {
            put(f.dte, 17 * 32 + 8, 1);
        },
        "denied domain cannot match mapped root");
    rejects(
        [](Fixture &f) {
            put(f.dte, 0, 0);
        },
        "zero default DTE is bypass");
    rejects(
        [](Fixture &f) {
            put(f.dte, 0x10 * 32, 0);
        },
        "zero target DTE is bypass");
    rejects(
        [](Fixture &f) {
            f.root[3 * 8] = std::byte{0};
        },
        "PR-clear nonzero leaf");
    rejects(
        [](Fixture &f) {
            put(f.root, 7 * 8, 0x200000000000c000ULL);
        },
        "nonzero absent leaf rejected despite architecturally ignored payload");
    rejects(
        [](Fixture &f) {
            put(f.root, 7 * 8, 0x200000000000c001ULL);
        },
        "extra present leaf");
    rejects(
        [](Fixture &f) {
            put(f.dte, 0x10 * 32, 0x6000000000007203ULL);
        },
        "forged root pointer");
    rejects(
        [](Fixture &f) {
            put(f.root, 3 * 8, 0x2000000000005001ULL);
        },
        "leaf points into root");
    rejects(
        [](Fixture &f) {
            for (std::size_t byte = 0; byte != 8; ++byte) {
                const auto value = f.dte[0x10 * 32 + byte];
                f.dte[0x10 * 32 + byte] = f.dte[0x10 * 32 + 7 - byte];
                f.dte[0x10 * 32 + 7 - byte] = value;
                if (byte == 3)
                    break;
            }
        },
        "big-endian encoding is not silently accepted");

    // Every single-bit deviation from the known-answer snapshot must fail.
    // This includes all forbidden/reserved/ignored bits, PR/V/TV, permissions,
    // every domain bit, all encoded addresses, and every otherwise unused slot.
    Fixture fixture;
    for (std::size_t byte = 0; byte != fixture.dte.size(); ++byte) {
        for (unsigned bit = 0; bit != 8; ++bit) {
            fixture.dte[byte] ^= std::byte(1U << bit);
            check(!independent::validate(fixture.input), "DTE single-bit mutation rejected");
            fixture.dte[byte] ^= std::byte(1U << bit);
        }
    }
    for (std::size_t byte = 0; byte != fixture.root.size(); ++byte) {
        for (unsigned bit = 0; bit != 8; ++bit) {
            fixture.root[byte] ^= std::byte(1U << bit);
            check(!independent::validate(fixture.input), "root single-bit mutation rejected");
            fixture.root[byte] ^= std::byte(1U << bit);
        }
    }
    check(independent::validate(fixture.input), "restored snapshot validates");
}

void unaligned_host_storage() {
    Fixture fixture;
    std::array<std::byte, 8193> dte{};
    std::array<std::byte, 4097> root{};
    for (std::size_t byte = 0; byte != fixture.dte.size(); ++byte)
        dte[byte + 1] = fixture.dte[byte];
    for (std::size_t byte = 0; byte != fixture.root.size(); ++byte)
        root[byte + 1] = fixture.root[byte];
    fixture.input.dte = std::span<const std::byte>{dte}.subspan(1);
    fixture.input.root = std::span<const std::byte>{root}.subspan(1);
    check(independent::validate(fixture.input), "copied bytes need no host alignment");
    check(independent::permits(fixture.input, 0x10, 0x4001, 2, true), "unaligned host read works");
    fixture.input.dte = dte;
    check(!independent::validate(fixture.input), "oversized DTE span rejected");
    fixture.input.dte = fixture.dte;
    fixture.input.root = root;
    check(!independent::validate(fixture.input), "oversized root span rejected");
}

} // namespace

int main() {
    known_answers();
    description_mutations();
    physical_boundaries();
    byte_mutations();
    unaligned_host_storage();
    std::printf("Independent AMD 3.10 decoder: %zu checks, %zu failures\n", checks, failures);
    return failures == 0 ? 0 : 1;
}
} // namespace kernel_dormant_decoder
