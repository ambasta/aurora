import A.Simulation
import R.Witnesses
namespace Aurora.A
set_option maxHeartbeats 300000
set_option maxRecDepth 4096

variable {Agent : Type} {s t u : State Agent}

def Reaches (issuer initialSubject : Agent) (allocation : Footprint) (s t : State Agent) : Prop :=
  ∃ events, Trace issuer initialSubject allocation s events t

theorem Trace.append (a : Trace issuer initialSubject allocation s xs t)
    (b : Trace issuer initialSubject allocation t ys u) :
    Trace issuer initialSubject allocation s (xs ++ ys) u := by
  induction a with
  | nil => exact b
  | cons step tail ih => exact .cons step (ih b)

theorem Reaches.trans (a : Reaches issuer initialSubject allocation s t)
    (b : Reaches issuer initialSubject allocation t u) : Reaches issuer initialSubject allocation s u := by
  obtain ⟨xs, a⟩ := a
  obtain ⟨ys, b⟩ := b
  exact ⟨xs ++ ys, a.append b⟩

theorem Reaches.single (step : Step issuer initialSubject allocation s event t) :
    Reaches issuer initialSubject allocation s t := ⟨[event], .cons step (.nil t)⟩

def receiptRetire (s : State Agent) (i : Nat) (e : R.Entry Agent) : State Agent :=
  atProtocol s (R.receiptRetire s.protocol i e)

theorem receiptRetire_reaches (found : s.protocol.entries i = some e)
    (kind : R.Closable e.kind) (sealed : e.sealed = true) :
    Reaches issuer initialSubject allocation s (receiptRetire s i e) := by
  apply Reaches.trans (Reaches.single (.passive _ _ (.sendReceipt _ i e found kind sealed)))
  apply Reaches.trans (Reaches.single (.passive _ _ (.receiveReceipt _ i e.generation e
    (by simp [atProtocol, R.enqueue]) (by exact found) rfl)))
  exact Reaches.single (.passive _ _ (.retire _ i { e with receipt := true } (by simp [atProtocol, R.put]) rfl))

def closeUse (s : State Agent) (i : Nat) (e : R.Entry Agent) : State Agent :=
  atProtocol s (R.closeTicket s.protocol i e)

theorem closeUse_reaches (found : s.protocol.entries i = some e)
    (use : e.kind = .use a) (published : e.published = true) :
    Reaches issuer initialSubject allocation s (closeUse s i e) := by
  apply Reaches.trans (Reaches.single (.passive _ _ (.requestUseClose _ i e a found use published)))
  exact Reaches.single (.passive _ _ (.close _ i e (by simp [atProtocol, R.enqueue]) found
    (by simp [R.Closable, use])))

def sealRetire (s : State Agent) (i : Nat) (e : R.Entry Agent) : State Agent :=
  receiptRetire (atProtocol s (R.put s.protocol i { e with sealed := true })) i { e with sealed := true }

theorem sealUse_reaches (found : s.protocol.entries i = some e) (use : e.kind = .use a)
    (closed : e.closed = true) (drained : e.work = 0) :
    Reaches issuer initialSubject allocation s (sealRetire s i e) := by
  apply Reaches.trans (Reaches.single (.passive _ _ (.sealUse _ i e a found use closed drained)))
  apply receiptRetire_reaches (by simp [atProtocol, R.put])
  · simp [R.Closable, use]
  · rfl

theorem closeGate_reaches (found : s.protocol.entries i = some e)
    (gate : e.kind = .gate a) (closing : s.protocol.phase = .closing) :
    Reaches issuer initialSubject allocation s (closeUse s i e) := by
  apply Reaches.trans (Reaches.single (.passive _ _ (.requestClose _ i e closing found (by simp [gate,R.Closable]))))
  exact Reaches.single (.passive _ _ (.close _ i e (by simp [atProtocol,R.enqueue]) found (by simp [gate,R.Closable])))

theorem sealGate_reaches (found : s.protocol.entries i = some e) (gate : e.kind = .gate a)
    (closed : e.closed = true) (settled : R.Settled s.protocol i) :
    Reaches issuer initialSubject allocation s (sealRetire s i e) := by
  apply Reaches.trans (Reaches.single (.passive _ _ (.sealGate _ i e a found gate closed settled)))
  exact receiptRetire_reaches (by simp [atProtocol,R.put]) (by simp [gate,R.Closable]) rfl

