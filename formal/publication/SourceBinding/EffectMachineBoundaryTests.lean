import SourceBinding.EffectResourceStepProof
namespace Aurora.SourceBinding.EffectMachineBoundaryTests

/- Small SAME-machine controls only, not canonical method admission or native
   bank implementation tests. Responses deliberately replace shared state. -/
private def target : ResourceDescriptor :=
  ⟨"words".toUTF8,3,0,["builtin".toUTF8,"OwnedWords".toUTF8],0,2,"set".toUTF8,
    [.word,.word],.boolean,1,2,1,"__set".toUTF8⟩
private def initial : ActiveCall Nat :=
  ⟨7,⟨0,none,[.word 25,.word 1,.word 99],fun _ => none,fun _ => some (.word 11)⟩,
    [],⟨fun _ => none,10⟩⟩
private def after : CallShared Nat := ⟨fun _ => some (.word 88),20⟩
private def program (consumer : EffectOp) : CallProgram := fun _ pc =>
  ([.resource target,.local consumer] : List CallOp)[pc]?
private def expect (condition : Bool) (message : String) : IO Unit :=
  unless condition do throw (IO.userError message)

#eval do
  let (.waiting pending,[.externalInvoke request]) :=
    callStep (program .require) initial (ExternalFault := Nat)
    | throw (IO.userError "resource did not produce genuine waiting phase")
  expect (request.arguments == [Value.word 1,Value.word 25] && request.before.world == 10 &&
    pending.continuation.pc == 1 && pending.continuation.stack == [Value.word 99])
    "pending frozen request/consumed private continuation"
  for (raw,expected) in [(some (Value.boolean false),EffectFault.assertion),
      (none,EffectFault.scalar .type),(some (Value.word 1),EffectFault.scalar .type)] do
    let (.running resumed,[.externalReturn returned shared]) :=
      resumeCall pending (.returned raw : ExternalOutcome Nat) after
      | throw (IO.userError "raw response validated before consumer")
    expect (returned == raw && shared.world == 20 && resumed.frame.accumulator == raw)
      "resume preserves raw response and changed shared state"
    let (.trapped (.local fault) active,[]) := callStep (program .require) resumed (ExternalFault := Nat)
      | throw (IO.userError "require accepted false/missing/wrong-kind response")
    expect (fault == expected && active.shared.world == 20 && active.shared.receiver 0 == some (Value.word 88) &&
      active.frame.pc == 1 && active.frame.stack == [Value.word 99] && active.frame.locals 8 == none)
      "require fault rolled back shared state or changed private continuation"
  for raw in [none,some (Value.boolean true),some (Value.word 37)] do
    let (.running resumed,_) := resumeCall pending (.returned raw : ExternalOutcome Nat) after
      | throw (IO.userError "initializer response did not resume")
    let observed := callStep (program (.localStore (.scalar .word) 8)) resumed (ExternalFault := Nat)
    match raw,observed with
    | some (.word 37),(.running active,[]) =>
      expect (active.frame.pc == 2 && active.frame.locals 8 == some (Value.word 37) &&
        active.frame.locals 16 == none && active.frame.arguments 0 == some (Value.word 11) &&
        active.shared.world == 20 && active.shared.receiver 0 == some (Value.word 88))
        "successful initializer did not preserve shared/private framing"
    | _,(.trapped (.local (.scalar .type)) active,[]) =>
      expect (active.frame.locals 8 == none && active.frame.pc == 1 && active.shared.world == 20 &&
        active.shared.receiver 0 == some (Value.word 88)) "initializer fault rolled back response"
    | _,_ => throw (IO.userError "initializer consumer classification")
  let (.trapped (.external reason) active,[.externalFault eventReason shared]) :=
    resumeCall pending (.fault 17) after
    | throw (IO.userError "external fault did not retain actual continuation")
  expect (reason == 17 && eventReason == 17 && shared.world == 20 && active.shared.world == 20 &&
    active.shared.receiver 0 == some (Value.word 88) && active.frame.pc == 1 &&
    active.frame.stack == [Value.word 99] && active.frame.locals 8 == none)
    "external fault fabricated unwind/consumer or restored old shared state"

end Aurora.SourceBinding.EffectMachineBoundaryTests
