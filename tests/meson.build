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
# C++ hosts the oracle drivers link, built once here instead of by
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
# aurora-fmt over every tracked Aurora product source (compiler, library, kernel, examples).
test('aurora-style', python, args: ['-B', files('../scripts/style.py'), 'aurora', '--formatter', aurora_fmt.full_path()],
     depends: aurora_fmt, suite: ['full', 'merge', 'dev'], timeout: 120)
# Shared drivers: golden-output comparison and Aurora fixture objects built once.
golden_runner = files('golden.py')
fixture_builder = files('../scripts/meson-native-fixture.py')
# Test drivers and fixtures are not performance-critical; the code under test
# is Aurora, compiled by aurorac. -O1, not -O0: with GCC 16
# these template-heavy fixtures compile no faster at -O0 and emit ~24x larger
# objects (1.8 GiB in total), while -O1 cuts compile CPU by about a quarter.

# Every test in full is also in exactly one of merge (run on every merge) or
# release (opt-in: releases, compiler and seed changes). dev/slow/core/bytes are focused
# selections; explicit library enumeration is separate in exhaustive.
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
    runner_args = ['-B', '-O', files(entry[1]), aurorac.full_path()]
    test(
        entry[0],
        python,
        args: runner_args,
        depends: [aurorac] + record_host_targets,
        suite: ['full', 'merge', feedback, entry[2], 'compiler'],
        env: oracle_env,
        workdir: meson.current_build_dir(),
        timeout: 300,
        is_parallel: true,
    )
endforeach

test('volatile-file-source-native', python,
    args: ['-B', '-O', files('compiler/volatile_file.py'), aurorac.full_path()],
    depends: [aurorac] + record_host_targets, suite: ['full', 'merge', 'dev', 'core', 'bytes', 'compiler'],
    env: oracle_env, workdir: meson.current_build_dir(), timeout: 120, is_parallel: true)

# HostFiles: the example tools and the hostile-case drivers, each compiled and
# linked once with no C or C++ runtime; cases and rejections are golden data.
test('host-files', python,
     args: ['-B', files('host_files.py'), files('host-files/cases.golden'),
            'cat=' + hosted_programs['host-files-cat'].full_path(),
            'probe=' + hosted_programs['host-files-probe'].full_path(),
            'sort=' + hosted_programs['host-sort'].full_path()],
     depends: hosted_programs.values(), suite: ['full', 'merge', 'dev', 'core', 'compiler'], timeout: 120)
# The Aurora byte runtime (aurora.memory) under a hosted program's region:
# owners, views, quota and limits, failures and traps.
test('host-memory', python,
     args: ['-B', files('host_files.py'), files('host-files/memory.golden'),
            'memory=' + hosted_programs['host-memory-probe'].full_path()],
     depends: hosted_programs.values(), suite: ['full', 'merge', 'dev', 'core', 'compiler'], timeout: 120)
# The 64 MiB per-output limit costs real writes; limits run in the release suite.
test('host-files-limits', python,
     args: ['-B', files('host_files.py'), files('host-files/limits.golden'),
            'probe=' + hosted_programs['host-files-probe'].full_path()],
     depends: hosted_programs.values(), suite: ['full', 'release', 'compiler'], timeout: 120)
test('host-files-rejections', python,
     args: ['-B', golden_runner, files('host-files/rejections.golden'), '--reject', '--', aurorac.full_path(), '--check',
            '--module-root', 'tests/host-files/library'],
     depends: [aurorac], workdir: meson.project_source_root(), suite: ['full', 'merge', 'dev', 'core', 'compiler'],
     timeout: 120)
# --runtime-root replaces the configured runtime root (here one without aurora.*).
test('host-files-runtime-root', python,
     args: ['-B', golden_runner, files('host-files/runtime-root.golden'), '--reject', '--', aurorac.full_path(), '--check',
            '--runtime-root', 'tests/host-files/library'],
     depends: [aurorac], workdir: meson.project_source_root(), suite: ['full', 'merge', 'dev', 'core', 'compiler'],
     timeout: 120)
# A user module root that supplies its own aurora.host cannot replace the runtime.
test('host-files-impostor', python,
     args: ['-B', golden_runner, files('host-files/impostor.golden'), '--reject', '--', aurorac.full_path(), '--check',
            '--module-root', 'tests/host-files/impostor'],
     depends: [aurorac], workdir: meson.project_source_root(), suite: ['full', 'merge', 'dev', 'core', 'compiler'],
     timeout: 120)
