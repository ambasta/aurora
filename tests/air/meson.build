# The test graph's object and header live in their own build directory, so its
# hosted_frontend_abi.hpp is visible only to targets that include this directory
# and never shadows the production header for other test targets.
air_forwarders = custom_target('air-frontend-forwarders', input: '../tools/frontend.au', output: 'frontend.au',
    command: [python, '-B', bridge_table, '@INPUT@', '@OUTPUT@'])
air_frontend = custom_target('air-frontend',
    input: frontend_modules + files('../tools/air.au', '../compiler/initialization_probe.au') + [air_forwarders],
    output: ['hosted-frontend.o', 'hosted-frontend.generated.o', 'hosted-frontend.abi.json',
             'hosted_frontend_abi.hpp', 'hosted-frontend.stack.json'],
    command: [python, '-B', files('../../scripts/bootstrap_frontend.py'), aurorac, '--output-mode', 'object',
              '--test-entries', '--output', '@OUTPUT0@', '@INPUT@'],
    depend_files: bridge_table)
