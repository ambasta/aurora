# Canonical root-native coverage. Included after tests/meson.build definitions.
native_root = meson.project_source_root()
native_output = meson.current_build_dir()
native_adapter = files('../../scripts/meson-native-run.py')
native_fixture = files('../../scripts/meson-native-fixture.py')
native_adapter_args = ['-B', native_adapter, '--repo', native_root,
                       '--build-root', native_output, '--cxx', oracle_cxx]
native_test_variables = {
  'PYTHONDONTWRITEBYTECODE': '1',
  'TMPDIR': native_output,
  'TMP': native_output,
  'TEMP': native_output,
  'CXX': oracle_cxx,
  'ASAN_OPTIONS': 'detect_leaks=0:halt_on_error=1:abort_on_error=1',
  'UBSAN_OPTIONS': 'halt_on_error=1:print_stacktrace=1',
}
native_test_env = environment(native_test_variables)

# Shared generated Aurora fixtures have Ninja dependencies and private outputs.
native_bios_object = custom_target('native-bios-policy',
    input: '../../examples/kernel-bios.au', output: 'bios-policy.o',
    depfile: 'bios-policy.d',
    command: [python, '-B', native_fixture, '--compiler', aurorac,
              '--source', '@INPUT@', '--module-root', native_root / 'kernel/policies',
              '--object', '@OUTPUT@', '--depfile', '@DEPFILE@'])
native_uefi_object = custom_target('native-uefi-policy',
    input: '../../examples/kernel.au', output: 'uefi-policy.o',
    depfile: 'uefi-policy.d',
    command: [python, '-B', native_fixture, '--compiler', aurorac,
              '--source', '@INPUT@', '--module-root', native_root / 'kernel/policies',
              '--object', '@OUTPUT@', '--depfile', '@DEPFILE@'])
native_console_object = custom_target('native-console-session',
    input: '../../examples/kernel-console.au', output: 'console-session.o',
    depfile: 'console-session.d',
    command: [python, '-B', native_fixture, '--compiler', aurorac,
              '--source', '@INPUT@', '--module-root', native_root / 'kernel/policies',
              '--module-root', native_root / 'library',
              '--bridge', native_root / 'kernel/console-service-entry.S',
              '--object', '@OUTPUT@', '--depfile', '@DEPFILE@'])
native_uart_object = custom_target('native-uart-policy',
    input: '../../examples/kernel-uart.au', output: 'uart-policy.o',
    depfile: 'uart-policy.d',
    command: [python, '-B', native_fixture, '--compiler', aurorac,
              '--source', '@INPUT@', '--module-root', native_root / 'kernel/policies',
              '--local-symbols', '--referenced-reflection-only',
              '--bridge', native_root / 'kernel/uart-policy-entry.S',
              '--object', '@OUTPUT@', '--depfile', '@DEPFILE@'])
native_program_console_object = custom_target('native-program-console-policy',
    input: '../../examples/kernel-program-console.au', output: 'program-console-policy.o',
    depfile: 'program-console-policy.d',
    command: [python, '-B', native_fixture, '--compiler', aurorac,
              '--source', '@INPUT@', '--module-root', native_root / 'kernel/policies',
              '--module-root', native_root / 'library', '--local-symbols', '--referenced-reflection-only',
              '--bridge', native_root / 'kernel/uefi/program-note-entry.S',
              '--bridge', native_root / 'kernel/uefi/kernel-policy-entry.S',
              '--object', '@OUTPUT@', '--depfile', '@DEPFILE@'])
native_memory_object = custom_target('native-uefi-memory-object',
    input: '../../kernel/uefi/memory.S', output: 'uefi-memory.o',
    command: [find_program('as', native: true), '--64', '@INPUT@', '-o', '@OUTPUT@'])
native_round_robin_object = custom_target('native-round-robin-substitution',
    input: native_uefi_object, output: 'round-robin-substitution.o',
    command: [find_program('objcopy', native: true), '--redefine-sym',
              'aurora_kernel_round_robin_next=aurora_kernel_round_robin_next_real',
              '@INPUT@', '@OUTPUT@'])

native_host = executable('native-kernel-pages', files('../../tests/kernel-pages.cpp') + [native_bios_object],
    native: true, install: false, override_options: ['optimization=1', 'warning_level=3'],
    cpp_args: [], link_args: ['-no-pie'])
