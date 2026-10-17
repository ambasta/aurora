#pragma once
#include "program-note.hpp"
#include <algorithm>

namespace aurora::program {
// Retention, grant authentication and one-shot publication only. Aurora owns the
// four-record store, names, revision checks and atomic replacement policy.
class Files final {
public:
    using Value = std::array<std::byte, 272>;
    using Selection = std::array<std::byte, 88>;
    using UpdateInput = std::array<std::byte, 344>;
    using Update = std::array<std::byte, 520>;
    using ReplaceInput = std::array<std::byte, 432>;
    using Mutation = std::array<std::byte, 352>;

private:
    enum class State {
        idle,
        selected,
        bound,
        read_bound,
        completed,
        retired,
        publishing
    };
    Value saved_{};
    Selection selection_{};
    Note::Value projection_{};
    user::DomainHandle client_{}, service_{};
    const user::DomainRegistry *registry_{};
    const ipc::Mailbox *mailbox_{};
    std::uint64_t generation_{};
    bool writable_{};
    State state_ = State::idle;
    Stream *completed_stream_{};
    std::uint64_t stream_run_{};

    static auto word(std::span<const std::byte> bytes, std::size_t offset) -> std::uint64_t {
        std::uint64_t value = 0;
        for (unsigned i = 0; i < 8; ++i)
            value |= std::uint64_t(std::to_integer<unsigned char>(bytes[offset + i])) << (8 * i);
        return value;
    }
    static constexpr auto put(std::span<std::byte> bytes, std::size_t offset, std::uint64_t value) -> void {
        for (unsigned i = 0; i < 8; ++i)
            bytes[offset + i] = std::byte(value >> (8 * i));
    }
    auto matching(const user::DomainRegistry &registry,
                  const ipc::Mailbox &mailbox,
                  user::DomainHandle caller,
                  ipc::Endpoint endpoint) const -> bool {
        const auto actual = registry.index(caller), retained = registry.index(client_);
        const auto client = mailbox.endpoint(client_), service = mailbox.endpoint(service_);
        return actual && retained && *actual == *retained && client && service && endpoint.slot() == 0 &&
               endpoint.generation() == generation_ && generation_ != 0 && client->slot() == 0 &&
               client->generation() == generation_ && service->slot() == 1 && service->generation() == generation_;
    }

