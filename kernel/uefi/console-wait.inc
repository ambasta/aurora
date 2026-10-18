// Shared supervisor polling wake. Policy is provided by the active adapter.
bool console_waiting{};
U64 console_wait_stack{},console_wakes{},console_expected_wake{};
extern const std::byte program_poll_begin asm("uefi_program_poll_begin");
extern const std::byte program_poll_end asm("uefi_program_poll_end");

[[nodiscard]] auto program_boundary() -> bool;
[[nodiscard]] auto program_poll_policy() -> bool;
[[nodiscard]] auto program_console_interrupt(U64 vector,U64 error,U64 pc,U64 cs,U64 frame) -> bool {
    if (vector!=64 || !program_poll_policy()) return false;
    require(console_waiting && !timer_armed && !timer_owner
        && !timer_draining && active==L::domain_count && saved_rsp==0 && !program.running()
        && root()==kernel_root && irq_off() && error==0 && cs==8
        && console_wakes<console_expected_wake && console_expected_wake-console_wakes==1
        && ConsoleWakeContext::frame_valid(frame,arena),"program console interrupt origin");
    const Bytes captured{view(frame,ConsoleWakeContext::byte_count)};
    std::array<U64,ConsoleWakeContext::word_count> words{};
    for (std::size_t i=0;i<words.size();++i) words[i]=captured.get(i*8);
    require(pc==words[17] && ConsoleWakeContext::valid(words,frame,arena,
        reinterpret_cast<U64>(&program_poll_begin),reinterpret_cast<U64>(&program_poll_end),console_wait_stack)
        && timer_acknowledge(),"program console frame authority");
    ++console_wakes;
    return true;
}
__attribute__((noinline)) auto program_wait_sample() -> void {
    require(program_poll_policy() && program_boundary() && console_wakes!=UINT64_MAX,"program poll boundary");
    console_expected_wake=console_wakes+1;
    console_waiting=true;
    require(LocalApicTimerIo::arm(1250000),"program poll arm");
    asm volatile("mov %%rsp,%0":"=m"(console_wait_stack)::"memory");
    require(console_wait_stack%8==0 && console_wait_stack<=arena+Handoff::stack_top
        && ConsoleWakeContext::frame_valid((console_wait_stack&~U64{15})-ConsoleWakeContext::byte_count,arena),
        "program poll stack ownership");
    asm volatile(".global uefi_program_poll_begin\nuefi_program_poll_begin:\nsti\nhlt\ncli\n"
        ".global uefi_program_poll_end\nuefi_program_poll_end:":::"memory");
    console_waiting=false; console_wait_stack=0;
    require(console_wakes==console_expected_wake && program_boundary(),"program poll completion");
}
