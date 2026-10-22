// Included only by explicitly selected fixture images, inside their private
// namespace. Ordinary images have neither serial selector nor injection state.
enum class Fixture : unsigned char {
#define AURORA_FIXTURE(name, mode, image, value) name = value,
#include "runtime-fixtures.inc"
#undef AURORA_FIXTURE
};
[[nodiscard]] inline auto read_fixture(Fixture first, Fixture last) -> std::optional<Fixture> {
    hardware::Serial::text("AURORA_FIXTURE_READY\r\n");
    // Keep the existing host smoke deadline; an absent byte grants no authority.
    while ((hardware::Io::read(0x3fd) & 1) == 0)
        asm volatile("pause");
    const auto value = hardware::Io::read(0x3f8);
    if (value < static_cast<unsigned char>(first) || value > static_cast<unsigned char>(last))
        return std::nullopt;
    return static_cast<Fixture>(value);
}
