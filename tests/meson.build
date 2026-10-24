# Compiler runner scratch lives beneath this build directory, including module
# alias, FIFO and oversized-source cases. Native routing below handles its own paths.
# Source/library inputs are read-only; parallel tests share no generated paths.
oracle_env = environment()
oracle_env.set('TMPDIR', meson.current_build_dir())
oracle_env.set('TMP', meson.current_build_dir())
oracle_env.set('TEMP', meson.current_build_dir())
oracle_env.set('PYTHONDONTWRITEBYTECODE', '1')
oracle_env.set('CXX', oracle_cxx)
artifact_adapter = files('meson_artifacts.py')
# Shared drivers: golden-output comparison and Aurora fixture objects built once.
golden_runner = files('golden.py')
fixture_builder = files('../scripts/meson-native-fixture.py')
# Test drivers and fixtures are not performance-critical; the code under test in
# hosted_frontend keeps the project optimization level. -O1, not -O0: with GCC 16
# these template-heavy fixtures compile no faster at -O0 and emit ~24x larger
# objects (1.8 GiB in total), while -O1 cuts compile CPU by about a quarter.
fixture_options = ['optimization=1']

# Every test in full is also in exactly one of merge (run on every merge) or
# release (opt-in: releases and compiler bumps). dev/slow/core/bytes are focused
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
    )
endforeach

