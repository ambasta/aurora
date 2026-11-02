import SourceBinding.RuntimeBodyPublic
namespace Aurora.SourceBinding.RuntimeBodyExecutionTests

/-- Small source rules retain their exact current state at return/fault, even
    when it contains an active nested scope. No cleanup state is substituted. -/
example (cursor : LocalContext) (state : RuntimeLocals) :
    RuntimeStatementsEvaluate [] [] [] [] [] (.scalar .word) cursor state
      [.returnValue (.word 7)] cursor (.returned (.word 7) state) [] := by
  apply RuntimeStatementsEvaluation.returned (middle := cursor)
  · exact .returnValue .word
  · exact .nil
example (cursor : LocalContext) (state : RuntimeLocals) :
    RuntimeStatementsEvaluate [] [] [] [] [] (.scalar .word) cursor state
      [.returnValue (.binary .shift (.word 4294967296) (.signedCount 32))] cursor (.trapped .overflow state) [] := by
  apply RuntimeStatementsEvaluation.trapped (middle := cursor)
  · exact .returnFault (.shiftLeft .word .thirtyTwo)
  · exact .nil

private def program (condition : Bool) : CallProgram := fun _ pc =>
  (([.pure (.constant .word (.word 1)),.localStore (.scalar .word) 8,
    .pure (.constant .boolean (.boolean condition)),.pure (.branchFalse 9),
    .pure (.constant .word (.word 2)),.localStore (.scalar .word) 8,
    .pure (.constant .word (.word 7)),.localStore (.scalar .word) 16,
    .pure (.jump 10),.pure .label,.pure .label,.pure (.load .word 8),.pure .ret] : List EffectOp)[pc]?).map .local
private def faultProgram : CallProgram := fun _ pc =>
  (([.pure (.constant .word (.word 1)),.localStore (.scalar .word) 8,
    .pure (.constant .word (.word 4294967296)),.pure .push,.pure .count32,
    .pure (.binary .leftShift),.localStore (.scalar .word) 8,.pure .ret] : List EffectOp)[pc]?).map .local
private def earlyProgram : CallProgram := fun _ pc =>
  (([.pure (.constant .word (.word 7)),.pure .ret,
    .pure (.constant .word (.word 2)),.localStore (.scalar .word) 16] : List EffectOp)[pc]?).map .local
private def initial : ActiveCall Nat :=
  ⟨0,⟨0,none,[],fun _ => none,fun _ => none⟩,[],⟨fun _ => none,55⟩⟩
private def run (code : CallProgram) : Nat → CallPhase Nat Nat → CallPhase Nat Nat × List (CallEvent Nat Nat)
  | 0, phase => (phase,[])
  | fuel+1, .running active =>
    let step := callStep code active
    let rest := run code fuel step.1
    (rest.1,step.2 ++ rest.2)
  | _+1, phase => (phase,[])
private def expect (value : Bool) (label : String) : IO Unit :=
  unless value do throw (IO.userError label)

-- Synthetic whole local-body executions of the SAME machine, not byte-backed
-- publication acceptance. Local stores are private and emit no receiver event.
#eval do
  for condition in [true,false] do
    match run (program condition) 20 (.running initial) with
    | (.returned (.word value) active,[]) =>
      expect (value == (if condition then 2 else 1) && active.frame.locals 8 == some (Value.word value))
        "normal branch lost current mutable local"
      expect (active.frame.locals 16 == (if condition then some (Value.word 7) else none))
        "skipped branch initialized a local or continuing branch rolled back"
      expect (active.shared.world == 55 && active.saved.isEmpty) "local body changed shared/caller state"
    | _ => throw (IO.userError "branch body did not return normally")
  match run faultProgram 20 (.running initial) with
  | (.trapped (.local (.scalar .overflow)) active,[]) =>
    expect (active.frame.pc == 5 && active.frame.locals 8 == some (Value.word 1) &&
      active.frame.stack == [Value.word 4294967296]) "first fault rolled back or executed later assignment"
  | _ => throw (IO.userError "missing first-fault outcome")
  match run earlyProgram 20 (.running initial) with
  | (.returned (.word 7) active,[]) =>
    expect (active.frame.pc == 1 && (active.frame.locals 16).isNone) "early return executed dead suffix"
  | _ => throw (IO.userError "missing early return")
  IO.println "runtime whole-body execution controls: 4 passed"

end Aurora.SourceBinding.RuntimeBodyExecutionTests
