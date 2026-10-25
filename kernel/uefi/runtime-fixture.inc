// Only fixture images accept a boot-time selector; ordinary images omit this code.
#include "fixture-selector.inc"
Fixture fixture{};
auto select_fixture(Fixture first, Fixture last) -> void {
    const auto selected = read_fixture(first, last);
    require(selected.has_value(), "fixture selector outside image family");
    fixture = *selected;
}
#ifdef AURORA_RUNTIME_CONTROL_FIXTURE
// Probe numbers follow the table order and the UEFI_USER_PROBES dispatch in
// user-image-entry.S: code, stack, kernel, window, write, nx, return, unknown,
// syscall, sysenter. Zero runs the program normally.
auto runtime_probe() -> U64 {
    const auto first = static_cast<unsigned>(Fixture::runtime_code);
    const auto value = static_cast<unsigned>(fixture);
    return value >= first && value <= static_cast<unsigned>(Fixture::runtime_sysenter) ? value - first + 1 : 0;
}
#endif
#ifdef AURORA_IPC_PROBES
// Selectors for the IPC_PROBES dispatch in ipc-user-entry.S: mmio 1, softint 2,
// fpu 3, register loop 4, peer code read 5, unknown UD2 before the exit 6. Each
// row family places its probes in the one domain its former image did: the
// budget service, the dispatcher's peer client, or the user client. The
// faulting probes are fatal on their first entry; the register loops run on
// the phase their former images tested. Zero runs the program normally, as
// every IPC and resume row does.
auto ipc_probe(unsigned index, U64 source_phase) -> U64 {
    switch (fixture) {
    case Fixture::budget_mmio:
        return index == 1 ? 1 : 0;
    case Fixture::budget_softint:
        return index == 1 ? 2 : 0;
    case Fixture::budget_fpu:
        return index == 1 ? 3 : 0;
    case Fixture::budget_context:
        return index == 1 && source_phase == 1 ? 4 : 0;
    case Fixture::dispatch_peer_code:
        return index == 2 ? 5 : 0;
    case Fixture::user_context:
        return index == 0 && source_phase == 0 ? 4 : 0;
    case Fixture::user_unknown:
        return index == 0 ? 6 : 0;
    default:
        return 0;
    }
}
#endif
#if defined(AURORA_IPC_FIXTURE) || defined(AURORA_SNAPSHOT_FIXTURE) || defined(AURORA_PROGRAM_FIXTURE)
// Hostile-client equivalents: alter the trapped exit exactly as the former
// per-fault client images did, before the kernel reports or validates it.
// Returns true when the client must resume and raise a real #UD instead.
auto hostile_exit_fixture(U64 vector, [[maybe_unused]] U64 &pc, U64 frame, [[maybe_unused]] U64 &result) -> bool {
    if (vector != 129)
        return false;
    // Frame words: 6 r9, 7 r8, 8 rdi, 9 rsi, 11 rdx, 14 rax, 17 rip.
    auto *words = reinterpret_cast<U64 *>(frame);
    const bool client = active == 0 && selected_phase == ipc::Phase::request;
    const bool service = active == 1 && selected_phase == ipc::Phase::service;
    bool resume = false;
#ifdef AURORA_IPC_FIXTURE
    if (client && fixture == Fixture::ipc_owner)
        words[11] ^= 1; // claimed slot
    if (client && fixture == Fixture::ipc_version)
        words[9] = 2;
    if (client && fixture == Fixture::ipc_phase)
        words[8] = 1;
    if (service && fixture == Fixture::ipc_transaction)
        ++words[7];
    // Inside the return-site ud2, never a registered site: both the trapped RIP
    // and dispatch's copy of it, as a real INT 0x81 from elsewhere would leave.
    if (client && fixture == Fixture::ipc_site)
        pc = ++words[17];
    resume = client && fixture == Fixture::ipc_unknown;
#endif
#ifdef AURORA_SNAPSHOT_FIXTURE
    if (client && fixture == Fixture::snapshot_owner)
        words[11] ^= 1;
    // The reply travels in rax: both the frame word and dispatch's copy of it.
    if (service && fixture == Fixture::snapshot_reply_byte)
        result = words[14] ^= 0x100;
    if (service && fixture == Fixture::snapshot_reply_reserved)
        result = words[14] |= U64{1} << 63;
#endif
#ifdef AURORA_PROGRAM_FIXTURE
    if (client && fixture == Fixture::program_ordinal)
        ++words[6];
    if (client && fixture == Fixture::program_owner)
        words[11] ^= 1;
    if (service && fixture == Fixture::program_transaction)
        ++words[7];
    resume = client && fixture == Fixture::program_unknown;
#endif
    // Resume the client at bad_entry, the wrapper's ud2 just after the return
    // site, so it raises a real #UD from an address that is no registered site.
    if (resume)
        words[17] += 2;
    return resume;
}
#endif
#if defined(AURORA_OWNED_TEXT) && !defined(AURORA_CONSOLE_REGION)
auto text_fixture_entry(U64 *words) -> void {
    if (fixture == Fixture::text_site)
        ++words[17];
    if (fixture == Fixture::text_region)
        words[6] ^= 1;
}
auto text_fixture_owner(std::size_t operation, aurora::hosted::bytes::NativeOwner &owner) -> void {
    static aurora::hosted::bytes::NativeOwner stale;
    if (fixture != Fixture::text_stale)
        return;
    if (operation == 4)
        stale = owner;
    if (operation == 3 && stale.success) {
        require(stale.allocation != owner.allocation && stale.region == owner.region,
                "text stale fixture after committed resize");
        owner = stale;
        Serial::text("AURORA_OWNED_TEXT_STALE: committed-resize\r\n");
    }
}

#endif
#if defined(AURORA_BLOCKING_CALL) && !defined(AURORA_FILE_CALL)
auto call_fixture_entry(U64 *words) -> void {
    if (fixture == Fixture::call_owner)
        words[9] ^= 1;
    if (fixture == Fixture::call_site)
        ++words[17];
}
#endif

#ifdef AURORA_FILE_CALL
// Inject only in the fixture image; ordinary calls carry their normal operation.
unsigned file_wc_probes{}, file_crc_probes{};
bool file_byte_probe_used{};
U64 file_probe{};
auto file_fixture_phase(unsigned index, U64 operation, U64 offset) -> U64 {
    if (index == 0) {
        file_probe = 0;
        if (operation == 16) {
            if (!file_byte_probe_used)
                file_probe = fixture == Fixture::file_fault ? 1 : 8;
            file_byte_probe_used = true;
            return operation + file_probe;
        }
        auto &probes = operation == 48 ? file_crc_probes : file_wc_probes;
        if (fixture == Fixture::file_fault && probes == 0)
            file_probe = 33;
        if (fixture == Fixture::file_budget && probes < 4)
            file_probe = 34 + probes;
        if (probes < 4)
            ++probes;
        return file_probe ? file_probe + (operation == 48 ? 16 : 0) : operation;
    }
    if (file_probe == 1 || (file_probe == 33 && offset == 2))
        return 4;
    if (file_probe == 35 && offset == 2)
        return 5;
    return operation;
}
#endif