/-- Duplicate one existing packet and lose that copy, without changing authority. -/
theorem channel_roundtrip (present : packet ∈ s.protocol.packets) :
    Reaches issuer initialSubject allocation s s := by
  apply Reaches.trans (Reaches.single (.passive _ _ (.duplicate _ packet present)))
  exact Reaches.single (.passive _ _ (.lose _ s.protocol.packets
    (fun p hp => List.mem_cons_of_mem packet hp)))

/-- Reprocessing a registration resends its retained ID; losing that reply does
    not change the pending transfer or permission escrow. -/
theorem registration_roundtrip (packet : R.Packet.register r destination ∈ s.protocol.packets)
    (registered : s.protocol.registrations r = some i) :
    Reaches issuer initialSubject allocation s s := by
  apply Reaches.trans (Reaches.single (.passive _ _ (.duplicateRegister _ r destination i packet registered)))
  exact Reaches.single (.passive _ _ (.lose _ s.protocol.packets
    (fun p hp => by simpa only [atProtocol,R.enqueue] using
      List.mem_cons_of_mem (R.Packet.grant r i) hp)))

namespace Witness
abbrev CPU := Nat
def allocation : Footprint := [7,9,11,13]
def left : Footprint := [7,11]
def right : Footprint := [9,13]
def defaultGrant : Grant CPU := ⟨0,1,0,allocation,true,true⟩
def entry (s : State CPU) (i : Nat) : R.Entry CPU :=
  (s.protocol.entries i).getD { generation := 0, kind := .gate 1 }
def cap (s : State CPU) (i : Nat) : Grant CPU := (s.grants i).getD defaultGrant
def pub (s : State CPU) (i : Nat) := atProtocol s (R.put s.protocol i { entry s i with published := true })
def root (s : State CPU) := mint (putGrant (atProtocol s
  (R.enqueue (R.issue s.protocol s.protocol.generation (.gate 1)) (.publish s.protocol.next)))
  s.protocol.next ⟨0,1,s.protocol.generation,allocation,true,true⟩)
  s.protocol.generation s.protocol.next allocation

def askAt (s : State CPU) (source nonce : Nat) (g : Grant CPU) (f : Footprint) (write : Bool) :=
  let t := putPayload (atProtocol s (R.enqueue (R.putRequest s.protocol (source,nonce) ⟨none,false⟩)
    (.register (source,nonce) none))) (source,nonce) ⟨child g none f write false,source⟩
  if write then move t g.generation (.gate source) (.request (source,nonce)) f else t
def regAt (s : State CPU) (source nonce : Nat) (e : R.Entry CPU) (g : Grant CPU) :=
  let t := putGrant (atProtocol s (R.enqueue
    (R.registerId (R.issue s.protocol e.generation (.use g.subject)) (source,nonce) s.protocol.next)
    (.grant (source,nonce) s.protocol.next))) s.protocol.next g
  if g.writable then move t g.generation (.request (source,nonce)) (.use s.protocol.next) g.footprint else t
def acceptAt (s : State CPU) (source nonce ticket : Nat) := atProtocol s
  (R.enqueue (R.putRequest s.protocol (source,nonce) ⟨none,true⟩) (.publish ticket))
def publish (s : State CPU) (ticket : Nat) (e : R.Entry CPU) :=
  atProtocol s (R.put s.protocol ticket { e with published := true })
def submit (s : State CPU) (ticket : Nat) (e : R.Entry CPU) :=
  atProtocol s (R.put s.protocol ticket { e with work := e.work + 1 })
def useEntry (generation subject : Nat) : R.Entry CPU := { generation, kind := .use subject }
def admitAt (s : State CPU) (source nonce : Nat) (e : R.Entry CPU) (g : Grant CPU) (f : Footprint) (write : Bool) :=
  let a := askAt s source nonce g f write
  let b := regAt a source nonce e (child g none f write false)
  let c := acceptAt b source nonce s.protocol.next
  let d := publish c s.protocol.next (useEntry e.generation g.subject)
  submit d s.protocol.next { useEntry e.generation g.subject with published := true }

