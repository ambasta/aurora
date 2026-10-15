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

# Keep complete existing runners: no first-N sampling or weaker result/trap oracle.
# dev is quick feedback; slow contains exhaustive integration/ABI sweeps.
# full and unfiltered tests preserve all runners; core/bytes retain their coverage.
foreach entry : [
    ['frontend', 'compiler/run.py', 'core'],
    ['classes', 'compiler/classes.py', 'core'],
    ['value-calls', 'compiler/value_calls.py', 'core'],
    ['owned-mutation', 'compiler/owned_mutation.py', 'core'],
    ['class-arrays', 'compiler/class_arrays.py', 'core'],
    ['owned-bytes', 'compiler/owned_bytes.py', 'core'],
    ['owning-classes', 'compiler/owning_classes.py', 'core'],
    ['signed-integers', 'compiler/integers.py', 'core'],
    ['unsigned-integers', 'compiler/unsigned.py', 'core'],
    ['binary-literals', 'compiler/binary_literals.py', 'core'],
    ['modules', 'modules/run.py', 'core'],
    ['source-depth', 'modules/robustness.py', 'core'],
    ['byte-literals', 'compiler/byte_literals.py', 'bytes'],
    ['byte-codec', 'compiler/byte_codec.py', 'bytes'],
    ['binary-buffer', 'compiler/binary_buffer.py', 'bytes'],
    ['byte-buffer', 'compiler/byte_buffer.py', 'bytes'],
    ['method-spans', 'compiler/method_spans.py', 'bytes'],
    ['owned-spans', 'compiler/owned_spans.py', 'bytes'],
    ['json-owned', 'compiler/json_owned.py', 'bytes'],
    ['owned-sector', 'compiler/sector.py', 'bytes'],
    ['block-io', 'compiler/block_io.py', 'bytes'],
    ['sector-window', 'compiler/sector_window.py', 'bytes'],
    ['xfs-sector', 'compiler/xfs_sector.py', 'bytes'],
    ['xfs-file', 'compiler/xfs_file.py', 'bytes'],
    ['packed-values', 'compiler/packed_values.py', 'bytes'],
    ['sector-values', 'compiler/sector_values.py', 'bytes'],
    ['storage-binary', 'compiler/storage_binary.py', 'bytes'],
]
    feedback = 'dev'
    if entry[0] in ['block-io', 'sector-window', 'xfs-sector', 'xfs-file']
        feedback = 'slow'
    endif
    runner_args = ['-B', '-O', files(entry[1]), aurorac]
    if entry[0] == 'json-owned'
        runner_args = ['-B', artifact_adapter, python] + runner_args + ['--artifacts', '@ARTIFACTS@']
    endif
    test(
        entry[0],
        python,
        args: runner_args,
        depends: aurorac,
        suite: ['full', feedback, entry[2], 'compiler'],
        env: oracle_env,
        workdir: meson.current_build_dir(),
        timeout: entry[0] == 'xfs-file' ? 600 : 300,
        is_parallel: true,
    )
endforeach

initialization_facts = executable(
    'initialization-facts',
    'compiler/initialization_facts.cpp',
    dependencies: hosted_frontend,
    include_directories: include_directories('../compiler'),
    native: true,
    install: false,
)
test(
    'initialization-facts',
    initialization_facts,
    suite: ['full', 'dev', 'core', 'compiler'],
    timeout: 120,
)

class_arrays_ir = executable(
    'class-arrays-ir',
    'compiler/class_arrays_ir.cpp',
    dependencies: hosted_frontend,
    include_directories: include_directories('../compiler'),
    native: true,
    install: false,
)
test('class-arrays-ir', class_arrays_ir, suite: ['full', 'dev', 'core', 'compiler'], timeout: 120)

owned_mutation_ir = executable(
    'owned-mutation-ir',
    'compiler/owned_mutation_ir.cpp',
    dependencies: hosted_frontend,
    include_directories: include_directories('../compiler'),
    native: true,
    install: false,
)
test('owned-mutation-ir', owned_mutation_ir, suite: ['full', 'dev', 'core', 'compiler'], timeout: 120)
test(
    'owned-mutation-abi',
    python,
    args: ['-B', '-O', files('compiler/owned_mutation_abi.py'), owned_mutation_ir],
    depends: owned_mutation_ir,
    suite: ['full', 'dev', 'core', 'compiler'],
    env: oracle_env,
    workdir: meson.current_build_dir(),
    timeout: 180,
)

sector_values_ir = executable(
    'sector-values-ir',
    'compiler/sector_values_ir.cpp',
    dependencies: hosted_frontend,
    include_directories: include_directories('../compiler'),
    native: true,
    install: false,
)
test('sector-values-ir', sector_values_ir, suite: ['full', 'dev', 'bytes', 'compiler'], timeout: 120)
test(
    'sector-values-abi',
    python,
    args: ['-B', '-O', files('compiler/sector_values_abi.py'), sector_values_ir],
    depends: sector_values_ir,
    suite: ['full', 'dev', 'bytes', 'compiler'],
    env: oracle_env,
    workdir: meson.current_build_dir(),
    timeout: 180,
)

