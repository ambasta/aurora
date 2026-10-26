// Saved transport state is shared; each caller retains its distinct authority checks.
class ParkedRun final {
public:
    constexpr ParkedRun() = default;
#ifndef AURORA_USER_RESUME
    // Program callers cannot be duplicated. The separate three-domain resume
    // fixture retains its existing deliberate foreign-owner rejection copy.
    ParkedRun(const ParkedRun &) = delete;
    auto operator=(const ParkedRun &) -> ParkedRun & = delete;
    ParkedRun(ParkedRun &&) = delete;
    auto operator=(ParkedRun &&) -> ParkedRun & = delete;
#endif
    std::optional<ServiceContext> context;
#ifdef AURORA_USER_RESUME
    std::optional<RunAuthority> authority;
#else
    std::optional<ProgramRunAuthority> authority;
    std::optional<user::DomainHandle> service;
    ipc::Endpoint endpoint;
    U64 ticket{};
#ifdef AURORA_CONSOLE_REGION
    // The console-region rows' parked read; the file-call rows use the fields above.
    std::optional<user::DomainHandle> owner;
    U64 root{}, region{}, generation{}, epoch{};
    unsigned initial{};
#endif
#endif
    std::array<U64, launch_words> launch{};
    unsigned remaining{}, ticks{}, resumes{}, compiled{}, contexts{};
#ifdef AURORA_CONSOLE_REGION
    std::optional<console::RawSample> ready;
#endif
    [[nodiscard]] auto empty() const -> bool {
        if (context || authority || remaining || ticks || resumes || compiled || contexts)
            return false;
#ifndef AURORA_USER_RESUME
        if (service || endpoint.slot() || endpoint.generation() || ticket)
            return false;
#ifdef AURORA_CONSOLE_REGION
        if (owner || root || region || generation || epoch || initial || ready)
            return false;
#endif
#endif
        for (const auto word : launch)
            if (word)
                return false;
        return true;
    }
    auto clear() -> void {
        std::destroy_at(this);
        auto *bytes = reinterpret_cast<volatile std::byte *>(this);
        for (std::size_t i = 0; i < sizeof(ParkedRun); ++i)
            bytes[i] = std::byte{0};
        std::construct_at(this);
    }
};
