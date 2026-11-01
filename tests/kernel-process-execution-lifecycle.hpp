// The existing process driver links the actual compiled source owner once.
// Scripted native effects supply observations, not a second lifecycle oracle.
namespace lifecycle_fixture {
namespace lifecycle = aurora::lifecycle;
using Kind = lifecycle::EffectKind;
using Field = lifecycle::Field;
struct Platform {
    static inline bool quiet_value = true;
    static auto quiet() -> bool {
        return quiet_value;
    }
    [[noreturn]] static auto fail() -> void {
        _exit(96);
    }
};
using Root = lifecycle::Root<Platform>;
Root *current = nullptr;
std::array<lifecycle::Observation, 2> identities{}, captures{};
std::array<U64, 2> incarnations{};
bool invalidated = false, loader_snapshot = false;
lifecycle::Observation selected{};
std::string fault;
std::ostringstream effects;
U64 preparations = 0, previous_epoch = 0;
bool high_bits = false;

auto reset(Root &root) -> void {
    current = &root;
    identities = {};
    captures = {};
    incarnations = {};
    invalidated = false;
    loader_snapshot = false;
    selected = {};
    fault.clear();
    effects.str("");
    effects.clear();
    preparations = 0;
    previous_epoch = 0;
    high_bits = false;
    Platform::quiet_value = true;
    root.initialize();
}
auto enter(const void *binding, U64 epoch, const void *address, Kind kind, U64 slot) -> void {
    lifecycle::Descriptor copied{binding, epoch};
    if (fault == "wrong-binding")
        binding = &copied;
    if (fault == "wrong-epoch")
        ++epoch;
    if (fault == "copied-field")
        address = &copied;
    if (fault == "cross-slot")
        slot = 1 - slot;
    if (fault == "wrong-kind")
        kind = Kind::finish;
    if (fault == "not-quiet")
        Platform::quiet_value = false;
    current->enter(binding, epoch, address, kind, slot);
    if (fault == "owner-reentry")
        static_cast<void>(current->prepare(slot));
    if (fault == "effect-reentry")
        current->enter(binding, epoch, address, kind, slot);
    if (fault == "consume-live")
        current->consume();
    if (fault == "canonical-other-slot")
        static_cast<void>(current->canonical(1 - slot, Field::phase));
}
auto output_storage(const void *address, const lifecycle::Observation *output) -> void {
    const auto root = reinterpret_cast<std::uintptr_t>(address);
    const auto result = reinterpret_cast<std::uintptr_t>(output);
    if ((root & 15) || !(result + sizeof(*output) <= root || result >= root + 272))
        usage("lifecycle copied result aliases the retained root");
}
auto identity(U64 slot) -> void {
    const auto &value = identities[slot];
    if (current->canonical(slot, Field::epoch) != value.epoch || current->canonical(slot, Field::root) != value.root ||
        current->canonical(slot, Field::incarnation) != value.incarnation ||
        current->canonical(slot, Field::initial) != value.initial ||
        current->canonical(slot, Field::saved) != value.saved)
        usage("lifecycle canonical identity lost observation bits");
}
auto observe(U64 slot) -> lifecycle::Observation {
    auto result = identities[slot];
    result.event = selected.event;
    result.detail = selected.detail;
    result.exhausted = selected.exhausted;
    if (fault == "stale-epoch")
        --result.epoch;
    if (fault == "stale-reuse")
        result.epoch = previous_epoch;
    if (fault == "wrong-root")
        ++result.root;
    if (fault == "wrong-service")
        ++result.incarnation;
    if (fault == "wrong-initial")
        ++result.initial;
    if (fault == "wrong-saved")
        ++result.saved;
    if (fault == "foreign-identity") {
        const auto event = result.event;
        result = identities[1 - slot];
        result.event = event;
    }
    return result;
}
extern "C" void __au_runtime_execution_authority_prepare(
    const void *binding, U64 epoch, const void *address, lifecycle::Observation *output, U64 slot) {
    output_storage(address, output);
    enter(binding, epoch, address, Kind::prepare, slot);
    if (current->canonical(slot, Field::phase) != 0)
        usage("lifecycle preparation observed a nonempty source slot");
    ++preparations;
    identities[slot] = {
        1, 0, 0, 100 + preparations, 4096 * (slot + 1), incarnations[slot], 8192 + slot * 256, 16384 + slot * 256};
    if (high_bits) {
        identities[slot].epoch |= U64{1} << 63;
        identities[slot].root |= U64{1} << 63;
        identities[slot].incarnation |= U64{1} << 63;
        identities[slot].initial |= U64{1} << 63;
        identities[slot].saved |= U64{1} << 63;
    }
    *output = identities[slot];
    if (fault == "prepare-refused")
        output->event = 0;
    current->leave();
}
extern "C" void __au_runtime_execution_authority_activate(
    const void *binding, U64 epoch, const void *address, lifecycle::Observation *output, U64 slot) {
    output_storage(address, output);
    enter(binding, epoch, address, Kind::activate, slot);
    identity(slot);
    if (current->canonical(slot, Field::phase) != 2)
        usage("lifecycle activation was not source-selected");
    effects << " enter=" << current->canonical(slot, Field::mode);
    *output = observe(slot);
    captures[slot] = *output;
    current->leave();
}
extern "C" void __au_runtime_execution_authority_force(
    const void *binding, U64 epoch, const void *address, lifecycle::Observation *output, U64 slot) {
    output_storage(address, output);
    enter(binding, epoch, address, Kind::force, slot);
    identity(slot);
    const auto phase = current->canonical(slot, Field::phase);
    if (phase != 1 && phase != 3)
        usage("forced lifecycle observation lacks a prepared or parked source slot");
    *output = observe(slot);
    if (invalidated && slot == 1) {
        output->event = 14;
        output->detail = 16;
        output->exhausted = 0;
        if (fault == "natural-cross-incarnation")
            ++output->incarnation;
    }
    captures[slot] = *output;
    current->leave();
}
extern "C" void __au_runtime_execution_authority_complete(
    const void *binding, U64 epoch, const void *address, lifecycle::Observation *output, U64 slot) {
    output_storage(address, output);
    enter(binding, epoch, address, Kind::complete, slot);
    identity(slot);
    if (current->canonical(slot, Field::phase) != 3 || current->canonical(slot, Field::pending) < 3 ||
        current->canonical(slot, Field::pending) > 5)
        usage("completion has no source-owned pending operation");
    *output = observe(slot);
    current->leave();
}
// Models only physical invalidation/discard receipts. The compiled owner chooses
// when this barrier occurs and which slot must be retired before the service.
extern "C" U64
__au_runtime_execution_authority_invalidate_service(const void *binding, U64 epoch, const void *address, U64 slot) {
    enter(binding, epoch, address, Kind::invalidate_service, slot);
    identity(slot);
    if (slot != 0 || current->canonical(slot, Field::phase) != 4 || current->canonical(slot, Field::incarnation) == 0)
        usage("service invalidation lacks revoked source service authority");
    if (fault == "invalidate-cross-slot") {
        current->leave();
        current->enter(binding, epoch, address, Kind::invalidate_service, 1);
    }
    if (fault == "invalidate-failure") {
        current->leave();
        return 0;
    }
    invalidated = true;
    effects << " invalidate=" << slot;
    if (loader_snapshot) {
        loader_snapshot = false;
        effects << " snapshot=discarded";
    }
    current->leave();
    return fault == "invalidate-noncanonical" ? U64{0x1000000000000001} : U64{1};
}
extern "C" U64 __au_runtime_execution_authority_retire(const void *binding, U64 epoch, const void *address, U64 slot) {
    enter(binding, epoch, address, Kind::retire, slot);
    identity(slot);
    if (current->canonical(slot, Field::phase) != 4)
        usage("cleanup occurred before source activation revocation");
    if (current->canonical(slot, Field::event) != captures[slot].event ||
        current->canonical(slot, Field::detail) != captures[slot].detail ||
        current->canonical(slot, Field::exhausted) != captures[slot].exhausted)
        usage("source retirement overwrote primary physical evidence");
    effects << " retire=" << slot << ':' << current->canonical(slot, Field::event) << ':'
            << current->canonical(slot, Field::terminal);
    const bool result = fault != "cleanup-failure" && !(fault == "service-cleanup-failure" && slot == 0);
    if (slot == 0)
        invalidated = false;
    current->leave();
    return fault == "retire-noncanonical" ? U64{0x1000000000000001} : result ? U64{1} : U64{0};
}
extern "C" U64 __au_runtime_execution_authority_finish(const void *binding, U64 epoch, const void *address) {
    enter(binding, epoch, address, Kind::finish, 0);
    if (current->canonical(0, Field::phase) || current->canonical(1, Field::phase))
        usage("lifecycle consumption preceded complete two-slot retirement");
    current->consume();
    current->leave();
    return fault == "finish-noncanonical" ? U64{0x1000000000000001} : U64{1};
}
auto denial(const std::string &name, bool source) -> void {
    const auto child = fork();
    if (child < 0)
        usage("lifecycle denial fork");
    if (!child) {
        Root root;
        reset(root);
        if (name == "finish-noncanonical") {
            fault = name;
            static_cast<void>(root.finish());
        } else if (name == "natural-cross-incarnation" || name == "invalidate-failure" ||
                   name == "service-cleanup-failure" || name == "invalidate-cross-slot" ||
                   name == "invalidate-noncanonical") {
            incarnations = {7, 7};
            static_cast<void>(root.prepare(0));
            static_cast<void>(root.prepare(1));
            selected = {6, 0, 0};
            fault = name;
            static_cast<void>(root.execute(0));
        } else if (!source) {
            if (name == "after-finish" || name == "reinitialize") {
                static_cast<void>(root.finish());
                if (name == "after-finish")
                    static_cast<void>(root.prepare(0));
                else
                    root.initialize();
            } else {
                fault = name;
                static_cast<void>(root.prepare(0));
            }
        } else {
            static_cast<void>(root.prepare(0));
            static_cast<void>(root.prepare(1));
            if (name == "stale-reuse") {
                previous_epoch = identities[0].epoch;
                selected = {6, 0, 0};
                static_cast<void>(root.execute(0));
                static_cast<void>(root.prepare(0));
                fault = "stale-reuse";
                static_cast<void>(root.execute(0));
            } else if (name == "finish-live")
                static_cast<void>(root.finish());
            else if (name == "completion-identity" || name == "completion-event" || name == "completion-exhausted" ||
                     name == "completion-detail") {
                selected = {5, 0, 0};
                static_cast<void>(root.execute(0));
                selected = {name == "completion-event" ? U64{6} : U64{13}, 0, 0};
                if (name == "completion-identity")
                    fault = "wrong-saved";
                if (name == "completion-exhausted")
                    selected.exhausted = 1;
                if (name == "completion-detail")
                    selected.detail = 1;
                static_cast<void>(root.complete(0));
            } else if (name == "cancel-exhausted" || name == "output-failure-exhausted" ||
                       name == "unavailable-exhausted") {
                if (name == "output-failure-exhausted") {
                    selected = {5, 0, 0};
                    static_cast<void>(root.execute(0));
                }
                selected = {14,
                            name == "cancel-exhausted"           ? U64{10}
                            : name == "output-failure-exhausted" ? U64{1}
                                                                 : U64{16},
                            1};
                static_cast<void>(root.force(0));
            } else if (name == "forced-unknown-mask" || name == "forced-empty-mask" ||
                       name == "forced-explicit-without-endpoint" || name == "forced-prior-without-intent") {
                selected = {14,
                            name == "forced-unknown-mask"                ? U64{32}
                            : name == "forced-empty-mask"                ? U64{0}
                            : name == "forced-explicit-without-endpoint" ? U64{2}
                                                                         : U64{12},
                            0};
                static_cast<void>(root.force(0));
            } else if (name == "prepared-output" || name == "prepared-expiry" || name == "prepared-prior" ||
                       name == "service-output-collision" || name == "output-with-timer" ||
                       name == "expiry-without-request") {
                if (name == "output-with-timer" || name == "expiry-without-request") {
                    selected = {2, 0, 0};
                    static_cast<void>(root.execute(0));
                }
                selected = {14,
                            name == "prepared-output" || name == "output-with-timer" ? U64{1}
                            : name == "prepared-prior"                               ? U64{14}
                            : name == "service-output-collision"                     ? U64{17}
                                                                                     : U64{8},
                            0};
                static_cast<void>(root.force(0));
            } else if (name == "force-identity") {
                selected = {14, 16, 0};
                fault = "wrong-saved";
                static_cast<void>(root.force(0));
            } else {
                fault = name;
                selected = {6, 0, 0};
                if (name == "invalid-event")
                    selected.event = 12;
                if (name == "invalid-exhaustion")
                    selected.exhausted = 2;
                static_cast<void>(root.execute(0));
            }
        }
        _exit(0);
    }
    int status = 0;
    if (waitpid(child, &status, 0) != child || (source ? (!WIFSIGNALED(status) || WTERMSIG(status) != SIGILL)
                                                       : (!WIFEXITED(status) || WEXITSTATUS(status) != 96)))
        usage("lifecycle denial did not fail closed: " + name);
}
} // namespace lifecycle_fixture

