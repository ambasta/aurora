# Canonical root-native coverage. Included after tests/meson.build definitions.
# Compiler-free controls stay separate; no whole-Make aggregate is nested here.
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
test('native-kernel-pages', native_host, suite: ['full', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-protection', files('../../tests/kernel-protection.cpp') + [native_bios_object],
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: [], link_args: ['-no-pie'])
test('native-kernel-protection', native_host, suite: ['full', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-program', files('../../tests/kernel-program.cpp') + [native_bios_object],
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: [], link_args: ['-no-pie'])
test('native-kernel-program', native_host, suite: ['full', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-program-layout', files('../../tests/kernel-program-layout.cpp') + [native_bios_object],
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: [], link_args: ['-no-pie'])
test('native-kernel-program-layout', native_host, suite: ['full', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-domain', files('../../tests/kernel-domain.cpp') + [native_bios_object],
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: [], link_args: ['-no-pie'])
test('native-kernel-domain', native_host, suite: ['full', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-schedule', files('../../tests/kernel-schedule.cpp') + [native_bios_object],
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: [], link_args: ['-no-pie'])
test('native-kernel-schedule', native_host, suite: ['full', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-uefi-runtime', files('../../tests/kernel-uefi-runtime.cpp') + [native_bios_object],
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page'], link_args: ['-no-pie'])
test('native-uefi-runtime', native_host, suite: ['full', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-uefi-multipage-runtime', files('../../tests/kernel-uefi-runtime.cpp') + [native_bios_object],
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: ['-DAURORA_RUNTIME_MULTIPAGE=1', '-DAURORA_RUNTIME_IMAGE_POLICY=multipage'], link_args: ['-no-pie'])
test('native-uefi-multipage-runtime', native_host, suite: ['full', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-ipc', files('../../tests/kernel-ipc.cpp') + [native_uefi_object],
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page'], link_args: ['-no-pie'])
test('native-kernel-ipc', native_host, suite: ['full', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-program-mailbox', files('../../tests/kernel-program-mailbox.cpp') + [native_program_console_object],
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: [], link_args: ['-no-pie'])
test('native-kernel-program-mailbox', native_host, suite: ['full', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-uefi-service-budget', files('../../tests/kernel-uefi-service-budget.cpp') + [native_uefi_object],
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page'], link_args: ['-no-pie'])
test('native-kernel-uefi-service-budget', native_host, suite: ['full', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-uefi-dispatch-layout', files('../../tests/kernel-uefi-dispatch-layout.cpp') + [native_uefi_object],
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page'], link_args: ['-no-pie'])
test('native-kernel-uefi-dispatch-layout', native_host, suite: ['full', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-dispatch', files('../../tests/kernel-dispatch.cpp') + [native_uefi_object],
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: [], link_args: ['-no-pie'])
test('native-kernel-dispatch', native_host, suite: ['full', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-uefi-user-run', files('../../tests/kernel-uefi-user-run.cpp') + [native_uefi_object],
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page'], link_args: ['-no-pie'])
test('native-kernel-uefi-user-run', native_host, suite: ['full', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-uefi-multipage-user-run', files('../../tests/kernel-uefi-user-run.cpp') + [native_uefi_object],
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: ['-DAURORA_RUNTIME_MULTIPAGE=1', '-DAURORA_RUNTIME_IMAGE_POLICY=multipage'], link_args: ['-no-pie'])
test('native-uefi-multipage-user-run', native_host, suite: ['full', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-client-disposal', files('../../tests/kernel-client-disposal.cpp') + [native_uefi_object],
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: [], link_args: ['-no-pie'])
test('native-kernel-client-disposal', native_host, suite: ['full', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-console', files('../../tests/kernel-console.cpp') + [native_console_object],
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: [], link_args: ['-no-pie'])
test('native-kernel-console', native_host, suite: ['full', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-console-uart', files('../../tests/kernel-console-uart.cpp') + [native_console_object],
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: [], link_args: ['-no-pie'])
test('native-kernel-console-uart', native_host, suite: ['full', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-generated-uart',
    files('../../tests/kernel-console-uart.cpp') + [native_console_object, native_uart_object],
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: ['-DAURORA_GENERATED_UART=1'], link_args: ['-no-pie'])
test('native-kernel-generated-uart', native_host, suite: ['full', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-port-session', files('../../tests/kernel-port-session.cpp'),
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: [], link_args: ['-no-pie'])
test('native-kernel-port-session', native_host, suite: ['full', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-uefi', files('../../tests/kernel-uefi.cpp'),
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=2'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page', '-fno-pie'], link_args: ['-no-pie'])
test('native-kernel-uefi', native_host, suite: ['full', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-acpi', files('../../tests/kernel-acpi.cpp'),
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=2'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page'], link_args: [])
test('native-kernel-acpi', native_host, suite: ['full', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-pci', files('../../tests/kernel-pci.cpp'),
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=2'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page'], link_args: [])
test('native-kernel-pci', native_host, suite: ['full', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-program-stream', files('../../tests/kernel-program-stream.cpp') + [native_program_console_object],
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: [], link_args: ['-no-pie'])
test('native-kernel-program-stream', native_host, suite: ['full', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-program-run-authority', files('../../tests/kernel-program-run-authority.cpp'),
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page'], link_args: ['-no-pie'])
test('native-kernel-program-run-authority', native_host, suite: ['full', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-uefi-bar', files('../../tests/kernel-uefi-bar.cpp'),
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=2'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page', '-DNDEBUG'], link_args: [])
test('native-kernel-uefi-bar', native_host, suite: ['full', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-uefi-bar-record', files('../../tests/kernel-uefi-bar-record.cpp'),
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=2'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page', '-DNDEBUG'], link_args: [])
test('native-kernel-uefi-bar-record', native_host, suite: ['full', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-uefi-ivrs', files('../../tests/kernel-uefi-ivrs.cpp'),
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=2'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page', '-DNDEBUG'], link_args: [])
test('native-kernel-uefi-ivrs', native_host, suite: ['full', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-kernel-owned-bytes', files('../../tests/kernel-owned-bytes.cpp', '../../kernel/owned-bytes.cpp'),
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: ['-DNDEBUG', '-fno-exceptions', '-fno-rtti', '-DAURORA_KERNEL_BYTES_TESTING=1'], link_args: ['-no-pie'])
test('native-kernel-owned-bytes', native_host, suite: ['full', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-round-robin-adapter', files('../../tests/kernel-round-robin-adapter.cpp') + [native_round_robin_object],
    native: true, install: false, override_options: ['optimization=1', 'debug=true', 'warning_level=3'],
    cpp_args: [], link_args: ['-no-pie'])
test('native-round-robin-adapter', native_host, suite: ['full', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-uefi-memory', files('../../tests/kernel-uefi-memory.cpp') + [native_memory_object],
    native: true, install: false, override_options: ['optimization=2', 'debug=false', 'warning_level=2'],
    cpp_args: ['-fno-builtin'], link_args: [])
test('native-uefi-memory', native_host, suite: ['full', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
test('native-uefi-memory-symbols', python,
    args: ['-B', files('memory-object.py'), native_memory_object],
    suite: ['full', 'slow', 'integration'], env: native_test_env, timeout: 30)
native_host = executable('native-uefi-framebuffer', files('../../tests/kernel-uefi-framebuffer.cpp'),
    native: true, install: false, override_options: ['optimization=1', 'debug=false', 'warning_level=3'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page'], link_args: ['-no-pie'])
test('native-uefi-framebuffer', native_host, suite: ['full', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-uefi-framebuffer-tables', files('../../tests/kernel-uefi-framebuffer-tables.cpp'),
    native: true, install: false, override_options: ['optimization=1', 'debug=false', 'warning_level=3'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page'], link_args: ['-no-pie'])
test('native-uefi-framebuffer-tables', native_host, suite: ['full', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-uefi-framebuffer-loader', files('../../tests/kernel-uefi-framebuffer-loader.cpp'),
    native: true, install: false, override_options: ['optimization=1', 'debug=false', 'warning_level=3'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page'], link_args: ['-no-pie'])
test('native-uefi-framebuffer-loader', native_host, suite: ['full', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-uefi-framebuffer-pixels', files('../../tests/kernel-uefi-framebuffer-pixels.cpp'),
    native: true, install: false, override_options: ['optimization=1', 'debug=false', 'warning_level=3'],
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page'], link_args: ['-no-pie'])
test('native-uefi-framebuffer-pixels', native_host, suite: ['full', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
native_host = executable('native-display-session', files('../../tests/kernel-display-session.cpp'),
    native: true, install: false, override_options: ['optimization=1', 'debug=false', 'warning_level=3'],
    cpp_args: [], link_args: [])
test('native-display-session', native_host, suite: ['full', 'slow', 'integration'],
     env: native_test_env, timeout: 180)
test('native-kernel-smoke-controls', python, args: ['-B', files('../../tests/kernel-smoke.py'), '--self-test'],
     suite: ['full', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 180)
test('native-kernel-schedule-controls', python, args: ['-B', files('../../tests/kernel-schedule-smoke.py'), '--self-test'],
     suite: ['full', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 180)
test('native-uefi-smoke-controls', python, args: ['-B', '-O', files('../../tests/kernel-uefi-smoke.py'), '--self-test'],
     suite: ['full', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 180)
test('native-acpi-smoke-controls', python, args: ['-B', '-O', files('../../tests/kernel-acpi-smoke.py'), '--self-test'],
     suite: ['full', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 180)
test('native-pci-smoke-controls', python, args: ['-B', '-O', files('../../tests/kernel-pci-smoke.py'), '--self-test'],
     suite: ['full', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 180)
test('native-uefi-runtime-smoke-controls', python, args: ['-B', '-O', files('../../tests/kernel-uefi-runtime-smoke.py'), '--self-test'],
     suite: ['full', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 180)
test('native-uefi-ipc-smoke-controls', python, args: ['-B', '-O', files('../../tests/kernel-uefi-ipc-smoke.py'), '--self-test'],
     suite: ['full', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 180)
test('native-uefi-budget-smoke-controls', python, args: ['-B', '-O', files('../../tests/kernel-uefi-budget-smoke.py'), '--self-test'],
     suite: ['full', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 180)
test('native-uefi-dispatch-smoke-controls', python, args: ['-B', '-O', files('../../tests/kernel-uefi-dispatch-smoke.py'), '--self-test'],
     suite: ['full', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 180)
test('native-uefi-user-phases-smoke-controls', python, args: ['-B', '-O', files('../../tests/kernel-uefi-user-phases-smoke.py'), '--self-test'],
     suite: ['full', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 180)
test('native-division-image-optimized', python, args: ['-B', '-O', files('../../tests/kernel-division-image.py')],
     suite: ['full', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 180)
test('native-division-smoke-controls-optimized', python, args: ['-B', '-O', files('../../tests/kernel-division-smoke.py'), '--self-test'],
     suite: ['full', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 180)
test('native-unsigned-image-optimized', python, args: ['-B', '-O', files('../../tests/kernel-unsigned-image.py')],
     suite: ['full', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 180)
test('native-unsigned-smoke-controls-optimized', python, args: ['-B', '-O', files('../../tests/kernel-unsigned-smoke.py'), '--self-test'],
     suite: ['full', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 180)
test('native-unsigned-source', python, args: native_adapter_args + ['--compiler', aurorac] + ['--', python] + ['-B', files('../../tests/kernel-unsigned-source.py')],
     suite: ['full', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 180, depends: aurorac)
test('native-uefi-user-image', python, args: ['-B', '-O', files('../../tests/kernel-uefi-user-image.py')],
     suite: ['full', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 180)
test('native-uefi-ipc-image', python, args: ['-B', '-O', files('../../tests/kernel-uefi-ipc-image.py')],
     suite: ['full', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 180)
test('native-uefi-budget-image', python, args: ['-B', '-O', files('../../tests/kernel-uefi-budget-image.py')],
     suite: ['full', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 180)
test('native-uefi-dispatch-image', python, args: ['-B', '-O', files('../../tests/kernel-uefi-dispatch-image.py')],
     suite: ['full', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 180)
test('native-uefi-user-phases-image', python, args: ['-B', '-O', files('../../tests/kernel-uefi-user-phases-image.py')],
     suite: ['full', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 180)
test('native-uefi-bar-smoke-controls', python, args: ['-B', '-O', files('../../tests/kernel-uefi-bar-smoke.py'), '--self-test'],
     suite: ['full', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 180)
test('native-uefi-bar-trace-controls', python, args: ['-B', '-O', files('../../tests/kernel-uefi-bar-trace.py'), '--self-test'],
     suite: ['full', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 180)
test('native-uefi-bar-provenance-controls', python, args: ['-B', '-O', files('../../tests/kernel-uefi-bar-provenance.py'), '--self-test'],
     suite: ['full', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 180)
test('native-uefi-ivrs-stack-controls', python, args: ['-B', '-O', files('../../tests/kernel-uefi-ivrs-stack.py'), '--self-test'],
     suite: ['full', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 180)
test('native-uefi-ivrs-smoke-controls', python, args: ['-B', '-O', files('../../tests/kernel-uefi-ivrs-smoke.py'), '--self-test'],
     suite: ['full', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 180)
test('native-uefi-ivrs-trace-controls', python, args: ['-B', '-O', files('../../tests/kernel-uefi-ivrs-trace.py'), '--self-test'],
     suite: ['full', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 180)
test('native-uefi-ivrs-provenance-controls', python, args: ['-B', '-O', files('../../tests/kernel-uefi-ivrs-provenance.py'), '--self-test'],
     suite: ['full', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 180)
# These controls observe the whole source/build tree; unrelated writers must stop.
test('native-test-compiler-contract', python, args: ['-B', files('../../tests/test_compiler_contract.py')],
     suite: ['full', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 300, is_parallel: false)
test('native-uefi-owned-bytes-admission-optimized', python, args: ['-B', '-O', files('../../tests/kernel-uefi-owned-bytes-admission.py'), '--self-test'],
     suite: ['full', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 180)
test('native-uefi-owned-bytes-stack-optimized', python, args: ['-B', '-O', files('../../tests/kernel-uefi-owned-bytes-stack.py'), '--self-test'],
     suite: ['full', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 180)
test('native-uefi-pin-smoke-controls-optimized', python, args: ['-B', '-O', files('../../tests/kernel-uefi-pin-smoke.py')],
     suite: ['full', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 180)
test('native-uefi-tables-smoke-controls-optimized', python, args: ['-B', '-O', files('../../tests/kernel-uefi-tables-smoke.py')],
     suite: ['full', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 180)
test('native-storage-test-durability-optimized', python, args: ['-B', '-O', files('../../storage/design/model/test_durability.py')],
     suite: ['full', 'slow', 'storage'], env: native_test_env,
     workdir: native_root, timeout: 180)
test('native-storage-check-traceability-optimized', python, args: ['-B', '-O', files('../../storage/design/model/check_traceability.py')],
     suite: ['full', 'slow', 'storage'], env: native_test_env,
     workdir: native_root, timeout: 180)
test('native-storage-test-traceability-optimized', python, args: ['-B', '-O', files('../../storage/design/model/test_traceability.py')],
     suite: ['full', 'slow', 'storage'], env: native_test_env,
     workdir: native_root, timeout: 180)
test('native-kernel-boot-image-optimized', python, args: ['-B', '-O', files('../../tests/kernel-boot-image.py')],
     suite: ['full', 'slow', 'boot'], env: native_test_env,
     workdir: native_root, timeout: 300)
test('native-kernel-boot-capacity-optimized', python, args: ['-B', '-O', files('../../tests/kernel-boot-capacity.py')],
     suite: ['full', 'slow', 'boot'], env: native_test_env,
     workdir: native_root, timeout: 300)
test('native-native-cap-contracts-optimized', python,
     args: ['-B', artifact_adapter, python, '-B', '-O', files('../../tests/native-cap-contracts.py'), '--artifacts', '@ARTIFACTS@'],
     suite: ['full', 'slow', 'integration'], env: native_artifact_env,
     workdir: native_root, timeout: 300)
test('native-test-compiler-contract-optimized', python, args: ['-B', '-O', files('../../tests/test_compiler_contract.py')],
     suite: ['full', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 300, is_parallel: false)
test('native-kernel-emulator-clock-optimized', python, args: ['-B', '-O', files('../../tests/kernel-emulator-clock.py')],
     suite: ['full', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 300)
test('native-kernel-program-admission-optimized', python, args: ['-B', '-O', files('../../tests/kernel-program-admission.py')],
     suite: ['full', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 180)
test('native-kernel-program-console-transcript-optimized', python, args: ['-B', '-O', files('../../tests/kernel-program-console-transcript.py')],
     suite: ['full', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 180)
test('native-uefi-tables-stack-controls', python, args: ['-B', files('../../tests/kernel-uefi-tables-stack.py'), '--self-test'],
     suite: ['full', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 180)
test('native-scratchpad-console-transcript', python,
    args: ['-B', '-O', files('../../tests/kernel-scratchpad-console-transcript.py')],
    suite: ['full', 'dev', 'slow', 'integration'], env: native_test_env,
    workdir: native_root, timeout: 120)

test('native-program-console-routing', python, args: ['-B', files('../../tests/kernel-program-console-routing.py')],
     suite: ['full', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 180)
test('native-program-console-entrypoints-optimized', python, args: ['-B', '-O', files('../../tests/kernel-program-console-entrypoints.py')],
     suite: ['full', 'dev', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 60)
test('native-semantics-harness', python, args: ['-B', files('../../tests/semantics/test_runner.py')],
     suite: ['full', 'slow', 'semantics'], env: native_test_env,
     workdir: native_root, timeout: 180)
test('native-semantics', python, args: native_adapter_args + ['--compiler', aurorac] + ['--', python] + ['-B', files('../../tests/semantics/run.py'), aurorac],
     suite: ['full', 'slow', 'semantics'], env: native_test_env,
     workdir: native_root, timeout: 1200, depends: aurorac)
test('native-protected-note', python,
     args: native_artifact_args + ['--compiler', aurorac, '--', find_program('bash', native: true),
                                  files('../../scripts/kernel-program-note-tests.sh'), '@ARTIFACTS@'],
     depends: aurorac, suite: ['full', 'slow', 'integration'], env: native_artifact_env,
     workdir: native_root, timeout: 900)
test('native-protected-snapshot', python,
     args: native_artifact_args + ['--compiler', aurorac, '--', find_program('bash', native: true),
                                  files('../../scripts/kernel-snapshot-tests.sh'), '@ARTIFACTS@'],
     depends: aurorac, suite: ['full', 'slow', 'integration'], env: native_artifact_env,
     workdir: native_root, timeout: 900)
test('native-snapshot-smoke-controls', python,
     args: ['-B', '-O', files('../../tests/kernel-snapshot-smoke.py'), '--self-test'],
     suite: ['full', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 180)
test('native-policy-budget', python, args: native_artifact_args + ['--compiler', aurorac, '--', python, '-B', '-O', native_root / 'tests/kernel-budget-native.py', '--compiler', aurorac, '--meson-selected-compiler', '--candidate-cap-mib', '1024', '--output', '@ARTIFACTS@'],
     depends: aurorac, suite: ['full', 'slow', 'integration'], env: native_artifact_env,
     workdir: native_root, timeout: 900)
test('native-policy-round-robin', python, args: native_artifact_args + ['--compiler', aurorac, '--', python, '-B', '-O', files('../../tests/kernel-round-robin-native.py'), '--compiler', aurorac, '--meson-selected-compiler', '--candidate-cap-mib', '1024', '--output', '@ARTIFACTS@'],
     depends: aurorac, suite: ['full', 'slow', 'integration'], env: native_artifact_env,
     workdir: native_root, timeout: 900)
test('native-policy-ipc-transition', python, args: native_artifact_args + ['--compiler', aurorac, '--', python, '-B', '-O', files('../../tests/kernel-ipc-transition-native.py'), '--compiler', aurorac, '--meson-selected-compiler', '--candidate-cap-mib', '1024', '--output', '@ARTIFACTS@'],
     depends: aurorac, suite: ['full', 'slow', 'integration'], env: native_artifact_env,
     workdir: native_root, timeout: 900)
test('native-policy-client-disposal', python, args: native_artifact_args + ['--compiler', aurorac, '--', python, '-B', '-O', files('../../tests/kernel-client-disposal-native.py'), '--compiler', aurorac, '--meson-selected-compiler', '--output', '@ARTIFACTS@'],
     depends: aurorac, suite: ['full', 'slow', 'integration'], env: native_artifact_env,
     workdir: native_root, timeout: 900)
test('native-policy-terminal-event', python, args: native_artifact_args + ['--compiler', aurorac, '--', python, '-B', '-O', native_root / 'tests/kernel-terminal-event-native.py', '--compiler', aurorac, '--meson-selected-compiler', '--output', '@ARTIFACTS@'],
     depends: aurorac, suite: ['full', 'slow', 'integration'], env: native_artifact_env,
     workdir: native_root, timeout: 900)
test('native-pin-integration', python, args: native_adapter_args + ['--shared-output'] + ['--', find_program('bash', native: true), files('../../scripts/kernel-pin-tests.sh')],
     suite: ['full', 'slow', 'integration'], env: native_test_env, workdir: native_root,
     timeout: 1800)
test('native-nvme-queue-integration', python, args: native_adapter_args + ['--shared-output'] + ['--', find_program('bash', native: true), files('../../scripts/kernel-nvme-queue-tests.sh')],
     suite: ['full', 'slow', 'integration'], env: native_test_env, workdir: native_root,
     timeout: 1800)
test('native-dormant-integration', python, args: native_artifact_args + ['--', find_program('bash', native: true), files('../../scripts/kernel-dormant-tests.sh'), '@ARTIFACTS@'],
     suite: ['full', 'slow', 'integration'], env: native_test_env, workdir: native_root,
     timeout: 1800)
if get_option('kernel_images')
  test('native-uefi-span-integration', python,
       args: native_adapter_args + ['--compiler', aurorac, '--', find_program('bash', native: true),
              files('../../scripts/kernel-uefi-span-tests.sh'), '--images',
              meson.project_build_root() / 'kernel-images/uefi/runtime',
              meson.project_build_root() / 'kernel-images/uefi/runtime-span'],
       suite: ['full', 'slow', 'integration'], env: native_test_env, workdir: native_root,
       timeout: 1800, depends: [aurorac, kernel_profile_users['uefi/runtime'], kernel_profile_users['uefi/runtime-span']])
  foreach mode : ['runtime-owned-text', 'runtime-owned-text-fixture']
    test('native-uefi-' + mode + '-image', python,
      args: ['-B', files('../../tests/kernel-uefi-image.py'), '--build-dir',
             meson.project_build_root() / 'kernel-images/uefi' / mode, '--owned-text', '--check-only'],
      depends: kernel_profile_images['uefi/' + mode], suite: ['full', 'slow', 'integration', 'boot'],
      env: native_test_env, workdir: native_root, timeout: 900)
  endforeach
  foreach mode : ['runtime-console-region', 'runtime-console-region-fixture']
    test('native-uefi-' + mode + '-image', python,
      args: ['-B', files('../../tests/kernel-uefi-image.py'), '--build-dir',
             meson.project_build_root() / 'kernel-images/uefi' / mode, '--owned-text', '--console-region', '--check-only'],
      depends: kernel_profile_images['uefi/' + mode], suite: ['full', 'slow', 'integration', 'boot'],
      env: native_test_env, workdir: native_root, timeout: 900)
  endforeach
  foreach mode : ['user-ram-file', 'user-ram-file-fixture']
    test('native-uefi-' + mode + '-image', python,
      args: ['-B', files('../../tests/kernel-uefi-image.py'), '--build-dir',
             meson.project_build_root() / 'kernel-images/uefi' / mode, '--ipc-policy', '--check-only'],
      depends: kernel_profile_images['uefi/' + mode], suite: ['full', 'slow', 'integration', 'boot'],
      env: native_test_env, workdir: native_root, timeout: 900)
  endforeach
  test('native-uefi-ram-file-linked-image', python,
      args: ['-B', '-O', files('../../tests/kernel-uefi-user-phases-image.py'), '--ram-file-build-dir',
             meson.project_build_root() / 'kernel-images/uefi/user-ram-file'],
      depends: kernel_profile_images['uefi/user-ram-file'], suite: ['full', 'slow', 'integration', 'boot'],
      env: native_test_env, workdir: native_root, timeout: 900)
  foreach mode : ['ram-scratchpad-console', 'ram-scratchpad-console-fixture']
    test('native-uefi-' + mode + '-linked-image', python,
      args: ['-B', '-O', files('../../tests/kernel-uefi-user-phases-image.py'), '--ram-scratchpad-build-dir',
             meson.project_build_root() / 'kernel-images/uefi' / mode]
            + (mode == 'ram-scratchpad-console-fixture' ? ['--ram-scratchpad-fixture'] : []),
      depends: kernel_profile_images['uefi/' + mode], suite: ['full', 'slow', 'integration', 'boot'],
      env: native_test_env, workdir: native_root, timeout: 900)
  endforeach
  test('native-bios-image', python,
      args: ['-B', files('../../tests/kernel-image.py'), '--build-dir', bios_image_dir, '--check-only'],
      depends: bios_image, suite: ['full', 'slow', 'integration', 'boot'],
      env: native_test_env, workdir: native_root, timeout: 900)
  test('native-uefi-normal-image', python,
      args: ['-B', files('../../tests/kernel-uefi-image.py'), '--build-dir', uefi_image_dir, '--check-only'],
      depends: uefi_image, suite: ['full', 'slow', 'integration', 'boot'],
      env: native_test_env, workdir: native_root, timeout: 900)
else
  test('native-uefi-span-integration', python,
       args: ['-c', 'raise SystemExit("Kernel images disabled: configure -Dkernel_images=true for full/boot qualification")'],
       suite: ['full', 'slow', 'integration'], env: native_test_env, workdir: native_root, timeout: 1800)
  # Retain explicit failing full/boot coverage, even with --no-rebuild and stale
  # images left by a previous enabled configuration. Hosted compiler/dev is usable.
  foreach image_name : fs.read('kernel-image-tests.txt').strip().split('\n')
    test(image_name, python,
      args: ['-c', 'raise SystemExit("Kernel images disabled: configure -Dkernel_images=true for full/boot qualification")'],
      suite: ['full', 'slow', 'integration', 'boot'],
      env: native_test_env, workdir: native_root, timeout: 900)
  endforeach
endif
test('native-framebuffer-preview-optimized', python, args: ['-B', '-O', files('../../tests/framebuffer-preview.py')],
     suite: ['full', 'dev', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 120)
test('native-uefi-firmware-optimized', python, args: ['-B', '-O', files('../../tests/uefi-firmware.py')],
     suite: ['full', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 180)
test('native-kernel-console-routing-optimized', python, args: ['-B', '-O', files('../../tests/kernel-console-routing.py')],
     suite: ['full', 'dev', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 120)
test('native-kernel-uefi-bar-runner', python, args: ['-B', files('../../tests/kernel-uefi-bar-runner.py')],
     suite: ['full', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 180)
test('native-kernel-uefi-bar-runner-optimized', python, args: ['-B', '-O', files('../../tests/kernel-uefi-bar-runner.py')],
     suite: ['full', 'slow', 'integration'], env: native_test_env,
     workdir: native_root, timeout: 180)

# Compiler-free helper controls; image/ABI/guest qualification remains separate.
test('native-meson-kernel-controls-optimized', python,
  args: ['-B', '-O'] + [files('../meson-kernel-images.py'),
    'GeneratorBoundaries', 'SmokeRunOnlyRouting'],
  suite: ['full', 'dev', 'boot'], env: native_test_env, workdir: native_root, timeout: 30, is_parallel: false)
# Intentional timeout plus descendant cleanup has its own aggregate guard.
test('native-meson-kernel-timeout-controls-optimized', python,
  args: ['-B', '-O'] + [files('../meson-kernel-images.py'), 'WrapperTimeoutCleanup'],
  suite: ['full', 'dev', 'boot'], env: native_test_env, workdir: native_root, timeout: 30, is_parallel: false)
