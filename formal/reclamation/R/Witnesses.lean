import R.Preservation

namespace Aurora.R

variable {Agent : Type} {s t u : State Agent} {e : Entry Agent}

def Reaches (s t : State Agent) : Prop := ∃ events, Trace s events t

theorem Trace.append (a : Trace s xs t) (b : Trace t ys u) : Trace s (xs ++ ys) u := by
  induction a with
  | nil => exact b
  | cons step tail ih => exact .cons step (ih b)

theorem Reaches.trans (a : Reaches s t) (b : Reaches t u) : Reaches s u := by
  obtain ⟨xs, a⟩ := a
  obtain ⟨ys, b⟩ := b
  exact ⟨xs ++ ys, a.append b⟩

theorem Reaches.single (step : Step s event t) : Reaches s t :=
  ⟨[event], .cons step (.nil t)⟩

/-- All three receipt-production/receipt-acceptance/retirement steps remain visible. -/
def receiptRetire (s : State Agent) (i : Nat) (e : Entry Agent) : State Agent :=
  put (put (enqueue s (.receipt e.generation i)) i { e with receipt := true })
    i { e with receipt := true, live := false }

theorem receiptRetire_reaches (found : s.entries i = some e)
    (kind : Closable e.kind) (sealed : e.sealed = true) :
    Reaches s (receiptRetire s i e) := by
  apply Reaches.trans (Reaches.single (.sendReceipt s i e found kind sealed))
  apply Reaches.trans (Reaches.single (.receiveReceipt (enqueue s (.receipt e.generation i)) i e.generation e
    (by simp [enqueue]) (by exact found) rfl))
  exact Reaches.single (.retire _ i { e with receipt := true } (by simp [put]) rfl)

def closeTicket (s : State Agent) (i : Nat) (e : Entry Agent) : State Agent :=
  put (enqueue s (.close i)) i { e with closed := true }

theorem closeTicket_reaches (found : s.entries i = some e)
    (closing : s.phase = .closing) (kind : Closable e.kind) :
    Reaches s (closeTicket s i e) := by
  apply Reaches.trans (Reaches.single (.requestClose s i e closing found kind))
  exact Reaches.single (.close (enqueue s (.close i)) i e (by simp [enqueue]) (by exact found) kind)

def sealRetire (s : State Agent) (i : Nat) (e : Entry Agent) : State Agent :=
  receiptRetire (put s i { e with sealed := true }) i { e with sealed := true }

theorem sealGate_reaches (found : s.entries i = some e) (gate : e.kind = .gate a)
    (closed : e.closed = true) (settled : Settled s i) : Reaches s (sealRetire s i e) := by
  apply Reaches.trans (Reaches.single (.sealGate s i e a found gate closed settled))
  apply receiptRetire_reaches (by simp [put])
  · simp [Closable, gate]
  · rfl

theorem sealUse_reaches (found : s.entries i = some e) (use : e.kind = .use a)
    (closed : e.closed = true) (drained : e.work = 0) : Reaches s (sealRetire s i e) := by
  apply Reaches.trans (Reaches.single (.sealUse s i e a found use closed drained))
  apply receiptRetire_reaches (by simp [put])
  · simp [Closable, use]
  · rfl

namespace Witness
deriving instance DecidableEq for Packet
abbrev CPU := Fin 2
def a : CPU := 0
def b : CPU := 1
/-- Only notation for concrete known-present entries; every Step proves lookup. -/
def entryAt (s : State CPU) (i : Nat) : Entry CPU :=
  (s.entries i).getD { generation := 0, kind := .gate a }
def edit (s : State CPU) (i : Nat) (f : Entry CPU → Entry CPU) := put s i (f (entryAt s i))
def pub (s : State CPU) (i : Nat) := edit s i (fun e => { e with published := true })
def submit (s : State CPU) (i : Nat) := edit s i (fun e => { e with work := e.work + 1 })
def ask (s : State CPU) (r : RequestId) (d : Option CPU) :=
  enqueue (putRequest s r ⟨d, false⟩) (.register r d)
def register (s : State CPU) (r : RequestId) (kind : Q.Kind CPU) :=
  enqueue (registerId (issue s 0 kind) r s.next) (.grant r s.next)
def grant (s : State CPU) (r : RequestId) (d : Option CPU) (i : Nat) :=
  enqueue (putRequest s r ⟨d, true⟩) (grantPacket ⟨d, false⟩ i)

