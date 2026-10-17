#include "../kernel/uefi/snapshot.hpp"
#include "../kernel/uefi/handoff.hpp"

#include <array>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <span>
#include <sys/wait.h>
#include <unistd.h>

using U64 = std::uint64_t;
using namespace aurora;
extern "C" U64 aurora_user_main(U64, U64, U64);
extern "C" U64 snapshot_test_service(const void *);
extern "C" U64 snapshot_test_checksum(const void *);

namespace {
alignas(4096) std::array<std::byte, uefi::Handoff::arena_bytes> arena_storage;
U64 checks = 0;
constexpr U64 done = std::numeric_limits<U64>::max();
constexpr U64 cancelled = done - 1;
constexpr U64 failed = done - 2;

void require(bool good, const char *why) {
    if (!good) {
        std::fprintf(stderr, "FAIL snapshot: %s\n", why);
        std::exit(1);
    }
    ++checks;
}

class Fixture {
public:
    memory::PhysicalPages pool;
    ipc::SnapshotSlot slot;
    user::DomainRegistry registry;
    user::DomainHandle client;
    user::DomainHandle service;
    ipc::Mailbox mailbox;
    U64 transaction = 0;
    alignas(16) std::array<std::byte, 128> storage;

    Fixture() : mailbox(registry) {
        const auto arena = reinterpret_cast<U64>(arena_storage.data());
        require(pool.initialize(arena + uefi::Handoff::pool_offset, 16), "real independent producer pool");
        const auto a = registry.create();
        const auto b = registry.create();
        require(a && b, "real participant handles");
        client = *a;
        service = *b;
    }
    void produce() {
        require(uefi::prepare_snapshot(
                    reinterpret_cast<U64>(arena_storage.data()), pool, slot, uefi::SnapshotProducerCase::normal) ==
                    ipc::SnapshotPublication::ready,
                "real producer closes then publishes");
        require(pool.used() == 0 && slot.ready() && !slot.bound(), "no owner or endpoint published early");
    }
    void bind() {
        require(mailbox.bind(client, service) && slot.bind(*mailbox.endpoint(service)), "fresh endpoint binding");
    }
    void submit(U64 offset, U64 phase = 0) {
        const auto operation = aurora_user_main(phase, 0, offset);
        const auto ticket =
            mailbox.submit(client, ipc::Phase::request, *mailbox.endpoint(client), ipc::Request{operation, offset});
        require(ticket.has_value(), "real compiled client submit");
        transaction = *ticket;
    }
    ipc::SnapshotSlot::Record receive(U64 phase = 1) {
        const auto endpoint = *mailbox.endpoint(service);
        const auto request = mailbox.receive(service, ipc::Phase::service, endpoint, transaction);
        require(request.has_value(), "authenticated service receive");
        storage.fill(std::byte{0xa5});
        ipc::SnapshotSlot::Record record{storage.data() + 16, ipc::SnapshotSlot::record_bytes};
        require(slot.stage(record, endpoint, phase, *request), "bound exact copied record");
        for (std::size_t byte = 0; byte < 16; ++byte) {
            require(storage[byte] == std::byte{0xa5} && storage[112 + byte] == std::byte{0xa5}, "record canaries");
        }
        for (std::size_t byte = 88; byte < 96; ++byte) {
            require(record[byte] == std::byte{0}, "record padding");
        }
        return record;
    }
    U64 reply(U64 result, U64 offset, U64 phase = 2) {
        require(ipc::snapshot_reply_valid(result), "closed actual reply");
        require(mailbox.reply(service, ipc::Phase::service, *mailbox.endpoint(service), transaction, result),
                "real reply commit");
        require(!mailbox.cancel(ipc::Phase::inactive) &&
                    !mailbox.reply(service, ipc::Phase::service, *mailbox.endpoint(service), transaction, result),
                "reply first terminal wins, duplicate rejected");
        const auto completion = mailbox.consume(client, ipc::Phase::completion, *mailbox.endpoint(client), transaction);
        require(completion && completion->outcome() == ipc::Outcome::replied && completion->value() == result &&
                    mailbox.scrubbed(),
                "exact reply consumption and scrub");
        const auto next = aurora_user_main(phase, completion->value(), offset);
        require(mailbox.recycle(ipc::Phase::inactive), "consumed record recycling");
        return next;
    }
    void cancel() {
        const auto endpoint = *mailbox.endpoint(service);
        require(mailbox.cancel(ipc::Phase::inactive) && !mailbox.cancel(ipc::Phase::inactive) &&
                    !mailbox.reply(service, ipc::Phase::service, endpoint, transaction, 1),
                "cancel first terminal wins");
        const auto result = mailbox.consume(client, ipc::Phase::completion, *mailbox.endpoint(client), transaction);
        require(result && result->outcome() == ipc::Outcome::cancelled && result->value() == 0 && mailbox.scrubbed(),
                "typed cancelled completion");
        require(aurora_user_main(3, result->value(), 0) == cancelled, "real client consumes cancellation");
    }
    void restart() {
        const auto old = *mailbox.endpoint(service);
        const auto former = service;
        slot.clear();
        require(mailbox.revoke(ipc::Phase::inactive) && registry.destroy(service), "revocation and retirement");
        const auto fresh = registry.create();
        require(fresh && !registry.index(former), "new domain incarnation");
        service = *fresh;
        produce();
        bind();
        require(
            !slot.matches(old) &&
                !mailbox.submit(client, ipc::Phase::request, ipc::Endpoint{0, old.generation()}, ipc::Request{1, 0}),
            "stale grant cannot request or stage");
    }
    void read_all() {
        U64 offset = 0;
        for (unsigned iteration = 0; iteration < 65; ++iteration) {
            submit(offset);
            const auto record = receive();
            const auto before = storage;
            const auto result = snapshot_test_service(record.data());
            require(storage == before, "compiled service input record remains immutable");
            if (offset == 24) {
                require(result == 0xff01, "literal binary255");
            }
            if (offset == 53) {
                require(result == 1, "literal binary0");
            }
            if (offset == 64) {
                require(result == 2, "literal EOF");
            }
            offset = reply(result, offset);
            require(offset == (iteration == 64 ? done : iteration + 1), "compiled client alone chooses next offset");
        }
    }
};

// Independent bitwise Castagnoli oracle over the producer's known bytes.
void checksum_boundaries() {
    Fixture f;
    f.produce();
    f.bind();
    const auto endpoint = *f.mailbox.endpoint(f.service);
    ipc::SnapshotSlot::Record record{f.storage.data() + 16, ipc::SnapshotSlot::record_bytes};
    for (U64 offset = 0; offset <= 65; ++offset) {
        for (U64 count = 0; count <= 65; ++count) {
            require(f.slot.stage(record, endpoint, 1, ipc::Request{offset | (count << 8), 0}),
                    "checksum copied request");
            const auto before = f.storage;
            const auto actual = snapshot_test_checksum(record.data());
            U64 expected = 2;
            if (offset <= 64 && count <= 64 - offset) {
                std::uint32_t crc = 0xffffffff;
                for (U64 i = offset; i < offset + count; ++i) {
                    crc ^= static_cast<std::uint8_t>((i * 53 + 7) % 256);
                    for (unsigned bit = 0; bit < 8; ++bit)
                        crc = (crc >> 1) ^ ((crc & 1) ? 0x82f63b78 : 0);
                }
                expected = 1 | (U64(crc ^ 0xffffffff) << 8);
            }
            require(actual == expected && f.storage == before, "independent range CRC and immutable input");
            require(ipc::snapshot_crc_reply_valid(actual), "canonical checksum result");
        }
    }
    for (const auto request : {U64{65536}, std::numeric_limits<U64>::max()}) {
        require(f.slot.stage(record, endpoint, 1, ipc::Request{request, 0}) &&
                    snapshot_test_checksum(record.data()) == 3,
                "checksum reserved request bits");
    }
    require(f.slot.stage(record, endpoint, 1, ipc::Request{0, 1}) && snapshot_test_checksum(record.data()) == 3,
            "checksum reserved second channel");
    require(f.slot.stage(record, endpoint, 0, ipc::Request{0, 0}) && snapshot_test_checksum(record.data()) == 3,
            "checksum unsupported phase");
    for (U64 status = 0; status < 256; ++status) {
        require(ipc::snapshot_crc_reply_valid(status) == (status >= 1 && status <= 3), "closed checksum statuses");
        require(ipc::snapshot_crc_reply_valid(status | 256) == (status == 1), "failure checksum payload rejected");
    }
    for (unsigned bit = 40; bit < 64; ++bit)
        require(!ipc::snapshot_crc_reply_valid(1 | (U64{1} << bit)), "checksum high reserved bits");
    require(ipc::snapshot_crc_reply_valid(0xffffffff01), "maximum CRC copied value");
}

void copied_boundaries() {
    ipc::SnapshotSlot slot;
    std::array<std::byte, 72> output{};
    std::array<std::byte, 96> record{};
    for (const auto status : {1, 3}) {
        output.fill(std::byte{0});
        output[0] = std::byte(status);
        require(slot.publish(output) == ipc::SnapshotPublication::unavailable && !slot.ready(),
                "canonical failed publication");
        output[71] = std::byte{1};
        require(slot.publish(output) == ipc::SnapshotPublication::malformed && !slot.ready(),
                "nonzero failed payload cannot publish");
    }
    for (const auto byte : {0, 7}) {
        output.fill(std::byte{0});
        output[byte] = std::byte{2};
        require(slot.publish(output) == ipc::SnapshotPublication::malformed && !slot.ready(),
                "unknown or wide status cannot publish");
    }
    const ipc::Endpoint endpoint{1, done};
    for (unsigned value : {0U, 1U, 127U, 128U, 255U}) {
        output.fill(std::byte(value));
        for (std::size_t byte = 0; byte < 8; ++byte) {
            output[byte] = std::byte{0};
        }
        require(slot.publish(output) == ipc::SnapshotPublication::ready && !slot.bind(ipc::Endpoint{0, done}) &&
                    !slot.bind(ipc::Endpoint{1, 0}) && slot.bind(endpoint) && !slot.bind(endpoint),
                "one exact nonzero service binding");
        output.fill(std::byte{0xa5});
        for (U64 offset = 0; offset < 64; ++offset) {
            require(slot.stage(record, endpoint, 1, ipc::Request{1, offset}), "stage independently supplied bytes");
            const auto before = record;
            require(snapshot_test_service(record.data()) == (1 | (U64(value) << 8)) && record == before,
                    "actual service selects copied arbitrary bytes without mutation");
        }
    }
    for (const auto phase : {U64{0}, U64{2}, done}) {
        require(slot.stage(record, endpoint, phase, ipc::Request{done, done}) &&
                    snapshot_test_service(record.data()) == 5,
                "phase precedes operation and range");
    }
    for (const auto operation : {U64{0}, U64{2}, done}) {
        require(slot.stage(record, endpoint, 1, ipc::Request{operation, done}) &&
                    snapshot_test_service(record.data()) == 3,
                "operation precedes range");
    }
    const auto saved = record;
    for (const auto rejected : {ipc::Endpoint{0, done}, ipc::Endpoint{1, 0}, ipc::Endpoint{1, done - 1}}) {
        require(!slot.stage(record, rejected, 1, ipc::Request{1, 0}) && record == saved,
                "foreign, zero or stale binding stages nothing");
    }
    slot.clear();
    require(!slot.ready() && !slot.bound() && !slot.stage(record, endpoint, 1, ipc::Request{1, 0}) && record == saved,
            "revoked slot preserves destination");
}
} // namespace

