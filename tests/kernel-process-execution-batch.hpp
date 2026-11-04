// The production Aurora policy is linked once; cases supply physical observations.
namespace batch_fixture {
namespace batch = aurora::batch;
class Platform final {
public:
    static inline U64 identity = 0;
    static inline bool pinned = false, loan = false, complete = true, stale = false;
    [[noreturn]] static auto fail() -> void {
        _exit(79);
    }
    static auto capture_parent() -> aurora::resident::Parent {
        if (pinned)
            fail();
        pinned = true;
        return {&identity, 1};
    }
    static auto valid(const void *binding, aurora::resident::Parent parent) -> bool {
        return pinned && !stale && binding == &identity && parent.context == &identity && parent.epoch == 1;
    }
    static auto enter() -> void {
        if (!pinned || loan)
            fail();
        loan = true;
    }
    static auto leave() -> void {
        if (!pinned || !loan)
            fail();
        loan = false;
    }
    static auto settled(const void *binding) -> bool {
        return binding == &identity && !loan && complete;
    }
    static auto release_parent(aurora::resident::Parent parent) -> void {
        if (!valid(&identity, parent) || loan)
            fail();
        pinned = false;
    }
};
auto binding_case(const std::string &kind) -> bool {
    const auto child = fork();
    if (child < 0)
        usage("batch binding fork");
    if (child == 0) {
        {
            batch::Root<Platform> root{&Platform::identity};
            if (kind == "early-finish")
                static_cast<void>(root.finish());
            auto request = root.next();
            if (kind == "double-issue")
                static_cast<void>(root.next());
            if (kind == "forged-load-quota") {
                root.begin_effect(request);
                root.accept(batch::Event::success);
                request = root.next();
                request.quota = 8192;
            }
            if (kind == "forged-quota")
                request.quota = 4096;
            if (kind == "forged-child")
                request.child = 1;
            if (kind == "stale-parent")
                Platform::stale = true;
            root.begin_effect(request);
            if (kind == "double-effect")
                root.begin_effect(request);
            if (kind != "unfinished") {
                root.accept(batch::Event::refused, 6);
                if (kind == "unsettled")
                    Platform::complete = false;
                const auto result = root.finish();
                if (result.admission != 6 || Platform::pinned || Platform::loan)
                    _exit(80);
            }
        }
        _exit(0);
    }
    int status = 0;
    if (waitpid(child, &status, 0) != child || !WIFEXITED(status))
        usage("batch binding child status");
    const int expected = kind == "good" ? 0 : 79;
    if (WEXITSTATUS(status) != expected)
        usage("batch binding rejection missing");
    return expected == 0;
}
constexpr const char *actions[] = {
    "admit", "load", "activate", "output", "request", "retire", "close", "abandon", "done"};
constexpr const char *events[] = {"success",
                                  "refused",
                                  "parked",
                                  "output",
                                  "request",
                                  "terminal",
                                  "pending",
                                  "service_lost",
                                  "output_failed",
                                  "cancelled"};
auto event(const std::string &name) -> batch::Event {
    for (U64 at = 0; at < std::size(events); ++at)
        if (name == events[at])
            return static_cast<batch::Event>(at);
    usage("unknown batch observation");
}
auto show(const batch::Request &request, std::ostream &output) -> void {
    if (static_cast<U64>(request.action) >= std::size(actions))
        usage("invalid batch action");
    output << actions[static_cast<U64>(request.action)] << '.' << request.child << '#' << request.ordinal << 'q'
           << request.quota;
}
} // namespace batch_fixture

auto execution_batch_mode(const char *cases) -> int {
    namespace fixture = batch_fixture;
    std::ifstream input{cases};
    if (!input)
        usage("cannot read batch cases");
    for (std::string line; std::getline(input, line);) {
        if (line.empty() || line.starts_with('#'))
            continue;
        std::istringstream row{line};
        std::string name, token;
        row >> name;
        if (name.starts_with("withdraw-")) {
            U64 slot = 0, caller = 0, client = 0, generation = 0, phase = 0;
            aurora::endpoint::Observation observation{};
            if (!(row >> slot >> caller >> client >> generation >> phase >> observation.client >>
                  observation.incarnation >> observation.source) ||
                phase > 8)
                usage(
                    "withdrawal case requires slot caller client generation phase observed-client incarnation source");
            observation.phase = static_cast<aurora::endpoint::Phase>(phase);
            const bool accepted = fixture::batch::can_withdraw_staged(slot, caller, client, generation, observation);
            std::cout << name << (accepted ? " accepted" : " denied") << '\n';
            continue;
        }
        if (name.starts_with("binding-")) {
            row >> token;
            const bool accepted = fixture::binding_case(token);
            std::cout << name << (accepted ? " accepted" : " denied") << '\n';
            continue;
        }
        alignas(16) std::byte storage[160]{};
        fixture::batch::__au_runtime_batch_create(storage);
        std::ostringstream output;
        output << name;
        while (row >> token) {
            std::vector<std::string> fields;
            std::istringstream part{token};
            for (std::string field; std::getline(part, field, ':');)
                fields.push_back(field);
            if (fields.size() != 3)
                usage("batch receipt requires event:status:value");
            fixture::batch::Request request, repeated;
            fixture::batch::__au_runtime_batch_next(storage, &request);
            fixture::batch::__au_runtime_batch_next(storage, &repeated);
            if (request != repeated)
                usage("batch outstanding observation changed");
            const bool stale = fields[0] == "stale";
            const auto event = stale ? fixture::batch::Event::success : fixture::event(fields[0]);
            const bool accepted = fixture::batch::__au_runtime_batch_accept(
                storage, stale ? request.ordinal - 1 : request.ordinal, event, number(fields[1]), number(fields[2]));
            output << ' ';
            fixture::show(request, output);
            output << '/' << fields[0] << '=' << accepted;
        }
        fixture::batch::Request request;
        fixture::batch::__au_runtime_batch_next(storage, &request);
        output << " final=";
        fixture::show(request, output);
        if (request.action == fixture::batch::Action::done) {
            fixture::batch::Result result;
            fixture::batch::__au_runtime_batch_result(storage, &result);
            output << ':' << result.admission << ',' << result.status1 << ',' << result.value1 << ',' << result.status2
                   << ',' << result.value2;
        }
        std::cout << output.str() << '\n';
    }
    return 0;
}
