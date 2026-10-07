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

# The RAM example also imports the writer and owned-block modules. Keep every
# direct and transitive Aurora input explicit until compiler depfiles exist.
ram_record_assembly = custom_target(
    'ram-record-example',
    input: 'ram_record.au',
    output: 'ram_record.s',
    command: [aurorac, '--module-root', meson.project_source_root() / 'library', '@INPUT@', '-o', '@OUTPUT@'],
    depend_files: files(
      '../storage/ram_blocks.au',
      '../storage/block.au',
      '../storage/block_codec.au',
      '../std/binary_writer.au',
      '../std/bytes.au',
      '../std/binary.au',
    ),
    build_by_default: true,
    install: false,
)
