import A.Invariants
import A.Simulation
import A.Metadata
namespace Aurora.A

variable {Agent : Type} {allocation : Footprint} {s t : State Agent}

theorem expected_protocol_eq (p : R.State Agent)
    (entries : ∀ i, (p.entries i).map (fun e => (e.kind, e.receiver)) =
      (s.protocol.entries i).map (fun e => (e.kind, e.receiver)))
    (registrations : p.registrations = s.protocol.registrations) :
    expected (atProtocol s p) generation location = expected s generation location := by
  cases location with
  | gate => rfl
  | frozen => rfl
  | request r => simp [expected, atProtocol, registrations]
  | use i | transfer i =>
    have hi := entries i
    cases old : s.protocol.entries i <;> cases new : p.entries i <;> simp [old, new] at hi
    · simp [expected, atProtocol, old, new]
    · cases hg : s.grants i <;> simp [expected, atProtocol, old, new, hg, hi.1, hi.2]

/-- Proof transport, not an operational compatibility predicate. -/
theorem protocol_transport (h : Invariant allocation s) (p : R.State Agent)
    (hp : R.Invariant p)
    (forward : ∀ i e, s.protocol.entries i = some e →
      ∃ n, p.entries i = some n ∧ n.generation = e.generation ∧ n.kind = e.kind ∧ n.receiver = e.receiver)
    (backward : ∀ i n, p.entries i = some n →
      ∃ e, s.protocol.entries i = some e ∧ n.generation = e.generation ∧ n.kind = e.kind ∧
        n.receiver = e.receiver ∧ (n.sealed = false → e.sealed = false))
    (reqForward : ∀ r q, s.protocol.requests r = some q →
      ∃ n, p.requests r = some n ∧ n.destination = q.destination)
    (reqBackward : ∀ r n, p.requests r = some n → ∃ q, s.protocol.requests r = some q)
    (registrations : p.registrations = s.protocol.registrations)
    (sequential : ∀ i g e, s.grants i = some g → p.entries i = some e →
      g.writable = true → e.work ≤ 1) : Invariant allocation (atProtocol s p) := by
  have identity (i) : (p.entries i).map (fun e => (e.kind,e.receiver)) =
      (s.protocol.entries i).map (fun e => (e.kind,e.receiver)) := by
    cases old : s.protocol.entries i with
    | none =>
      cases new : p.entries i with
      | none => rfl
      | some n => obtain ⟨e,he,_⟩ := backward i n new; simp [old] at he
    | some e =>
      obtain ⟨n, hn, _, hk, hr⟩ := forward i e old
      simp [hn, hk, hr]
  constructor
  · exact hp
  · intro i g hg
    obtain ⟨e, he, hgen, hsub, hb⟩ := h.grantsBound i g hg
    obtain ⟨n, hn, ngen, nkind, _⟩ := forward i e he
    exact ⟨n, hn, ngen.trans hgen, by simpa [nkind] using hsub, hb⟩
  · intro i n hn
    obtain ⟨e, he, _⟩ := backward i n hn
    exact h.grantsTotal i e he
  · exact h.grantsIssued
  · intro r payload hpayload
    obtain ⟨q, parent, hq, hg, origin, derived⟩ := h.payloadBound r payload hpayload
    obtain ⟨n, hn, ndest⟩ := reqForward r q hq
    exact ⟨n, parent, hn, hg, origin, by simpa [ndest] using derived⟩
  · intro r n hn
    obtain ⟨q, hq⟩ := reqBackward r n hn
    exact h.payloadTotal r q hq
  · intro r i hi; exact h.registeredBound r i (by simpa [atProtocol,registrations] using hi)
  · exact h.partition
  · exact h.unissuedEmpty
  · intro gen loc cell
    rw [expected_protocol_eq p identity registrations]
    exact h.accounted gen loc cell
  · intro gen i cell hc
    obtain ⟨g,e,hg,he,hgen,hkind,hcell⟩ := h.gateInventory gen i cell hc
    obtain ⟨n,hn,_,nk,_⟩ := forward i e he
    exact ⟨g,n,hg,hn,hgen,nk.trans hkind,hcell⟩
  · intro i hi
    obtain ⟨e,a,he,hkind,hseal⟩ := h.returnedSound i hi
    obtain ⟨n,hn,_,nk,_⟩ := forward i e he
    refine ⟨n,a,hn,nk.trans hkind,?_⟩
    cases hs : n.sealed
    · obtain ⟨old,hold,_,_,_,back⟩ := backward i n hn
      have eq : old = e := Option.some.inj (hold.symm.trans he)
      have no := back hs
      simp [eq,hseal] at no
    · rfl
  · exact h.readerPayload
  · exact h.readerGrant
  · exact h.readableSound
  · exact sequential

