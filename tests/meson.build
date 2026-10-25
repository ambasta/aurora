# Compiler runner scratch lives beneath this build directory, including module
# alias, FIFO and oversized-source cases. Native routing below handles its own paths.
# Source/library inputs are read-only; parallel tests share no generated paths.
oracle_env = environment()
oracle_env.set('TMPDIR', meson.current_build_dir())
oracle_env.set('TMP', meson.current_build_dir())
oracle_env.set('TEMP', meson.current_build_dir())
oracle_env.set('PYTHONDONTWRITEBYTECODE', '1')
oracle_env.set('CXX', oracle_cxx)
fixture_options = ['optimization=1']
# C++ hosts the record and storage drivers link, built once here instead of by
# every test run; the drivers find them through these variables.
record_hosts = {
  'AURORA_RUNTIME_RECORDS_HOST': static_library('runtime-records-host', 'compiler/runtime_records_host.cpp',
                                                 native: true, override_options: fixture_options, install: false),
  'AURORA_HOSTED_RECORDS_HOST': static_library('hosted-records-host',
                                                ['compiler/hosted_records_host.cpp', '../runtime/hosted_bytes.cpp'],
                                                include_directories: include_directories('..'), native: true,
                                                override_options: fixture_options, install: false),
  'AURORA_STORAGE_RECORD_HOST': static_library('storage-record-host', 'compiler/storage/record_host.cpp',
                                                native: true, override_options: fixture_options, install: false),
}
# The freestanding SIGILL/SIGFPE observer every native_runner program links.
record_hosts += {'AURORA_INTEGER_SIGNAL_OBSERVER': static_library('integer-signal-observer',
    'compiler/integer_signal.cpp', native: true, override_options: fixture_options + ['cpp_eh=none', 'cpp_rtti=false'],
    cpp_args: ['-ffreestanding', '-fno-stack-protector', '-fno-asynchronous-unwind-tables', '-fno-pie'],
    pic: false, install: false)}
foreach name, host : record_hosts
  oracle_env.set(name, host.full_path())
endforeach
record_host_targets = record_hosts.values()
# The pinned formatters over every host source; skipped where they are not installed.
test('style', python, args: ['-B', files('../scripts/style.py'), 'check', '--tree'],
     suite: ['full', 'merge', 'dev'], timeout: 120)
# Shared drivers: golden-output comparison and Aurora fixture objects built once.
golden_runner = files('golden.py')
fixture_builder = files('../scripts/meson-native-fixture.py')
# Test drivers and fixtures are not performance-critical; the code under test in
# hosted_frontend keeps the project optimization level. -O1, not -O0: with GCC 16
# these template-heavy fixtures compile no faster at -O0 and emit ~24x larger
# objects (1.8 GiB in total), while -O1 cuts compile CPU by about a quarter.

# Every test in full is also in exactly one of merge (run on every merge) or
# release (opt-in: releases and compiler bumps). dev/slow/core/bytes are focused
# selections; explicit library enumeration is separate in exhaustive.
# Start the longest merge tests first so they do not form the tail of a run.
slow_tests = {'json-library': 30, 'package-graph': 20, 'method-values': 20,
              'package-manifest': 15, 'hosted-parser': 5, 'decimal-values': 10, 'sector-values-abi': 10,
              'readonly-windows': 5, 'json-string-write': 5, 'composed-values': 5}
foreach entry : [
    ['frontend', 'compiler/run.py', 'core'],
    ['classes', 'compiler/classes.py', 'core'],
    ['value-calls', 'compiler/value_calls.py', 'core'],
    ['owned-mutation', 'compiler/owned_mutation.py', 'core'],
    ['class-arrays', 'compiler/class_arrays.py', 'core'],
    ['owned-bytes', 'compiler/owned_bytes.py', 'core'],
    ['owning-classes', 'compiler/owning_classes.py', 'core'],
    ['binary-literals', 'compiler/binary_literals.py', 'core'],
    ['modules', 'modules/run.py', 'core'],
    ['source-depth', 'modules/robustness.py', 'core'],
    ['byte-literals', 'compiler/byte_literals.py', 'bytes'],
    ['byte-buffer', 'compiler/byte_buffer.py', 'bytes'],
    ['method-spans', 'compiler/method_spans.py', 'bytes'],
    ['owned-spans', 'compiler/owned_spans.py', 'bytes'],
    ['packed-values', 'compiler/packed_values.py', 'bytes'],
    ['sector-values', 'compiler/sector_values.py', 'bytes'],
]
    feedback = 'dev'
    runner_args = ['-B', '-O', files(entry[1]), aurorac]
    test(
        entry[0],
        python,
        args: runner_args,
        depends: aurorac,
        suite: ['full', 'merge', feedback, entry[2], 'compiler'],
        env: oracle_env,
        workdir: meson.current_build_dir(),
        timeout: 300,
        is_parallel: true,
        priority: slow_tests.get(entry[0], 0),
    )
endforeach

test('volatile-file-source-native', python,
    args: ['-B', '-O', files('compiler/volatile_file.py'), aurorac],
    depends: aurorac, suite: ['full', 'merge', 'dev', 'core', 'bytes', 'compiler'],
    env: oracle_env, workdir: meson.current_build_dir(), timeout: 120, is_parallel: true)

