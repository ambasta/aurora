#pragma once
#include "handoff.hpp"
namespace aurora::uefi {
enum class RunStatus {
    exited,
    fault,
    watchdog,
    missing,
    malformed,
    quota,
    unavailable,
    output_failed,
    cancelled
};
class RunResult final {
public:
    RunStatus status = RunStatus::unavailable;
    std::uint64_t value = 0;
};
using ProcessOutput = bool (*)(void *, bool, std::span<const std::byte>);
// A supervisor-only command boundary. The retained service survives return;
// all process mappings are detached from the production console's exact root.
[[nodiscard]] auto run_program(std::uint64_t arena,
                               const Bytes &handoff,
                               std::span<const std::byte> path,
                               std::span<const std::byte> arguments,
                               ProcessOutput output,
                               void *context) -> RunResult;

// Exact production NVMe composition only: admit its readonly mount before the
// first prompt. A valid unavailable mount preserves the boot/console owner.
[[nodiscard]] auto prepare_programs(std::uint64_t arena, const Bytes &handoff) -> bool;

// Private legacy-console policy retained by the same source file owner. These
// copied commands expose only projections/selections, never its saved namespace.
enum class ConsoleOperation : std::uint64_t {
    note_command = 10,
    files_command,
    note_replace,
    files_replace,
    clear
};
enum class ConsoleStatus {
    success,
    unavailable,
    conflict,
    malformed
};
class ConsoleResult final {
public:
    ConsoleStatus status = ConsoleStatus::unavailable;
    std::uint64_t generation = 0, revision = 0;
};
[[nodiscard]] auto console_request(std::uint64_t arena,
                                   const Bytes &handoff,
                                   ConsoleOperation operation,
                                   std::uint64_t expected_generation,
                                   std::uint64_t expected_note_revision,
                                   std::span<const std::byte> request,
                                   std::span<std::byte> response) -> ConsoleResult;

// An inner policy decoder may reject a structurally valid reply. Revoke only
// the observed incarnation; this never starts or replays a service request.
[[nodiscard]] auto reject_program_service(std::uint64_t arena, const Bytes &handoff, std::uint64_t expected_generation)
    -> ConsoleStatus;

// The process image's phase after the payload's own checks: admit the final map
// and boot volume, build the frame allocator and its kernel mappings, run the
// row's frame and export cases, and stop the guest (process.md).
[[noreturn]] auto run_process(std::uint64_t arena, const Bytes &h) -> void;
} // namespace aurora::uefi
