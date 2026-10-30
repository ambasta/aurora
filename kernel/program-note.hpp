#pragma once
#include "ipc-policy.hpp"
#include "program-stream.hpp"
#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <span>

namespace aurora::program {
// Native retention and authenticated publication only. Aurora owns all commands,
// replacement policy, missing/empty interpretation and the projected read bytes.
template <bool RetainNote> class NoteCommand final {
public:
    using Value = std::array<std::byte, 72>;
    using UpdateInput = std::array<std::byte, 144>;
    using Update = std::array<std::byte, 80>;
    static constexpr std::size_t record_bytes = 96;
    static constexpr std::size_t stack_reservation = 112;
    static constexpr std::size_t stream_record_bytes = 168;
    static constexpr std::size_t stream_stack_reservation = 176;

private:
    [[no_unique_address]] std::array<std::byte, RetainNote ? 72 : 0> saved_{};
    Value read_{}, suffix_{};
    std::uint64_t generation_{};
    static constexpr auto empty() -> Value {
        Value result{};
        for (std::size_t i = 64; i < 72; ++i)
            result[i] = std::byte{255};
        return result;
    }
    static constexpr auto word(std::span<const std::byte> bytes, std::size_t offset) -> std::uint64_t {
        std::uint64_t result = 0;
        for (unsigned i = 0; i < 8; ++i)
            result |= std::uint64_t(std::to_integer<unsigned char>(bytes[offset + i])) << (8 * i);
        return result;
    }
    static constexpr auto closed(std::span<const std::byte> value) -> bool {
        const auto size = word(value, 64);
        return size == UINT64_MAX || size <= 53;
    }

public:
    constexpr NoteCommand() {
        if constexpr (RetainNote)
            saved_ = empty();
    }
    NoteCommand(const NoteCommand &) = delete;
    auto operator=(const NoteCommand &) -> NoteCommand & = delete;
    [[nodiscard]] auto saved() const -> const Value &
        requires(RetainNote)
    {
        return saved_;
    }
    [[nodiscard]] auto select_projection(const Value &projection) -> bool
        requires(!RetainNote)
    {
        if (bound() || !closed(projection))
            return false;
        const auto length = word(projection, 64);
        for (std::size_t index = 0; index < 64; ++index) {
            const auto byte = std::to_integer<unsigned>(projection[index]);
            if (length != UINT64_MAX && index < length ? byte < 32 || byte > 126 : byte != 0)
                return false;
        }
        read_ = projection;
        return true;
    }
    [[nodiscard]] auto select(const Update &update) -> std::optional<std::uint64_t>
        requires(!RetainNote)
    {
        const auto action = word(update, 72), length = word(update, 64);
        if (action > 4 || (action == 3 ? length != UINT64_MAX : action != 0 && length == UINT64_MAX))
            return std::nullopt;
        Value projection{};
        std::copy_n(update.begin(), projection.size(), projection.begin());
        const bool valid = select_projection(projection);
        for (auto &byte : projection)
            *static_cast<volatile std::byte *>(&byte) = std::byte{0};
        if (!valid)
            return std::nullopt;
        if (action < 2)
            release();
        return action;
    }
    [[nodiscard]] auto projection() const -> const Value &
        requires(!RetainNote)
    {
        return read_;
    }
    [[nodiscard]] auto bound() const -> bool {
        return generation_ != 0;
    }
    [[nodiscard]] auto commit(const Update &update) -> std::optional<std::uint64_t>
        requires(RetainNote)
    {
        const auto event = word(update, 72);
        if (bound() || event > 4 || !closed(update))
            return std::nullopt;
        if (event != 1) {
            for (std::size_t i = 0; i < saved_.size(); ++i)
                if (update[i] != saved_[i])
                    return std::nullopt;
        }
        for (std::size_t i = 0; i < saved_.size(); ++i)
            saved_[i] = update[i];
        return event;
    }
    // Only copied data preparation. The supervisor separately requires a fully
    // retired command before calling Aurora and committing a replacement.
    [[nodiscard]] auto begin_upper(const Value &projection, Stream &stream) const -> bool {
        const auto length = word(projection, 64);
        if (bound() || length > 53)
            return false;
        StreamBytes input{};
        for (std::size_t i = 0; i < length; ++i)
            input[i] = std::to_integer<std::uint8_t>(projection[i]);
        return stream.begin(input, length);
    }
    [[nodiscard]] auto replacement(const Output &output, UpdateInput &input) const -> bool
        requires(RetainNote)
    {
        if (bound() || output.missing() || output.length() > 53)
            return false;
        input = {};
        for (std::size_t i = 0; i < saved_.size(); ++i)
            input[i] = saved_[i];
        constexpr char prefix[] = "write note ";
        for (std::size_t i = 0; i < sizeof(prefix) - 1; ++i)
            input[72 + i] = std::byte(prefix[i]);
        for (std::size_t i = 0; i < output.length(); ++i) {
            const auto byte = output.byte(i);
            if (!byte)
                return false;
            input[83 + i] = std::byte(*byte);
        }
        for (unsigned i = 0; i < 8; ++i)
            input[136 + i] = std::byte((output.length() + 11) >> (8 * i));
        return true;
    }
    [[nodiscard]] auto bind(const Value &projection, ipc::Endpoint service, const Value &suffix = {}) -> bool {
        if (bound() || !closed(projection) || word(suffix, 64) > 49 || service.slot() != 1 || service.generation() == 0)
            return false;
        read_ = projection;
        suffix_ = suffix;
        generation_ = service.generation();
        return true;
    }
    [[nodiscard]] auto matches(ipc::Endpoint service) const -> bool {
        return bound() && service.slot() == 1 && service.generation() == generation_;
    }
    [[nodiscard]] auto stage(std::span<std::byte, record_bytes> output,
                             ipc::Endpoint service,
                             std::uint64_t phase,
                             ipc::Request request) const -> bool {
        if (!matches(service))
            return false;
        const std::array words{phase, request.first(), request.second()};
        for (std::size_t i = 0; i < words.size(); ++i) {
            for (unsigned j = 0; j < 8; ++j)
                output[i * 8 + j] = std::byte(words[i] >> (j * 8));
        }
        for (std::size_t i = 0; i < read_.size(); ++i)
            output[24 + i] = read_[i];
        return true;
    }
    [[nodiscard]] auto stage_stream(std::span<std::byte, stream_record_bytes> output,
                                    ipc::Endpoint service,
                                    std::uint64_t phase,
                                    ipc::Request request) const -> bool {
        if (!stage(output.first<record_bytes>(), service, phase, request))
            return false;
        std::copy(suffix_.begin(), suffix_.end(), output.begin() + record_bytes);
        return true;
    }
    auto release() -> void {
        generation_ = 0;
        volatile std::byte *suffix = suffix_.data();
        for (std::size_t i = 0; i < suffix_.size(); ++i)
            suffix[i] = std::byte{0};
        volatile std::byte *data = read_.data();
        for (std::size_t i = 0; i < read_.size(); ++i)
            data[i] = std::byte{0};
    }
    auto clear() -> void {
        release();
        if constexpr (RetainNote)
            saved_ = empty();
    }
};
using Note = NoteCommand<true>;
using ExternalNote = NoteCommand<false>;
} // namespace aurora::program
