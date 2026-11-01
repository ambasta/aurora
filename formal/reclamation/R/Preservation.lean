import R.Simulation
namespace Aurora.R

variable {s : State Agent}

private theorem valid_enqueue (s : State Agent) (p q : Packet Agent) :
    PacketValid (enqueue s p) q ↔ PacketValid s q := by cases q <;> rfl

theorem local_enqueue (h : LocalInvariant s) (valid : PacketValid s p) :
    LocalInvariant (enqueue s p) := by
  constructor
  · exact h.requestSource
  · exact h.settledRegistered
  · exact h.sealedSafe
  · exact h.gateBarrier
  · exact h.transferSeal
  · intro q hq
    have hq' : q = p ∨ q ∈ s.packets := by simpa [enqueue] using hq
    apply (valid_enqueue s p q).mpr
    rcases hq' with rfl | hq'
    · exact valid
    · exact h.packetsValid q hq'

private theorem put_other (s : State Agent) (i j : Nat) (e : Entry Agent)
    (different : j ≠ i) : (put s i e).entries j = s.entries j := by simp [put, different]

/-- Frame rule for changing one existing endpoint/coordinator record. The new
local facts are operational proof obligations; no projected target invariant. -/
theorem local_put (h : LocalInvariant s) (found : s.entries i = some old)
    (sameKind : new.kind = old.kind) (sameGeneration : new.generation = old.generation)
    (monotone : old.sealed = true → new.sealed = true)
    (safe : new.sealed = true → new.closed = true ∧
      (∀ a, new.kind = .use a → new.work = 0))
    (barrier : ∀ a, new.kind = .gate a → new.sealed = true → Settled s i)
    (transfer : ∀ a, new.kind = .transfer a → new.sealed = new.receiver.isSome) :
    LocalInvariant (put s i new) := by
  constructor
  · intro r q hq
    obtain ⟨e, a, he, hk⟩ := h.requestSource r q hq
    by_cases same : r.1 = i
    · rw [same, found] at he
      cases he
      exact ⟨new, a, by simp [put, same], sameKind.trans hk⟩
    · exact ⟨e, a, by simpa [put, same] using he, hk⟩
  · exact h.settledRegistered
  · intro j e he hs
    by_cases same : j = i
    · subst j
      simp [put] at he
      subst e
      exact safe hs
    · rw [put_other s i j new same] at he
      exact h.sealedSafe j e he hs
  · intro j e a he hk hs
    by_cases same : j = i
    · subst j
      simp [put] at he
      subst e
      exact barrier a hk hs
    · rw [put_other s i j new same] at he
      exact h.gateBarrier j e a he hk hs
  · intro j e a he hk
    by_cases same : j = i
    · subst j
      simp [put] at he
      subst e
      exact transfer a hk
    · rw [put_other s i j new same] at he
      exact h.transferSeal j e a he hk
  · intro p hp
    have valid := h.packetsValid p hp
    cases p with
    | register r d => exact valid
    | grant r j => exact valid
    | publish j => trivial
    | activate j => trivial
    | close j => trivial
    | receipt g j =>
      obtain ⟨e, he, hg, hs⟩ := valid
      by_cases same : j = i
      · subst j
        rw [found] at he
        cases he
        exact ⟨new, by simp [put], sameGeneration.trans hg, monotone hs⟩
      · exact ⟨e, by simpa [put, same] using he, hg, hs⟩

/-- Fresh allocation cannot replace an old receipt or pending source. -/
theorem local_issue (h : LocalInvariant s) (absent : s.entries s.next = none)
    (generation : Nat) (kind : Q.Kind Agent) :
    LocalInvariant (issue s generation kind) := by
  constructor
  · intro r q hq
    obtain ⟨e, a, he, hk⟩ := h.requestSource r q hq
    have different : r.1 ≠ s.next := by intro eq; rw [eq, absent] at he; contradiction
    exact ⟨e, a, by simpa [issue, put, different] using he, hk⟩
  · exact h.settledRegistered
  · intro i e he hs
    by_cases same : i = s.next
    · subst i
      simp [issue, put] at he
      subst e
      contradiction
    · simp [issue, put, same] at he
      exact h.sealedSafe i e he hs
  · intro i e a he hk hs
    by_cases same : i = s.next
    · subst i
      simp [issue, put] at he
      subst e
      contradiction
    · simp [issue, put, same] at he
      exact h.gateBarrier i e a he hk hs
  · intro i e a he hk
    by_cases same : i = s.next
    · subst i
      simp [issue, put] at he
      subst e
      rfl
    · simp [issue, put, same] at he
      exact h.transferSeal i e a he hk
  · intro p hp
    have valid := h.packetsValid p hp
    cases p with
    | register r d => exact valid
    | grant r j => exact valid
    | publish j => trivial
    | activate j => trivial
    | close j => trivial
    | receipt g j =>
      obtain ⟨e, he, hg, hs⟩ := valid
      have different : j ≠ s.next := by intro eq; rw [eq, absent] at he; contradiction
      exact ⟨e, by simpa [issue, put, different] using he, hg, hs⟩

