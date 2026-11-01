import A.Activation
import A.Admission
import A.Registration
import A.Safety
import R.Witnesses
namespace Aurora.A

variable {Agent : Type} {s t u : State Agent}

def Reaches (issuer initialSubject : Agent) (allocation : Extent) (s t : State Agent) : Prop :=
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
def allocation : Extent := ⟨0, 16⟩
def defaultGrant : Grant CPU := ⟨0, 1, 0, allocation, true, true⟩
def entry (s : State CPU) (i : Nat) : R.Entry CPU :=
  (s.protocol.entries i).getD { generation := 0, kind := .gate 1 }
def cap (s : State CPU) (i : Nat) : Grant CPU := (s.grants i).getD defaultGrant
def payload (s : State CPU) (r : R.RequestId) : Payload CPU :=
  (s.payloads r).getD ⟨defaultGrant, r.1⟩
def pub (s : State CPU) (i : Nat) := atProtocol s (R.put s.protocol i { entry s i with published := true })
def submit (s : State CPU) (i : Nat) := atProtocol s (R.put s.protocol i { entry s i with work := (entry s i).work + 1 })
def finish (s : State CPU) (i : Nat) := atProtocol s (R.put s.protocol i { entry s i with work := 0 })
def grant (s : State CPU) (nonce i : Nat) := atProtocol s
  (R.enqueue (R.putRequest s.protocol (0, nonce) ⟨none, true⟩) (.publish i))
def request (s : State CPU) (nonce : Nat) (extent : Extent) (write : Bool) :=
  requestState s 0 nonce (cap s 0) none extent write false
def register (s : State CPU) (nonce : Nat) :=
  registeredState s (0, nonce) none (entry s 0) 1 (payload s (0, nonce))

def s0 : State CPU := initial
def s1 := rootState s0 0 1 allocation
def s2 := pub s1 0
def s3 := request s2 0 allocation true
def s4 := register s3 0
def s5 := grant s4 0 1
def s6 := pub s5 1
def s7 := submit s6 1
def s8 := closeUse s7 1 (entry s7 1)
def s9 := finish s8 1
def s10 := sealRetire s9 1 (entry s9 1)
def s11 := move s10 0 (.gate 0)
def s12 := readEnable (move s11 0 (.frozen 0)) 0
def s13 := request s12 1 ⟨0, 8⟩ false
def s14 := register s13 1
def s15 := grant s14 1 2
def s16 := pub s15 2
def s17 := submit s16 2
def s18 := request s17 2 ⟨4, 12⟩ false
def s19 := register s18 2
def s20 := grant s19 2 3
def s21 := pub s20 3
def s22 := submit s21 3

abbrev Reached (s : State CPU) := Reachable 0 1 allocation s
abbrev Goes (s t : State CPU) := Reaches 0 1 allocation s t

theorem step1 : Goes s0 s1 := Reaches.single (.root _ rfl (by decide) rfl)
theorem step2 : Goes s1 s2 := Reaches.single (.passive _ _ (.publish _ 0 (entry s1 0)
  (by decide) rfl (by trivial) rfl))
theorem step3 : Goes s2 s3 := Reaches.single (.request _ 0 0 (entry s2 0) (cap s2 0) none allocation true false
  rfl rfl rfl rfl rfl rfl (by decide) (by simp) (by simp) (by decide))
theorem step4 : Goes s3 s4 := Reaches.single (.register _ (0,0) none (entry s3 0) 1 (payload s3 (0,0))
  (by decide) rfl rfl rfl rfl)
theorem step5 : Goes s4 s5 := Reaches.single (.passive _ _ (.grant _ (0,0) 1 ⟨none,false⟩ (by decide) rfl))
theorem step6 : Goes s5 s6 := Reaches.single (.passive _ _ (.publish _ 1 (entry s5 1)
  (by decide) rfl (by trivial) rfl))
theorem step7 : Goes s6 s7 := Reaches.single (.submit _ 1 (entry s6 1) (cap s6 1) rfl rfl rfl rfl rfl (by intro _; rfl))
theorem step8 : Goes s7 s8 := closeUse_reaches rfl rfl rfl
theorem step9 : Goes s8 s9 := Reaches.trans
  (Reaches.single (.effect _ 1 (entry s8 1) (cap s8 1) 5 rfl rfl rfl (by decide) (by decide)))
  (Reaches.single (.passive _ _ (.finishOne _ 1 0 (entry s8 1) 1 rfl rfl rfl)))