# The scratchpad host in its three modes, built once; the runner links each generated root.
scratchpad_hosts = []
scratchpad_args = []
foreach mode : ['client', 'input', 'output']
  scratchpad_hosts += static_library('scratchpad-' + mode + '-host',
      ['compiler/scratchpad_host.cpp', 'compiler/service_group_abi.S'],
      cpp_args: mode == 'output' ? [] : ['-DAURORA_SCRATCHPAD_' + mode.to_upper() + '_TEST'],
      native: true, override_options: fixture_options)
  scratchpad_args += ['--' + mode + '-host', scratchpad_hosts[-1].full_path()]
endforeach
test('scratchpad-source-native', python,
    args: ['-B', '-O', files('compiler/scratchpad.py'), aurorac] + scratchpad_args,
    depends: [aurorac] + scratchpad_hosts, suite: ['full', 'merge', 'dev', 'core', 'bytes', 'compiler'],
    env: oracle_env, workdir: meson.current_build_dir(), timeout: 180, is_parallel: true)

# Model and ownership checks use one standalone source graph. No production
# friendship, synthesized workspace descriptor or overlapping frontend graph is linked.
initialization_probe = custom_target(
    'initialization-probe',
    input: files('compiler/initialization_probe.au', '../compiler/ir_verification_errors.au',
                 '../compiler/ir_verification_storage.au', '../compiler/ir_verification_initialization.au',
                 '../compiler/ir_metadata_storage.au', '../compiler/ir_metadata.au'),
    output: ['initialization-probe.s', 'initialization-probe.generated.s',
             'initialization-probe.abi.json', 'initialization_probe_abi.hpp'],
    command: [python, '-B', files('compiler/initialization_probe.py'), bootstrap_compiler,
              '--compiler-sha256', bootstrap_sha256,
              '--output', '@OUTPUT0@', '--frontend-facts', frontend_assembly[2], '@INPUT@'],
    depend_files: bootstrap_depend_files + files('../scripts/bootstrap_frontend.py', '../scripts/frontend_bridge.py'),
)
initialization_probe_object = custom_target(
    'initialization-probe-object', input: initialization_probe[0], output: 'initialization-probe.o',
    command: native_cpp.cmd_array() + ['-c', '-x', 'assembler', '@INPUT@', '-o', '@OUTPUT@'],
)
initialization_facts = executable(
    'initialization-facts',
    ['compiler/initialization_facts.cpp', 'compiler/initialization_workspace.cpp',
     'compiler/initialization_ownership.cpp', '../runtime/hosted_bytes.cpp',
     initialization_probe_object, initialization_probe[3]],
    dependencies: frontend_headers,
    include_directories: include_directories('.', '../compiler'),
    native: true, override_options: fixture_options,
    install: false,
)
test(
    'initialization-facts',
    initialization_facts,
    suite: ['full', 'merge', 'dev', 'core', 'compiler'],
    timeout: 120,
)


# Textual IR cases (.air) run through one driver; each top-level directory of
# tests/compiler/ir is one test. See tests/compiler/ir/README.md.
# The textual IR printer/reader is test tooling: it stays out of the compiler's
# own library so aurorac (and every image built by it) never waits for it.
ir_text = static_library('ir-text', '../compiler/ir_text.cpp',
    dependencies: hosted_frontend, native: true, override_options: fixture_options, install: false)
aurora_ir_check = executable('aurora-ir-check', 'tools/aurora_ir_check.cpp',
    dependencies: hosted_frontend, link_with: ir_text, include_directories: include_directories('../compiler'),
    native: true, override_options: fixture_options, install: false)
air_lit = files('tools/air_lit.py')
# The large native-ABI programs are loops over call shapes; abi_programs.py
# writes each as one case file per build for its directory test and runner.
abi_air = {}
foreach name : ['method-spans', 'borrowed-objects', 'logical-spans', 'sector-values', 'short-circuit']
    abi_air += {name: custom_target(name + '-abi-air', output: name + '-abi.air',
        input: files('compiler/ir/abi_programs.py'), command: [python, '-B', '@INPUT@', name, '@OUTPUT@'])}
endforeach
air_generated = {'owned-spans-ir': 'logical-spans', 'method-spans-ir': 'method-spans',
                 'borrowed-objects-ir': 'borrowed-objects', 'sector-values-ir': 'sector-values',
                 'short-circuit-ir': 'short-circuit'}