# The compiler with no arguments: its usage, exit 2 (the process image runs the
# --target aurora build the same way, kernel/uefi/process.md#guest-rows).
test('host-files-usage', python,
     args: ['-B', golden_runner, files('host-files/usage.golden'), '--modes', '--', aurorac.full_path()],
     depends: [aurorac], suite: ['full', 'merge', 'dev', 'core', 'compiler'], timeout: 60)
# The rejected sources the process image's compile row also compiles in the
# guest (kernel/uefi/process.md#tests), with its flags: the guest's
# diagnostics and exit status must be these.
test('kernel-process-compile', python,
     args: ['-B', golden_runner, files('kernel-process/compile.golden'), '--reject', '--', aurorac.full_path(),
            '--emit-object', '--target', 'linux', '--runtime-root', 'runtime/linux'],
     depends: [aurorac], workdir: meson.project_source_root(), suite: ['full', 'merge', 'dev', 'core', 'compiler'],
     timeout: 120)
# --target selects the runtime root and the HostFiles primitives the typed IR admits.
test('host-files-target', python,
     args: ['-B', golden_runner, files('host-files/target.golden'), '--modes', '--', aurorac.full_path(), '--check'],
     depends: [aurorac], workdir: meson.project_source_root(), suite: ['full', 'merge', 'dev', 'core', 'compiler'],
     timeout: 120)

# One scratchpad host and one linked driver; modes and transcripts are runtime data.
scratchpad_host = static_library('scratchpad-host',
    ['compiler/scratchpad_host.cpp', 'compiler/service_group_abi.S'],
    native: true, override_options: fixture_options)
test('scratchpad-source-native', python,
    args: ['-B', '-O', files('compiler/scratchpad.py'), aurorac.full_path(), '--host', scratchpad_host.full_path()],
    depends: [aurorac, scratchpad_host] + record_host_targets,
    suite: ['full', 'merge', 'dev', 'core', 'bytes', 'compiler'],
    env: oracle_env, workdir: meson.current_build_dir(), timeout: 180, is_parallel: true)



# Textual IR cases (.air) run through one driver; each top-level directory of
# tests/compiler/ir is one test. See tests/compiler/ir/README.md.
# The bridged test graph: the compiler's own modules plus the Aurora .air
# reader (tools/air.au) and the initialization workspace probes, built by C1
# into its own object and header. The C++ test drivers and the optional
# language server link it; the compiler never does.
subdir('air')
air_adapter_sources = files('../compiler/hosted_resolver.cpp', '../compiler/hosted_pipeline.cpp',
                            '../runtime/hosted_bytes.cpp')
air_frontend_library = static_library('air-frontend', [air_frontend[0], air_frontend[3], air_adapter_sources],
    include_directories: include_directories('air', '.', '../compiler'), native: true,
    override_options: fixture_options, install: false)
air_frontend_headers = declare_dependency(sources: air_frontend[3],
                                          include_directories: include_directories('air', '.', '../compiler'))
air_frontend_dep = declare_dependency(link_with: air_frontend_library, dependencies: air_frontend_headers)
aurora_ir_check = executable('aurora-ir-check', 'tools/aurora_ir_check.cpp', dependencies: air_frontend_dep,
    native: true, override_options: fixture_options, install: false)
air_lit = files('tools/air_lit.py')
# The initialization workspace against standard-library reference sets, through
# the Aurora probes and metadata read from textual IR by the same reader.
initialization_facts = executable('initialization-facts',
    ['compiler/initialization_facts.cpp', 'compiler/initialization_workspace.cpp',
     'compiler/initialization_ownership.cpp'],
    dependencies: air_frontend_dep, native: true, override_options: fixture_options, install: false)
test('initialization-facts', initialization_facts, suite: ['full', 'merge', 'dev', 'core', 'compiler'], timeout: 120)
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
    ['host-files-service-ir', ['full', 'merge', 'dev', 'core', 'compiler']],
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

# One driver consumes existing IR data and one preassembled wrapper; malformed
# inputs and allocation failures reuse that admitted pair without recompilation.
private_object_wrapper = custom_target(
    'private-object-wrapper', input: 'compiler/private_object.S', output: 'private-object-wrapper.o',
    command: native_cpp.cmd_array() + ['-c', '-x', 'assembler', '-Wa,-mx86-used-note=no', '@INPUT@', '-o', '@OUTPUT@'],
)
private_object_test = executable('private-object-test', 'compiler/private_object.cpp',
    dependencies: air_frontend_dep, native: true, override_options: fixture_options, install: false)