theorem step10 : Goes s9 s10 := sealUse_reaches rfl rfl rfl rfl
theorem step11 : Goes s10 s11 := Reaches.single (.returnUse _ (0,0) 1 (entry s10 1) (payload s10 (0,0))
  rfl rfl rfl rfl rfl rfl rfl)
theorem step12 : Goes s11 s12 := Reaches.single (.freeze _ 0 (cap s11 0) rfl rfl)
theorem step13 : Goes s12 s13 := Reaches.single (.request _ 0 1 (entry s12 0) (cap s12 0) none ⟨0,8⟩ false false
  rfl rfl rfl rfl rfl rfl (by decide) (by simp) (by simp) (by decide))
theorem step14 : Goes s13 s14 := Reaches.single (.register _ (0,1) none (entry s13 0) 1 (payload s13 (0,1))
  (by decide) rfl rfl rfl rfl)
theorem step15 : Goes s14 s15 := Reaches.single (.passive _ _ (.grant _ (0,1) 2 ⟨none,false⟩ (by decide) rfl))
theorem step16 : Goes s15 s16 := Reaches.single (.passive _ _ (.publish _ 2 (entry s15 2)
  (by decide) rfl (by trivial) rfl))
theorem step17 : Goes s16 s17 := Reaches.single (.submit _ 2 (entry s16 2) (cap s16 2) rfl rfl rfl rfl rfl (by decide))
theorem step18 : Goes s17 s18 := Reaches.single (.request _ 0 2 (entry s17 0) (cap s17 0) none ⟨4,12⟩ false false
  rfl rfl rfl rfl rfl rfl (by decide) (by simp) (by simp) (by decide))
theorem step19 : Goes s18 s19 := Reaches.single (.register _ (0,2) none (entry s18 0) 1 (payload s18 (0,2))
  (by decide) rfl rfl rfl rfl)
theorem step20 : Goes s19 s20 := Reaches.single (.passive _ _ (.grant _ (0,2) 3 ⟨none,false⟩ (by decide) rfl))
theorem step21 : Goes s20 s21 := Reaches.single (.passive _ _ (.publish _ 3 (entry s20 3)
  (by decide) rfl (by trivial) rfl))
theorem step22 : Goes s21 s22 := Reaches.single (.submit _ 3 (entry s21 3) (cap s21 3) rfl rfl rfl rfl rfl (by decide))

theorem reaches7 : Reached s7 := step1.trans (step2.trans (step3.trans (step4.trans (step5.trans (step6.trans step7)))))
theorem reaches12 : Reached s12 := Reaches.trans reaches7 (step8.trans (step9.trans (step10.trans (step11.trans step12))))
theorem reaches22 : Reached s22 := Reaches.trans reaches12 (step13.trans (step14.trans (step15.trans
  (step16.trans (step17.trans (step18.trans (step19.trans (step20.trans (step21.trans step22)))))))))

theorem active_writer_close_keeps_effect : s8.protocol.phase = .active ∧
    Step 0 1 allocation s8 (.access 0 1 5 true) s8 := by
  refine ⟨rfl, .effect _ 1 (entry s8 1) (cap s8 1) 5 rfl rfl rfl (by decide) (by decide)⟩

theorem overlapping_readers : s22.protocol.phase = .active ∧ Frozen s22 0 ∧
    Enabled s22 2 5 false ∧ Enabled s22 3 5 false := by
  refine ⟨rfl, ⟨0,rfl⟩, ?_, ?_⟩
  · exact ⟨entry s22 2, cap s22 2, rfl, rfl, rfl, by decide, by decide, rfl⟩
  · exact ⟨entry s22 3, cap s22 3, rfl, rfl, rfl, by decide, by decide, rfl⟩