/-- The five original transitions, with only their actual local premises.
No invariant is assumed, so the same helper also checks mutant continuations. -/
theorem admitAt_reaches (s : State CPU) (source nonce : Nat) (e : R.Entry CPU) (g : Grant CPU)
    (f : Footprint) (write : Bool)
    (found : s.protocol.entries source = some e) (gate : e.kind = .gate g.subject)
    (granted : s.grants source = some g) (published : e.published = true) (openGate : e.closed = false)
    (fresh : s.protocol.requests (source,nonce) = none) (unregistered : s.protocol.registrations (source,nonce) = none)
    (within : f.Within g.footprint)
    (permission : if write then g.writable = true ∧ f.Within (s.holdings g.generation (.gate source))
      else f.Within (s.readable source)) :
    Reaches 0 1 allocation s (admitAt s source nonce e g f write) := by
  let a := askAt s source nonce g f write
  let b := regAt a source nonce e (child g none f write false)
  let c := acceptAt b source nonce s.protocol.next
  let d := publish c s.protocol.next (useEntry e.generation g.subject)
  have h1 : Reaches 0 1 allocation s a := Reaches.single (.request s source nonce e g none f write false
    found gate granted published openGate fresh within (by simp) (by simp) permission)
  have h2 : Reaches 0 1 allocation a b := Reaches.single (.register a (source,nonce) none e g.subject
    ⟨child g none f write false,source⟩
    (by cases write <;> simp [a,askAt,putPayload,atProtocol,move,R.enqueue])
    (by cases write <;> simpa [a,askAt,putPayload,atProtocol,move,R.enqueue,R.putRequest] using unregistered)
    (by cases write <;> simpa [a,askAt,putPayload,atProtocol,move,R.enqueue,R.putRequest] using found)
    gate (by cases write <;> simp [a,askAt,putPayload,atProtocol,move]))
  have h3 : Reaches 0 1 allocation b c := Reaches.single (.passive _ _ (.grant _ (source,nonce) s.protocol.next ⟨none,false⟩
    (by cases write <;> simp [a,b,askAt,regAt,child,putGrant,putPayload,atProtocol,move,R.enqueue,R.issue,R.registerId,R.putRequest])
    (by cases write <;> simp [a,b,askAt,regAt,child,putGrant,putPayload,atProtocol,move,R.enqueue,R.issue,R.registerId,R.putRequest,R.put])))
  have h4 : Reaches 0 1 allocation c d := Reaches.single (.passive _ _ (.publish _ s.protocol.next
    (useEntry e.generation g.subject) (by simp [c,acceptAt,atProtocol,R.enqueue])
    (by cases write <;> simp [a,b,c,acceptAt,askAt,regAt,child,putGrant,putPayload,atProtocol,move,R.enqueue,R.issue,R.registerId,R.putRequest,R.put,useEntry])
    (by trivial) rfl))
  have h5 : Reaches 0 1 allocation d (admitAt s source nonce e g f write) := Reaches.single
    (.submit _ s.protocol.next { useEntry e.generation g.subject with published := true }
      (child g none f write false) (by simp [d,publish,atProtocol,R.put]) rfl
      (by cases write <;> simp [a,b,c,d,publish,acceptAt,askAt,regAt,child,putGrant,putPayload,atProtocol,move,R.issue,R.enqueue,R.registerId,R.putRequest])
      rfl rfl (by intro _; rfl))
  exact h1.trans (h2.trans (h3.trans (h4.trans h5)))


def ask (s : State CPU) (nonce : Nat) (g : Grant CPU) (f : Footprint) (write : Bool) := askAt s 0 nonce g f write
def reg (s : State CPU) (nonce : Nat) (e : R.Entry CPU) (g : Grant CPU) := regAt s 0 nonce e g
def accept (s : State CPU) (nonce ticket : Nat) := acceptAt s 0 nonce ticket
def admit (s : State CPU) (nonce : Nat) (e : R.Entry CPU) (g : Grant CPU) (f : Footprint) (write : Bool) :=
  admitAt s 0 nonce e g f write
