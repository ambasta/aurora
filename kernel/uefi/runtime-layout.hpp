#pragma once
#include "../bootstrap-layout.hpp"
#include "image-page-policy.hpp"
#include <array>
#include <cstddef>
#include <cstdint>

namespace aurora::uefi {
// Offsets belong to the loader's existing allocation. This describes ownership;
// neither a valid layout nor a physical address grants a mapping by itself.
// Slots counts the installed image slots: one per domain, or a test image's bank
// whose boot-selected rows choose which slots act as the domains' images. Each
// slot spans SlotPages pages: the largest image by default, or one page for a
// bank of one-page images, which must still hold every image its policy admits.
template <std::size_t Domains, std::size_t Slots = Domains, std::size_t SlotPages = BootstrapLayout::max_code_pages>
class RuntimeLayoutProfile final : public BootstrapLayout {
    static_assert(Domains == 2 || Domains == 3);
    static_assert(Slots >= Domains && SlotPages != 0 && SlotPages <= max_code_pages);
    static_assert([] {
        for (std::size_t image = 0; image < Domains; ++image)
            if (ImagePagePolicy::pages(image) > SlotPages)
                return false;
        return true;
    }());
    // The third pool follows the stack frames, not the first two pools: the
    // next contiguous address (0xb0000) already belongs to an RX image.
    static constexpr std::array<std::uint64_t, 3> table_offsets{
        tables_offset, tables_offset + table_pages * page_size, third_tables_offset};

public:
    static constexpr std::size_t domain_count = Domains;
    static constexpr std::size_t image_count = Domains;
    static constexpr std::size_t image_slots = Slots;
    static constexpr std::uint64_t slot_bytes = SlotPages * page_size;

    [[nodiscard]] static constexpr auto user_stack_begin(std::size_t domain) -> std::uint64_t {
        return domain < domain_count ? user_stack_bottom + domain * user_stack_stride : lower_limit;
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
        return index < image_count ? image_offset + index * image_slot_bytes : arena_bytes;
    }
    [[nodiscard]] static constexpr auto slot_page(std::size_t slot) -> std::uint64_t {
        return slot < image_slots ? image_offset + slot * slot_bytes : arena_bytes;
    }
    [[nodiscard]] static constexpr auto code_begin(std::size_t image) -> std::uint64_t {
        return image < image_count ? user_code + image * code_stride : lower_limit;
    }
    [[nodiscard]] static constexpr auto code_end(std::size_t image) -> std::uint64_t {
        return image < image_count ? code_begin(image) + image_slot_bytes : lower_limit;
    }
    [[nodiscard]] static constexpr auto image_limit(std::size_t image) -> std::uint64_t {
        if (image >= image_count)
            return 0;
        return ImagePagePolicy::pages(image) * page_size;
    }
    [[nodiscard]] static constexpr auto code_pages(std::size_t image, std::uint64_t bytes) -> std::size_t {
        return bytes && bytes <= image_limit(image) ? (bytes - 1) / page_size + 1 : 0;
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
        if (offset >= image_offset && offset < image_offset + image_slots * slot_bytes)
            return 1;
        return 0;
    }
    [[nodiscard]] static constexpr auto valid(std::uint64_t arena) -> bool {
        if (arena < 0x100000 || !valid_interval(arena, arena_bytes) || arena > 0x100000000ULL - arena_bytes)
            return false;
        if (stack_pages == 0 || domain_count > stack_frame_count / stack_pages || image_count != domain_count ||
            table_offset(0) != tables_offset)
            return false;
        // The first range reserves the complete preceding loader/kernel layout.
        std::array<std::array<std::uint64_t, 2>, 7 + domain_count> ranges{
            {{0, metadata_offset},
             {metadata_offset, page_size},
             {gdt_offset, page_size},
             {rsp0_bottom, rsp0_top - rsp0_bottom},
             {ist_bottom, ist_top - ist_bottom},
             {image_offset, image_slots * slot_bytes},
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
                !disjoint(user_code, image_count * code_stride, guard, span))
                return false;
            for (std::size_t other = 0; other < domain; ++other)
                if (!disjoint(guard, span, user_stack_begin(other) - page_size, span))
                    return false;
        }
        return rsp0_guard + page_size == rsp0_bottom && rsp0_top == ist_guard && ist_guard + page_size == ist_bottom &&
               valid_interval(user_code, image_count * code_stride) &&
               valid_interval(user_stack_bottom, user_stack_top - user_stack_bottom) &&
               valid_interval(user_stack_guard, page_size) && valid_interval(user_stack_top, page_size) &&
               disjoint(user_code,
                        image_count * code_stride,
                        user_stack_guard,
                        user_stack_top - user_stack_guard + page_size) &&
               disjoint(arena, arena_bytes, user_code, image_count * code_stride) &&
               disjoint(arena, arena_bytes, user_stack_guard, user_stack_top - user_stack_guard + page_size);
    }
};
#if defined(AURORA_UEFI_DISPATCH) && defined(AURORA_RUNTIME_IMAGE_BANK)
// The service fixture's bank holds one-page images, packed one page apart.
using RuntimeLayout = RuntimeLayoutProfile<3, AURORA_RUNTIME_IMAGE_BANK, 1>;
#elif defined(AURORA_UEFI_DISPATCH)
using RuntimeLayout = RuntimeLayoutProfile<3>;
#elif defined(AURORA_RUNTIME_IMAGE_BANK)
using RuntimeLayout = RuntimeLayoutProfile<2, AURORA_RUNTIME_IMAGE_BANK>;
#else
using RuntimeLayout = RuntimeLayoutProfile<2>;
#endif
static_assert(RuntimeLayoutProfile<2>::valid(0x100000));
static_assert(RuntimeLayoutProfile<3>::valid(0x100000));
static_assert(RuntimeLayout::valid(0x100000));
} // namespace aurora::uefi
