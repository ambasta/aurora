kernel_source = meson.project_source_root()
kernel_assembly_helper = files('../scripts/meson_aurora_assembly.py')
kernel_object_helper = files('../scripts/meson_kernel_object.py')
# b_ndebug avoids Meson's hosted libstdc++ assertions; -UNDEBUG then restores
# the original freestanding preprocessor state instead of defining NDEBUG.
kernel_flags = [
    '-Wall',
    '-Wextra',
    '-Werror',
    '-ffreestanding',
    '-fcf-protection=none',
    '-mstringop-strategy=libcall',
    '-fno-exceptions',
    '-fno-rtti',
    '-fno-stack-protector',
    '-fno-asynchronous-unwind-tables',
    '-fno-unwind-tables',
    '-mno-red-zone',
    '-mgeneral-regs-only',
    '-fno-tree-loop-distribute-patterns',
]
kernel_options = {
    'cpp_std': 'c++23',
    'optimization': '2',
    'debug': false,
    'warning_level': '0',
    'werror': false,
    'cpp_debugstl': false,
    'b_lto': false,
    'b_sanitize': 'none',
    'b_pch': false,
    'b_coverage': false,
    'b_pgo': 'off',
    'b_ndebug': 'true',
    'b_pie': false,
    'unity': 'off',
}

# One canonical data catalog is shared with the command selectors. All generated
# metadata below is build-local; only the two normal images are default products.
profile_file = configure_file(
  input: ['../scripts/kernel_profiles.py', '../scripts/kernel_layout.py', '../kernel/bootstrap-layout-values.inc',
         '../kernel/uefi/image-page-policies.inc', '../kernel/uefi/runtime-fixtures.inc'],
  output: 'profile-data.ini',
  command: [python, '-B', '@INPUT0@', '--meson-output', '@OUTPUT@'])