test(
    'owned-mutation-abi',
    python,
    args: ['-B', '-O', files('compiler/owned_mutation_abi.py'), aurora_ir_check],
    depends: [aurora_ir_check] + record_host_targets,
    suite: ['full', 'merge', 'dev', 'core', 'compiler'],
    env: oracle_env,
    workdir: meson.current_build_dir(),
    timeout: 180,
)

test(
    'sector-values-abi',
    python,
    args: ['-B', '-O', files('compiler/sector_values_abi.py'), aurora_ir_check, '--air', abi_air['sector-values']],
    depends: [aurora_ir_check, abi_air['sector-values']] + record_host_targets,
    suite: ['full', 'merge', 'dev', 'bytes', 'compiler'],
    env: oracle_env,
    workdir: meson.current_build_dir(),
    timeout: 180,
)

# Standalone behavioral runners participate in the ordinary full graph.
test('semantic-lint', python,
     args: ['-B', files('compiler/lint.py'), aurora_fmt.full_path(), aurorac.full_path()],
     depends: [aurora_fmt, aurorac] + record_host_targets, suite: ['full', 'merge', 'dev', 'compiler'],
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
    depends: [aurora_ir_check, owning_classes_abi_driver] + record_host_targets, suite: ['full', 'merge', 'dev', 'core', 'compiler'],
    env: oracle_env, workdir: meson.current_build_dir(), timeout: 180,
)

# Logical owner views share the established readonly-span source type.
test('owned-spans-source', python,
     args: ['-B', '-O', files('compiler/owned_spans_source.py'), aurorac.full_path()],
     depends: [aurorac] + record_host_targets, suite: ['full', 'merge', 'dev', 'core', 'bytes', 'compiler'], env: oracle_env,
     workdir: meson.current_build_dir(), timeout: 180)
owned_spans_kernel_host = static_library('owned-spans-kernel-host',
    ['compiler/owned_spans_kernel_host.cpp', '../kernel/owned-bytes.cpp'],
    cpp_args: ['-DNDEBUG', '-fno-exceptions', '-fno-rtti'], pic: false,
    native: true, override_options: fixture_options, install: false)
foreach mode : ['standalone', 'receiver']
    span_kernel_args = ['-B', '-O', files('compiler/owned_spans_kernel.py'), aurorac.full_path(), '--host', owned_spans_kernel_host]
    if mode == 'receiver'
        span_kernel_args += ['--receiver-bound']
    endif
    test('owned-spans-kernel-' + mode, python,
         args: span_kernel_args, depends: [aurorac, owned_spans_kernel_host] + record_host_targets, suite: ['full', 'merge', 'dev', 'bytes', 'compiler'],
         env: oracle_env, workdir: meson.current_build_dir(), timeout: 180)
endforeach
test('logical-spans-abi', python,
     args: ['-B', '-O', files('compiler/logical_spans_abi.py'), aurora_ir_check, '--air', abi_air['logical-spans']],
     depends: [aurora_ir_check, abi_air['logical-spans']] + record_host_targets, suite: ['full', 'merge', 'dev', 'core', 'bytes', 'compiler'],
     env: oracle_env, workdir: meson.current_build_dir(), timeout: 180)

# Synchronous method capabilities retain independent IR and literal-layout ABI gates.
test('method-spans-abi', python,
     args: ['-B', '-O', files('compiler/method_spans_abi.py'), aurora_ir_check, '--air', abi_air['method-spans']],
     depends: [aurora_ir_check, abi_air['method-spans']] + record_host_targets, suite: ['full', 'merge', 'slow', 'core', 'bytes', 'compiler'],
     env: oracle_env, workdir: meson.current_build_dir(), timeout: 180)
# Keep routine borrowed-object feedback small; full owner/helper and literal ABI
# sweeps remain explicit slow coverage. Full/unfiltered runs retain every gate.
test('borrowed-objects-smoke', python,
     args: ['-B', '-O', files('compiler/borrowed_objects.py'), aurorac.full_path(), '--smoke'],
     depends: [aurorac] + record_host_targets, suite: ['full', 'merge', 'dev', 'bytes', 'compiler'], env: oracle_env,
     workdir: meson.current_build_dir(), timeout: 120, is_parallel: true)
test('borrowed-objects', python,
     args: ['-B', '-O', files('compiler/borrowed_objects.py'), aurorac.full_path()],
     depends: [aurorac] + record_host_targets, suite: ['full', 'release', 'bytes', 'compiler'], env: oracle_env,
     workdir: meson.current_build_dir(), timeout: 300, is_parallel: true)