test('volatile-file-source-native', python,
    args: ['-B', artifact_adapter, python, '-B', '-O', files('compiler/volatile_file.py'), aurorac,
           '--artifacts', '@ARTIFACTS@'],
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
    args: ['-B', artifact_adapter, python, '-B', '-O', files('compiler/scratchpad.py'), aurorac,
           '--artifacts', '@ARTIFACTS@'] + scratchpad_args,
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


# Frozen independent oracle rows are expectations, not a final-source receipt.
verifier_contract = executable('verifier-contract', 'compiler/verifier_contract.cpp',
    dependencies: hosted_frontend, include_directories: include_directories('../compiler'),
    native: true, override_options: fixture_options, install: false)
test('verifier-contract', python,
    args: ['-B', artifact_adapter, python, '-B', files('compiler/verifier_contract.py'),
           verifier_contract, files('compiler/verifier_contract.expected.jsonl'), '--artifacts', '@ARTIFACTS@'],
    depends: verifier_contract, suite: ['full', 'merge', 'dev', 'core', 'compiler'],
    env: oracle_env, workdir: meson.current_build_dir(), timeout: 120)

class_arrays_ir = executable(
    'class-arrays-ir',
    'compiler/class_arrays_ir.cpp',
    dependencies: hosted_frontend,
    include_directories: include_directories('../compiler'),
    native: true, override_options: fixture_options,
    install: false,
)
test('class-arrays-ir', class_arrays_ir, suite: ['full', 'merge', 'dev', 'core', 'compiler'], timeout: 120)

owned_mutation_ir = executable(
    'owned-mutation-ir',
    'compiler/owned_mutation_ir.cpp',
    dependencies: hosted_frontend,
    include_directories: include_directories('../compiler'),
    native: true, override_options: fixture_options,
    install: false,
)
test('owned-mutation-ir', owned_mutation_ir, suite: ['full', 'merge', 'dev', 'core', 'compiler'], timeout: 120)
test(
    'owned-mutation-abi',
    python,
    args: ['-B', '-O', files('compiler/owned_mutation_abi.py'), owned_mutation_ir],
    depends: owned_mutation_ir,
    suite: ['full', 'merge', 'dev', 'core', 'compiler'],
    env: oracle_env,
    workdir: meson.current_build_dir(),
    timeout: 180,
)

sector_values_ir = executable(
    'sector-values-ir',
    'compiler/sector_values_ir.cpp',
    dependencies: hosted_frontend,
    include_directories: include_directories('../compiler'),
    native: true, override_options: fixture_options,
    install: false,
)
test('sector-values-ir', sector_values_ir, suite: ['full', 'merge', 'dev', 'bytes', 'compiler'], timeout: 120)
test(
    'sector-values-abi',
    python,
    args: ['-B', '-O', files('compiler/sector_values_abi.py'), sector_values_ir],
    depends: sector_values_ir,
    suite: ['full', 'merge', 'dev', 'bytes', 'compiler'],
    env: oracle_env,
    workdir: meson.current_build_dir(),
    timeout: 180,
)

# Standalone behavioral runners participate in the ordinary full graph.
lint_fixture = executable(
    'lint-fixture', 'compiler/lint.cpp',
    include_directories: include_directories('../compiler'), dependencies: hosted_frontend,
    native: true, override_options: fixture_options, install: false,
)
test('semantic-lint', python,
     args: ['-B', artifact_adapter, python, '-B', files('compiler/lint.py'),
            aurora_fmt, aurorac, lint_fixture, '--artifacts', '@ARTIFACTS@'],
     depends: [aurora_fmt, aurorac, lint_fixture], suite: ['full', 'merge', 'dev', 'compiler'],
     env: oracle_env, workdir: meson.current_build_dir(), timeout: 180)


# Runtime-owned bytes are a hosted bootstrap boundary, separate from freestanding core.
owned_bytes_ir = executable(
    'owned-bytes-ir', 'compiler/owned_bytes_ir.cpp',
    dependencies: hosted_frontend,
    include_directories: include_directories('../compiler'), native: true, override_options: fixture_options, install: false,
)
test('owned-bytes-ir', owned_bytes_ir, suite: ['full', 'merge', 'dev', 'core', 'compiler'], timeout: 120)
owned_bytes_host = executable(
    'owned-bytes-host', ['compiler/owned_bytes_host.cpp', '../runtime/hosted_bytes.cpp'],
    cpp_args: ['-DAURORA_HOSTED_BYTES_TESTING'], native: true, override_options: fixture_options, install: false,
)
test('owned-bytes-host', owned_bytes_host, suite: ['full', 'merge', 'dev', 'core', 'compiler'], timeout: 120)

# Direct owning classes reuse the hosted byte adapter and private value ABI.
owning_classes_ir = executable(
    'owning-classes-ir', 'compiler/owning_classes_ir.cpp',
    dependencies: hosted_frontend,
    include_directories: include_directories('../compiler'), native: true, override_options: fixture_options, install: false,
)
test('owning-classes-ir', owning_classes_ir, suite: ['full', 'merge', 'dev', 'core', 'compiler'], timeout: 120)
owning_classes_abi_driver = static_library(
    'owning-classes-abi-driver', ['compiler/owning_classes_abi_driver.cpp', '../runtime/hosted_bytes.cpp'],
    include_directories: include_directories('..'), native: true, override_options: fixture_options, install: false,
)
test(
    'owning-classes-abi', python,
    args: ['-B', '-O', files('compiler/owning_classes_abi.py'), owning_classes_ir, owning_classes_abi_driver.full_path()],
    depends: [owning_classes_ir, owning_classes_abi_driver], suite: ['full', 'merge', 'dev', 'core', 'compiler'],
    env: oracle_env, workdir: meson.current_build_dir(), timeout: 180,
)

# Logical owner views share the established readonly-span source type.
owned_spans_ir = executable(
    'owned-spans-ir', 'compiler/owned_spans_ir.cpp',
    dependencies: hosted_frontend,
    include_directories: include_directories('../compiler'), native: true, override_options: fixture_options, install: false,
)
test('owned-spans-ir', owned_spans_ir, suite: ['full', 'merge', 'dev', 'core', 'bytes', 'compiler'], timeout: 120)
test('owned-spans-source', python,
     args: ['-B', artifact_adapter, python, '-B', '-O', files('compiler/owned_spans_source.py'), aurorac,
            '--artifacts', '@ARTIFACTS@'],
     depends: aurorac, suite: ['full', 'merge', 'dev', 'core', 'bytes', 'compiler'], env: oracle_env,
     workdir: meson.current_build_dir(), timeout: 180)
foreach mode : ['standalone', 'receiver']
    span_kernel_args = ['-B', artifact_adapter, python, '-B', '-O', files('compiler/owned_spans_kernel.py'), aurorac,
                        '--artifacts', '@ARTIFACTS@']
    if mode == 'receiver'
        span_kernel_args += ['--receiver-bound']
    endif
    test('owned-spans-kernel-' + mode, python,
         args: span_kernel_args, depends: aurorac, suite: ['full', 'merge', 'dev', 'bytes', 'compiler'],
         env: oracle_env, workdir: meson.current_build_dir(), timeout: 180)
endforeach
logical_spans_abi = executable(
    'logical-spans-abi', 'compiler/logical_spans_abi.cpp',
    dependencies: hosted_frontend,
    include_directories: include_directories('../compiler'), native: true, override_options: fixture_options, install: false,
)
test('logical-spans-abi', python,
     args: ['-B', artifact_adapter, python, '-B', '-O', files('compiler/logical_spans_abi.py'),
            logical_spans_abi, '--artifacts', '@ARTIFACTS@'],
     depends: logical_spans_abi, suite: ['full', 'merge', 'dev', 'core', 'bytes', 'compiler'],
     env: oracle_env, workdir: meson.current_build_dir(), timeout: 180)

# Synchronous method capabilities retain independent IR and literal-layout ABI gates.
method_spans_ir = executable(
    'method-spans-ir', 'compiler/method_spans_ir.cpp',
    dependencies: hosted_frontend,
    include_directories: include_directories('../compiler'), native: true, override_options: fixture_options, install: false,
)
test('method-spans-ir', method_spans_ir, suite: ['full', 'merge', 'dev', 'core', 'bytes', 'compiler'], timeout: 120)
method_spans_abi = executable(
    'method-spans-abi', 'compiler/method_spans_abi.cpp',
    dependencies: hosted_frontend,
    include_directories: include_directories('../compiler'), native: true, override_options: fixture_options, install: false,
)
test('method-spans-abi', python,
     args: ['-B', artifact_adapter, python, '-B', '-O', files('compiler/method_spans_abi.py'),
            method_spans_abi, '--artifacts', '@ARTIFACTS@'],
     depends: method_spans_abi, suite: ['full', 'merge', 'slow', 'core', 'bytes', 'compiler'],
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
borrowed_objects_ir = executable(
    'borrowed-objects-ir', 'compiler/borrowed_objects_ir.cpp',
    dependencies: hosted_frontend,
    include_directories: include_directories('../compiler'), native: true, override_options: fixture_options, install: false,
)
test('borrowed-objects-ir', borrowed_objects_ir, suite: ['full', 'merge', 'dev', 'core', 'bytes', 'compiler'], timeout: 120)
borrowed_objects_abi = executable(
    'borrowed-objects-abi', 'compiler/borrowed_objects_abi.cpp',
    dependencies: hosted_frontend,
    include_directories: include_directories('../compiler'), native: true, override_options: fixture_options, install: false,
)
test('borrowed-objects-abi', python,
     args: ['-B', artifact_adapter, python, '-B', '-O', files('compiler/borrowed_objects_abi.py'),
            borrowed_objects_abi, '--artifacts', '@ARTIFACTS@'],
     depends: borrowed_objects_abi, suite: ['full', 'merge', 'slow', 'core', 'bytes', 'compiler'],
     env: oracle_env, workdir: meson.current_build_dir(), timeout: 180)

# Sealed service authority has its own independent verifier and host-grant model.
# Shared hand-built service IR fixtures, compiled once for all service IR tests.
service_ir_common = static_library(
    'service-ir-common', 'compiler/service_ir_common.cpp',
    dependencies: hosted_frontend,
    include_directories: include_directories('../compiler'), native: true, override_options: fixture_options, install: false,
)
console_service_ir = executable(
    'console-service-ir', 'compiler/console_service_ir.cpp', link_with: service_ir_common,
    dependencies: hosted_frontend,
    include_directories: include_directories('../compiler'), native: true, override_options: fixture_options, install: false,
)
test('console-service-ir', console_service_ir, suite: ['full', 'merge', 'dev', 'core', 'compiler'], timeout: 120)
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
     args: ['-B', artifact_adapter, python, '-B', '-O', files('compiler/console_service.py'), aurorac,
            '--comparison-compiler', aurorac_stage2] + console_service_args + ['--artifacts', '@ARTIFACTS@'],
     depends: [aurorac, aurorac_stage2] + console_service_hosts.values(),
     suite: ['full', 'merge', 'slow', 'core', 'compiler'], env: oracle_env,
     workdir: meson.current_build_dir(), timeout: 300)

# Second sealed kind reuses the service verifier and private bridge.
display_service_ir = executable(
    'display-service-ir', ['compiler/service_group_ir.cpp', 'compiler/display_service_ir.cpp'], link_with: service_ir_common,
    dependencies: hosted_frontend,
    include_directories: include_directories('../compiler'), native: true, override_options: fixture_options, install: false,
)
test('display-service-ir', python,
     args: ['-B', artifact_adapter, python, '-B', '-O', files('compiler/service_group_ir_abi.py'),
            display_service_ir.full_path(), '--artifacts', '@ARTIFACTS@'],
     depends: display_service_ir, suite: ['full', 'merge', 'dev', 'core', 'compiler'], env: oracle_env, timeout: 120)
test('display-service-source-native', python,
     args: ['-B', artifact_adapter, python, '-B', '-O', files('compiler/display_service.py'), aurorac,
            '--artifacts', '@ARTIFACTS@'],
     depends: aurorac, suite: ['full', 'merge', 'slow', 'core', 'compiler'], env: oracle_env,
     workdir: meson.current_build_dir(), timeout: 300)

# Port remains a sealed singleton with fixed hosted mocks, never native I/O.
port_service_ir = executable(
    'port-service-ir', 'compiler/port_service_ir.cpp', link_with: service_ir_common,
    dependencies: hosted_frontend,
    include_directories: include_directories('../compiler'), native: true, override_options: fixture_options, install: false,
)
test('port-service-ir', port_service_ir, suite: ['full', 'merge', 'dev', 'core', 'compiler'], timeout: 120)
test('port-service-source-native', python,
     args: ['-B', artifact_adapter, python, '-B', '-O', files('compiler/port_service.py'), aurorac,
            port_service_ir.full_path(), '--artifacts', '@ARTIFACTS@'],
     depends: [aurorac, port_service_ir], suite: ['full', 'merge', 'slow', 'core', 'compiler'], env: oracle_env,
     workdir: meson.current_build_dir(), timeout: 300)

# Serve keeps an exact copied two-register result and singleton grant.
serve_service_ir = executable(
    'serve-service-ir', 'compiler/serve_service_ir.cpp', link_with: service_ir_common,
    dependencies: hosted_frontend,
    include_directories: include_directories('../compiler'), native: true, override_options: fixture_options, install: false,
)
test('serve-service-ir', serve_service_ir, suite: ['full', 'merge', 'dev', 'core', 'compiler'], timeout: 120)
test('serve-service-source-native', python,
     args: ['-B', artifact_adapter, python, '-B', '-O', files('compiler/serve_service.py'), aurorac,
            serve_service_ir.full_path(), '--artifacts', '@ARTIFACTS@'],
     depends: [aurorac, serve_service_ir], suite: ['full', 'merge', 'slow', 'core', 'compiler'], env: oracle_env,
     workdir: meson.current_build_dir(), timeout: 300)

# Event intake retains the existing service loan graph and executes the real
# Aurora consumer against bounded hosted observations; no guest is run here.
iommu_event_ir = executable(
    'iommu-event-service-ir', 'compiler/iommu_event_service_ir.cpp', link_with: service_ir_common,
    dependencies: hosted_frontend,
    include_directories: include_directories('../compiler'), native: true, override_options: fixture_options, install: false,
)
test('iommu-event-service-ir', iommu_event_ir, suite: ['full', 'merge', 'slow', 'core', 'compiler'], timeout: 60)
iommu_event_ir_assembly = custom_target('iommu-event-ir-assembly', output: 'iommu-event-ir.s',
    command: [iommu_event_ir, '@OUTPUT@'], capture: false)
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
foreach model : ['framebuffer', 'framebuffer-tables', 'framebuffer-loader', 'framebuffer-pixels']
    framebuffer_model = executable(
        'uefi-' + model, 'kernel-uefi-' + model + '.cpp',
        native: true, override_options: fixture_options, install: false, cpp_args: ['-DAURORA_RUNTIME_IMAGE_POLICY=one_page'], link_args: ['-no-pie'],
    )
    test('uefi-' + model, framebuffer_model, suite: ['full', 'merge', 'dev'], timeout: 120)
endforeach
display_session = executable('display-session', 'kernel-display-session.cpp', native: true, override_options: fixture_options, install: false)
test('display-session', display_session, suite: ['full', 'merge', 'dev'], timeout: 120)
test('kernel_framebuffer_probe_oracle.py', python, args: ['-B', files('kernel_framebuffer_probe_oracle.py')],
     suite: ['full', 'merge', 'dev'], env: oracle_env, timeout: 120)
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


# Compiler-free model-fixture integrity/mocks. No emulator or hardware acceptance.
test('iommu-diagnostics-optimized', python, args: ['-B', '-O', files('iommu-diagnostics.py')],
     suite: ['full', 'merge', 'dev'], env: oracle_env, timeout: 30)

# Remaining compiler-native coverage. Fixtures are build targets, not commands
# hidden inside each test invocation; Ninja tracks C++ header dependencies.
compiler_fixtures = {}
foreach fixture : [
    'diagnostics', 'lexer_trivia', 'source_overlays', 'ir_tests', 'stack_probes',
    'method_values_ir', 'readonly_windows_ir', 'short_circuit_ir',
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
# The exact legacy glob roots; this adapter enumerates them anew on every run.
test('lexer-trivia', python,
     args: ['-B', files('meson_lexer_inputs.py'), compiler_fixtures['lexer_trivia'], meson.project_source_root()],
     depends: compiler_fixtures['lexer_trivia'], suite: ['full', 'merge', 'slow', 'compiler'],
     env: oracle_env, timeout: 180)
foreach fixture : ['ir_tests', 'stack_probes', 'method_values_ir', 'readonly_windows_ir', 'short_circuit_ir']
    test(fixture.replace('_', '-'), compiler_fixtures[fixture],
         suite: ['full', 'merge', 'slow', 'compiler'], env: oracle_env, timeout: 180)
endforeach
# Reuse the real CLI entry object for alternate-emitter mutation probes.
# No duplicate compiler/IR translation unit or production entry is added.
emitter_probe_main = static_library('emitter-probe-main',
    objects: aurorac.extract_all_objects(recursive: false), native: true, build_by_default: false)
test('ir-exhaustive', python,
     args: ['-B', artifact_adapter, python, '-B', files('compiler/ir_exhaustive.py'), compiler_fixtures['ir_tests'],
            '--abi-header', frontend_assembly[3], '--abi-facts', frontend_assembly[2],
            '--compiler', aurorac, '--frontend-library', frontend_library,
            '--main-library', emitter_probe_main, '--artifacts', '@ARTIFACTS@'],
     depends: [compiler_fixtures['ir_tests'], frontend_assembly, frontend_library, aurorac, emitter_probe_main], suite: ['full', 'release', 'compiler'],
     env: oracle_env, workdir: meson.current_build_dir(), timeout: 600, is_parallel: false)
test('stack-guards', python,
     args: ['-B', '-O', files('compiler/sector_values_abi.py'), compiler_fixtures['stack_probes'], '--stack-guards'],
     depends: compiler_fixtures['stack_probes'], suite: ['full', 'merge', 'slow', 'compiler'],
     env: oracle_env, workdir: meson.current_build_dir(), timeout: 180)
test('method-values-abi', python,
     args: ['-B', artifact_adapter, python, '-B', '-O', files('compiler/method_values_abi.py'),
            compiler_fixtures['method_values_ir'], '--work-dir', '@ARTIFACTS@'],
     depends: compiler_fixtures['method_values_ir'], suite: ['full', 'merge', 'slow', 'compiler'],
     env: oracle_env, workdir: meson.current_build_dir(), timeout: 180)
foreach family : ['readonly_windows', 'short_circuit']
    test(family.replace('_', '-'), python,
         args: ['-B', artifact_adapter, python, '-B', '-O', files('compiler/' + family + '.py'),
                aurorac, '--artifacts', '@ARTIFACTS@'],
         depends: aurorac, suite: ['full', 'merge', 'slow', 'compiler'],
         env: oracle_env, workdir: meson.current_build_dir(), timeout: 300)
    test(family.replace('_', '-') + '-ir-native', python,
         args: ['-B', artifact_adapter, python, '-B', '-O', files('compiler/' + family + '_ir_native.py'),
                compiler_fixtures[family + '_ir'], '--artifacts', '@ARTIFACTS@'],
         depends: compiler_fixtures[family + '_ir'], suite: ['full', 'merge', 'slow', 'compiler'],
         env: oracle_env, workdir: meson.current_build_dir(), timeout: 300)
endforeach
# Library behaviour: one compiled driver per library, linked once with
# compiler/runtime_records_host.cpp and fed every case as a data record.
foreach family : ['token_scan', 'utf8', 'utf8_range', 'utf8_lines', 'utf8_text']
    test(family.replace('_', '-'), python,
         args: ['-B', files('compiler/' + family + '.py'), '--compiler', aurorac],
         depends: aurorac, suite: ['full', 'merge', 'dev', 'compiler'],
         env: oracle_env, workdir: meson.current_build_dir(), timeout: 300)
endforeach
# std.json, std.json_read and std.json_write: one compiled driver or packed
# owned-bytes program per surface, every case streamed as a record or row.
foreach family : ['json_library', 'json_owned', 'json_string_read', 'json_string_write']
    test(family.replace('_', '-'), python,
         args: ['-B', files('compiler/' + family + '.py'), '--compiler', aurorac],
         depends: aurorac, suite: ['full', 'merge', 'dev', 'bytes', 'compiler'],
         env: oracle_env, workdir: meson.current_build_dir(), timeout: 300)
endforeach
# Every two-byte input and a native sweep of all code points through the same driver.
test('utf8-exhaustive', python,
     args: ['-B', files('compiler/utf8.py'), '--compiler', aurorac, '--profile', 'exhaustive'],
     depends: aurorac, suite: ['exhaustive'], env: oracle_env,
     workdir: meson.current_build_dir(), timeout: 300)
# Package identity, manifest and graph, each with its complete case corpus.
foreach family : ['identity', 'manifest', 'graph']
    test('package-' + family, python,
         args: ['-B', files('compiler/package_' + family + '.py'), '--compiler', aurorac],
         depends: aurorac, suite: ['full', 'merge', 'dev', 'packages', 'compiler'],
         env: oracle_env, workdir: meson.current_build_dir(), timeout: 300)
endforeach
# Storage and filesystem libraries: one compiled driver per family over data cases,
# compared with the golden file beside it (tests/compiler/storage).
foreach family : ['byte_storage', 'storage_binary', 'block_io', 'xfs_geometry', 'xfs_root', 'xfs_file']
    test(family.replace('_', '-'), python,
         args: ['-B', files('compiler/storage/' + family + '.py'), aurorac],
         depends: aurorac, suite: ['full', 'merge', 'dev', 'bytes', 'compiler'],
         env: oracle_env, workdir: meson.current_build_dir(), timeout: 120)
endforeach
test('xfs-offline-native', python,
     args: ['-B', '-O', files('../fixtures/xfs-offline/verify_native.py'),
            '--compiler', aurorac, '--meson-selected-compiler'],
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

# Bootstrap tooling only matters when the route runs: at compiler bumps.
test('bootstrap-identity-optimized', python,
     args: ['-B', '-O', files('test_bootstrap.py')],
     suite: ['full', 'release'], env: oracle_env, timeout: 60)

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
test('hosted-lexer', python,
     args: ['-B', files('meson_lexer_inputs.py'), hosted_lexer_test, meson.project_source_root(), '--all', frontend_forwarders],
     depends: hosted_lexer_test, suite: ['full', 'merge', 'dev', 'core', 'compiler'], env: oracle_env, timeout: 180)
bootstrap_args = ['-B', '-O', files('compiler/hosted_lexer_bootstrap.py'), aurorac, aurorac_stage2,
                  meson.project_source_root(), frontend_assembly[0], frontend_stage2_assembly[0]]
test('hosted-lexer-bootstrap', python, args: bootstrap_args,
     depends: [aurorac, aurorac_stage2], suite: ['full', 'merge', 'dev', 'core', 'compiler'],
     env: oracle_env, workdir: meson.current_build_dir(), timeout: 180, is_parallel: false)
# Historical C++ emitter oracle versus C2, plus C1/C2 corpus convergence: run at
# compiler bumps and releases (release suite), not on every merge.
foreach profile : [['default', []], ['closed', ['--local-symbols', '--referenced-reflection-only']]]
  test('emitter-differential-' + profile[0], python,
       args: ['-B', artifact_adapter, python, '-B', files('compiler/emitter_differential.py'),
              '--old-compiler', historical_cpp_oracle, '--old-compiler-sha256', historical_cpp_oracle_sha256,
              '--new-compiler', aurorac_stage2, '--stage1-compiler', aurorac,
              '--source-root', meson.project_source_root()] + profile[1] + ['--artifacts', '@ARTIFACTS@'],
       depends: [aurorac, aurorac_stage2], suite: ['full', 'release', 'compiler'], env: oracle_env,
       workdir: meson.current_build_dir(), timeout: 900, is_parallel: false, priority: 1)
endforeach

format_fixture = executable('format-fixture', 'compiler/format.cpp', dependencies: hosted_frontend,
                            include_directories: include_directories('../compiler'), native: true, override_options: fixture_options, install: false)
test('hosted-lexer-format', python,
     args: ['-B', files('meson_lexer_inputs.py'), format_fixture, meson.project_source_root(), '--all', frontend_forwarders],
     depends: format_fixture, suite: ['full', 'merge', 'dev', 'compiler'], env: oracle_env, timeout: 180)
test('hosted-lexer-format-cli', python, args: ['-B', '-O', files('compiler/format.py'), aurora_fmt],
     depends: aurora_fmt, suite: ['full', 'merge', 'dev', 'compiler'], env: oracle_env,
     workdir: meson.current_build_dir(), timeout: 180)

hosted_lexer_invalid = executable(
    'hosted-lexer-invalid', ['compiler/hosted_lexer_invalid.cpp', '../compiler/hosted_lexer.cpp', frontend_assembly[3]],
    cpp_args: ['-DAURORA_HOSTED_LEXER'], include_directories: include_directories('../compiler', '..'),
    native: true, override_options: fixture_options, install: false,
)
test('hosted-lexer-invalid', hosted_lexer_invalid, suite: ['full', 'merge', 'dev', 'core', 'compiler'], timeout: 30)

# The real generated-code fixture checks explicit AST/diagnostic contracts and
# private ABI behavior. The separate forged-return fixture never links it.
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
     args: files('../compiler/lexer.au', '../compiler/syntax_arena.au', '../compiler/parser.au',
                 '../library/std/array.au', '../library/console/session_files.au',
                 '../examples/kernel-graphical-console.au', '../library/fs/xfs_sector.au',
                 '../examples/class_values.au', '../library/std/utility.au', '../library/std/decimal.au',
                 '../library/std/json.au', '../library/package/graph.au', '../examples/function_token_values.au',
                 '../examples/class_values.au', '../examples/kernel-bios.au', '../compiler/resolution_kinds.au',
                 '../compiler/resolution_arena.au', '../compiler/resolver.au') + [frontend_forwarders] + files(
                 '../compiler/lowering_kinds.au', '../compiler/lowering_errors.au', '../compiler/lowering_storage.au',
                 '../compiler/lowering_common.au', '../compiler/lowering_configuration.au', '../compiler/lowering_types.au',
                 '../compiler/lowering_values.au', '../compiler/lowering_body.au', '../compiler/lowering.au',
                 '../compiler/lowering_frames.au', '../compiler/lowering_calls.au',
                 '../compiler/lowering_expressions.au', '../compiler/lowering_statements.au',
                 '../compiler/resolution_rows.au', '../compiler/resolution_names.au',
                 '../compiler/resolution_ingest.au', '../compiler/ir_graph.au', '../library/console/line.au',
                 '../compiler/ir_metadata_storage.au', '../compiler/ir_metadata.au',
                 '../compiler/ir_instruction_storage.au', '../compiler/ir_instructions.au',
                 '../compiler/ir_verification_errors.au',
                 '../compiler/x86_storage.au', '../compiler/x86_helpers.au', '../compiler/x86_scalar.au',
                 '../compiler/x86_objects.au', '../compiler/x86_resources.au', '../compiler/x86_facts.au',
                 '../compiler/x86_module.au', '../library/std/decimal_digits.au', '../compiler/formatter.au',
                 '../compiler/resolution_linkage.au',
                 '../compiler/ir_verification_storage.au',
                 '../compiler/ir_verification_initialization.au',
                 '../compiler/ir_verification_common.au',
                 '../compiler/ir_verification_values.au',
                 '../compiler/ir_verification_resources.au',
                 '../compiler/ir_verification_services.au',
                 '../compiler/ir_verification_transfer.au',
                 '../compiler/ir_verification.au'),
     suite: ['full', 'merge', 'dev', 'core', 'compiler'], timeout: 120)
hosted_parser_invalid = executable(
    'hosted-parser-invalid', ['compiler/hosted_parser_invalid.cpp', '../compiler/hosted_parser.cpp',
                              '../compiler/hosted_resolver.cpp', '../compiler/hosted_lowering.cpp',
                              '../compiler/hosted_lowering_diagnostics.cpp', '../compiler/hosted_ir_metadata.cpp',
                              '../compiler/hosted_ir_instructions.cpp',
                              '../compiler/ir_verify.cpp',
                              '../runtime/hosted_bytes.cpp', frontend_assembly[3]],
    cpp_args: ['-DAURORA_HOSTED_PARSER'], include_directories: include_directories('../compiler', '..'),
    native: true, override_options: fixture_options, install: false,
)
test('hosted-parser-invalid', hosted_parser_invalid,
     suite: ['full', 'merge', 'dev', 'core', 'compiler'], timeout: 30)
