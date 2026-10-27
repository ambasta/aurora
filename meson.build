project(
  'aurora-bootstrap',
  'cpp',
  meson_version: '>=1.12.1',
  default_options: ['cpp_std=c++23', 'warning_level=3', 'werror=true', 'optimization=2', 'debug=false'],
)

# The compiler runs on the build machine, even when a future target is cross-built.
native_cpp = meson.get_compiler('cpp', native: true)
python = find_program('python3', native: true)
fs = import('fs')
# compiler/checkpoint.json names the checkpoint (C0) by source commit; any C0
# built from it compiles C1, C1 compiles C2, and hosted-lexer-bootstrap requires
# C1 and C2 to agree (GCC's stage compare). Ninja tracks the C0 executable.
bootstrap_driver = files('scripts/bootstrap.py')
bootstrap_pin = files('compiler/checkpoint.json')
bootstrap_select = run_command(python, '-B', bootstrap_driver, 'select',
                               '--compiler', get_option('bootstrap_compiler'), check: false)
if bootstrap_select.returncode() != 0
  error(bootstrap_select.stderr().strip())
endif
fs.read(bootstrap_pin)
bootstrap_compiler_path = bootstrap_select.stdout().strip()
bootstrap_compiler = find_program(bootstrap_compiler_path, native: true)
bootstrap_depend_files = files(bootstrap_compiler_path) + bootstrap_driver + bootstrap_pin
frontend_inputs = files('compiler/formatter.au', 'compiler/lexer.au', 'compiler/syntax_arena.au', 'compiler/parser.au',
                        'compiler/resolution_kinds.au', 'compiler/lowering_errors.au', 'compiler/lowering_kinds.au',
                        'compiler/lowering_storage.au', 'compiler/resolution_rows.au', 'compiler/resolution_arena.au',
                        'compiler/resolution_names.au', 'compiler/resolution_linkage.au',
                        'compiler/resolution_ingest.au', 'compiler/builtin_catalog.au', 'compiler/resolver.au',
                        'compiler/ir_graph.au',
                        'compiler/ir_metadata_storage.au', 'compiler/ir_metadata.au',
                        'compiler/ir_instruction_storage.au', 'compiler/ir_instructions.au',
                        'compiler/ir_verification_errors.au', 'compiler/ir_verification_storage.au',
                        'compiler/ir_verification_initialization.au', 'compiler/ir_verification_common.au',
                        'compiler/ir_verification_values.au', 'compiler/ir_verification_resources.au',
                        'compiler/ir_verification_services.au', 'compiler/ir_verification_transfer.au',
                        'compiler/ir_verification.au',
                        'compiler/x86_storage.au', 'compiler/x86_object_storage.au',
                        'compiler/x86_helpers.au', 'compiler/x86_scalar.au',
                        'compiler/x86_objects.au', 'compiler/x86_resources.au', 'compiler/x86_facts.au',
                        'compiler/x86_module.au', 'compiler/private_object.au', 'compiler/frontend_wrapper.au',
                        'library/std/decimal_digits.au', 'library/std/binary.au',
                        'compiler/lowering_common.au', 'compiler/lowering_configuration.au',
                        'compiler/lowering_types.au', 'compiler/lowering_values.au', 'compiler/lowering_frames.au',
                        'compiler/lowering_calls.au', 'compiler/lowering_expressions.au',
                        'compiler/lowering_statements.au', 'compiler/lowering_body.au', 'compiler/lowering.au',
                        'compiler/lowering_projection_storage.au', 'compiler/lowering_projection_identity.au',
                        'compiler/lowering_projection_common.au', 'compiler/lowering_projection_instructions.au',
                        'compiler/lowering_projection.au',
                        )
frontend_forwarders = custom_target(
  'frontend-forwarders', input: 'compiler/frontend.au', output: 'frontend.au',
  command: [python, '-B', files('scripts/frontend_bridge.py'), '@INPUT@', '@OUTPUT@'],
)
frontend_inputs += [frontend_forwarders]
bridge_table = files('scripts/frontend_bridge.py')

frontend_assembly = custom_target(
  'hosted-frontend-assembly', input: frontend_inputs,
  output: ['hosted-frontend.s', 'hosted-frontend.generated.s', 'hosted-frontend.abi.json', 'hosted_frontend_abi.hpp'],
  command: [python, '-B', files('scripts/bootstrap_frontend.py'), bootstrap_compiler,
            '--output-mode', 'text', '--output', '@OUTPUT0@', '@INPUT@'],
  depend_files: bootstrap_depend_files + bridge_table,
)
frontend_object = custom_target(
  'hosted-frontend-object', input: frontend_assembly[0], output: 'hosted-frontend.o',
  command: native_cpp.cmd_array() + ['-c', '-x', 'assembler', '@INPUT@', '-o', '@OUTPUT@'],
)
frontend_args = ['-DAURORA_HOSTED_LEXER', '-DAURORA_HOSTED_PARSER']
# The parser-through-IR adapters; hosted-parser-invalid links these objects alone.
frontend_adapter_sources = files('compiler/hosted_parser.cpp', 'compiler/hosted_resolver.cpp',
                                 'compiler/hosted_lowering.cpp', 'compiler/hosted_lowering_diagnostics.cpp',
                                 'compiler/hosted_ir_metadata.cpp', 'compiler/hosted_ir_instructions.cpp',
                                 'compiler/ir_verify.cpp', 'runtime/hosted_bytes.cpp')