test('borrowed-objects-abi', python,
     args: ['-B', '-O', files('compiler/borrowed_objects_abi.py'), aurora_ir_check, '--air', abi_air['borrowed-objects']],
     depends: [aurora_ir_check, abi_air['borrowed-objects']] + record_host_targets, suite: ['full', 'merge', 'slow', 'core', 'bytes', 'compiler'],
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
     args: ['-B', '-O', files('compiler/console_service.py'), aurorac.full_path()] + console_service_args,
     depends: [aurorac] + console_service_hosts.values() + record_host_targets,
     suite: ['full', 'merge', 'slow', 'core', 'compiler'], env: oracle_env,
     workdir: meson.current_build_dir(), timeout: 300)

# Second sealed kind reuses the service verifier and private bridge.
test('display-service-abi', python,
     args: ['-B', '-O', files('compiler/service_group_ir_abi.py'), aurora_ir_check.full_path()],
     depends: [aurora_ir_check] + record_host_targets, suite: ['full', 'merge', 'dev', 'core', 'compiler'], env: oracle_env, timeout: 120)
test('display-service-source-native', python,
     args: ['-B', '-O', files('compiler/display_service.py'), aurorac.full_path()],
     depends: [aurorac] + record_host_targets, suite: ['full', 'merge', 'slow', 'core', 'compiler'], env: oracle_env,
     workdir: meson.current_build_dir(), timeout: 300)

# Port remains a sealed singleton with fixed hosted mocks, never native I/O.
test('port-service-source-native', python,
     args: ['-B', '-O', files('compiler/port_service.py'), aurorac.full_path(), aurora_ir_check.full_path()],
     depends: [aurorac, aurora_ir_check] + record_host_targets, suite: ['full', 'merge', 'slow', 'core', 'compiler'], env: oracle_env,
     workdir: meson.current_build_dir(), timeout: 300)

# Serve keeps an exact copied two-register result and singleton grant.
test('serve-service-source-native', python,
     args: ['-B', '-O', files('compiler/serve_service.py'), aurorac.full_path(), aurora_ir_check.full_path()],
     depends: [aurorac, aurora_ir_check] + record_host_targets, suite: ['full', 'merge', 'slow', 'core', 'compiler'], env: oracle_env,
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
       suite: ['full', 'merge', 'slow', 'core', 'compiler'], depends: record_host_targets, env: oracle_env, timeout: 60)
endforeach
test('iommu-event-rejections', python,
     args: ['-B', golden_runner, files('compiler/iommu_event_service_rejections.golden'), '--reject', '--', aurorac.full_path(),
            '--check'],
     depends: [aurorac] + record_host_targets, suite: ['full', 'merge', 'slow', 'core', 'compiler'], env: oracle_env, timeout: 60)
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
     suite: ['full', 'merge', 'slow'], depends: record_host_targets, env: oracle_env, timeout: 60)
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
     suite: ['full', 'merge', 'slow'], depends: record_host_targets, env: oracle_env, timeout: 120)
# The production graphical terminal: the real cell grid and generated painter,
# compiled and linked once with its host; results compare with the golden file.
graphical_terminal_object = custom_target('graphical-terminal-painter',
    input: '../examples/kernel-graphical-terminal.au', output: 'graphical-terminal-painter.o',
    depfile: 'graphical-terminal-painter.d',
    command: [python, '-B', fixture_builder, '--compiler', aurorac, '--source', '@INPUT@',
              '--module-root', meson.project_source_root() / 'library', '--local-symbols',
              '--referenced-reflection-only', '--emit-object',
              '--bridge', files('../kernel/uefi/graphical-terminal-entry.S'),
              '--object', '@OUTPUT@', '--depfile', '@DEPFILE@'])
graphical_terminal_host = executable('graphical-terminal-host', 'kernel-graphical-terminal.cpp',
    graphical_terminal_object, cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page'], link_args: ['-no-pie'],
    native: true, override_options: fixture_options, install: false)
test('graphical-terminal-native', python,
     args: ['-B', golden_runner, files('kernel-graphical-terminal.golden'), '--modes', '--', graphical_terminal_host],
     suite: ['full', 'merge', 'dev'], depends: record_host_targets, env: oracle_env, timeout: 60)