theorem admit_reaches (s : State CPU) (nonce : Nat) (e : R.Entry CPU) (g : Grant CPU)
    (f : Footprint) (write : Bool)
    (found : s.protocol.entries 0 = some e) (gate : e.kind = .gate g.subject)
    (granted : s.grants 0 = some g) (published : e.published = true) (openGate : e.closed = false)
    (fresh : s.protocol.requests (0,nonce) = none) (unregistered : s.protocol.registrations (0,nonce) = none)
    (within : f.Within g.footprint)
    (permission : if write then g.writable = true ∧ f.Within (s.holdings g.generation (.gate 0))
      else f.Within (s.readable 0)) :
    Reaches 0 1 allocation s (admit s nonce e g f write) :=
  admitAt_reaches s 0 nonce e g f write found gate granted published openGate fresh unregistered within permission

/-- Disable submission, drain one real outstanding item, seal, receive the
exact receipt, and retire. Retirement does not itself return writable cells. -/
def finishUse (s : State CPU) (i : Nat) (e : R.Entry CPU) :=
  let closed := closeUse s i e
  let drained := atProtocol closed (R.put closed.protocol i { e with closed := true, work := 0 })
  sealRetire drained i { e with closed := true, work := 0 }
theorem finishUse_reaches {s : State CPU} {i : Nat} {e : R.Entry CPU} {a : CPU} (found : s.protocol.entries i = some e) (use : e.kind = .use a)
    (published : e.published = true) (work : e.work = 1) :
    Reaches 0 1 allocation s (finishUse s i e) := by
  have h1 := closeUse_reaches (issuer := 0) (initialSubject := 1) (allocation := allocation) found use published
  have h2 : Reaches 0 1 allocation (closeUse s i e)
      (atProtocol (closeUse s i e) (R.put (closeUse s i e).protocol i { e with closed := true, work := 0 })) :=
    Reaches.single (.passive _ _ (.finishOne _ i 0 { e with closed := true } a
      (by simp [closeUse,atProtocol,R.closeTicket,R.put]) use work))
  exact h1.trans (h2.trans (sealUse_reaches (i := i) (e := { e with closed := true, work := 0 }) (by simp [atProtocol,R.put]) use rfl rfl))
def rootEntry : R.Entry CPU := { generation := 0, kind := .gate 1, published := true }
def busyUse : R.Entry CPU := { generation := 0, kind := .use 1, published := true, work := 1 }
def doneUse : R.Entry CPU := { generation := 0, kind := .use 1, published := true, closed := true, sealed := true, receipt := true, live := false }
def returnCells (s : State CPU) (ticket : Nat) (f : Footprint) :=
  markReturned (move s 0 (.use ticket) (.gate 0) f) ticket
def freezeCells (s : State CPU) (f : Footprint) := readEnable (move s 0 (.gate 0) .frozen f) 0 f

def s0 : State CPU := initial
def s1 := root s0
def s2 := pub s1 0
def s3 := admit s2 0 rootEntry defaultGrant left true
def s4 := admit s3 1 rootEntry defaultGrant right true
def s5 := finishUse s4 1 busyUse
def s6 := returnCells s5 1 left
def s7 := admit s6 2 rootEntry defaultGrant left true
def s8 := finishUse s7 3 busyUse
def s9 := returnCells s8 3 left
def s10 := freezeCells s9 left
def s11 := admit s10 3 rootEntry defaultGrant left false
def s12 := admit s11 4 rootEntry defaultGrant [11] false
def s13 := finishUse s12 2 busyUse
def s14 := returnCells s13 2 right
def s15 := freezeCells s14 right
def s16 := finishUse s15 4 busyUse
def s17 := finishUse s16 5 busyUse
def s18 := atProtocol s17 { s17.protocol with phase := .closing }
def s19 := closeUse s18 0 (entry s18 0)
def s20 := sealRetire s19 0 (entry s19 0)
def s21 := atProtocol s20 { s20.protocol with phase := .quiescent }
def s22 := atProtocol s21 { s21.protocol with generation := 1, phase := .active }
def s23 := root s22
abbrev Reached (s : State CPU) := Reachable 0 1 allocation s
abbrev Goes (s t : State CPU) := Reaches 0 1 allocation s t

