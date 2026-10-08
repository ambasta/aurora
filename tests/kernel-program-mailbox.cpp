#include "../kernel/program-stream.hpp"
#include "../kernel/ipc-policy.hpp"
#include <cstdlib>
#include <iostream>
#include <string_view>

namespace {
using namespace aurora;
auto need(bool value, std::string_view message) -> void {
    if (!value) { std::cerr << "FAIL: " << message << '\n'; std::exit(1); }
}
class Command final {
public:
    user::DomainRegistry registry;
    user::DomainHandle client{}, service{}, stranger{};
    ipc::Mailbox mailbox{registry};
    program::Stream stream;
    ipc::Endpoint client_cap{}, service_cap{}, old_client{}, old_service{};
    std::uint64_t transaction{}, previous_transaction{};
    program::StreamBytes input{};
    Command() { stranger = *registry.create(); }
    auto begin(std::size_t count) -> void {
        client = *registry.create(); service = *registry.create();
        need(mailbox.bind(client, service), "new command binding");
        client_cap = *mailbox.endpoint(client); service_cap = *mailbox.endpoint(service);
        input.fill('a');
        need(stream.begin(input, count), "copied input begin");
        if (old_client.generation()) {
            need(client_cap.generation() != old_client.generation(), "fresh command grant");
            need(!mailbox.submit(client, ipc::Phase::request, old_client, ipc::Request{'Q', 0}), "old command grant");
            need(!mailbox.receive(service, ipc::Phase::service, old_service, previous_transaction), "old service grant");
        }
    }
    auto request(std::uint64_t ordinal) -> void {
        const auto source = stream.next_input();
        need(source && source->ordinal() == ordinal && source->byte() == 'a', "bounded copied launch input");
        need(!stream.accept_request('Q', ordinal + 1) && !stream.accept_reply('Q', ordinal)
            && !stream.acknowledge('Q', ordinal), "stream request order");
        need(!mailbox.submit(stranger, ipc::Phase::request, client_cap, ipc::Request{'Q', ordinal})
            && !mailbox.submit(service, ipc::Phase::request, client_cap, ipc::Request{'Q', ordinal})
            && !mailbox.submit(client, ipc::Phase::service, client_cap, ipc::Request{'Q', ordinal}), "request owner/phase");
        need(stream.accept_request('Q', ordinal), "client transformed scalar");
        need(registry.activate(client), "request live owner");
        const auto ticket = mailbox.submit(client, ipc::Phase::request, client_cap, ipc::Request{'Q', ordinal});
        need(ticket.has_value() && *ticket != previous_transaction, "actual fresh transaction"); transaction = *ticket;
        need(!mailbox.submit(client, ipc::Phase::request, client_cap, ipc::Request{'Q', ordinal}), "duplicate mailbox submit");
        need(registry.deactivate(client), "request root restoration");
        need(!mailbox.receive(client, ipc::Phase::service, service_cap, transaction)
            && !mailbox.receive(stranger, ipc::Phase::service, service_cap, transaction)
            && !mailbox.receive(service, ipc::Phase::service, service_cap, transaction + 1), "delivery owner/transaction");
    }
    auto deliver(std::uint64_t ordinal) -> void {
        const auto copied = mailbox.receive(service, ipc::Phase::service, service_cap, transaction);
        need(copied && copied->first() == 'Q' && copied->second() == ordinal && mailbox.scrubbed(), "actual request copy/scrub");
        need(!mailbox.receive(service, ipc::Phase::service, service_cap, transaction), "duplicate receive");
    }
    auto reply(std::uint64_t ordinal) -> void {
        need(registry.activate(service), "service live owner");
        need(!stream.accept_reply('R', ordinal) && !stream.accept_reply('Q', ordinal + 1), "changed service scalar");
        need(!mailbox.reply(client, ipc::Phase::service, service_cap, transaction, 'Q')
            && !mailbox.reply(stranger, ipc::Phase::service, service_cap, transaction, 'Q')
            && !mailbox.reply(service, ipc::Phase::service, service_cap, transaction + 1, 'Q'), "reply owner/transaction");
        need(stream.accept_reply('Q', ordinal) && mailbox.reply(service, ipc::Phase::service, service_cap, transaction, 'Q'),
            "actual service reply");
        need(!stream.accept_reply('Q', ordinal)
            && !mailbox.reply(service, ipc::Phase::service, service_cap, transaction, 'Q'), "duplicate service reply");
        need(registry.deactivate(service), "service root restoration");
    }
    auto consume() -> void {
        need(!mailbox.consume(service, ipc::Phase::completion, client_cap, transaction)
            && !mailbox.consume(stranger, ipc::Phase::completion, client_cap, transaction)
            && !mailbox.consume(client, ipc::Phase::completion, client_cap, transaction + 1), "completion owner/transaction");
        const auto completion = mailbox.consume(client, ipc::Phase::completion, client_cap, transaction);
        need(completion && completion->outcome() == ipc::Outcome::replied && completion->value() == 'Q'
            && mailbox.scrubbed(), "actual copied completion");
        need(!mailbox.consume(client, ipc::Phase::completion, client_cap, transaction), "duplicate completion consumption");
    }
    auto acknowledge(std::uint64_t ordinal) -> void {
        need(registry.activate(client), "completion live owner");
        need(!stream.acknowledge('R', ordinal) && !stream.acknowledge('Q', ordinal + 1), "changed client acknowledgment");
        need(stream.acknowledge('Q', ordinal) && !stream.acknowledge('Q', ordinal), "one-shot acknowledged output");
        need(registry.deactivate(client), "completion root restoration");
        need(mailbox.recycle(ipc::Phase::inactive), "actual mailbox recycle");
        previous_transaction = transaction; transaction = 0;
    }
    auto retire(bool success) -> void {
        if (!success) {
            need(stream.cancel(), "discard partial output");
            if (mailbox.state() == ipc::State::pending || mailbox.state() == ipc::State::delivered) {
                need(mailbox.cancel(ipc::Phase::inactive) && !mailbox.cancel(ipc::Phase::inactive), "one-shot cancellation");
                const auto completion = mailbox.consume(client, ipc::Phase::completion, client_cap, transaction);
                need(completion && completion->outcome() == ipc::Outcome::cancelled && completion->value() == 0,
                    "cancelled completion scrub");
            } else if (mailbox.state() == ipc::State::replied) {
                // A terminal reply cannot become cancellation; consume it before
                // retirement while discarding the unacknowledged stream output.
                consume();
            }
        }
        need(mailbox.scrubbed() && mailbox.revoke(ipc::Phase::inactive), "actual revoke after terminal consumption");
        const auto stale_client = client, stale_service = service;
        need(registry.destroy(client) && registry.destroy(service), "retire both domains before release");
        need(!registry.index(stale_client) && !registry.index(stale_service)
            && !mailbox.submit(stale_client, ipc::Phase::request, client_cap, ipc::Request{'Q', 0})
            && !mailbox.reply(stale_service, ipc::Phase::service, service_cap, transaction, 'Q'), "dead domain authority");
        old_client = client_cap; old_service = service_cap;
        if (transaction) previous_transaction = transaction;
        transaction = 0;
        if (!success) need(stream.scrubbed() && !stream.finish(), "cancelled output inaccessible");
    }
};
}