def s0 : State CPU := initial
def s1 := enqueue (issue s0 0 (.gate a)) (.publish 0)
def s2 := pub s1 0
def s3 := ask s2 (0, 0) none
def s4 := register s3 (0, 0) (.use a)
def s5 := grant s4 (0, 0) none 1
def s6 := pub s5 1
def s7 := submit s6 1
def s8 := ask s7 (0, 1) (some b)
def s9 : State CPU := { s8 with phase := .closing }
def s10 := closeTicket s9 0 (entryAt s9 0)
def s11 := register s10 (0, 1) (.transfer b)
def s12 := grant s11 (0, 1) (some b) 2
def s13 := enqueue (issue (put s12 2 (resolved (entryAt s12 2) 3)) 0 (.gate b)) (.publish 3)
def s14 := pub s13 3
def s15 := sealRetire s14 0 (entryAt s14 0)
def s16 := ask s15 (3, 0) none
def s17 := register s16 (3, 0) (.use b)
def s18 := grant s17 (3, 0) none 4
def s19 := pub s18 4
def s20 := submit s19 4

theorem root_settled : Settled s14 0 := by
  intro r q found source
  change (if r = (0,1) then some ⟨some b,true⟩ else
    if r = (0,1) then some ⟨some b,false⟩ else
    if r = (0,0) then some ⟨none,true⟩ else
    if r = (0,0) then some ⟨none,false⟩ else none) = some q at found
  by_cases one : r = (0,1)
  · simp only [one, if_true, Option.some.injEq] at found
    cases found; rfl
  by_cases zero : r = (0,0)
  · simp only [if_neg one, if_pos zero, Option.some.injEq] at found
    cases found; rfl
  · simp [one, zero] at found

/-- Exact packet-membership facts are reduced in the finite witness, not assumed. -/
theorem reaches7 : Reaches s0 s7 := by
  apply Reaches.trans (Reaches.single (.root s0 a rfl))
  apply Reaches.trans (Reaches.single (.publish s1 0 (entryAt s1 0) (by decide) rfl (by trivial) rfl))
  apply Reaches.trans (Reaches.single (.request s2 0 0 (entryAt s2 0) a none rfl rfl rfl rfl rfl))
  apply Reaches.trans (Reaches.single (.register s3 (0,0) none (entryAt s3 0) a (by decide) rfl rfl rfl))
  apply Reaches.trans (Reaches.single (.grant s4 (0,0) 1 ⟨none,false⟩ (by decide) rfl))
  apply Reaches.trans (Reaches.single (.publish s5 1 (entryAt s5 1) (by decide) rfl (by trivial) rfl))
  exact Reaches.single (.submit s6 1 (entryAt s6 1) a rfl rfl rfl rfl)

theorem reaches20 : Reaches s0 s20 := by
  apply Reaches.trans reaches7
  apply Reaches.trans (Reaches.single (.request s7 0 1 (entryAt s7 0) a (some b) rfl rfl rfl rfl rfl))
  apply Reaches.trans (Reaches.single (.beginClose s8 rfl))
  apply Reaches.trans (closeTicket_reaches (s := s9) (i := 0) (e := entryAt s9 0) rfl rfl (by trivial))
  apply Reaches.trans (Reaches.single (.register s10 (0,1) (some b) (entryAt s10 0) a (by decide) rfl rfl rfl))
  apply Reaches.trans (Reaches.single (.grant s11 (0,1) 2 ⟨some b,false⟩ (by decide) rfl))
  apply Reaches.trans (Reaches.single (.activate s12 2 (entryAt s12 2) b (by decide) rfl rfl rfl))
  apply Reaches.trans (Reaches.single (.publish s13 3 (entryAt s13 3) (by decide) rfl (by trivial) rfl))
  apply Reaches.trans (sealGate_reaches (s := s14) (i := 0) (e := entryAt s14 0) rfl rfl rfl root_settled)
  apply Reaches.trans (Reaches.single (.request s15 3 0 (entryAt s15 3) b none rfl rfl rfl rfl rfl))
  apply Reaches.trans (Reaches.single (.register s16 (3,0) none (entryAt s16 3) b (by decide) rfl rfl rfl))
  apply Reaches.trans (Reaches.single (.grant s17 (3,0) 4 ⟨none,false⟩ (by decide) rfl))
  apply Reaches.trans (Reaches.single (.publish s18 4 (entryAt s18 4) (by decide) rfl (by trivial) rfl))
  exact Reaches.single (.submit s19 4 (entryAt s19 4) b rfl rfl rfl rfl)

