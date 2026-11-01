import SourceBinding.Stateful
open Aurora.SourceBinding
namespace StatefulFixtures

def base : Machine := ⟨0,some (.word 7),[],fun _ => none,fun _ => some (.word 0),fun _ => none⟩
def program : EffectProgram
  | 0 => some (.store .word 2)
  | 1 => some (.pure (.constant .boolean (.boolean false)))
  | 2 => some .require
  | _ => none

def stored : Machine := {base with pc := 1,receiver := fun index => if index = 2 then some (.word 7) else base.receiver index}
def failing : Machine := {stored with pc := 2,accumulator := some (.boolean false)}
example : effectStep program base = ⟨.next stored,[⟨2,.word 7⟩]⟩ := by rfl
example : effectStep program failing = ⟨.trap .assertion failing,[]⟩ := by rfl
example : EffectRuns program base [⟨2,.word 7⟩] (.trap .assertion failing) := by
  have last : EffectRuns program failing [] (.trap .assertion failing) := .trap rfl
  have second : EffectRuns program stored [] (.trap .assertion failing) := .next (events := []) rfl last
  exact .next (events := [⟨2,.word 7⟩]) rfl second
example : failing.receiver 2 = some (.word 7) := by rfl
example : effectStep (fun _ => some .require) {base with accumulator := some (.boolean true)} =
    ⟨.next {base with pc := 1,accumulator := none},[]⟩ := by rfl
example : effectStep (fun _ => some (.store .word 2)) {base with accumulator := some (.boolean true)} =
    ⟨.trap (.scalar .type) {base with accumulator := some (.boolean true)},[]⟩ := by rfl

#print axioms embedded_step_erases
#print axioms pure_runs_lift
#print axioms require_false_stops
#print axioms store_step
end StatefulFixtures