theorem move_partition (h : Invariant allocation s) (issued : s.issued generation = true)
    (distinct : src ≠ dst) (owned : footprint.Within (s.holdings generation src)) :
    (∀ gen, (move s generation src dst footprint).issued gen = true →
      Inventory.Partition allocation ((move s generation src dst footprint).holdings gen)) ∧
    (∀ gen, (move s generation src dst footprint).issued gen = false →
      ∀ loc, (move s generation src dst footprint).holdings gen loc = []) := by
  constructor
  · intro gen hi
    by_cases same : gen = generation
    · subst gen
      simpa [move] using Inventory.move_partition (h.partition generation issued) distinct owned
    · simpa [move,same] using h.partition gen hi
  · intro gen hi loc
    have ne : gen ≠ generation := by intro eq; subst gen; simp [move,issued] at hi
    simpa [move,ne] using h.unissuedEmpty gen hi loc

theorem move_frozen (hf : Frozen s gen frozen) (notSource : src ≠ .frozen) :
    Frozen (move s generation src dst footprint) gen frozen := by
  intro cell hc
  have old := hf hc
  by_cases same : gen = generation
  · subst gen
    by_cases destination : dst = .frozen
    · subst dst; simp [move,Inventory.move,Ne.symm notSource,old]
    · simpa [move,Inventory.move,Ne.symm notSource,Ne.symm destination] using old
  · simpa [move,same] using old

theorem receipt_is_sealed (h : Invariant allocation s)
    (found : s.protocol.entries i = some e) (receipt : e.receipt = true) : e.sealed = true := by
  have stopped := (h.protocol.1.entriesOK i (R.abstractEntry e) (R.project_found found)).receiptSound receipt
  cases hs : e.sealed <;> simp_all [R.abstractEntry]

theorem passive_preserves (h : Invariant allocation s) (op : Passive s.protocol p) :
    Invariant allocation (atProtocol s p) := by
  apply protocol_transport h p (R.step_preserves_invariant h.protocol (passive_erases op))
  · intro i e he
    obtain ⟨n,hn,hg,hk⟩ := passive_entry_forward op he
    exact ⟨n,hn,hg,hk,passive_receiver_same op he hn⟩
  · intro i e he
    obtain ⟨old, ho, hg, hk, hs, _⟩ := passive_entry_backward op he
    exact ⟨old, ho, hg, hk, passive_receiver_same op ho he, hs⟩
  · intro r q hq; exact passive_request_forward op hq
  · intro r q hq
    obtain ⟨old, ho, _⟩ := passive_request_backward op hq
    exact ⟨old, ho⟩
  · exact passive_registrations op
  · intro i g e hg he hw
    obtain ⟨old, ho, _, _, _, work⟩ := passive_entry_backward op he
    exact Nat.le_trans work (h.sequential i g old hg ho hw)