# The process image's map admission, frame inventory and records, boot-volume
# admission and export encoding: the generated policies and their bridge linked
# once with the kernel's own storage; cases and verdicts are golden data.
process_policy_object = custom_target('process-policy',
    input: '../examples/kernel-process.au', output: 'process-policy.o', depfile: 'process-policy.d',
    command: [python, '-B', fixture_builder, '--compiler', aurorac, '--source', '@INPUT@',
              '--module-root', meson.project_source_root() / 'kernel/policies',
              '--module-root', meson.project_source_root() / 'library', '--local-symbols',
              '--referenced-reflection-only', '--bridge', files('../kernel/uefi/process-entry.S'),
              '--object', '@OUTPUT@', '--depfile', '@DEPFILE@'])
kernel_process = executable('kernel-process', 'kernel-process.cpp', process_policy_object,
    cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page'], link_args: ['-no-pie'],
    native: true, override_options: fixture_options, install: false)
process_volume_cases = custom_target('process-volume-cases', input: 'kernel-process/volumes.cases',
    output: 'process-volumes.bin',
    depend_files: files('../scripts/kernel_volume.py', '../examples/core_math.au', '../examples/host-sort.au'),
    command: [python, '-B', files('../scripts/kernel_volume.py'), '--cases', '@INPUT@',
              '--root', meson.project_source_root(), '--output', '@OUTPUT@'])
test('kernel-process-frames', python,
     args: ['-B', golden_runner, files('kernel-process/frames.golden'), '--', kernel_process, 'frames',
            files('kernel-process/frames.cases')],
     suite: ['full', 'merge', 'dev'], timeout: 60)
test('kernel-process-volumes', python,
     args: ['-B', golden_runner, files('kernel-process/volumes.golden'), '--', kernel_process, 'volumes',
            process_volume_cases],
     depends: process_volume_cases, suite: ['full', 'merge', 'dev'], timeout: 60)
# Programs (ELF admission, layout and regions), run lists and process events.
process_program_cases = custom_target('process-program-cases', input: 'kernel-process/programs.cases',
    output: 'process-programs.bin', depend_files: files('../scripts/kernel_volume.py'),
    command: [python, '-B', files('../scripts/kernel_volume.py'), '--cases', '@INPUT@',
              '--root', meson.project_source_root(), '--output', '@OUTPUT@'])
test('kernel-process-programs', python,
     args: ['-B', golden_runner, files('kernel-process/programs.golden'), '--', kernel_process, 'volumes',
            process_program_cases],
     depends: process_program_cases, suite: ['full', 'merge', 'dev'], timeout: 60)
test('kernel-process-events', python,
     args: ['-B', golden_runner, files('kernel-process/events.golden'), '--', kernel_process, 'events',
            files('kernel-process/events.cases')],
     suite: ['full', 'merge', 'dev'], timeout: 60)
test('kernel-process-memory', python,
     args: ['-B', golden_runner, files('kernel-process/memory.golden'), '--', kernel_process, 'events',
            files('kernel-process/memory.cases')],
     suite: ['full', 'merge', 'dev'], timeout: 60)
# The file service over a volume of the HostFiles cases' tree and a few more
# entries for path order and depth.
process_files_volume = custom_target('process-files-volume', output: 'process-files.volume',
    depend_files: files('../scripts/kernel_volume.py', 'host_files.py'),
    command: [python, '-B', files('../scripts/kernel_volume.py'), '--output', '@OUTPUT@', '--host-files-tree',
              '--text', 'deep/x/y/z.txt=deep', '--text', 'a-b/c.txt=dash', '--text', 'ab/c=plain',
              '--text', 'top.txt=top'])
test('kernel-process-files', python,
     args: ['-B', golden_runner, files('kernel-process/files.golden'), '--', kernel_process, 'files',
            process_files_volume, files('kernel-process/files.cases')],
     depends: process_files_volume, suite: ['full', 'merge', 'dev'], timeout: 60)
font_glyphs_object = custom_target('font-glyphs-module',
    input: 'kernel-programs/font-glyphs.au', output: 'font-glyphs.o', depfile: 'font-glyphs.d',
    command: [python, '-B', fixture_builder, '--compiler', aurorac, '--source', '@INPUT@',
              '--module-root', meson.project_source_root() / 'library',
              '--object', '@OUTPUT@', '--depfile', '@DEPFILE@'])
font_glyphs = executable('font-glyphs', 'font-glyphs.cpp', font_glyphs_object,
    native: true, override_options: fixture_options, install: false)
test('font5x7', python, args: ['-B', golden_runner, files('font5x7.golden'), '--', font_glyphs],
     suite: ['full', 'merge', 'dev'], depends: record_host_targets, env: oracle_env, timeout: 60)
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
  runner_args = ['-B', '-O', files('compiler/' + runner + '.py'), aurorac.full_path()]
  test(runner.replace('_', '-'), python,
       args: runner_args,
       depends: [aurorac] + record_host_targets, suite: ['full', 'merge', 'slow', 'compiler'], env: oracle_env,
       workdir: meson.current_build_dir(), timeout: 900, is_parallel: true)
