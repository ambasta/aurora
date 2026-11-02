import SourceBinding.RuntimeExpressionCode
namespace Aurora.SourceBinding

namespace RuntimeExpressionFixtures
private def bytes := String.toUTF8
private def context : RuntimeExprContext :=
  ⟨[.enumDecl (bytes "E") [bytes "zero",bytes "one"],.enumDecl (bytes "F") [bytes "zero",bytes "one"]],
    [bytes "m"],[bytes "n"],
    [⟨bytes "a",.named [bytes "u64"]⟩,⟨bytes "b",.named [bytes "u64"]⟩,
     ⟨bytes "tag",.named [bytes "E"]⟩,⟨bytes "flag",.named [bytes "bool"]⟩],
    [⟨bytes "x",.scalar .word,false,1,40⟩,⟨bytes "y",.scalar .word,true,1,48⟩]⟩
private def enumE : NominalIdentity := ⟨enumSymbol context.module context.path (bytes "E"),2⟩
private def enumF : NominalIdentity := ⟨enumSymbol context.module context.path (bytes "F"),2⟩
private def x : SourceExpr := .name [bytes "x"]
private def y : SourceExpr := .name [bytes "y"]
private def one : SourceExpr := .name [bytes "E",bytes "one"]
private def program (code : List EffectOp) : EffectProgram := fun pc => code[pc]?
private def accepts (source : SourceExpr) (code : List EffectOp) : Bool :=
  (bindRuntimeExpressionCode (program code) context source 0).isSome
private def typed (source : SourceExpr) : Bool := (checkRuntimeExpression context source).isSome

-- Synthetic context/program controls, NOT byte-backed production acceptance.
#eval do
  let checks := [
    ("exact local slot",accepts x [.pure (.load .word 40)],true),
    ("same-typed other local rejected",accepts x [.pure (.load .word 48)],false),
    ("formal exact slot",accepts (.name [bytes "a"]) [.pure (.load .word 8)],true),
    ("formal slot swap",accepts (.name [bytes "a"]) [.pure (.load .word 16)],false),
    ("enum exact identity and ordinal",accepts one [.enumConstant enumE 1],true),
    ("same-cardinality different enum",accepts one [.enumConstant enumF 1],false),
    ("wrong enum cardinality",accepts one [.enumConstant {enumE with cases := 3} 1],false),
    ("wrong named case ordinal",accepts one [.enumConstant enumE 0],false),
    ("enum not a word",accepts one [.pure (.constant .word (.word 1))],false),
    ("enum eq same nominal",typed (.binary (.compare .eq) one (.name [bytes "tag"])),true),
    ("enum ordering unsupported",typed (.binary (.compare .lt) one one),false),
    ("different nominal comparison",typed (.binary (.compare .eq) one (.name [bytes "F",bytes "one"])),false),
    ("standalone signed marker",typed (.signedCount 4),false),
    ("numeric word is not signed count",typed (.binary .shift x (.word 4)),false),
    ("calls outside first slice",typed (.call (.named [bytes "callee"]) []),false),
    ("exact shift four",accepts (.binary .shift x (.signedCount 4))
      [.pure (.load .word 40),.pure .push,.pure .count4,.pure (.binary .leftShift)],true),
    ("wrong signed literal",accepts (.binary .shift x (.signedCount 4))
      [.pure (.load .word 40),.pure .push,.pure .count32,.pure (.binary .leftShift)],false),
    ("unsigned shift operand",accepts (.binary .shift x (.signedCount 4))
      [.pure (.load .word 40),.pure .push,.pure (.constant .word (.word 4)),.pure (.binary .leftShift)],false),
    ("exact subtraction",accepts (.binary .subtract x y)
      [.pure (.load .word 40),.pure .push,.pure (.load .word 48),.pure (.binary .sub)],true),
    ("swapped subtraction uses",accepts (.binary .subtract x y)
      [.pure (.load .word 48),.pure .push,.pure (.load .word 40),.pure (.binary .sub)],false)]
  for (name,actual,expected) in checks do
    unless actual == expected do throw (IO.userError s!"runtime expression control failed: {name}")
  let args := program [.pure (.load .word 40),.pure .push,.enumConstant enumE 1,.pure .push]
  unless (checkRuntimeArgumentsCode args context [x,one] 0).isSome do
    throw (IO.userError "ordered arguments rejected")
  unless (checkRuntimeArgumentsCode args context [one,x] 0).isNone do
    throw (IO.userError "reordered arguments accepted")
  let aliases := {context with visible := [⟨bytes "x",.scalar .word,false,1,40⟩,⟨bytes "y",.scalar .word,true,1,40⟩]}
  unless (checkRuntimeContext aliases).isNone do throw (IO.userError "aliased local slots accepted")
  IO.println "RUNTIME-EXPRESSION-CONTROLS 23 synthetic source-use/typing/interval controls passed"
end RuntimeExpressionFixtures
end Aurora.SourceBinding
