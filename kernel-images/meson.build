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
# artifact paths and every per-image link/embedding/admission edge below.
kernel_user_assemblies = {}
kernel_copy = find_program('cp', native: true)
admission_recipes = {
  'bios-console': ['kernel_bios_console_admission.py', 'bios-console-admission.json'],
  'program': ['kernel_program_console_admission.py', 'program-console-admission.json'],
  'console': ['kernel_console_service_admission.py', 'console-service-admission.json'],
  'graphical': ['kernel_graphical_console_admission.py', 'graphical-console-admission.json'],
  'framebuffer': ['kernel_framebuffer_admission.py', 'framebuffer-admission.json'],
  'event': ['kernel_iommu_event_admission.py', 'iommu-event-admission.json'],
}
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
  aurora_facts = []
  checks = []
  admission = profile_data[key + '.admission']
  bios_console = platform == 'bios' and mode == 'console'
  ram_scratchpad = platform == 'uefi' and mode in ['ram-scratchpad-console', 'ram-scratchpad-console-fixture']
  image_option_text = profile_data[key + '.image_options']
  image_options = image_option_text == '' ? [] : image_option_text.split('|')
  if admission != ''
    admission_recipe = admission_recipes[admission]
    admission_tool = files('../scripts/' + admission_recipe[0])
    admission_common_args = ['--mode', mode, '--build-dir', output_dir, '--source-root', kernel_source]
  endif

  root_args = []
  foreach root : profile_data[key + '.roots'].split('|')
    root_args += ['--module-root', kernel_source / root]
  endforeach
  # The closed supervisor exposes only its bridge-declared scalar/native ABI.
  if admission == 'program' or ram_scratchpad
    root_args += ['--referenced-reflection-only', '--local-symbols']
  endif
  bridge = profile_data[key + '.bridge']
  bridge_input = bridge == '' ? [] : files('../' + bridge)
  language_outputs = [platform == 'bios' ? 'kernel-language.s' : 'language.s',
                      platform == 'bios' ? 'kernel-language.stack.json' : 'language.stack.json']
  language_dependencies = compiler_files
  if admission == 'program' or bios_console or ram_scratchpad
    language_outputs += [bios_console ? 'kernel-language.abi.json' : 'language.abi.json']
    root_args += ['--abi-facts', '@OUTPUT2@', '--bridge', kernel_source / bridge]
    language_dependencies += bridge_input + files('../scripts/bootstrap_frontend.py')
    if admission == 'program' or ram_scratchpad
      root_args += ['--bridge', kernel_source / 'kernel/uefi/kernel-policy-entry.S']
      language_dependencies += files('../kernel/uefi/kernel-policy-entry.S')
    endif
    bridge_input = []
  endif
  language_name = platform == 'bios' ? 'kernel-language' : 'language'
  language = custom_target(prefix + '-language-assembly',
    input: files('../' + profile_data[key + '.language']), output: language_outputs,
    build_subdir: output_subdir, depfile: language_name + '.d', depend_files: language_dependencies,
    command: [python, '-B', kernel_assembly_helper, '--compiler', kernel_image_compiler, '--source', '@INPUT@',
              '--output', '@OUTPUT0@', '--stack-facts', '@OUTPUT1@', '--depfile', '@DEPFILE@'] + root_args)
  aurora_facts += [language[1]]
  if admission == 'program' or bios_console or ram_scratchpad
    aurora_facts += [language[2]]
  endif
  # Private local symbols require the bridge and generated source in ONE as command.
  objects += {language_name: custom_target(prefix + '-language-object',
    input: [language[0]] + bridge_input, output: language_name + '.o', build_subdir: object_subdir,
    command: [kernel_as, '--64', '@INPUT@', '-o', '@OUTPUT@'])}
  if bios_console
    uart_assembly = custom_target(prefix + '-uart-assembly',
      input: files('../examples/kernel-uart.au'),
      output: ['kernel-uart.s', 'kernel-uart.stack.json', 'kernel-uart.abi.json'],
      build_subdir: output_subdir, depfile: 'kernel-uart.d',
      depend_files: compiler_files + files('../kernel/uart-policy-entry.S', '../scripts/bootstrap_frontend.py'),
      command: [python, '-B', kernel_assembly_helper, '--compiler', kernel_image_compiler, '--source', '@INPUT@',
                '--output', '@OUTPUT0@', '--stack-facts', '@OUTPUT1@', '--abi-facts', '@OUTPUT2@',
                '--depfile', '@DEPFILE@', '--module-root', kernel_source / 'kernel/policies',
                '--local-symbols', '--referenced-reflection-only',
                '--bridge', kernel_source / 'kernel/uart-policy-entry.S'])
    aurora_facts += [uart_assembly[1], uart_assembly[2]]
    objects += {'kernel-uart': custom_target(prefix + '-uart-object',
      input: uart_assembly[0], output: 'kernel-uart.o', build_subdir: object_subdir,
      command: [kernel_as, '--64', '@INPUT@', '-o', '@OUTPUT@'])}
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
      owned_text = '--owned-text' in image_options and name == 'clean'
      call_client = combined and '--blocking-call' in profile_data[key + '.user_options'].split('|')
      ram_file = '--ram-file' in profile_data[key + '.user_options'].split('|')
      # Closed callers and owned text have independently checked linked graphs.
      if (call_client and name == 'clean') or owned_text or ram_file
        user_root_args += ['--referenced-reflection-only']
      endif
      if owned_text
        user_root_args += ['--local-symbols']
      endif
      user_outputs = ['user-' + name + '.s', 'user-' + name + '.stack.json']
      user_dependencies = compiler_files
      if admission == 'program' or call_client or owned_text or ram_file
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
      aurora_facts += [user_assembly[1]]
      if admission == 'program' or call_client or owned_text or ram_file
        aurora_facts += [user_assembly[2]]
      endif
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
      user_inputs += [user_elf, user_binary]
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
      user_tool = profile_data[key + '.user_kind'] == 'ipc' ? 'kernel-uefi-ipc-images.py' : 'kernel-uefi-user-images.py'
      user_option_text = profile_data[key + '.user_options']
      user_options = user_option_text == '' ? [] : user_option_text.split('|')
      user_metadata = custom_target(prefix + '-user-metadata', input: user_inputs + aurora_facts,
        output: ['uefi-user-images.hpp', 'user-images.json'], build_subdir: output_subdir,
        depend_files: files('../scripts/kernel-uefi-user-images.py', '../scripts/bootstrap_frontend.py',
                            '../scripts/kernel_stack.py'),
        command: [python, '-B', files('../scripts/' + user_tool), '--output', output_dir,
                  '--mode', profile_data[key + '.user_mode']] + user_options)
      generated_headers = [user_metadata[0]]
    endif
    kernel_profile_users += {profile_id: user_metadata}
  endif

  # Native Meson compiles own C++ dependency files and compile_commands entries.
  # Keep the closed protected supervisor within its existing 128 KiB reservation.
  # Both bounded scratchpad compositions use the existing protected Console size recipe.
  profile_options = kernel_options + {'optimization': (admission == 'program' or ram_scratchpad) ? 's' : '2'}
  cpp_names = profile_data[key + '.cpp'].split('|')
  foreach name : cpp_names
    source = files('../' + profile_data[key + '.cpp.' + name])
    flags = ['-fstack-usage'] + (platform == 'uefi' or bios_console ? ['-fcallgraph-info=su'] : []) + kernel_flags + ['-UNDEBUG'] + profile_flags
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
    sidecars = [name + '.o', name + '.su', name + '.source.json'] + (platform == 'uefi' or bios_console ? [name + '.ci'] : [])
    objects += {name: custom_target(prefix + '-' + name + '-export', input: native.extract_objects(source),
      output: sidecars, build_subdir: object_subdir,
      command: [python, '-B', kernel_object_helper, '--native-object', '@INPUT@', '--source', source,
                '--output', '@OUTPUT0@', '--compile-directory', meson.project_build_root()] +
               (platform == 'uefi' or bios_console ? ['--callgraph'] : []))}
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
      input: [boot, objects['boot'], objects[language_name], elf, binary, user_metadata[0]] + aurora_facts,
      output: 'aurora.img', build_subdir: output_subdir, build_by_default: mode == 'normal',
      depend_files: files('../examples/kernel-bios.au', '../examples/kernel.au'),
      command: [python, '-B', files('../tests/kernel-image.py'), '--build-dir', output_dir] + image_options)
  else
    linker_script = custom_target(prefix + '-linker-script', input: files('../kernel/uefi/payload.ld'),
      output: 'payload.ld', build_subdir: output_subdir,
      command: native_cpp.cmd_array() + ['-E', '-P', '-x', 'c'] + profile_flags + ['@INPUT@', '-o', '@OUTPUT@'])
    elf = custom_target(prefix + '-elf', input: link_objects, output: 'payload.elf',
      build_subdir: output_subdir,
      command: [kernel_ld, '-nostdlib', '-T', linker_script, '-z', 'max-page-size=0x1000', '@INPUT@', '-o', '@OUTPUT@'])
    binary = custom_target(prefix + '-binary', input: elf, output: 'payload.bin', build_subdir: output_subdir,
      command: [kernel_objcopy, '-O', 'binary', '@INPUT@', '@OUTPUT@'])
    metadata_outputs = ['uefi-payload.hpp', 'embed.S', 'bar-metadata.json', 'ivrs-metadata.json']
    if admission in ['console', 'graphical']
      metadata_outputs += ['console-poll-metadata.json']
    endif
    if admission == 'program' or ram_scratchpad
      metadata_outputs += ['program-poll-metadata.json']
    endif
    if '--service-budget' in user_options
      metadata_outputs += ['service-timer-metadata.json']
    endif
    metadata = custom_target(prefix + '-payload-metadata', input: [elf, binary], output: metadata_outputs,
      build_subdir: output_subdir,
      command: [python, '-B', files('../scripts/kernel-uefi-metadata.py'), '--build-dir', output_dir])
    objects += {'embed': custom_target(prefix + '-embed-object', input: metadata[1], output: 'embed.o',
      build_subdir: object_subdir, depends: [binary],
      command: [kernel_as, '--64', '@INPUT@', '-o', '@OUTPUT@'])}
    loader_source = files('../kernel/uefi/loader.cpp')
    loader = static_library(prefix + '-loader', [loader_source, metadata[0], generated_headers],
      native: true, pic: false, install: false, build_by_default: false, implicit_include_directories: false,
      override_options: kernel_options, build_subdir: output_subdir / 'native',
      cpp_args: ['-fstack-usage', '-fcallgraph-info=su'] + kernel_flags + ['-UNDEBUG'] + profile_flags + ['-fpie', '-maccumulate-outgoing-args', '-I' + include_dir])
    objects += {'loader': custom_target(prefix + '-loader-export', input: loader.extract_objects(loader_source),
      output: ['loader.o', 'loader.su', 'loader.ci', 'loader.source.json'], build_subdir: object_subdir,
      command: [python, '-B', kernel_object_helper, '--native-object', '@INPUT@', '--source', loader_source,
                '--output', '@OUTPUT0@', '--compile-directory', meson.project_build_root(), '--callgraph'])}
    pe_objects = []
    foreach name : ['loader', 'embed', 'transition', 'memory']
      pe_objects += [custom_target(prefix + '-' + name + '-pe-object', input: objects[name][0], output: name + '-pe.o',
        build_subdir: object_subdir,
        command: [kernel_objcopy, '--remove-section=.comment', '--remove-section=.note.GNU-stack', '@INPUT@', '@OUTPUT@'])]
    endforeach
    pe = custom_target(prefix + '-pe', input: pe_objects, output: 'BOOTX64.EFI',
      build_subdir: output_subdir / 'esp/EFI/BOOT',
      command: [pe_linker, '-mi386pep', '--subsystem', '10', '--entry=aurora_efi_entry', '--image-base=0x100000',
                '--enable-reloc-section', '--dynamicbase', '--nxcompat', '--no-insert-timestamp', '@INPUT@', '-o', '@OUTPUT@'])
    if admission == 'event'
      image_options += ['--event-mode', mode]
    endif
    profile_image = custom_target(prefix + '-image', input: [pe, elf, binary], output: 'image-metadata.json',
      build_subdir: output_subdir, build_by_default: mode == 'normal',
      depend_files: files('../scripts/kernel_program_console_admission.py',
        '../scripts/kernel_stack.py', '../scripts/kernel_snapshot_abi.py',
        '../scripts/kernel_owned_bytes_admission.py'),
      command: [python, '-B', files('../scripts/kernel_uefi_image.py'), '--build-dir', output_dir] + image_options)
  endif
  check_names = profile_data[key + '.checks']
  validation_dependencies = files('../scripts/bootstrap_frontend.py', '../scripts/kernel_program_console_admission.py',
    '../scripts/kernel_stack.py', '../scripts/kernel_snapshot_abi.py', '../scripts/kernel_uefi_image.py',
    '../scripts/kernel_owned_bytes_admission.py',
    '../scripts/kernel-uefi-user-images.py', '../scripts/kernel-uefi-ipc-images.py',
    '../tests/kernel-snapshot-abi.py')
  native_exports = []
  foreach name : cpp_names
    native_exports += [objects[name]]
  endforeach
  if platform == 'uefi'
    native_exports += [objects['loader']]
  endif
  if check_names != ''
    foreach check : check_names.split('|')
      if check == 'call'
        checks += [custom_target(prefix + '-call-stack', input: [elf, binary, user_metadata] + user_inputs + native_exports + aurora_facts,
          output: 'call-stack.json', build_subdir: output_subdir,
          depend_files: validation_dependencies,
          command: [python, '-B', files('../scripts/kernel-uefi-ipc-images.py'), '--output', output_dir, '--call-stack'])]
      endif
      if check == 'ram-scratchpad'
        checks += [custom_target(prefix + '-ram-scratchpad-stack', input: [elf, binary, user_metadata] + user_inputs + native_exports + aurora_facts,
          output: 'ram-scratchpad-stack.json', build_subdir: output_subdir,
          depend_files: validation_dependencies,
          command: [python, '-B', files('../scripts/kernel-uefi-ipc-images.py'), '--output', output_dir, '--ram-scratchpad-stack'] + (mode == 'ram-scratchpad-console-fixture' ? ['--ram-scratchpad-fixture'] : []))]
      endif
      if check == 'ram-file'
        checks += [custom_target(prefix + '-ram-file-stack', input: [elf, binary, user_metadata] + user_inputs + native_exports + aurora_facts,
          output: 'ram-file-stack.json', build_subdir: output_subdir,
          depend_files: validation_dependencies,
          command: [python, '-B', files('../scripts/kernel-uefi-ipc-images.py'), '--output', output_dir, '--ram-file-stack'])]
      endif
      if check in ['snapshot', 'note']
        checks += [custom_target(prefix + '-user-abi', input: user_inputs + [user_metadata] + aurora_facts,
          output: check == 'note' ? 'note-abi.json' : 'abi.json', build_subdir: output_subdir,
          depend_files: validation_dependencies,
          command: [python, '-B', files('../tests/kernel-snapshot-abi.py'), output_dir,
                    '--uefi-mode', profile_data[key + '.user_mode']] + (check == 'note' ? ['--note'] : []))]
      endif
      if check == 'snapshot'
        checks += [custom_target(prefix + '-snapshot-stack', input: [elf, binary] + native_exports + aurora_facts,
          output: 'snapshot-stack.json', build_subdir: output_subdir,
          depend_files: validation_dependencies,
          command: [python, '-B', files('../tests/kernel-snapshot-abi.py'), output_dir, '--kernel-stack'])]
      elif check == 'owned-bytes'
        checks += [custom_target(prefix + '-owned-imports', input: objects[language_name],
          output: 'owned-bytes-imports.checked', build_subdir: output_subdir, capture: true,
          depend_files: validation_dependencies,
          command: [python, '-B', files('../tests/kernel-uefi-owned-bytes-admission.py'), '@INPUT@'])]
        checks += [custom_target(prefix + '-owned-stack', input: [elf, binary] + native_exports + aurora_facts,
          output: 'owned-bytes-stack.json', build_subdir: output_subdir,
          depend_files: validation_dependencies,
          command: [python, '-B', files('../tests/kernel-uefi-owned-bytes-stack.py'), output_dir, '@OUTPUT@'])]
      elif check == 'tables'
        checks += [custom_target(prefix + '-table-stack', input: [elf, binary] + native_exports + aurora_facts,
          output: ['stack.json', 'payload.su', 'acpi.su', 'pci.su', 'runtime.su', 'payload.disassembly.txt'],
          build_subdir: output_subdir / 'table-stack' / mode,
          depend_files: validation_dependencies,
          command: [python, '-B', files('../tests/kernel-uefi-tables-stack.py'), output_dir,
                    output_dir / 'table-stack' / mode])]
      elif check in ['ivrs', 'nvme']
        checks += [custom_target(prefix + '-' + check + '-stack', input: [elf, binary] + native_exports + aurora_facts,
          output: check + '-stack.json', build_subdir: output_subdir,
          depend_files: validation_dependencies,
          command: [python, '-B', files('../tests/kernel-uefi-' + check + '-stack.py'), output_dir, '@OUTPUT@'])]
      endif
    endforeach
  endif
  if admission != ''
    admission_inputs = [profile_image] + aurora_facts + native_exports + checks
    if bios_console
      admission_inputs += [elf, binary, objects['kernel-language'], objects['kernel-uart']]
      foreach name : profile_data[key + '.assembly'].split('|')
        admission_inputs += [objects[name]]
      endforeach
    else
      admission_inputs += [metadata]
    endif
    checks += [custom_target(prefix + '-admission',
      input: admission_inputs,
      output: admission_recipe[1], build_subdir: output_subdir,
      depend_files: validation_dependencies + files('../scripts/kernel_console_service_admission.py',
        '../scripts/meson_aurora_assembly.py', '../tests/kernel-image.py'),
      command: [python, '-B', admission_tool, 'emit'] + admission_common_args)]
  endif
  kernel_profile_images += {profile_id: [profile_image] + checks}
  alias_target('kernel-' + prefix, [profile_image] + checks)
  if mode == 'normal'
    if platform == 'bios'
      bios_image = profile_image
      bios_image_dir = output_dir
    else
      uefi_image = profile_image
      uefi_image_dir = output_dir
    endif
  endif
endforeach

# One stamp over every canonical profile and its checks, so that full builds all
# images rather than only those a guest smoke happens to select.
kernel_images_all_inputs = []
foreach profile_id, targets : kernel_profile_images
  kernel_images_all_inputs += targets
endforeach
kernel_images_all = custom_target('kernel-images-all', input: kernel_images_all_inputs,
  output: 'kernel-images-all.stamp',
  command: [python, '-B', '-c', 'import pathlib, sys; pathlib.Path(sys.argv[1]).write_text("built\\n")', '@OUTPUT@'])

# Guest-machine aliases share identical image bytes and native compilation.
foreach alias : profile_data['aliases'].split('|')
  canonical = profile_data['aliases.' + alias]
  alias_target('kernel-' + alias.replace('/', '-'), kernel_profile_images[canonical])
endforeach