theorem replace_preserves (h : Invariant allocation s)
    (found : s.protocol.entries k = some old) (kind : fresh.kind = old.kind)
    (generation : fresh.generation = old.generation)
    (receiver : fresh.receiver = old.receiver)
    (unsealed : fresh.sealed = false → old.sealed = false)
    (bounded : ∀ g, s.grants k = some g → g.writable = true → fresh.work ≤ 1)
    (hp : R.Invariant (R.put s.protocol k fresh)) :
    Invariant allocation (atProtocol s (R.put s.protocol k fresh)) := by
  apply protocol_transport h _ hp
  · intro i e he
    by_cases same : i = k
    · subst i
      have eq : e = old := Option.some.inj (he.symm.trans found)
      exact ⟨fresh, by simp [R.put], by simpa [eq] using generation, by simpa [eq] using kind, by simpa [eq] using receiver⟩
    · exact ⟨e, by simpa [R.put, same] using he, rfl, rfl, rfl⟩
  · intro i e he
    by_cases same : i = k
    · subst i
      have eq : e = fresh := by simpa [R.put] using he.symm
      subst e
      exact ⟨old, found, generation, kind, receiver, unsealed⟩
    · exact ⟨e, by simpa [R.put, same] using he, rfl, rfl, rfl, fun x => x⟩
  · intro r q hq; exact ⟨q, hq, rfl⟩
  · intro r q hq; exact ⟨q, hq⟩
  · rfl
  · intro i g e hg he hw
    by_cases same : i = k
    · subst i
      have eq : e = fresh := by simpa [R.put] using he.symm
      subst e; exact bounded g hg hw
    · exact h.sequential i g e hg (by simpa [R.put, same] using he) hw

theorem submit_preserves (h : Invariant allocation s)
    (found : s.protocol.entries i = some e) (use : e.kind = .use g.subject)
    (granted : s.grants i = some g) (published : e.published = true)
    (notClosed : e.closed = false) (sequential : g.writable = true → e.work = 0) :
    Invariant allocation (atProtocol s (R.put s.protocol i { e with work := e.work + 1 })) := by
  apply replace_preserves (fresh := { e with work := e.work + 1 }) h found rfl rfl rfl (fun x => x)
  · intro grant hg hw
    have same : grant = g := Option.some.inj (hg.symm.trans granted)
    have zero := sequential (by simpa [same] using hw)
    simp [zero]
  · exact R.step_preserves_invariant h.protocol
      (.submit s.protocol i e g.subject found use published notClosed)

theorem reuse_preserves (h : Invariant allocation s)
    (quiet : s.protocol.phase = .quiescent) :
    Invariant allocation (atProtocol s
      { s.protocol with generation := s.protocol.generation + 1, phase := .active }) := by
  apply protocol_transport h _ (R.step_preserves_invariant h.protocol (.reuse s.protocol quiet))
  · intro i e he; exact ⟨e, he, rfl, rfl, rfl⟩
  · intro i e he; exact ⟨e, he, rfl, rfl, rfl, fun x => x⟩
  · intro r q hq; exact ⟨q, hq, rfl⟩
  · intro r q hq; exact ⟨q, hq⟩
  · rfl
  · exact h.sequential

def freezeState (s : State Agent) (i : Nat) (g : Grant Agent) (footprint : Footprint) :=
  readEnable (move s g.generation (.gate i) .frozen footprint) i footprint

