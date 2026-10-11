#pragma once
#include <array>
#include <cstddef>
#include <cstdint>

namespace aurora::uefi {
// Offsets belong to the loader's existing allocation. This describes ownership;
// neither a valid layout nor a physical address grants a mapping by itself.
template <std::size_t Domains> class RuntimeLayoutProfile final {
    static_assert(Domains == 2 || Domains == 3);
    // The third pool follows the stack frames, not the first two pools: the
    // next contiguous address (0xb0000) already belongs to an RX image.
    static constexpr std::array<std::uint64_t, 3> table_offsets{0x90000, 0xa0000, 0xd0000};

public:
    static constexpr std::uint64_t page_size = 4096;
    static constexpr std::uint64_t arena_bytes = 0x100000;
    static constexpr std::uint64_t metadata_offset = 0x81000;
    static constexpr std::uint64_t gdt_offset = 0x82000;
    static constexpr std::uint64_t rsp0_guard = 0x83000;
    static constexpr std::uint64_t rsp0_bottom = 0x84000;
    static constexpr std::uint64_t rsp0_top = 0x88000;
    static constexpr std::uint64_t ist_guard = 0x88000;
    static constexpr std::uint64_t ist_bottom = 0x89000;
    static constexpr std::uint64_t ist_top = 0x8d000;
    static constexpr std::uint64_t tables_offset = 0x90000;
    static constexpr std::size_t table_pages = 16;
    static constexpr std::size_t domain_count = Domains;
    static constexpr std::uint64_t image_offset = 0xb0000;
    static constexpr std::size_t image_pages = Domains;
    static constexpr std::uint64_t stack_frames_offset = 0xc0000;
    static constexpr std::size_t stack_frame_count = 16;
    static constexpr std::size_t stack_pages = 4;
    static constexpr std::uint64_t user_code = 0x10000000000ULL;
    static constexpr std::uint64_t user_stack_bottom = 0x10000200000ULL;
    static constexpr std::uint64_t user_stack_top = user_stack_bottom + stack_pages * page_size;
    static constexpr std::uint64_t user_stack_guard = user_stack_bottom - page_size;
    static constexpr std::uint64_t lower_limit = 1ULL << 47;

    [[nodiscard]] static constexpr auto user_stack_begin(std::size_t domain) -> std::uint64_t {
        return domain < domain_count ? user_stack_bottom + domain * 0x200000 : lower_limit;
    }
    [[nodiscard]] static constexpr auto user_stack_end(std::size_t domain) -> std::uint64_t {
        return domain < domain_count ? user_stack_begin(domain) + stack_pages * page_size : lower_limit;
    }

    [[nodiscard]] static constexpr auto canonical_lower(std::uint64_t address) -> bool {
        return address < lower_limit;
    }
    // Half-open, nonempty page intervals. Subtraction checks avoid wrapped ends.
    [[nodiscard]] static constexpr auto valid_interval(std::uint64_t start, std::uint64_t bytes) -> bool {
        return canonical_lower(start) && start % page_size == 0 && bytes != 0 && bytes % page_size == 0 &&
               bytes <= lower_limit - start;
    }
    [[nodiscard]] static constexpr auto
    disjoint(std::uint64_t a, std::uint64_t a_bytes, std::uint64_t b, std::uint64_t b_bytes) -> bool {
        return valid_interval(a, a_bytes) && valid_interval(b, b_bytes) && (a + a_bytes <= b || b + b_bytes <= a);
    }
    // Invalid indices return the first byte outside the owned arena.
    [[nodiscard]] static constexpr auto table_offset(std::size_t domain) -> std::uint64_t {
        return domain < domain_count ? table_offsets[domain] : arena_bytes;
    }
    [[nodiscard]] static constexpr auto image_page(std::size_t index) -> std::uint64_t {
        return index < image_pages ? image_offset + index * page_size : arena_bytes;
    }
    [[nodiscard]] static constexpr auto stack_frame_offset(std::size_t index) -> std::uint64_t {
        return index < stack_frame_count ? stack_frames_offset + index * page_size : arena_bytes;
    }
    [[nodiscard]] static constexpr auto valid_probe(std::uint64_t size, std::uint64_t offset) -> bool {
        return offset == 0 || (size >= 8 && offset >= 2 && offset <= size - 8);
    }
    [[nodiscard]] static constexpr auto kernel_flags(std::uint64_t offset) -> std::uint64_t {
        if (offset >= arena_bytes || offset % page_size != 0)
            return 0;
        constexpr auto nx = 1ULL << 63;
        if (offset == metadata_offset)
            return 1 | nx;
        if (offset == gdt_offset || (offset >= rsp0_bottom && offset < rsp0_top) ||
            (offset >= ist_bottom && offset < ist_top) ||
            (offset >= stack_frames_offset && offset < stack_frames_offset + stack_frame_count * page_size))
            return 3 | nx;
        for (std::size_t domain = 0; domain < domain_count; ++domain)
            if (offset >= table_offset(domain) && offset - table_offset(domain) < table_pages * page_size)
                return 3 | nx;
        if (offset >= image_offset && offset < image_offset + image_pages * page_size)
            return 1;
        return 0;
    }
    [[nodiscard]] static constexpr auto valid(std::uint64_t arena) -> bool {
        if (arena < 0x100000 || !valid_interval(arena, arena_bytes) || arena > 0x100000000ULL - arena_bytes)
            return false;
        if (stack_pages == 0 || domain_count > stack_frame_count / stack_pages || image_pages != domain_count ||
            table_offset(0) != tables_offset)
            return false;
        // The first range reserves the complete preceding loader/kernel layout.
        std::array<std::array<std::uint64_t, 2>, 7 + domain_count> ranges{
            {{0, metadata_offset},
             {metadata_offset, page_size},
             {gdt_offset, page_size},
             {rsp0_bottom, rsp0_top - rsp0_bottom},
             {ist_bottom, ist_top - ist_bottom},
             {image_offset, image_pages * page_size},
             {stack_frames_offset, stack_frame_count * page_size}}};
        for (std::size_t domain = 0; domain < domain_count; ++domain)
            ranges[7 + domain] = {table_offset(domain), table_pages * page_size};
        constexpr std::array guards{rsp0_guard, ist_guard, ist_top};
        for (std::size_t i = 0; i < guards.size(); ++i) {
            if (!valid_interval(guards[i], page_size) || guards[i] >= arena_bytes ||
                page_size > arena_bytes - guards[i] || !valid_interval(arena + guards[i], page_size))
                return false;
            for (std::size_t j = 0; j < i; ++j)
                if (!disjoint(guards[i], page_size, guards[j], page_size))
                    return false;
        }
        for (std::size_t i = 0; i < ranges.size(); ++i) {
            const auto start = ranges[i][0], size = ranges[i][1];
            if (!valid_interval(start, size) || start >= arena_bytes || size > arena_bytes - start ||
                !valid_interval(arena + start, size))
                return false;
            for (std::size_t j = 0; j < i; ++j)
                if (!disjoint(start, size, ranges[j][0], ranges[j][1]))
                    return false;
            for (const auto guard : guards)
                if (!disjoint(start, size, guard, page_size))
                    return false;
        }
        for (std::size_t domain = 0; domain < domain_count; ++domain) {
            const auto begin = user_stack_begin(domain), end = user_stack_end(domain);
            if (begin < page_size || end < begin || end - begin != stack_pages * page_size ||
                !valid_interval(begin, end - begin) || !valid_interval(end, page_size))
                return false;
            const auto guard = begin - page_size;
            const auto span = stack_pages * page_size + 2 * page_size;
            if (!valid_interval(guard, page_size) || !valid_interval(guard, span) ||
                !disjoint(arena, arena_bytes, guard, span) ||
                !disjoint(user_code, image_pages * page_size, guard, span))
                return false;
            for (std::size_t other = 0; other < domain; ++other)
                if (!disjoint(guard, span, user_stack_begin(other) - page_size, span))
                    return false;
        }
        return rsp0_guard + page_size == rsp0_bottom && rsp0_top == ist_guard && ist_guard + page_size == ist_bottom &&
               valid_interval(user_code, image_pages * page_size) &&
               valid_interval(user_stack_bottom, user_stack_top - user_stack_bottom) &&
               valid_interval(user_stack_guard, page_size) && valid_interval(user_stack_top, page_size) &&
               disjoint(user_code,
                        image_pages * page_size,
                        user_stack_guard,
                        user_stack_top - user_stack_guard + page_size) &&
               disjoint(arena, arena_bytes, user_code, image_pages * page_size) &&
               disjoint(arena, arena_bytes, user_stack_guard, user_stack_top - user_stack_guard + page_size);
    }
};
#if defined(AURORA_UEFI_DISPATCH)
using RuntimeLayout = RuntimeLayoutProfile<3>;
#else
using RuntimeLayout = RuntimeLayoutProfile<2>;
#endif
static_assert(RuntimeLayoutProfile<2>::valid(0x100000));
static_assert(RuntimeLayoutProfile<3>::valid(0x100000));
static_assert(RuntimeLayout::valid(0x100000));
} // namespace aurora::uefi
