import B.Basic
import B.Finish
namespace Aurora.B
open Aurora.A
variable {Agent : Type} {issuer subject : Agent}

private theorem put_retains {p : R.State Agent} {old new e : R.Entry Agent}
    (atChanged : p.entries changed = some old) (found : p.entries ticket = some e)
    (kind : new.kind = old.kind) (generation : new.generation = old.generation)
    (work : old.work ≤ new.work) :
    ∃ after, (R.put p changed new).entries ticket = some after ∧
      after.kind = e.kind ∧ after.generation = e.generation ∧ e.work ≤ after.work := by
  by_cases same : ticket = changed
  · subst ticket
    have equal : e = old := Option.some.inj (found.symm.trans atChanged)
    subst e
    exact ⟨new,by simp [R.put],kind,generation,work⟩
  · exact ⟨e,by simpa [R.put,same] using found,rfl,rfl,Nat.le_refl _⟩

/-- Existing entries retain identity and cannot lose work except through the
    actual finishOne transition at that same ticket. Closing is not finishing. -/
theorem retained_entry {s t : A.State Agent} (h : A.Invariant allocation s)
    (action : A.Step issuer subject allocation s event t)
    (found : s.protocol.entries ticket = some e) (notFinished : ¬ Finishes action ticket) :
    ∃ after, t.protocol.entries ticket = some after ∧
      after.kind = e.kind ∧ after.generation = e.generation ∧ e.work ≤ after.work := by
  have different : ticket ≠ s.protocol.next := by
    intro same
    subst ticket
    rw [R.next_absent h.protocol.1] at found
    cases found
  cases action with
  | root active available =>
    exact ⟨e,by simpa [mint,putGrant,atProtocol,R.enqueue,R.issue,R.put,different] using found,rfl,rfl,Nat.le_refl _⟩
  | request i nonce old grant destination footprint writable delegates he gate hg published closed fresh within delegation attenuate permission =>
    cases writable <;> exact ⟨e,found,rfl,rfl,Nat.le_refl _⟩
  | register r destination old owner payload packet absent he gate hp =>
    cases writable : payload.grant.writable <;>
      exact ⟨e,by simpa [writable,move,putGrant,atProtocol,R.enqueue,R.registerId,R.issue,R.put,different] using found,
        rfl,rfl,Nat.le_refl _⟩
  | activate i old destination grant packet he transfer pending hg =>
    have retained := put_retains he found (new := R.resolved old s.protocol.next) rfl rfl (Nat.le_refl _)
    obtain ⟨after,ha,hk,hg,hw⟩ := retained
    cases writable : grant.writable <;>
      exact ⟨after,by simpa [writable,move,readEnable,putGrant,atProtocol,R.enqueue,R.issue,R.put,different] using ha,hk,hg,hw⟩
  | submit i old grant he use hg published closed sequential =>
    exact put_retains he found rfl rfl (Nat.le_succ _)
  | effect => exact ⟨e,found,rfl,rfl,Nat.le_refl _⟩
  | returnUse => exact ⟨e,found,rfl,rfl,Nat.le_refl _⟩
  | freeze => exact ⟨e,found,rfl,rfl,Nat.le_refl _⟩
  | reuse => exact ⟨e,found,rfl,rfl,Nat.le_refl _⟩
  | refuse => exact ⟨e,found,rfl,rfl,Nat.le_refl _⟩
  | passive p operation =>
    cases operation <;> try exact ⟨e,found,rfl,rfl,Nat.le_refl _⟩
    case finishOne i n old owner he use work =>
      by_cases same : ticket = i
      · subst ticket
        exact False.elim (notFinished (.finish _ _ _ _ _ he use work))
      · exact ⟨e,by simpa [atProtocol,R.put,same] using found,rfl,rfl,Nat.le_refl _⟩
    all_goals apply put_retains <;> first | assumption | rfl | exact Nat.le_refl _

/-- Grant identity and work retention are derived from the actual protocol step;
    no post-state Authorized premise or close-before-drain prohibition is used. -/
theorem Authorized.retained {s t : A.State Agent} (h : A.Invariant allocation s)
    (action : A.Step issuer subject allocation s event t)
    (authorized : Authorized s ticket d) (notFinished : ¬ Finishes action ticket) :
    Authorized t ticket d := by
  obtain ⟨e,g,found,grant,kind,work,writer,generation,range⟩ := authorized
  obtain ⟨after,ha,hk,hg,hw⟩ := retained_entry h action found notFinished
  exact ⟨after,g,ha,A.step_preserves_grant h action grant,hk.trans kind,
    Nat.lt_of_lt_of_le work hw,writer,hg.trans generation,range⟩
end Aurora.B
