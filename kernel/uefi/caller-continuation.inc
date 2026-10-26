// A boot-selected caller owner, not interchangeable Call/RAM protocol authority.
// Service continuations can coexist with this member and remain independent.
[[noreturn]] auto stop(std::string_view reason) -> void;
class CallerContinuation final {
    enum class Kind : unsigned char {
        uninitialized,
        none,
        ordinary,
        ram
    };
    ParkedRun run_;
    Kind kind_{};

    [[nodiscard]] auto initialize(Kind kind) -> bool {
        if (kind_ != Kind::uninitialized || kind == Kind::uninitialized || !run_.empty())
            return false;
        kind_ = kind;
        return true;
    }
    [[nodiscard]] auto ordinary() -> ParkedRun * {
        return kind_ == Kind::ordinary ? &run_ : nullptr;
    }
    [[nodiscard]] auto ram() -> ParkedRun * {
        return kind_ == Kind::ram ? &run_ : nullptr;
    }
    [[nodiscard, gnu::noinline]] auto ordinary_checked() -> ParkedRun & {
        if (!ordinary())
            stop("call owner");
        return run_;
    }
    [[nodiscard, gnu::noinline]] auto ram_checked() -> ParkedRun & {
        if (!ram())
            stop("RAM caller owner");
        return run_;
    }
    [[nodiscard]] auto ordinary_empty() -> bool {
        return ordinary() && run_.empty();
    }
    [[nodiscard]] auto ram_empty() -> bool {
        return ram() && run_.empty();
    }

    friend auto initialize_caller() -> void;
    friend auto call_retire(unsigned) -> bool;
    friend auto call_trap(U64) -> U64;
    friend auto call_envelope(const Bytes &, U64) -> void;
    friend auto call_resume(U64) -> bool;
#ifndef AURORA_PROGRAM_APPEND_CALL
    friend auto call_execute(unsigned, U64, U64, U64) -> void;
#endif
#ifdef AURORA_STORAGE_FIXTURE
    friend auto call_completion_controls(U64) -> void;
    friend auto run_blocking_calls(memory::PhysicalPages &) -> void;
#endif
#ifdef AURORA_FILE_CALL
    friend auto file_service_quiet() -> bool;
    friend auto program_file_call(program::Submission &, bool, bool) -> bool;
#endif
#ifdef AURORA_PROGRAM_APPEND_CALL
    friend class ProgramInputPlatform;
    friend auto program_execute(unsigned, ipc::Phase, U64, U64, U64) -> bool;
    friend auto program_append_call() -> bool;
    friend auto program_cleanup(bool) -> void;
    friend auto append_service_trap(U64) -> U64;
    friend auto append_service_resume(U64, U64) -> bool;
#endif
#ifdef AURORA_RAM_FILE
    friend auto ram_service_admitted() -> bool;
    friend auto ram_active_authority() -> bool;
    friend auto ram_trap(U64) -> U64;
    friend auto ram_launch(unsigned, U64, U64) -> void;
    friend auto ram_resume_service(U64, U64, U64) -> void;
    friend auto ram_resume_caller(U64) -> bool;
    friend auto ram_settle_caller() -> void;
    friend auto ram_reset() -> void;
    friend auto ram_start() -> bool;
    friend auto ram_exchange_commands() -> void;
    friend auto ram_command_run(U64, RamFileFraming::Right) -> bool;
    friend auto scratchpad_empty_caller() -> bool;
    friend auto run_ram_file() -> void;
    friend auto run_ram_scratchpad_console() -> void;
    friend auto scratchpad_restart() -> bool;
#endif
#ifdef AURORA_CALLER_CONTINUATION_TESTING
    friend class CallerContinuationProbe;
#endif

public:
    constexpr CallerContinuation() = default;
    CallerContinuation(const CallerContinuation &) = delete;
    auto operator=(const CallerContinuation &) -> CallerContinuation & = delete;
    CallerContinuation(CallerContinuation &&) = delete;
    auto operator=(CallerContinuation &&) -> CallerContinuation & = delete;
};