# Standalone behavioral runners participate in the ordinary full graph.
lint_fixture = executable(
    'lint-fixture', 'compiler/lint.cpp',
    include_directories: include_directories('../compiler'), dependencies: hosted_frontend,
    native: true, install: false,
)
test('semantic-lint', python,
     args: ['-B', artifact_adapter, python, '-B', files('compiler/lint.py'),
            aurora_fmt, aurorac, lint_fixture, '--artifacts', '@ARTIFACTS@'],
     depends: [aurora_fmt, aurorac, lint_fixture], suite: ['full', 'dev', 'compiler'],
     env: oracle_env, workdir: meson.current_build_dir(), timeout: 180)
test('function-overloads-independent', python,
     args: ['-B', artifact_adapter, python, '-B', files('compiler/function_overloads_independent.py'),
            aurorac, '--artifacts', '@ARTIFACTS@'],
     depends: aurorac, suite: ['full', 'slow', 'core', 'compiler'],
     env: oracle_env, workdir: meson.current_build_dir(), timeout: 300)
test('json-codecs-owned', python,
     args: ['-B', artifact_adapter, python, '-B', '-O', files('compiler/json_codecs_owned.py'),
            aurorac, '--artifacts', '@ARTIFACTS@'],
     depends: aurorac, suite: ['full', 'slow', 'bytes', 'compiler'],
     env: oracle_env, workdir: meson.current_build_dir(), timeout: 300)

# Compiler-free semantic selection and authority controls for package profiles.
test('package-profile-controls', python,
     args: ['-B', files('test_package_profiles.py')],
     suite: ['full', 'dev', 'packages', 'compiler'], env: oracle_env,
     workdir: meson.current_build_dir(), timeout: 60, is_parallel: true)

# Named semantic selections, explicitly partial; Meson/Ninja builds aurorac.
# Each family uses adapter-owned output beneath TMPDIR and gives every
# subprocess a private, cap-accounted tmp subdirectory.
foreach family : ['identity', 'manifest', 'graph']
    test(
        'package-' + family,
        python,
        args: ['-B', artifact_adapter, python, '-B', '-O', files('compiler/package_' + family + '.py'), aurorac,
               '--profile', 'dev', '--developer-selected-compiler', '--artifact-root', '@ARTIFACTS@'],
        depends: aurorac,
        suite: ['full', 'dev', 'packages'],
        env: oracle_env,
        workdir: meson.current_build_dir(),
        timeout: 300,
        is_parallel: true,
    )
endforeach

# Runtime-owned bytes are a hosted bootstrap boundary, separate from freestanding core.
owned_bytes_ir = executable(
    'owned-bytes-ir', 'compiler/owned_bytes_ir.cpp',
    dependencies: hosted_frontend,
    include_directories: include_directories('../compiler'), native: true, install: false,
)
test('owned-bytes-ir', owned_bytes_ir, suite: ['full', 'dev', 'core', 'compiler'], timeout: 120)
owned_bytes_host = executable(
    'owned-bytes-host', ['compiler/owned_bytes_host.cpp', '../runtime/hosted_bytes.cpp'],
    cpp_args: ['-DAURORA_HOSTED_BYTES_TESTING'], native: true, install: false,
)
test('owned-bytes-host', owned_bytes_host, suite: ['full', 'dev', 'core', 'compiler'], timeout: 120)

# Direct owning classes reuse the hosted byte adapter and private value ABI.
owning_classes_ir = executable(
    'owning-classes-ir', 'compiler/owning_classes_ir.cpp',
    dependencies: hosted_frontend,
    include_directories: include_directories('../compiler'), native: true, install: false,
)
test('owning-classes-ir', owning_classes_ir, suite: ['full', 'dev', 'core', 'compiler'], timeout: 120)
test(
    'owning-classes-abi', python,
    args: ['-B', '-O', files('compiler/owning_classes_abi.py'), owning_classes_ir],
    depends: owning_classes_ir, suite: ['full', 'dev', 'core', 'compiler'],
    env: oracle_env, workdir: meson.current_build_dir(), timeout: 180,
)

# Logical owner views share the established readonly-span source type.
owned_spans_ir = executable(
    'owned-spans-ir', 'compiler/owned_spans_ir.cpp',
    dependencies: hosted_frontend,
    include_directories: include_directories('../compiler'), native: true, install: false,
)
test('owned-spans-ir', owned_spans_ir, suite: ['full', 'dev', 'core', 'bytes', 'compiler'], timeout: 120)
test('owned-spans-source', python,
     args: ['-B', artifact_adapter, python, '-B', '-O', files('compiler/owned_spans_source.py'), aurorac,
            '--artifacts', '@ARTIFACTS@'],
     depends: aurorac, suite: ['full', 'dev', 'core', 'bytes', 'compiler'], env: oracle_env,
     workdir: meson.current_build_dir(), timeout: 180)
foreach mode : ['standalone', 'receiver']
    span_kernel_args = ['-B', artifact_adapter, python, '-B', '-O', files('compiler/owned_spans_kernel.py'), aurorac,
                        '--artifacts', '@ARTIFACTS@']
    if mode == 'receiver'
        span_kernel_args += ['--receiver-bound']
    endif
    test('owned-spans-kernel-' + mode, python,
         args: span_kernel_args, depends: aurorac, suite: ['full', 'dev', 'bytes', 'compiler'],
         env: oracle_env, workdir: meson.current_build_dir(), timeout: 180)
