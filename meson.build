project(
  'aurora-bootstrap',
  'cpp',
  meson_version: '>=1.12.1',
  default_options: ['cpp_std=c++23', 'warning_level=3', 'werror=true', 'optimization=2', 'debug=false'],
)

# The compiler runs on the build machine, even when a future target is cross-built.
native_cpp = meson.get_compiler('cpp', native: true)
python = find_program('python3', native: true)
# Stage 0 retains the C++ scanner/parser solely as the bootstrap seed/reference.
aurorac_stage0 = executable('aurorac-stage0', 'compiler/main.cpp', native: true, install: false)
frontend_assembly = custom_target(
  'hosted-frontend-assembly',
  input: ['compiler/lexer.au', 'compiler/expression_arena.au', 'compiler/expression_parser.au',
          'compiler/hosted_lexer.S', 'compiler/hosted_parser.S'],
  output: ['hosted-frontend.s', 'hosted-frontend.generated.s'],
  command: [python, '-B', files('scripts/bootstrap_frontend.py'), aurorac_stage0,
            '@INPUT0@', '@INPUT1@', '@INPUT2@', '@INPUT3@', '@INPUT4@', '@OUTPUT0@'],
)
frontend_object = custom_target(
  'hosted-frontend-object', input: frontend_assembly[0], output: 'hosted-frontend.o',
  command: native_cpp.cmd_array() + ['-c', '-x', 'assembler', '@INPUT@', '-o', '@OUTPUT@'],
)
frontend_args = ['-DAURORA_HOSTED_LEXER', '-DAURORA_HOSTED_PARSER']
frontend_library = static_library(
  'hosted-frontend', ['compiler/hosted_lexer.cpp', 'compiler/hosted_parser.cpp',
                      'runtime/hosted_bytes.cpp', frontend_object],
  cpp_args: frontend_args, native: true, install: false,
)
hosted_frontend = declare_dependency(link_with: frontend_library, compile_args: frontend_args)
aurorac = executable('aurorac', 'compiler/main.cpp', dependencies: hosted_frontend, native: true, install: false)
aurora_fmt = executable('aurora-fmt', 'compiler/format_main.cpp', dependencies: hosted_frontend,
                        native: true, install: false)

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

toolchain_args = []
kernel_image_compiler = aurorac
if get_option('kernel_compiler') != ''
  if not get_option('kernel_compiler').startswith('/')
    error('kernel_compiler must be an absolute executable path.')
  endif
  kernel_image_compiler = find_program(get_option('kernel_compiler'), native: true)
endif
if get_option('kernel_images')
  subdir('kernel-images/tools')
  toolchain_args += ['--pe-linker', pe_linker.full_path()]
endif

# The image fixes distributed tools; explicit PATH/CXX also supports comparable
# local tools. Check versions once at setup; Ninja tracks build inputs thereafter.
run_command(python, '-B', files('scripts/meson_toolchain.py'),
            '--cxx', oracle_cxx, toolchain_args, check: true)

# The JSON dependency belongs only to the explicitly enabled language server.
if get_option('lsp')
  lsp_json = dependency('nlohmann_json', version: '>=3.11.3', native: true, required: true)
  aurora_lsp = executable(
    'aurora-lsp', ['compiler/lsp/main.cpp', 'compiler/lsp/check.cpp'],
    dependencies: [lsp_json, hosted_frontend], native: true, install: false,
  )
  lsp_units = executable('lsp-units', 'tests/lsp-units.cpp', dependencies: hosted_frontend,
                         native: true, install: false)
  test('lsp-units', lsp_units, suite: 'lsp', timeout: 30)
  test('lsp-protocol', python, args: ['-B', files('tests/lsp-protocol.py'), aurora_lsp],
       depends: aurora_lsp, suite: 'lsp', timeout: 120)
endif

if get_option('kernel_images')
  subdir('kernel-images')
endif
subdir('tests')
subdir('library/examples')
