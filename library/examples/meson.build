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

ram_sector_record_assembly = custom_target(
    'ram-sector-record-example',
    input: 'ram_sector_record.au',
    output: 'ram_sector_record.s',
    command: [aurorac, '--module-root', meson.project_source_root() / 'library', '@INPUT@', '-o', '@OUTPUT@'],
    depend_files: files(
        '../storage/ram_sector.au',
        '../storage/block_io.au',
        '../storage/sector.au',
        '../std/binary_buffer.au',
        '../std/bytes.au',
        '../std/binary.au',
    ),
    build_by_default: true,
    install: false,
)

byte_buffer_assembly = custom_target(
    'byte-buffer-example',
    input: 'byte_buffer.au',
    output: 'byte_buffer.s',
    command: [aurorac, '--module-root', meson.project_source_root() / 'library', '@INPUT@', '-o', '@OUTPUT@'],
    depend_files: files('../std/byte_buffer.au', '../std/binary.au'),
    build_by_default: true,
    install: false,
)

json_assembly = custom_target(
    'json-example',
    input: 'json.au',
    output: 'json.s',
    command: [aurorac, '--module-root', meson.project_source_root() / 'library', '@INPUT@', '-o', '@OUTPUT@'],
    depend_files: files('../std/json.au', '../std/utf8.au', '../std/array.au'),
    build_by_default: true,
    install: false,
)