endforeach
# Meson owns compiler dependencies; this records observed artifact stability only.
test(
    'json-profile', python,
    args: ['-B', artifact_adapter, python, '-B', '-O', files('compiler/json_profile.py'),
           aurorac, '--developer-selected-compiler', '--artifacts', '@ARTIFACTS@'],
    depends: aurorac, suite: ['full', 'slow', 'bytes', 'compiler'], env: oracle_env,
    workdir: meson.current_build_dir(), timeout: 300, is_parallel: true,
)

logical_spans_abi = executable(
    'logical-spans-abi', 'compiler/logical_spans_abi.cpp',
    dependencies: hosted_frontend,
    include_directories: include_directories('../compiler'), native: true, install: false,
)
test('logical-spans-abi', python,
     args: ['-B', artifact_adapter, python, '-B', '-O', files('compiler/logical_spans_abi.py'),
            logical_spans_abi, '--artifacts', '@ARTIFACTS@'],
     depends: logical_spans_abi, suite: ['full', 'dev', 'core', 'bytes', 'compiler'],
     env: oracle_env, workdir: meson.current_build_dir(), timeout: 180)

# Synchronous method capabilities retain independent IR and literal-layout ABI gates.
method_spans_ir = executable(
    'method-spans-ir', 'compiler/method_spans_ir.cpp',
    dependencies: hosted_frontend,
    include_directories: include_directories('../compiler'), native: true, install: false,
)
test('method-spans-ir', method_spans_ir, suite: ['full', 'dev', 'core', 'bytes', 'compiler'], timeout: 120)
method_spans_abi = executable(
    'method-spans-abi', 'compiler/method_spans_abi.cpp',
    dependencies: hosted_frontend,
    include_directories: include_directories('../compiler'), native: true, install: false,
)
test('method-spans-abi', python,
     args: ['-B', artifact_adapter, python, '-B', '-O', files('compiler/method_spans_abi.py'),
            method_spans_abi, '--artifacts', '@ARTIFACTS@'],
     depends: method_spans_abi, suite: ['full', 'slow', 'core', 'bytes', 'compiler'],
     env: oracle_env, workdir: meson.current_build_dir(), timeout: 180)
# Single-scalar codecs retain their own independent oracle and hosted composition.
test(
    'json-codecs', python,
    args: ['-B', artifact_adapter, python, '-B', '-O', files('compiler/json_codecs.py'),
           aurorac, '--developer-selected-compiler', '--artifacts', '@ARTIFACTS@'],
    depends: aurorac, suite: ['full', 'slow', 'bytes', 'compiler'], env: oracle_env,
    workdir: meson.current_build_dir(), timeout: 300, is_parallel: true,
)

# Exact integer spelling conversion and mathematically bounded decimal output.
test(
    'json-integers', python,
    args: ['-B', artifact_adapter, python, '-B', '-O', files('compiler/json_integers.py'),
           aurorac, '--developer-selected-compiler', '--artifacts', '@ARTIFACTS@'],
    depends: aurorac, suite: ['full', 'slow', 'bytes', 'compiler'], env: oracle_env,
    workdir: meson.current_build_dir(), timeout: 660, is_parallel: true,
)

# Full-document validation precedes copied root member/index observations.
test(
    'json-lookup', python,
    args: ['-B', artifact_adapter, python, '-B', '-O', files('compiler/json_lookup.py'),
           aurorac, '--developer-selected-compiler', '--artifacts', '@ARTIFACTS@'],
    depends: aurorac, suite: ['full', 'slow', 'bytes', 'compiler'], env: oracle_env,
    workdir: meson.current_build_dir(), timeout: 1200, is_parallel: true,
)

# Keep routine borrowed-object feedback small; full owner/helper and literal ABI
# sweeps remain explicit slow coverage. Full/unfiltered runs retain every gate.
test('borrowed-objects-smoke', python,
     args: ['-B', '-O', files('compiler/borrowed_objects.py'), aurorac, '--smoke'],
     depends: aurorac, suite: ['full', 'dev', 'bytes', 'compiler'], env: oracle_env,
     workdir: meson.current_build_dir(), timeout: 120, is_parallel: true)
test('borrowed-objects', python,
     args: ['-B', '-O', files('compiler/borrowed_objects.py'), aurorac],
     depends: aurorac, suite: ['full', 'slow', 'bytes', 'compiler'], env: oracle_env,
     workdir: meson.current_build_dir(), timeout: 300, is_parallel: true)
borrowed_objects_ir = executable(
    'borrowed-objects-ir', 'compiler/borrowed_objects_ir.cpp',
    dependencies: hosted_frontend,
    include_directories: include_directories('../compiler'), native: true, install: false,
)
test('borrowed-objects-ir', borrowed_objects_ir, suite: ['full', 'dev', 'core', 'bytes', 'compiler'], timeout: 120)
borrowed_objects_abi = executable(
    'borrowed-objects-abi', 'compiler/borrowed_objects_abi.cpp',
    dependencies: hosted_frontend,
    include_directories: include_directories('../compiler'), native: true, install: false,
)
test('borrowed-objects-abi', python,
     args: ['-B', artifact_adapter, python, '-B', '-O', files('compiler/borrowed_objects_abi.py'),
            borrowed_objects_abi, '--artifacts', '@ARTIFACTS@'],
     depends: borrowed_objects_abi, suite: ['full', 'slow', 'core', 'bytes', 'compiler'],
     env: oracle_env, workdir: meson.current_build_dir(), timeout: 180)