auto main() -> int {
    Command command;
    for (const std::size_t length : {0, 1, 64, 1}) {
        command.begin(length);
        for (std::size_t ordinal = 0; ordinal < length; ++ordinal) {
            need(!command.stream.finish(), "no partial publication");
            command.request(ordinal); command.deliver(ordinal); command.reply(ordinal);
            command.consume(); command.acknowledge(ordinal);
        }
        need(command.stream.ready_to_finish(), "full stream acknowledgments");
        command.retire(true);
        auto output = command.stream.finish();
        need(output && output->length() == length && command.stream.scrubbed(), "release only after retirement");
        for (std::size_t ordinal = 0; ordinal < length; ++ordinal)
            need(output->byte(ordinal) == 'Q', "opaque service output preserved without transformation");
        need(!output->byte(length) && !output->byte(SIZE_MAX), "copied output read bounds");
        output->scrub(); need(output->length() == 0 && output->bytes() == program::StreamBytes{}, "published copy scrub");
        need(!command.stream.finish(), "one-shot output publication");
    }
    // First complete one byte, then interrupt the next byte at every handoff.
    for (unsigned stage = 0; stage < 6; ++stage) {
        command.begin(2);
        command.request(0); command.deliver(0); command.reply(0); command.consume(); command.acknowledge(0);
        if (stage >= 1) command.request(1);
        if (stage >= 2) command.deliver(1);
        if (stage >= 3) command.reply(1);
        if (stage >= 4) command.consume();
        if (stage >= 5) command.acknowledge(1);
        command.retire(false);
    }
    command.begin(1); command.request(0); command.deliver(0); command.reply(0); command.consume(); command.acknowledge(0);
    command.retire(true);
    need(command.stream.finish().has_value(), "healthy fresh command after all cancellation stages");
    std::cout << "PASS: real Mailbox + compiled Aurora transition + copied stream composition, grants, transactions, retirement and cancellation\n";
}
