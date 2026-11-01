// One compiled production policy, driven by reviewed request/receipt data.
namespace load_fixture {
namespace load = aurora::load;
class Platform final {
public:
    static auto enter() -> void {
    }
    static auto leave() -> void {
    }
    [[noreturn]] static auto fail() -> void {
        std::_Exit(78);
    }
};
constexpr const char *actions[] = {
    "open", "reserve", "read", "fill", "seal", "discard_close", "close", "load", "discard_done", "done"};
constexpr const char *results[] = {"loaded", "missing", "malformed", "quota", "unavailable"};
auto action(const std::string &name) -> load::Action {
    for (U64 i = 0; i < std::size(actions); ++i)
        if (name == actions[i])
            return static_cast<load::Action>(i);
    usage("unknown committed-load action");
}
auto show(const load::Request &request, std::ostream &output) -> void {
    const auto action = static_cast<U64>(request.action), result = static_cast<U64>(request.result);
    if (action >= std::size(actions) || result >= std::size(results))
        usage("invalid committed-load observation");
    output << actions[action] << ':' << results[result] << ':' << request.id << ':' << request.size << ':'
           << request.offset << ':' << request.count;
}
} // namespace load_fixture

auto committed_load_mode(const char *cases) -> int {
    namespace fixture = load_fixture;
    std::ifstream input{cases};
    if (!input)
        usage("cannot read committed-load cases");
    for (std::string line; std::getline(input, line);) {
        if (line.empty() || line.starts_with('#'))
            continue;
        std::istringstream row{line};
        std::string name, token;
        row >> name;
        fixture::load::Operation<fixture::Platform> operation;
        std::ostringstream output;
        output << name;
        while (row >> token) {
            std::vector<std::string> fields;
            std::istringstream part{token};
            for (std::string field; std::getline(part, field, ':');)
                fields.push_back(field);
            if (fields.size() != 5 || number(fields[1]) > 1)
                usage("committed-load receipt requires action:ok:status:value:count");
            const auto accepted = operation.accept(fixture::action(fields[0]),
                                                   number(fields[1]) != 0,
                                                   number(fields[2]),
                                                   number(fields[3]),
                                                   number(fields[4]));
            output << ' ' << fields[0] << '=' << accepted << '>';
            const auto request = operation.next();
            const auto index = static_cast<U64>(request.action);
            if (index >= std::size(fixture::actions))
                usage("invalid committed-load action");
            output << fixture::actions[index];
        }
        output << " final=";
        fixture::show(operation.next(), output);
        std::cout << output.str() << '\n';
    }
    return 0;
}