# Complete native string transactions stay in slow; routine feedback uses an
# explicitly partial manifest with the same byte and allocation assertions.
test('json-string-write-smoke', python,
     args: ['-B', '-O', files('compiler/json_string_write.py'), aurorac, '--smoke'],
     depends: aurorac, suite: ['full', 'dev', 'bytes', 'compiler'], env: oracle_env,
     workdir: meson.current_build_dir(), timeout: 120, is_parallel: true)
test('json-string-write', python,
     args: ['-B', '-O', files('compiler/json_string_write.py'), aurorac],
     depends: aurorac, suite: ['full', 'slow', 'bytes', 'compiler'], env: oracle_env,
     workdir: meson.current_build_dir(), timeout: 600, is_parallel: true)

# Sealed service authority has its own independent verifier and host-grant model.
console_service_ir = executable(
    'console-service-ir', 'compiler/console_service_ir.cpp',
    dependencies: hosted_frontend,
    include_directories: include_directories('../compiler'), native: true, install: false,
)
test('console-service-ir', console_service_ir, suite: ['full', 'dev', 'core', 'compiler'], timeout: 120)
console_session = executable('console-session', 'kernel-console-session.cpp', native: true, install: false)
test('console-session', console_session, suite: ['full', 'dev'], timeout: 120)
test('console-service-source-native', python,
     args: ['-B', artifact_adapter, python, '-B', '-O', files('compiler/console_service.py'), aurorac,
            '--artifacts', '@ARTIFACTS@'],
     depends: aurorac, suite: ['full', 'slow', 'core', 'compiler'], env: oracle_env,
     workdir: meson.current_build_dir(), timeout: 300)
test('console-service-admission-controls', python,
     args: ['-B', '-O', files('kernel-console-service-admission.py')],
     suite: ['full', 'dev'], timeout: 120)

# Second sealed kind reuses the service verifier and private bridge.
display_service_ir = executable(
    'display-service-ir', 'compiler/service_group_ir.cpp',
    dependencies: hosted_frontend,
    include_directories: include_directories('../compiler'), native: true, install: false,
)
test('display-service-ir', python,
     args: ['-B', artifact_adapter, python, '-B', '-O', files('compiler/service_group_ir_abi.py'),
            display_service_ir.full_path(), '--artifacts', '@ARTIFACTS@'],
     depends: display_service_ir, suite: ['full', 'dev', 'core', 'compiler'], env: oracle_env, timeout: 120)
test('display-service-source-native', python,
     args: ['-B', artifact_adapter, python, '-B', '-O', files('compiler/display_service.py'), aurorac,
            '--artifacts', '@ARTIFACTS@'],
     depends: aurorac, suite: ['full', 'slow', 'core', 'compiler'], env: oracle_env,
     workdir: meson.current_build_dir(), timeout: 300)

# Event intake retains the existing service loan graph and executes the real
# Aurora consumer against bounded hosted observations; no guest is run here.
iommu_event_ir = executable(
    'iommu-event-service-ir', 'compiler/iommu_event_service_ir.cpp',
    dependencies: hosted_frontend,
    include_directories: include_directories('../compiler'), native: true, install: false,
)
test('iommu-event-source-native', python,
     args: ['-B', artifact_adapter, python, '-B', '-O', files('compiler/iommu_event_service.py'), aurorac,
            iommu_event_ir.full_path(), '--artifacts', '@ARTIFACTS@'],
     depends: [aurorac, iommu_event_ir], suite: ['full', 'slow', 'core', 'compiler'], env: oracle_env,
     workdir: meson.current_build_dir(), timeout: 300)
iommu_event_session = executable('iommu-event-session', 'kernel-iommu-event-session.cpp', native: true, install: false)
test('iommu-event-session', iommu_event_session, suite: ['full', 'dev'], timeout: 120)
iommu_event_profile = executable('iommu-event-profile', 'kernel-uefi-event-profile.cpp', native: true, install: false)
test('iommu-event-profile', iommu_event_profile, suite: ['full', 'dev'], timeout: 120)
iommu_event_backing = executable('iommu-event-backing', 'kernel-uefi-event-backing.cpp', native: true, install: false)
test('iommu-event-backing', iommu_event_backing, suite: ['full', 'dev'], timeout: 120)
test('iommu-event-admission-controls', python,
     args: ['-B', files('kernel-uefi-event-admission.py')], suite: ['full', 'dev'], timeout: 120)
test('iommu-event-admission-controls-optimized', python,
     args: ['-B', '-O', files('kernel-uefi-event-admission.py')], suite: ['full', 'dev'], timeout: 120)




# Output-only framebuffer boundary and its actual Aurora software renderer.
foreach model : ['framebuffer', 'framebuffer-tables', 'framebuffer-loader', 'framebuffer-pixels']
    framebuffer_model = executable(
        'uefi-' + model, 'kernel-uefi-' + model + '.cpp',
        native: true, install: false, link_args: ['-no-pie'],
    )
    test('uefi-' + model, framebuffer_model, suite: ['full', 'dev'], timeout: 120)
