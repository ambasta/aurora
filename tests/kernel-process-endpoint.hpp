// Included by the one kernel-process driver. Each row drives the actual
// compiled Aurora owner; reviewed golden observations are the oracle.
namespace endpoint_fixture {
namespace endpoint = aurora::endpoint;
bool excluded = true, reenter = false;
class Platform final {
public:
    static auto enter() -> void;
    static auto leave() -> void {
        if (!excluded)
            fail();
    }
    [[noreturn]] static auto fail() -> void {
        std::_Exit(78);
    }
};
using Root = endpoint::Root<Platform>;
Root *entered = nullptr;
auto Platform::enter() -> void {
    if (reenter) {
        reenter = false;
        if (!entered)
            usage("missing endpoint reentry target");
        static_cast<void>(entered->observe());
    }
    if (!excluded)
        fail();
}
auto denial(const std::string &kind) -> void {
    const auto child = fork();
    if (child < 0)
        usage("endpoint fixture fork failed");
    if (!child) {
        Root root;
        if (kind == "before_create") {
            static_cast<void>(root.observe());
        } else {
            root.create();
            if (kind == "duplicate_create") {
                root.create();
            } else if (kind == "not_excluded") {
                excluded = false;
                static_cast<void>(root.observe());
            } else if (kind == "reentrant") {
                entered = &root;
                reenter = true;
                static_cast<void>(root.observe());
            } else {
                usage("unknown endpoint denial");
            }
        }
        std::_Exit(1);
    }
    int status{};
    if (waitpid(child, &status, 0) != child || !WIFEXITED(status) || WEXITSTATUS(status) != 78)
        usage("endpoint root denial failed");
}
} // namespace endpoint_fixture

namespace endpoint_fixture {
constexpr const char *phases[] = {
    "absent", "initial", "waiting", "staged", "delivery", "processing", "replied", "completion", "revoked"};
constexpr const char *exchanges[] = {"refused", "initial", "reply"};
constexpr const char *steps[] = {"failed", "launch", "resume", "replied"};
constexpr const char *consumptions[] = {"refused", "completion", "cancelled", "tail"};
constexpr const char *cancellations[] = {"refused", "settled", "draining"};
constexpr const char *completions[] = {"none", "service", "client"};
template <class Value, std::size_t N> auto word(Value value, const char *const (&names)[N]) -> const char * {
    const auto index = static_cast<U64>(value);
    if (index >= N)
        usage("invalid source endpoint observation");
    return names[index];
}
auto flag(const std::string &value) -> bool {
    const auto result = number(value);
    if (result > 1)
        usage("invalid endpoint flag");
    return result != 0;
}
auto view(Root &root, std::ostream &result) -> void {
    const auto observation = root.observe();
    result << word(observation.phase, phases) << ':' << observation.incarnation << ':' << observation.next << ':'
           << observation.transaction << ':' << observation.source << ':' << observation.client;
}
} // namespace endpoint_fixture

auto endpoint_mode(const char *cases) -> int {
    namespace fixture = endpoint_fixture;
    std::ifstream input{cases};
    if (!input)
        usage("cannot read endpoint cases");
    for (std::string line; std::getline(input, line);) {
        if (line.empty() || line.starts_with('#'))
            continue;
        std::istringstream row{line};
        std::string name, previous, token;
        if (!(row >> name >> previous))
            usage("missing endpoint initial ordinal");
        fixture::Root root;
        root.create(number(previous));
        std::ostringstream result;
        result << name;
        while (row >> token) {
            std::vector<std::string> fields;
            std::istringstream part{token};
            for (std::string field; std::getline(part, field, ':');)
                fields.push_back(field);
            const auto &operation = fields[0];
            result << ' ' << operation << '=';
            if (operation == "view" && fields.size() == 1) {
                fixture::view(root, result);
            } else if (operation == "bind" && fields.size() == 2) {
                result << root.bind(number(fields[1]));
            } else if (operation == "reset" && fields.size() == 1) {
                result << root.reset();
            } else if (operation == "exchange" && fields.size() == 4) {
                result << fixture::word(root.accept_exchange(number(fields[1]), number(fields[2]), number(fields[3])),
                                        fixture::exchanges);
            } else if (operation == "stage" && fields.size() == 2) {
                result << root.stage_client(number(fields[1]));
            } else if (operation == "begin" && fields.size() == 2) {
                result << root.begin(number(fields[1]));
            } else if (operation == "client_step" && fields.size() == 2) {
                result << fixture::word(root.client_step(number(fields[1])), fixture::steps);
            } else if (operation == "step" && fields.size() == 1) {
                result << fixture::word(root.step(), fixture::steps);
            } else if (operation == "alive" && fields.size() == 2) {
                result << fixture::word(root.observe_step(fixture::flag(fields[1])), fixture::steps);
            } else if (operation == "completion" && fields.size() == 1) {
                result << fixture::word(root.completion(), fixture::completions);
            } else if (operation == "delivered" && fields.size() == 3) {
                result << root.delivered(number(fields[1]), number(fields[2]));
            } else if (operation == "control" && fields.size() == 2) {
                result << root.consume_control(number(fields[1]));
            } else if (operation == "consume" && fields.size() == 4) {
                result << fixture::word(
                    root.consume_client(number(fields[1]), fixture::flag(fields[2]), fixture::flag(fields[3])),
                    fixture::consumptions);
            } else if (operation == "complete" && fields.size() == 2) {
                result << root.complete_client(number(fields[1]));
            } else if (operation == "cancel" && fields.size() == 3) {
                result << fixture::word(root.cancel(number(fields[1]), fixture::flag(fields[2])),
                                        fixture::cancellations);
            } else if (operation == "finish" && fields.size() == 2) {
                result << root.finish_client(number(fields[1]));
            } else if (operation == "invalidate" && fields.size() == 2) {
                result << root.invalidate(number(fields[1]));
            } else if (operation == "deny" && fields.size() == 2) {
                fixture::denial(fields[1]);
                result << "denied";
            } else {
                usage("invalid endpoint operation");
            }
        }
        std::cout << result.str() << '\n';
    }
    return 0;
}
