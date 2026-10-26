// Private adapter state. No source file content is represented in these records.
enum class RamState {
    absent,
    booting,
    idle,
    command,
    aborting,
    poisoned
};
RamState ram_state = RamState::absent;
constinit ParkedRun ram_service_wait;
// Healthy transitions never replace the Domain's four move-only stack leases.
// Their original owner handle and allocator validation remain the backing proof.
struct RamLifetime final {
    user::DomainHandle owner;
    user::ProgramContract contract;
    U64 root, grant, generation;
    std::array<U64, 4> backing;
};
struct RamCommand final {
    const user::DomainHandle caller, service;
    const ipc::Endpoint caller_endpoint, service_endpoint;
    const U64 cleanup_epoch;
    RamFileFraming framing;
    unsigned service_used{};
    bool caller_disabled{}, delivered{};
    RamCommand(user::DomainHandle c,
               user::DomainHandle s,
               ipc::Endpoint ce,
               ipc::Endpoint se,
               U64 cleanup,
               RamFileFraming::Right right,
               unsigned expected_replace_count = 50)
        : caller(c), service(s), caller_endpoint(ce), service_endpoint(se), cleanup_epoch(cleanup),
          framing(right, expected_replace_count) {
    }
};
std::optional<RamLifetime> ram_lifetime;
std::optional<RamCommand> ram_command;
U64 ram_generation_watermark{}, ram_run_epoch{};
unsigned ram_commands{};
[[nodiscard]] auto ram_active_authority() -> bool;
[[nodiscard]] auto ram_service_admitted() -> bool {
    auto *record = caller_continuation.ram();
    if (!record)
        return false;
    auto &ram_caller_wait = *record;
    return (ram_state == RamState::booting && !ram_command && transaction == 0) ||
           (ram_state == RamState::aborting && ram_command && ram_command->caller_disabled && mailbox &&
            mailbox->revoked() && transaction == 0) ||
           (ram_state == RamState::command && ram_command && mailbox && mailbox->state() == ipc::State::delivered &&
            transaction == ram_caller_wait.ticket);
}
bool ram_fixture_injected{};
U64 ram_epoch_ceiling = UINT64_MAX;

auto scratchpad_discard() -> void;
