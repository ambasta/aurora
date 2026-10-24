#pragma once
#include <array>
#include <cstddef>
#include <cstdint>

namespace aurora::terminal {
// Copied text cells of the bytes a Console session actually wrote. This is data
// only: it grants no Console, display, mapping or input authority. CR returns to
// column zero, LF advances a row (scrolling at the last row), BS moves left
// within the row and a 96th printable byte wraps. Every other byte occupies one
// cell; the Aurora painter draws non-printable bytes as its fallback glyph.
// A cell is dirty when its byte or cursor state changed since it was painted.
class Grid final {
public:
    static constexpr unsigned columns = 80, rows = 24, cells = columns * rows;
    static constexpr std::uint64_t cursor_glyph = 256;

private:
    std::array<std::uint8_t, cells> text_{};
    std::array<std::uint8_t, (cells + 7) / 8> dirty_{};
    unsigned row_{}, column_{}, painted_cursor_{cells};

    auto mark(unsigned index) -> void {
        dirty_[index / 8] = static_cast<std::uint8_t>(dirty_[index / 8] | (1U << (index % 8)));
    }
    auto store(unsigned index, std::uint8_t byte) -> void {
        if (text_[index] != byte) {
            text_[index] = byte;
            mark(index);
        }
    }
    auto scroll() -> void {
        for (unsigned index = 0; index < cells - columns; ++index)
            store(index, text_[index + columns]);
        for (unsigned index = cells - columns; index < cells; ++index)
            store(index, ' ');
    }
    auto next_row() -> void {
        if (row_ + 1 == rows)
            scroll();
        else
            ++row_;
    }

public:
    constexpr Grid() {
        text_.fill(' ');
        dirty_.fill(0xff);
    }
    auto apply(std::uint8_t byte) -> void {
        if (byte == '\r') {
            column_ = 0;
        } else if (byte == '\n') {
            next_row();
        } else if (byte == '\b') {
            if (column_ != 0)
                --column_;
        } else {
            if (column_ == columns) {
                column_ = 0;
                next_row();
            }
            store(row_ * columns + column_, byte);
            ++column_;
        }
    }
    // The cursor occupies the next write position; after a full row it rests
    // on the last cell until the following byte wraps.
    [[nodiscard]] auto cursor() const -> unsigned {
        return row_ * columns + (column_ == columns ? columns - 1 : column_);
    }
    [[nodiscard]] auto any_dirty() const -> bool {
        for (const auto bits : dirty_)
            if (bits)
                return true;
        return cursor() != painted_cursor_;
    }
    // Start one paint pass: a moved cursor dirties the cell it leaves and the
    // cell it enters. Cells are then painted and committed in any order.
    auto prepare() -> void {
        if (cursor() == painted_cursor_)
            return;
        if (painted_cursor_ < cells)
            mark(painted_cursor_);
        mark(cursor());
        painted_cursor_ = cursor();
    }
    [[nodiscard]] auto dirty(unsigned index) const -> bool {
        return index < cells && ((dirty_[index / 8] >> (index % 8)) & 1U) != 0;
    }
    [[nodiscard]] auto glyph(unsigned index) const -> std::uint64_t {
        return index < cells ? text_[index] | (index == cursor() ? cursor_glyph : 0) : 0;
    }
    [[nodiscard]] auto byte(unsigned index) const -> std::uint8_t {
        return index < cells ? text_[index] : 0;
    }
    auto commit(unsigned index) -> void {
        if (index < cells)
            dirty_[index / 8] = static_cast<std::uint8_t>(dirty_[index / 8] & ~(1U << (index % 8)));
    }
};
} // namespace aurora::terminal