/-- Dedup registration grows only at an absent key. -/
theorem local_registerId (h : LocalInvariant s) (absent : s.registrations r = none)
    (i : Nat) : LocalInvariant (registerId s r i) := by
  constructor
  · exact h.requestSource
  · intro a q hq hs
    obtain ⟨j, hj⟩ := h.settledRegistered a q hq hs
    have different : a ≠ r := by intro eq; rw [eq, absent] at hj; contradiction
    exact ⟨j, by simpa [registerId, different] using hj⟩
  · exact h.sealedSafe
  · exact h.gateBarrier
  · exact h.transferSeal
  · intro p hp
    have valid := h.packetsValid p hp
    cases p with
    | register a d => exact valid
    | grant a j =>
      obtain ⟨hq, hj⟩ := valid
      have different : a ≠ r := by intro eq; rw [eq, absent] at hj; contradiction
      exact ⟨hq, by simpa [registerId, different] using hj⟩
    | publish j => trivial
    | activate j => trivial
    | close j => trivial
    | receipt g j => exact valid

/-- Settling changes only endpoint-owned pending status, monotonically. -/
theorem local_settle (h : LocalInvariant s) (found : s.requests r = some q)
    (registered : ∃ i, s.registrations r = some i) :
    LocalInvariant (putRequest s r { q with settled := true }) := by
  constructor
  · intro a x hx
    by_cases same : a = r
    · subst a; simp [putRequest] at hx; subst x
      exact h.requestSource r q found
    · simp [putRequest, same] at hx
      exact h.requestSource a x hx
  · intro a x hx hs
    by_cases same : a = r
    · subst a; exact registered
    · simp [putRequest, same] at hx
      exact h.settledRegistered a x hx hs
  · exact h.sealedSafe
  · intro i e a he hk hs r' q' hq' source
    by_cases same : r' = r
    · subst r'; simp [putRequest] at hq'; subst q'; rfl
    · simp [putRequest, same] at hq'
      exact h.gateBarrier i e a he hk hs r' q' hq' source
  · exact h.transferSeal
  · intro p hp
    have valid := h.packetsValid p hp
    cases p with
    | register a d =>
      obtain ⟨x, hx, hd⟩ := valid
      by_cases same : a = r
      · subst a; rw [found] at hx; cases hx
        exact ⟨{ q with settled := true }, by simp [putRequest], hd⟩
      · exact ⟨x, by simpa [putRequest, same] using hx, hd⟩
    | grant a j =>
      obtain ⟨⟨x, hx⟩, hj⟩ := valid
      by_cases same : a = r
      · subst a
        exact ⟨⟨{ q with settled := true }, by simp [putRequest]⟩, hj⟩
      · exact ⟨⟨x, by simpa [putRequest, same] using hx⟩, hj⟩
    | publish j => trivial
    | activate j => trivial
    | close j => trivial
    | receipt g j => exact valid