foreach entry : [
    ['verifier-contract', ['full', 'merge', 'dev', 'core', 'compiler']],
    ['class-arrays-ir', ['full', 'merge', 'dev', 'core', 'compiler']],
    ['owned-mutation-ir', ['full', 'merge', 'dev', 'core', 'compiler']],
    ['sector-values-ir', ['full', 'merge', 'dev', 'bytes', 'compiler']],
    ['owned-bytes-ir', ['full', 'merge', 'dev', 'core', 'compiler']],
    ['owning-classes-ir', ['full', 'merge', 'dev', 'core', 'compiler']],
    ['owned-spans-ir', ['full', 'merge', 'dev', 'core', 'bytes', 'compiler']],
    ['method-spans-ir', ['full', 'merge', 'dev', 'core', 'bytes', 'compiler']],
    ['borrowed-objects-ir', ['full', 'merge', 'dev', 'core', 'bytes', 'compiler']],
    ['console-service-ir', ['full', 'merge', 'dev', 'core', 'compiler']],
    ['display-service-ir', ['full', 'merge', 'dev', 'core', 'compiler']],
    ['port-service-ir', ['full', 'merge', 'dev', 'core', 'compiler']],
    ['serve-service-ir', ['full', 'merge', 'dev', 'core', 'compiler']],
    ['iommu-event-service-ir', ['full', 'merge', 'dev', 'core', 'compiler']],
    ['ir-tests', ['full', 'merge', 'slow', 'compiler']],
    ['stack-probes', ['full', 'merge', 'slow', 'compiler']],
    ['method-values-ir', ['full', 'merge', 'slow', 'compiler']],
    ['readonly-windows-ir', ['full', 'merge', 'slow', 'compiler']],
    ['short-circuit-ir', ['full', 'merge', 'slow', 'compiler']],
]
    generated = entry[0] in air_generated ? [abi_air[air_generated[entry[0]]]] : []
    test(entry[0], python,
         args: ['-B', air_lit, aurora_ir_check, meson.current_source_dir() / 'compiler' / 'ir' / entry[0]] + generated,
         depends: [aurora_ir_check] + generated, suite: entry[1], timeout: 120)
endforeach
# Owner, view, writer and emitter API unit tests over modules from the same cases.
ir_api = executable('ir-api', 'compiler/ir_api.cpp',
    dependencies: hosted_frontend, link_with: ir_text, include_directories: include_directories('../compiler'),
    native: true, override_options: fixture_options, install: false)
test('ir-api', ir_api, args: [meson.current_source_dir() / 'compiler' / 'ir'],
     suite: ['full', 'merge', 'dev', 'core', 'compiler'], timeout: 120)

test(
    'owned-mutation-abi',
    python,
    args: ['-B', '-O', files('compiler/owned_mutation_abi.py'), aurora_ir_check],
    depends: aurora_ir_check,
    suite: ['full', 'merge', 'dev', 'core', 'compiler'],
    env: oracle_env,
    workdir: meson.current_build_dir(),
    timeout: 180,
)

test(
    'sector-values-abi',
    python,
    args: ['-B', '-O', files('compiler/sector_values_abi.py'), aurora_ir_check, '--air', abi_air['sector-values']],
    depends: [aurora_ir_check, abi_air['sector-values']],
    suite: ['full', 'merge', 'dev', 'bytes', 'compiler'],
    env: oracle_env,
    workdir: meson.current_build_dir(),
    timeout: 180,
    priority: slow_tests['sector-values-abi'],
)

# Standalone behavioral runners participate in the ordinary full graph.
lint_fixture = executable(
    'lint-fixture', 'compiler/lint.cpp',
    include_directories: include_directories('../compiler'), dependencies: hosted_frontend,
    native: true, override_options: fixture_options, install: false,
)
test('semantic-lint', python,
     args: ['-B', files('compiler/lint.py'), aurora_fmt, aurorac, lint_fixture],
     depends: [aurora_fmt, aurorac, lint_fixture], suite: ['full', 'merge', 'dev', 'compiler'],
     env: oracle_env, workdir: meson.current_build_dir(), timeout: 180)


# Runtime-owned bytes are a hosted bootstrap boundary, separate from freestanding core.
owned_bytes_host = executable(
    'owned-bytes-host', ['compiler/owned_bytes_host.cpp', '../runtime/hosted_bytes.cpp'],
    cpp_args: ['-DAURORA_HOSTED_BYTES_TESTING'], native: true, override_options: fixture_options, install: false,
)
test('owned-bytes-host', owned_bytes_host, suite: ['full', 'merge', 'dev', 'core', 'compiler'], timeout: 120)

# Direct owning classes reuse the hosted byte adapter and private value ABI.
owning_classes_abi_driver = static_library(
    'owning-classes-abi-driver', ['compiler/owning_classes_abi_driver.cpp', '../runtime/hosted_bytes.cpp'],
    include_directories: include_directories('..'), native: true, override_options: fixture_options, install: false,
)
test(
    'owning-classes-abi', python,
    args: ['-B', '-O', files('compiler/owning_classes_abi.py'), aurora_ir_check, owning_classes_abi_driver.full_path()],
    depends: [aurora_ir_check, owning_classes_abi_driver], suite: ['full', 'merge', 'dev', 'core', 'compiler'],
    env: oracle_env, workdir: meson.current_build_dir(), timeout: 180,
)

# Logical owner views share the established readonly-span source type.
test('owned-spans-source', python,
     args: ['-B', '-O', files('compiler/owned_spans_source.py'), aurorac],
     depends: aurorac, suite: ['full', 'merge', 'dev', 'core', 'bytes', 'compiler'], env: oracle_env,
     workdir: meson.current_build_dir(), timeout: 180)
owned_spans_kernel_host = static_library('owned-spans-kernel-host',
    ['compiler/owned_spans_kernel_host.cpp', '../kernel/owned-bytes.cpp'],
    cpp_args: ['-DNDEBUG', '-fno-exceptions', '-fno-rtti'], pic: false,
    native: true, override_options: fixture_options, install: false)
foreach mode : ['standalone', 'receiver']
    span_kernel_args = ['-B', '-O', files('compiler/owned_spans_kernel.py'), aurorac, '--host', owned_spans_kernel_host]
    if mode == 'receiver'
        span_kernel_args += ['--receiver-bound']
    endif
    test('owned-spans-kernel-' + mode, python,
         args: span_kernel_args, depends: [aurorac, owned_spans_kernel_host], suite: ['full', 'merge', 'dev', 'bytes', 'compiler'],
         env: oracle_env, workdir: meson.current_build_dir(), timeout: 180)
