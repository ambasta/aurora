# Every registered Python runner owns unique TemporaryDirectory outputs beneath
# this build directory, including module alias, FIFO and oversized-source cases.
# Source/library inputs are read-only; parallel tests share no generated paths.
oracle_env = environment()
oracle_env.set('TMPDIR', meson.current_build_dir())
oracle_env.set('TMP', meson.current_build_dir())
oracle_env.set('TEMP', meson.current_build_dir())
oracle_env.set('PYTHONDONTWRITEBYTECODE', '1')
oracle_env.set('CXX', oracle_cxx)

# Keep complete existing runners: no first-N sampling or weaker result/trap oracle.
# dev is quick feedback; slow contains exhaustive integration/ABI sweeps.
# full and unfiltered tests preserve all runners; core/bytes retain their coverage.
foreach entry : [
    ['frontend', 'compiler/run.py', 'core'],
    ['classes', 'compiler/classes.py', 'core'],
    ['value-calls', 'compiler/value_calls.py', 'core'],
    ['owned-mutation', 'compiler/owned_mutation.py', 'core'],
    ['owned-bytes', 'compiler/owned_bytes.py', 'core'],
    ['owning-classes', 'compiler/owning_classes.py', 'core'],
    ['signed-integers', 'compiler/integers.py', 'core'],
    ['unsigned-integers', 'compiler/unsigned.py', 'core'],
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
    test(
        entry[0],
        python,
        args: ['-B', '-O', files(entry[1]), aurorac],
        depends: aurorac,
        suite: ['full', feedback, entry[2]],
        env: oracle_env,
        workdir: meson.current_build_dir(),
        timeout: 300,
        is_parallel: true,
    )
endforeach

initialization_facts = executable(
    'initialization-facts',
    'compiler/initialization_facts.cpp',
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

owned_mutation_ir = executable(
    'owned-mutation-ir',
    'compiler/owned_mutation_ir.cpp',
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

# Named semantic selections, explicitly partial; Meson/Ninja builds aurorac.
# Each family creates a unique retained receipt/output directory beneath TMPDIR
# and gives every subprocess a private, cap-accounted tmp subdirectory.
foreach family : ['identity', 'manifest', 'graph']
    test(
        'package-' + family,
        python,
        args: ['-B', '-O', files('compiler/package_' + family + '.py'), aurorac,
               '--profile', 'dev', '--developer-selected-compiler'],
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
    include_directories: include_directories('../compiler'), native: true, install: false,
)
test('owned-spans-ir', owned_spans_ir, suite: ['full', 'dev', 'core', 'bytes', 'compiler'], timeout: 120)
test('owned-spans-source', python,
     args: ['-B', '-O', files('compiler/owned_spans_source.py'), aurorac],
     depends: aurorac, suite: ['full', 'dev', 'core', 'bytes'], env: oracle_env,
     workdir: meson.current_build_dir(), timeout: 180)
foreach mode : ['standalone', 'receiver']
    span_kernel_args = ['-B', '-O', files('compiler/owned_spans_kernel.py'), aurorac]
    if mode == 'receiver'
        span_kernel_args += ['--receiver-bound']
    endif
    test('owned-spans-kernel-' + mode, python,
         args: span_kernel_args, depends: aurorac, suite: ['full', 'dev', 'bytes'],
         env: oracle_env, workdir: meson.current_build_dir(), timeout: 180)
endforeach
# Meson owns compiler dependencies; this records observed artifact stability only.
test(
    'json-profile', python,
    args: ['-B', '-O', files('compiler/json_profile.py'), aurorac, '--developer-selected-compiler'],
    depends: aurorac, suite: ['full', 'slow', 'bytes'], env: oracle_env,
    workdir: meson.current_build_dir(), timeout: 300, is_parallel: true,
)

logical_spans_abi = executable(
    'logical-spans-abi', 'compiler/logical_spans_abi.cpp',
    include_directories: include_directories('../compiler'), native: true, install: false,
)
test('logical-spans-abi', python,
     args: ['-B', '-O', files('compiler/logical_spans_abi.py'), logical_spans_abi],
     depends: logical_spans_abi, suite: ['full', 'dev', 'core', 'bytes', 'compiler'],
     env: oracle_env, workdir: meson.current_build_dir(), timeout: 180)

# Synchronous method capabilities retain independent IR and literal-layout ABI gates.
method_spans_ir = executable(
    'method-spans-ir', 'compiler/method_spans_ir.cpp',
    include_directories: include_directories('../compiler'), native: true, install: false,
)
test('method-spans-ir', method_spans_ir, suite: ['full', 'dev', 'core', 'bytes', 'compiler'], timeout: 120)
method_spans_abi = executable(
    'method-spans-abi', 'compiler/method_spans_abi.cpp',
    include_directories: include_directories('../compiler'), native: true, install: false,
)
test('method-spans-abi', python,
     args: ['-B', '-O', files('compiler/method_spans_abi.py'), method_spans_abi],
     depends: method_spans_abi, suite: ['full', 'slow', 'core', 'bytes', 'compiler'],
     env: oracle_env, workdir: meson.current_build_dir(), timeout: 180)
# Single-scalar codecs retain their own independent oracle and hosted composition.
test(
    'json-codecs', python,
    args: ['-B', '-O', files('compiler/json_codecs.py'), aurorac, '--developer-selected-compiler'],
    depends: aurorac, suite: ['full', 'slow', 'bytes'], env: oracle_env,
    workdir: meson.current_build_dir(), timeout: 300, is_parallel: true,
)

# Exact integer spelling conversion and mathematically bounded decimal output.
test(
    'json-integers', python,
    args: ['-B', '-O', files('compiler/json_integers.py'), aurorac, '--developer-selected-compiler'],
    depends: aurorac, suite: ['full', 'slow', 'bytes'], env: oracle_env,
    workdir: meson.current_build_dir(), timeout: 300, is_parallel: true,
)

# Full-document validation precedes copied root member/index observations.
test(
    'json-lookup', python,
    args: ['-B', '-O', files('compiler/json_lookup.py'), aurorac, '--developer-selected-compiler'],
    depends: aurorac, suite: ['full', 'slow', 'bytes'], env: oracle_env,
    workdir: meson.current_build_dir(), timeout: 600, is_parallel: true,
)

# Keep routine borrowed-object feedback small; full owner/helper and literal ABI
# sweeps remain explicit slow coverage. Full/unfiltered runs retain every gate.
test('borrowed-objects-smoke', python,
     args: ['-B', '-O', files('compiler/borrowed_objects.py'), aurorac, '--smoke'],
     depends: aurorac, suite: ['full', 'dev', 'bytes'], env: oracle_env,
     workdir: meson.current_build_dir(), timeout: 120, is_parallel: true)
test('borrowed-objects', python,
     args: ['-B', '-O', files('compiler/borrowed_objects.py'), aurorac],
     depends: aurorac, suite: ['full', 'slow', 'bytes'], env: oracle_env,
     workdir: meson.current_build_dir(), timeout: 300, is_parallel: true)
borrowed_objects_ir = executable(
    'borrowed-objects-ir', 'compiler/borrowed_objects_ir.cpp',
    include_directories: include_directories('../compiler'), native: true, install: false,
)
test('borrowed-objects-ir', borrowed_objects_ir, suite: ['full', 'dev', 'core', 'bytes', 'compiler'], timeout: 120)
borrowed_objects_abi = executable(
    'borrowed-objects-abi', 'compiler/borrowed_objects_abi.cpp',
    include_directories: include_directories('../compiler'), native: true, install: false,
)
test('borrowed-objects-abi', python,
     args: ['-B', '-O', files('compiler/borrowed_objects_abi.py'), borrowed_objects_abi],
     depends: borrowed_objects_abi, suite: ['full', 'slow', 'core', 'bytes', 'compiler'],
     env: oracle_env, workdir: meson.current_build_dir(), timeout: 180)

# Complete native string transactions stay in slow; routine feedback uses an
# explicitly partial manifest with the same byte and allocation assertions.
test('json-string-write-smoke', python,
     args: ['-B', '-O', files('compiler/json_string_write.py'), aurorac, '--smoke'],
     depends: aurorac, suite: ['full', 'dev', 'bytes'], env: oracle_env,
     workdir: meson.current_build_dir(), timeout: 120, is_parallel: true)
test('json-string-write', python,
     args: ['-B', '-O', files('compiler/json_string_write.py'), aurorac],
     depends: aurorac, suite: ['full', 'slow', 'bytes'], env: oracle_env,
     workdir: meson.current_build_dir(), timeout: 600, is_parallel: true)

# Sealed service authority has its own independent verifier and host-grant model.
console_service_ir = executable(
    'console-service-ir', 'compiler/console_service_ir.cpp',
    include_directories: include_directories('../compiler'), native: true, install: false,
)
test('console-service-ir', console_service_ir, suite: ['full', 'dev', 'core', 'compiler'], timeout: 120)
console_session = executable('console-session', 'kernel-console-session.cpp', native: true, install: false)
test('console-session', console_session, suite: ['full', 'dev'], timeout: 120)
test('console-service-source-native', python,
     args: ['-B', '-O', files('compiler/console_service.py'), aurorac],
     depends: aurorac, suite: ['full', 'slow', 'core', 'compiler'], env: oracle_env,
     workdir: meson.current_build_dir(), timeout: 300)
test('console-service-admission-controls', python,
     args: ['-B', '-O', files('kernel-console-service-admission.py')],
     suite: ['full', 'dev'], timeout: 120)

# Previously Make-only complete source oracles. Keep exhaustive sweeps in slow.
foreach runner : [
  'templates', 'function_templates', 'function_overloads', 'fixed_containers',
  'composed_values', 'nested_values', 'decimal_values', 'enum_composition',
  'method_values', 'u8_numeric', 'readonly_spans', 'utf8', 'utf8_encoding',
  'integer_oracle', 'unsigned_oracle',
]
  test(runner.replace('_', '-'), python,
       args: ['-B', '-O', files('compiler/' + runner + '.py'), aurorac],
       depends: aurorac, suite: ['full', 'slow', 'compiler'], env: oracle_env,
       workdir: meson.current_build_dir(), timeout: 900, is_parallel: true)
endforeach

# Public Make routing must be exercised by the required developer suite.
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
