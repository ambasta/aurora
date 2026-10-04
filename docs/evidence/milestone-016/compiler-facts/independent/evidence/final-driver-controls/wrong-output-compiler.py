#!/opt/codex/runtimes/codex-primary-runtime/dependencies/python/bin/python3
import pathlib,sys
output=pathlib.Path(sys.argv[sys.argv.index("-o")+1])
output.write_text(".text\n.globl test\ntest:\n movq $43,%rax\n ret\n.section .note.GNU-stack,\"\",@progbits\n")
