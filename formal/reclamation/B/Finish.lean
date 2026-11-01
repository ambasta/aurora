import B.Model
namespace Aurora.B

theorem Finishes.decreases {action : A.Step issuer subject allocation before event after}
    (finish : Finishes action ticket) : ∃ e f, before.protocol.entries ticket = some e ∧
      after.protocol.entries ticket = some f ∧ f.work < e.work := by
  cases finish with
  | finish before n e owner found use work =>
    refine ⟨e,{e with work := n},found,?_,?_⟩
    · simp [A.atProtocol,R.put]
    · dsimp; omega

theorem no_finish_of_nondecreasing {action : A.Step issuer subject allocation before event after}
    (preserves : ∀ i e, before.protocol.entries i = some e →
      ∃ f, after.protocol.entries i = some f ∧ e.work ≤ f.work) : ¬ Finishes action ticket := by
  intro finish
  obtain ⟨e,f,found,afterFound,decreased⟩ := finish.decreases
  obtain ⟨g,afterAgain,increased⟩ := preserves ticket e found
  have same : f = g := Option.some.inj (afterFound.symm.trans afterAgain)
  subst g
  omega
end Aurora.B
