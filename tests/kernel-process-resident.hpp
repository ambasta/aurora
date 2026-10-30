// Included by the one kernel-process component driver. The real compiled owner
// supplies construction, borrowing and explicit source shutdown progression.
namespace resident_fixture {
namespace resident = aurora::resident;
using Kind = resident::OperationKind;
struct Input {
    U64 value = 0, detail = 0, result = 0;
    std::vector<U64> progress;
    std::size_t cursor = 0;
    bool terminal = false;
};
struct Platform {
    static inline bool quiet_value = true;
    static inline unsigned construction_fault = 0;
    static auto quiet() -> bool {
        return quiet_value;
    }
    [[noreturn]] static auto fail() -> void {
        _exit(96);
    }
    static auto construct(void *, resident::Descriptor *) -> void;
};
using Root = resident::Root<Input, Platform>;
Root *current = nullptr;
extern "C" void __au_runtime_resident_construct(void *, resident::Descriptor *);
extern "C" U64 __au_runtime_process_resident_prepare(void *);
extern "C" void __au_runtime_process_resident_run(void *, aurora::execution::Result *);
extern "C" U64 __au_runtime_process_resident_console(void *);
extern "C" U64 __au_runtime_process_resident_reject(void *);
extern "C" U64 __au_runtime_process_resident_finish(void *);
auto Platform::construct(void *storage, resident::Descriptor *input) -> void {
    const auto original = *input;
    __au_runtime_resident_construct(storage, input);
    if (construction_fault == 1)
        *input = original;
    if (construction_fault == 2)
        static_cast<resident::Descriptor *>(storage)->epoch = 0;
}
auto field(Root &root) -> resident::Descriptor {
    resident::Descriptor result;
    std::memcpy(&result, root.storage(), sizeof(result));
    return result;
}
auto scalar(const void *binding, U64 epoch, const void *address, Kind kind) -> U64 {
    auto &operation = current->enter(binding, epoch, address, kind);
    const auto parent = current->capture_parent();
    if (!current->parent_valid(parent))
        usage("resident parent was not live");
    const auto result = operation.input().value;
    current->release_parent(parent);
    current->leave(operation);
    return result;
}
extern "C" U64 __au_runtime_resident_prepare(const void *binding, U64 epoch, const void *address) {
    return scalar(binding, epoch, address, Kind::prepare);
}
extern "C" void
__au_runtime_resident_run(const void *binding, U64 epoch, const void *address, aurora::execution::Result *result) {
    auto &operation = current->enter(binding, epoch, address, Kind::run);
    *result = {static_cast<aurora::execution::Status>(operation.input().value), operation.input().detail};
    current->leave(operation);
}
extern "C" U64 __au_runtime_resident_console(const void *binding, U64 epoch, const void *address) {
    return scalar(binding, epoch, address, Kind::console);
}
extern "C" U64 __au_runtime_resident_reject(const void *binding, U64 epoch, const void *address) {
    return scalar(binding, epoch, address, Kind::reject);
}
auto progress(const void *binding, U64 epoch, const void *address, bool continuation) -> U64 {
    auto &operation = current->enter(binding, epoch, address, Kind::shutdown, continuation);
    auto &input = operation.input();
    if (input.terminal || input.cursor == input.progress.size())
        usage("unexpected resident shutdown progression");
    const auto result = input.progress[input.cursor++];
    input.terminal = result != 0;
    current->leave(operation);
    return result;
}
extern "C" U64 __au_runtime_resident_begin_shutdown(const void *binding, U64 epoch, const void *address) {
    return progress(binding, epoch, address, false);
}
extern "C" U64 __au_runtime_resident_advance_shutdown(const void *binding, U64 epoch, const void *address) {
    return progress(binding, epoch, address, true);
}
extern "C" U64 __au_runtime_resident_finish(const void *binding, U64 epoch, const void *address) {
    auto &operation = current->enter(binding, epoch, address, Kind::shutdown, true);
    auto &input = operation.input();
    if (!input.terminal || input.cursor != input.progress.size())
        usage("resident field consumed before scripted physical terminal");
    const auto result = input.result;
    current->consume(operation);
    current->leave(operation);
    return result;
}
auto finish(Root &root, Input &input) -> U64 {
    Root::Operation operation{Kind::shutdown, input};
    root.open(operation);
    const auto result = __au_runtime_process_resident_finish(root.storage());
    root.finish(operation);
    return result;
}
auto denial(const std::string &name) -> void {
    const auto child = fork();
    if (child < 0)
        usage("resident denial fork");
    if (child == 0) {
        Root root;
        current = &root;
        if (name == "constructor-input")
            Platform::construction_fault = 1;
        if (name == "constructor-field")
            Platform::construction_fault = 2;
        root.initialize();
        Input input;
        Root::Operation operation{Kind::prepare, input};
        root.open(operation);
        const auto descriptor = field(root);
        if (name == "wrong-binding")
            root.enter(&descriptor, descriptor.epoch, root.storage(), Kind::prepare);
        else if (name == "wrong-epoch")
            root.enter(descriptor.binding, descriptor.epoch + 1, root.storage(), Kind::prepare);
        else if (name == "copied-field")
            root.enter(descriptor.binding, descriptor.epoch, &descriptor, Kind::prepare);
        else if (name == "wrong-kind")
            root.enter(descriptor.binding, descriptor.epoch, root.storage(), Kind::run);
        else if (name == "not-quiet") {
            Platform::quiet_value = false;
            root.enter(descriptor.binding, descriptor.epoch, root.storage(), Kind::prepare);
        } else if (name == "owner-reentry") {
            Root::Operation other{Kind::prepare, input};
            root.open(other);
        } else {
            root.enter(descriptor.binding, descriptor.epoch, root.storage(), Kind::prepare);
            if (name == "effect-reentry")
                root.enter(descriptor.binding, descriptor.epoch, root.storage(), Kind::prepare);
            else if (name == "pinned-return") {
                static_cast<void>(root.capture_parent());
                root.leave(operation);
            } else if (name == "parent-epoch") {
                auto parent = root.capture_parent();
                ++parent.epoch;
                root.release_parent(parent);
            } else if (name == "parent-double-release") {
                const auto parent = root.capture_parent();
                root.release_parent(parent);
                root.release_parent(parent);
            } else if (name == "expired-parent") {
                const auto old = root.capture_parent();
                root.release_parent(old);
                root.leave(operation);
                root.close(operation);
                Root::Operation next{Kind::prepare, input};
                root.open(next);
                root.enter(descriptor.binding, descriptor.epoch, root.storage(), Kind::prepare);
                static_cast<void>(root.capture_parent());
                root.release_parent(old);
            } else if (name == "after-finish" || name == "double-finish" || name == "reinitialize") {
                root.leave(operation);
                root.close(operation);
                input.progress = {1};
                static_cast<void>(finish(root, input));
                if (name == "reinitialize")
                    root.initialize();
                else if (name == "after-finish")
                    static_cast<void>(__au_runtime_process_resident_prepare(root.storage()));
                else
                    static_cast<void>(__au_runtime_process_resident_finish(root.storage()));
            } else if (name == "replay") {
                root.leave(operation);
                root.enter(descriptor.binding, descriptor.epoch, root.storage(), Kind::prepare);
            } else
                usage("unknown resident denial");
        }
        _exit(0);
    }
    int status = 0;
    if (waitpid(child, &status, 0) != child || !WIFEXITED(status) || WEXITSTATUS(status) != 96)
        usage("resident authority denial did not fail closed: " + name);
}
} // namespace resident_fixture