endforeach


# Remaining compiler-native coverage. Fixtures are build targets, not commands
# hidden inside each test invocation; Ninja tracks C++ header dependencies.
test('diagnostics', python,
     args: ['-B', '-O', files('compiler/diagnostics.py'), aurorac.full_path(), aurora_fmt.full_path()],
     depends: [aurorac, aurora_fmt] + record_host_targets, suite: ['full', 'merge', 'slow', 'compiler'],
     env: oracle_env, workdir: meson.current_build_dir(), timeout: 180)
# The C++ source overlays, lint API and loader the optional language server uses.
if get_option('lsp')
    source_overlays_fixture = executable('source-overlays-fixture', 'compiler/source_overlays.cpp',
        dependencies: air_frontend_dep, native: true, override_options: fixture_options, install: false)
    test('source-overlays', python,
         args: ['-B', '-O', files('compiler/source_overlays.py'), source_overlays_fixture],
         depends: [source_overlays_fixture] + record_host_targets, suite: 'lsp',
         env: oracle_env, workdir: meson.current_build_dir(), timeout: 120)
    lint_fixture = executable('lint-fixture', 'compiler/lint.cpp',
        dependencies: air_frontend_dep, native: true, override_options: fixture_options, install: false)
    test('lint-overlays', lint_fixture, args: files('../examples/kernel.au'), suite: 'lsp', timeout: 60)
    # Its C++ loader's descriptor policy (compiler/host_sources.hpp).
    host_sources_fixture = executable('host-sources-tests', 'modules/host_sources_tests.cpp',
        include_directories: include_directories('../compiler'),
        dependencies: dependency('threads'), native: true, override_options: fixture_options, install: false)
    test('host-sources-tests', python, args: ['-B', files('modules/host_sources.py'), host_sources_fixture],
         depends: [host_sources_fixture] + record_host_targets, suite: 'lsp',
         env: oracle_env, workdir: meson.current_build_dir(), timeout: 180)
endif
# Mutated copies of the verifier and emitter, each built into a whole probe
# compiler from the staged sources and its configured driver.
test('ir-exhaustive', python,
     args: ['-B', files('compiler/ir_exhaustive.py'), aurora_ir_check, '--compiler', aurorac.full_path(),
            '--driver', compiler_driver, '--runtime-root', hosted_runtime_root],
     depends: [aurora_ir_check, aurorac] + record_host_targets, suite: ['full', 'release', 'compiler'],
     env: oracle_env, workdir: meson.current_build_dir(), timeout: 600)
test('stack-guards', python,
     args: ['-B', '-O', files('compiler/sector_values_abi.py'), aurora_ir_check, '--stack-guards'],
     depends: [aurora_ir_check] + record_host_targets, suite: ['full', 'merge', 'slow', 'compiler'],
     env: oracle_env, workdir: meson.current_build_dir(), timeout: 180)
test('method-values-abi', python,
     args: ['-B', '-O', files('compiler/method_values_abi.py'), aurora_ir_check],
     depends: [aurora_ir_check] + record_host_targets, suite: ['full', 'merge', 'slow', 'compiler'],
     env: oracle_env, workdir: meson.current_build_dir(), timeout: 180)
foreach family : ['readonly_windows', 'short_circuit']
    test(family.replace('_', '-'), python,
         args: ['-B', '-O', files('compiler/' + family + '.py'), aurorac.full_path()],
         depends: [aurorac] + record_host_targets, suite: ['full', 'merge', 'slow', 'compiler'],
         env: oracle_env, workdir: meson.current_build_dir(), timeout: 300)
    generated = family == 'short_circuit' ? [abi_air['short-circuit']] : []
    source_compiler = family == 'readonly_windows' ? ['--compiler', aurorac.full_path()] : []
    test(family.replace('_', '-') + '-ir-native', python,
         args: ['-B', '-O', files('compiler/' + family + '_ir_native.py'), aurora_ir_check] + (generated.length() > 0 ? ['--air'] + generated : []) + source_compiler,
         depends: [aurora_ir_check, aurorac] + generated + record_host_targets, suite: ['full', 'merge', 'slow', 'compiler'],
         env: oracle_env, workdir: meson.current_build_dir(), timeout: 300)