theorem freeze_preserves (h : Invariant allocation s) (_found : s.protocol.entries i = some e)
    (_gate : e.kind = .gate g.subject) (granted : s.grants i = some g)
    (within : footprint.Within g.footprint)
    (available : footprint.Within (s.holdings g.generation (.gate i))) :
    Invariant allocation (freezeState s i g footprint) := by
  let t := freezeState s i g footprint
  have part := move_partition h (h.grantsIssued i g granted) (src := .gate i) (dst := .frozen) (by simp) available
  have frozen (gen f) (hf : Frozen s gen f) : Frozen t gen f := move_frozen hf (by simp)
  have gateSubset (gen j cell) (hc : cell ∈ t.holdings gen (.gate j)) :
      cell ∈ s.holdings gen (.gate j) := by
    by_cases sameGen : gen = g.generation
    · by_cases sameGate : j = i
      · subst gen; subst j
        have both : cell ∈ s.holdings g.generation (.gate i) ∧ cell ∉ footprint := by
          simpa [t,freezeState,readEnable,move,Inventory.move] using hc
        exact both.1
      · simpa [t,freezeState,readEnable,move,Inventory.move,sameGen,sameGate] using hc
    · simpa [t,freezeState,readEnable,move,sameGen] using hc
  have newFrozen (cell) (hc : cell ∈ footprint) : cell ∈ t.holdings g.generation .frozen := by
    simp [t,freezeState,readEnable,move,Inventory.move,hc]
  change Invariant allocation t
  constructor
  · exact h.protocol
  · exact h.grantsBound
  · exact h.grantsTotal
  · exact h.grantsIssued
  · exact h.payloadBound
  · exact h.payloadTotal
  · exact h.registeredBound
  · exact part.1
  · exact part.2
  · intro gen loc cell
    cases loc with
    | gate j => rfl
    | frozen => rfl
    | request r =>
      by_cases hg : gen = g.generation <;>
        simpa [t,freezeState,readEnable,move,Inventory.move,expected,hg] using h.accounted gen (.request r) cell
    | use j =>
      by_cases hg : gen = g.generation <;>
        simpa [t,freezeState,readEnable,move,Inventory.move,expected,hg] using h.accounted gen (.use j) cell
    | transfer j =>
      by_cases hg : gen = g.generation <;>
        simpa [t,freezeState,readEnable,move,Inventory.move,expected,hg] using h.accounted gen (.transfer j) cell
  · intro gen j cell hc
    exact h.gateInventory gen j cell (gateSubset gen j cell hc)
  · exact h.returnedSound
  · intro r p hp hr; exact frozen _ _ (h.readerPayload r p hp hr)
  · intro j grant hg hr; exact frozen _ _ (h.readerGrant j grant hg hr)
  · intro j cell hc
    by_cases same : j = i
    · subst j
      have splitMem : cell ∈ s.readable i ∨ cell ∈ footprint := by
        simpa [t,freezeState,readEnable] using hc
      rcases splitMem with old | fresh
      · obtain ⟨grant,hg,hc,hf⟩ := h.readableSound i cell old
        exact ⟨grant,hg,hc,frozen _ [cell] (by simpa [Frozen,Footprint.Within] using hf) (by simp)⟩
      · exact ⟨g,granted,within fresh,newFrozen cell fresh⟩
    · obtain ⟨grant,hg,hc,hf⟩ := h.readableSound j cell (by simpa [t,freezeState,readEnable,same] using hc)
      exact ⟨grant,hg,hc,frozen _ [cell] (by simpa [Frozen,Footprint.Within] using hf) (by simp)⟩
  · exact h.sequential

def returnedState (s : State Agent) (i : Nat) (p : Payload Agent) :=
  markReturned (move s p.grant.generation (.use i) (.gate p.origin) p.grant.footprint) i