theorem reaches2 : Reached s2 := by
  exact (Reaches.single (.root s0 rfl rfl)).trans
    (Reaches.single (.passive _ _ (.publish _ 0 (entry s1 0) (by decide) rfl (by trivial) rfl)))
theorem step3 : Goes s2 s3 := admit_reaches _ _ _ _ _ _ rfl rfl rfl rfl rfl rfl rfl (by decide) (by decide)
theorem step4 : Goes s3 s4 := admit_reaches _ _ _ _ _ _ rfl rfl rfl rfl rfl rfl rfl (by decide) (by decide)
theorem reaches4 : Reached s4 := Reaches.trans reaches2 (step3.trans step4)

theorem concurrent_writers : Reached s4 ∧
    Step 0 1 allocation s4 (.access 0 1 11 true) s4 ∧
    Step 0 1 allocation s4 (.access 0 2 9 true) s4 := by
  exact ⟨reaches4,.effect _ 1 busyUse (child defaultGrant none left true false) 11 rfl rfl rfl (by decide) (by decide),
    .effect _ 2 busyUse (child defaultGrant none right true false) 9 rfl rfl rfl (by decide) (by decide)⟩
theorem reaches7 : Reached s7 := by
  apply Reaches.trans reaches4
  apply (Reaches.single concurrent_writers.2.1).trans
  apply (Reaches.single concurrent_writers.2.2).trans
  apply (finishUse_reaches (s := s4) (i := 1) (e := busyUse) rfl rfl rfl rfl).trans
  apply (Reaches.single (.returnUse s5 (0,0) 1 doneUse ⟨child defaultGrant none left true false,0⟩
    rfl rfl rfl rfl rfl rfl rfl rfl rfl)).trans
  exact admit_reaches _ _ _ _ _ _ rfl rfl rfl rfl rfl rfl rfl (by decide) (by decide)

/-- A new reservation consumes the returned cells but cannot reset the old ticket.
The old return guard is false even though the old receipt remains present. -/
theorem duplicate_return_after_reborrow_refused : Reached s7 ∧
    (entry s7 1).receipt = true ∧ s7.returned 1 = true ∧
    ¬s7.returned 1 = false ∧ s7.returned 3 = false ∧
    s7.holdings 0 (.gate 0) = [] ∧ s7.holdings 0 (.use 3) = left := by
  exact ⟨reaches7,rfl,rfl,by decide,rfl,rfl,rfl⟩
theorem reaches12 : Reached s12 := by
  apply Reaches.trans reaches7
  apply (finishUse_reaches (s := s7) (i := 3) (e := busyUse) rfl rfl rfl rfl).trans
  apply (Reaches.single (.returnUse s8 (0,2) 3 doneUse ⟨child defaultGrant none left true false,0⟩
    rfl rfl rfl rfl rfl rfl rfl rfl rfl)).trans
  apply (Reaches.single (.freeze s9 0 rootEntry defaultGrant left rfl rfl rfl (by decide) (by decide))).trans
  apply (admit_reaches s10 3 rootEntry defaultGrant left false
    rfl rfl rfl rfl rfl rfl rfl (by decide) (by decide)).trans
  exact admit_reaches _ _ _ _ _ _ rfl rfl rfl rfl rfl rfl rfl (by decide) (by decide)

theorem overlapping_readers : Reached s12 ∧ s12.protocol.phase = .active ∧ Frozen s12 0 left ∧
    Step 0 1 allocation s12 (.access 0 4 11 false) s12 ∧
    Step 0 1 allocation s12 (.access 0 5 11 false) s12 ∧
    Step 0 1 allocation s12 (.access 0 2 9 true) s12 := by
  exact ⟨reaches12,rfl,(by unfold Frozen; decide),
    .effect _ 4 busyUse (child defaultGrant none left false false) 11 rfl rfl rfl (by decide) (by decide),
    .effect _ 5 busyUse (child defaultGrant none [11] false false) 11 rfl rfl rfl (by decide) (by decide),
    .effect _ 2 busyUse (child defaultGrant none right true false) 9 rfl rfl rfl (by decide) (by decide)⟩