def s21 := closeTicket s20 3 (entryAt s20 3)
def s22 := sealRetire s21 3 (entryAt s21 3)
def s23 := closeTicket s22 1 (entryAt s22 1)
def s24 := edit s23 1 (fun e => { e with work := 0 })
def s25 := sealRetire s24 1 (entryAt s24 1)
def s26 := closeTicket s25 4 (entryAt s25 4)
def s27 := edit s26 4 (fun e => { e with work := 0 })
def s28 := sealRetire s27 4 (entryAt s27 4)
def s29 : State CPU := { s28 with phase := .quiescent }
def s30 : State CPU := { s29 with generation := 1, phase := .active }

theorem receiver_settled : Settled s21 3 := by
  intro r q found source
  change (if r = (3,0) then some ⟨none,true⟩ else
    if r = (3,0) then some ⟨none,false⟩ else
    if r = (0,1) then some ⟨some b,true⟩ else
    if r = (0,1) then some ⟨some b,false⟩ else
    if r = (0,0) then some ⟨none,true⟩ else
    if r = (0,0) then some ⟨none,false⟩ else none) = some q at found
  by_cases three : r = (3,0)
  · simp only [three, if_true, Option.some.injEq] at found
    cases found; rfl
  by_cases one : r = (0,1)
  · simp only [if_neg three, if_pos one, Option.some.injEq] at found
    cases found; rfl
  by_cases zero : r = (0,0)
  · simp only [if_neg three, if_neg one, if_pos zero, Option.some.injEq] at found
    cases found; rfl
  · simp [three, one, zero] at found

theorem reaches26 : Reaches s0 s26 := by
  apply Reaches.trans reaches20
  apply Reaches.trans (closeTicket_reaches (s := s20) (i := 3) (e := entryAt s20 3) rfl rfl (by trivial))
  apply Reaches.trans (sealGate_reaches (s := s21) (i := 3) (e := entryAt s21 3) rfl rfl rfl receiver_settled)
  apply Reaches.trans (closeTicket_reaches (s := s22) (i := 1) (e := entryAt s22 1) rfl rfl (by trivial))
  apply Reaches.trans (Reaches.single (.effect s23 1 (entryAt s23 1) a rfl rfl (by decide)))
  apply Reaches.trans (Reaches.single (.finishOne s23 1 0 (entryAt s23 1) a rfl rfl rfl))
  apply Reaches.trans (sealUse_reaches (s := s24) (i := 1) (e := entryAt s24 1) rfl rfl rfl rfl)
  exact closeTicket_reaches (s := s25) (i := 4) (e := entryAt s25 4) rfl rfl (by trivial)

theorem suffix28 : Reaches s26 s28 := by
  apply Reaches.trans (Reaches.single (.effect s26 4 (entryAt s26 4) b rfl rfl (by decide)))
  apply Reaches.trans (Reaches.single (.finishOne s26 4 0 (entryAt s26 4) b rfl rfl rfl))
  exact sealUse_reaches (s := s27) (i := 4) (e := entryAt s27 4) rfl rfl rfl rfl

theorem reaches28 : Reaches s0 s28 := Reaches.trans reaches26 suffix28

theorem final_entry_facts (i : Nat) (bound : i < 5) :
    (s28.entries i).map Entry.live = some false ∧
    (s28.entries i).map Entry.receipt = some true := by
  have cases : i = 0 ∨ i = 1 ∨ i = 2 ∨ i = 3 ∨ i = 4 := by omega
  rcases cases with h | h | h | h | h <;> subst i <;> exact ⟨rfl, rfl⟩

theorem final_empty : LedgerEmpty s28 := by
  intro i e found
  have bound : i < 5 := Q.registered_lt (reachable_invariant reaches28).1 (project_found found)
  have live := (final_entry_facts i bound).1
  rw [found] at live
  exact Option.some.inj live

theorem final_gates : GatesAcknowledged s28 := by
  intro i e a found kind
  have bound : i < 5 := Q.registered_lt (reachable_invariant reaches28).1 (project_found found)
  have receipt := (final_entry_facts i bound).2
  rw [found] at receipt
  exact Option.some.inj receipt

