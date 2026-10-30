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
              '--local-symbols', '--referenced-reflection-only', '--emit-object',
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

# Model drivers: each groups the kernel model tests that share compiler flags and
# link inputs into one translation unit (tests/native/driver.hpp); every former
# program stays its own named case and Meson test. The runtime, dispatch-layout,
# handoff and page/domain cases reference no policy symbol, so the linked policy
# object and -no-pie are inert for them.
native_kernel_suites = ['full', 'merge', 'slow', 'integration']
native_options = ['optimization=1', 'warning_level=3']
native_drivers = {}
foreach driver : [
    ['bios-models', [native_bios_object], []],
    ['uefi-tables', [native_uefi_object], ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page']],
    ['uefi-user', [native_uefi_object], ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page']],
    ['uefi-multipage', [native_uefi_object], ['-DAURORA_RUNTIME_MULTIPAGE=1', '-DAURORA_RUNTIME_IMAGE_POLICY=multipage']],
    ['uefi-policy-models', [native_uefi_object], []],
    ['uefi-handoff-terminal', [], ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page', '-DAURORA_UEFI_GRAPHICAL_TERMINAL', '-DAURORA_PRODUCTION', '-DAURORA_UEFI_NVME']],
]
  native_drivers += {driver[0]: executable('native-' + driver[0], files(driver[0] + '.cpp') + driver[1],
      native: true, install: false, override_options: native_options, cpp_args: driver[2], link_args: ['-no-pie'])}
endforeach
# Warning level 2 models; the platform group keeps kernel-uefi's non-PIE code.
foreach driver : [
    ['uefi-platform', ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page', '-fno-pie'], ['-no-pie']],
    ['uefi-devices', ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page', '-DNDEBUG'], []],
    ['iommu-models', [], []],
    ['kernel-api', [], []],
]
  native_drivers += {driver[0]: executable('native-' + driver[0], files(driver[0] + '.cpp'),
      native: true, install: false, override_options: ['optimization=1', 'warning_level=2'],
      cpp_args: driver[1], link_args: driver[2])}
endforeach
# The program lifecycle cases also run against the UEFI policy object's terminal producer.
native_drivers += {'lifecycle-uefi-policy': executable('native-lifecycle-uefi-policy', native_uefi_object,
    objects: native_drivers['bios-models'].extract_objects('bios-models.cpp'),
    native: true, install: false, link_args: ['-no-pie'])}
foreach entry : [
    ['native-kernel-pages', 'bios-models', 'kernel-pages'],
    ['native-kernel-protection', 'bios-models', 'kernel-protection'],
    ['native-kernel-program', 'bios-models', 'kernel-program'],
    ['native-kernel-program-layout', 'bios-models', 'kernel-program-layout'],
    ['native-kernel-domain', 'bios-models', 'kernel-domain'],
    ['native-kernel-schedule', 'bios-models', 'kernel-schedule'],
    ['native-kernel-program-uefi-policy', 'lifecycle-uefi-policy', 'kernel-program'],
    ['native-kernel-program-layout-uefi-policy', 'lifecycle-uefi-policy', 'kernel-program-layout'],
    ['native-kernel-schedule-uefi-policy', 'lifecycle-uefi-policy', 'kernel-schedule'],
    ['native-uefi-runtime', 'uefi-tables', 'kernel-uefi-runtime'],
    ['native-kernel-uefi-dispatch-layout', 'uefi-tables', 'kernel-uefi-dispatch-layout'],
    ['native-kernel-uefi-service-budget', 'uefi-tables', 'kernel-uefi-service-budget'],
    ['native-kernel-uefi-user-run', 'uefi-user', 'kernel-uefi-user-run'],
    ['native-kernel-program-run-authority', 'uefi-user', 'kernel-program-run-authority'],
    ['native-kernel-ipc', 'uefi-user', 'kernel-ipc'],
    ['native-kernel-uefi-console-context', 'uefi-user', 'kernel-uefi-console-context'],
    ['native-uefi-multipage-runtime', 'uefi-multipage', 'kernel-uefi-runtime'],
    ['native-uefi-multipage-user-run', 'uefi-multipage', 'kernel-uefi-user-run'],
    ['native-kernel-dispatch', 'uefi-policy-models', 'kernel-dispatch'],
    ['native-kernel-client-disposal', 'uefi-policy-models', 'kernel-client-disposal'],
    ['native-kernel-uefi', 'uefi-platform', 'kernel-uefi'],
    ['native-kernel-acpi', 'uefi-platform', 'kernel-acpi'],
    ['native-kernel-pci', 'uefi-platform', 'kernel-pci'],
    ['native-kernel-uefi-bar', 'uefi-devices', 'kernel-uefi-bar'],
    ['native-kernel-uefi-bar-record', 'uefi-devices', 'kernel-uefi-bar-record'],
    ['native-kernel-uefi-ivrs', 'uefi-devices', 'kernel-uefi-ivrs'],
]
  test(entry[0], native_drivers[entry[1]], args: [entry[2]], suite: native_kernel_suites,
       env: native_test_env, timeout: 180)
endforeach
# The handoff layout tables, for the production (v7) header and every other image.
foreach entry : [['native-kernel-uefi-handoff', 'uefi-tables'],
                 ['native-kernel-uefi-handoff-terminal', 'uefi-handoff-terminal']]
  test(entry[0], native_drivers[entry[1]], args: ['kernel-uefi-handoff'], suite: ['full', 'merge', 'dev'],
       env: native_test_env, timeout: 60)
endforeach
native_host = executable('native-kernel-program-mailbox', files('../../tests/kernel-program-mailbox.cpp') + [native_program_console_object],
    native: true, install: false, override_options: native_options, link_args: ['-no-pie'])
test('native-kernel-program-mailbox', native_host, suite: native_kernel_suites, env: native_test_env, timeout: 180)
native_host = executable('native-kernel-console', files('../../tests/kernel-console.cpp') + [native_console_object],
    native: true, install: false, override_options: native_options, link_args: ['-no-pie'])
test('native-kernel-console', native_host, suite: native_kernel_suites, env: native_test_env, timeout: 180)
native_host = executable('native-kernel-console-uart', files('../../tests/kernel-console-uart.cpp') + [native_console_object],
    native: true, install: false, override_options: native_options, link_args: ['-no-pie'])
test('native-kernel-console-uart', native_host, suite: native_kernel_suites, env: native_test_env, timeout: 180)
native_host = executable('native-kernel-generated-uart',
    files('../../tests/kernel-console-uart.cpp') + [native_console_object, native_uart_object],
    native: true, install: false, override_options: native_options,
    cpp_args: ['-DAURORA_GENERATED_UART=1'], link_args: ['-no-pie'])
test('native-kernel-generated-uart', native_host, suite: native_kernel_suites, env: native_test_env, timeout: 180)
native_host = executable('native-kernel-port-session', files('../../tests/kernel-port-session.cpp'),
    native: true, install: false, override_options: native_options, link_args: ['-no-pie'])
test('native-kernel-port-session', native_host, suite: native_kernel_suites, env: native_test_env, timeout: 180)
native_host = executable('native-kernel-program-stream', files('../../tests/kernel-program-stream.cpp') + [native_program_console_object],
    native: true, install: false, override_options: native_options, link_args: ['-no-pie'])
test('native-kernel-program-stream', native_host, args: [native_root / 'tests/kernel-program-session.cases'],
     suite: native_kernel_suites, env: native_test_env, timeout: 180)
native_host = executable('native-kernel-owned-bytes', files('../../tests/kernel-owned-bytes.cpp', '../../kernel/owned-bytes.cpp'),
    native: true, install: false, override_options: native_options,
    cpp_args: ['-DNDEBUG', '-fno-exceptions', '-fno-rtti', '-DAURORA_KERNEL_BYTES_TESTING=1'], link_args: ['-no-pie'])
test('native-kernel-owned-bytes', native_host, suite: native_kernel_suites, env: native_test_env, timeout: 180)
native_host = executable('native-round-robin-adapter', files('../../tests/kernel-round-robin-adapter.cpp') + [native_round_robin_object],
    native: true, install: false, override_options: native_options, link_args: ['-no-pie'])
test('native-round-robin-adapter', native_host, suite: native_kernel_suites, env: native_test_env, timeout: 180)
native_host = executable('native-uefi-memory', files('../../tests/kernel-uefi-memory.cpp') + [native_memory_object],
    native: true, install: false, override_options: ['optimization=2', 'debug=false', 'warning_level=2'],
    cpp_args: ['-fno-builtin'], link_args: [])
test('native-uefi-memory', native_host, suite: native_kernel_suites, env: native_test_env, timeout: 180)
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
test('native-unsigned-source', python, args: native_adapter_args + ['--compiler', aurorac.full_path()] + ['--', python] + ['-B', files('../../tests/kernel-unsigned-source.py')],
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
test('native-semantics', python, args: ['-B', files('../../tests/semantics/run.py'), aurorac.full_path()],
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
    ['note-client', 'tests/kernel-programs/program-upper-client.au',
     policies_root + ['--bridge', native_root / 'tests/program-append-client-entry.S', '--localize-reflection']],
    ['note-service', 'tests/kernel-programs/program-stream-service.au',
     policies_root + ['--bridge', native_root / 'tests/program-append-service-entry.S', '--localize-reflection']],
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
test('native-protected-note', native_host, args: [files('../../tests/kernel-program-append-service.cases')],
     suite: ['full', 'merge', 'slow', 'integration'], env: native_test_env, timeout: 120)
# Kernel policies: the real generated UEFI policy object is linked once with the
# C++ observers (cases of uefi-policy-models), whose fixed vector families are
# compared with a golden file. Copy
# probes, hostile-producer adapters (one producer renamed) and source rejections
# are separate programs and golden cases.
foreach policy : ['budget', 'round-robin', 'ipc-transition', 'client-disposal', 'terminal-event']
  test('native-policy-' + policy, python,
       args: ['-B', golden_runner, files('../../tests/kernel-' + policy + '-native.golden'), '--',
              native_drivers['uefi-policy-models'], 'kernel-' + policy + '-native'],
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
foreach adapter : [['ipc-transition', 'aurora_kernel_ipc_transition', '../../tests/kernel-ipc-transition-adapter.cpp', [], []],
                   ['client-disposal', 'aurora_kernel_client_disposal', '../../tests/kernel-client-disposal-adapter.cpp',
                    [], []],
                   ['terminal-event', 'aurora_kernel_terminal_event', 'terminal-event-adapter.cpp',
                    ['-DTERMINAL_SUBSTITUTE'], ['kernel-terminal-event-native']]]
  substituted = custom_target('native-' + adapter[0] + '-substitution', input: native_uefi_object,
      output: adapter[0] + '-substitution.o',
      command: [find_program('objcopy', native: true), '--redefine-sym', adapter[1] + '=' + adapter[1] + '_real',
                '@INPUT@', '@OUTPUT@'])
  native_host = executable('kernel-' + adapter[0] + '-adapter', files(adapter[2]) + [substituted],
      native: true, install: false, override_options: ['optimization=1', 'warning_level=3'],
      cpp_args: adapter[3], link_args: ['-no-pie'])
  test('native-' + adapter[0] + '-adapter', native_host, args: adapter[4], suite: ['full', 'merge', 'slow', 'integration'],
       env: native_test_env, timeout: 60)
endforeach
test('native-policy-rejections', python,
     args: ['-B', golden_runner, files('../../tests/kernel-policy-rejections.golden'), '--reject', '--', aurorac.full_path(),
            '--module-root', native_root / 'kernel/policies'],
     suite: ['full', 'merge', 'slow', 'integration'], env: native_test_env, timeout: 120, depends: aurorac)
# Pin ledger, NVMe queue and dormant-table models: programs whose testing macros
# differ are built separately and run their own fixtures; the rest are cases of
# the iommu-models, kernel-api and uefi-devices drivers. The configuration
# guards are compile-fail cases.
foreach program : [
    ['kernel-pin-ledger', 'kernel-pin-ledger.cpp', ['-DAURORA_PIN_LEDGER_TESTING=1']],
    ['kernel-pin-ledger-generation-3', 'kernel-pin-ledger.cpp',
     ['-DAURORA_PIN_LEDGER_TESTING=1', '-DAURORA_PIN_LEDGER_TEST_GENERATION_LIMIT=3']],
    ['kernel-nvme-queues', 'kernel-nvme-queues.cpp',
     ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page', '-DNDEBUG', '-DAURORA_NVME_QUEUE_TESTING=1']],
    ['kernel-nvme-queues-generation-3', 'kernel-nvme-queues.cpp',
     ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page', '-DNDEBUG', '-DAURORA_NVME_QUEUE_TESTING=1',
      '-DAURORA_NVME_QUEUE_GENERATION_LIMIT=3']],
    ['kernel-dormant-oracle', 'kernel-dormant-oracle.cpp', []],
    ['kernel-dormant-generation', 'kernel-dormant-generation.cpp',
     ['-DAURORA_PIN_LEDGER_TESTING=1', '-DAURORA_PIN_LEDGER_TEST_GENERATION_LIMIT=3']],
]
  native_host = executable(program[0], files('../../tests/' + program[1]),
      native: true, install: false, override_options: ['optimization=1', 'warning_level=2'],
      cpp_args: program[2])
  test(program[0], native_host, suite: ['full', 'merge', 'slow', 'integration'], env: native_test_env, timeout: 120)
endforeach
foreach entry : [['iommu-models', 'kernel-dormant-tables'], ['iommu-models', 'kernel-dormant-decoder'],
                 ['iommu-models', 'kernel-iommu-oracle'], ['iommu-models', 'kernel-iommu-event-completion'],
                 ['kernel-api', 'kernel-dormant-api'], ['kernel-api', 'kernel-pin-api'],
                 ['uefi-devices', 'kernel-nvme-queues-api']]
  test(entry[1], native_drivers[entry[0]], args: [entry[1]], suite: ['full', 'merge', 'slow', 'integration'],
       env: native_test_env, timeout: 120)
endforeach
test('kernel-compile-fail', python,
     args: ['-B', files('../compile_fail.py'), files('../kernel-compile-fail.txt'), native_root] + native_cpp.cmd_array(),
     suite: ['full', 'merge', 'slow', 'integration'], env: native_test_env, timeout: 120)
if get_option('kernel_images')
  test('native-uefi-span-integration', python,
       args: ['-B', files('../../tests/kernel-uefi-span.py'), aurorac.full_path(),
              meson.project_build_root() / 'kernel-images/uefi/runtime-fixture'],
       suite: ['full', 'merge', 'slow', 'integration'], env: native_test_env, workdir: native_root,
       timeout: 120, depends: [aurorac, kernel_profile_users['uefi/runtime-fixture']])
endif

# UEFI guest families (QEMU), outside full: meson test --suite guest or guest-<family>.
# The self-host family, the compiler compiling itself in the guest for minutes,
# is also in the release suite.
if get_option('kernel_images')
  uefi_smoke = files('../../scripts/kernel-uefi-smoke.sh')
  foreach family : profile_data['guests'].split('|')
    foreach mode : profile_data['guests.' + family].split('|')
      canonical = profile_data.get('aliases.uefi/' + mode, 'uefi/' + mode)
      test('guest-uefi-' + mode, find_program('bash', native: true),
           args: [uefi_smoke, '--run-only', meson.project_build_root() / 'kernel-images' / canonical, mode],
           depends: kernel_profile_images[canonical] + process_references.get(mode, []),
           suite: ['guest', 'guest-' + family] + (family == 'self-host' ? ['release'] : []),
           # These full-capacity workloads measure original-clock deadlines
           # without other Meson tests running, not competing-emulator throughput.
           is_parallel: mode != 'process-files' and mode != 'process-service',
           workdir: native_root, timeout: profile_data.get('guest_timeouts.' + mode, '60').to_int() + 120)
    endforeach
  endforeach
  # The production image: its protected program console through the PTY oracle,
  # then serial commands plus the graphical terminal's framebuffer in one guest.
  test('guest-uefi-production', python,
       args: ['-B', files('../../scripts/kernel_production_smoke.py'),
              '--build-dir', meson.project_build_root() / 'kernel-images/uefi/production',
              '--renderer', graphical_terminal_host],
       depends: kernel_profile_images['uefi/production'] + [graphical_terminal_host,
                process_programs['aurora:process-hostile'], process_programs['aurora:process-lifecycle'],
                process_programs['aurora:host-files-probe'], process_programs['assembly:process-isolation-3'],
                process_programs['assembly:process-isolation-6'], process_programs['aurora:console-commit-hostile']],
       suite: ['guest', 'guest-production'], workdir: native_root, timeout: 480)
endif
