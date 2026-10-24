// Included only by the production composition's program console. The protected
// program console stays the only owner of COM1 input and of the LAPIC timer and
// remains the command surface. This adapter copies the bytes its Console session
// actually wrote into a cell grid and asks the separately compiled Aurora
// terminal painter to render changed cells through one sealed DisplaySession
// loan. It reads no input, arms no timer and never runs inside a protected run.
std::optional<FramebufferAdmission> terminal_graphics;
constinit terminal::Grid terminal_grid;
bool terminal_painting{};
// One cell is 54 background, at most 35 glyph and five cursor stores.
constexpr unsigned terminal_cell_store_limit = 94;
unsigned terminal_cell_stores{};
extern "C" auto __au_runtime_terminal_paint(const void *) -> U64;

// Per-store state: the private kernel root, interrupts off, no domain, run,
// armed timer, poll wait or IPC phase, and the kernel stack. The LAPIC and the
// complete paired mapping tree are rechecked once when each paint opens.
[[nodiscard]] auto terminal_quiet() -> bool {
    const auto current = stack();
    return terminal_graphics.has_value() && root() == kernel_root && irq_off() && active == L::domain_count &&
           saved_rsp == 0 && !program.running() && !timer_armed && !timer_draining && !timer_owner &&
           !run_authority && selected_phase == ipc::Phase::inactive && !console_waiting && console_wait_stack == 0 &&
           current % 8 == 0 && current >= arena + Handoff::stack_bottom && current < arena + Handoff::stack_top;
}
class TerminalDisplayTransport final {
public:
    static auto identity() -> U64 {
        return kernel_root;
    }
    static auto width() -> U64 {
        return terminal_graphics->geometry().width();
    }
    static auto height() -> U64 {
        return terminal_graphics->geometry().height();
    }
    static auto pixel(U64 x, U64 y, std::uint8_t red, std::uint8_t green, std::uint8_t blue) -> U64 {
        require(terminal_painting && terminal_quiet() && terminal_cell_stores < terminal_cell_store_limit,
                "graphical terminal store boundary");
        ++terminal_cell_stores;
        const auto offset = terminal_graphics->geometry().pixel_offset(x, y);
        require(offset.has_value(), "graphical terminal pixel coordinates");
        const auto page = FramebufferAdmission::virtual_address + (*offset & ~U64{4095});
        require((PageTables{kernel_root, static_cast<std::size_t>(handoff->get(96))}.entry(page) & ~0x60ULL) ==
                    terminal_graphics->mapping(page),
                "graphical terminal pixel mapping");
        return static_cast<U64>(FramebufferPixels<FramebufferMmio>::pixel(*terminal_graphics, x, y, red, green, blue));
    }
};
class TerminalDisplayPlatform final {
public:
    [[nodiscard]] static auto quiet() -> bool {
        return terminal_quiet();
    }
    [[noreturn]] static auto fail() -> void {
        stop("graphical terminal display authority");
    }
};
using TerminalDisplay = display::Session<TerminalDisplayTransport, TerminalDisplayPlatform>;
// The exact six-qword record the paint bridge forwards (checked against the
// compiler's ABI facts when the bridge is rendered).
class TerminalPaintArgument final {
public:
    const void *grant;
    U64 generation, width, height, position, glyph;
};
static_assert(sizeof(TerminalPaintArgument) == 48 && offsetof(TerminalPaintArgument, position) == 32 &&
              offsetof(TerminalPaintArgument, glyph) == 40);
[[nodiscard]] auto terminal_mapping() -> bool {
    return terminal_graphics && interrupt_admission &&
           PageTables{kernel_root, static_cast<std::size_t>(handoff->get(96))}.verify_graphical(
               arena, *handoff, &*interrupt_admission, &*terminal_graphics);
}
// Install the framebuffer once, at the quiescent console start, after the
// shared timer admission mapped the LAPIC page.
__attribute__((noinline)) auto terminal_install() -> void {
    require(program_boundary() && !terminal_graphics && !terminal_painting && interrupt_admission,
            "graphical terminal install boundary");
    auto restored = FramebufferPayload::restore_terminal(arena, *interrupt_admission);
    require(restored.has_value(), "graphical terminal framebuffer admission");
    const auto &geometry = restored->geometry();
    // The painter's 80x24 viewport of 6x9 cells at (32,32).
    require(geometry.width() >= 32 + terminal::Grid::columns * 6 && geometry.height() >= 32 + terminal::Grid::rows * 9,
            "graphical terminal viewport geometry");
    PageTables tables{kernel_root, static_cast<std::size_t>(handoff->get(96))};
    require(tables.install_framebuffer(*restored), "graphical terminal leaf installation");
    asm volatile("mov %0,%%cr3" : : "r"(kernel_root) : "memory");
    terminal_graphics = restored;
    require(terminal_mapping() && program_boundary(), "graphical terminal paired mapping");
    Serial::text("AURORA_GRAPHICAL_TERMINAL_READY: base=");
    Serial::number(geometry.base());
    Serial::text(" width=");
    Serial::number(geometry.width());
    Serial::text(" height=");
    Serial::number(geometry.height());
    Serial::text(" pitch=");
    Serial::number(geometry.pitch());
    Serial::text(" format=");
    Serial::number(geometry.format());
    Serial::text(" columns=80 rows=24\r\n");
}
// Paint changed cells. Called between Console samples (before the poll wait)
// and after each Console turn releases its grant; never during a run. Unless
// `complete`, painting yields as soon as a received byte waits, so rendering
// never holds input past the UART FIFO; the remaining cells stay dirty. The
// result reports whether it yielded to a waiting byte.
__attribute__((noinline)) auto terminal_present(bool complete = false) -> bool {
    if (!terminal_grid.any_dirty())
        return false;
    require(!terminal_painting && program_boundary() && terminal_quiet() && terminal_mapping(),
            "graphical terminal paint boundary");
    const auto argument = TerminalDisplay::open();
    terminal_painting = true;
    terminal_grid.prepare();
    bool yielded = false;
    for (unsigned index = 0; index < terminal::Grid::cells; ++index) {
        if (!terminal_grid.dirty(index))
            continue;
        if (!complete && ProgramSerial::input_pending()) {
            yielded = true;
            break;
        }
        const TerminalPaintArgument record{argument.grant,
                                           argument.generation,
                                           argument.width,
                                           argument.height,
                                           index,
                                           terminal_grid.glyph(index)};
        terminal_cell_stores = 0;
        require(__au_runtime_terminal_paint(&record) == 1, "graphical terminal cell paint");
        terminal_grid.commit(index);
    }
    terminal_painting = false;
    require(TerminalDisplay::close(argument, 0) == display::Completion::rendered && terminal_quiet(),
            "graphical terminal paint completion");
    FramebufferMmio::complete();
    return yielded;
}
