#!/usr/bin/env python3
"""Source routing guard for the real program runtime's UART diagnostic path."""
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]

def need(okay, reason):
    if not okay:
        raise ValueError(reason)

def clean(text):
    return re.sub(r'//[^\n]*|/\*.*?\*/', '', text, flags=re.S)

runtime = clean((root / 'kernel/uefi/runtime.cpp').read_text())
route = re.compile(r'#ifdef AURORA_UEFI_PROGRAM_CONSOLE\s*'
                   r'using Serial=console::Uart<hardware::Io,console::FifoTrigger::fourteen>;\s*'
                   r'#else\s*using hardware::Serial;\s*#endif')
need(len(route.findall(runtime)) == 1, 'Runtime and input must select the same sticky UART specialization')
runtime = route.sub('', runtime)
program = clean((root / 'kernel/uefi/program-console.inc').read_text())
need(re.search(r'using ProgramSerial\s*=\s*Serial;', program), 'Program input must alias runtime diagnostics')
for name, text in [('runtime.cpp', runtime), ('program-console.inc', program),
                   ('service-timer.inc', clean((root / 'kernel/uefi/service-timer.inc').read_text()))]:
    need(not re.search(r'hardware\s*::\s*Serial|0x0*3fd\b|\b1021\b', text, re.I),
         'Raw serial/error-clearing LSR access in program runtime include chain: ' + name)
need('program_console_interrupt(vector,error,pc,cs,frame)' in runtime,
     'Shared IRQ dispatcher must route console ownership before runtime handling')
print('PASS: actual program runtime/timer/include UART routing uses one sticky-latch instance')