profile_data = import('keyval').load(profile_file)
kernel_profile_images = {}
kernel_profile_users = {}
# Reuse identical user compiler products within this configured graph. Keep local
# artifact paths and every per-image link/embedding edge below.
kernel_user_assemblies = {}
kernel_copy = find_program('cp', native: true)
# Whole-image build checks (objtool/modpost-like); see the scripts' docstrings.
image_check = files('../scripts/kernel_image_check.py')
stack_check = files('../scripts/kernel_stack_check.py')
image_policy = files('image-policy.py')
check_dependencies = files('../scripts/kernel_elf.py')
stack_limit = profile_data['layout.stack_cap']
foreach profile_id : profile_data['profiles'].split('|')
  key = 'profiles.' + profile_id
  platform = profile_data[key + '.platform']
  mode = profile_data[key + '.mode']
  prefix = platform + '-' + mode
  output_subdir = platform / mode
  output_dir = meson.current_build_dir() / output_subdir
  include_dir = 'kernel-images' / output_subdir
  object_subdir = platform == 'uefi' ? output_subdir / 'objects' : output_subdir
  flag_text = profile_data[key + '.flags']
  profile_flags = flag_text == '' ? [] : flag_text.split('|')
  compiler_files = get_option('kernel_compiler') == '' ? [] : files(get_option('kernel_compiler'))
  objects = {}
  bios_console = platform == 'bios' and mode == 'console'
  uefi_console = platform == 'uefi' and mode == 'device-fixture'
  # Closed objects (the protected supervisor, the scratchpad and the packed test
  # images that compose them) keep local symbols and referenced reflection only.
  sealed = profile_data[key + '.sealed'] == '1'
  stack_facts = []
  language_objects = []
  user_stack_args = []

  root_args = []
  foreach root : profile_data[key + '.roots'].split('|')
    root_args += ['--module-root', kernel_source / root]
  endforeach
  # Closed supervisors and the ordinary UEFI console expose only their bridges.
  if sealed or uefi_console
    root_args += ['--referenced-reflection-only', '--local-symbols']
  endif
  bridge = profile_data[key + '.bridge']
  bridge_input = bridge == '' ? [] : files('../' + bridge)
  language_outputs = [platform == 'bios' ? 'kernel-language.s' : 'language.s',
                      platform == 'bios' ? 'kernel-language.stack.json' : 'language.stack.json']
  language_dependencies = compiler_files
  if sealed or bios_console or uefi_console
    language_outputs += [bios_console ? 'kernel-language.abi.json' : 'language.abi.json']
    root_args += ['--abi-facts', '@OUTPUT2@', '--bridge', kernel_source / bridge]
    language_dependencies += bridge_input + files('../scripts/bootstrap_frontend.py')
    if sealed
      root_args += ['--bridge', kernel_source / 'kernel/uefi/kernel-policy-entry.S']
      language_dependencies += files('../kernel/uefi/kernel-policy-entry.S')
    endif
    bridge_input = []
  endif
  language_name = platform == 'bios' ? 'kernel-language' : 'language'
  if uefi_console
    # Aurora composes the ordinary UEFI session object and its GNU-as adapter;
    # the source definitions stay LOCAL and the final image still uses GNU ld.
    language = custom_target(prefix + '-language-object',
      input: files('../' + profile_data[key + '.language']),
      output: ['language.o', 'language.stack.json', 'language.abi.json'],
      build_subdir: object_subdir, depfile: language_name + '.d', depend_files: language_dependencies,
      command: [python, '-B', kernel_assembly_helper, '--compiler', kernel_image_compiler, '--source', '@INPUT@',
                '--output', '@OUTPUT0@', '--stack-facts', '@OUTPUT1@', '--depfile', '@DEPFILE@',
                '--emit-object', '--assembler', kernel_as] + root_args)
    objects += {language_name: language}
  else
    language = custom_target(prefix + '-language-assembly',
      input: files('../' + profile_data[key + '.language']), output: language_outputs,
      build_subdir: output_subdir, depfile: language_name + '.d', depend_files: language_dependencies,
      command: [python, '-B', kernel_assembly_helper, '--compiler', kernel_image_compiler, '--source', '@INPUT@',
                '--output', '@OUTPUT0@', '--stack-facts', '@OUTPUT1@', '--depfile', '@DEPFILE@'] + root_args)
    # Private local symbols require the bridge and generated source in ONE as command.
    objects += {language_name: custom_target(prefix + '-language-object',
      input: [language[0]] + bridge_input, output: language_name + '.o', build_subdir: object_subdir,
      command: [kernel_as, '--64', '@INPUT@', '-o', '@OUTPUT@'])}
  endif
  stack_facts += [language[1]]
  language_objects += [objects[language_name][0]]
  # Further closed Aurora objects: the production terminal painter and the
  # services the display and device fixture images co-host, each with its own
  # private bridge (rendered from its compiler facts) and import policy.
  extra_languages = profile_data[key + '.languages']
  if extra_languages != ''
    foreach stem : extra_languages.split('|')
      extra_key = key + '.languages.' + stem
      extra_bridge = profile_data[extra_key + '.bridge']
      extra_roots = []
      foreach root : profile_data[extra_key + '.roots'].split('|')
        extra_roots += ['--module-root', kernel_source / root]
      endforeach
      if stem == 'terminal'
        # The production painter fits the checked direct-object profile. Only
        # its existing private adapter is assembled; Aurora preserves LOCALs.
        extra_language = custom_target(prefix + '-' + stem + '-object',
          input: files('../' + profile_data[extra_key + '.source']),
          output: [stem + '.o', stem + '.stack.json', stem + '.abi.json'],
          build_subdir: object_subdir, depfile: stem + '.d',
          depend_files: compiler_files + files('../' + extra_bridge, '../scripts/bootstrap_frontend.py'),
          command: [python, '-B', kernel_assembly_helper, '--compiler', kernel_image_compiler, '--source', '@INPUT@',
                    '--output', '@OUTPUT0@', '--stack-facts', '@OUTPUT1@', '--abi-facts', '@OUTPUT2@',
                    '--depfile', '@DEPFILE@'] + extra_roots + ['--local-symbols', '--referenced-reflection-only',
                    '--emit-object', '--assembler', kernel_as,
                    '--bridge', kernel_source / extra_bridge])
        objects += {stem: extra_language}
      else
        extra_language = custom_target(prefix + '-' + stem + '-assembly',
          input: files('../' + profile_data[extra_key + '.source']),
          output: [stem + '.s', stem + '.stack.json', stem + '.abi.json'],
          build_subdir: output_subdir, depfile: stem + '.d',
          depend_files: compiler_files + files('../' + extra_bridge, '../scripts/bootstrap_frontend.py'),
          command: [python, '-B', kernel_assembly_helper, '--compiler', kernel_image_compiler, '--source', '@INPUT@',
                    '--output', '@OUTPUT0@', '--stack-facts', '@OUTPUT1@', '--abi-facts', '@OUTPUT2@',
                    '--depfile', '@DEPFILE@'] + extra_roots + ['--local-symbols', '--referenced-reflection-only',
                    '--bridge', kernel_source / extra_bridge])
        objects += {stem: custom_target(prefix + '-' + stem + '-object',
          input: extra_language[0], output: stem + '.o', build_subdir: object_subdir,
          command: [kernel_as, '--64', '@INPUT@', '-o', '@OUTPUT@'])}
      endif
      stack_facts += [extra_language[1]]
      language_objects += [objects[stem][0]]
    endforeach
  endif
  if bios_console or uefi_console
    uart_object = custom_target(prefix + '-uart-object',
      input: files('../examples/kernel-uart.au'),
      output: ['kernel-uart.o', 'kernel-uart.stack.json', 'kernel-uart.abi.json'],
      build_subdir: object_subdir, depfile: 'kernel-uart.d',
      depend_files: compiler_files + files('../kernel/uart-policy-entry.S', '../scripts/bootstrap_frontend.py'),
      command: [python, '-B', kernel_assembly_helper, '--compiler', kernel_image_compiler, '--source', '@INPUT@',
                '--output', '@OUTPUT0@', '--stack-facts', '@OUTPUT1@', '--abi-facts', '@OUTPUT2@',
                '--depfile', '@DEPFILE@', '--module-root', kernel_source / 'kernel/policies',
                '--local-symbols', '--referenced-reflection-only', '--emit-object',
                '--assembler', kernel_as,
                '--bridge', kernel_source / 'kernel/uart-policy-entry.S'])
    stack_facts += [uart_object[1]]
    objects += {'kernel-uart': uart_object}
    language_objects += [uart_object[0]]
  endif
  foreach name : profile_data[key + '.assembly'].split('|')
    assembly_key = key + '.assembly.' + name
    objects += {name: custom_target(prefix + '-' + name + '-object',
      input: files('../' + profile_data[assembly_key + '.source']), output: name + '.o',
      build_subdir: object_subdir,
      command: [kernel_as] + profile_data[assembly_key + '.flags'].split('|') + ['@INPUT@', '-o', '@OUTPUT@'])}
  endforeach
  if platform == 'bios'
    boot = custom_target(prefix + '-boot', input: objects['boot'], output: 'boot.bin',
      build_subdir: output_subdir, depend_files: files('../kernel/boot.ld'),
      command: [kernel_ld, '-m', 'elf_i386', '--build-id=none', '--orphan-handling=error', '-T',
                files('../kernel/boot.ld'), '@INPUT@', '-o', '@OUTPUT@'])
  endif

  # Per-program compile, combined private bridge, adapter, link and binary edges.
  user_names = profile_data[key + '.users']
  generated_headers = []
  user_inputs = []
  user_options = []
  if user_names != ''
    foreach name : user_names.split('|')
      user_key = key + '.users.' + name
      user_root_args = []
      foreach root : profile_data[user_key + '.roots'].split('|')
        user_root_args += ['--module-root', kernel_source / root]
      endforeach
      entry_source = files('../' + profile_data[user_key + '.entry'])
      combined = profile_data[user_key + '.combined'] == '1'
      # Per-image options from the catalog: closed callers, owned text and RAM
      # file images have independently checked linked graphs (ABI facts).
      owned_text = profile_data[user_key + '.byte_stubs'] == '1'
      user_abi = profile_data[user_key + '.abi'] == '1'
      if profile_data[user_key + '.reflection_only'] == '1'
        user_root_args += ['--referenced-reflection-only']
      endif
      if profile_data[user_key + '.local_symbols'] == '1'
        user_root_args += ['--local-symbols']
      endif
      user_outputs = ['user-' + name + '.s', 'user-' + name + '.stack.json']
      user_dependencies = compiler_files
      if user_abi
        user_outputs += ['user-' + name + '.abi.json']
        user_root_args += ['--abi-facts', '@OUTPUT2@']
        if combined
          user_root_args += ['--bridge', kernel_source / profile_data[user_key + '.entry']]
          user_dependencies += entry_source + files('../scripts/bootstrap_frontend.py')
          entry_source = []
        endif
      endif
      entry_flags_text = profile_data[user_key + '.entry_flags']
      entry_flags = entry_flags_text == '' ? [] : entry_flags_text.split('|')
      # Same source and ordered module roots imply the same resolved closure;
      # the canonical producer's depfile tracks every imported source. All
      # producers also share kernel_image_compiler and kernel_assembly_helper.
      # Include the complete user recipe, not just its source: private bridge,
      # sidecars/compiler options, entry flags, fixed linker script and layout.
      user_recipe = '\n'.join([
        platform, profile_data[user_key + '.source'], profile_data[user_key + '.roots'],
        profile_data[user_key + '.entry'], profile_data[user_key + '.combined'], entry_flags_text,
        profile_data[user_key + '.base'], profile_data.get(user_key + '.max_pages', ''),
        'kernel/program.ld', '|'.join(user_root_args), '|'.join(user_outputs),
        owned_text ? 'owned-bytes-stubs' : '',
      ])
      if user_recipe in kernel_user_assemblies
        user_assembly = custom_target(prefix + '-user-' + name + '-assembly',
          input: kernel_user_assemblies[user_recipe], output: user_outputs, build_subdir: output_subdir,
          command: [kernel_copy, '--', '@INPUT@', output_dir])
      else
        user_assembly = custom_target(prefix + '-user-' + name + '-assembly',
          input: files('../' + profile_data[user_key + '.source']), output: user_outputs,
          build_subdir: output_subdir, depfile: 'user-' + name + '.d', depend_files: user_dependencies,
          command: [python, '-B', kernel_assembly_helper, '--compiler', kernel_image_compiler, '--source', '@INPUT@',
                    '--output', '@OUTPUT0@', '--stack-facts', '@OUTPUT1@', '--depfile', '@DEPFILE@'] + user_root_args)
        kernel_user_assemblies += {user_recipe: user_assembly}
      endif
      user_facts = [user_assembly[1]] + (user_abi ? [user_assembly[2]] : [])
      byte_stubs = owned_text ? files('../kernel/uefi/owned-bytes-stubs.inc') : []
      user_object = custom_target(prefix + '-user-' + name + '-object',
        input: [user_assembly[0]] + (combined ? entry_source : []), output: 'user-' + name + '.o',
        build_subdir: object_subdir, depend_files: byte_stubs,
        command: [kernel_as, '--64', '-L', '-I', kernel_source / 'kernel/uefi'] + (combined ? entry_flags : []) + ['@INPUT@', '-o', '@OUTPUT@'])
      user_link_inputs = []
      if not combined
        entry_object = custom_target(prefix + '-user-' + name + '-entry-object',
          input: entry_source, output: 'user-' + name + '-entry.o', build_subdir: object_subdir,
                command: [kernel_as, '--64'] + entry_flags + ['@INPUT@', '-o', '@OUTPUT@'])
        user_link_inputs += [entry_object]
      endif
      user_link_inputs += [user_object]
      user_link_flags = platform == 'bios' ? ['-z', 'max-page-size=0x1000', '-T', files('../kernel/program.ld'),
        '--defsym=USER_BASE=' + profile_data[user_key + '.base']] : ['-T', files('../kernel/program.ld'),
        '--defsym', 'USER_BASE=' + profile_data[user_key + '.base'], '-z', 'max-page-size=0x1000']
      if platform == 'uefi'
        user_link_flags += ['--defsym=USER_IMAGE_PAGES=' + profile_data[user_key + '.max_pages']]
      endif
      user_elf = custom_target(prefix + '-user-' + name + '-elf', input: user_link_inputs,
        output: 'user-' + name + '.elf', build_subdir: output_subdir,
        depend_files: files('../kernel/program.ld'),
        command: [kernel_ld, '-nostdlib', '--discard-none'] + user_link_flags + ['@INPUT@', '-o', '@OUTPUT@'])
      user_binary = custom_target(prefix + '-user-' + name + '-binary', input: user_elf,
        output: 'user-' + name + '.bin', build_subdir: output_subdir,
        command: [kernel_objcopy, '-O', 'binary', '@INPUT@', '@OUTPUT@'])
      user_inputs += [user_elf, user_binary] + user_facts
      user_stack_args += ['--user', user_elf.full_path(), '--facts', user_assembly[1].full_path()]
    endforeach
    if platform == 'bios'
      user_metadata = custom_target(prefix + '-user-metadata', input: user_inputs,
        output: ['user-metadata.json', 'kernel-user-images.S', 'kernel-user-images.hpp'],
        build_subdir: output_subdir,
        command: [python, '-B', files('../tests/kernel-user-image.py'), '--build-dir', output_dir] +
                 profile_data[key + '.user_metadata_options'].split('|'))
      generated_headers = [user_metadata[2]]
      objects += {'kernel-user-images': custom_target(prefix + '-user-images-object', input: user_metadata[1],
        output: 'kernel-user-images.o', build_subdir: object_subdir, depends: user_inputs,
        command: [kernel_as, '--64', '@INPUT@', '-o', '@OUTPUT@'])}
    else
      user_option_text = profile_data[key + '.user_options']
      user_options = user_option_text == '' ? [] : user_option_text.split('|')
      # A user image bank also names the images each selected mode runs.
      user_metadata = custom_target(prefix + '-user-metadata', input: user_inputs,
        output: ['uefi-user-images.hpp', 'user-images.json'] + ('--image' in user_options ? ['user-sets.json'] : []),
        build_subdir: output_subdir,
        depend_files: files('../scripts/bootstrap_frontend.py') + check_dependencies,
        command: [python, '-B', files('../scripts/kernel-uefi-user-images.py'), '--output', output_dir,
                  '--mode', profile_data[key + '.user_mode']] + user_options)
      generated_headers = [user_metadata[0]]
    endif
    kernel_profile_users += {profile_id: user_metadata}
  endif

  # Native Meson compiles own C++ dependency files and compile_commands entries.
  # Keep the closed protected supervisor, the scratchpad and the packed test
  # images size-optimized independently of the shared payload reservation.
  profile_options = kernel_options + {'optimization': profile_data[key + '.optimization']}
  cpp_names = profile_data[key + '.cpp'].split('|')
  foreach name : cpp_names
    source = files('../' + profile_data[key + '.cpp.' + name])
    flags = ['-fstack-usage', '-fcallgraph-info=su'] + kernel_flags + ['-UNDEBUG'] + profile_flags
    # The production append composition retains the same image/stack caps. GCC's
    # strongest size recipe applies only to its native objects, after Meson's -Os.
    if '-DAURORA_PROGRAM_APPEND_CALL' in profile_flags
      flags += ['-Oz']
    endif
    flags += platform == 'bios' ? ['-fno-pie'] : ['-fpie', '-fvisibility=hidden']
    # Keep the BIOS console's conservative exception closure directly auditable.
    if bios_console
      flags += ['-fno-jump-tables']
    endif
    if platform == 'bios' or name == 'runtime'
      flags += ['-I' + include_dir]
    endif
    native = static_library(prefix + '-' + name, [source, generated_headers],
      native: true, pic: false, install: false, build_by_default: false, implicit_include_directories: false,
      override_options: profile_options, build_subdir: output_subdir / 'native', cpp_args: flags)
    sidecars = [name + '.o', name + '.su', name + '.source.json', name + '.ci']
    objects += {name: custom_target(prefix + '-' + name + '-export', input: native.extract_objects(source),
      output: sidecars, build_subdir: object_subdir,
      command: [python, '-B', kernel_object_helper, '--native-object', '@INPUT@', '--source', source,
                '--output', '@OUTPUT0@', '--compile-directory', meson.project_build_root(), '--callgraph'])}
    stack_facts += [objects[name][3]]
  endforeach
  link_objects = []
  foreach name : profile_data[key + '.link'].split('|')
    link_objects += [objects[name][0]]
  endforeach
  if platform == 'bios'
    elf = custom_target(prefix + '-elf', input: link_objects, output: 'kernel.elf',
      build_subdir: output_subdir, depend_files: files('../kernel/link.ld'),
      command: [kernel_ld, '-nostdlib', '-z', 'max-page-size=0x1000', '-T', files('../kernel/link.ld'),
                '@INPUT@', '-o', '@OUTPUT@'])
    binary = custom_target(prefix + '-binary', input: elf, output: 'kernel.bin', build_subdir: output_subdir,
      command: [kernel_objcopy, '-O', 'binary', '@INPUT@', '@OUTPUT@'])
    profile_image = custom_target(prefix + '-image',
      input: [boot, objects['boot'], elf, binary],
      output: 'aurora.img', build_subdir: output_subdir, build_by_default: mode == 'normal',
      command: [python, '-B', files('../tests/kernel-image.py'), '--build-dir', output_dir])
    image_args = ['--elf', elf.full_path()]
  else
    linker_script = custom_target(prefix + '-linker-script', input: files('../kernel/uefi/payload.ld'),
      output: 'payload.ld', build_subdir: output_subdir,
      command: native_cpp.cmd_array() + ['-E', '-P', '-x', 'c'] + profile_flags +
               ['-DAURORA_PAYLOAD_LIMIT=' + profile_data['layout.kernel_payload_limit'], '@INPUT@', '-o', '@OUTPUT@'])
    elf = custom_target(prefix + '-elf', input: link_objects, output: 'payload.elf',
      build_subdir: output_subdir,
      command: [kernel_ld, '-nostdlib', '-T', linker_script, '-z', 'max-page-size=0x1000', '@INPUT@', '-o', '@OUTPUT@'])
    binary = custom_target(prefix + '-binary', input: elf, output: 'payload.bin', build_subdir: output_subdir,
      command: [kernel_objcopy, '-O', 'binary', '@INPUT@', '@OUTPUT@'])
    metadata_outputs = ['uefi-payload.hpp', 'embed.S', 'bar-metadata.json', 'ivrs-metadata.json']
    if '--service-budget' in user_options
      metadata_outputs += ['service-timer-metadata.json']
    endif
    metadata = custom_target(prefix + '-payload-metadata', input: [elf, binary], output: metadata_outputs,
      build_subdir: output_subdir,
      depend_files: check_dependencies + files('../scripts/kernel_layout.py', '../kernel/bootstrap-layout-values.inc'),
      command: [python, '-B', files('../scripts/kernel-uefi-metadata.py'), '--build-dir', output_dir])
    objects += {'embed': custom_target(prefix + '-embed-object', input: metadata[1], output: 'embed.o',
      build_subdir: object_subdir, depends: [binary],
      command: [kernel_as, '--64', '@INPUT@', '-o', '@OUTPUT@'])}
    loader_source = files('../kernel/uefi/loader.cpp')
    loader = static_library(prefix + '-loader', [loader_source, metadata[0], generated_headers],
      native: true, pic: false, install: false, build_by_default: false, implicit_include_directories: false,
      override_options: kernel_options, build_subdir: output_subdir / 'native',
      cpp_args: kernel_flags + ['-UNDEBUG'] + profile_flags + ['-fpie', '-maccumulate-outgoing-args', '-I' + include_dir])
    loader_object = loader.extract_objects(loader_source)
    pe_objects = []
    foreach name : ['loader', 'embed', 'transition', 'memory']
      pe_objects += [custom_target(prefix + '-' + name + '-pe-object',
        input: name == 'loader' ? loader_object : objects[name][0], output: name + '-pe.o',
        build_subdir: object_subdir,
        command: [kernel_objcopy, '--remove-section=.comment', '--remove-section=.note.GNU-stack', '@INPUT@', '@OUTPUT@'])]
    endforeach
    profile_image = custom_target(prefix + '-pe', input: pe_objects, output: 'BOOTX64.EFI',
      build_subdir: output_subdir / 'esp/EFI/BOOT', build_by_default: mode == 'normal',
      command: [pe_linker, '-mi386pep', '--subsystem', '10', '--entry=aurora_efi_entry', '--image-base=0x100000',
                '--enable-reloc-section', '--dynamicbase', '--nxcompat', '--no-insert-timestamp', '@INPUT@', '-o', '@OUTPUT@'])
    image_args = ['--pe', profile_image.full_path(), '--elf', elf.full_path()]
    foreach object : link_objects
      image_args += ['--pic-object', object.full_path()]
    endforeach
  endif
  foreach object : language_objects
    image_args += ['--language', object.full_path()]
  endforeach
  stack_args = ['--image', elf.full_path()]
  foreach fact : stack_facts
    stack_args += ['--facts', fact.full_path()]
  endforeach
  foreach input : user_inputs
    if input.full_path().endswith('.elf')
      image_args += ['--user', input.full_path()]
    endif
  endforeach
  checks = [
    custom_target(prefix + '-image-check', input: [profile_image, elf] + link_objects + user_inputs,
      output: 'image-check.stamp', build_subdir: output_subdir, build_by_default: mode == 'normal',
      depend_files: [image_policy, check_dependencies],
      command: [python, '-B', image_check, '--profile', profile_id, '--policy', image_policy,
                '--output', '@OUTPUT@'] + image_args),
    custom_target(prefix + '-stack-check', input: [elf] + stack_facts + user_inputs,
      output: 'stack-check.json', build_subdir: output_subdir, build_by_default: mode == 'normal',
      depend_files: [image_policy, check_dependencies],
      command: [python, '-B', stack_check, '--profile', profile_id, '--policy', image_policy,
                '--limit', stack_limit, '--output', '@OUTPUT@'] + stack_args + user_stack_args),
  ]
  kernel_profile_images += {profile_id: [profile_image] + checks}
  alias_target('kernel-' + prefix, [profile_image] + checks)
endforeach

# Guest-machine aliases share identical image bytes and native compilation.
foreach alias : profile_data['aliases'].split('|')
  canonical = profile_data['aliases.' + alias]
  alias_target('kernel-' + alias.replace('/', '-'), kernel_profile_images[canonical])
endforeach
