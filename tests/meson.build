# Each existing runner creates a unique TemporaryDirectory beneath this build
# directory. Parallel tests never write to the source tree or another build tree.
oracle_env = environment()
oracle_env.set('TMPDIR', meson.current_build_dir())
oracle_env.set('PYTHONDONTWRITEBYTECODE', '1')
oracle_env.set('CXX', oracle_cxx)

foreach entry : [
  ['byte-codec', 'compiler/byte_codec.py'],
  ['packed-values', 'compiler/packed_values.py'],
  ['storage-binary', 'compiler/storage_binary.py'],
]
  test(
    entry[0],
    python,
    args: ['-B', '-O', files(entry[1]), aurorac],
    depends: aurorac,
    suite: 'bytes',
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
test('initialization-facts', initialization_facts, suite: 'compiler', timeout: 120)