theorem reaches17 : Reached s17 := by
  apply Reaches.trans reaches12
  apply (Reaches.single overlapping_readers.2.2.2.1).trans
  apply (Reaches.single overlapping_readers.2.2.2.2.1).trans
  apply (Reaches.single overlapping_readers.2.2.2.2.2).trans
  apply (finishUse_reaches (s := s12) (i := 2) (e := busyUse) rfl rfl rfl rfl).trans
  apply (Reaches.single (.returnUse s13 (0,1) 2 doneUse ⟨child defaultGrant none right true false,0⟩
    rfl rfl rfl rfl rfl rfl rfl rfl rfl)).trans
  apply (Reaches.single (.freeze s14 0 rootEntry defaultGrant right rfl rfl rfl (by decide) (by decide))).trans
  apply (finishUse_reaches (s := s15) (i := 4) (e := busyUse) rfl rfl rfl rfl).trans
  exact finishUse_reaches (s := s16) (i := 5) (e := busyUse) rfl rfl rfl rfl

theorem full_cover_frozen : Frozen s15 0 allocation := by unfold Frozen; decide


theorem root_settled : R.Settled s19.protocol 0 := by
  intro r q found source
  change (if r = (0,4) then some ⟨none,true⟩ else if r = (0,4) then some ⟨none,false⟩ else
    if r = (0,3) then some ⟨none,true⟩ else if r = (0,3) then some ⟨none,false⟩ else
    if r = (0,2) then some ⟨none,true⟩ else if r = (0,2) then some ⟨none,false⟩ else
    if r = (0,1) then some ⟨none,true⟩ else if r = (0,1) then some ⟨none,false⟩ else
    if r = (0,0) then some ⟨none,true⟩ else if r = (0,0) then some ⟨none,false⟩ else none) = some q at found
  by_cases n4 : r = (0,4)
  · simp only [if_pos n4,Option.some.injEq] at found; cases found; rfl
  simp only [if_neg n4] at found
  by_cases n3 : r = (0,3)
  · simp only [if_pos n3,Option.some.injEq] at found; cases found; rfl
  simp only [if_neg n3] at found
  by_cases n2 : r = (0,2)
  · simp only [if_pos n2,Option.some.injEq] at found; cases found; rfl
  simp only [if_neg n2] at found
  by_cases n1 : r = (0,1)
  · simp only [if_pos n1,Option.some.injEq] at found; cases found; rfl
  simp only [if_neg n1] at found
  by_cases n0 : r = (0,0)
  · simp only [if_pos n0,Option.some.injEq] at found; cases found; rfl
  simp only [if_neg n0] at found
  contradiction

theorem reaches20 : Reached s20 := by
  apply Reaches.trans reaches17
  apply (Reaches.single (.passive _ _ (.beginClose _ rfl))).trans
  apply (closeGate_reaches (s := s18) (i := 0) (e := rootEntry) rfl rfl rfl).trans
  exact sealGate_reaches (s := s19) (i := 0) (e := { rootEntry with closed := true }) rfl rfl rfl root_settled

theorem final_entry_facts (i : Nat) (bound : i < 6) :
    (s20.protocol.entries i).map R.Entry.live = some false ∧
    (s20.protocol.entries i).map R.Entry.receipt = some true := by
  have choices : i = 0 ∨ i = 1 ∨ i = 2 ∨ i = 3 ∨ i = 4 ∨ i = 5 := by omega
  rcases choices with eq | eq | eq | eq | eq | eq <;> subst i <;> exact ⟨rfl,rfl⟩
theorem final_empty : R.LedgerEmpty s20.protocol := by
  intro i e found
  have bound : i < 6 := Q.registered_lt (reachable_protocol_invariant reaches20).1 (R.project_found found)
  have live := (final_entry_facts i bound).1
  rw [found] at live
  exact Option.some.inj live
theorem final_gates : R.GatesAcknowledged s20.protocol := by
  intro i e a found gate
  have bound : i < 6 := Q.registered_lt (reachable_protocol_invariant reaches20).1 (R.project_found found)
  have receipt := (final_entry_facts i bound).2
  rw [found] at receipt
  exact Option.some.inj receipt

