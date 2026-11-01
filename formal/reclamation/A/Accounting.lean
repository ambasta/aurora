import A.Model
namespace Aurora.A

/-- Erases ONLY non-gate protocol accounting. Endpoint-local free inventory,
read permission and every operational guard field remain observable here. -/
structure OperationalEq (s t : State Agent) : Prop where
  protocol : s.protocol = t.protocol
  grants : s.grants = t.grants
  payloads : s.payloads = t.payloads
  readable : s.readable = t.readable
  issued : s.issued = t.issued
  returned : s.returned = t.returned
  gates : ∀ generation i, s.holdings generation (.gate i) = t.holdings generation (.gate i)

namespace OperationalEq
variable {s t : State Agent}
theorem refl (s : State Agent) : OperationalEq s s := ⟨rfl,rfl,rfl,rfl,rfl,rfl,fun _ _ => rfl⟩
theorem atProtocol (h : OperationalEq s t) (p : R.State Agent) :
    OperationalEq (Aurora.A.atProtocol s p) (Aurora.A.atProtocol t p) :=
  ⟨rfl,h.grants,h.payloads,h.readable,h.issued,h.returned,h.gates⟩
theorem putGrant (h : OperationalEq s t) (i : Nat) (g : Grant Agent) :
    OperationalEq (Aurora.A.putGrant s i g) (Aurora.A.putGrant t i g) := by
  constructor
  · exact h.protocol
  · simp only [Aurora.A.putGrant, h.grants]
  · exact h.payloads
  · exact h.readable
  · exact h.issued
  · exact h.returned
  · exact h.gates
theorem putPayload (h : OperationalEq s t) (r : R.RequestId) (p : Payload Agent) :
    OperationalEq (Aurora.A.putPayload s r p) (Aurora.A.putPayload t r p) := by
  constructor
  · exact h.protocol
  · exact h.grants
  · simp only [Aurora.A.putPayload, h.payloads]
  · exact h.readable
  · exact h.issued
  · exact h.returned
  · exact h.gates
theorem move (h : OperationalEq s t) (generation : Nat) (source destination : Location) (f : Footprint) :
    OperationalEq (Aurora.A.move s generation source destination f)
      (Aurora.A.move t generation source destination f) := by
  refine ⟨h.protocol,h.grants,h.payloads,h.readable,h.issued,h.returned,?_⟩
  intro gen i
  by_cases same : gen = generation
  · simp [Aurora.A.move,same,Inventory.move,h.gates]
  · simp [Aurora.A.move,same,h.gates]
theorem mint (h : OperationalEq s t) (generation gate : Nat) (f : Footprint) :
    OperationalEq (Aurora.A.mint s generation gate f) (Aurora.A.mint t generation gate f) := by
  refine ⟨h.protocol,h.grants,h.payloads,h.readable,?_,h.returned,?_⟩
  · simp only [Aurora.A.mint,h.issued]
  · intro gen i; simp [Aurora.A.mint,h.gates]
theorem readEnable (h : OperationalEq s t) (i : Nat) (f : Footprint) :
    OperationalEq (Aurora.A.readEnable s i f) (Aurora.A.readEnable t i f) := by
  refine ⟨h.protocol,h.grants,h.payloads,?_,h.issued,h.returned,h.gates⟩
  simp only [Aurora.A.readEnable,h.readable]
theorem markReturned (h : OperationalEq s t) (i : Nat) :
    OperationalEq (Aurora.A.markReturned s i) (Aurora.A.markReturned t i) := by
  refine ⟨h.protocol,h.grants,h.payloads,h.readable,h.issued,?_,h.gates⟩
  simp only [Aurora.A.markReturned,h.returned]
end OperationalEq

