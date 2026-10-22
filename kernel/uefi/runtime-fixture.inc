// Only fixture images accept a boot-time selector; ordinary images omit this code.
#include "fixture-selector.inc"
Fixture fixture{};
auto select_fixture(Fixture first, Fixture last) -> void {
    const auto selected = read_fixture(first, last);
    require(selected.has_value(), "fixture selector outside image family");
    fixture = *selected;
}
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