theorem successful_reuse : Reached s23 ∧ s23.protocol.generation = 1 ∧
    s23.holdings 1 (.gate 6) = allocation ∧ Frozen s23 0 allocation := by
  refine ⟨?_,rfl,rfl,by unfold Frozen; decide⟩
  apply Reaches.trans reaches20
  apply (Reaches.single (.passive _ _ (.quiesce _ rfl final_empty final_gates))).trans
  apply (Reaches.single (.reuse s21 rfl)).trans
  exact Reaches.single (.root s22 rfl rfl)

def freshGrant : Grant CPU := ⟨0,1,1,allocation,true,true⟩
def freshPublished := publish s23 6 { generation := 1, kind := .gate 1 }
def freshWriter := admitAt freshPublished 6 0
  { generation := 1, kind := .gate 1, published := true } freshGrant left true

/-- Reuse is productive: after all old liabilities retire, a newly admitted
stream really can write the reused backing in generation1. -/
theorem fresh_generation_writer_after_reuse : Reached freshWriter ∧
    Frozen freshWriter 0 allocation ∧
    Step 0 1 allocation freshWriter (.access 1 7 11 true) freshWriter := by
  refine ⟨?_,by unfold Frozen; decide,?_⟩
  · apply Reaches.trans successful_reuse.1
    apply (Reaches.single (.passive _ _ (.publish _ 6 { generation := 1, kind := .gate 1 }
      (by decide) rfl (by trivial) rfl))).trans
    exact admitAt_reaches _ _ _ _ _ _ _ rfl rfl rfl rfl rfl rfl rfl (by decide) (by decide)
  · exact .effect _ 7 { generation := 1, kind := .use 1, published := true, work := 1 }
      (child freshGrant none left true false) 11 rfl rfl rfl (by decide) (by decide)

def staleClosed := atProtocol s23 (R.put s23.protocol 4 { doneUse with closed := true })
theorem stale_close_isolated_after_reuse : Step 0 1 allocation s23 .internal staleClosed ∧
    staleClosed.protocol.entries 6 = s23.protocol.entries 6 ∧
    staleClosed.holdings 1 (.gate 6) = allocation ∧ (entry staleClosed 4).generation = 0 ∧
    (entry staleClosed 4).work = 0 := by
  exact ⟨.passive _ _ (.close _ 4 doneUse (by decide) rfl (by trivial)),rfl,rfl,rfl,rfl⟩


def liveClosed := closeUse s4 1 busyUse
/-- Submission disabling alone is not a drain receipt: queued work can still effect. -/
theorem active_writer_close_keeps_effect : Reached liveClosed ∧ liveClosed.protocol.phase = .active ∧
    Step 0 1 allocation liveClosed (.access 0 1 11 true) liveClosed := by
  exact ⟨Reaches.trans reaches4 (closeUse_reaches rfl rfl rfl),rfl,
    .effect _ 1 { busyUse with closed := true } (child defaultGrant none left true false) 11
      rfl rfl rfl (by decide) (by decide)⟩

/-- Delegation transfers only the reserved scattered footprint. Neither lost
replies nor duplicate registration/activation remint another writable owner. -/
def delegated : Grant CPU := child defaultGrant (some 2) left true false
def d3 := move (putPayload (atProtocol s2 (R.enqueue (R.putRequest s2.protocol (0,0) ⟨some 2,false⟩)
  (.register (0,0) (some 2)))) (0,0) ⟨delegated,0⟩) 0 (.gate 0) (.request (0,0)) left
def d4 := move (putGrant (atProtocol d3 (R.enqueue
  (R.registerId (R.issue d3.protocol 0 (.transfer 2)) (0,0) 1) (.grant (0,0) 1))) 1 delegated)
  0 (.request (0,0)) (.transfer 1) left
def d5 := atProtocol d4 (R.enqueue (R.putRequest d4.protocol (0,0) ⟨some 2,true⟩) (.activate 1))
def transferEntry : R.Entry CPU := { generation := 0, kind := .transfer 2 }
def d6 := move (putGrant (atProtocol d5 (R.enqueue
  (R.issue (R.put d5.protocol 1 (R.resolved transferEntry 2)) 0 (.gate 2)) (.publish 2))) 2 delegated)
  0 (.transfer 1) (.gate 2) left
def d7 := pub d6 2
def d8 := atProtocol d7 (R.enqueue d7.protocol (.publish 2))
def lostTransfer := atProtocol d5 { d5.protocol with packets := [] }

