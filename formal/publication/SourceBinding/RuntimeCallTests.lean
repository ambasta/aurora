import SourceBinding.RuntimeCallBinding
namespace Aurora.SourceBinding.RuntimeCallTests
open Aurora.Publication

/-- Synthetic relation/checker controls, not full publication or source-graph
    acceptance. Production interval controls retain the entire captured inputs. -/
def noContext : RuntimeExprContext := ⟨[],[],[],[],[]⟩
def localProgramOnly : CallProgram := fun _ pc =>
  if pc = 0 then some (.local (.pure (.constant .word (.word 1)))) else none

def noLeaves : List (RuntimeCallLeaf (tables []) [] [] [] []) := []
example : (checkRuntimeCallExpressionCode localProgramOnly 0 noLeaves noContext 8 (.word 1) 0).isSome = true := by decide
example : (checkRuntimeCallExpressionCode localProgramOnly 0 noLeaves noContext 8 (.word 2) 0).isNone = true := by decide
example : (checkRuntimeCallExpressionCode localProgramOnly 0 noLeaves noContext 8
    (.call (.named ["missing".toUTF8]) []) 0).isNone = true := by decide
example : RuntimeLeavesCompatible noLeaves := by intro first present; cases present

example : (SourceExpr.call (.named ["f".toUTF8]) [.word 1,.word 2]) ≠
    (.call (.named ["f".toUTF8]) [.word 2,.word 1]) := by
  intro same
  have impossible := (SourceExpr.call.inj same).2
  cases impossible
example : (Declaration.namespaceDecl "N".toUTF8 true [.enumDecl "E".toUTF8 ["a".toUTF8]]) ≠
    (.namespaceDecl "N".toUTF8 true [.enumDecl "E".toUTF8 ["b".toUTF8]]) := by
  intro same
  have impossible := (Declaration.enumDecl.inj
    (List.cons.inj (Declaration.namespaceDecl.inj same).2.2).1).2
  exact (by decide : (["a".toUTF8] : List ByteArray) ≠ ["b".toUTF8]) impossible

def declaration : Formal := ⟨"x".toUTF8,.constant (guardSourceType .word)⟩
def statements : List SourceStatement :=
  [.ifThen (.boolean false) [.localDecl declaration (.word 1),.returnValue (.name ["x".toUTF8])],
   .returnValue (.word 0)]
def selected (indices : List Nat) := selectScopedReturn [] [] [] [] 32 ⟨[],0,1,0⟩ statements indices
example : (selected [0,1]).isSome = true := by decide
example : ((selected [0,1]).map fun result => result.context.visible.map (fun (x : SourceLocal) => (x.slot,x.scope,x.mutable))) =
    some [(8,1,false)] := by decide
example : ((selected [1]).map fun result => result.context.visible.length) = some 0 := by decide
example : (selected [0,0]).isNone = true := by decide
example : (selected [2]).isNone = true := by decide
example : runtimeCalledNames 16 (.call (.named ["outer".toUTF8])
    [.call (.named ["inner".toUTF8]) [],.word 0]) = some ["outer".toUTF8,"inner".toUTF8] := by decide
example : runtimeCalledNames 16 (.call (.receiver "field".toUTF8 "method".toUTF8) []) = none := by decide

end Aurora.SourceBinding.RuntimeCallTests