theorem return_preserves (h : Invariant allocation s)
    (registered : s.protocol.registrations r = some i) (payload : s.payloads r = some p)
    (writer : p.grant.writable = true) (_origin : p.origin = r.1)
    (found : s.protocol.entries i = some e) (use : e.kind = .use p.grant.subject)
    (_bound : e.generation = p.grant.generation) (receipt : e.receipt = true)
    (fresh : s.returned i = false) : Invariant allocation (returnedState s i p) := by
  let t := returnedState s i p
  obtain ⟨data,hd,hg⟩ := h.registeredBound r i registered
  have dataEq : data = p := Option.some.inj (hd.symm.trans payload)
  subst data
  have source (gen cell) : cell ∈ s.holdings gen (.use i) ↔
      p.grant.generation = gen ∧ cell ∈ p.grant.footprint := by
    have claim := h.accounted gen (.use i) cell
    by_cases same : p.grant.generation = gen <;>
      simpa [expected,hg,found,use,isUse,writer,fresh,same] using claim
  have owned : p.grant.footprint.Within (s.holdings p.grant.generation (.use i)) :=
    fun cell hc => (source _ cell).2 ⟨rfl,hc⟩
  have part := move_partition h (h.grantsIssued i p.grant hg) (src := .use i)
    (dst := .gate p.origin) (by simp) owned
  have frozen (gen f) (hf : Frozen s gen f) : Frozen t gen f := move_frozen hf (by simp)
  have sealed := receipt_is_sealed h found receipt
  obtain ⟨q,parent,hq,hparent,origin,derived⟩ := h.payloadBound r p payload
  obtain ⟨gateEntry,owner,gateFound,gateKind⟩ := h.protocol.2.requestSource r q hq
  have parentBind := grant_entry h hparent gateFound
  have parentKind : gateEntry.kind = .gate parent.subject := by
    have sub : owner = parent.subject := by simpa [gateKind,subject] using parentBind.2.1
    simpa [sub] using gateKind
  have parentGen : parent.generation = p.grant.generation := derived.2.2.1.symm
  have parentAt : s.grants p.origin = some parent := by simpa [origin] using hparent
  have parentFound : s.protocol.entries p.origin = some gateEntry := by simpa [origin] using gateFound
  change Invariant allocation t
  constructor
  · exact h.protocol
  · exact h.grantsBound
  · exact h.grantsTotal
  · exact h.grantsIssued
  · exact h.payloadBound
  · exact h.payloadTotal
  · exact h.registeredBound
  · exact part.1
  · exact part.2
  · intro gen loc cell
    cases loc with
    | gate j => rfl
    | frozen => rfl
    | request q =>
      by_cases same : gen = p.grant.generation <;>
        simpa [t,returnedState,markReturned,move,Inventory.move,expected,same] using h.accounted gen (.request q) cell
    | transfer j =>
      by_cases same : gen = p.grant.generation <;>
        simpa [t,returnedState,markReturned,move,Inventory.move,expected,same] using h.accounted gen (.transfer j) cell
    | use j =>
      by_cases sameTicket : j = i
      · subst j
        by_cases sameGen : gen = p.grant.generation
        · subst gen
          simp [t,returnedState,markReturned,move,Inventory.move,expected,hg,found,source]
        · have different : p.grant.generation ≠ gen := Ne.symm sameGen
          simp [t,returnedState,markReturned,move,expected,hg,found,sameGen,different,source]
      · by_cases sameGen : gen = p.grant.generation <;>
          simpa [t,returnedState,markReturned,move,Inventory.move,expected,sameTicket,sameGen]
            using h.accounted gen (.use j) cell
  · intro gen j cell hc
    by_cases sameGen : gen = p.grant.generation
    · subst gen
      by_cases sameGate : j = p.origin
      · subst j
        have members : cell ∈ s.holdings p.grant.generation (.gate p.origin) ∨ cell ∈ p.grant.footprint := by
          simpa [t,returnedState,markReturned,move,Inventory.move] using hc
        rcases members with old | moved
        · exact h.gateInventory _ _ _ old
        · exact ⟨parent,gateEntry,parentAt,parentFound,parentGen,parentKind,derived.2.2.2.1 moved⟩
      · exact h.gateInventory _ _ _ (by simpa [t,returnedState,markReturned,move,Inventory.move,sameGate] using hc)
    · exact h.gateInventory _ _ _ (by simpa [t,returnedState,markReturned,move,sameGen] using hc)
  · intro j hj
    by_cases same : j = i
    · subst j; exact ⟨e,p.grant.subject,found,use,sealed⟩
    · exact h.returnedSound j (by simpa [t,returnedState,markReturned,same] using hj)
  · intro q data hdata hr; exact frozen _ _ (h.readerPayload q data hdata hr)
  · intro j grant hgrant hr; exact frozen _ _ (h.readerGrant j grant hgrant hr)
  · intro j cell hc
    obtain ⟨grant,hgrant,hcell,hf⟩ := h.readableSound j cell hc
    exact ⟨grant,hgrant,hcell,frozen _ [cell] (by simpa [Frozen,Footprint.Within] using hf) (by simp)⟩
  · exact h.sequential

end Aurora.A