endforeach
display_session = executable('display-session', 'kernel-display-session.cpp', native: true, install: false)
test('display-session', display_session, suite: ['full', 'dev'], timeout: 120)
foreach control : [
    'kernel-framebuffer-admission.py', 'kernel_framebuffer_probe_oracle.py',
    'test_framebuffer_capture.py', 'framebuffer-preview.py',
]
    test(control, python, args: ['-B', files(control)], suite: ['full', 'dev'], env: oracle_env, timeout: 120)
endforeach
test('display-renderer-native', python,
     args: ['-B', files('kernel-display-renderer.py'), aurorac], depends: aurorac,
     suite: ['full', 'slow'], env: oracle_env, timeout: 300)
# The complete generated graphical consumer remains outside fast developer feedback.
# Its driver builds consumer/harness artifacts per invocation, never aurorac itself.
test('graphical-console-native', python,
     args: ['-B', artifact_adapter, python, '-B', '-O', files('kernel-graphical-console.py'), '--run', aurorac,
            '--developer-selected-compiler', '--artifacts', '@ARTIFACTS@'], depends: aurorac,
     suite: ['full', 'slow'], env: oracle_env, workdir: meson.current_build_dir(), timeout: 600)
graphical_paging = executable('graphical-paging', 'kernel-graphical-paging.cpp',
                            native: true, install: false, override_options: ['optimization=1'],
                            link_args: ['-no-pie'])
test('graphical-paging', graphical_paging, suite: ['full', 'dev'], timeout: 120)
test('graphical-admission-controls', python,
     args: ['-B', files('kernel-graphical-admission-controls.py')],
     suite: ['full', 'dev'], env: oracle_env, timeout: 120)
test('graphical-admission-controls-optimized', python,
     args: ['-B', '-O', files('kernel-graphical-admission-controls.py')],
     suite: ['full', 'dev'], env: oracle_env, timeout: 120)

test('graphical-smoke-controls', python,
     args: ['-B', files('kernel-graphical-smoke.py')],
     suite: ['full', 'dev'], env: oracle_env, timeout: 120)
test('graphical-smoke-controls-optimized', python,
     args: ['-B', '-O', files('kernel-graphical-smoke.py')],
     suite: ['full', 'dev'], env: oracle_env, timeout: 120)

# Previously Make-only complete source oracles. Keep exhaustive sweeps in slow.
foreach runner : [
  'templates', 'function_templates', 'function_overloads', 'fixed_containers',
  'composed_values', 'nested_values', 'decimal_values', 'enum_composition',
  'method_values', 'u8_numeric', 'readonly_spans', 'utf8', 'utf8_encoding',
  'integer_oracle', 'unsigned_oracle',
]
  runner_args = ['-B', '-O', files('compiler/' + runner + '.py'), aurorac]
  if runner in ['utf8', 'utf8_encoding']
    runner_args = ['-B', artifact_adapter, python] + runner_args + ['--artifacts', '@ARTIFACTS@']
  endif
  test(runner.replace('_', '-'), python,
       args: runner_args,
       depends: aurorac, suite: ['full', 'slow', 'compiler'], env: oracle_env,
       workdir: meson.current_build_dir(), timeout: 900, is_parallel: true)
endforeach

# Public Make routing must be exercised by the required developer suite.
test('graphical-image-policy', python, args: ['-B', files('kernel-graphical-image-policy.py')],
     suite: ['full', 'dev'], env: oracle_env, timeout: 30)
test('graphical-image-policy-optimized', python, args: ['-B', '-O', files('kernel-graphical-image-policy.py')],
     suite: ['full', 'dev'], env: oracle_env, timeout: 30)
test('graphical-profile-metadata', python, args: ['-B', files('kernel-graphical-profile-metadata.py')],
     suite: ['full', 'dev'], env: oracle_env, timeout: 30)
test('graphical-profile-metadata-optimized', python, args: ['-B', '-O', files('kernel-graphical-profile-metadata.py')],
     suite: ['full', 'dev'], env: oracle_env, timeout: 30)
test('developer-commands', python, args: ['-B', files('developer-commands.py')],
     suite: ['full', 'dev'], env: oracle_env, timeout: 120)
test('developer-commands-optimized', python, args: ['-B', '-O', files('developer-commands.py')],
     suite: ['full', 'dev'], env: oracle_env, timeout: 120)
test('console-routing', python, args: ['-B', files('kernel-console-routing.py')],
     suite: ['full', 'dev'], env: oracle_env, timeout: 120)

test('compiler-test-inventory', python,
     args: ['-B', files('test-inventory.py'), '--meson-info',
            meson.project_build_root() / 'meson-info' / 'intro-tests.json'],
     suite: ['full', 'dev'], env: oracle_env, timeout: 30)

test('program-console-entrypoints', python,
     args: ['-B', files('kernel-program-console-entrypoints.py')],
     suite: ['full', 'dev'], env: oracle_env, timeout: 60)

