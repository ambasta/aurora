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
    ['signed-integers', 'compiler/integers.py', 'core'],
    ['unsigned-integers', 'compiler/unsigned.py', 'core'],
    ['modules', 'modules/run.py', 'core'],
    ['source-depth', 'modules/robustness.py', 'core'],
    ['byte-codec', 'compiler/byte_codec.py', 'bytes'],
    ['binary-writer', 'compiler/binary_writer.py', 'bytes'],
    ['block-value', 'compiler/block_value.py', 'bytes'],
    ['ram-blocks', 'compiler/ram_blocks.py', 'bytes'],
    ['owned-sector', 'compiler/sector.py', 'bytes'],
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