endforeach
test('logical-spans-abi', python,
     args: ['-B', '-O', files('compiler/logical_spans_abi.py'), aurora_ir_check, '--air', abi_air['logical-spans']],
     depends: [aurora_ir_check, abi_air['logical-spans']], suite: ['full', 'merge', 'dev', 'core', 'bytes', 'compiler'],
     env: oracle_env, workdir: meson.current_build_dir(), timeout: 180)

# Synchronous method capabilities retain independent IR and literal-layout ABI gates.
test('method-spans-abi', python,
     args: ['-B', '-O', files('compiler/method_spans_abi.py'), aurora_ir_check, '--air', abi_air['method-spans']],
     depends: [aurora_ir_check, abi_air['method-spans']], suite: ['full', 'merge', 'slow', 'core', 'bytes', 'compiler'],
     env: oracle_env, workdir: meson.current_build_dir(), timeout: 180)
# Keep routine borrowed-object feedback small; full owner/helper and literal ABI
# sweeps remain explicit slow coverage. Full/unfiltered runs retain every gate.
test('borrowed-objects-smoke', python,
     args: ['-B', '-O', files('compiler/borrowed_objects.py'), aurorac, '--smoke'],
     depends: aurorac, suite: ['full', 'merge', 'dev', 'bytes', 'compiler'], env: oracle_env,
     workdir: meson.current_build_dir(), timeout: 120, is_parallel: true)
test('borrowed-objects', python,
     args: ['-B', '-O', files('compiler/borrowed_objects.py'), aurorac],
     depends: aurorac, suite: ['full', 'release', 'bytes', 'compiler'], env: oracle_env,
     workdir: meson.current_build_dir(), timeout: 300, is_parallel: true)
test('borrowed-objects-abi', python,
     args: ['-B', '-O', files('compiler/borrowed_objects_abi.py'), aurora_ir_check, '--air', abi_air['borrowed-objects']],
     depends: [aurora_ir_check, abi_air['borrowed-objects']], suite: ['full', 'merge', 'slow', 'core', 'bytes', 'compiler'],
     env: oracle_env, workdir: meson.current_build_dir(), timeout: 180)

# Sealed service authority has its own independent verifier and host-grant model.
console_session = executable('console-session', 'kernel-console-session.cpp', native: true, override_options: fixture_options, install: false)
test('console-session', console_session, suite: ['full', 'merge', 'dev'], timeout: 120)
# Hosts for the console service runner, built once; it links each generated root.
console_service_hosts = {
  'console': static_library('console-service-host', ['compiler/console_service_host.cpp',
                            'compiler/console_service_abi.S'], native: true, override_options: fixture_options),
  'region': static_library('console-service-region-host', ['compiler/console_service_host.cpp',
                           'compiler/console_service_abi.S', '../runtime/hosted_bytes.cpp'],
                           cpp_args: ['-DAURORA_CONSOLE_REGION_TEST'], include_directories: include_directories('..'),
                           native: true, override_options: fixture_options),
  'note': static_library('console-note-policy-host', 'compiler/console_note_policy_host.cpp',
                         native: true, override_options: fixture_options),
  'files': static_library('console-files-policy-host', 'compiler/console_files_policy_host.cpp',
                          native: true, override_options: fixture_options),
}
console_service_args = []
foreach name, host : console_service_hosts
  console_service_args += ['--' + name + '-host', host.full_path()]
endforeach
test('console-service-source-native', python,
     args: ['-B', '-O', files('compiler/console_service.py'), aurorac] + console_service_args,
     depends: [aurorac] + console_service_hosts.values(),
     suite: ['full', 'merge', 'slow', 'core', 'compiler'], env: oracle_env,
     workdir: meson.current_build_dir(), timeout: 300)

# Second sealed kind reuses the service verifier and private bridge.
test('display-service-abi', python,
     args: ['-B', '-O', files('compiler/service_group_ir_abi.py'), aurora_ir_check.full_path()],
     depends: aurora_ir_check, suite: ['full', 'merge', 'dev', 'core', 'compiler'], env: oracle_env, timeout: 120)
test('display-service-source-native', python,
     args: ['-B', '-O', files('compiler/display_service.py'), aurorac],
     depends: aurorac, suite: ['full', 'merge', 'slow', 'core', 'compiler'], env: oracle_env,
     workdir: meson.current_build_dir(), timeout: 300)

# Port remains a sealed singleton with fixed hosted mocks, never native I/O.
test('port-service-source-native', python,
     args: ['-B', '-O', files('compiler/port_service.py'), aurorac, aurora_ir_check.full_path()],
     depends: [aurorac, aurora_ir_check], suite: ['full', 'merge', 'slow', 'core', 'compiler'], env: oracle_env,
     workdir: meson.current_build_dir(), timeout: 300)

# Serve keeps an exact copied two-register result and singleton grant.
test('serve-service-source-native', python,
     args: ['-B', '-O', files('compiler/serve_service.py'), aurorac, aurora_ir_check.full_path()],
     depends: [aurorac, aurora_ir_check], suite: ['full', 'merge', 'slow', 'core', 'compiler'], env: oracle_env,
     workdir: meson.current_build_dir(), timeout: 300)

