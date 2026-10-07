#include "amd310-event-completion-oracle.hpp"
#include "amd310-translation-oracle.hpp"

#include <algorithm>
#include <array>
#include <cstdio>
#include <limits>

namespace {
using namespace amd310_event_oracle;
std::size_t checks = 0;
std::size_t failures = 0;

void check(bool value, const char *description) {
    ++checks;
    if (!value) {
        ++failures;
        std::fprintf(stderr, "FAIL: %s\n", description);
    }
}
using Bytes = std::array<std::byte, 16>;
auto golden_fault() -> Bytes {
    // Code 2, RID=1234h, Domain=abcdh, PR/PE/RW=1, RZ/I/TR/GN=0.
    return {std::byte{0x34}, std::byte{0x12}, std::byte{0},    std::byte{0},
            std::byte{0xcd}, std::byte{0xab}, std::byte{0x70}, std::byte{0x20},
            std::byte{0xef}, std::byte{0xcd}, std::byte{0xab}, std::byte{0x89},
            std::byte{0x67}, std::byte{0x45}, std::byte{0x23}, std::byte{0x01}};
}
auto golden_command_error(bool hardware = false) -> Bytes {
    return {std::byte{0},    std::byte{0},    std::byte{0},    std::byte{0},
            std::byte{0},    std::byte{0},    std::byte{0},    hardware ? std::byte{0x64} : std::byte{0x50},
            std::byte{0xf0}, std::byte{0xde}, std::byte{0xbc}, std::byte{0x9a},
            std::byte{0x78}, std::byte{0x56}, std::byte{0x34}, std::byte{0x12}};
}
void unsupported(const EventResult &result, UnsupportedCause cause, const char *description) {
    const auto *value = std::get_if<Unsupported>(&result);
    check(value && value->cause == cause, description);
}
void raw_events() {
    auto bytes = golden_fault();
    auto result = decode_event(bytes);
    const auto *fault = std::get_if<RawIoPageFault>(&result);
    check(fault && fault->requester == 0x1234 && fault->domain == 0xabcd &&
              fault->address == 0x0123456789abcdefULL && fault->present && fault->permission_denied && fault->write &&
              !fault->reserved_bit && !fault->interrupt && !fault->translation_request && !fault->guest,
          "literal ordinary fault fields");
    FaultExpectation expected{0x1234, 0xabcd, 0x0123456789abcdefULL, true, true, true, {}};
    check(fault && matches_fault(*fault, expected), "defined fault fields match");
    expected.domain = 0;
    check(!fault || !matches_fault(*fault, expected), "DomainID mismatch rejected");
    bytes[6] = std::byte{0xe0}; // PR=0; every PR-dependent raw payload flag is set.
    result = decode_event(bytes);
    fault = std::get_if<RawIoPageFault>(&result);
    expected = {0x1234, 0xabcd, 0x0123456789abcdefULL, false, {}, {}, {}};
    check(fault && !fault->present && fault->permission_denied && fault->write && fault->reserved_bit &&
              matches_fault(*fault, expected),
          "unknown fault fields ignore raw payload");
    expected.present = {}; // For example, no valid DTE/known PR at all.
    check(fault && matches_fault(*fault, expected), "unclaimed PR stays unknown");
    bytes[6] = std::byte{0x90}; // PR=1 RZ=1, no write or denied permission.
    result = decode_event(bytes);
    fault = std::get_if<RawIoPageFault>(&result);
    expected = {0x1234, 0xabcd, 0x0123456789abcdefULL, true, false, false, true};
    check(fault && matches_fault(*fault, expected), "defined present read RZ fields");
    expected.write = true;
    check(!fault || !matches_fault(*fault, expected), "defined write mismatch rejected");
    expected.write = false;
    expected.reserved_bit = false;
    check(!fault || !matches_fault(*fault, expected), "defined RZ mismatch rejected");
    for (unsigned bit : {16U, 17U, 18U, 19U, 24U, 25U, 26U, 27U}) {
        bytes = golden_fault();
        bytes[4 + bit / 8] |= std::byte{static_cast<unsigned char>(1U << (bit % 8))};
        unsupported(decode_event(bytes), UnsupportedCause::event_profile, "nonordinary fault profile unsupported");
    }
    for (unsigned bit = 16; bit != 32; ++bit) {
        bytes = golden_fault();
        bytes[bit / 8] |= std::byte{static_cast<unsigned char>(1U << (bit % 8))};
        unsupported(decode_event(bytes),
                    UnsupportedCause::event_profile,
                    "PASID virtualized reserved profile unsupported");
    }
    for (unsigned code = 0; code != 16; ++code) {
        if (code == 2 || code == 5 || code == 6) {
            continue;
        }
        bytes = {};
        bytes[7] = std::byte{static_cast<unsigned char>(code << 4)};
        unsupported(decode_event(bytes), UnsupportedCause::event_code, "other event code unsupported");
    }
    for (std::size_t size = 0; size != 16; ++size) {
        unsupported(decode_event(std::span<const std::byte>{bytes}.first(size)),
                    UnsupportedCause::input_size,
                    "truncated event input unsupported");
    }
    std::array<std::byte, 17> shifted{};
    bytes = golden_fault();
    std::copy(bytes.begin(), bytes.end(), shifted.begin() + 1);
    unsupported(decode_event(shifted), UnsupportedCause::input_size, "oversize single event unsupported");
    result = decode_event(std::span<const std::byte>{shifted}.subspan(1));
    fault = std::get_if<RawIoPageFault>(&result);
    check(fault && fault->domain == 0xabcd, "unaligned host copy decoded");
    for (const bool hardware : {false, true}) {
        result = decode_event(golden_command_error(hardware));
        const auto *error = std::get_if<CommandError>(&result);
        check(error && error->raw_address == 0x123456789abcdef0ULL &&
                  error->kind == (hardware ? CommandErrorKind::hardware : CommandErrorKind::illegal) &&
                  error->hardware_type == (hardware ? std::optional<std::uint8_t>{2} : std::nullopt),
              "command error kind and raw address");
        bytes = golden_command_error(hardware);
        bytes[8] |= std::byte{1};
        unsupported(decode_event(bytes), UnsupportedCause::event_profile, "command reserved address bits unsupported");
    }
    for (unsigned type = 1; type != 4; ++type) {
        bytes = golden_command_error(true);
        bytes[7] = std::byte{static_cast<unsigned char>(0x60 | (type << 1))};
        result = decode_event(bytes);
        const auto *error = std::get_if<CommandError>(&result);
        check(error && error->hardware_type == type, "non-SNP command hardware types decoded");
    }
    bytes = golden_command_error(true);
    bytes[7] = std::byte{0x60};
    unsupported(decode_event(bytes), UnsupportedCause::event_profile, "SNP hardware type unsupported");
}

void translation_cross_check() {
    std::array<std::byte, 8192> table{};
    std::array<std::byte, 4096> root{};
    table[512] = std::byte{3};
    table[513] = std::byte{0x52};
    table[519] = std::byte{0x60};
    table[520] = std::byte{0x34};
    table[521] = std::byte{0x12};
    const amd310_oracle::Input input{table, root, 0x5000, 1};
    const auto translated = amd310_oracle::translate(input, {16, 0x3123, amd310_oracle::Access::write});
    const auto *semantic = std::get_if<amd310_oracle::IoPageFault>(&translated);
    const Bytes bytes{std::byte{0x10}, std::byte{0},    std::byte{0},    std::byte{0},
                      std::byte{0x34}, std::byte{0x12}, std::byte{0xe0}, std::byte{0x20},
                      std::byte{0x23}, std::byte{0x31}, std::byte{0},    std::byte{0},
                      std::byte{0},    std::byte{0},    std::byte{0},    std::byte{0}};
    const auto decoded = decode_event(bytes);
    const auto *raw = std::get_if<RawIoPageFault>(&decoded);
    check(semantic && raw && matches_fault(*raw,
                                          {semantic->requester,
                                           semantic->domain,
                                           semantic->address,
                                           semantic->present,
                                           semantic->permission_denied,
                                           semantic->write,
                                           semantic->reserved_bit}),
          "independent translation optional fields match copied event");
}

void status_and_ring() {
    for (unsigned bit = 0; bit != 5; ++bit) {
        const Status status{std::uint64_t{1} << bit};
        check(status.overflow() == (bit == 0) && status.event_pending() == (bit == 1) &&
                  status.completion_pending() == (bit == 2) && status.logging() == (bit == 3) &&
                  status.fetching() == (bit == 4),
              "status bits have independent meanings");
    }
    for (std::uint8_t length = 8; length != 16; ++length) {
        const auto bytes = std::uint32_t{16} << length;
        auto result = append_event({length, 0, 0}, {8});
        const auto *effect = std::get_if<Append>(&result);
        check(effect && effect->written && effect->ring.head == 0 && effect->ring.tail == 16 &&
                  effect->status.raw == 10 && !effect->status.completion_pending(),
              "ordinary event uses bit1 and advances only tail");
        result = append_event({length, 16, bytes - 16}, {8 | 4 | 16});
        effect = std::get_if<Append>(&result);
        check(effect && effect->written && effect->ring.head == 16 && effect->ring.tail == 0 &&
                  effect->status.raw == 30,
              "tail wraps and stale completion is preserved");
        result = append_event({length, 0, bytes - 32}, {8});
        effect = std::get_if<Append>(&result);
        check(effect && effect->written && effect->ring.tail == bytes - 16 && !effect->status.overflow(),
              "last usable slot remains available");
        result = append_event({length, 0, bytes - 16}, {8});
        effect = std::get_if<Append>(&result);
        check(effect && !effect->written && effect->ring.head == 0 && effect->ring.tail == bytes - 16 &&
                  effect->status.raw == 9,
              "one unused slot detects full without tail advance");
        result = append_event({length, 32, 16}, {8 | 4});
        effect = std::get_if<Append>(&result);
        check(effect && !effect->written && effect->ring.tail == 16 && effect->status.raw == 13,
              "full works away from zero and preserves stale completion");
        for (const auto status : {0ULL, 1ULL, 9ULL, 15ULL}) {
            result = append_event({length, 0, 0}, {status});
            effect = std::get_if<Append>(&result);
            check(effect && !effect->written && effect->ring.tail == 0 && effect->status.raw == (status | 1),
                  "disabled or overflowed logging discards events");
        }
        for (const EventRing ring : {EventRing{length, 1, 0},
                                     EventRing{length, 0, 1},
                                     EventRing{length, bytes, 0},
                                     EventRing{length, 0, bytes}}) {
            check(std::holds_alternative<Unsupported>(append_event(ring, {8})), "invalid ring offsets unsupported");
        }
    }
    check(std::holds_alternative<Unsupported>(append_event({8, 0, 0}, {32})),
          "unmodeled status profile unsupported");
    for (const auto length : {0, 7, 16, 255}) {
        check(std::holds_alternative<Unsupported>(append_event({static_cast<std::uint8_t>(length), 0, 0}, {8})),
              "invalid EventLen unsupported");
    }
}

void fetch_all(Batch &batch) {
    check(batch.fetch(Command::device_table) == Step::advanced && batch.fetch(Command::pages) == Step::advanced &&
              batch.fetch(Command::completion_wait) == Step::advanced && batch.fetched() == 3,
          "three commands fetch in order");
}
void cache_facts(Batch &batch) {
    check(batch.assume(Fact::device_cache_invalidated) == Step::advanced &&
              batch.assume(Fact::page_cache_invalidated) == Step::advanced,
          "separate device and page cache facts accepted");
}
void batches() {
    for (const bool store : {false, true}) {
        for (const bool interrupt : {false, true}) {
            Batch batch({store, interrupt, 0x8000, 0x0123456789abcdefULL}, {8});
            check(batch.fetch(Command::pages) == Step::unsupported && batch.fetched() == 0,
                  "wrong fixed batch order rejected");
            fetch_all(batch);
            check(!batch.completed() && !batch.store() && batch.finish_wait() == Step::blocked &&
                      !batch.status().completion_pending(),
                  "fetching wait never completes invalidation");
            check(batch.assume(Fact::page_cache_invalidated) == Step::blocked,
                  "page invalidation waits for prior DTE cache invalidation");
            check(batch.assume(Fact::reads_drained) == Step::blocked &&
                      batch.assume(Fact::writes_drained) == Step::blocked,
                  "drain facts belong to invalidated batch");
            check(batch.assume(Fact::device_cache_invalidated) == Step::advanced, "DTE cache invalidation accepted");
            check(batch.assume(Fact::reads_drained) == Step::blocked && batch.finish_wait() == Step::blocked,
                  "DTE invalidation does not invalidate pages");
            check(batch.assume(Fact::page_cache_invalidated) == Step::advanced, "page cache invalidation accepted");
            check(batch.assume(Fact::reads_drained) == Step::advanced && batch.finish_wait() == Step::blocked &&
                      !batch.store(),
                  "write drain required before completion");
            check(batch.assume(Fact::writes_drained) == Step::advanced && batch.finish_wait() == Step::advanced &&
                      batch.completed(),
                  "all modeled prerequisites permit completion");
            const auto expected_store = store ? std::optional<Store>{{0x8000, 0x0123456789abcdefULL}} : std::nullopt;
            check(batch.store() == expected_store, "completion store requires s");
            check(batch.status().completion_pending() == interrupt && !batch.status().event_pending(),
                  "completion interrupt requires i");
            check(batch.finish_wait() == Step::blocked && batch.fetch(Command::device_table) == Step::blocked &&
                      batch.assume(Fact::writes_drained) == Step::blocked,
                  "batch cannot be reused or replayed");
        }
    }
    Batch unsupported_status({false, false, 0, 0}, {32});
    check(unsupported_status.fetch(Command::device_table) == Step::unsupported, "unmodeled batch status unsupported");
    Batch reads({true, true, 0x8000, 77});
    fetch_all(reads);
    cache_facts(reads);
    check(reads.assume(Fact::writes_drained) == Step::advanced && reads.finish_wait() == Step::blocked &&
              !reads.completed() && !reads.store(),
          "read drain required before completion");
    check(reads.assume(Fact::reads_drained) == Step::advanced && reads.finish_wait() == Step::advanced,
          "read and write fact order independent");
    Batch unfetched({true, true, 0x8000, 1});
    check(unfetched.assume(Fact::device_cache_invalidated) == Step::blocked, "unfetched command cannot execute");
    check(unfetched.fetch(Command::device_table) == Step::advanced && unfetched.fetch(Command::pages) == Step::advanced,
          "first two fetch without wait");
    cache_facts(unfetched);
    check(unfetched.assume(Fact::reads_drained) == Step::advanced &&
              unfetched.assume(Fact::writes_drained) == Step::advanced && unfetched.finish_wait() == Step::blocked,
          "all drain facts without fetched wait cannot signal completion");
    for (const auto address : {1ULL, 0x8004ULL, 0x0010000000000000ULL, 0xfee00000ULL, 0xfd00000000ULL}) {
        Batch bad({true, true, address, 0});
        check(bad.fetch(Command::device_table) == Step::unsupported && bad.finish_wait() == Step::unsupported,
              "unsupported completion store target");
        Batch unused({false, false, address, 0});
        check(unused.fetch(Command::device_table) == Step::advanced, "s zero ignores unused store target");
    }
}

void faults_are_not_completion() {
    const auto decoded = decode_event(golden_fault());
    const auto *fault = std::get_if<RawIoPageFault>(&decoded);
    check(fault != nullptr, "fault fixture decodes before batch interleave");
    if (!fault) {
        return;
    }
    for (const auto initial : {8ULL, 12ULL}) {
        Batch batch({true, true, 0x8000, 55}, {initial});
        fetch_all(batch);
        const auto report = batch.report_event(Event{*fault}, {8, 0, 0});
        const auto *effect = std::get_if<Append>(&report);
        check(effect && effect->written && batch.status().event_pending() &&
                  batch.status().completion_pending() == ((initial & 4) != 0) && !batch.completed() && !batch.store() &&
                  batch.finish_wait() == Step::blocked,
              "ordinary fault and stale status never finish pending batch");
        cache_facts(batch);
        check(batch.assume(Fact::reads_drained) == Step::advanced &&
                  batch.assume(Fact::writes_drained) == Step::advanced &&
                  batch.finish_wait() == Step::advanced && batch.completed(),
              "ordinary fault does not stop modeled commands");
    }
    for (const bool hardware : {false, true}) {
        const auto event = decode_event(golden_command_error(hardware));
        const auto *error = std::get_if<CommandError>(&event);
        check(error != nullptr, "command error fixture decodes");
        if (!error) {
            continue;
        }
        for (const Status initial : {Status{8}, Status{9}, Status{0}}) {
            Batch batch({true, true, 0x8000, 99}, initial);
            check(batch.fetch(Command::device_table) == Step::advanced, "error follows first command fetch");
            const auto report = batch.report_event(Event{*error}, {8, 0, 0});
            check(std::holds_alternative<Append>(report) && !batch.status().fetching() &&
                      batch.fetch(Command::pages) == Step::blocked && batch.finish_wait() == Step::blocked &&
                      !batch.completed() && !batch.store() && !batch.status().completion_pending(),
                  "command error halts fetch even when logging is lost");
            const auto subsequent = batch.report_event(Event{*fault}, {8, 0, 0});
            check(std::holds_alternative<Append>(subsequent), "event reporting remains possible after command stop");
        }
        Batch outside({true, true, 0x8000, 1});
        fetch_all(outside);
        check(std::holds_alternative<Unsupported>(outside.report_event(Event{*error}, {8, 0, 0})),
              "error after wait fetch is outside bounded model");
    }
}
} // namespace

int main() {
    raw_events();
    translation_cross_check();
    status_and_ring();
    batches();
    faults_are_not_completion();
    std::printf("%s %zu independent AMD310 event/completion checks; no device operation\n",
                failures ? "FAIL" : "PASS",
                checks);
    return failures ? 1 : 0;
}
