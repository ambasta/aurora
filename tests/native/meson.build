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
# Some legacy runners require source-contained output even for out-of-tree builds.
native_artifact_env = environment(native_test_variables)
native_artifact_env.set('TMPDIR', native_root)
native_artifact_env.set('TMP', native_root)
native_artifact_env.set('TEMP', native_root)
native_artifact_args = ['-B', artifact_adapter, python] + native_adapter_args

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
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: [], link_args: ['-no-pie'])
test('native-kernel-pages', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-protection', files('../../tests/kernel-protection.cpp') + [native_bios_object],
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: [], link_args: ['-no-pie'])
test('native-kernel-protection', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-program', files('../../tests/kernel-program.cpp') + [native_bios_object],
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: [], link_args: ['-no-pie'])
test('native-kernel-program', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-program-layout', files('../../tests/kernel-program-layout.cpp') + [native_bios_object],
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: [], link_args: ['-no-pie'])
test('native-kernel-program-layout', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-domain', files('../../tests/kernel-domain.cpp') + [native_bios_object],
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: [], link_args: ['-no-pie'])
test('native-kernel-domain', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-schedule', files('../../tests/kernel-schedule.cpp') + [native_bios_object],
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: [], link_args: ['-no-pie'])
test('native-kernel-schedule', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-uefi-runtime', files('../../tests/kernel-uefi-runtime.cpp') + [native_bios_object],
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page'], link_args: ['-no-pie'])
test('native-uefi-runtime', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-uefi-multipage-runtime', files('../../tests/kernel-uefi-runtime.cpp') + [native_bios_object],
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: ['-DAURORA_RUNTIME_MULTIPAGE=1', '-DAURORA_RUNTIME_IMAGE_POLICY=multipage'], link_args: ['-no-pie'])
test('native-uefi-multipage-runtime', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-ipc', files('../../tests/kernel-ipc.cpp') + [native_uefi_object],
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page'], link_args: ['-no-pie'])
test('native-kernel-ipc', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-program-mailbox', files('../../tests/kernel-program-mailbox.cpp') + [native_program_console_object],
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: [], link_args: ['-no-pie'])
test('native-kernel-program-mailbox', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-uefi-service-budget', files('../../tests/kernel-uefi-service-budget.cpp') + [native_uefi_object],
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page'], link_args: ['-no-pie'])
test('native-kernel-uefi-service-budget', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-uefi-dispatch-layout', files('../../tests/kernel-uefi-dispatch-layout.cpp') + [native_uefi_object],
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page'], link_args: ['-no-pie'])
test('native-kernel-uefi-dispatch-layout', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-dispatch', files('../../tests/kernel-dispatch.cpp') + [native_uefi_object],
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: [], link_args: ['-no-pie'])
test('native-kernel-dispatch', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-uefi-user-run', files('../../tests/kernel-uefi-user-run.cpp') + [native_uefi_object],
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page'], link_args: ['-no-pie'])
test('native-kernel-uefi-user-run', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-uefi-multipage-user-run', files('../../tests/kernel-uefi-user-run.cpp') + [native_uefi_object],
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: ['-DAURORA_RUNTIME_MULTIPAGE=1', '-DAURORA_RUNTIME_IMAGE_POLICY=multipage'], link_args: ['-no-pie'])
test('native-uefi-multipage-user-run', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-client-disposal', files('../../tests/kernel-client-disposal.cpp') + [native_uefi_object],
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: [], link_args: ['-no-pie'])
test('native-kernel-client-disposal', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-console', files('../../tests/kernel-console.cpp') + [native_console_object],
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: [], link_args: ['-no-pie'])
test('native-kernel-console', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-console-uart', files('../../tests/kernel-console-uart.cpp') + [native_console_object],
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: [], link_args: ['-no-pie'])
test('native-kernel-console-uart', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-generated-uart',
    files('../../tests/kernel-console-uart.cpp') + [native_console_object, native_uart_object],
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: ['-DAURORA_GENERATED_UART=1'], link_args: ['-no-pie'])
test('native-kernel-generated-uart', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-port-session', files('../../tests/kernel-port-session.cpp'),
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: [], link_args: ['-no-pie'])
test('native-kernel-port-session', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-uefi', files('../../tests/kernel-uefi.cpp'),
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=2'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page', '-fno-pie'], link_args: ['-no-pie'])
test('native-kernel-uefi', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-acpi', files('../../tests/kernel-acpi.cpp'),
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=2'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page'], link_args: [])
test('native-kernel-acpi', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-pci', files('../../tests/kernel-pci.cpp'),
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=2'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page'], link_args: [])
test('native-kernel-pci', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-program-stream', files('../../tests/kernel-program-stream.cpp') + [native_program_console_object],
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: [], link_args: ['-no-pie'])
test('native-kernel-program-stream', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-program-run-authority', files('../../tests/kernel-program-run-authority.cpp'),
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page'], link_args: ['-no-pie'])
test('native-kernel-program-run-authority', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-uefi-bar', files('../../tests/kernel-uefi-bar.cpp'),
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=2'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page', '-DNDEBUG'], link_args: [])
test('native-kernel-uefi-bar', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-uefi-bar-record', files('../../tests/kernel-uefi-bar-record.cpp'),
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=2'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page', '-DNDEBUG'], link_args: [])
test('native-kernel-uefi-bar-record', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-uefi-ivrs', files('../../tests/kernel-uefi-ivrs.cpp'),
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=2'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page', '-DNDEBUG'], link_args: [])
test('native-kernel-uefi-ivrs', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-owned-bytes', files('../../tests/kernel-owned-bytes.cpp', '../../kernel/owned-bytes.cpp'),
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: ['-DNDEBUG', '-fno-exceptions', '-fno-rtti', '-DAURORA_KERNEL_BYTES_TESTING=1'], link_args: ['-no-pie'])
test('native-kernel-owned-bytes', native_host, suite: ['full', 'merge', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-round-robin-adapter', files('../../tests/kernel-round-robin-adapter.cpp') + [native_round_robin_object],
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
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
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
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
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
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
test('native-semantics-harness', python, args: ['-B', files('../../tests/semantics/test_runner.py')],
     suite: ['full', 'merge', 'slow', 'semantics'], env: native_test_env,
     workdir: native_root, timeout: 180)
test('native-semantics', python, args: native_adapter_args + ['--compiler', aurorac] + ['--', python] + ['-B', files('../../tests/semantics/run.py'), aurorac],
     suite: ['full', 'merge', 'slow', 'semantics'], env: native_test_env,
     workdir: native_root, timeout: 1200, depends: aurorac)
test('native-protected-note', python,
     args: native_artifact_args + ['--compiler', aurorac, '--', find_program('bash', native: true),
                                  files('../../scripts/kernel-program-note-tests.sh'), '@ARTIFACTS@'],
     depends: aurorac, suite: ['full', 'merge', 'slow', 'integration'], env: native_artifact_env,
     workdir: native_root, timeout: 900)
test('native-protected-snapshot', python,
     args: native_artifact_args + ['--compiler', aurorac, '--', find_program('bash', native: true),
                                  files('../../scripts/kernel-snapshot-tests.sh'), '@ARTIFACTS@'],
     depends: aurorac, suite: ['full', 'merge', 'slow', 'integration'], env: native_artifact_env,
     workdir: native_root, timeout: 900)
test('native-policy-budget', python, args: native_artifact_args + ['--compiler', aurorac, '--', python, '-B', '-O', native_root / 'tests/kernel-budget-native.py', '--compiler', aurorac, '--output', '@ARTIFACTS@'],
     depends: aurorac, suite: ['full', 'merge', 'slow', 'integration'], env: native_artifact_env,
     workdir: native_root, timeout: 900)
test('native-policy-round-robin', python, args: native_artifact_args + ['--compiler', aurorac, '--', python, '-B', '-O', files('../../tests/kernel-round-robin-native.py'), '--compiler', aurorac, '--output', '@ARTIFACTS@'],
     depends: aurorac, suite: ['full', 'merge', 'slow', 'integration'], env: native_artifact_env,
     workdir: native_root, timeout: 900)
test('native-policy-ipc-transition', python, args: native_artifact_args + ['--compiler', aurorac, '--', python, '-B', '-O', files('../../tests/kernel-ipc-transition-native.py'), '--compiler', aurorac, '--output', '@ARTIFACTS@'],
     depends: aurorac, suite: ['full', 'merge', 'slow', 'integration'], env: native_artifact_env,
     workdir: native_root, timeout: 900)
test('native-policy-client-disposal', python, args: native_artifact_args + ['--compiler', aurorac, '--', python, '-B', '-O', files('../../tests/kernel-client-disposal-native.py'), '--compiler', aurorac, '--output', '@ARTIFACTS@'],
     depends: aurorac, suite: ['full', 'merge', 'slow', 'integration'], env: native_artifact_env,
     workdir: native_root, timeout: 900)
test('native-policy-terminal-event', python, args: native_artifact_args + ['--compiler', aurorac, '--', python, '-B', '-O', native_root / 'tests/kernel-terminal-event-native.py', '--compiler', aurorac, '--output', '@ARTIFACTS@'],
     depends: aurorac, suite: ['full', 'merge', 'slow', 'integration'], env: native_artifact_env,
     workdir: native_root, timeout: 900)
test('native-pin-integration', python, args: native_adapter_args + ['--shared-output'] + ['--', find_program('bash', native: true), files('../../scripts/kernel-pin-tests.sh')],
     suite: ['full', 'merge', 'slow', 'integration'], env: native_test_env, workdir: native_root,
     timeout: 1800)
test('native-nvme-queue-integration', python, args: native_adapter_args + ['--shared-output'] + ['--', find_program('bash', native: true), files('../../scripts/kernel-nvme-queue-tests.sh')],
     suite: ['full', 'merge', 'slow', 'integration'], env: native_test_env, workdir: native_root,
     timeout: 1800)
test('native-dormant-integration', python, args: native_artifact_args + ['--', find_program('bash', native: true), files('../../scripts/kernel-dormant-tests.sh'), '@ARTIFACTS@'],
     suite: ['full', 'merge', 'slow', 'integration'], env: native_test_env, workdir: native_root,
     timeout: 1800)
if get_option('kernel_images')
  test('native-uefi-span-integration', python,
       args: native_adapter_args + ['--compiler', aurorac, '--', find_program('bash', native: true),
              files('../../scripts/kernel-uefi-span-tests.sh'), '--images',
              meson.project_build_root() / 'kernel-images/uefi/runtime',
              meson.project_build_root() / 'kernel-images/uefi/runtime-span'],
       suite: ['full', 'merge', 'slow', 'integration'], env: native_test_env, workdir: native_root,
       timeout: 1800, depends: [aurorac, kernel_profile_users['uefi/runtime'], kernel_profile_users['uefi/runtime-span']])
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
      test('guest-uefi-' + mode, python,
           args: ['-B', artifact_adapter, find_program('bash', native: true), uefi_smoke, '--run-only',
                  meson.project_build_root() / 'kernel-images' / canonical, '--output-dir', '@ARTIFACTS@', mode],
           depends: kernel_profile_images[canonical], suite: ['guest', 'guest-' + family],
           workdir: native_root, timeout: 180)
    endforeach
  endforeach
endif