auto resident_mode(const char *path) -> int {
    std::ifstream input{path};
    if (!input)
        usage("cannot read resident cases");
    for (std::string line; std::getline(input, line);) {
        if (line.empty() || line[0] == '#')
            continue;
        std::istringstream row{line};
        std::string name, token;
        row >> name;
        std::ostringstream output;
        output << name;
        resident_fixture::Root root;
        resident_fixture::current = &root;
        root.initialize();
        bool finished = false;
        while (row >> token) {
            std::vector<std::string> fields;
            std::istringstream pieces{token};
            for (std::string piece; std::getline(pieces, piece, ':');)
                fields.push_back(piece);
            const auto &operation = fields[0];
            if (operation == "deny" && fields.size() == 2) {
                resident_fixture::denial(fields[1]);
                output << " denied";
            } else if (operation == "finish" && fields.size() >= 3) {
                resident_fixture::Input selected;
                selected.result = number(fields[1]);
                for (std::size_t i = 2; i < fields.size(); ++i)
                    selected.progress.push_back(number(fields[i]));
                const auto result = resident_fixture::finish(root, selected);
                output << " finish=" << result << " steps=" << selected.cursor << " active=" << root.active();
                finished = true;
            } else {
                using Kind = resident_fixture::Kind;
                const auto kind = operation == "prepare"   ? Kind::prepare
                                  : operation == "run"     ? Kind::run
                                  : operation == "console" ? Kind::console
                                                           : Kind::reject;
                if ((operation != "prepare" && operation != "run" && operation != "console" && operation != "reject") ||
                    fields.size() != (kind == Kind::run ? 3U : 2U))
                    usage("invalid resident operation");
                resident_fixture::Input selected;
                selected.value = number(fields[1]);
                if (kind == Kind::run)
                    selected.detail = number(fields[2]);
                resident_fixture::Root::Operation call{kind, selected};
                root.open(call);
                output << ' ' << operation << '=';
                if (kind == Kind::run) {
                    aurora::execution::Result result;
                    resident_fixture::__au_runtime_process_resident_run(root.storage(), &result);
                    output << static_cast<U64>(result.status) << ':' << result.value;
                } else if (kind == Kind::prepare)
                    output << resident_fixture::__au_runtime_process_resident_prepare(root.storage());
                else if (kind == Kind::console)
                    output << resident_fixture::__au_runtime_process_resident_console(root.storage());
                else
                    output << resident_fixture::__au_runtime_process_resident_reject(root.storage());
                root.close(call);
            }
        }
        if (!finished) {
            resident_fixture::Input empty;
            empty.progress = {1};
            if (resident_fixture::finish(root, empty) != 0)
                usage("empty resident fixture finalization");
        }
        std::cout << output.str() << '\n';
    }
    return 0;
}