auto lifecycle_mode(const char *path) -> int {
    std::ifstream input{path};
    if (!input)
        usage("cannot read lifecycle cases");
    for (std::string line; std::getline(input, line);) {
        if (line.empty() || line[0] == '#')
            continue;
        std::istringstream row{line};
        std::string name, token;
        row >> name;
        lifecycle_fixture::Root root;
        lifecycle_fixture::reset(root);
        std::ostringstream output;
        output << name;
        bool finished = false;
        while (row >> token) {
            std::vector<std::string> fields;
            std::istringstream pieces{token};
            for (std::string piece; std::getline(pieces, piece, ':');)
                fields.push_back(piece);
            const auto &operation = fields[0];
            if ((operation == "native" || operation == "source") && fields.size() == 2) {
                lifecycle_fixture::denial(fields[1], operation == "source");
                output << " denied=" << operation;
            } else if (operation == "incarnation" && fields.size() == 3) {
                const auto slot = number(fields[1]);
                if (slot >= 2)
                    usage("invalid lifecycle incarnation slot");
                lifecycle_fixture::incarnations[slot] = number(fields[2]);
            } else if (operation == "loader-snapshot" && fields.size() == 1) {
                lifecycle_fixture::loader_snapshot = true;
            } else if (operation == "high-bits" && fields.size() == 1) {
                lifecycle_fixture::high_bits = true;
            } else if (operation == "finish" && fields.size() == 1) {
                output << " finish=" << root.finish();
                finished = true;
            } else if ((operation == "prepare" || operation == "refuse") && fields.size() == 2) {
                const auto slot = number(fields[1]);
                lifecycle_fixture::fault = operation == "refuse" ? "prepare-refused" : "";
                output << " prepare=" << root.prepare(slot);
                lifecycle_fixture::fault.clear();
            } else if ((operation == "run" || operation == "force") && fields.size() == 5) {
                const auto slot = number(fields[1]);
                lifecycle_fixture::selected = {number(fields[2]), number(fields[3]), number(fields[4])};
                const auto result = operation == "run" ? root.execute(slot) : root.force(slot);
                output << ' ' << operation << '=' << result.event << ':' << result.detail << ':' << result.generation;
            } else if (operation == "complete" && fields.size() == 2) {
                lifecycle_fixture::selected = {13, 0, 0};
                output << " complete=" << root.complete(number(fields[1]));
            } else if (operation == "can-prepare" && fields.size() == 2) {
                output << " can-prepare=" << root.can_prepare(number(fields[1]));
            } else if (operation == "state" && fields.size() == 2) {
                const auto slot = number(fields[1]);
                output << " state=" << static_cast<U64>(root.phase(slot)) << ':' << root.generation(slot);
            } else
                usage("invalid lifecycle operation: " + token);
        }
        if (!finished && !root.finish())
            usage("lifecycle fixture finalization");
        std::cout << output.str() << lifecycle_fixture::effects.str() << '\n';
    }
    return 0;
}
