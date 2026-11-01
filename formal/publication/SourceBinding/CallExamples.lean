import SourceBinding.CallBinding
import SourceBinding.CallGuardPrefix
namespace Aurora.SourceBinding
open Aurora.Publication

-- Workload fixtures only; no names or expected policy values enter the checker.
private def named (decls : List Formal) (name : String) (kind : GuardType) : IO Nat := do
  match decls.zipIdx.filter (fun pair => pair.1.name == name.toUTF8) with
  | [(decl,index)] =>
    unless decl.type == guardSourceType kind do throw (IO.userError s!"call fixture type: {name}")
    return index
  | _ => throw (IO.userError s!"call fixture declaration: {name}")

private def defaults (decls : List Formal) (index : Nat) : Option Value := do
  let decl ← decls[index]?
  if decl.type == guardSourceType .word then return .word 0
  if decl.type == guardSourceType .boolean then return .boolean false
  none

private def sharedEq (count : Nat) (a b : CallShared Nat) : Bool :=
  a.world == b.world && (List.range count).all (fun index => a.receiver index == b.receiver index)
private def requestEq (count : Nat) (a b : ExternalRequest Nat) : Bool :=
  a.target == b.target && a.arguments == b.arguments && sharedEq count a.before b.before
private def eventEq (count : Nat) : CallEvent Nat Nat → CallEvent Nat Nat → Bool
  | .store a,.store b => a == b
  | .ordinaryInvoke a av,.ordinaryInvoke b bv => a == b && av == bv
  | .ordinaryReturn a av,.ordinaryReturn b bv => a == b && av == bv
  | .externalInvoke a,.externalInvoke b => requestEq count a b
  | .externalReturn a av,.externalReturn b bv => a == b && sharedEq count av bv
  | .externalFault a av,.externalFault b bv => a == b && sharedEq count av bv
  | _,_ => false
private def eventsEq (count : Nat) (a b : List (CallEvent Nat Nat)) : Bool :=
  a.length == b.length && (a.zip b).all (fun pair => eventEq count pair.1 pair.2)
private def faultEq : CallFault Nat → CallFault Nat → Bool
  | .local a,.local b => a == b
  | .external a,.external b => a == b
  | _,_ => false
private def boundaryEq (count : Nat) : SourceCallPhase Nat Nat → CallPhase Nat Nat → Bool
  | .waiting a,.waiting b => requestEq count a.request b.request
  | .returned a av,.returned b bv => a == b && sharedEq count av bv.shared
  | .trapped a av,.trapped b bv => faultEq a b && sharedEq count av bv.shared
  | _,_ => false

-- Fuel bounds are fixture failure limits, not termination proof premises.
private def sourceRun (program : SourceCallProgram) : Nat → SourceCallPhase Nat Nat →
    Option (List (CallEvent Nat Nat) × SourceCallPhase Nat Nat)
  | 0,_ => none
  | fuel + 1,.running active => do
    let (next,events) := sourceCallStep program active
    let (later,final) ← sourceRun program fuel next
    return (events ++ later,final)
  | _ ,final => some ([],final)
private def machineRun (program : CallProgram) : Nat → CallPhase Nat Nat →
    Option (List (CallEvent Nat Nat) × CallPhase Nat Nat)
  | 0,_ => none
  | fuel + 1,.running active => do
    let (next,events) := callStep program active
    let (later,final) ← machineRun program fuel next
    return (events ++ later,final)
  | _,final => some ([],final)

private def paired (checked : CallBinding files root module path member bytes) (count : Nat)
    (source : SourceCallPhase Nat Nat) (machine : CallPhase Nat Nat) :
    IO (List (CallEvent Nat Nat) × SourceCallPhase Nat Nat × CallPhase Nat Nat) := do
  let some (se,sf) := sourceRun checked.family.sourceBodies 1024 source | throw (IO.userError "source fixture fuel")
  let some (me,mf) := machineRun checked.family.program 4096 machine | throw (IO.userError "IR fixture fuel")
  unless eventsEq count se me && boundaryEq count sf mf do throw (IO.userError "call paired boundary/trace mismatch")
  return (se,sf,mf)

/-- Actual selected AST and actual canonical IR, with identical explicit external
    responses. All declared optional receiver entries and abstract world are compared.
    Opaque None entries do not model native resource representation or validity. -/