# Compiler-free model-fixture integrity/mocks. No emulator or hardware acceptance.
foreach mode : ['ordinary', 'optimized']
    diagnostic_args = ['-B']
    if mode == 'optimized'
        diagnostic_args += ['-O']
    endif
    diagnostic_args += [files('iommu-diagnostics.py')]
    test('iommu-diagnostics-' + mode, python, args: diagnostic_args,
         suite: ['full', 'dev'], env: oracle_env, timeout: 30)
endforeach

# Compiler-free controls for complete per-command artifact accounting.
foreach mode : ['ordinary', 'optimized']
    budget_args = ['-B']
    if mode == 'optimized'
        budget_args += ['-O']
    endif
    budget_args += [files('test_artifact_budget.py')]
    test('artifact-budget-' + mode, python, args: budget_args,
         suite: ['full', 'dev'], env: oracle_env, timeout: 30)
endforeach

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
        include_directories: include_directories('../compiler'), native: true, install: false,
    )}
endforeach

test('diagnostics', python,
     args: ['-B', '-O', files('compiler/diagnostics.py'), aurorac, compiler_fixtures['diagnostics']],
     depends: [aurorac, compiler_fixtures['diagnostics']], suite: ['full', 'slow', 'compiler'],
     env: oracle_env, workdir: meson.current_build_dir(), timeout: 180)
test('source-overlays', python,
     args: ['-B', '-O', files('compiler/source_overlays.py'), compiler_fixtures['source_overlays']],
     depends: compiler_fixtures['source_overlays'], suite: ['full', 'slow', 'compiler'],
     env: oracle_env, workdir: meson.current_build_dir(), timeout: 120)
# The exact legacy glob roots; this adapter enumerates them anew on every run.
test('lexer-trivia', python,
     args: ['-B', files('meson_lexer_inputs.py'), compiler_fixtures['lexer_trivia'], meson.project_source_root()],
     depends: compiler_fixtures['lexer_trivia'], suite: ['full', 'slow', 'compiler'],
     env: oracle_env, timeout: 180)
foreach fixture : ['ir_tests', 'stack_probes', 'method_values_ir', 'readonly_windows_ir', 'short_circuit_ir']
    test(fixture.replace('_', '-'), compiler_fixtures[fixture],
         suite: ['full', 'slow', 'compiler'], env: oracle_env, timeout: 180)
endforeach
test('ir-exhaustive', python,
     args: ['-B', artifact_adapter, python, '-B', files('compiler/ir_exhaustive.py'), compiler_fixtures['ir_tests'],
            '--abi-header', frontend_assembly[3], '--abi-facts', frontend_assembly[2],
            '--compiler', aurorac, '--frontend-library', frontend_library, '--artifacts', '@ARTIFACTS@'],
     depends: [compiler_fixtures['ir_tests'], frontend_assembly, frontend_library, aurorac], suite: ['full', 'slow', 'compiler'],
     env: oracle_env, workdir: meson.current_build_dir(), timeout: 600)
test('stack-guards', python,
     args: ['-B', '-O', files('compiler/sector_values_abi.py'), compiler_fixtures['stack_probes'], '--stack-guards'],
     depends: compiler_fixtures['stack_probes'], suite: ['full', 'slow', 'compiler'],
     env: oracle_env, workdir: meson.current_build_dir(), timeout: 180)
test('method-values-abi', python,
     args: ['-B', artifact_adapter, python, '-B', '-O', files('compiler/method_values_abi.py'),
            compiler_fixtures['method_values_ir'], '--work-dir', '@ARTIFACTS@'],
     depends: compiler_fixtures['method_values_ir'], suite: ['full', 'slow', 'compiler'],
     env: oracle_env, workdir: meson.current_build_dir(), timeout: 180)
foreach family : ['readonly_windows', 'short_circuit']
    test(family.replace('_', '-'), python,
         args: ['-B', artifact_adapter, python, '-B', '-O', files('compiler/' + family + '.py'),
                aurorac, '--artifacts', '@ARTIFACTS@'],
         depends: aurorac, suite: ['full', 'slow', 'compiler'],
         env: oracle_env, workdir: meson.current_build_dir(), timeout: 300)
    test(family.replace('_', '-') + '-ir-native', python,
         args: ['-B', artifact_adapter, python, '-B', '-O', files('compiler/' + family + '_ir_native.py'),
                compiler_fixtures[family + '_ir'], '--artifacts', '@ARTIFACTS@'],
         depends: compiler_fixtures[family + '_ir'], suite: ['full', 'slow', 'compiler'],
         env: oracle_env, workdir: meson.current_build_dir(), timeout: 300)
endforeach
foreach family : ['utf8_range', 'utf8_lines', 'token_scan']
    test(family.replace('_', '-'), python,
         args: ['-B', artifact_adapter, python, '-B', '-O', files('compiler/' + family + '.py'),
                '--compiler', aurorac, '--meson-selected-compiler', '--artifacts', '@ARTIFACTS@'],
         depends: aurorac, suite: ['full', 'slow', 'compiler'],
         env: oracle_env, workdir: meson.current_build_dir(), timeout: 600)
endforeach
test('xfs-geometry', python,
     args: ['-B', artifact_adapter, python, '-B', '-O', files('compiler/xfs_geometry.py'),
            aurorac, '--meson-selected-compiler', '--mutation-controls', '--artifacts', '@ARTIFACTS@'],
     depends: aurorac, suite: ['full', 'slow', 'compiler'],
     env: oracle_env, workdir: meson.current_build_dir(), timeout: 600)
