# Native freestanding translation units feed explicit assembler/link/image edges.
# The archive is only an object owner: ld receives extracted objects in ABI order.
if native_cpp.get_id() != 'gcc'
    error(
        'Kernel images require GCC freestanding and stack/callgraph metadata support.',
    )
endif
# Meson appends global cpp_args even to native targets with override_options.
# Reject them rather than leaking hosted instrumentation or profile defines.
if get_option('cpp_args').length() != 0 or get_option('build.cpp_args').length() != 0
    error(
        'Freestanding kernel targets require empty cpp_args/CXXFLAGS/CPPFLAGS; use their fixed profile flags.',
    )
endif
kernel_as = find_program('as', native: true)
kernel_ld = find_program('ld', native: true)
kernel_objcopy = find_program('objcopy', native: true)
pe_linker = disabler()
pe_candidates = get_option('uefi_ld') == '' ? ['ld', 'x86_64-w64-mingw32-ld'] : [
    get_option('uefi_ld'),
]
foreach candidate : pe_candidates
    program = find_program(candidate, native: true, required: false)
    if program.found()
        emulations = run_command(program, '-V', check: false)
        if emulations.returncode() == 0 and 'i386pep' in emulations.stdout().strip().split()
            pe_linker = program
            break
        endif
    endif
endforeach
if is_disabler(pe_linker)
    error(
        'Normal UEFI images need GNU ld with i386pep support; set -Duefi_ld=/path/to/linker.',
    )
endif

