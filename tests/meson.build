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
# dev is the default feedback set; core and bytes select independent sub-suites.
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
    test(
        entry[0],
        python,
        args: ['-B', '-O', files(entry[1]), aurorac],
        depends: aurorac,
        suite: ['dev', entry[2]],
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
    suite: ['dev', 'core', 'compiler'],
    timeout: 120,
)

owned_mutation_ir = executable(
    'owned-mutation-ir',
    'compiler/owned_mutation_ir.cpp',
    include_directories: include_directories('../compiler'),
    native: true,
    install: false,
)
test('owned-mutation-ir', owned_mutation_ir, suite: ['dev', 'core', 'compiler'], timeout: 120)
test(
    'owned-mutation-abi',
    python,
    args: ['-B', '-O', files('compiler/owned_mutation_abi.py'), owned_mutation_ir],
    depends: owned_mutation_ir,
    suite: ['dev', 'core', 'compiler'],
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
test('sector-values-ir', sector_values_ir, suite: ['dev', 'bytes', 'compiler'], timeout: 120)
test(
    'sector-values-abi',
    python,
    args: ['-B', '-O', files('compiler/sector_values_abi.py'), sector_values_ir],
    depends: sector_values_ir,
    suite: ['dev', 'bytes', 'compiler'],
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
        suite: ['dev', 'packages'],
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
test('owned-bytes-ir', owned_bytes_ir, suite: ['dev', 'core', 'compiler'], timeout: 120)
owned_bytes_host = executable(
    'owned-bytes-host', ['compiler/owned_bytes_host.cpp', '../runtime/hosted_bytes.cpp'],
    cpp_args: ['-DAURORA_HOSTED_BYTES_TESTING'], native: true, install: false,
)
test('owned-bytes-host', owned_bytes_host, suite: ['dev', 'core', 'compiler'], timeout: 120)

# Direct owning classes reuse the hosted byte adapter and private value ABI.
owning_classes_ir = executable(
    'owning-classes-ir', 'compiler/owning_classes_ir.cpp',
    include_directories: include_directories('../compiler'), native: true, install: false,
)
test('owning-classes-ir', owning_classes_ir, suite: ['dev', 'core', 'compiler'], timeout: 120)
test(
    'owning-classes-abi', python,
    args: ['-B', '-O', files('compiler/owning_classes_abi.py'), owning_classes_ir],
    depends: owning_classes_ir, suite: ['dev', 'core', 'compiler'],
    env: oracle_env, workdir: meson.current_build_dir(), timeout: 180,
)

# Logical owner views share the established readonly-span source type.
owned_spans_ir = executable(
    'owned-spans-ir', 'compiler/owned_spans_ir.cpp',
    include_directories: include_directories('../compiler'), native: true, install: false,
)
test('owned-spans-ir', owned_spans_ir, suite: ['dev', 'core', 'bytes', 'compiler'], timeout: 120)
test('owned-spans-source', python,
     args: ['-B', '-O', files('compiler/owned_spans_source.py'), aurorac],
     depends: aurorac, suite: ['dev', 'core', 'bytes'], env: oracle_env,
     workdir: meson.current_build_dir(), timeout: 180)
foreach mode : ['standalone', 'receiver']
    span_kernel_args = ['-B', '-O', files('compiler/owned_spans_kernel.py'), aurorac]
    if mode == 'receiver'
        span_kernel_args += ['--receiver-bound']
    endif
    test('owned-spans-kernel-' + mode, python,
         args: span_kernel_args, depends: aurorac, suite: ['dev', 'bytes'],
         env: oracle_env, workdir: meson.current_build_dir(), timeout: 180)
endforeach
# Meson owns compiler dependencies; this records observed artifact stability only.
test(
    'json-profile', python,
    args: ['-B', '-O', files('compiler/json_profile.py'), aurorac, '--developer-selected-compiler'],
    depends: aurorac, suite: ['dev', 'bytes'], env: oracle_env,
    workdir: meson.current_build_dir(), timeout: 300, is_parallel: true,
)

logical_spans_abi = executable(
    'logical-spans-abi', 'compiler/logical_spans_abi.cpp',
    include_directories: include_directories('../compiler'), native: true, install: false,
)
test('logical-spans-abi', python,
     args: ['-B', '-O', files('compiler/logical_spans_abi.py'), logical_spans_abi],
     depends: logical_spans_abi, suite: ['dev', 'core', 'bytes', 'compiler'],
     env: oracle_env, workdir: meson.current_build_dir(), timeout: 180)

# Synchronous method capabilities retain independent IR and literal-layout ABI gates.
method_spans_ir = executable(
    'method-spans-ir', 'compiler/method_spans_ir.cpp',
    include_directories: include_directories('../compiler'), native: true, install: false,
)
test('method-spans-ir', method_spans_ir, suite: ['dev', 'core', 'bytes', 'compiler'], timeout: 120)
method_spans_abi = executable(
    'method-spans-abi', 'compiler/method_spans_abi.cpp',
    include_directories: include_directories('../compiler'), native: true, install: false,
)
test('method-spans-abi', python,
     args: ['-B', '-O', files('compiler/method_spans_abi.py'), method_spans_abi],
     depends: method_spans_abi, suite: ['dev', 'core', 'bytes', 'compiler'],
     env: oracle_env, workdir: meson.current_build_dir(), timeout: 180)
# Single-scalar codecs retain their own independent oracle and hosted composition.
test(
    'json-codecs', python,
    args: ['-B', '-O', files('compiler/json_codecs.py'), aurorac, '--developer-selected-compiler'],
    depends: aurorac, suite: ['dev', 'bytes'], env: oracle_env,
    workdir: meson.current_build_dir(), timeout: 300, is_parallel: true,
)