def runCallExamples (checked : CallBinding files root module path member bytes) : IO Unit := do
  let some _guardPrefix := checkGuardedCallPrefix checked | throw (IO.userError "guard/callee footprint profile rejected")
  IO.println "CALL-GUARD-PREFIX actual source shape and disjoint leaf writes checked; pre-external only"
  let selected := checked.family.shape.selected.selected
  unless selected.method.function.name == "fill_snapshot".toUTF8 do throw (IO.userError "call examples require fill_snapshot")
  let decls := fields selected.classDecl.members
  let formals := selected.method.function.formals
  let phase ← named decls "snapshot_phase" .word
  let epochField ← named decls "snapshot_epoch" .word
  let size ← named decls "snapshot_bytes" .word
  let initialized ← named decls "initialized" .boolean
  let operation ← named decls "operation" .word
  let active ← named decls "active_slot" .word
  let staged ← named decls "staged_count" .word
  let epoch ← named formals "epoch" .word
  let offset ← named formals "offset" .word
  let count ← named formals "count" .word
  let receiver := fun index =>
    if index == phase then some (.word 1) else if index == epochField then some (.word 7)
    else if index == size then some (.word 64) else if index == initialized then some (.boolean true)
    else if index == active then some (.word 3) else defaults decls index
  let arguments := fun index => if index == epoch then some (.word 7)
    else if index == offset then some (.word 8) else if index == count then some (.word 16) else none
  let base : Machine := ⟨0,none,[],fun _ => none,receiver,arguments⟩
  let start := fun base => paired checked decls.length (.running (checked.sourceInitial 10 base))
    (.running (checked.machineInitial 10 base))
  let (refusal,rf,_) ← start {base with receiver := fun i => if i == phase then some (.word 0) else receiver i}
  unless refusal.isEmpty && (match rf with | .returned (.boolean false) _ => true | _ => false) do
    throw (IO.userError "guard refusal performed effects")
  let (failure,ff,_) ← start {base with receiver := fun i => if i == initialized then some (.boolean false) else receiver i}
  unless failure.length == 1 && (match ff with | .trapped (.local .assertion) _ => true | _ => false) do
    throw (IO.userError "enter failure control")
  let (before,sf,mf) ← start base
  let .waiting source := sf | throw (IO.userError "source did not suspend")
  let .waiting machine := mf | throw (IO.userError "IR did not suspend")
  unless source.request.arguments == [.word 7,.word 8,.word 0,.word 16] do
    throw (IO.userError "external argument order")
  let stores := before.filterMap (fun event => match event with | .store store => some store | _ => none)
  unless stores == [⟨active,.word 2⟩,⟨operation,.word 1⟩] && before.length == 5 do
    throw (IO.userError "enter ordered trace")
  let cases : List (String × ExternalOutcome Nat × Nat) := [
    ("true",.returned (some (.boolean true)),0),
    ("false",.returned (some (.boolean false)),0),
    ("none",.returned none,0), ("wrong-kind",.returned (some (.word 9)),0),
    ("external-fault",.fault 99,0),
    ("true-mutated-leave-refusal",.returned (some (.boolean true)),1),
    ("true-malformed-leave-field",.returned (some (.boolean true)),2),
    ("true-inactive-leave",.returned (some (.boolean true)),3)]
  for (label,outcome,mutation) in cases do
    let after : CallShared Nat := ⟨fun i =>
      if i == epochField then some (.word 99)
      else if mutation == 1 && i == staged then some (.word 1)
      else if mutation == 2 && i == operation then none
      else if mutation == 3 && i == operation then some (.word 0)
      else source.request.before.receiver i,20⟩
    let (sn,se) := sourceResume source outcome after
    let (mn,me) := resumeCall machine outcome after
    unless eventsEq decls.length se me do throw (IO.userError "resume event mismatch")
    let (later,final,actual) ← paired checked decls.length sn mn
    let success := label == "true"
    let expectedFault : CallFault Nat := match outcome with
      | .fault n => .external n
      | .returned (some (.boolean _)) => if mutation == 2 then .local (.scalar .type) else .local .assertion
      | _ => .local (.scalar .type)
    unless (match final with
      | .returned (.boolean true) _ => success
      | .trapped fault _ => !success && faultEq fault expectedFault
      | _ => false) do throw (IO.userError s!"call outcome: {label}")
    let finalShared := actual.shared
    unless finalShared.world == 20 && finalShared.receiver epochField == some (.word 99) do
      throw (IO.userError "external mutation rolled back")
    let laterStores := later.filterMap (fun event => match event with | .store store => some store | _ => none)
    let expectedStores : List StoreEvent := if success then [⟨operation,.word 0⟩,⟨active,.word 3⟩] else []
    unless laterStores == expectedStores && later.length == (if success then 4 else if mutation != 0 then 1 else 0) do
      throw (IO.userError s!"leave trace: {label}")
    unless success || finalShared.receiver operation == after.receiver operation do
      throw (IO.userError "failure rolled back enter")
    IO.println s!"CALL-EXAMPLE {label} exact_trace=true receiver_entries={decls.length} world=true"
  IO.println "CALL-EXAMPLES 11 controls: refusal, enter fault, suspension, eight SAME-request responses. Waiting is not automatically blocked/divergent; no external frame assumed."
end Aurora.SourceBinding
