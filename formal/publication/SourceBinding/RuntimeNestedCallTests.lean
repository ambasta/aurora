import SourceBinding.RuntimeCallExpressionProof
namespace Aurora.SourceBinding.RuntimeNestedCallTests
-- Synthetic execution controls of the SAME machine. These are not a proof that
-- production execution reaches the selected caller interval.
def constantLeaf : OrdinaryDescriptor := ⟨"kernel".toUTF8,1,[],.scalar .word⟩
def packingLeaf : OrdinaryDescriptor :=
  ⟨"record".toUTF8,2,[.scalar .word,.scalar .word,.scalar .word],.scalar .word⟩
-- Runtime signatures retain nominal name and cardinality, not only arity.
example : (⟨"f".toUTF8,7,[.nominal ⟨"E".toUTF8,5⟩],.scalar .word⟩ : OrdinaryDescriptor) ≠
    ⟨"f".toUTF8,7,[.nominal ⟨"F".toUTF8,5⟩],.scalar .word⟩ := by decide
example : (⟨"f".toUTF8,7,[.nominal ⟨"E".toUTF8,5⟩],.scalar .word⟩ : OrdinaryDescriptor) ≠
    ⟨"f".toUTF8,7,[.nominal ⟨"E".toUTF8,6⟩],.scalar .word⟩ := by decide
example : (⟨"f".toUTF8,7,[.nominal ⟨"E".toUTF8,5⟩],.scalar .word⟩ : OrdinaryDescriptor) ≠
    ⟨"f".toUTF8,7,[.scalar .word],.scalar .word⟩ := by decide

def program : CallProgram := fun callable pc =>
  if callable == 0 then
    ([.ordinary constantLeaf,.local (.pure .push),.local (.pure (.constant .word (Value.word 0))),
      .local (.pure .push),.local (.pure (.constant .word (Value.word 4294967296))),
      .local (.pure .push),.ordinary packingLeaf,.local (.pure .ret)] : List CallOp)[pc]?
  else if callable == 1 then
    ([.local (.pure (.constant .word (Value.word 2))),.local (.pure .ret)] : List CallOp)[pc]?
  else if callable == 2 then
    ([.local (.pure (.bind .word 0 8)),.local (.pure (.bind .word 1 16)),.local (.pure (.bind .word 2 24)),
      .local (.pure (.load .word 24)),.local (.pure .push),.local (runtimeCount .thirtyTwo),
      .local (.pure (.binary .leftShift)),.local (.pure .ret)] : List CallOp)[pc]?
  else none

def initial : ActiveCall Nat :=
  ⟨0,⟨0,none,[Value.word 999],fun slot => if slot == 8 then some (Value.word 77) else none,
      fun index => if index == 0 then some (Value.word 88) else none⟩,[],
    ⟨fun cell => if cell == 9 then some (Value.word 66) else none,55⟩⟩
def run : Nat → CallPhase Nat Nat → CallPhase Nat Nat × List (CallEvent Nat Nat)
  | 0, phase => (phase,[])
  | fuel+1, .running active =>
    let first := callStep program active
    let rest := run fuel first.1
    (rest.1,first.2++rest.2)
  | _+1, phase => (phase,[])
private def expect (condition : Bool) (message : String) : IO Unit :=
  unless condition do throw (IO.userError message)
#eval do
  match run 32 (.running initial) with
  | (.trapped (.local (.scalar .overflow)) active,
      [.ordinaryInvoke first [],.ordinaryReturn second (Value.word 2),.ordinaryInvoke third arguments]) =>
    expect (first == constantLeaf && second == constantLeaf && third == packingLeaf &&
      arguments == [Value.word 2,Value.word 0,Value.word 4294967296]) "nested exact ordered trace"
    expect (active.callable == 2 && active.frame.pc == 6 && active.frame.locals 24 == some (Value.word 4294967296))
      "overflow retains active packing callee"
    expect (active.shared.world == 55 && active.shared.receiver 9 == some (Value.word 66)) "fault shared frame"
    match active.saved with
    | [saved] =>
      expect (saved.target == packingLeaf && saved.caller == 0 && saved.continuation.pc == 7 &&
        saved.continuation.stack == [Value.word 999] && saved.continuation.locals 8 == some (Value.word 77) &&
        saved.continuation.arguments 0 == some (Value.word 88)) "fault retains protected caller and residual operand"
    | _ => throw (IO.userError "fault fabricated unwind")
  | _ => throw (IO.userError "missing overflow or fabricated return")
  IO.println "nested-call machine controls: 4 passed"
end Aurora.SourceBinding.RuntimeNestedCallTests
