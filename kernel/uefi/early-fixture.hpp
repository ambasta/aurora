#pragma once
// Included only by the early-fixture image. Its loader-stage faults inject before
// ExitBootServices, while OVMF's terminal driver still owns the UART, so the
// selector arrives in a QEMU fw_cfg file (fw-cfg-fixture.hpp) read at loader
// entry instead of a serial byte. The loader copies the one admitted value into
// the handoff's fixture word; the payload rejects any handoff whose word is
// outside the family.
#ifndef AURORA_EARLY_FIXTURE
#error "The fw_cfg selector belongs only to the early-fixture image"
#endif
#include "fw-cfg-fixture.hpp"
#include <cstdint>
#include <optional>
namespace aurora::uefi::early {
using Fixture = fw_cfg::Fixture;
inline constexpr auto first = Fixture::early_stale;
inline constexpr auto last = Fixture::early_nx;
[[nodiscard]] constexpr auto admitted(std::uint64_t value) -> bool {
    return value >= static_cast<unsigned>(first) && value <= static_cast<unsigned>(last);
}
[[nodiscard]] constexpr auto selected(std::uint64_t value, Fixture fixture) -> bool {
    return admitted(value) && value == static_cast<unsigned>(fixture);
}
class FwCfg final {
public:
    [[nodiscard]] static auto read() -> std::optional<Fixture> {
        return fw_cfg::FwCfg::read(first, last);
    }
};
} // namespace aurora::uefi::early