def s23 := atProtocol s22 { s22.protocol with phase := .closing }
def s24 := closeUse s23 0 (entry s23 0)
def s25 := sealRetire s24 0 (entry s24 0)
def s26 := closeUse s25 2 (entry s25 2)
def s27 := finish s26 2
def s28 := sealRetire s27 2 (entry s27 2)
def s29 := closeUse s28 3 (entry s28 3)
def s30 := finish s29 3
def s31 := sealRetire s30 3 (entry s30 3)
def s32 := atProtocol s31 { s31.protocol with phase := .quiescent }
def s33 := atProtocol s32 { s32.protocol with generation := 1, phase := .active }
def s34 := rootState s33 0 1 allocation

theorem root_settled : R.Settled s24.protocol 0 := by
  intro r q found source
  change (if r = (0,2) then some ⟨none,true⟩ else if r = (0,2) then some ⟨none,false⟩ else
    if r = (0,1) then some ⟨none,true⟩ else if r = (0,1) then some ⟨none,false⟩ else
    if r = (0,0) then some ⟨none,true⟩ else if r = (0,0) then some ⟨none,false⟩ else none) = some q at found
  by_cases two : r = (0,2)
  · simp [two] at found; cases found; rfl
  by_cases one : r = (0,1)
  · simp [one] at found; cases found; rfl
  by_cases zero : r = (0,0)
  · simp [zero] at found; cases found; rfl
  · simp [two,one,zero] at found

theorem reaches31 : Reached s31 := by
  apply Reaches.trans reaches22
  apply Reaches.trans (Reaches.single (.passive _ _ (.beginClose _ rfl)))
  apply Reaches.trans (closeGate_reaches (s := s23) (i := 0) (e := entry s23 0) rfl rfl rfl)
  apply Reaches.trans (sealGate_reaches (s := s24) (i := 0) (e := entry s24 0) rfl rfl rfl root_settled)
  apply Reaches.trans (closeUse_reaches (s := s25) (i := 2) (e := entry s25 2) rfl rfl rfl)
  apply Reaches.trans (Reaches.single (.effect s26 2 (entry s26 2) (cap s26 2) 5 rfl rfl rfl (by decide) (by decide)))
  apply Reaches.trans (Reaches.single (.passive _ _ (.finishOne s26.protocol 2 0 (entry s26 2) 1 rfl rfl rfl)))
  apply Reaches.trans (sealUse_reaches (s := s27) (i := 2) (e := entry s27 2) rfl rfl rfl rfl)
  apply Reaches.trans (closeUse_reaches (s := s28) (i := 3) (e := entry s28 3) rfl rfl rfl)
  apply Reaches.trans (Reaches.single (.effect s29 3 (entry s29 3) (cap s29 3) 5 rfl rfl rfl (by decide) (by decide)))
  apply Reaches.trans (Reaches.single (.passive _ _ (.finishOne s29.protocol 3 0 (entry s29 3) 1 rfl rfl rfl)))
  exact sealUse_reaches (s := s30) (i := 3) (e := entry s30 3) rfl rfl rfl rfl

theorem final_entry_facts (i : Nat) (bound : i < 4) :
    (s31.protocol.entries i).map R.Entry.live = some false ∧
    (s31.protocol.entries i).map R.Entry.receipt = some true := by
  have choices : i = 0 ∨ i = 1 ∨ i = 2 ∨ i = 3 := by omega
  rcases choices with eq | eq | eq | eq <;> subst i <;> exact ⟨rfl,rfl⟩

theorem final_empty : R.LedgerEmpty s31.protocol := by
  intro i e found
  have bound : i < 4 := Q.registered_lt (reachable_protocol_invariant reaches31).1 (R.project_found found)
  have live := (final_entry_facts i bound).1
  rw [found] at live
  exact Option.some.inj live

theorem final_gates : R.GatesAcknowledged s31.protocol := by
  intro i e a found gate
  have bound : i < 4 := Q.registered_lt (reachable_protocol_invariant reaches31).1 (R.project_found found)
  have receipt := (final_entry_facts i bound).2
  rw [found] at receipt
  exact Option.some.inj receipt

theorem successful_reuse : Reached s34 ∧ s34.protocol.generation = 1 ∧
    s34.tokens 1 = .gate 4 ∧ s34.tokens 0 = .frozen 0 := by
  refine ⟨?_,rfl,rfl,rfl⟩
  apply Reaches.trans reaches31
  apply Reaches.trans (Reaches.single (.passive _ _ (.quiesce _ rfl final_empty final_gates)))
  apply Reaches.trans (Reaches.single (.reuse s32 rfl))
  exact Reaches.single (.root s33 rfl (by decide) rfl)