endforeach
# Library behaviour: one compiled driver per library, linked once with
# compiler/runtime_records_host.cpp and fed every case as a data record.
foreach family : ['token_scan', 'utf8', 'utf8_range', 'utf8_lines', 'utf8_text']
    test(family.replace('_', '-'), python,
         args: ['-B', files('compiler/' + family + '.py'), '--compiler', aurorac.full_path()],
         depends: [aurorac] + record_host_targets, suite: ['full', 'merge', 'dev', 'compiler'],
         env: oracle_env, workdir: meson.current_build_dir(), timeout: 300)
endforeach
# std.json, std.json_read and std.json_write: one compiled driver or packed
# owned-bytes program per surface, every case streamed as a record or row.
foreach family : ['json_library', 'json_owned', 'json_string_read', 'json_string_write']
    test(family.replace('_', '-'), python,
         args: ['-B', files('compiler/' + family + '.py'), '--compiler', aurorac.full_path()],
         depends: [aurorac] + record_host_targets, suite: ['full', 'merge', 'dev', 'bytes', 'compiler'],
         env: oracle_env, workdir: meson.current_build_dir(), timeout: 300)
endforeach
# Every two-byte input and a native sweep of all code points through the same driver.
test('utf8-exhaustive', python,
     args: ['-B', files('compiler/utf8.py'), '--compiler', aurorac.full_path(), '--profile', 'exhaustive'],
     depends: [aurorac] + record_host_targets, suite: ['exhaustive'], env: oracle_env,
     workdir: meson.current_build_dir(), timeout: 300)
# Package identity, manifest and graph: one driver each over golden cases.
foreach family : ['identity', 'manifest', 'graph']
    test('package-' + family, python,
         args: ['-B', files('compiler/package_' + family + '.py'), '--compiler', aurorac.full_path()],
         depends: [aurorac] + record_host_targets, suite: ['full', 'merge', 'dev', 'packages', 'compiler'],
         env: oracle_env, workdir: meson.current_build_dir(), timeout: 300)
endforeach
# Storage and filesystem libraries: one compiled driver per family over data cases,
# compared with the golden file beside it (tests/compiler/storage).
foreach family : ['byte_storage', 'storage_binary', 'block_io', 'xfs_geometry', 'xfs_root', 'xfs_file']
    test(family.replace('_', '-'), python,
         args: ['-B', files('compiler/storage/' + family + '.py'), aurorac.full_path()],
         depends: [aurorac] + record_host_targets, suite: ['full', 'merge', 'dev', 'bytes', 'compiler'],
         env: oracle_env, workdir: meson.current_build_dir(), timeout: 120)
endforeach
test('xfs-offline-native', python,
     args: ['-B', '-O', files('../fixtures/xfs-offline/verify_native.py'),
            '--compiler', aurorac.full_path()],
     depends: [aurorac] + record_host_targets, suite: ['full', 'merge', 'slow', 'compiler'],
     env: oracle_env, workdir: meson.current_build_dir(), timeout: 300)

subdir('native')

test('private-object', python,
     args: ['-B', files('compiler/private_object.py'), private_object_test, aurorac.full_path(), private_object_wrapper,
            aurora_ir_check, '--frontend', air_frontend[1], air_frontend[0], air_frontend[2],
            '--uart', native_uart_object, '--terminal', graphical_terminal_object],
     depends: [private_object_test, private_object_wrapper, aurorac, aurora_ir_check, air_frontend,
               native_uart_object, graphical_terminal_object],
     suite: ['full', 'merge', 'dev', 'core', 'compiler'], env: oracle_env, timeout: 120)


# Lexer cases through the raw Aurora lexer entry, checked against a reviewed golden file.
hosted_lexer_abi = custom_target(
    'hosted-lexer-abi-object', input: 'compiler/hosted_lexer_abi.S', output: 'hosted-lexer-abi.o',
    command: native_cpp.cmd_array() + ['-c', '-x', 'assembler', '@INPUT@', '-o', '@OUTPUT@'],
)
hosted_lexer_test = executable(
    'hosted-lexer-test', ['compiler/hosted_lexer.cpp', hosted_lexer_abi],
    dependencies: air_frontend_dep,
    native: true, override_options: fixture_options, install: false,
)
test('hosted-lexer', hosted_lexer_test, args: files('compiler/golden/hosted_lexer.golden'),
     suite: ['full', 'merge', 'dev', 'core', 'compiler'], timeout: 180)
