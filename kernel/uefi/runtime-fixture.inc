// Only fixture images accept a boot-time selector; ordinary images omit this code.
enum class Fixture : unsigned char {
#define AURORA_FIXTURE(name, mode, image, value) name = value,
#include "runtime-fixtures.inc"
#undef AURORA_FIXTURE
};
Fixture fixture{};
auto select_fixture(Fixture first, Fixture last) -> void {
    Serial::text("AURORA_FIXTURE_READY\r\n");
    // The existing host smoke deadline bounds a missing selector.
    while ((hardware::Io::read(0x3fd) & 1) == 0)
        asm volatile("pause");
    const auto value = hardware::Io::read(0x3f8);
    require(value >= static_cast<unsigned char>(first) && value <= static_cast<unsigned char>(last),
            "fixture selector outside image family");
    fixture = static_cast<Fixture>(value);
}
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
