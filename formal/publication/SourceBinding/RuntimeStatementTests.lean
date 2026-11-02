import SourceBinding.RuntimeBodyBinding
namespace Aurora.SourceBinding
open Aurora.Publication

private def statementFixture (body : String) (code : List EffectOp) : Bool := Id.run do
  let text := "module r; namespace n { auto f() -> u64 { " ++ body ++ " } }"
  let some shell := namedSource text.toUTF8 | return false
  let file : SourceFile := ⟨text.toUTF8,shell⟩
  let some selected := checkFreeSelection [file] ["r".toUTF8] ["r".toUTF8] ["n".toUTF8] "f".toUTF8 | return false
  let some source := scopeMethod text.toUTF8 selected.function.function selected.scope.members ["r".toUTF8] ["n".toUTF8] | return false
  let leaves : List (RuntimeCallable (tables []) [] ["r".toUTF8] ["r".toUTF8] ["n".toUTF8]) := []
  let program : CallProgram := fun _ pc => (code[pc]?).map CallOp.local
  let some result := checkRuntimeStatements program 0 leaves selected.scope.members [] (.scalar .word)
    4096 ⟨[],0,1,0⟩ source.parsed.statements 0 | return false
  return result.stop == code.length && (checkRuntimeNoFallthrough source.parsed.statements).isSome

-- Executable parsed-source/synthetic-code controls, not canonical publication certificates.
#eval do
  let one : EffectOp := .pure (.constant .word (.word 1))
  let two : EffectOp := .pure (.constant .word (.word 2))
  let store : EffectOp := .localStore (.scalar .word) 8
  let load : EffectOp := .pure (.load .word 8)
  let ret : EffectOp := .pure .ret
  let code := [one,store,two,store,load,ret]
  let cases := [
    ("mutable local",statementFixture "u64 x = 1u64; x = 2u64; return x;" code,true),
    ("const assignment",statementFixture "const u64 x = 1u64; x = 2u64; return x;" code,false),
    ("old-context initializer",statementFixture "u64 x = x; return x;" [load,store,load,ret],false),
    ("wrong local store",statementFixture "u64 x = 1u64; return x;" [one,.localStore (.scalar .word) 16,load,ret],false),
    ("dead suffix checked",statementFixture "return 1u64; return 2u64;" [one,ret,two,ret],true),
    ("dead suffix omitted",statementFixture "return 1u64; return 2u64;" [one,ret],false),
    ("extra instruction",statementFixture "return 1u64;" [one,ret,two],false),
    ("no terminal return",statementFixture "u64 x = 1u64;" [one,store],false),
    ("linear labels",statementFixture "if (true) { return 1u64; } return 2u64;"
      [.pure (.constant .boolean (.boolean true)),.pure (.branchFalse 4),one,ret,.pure .label,.pure .label,two,ret],true),
    ("nonlabel hidden",statementFixture "if (true) { return 1u64; } return 2u64;"
      [.pure (.constant .boolean (.boolean true)),.pure (.branchFalse 4),one,ret,.pure .label,one,two,ret],false)]
  for (label,actual,expected) in cases do
    unless actual == expected do throw (IO.userError s!"statement control failed: {label}")
  IO.println s!"runtime statement controls: {cases.length} passed"

end Aurora.SourceBinding
