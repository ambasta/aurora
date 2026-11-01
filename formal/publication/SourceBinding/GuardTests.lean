import SourceBinding.GuardCode
import SourceBinding.EntryBinding
open Aurora.SourceBinding
namespace GuardFixtures
-- Synthetic model fixtures; generic proofs, not these evaluations, cover states.
def expression : GuardExpr .boolean := .parameter .boolean "p".toUTF8 0
def formals : List Formal := [⟨"p".toUTF8,guardSourceType .boolean⟩]
def program : Program
  | 0 => some (.bind .boolean 0 8)
  | 1 => some (.load .boolean 8)
  | 2 => some (.branchFalse 5)
  | 3 => some (.constant .boolean (.boolean false))
  | 4 => some .ret
  | 5 => some .label
  | 6 => some (.jump 6) -- tail divergence must NOT be ruled out
  | _ => none
def slots (_ : Nat) := 8
def machine (b : Bool) : Machine := ⟨0,none,[],fun _ => none,fun _ => some (.word 7),fun _ => some (.boolean b)⟩
example : firstExitFuel program 6 6 (machine true) = some (.returned (.boolean false)) := by rfl
example : (firstExitFuel program 6 6 (machine false)).isSome = true := by rfl
#eval do
  unless (checkEntry program formals).isSome do throw (IO.userError "entry failed")
  let some code := checkGuardCode program slots expression 1 | throw (IO.userError "guard failed")
  unless code.endExpr == 2 do throw (IO.userError "guard endpoint moved")
  for bad in ([fun pc => if pc == 2 then some (.branchFalse 6) else program pc,
      fun pc => if pc == 3 then some (.constant .boolean (.boolean true)) else program pc,
      fun pc => if pc == 4 then some .label else program pc,
      fun pc => if pc == 5 then some .ret else program pc,
      fun pc => if pc == 1 then some (.load .boolean 16) else program pc] : List Program) do
    unless (checkGuardCode bad slots expression 1).isNone do throw (IO.userError "bad guard accepted")
  match firstExitFuel program 6 6 (machine true) with
  | some (.returned (.boolean false)) => pure ()
  | _ => throw (IO.userError "refusal result wrong")
  match firstExitFuel program 6 6 (machine false) with
  | some (.next state) =>
    unless state.pc == 6 && state.stack.isEmpty && (state.locals 8 == some (Value.boolean false)) &&
        (state.receiver 0 == some (Value.word 7)) do throw (IO.userError "continuation frame wrong")
  | _ => throw (IO.userError "continuation missing")
  IO.println "NATIVE entry/guard/first-exit fixtures: 9 passed; tail loop deliberately unexecuted"
end GuardFixtures
