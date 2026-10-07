# Neither imported module has imports. Keep dependencies explicit until aurorac emits
# dependency files; any future import must be added here with its transitive inputs.
storage_codec_assembly = custom_target(
  'storage-codec-example',
  input: 'storage_codec.au',
  output: 'storage_codec.s',
  command: [aurorac, '--module-root', meson.project_source_root() / 'library', '@INPUT@', '-o', '@OUTPUT@'],
  depend_files: files('../std/bytes.au', '../std/binary.au'),
  build_by_default: true,
  install: false,
)