/-- Endpoint-local nonce freshness and closed-gate exclusion preserve every
other gate's pending-operation barrier. -/
theorem local_request (h : LocalInvariant s) (found : s.entries i = some e)
    (gate : e.kind = .gate a) (notClosed : e.closed = false)
    (fresh : s.requests (i, nonce) = none) (destination : Option Agent) :
    LocalInvariant (putRequest s (i, nonce) ⟨destination, false⟩) := by
  constructor
  · intro r q hq
    by_cases same : r = (i, nonce)
    · subst r
      exact ⟨e, a, found, gate⟩
    · simp [putRequest, same] at hq
      exact h.requestSource r q hq
  · intro r q hq hs
    by_cases same : r = (i, nonce)
    · subst r; simp [putRequest] at hq; subst q; contradiction
    · simp [putRequest, same] at hq
      exact h.settledRegistered r q hq hs
  · exact h.sealedSafe
  · intro j x b hx hk hs r q hq source
    by_cases same : r = (i, nonce)
    · subst r
      have ji : i = j := source
      change s.entries j = some x at hx
      rw [← ji, found] at hx
      cases hx
      have hc := (h.sealedSafe i e found hs).1
      simp [notClosed] at hc
    · simp [putRequest, same] at hq
      exact h.gateBarrier j x b hx hk hs r q hq source
  · exact h.transferSeal
  · intro p hp
    have valid := h.packetsValid p hp
    cases p with
    | register r d =>
      obtain ⟨q, hq, hd⟩ := valid
      have different : r ≠ (i, nonce) := by intro eq; rw [eq, fresh] at hq; contradiction
      exact ⟨q, by simpa [putRequest, different] using hq, hd⟩
    | grant r j =>
      obtain ⟨⟨q, hq⟩, hj⟩ := valid
      have different : r ≠ (i, nonce) := by intro eq; rw [eq, fresh] at hq; contradiction
      exact ⟨⟨q, by simpa [putRequest, different] using hq⟩, hj⟩
    | publish j => trivial
    | activate j => trivial
    | close j => trivial
    | receipt g j => exact valid


theorem local_control (h : LocalInvariant s) (generation : Nat) (phase : Q.Phase) :
    LocalInvariant { s with generation, phase } := by
  constructor
  · exact h.requestSource
  · exact h.settledRegistered
  · exact h.sealedSafe
  · exact h.gateBarrier
  · exact h.transferSeal
  · exact h.packetsValid

theorem local_packets (h : LocalInvariant s) (packets : List (Packet Agent))
    (subset : ∀ p, p ∈ packets → p ∈ s.packets) :
    LocalInvariant { s with packets } := by
  constructor
  · exact h.requestSource
  · exact h.settledRegistered
  · exact h.sealedSafe
  · exact h.gateBarrier
  · exact h.transferSeal
  · intro p hp
    have valid := h.packetsValid p (subset p hp)
    cases p <;> exact valid

theorem next_absent (h : Q.Invariant (project s)) : s.entries s.next = none := by
  have fresh := h.fresh s.next (Nat.le_refl _)
  cases he : s.entries s.next
  · rfl
  · simp [project, he] at fresh

