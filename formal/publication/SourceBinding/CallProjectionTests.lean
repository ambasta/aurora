import SourceBinding.CallProjection
import SourceBinding.CallTests
open Aurora.SourceBinding Aurora.Publication
namespace CallProjectionFixtures
open CallFixtures IdentityFixtures
-- Isolated projection relations/programs; synthetic Tables are not artifact admission.
example (t : Tables) (targets : List CallTarget) (id : Int) :
    localProgram (canonicalCalls t targets) id = canonicalEffects t id := canonical_calls_local t targets id

#eval do
  let some ordinary := ordinary | throw (IO.userError "ordinary fixture")
  let some resource := retained | throw (IO.userError "resource fixture")
  let one := CallTarget.ordinary ordinary.target
  let duplicate := [one,one]
  let conflict := CallTarget.ordinary {ordinary.target with member := "other".toUTF8}
  let external := CallTarget.resource resource.target
  let candidates := [one,external]
  let cases : List (String × Bool × Bool) := [
    ("ordinary exact row",(resolveCall ordinaryTables candidates 0 0).isSome,true),
    ("resource exact row",(resolveCall resourceTables candidates 0 0).isSome,true),
    ("unlisted call rejected",(resolveCall ordinaryTables [] 0 0).isSome,false),
    ("duplicate identical descriptor accepted",(resolveCall ordinaryTables duplicate 0 0).isSome,true),
    ("matching descriptor conflict rejected",(resolveCall ordinaryTables [one,conflict] 0 0).isSome,false),
    ("reverse conflict also rejected",(resolveCall ordinaryTables [conflict,one] 0 0).isSome,false),
    ("finite compatibility accepts duplicates",decide (ProjectionCompatible ordinaryTables [0] duplicate),true),
    ("finite compatibility rejects conflict",decide (ProjectionCompatible ordinaryTables [0] [one,conflict]),false),
    ("wrong normalized PC rejected",(resolveCall {ordinaryTables with
      codes := ordinaryTables.codes.set! 0 (setInt callRow 1 1)} candidates 0 0).isSome,false),
    ("out of body rejected",(resolveCall ordinaryTables candidates 0 20).isSome,false),
    ("wrong callable rejected",(resolveCall ordinaryTables candidates 99 0).isSome,false)]
  for (label, actual, expected) in cases do
    unless actual == expected do throw (IO.userError s!"projection fixture failed: {label}")
  match canonicalCalls ordinaryTables duplicate 0 0 with
  | some (.ordinary target) => unless target == ordinary.target do throw (IO.userError "ordinary descriptor changed")
  | _ => throw (IO.userError "ordinary projection missing")
  match canonicalCalls resourceTables candidates 0 0 with
  | some (.resource target) => unless target == resource.target do throw (IO.userError "resource descriptor changed")
  | _ => throw (IO.userError "resource projection missing")
  match canonicalCalls simpleTables [one,conflict] 0 0 with
  | some (.local (.pure (.constant .boolean (.boolean true)))) => pure ()
  | _ => throw (IO.userError "local decoder changed by descriptors")
  match canonicalCalls {ordinaryTables with codes := ordinaryTables.codes.set! 0 (setInt callRow 6 999)} candidates 0 0 with
  | none => pure ()
  | _ => throw (IO.userError "unsupported row fabricated an operation")
  IO.println s!"NATIVE canonical call projection fixtures: {cases.length + 4} passed"
end CallProjectionFixtures