test('native-kernel-pages', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-protection', files('../../tests/kernel-protection.cpp') + [native_bios_object],
    native: true, install: false, override_options: ['optimization=1', 'warning_level=3'],
    cpp_args: [], link_args: ['-no-pie'])
test('native-kernel-protection', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-program', files('../../tests/kernel-program.cpp') + [native_bios_object],
    native: true, install: false, override_options: ['optimization=1', 'warning_level=3'],
    cpp_args: [], link_args: ['-no-pie'])
native_program_host = native_host
test('native-kernel-program', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-program-layout', files('../../tests/kernel-program-layout.cpp') + [native_bios_object],
    native: true, install: false, override_options: ['optimization=1', 'warning_level=3'],
    cpp_args: [], link_args: ['-no-pie'])
native_program_layout_host = native_host
test('native-kernel-program-layout', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-domain', files('../../tests/kernel-domain.cpp') + [native_bios_object],
    native: true, install: false, override_options: ['optimization=1', 'warning_level=3'],
    cpp_args: [], link_args: ['-no-pie'])
test('native-kernel-domain', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-schedule', files('../../tests/kernel-schedule.cpp') + [native_bios_object],
    native: true, install: false, override_options: ['optimization=1', 'warning_level=3'],
    cpp_args: [], link_args: ['-no-pie'])