# Stage compare (GCC's compare-stage). From a cached C0: the compiler object C1
# emitted and the one C2 emitted are identical.
if not from_seed
  test('hosted-lexer-bootstrap', find_program('cmp', native: true),
       args: [aurorac_stage2_object, aurorac_stage3_object],
       depends: [aurorac_stage2_object, aurorac_stage3_object], suite: ['full', 'merge', 'dev', 'core', 'compiler'],
       timeout: 30)
endif
# The seed's check: the compiler object aurora-seed emits by interpreting the
# compiler (X) is the one the compiled compiler emits. In a seed build C1 is X
# linked, so this is the build's stage compare; from a cached C0 it joins the
# compare above in the release suite, which builds X.
seed_suites = from_seed ? ['full', 'merge', 'dev', 'core', 'compiler', 'release'] : ['full', 'release']
test('seed-bootstrap', find_program('cmp', native: true), args: [aurorac_seed_object, aurorac_stage2_object],
     depends: [aurorac_seed_object, aurorac_stage2_object], suite: seed_suites, timeout: 30)
# The seed's own cases, with reviewed results: traps, fail-closed rejections of
# constructs outside its subset and of invalid ownership.
test('seed-cases', python, args: ['-B', golden_runner, files('seed/cases.golden'), '--modes', '--', aurora_seed],
     depends: [aurora_seed], workdir: meson.project_source_root(), suite: ['full', 'merge', 'dev', 'core', 'compiler'],
     timeout: 60)
# The semantics case's reviewed output is what the compiled program prints too.
foreach name, command : {'seed-semantics': [aurora_seed, '--runtime-root', hosted_runtime_root,
                                            files('seed/semantics.au')],
                         'seed-semantics-compiled': [hosted_programs['seed-semantics'].full_path()]}
  test(name, python, args: ['-B', golden_runner, files('seed/semantics.golden'), '--'] + command,
       depends: [aurora_seed, hosted_programs['seed-semantics']], suite: ['full', 'merge', 'dev', 'core', 'compiler'],
       timeout: 60)
endforeach

format_fixture = executable('format-fixture', 'compiler/format.cpp', dependencies: air_frontend_dep,
                            native: true, override_options: fixture_options, install: false)
test('hosted-lexer-format', format_fixture, suite: ['full', 'merge', 'dev', 'compiler'], timeout: 180)
test('hosted-lexer-format-cli', python, args: ['-B', '-O', files('compiler/format.py'), aurora_fmt.full_path()],
     depends: [aurora_fmt] + record_host_targets, suite: ['full', 'merge', 'dev', 'compiler'], env: oracle_env,
     workdir: meson.current_build_dir(), timeout: 180)

# Parser cases are data (compiler/hosted_parser.cases) checked against a reviewed
# golden dump; the driver also keeps the private ABI, growth and ownership
# controls. The separate forged-return fixture never links the generated code.
hosted_parser_abi = custom_target(
    'hosted-parser-abi-object', input: 'compiler/hosted_parser_abi.S', output: 'hosted-parser-abi.o',
    command: native_cpp.cmd_array() + ['-c', '-x', 'assembler', '@INPUT@', '-o', '@OUTPUT@'],
)
hosted_parser_test = executable(
    'hosted-parser-test', ['compiler/hosted_parser.cpp', hosted_parser_abi],
    dependencies: air_frontend_dep,
    native: true, override_options: fixture_options, install: false,
)
test('hosted-parser', hosted_parser_test,
     args: files('compiler/hosted_parser.cases', 'compiler/golden/hosted_parser.golden'),
     suite: ['full', 'merge', 'dev', 'core', 'compiler'], timeout: 120)
# One compiled raw lowering projection driver; cases include every instruction
# form and malformed source-owned transport without rebuilding per case.
hosted_lowering_test = executable(
    'hosted-lowering-test', 'compiler/hosted_lowering.cpp',
    dependencies: air_frontend_dep,
    native: true, override_options: fixture_options, install: false,
)
test('hosted-lowering', hosted_lowering_test, args: files('compiler/hosted_lowering.cases'),
     suite: ['full', 'merge', 'dev', 'core', 'compiler'], timeout: 120)
# The already-built adapter objects with forged Aurora entries; the generated
# frontend object itself is never linked.
hosted_parser_invalid = executable(
    'hosted-parser-invalid', 'compiler/hosted_parser_invalid.cpp',
    objects: air_frontend_library.extract_objects(air_adapter_sources),
    dependencies: air_frontend_headers, native: true, override_options: fixture_options, install: false,
)
test('hosted-parser-invalid', hosted_parser_invalid,
     suite: ['full', 'merge', 'dev', 'core', 'compiler'], timeout: 30)