frontend_host_sources = frontend_adapter_sources + files('compiler/hosted_lexer.cpp', 'compiler/hosted_graph.cpp',
                                                         'compiler/hosted_x86.cpp', 'compiler/hosted_private_object.cpp')
frontend_library = static_library(
  'hosted-frontend', [frontend_host_sources, frontend_object, frontend_assembly[3]],
  cpp_args: frontend_args, native: true, install: false,
)
# Operator enums are source-defined. Header-only IR consumers need the generated
# declarations; every executable calling validate also links hosted_frontend.
frontend_headers = declare_dependency(sources: frontend_assembly[3],
                                     include_directories: include_directories('.'))
hosted_frontend = declare_dependency(link_with: frontend_library, dependencies: frontend_headers,
                                   compile_args: frontend_args)
aurorac = executable('aurorac', 'compiler/main.cpp', dependencies: hosted_frontend, native: true, install: false)
aurora_fmt = executable('aurora-fmt', 'compiler/format_main.cpp', dependencies: hosted_frontend,
                        native: true, install: false)

# C0 emits text frontend A; C1 emits direct-object B, which current C2 links.
# Reuse only current host C++ objects. The old checkpoint needs no object support.
# These prerequisites stay outside the default build unless the test is selected.
frontend_stage2_output = custom_target(
  'hosted-frontend-stage2-output', input: frontend_inputs + [frontend_assembly[3]],
  output: ['hosted-frontend-stage2.o', 'hosted-frontend-stage2.generated.o',
           'hosted-frontend-stage2.abi.json', 'hosted_frontend_stage2_abi.hpp',
           'hosted-frontend-stage2.stack.json'],
  command: [python, '-B', files('scripts/bootstrap_frontend.py'), aurorac,
            '--output-mode', 'object', '--output', '@OUTPUT0@', '@INPUT@'],
  depend_files: bridge_table,
  build_by_default: false,
)
frontend_stage2_library = static_library(
  'hosted-frontend-stage2', frontend_stage2_output[0],
  objects: frontend_library.extract_objects(frontend_host_sources),
  native: true, install: false, build_by_default: false,
)
aurorac_stage2 = executable(
  'aurorac-stage2', objects: aurorac.extract_objects('compiler/main.cpp'),
  link_with: frontend_stage2_library, link_language: 'cpp',
  native: true, install: false, build_by_default: false,
)
# C2 emits frontend C; hosted-lexer-bootstrap compares it with B (stage compare).
frontend_stage3_output = custom_target(
  'hosted-frontend-stage3-output', input: frontend_inputs + [frontend_assembly[3]],
  output: ['hosted-frontend-stage3.o', 'hosted-frontend-stage3.generated.o',
           'hosted-frontend-stage3.abi.json', 'hosted_frontend_stage3_abi.hpp',
           'hosted-frontend-stage3.stack.json'],
  command: [python, '-B', files('scripts/bootstrap_frontend.py'), aurorac_stage2,
            '--output-mode', 'object', '--output', '@OUTPUT0@', '@INPUT@'],
  depend_files: bridge_table,
  build_by_default: false,
)

# These existing native oracles use Linux/x86-64 syscalls and GNU binutils.
if build_machine.system() != 'linux' or build_machine.cpu_family() != 'x86_64'
  error('The bootstrap test prototype currently requires an x86-64 Linux build machine.')
endif
foreach tool : ['as', 'ld', 'nm', 'objdump', 'objcopy']
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

# The supported container fixes exact tool versions; advanced native runs must
# match those pinned tools via PATH/CXX. Check once at setup; Ninja tracks inputs.
toolchain_check = run_command(python, '-B', files('scripts/meson_toolchain.py'),
                              '--cxx', oracle_cxx, toolchain_args, check: false)
if toolchain_check.returncode() != 0
  diagnostic = toolchain_check.stderr().strip()
  if diagnostic == ''
    diagnostic = 'BLOCKED: Development toolchain check failed (exit @0@).'.format(toolchain_check.returncode())
  endif
  error(diagnostic + '\nUse ./scripts/container.sh make test for the supported pinned environment; see docs/local-development.md.')
endif

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