native_schedule_host = native_host
test('native-kernel-schedule', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-uefi-runtime', files('../../tests/kernel-uefi-runtime.cpp') + [native_bios_object],
    native: true, install: false, override_options: ['optimization=1', 'warning_level=3'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page'], link_args: ['-no-pie'])
test('native-uefi-runtime', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-uefi-multipage-runtime', files('../../tests/kernel-uefi-runtime.cpp') + [native_bios_object],
    native: true, install: false, override_options: ['optimization=1', 'warning_level=3'],
    cpp_args: ['-DAURORA_RUNTIME_MULTIPAGE=1', '-DAURORA_RUNTIME_IMAGE_POLICY=multipage'], link_args: ['-no-pie'])
test('native-uefi-multipage-runtime', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-ipc', files('../../tests/kernel-ipc.cpp') + [native_uefi_object],
    native: true, install: false, override_options: ['optimization=1', 'warning_level=3'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page'], link_args: ['-no-pie'])
test('native-kernel-ipc', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-program-mailbox', files('../../tests/kernel-program-mailbox.cpp') + [native_program_console_object],
    native: true, install: false, override_options: ['optimization=1', 'warning_level=3'],
    cpp_args: [], link_args: ['-no-pie'])
test('native-kernel-program-mailbox', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-uefi-service-budget', files('../../tests/kernel-uefi-service-budget.cpp') + [native_uefi_object],
    native: true, install: false, override_options: ['optimization=1', 'warning_level=3'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page'], link_args: ['-no-pie'])
test('native-kernel-uefi-service-budget', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-uefi-dispatch-layout', files('../../tests/kernel-uefi-dispatch-layout.cpp') + [native_uefi_object],
    native: true, install: false, override_options: ['optimization=1', 'warning_level=3'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page'], link_args: ['-no-pie'])
test('native-kernel-uefi-dispatch-layout', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-dispatch', files('../../tests/kernel-dispatch.cpp') + [native_uefi_object],
    native: true, install: false, override_options: ['optimization=1', 'warning_level=3'],
    cpp_args: [], link_args: ['-no-pie'])
test('native-kernel-dispatch', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-uefi-user-run', files('../../tests/kernel-uefi-user-run.cpp') + [native_uefi_object],
    native: true, install: false, override_options: ['optimization=1', 'warning_level=3'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page'], link_args: ['-no-pie'])
test('native-kernel-uefi-user-run', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-uefi-multipage-user-run', files('../../tests/kernel-uefi-user-run.cpp') + [native_uefi_object],
    native: true, install: false, override_options: ['optimization=1', 'warning_level=3'],
    cpp_args: ['-DAURORA_RUNTIME_MULTIPAGE=1', '-DAURORA_RUNTIME_IMAGE_POLICY=multipage'], link_args: ['-no-pie'])
test('native-uefi-multipage-user-run', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-client-disposal', files('../../tests/kernel-client-disposal.cpp') + [native_uefi_object],
    native: true, install: false, override_options: ['optimization=1', 'warning_level=3'],
    cpp_args: [], link_args: ['-no-pie'])
test('native-kernel-client-disposal', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-console', files('../../tests/kernel-console.cpp') + [native_console_object],
    native: true, install: false, override_options: ['optimization=1', 'warning_level=3'],
    cpp_args: [], link_args: ['-no-pie'])
test('native-kernel-console', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-console-uart', files('../../tests/kernel-console-uart.cpp') + [native_console_object],
    native: true, install: false, override_options: ['optimization=1', 'warning_level=3'],
    cpp_args: [], link_args: ['-no-pie'])
test('native-kernel-console-uart', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-generated-uart',
    files('../../tests/kernel-console-uart.cpp') + [native_console_object, native_uart_object],
    native: true, install: false, override_options: ['optimization=1', 'warning_level=3'],
    cpp_args: ['-DAURORA_GENERATED_UART=1'], link_args: ['-no-pie'])
test('native-kernel-generated-uart', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-port-session', files('../../tests/kernel-port-session.cpp'),
    native: true, install: false, override_options: ['optimization=1', 'warning_level=3'],
    cpp_args: [], link_args: ['-no-pie'])
test('native-kernel-port-session', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-uefi', files('../../tests/kernel-uefi.cpp'),
    native: true, install: false, override_options: ['optimization=1', 'warning_level=2'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page', '-fno-pie'], link_args: ['-no-pie'])
test('native-kernel-uefi', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
# The handoff layout tables, for the production (v7) header and every other image.
foreach variant : [['native-kernel-uefi-handoff', []],
                   ['native-kernel-uefi-handoff-terminal', ['-DAURORA_UEFI_GRAPHICAL_TERMINAL']]]
  native_host = executable(variant[0], files('../../tests/kernel-uefi-handoff.cpp'),
      native: true, install: false, override_options: ['optimization=1', 'warning_level=3'],
      cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page'] + variant[1], link_args: [])
  test(variant[0], native_host, suite: ['full', 'merge', 'dev'], env: native_test_env, timeout: 60)
endforeach
native_host = executable('native-kernel-acpi', files('../../tests/kernel-acpi.cpp'),
    native: true, install: false, override_options: ['optimization=1', 'warning_level=2'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page'], link_args: [])
test('native-kernel-acpi', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-pci', files('../../tests/kernel-pci.cpp'),
    native: true, install: false, override_options: ['optimization=1', 'warning_level=2'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page'], link_args: [])
test('native-kernel-pci', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-program-stream', files('../../tests/kernel-program-stream.cpp') + [native_program_console_object],
    native: true, install: false, override_options: ['optimization=1', 'warning_level=3'],
    cpp_args: [], link_args: ['-no-pie'])
test('native-kernel-program-stream', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-program-run-authority', files('../../tests/kernel-program-run-authority.cpp'),
    native: true, install: false, override_options: ['optimization=1', 'warning_level=3'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page'], link_args: ['-no-pie'])
test('native-kernel-program-run-authority', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-uefi-bar', files('../../tests/kernel-uefi-bar.cpp'),
    native: true, install: false, override_options: ['optimization=1', 'warning_level=2'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page', '-DNDEBUG'], link_args: [])
test('native-kernel-uefi-bar', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-uefi-bar-record', files('../../tests/kernel-uefi-bar-record.cpp'),
    native: true, install: false, override_options: ['optimization=1', 'warning_level=2'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page', '-DNDEBUG'], link_args: [])
test('native-kernel-uefi-bar-record', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-uefi-ivrs', files('../../tests/kernel-uefi-ivrs.cpp'),
    native: true, install: false, override_options: ['optimization=1', 'warning_level=2'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page', '-DNDEBUG'], link_args: [])
test('native-kernel-uefi-ivrs', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-owned-bytes', files('../../tests/kernel-owned-bytes.cpp', '../../kernel/owned-bytes.cpp'),
    native: true, install: false, override_options: ['optimization=1', 'warning_level=3'],
    cpp_args: ['-DNDEBUG', '-fno-exceptions', '-fno-rtti', '-DAURORA_KERNEL_BYTES_TESTING=1'], link_args: ['-no-pie'])
test('native-kernel-owned-bytes', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-round-robin-adapter', files('../../tests/kernel-round-robin-adapter.cpp') + [native_round_robin_object],
    native: true, install: false, override_options: ['optimization=1', 'warning_level=3'],
    cpp_args: [], link_args: ['-no-pie'])
test('native-round-robin-adapter', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-uefi-memory', files('../../tests/kernel-uefi-memory.cpp') + [native_memory_object],
    native: true, install: false, override_options: ['optimization=2', 'debug=false', 'warning_level=2'],
    cpp_args: ['-fno-builtin'], link_args: [])
test('native-uefi-memory', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-uefi-framebuffer', files('../../tests/kernel-uefi-framebuffer.cpp'),
    native: true, install: false, override_options: ['optimization=1', 'debug=false', 'warning_level=3'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page'], link_args: ['-no-pie'])
test('native-uefi-framebuffer', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-uefi-framebuffer-tables', files('../../tests/kernel-uefi-framebuffer-tables.cpp'),
    native: true, install: false, override_options: ['optimization=1', 'debug=false', 'warning_level=3'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page'], link_args: ['-no-pie'])
test('native-uefi-framebuffer-tables', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-uefi-framebuffer-loader', files('../../tests/kernel-uefi-framebuffer-loader.cpp'),
    native: true, install: false, override_options: ['optimization=1', 'debug=false', 'warning_level=3'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page'], link_args: ['-no-pie'])
test('native-uefi-framebuffer-loader', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-uefi-framebuffer-pixels', files('../../tests/kernel-uefi-framebuffer-pixels.cpp'),
    native: true, install: false, override_options: ['optimization=1', 'debug=false', 'warning_level=3'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page'], link_args: ['-no-pie'])
test('native-uefi-framebuffer-pixels', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-display-session', files('../../tests/kernel-display-session.cpp'),
    native: true, install: false, override_options: ['optimization=1', 'debug=false', 'warning_level=3'],
    cpp_args: [], link_args: [])
test('native-display-session', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-uefi-console-context', files('../../tests/kernel-uefi-console-context.cpp'),
    native: true, install: false, override_options: ['optimization=1', 'warning_level=3'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page'], link_args: ['-no-pie'])
test('native-kernel-uefi-console-context', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_owned_object = custom_target('native-owned-bytes-policy',
    input: '../../examples/kernel-owned-bytes.au', output: 'owned-bytes-policy.o',
    depfile: 'owned-bytes-policy.d',
    command: [python, '-B', native_fixture, '--compiler', aurorac,
              '--source', '@INPUT@', '--module-root', native_root / 'library',
              '--bridge', native_root / 'kernel/uefi/owned-bytes-entry.S',
              '--object', '@OUTPUT@', '--depfile', '@DEPFILE@'])
native_host = executable('native-kernel-uefi-owned-views',
    files('../../tests/kernel-uefi-owned-views.cpp', '../../kernel/owned-bytes.cpp') + [native_owned_object],
    native: true, install: false, override_options: ['optimization=1', 'warning_level=3'],
    cpp_args: ['-DNDEBUG', '-fno-exceptions', '-fno-rtti'],
    link_args: ['-no-pie', '-Wl,--wrap=__au_runtime_bytes_allocate', '-Wl,--wrap=__au_runtime_bytes_drop'])
foreach mode : range(17)
  test('native-kernel-uefi-owned-views-' + mode.to_string(), native_host, args: [mode.to_string()],
       suite: ['full', 'merge', 'slow', 'integration'], env: native_test_env, timeout: 60)
endforeach
test('native-unsigned-source', python, args: native_adapter_args + ['--compiler', aurorac] + ['--', python] + ['-B', files('../../tests/kernel-unsigned-source.py')],
     suite: ['full', 'merge', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 180, depends: aurorac)
test('native-storage-test-durability-optimized', python, args: ['-B', '-O', files('../../storage/design/model/test_durability.py')],
     suite: ['full', 'merge', 'slow', 'storage'], env: native_test_env,
     workdir: native_root, timeout: 180)
test('native-storage-check-traceability-optimized', python, args: ['-B', '-O', files('../../storage/design/model/check_traceability.py')],
     suite: ['full', 'merge', 'slow', 'storage'], env: native_test_env,
     workdir: native_root, timeout: 180)
test('native-storage-test-traceability-optimized', python, args: ['-B', '-O', files('../../storage/design/model/test_traceability.py')],
     suite: ['full', 'merge', 'slow', 'storage'], env: native_test_env,
     workdir: native_root, timeout: 180)
test('native-semantics', python, args: ['-B', files('../../tests/semantics/run.py'), aurorac],
     suite: ['full', 'merge', 'slow', 'semantics'], env: native_test_env,
     workdir: native_output, timeout: 300, depends: aurorac)
# Protected snapshot and note replays: each generated root is compiled and
# assembled once (reflection exports localized so separately compiled roots can
# share one hosted link) and linked with its native observer. The user images
# themselves are built and checked by the snapshot and program-console profiles.
native_fixture_command = [python, '-B', native_fixture, '--compiler', aurorac, '--source', '@INPUT@',
                          '--object', '@OUTPUT@', '--depfile', '@DEPFILE@', '--keep-local-labels']
policies_root = ['--module-root', native_root / 'kernel/policies']
library_root = ['--module-root', native_root / 'library']
protected_objects = {}
foreach fixture : [
    ['snapshot-client', 'tests/kernel-programs/snapshot-client.au', policies_root + ['--localize-reflection']],
    ['snapshot-service', 'tests/kernel-programs/snapshot-service.au',
     policies_root + ['--assemble-with', native_root / 'tests/kernel-snapshot-entry.S', '--localize-reflection']],
    ['snapshot-checksum', 'tests/kernel-programs/call-snapshot-service.au',
     policies_root + library_root + ['--defsym', 'CHECKSUM_SERVICE=1',
     '--assemble-with', native_root / 'tests/kernel-snapshot-entry.S', '--localize-reflection']],
    ['snapshot-supervisor', 'examples/kernel-snapshot.au',
     policies_root + library_root + ['--assemble-with', native_root / 'kernel/uefi/snapshot-entry.S']],
    ['note-client', 'tests/kernel-programs/program-upper-client.au', ['--localize-reflection']],
    ['note-service', 'tests/kernel-programs/program-stream-service.au',
     policies_root + ['--assemble-with', native_root / 'tests/kernel-program-note-entry.S', '--localize-reflection']],
    ['note-supervisor', 'examples/kernel-program-console.au',
     policies_root + library_root + ['--local-symbols', '--bridge', native_root / 'kernel/uefi/program-note-entry.S',
     '--assemble-with', native_root / 'kernel/uefi/kernel-policy-entry.S']],
    ['note-initial', 'tests/kernel-programs/program-note-initial.au',
     library_root + ['--defsym', 'NOTE_TEST_INITIAL=1',
     '--assemble-with', native_root / 'tests/kernel-program-note-entry.S', '--localize-reflection']],
    ['note-stream', 'tests/kernel-programs/program-command-stream.au',
     library_root + policies_root + ['--defsym', 'STREAM_TEST_INITIAL=1',
     '--bridge', native_root / 'tests/kernel-program-note-entry.S', '--localize-reflection']],
    ['note-file-service', 'tests/kernel-programs/file-call-service.au',
     policies_root + ['--local-symbols', '--bridge', native_root / 'tests/kernel-file-call-entry.S']],
]
  protected_objects += {fixture[0]: custom_target('native-' + fixture[0], input: '../../' + fixture[1],
      output: fixture[0] + '.o', depfile: fixture[0] + '.d', command: native_fixture_command + fixture[2])}
endforeach
native_host = executable('native-protected-snapshot',
    files('../../tests/kernel-snapshot.cpp', '../../kernel/uefi/snapshot.cpp', '../../kernel/owned-bytes.cpp') +
    [protected_objects['snapshot-client'], protected_objects['snapshot-service'],
     protected_objects['snapshot-checksum'], protected_objects['snapshot-supervisor']],
    native: true, install: false, override_options: ['optimization=1', 'warning_level=3'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page', '-DNDEBUG', '-fno-exceptions', '-fno-rtti',
               '-DAURORA_UEFI_SNAPSHOT', '-DAURORA_UEFI_RUNTIME', '-DAURORA_UEFI_IPC', '-DAURORA_UEFI_ACPI',
               '-DAURORA_UEFI_PCI'],
    link_args: ['-no-pie'])
test('native-protected-snapshot', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 120)
native_host = executable('native-protected-note', files('../../tests/kernel-program-note.cpp') +
    [protected_objects['note-client'], protected_objects['note-service'], protected_objects['note-supervisor'],
     protected_objects['note-initial'], protected_objects['note-stream'], protected_objects['note-file-service']],
    native: true, install: false, override_options: ['optimization=1', 'warning_level=3'],
    cpp_args: ['-DNDEBUG', '-fno-exceptions', '-fno-rtti'], link_args: ['-no-pie'])
test('native-protected-note', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 120)
# Kernel policies: each real generated policy object is linked once with its C++
# observer, whose fixed vector families are compared with a golden file. Copy
# probes, hostile-producer adapters (one producer renamed) and source rejections
# are separate programs and golden cases.
policy_hosts = {}
foreach policy : ['budget', 'round-robin', 'ipc-transition', 'client-disposal', 'terminal-event']
  policy_hosts += {policy: executable('kernel-' + policy + '-native',
      files('../../tests/kernel-' + policy + '-native.cpp') + [native_uefi_object],
      native: true, install: false, override_options: ['optimization=1', 'warning_level=3'], link_args: ['-no-pie'])}
  test('native-policy-' + policy, python,
       args: ['-B', golden_runner, files('../../tests/kernel-' + policy + '-native.golden'), '--', policy_hosts[policy]],
       suite: ['full', 'merge', 'slow', 'integration'], env: native_test_env, timeout: 120)
endforeach
foreach policy : ['round-robin', 'ipc-transition', 'client-disposal']
  copy_object = custom_target('native-' + policy + '-copy',
      input: '../../tests/kernel-programs/' + policy + '-copy.au', output: policy + '-copy.o',
      depfile: policy + '-copy.d',
      command: [python, '-B', native_fixture, '--compiler', aurorac, '--source', '@INPUT@',
                '--module-root', native_root / 'kernel/policies', '--object', '@OUTPUT@', '--depfile', '@DEPFILE@'])
  native_host = executable('kernel-' + policy + '-copy', files('../../tests/kernel-' + policy + '-copy.cpp') + [copy_object],
      native: true, install: false, override_options: ['optimization=1', 'warning_level=3'], link_args: ['-no-pie'])
  test('native-' + policy + '-copy', native_host, suite: ['full', 'merge', 'slow', 'integration'],
       env: native_test_env, timeout: 60)
endforeach
foreach adapter : [['ipc-transition', 'aurora_kernel_ipc_transition', 'kernel-ipc-transition-adapter.cpp', []],
                   ['client-disposal', 'aurora_kernel_client_disposal', 'kernel-client-disposal-adapter.cpp', []],
                   ['terminal-event', 'aurora_kernel_terminal_event', 'kernel-terminal-event-native.cpp',
                    ['-DTERMINAL_SUBSTITUTE']]]
  substituted = custom_target('native-' + adapter[0] + '-substitution', input: native_uefi_object,
      output: adapter[0] + '-substitution.o',
      command: [find_program('objcopy', native: true), '--redefine-sym', adapter[1] + '=' + adapter[1] + '_real',
                '@INPUT@', '@OUTPUT@'])
  native_host = executable('kernel-' + adapter[0] + '-adapter', files('../../tests/' + adapter[2]) + [substituted],
      native: true, install: false, override_options: ['optimization=1', 'warning_level=3'],
      cpp_args: adapter[3], link_args: ['-no-pie'])
  test('native-' + adapter[0] + '-adapter', native_host, suite: ['full', 'merge', 'slow', 'integration'],
       env: native_test_env, timeout: 60)
endforeach
# The program lifecycle tests also run against the UEFI policy object's terminal producer.
foreach fixture : [['kernel-program', native_program_host], ['kernel-program-layout', native_program_layout_host],
                   ['kernel-schedule', native_schedule_host]]
  native_host = executable('native-' + fixture[0] + '-uefi-policy', native_uefi_object,
      objects: fixture[1].extract_objects('../../tests/' + fixture[0] + '.cpp'),
      native: true, install: false, link_args: ['-no-pie'])
  test('native-' + fixture[0] + '-uefi-policy', native_host, suite: ['full', 'merge', 'slow', 'integration'],
       env: native_test_env, timeout: 180)
endforeach
test('native-policy-rejections', python,
     args: ['-B', golden_runner, files('../../tests/kernel-policy-rejections.golden'), '--reject', '--', aurorac,
            '--module-root', native_root / 'kernel/policies'],
     suite: ['full', 'merge', 'slow', 'integration'], env: native_test_env, timeout: 120, depends: aurorac)
# Pin ledger, NVMe queue and dormant-table models: each program is built once and
# runs its own fixtures; the configuration guards are compile-fail cases.
foreach program : [
    ['kernel-pin-ledger', 'kernel-pin-ledger.cpp', ['-DAURORA_PIN_LEDGER_TESTING=1']],
    ['kernel-pin-ledger-generation-3', 'kernel-pin-ledger.cpp',
     ['-DAURORA_PIN_LEDGER_TESTING=1', '-DAURORA_PIN_LEDGER_TEST_GENERATION_LIMIT=3']],
    ['kernel-pin-api', 'kernel-pin-api.cpp', []],
    ['kernel-nvme-queues', 'kernel-nvme-queues.cpp',
     ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page', '-DNDEBUG', '-DAURORA_NVME_QUEUE_TESTING=1']],
    ['kernel-nvme-queues-generation-3', 'kernel-nvme-queues.cpp',
     ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page', '-DNDEBUG', '-DAURORA_NVME_QUEUE_TESTING=1',
      '-DAURORA_NVME_QUEUE_GENERATION_LIMIT=3']],
    ['kernel-nvme-queues-api', 'kernel-nvme-queues-api.cpp', ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page', '-DNDEBUG']],
    ['kernel-dormant-tables', 'kernel-dormant-tables.cpp', []],
    ['kernel-dormant-decoder', 'kernel-dormant-decoder.cpp', []],
    ['kernel-dormant-oracle', 'kernel-dormant-oracle.cpp', []],
    ['kernel-dormant-generation', 'kernel-dormant-generation.cpp',
     ['-DAURORA_PIN_LEDGER_TESTING=1', '-DAURORA_PIN_LEDGER_TEST_GENERATION_LIMIT=3']],
    ['kernel-dormant-api', 'kernel-dormant-api.cpp', []],
    ['kernel-iommu-oracle', 'kernel-iommu-oracle.cpp', []],
    ['kernel-iommu-event-completion', 'kernel-iommu-event-completion.cpp', []],
]
  native_host = executable(program[0], files('../../tests/' + program[1]),
      native: true, install: false, override_options: ['optimization=1', 'warning_level=2'],
      cpp_args: program[2])
  test(program[0], native_host, suite: ['full', 'merge', 'slow', 'integration'], env: native_test_env, timeout: 120)
endforeach
test('kernel-compile-fail', python,
     args: ['-B', files('../compile_fail.py'), files('../kernel-compile-fail.txt'), native_root] + native_cpp.cmd_array(),
     suite: ['full', 'merge', 'slow', 'integration'], env: native_test_env, timeout: 120)
if get_option('kernel_images')
  test('native-uefi-span-integration', python,
       args: ['-B', files('../../tests/kernel-uefi-span.py'), aurorac,
              meson.project_build_root() / 'kernel-images/uefi/runtime-span'],
       suite: ['full', 'merge', 'slow', 'integration'], env: native_test_env, workdir: native_root,
       timeout: 120, depends: [aurorac, kernel_profile_users['uefi/runtime-span']])
  # Building every profile runs its image and stack checks (kernel-images/meson.build).
  test('kernel-images', find_program('true'), depends: kernel_images_all,
       suite: ['full', 'merge', 'slow', 'integration', 'boot'], timeout: 900)
endif

# UEFI guest families (QEMU), outside full: meson test --suite guest or guest-<family>.
if get_option('kernel_images')
  uefi_smoke = files('../../scripts/kernel-uefi-smoke.sh')
  foreach family : profile_data['guests'].split('|')
    foreach mode : profile_data['guests.' + family].split('|')
      canonical = profile_data.get('aliases.uefi/' + mode, 'uefi/' + mode)
      test('guest-uefi-' + mode, find_program('bash', native: true),
           args: [uefi_smoke, '--run-only', meson.project_build_root() / 'kernel-images' / canonical, mode],
           depends: kernel_profile_images[canonical], suite: ['guest', 'guest-' + family],
           workdir: native_root, timeout: 180)
    endforeach
  endforeach
  # The production image: its protected program console through the PTY oracle,
  # then serial commands plus the graphical terminal's framebuffer in one guest.
  test('guest-uefi-production', python,
       args: ['-B', files('../../scripts/kernel_production_smoke.py'),
              '--build-dir', meson.project_build_root() / 'kernel-images/uefi/production',
              '--renderer', graphical_terminal_host],
       depends: kernel_profile_images['uefi/production'] + [graphical_terminal_host],
       suite: ['guest', 'guest-production'], workdir: native_root, timeout: 480)
endif