# Event intake retains the existing service loan graph and executes the real
# Aurora consumer against bounded hosted observations; no guest is run here.
# The independent IR program comes from its textual IR case, printed once.
iommu_event_ir_assembly = custom_target('iommu-event-ir-assembly', output: 'iommu-event-ir.s',
    input: files('compiler/ir/iommu-event-service-ir/abi.air'),
    command: [aurora_ir_check, '--output', '@INPUT@', 'executed', '@OUTPUT@'])
iommu_event_ir_object = custom_target('iommu-event-ir-object', input: iommu_event_ir_assembly,
    output: 'iommu-event-ir.o',
    command: [find_program('as', native: true), '--64', '@INPUT@', files('compiler/iommu_event_ir_bridge.S'),
              '-o', '@OUTPUT@'])
iommu_event_objects = {'ir': iommu_event_ir_object}
foreach fixture : [
    ['consumer', '../examples/kernel-iommu-event-service.au', 'intake', []],
    ['abi', 'compiler/iommu_event_service.au', 'service', []],
    ['cross-module', 'compiler/iommu_event_service_cross.au', 'service',
     ['--module-root', meson.current_source_dir() / 'compiler/iommu-event-modules']],
]
  iommu_event_objects += {fixture[0]: custom_target('iommu-event-' + fixture[0], input: fixture[1],
      output: 'iommu-event-' + fixture[0] + '.o', depfile: 'iommu-event-' + fixture[0] + '.d',
      command: [python, '-B', fixture_builder, '--compiler', aurorac, '--source', '@INPUT@',
                '--module-root', meson.project_source_root() / 'library'] + fixture[3] + [
                '--bridge', files('compiler/iommu_event_' + fixture[2] + '_bridge.S'),
                '--object', '@OUTPUT@', '--depfile', '@DEPFILE@'])}
endforeach
# The executed consumer, its kernel composition, the source ABI fixture (also
# across a module boundary) and the independent IR, each linked once; every
# mode's exit, signal and output is golden.
foreach program : [['consumer', 'compiler/iommu_event_service_host.cpp', 'consumer'],
                   ['composition', 'kernel-iommu-event-composition.cpp', 'consumer'],
                   ['abi', 'compiler/iommu_event_service_host.cpp', 'abi'],
                   ['cross-module', 'compiler/iommu_event_service_host.cpp', 'cross-module'],
                   ['ir', 'compiler/iommu_event_service_host.cpp', 'ir']]
  iommu_event_program = executable('iommu-event-' + program[0],
      [program[1], 'compiler/iommu_event_service_abi.S', iommu_event_objects[program[2]]],
      link_args: ['-no-pie'], native: true, override_options: fixture_options, install: false)
  test('iommu-event-' + program[0], python,
       args: ['-B', golden_runner, files('compiler/iommu-event-' + program[0] + '.golden'), '--modes', '--',
              iommu_event_program],
       suite: ['full', 'merge', 'slow', 'core', 'compiler'], env: oracle_env, timeout: 60)
endforeach
test('iommu-event-rejections', python,
     args: ['-B', golden_runner, files('compiler/iommu_event_service_rejections.golden'), '--reject', '--', aurorac,
            '--check'],
     depends: aurorac, suite: ['full', 'merge', 'slow', 'core', 'compiler'], env: oracle_env, timeout: 60)
