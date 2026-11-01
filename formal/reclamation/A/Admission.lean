import A.Metadata
namespace Aurora.A
variable {Agent : Type} {allocation : Footprint} {s : State Agent}

def rootState (s : State Agent) (issuer subject : Agent) (allocation : Footprint) : State Agent :=
  mint (putGrant (atProtocol s
    (R.enqueue (R.issue s.protocol s.protocol.generation (.gate subject)) (.publish s.protocol.next)))
    s.protocol.next ⟨issuer,subject,s.protocol.generation,allocation,true,true⟩)
    s.protocol.generation s.protocol.next allocation

theorem root_preserves (h : Invariant allocation s) (issuer owner : Agent)
    (active : s.protocol.phase = .active) (available : s.issued s.protocol.generation = false) :
    Invariant allocation (rootState s issuer owner allocation) := by
  let t := rootState s issuer owner allocation
  let ng : Grant Agent := ⟨issuer,owner,s.protocol.generation,allocation,true,true⟩
  let ne : R.Entry Agent := { generation := s.protocol.generation, kind := .gate owner }
  have fresh := grants_fresh h (Nat.le_refl s.protocol.next)
  have entryFresh : s.protocol.entries s.protocol.next = none := by
    have hf := h.protocol.1.fresh s.protocol.next (Nat.le_refl _)
    cases he : s.protocol.entries s.protocol.next with
    | none => rfl
    | some e => simp [R.project, he] at hf
  have oldGrant : ∀ i g, s.grants i = some g → i ≠ s.protocol.next := by
    intro i g hg same; subst i; simp [fresh] at hg
  have oldEntry : ∀ i e, s.protocol.entries i = some e → i ≠ s.protocol.next := by
    intro i e he same; subst i; simp [entryFresh] at he
  have grants : t.grants = fun i => if i = s.protocol.next then some ng else s.grants i := rfl
  have entries : t.protocol.entries = fun i => if i = s.protocol.next then some ne else s.protocol.entries i := rfl
  have holdings : t.holdings = fun gen loc => if gen = s.protocol.generation then
      (if loc = .gate s.protocol.next then allocation else []) else s.holdings gen loc := rfl
  have issued : t.issued = fun gen => if gen = s.protocol.generation then true else s.issued gen := rfl
  have frozenSame : ∀ gen, t.holdings gen .frozen = s.holdings gen .frozen := by
    intro gen
    by_cases same : gen = s.protocol.generation
    · subst gen; simp [holdings, h.unissuedEmpty _ available .frozen]
    · simp [holdings, same]
  have expectedSame : ∀ gen loc, (∀ i, loc ≠ .gate i) → loc ≠ .frozen →
      expected t gen loc = expected s gen loc := by
    intro gen loc nongate nonfrozen
    cases loc with
    | gate i => exact False.elim (nongate i rfl)
    | frozen => contradiction
    | request r => rfl
    | use i =>
      by_cases same : i = s.protocol.next
      · subst i; simp [expected, grants, entries, ng, ne, isUse, fresh]
      · simp [expected, same, t, rootState, mint, putGrant, atProtocol, R.enqueue, R.issue, R.put]
    | transfer i =>
      by_cases same : i = s.protocol.next
      · subst i; simp [expected, grants, entries, ng, ne, isTransfer, fresh]
      · simp [expected, same, t, rootState, mint, putGrant, atProtocol, R.enqueue, R.issue, R.put]
  change Invariant allocation t
  constructor
  · exact R.step_preserves_invariant h.protocol (.root s.protocol owner active)
  · intro i g hg
    simp only [grants] at hg
    split at hg
    · rename_i same; subst i
      have eq : g = ng := Option.some.inj hg.symm; subst g
      exact ⟨ne, by simp [entries], rfl, rfl, List.Subset.refl _⟩
    · obtain ⟨e, he, rest⟩ := h.grantsBound i g hg
      exact ⟨e, by simpa [entries,oldEntry i e he] using he, rest⟩
  · intro i e he
    simp only [entries] at he
    split at he
    · rename_i same; subst i; exact ⟨ng, by simp [grants]⟩
    · obtain ⟨g,hg⟩ := h.grantsTotal i e he
      exact ⟨g,by simpa [grants,oldGrant i g hg] using hg⟩
  · intro i g hg
    simp only [grants] at hg
    split at hg
    · have eq : g = ng := Option.some.inj hg.symm; subst g; simp [issued,ng]
    · have old := h.grantsIssued i g hg
      simp only [issued]
      split <;> simp_all
  · intro r p hp
    obtain ⟨q,parent,hq,hg,rest⟩ := h.payloadBound r p hp
    exact ⟨q,parent,hq,by simpa [grants,oldGrant _ _ hg] using hg,rest⟩
  · exact h.payloadTotal
  · intro r i hi
    obtain ⟨p,hp,hg⟩ := h.registeredBound r i hi
    exact ⟨p,hp,by simpa [grants,oldGrant _ _ hg] using hg⟩
  · intro gen hi
    by_cases same : gen = s.protocol.generation
    · subst gen
      constructor
      · intro loc cell member
        simp [holdings] at member
        exact member.2
      · intro a b cell ha hb
        simp [holdings] at ha hb
        exact ha.1.trans hb.1.symm
      · intro cell member; exact ⟨.gate s.protocol.next, by simpa [holdings] using member⟩
    · simpa [holdings,same] using h.partition gen (by simpa [issued,same] using hi)
  · intro gen hi loc
    have different : gen ≠ s.protocol.generation := by intro eq; subst gen; simp [issued] at hi
    simpa [holdings,different] using h.unissuedEmpty gen (by simpa [issued,different] using hi) loc
  · intro gen loc cell
    cases loc with
    | gate i => rfl
    | frozen => rfl
    | request r | use r | transfer r =>
      rw [expectedSame gen _ (by intro i; simp) (by simp)]
      rw [← h.accounted gen _ cell]
      by_cases same : gen = s.protocol.generation
      · subst gen
        simp [holdings,h.unissuedEmpty _ available]
      · simp [holdings,same]
  · intro gen i cell member
    by_cases same : gen = s.protocol.generation
    · subst gen
      have eq : i = s.protocol.next := by
        have hm := member
        simp [holdings] at hm
        exact hm.1
      subst i
      exact ⟨ng,ne,by simp [grants],by simp [entries],rfl,rfl,by simpa [holdings] using member⟩
    · obtain ⟨g,e,hg,he,gg,hk,hc⟩ := h.gateInventory gen i cell (by simpa [holdings,same] using member)
      exact ⟨g,e,by simpa [grants,oldGrant _ _ hg] using hg,
        by simpa [entries,oldEntry _ _ he] using he,gg,hk,hc⟩
  · intro i hi
    obtain ⟨e,a,he,hk,hs⟩ := h.returnedSound i hi
    exact ⟨e,a,by simpa [entries,oldEntry _ _ he] using he,hk,hs⟩
  · intro r p hp hw cell member
    rw [frozenSame]
    exact h.readerPayload r p hp hw member
  · intro i g hg hw cell member
    simp only [grants] at hg
    split at hg
    · have eq : g = ng := Option.some.inj hg.symm; subst g; contradiction
    · rw [frozenSame]; exact h.readerGrant i g hg hw member
  · intro i cell member
    obtain ⟨g,hg,hc,hf⟩ := h.readableSound i cell member
    exact ⟨g,by simpa [grants,oldGrant _ _ hg] using hg,hc,by simpa [frozenSame] using hf⟩
  · intro i g e hg he hw
    simp only [grants] at hg
    simp only [entries] at he
    split at he
    · have eq : e = ne := Option.some.inj he.symm; subst e; exact Nat.zero_le _
    · rename_i neq
      exact h.sequential i g e (by simpa [neq] using hg) he hw

