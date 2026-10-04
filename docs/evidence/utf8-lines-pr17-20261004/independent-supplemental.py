import json,pathlib,signal
import review_native as h
h.OUT=h.BASE/'supplemental'
h.require(not h.OUT.exists(),'fresh supplemental output');h.OUT.mkdir()
items=[]
items.append(dict(label='private report metadata exposes zero fields',args=[],expected=[0,0,24,42],body='static_assert(field_count(std::Utf8LineResult)==0);static_assert(size_of(std::Utf8LineResult)==24);if(field==0){return field_count(std::Utf8LineResult);}if(field==1){return reflect_field_count(type_id(std::Utf8LineResult));}if(field==2){return reflect_size(type_id(std::Utf8LineResult));}return 42;'))
for a,n in [(0,1),(1,1),(0,2)]:
    raw=b'\r\n';body=h.array(raw)+f'const std::Utf8LineResult r=std::read_utf8_line(borrow_bytes(owner),{a},{n});'+h.observe()
    items.append(dict(label='separate final windows do not retroactively form CRLF',args=[a,n],expected=h.oracle(raw,a,n),body=body))
h.batch(items,0)
d=h.OUT/'forged-count-bounds-trap';d.mkdir()
source='module forged;import std.utf8_lines;auto test()->i64{const builtin::array<u8,1> owner={65u8};const std::Utf8LineResult forged=std::Utf8LineResult(std::Utf8LineStatus::success,9223372036854775807,std::Utf8LineEnding::none);const builtin::span<const u8> view=borrow_bytes(owner);return i64(view.at(forged.content_bytes()));}'
(d/'input.au').write_text(source)
h.run([h.CC,'--module-root',h.ROOT/'library',d/'input.au','-o',d/'generated.s'],d,'compile')
(d/'entry.s').write_text('.text\n.globl _start\n_start:\ncall test\nmovq %rax,%rdi\nmovq $60,%rax\nsyscall\n.section .note.GNU-stack,"",@progbits\n')
h.run(['as','--64',d/'generated.s','-o',d/'generated.o'],d,'assemble');h.run(['as','--64',d/'entry.s','-o',d/'entry.o'],d,'entry');h.run(['ld',d/'entry.o',d/'generated.o','-o',d/'probe'],d,'link')
h.run([d/'probe'],d,'execute',-signal.SIGILL)
frozen=json.loads((h.ROOT/'work/source-freeze-v1.json').read_text());h.verify(frozen)
result=dict(status='passed',cases=4,full_i64_observations=16,bounds_traps=1,trap_limit='SIGILL observed; no exact instruction-address claim',source_freeze_sha256=h.sha(h.ROOT/'work/source-freeze-v1.json'),compiler_sha256=h.PIN,script_sha256=h.sha(__file__),allocated_bytes=h.budget(0))
(h.BASE/'supplemental-summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