/-- A real concrete-protocol trace, not merely a projected abstract witness. -/
theorem successful_reuse : Reachable s30 ∧ s30.generation = 1 := by
  refine ⟨?_, rfl⟩
  apply Reaches.trans reaches28
  apply Reaches.trans (Reaches.single (.quiesce s28 rfl final_empty final_gates))
  exact Reaches.single (.reuse s29 rfl)

theorem pending_after_close : (entryAt s10 0).closed = true ∧
    s10.requests (0,1) = some ⟨some b,false⟩ ∧ s10.registrations (0,1) = none := ⟨rfl,rfl,rfl⟩

theorem activation_during_closing : s12.phase = .closing ∧
    Step s12 .internal s13 :=
  ⟨rfl, .activate s12 2 (entryAt s12 2) b (by decide) rfl rfl rfl⟩

theorem retired_parent_live_use : (entryAt s15 0).live = false ∧ (entryAt s15 1).live = true ∧
    Step s15 (.access 0 1) s15 :=
  ⟨rfl, rfl, .effect s15 1 (entryAt s15 1) a rfl rfl (by decide)⟩

theorem queued_effect_after_close : (entryAt s23 1).closed = true ∧
    Step s23 (.access 0 1) s23 :=
  ⟨rfl, .effect s23 1 (entryAt s23 1) a rfl rfl (by decide)⟩

/-- Both aliases name this one backing, through distinct CPU/use tickets. -/
theorem two_live_aliases : (entryAt s20 1).kind = .use a ∧
    (entryAt s20 4).kind = .use b ∧ (entryAt s20 1).work = 1 ∧
    (entryAt s20 4).work = 1 := ⟨rfl,rfl,rfl,rfl⟩

/-- Last queued work remains after all other obligations have retired. -/
theorem last_closed_use : (entryAt s26 4).live = true ∧
    (entryAt s26 4).closed = true ∧ (entryAt s26 4).work = 1 := ⟨rfl,rfl,rfl⟩

/-- Publication cannot pass its local unsealed guard after the final seal. -/
theorem late_publication_disabled : (entryAt s28 4).sealed ≠ false := by decide

/-- A close message can overtake the FIRST publication of a reserved endpoint. -/
def beforePubClosing : State CPU := { s1 with phase := .closing }
def beforePubClosed := closeTicket beforePubClosing 0 (entryAt beforePubClosing 0)
def beforePubSealed := edit beforePubClosed 0 (fun e => { e with sealed := true })

theorem close_before_initial_publication : Reachable beforePubSealed ∧
    Packet.publish 0 ∈ beforePubSealed.packets ∧
    (entryAt beforePubSealed 0).published = false ∧
    (entryAt beforePubSealed 0).sealed ≠ false := by
  refine ⟨?_, by decide, rfl, by decide⟩
  apply Reaches.trans (Reaches.single (.root s0 a rfl))
  apply Reaches.trans (Reaches.single (.beginClose s1 rfl))
  apply Reaches.trans (closeTicket_reaches (s := beforePubClosing) (i := 0)
    (e := entryAt beforePubClosing 0) rfl rfl (by trivial))
  apply Reaches.single (.sealGate beforePubClosed 0 (entryAt beforePubClosed 0) a rfl rfl rfl ?_)
  intro r q found source
  change none = some q at found
  cases found

/-- The queued original publication cannot satisfy the local delivery guard. -/
theorem initial_publication_guard_rejected (e : Entry CPU)
    (found : beforePubSealed.entries 0 = some e) : e.sealed ≠ false := by
  have exactEntry : entryAt beforePubSealed 0 = e := by
    unfold entryAt
    rw [found]
    rfl
  rw [← exactEntry]
  decide

theorem drop_enqueued (s : State Agent) (p : Packet Agent) :
    Step (enqueue s p) .internal s := by
  exact .lose (enqueue s p) s.packets (fun q present => List.mem_cons_of_mem p present)

theorem duplicate_loss_roundtrip : Reaches s26 s26 := by
  apply Reaches.trans (Reaches.single (.duplicate s26 (.publish 4) (by decide)))
  exact Reaches.single (drop_enqueued s26 (.publish 4))

/-- A concrete successful trace can include actual channel duplication and loss. -/
theorem successful_reuse_with_duplicate_loss : Reachable s30 := by
  apply Reaches.trans reaches26
  apply Reaches.trans duplicate_loss_roundtrip
  apply Reaches.trans suffix28
  apply Reaches.trans (Reaches.single (.quiesce s28 rfl final_empty final_gates))
  exact Reaches.single (.reuse s29 rfl)