extern "C" [[noreturn]] void __au_runtime_bytes_kernel_fault(U64 reason) noexcept {
    std::fprintf(stderr, "unexpected byte-runtime fault: %llu\n", static_cast<unsigned long long>(reason));
    std::_Exit(2);
}

int main() {
    checksum_boundaries();
    copied_boundaries();
    Fixture f;
    for (const auto scenario : {uefi::SnapshotProducerCase::invalid_selector,
                                uefi::SnapshotProducerCase::quota,
                                uefi::SnapshotProducerCase::pages}) {
        require(uefi::prepare_snapshot(reinterpret_cast<U64>(arena_storage.data()), f.pool, f.slot, scenario) ==
                    ipc::SnapshotPublication::unavailable,
                "actual producer failure");
        require(!f.slot.ready() && !f.slot.bind(ipc::Endpoint{1, 1}) && f.pool.used() == 0,
                "failure cannot publish or bind");
    }
    f.produce();
    f.bind();
    f.read_all();
    for (const auto edge : {U64{65}, done}) {
        f.submit(edge);
        const auto record = f.receive();
        require(f.reply(snapshot_test_service(record.data()), edge) == done, "full-width range errors");
    }
    f.submit(0, 6);
    const auto unsupported = f.receive();
    require(f.reply(snapshot_test_service(unsupported.data()), 0, 7) == done, "actual unsupported operation");

    f.submit(0);
    const auto malformed_record = f.receive();
    const auto actual = snapshot_test_service(malformed_record.data());
    require(!ipc::snapshot_reply_valid(actual | (U64{1} << 63)) && f.mailbox.state() == ipc::State::delivered,
            "malformed actual reply cannot commit");
    f.cancel();
    f.restart();
    f.read_all();

    f.submit(0);
    f.cancel();
    f.restart();
    f.read_all();

    f.submit(0);
    const auto wrong_byte = f.receive();
    require(f.reply(snapshot_test_service(wrong_byte.data()) ^ 0x100, 0) == failed,
            "canonical wrong byte reaches compiled client without native fallback");

    f.submit(0);
    const auto trap_record = f.receive(4);
    const auto child = fork();
    require(child >= 0, "fault child creation");
    if (child == 0) {
        static_cast<void>(snapshot_test_service(trap_record.data()));
        std::_Exit(3);
    }
    int status = 0;
    require(waitpid(child, &status, 0) == child && WIFSIGNALED(status) && WTERMSIG(status) == SIGILL,
            "actual compiled service bounds trap is SIGILL");
    f.cancel();
    f.restart();
    f.read_all();

    const auto endpoint = *f.mailbox.endpoint(f.service);
    f.storage.fill(std::byte{0xa5});
    const auto before = f.storage;
    ipc::SnapshotSlot::Record destination{f.storage.data() + 16, ipc::SnapshotSlot::record_bytes};
    require(!f.slot.stage(destination, ipc::Endpoint{0, endpoint.generation()}, 1, ipc::Request{1, 0}) &&
                f.storage == before,
            "foreign endpoint does not stage bytes");
    require(!f.mailbox.submit(f.service, ipc::Phase::request, *f.mailbox.endpoint(f.client), ipc::Request{1, 0}),
            "foreign domain cannot submit");
    f.slot.clear();
    require(!f.slot.stage(destination, endpoint, 1, ipc::Request{1, 0}) && f.storage == before,
            "cleared slot cannot stage");
    require(f.mailbox.revoke(ipc::Phase::inactive) && f.registry.destroy(f.client) && f.registry.destroy(f.service) &&
                f.pool.used() == 0 && f.mailbox.scrubbed(),
            "final revoked and scrubbed lifetime");
    for (U64 value = 0; value < 65536; ++value) {
        const bool wanted = value == 2 || value == 3 || value == 4 || value == 5 || value % 256 == 1;
        require(ipc::snapshot_reply_valid(value) == wanted, "exhaustive16-bit reply representation");
    }
    for (unsigned bit = 16; bit < 64; ++bit) {
        require(!ipc::snapshot_reply_valid(U64{1} | (U64{1} << bit)), "reserved high bits rejected");
    }
    std::printf("PASS: snapshot real producer/client/service/Mailbox controls, %llu checks; actual bounds SIGILL\n",
                static_cast<unsigned long long>(checks));
}
