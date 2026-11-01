import A.Preservation
namespace Aurora.A
variable {Agent : Type} {allocation : Footprint} {s : State Agent}

def activatedState (s : State Agent) (i : Nat) (e : R.Entry Agent)
    (destination : Agent) (g : Grant Agent) : State Agent :=
  let t := putGrant (atProtocol s
    (R.enqueue (R.issue (R.put s.protocol i (R.resolved e s.protocol.next))
      e.generation (.gate destination)) (.publish s.protocol.next))) s.protocol.next g
  if g.writable then move t g.generation (.transfer i) (.gate s.protocol.next) g.footprint
  else readEnable t s.protocol.next g.footprint

theorem activate_preserves (h : Invariant allocation s) (i : Nat) (e : R.Entry Agent)
    (destination : Agent) (g : Grant Agent)
    (packet : R.Packet.activate i ∈ s.protocol.packets)
    (found : s.protocol.entries i = some e) (transfer : e.kind = .transfer destination)
    (pending : e.receiver = none) (granted : s.grants i = some g) :
    Invariant allocation (activatedState s i e destination g) := by
  let t := activatedState s i e destination g
  let rp := R.enqueue (R.issue (R.put s.protocol i (R.resolved e s.protocol.next))
      e.generation (.gate destination)) (.publish s.protocol.next)
  have pt : t.protocol = rp := by cases hw : g.writable <;> simp [t,activatedState,hw,move,readEnable,putGrant,atProtocol,rp]
  have gt : t.grants = fun j => if j = s.protocol.next then some g else s.grants j := by
    cases hw : g.writable <;> simp [t,activatedState,hw,move,readEnable,putGrant,atProtocol]
  have rt : t.payloads = s.payloads := by cases hw : g.writable <;> simp [t,activatedState,hw,move,readEnable,putGrant,atProtocol]
  have it : t.issued = s.issued := by cases hw : g.writable <;> simp [t,activatedState,hw,move,readEnable,putGrant,atProtocol]
  have ret : t.returned = s.returned := by cases hw : g.writable <;> simp [t,activatedState,hw,move,readEnable,putGrant,atProtocol]
  have lt : t.readable = fun j => if g.writable = false ∧ j = s.protocol.next then
      s.readable j ++ g.footprint else s.readable j := by
    funext j; cases hw : g.writable <;> simp [t,activatedState,hw,move,readEnable,putGrant,atProtocol]
  have hold : t.holdings = fun gen => if g.writable = true ∧ gen = g.generation then
      Inventory.move (s.holdings gen) (.transfer i) (.gate s.protocol.next) g.footprint
      else s.holdings gen := by
    funext gen; cases hw : g.writable <;> simp [t,activatedState,hw,move,readEnable,putGrant,atProtocol]
  have ent : t.protocol.entries = fun j => if j = s.protocol.next then
      some ({ generation := e.generation, kind := .gate destination } : R.Entry Agent)
      else if j = i then some (R.resolved e s.protocol.next) else s.protocol.entries j := by rw [pt]; rfl
  have req : t.protocol.requests = s.protocol.requests := by rw [pt]; rfl
  have reg : t.protocol.registrations = s.protocol.registrations := by rw [pt]; rfl
  have hp : R.Invariant t.protocol := by
    rw [pt]; exact R.step_preserves_invariant h.protocol (.activate s.protocol i e destination packet found transfer pending)
  have binding := grant_entry h granted found
  have owner : g.subject = destination := by simpa [transfer,subject] using binding.2.1.symm
  have freshGrant := grants_fresh h (i := s.protocol.next) (Nat.le_refl _)
  have indexOld (j : Nat) (n : R.Entry Agent) (hn : s.protocol.entries j = some n) : j ≠ s.protocol.next := by
    have less := Q.registered_lt h.protocol.1 (R.project_found hn)
    change j < s.protocol.next at less
    omega
  have indexDifferent : i ≠ s.protocol.next := indexOld i e found
  have oldGrant (j : Nat) (grant : Grant Agent) (hg : s.grants j = some grant) : t.grants j = some grant := by
    have ne : j ≠ s.protocol.next := by intro eq; subst j; simp [freshGrant] at hg
    simp [gt,ne,hg]
  have forward (j : Nat) (n : R.Entry Agent) (hn : s.protocol.entries j = some n) :
      ∃ after, t.protocol.entries j = some after ∧ after.generation = n.generation ∧
        after.kind = n.kind ∧ after.work = n.work ∧ (n.sealed = true → after.sealed = true) := by
    have notNew := indexOld j n hn
    by_cases same : j = i
    · subst j
      have eq : n = e := Option.some.inj (hn.symm.trans found)
      subst n
      exact ⟨R.resolved e s.protocol.next,by simp [ent,notNew],rfl,rfl,rfl,by simp [R.resolved]⟩
    · exact ⟨n,by simpa [ent,notNew,same] using hn,rfl,rfl,rfl,fun x => x⟩
  have frozenEqual (gen : Nat) : t.holdings gen .frozen = s.holdings gen .frozen := by
    simp only [hold]; split <;> simp [Inventory.move]
  have sourceMembers (gen cell : Nat) : cell ∈ s.holdings gen (.transfer i) ↔
      g.generation = gen ∧ g.writable = true ∧ cell ∈ g.footprint := by
    rw [h.accounted]
    by_cases hg : g.generation = gen <;> cases hw : g.writable <;>
      simp [expected,granted,found,transfer,isTransfer,pending,hg,hw]
  have freshUse (gen cell : Nat) : cell ∉ s.holdings gen (.use s.protocol.next) := by
    simp [h.accounted,expected,freshGrant]
  have freshTransfer (gen cell : Nat) : cell ∉ s.holdings gen (.transfer s.protocol.next) := by
    simp [h.accounted,expected,freshGrant]
  have oldSourceUse (gen cell : Nat) : cell ∉ s.holdings gen (.use i) := by
    simp [h.accounted,expected,granted,found,transfer,isUse]
  change Invariant allocation t
  constructor
  · exact hp
  · intro j grant hg
    simp only [gt] at hg
    split at hg
    · subst j
      have eq : grant = g := Option.some.inj hg.symm
      subst grant
      exact ⟨{generation := e.generation,kind := .gate destination},by simp [ent],binding.1,
        by simpa [subject] using owner.symm,binding.2.2⟩
    · obtain ⟨n,hn,ng,ns,nb⟩ := h.grantsBound j grant hg
      obtain ⟨after,ha,ag,ak,_,_⟩ := forward j n hn
      exact ⟨after,ha,ag.trans ng,by simpa [ak] using ns,nb⟩
  · intro j n hn
    by_cases same : j = s.protocol.next
    · subst j; exact ⟨g,by simp [gt]⟩
    · simp only [ent,if_neg same] at hn
      split at hn
      · subst j; exact ⟨g,oldGrant _ _ granted⟩
      · obtain ⟨grant,hg⟩ := h.grantsTotal j n hn
        exact ⟨grant,oldGrant j grant hg⟩
  · intro j grant hg
    simp only [gt] at hg
    split at hg
    · have eq : grant = g := Option.some.inj hg.symm
      subst grant; simpa [it] using h.grantsIssued i g granted
    · simpa [it] using h.grantsIssued j grant hg
  · intro r data hd
    obtain ⟨q,parent,hq,hg,origin,derived⟩ := h.payloadBound r data (by simpa [rt] using hd)
    exact ⟨q,parent,by simpa [req] using hq,oldGrant _ _ hg,origin,derived⟩
  · intro r q hq; simpa [rt] using h.payloadTotal r q (by simpa [req] using hq)
  · intro r j hj
    obtain ⟨data,hd,hg⟩ := h.registeredBound r j (by simpa [reg] using hj)
    exact ⟨data,by simpa [rt] using hd,oldGrant _ _ hg⟩
  · intro gen hi
    simp only [it] at hi
    simp only [hold]; split
    · rename_i hc
      have owned : g.footprint ⊆ s.holdings gen (.transfer i) := by
        intro cell member; exact (sourceMembers gen cell).2 ⟨hc.2.symm,hc.1,member⟩
      exact Inventory.move_partition (h.partition gen hi) (by simp) owned
    · exact h.partition gen hi
  · intro gen hi loc
    simp only [it] at hi
    have ne : gen ≠ g.generation := by intro eq; subst gen; simp [h.grantsIssued i g granted] at hi
    simpa [hold,ne] using h.unissuedEmpty gen hi loc
  · intro gen loc cell
    cases loc with
    | gate j => rfl
    | frozen => rfl
    | request r =>
      have old := h.accounted gen (.request r) cell
      by_cases hc : g.writable = true ∧ gen = g.generation <;>
        simpa [hold,hc,Inventory.move,expected,rt,reg] using old
    | use j =>
      by_cases same : j = s.protocol.next
      · subst j
        by_cases hc : g.writable = true ∧ gen = g.generation <;>
          simp [hold,hc,Inventory.move,expected,gt,ent,isUse,freshUse]
      · by_cases source : j = i
        · subst j
          by_cases hc : g.writable = true ∧ gen = g.generation <;>
            simp [hold,hc,Inventory.move,expected,gt,ent,same,granted,transfer,R.resolved,isUse,oldSourceUse]
        · have old := h.accounted gen (.use j) cell
          by_cases hc : g.writable = true ∧ gen = g.generation <;>
            simpa [hold,hc,Inventory.move,expected,gt,ent,same,source,ret] using old
    | transfer j =>
      by_cases same : j = s.protocol.next
      · subst j
        by_cases hc : g.writable = true ∧ gen = g.generation <;>
          simp [hold,hc,Inventory.move,expected,gt,ent,isTransfer,freshTransfer,Ne.symm indexDifferent]
      · by_cases source : j = i
        · subst j
          by_cases hw : g.writable = true <;> by_cases heq : gen = g.generation <;>
            simp [hold,hw,heq,Inventory.move,expected,gt,ent,same,granted,transfer,R.resolved,
              sourceMembers,isTransfer,eq_comm]
        · have old := h.accounted gen (.transfer j) cell
          by_cases hc : g.writable = true ∧ gen = g.generation <;>
            simpa [hold,hc,Inventory.move,expected,gt,ent,same,source] using old
  · intro gen j cell hc
    simp only [hold] at hc
    split at hc
    · rename_i moved
      have notSource : Location.gate j ≠ .transfer i := by simp
      simp only [Inventory.move,if_neg notSource] at hc
      split at hc
      · rename_i same
        have jnew : j = s.protocol.next := Location.gate.inj same
        subst j
        rcases List.mem_append.mp hc with old | member
        · obtain ⟨oldg,_,hg,_⟩ := h.gateInventory gen s.protocol.next cell old
          simp [freshGrant] at hg
        · exact ⟨g,{generation := e.generation,kind := .gate destination},by simp [gt],by simp [ent],
            moved.2.symm,by simpa using congrArg Q.Kind.gate owner.symm,member⟩
      · obtain ⟨grant,n,hg,hn,hgen,hkind,hcell⟩ := h.gateInventory gen j cell hc
        obtain ⟨after,ha,_,ak,_,_⟩ := forward j n hn
        exact ⟨grant,after,oldGrant _ _ hg,ha,hgen,ak.trans hkind,hcell⟩
    · obtain ⟨grant,n,hg,hn,hgen,hkind,hcell⟩ := h.gateInventory gen j cell hc
      obtain ⟨after,ha,_,ak,_,_⟩ := forward j n hn
      exact ⟨grant,after,oldGrant _ _ hg,ha,hgen,ak.trans hkind,hcell⟩
  · intro j hj
    obtain ⟨n,b,hn,hkind,hseal⟩ := h.returnedSound j (by simpa [ret] using hj)
    obtain ⟨after,ha,_,ak,_,aseal⟩ := forward j n hn
    exact ⟨after,b,ha,ak.trans hkind,aseal hseal⟩
  · intro r data hd hr
    simpa [Frozen,frozenEqual] using h.readerPayload r data (by simpa [rt] using hd) hr
  · intro j grant hg hr
    simp only [gt] at hg
    split at hg
    · have eq : grant = g := Option.some.inj hg.symm
      subst grant; simpa [Frozen,frozenEqual] using h.readerGrant i g granted hr
    · simpa [Frozen,frozenEqual] using h.readerGrant j grant hg hr
  · intro j cell hc
    simp only [lt] at hc
    split at hc
    · rename_i enabled
      rcases List.mem_append.mp hc with old | member
      · obtain ⟨grant,hg,hcell,hf⟩ := h.readableSound j cell old
        exact ⟨grant,oldGrant _ _ hg,hcell,by simpa [frozenEqual] using hf⟩
      · have same := enabled.2
        subst j
        exact ⟨g,by simp [gt],member,by simpa [frozenEqual] using h.readerGrant i g granted enabled.1 member⟩
    · obtain ⟨grant,hg,hcell,hf⟩ := h.readableSound j cell hc
      exact ⟨grant,oldGrant _ _ hg,hcell,by simpa [frozenEqual] using hf⟩
  · intro j grant n hg hn hw
    by_cases same : j = s.protocol.next
    · subst j
      have eq : n = ({generation := e.generation,kind := .gate destination} : R.Entry Agent) := by simpa [ent] using hn.symm
      subst n; simp
    · have hgOld : s.grants j = some grant := by simpa [gt,same] using hg
      by_cases source : j = i
      · subst j
        have eq : n = R.resolved e s.protocol.next := by simpa [ent,same] using hn.symm
        subst n
        exact h.sequential i grant e hgOld found hw
      · exact h.sequential j grant n hgOld (by simpa [ent,same,source] using hn) hw

end Aurora.A
