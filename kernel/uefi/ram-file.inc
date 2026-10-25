// Opt-in retained CPL3 service. The supervisor stores authority, framing and
// accounting only; file contents never enter a native semantic backing store.
template <class T> auto ram_clear(std::optional<T> &record) -> void {
    std::destroy_at(&record);
    auto *bytes = reinterpret_cast<volatile std::byte *>(&record);
    for (std::size_t i = 0; i < sizeof(record); ++i)
        bytes[i] = std::byte{0};
    std::construct_at(&record);
}
[[nodiscard]] auto ram_lifetime_valid() -> bool {
    if (!ram_lifetime || !domains[1].handle || !domains[1].contract || !domains[1].tables ||
        registry.index(ram_lifetime->owner) != std::optional<std::size_t>{1} ||
        registry.index(*domains[1].handle) != std::optional<std::size_t>{1} ||
        !user::same_contract(ram_lifetime->contract, *domains[1].contract) ||
        ram_lifetime->root != domains[1].tables->root() || !verify(domains[1]))
        return false;
    for (unsigned i = 0; i < 4; ++i)
        if (!domains[1].stacks[i] || frames.address(*domains[1].stacks[i]) != ram_lifetime->backing[i])
            return false;
    return ram_lifetime->grant == 1 && ram_lifetime->generation != 0;
}
[[nodiscard]] auto ram_command_valid() -> bool {
    return ram_command && ram_lifetime_valid() &&
           registry.index(ram_command->caller) == std::optional<std::size_t>{0} &&
           registry.index(ram_command->service) == std::optional<std::size_t>{1} && domains[0].handle &&
           registry.index(*domains[0].handle) == std::optional<std::size_t>{0} && verify(domains[0]);
}
[[nodiscard]] auto ram_active_authority() -> bool {
    if (!ram_lifetime_valid() || !run_authority || active > 1 || !verify(domains[active]))
        return false;
    if (active == 0)
        return ram_state == RamState::command && ram_command_valid() && !ram_command->caller_disabled &&
               launch[2] == ram_command->caller_endpoint.slot() &&
               launch[3] == ram_command->caller_endpoint.generation();
    return launch[2] == ram_lifetime->grant && launch[3] == ram_lifetime->generation &&
           ((ram_state == RamState::booting && launch[0] == 1 && !ram_command) ||
            (ram_state == RamState::command && launch[0] == 2 && ram_command_valid() && ram_command->delivered &&
             transaction == ram_caller_wait.ticket && ram_command->framing.state() == RamFileFraming::State::pending) ||
            (ram_state == RamState::aborting && launch[0] == 3 && ram_command && ram_command->caller_disabled &&
             !domains[0].handle && mailbox->revoked() &&
             ram_command->framing.state() == RamFileFraming::State::aborting));
}
[[nodiscard]] auto ram_mint_epoch() -> std::optional<U64> {
    if (timer_epoch_watermark == UINT64_MAX || timer_epoch_watermark >= ram_epoch_ceiling)
        return std::nullopt;
    return ++timer_epoch_watermark;
}
[[nodiscard]] auto ram_boundary_debit() -> bool {
    require(timer_armed && !timer_exhausted && timer_remaining && timer_initial == timer_remaining + timer_ticks,
            "RAM boundary allowance");
    // Conservative debits exercise exhaustion without replenishing any ledger.
    const bool inject = !ram_fixture_injected && ram_command &&
                        ((fixture == Fixture::ram_caller_budget && ram_commands == 2 && active == 0 &&
                          ram_command->framing.count() == 2) ||
                         (fixture == Fixture::ram_service_budget && active == 1 && ram_command->framing.count() == 2) ||
                         (fixture == Fixture::ram_abort_budget && ram_state == RamState::aborting));
    if (inject) {
        ram_fixture_injected = true;
        while (timer_remaining > 1) {
            const auto debit =
                BudgetTransition::decode(language_budget_tick(timer_initial, timer_remaining, timer_ticks),
                                         timer_initial,
                                         timer_remaining,
                                         timer_ticks);
            require(debit && debit->resume(), "RAM fixture conservative debit");
            timer_ticks = debit->used();
            timer_remaining = debit->remaining();
        }
        Serial::text("AURORA_RAM_FILE_BUDGET_PROBE: role=");
        Serial::number(active);
        Serial::text(" initial=");
        Serial::number(timer_initial);
        Serial::text("\r\n");
    }
    const auto charge = BudgetTransition::decode(
        language_budget_tick(timer_initial, timer_remaining, timer_ticks), timer_initial, timer_remaining, timer_ticks);
    require(charge.has_value(), "RAM boundary policy");
    timer_ticks = charge->used();
    timer_remaining = charge->remaining();
    timer_exhausted = !charge->resume();
    Serial::text("AURORA_RAM_FILE_DEBIT: epoch=");
    Serial::number(timer_epoch);
    Serial::text(" used=");
    Serial::number(timer_ticks);
    Serial::text(" remaining=");
    Serial::number(timer_remaining);
    Serial::text("\r\n");
    return !timer_exhausted;
}
[[nodiscard]] auto ram_capture(U64 frame, U64 pc) -> ServiceContext {
    require(active < 2 && current_run_identity() && timer_armed && timer_owner && registry.active(*timer_owner) &&
                timer_owner_epoch == timer_epoch && timer_remaining && timer_initial == timer_remaining + timer_ticks &&
                timer_initial == run_authority->budget(),
            "RAM active exchange authority");
    const auto context = capture_exchange(active, frame, pc);
    require(context.has_value(), "RAM exact role selected exchange site");
    return *context;
}
auto ram_trap(U64 frame) -> U64 {
    if (active == 1 && ram_state == RamState::booting) {
        auto *words = reinterpret_cast<U64 *>(frame);
        if (fixture == Fixture::ram_grant)
            ++words[9];
        if (fixture == Fixture::ram_site)
            ++words[17];
        if (fixture == Fixture::ram_frame)
            words[19] |= U64{1} << 63;
        if (fixture == Fixture::ram_root)
            asm volatile("mov %0,%%cr3" ::"r"(kernel_root) : "memory");
    }
    const auto context = ram_capture(frame, active == 0 ? image_sites(0).call_pc : image_sites(1).serve_pc);
    const auto &words = context.words();
    if (active == 0) {
        require(ram_command_valid() && !ram_caller_wait.context && words[8] == ram_command->caller_endpoint.slot() &&
                    words[9] == ram_command->caller_endpoint.generation(),
                "RAM Call grant authority");
        // Refusal returns synchronously under the same active identity. Leave
        // the existing timer armed so an already pending IRQ is not rearmed
        // over or discarded. Both accepted and refused calls consume a quantum.
        const bool permitted = ram_command->framing.permits(words[11]);
        require(!permitted || timer_stop(), "RAM caller boundary stop");
        if (!ram_boundary_debit()) {
            require(permitted || timer_stop(), "RAM refused caller exhaustion stop");
            ram_command->caller_disabled = true;
            park_run(*domains[0].handle);
            return 1;
        }
        if (!permitted) {
            auto *restored = reinterpret_cast<U64 *>(frame);
            restored[14] = 2;
            restored[11] = 0;
            return 0;
        }
        if (mailbox->state() == ipc::State::consumed)
            require(mailbox->recycle(ipc::Phase::inactive), "RAM exchange recycle");
        require(mailbox->state() == ipc::State::idle && mailbox->scrubbed(), "RAM publication boundary");
        const auto ticket = mailbox->submit(
            *domains[0].handle, ipc::Phase::request, ram_command->caller_endpoint, ipc::Request{words[11], 0});
        if (!ticket) {
            ram_command->caller_disabled = true;
            park_run(*domains[0].handle);
            return 1; // Reserved abort authority is still available.
        }
        require(ram_command->framing.publish(words[11]), "RAM admitted request framing");
        save_parked_run(ram_caller_wait, context);
        ram_caller_wait.authority.emplace(*run_authority);
        ram_caller_wait.service = ram_command->service;
        ram_caller_wait.endpoint = ram_command->caller_endpoint;
        ram_caller_wait.ticket = *ticket;
        ram_caller_wait.launch = launch;
        park_run(*domains[0].handle);
        return 1;
    }
    require(words[8] == ram_lifetime->grant && words[9] == ram_lifetime->generation && !ram_service_wait.context &&
                timer_stop(),
            "RAM Serve grant and dormant capacity");
    const bool budget = ram_boundary_debit();
    bool accepted = false;
    if (budget) {
        if (ram_state == RamState::booting)
            accepted = words[11] == 0;
        else if (ram_state == RamState::aborting)
            accepted = ram_command->framing.acknowledge_abort(words[11]);
        else {
            require(ram_state == RamState::command && ram_command_valid() && ram_command->delivered &&
                        mailbox->state() == ipc::State::delivered,
                    "RAM exact delivered reply authority");
            accepted = ram_command->framing.reply(words[11]);
        }
    }
    if (!accepted) {
        ram_state = RamState::poisoned;
        park_run(*domains[1].handle);
        return 1;
    }
    if (fixture == Fixture::ram_pending && !ram_fixture_injected) {
        ram_fixture_injected = true;
        force_timer_pending();
    }
    // Capture the complete dormant record before publishing any observable reply.
    save_parked_run(ram_service_wait, context);
    if (ram_state == RamState::command) {
        require(mailbox->reply(*domains[1].handle,
                               ipc::Phase::service,
                               ram_command->service_endpoint,
                               ram_caller_wait.ticket,
                               words[11]),
                "RAM atomic service reply");
        ram_command->service_used = timer_ticks;
        ram_command->delivered = false;
    }
    park_run(*domains[1].handle);
    return 1;
}
auto ram_terminal() -> void {
    // The generic dispatcher has already authenticated the exact language site,
    // integer frame and run authority. Unknown sites never reach this hook.
    if (active == 1)
        ram_state = RamState::poisoned; // Returning from Serve is not completion.
    else {
        require(active == 0 && ram_command_valid(), "RAM caller terminal authority");
        ram_command->caller_disabled = true;
    }
}
auto ram_finish_execution(unsigned index) -> void {
    timer_finish();
    require(root() == kernel_root && active == L::domain_count && saved_rsp == 0 && !program.running(),
            "RAM unwound kernel continuation");
    if (timer_exhausted) {
        if (index == 1)
            ram_state = RamState::poisoned;
        else
            ram_command->caller_disabled = true;
    }
    launch = {};
    selected_phase = ipc::Phase::inactive;
    transaction = 0;
}
auto ram_launch(unsigned index, U64 phase, U64 epoch) -> void {
    require(index < 2 && root() == kernel_root && active == L::domain_count && irq_off() && !timer_armed &&
                !program.running() && !saved_rsp && domains[index].handle && verify(domains[index]),
            "RAM fresh launch boundary");
    if (index == 1)
        require(ram_state == RamState::booting && !ram_service_wait.context, "RAM one time startup");
    else
        require(ram_state == RamState::command && ram_command_valid() && !ram_command->caller_disabled,
                "RAM fresh caller authority");
    selected_client = 0;
    selected_role = index == 0 ? SelectedRunAuthority::Role::client : SelectedRunAuthority::Role::service;
    selected_phase = index == 0 ? ipc::Phase::request : ipc::Phase::service;
    transaction = 0;
    const auto grant = index == 0 ? ram_command->caller_endpoint.slot() : ram_lifetime->grant;
    const auto generation = index == 0 ? ram_command->caller_endpoint.generation() : ram_lifetime->generation;
    launch = {phase, 0, grant, generation, 0, 0, 0x202};
    ram_run_epoch = epoch;
    require(launch_domain(index, *domains[index].handle), "RAM launch continuation");
    ram_finish_execution(index);
}
// Service activation always mints a new active identity; the dormant frame never
// confers a previous command's run authority or a renewed normal allowance.
auto ram_resume_service(U64 status, U64 word, U64 epoch) -> void {
    require(root() == kernel_root && active == L::domain_count && irq_off() && !timer_armed && !saved_rsp &&
                !program.running() && ram_lifetime_valid() && ram_service_wait.context &&
                ram_service_wait.context->call_frame(ram_lifetime->contract, image_sites(1).serve_pc),
            "RAM dormant service authority");
    const bool cleanup = ram_state == RamState::aborting;
    require((cleanup && status == 1 && word == 0 && ram_command && ram_command->caller_disabled &&
             epoch == ram_command->cleanup_epoch && mailbox->revoked() && !domains[0].handle) ||
                (!cleanup && status == 0 && ram_state == RamState::command && ram_command_valid() &&
                 ram_command->delivered && mailbox->state() == ipc::State::delivered &&
                 ram_command->framing.request() == word),
            "RAM narrow resume purpose");
    selected_client = 0;
    selected_role = SelectedRunAuthority::Role::service;
    selected_phase = ipc::Phase::service;
    transaction = cleanup ? 0 : ram_caller_wait.ticket;
    launch = {cleanup ? 3U : 2U, 0, ram_lifetime->grant, ram_lifetime->generation, 0, 0, 0x202};
    const auto frame = restore_parked_run(ram_service_wait);
    auto *words = reinterpret_cast<U64 *>(frame);
    words[14] = status;
    words[11] = word;
    ram_service_wait.clear(); // Consume dormant authority exactly once.
    ram_run_epoch = epoch;
    activate_parked_run(1);
    timer_begin(1); // Restores the command ledger, never per-exchange quota.
    require(current_run_identity() && resume(frame) == 1, "RAM service fresh continuation");
    ram_finish_execution(1);
}
[[nodiscard]] auto ram_resume_caller(U64 ticket) -> bool {
    auto &saved = ram_caller_wait;
    if (ram_state != RamState::command || !ram_command_valid() || ram_command->caller_disabled ||
        root() != kernel_root || active != L::domain_count || !irq_off() || timer_armed || saved_rsp ||
        program.running() || !saved.context || !saved.authority || !ticket || ticket != saved.ticket ||
        !saved.authority->ready_owner(registry, ram_command->caller, saved.authority->epoch()) ||
        !saved.context->call_frame(*domains[0].contract, image_sites(0).call_pc) ||
        !saved.context->call_frame(saved.authority->contract(), image_sites(0).call_pc) || saved.remaining == 0 ||
        saved.ticks >= 128 || saved.remaining != 128 - saved.ticks ||
        saved.endpoint.slot() != ram_command->caller_endpoint.slot() ||
        saved.endpoint.generation() != ram_command->caller_endpoint.generation() ||
        saved.launch[2] != saved.endpoint.slot() || saved.launch[3] != saved.endpoint.generation() ||
        saved.launch[0] != saved.authority->source_phase() || saved.authority->transaction() != 0 ||
        saved.authority->root() != domains[0].tables->root() || saved.authority->owned_arena() != arena ||
        saved.authority->role() != SelectedRunAuthority::Role::client || mailbox->state() != ipc::State::replied)
        return false;
    const auto completion = mailbox->consume(ram_command->caller, ipc::Phase::completion, saved.endpoint, ticket);
    if (!completion || completion->outcome() != ipc::Outcome::replied)
        return false; // Never translate post-COMMIT uncertainty to cancelled.
    launch = saved.launch;
    selected_client = 0;
    selected_role = SelectedRunAuthority::Role::client;
    selected_phase = ipc::Phase::request;
    transaction = 0;
    run_authority.emplace(*saved.authority);
    timer_owner = ram_command->caller;
    timer_owner_epoch = timer_epoch = saved.authority->epoch();
    timer_initial = 128;
    const auto frame = restore_parked_run(saved);
    auto *words = reinterpret_cast<U64 *>(frame);
    words[14] = 0;
    words[11] = completion->value();
    saved.clear();
    activate_parked_run(0);
    require(current_run_identity(), "RAM caller original quota authority");
    timer_armed = true;
    require(timer_arm() && resume(frame) == 1, "RAM caller completion continuation");
    ram_finish_execution(0);
    return true;
}
// Disable execution first, but keep both original registry incarnations until
// the exact pending receipt is consumed. This is settlement, not caller revival.
auto ram_settle_caller() -> void {
    require(ram_command_valid() && root() == kernel_root && active == L::domain_count && !timer_armed,
            "RAM settlement identities");
    ram_command->caller_disabled = true;
    if (mailbox->state() == ipc::State::pending || mailbox->state() == ipc::State::delivered)
        require(mailbox->cancel(ipc::Phase::inactive), "RAM transport cancellation");
    if (mailbox->state() == ipc::State::replied || mailbox->state() == ipc::State::cancelled) {
        require(ram_caller_wait.ticket != 0, "RAM unsettled receipt ticket");
        const auto receipt = mailbox->consume(
            ram_command->caller, ipc::Phase::completion, ram_command->caller_endpoint, ram_caller_wait.ticket);
        require(receipt.has_value(), "RAM exact original receipt settlement");
    }
    require((mailbox->state() == ipc::State::idle || mailbox->state() == ipc::State::consumed) && mailbox->scrubbed() &&
                mailbox->revoke(ipc::Phase::inactive),
            "RAM revoke settled transport");
    ram_caller_wait.clear();
    require(retire(0), "RAM retired caller scrub");
}
auto ram_reset() -> void {
    scratchpad_discard(); // No candidate can cross a reset or a new incarnation.
    require(ram_state == RamState::poisoned && ram_lifetime_valid(), "RAM authenticated reset only");
    const bool uncertain = ram_command && ram_command->framing.commit_delivered() &&
                           ram_command->framing.outcome() != RamFileFraming::Outcome::committed &&
                           ram_command->framing.outcome() != RamFileFraming::Outcome::rejected;
    if (ram_command && domains[0].handle)
        ram_settle_caller();
    else if (domains[0].handle)
        require(retire(0), "RAM startup caller scrub");
    ram_service_wait.clear();
    ram_clear(ram_lifetime);
    require(retire(1) && frames.used() == 0 && mailbox->revoked(), "RAM reset full reclamation");
    ram_clear(ram_command);
    ram_state = RamState::absent;
    Serial::text(uncertain ? std::string_view{"AURORA_RAM_FILE_RESET: outcome=indeterminate data_lost=1\r\n"}
                           : std::string_view{"AURORA_RAM_FILE_RESET: outcome=reset data_lost=1\r\n"});
}
[[nodiscard]] auto ram_start() -> bool {
    require(ram_state == RamState::absent && !ram_lifetime && !ram_command && !ram_service_wait.context && mailbox &&
                mailbox->revoked() && frames.used() == 0,
            "RAM absent lifetime");
    const auto epoch = ram_mint_epoch();
    if (!epoch || ram_generation_watermark == UINT64_MAX)
        return false;
    if (create(0) != 0)
        return false;
    if (create(1) != 1) {
        require(retire(0), "RAM partial creation rollback");
        return false;
    }
    std::array<U64, 4> backing{};
    for (unsigned i = 0; i < 4; ++i)
        backing[i] = *frames.address(*domains[1].stacks[i]);
    ram_lifetime.emplace(RamLifetime{
        *domains[1].handle, *domains[1].contract, domains[1].tables->root(), 1, ++ram_generation_watermark, backing});
    ram_state = RamState::booting;
    ram_launch(1, 1, *epoch);
    if (ram_state == RamState::poisoned) {
        ram_reset();
        return false;
    }
    require(ram_service_wait.context && ram_lifetime_valid(), "RAM startup READY parked");
    require(retire(0), "RAM startup reservation retired");
    ram_state = RamState::idle;
    return true;
}
// Shared scenario-free exchange mechanism; fixture selection stays in its caller.
auto ram_exchange_commands() -> void {
    while (ram_caller_wait.context && !ram_command->caller_disabled && ram_state != RamState::poisoned) {
        const auto epoch = ram_mint_epoch();
        if (!epoch) {
            ram_command->caller_disabled = true;
            break;
        }
        require(ram_lifetime_valid() && ram_command_valid() && ram_service_wait.context &&
                    ram_service_wait.context->call_frame(ram_lifetime->contract, image_sites(1).serve_pc),
                "RAM pre-delivery continuation authority");
        const auto request = mailbox->receive(
            ram_command->service, ipc::Phase::service, ram_command->service_endpoint, ram_caller_wait.ticket);
        require(request && request->second() == 0 && ram_command->framing.delivered(request->first()),
                "RAM exact one-shot delivery");
        ram_command->delivered = true;
        ram_resume_service(0, request->first(), *epoch);
        if (ram_state == RamState::poisoned)
            break;
        require(ram_service_wait.context && mailbox->state() == ipc::State::replied, "RAM parked before caller reply");
        // Exercise caller loss with the real pending receipt. DATA #2 means
        // the unchanged caller already accumulated DATA #1 in its private result.
        if (ram_commands == 2 &&
            ((scratchpad_probe == '1' && ram_command->framing.count() == 2) ||
             (scratchpad_probe == '2' && ram_command->framing.data_count() == 2) ||
             (scratchpad_probe == '3' && ram_command->framing.outcome() == RamFileFraming::Outcome::committed))) {
            ram_command->caller_disabled = true;
            break;
        }
        if (fixture == Fixture::ram_settlement &&
            ram_command->framing.outcome() == RamFileFraming::Outcome::committed) {
            // Dispose execution before consuming the committed receipt. Its
            // original identity remains alive solely for the settlement below.
            ram_command->caller_disabled = true;
            break;
        }
        const auto ticket = ram_caller_wait.ticket;
        require(!ram_resume_caller((ticket == UINT64_MAX ? ticket - 1 : ticket + 1)) && ram_resume_caller(ticket),
                "RAM exact reply wake");
    }
}
[[nodiscard]] auto ram_command_run(U64 scenario, RamFileFraming::Right right) -> bool {
    require(ram_state == RamState::idle && ram_lifetime_valid() && ram_service_wait.context && !ram_command &&
                !domains[0].handle && !ram_caller_wait.context && mailbox->revoked(),
            "RAM command idle exclusivity");
    if (ram_commands >= 64)
        return false;
    if (fixture == Fixture::ram_epochs && ram_commands == 1) {
        // Withhold every intermediate unused identity, monotonically. Never
        // decrease/reset a counter or admit a fabricated run. Both final tokens
        // still come from ram_mint_epoch and all real authority checks execute.
        require(timer_epoch_watermark < UINT64_MAX - 2, "RAM near-max fixture monotonicity");
        timer_epoch_watermark = UINT64_MAX - 2;
    }
    const auto cleanup = ram_mint_epoch(), caller_epoch = ram_mint_epoch();
    if (!cleanup || !caller_epoch)
        return false; // No command admission, and no change to service contents.
    if (create(0) != 0)
        return false;
    if (!mailbox->bind(*domains[0].handle, *domains[1].handle)) {
        require(retire(0), "RAM refused command reclaim");
        return false;
    }
    ram_command.emplace(*domains[0].handle,
                        *domains[1].handle,
                        *mailbox->endpoint(*domains[0].handle),
                        *mailbox->endpoint(*domains[1].handle),
                        *cleanup,
                        right);
    ++ram_commands;
    Serial::text("AURORA_RAM_FILE_BEGIN: phase=");
    Serial::number(scenario);
    Serial::text(" service=");
    Serial::number(ram_lifetime->generation);
    Serial::text(" caller=");
    Serial::number(*registry.incarnation(*domains[0].handle));
    Serial::text(" root=");
    Serial::number(ram_lifetime->root);
    Serial::text("\r\n");
    if (fixture == Fixture::ram_epochs && ram_commands == 2) {
        require(*cleanup == UINT64_MAX - 1 && *caller_epoch == UINT64_MAX && timer_epoch_watermark == UINT64_MAX,
                "RAM exact final command identities");
        Serial::text("AURORA_RAM_FILE_EPOCH_PROBE: cleanup=");
        Serial::number(*cleanup);
        Serial::text(" ceiling=");
        Serial::number(ram_epoch_ceiling);
        Serial::text("\r\n");
    }
    ram_state = RamState::command;
    ram_launch(0, scenario, *caller_epoch);
    ram_exchange_commands();
    if (ram_state == RamState::poisoned) {
        ram_reset();
        return false;
    }
    const bool completed = ram_command->framing.state() == RamFileFraming::State::terminal;
    const bool disposed_commit = fixture == Fixture::ram_settlement && completed && ram_command->caller_disabled &&
                                 mailbox->state() == ipc::State::replied &&
                                 ram_command->framing.outcome() == RamFileFraming::Outcome::committed;
    const auto value = program.value();
    const auto event = program.event();
    const auto exchanges = ram_command->framing.count();
    if (!completed)
        require(!ram_command->framing.commit_delivered(), "RAM unresolved COMMIT cannot abort");
    ram_settle_caller();
    if (!completed) {
        require(ram_command->framing.begin_abort(), "RAM exclusive abort transition");
        ram_state = RamState::aborting;
        ram_resume_service(1, 0, ram_command->cleanup_epoch);
        if (ram_state == RamState::poisoned) {
            ram_reset();
            return false;
        }
        require(ram_service_wait.context && ram_command->framing.state() == RamFileFraming::State::aborted,
                "RAM source ABORTED cleanup acknowledgement");
    }
    ram_clear(ram_command);
    ram_state = RamState::idle;
    require(frames.used() == 4 && !domains[0].handle && !ram_caller_wait.context && mailbox->revoked(),
            "RAM healthy idle retained service");
    Serial::text("AURORA_RAM_FILE_COMMAND: phase=");
    Serial::number(scenario);
    Serial::text(" exchanges=");
    Serial::number(exchanges);
    Serial::text(" result=");
    Serial::number(value);
    Serial::text(completed ? std::string_view{" outcome=completed retained=1\r\n"}
                           : std::string_view{" outcome=aborted retained=1\r\n"});
    if (disposed_commit) {
        Serial::text("AURORA_RAM_FILE_SETTLED: caller_disabled=1 committed=1 consumed_once=1 retained=1\r\n");
        return true;
    }
    return (scenario == 15 || scenario == 16) ? event == ProgramEvent::bounds
                                              : event == ProgramEvent::returned && value == 42;
}
// Keep fixture dispatch explicit: byte-enum jump tables are intentionally not
// in the stack checker's admitted full-width bounded-switch instruction set.
[[gnu::noinline]] auto ram_fixture_is(Fixture expected) -> bool {
    return fixture == expected;
}
// The baseline row runs the former fixture-free image's scenario list.
auto run_ram_baseline() -> void {
    using Right = RamFileFraming::Right;
    constexpr std::array<U64, 25> scenarios{0, 1, 2,  3,  4,  7,  4,  15, 4,  16, 2, 5, 6,
                                            8, 9, 13, 14, 10, 14, 11, 14, 12, 14, 5, 6};
    const auto generation = ram_lifetime->generation;
    for (const auto scenario : scenarios) {
        const bool write = scenario == 1 || scenario == 3 || scenario == 5 || scenario == 7 || scenario == 8 ||
                           scenario == 13 || (scenario >= 10 && scenario <= 12) || scenario == 15 || scenario == 16;
        require(ram_command_run(scenario, write ? Right::replace : Right::read), "RAM compiled command result");
        require(ram_lifetime->generation == generation, "RAM writer retirement retained incarnation");
    }
}
auto run_ram_file() -> void {
    mailbox.emplace(registry);
    const bool baseline = ram_fixture_is(Fixture::ram_baseline);
    if (!baseline)
        select_fixture(Fixture::ram_service_fault, Fixture::ram_root);
    require(ram_start(), "RAM initial service startup");
    using Right = RamFileFraming::Right;
    if (baseline) {
        run_ram_baseline();
    } else if (ram_fixture_is(Fixture::ram_settlement)) {
        require(ram_command_run(13, Right::replace) && ram_command_run(14, Right::read),
                "RAM disposed writer exact fresh reader");
    } else if (ram_fixture_is(Fixture::ram_caller_budget) || ram_fixture_is(Fixture::ram_epochs)) {
        require(ram_command_run(13, Right::replace), "RAM saved before caller exhaustion");
        require(!ram_command_run(1, Right::replace) && ram_state == RamState::idle && frames.used() == 4,
                "RAM caller exhaustion cleanup retained");
        if (ram_fixture_is(Fixture::ram_epochs))
            require(!ram_command_run(14, Right::read), "RAM exhausted identities deny new command");
        else
            require(ram_command_run(14, Right::read), "RAM caller budget preserves prior file");
    } else if (ram_fixture_is(Fixture::ram_service_budget) || ram_fixture_is(Fixture::ram_abort_budget)) {
        require(!ram_command_run(ram_fixture_is(Fixture::ram_abort_budget) ? 7 : 1, Right::replace) &&
                    ram_state == RamState::absent && frames.used() == 0,
                "RAM service budget reset");
        require(ram_start() && ram_command_run(0, Right::read), "RAM budget reset fresh missing");
    } else if (ram_fixture_is(Fixture::ram_pending)) {
        require(ram_fixture_injected && ram_command_run(0, Right::read), "RAM pending startup drain");
    } else if (ram_fixture_is(Fixture::ram_service_fault)) {
        const auto original_backing = ram_lifetime->backing;
        for (U64 round = 0; round < 2; ++round) {
            const auto old_owner = ram_lifetime->owner;
            const auto old_generation = ram_lifetime->generation;
            require(ram_command_run(round == 0 ? 1 : 3, Right::replace), "RAM stored before repeated service fault");
            require(!ram_command_run(round == 0 ? 2 : 4, Right::read) && ram_state == RamState::absent &&
                        frames.used() == 0,
                    "RAM repeated fault scrub");
            require(ram_start() && ram_lifetime->backing == original_backing &&
                        ram_lifetime->generation > old_generation && !registry.index(old_owner),
                    "RAM natural reused backing cannot revive old owner");
            Serial::text("AURORA_RAM_FILE_REUSE: generation=");
            Serial::number(ram_lifetime->generation);
            Serial::text(" pages=4 old_owner_denied=1\r\n");
            require(ram_command_run(0, Right::read), "RAM repeated reset fresh missing");
        }
    } else {
        const bool commit_fault = ram_fixture_is(Fixture::ram_commit_fault);
        require(commit_fault && ram_command_run(commit_fault ? 5 : 1, Right::replace),
                "RAM stored before service fault");
        require(!ram_command_run(commit_fault ? 1 : 2, commit_fault ? Right::replace : Right::read) &&
                    ram_state == RamState::absent && frames.used() == 0,
                "RAM source service fault reset");
        require(ram_start() && ram_command_run(0, Right::read), "RAM fresh missing after reset");
    }
    require(ram_state == RamState::idle && ram_lifetime_valid() && mailbox->revoked(), "RAM quiescent exit");
    ram_service_wait.clear();
    ram_clear(ram_lifetime);
    require(retire(1) && frames.used() == 0 && !domains[0].handle && !domains[1].handle && !ram_command,
            "RAM complete exit scrub");
    ram_state = RamState::absent;
    mailbox.reset();
    Serial::text("AURORA_UEFI_RAM_FILE_OK: used=0 volatile=1\r\n");
}
