# The --target aurora runtime root in the build tree (meson.build,
# kernel_runtime_root): this directory's aurora.host and the one aurora.memory
# both targets compile, so the memory runtime has a single source.
configure_file(input: 'host.au', output: 'host.au', copy: true)
configure_file(input: '../../linux/aurora/memory.au', output: 'memory.au', copy: true)
