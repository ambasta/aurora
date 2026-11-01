import B.Basic
namespace Aurora.B

def NoReuse : Event → Prop
  | .protocol (.reuse _) => False
  | _ => True

theorem a_generation (step : A.Step issuer subject allocation s event t)
    (notReuse : ∀ generation, event ≠ .reuse generation) : t.protocol.generation = s.protocol.generation := by
  cases step with
  | passive p op => cases op <;> rfl
  | reuse quiet => exact False.elim (notReuse _ rfl)
  | root | submit | effect | returnUse | freeze | refuse => rfl
  | request | register | activate => dsimp; split <;> rfl

theorem step_generation (step : Step issuer subject config s event t) (noReuse : NoReuse event) :
    t.authority.protocol.generation = s.authority.protocol.generation := by
  cases step with
  | protocol next event action nonwrite held =>
    apply a_generation action
    intro generation equal
    subst event
    exact False.elim noReuse
  | write next generation ticket cell value action idle => exact a_generation action (by intro old bad; cases bad)
  | beginCopy | payload | control | fault | release => rfl

theorem trace_generation (trace : Trace issuer subject config s events t)
    (noReuse : ∀ event ∈ events, NoReuse event) :
    t.authority.protocol.generation = s.authority.protocol.generation := by
  induction trace with
  | nil => rfl
  | cons step tail ih =>
    exact (ih (fun event member => noReuse event (List.mem_cons_of_mem _ member))).trans
      (step_generation step (noReuse _ List.mem_cons_self))
end Aurora.B