def staleClosed := atProtocol s34 (R.put s34.protocol 2 { entry s34 2 with closed := true })

theorem stale_close_isolated_after_reuse : Step 0 1 allocation s34 .internal staleClosed ∧
    staleClosed.protocol.entries 4 = s34.protocol.entries 4 ∧
    staleClosed.tokens 1 = .gate 4 ∧ (entry staleClosed 2).generation = 0 ∧
    (entry staleClosed 2).work = 0 := by
  exact ⟨.passive _ _ (.close _ 2 (entry s34 2) (by decide) rfl (by trivial)),rfl,rfl,rfl,rfl⟩

/-- A separate writer delegation consumes one token through request and transfer
    escrow; packet duplication/loss never recovers or mints another token. -/
def d3 := requestState s2 0 0 (cap s2 0) (some 2) ⟨2,10⟩ true false
def d4 := registeredState d3 (0,0) (some 2) (entry d3 0) 1 (payload d3 (0,0))
def d5 := atProtocol d4 (R.enqueue (R.putRequest d4.protocol (0,0) ⟨some 2,true⟩) (.activate 1))
def d6 := activatedState d5 1 (entry d5 1) 2 (cap d5 1)
def d7 := pub d6 2
def d8 := atProtocol d7 (R.enqueue d7.protocol (.publish 2))
def lostTransfer := atProtocol d5 { d5.protocol with packets := [] }

theorem reaches_d5 : Reached d5 := by
  apply Reaches.trans step1
  apply Reaches.trans step2
  apply Reaches.trans (Reaches.single (.request s2 0 0 (entry s2 0) (cap s2 0) (some 2) ⟨2,10⟩ true false
    rfl rfl rfl rfl rfl rfl (by decide) (by decide) (by simp) (by decide)))
  apply Reaches.trans (channel_roundtrip (s := d3) (packet := .register (0,0) (some 2)) (by decide))
  apply Reaches.trans (Reaches.single (.register d3 (0,0) (some 2) (entry d3 0) 1 (payload d3 (0,0))
    (by decide) rfl rfl rfl rfl))
  apply Reaches.trans (registration_roundtrip (s := d4) (r := (0,0)) (destination := some 2) (i := 1) (by decide) rfl)
  exact Reaches.single (.passive _ _ (.grant _ (0,0) 1 ⟨some 2,false⟩ (by decide) rfl))

theorem writer_delegation_success : Reached d8 ∧ d8.tokens 0 = .gate 2 ∧
    d8.protocol.next = 3 ∧ (cap d8 2).subject = 2 ∧ (cap d8 2).extent = ⟨2,10⟩ := by
  refine ⟨?_,rfl,rfl,rfl,rfl⟩
  apply Reaches.trans reaches_d5
  apply Reaches.trans (channel_roundtrip (s := d5) (packet := .activate 1) (by decide))
  apply Reaches.trans (Reaches.single (.activate d5 1 (entry d5 1) 2 (cap d5 1) (by decide) rfl rfl rfl rfl))
  apply Reaches.trans (Reaches.single (.passive _ _ (.publish _ 2 (entry d6 2) (by decide) rfl (by trivial) rfl)))
  exact Reaches.single (.passive _ _ (.duplicateActivate _ 1 2 (entry d7 1) 2 (by decide) rfl rfl rfl))

theorem transfer_loss_retains_escrow : Reached lostTransfer ∧
    lostTransfer.tokens 0 = .transfer 1 ∧ (entry lostTransfer 1).live = true ∧
    (entry lostTransfer 1).sealed = false := by
  refine ⟨?_,rfl,rfl,rfl⟩
  apply Reaches.trans reaches_d5
  exact Reaches.single (.passive _ _ (.lose _ [] (by simp)))

theorem duplicate_activation_no_new_owner : Step 0 1 allocation d7 .internal d8 ∧
    d8.tokens = d7.tokens ∧ d8.grants = d7.grants ∧ d8.protocol.next = d7.protocol.next := by
  exact ⟨.passive _ _ (.duplicateActivate _ 1 2 (entry d7 1) 2 (by decide) rfl rfl rfl),rfl,rfl,rfl⟩

end Witness
end Aurora.A