iommu_event_session = executable('iommu-event-session', 'kernel-iommu-event-session.cpp', native: true, override_options: fixture_options, install: false)
test('iommu-event-session', iommu_event_session, suite: ['full', 'merge', 'dev'], timeout: 120)
iommu_event_profile = executable('iommu-event-profile', 'kernel-uefi-event-profile.cpp', cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page'], native: true, override_options: fixture_options, install: false)
test('iommu-event-profile', iommu_event_profile, suite: ['full', 'merge', 'dev'], timeout: 120)
iommu_event_backing = executable('iommu-event-backing', 'kernel-uefi-event-backing.cpp', native: true, override_options: fixture_options, install: false)
test('iommu-event-backing', iommu_event_backing, suite: ['full', 'merge', 'dev'], timeout: 120)




# Output-only framebuffer boundary and its actual Aurora software renderer.
framebuffer_models = {}
foreach model : ['framebuffer', 'framebuffer-tables', 'framebuffer-loader', 'framebuffer-pixels']
    framebuffer_models += {model: executable(
        'uefi-' + model, 'kernel-uefi-' + model + '.cpp',
        native: true, override_options: fixture_options, install: false, cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page'], link_args: ['-no-pie'],
    )}
    test('uefi-' + model, framebuffer_models[model], suite: ['full', 'merge', 'dev'], timeout: 120)
endforeach
display_session = executable('display-session', 'kernel-display-session.cpp', native: true, override_options: fixture_options, install: false)
test('display-session', display_session, suite: ['full', 'merge', 'dev'], timeout: 120)
display_page_object = custom_target('display-page',
    input: '../examples/kernel-display-service.au', output: 'display-page.o', depfile: 'display-page.d',
    command: [python, '-B', fixture_builder, '--compiler', aurorac, '--source', '@INPUT@',
              '--module-root', meson.project_source_root() / 'library',
              '--assemble-with', files('../kernel/uefi/display-service-entry.S'),
              '--object', '@OUTPUT@', '--depfile', '@DEPFILE@'])
display_renderer = executable('display-renderer', 'kernel-display-renderer.cpp', display_page_object,
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page'], link_args: ['-no-pie'],
    native: true, override_options: fixture_options, install: false)
test('display-renderer-native', python,
     args: ['-B', golden_runner, files('kernel-display-renderer.golden'), '--modes', '--', display_renderer],
     suite: ['full', 'merge', 'slow'], env: oracle_env, timeout: 60)
# The real generated graphical consumer and the shared font, each compiled and
# linked once with its host; results are compared with the golden files.
graphical_console_object = custom_target('graphical-console-consumer',
    input: '../examples/kernel-graphical-console.au', output: 'graphical-console-consumer.o',
    depfile: 'graphical-console-consumer.d',
    command: [python, '-B', fixture_builder, '--compiler', aurorac, '--source', '@INPUT@',
              '--module-root', meson.project_source_root() / 'library',
              '--assemble-with', files('../kernel/uefi/graphical-console-entry.S'),
              '--object', '@OUTPUT@', '--depfile', '@DEPFILE@'])
graphical_console_host = executable('graphical-console-host', 'kernel-graphical-console.cpp', graphical_console_object,
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page'], link_args: ['-no-pie'],
    native: true, override_options: fixture_options, install: false)
test('graphical-console-native', python, args: ['-B', files('kernel-graphical-console.py'), graphical_console_host],
     suite: ['full', 'merge', 'slow'], env: oracle_env, timeout: 120)
# The production graphical terminal: the real cell grid and generated painter,
# compiled and linked once with its host; results compare with the golden file.
graphical_terminal_object = custom_target('graphical-terminal-painter',
    input: '../examples/kernel-graphical-terminal.au', output: 'graphical-terminal-painter.o',
    depfile: 'graphical-terminal-painter.d',
    command: [python, '-B', fixture_builder, '--compiler', aurorac, '--source', '@INPUT@',
              '--module-root', meson.project_source_root() / 'library', '--local-symbols',
              '--referenced-reflection-only', '--bridge', files('../kernel/uefi/graphical-terminal-entry.S'),
              '--object', '@OUTPUT@', '--depfile', '@DEPFILE@'])
graphical_terminal_host = executable('graphical-terminal-host', 'kernel-graphical-terminal.cpp',
    graphical_terminal_object, cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page'], link_args: ['-no-pie'],
    native: true, override_options: fixture_options, install: false)
test('graphical-terminal-native', python,
     args: ['-B', golden_runner, files('kernel-graphical-terminal.golden'), '--modes', '--', graphical_terminal_host],
     suite: ['full', 'merge', 'dev'], env: oracle_env, timeout: 60)
font_glyphs_object = custom_target('font-glyphs-module',
    input: 'kernel-programs/font-glyphs.au', output: 'font-glyphs.o', depfile: 'font-glyphs.d',
    command: [python, '-B', fixture_builder, '--compiler', aurorac, '--source', '@INPUT@',
              '--module-root', meson.project_source_root() / 'library',
              '--object', '@OUTPUT@', '--depfile', '@DEPFILE@'])
font_glyphs = executable('font-glyphs', 'font-glyphs.cpp', font_glyphs_object,
    native: true, override_options: fixture_options, install: false)
test('font5x7', python, args: ['-B', golden_runner, files('font5x7.golden'), '--', font_glyphs],
     suite: ['full', 'merge', 'dev'], env: oracle_env, timeout: 60)
graphical_paging = executable('graphical-paging', 'kernel-graphical-paging.cpp',
                            cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page'],
                            native: true, install: false, override_options: ['optimization=1'],
                            link_args: ['-no-pie'])
test('graphical-paging', graphical_paging, suite: ['full', 'merge', 'dev'], timeout: 120)

# Previously Make-only source oracles. Library whole-space enumeration is explicit.
foreach runner : [
  'templates', 'function_templates', 'function_overloads', 'fixed_containers',
  'composed_values', 'nested_values', 'decimal_values', 'enum_composition',
  'method_values', 'u8_numeric', 'readonly_spans',
  'integer_oracle', 'unsigned_oracle',
]
  runner_args = ['-B', '-O', files('compiler/' + runner + '.py'), aurorac]
  test(runner.replace('_', '-'), python,
       args: runner_args,
       depends: aurorac, suite: ['full', 'merge', 'slow', 'compiler'], env: oracle_env,
       workdir: meson.current_build_dir(), timeout: 900, is_parallel: true)
endforeach


# Remaining compiler-native coverage. Fixtures are build targets, not commands
# hidden inside each test invocation; Ninja tracks C++ header dependencies.
compiler_fixtures = {}
foreach fixture : [
    'diagnostics', 'lexer_trivia', 'source_overlays',
]
    compiler_fixtures += {fixture: executable(
        fixture.replace('_', '-') + '-fixture', 'compiler/' + fixture + '.cpp',
        dependencies: hosted_frontend,
        include_directories: include_directories('../compiler'), native: true, override_options: fixture_options, install: false,
    )}
endforeach

test('diagnostics', python,
     args: ['-B', '-O', files('compiler/diagnostics.py'), aurorac, compiler_fixtures['diagnostics']],
     depends: [aurorac, compiler_fixtures['diagnostics']], suite: ['full', 'merge', 'slow', 'compiler'],
     env: oracle_env, workdir: meson.current_build_dir(), timeout: 180)
test('source-overlays', python,
     args: ['-B', '-O', files('compiler/source_overlays.py'), compiler_fixtures['source_overlays']],
     depends: compiler_fixtures['source_overlays'], suite: ['full', 'merge', 'slow', 'compiler'],
     env: oracle_env, workdir: meson.current_build_dir(), timeout: 120)
test('lexer-trivia', compiler_fixtures['lexer_trivia'], suite: ['full', 'merge', 'slow', 'compiler'], timeout: 180)
# Reuse the real CLI entry object for alternate-emitter mutation probes.
# No duplicate compiler/IR translation unit or production entry is added.
emitter_probe_main = static_library('emitter-probe-main',
    objects: aurorac.extract_all_objects(recursive: false), native: true, build_by_default: false)
test('ir-exhaustive', python,
     args: ['-B', files('compiler/ir_exhaustive.py'), aurora_ir_check,
            '--abi-header', frontend_assembly[3], '--abi-facts', frontend_assembly[2],
            '--compiler', aurorac, '--frontend-library', frontend_library,
            '--main-library', emitter_probe_main],
     depends: [aurora_ir_check, frontend_assembly, frontend_library, aurorac, emitter_probe_main], suite: ['full', 'release', 'compiler'],
     env: oracle_env, workdir: meson.current_build_dir(), timeout: 600)
test('stack-guards', python,
     args: ['-B', '-O', files('compiler/sector_values_abi.py'), aurora_ir_check, '--stack-guards'],
     depends: aurora_ir_check, suite: ['full', 'merge', 'slow', 'compiler'],
     env: oracle_env, workdir: meson.current_build_dir(), timeout: 180)
test('method-values-abi', python,
     args: ['-B', '-O', files('compiler/method_values_abi.py'), aurora_ir_check],
     depends: aurora_ir_check, suite: ['full', 'merge', 'slow', 'compiler'],
     env: oracle_env, workdir: meson.current_build_dir(), timeout: 180)
foreach family : ['readonly_windows', 'short_circuit']
    test(family.replace('_', '-'), python,
         args: ['-B', '-O', files('compiler/' + family + '.py'), aurorac],
         depends: aurorac, suite: ['full', 'merge', 'slow', 'compiler'],
         env: oracle_env, workdir: meson.current_build_dir(), timeout: 300)
    generated = family == 'short_circuit' ? [abi_air['short-circuit']] : []
    source_compiler = family == 'readonly_windows' ? ['--compiler', aurorac] : []
    test(family.replace('_', '-') + '-ir-native', python,
         args: ['-B', '-O', files('compiler/' + family + '_ir_native.py'), aurora_ir_check] + (generated.length() > 0 ? ['--air'] + generated : []) + source_compiler,
         depends: [aurora_ir_check, aurorac] + generated, suite: ['full', 'merge', 'slow', 'compiler'],
         env: oracle_env, workdir: meson.current_build_dir(), timeout: 300)
endforeach
# Library behaviour: one compiled driver per library, linked once with
# compiler/runtime_records_host.cpp and fed every case as a data record.
foreach family : ['token_scan', 'utf8', 'utf8_range', 'utf8_lines', 'utf8_text']
    test(family.replace('_', '-'), python,
         args: ['-B', files('compiler/' + family + '.py'), '--compiler', aurorac],
         depends: [aurorac] + record_host_targets, suite: ['full', 'merge', 'dev', 'compiler'],
         env: oracle_env, workdir: meson.current_build_dir(), timeout: 300)
endforeach
# std.json, std.json_read and std.json_write: one compiled driver or packed
# owned-bytes program per surface, every case streamed as a record or row.
foreach family : ['json_library', 'json_owned', 'json_string_read', 'json_string_write']
    test(family.replace('_', '-'), python,
         args: ['-B', files('compiler/' + family + '.py'), '--compiler', aurorac],
         depends: [aurorac] + record_host_targets, suite: ['full', 'merge', 'dev', 'bytes', 'compiler'],
         env: oracle_env, workdir: meson.current_build_dir(), timeout: 300,
         priority: slow_tests.get(family.replace('_', '-'), 0))
endforeach
# Every two-byte input and a native sweep of all code points through the same driver.
test('utf8-exhaustive', python,
     args: ['-B', files('compiler/utf8.py'), '--compiler', aurorac, '--profile', 'exhaustive'],
     depends: [aurorac] + record_host_targets, suite: ['exhaustive'], env: oracle_env,
     workdir: meson.current_build_dir(), timeout: 300)
# Package identity, manifest and graph: one driver each over golden cases.
foreach family : ['identity', 'manifest', 'graph']
    test('package-' + family, python,
         args: ['-B', files('compiler/package_' + family + '.py'), '--compiler', aurorac],
         depends: [aurorac] + record_host_targets, suite: ['full', 'merge', 'dev', 'packages', 'compiler'],
         env: oracle_env, workdir: meson.current_build_dir(), timeout: 300,
         priority: slow_tests.get('package-' + family, 0))
endforeach
# Storage and filesystem libraries: one compiled driver per family over data cases,
# compared with the golden file beside it (tests/compiler/storage).
foreach family : ['byte_storage', 'storage_binary', 'block_io', 'xfs_geometry', 'xfs_root', 'xfs_file']
    test(family.replace('_', '-'), python,
         args: ['-B', files('compiler/storage/' + family + '.py'), aurorac],
         depends: [aurorac] + record_host_targets, suite: ['full', 'merge', 'dev', 'bytes', 'compiler'],
         env: oracle_env, workdir: meson.current_build_dir(), timeout: 120)
endforeach
test('xfs-offline-native', python,
     args: ['-B', '-O', files('../fixtures/xfs-offline/verify_native.py'),
            '--compiler', aurorac],
     depends: aurorac, suite: ['full', 'merge', 'slow', 'compiler'],
     env: oracle_env, workdir: meson.current_build_dir(), timeout: 300)
foreach family : ['host_sources_tests', 'host_output_tests']
    host_fixture = executable(family.replace('_', '-'), 'modules/' + family + '.cpp',
        include_directories: include_directories('../compiler'),
        dependencies: dependency('threads'), native: true, override_options: fixture_options, install: false)
    test(family.replace('_', '-'), python,
         args: ['-B', files('modules/host_sources.py'), host_fixture],
         depends: host_fixture, suite: ['full', 'merge', 'slow', 'compiler'],
         env: oracle_env, workdir: meson.current_build_dir(), timeout: 180)
endforeach

subdir('native')


# This fixture always links the Aurora phase; the C++ scanner is only its oracle.
hosted_lexer_abi = custom_target(
    'hosted-lexer-abi-object', input: 'compiler/hosted_lexer_abi.S', output: 'hosted-lexer-abi.o',
    command: native_cpp.cmd_array() + ['-c', '-x', 'assembler', '@INPUT@', '-o', '@OUTPUT@'],
)
hosted_lexer_test = executable(
    'hosted-lexer-test', ['compiler/hosted_lexer.cpp', hosted_lexer_abi],
    dependencies: hosted_frontend, include_directories: include_directories('../compiler'),
    native: true, override_options: fixture_options, install: false,
)
test('hosted-lexer', hosted_lexer_test, args: files('compiler/golden/hosted_lexer.golden'),
     suite: ['full', 'merge', 'dev', 'core', 'compiler'], timeout: 180)
test('hosted-lexer-bootstrap', python,
     args: ['-B', files('compiler/hosted_lexer_bootstrap.py'), frontend_assembly[0], frontend_stage2_output[0],
            frontend_stage3_output[0]],
     depends: [frontend_stage2_output, frontend_stage3_output], suite: ['full', 'merge', 'dev', 'core', 'compiler'],
     env: oracle_env, timeout: 30)

format_fixture = executable('format-fixture', 'compiler/format.cpp', dependencies: hosted_frontend,
                            include_directories: include_directories('../compiler'), native: true, override_options: fixture_options, install: false)
test('hosted-lexer-format', format_fixture, suite: ['full', 'merge', 'dev', 'compiler'], timeout: 180)
test('hosted-lexer-format-cli', python, args: ['-B', '-O', files('compiler/format.py'), aurora_fmt],
     depends: aurora_fmt, suite: ['full', 'merge', 'dev', 'compiler'], env: oracle_env,
     workdir: meson.current_build_dir(), timeout: 180)

hosted_lexer_invalid = executable(
    'hosted-lexer-invalid', ['compiler/hosted_lexer_invalid.cpp', '../compiler/hosted_lexer.cpp', frontend_assembly[3]],
    cpp_args: ['-DAURORA_HOSTED_LEXER'], include_directories: include_directories('../compiler', '..'),
    native: true, override_options: fixture_options, install: false,
)
test('hosted-lexer-invalid', hosted_lexer_invalid, suite: ['full', 'merge', 'dev', 'core', 'compiler'], timeout: 30)

# Parser cases are data (compiler/hosted_parser.cases) checked against a reviewed
# golden dump; the driver also keeps the private ABI, growth and ownership
# controls. The separate forged-return fixture never links the generated code.
hosted_parser_abi = custom_target(
    'hosted-parser-abi-object', input: 'compiler/hosted_parser_abi.S', output: 'hosted-parser-abi.o',
    command: native_cpp.cmd_array() + ['-c', '-x', 'assembler', '@INPUT@', '-o', '@OUTPUT@'],
)
hosted_parser_test = executable(
    'hosted-parser-test', ['compiler/hosted_parser.cpp', hosted_parser_abi],
    dependencies: hosted_frontend, include_directories: include_directories('../compiler'),
    native: true, override_options: fixture_options, install: false,
)
test('hosted-parser', hosted_parser_test,
     args: files('compiler/hosted_parser.cases', 'compiler/golden/hosted_parser.golden'),
     suite: ['full', 'merge', 'dev', 'core', 'compiler'], timeout: 120,
     priority: slow_tests['hosted-parser'])
# The already-built adapter objects with forged Aurora entries; the generated
# frontend object itself is never linked.
hosted_parser_invalid = executable(
    'hosted-parser-invalid', 'compiler/hosted_parser_invalid.cpp',
    objects: frontend_library.extract_objects(frontend_adapter_sources),
    dependencies: frontend_headers, cpp_args: frontend_args, include_directories: include_directories('../compiler'),
    native: true, override_options: fixture_options, install: false,
)
test('hosted-parser-invalid', hosted_parser_invalid,
     suite: ['full', 'merge', 'dev', 'core', 'compiler'], timeout: 30)
