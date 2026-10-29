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
frontend_modules = files('compiler/formatter.au', 'compiler/lexer.au', 'compiler/syntax_arena.au', 'compiler/parser.au',
                        'compiler/resolution_kinds.au', 'compiler/lowering_errors.au', 'compiler/lowering_kinds.au',
                        'compiler/lowering_storage.au', 'compiler/resolution_rows.au', 'compiler/resolution_arena.au',
                        'compiler/resolution_names.au', 'compiler/resolution_linkage.au',
                        'compiler/resolution_ingest.au', 'compiler/diagnostics.au', 'compiler/builtin_catalog.au',
                        'compiler/resolver.au', 'compiler/lowering_messages.au',
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
                        'compiler/ir_listing.au', 'compiler/pipeline_declarations.au', 'compiler/pipeline.au',
                        )
# The bridge table the C++ test drivers' graph is generated from (tests/air).
bridge_table = files('scripts/frontend_bridge.py')

# The compiler is one hosted Aurora program, compiler/aurorac.au (configured
# with its runtime root) over the compiler modules; run as aurora-fmt it is the
# formatter. C0 compiles C1 (aurorac), C1 compiles C2 (aurorac-stage2) and C2
# compiles the object hosted-lexer-bootstrap compares with C1's (GCC's stage
# compare). Every stage compiles with this tree's runtime root (runtime/linux:
# aurora.host and aurora.memory) and links with ld alone: no C or C++ objects,
# startup or libc.
hosted_runtime_root = meson.current_source_dir() / 'runtime/linux'
kernel_runtime_root = meson.current_source_dir() / 'runtime/aurora'
if hosted_runtime_root.contains('"') or hosted_runtime_root.contains('\\') or kernel_runtime_root.contains('"')
  error('aurorac embeds its runtime root as a byte string: the source path must not contain " or a backslash.')
endif
hosted_runtime_sources = files('runtime/linux/aurora/host.au', 'runtime/linux/aurora/memory.au')
# --target aurora's runtime root: programs for the Aurora kernel's process image.
kernel_runtime_sources = files('runtime/aurora/aurora/host.au')
hosted_linker = find_program('ld', native: true)
compiler_driver = configure_file(input: 'compiler/aurorac.au', output: 'aurorac.au',
                                 configuration: {'AURORA_RUNTIME_ROOT': hosted_runtime_root,
                                                 'AURORA_KERNEL_RUNTIME_ROOT': kernel_runtime_root})
compiler_stage = [python, '-B', files('scripts/bootstrap_frontend.py')]
compiler_link = [hosted_linker, '-static', '-e', '_start', '-o', '@OUTPUT@', '@INPUT@']

# The first compiler. From source, GCC builds aurora-seed, an interpreter of
# the Aurora subset the compiler is written in (compiler/seed); it runs
# aurorac.au on the compiler's sources to emit X, the object of the current
# compiler, and C1 (aurorac) is X linked. seed-bootstrap requires the object C1
# emits of the compiler to equal X: GCC's stage compare, one stage early.
# -Dbootstrap_compiler names a cached C0 instead, as the merge loop does: any
# aurorac that compiles these sources. C0 compiles C1, C1 compiles C2, and
# hosted-lexer-bootstrap requires C1 and C2 to agree; seed-bootstrap (release
# suite) still requires X to equal C1's object. Ninja tracks the C0 executable.
aurora_seed = executable('aurora-seed', 'compiler/seed/seed.cpp', 'compiler/seed/syntax.cpp', native: true,
                         install: false, build_by_default: false, override_options: ['optimization=1'])
aurorac_seed_object = custom_target(
  'aurorac-seed-object', input: [compiler_driver] + frontend_modules, output: 'aurorac-seed.o',
  command: compiler_stage + [aurora_seed, '--seed', '--program', hosted_runtime_root, '--output', '@OUTPUT@',
                             '@INPUT@'],
  depend_files: hosted_runtime_sources, build_by_default: false,
)
from_seed = get_option('bootstrap_compiler') == ''
if from_seed
  aurorac_object = aurorac_seed_object
else
  if not fs.is_absolute(get_option('bootstrap_compiler'))
    error('bootstrap_compiler must be the absolute path of a cached aurorac; leave it empty to build one with ' +
          'aurora-seed (compiler/README.md#source-bootstrap)')
  endif
  bootstrap_compiler = find_program(get_option('bootstrap_compiler'), native: true)
  aurorac_object = custom_target(
    'aurorac-object', input: [compiler_driver] + frontend_modules, output: 'aurorac.o',
    command: compiler_stage + [bootstrap_compiler, '--program', hosted_runtime_root, '--output', '@OUTPUT@',
                               '@INPUT@'],
    depend_files: files(get_option('bootstrap_compiler')) + hosted_runtime_sources,
  )
