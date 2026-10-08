// Included only by the opt-in two-domain program-console adapter.
// One shared timer mapping and one IDT gate; ownership is selected only at a
// fully quiescent private-kernel boundary. No source-language pointer ABI.
using ProgramSerial=Serial; // One shared sticky receive-error latch, including runtime traces.
using ProgramDisplay=console::Presentation<ProgramSerial>;
program::Stream command_stream;
bool command_owned{},console_waiting{},console_probe_used{};
U64 console_wait_stack{},console_wakes{},console_expected_wake{};
extern const std::byte program_poll_begin asm("uefi_program_poll_begin");
extern const std::byte program_poll_end asm("uefi_program_poll_end");

[[nodiscard]] auto program_boundary() -> bool {
    const auto current_stack=stack();
    return current_stack%8==0 && current_stack>=arena+Handoff::stack_bottom
        +ConsoleWakeContext::handler_reserve+ConsoleWakeContext::byte_count
        && current_stack<=arena+Handoff::stack_top && root()==kernel_root && irq_off() && active==L::domain_count && saved_rsp==0
        && !program.running() && !timer_armed && !timer_draining && !timer_owner && !run_authority
        && selected_phase==ipc::Phase::inactive && !console_waiting && console_wait_stack==0
        && timer_stop() && timer_quiet(0x100,false) && timer_quiet(0x200,false);
}
[[nodiscard]] auto program_console_interrupt(U64 vector,U64 error,U64 pc,U64 cs,U64 frame) -> bool {
    if (vector!=64 || command_owned) return false;
    require(console_waiting && !timer_armed && !timer_owner && !run_authority
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
    require(!command_owned && program_boundary() && console_wakes!=UINT64_MAX,"program poll boundary");
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
[[nodiscard]] auto recoverable_program_event() -> bool {
    const auto event=program.event();
    return (event==ProgramEvent::rejected && timer_exhausted)
        || event==ProgramEvent::bounds || event==ProgramEvent::overflow
        || event==ProgramEvent::division_zero || event==ProgramEvent::shift_count;
}
auto program_console_envelope(const Bytes& captured,U64 result) -> void {
    require(command_owned && active<2 && run_authority,"program envelope owner");
    if (program.event()!=ProgramEvent::returned) {
        require(recoverable_program_event(),"program recoverable emitted event");
        return;
    }
    require(captured.get(64)==launch[0] && captured.get(72)==1
        && captured.get(48)==launch[5],"program phase/version/ordinal");
    const ipc::Endpoint endpoint{captured.get(88),captured.get(96)};
    const auto actor=*domains[active].handle;
    if (selected_phase==ipc::Phase::request) {
        require(active==0 && captured.get(56)==0
            && command_stream.accept_request(result,launch[5]),"program request byte/ordinal");
        const auto ticket=mailbox->submit(actor,selected_phase,endpoint,ipc::Request{result,launch[5]});
        require(ticket.has_value(),"program request capability/state");
        transaction=*ticket;
    } else if (selected_phase==ipc::Phase::service) {
        require(active==1 && command_stream.accept_reply(result,launch[5])
            && mailbox->reply(actor,selected_phase,endpoint,captured.get(56),result),"program service capability/byte");
    } else {
        const auto expected_endpoint=mailbox->endpoint(actor);
        require(active==0 && selected_phase==ipc::Phase::completion && expected_endpoint
            && expected_endpoint->slot()==endpoint.slot() && expected_endpoint->generation()==endpoint.generation()
            && captured.get(56)==transaction && mailbox->state()==ipc::State::consumed
            && command_stream.acknowledge(result,launch[5]),"program completion authority/ack");
    }
}
[[nodiscard]] auto program_execute(unsigned index,ipc::Phase phase,U64 source,U64 byte,U64 ordinal) -> bool {
    require(command_owned && program_boundary() && index<2 && selected_client==0,"program launch boundary");
    auto& domain=domains[index];
    require(domain.handle && domain.contract && verify(domain),"program launch domain");
    const auto endpoint=mailbox->endpoint(*domain.handle);
    require(endpoint.has_value(),"program launch grant");
    launch={source,byte,endpoint->slot(),endpoint->generation(),phase==ipc::Phase::request ? 0 : transaction,ordinal,0x202};
    selected_phase=phase;
    selected_role=index==0 ? SelectedRunAuthority::Role::client : SelectedRunAuthority::Role::service;
    for (const auto& lease:domain.stacks) {
        const auto address=frames.address(*lease); require(address.has_value(),"program stack lease"); fill(*address,0);
    }
    require(program.begin(*domain.contract) && registry.activate(*domain.handle),"program launch state");
    active=index;
    const auto selected=domain.tables->root(); asm volatile("mov %0,%%cr3"::"r"(selected):"memory");
    timer_begin(index);
    require(enter(domain.contract->entry(),domain.contract->layout().user_stack_top(),launch.data())==1,"program continuation");
    timer_finish();
    require(root()==kernel_root && saved_rsp==0 && active==L::domain_count && !program.running(),"program restored authority");
    const auto okay=program.event()==ProgramEvent::returned;
    require(okay || recoverable_program_event(),"program terminal outcome");
    launch={}; selected_phase=ipc::Phase::inactive;
    require(program_boundary(),"program post-run quiescence");
    return okay;
}
// Inject only after one byte was fully acknowledged. Empty/one-byte commands
// do not consume the probe; only an actual injection makes later commands healthy.
[[nodiscard]] auto program_source(ipc::Phase phase,U64 ordinal) -> U64 {
    const U64 normal=phase==ipc::Phase::request ? 0 : phase==ipc::Phase::service ? 1 : 2;
    if (console_probe_used || ordinal!=1) return normal;
#ifdef AURORA_PROGRAM_REQUEST_FAULT
    if (phase==ipc::Phase::request) { console_probe_used=true; return 8; }
#endif
#ifdef AURORA_PROGRAM_SERVICE_FAULT
    if (phase==ipc::Phase::service) { console_probe_used=true; return 4; }
#endif
#ifdef AURORA_PROGRAM_COMPLETION_FAULT
    if (phase==ipc::Phase::completion) { console_probe_used=true; return 10; }
#endif
#ifdef AURORA_PROGRAM_REQUEST_BUDGET
    if (phase==ipc::Phase::request) { console_probe_used=true; return 6; }
#endif
#ifdef AURORA_PROGRAM_SERVICE_BUDGET
    if (phase==ipc::Phase::service) { console_probe_used=true; return 5; }
#endif
#ifdef AURORA_PROGRAM_COMPLETION_BUDGET
    if (phase==ipc::Phase::completion) { console_probe_used=true; return 7; }
#endif
    return normal;
}
auto program_cleanup(bool success) -> void {
    require(command_owned && program_boundary() && mailbox,"program cleanup boundary");
    if (!success) {
        require(command_stream.cancel(),"program stream cancellation");
        if (mailbox->state()==ipc::State::pending || mailbox->state()==ipc::State::delivered) {
            require(mailbox->cancel(ipc::Phase::inactive),"program fault cancel");
            const auto endpoint=mailbox->endpoint(*domains[0].handle);
            require(endpoint.has_value(),"program cancelled grant");
            const auto cancelled=mailbox->consume(*domains[0].handle,ipc::Phase::completion,*endpoint,transaction);
            require(cancelled && cancelled->outcome()==ipc::Outcome::cancelled && cancelled->value()==0,
                "program cancellation consumption");
        }
    }
    require(mailbox->scrubbed() && mailbox->revoke(ipc::Phase::inactive)
        && retire(0) && retire(1) && frames.used()==0,"program revoke/retire/scrub");
    mailbox.reset(); transaction=0; launch={}; selected_client=2;
    require(program_boundary(),"program retirement quiescence");
    command_owned=false;
    ProgramSerial::text("AURORA_PROGRAM_COMMAND_END: success="); ProgramSerial::number(success ? 1 : 0);
    ProgramSerial::text(" used=0 epoch="); ProgramSerial::number(timer_epoch); ProgramSerial::text("\r\n");
}
auto program_command(console::Snapshot& input) -> void {
    const auto input_length=input.length();
    require(!command_owned && program_boundary() && !mailbox && frames.used()==0
        && command_stream.begin(input.bytes(),input.length()),"program command admission");
    input={}; // The stream now owns the only retained command-input copy.
    command_owned=true; selected_client=0;
    mailbox.emplace(registry);
    require(create(0)==0 && create(1)==1 && mailbox->bind(*domains[0].handle,*domains[1].handle),"program participants");
    const auto grant=mailbox->endpoint(*domains[0].handle); require(grant.has_value(),"program command grant");
    ProgramSerial::text("AURORA_PROGRAM_COMMAND_BEGIN: grant="); ProgramSerial::number(grant->generation());
    ProgramSerial::text(" length="); ProgramSerial::number(input_length); ProgramSerial::text(" domains=2\r\n");
    bool success=true;
    while (const auto next=command_stream.next_input()) {
        const auto ordinal=next->ordinal();
        if (!program_execute(0,ipc::Phase::request,program_source(ipc::Phase::request,ordinal),next->byte(),ordinal)) {
            success=false; break;
        }
        const auto service=mailbox->endpoint(*domains[1].handle);
        require(service.has_value(),"program service endpoint");
        const auto request=mailbox->receive(*domains[1].handle,ipc::Phase::service,*service,transaction);
        require(request && request->second()==ordinal && mailbox->scrubbed(),"program copied request");
        if (!program_execute(1,ipc::Phase::service,program_source(ipc::Phase::service,ordinal),request->first(),ordinal)) {
            success=false; break;
        }
        const auto client=mailbox->endpoint(*domains[0].handle);
        require(client.has_value(),"program completion endpoint");
        const auto completion=mailbox->consume(*domains[0].handle,ipc::Phase::completion,*client,transaction);
        require(completion && completion->outcome()==ipc::Outcome::replied && mailbox->scrubbed(),"program copied completion");
        if (!program_execute(0,ipc::Phase::completion,program_source(ipc::Phase::completion,ordinal),completion->value(),ordinal)) {
            success=false; break;
        }
        require(mailbox->recycle(ipc::Phase::inactive),"program consumed recycle"); transaction=0;
    }
    program_cleanup(success);
    if (success) {
        auto output=command_stream.finish();
        require(output && command_stream.scrubbed(),"program complete output");
        ProgramSerial::text("output> ");
        for (std::size_t i=0;i<output->length();++i) {
            const auto byte=output->byte(i); require(byte.has_value(),"program output bounds");
            ProgramSerial::put(*byte);
        }
        output->scrub();
        ProgramSerial::text("\r\n");
    } else {
        require(command_stream.scrubbed(),"program cancelled output scrub");
        ProgramSerial::text("Program stopped: checked fault or budget exhausted; output discarded.\r\n");
    }
    ProgramSerial::text("aurora> ");
}
[[nodiscard]] auto is_upper(const console::Snapshot& input) -> bool {
    constexpr std::array<std::uint8_t,5> command{'u','p','p','e','r'};
    if (!input.submitted() || input.length()!=command.size()) return false;
    for (std::size_t i=0;i<command.size();++i) if (input.bytes()[i]!=command[i]) return false;
    return true;
}
auto run_program_console() -> void {
    require(program_boundary() && !command_owned && L::domain_count==2,"program console initial ownership");
    const auto begin=reinterpret_cast<U64>(&program_poll_begin),end=reinterpret_cast<U64>(&program_poll_end);
    require(begin>=arena+Handoff::payload_offset && end>begin && end-begin==3
        && end<arena+Handoff::payload_offset+handoff->get(64),"program console wake RX interval");
    require((hardware::Io::read(0x3fb)&0x80)==0,"program UART register bank");
    hardware::Io::write(0x3f9,0); require(hardware::Io::read(0x3f9)==0,"program UART IRQ disabled");
    ProgramSerial::initialize_input();
    ProgramSerial::text("AURORA_PROGRAM_CONSOLE_READY: UEFI CPL3 upper, ASCII, 64-byte lines\r\naurora> ");
    console::Line line; console::Snapshot copied; bool text_input=false;
    for (;;) {
        require(!command_owned && program_boundary(),"program console receive boundary");
        const auto byte=ProgramSerial::poll(line);
        if (!byte) { program_wait_sample(); continue; }
        const auto event=line.consume(*byte,&copied);
        if (copied.submitted()) {
            if (text_input) {
                text_input=false; ProgramSerial::text("\r\n"); program_command(copied); copied={}; continue;
            }
            if (is_upper(copied)) {
                copied={}; text_input=true; ProgramSerial::text("\r\ntext> "); continue;
            }
        }
        if (event==console::Event::rejected) text_input=false;
        if (event==console::Event::help) {
            ProgramSerial::text("\r\nupper   Uppercase a line in a protected Aurora program\r\nhelp    Show commands\r\nstatus  Show console state\r\nexit    Close this QEMU session\r\naurora> ");
        } else if (event==console::Event::status) {
            ProgramSerial::text("\r\nstatus: protected Aurora upper; two-domain copied stream; timer budgets; capacity=64\r\naurora> ");
        } else if (!ProgramDisplay::render(event,*byte,console::Platform::uefi)) {
            require(program_boundary() && frames.used()==0 && !mailbox,"program console exit boundary");
            ProgramSerial::text("AURORA_PROGRAM_CONSOLE_QUIET: timer=masked isr=0 irr=0 domains=0\r\n");
            return;
        }
    }
}