    auto bind_participants(const user::DomainRegistry &registry,
                           const ipc::Mailbox &mailbox,
                           user::DomainHandle client,
                           user::DomainHandle service,
                           State next) -> bool {
        const auto a = mailbox.endpoint(client), b = mailbox.endpoint(service);
        if (state_ != State::selected || !registry.ready(client) || !registry.ready(service) || !a || !b ||
            a->slot() != 0 || b->slot() != 1 || a->generation() == 0 || a->generation() != b->generation())
            return false;
        client_ = client;
        service_ = service;
        registry_ = &registry;
        mailbox_ = &mailbox;
        generation_ = a->generation();
        state_ = next;
        return true;
    }
    auto participants_retired(const user::DomainRegistry &registry, const ipc::Mailbox &mailbox) const -> bool {
        return registry_ == &registry && mailbox_ == &mailbox && !registry.index(client_) &&
               !registry.index(service_) && !mailbox.endpoint(client_) && !mailbox.endpoint(service_) &&
               mailbox.revoked();
    }

public:
    constexpr Files() {
        put(saved_, 264, 1);
    }
    Files(const Files &) = delete;
    auto operator=(const Files &) -> Files & = delete;
    [[nodiscard]] auto saved() const -> const Value & {
        return saved_;
    }
    [[nodiscard]] auto projection() const -> const Note::Value & {
        return projection_;
    }
    [[nodiscard]] auto selected() const -> bool {
        return state_ == State::selected;
    }
    [[nodiscard]] auto writable() const -> bool {
        return writable_;
    }
    [[nodiscard]] auto update(const Update &result) -> std::optional<std::uint64_t> {
        if (state_ != State::idle)
            return std::nullopt;
        const auto action = word(result, 352);
        if (action > 3 || word(result, 336) > 64 || word(result, 344) > 8)
            return std::nullopt;
        if (action != 1 && !std::equal(saved_.begin(), saved_.end(), result.begin()))
            return std::nullopt;
        if (action >= 2) {
            const auto length = word(result, 512);
            if (length != UINT64_MAX && length > 49)
                return std::nullopt;
            if (word(result, 432) == 0 || word(result, 440) != (action == 3 ? 1u : 0u))
                return std::nullopt;
        }
        std::copy_n(result.begin(), saved_.size(), saved_.begin());
        if (action >= 2) {
            std::copy_n(result.begin() + 360, selection_.size(), selection_.begin());
            std::copy_n(result.begin() + 448, projection_.size(), projection_.begin());
            writable_ = action == 3;
            state_ = State::selected;
        }
        return action;
    }
    [[nodiscard]] auto bind(const user::DomainRegistry &registry,
                            const ipc::Mailbox &mailbox,
                            user::DomainHandle client,
                            user::DomainHandle service,
                            Stream &stream) -> bool {
        if (!writable_ || !stream.awaiting_read(true) ||
            !bind_participants(registry, mailbox, client, service, State::bound))
            return false;
        completed_stream_ = &stream;
        stream_run_ = stream.run();
        return true;
    }
    // A read grant binds only this frozen selection's participant lifetime.
    // It promises neither a complete stream nor any particular number of bytes.
    [[nodiscard]] auto bind_read(const user::DomainRegistry &registry,
                                 const ipc::Mailbox &mailbox,
                                 user::DomainHandle client,
                                 user::DomainHandle service) -> bool {
        return !writable_ && bind_participants(registry, mailbox, client, service, State::read_bound);
    }
    [[nodiscard]] auto release_read(const user::DomainRegistry &registry, const ipc::Mailbox &mailbox) -> bool {
        if (state_ != State::read_bound || !participants_retired(registry, mailbox))
            return false;
        abort();
        return true;
    }
    // No copied Output is a save capability. Bind completion to this exact
    // private ledger, before revocation, without extracting any partial bytes.
    [[nodiscard]] auto complete(const user::DomainRegistry &registry,
                                const ipc::Mailbox &mailbox,
                                user::DomainHandle caller,
                                ipc::Endpoint endpoint,
                                Stream &stream) -> bool {
        if (registry_ != &registry || mailbox_ != &mailbox || state_ != State::bound || completed_stream_ != &stream ||
            stream_run_ != stream.run() || !writable_ || !matching(registry, mailbox, caller, endpoint) ||
            !registry.ready(client_) || !registry.ready(service_) || mailbox.state() != ipc::State::idle ||
            !mailbox.scrubbed() || !stream.ready_to_finish())
            return false;
        completed_stream_ = &stream;
        state_ = State::completed;
        return true;
    }
    [[nodiscard]] auto retire(const user::DomainRegistry &registry, const ipc::Mailbox &mailbox) -> bool {
        if (state_ != State::completed || !participants_retired(registry, mailbox))
            return false;
        client_ = {};
        service_ = {};
        generation_ = 0;
        projection_ = {};
        registry_ = nullptr;
        mailbox_ = nullptr;
        state_ = State::retired;
        return true;
    }
    [[nodiscard]] auto replacement(Stream &stream, ReplaceInput &input) -> bool {
        if (state_ != State::retired || completed_stream_ != &stream || stream_run_ != stream.run())
            return false;
        // Consume authority even when extraction fails. Nothing modifies saved_.
        completed_stream_ = nullptr;
        state_ = State::publishing;
        auto output = stream.finish();
        if (!output || output->missing() || output->length() > 49) {
            abort();
            return false;
        }
        ReplaceInput next{};
        std::copy(saved_.begin(), saved_.end(), next.begin());
        std::copy(selection_.begin(), selection_.end(), next.begin() + 272);
        for (std::size_t i = 0; i < output->length(); ++i)
            next[360 + i] = std::byte(*output->byte(i));
        put(next, 424, output->length());
        output->scrub();
        input = next;
        return true;
    }
    [[nodiscard]] auto publish(const Mutation &result) -> bool {
        if (state_ != State::publishing)
            return false;
        const auto event = word(result, 344);
        if (word(result, 336) > 64 || event > 8) {
            abort();
            return false;
        }
        // Only the real Aurora written event can change retained storage.
        if (event != 1) {
            abort();
            return false;
        }
        std::copy_n(result.begin(), saved_.size(), saved_.begin());
        abort();
        return true;
    }
    [[gnu::noinline]] auto abort() -> void {
        selection_ = {};
        projection_ = {};
        client_ = {};
        service_ = {};
        generation_ = 0;
        registry_ = nullptr;
        mailbox_ = nullptr;
        writable_ = false;
        completed_stream_ = nullptr;
        stream_run_ = 0;
        state_ = State::idle;
    }
    auto clear() -> void {
        abort();
        saved_ = {};
        put(saved_, 264, 1);
    }
};
} // namespace aurora::program