/-- Accounting is incapable of suppressing an operational transition. This
holds for arbitrary (even unreachable or inconsistent) states, not only states
satisfying the authority invariant. Destination credits use immutable payloads. -/
theorem accounting_noninterference (same : OperationalEq s s')
    (step : Step issuer initialSubject allocation s event t) :
    ∃ t', Step issuer initialSubject allocation s' event t' ∧ OperationalEq t t' := by
  cases step with
  | root active available =>
    have hs := Step.root (issuer := issuer) (initialSubject := initialSubject) (allocation := allocation) s'
      (by simpa [←same.protocol] using active) (by simpa [←same.protocol,←same.issued] using available)
    refine ⟨_,hs,?_⟩
    simpa only [←same.protocol] using ((same.atProtocol _).putGrant _ _).mint _ _ _
  | request i nonce e g destination footprint writable delegates found gate granted published notClosed fresh within delegation attenuate permission =>
    have perm : if writable then g.writable = true ∧ footprint.Within (s'.holdings g.generation (.gate i))
        else footprint.Within (s'.readable i) := by
      cases writable <;> simpa [←same.gates,←same.readable] using permission
    have hs := Step.request (issuer := issuer) (initialSubject := initialSubject) (allocation := allocation)
      s' i nonce e g destination footprint writable delegates
      (by simpa [←same.protocol] using found) gate (by simpa [←same.grants] using granted)
      published notClosed (by simpa [←same.protocol] using fresh) within delegation attenuate perm
    refine ⟨_,hs,?_⟩
    cases writable
    · simpa only [Bool.false_eq_true, ↓reduceIte, ←same.protocol] using (same.atProtocol _).putPayload _ _
    · simpa only [↓reduceIte, ←same.protocol] using ((same.atProtocol _).putPayload _ _).move _ _ _ _
  | register r destination e a p packet absent found gate payload =>
    have hs := Step.register (issuer := issuer) (initialSubject := initialSubject) (allocation := allocation)
      s' r destination e a p (by simpa [←same.protocol] using packet)
      (by simpa [←same.protocol] using absent) (by simpa [←same.protocol] using found) gate
      (by simpa [←same.payloads] using payload)
    refine ⟨_,hs,?_⟩
    cases writable : p.grant.writable
    · simpa only [writable, Bool.false_eq_true, ↓reduceIte, ←same.protocol] using (same.atProtocol _).putGrant _ _
    · simpa only [writable, ↓reduceIte, ←same.protocol] using ((same.atProtocol _).putGrant _ _).move _ _ _ _
  | activate i e destination g packet found transfer pending granted =>
    have hs := Step.activate (issuer := issuer) (initialSubject := initialSubject) (allocation := allocation)
      s' i e destination g (by simpa [←same.protocol] using packet)
      (by simpa [←same.protocol] using found) transfer pending (by simpa [←same.grants] using granted)
    refine ⟨_,hs,?_⟩
    cases writable : g.writable
    · simpa only [writable, Bool.false_eq_true, ↓reduceIte, ←same.protocol] using ((same.atProtocol _).putGrant _ _).readEnable _ _
    · simpa only [writable, ↓reduceIte, ←same.protocol] using ((same.atProtocol _).putGrant _ _).move _ _ _ _
  | submit i e g found use granted published notClosed sequential =>
    have hs := Step.submit (issuer := issuer) (initialSubject := initialSubject) (allocation := allocation)
      s' i e g (by simpa [←same.protocol] using found) use (by simpa [←same.grants] using granted)
      published notClosed sequential
    exact ⟨_,hs,by simpa only [←same.protocol] using same.atProtocol _⟩
  | effect i e g cell found use granted work within =>
    exact ⟨_,Step.effect s' i e g cell (by simpa [←same.protocol] using found) use
      (by simpa [←same.grants] using granted) work within,same⟩
  | returnUse r i e p registered payload writer origin found use bound receipt fresh =>
    have hs := Step.returnUse (issuer := issuer) (initialSubject := initialSubject) (allocation := allocation)
      s' r i e p (by simpa [←same.protocol] using registered) (by simpa [←same.payloads] using payload)
      writer origin (by simpa [←same.protocol] using found) use bound receipt (by simpa [←same.returned] using fresh)
    exact ⟨_,hs,(same.move _ _ _ _).markReturned _⟩
  | freeze i e g footprint found gate granted within available =>
    have hs := Step.freeze (issuer := issuer) (initialSubject := initialSubject) (allocation := allocation)
      s' i e g footprint (by simpa [←same.protocol] using found) gate (by simpa [←same.grants] using granted)
      within (by simpa [←same.gates] using available)
    exact ⟨_,hs,(same.move _ _ _ _).readEnable _ _⟩
  | passive p operation =>
    exact ⟨_,Step.passive s' p (by simpa [←same.protocol] using operation),same.atProtocol _⟩
  | reuse quiet =>
    have hs := Step.reuse (issuer := issuer) (initialSubject := initialSubject) (allocation := allocation)
      s' (by simpa [←same.protocol] using quiet)
    refine ⟨_,by simpa only [←same.protocol] using hs,?_⟩
    simpa only [←same.protocol] using same.atProtocol _
  | refuse => exact ⟨s',Step.refuse s',same⟩
end Aurora.A