theorem step_preserves_local (hq : Q.Invariant (project s)) (h : LocalInvariant s)
    (step : Step s event t) : LocalInvariant t := by
  have fresh := next_absent hq
  cases step with
  | root a active =>
    apply local_enqueue (local_issue h fresh s.generation (.gate a))
    trivial
  | request i nonce e a destination found gate published notClosed freshRequest =>
    apply local_enqueue (local_request h found gate notClosed freshRequest destination)
    exact ⟨⟨destination, false⟩, by simp [putRequest], rfl⟩
  | retransmit r q found =>
    exact local_enqueue h ⟨q, found, rfl⟩
  | register r destination e a packet absent found gate =>
    apply local_enqueue (local_registerId
      (local_issue h fresh e.generation (requestedKind a destination)) absent s.next)
    obtain ⟨q, hq, _⟩ := h.packetsValid _ packet
    exact ⟨⟨q, hq⟩, by simp [registerId]⟩
  | duplicateRegister r destination i packet registered =>
    obtain ⟨q, hq, _⟩ := h.packetsValid _ packet
    exact local_enqueue h ⟨⟨q, hq⟩, registered⟩
  | grant r i q packet found =>
    have valid := h.packetsValid _ packet
    apply local_enqueue (local_settle h found ⟨i, valid.2⟩)
    cases hd : q.destination <;> simp [grantPacket, hd, PacketValid]
  | publish i e packet found kind unsealed =>
    apply local_put h found (new := { e with published := true }) rfl rfl
    · exact fun hs => hs
    · exact h.sealedSafe i e found
    · exact fun a hk hs => h.gateBarrier i e a found hk hs
    · exact fun a hk => h.transferSeal i e a found hk
  | activate i e destination packet found transfer pending =>
    have replaced : LocalInvariant (put s i (resolved e s.next)) := by
      apply local_put h found (new := resolved e s.next) rfl rfl
      · intro; rfl
      · intro; refine ⟨rfl, ?_⟩
        intro a hk; simp [resolved, transfer] at hk
      · intro a hk; simp [resolved, transfer] at hk
      · intro a hk; rfl
    have different : s.next ≠ i := by intro eq; rw [eq, found] at fresh; contradiction
    have absent : (put s i (resolved e s.next)).entries
        (put s i (resolved e s.next)).next = none := by simpa [put, different] using fresh
    apply local_enqueue (local_issue replaced absent e.generation (.gate destination))
    trivial
  | duplicateActivate i j e destination packet found transfer committed =>
    exact local_enqueue h True.intro
  | beginClose active => exact local_control h s.generation .closing
  | requestClose i e closing found kind => exact local_enqueue h True.intro
  | close i e packet found kind =>
    apply local_put h found (new := { e with closed := true }) rfl rfl
    · exact fun hs => hs
    · intro hs; exact ⟨rfl, (h.sealedSafe i e found hs).2⟩
    · exact fun a hk hs => h.gateBarrier i e a found hk hs
    · exact fun a hk => h.transferSeal i e a found hk
  | submit i e a found use published notClosed =>
    have unsealed := not_closed_unsealed h found notClosed
    apply local_put h found (new := { e with work := e.work + 1 }) rfl rfl
    · exact fun hs => hs
    · intro hs; simp [unsealed] at hs
    · intro b hk; simp [use] at hk
    · intro b hk; simp [use] at hk
  | effect i e a found use work => exact h
  | finishOne i n e a found use work =>
    have positive : 0 < e.work := by omega
    have unsealed := work_unsealed h found use positive
    apply local_put h found (new := { e with work := n }) rfl rfl
    · exact fun hs => hs
    · intro hs; simp [unsealed] at hs
    · intro b hk; simp [use] at hk
    · intro b hk; simp [use] at hk
  | sealGate i e a found gate closed settled =>
    apply local_put h found (new := { e with sealed := true }) rfl rfl
    · intro; rfl
    · intro; refine ⟨closed, ?_⟩
      intro b hk; simp [gate] at hk
    · intro b hk hs; exact settled
    · intro b hk; simp [gate] at hk
  | sealUse i e a found use closed drained =>
    apply local_put h found (new := { e with sealed := true }) rfl rfl
    · intro; rfl
    · intro; exact ⟨closed, fun _ _ => drained⟩
    · intro b hk; simp [use] at hk
    · intro b hk; simp [use] at hk
  | sendReceipt i e found kind sealed =>
    exact local_enqueue h ⟨e, found, rfl, sealed⟩
  | receiveReceipt i generation e packet found bound =>
    apply local_put h found (new := { e with receipt := true }) rfl rfl
    · exact fun hs => hs
    · exact h.sealedSafe i e found
    · exact fun a hk hs => h.gateBarrier i e a found hk hs
    · exact fun a hk => h.transferSeal i e a found hk
  | retire i e found receipt =>
    apply local_put h found (new := { e with live := false }) rfl rfl
    · exact fun hs => hs
    · exact h.sealedSafe i e found
    · exact fun a hk hs => h.gateBarrier i e a found hk hs
    · exact fun a hk => h.transferSeal i e a found hk
  | quiesce closing empty gates => exact local_control h s.generation .quiescent
  | reuse quiet => exact local_control h (s.generation + 1) .active
  | duplicate p present => exact local_enqueue h (h.packetsValid p present)
  | lose packets subset => exact local_packets h packets subset
  | stutter => exact h

theorem step_preserves_invariant (h : Invariant s) (step : Step s event t) :
    Invariant t :=
  ⟨Q.step_preserves_invariant h.1 (step_refines h.2 step),
    step_preserves_local h.1 h.2 step⟩

theorem trace_preserves_invariant (h : Invariant s) (trace : Trace s events t) :
    Invariant t := by
  induction trace with
  | nil => exact h
  | cons step tail ih => exact ih (step_preserves_invariant h step)

theorem reachable_invariant (reachable : Reachable s) : Invariant s := by
  obtain ⟨events, trace⟩ := reachable
  exact trace_preserves_invariant initial_invariant trace

theorem trace_refines (h : Invariant s) (trace : Trace s events t) :
    Q.Trace (project s) events (project t) := by
  induction trace with
  | nil => exact .nil _
  | cons step tail ih =>
    exact .cons (step_refines h.2 step) (ih (step_preserves_invariant h step))

theorem after_reuse_no_old_access (h : Invariant s) (reuse : Step s (.reuse old) t)
    (future : Trace t events u) (access : Step u (.access generation ticket) v) :
    old < generation := by
  have ht := step_preserves_invariant h reuse
  have hu := trace_preserves_invariant ht future
  exact Q.after_reuse_no_old_access h.1 (step_refines h.2 reuse)
    (trace_refines ht future) (step_refines hu.2 access)

end Aurora.R
