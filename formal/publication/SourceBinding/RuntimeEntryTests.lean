import SourceBinding.RuntimeReturnProof
namespace Aurora.SourceBinding.RuntimeEntryTests

def program : EffectProgram := fun pc => match pc with
  | 0 => some (.pure (.bind .word 0 8))
  | 1 => some (.pure (.load .word 8))
  | 2 => some (.pure .ret)
  | _ => none

def base : Machine := ⟨0,none,[],fun _ => none,fun _ => none,
  fun i => if i=0 then some (.word 7) else none⟩
example : RuntimeEntryCode program [.scalar .word] := by decide
example : (formalRuntimeLocals [.scalar .word] base).read 8 = .value (.word 7) := by decide
example : (formalRuntimeLocals [.scalar .word] base).read 16 = .trap .type := by decide
example : (formalRuntimeLocals [.scalar .word] base).leave.read 8 = .trap .type := by decide

example (machine : Machine) (arguments : RuntimeEntryArguments [.scalar .word] machine.arguments) :
    EffectRuns program (preparedEntry machine runtimeParameterSlot 0) []
      (.next (preparedEntry machine runtimeParameterSlot 1)) :=
  runtime_entry_runs (by decide) machine arguments

/-- Nominal entry is a distinct operation; a word bind cannot impersonate it. -/
def identity : NominalIdentity := ⟨"E".toUTF8,2⟩
example : ¬RuntimeEntryCode program [.nominal identity] := by decide
example : runtimeBind (.nominal identity) 0 = .enumBind identity 0 8 := rfl
example : RuntimeEntryCode (fun _ => some (.enumBind identity 0 8)) [.nominal identity] := by decide

end Aurora.SourceBinding.RuntimeEntryTests