/-- Owner-driven normal use completion keeps the backing root Active. -/
def activeCloseRequested := enqueue s7 (.close 1)
def activeUseClosed := edit activeCloseRequested 1 (fun e => { e with closed := true })
def activeUseDrained := edit activeUseClosed 1 (fun e => { e with work := 0 })
def activeUseRetired := sealRetire activeUseDrained 1 (entryAt activeUseDrained 1)
def nextUseRequested := ask activeUseRetired (0,1) none
def nextUseRegistered := register nextUseRequested (0,1) (.use a)
def nextUseGranted := grant nextUseRegistered (0,1) none 2
def nextUsePublished := pub nextUseGranted 2
def nextUseSubmitted := submit nextUsePublished 2

theorem active_completion_reaches : Reachable nextUseSubmitted := by
  apply Reaches.trans reaches7
  apply Reaches.trans (Reaches.single (.requestUseClose s7 1 (entryAt s7 1) a rfl rfl rfl))
  apply Reaches.trans (Reaches.single (.close activeCloseRequested 1
    (entryAt activeCloseRequested 1) (by decide) rfl (by trivial)))
  apply Reaches.trans (Reaches.single (.effect activeUseClosed 1
    (entryAt activeUseClosed 1) a rfl rfl (by decide)))
  apply Reaches.trans (Reaches.single (.finishOne activeUseClosed 1 0
    (entryAt activeUseClosed 1) a rfl rfl rfl))
  apply Reaches.trans (sealUse_reaches (s := activeUseDrained) (i := 1)
    (e := entryAt activeUseDrained 1) rfl rfl rfl rfl)
  apply Reaches.trans (Reaches.single (.request activeUseRetired 0 1
    (entryAt activeUseRetired 0) a none rfl rfl rfl rfl rfl))
  apply Reaches.trans (Reaches.single (.register nextUseRequested (0,1) none
    (entryAt nextUseRequested 0) a (by decide) rfl rfl rfl))
  apply Reaches.trans (Reaches.single (.grant nextUseRegistered (0,1) 2
    ⟨none,false⟩ (by decide) rfl))
  apply Reaches.trans (Reaches.single (.publish nextUseGranted 2
    (entryAt nextUseGranted 2) (by decide) rfl (by trivial) rfl))
  exact Reaches.single (.submit nextUsePublished 2 (entryAt nextUsePublished 2) a rfl rfl rfl rfl)

theorem active_completion_and_fresh_use : nextUseSubmitted.phase = .active ∧
    (entryAt nextUseSubmitted 0).closed = false ∧
    (entryAt nextUseSubmitted 1).live = false ∧
    (entryAt nextUseSubmitted 1).receipt = true ∧
    Step nextUseSubmitted (.access 0 2) nextUseSubmitted :=
  ⟨rfl,rfl,rfl,rfl,.effect nextUseSubmitted 2 (entryAt nextUseSubmitted 2) a rfl rfl (by decide)⟩

/-- Close changes only the identified use; it cannot close a fresh ticket. -/
theorem close_preserves_other_ticket (s : State Agent) (i j : Nat) (e : Entry Agent)
    (different : j ≠ i) :
    (put s i { e with closed := true }).entries j = s.entries j := by
  simp [put, different]

def oldCloseOnce := edit nextUseSubmitted 1 (fun e => { e with closed := true })
def oldCloseTwice := edit oldCloseOnce 1 (fun e => { e with closed := true })

/-- The retained old close packet can be delivered twice after a new use exists.
    Both deliveries target ticket 1; ticket 2 remains executable. -/
theorem stale_duplicate_close_isolated :
    Step nextUseSubmitted .internal oldCloseOnce ∧
    Step oldCloseOnce .internal oldCloseTwice ∧
    oldCloseTwice.entries 2 = nextUseSubmitted.entries 2 ∧
    Step oldCloseTwice (.access 0 2) oldCloseTwice := by
  exact ⟨.close nextUseSubmitted 1 (entryAt nextUseSubmitted 1) (by decide) rfl (by trivial),
    .close oldCloseOnce 1 (entryAt oldCloseOnce 1) (by decide) rfl (by trivial),
    rfl, .effect oldCloseTwice 2 (entryAt oldCloseTwice 2) a rfl rfl (by decide)⟩

end Witness
end Aurora.R