theorem reaches_d5 : Reached d5 := by
  apply Reaches.trans reaches2
  apply (Reaches.single (.request s2 0 0 rootEntry defaultGrant (some 2) left true false
    rfl rfl rfl rfl rfl rfl (by decide) (by decide) (by simp) (by decide))).trans
  apply (channel_roundtrip (s := d3) (packet := .register (0,0) (some 2)) (by decide)).trans
  apply (Reaches.single (.register d3 (0,0) (some 2) rootEntry 1 ⟨delegated,0⟩
    (by decide) rfl rfl rfl rfl)).trans
  apply (registration_roundtrip (s := d4) (r := (0,0)) (destination := some 2) (i := 1) (by decide) rfl).trans
  exact Reaches.single (.passive _ _ (.grant _ (0,0) 1 ⟨some 2,false⟩ (by decide) rfl))
theorem writer_delegation_success : Reached d8 ∧ d8.holdings 0 (.gate 2) = left ∧
    d8.holdings 0 (.gate 0) = right ∧ d8.protocol.next = 3 ∧
    (cap d8 2).subject = 2 ∧ (cap d8 2).footprint = left := by
  refine ⟨?_,rfl,rfl,rfl,rfl,rfl⟩
  apply Reaches.trans reaches_d5
  apply (channel_roundtrip (s := d5) (packet := .activate 1) (by decide)).trans
  apply (Reaches.single (.activate d5 1 transferEntry 2 delegated (by decide) rfl rfl rfl rfl)).trans
  apply (Reaches.single (.passive _ _ (.publish _ 2 { generation := 0, kind := .gate 2 }
    (by decide) rfl (by trivial) rfl))).trans
  exact Reaches.single (.passive _ _ (.duplicateActivate _ 1 2 (R.resolved transferEntry 2) 2 (by decide) rfl rfl rfl))
theorem transfer_loss_retains_escrow : Reached lostTransfer ∧
    lostTransfer.holdings 0 (.transfer 1) = left ∧
    (entry lostTransfer 1).live = true ∧ (entry lostTransfer 1).sealed = false := by
  refine ⟨?_,rfl,rfl,rfl⟩
  apply Reaches.trans reaches_d5
  exact Reaches.single (.passive _ _ (.lose _ [] (by simp)))
theorem duplicate_activation_no_new_owner : Step 0 1 allocation d7 .internal d8 ∧
    d8.holdings = d7.holdings ∧ d8.grants = d7.grants ∧ d8.protocol.next = d7.protocol.next := by
  exact ⟨.passive _ _ (.duplicateActivate _ 1 2 (R.resolved transferEntry 2) 2 (by decide) rfl rfl rfl),rfl,rfl,rfl⟩

/-- Separate agent subjects genuinely execute disjoint writes under one root.
Agent2 can stand for a device/remote endpoint only under R's stated contracts;
this is not proof of physical device completion or coherence. -/
def twoAgentsFirst := admit d8 1 rootEntry defaultGrant right true
def twoAgents := admitAt twoAgentsFirst 2 0 { generation := 0, kind := .gate 2, published := true }
  delegated left true
theorem distinct_agents_concurrent_writers : Reached twoAgents ∧
    (cap twoAgents 3).subject ≠ (cap twoAgents 4).subject ∧
    Step 0 1 allocation twoAgents (.access 0 3 9 true) twoAgents ∧
    Step 0 1 allocation twoAgents (.access 0 4 11 true) twoAgents := by
  refine ⟨?_,by decide,?_,?_⟩
  · apply Reaches.trans writer_delegation_success.1
    apply (admit_reaches d8 1 rootEntry defaultGrant right true
      rfl rfl rfl rfl rfl rfl rfl (by decide) (by decide)).trans
    exact admitAt_reaches _ _ _ _ _ _ _ rfl rfl rfl rfl rfl rfl rfl (by decide) (by decide)
  · exact .effect _ 3 busyUse (child defaultGrant none right true false) 9 rfl rfl rfl (by decide) (by decide)
  · exact .effect _ 4 { generation := 0, kind := .use 2, published := true, work := 1 }
      (child delegated none left true false) 11 rfl rfl rfl (by decide) (by decide)

end Witness
end Aurora.A