foreach family : ['xfs_root', 'xfs_root_api', 'xfs_root_entry']
    test(family.replace('_', '-'), python,
         args: ['-B', artifact_adapter, python, '-B', '-O', files('compiler/' + family + '.py'),
                '--repo-root', meson.project_source_root(),
                '--fixture-root', meson.project_source_root() / 'fixtures/xfs-root',
                '--artifact-root', '@ARTIFACTS@', '--compiler', aurorac, '--meson-selected-compiler'],
         depends: aurorac, suite: ['full', 'slow', 'compiler'],
         env: oracle_env, workdir: meson.current_build_dir(), timeout: 600)
endforeach
test('xfs-offline-native', python,
     args: ['-B', '-O', files('../fixtures/xfs-offline/verify_native.py'),
            '--compiler', aurorac, '--meson-selected-compiler'],
     depends: aurorac, suite: ['full', 'slow', 'compiler'],
     env: oracle_env, workdir: meson.current_build_dir(), timeout: 300)
foreach family : ['host_sources_tests', 'host_output_tests']
    host_fixture = executable(family.replace('_', '-'), 'modules/' + family + '.cpp',
        include_directories: include_directories('../compiler'),
        dependencies: dependency('threads'), native: true, install: false)
    test(family.replace('_', '-'), python,
         args: ['-B', files('modules/host_sources.py'), host_fixture],
         depends: host_fixture, suite: ['full', 'slow', 'compiler'],
         env: oracle_env, workdir: meson.current_build_dir(), timeout: 180)
endforeach

# Full package profiles supplement fast dev selections. All cases/rejections are
# retained; the observed Meson artifact is never described as an external pin.
foreach family : ['identity', 'manifest', 'graph']
    test('package-' + family + '-full', python,
         args: ['-B', artifact_adapter, python, '-B', '-O', files('compiler/package_' + family + '.py'),
                aurorac, '--profile', 'full', '--meson-selected-compiler',
                '--candidate-cap-mib', '1024', '--artifact-root', '@ARTIFACTS@'],
         depends: aurorac, suite: ['full', 'slow', 'integration', 'packages'],
         env: oracle_env, workdir: meson.current_build_dir(), timeout: 900)
endforeach
foreach mode : ['ordinary', 'optimized']
    identity_args = ['-B']
    if mode == 'optimized'
        identity_args += ['-O']
    endif
    test('meson-identity-' + mode, python,
         args: identity_args + [files('test_meson_identity.py')],
         suite: ['full', 'dev'], env: oracle_env, timeout: 30)
endforeach

test('clean-controls', python,
     args: ['-B', files('test_clean.py')],
     suite: ['full', 'dev'], env: oracle_env, timeout: 30)

subdir('native')

# Raw ESP preparation is filesystem-only; these controls never launch a guest.
test('iommu-event-esp-controls', python,
     args: ['-B', files('kernel-uefi-event-esp.py')], suite: ['full', 'dev'], timeout: 120)
test('iommu-event-esp-controls-optimized', python,
     args: ['-B', '-O', files('kernel-uefi-event-esp.py')], suite: ['full', 'dev'], timeout: 120)

# Developer Event controls use synthetic bytes and owned fake children, never QEMU.
foreach mode : ['', '-O']
  foreach test_name : ['oracle', 'smoke']
    test('iommu-event-' + test_name + '-controls' + (mode == '' ? '' : '-optimized'), python,
         args: ['-B'] + (mode == '' ? [] : [mode]) + files('kernel-iommu-event-' + test_name + '.py'),
         suite: ['full', 'dev'], timeout: 120)
  endforeach
endforeach

# This fixture always links the Aurora phase; the C++ scanner is only its oracle.
hosted_lexer_abi = custom_target(
    'hosted-lexer-abi-object', input: 'compiler/hosted_lexer_abi.S', output: 'hosted-lexer-abi.o',
    command: native_cpp.cmd_array() + ['-c', '-x', 'assembler', '@INPUT@', '-o', '@OUTPUT@'],
)
hosted_lexer_test = executable(
    'hosted-lexer-test', ['compiler/hosted_lexer.cpp', hosted_lexer_abi],
    dependencies: hosted_frontend, include_directories: include_directories('../compiler'),
    native: true, install: false,
)
test('hosted-lexer', python,
     args: ['-B', files('meson_lexer_inputs.py'), hosted_lexer_test, meson.project_source_root(), '--all'],
     depends: hosted_lexer_test, suite: ['full', 'dev', 'core', 'compiler'], env: oracle_env, timeout: 180)
bootstrap_args = ['-B', '-O', files('compiler/hosted_lexer_bootstrap.py'), aurorac, aurorac_stage2,
                  meson.project_source_root(), frontend_assembly[0], frontend_stage2_assembly[0]]
test('hosted-lexer-bootstrap', python, args: bootstrap_args,
     depends: [aurorac, aurorac_stage2], suite: ['full', 'dev', 'core', 'compiler'],
     env: oracle_env, workdir: meson.current_build_dir(), timeout: 180)
