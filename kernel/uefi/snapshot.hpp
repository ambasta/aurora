#pragma once

#include "../pages.hpp"
#include "../snapshot.hpp"

namespace aurora::uefi {

enum class SnapshotProducerCase {
    normal,
    invalid_selector,
    quota,
    pages
};

// Called only under the verified supervisor root with no active domain. The
// existing pool and static region outlive all synchronous producer ownership.
[[nodiscard]] ipc::SnapshotPublication prepare_snapshot(std::uint64_t arena,
                                                        memory::PhysicalPages &pool,
                                                        ipc::SnapshotSlot &slot,
                                                        SnapshotProducerCase scenario) noexcept;

} // namespace aurora::uefi