endif
aurorac = custom_target('aurorac', input: aurorac_object, output: 'aurorac', command: compiler_link,
                        build_by_default: true)
aurora_fmt = custom_target('aurora-fmt', input: aurorac_object, output: 'aurora-fmt', command: compiler_link,
                           build_by_default: true)
# These stages stay outside the default build unless a stage compare is selected;
# a seed build needs no third stage.
aurorac_stage2_object = custom_target(
  'aurorac-stage2-object', input: [compiler_driver] + frontend_modules, output: 'aurorac-stage2.o',
  command: compiler_stage + [aurorac, '--program', hosted_runtime_root, '--output', '@OUTPUT@', '@INPUT@'],
  depend_files: hosted_runtime_sources, build_by_default: false,
)
aurorac_stage2 = custom_target('aurorac-stage2', input: aurorac_stage2_object, output: 'aurorac-stage2',
                               command: compiler_link, build_by_default: false)
if not from_seed
  aurorac_stage3_object = custom_target(
    'aurorac-stage3-object', input: [compiler_driver] + frontend_modules, output: 'aurorac-stage3.o',
    command: compiler_stage + [aurorac_stage2, '--program', hosted_runtime_root, '--output', '@OUTPUT@', '@INPUT@'],
    depend_files: hosted_runtime_sources, build_by_default: false,
  )
endif

# These existing native oracles use Linux/x86-64 syscalls and GNU binutils.
if build_machine.system() != 'linux' or build_machine.cpu_family() != 'x86_64'
  error('The bootstrap test prototype currently requires an x86-64 Linux build machine.')
endif
foreach tool : ['as', 'ld', 'nm', 'objdump', 'objcopy']
  find_program(tool, native: true)
endforeach

# Hosted Aurora programs: a root main(builtin::HostFiles&, builtin::span<const u8>)
# -> builtin::HostExit gets a compiler-emitted _start and links like aurorac.
hosted_programs = {}
foreach name, source : {'host-files-cat': 'examples/host-files-cat.au',
                        'host-files-probe': 'tests/host-files/probe.au',
                        'host-sort': 'examples/host-sort.au',
                        'host-memory-probe': 'tests/host-files/memory.au',
                        'seed-semantics': 'tests/seed/semantics.au'}
  hosted_object = custom_target(name + '-object', input: source, output: name + '.o',
      command: [aurorac, '--emit-object', '@INPUT@', '-o', '@OUTPUT@'],
      depend_files: hosted_runtime_sources)
  hosted_programs += {name: custom_target(name, input: hosted_object, output: name, command: compiler_link)}
endforeach

# Programs for the Aurora kernel's process image (kernel/uefi/process.md#guest-rows):
# --target aurora objects linked like the hosted programs, and one GNU as program.
process_programs = {}
if get_option('kernel_images')
  foreach name, source : {'host-files-probe': 'tests/host-files/probe.au',
                          'process-hostile': 'tests/kernel-process/hostile.au'}
    process_object = custom_target(name + '-aurora-object', input: source, output: name + '-aurora.o',
        command: [aurorac, '--emit-object', '--target', 'aurora', '@INPUT@', '-o', '@OUTPUT@'],
        depend_files: kernel_runtime_sources)
    process_programs += {'aurora:' + name: custom_target(name + '-aurora', input: process_object,
                                                         output: name + '-aurora', command: compiler_link)}
  endforeach
  recurse_object = custom_target('process-recurse-object', input: 'tests/kernel-process/recurse.S',
      output: 'process-recurse.o', command: [find_program('as', native: true), '--64', '-mx86-used-note=no',
                                             '@INPUT@', '-o', '@OUTPUT@'])
  process_programs += {'assembly:process-recurse': custom_target('process-recurse', input: recurse_object,
                                                                 output: 'process-recurse', command: compiler_link)}
  foreach name, program : hosted_programs
    process_programs += {'linux:' + name: program}
  endforeach
endif

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

if get_option('kernel_images')
  subdir('kernel-images')
endif
subdir('tests')
subdir('library/examples')

# The optional language server, a separate C++ tool over the bridged test
# graph (tests/air); the JSON dependency belongs only to it.
if get_option('lsp')
  lsp_json = dependency('nlohmann_json', version: '>=3.11.3', native: true, required: true)
  aurora_lsp = executable(
    'aurora-lsp', ['compiler/lsp/main.cpp', 'compiler/lsp/check.cpp'],
    dependencies: [lsp_json, air_frontend_dep], native: true, install: false,
  )
  lsp_units = executable('lsp-units', 'tests/lsp-units.cpp', native: true, install: false)
  test('lsp-units', lsp_units, suite: 'lsp', timeout: 30)
  test('lsp-protocol', python, args: ['-B', files('tests/lsp-protocol.py'), aurora_lsp],
       depends: aurora_lsp, suite: 'lsp', timeout: 120)
endif