# Comparing every other source across both stages compiles the whole corpus twice.
# Run this heavy comparison alone and first; retain its existing watchdogs.
test('hosted-lexer-bootstrap-corpus', python, args: bootstrap_args + ['--corpus'],
     depends: [aurorac, aurorac_stage2], suite: ['full', 'slow', 'compiler'],
     env: oracle_env, workdir: meson.current_build_dir(), timeout: 600,
     is_parallel: false, priority: 1)

format_fixture = executable('format-fixture', 'compiler/format.cpp', dependencies: hosted_frontend,
                            include_directories: include_directories('../compiler'), native: true, install: false)
test('hosted-lexer-format', python,
     args: ['-B', files('meson_lexer_inputs.py'), format_fixture, meson.project_source_root(), '--all'],
     depends: format_fixture, suite: ['full', 'dev', 'compiler'], env: oracle_env, timeout: 180)
test('hosted-lexer-format-cli', python, args: ['-B', '-O', files('compiler/format.py'), aurora_fmt],
     depends: aurora_fmt, suite: ['full', 'dev', 'compiler'], env: oracle_env,
     workdir: meson.current_build_dir(), timeout: 180)

hosted_lexer_invalid = executable(
    'hosted-lexer-invalid', ['compiler/hosted_lexer_invalid.cpp', '../compiler/hosted_lexer.cpp', frontend_assembly[3]],
    cpp_args: ['-DAURORA_HOSTED_LEXER'], include_directories: include_directories('../compiler', '..'),
    native: true, install: false,
)
test('hosted-lexer-invalid', hosted_lexer_invalid, suite: ['full', 'dev', 'core', 'compiler'], timeout: 30)

# The real generated-code fixture checks explicit AST/diagnostic contracts and
# private ABI behavior. The separate forged-return fixture never links it.
hosted_parser_abi = custom_target(
    'hosted-parser-abi-object', input: 'compiler/hosted_parser_abi.S', output: 'hosted-parser-abi.o',
    command: native_cpp.cmd_array() + ['-c', '-x', 'assembler', '@INPUT@', '-o', '@OUTPUT@'],
)
hosted_parser_test = executable(
    'hosted-parser-test', ['compiler/hosted_parser.cpp', hosted_parser_abi],
    dependencies: hosted_frontend, include_directories: include_directories('../compiler'),
    native: true, install: false,
)
test('hosted-parser', hosted_parser_test,
     args: files('../compiler/lexer.au', '../compiler/syntax_arena.au', '../compiler/parser.au',
                 '../library/std/array.au', '../library/console/session_files.au',
                 '../examples/kernel-graphical-console.au', '../library/fs/xfs_sector.au',
                 '../examples/class_values.au', '../library/std/utility.au', '../library/std/decimal.au',
                 '../library/std/json.au', '../library/package/graph.au', '../examples/function_token_values.au',
                 '../examples/class_values.au', '../examples/kernel-bios.au', '../compiler/resolution_kinds.au',
                 '../compiler/resolution_arena.au', '../compiler/resolver.au', '../compiler/frontend.au',
                 '../compiler/lowering_kinds.au', '../compiler/lowering_errors.au', '../compiler/lowering_storage.au',
                 '../compiler/lowering_common.au', '../compiler/lowering_configuration.au', '../compiler/lowering_types.au',
                 '../compiler/lowering_values.au', '../compiler/lowering_body.au', '../compiler/lowering.au',
                 '../compiler/lowering_frames.au', '../compiler/lowering_calls.au',
                 '../compiler/lowering_expressions.au', '../compiler/lowering_statements.au',
                 '../compiler/resolution_rows.au', '../compiler/resolution_names.au',
                 '../compiler/resolution_ingest.au', '../compiler/ir_graph.au', '../library/console/line.au',
                 '../compiler/ir_metadata_storage.au', '../compiler/ir_metadata.au',
                 '../compiler/ir_instruction_storage.au', '../compiler/ir_instructions.au',
                 '../compiler/ir_initialization.au',
                 '../compiler/x86_storage.au', '../compiler/x86_helpers.au', '../compiler/x86_scalar.au',
                 '../compiler/x86_objects.au', '../compiler/x86_resources.au', '../compiler/x86_facts.au',
                 '../compiler/x86_module.au', '../library/std/decimal_digits.au'),
     suite: ['full', 'dev', 'core', 'compiler'], timeout: 120)
hosted_parser_invalid = executable(
    'hosted-parser-invalid', ['compiler/hosted_parser_invalid.cpp', '../compiler/hosted_parser.cpp',
                              '../compiler/hosted_resolver.cpp', '../compiler/hosted_lowering.cpp',
                              '../compiler/hosted_lowering_diagnostics.cpp', '../compiler/hosted_ir_metadata.cpp',
                              '../compiler/hosted_ir_instructions.cpp', '../compiler/hosted_ir_initialization.cpp',
                              '../compiler/ir_verify.cpp',
                              '../runtime/hosted_bytes.cpp', frontend_assembly[3]],
    cpp_args: ['-DAURORA_HOSTED_PARSER'], include_directories: include_directories('../compiler', '..'),
    native: true, install: false,
)
test('hosted-parser-invalid', hosted_parser_invalid,
     suite: ['full', 'dev', 'core', 'compiler'], timeout: 30)
