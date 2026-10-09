project(
  'aurora-bootstrap',
  'cpp',
  meson_version: '>=1.12.1',
  default_options: ['cpp_std=c++23', 'warning_level=3', 'werror=true', 'optimization=2', 'debug=false'],
)

# The compiler runs on the build machine, even when a future target is cross-built.
native_cpp = meson.get_compiler('cpp', native: true)
python = find_program('python3', native: true)
aurorac = executable('aurorac', 'compiler/main.cpp', native: true, install: false)

# These existing native oracles use Linux/x86-64 syscalls and GNU binutils.
if build_machine.system() != 'linux' or build_machine.cpu_family() != 'x86_64'
  error('The bootstrap test prototype currently requires an x86-64 Linux build machine.')
endif
foreach tool : ['as', 'ld', 'nm', 'objdump']
  find_program(tool, native: true)
endforeach

# Preserve the configured compiler command (including wrappers and quoted paths)
# for the existing Python native observer. This does not build or run a test.
oracle_cxx = run_command(
  python, '-B', '-c', 'import shlex, sys; print(shlex.join(sys.argv[1:]))',
  native_cpp.cmd_array(),
  check: true,
).stdout().strip()

# Fail on in-place toolchain replacement instead of silently keeping old objects.
# This small configuration fingerprint is not a test/qualification receipt.
toolchain_guard = files('scripts/meson_toolchain.py')
toolchain_args = ['-B', toolchain_guard, '--cxx', oracle_cxx,
                  '--record', meson.project_build_root() / 'aurora-toolchain.json']
run_command(python, toolchain_args + ['--configure'], check: true)
custom_target('toolchain-identity-check', output: 'toolchain-identity.stamp',
              command: [python] + toolchain_args + ['--stamp', '@OUTPUT@'],
              build_by_default: true, build_always_stale: true)
test('toolchain-identity', python, args: toolchain_args,
     suite: ['full', 'dev', 'compiler'], timeout: 30)

# The JSON dependency belongs only to the explicitly enabled language server.
if get_option('lsp')
  lsp_json = dependency('nlohmann_json', version: '>=3.11.3', native: true, required: true)
  aurora_lsp = executable(
    'aurora-lsp', ['compiler/lsp/main.cpp', 'compiler/lsp/check.cpp'],
    dependencies: lsp_json, native: true, install: false,
  )
  lsp_units = executable('lsp-units', 'tests/lsp-units.cpp', native: true, install: false)
  test('lsp-units', lsp_units, suite: 'lsp', timeout: 30)
  test('lsp-protocol', python, args: ['-B', files('tests/lsp-protocol.py'), aurora_lsp],
       depends: aurora_lsp, suite: 'lsp', timeout: 120)
endif

subdir('tests')
subdir('library/examples')