def requestState (s : State Agent) (i nonce : Nat) (g : Grant Agent)
    (destination : Option Agent) (footprint : Footprint) (writable delegates : Bool) : State Agent :=
  let t := putPayload (atProtocol s
    (R.enqueue (R.putRequest s.protocol (i,nonce) ⟨destination,false⟩)
      (.register (i,nonce) destination))) (i,nonce)
    ⟨child g destination footprint writable delegates,i⟩
  if writable then move t g.generation (.gate i) (.request (i,nonce)) footprint else t

theorem request_preserves (h : Invariant allocation s) (i nonce : Nat)
    (e : R.Entry Agent) (g : Grant Agent) (destination : Option Agent)
    (footprint : Footprint) (writable delegates : Bool)
    (found : s.protocol.entries i = some e) (gate : e.kind = .gate g.subject)
    (granted : s.grants i = some g) (published : e.published = true)
    (notClosed : e.closed = false) (fresh : s.protocol.requests (i,nonce) = none)
    (within : footprint.Within g.footprint)
    (delegation : destination.isSome = true → g.delegates = true)
    (attenuate : delegates = true → g.delegates = true)
    (permission : if writable then g.writable = true ∧ footprint.Within (s.holdings g.generation (.gate i))
                  else footprint.Within (s.readable i)) :
    Invariant allocation (requestState s i nonce g destination footprint writable delegates) := by
  let t := requestState s i nonce g destination footprint writable delegates
  let protocol := R.enqueue (R.putRequest s.protocol (i,nonce) ⟨destination,false⟩)
    (.register (i,nonce) destination)
  let newPayload : Payload Agent := ⟨child g destination footprint writable delegates,i⟩
  have hp : t.protocol = protocol := by cases writable <;> rfl
  have hg : t.grants = s.grants := by cases writable <;> rfl
  have hr : t.readable = s.readable := by cases writable <;> rfl
  have hi : t.issued = s.issued := by cases writable <;> rfl
  have hret : t.returned = s.returned := by cases writable <;> rfl
  have hpay : t.payloads = fun r => if r = (i,nonce) then some newPayload else s.payloads r := by
    cases writable <;> rfl
  have hm : t.holdings = fun gen => if writable then
      (if gen = g.generation then Inventory.move (s.holdings gen) (.gate i) (.request (i,nonce)) footprint
       else s.holdings gen) else s.holdings gen := by cases writable <;> rfl
  have freshPayload := payload_fresh h fresh
  have regFresh : s.protocol.registrations (i,nonce) = none := by
    cases eq : s.protocol.registrations (i,nonce) with
    | none => rfl
    | some j =>
      obtain ⟨p,hp,_⟩ := h.registeredBound (i,nonce) j eq
      simp [freshPayload] at hp
  have oldPayload : ∀ r p, s.payloads r = some p → r ≠ (i,nonce) := by
    intro r p hfound same; subst r; simp [freshPayload] at hfound
  have emptyRequest : ∀ gen, s.holdings gen (.request (i,nonce)) = [] := by
    intro gen
    cases holding : s.holdings gen (.request (i,nonce)) with
    | nil => rfl
    | cons cell tail =>
      have member : cell ∈ s.holdings gen (.request (i,nonce)) := by simp [holding]
      have impossible := (h.accounted gen (.request (i,nonce)) cell).mp member
      simp [expected,freshPayload] at impossible
  have frozenSame : ∀ gen, t.holdings gen .frozen = s.holdings gen .frozen := by
    intro gen
    cases writable <;> by_cases same : gen = g.generation <;> simp [hm,same,Inventory.move]
  have keepFrozen : ∀ gen f, Frozen s gen f → Frozen t gen f := by
    intro gen f hf cell member
    rw [frozenSame]
    exact hf member
  have derived : Derived g destination newPayload.grant := by
    refine ⟨rfl,rfl,rfl,within,?_,attenuate,delegation⟩
    intro hw
    change writable = true at hw
    subst writable
    exact permission.1
  change Invariant allocation t
  constructor
  · rw [hp]
    exact R.step_preserves_invariant h.protocol
      (.request s.protocol i nonce e g.subject destination found gate published notClosed fresh)
  · intro j grant hgrant
    rw [hg] at hgrant
    obtain ⟨old,ho,rest⟩ := h.grantsBound j grant hgrant
    exact ⟨old, by simpa [hp,protocol,R.enqueue,R.putRequest] using ho, rest⟩
  · intro j entry hentry
    have old : s.protocol.entries j = some entry := by simpa only [hp] using hentry
    obtain ⟨grant,hgrant⟩ := h.grantsTotal j entry old
    exact ⟨grant,by simpa [hg] using hgrant⟩
  · intro j grant hgrant
    simpa [hi] using h.grantsIssued j grant (by simpa [hg] using hgrant)
  · intro r payload hfound
    simp only [hpay] at hfound
    by_cases same : r = (i,nonce)
    · subst r
      simp at hfound; subst payload
      exact ⟨⟨destination,false⟩,g,by simp [hp,protocol,R.enqueue,R.putRequest],
        by simpa [hg] using granted,rfl,derived⟩
    · simp only [if_neg same] at hfound
      obtain ⟨q,parent,hq,hparent,rest⟩ := h.payloadBound r payload hfound
      exact ⟨q,parent,by simpa [hp,protocol,R.enqueue,R.putRequest,same] using hq,
        by simpa [hg] using hparent,rest⟩
  · intro r q hq
    rw [hp] at hq
    change (if r = (i,nonce) then some ⟨destination,false⟩ else s.protocol.requests r) = some q at hq
    by_cases same : r = (i,nonce)
    · subst r; exact ⟨newPayload,by simp [hpay]⟩
    · simp only [if_neg same] at hq
      obtain ⟨payload,hpayload⟩ := h.payloadTotal r q hq
      exact ⟨payload,by simpa [hpay,same] using hpayload⟩
  · intro r j registered
    obtain ⟨payload,hpayload,hgrant⟩ := h.registeredBound r j (by simpa only [hp] using registered)
    exact ⟨payload,by simpa [hpay,oldPayload _ _ hpayload] using hpayload,
      by simpa [hg] using hgrant⟩
  · intro gen issued
    have old := h.partition gen (by simpa [hi] using issued)
    cases hw : writable
    · simpa [hm,hw] using old
    · by_cases same : gen = g.generation
      · subst gen
        have own : g.writable = true ∧ footprint.Within (s.holdings g.generation (.gate i)) := by simpa [hw] using permission
        have owned : footprint ⊆ s.holdings g.generation (.gate i) := own.2
        simpa [hm,hw] using Inventory.move_partition old (src := .gate i) (dst := .request (i,nonce)) (by simp) owned
      · simpa [hm,hw,same] using old
  · intro gen unissued loc
    have old := h.unissuedEmpty gen (by simpa [hi] using unissued) loc
    have ne : gen ≠ g.generation := by
      intro same; subst gen
      have issued := h.grantsIssued i g granted
      simp [hi,issued] at unissued
    simpa [hm,ne] using old
  · intro gen loc cell
    cases loc with
    | gate j => rfl
    | frozen => rfl
    | request r =>
      by_cases same : r = (i,nonce)
      · subst r
        cases hw : writable <;> by_cases gg : gen = g.generation <;>
          simp [hm,hw,gg,Inventory.move,emptyRequest,expected,hpay,newPayload,child,hp,protocol,
            R.enqueue,R.putRequest,regFresh,eq_comm]
      · have old := h.accounted gen (.request r) cell
        cases hw : writable <;> by_cases gg : gen = g.generation <;>
          simpa [hm,hw,gg,Inventory.move,same,expected,hpay,hp,protocol,R.enqueue,R.putRequest] using old
    | use j =>
      have old := h.accounted gen (.use j) cell
      cases hw : writable <;> by_cases gg : gen = g.generation <;>
        simpa [hm,hw,gg,Inventory.move,expected,hg,hp,protocol,R.enqueue,R.putRequest,hret] using old
    | transfer j =>
      have old := h.accounted gen (.transfer j) cell
      cases hw : writable <;> by_cases gg : gen = g.generation <;>
        simpa [hm,hw,gg,Inventory.move,expected,hg,hp,protocol,R.enqueue,R.putRequest] using old
  · intro gen j cell member
    have oldMember : cell ∈ s.holdings gen (.gate j) := by
      cases hw : writable
      · simpa [hm,hw] using member
      · by_cases gg : gen = g.generation
        · by_cases ji : j = i
          · subst j
            have both : cell ∈ s.holdings gen (.gate i) ∧ cell ∉ footprint := by
              simpa [hm,hw,gg,Inventory.move] using member
            exact both.1
          · simpa [hm,hw,gg,Inventory.move,ji] using member
        · simpa [hm,hw,gg] using member
    obtain ⟨grant,entry,hgrant,hentry,gg,hkind,hcell⟩ := h.gateInventory gen j cell oldMember
    exact ⟨grant,entry,by simpa [hg] using hgrant,by simpa only [hp] using hentry,gg,hkind,hcell⟩
  · intro j mark
    obtain ⟨entry,a,hentry,hkind,hseal⟩ := h.returnedSound j (by simpa [hret] using mark)
    exact ⟨entry,a,by simpa only [hp] using hentry,hkind,hseal⟩
  · intro r payload hfound reader
    simp only [hpay] at hfound
    by_cases same : r = (i,nonce)
    · subst r
      simp at hfound; subst payload
      change writable = false at reader
      subst writable
      intro cell member
      have hlocal : cell ∈ s.readable i := permission member
      obtain ⟨grant,hgrant,_,frozen⟩ := h.readableSound i cell hlocal
      have eq : grant = g := Option.some.inj (hgrant.symm.trans granted)
      subst grant
      simpa [newPayload,child,frozenSame] using frozen
    · simp only [if_neg same] at hfound
      exact keepFrozen _ _ (h.readerPayload r payload hfound reader)
  · intro j grant hgrant reader
    exact keepFrozen _ _ (h.readerGrant j grant (by simpa [hg] using hgrant) reader)
  · intro j cell readable
    obtain ⟨grant,hgrant,hcell,frozen⟩ := h.readableSound j cell (by simpa [hr] using readable)
    exact ⟨grant,by simpa [hg] using hgrant,hcell,by simpa [frozenSame] using frozen⟩
  · intro j grant entry hgrant hentry writer
    exact h.sequential j grant entry (by simpa [hg] using hgrant) (by simpa only [hp] using hentry) writer

end Aurora.A
