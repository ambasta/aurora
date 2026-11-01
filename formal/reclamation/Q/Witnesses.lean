import Q.Safety

namespace Aurora.Q

variable {Cpu : Type} {s t u : State Cpu} {e : Entry Cpu}

def Reaches (s t : State Cpu) : Prop := ∃ events, Trace s events t

theorem Trace.append (a : Trace s xs t) (b : Trace t ys u) :
    Trace s (xs ++ ys) u := by
  induction a with
  | nil => exact b
  | cons step tail ih => exact .cons step (ih b)

theorem Reaches.trans (a : Reaches s t) (b : Reaches t u) : Reaches s u := by
  obtain ⟨xs, a⟩ := a
  obtain ⟨ys, b⟩ := b
  exact ⟨xs ++ ys, a.append b⟩

theorem Reaches.single (step : Step s event t) : Reaches s t :=
  ⟨[event], .cons step (.nil t)⟩

/-- Physical stop, receipt, retirement: deliberately separate transitions. -/
def finish (s : State Cpu) (i : Nat) (e : Entry Cpu) : State Cpu :=
  put (put (put s i (stopped e)) i (acknowledged (stopped e)))
    i (retired (acknowledged (stopped e)))

theorem finish_reaches (found : s.entries i = some e) : Reaches s (finish s i e) := by
  apply Reaches.trans (Reaches.single (.hardwareStop s i e found))
  apply Reaches.trans (Reaches.single (.ack (put s i (stopped e)) i e.generation
    (stopped e) (by simp [put]) rfl rfl))
  exact Reaches.single (.retire _ i (acknowledged (stopped e)) (by simp [put]) rfl)

namespace Witness

abbrev CPU := Fin 2

def a : CPU := 0
def b : CPU := 1
def gateA : Entry CPU := ⟨0, .gate a, true, true, false⟩
def useA : Entry CPU := ⟨0, .use a, true, true, false⟩
def transferB : Entry CPU := ⟨0, .transfer b, true, true, false⟩
def gateB : Entry CPU := ⟨0, .gate b, true, true, false⟩
def useB : Entry CPU := ⟨0, .use b, true, true, false⟩

def s0 : State CPU := initial
def s1 := issue s0 0 (.gate a)
def s2 := issue s1 0 (.use a)
def s3 := issue s2 0 (.transfer b)
def s4 : State CPU := { s3 with phase := .closing }
def s5 := issue (put s4 2 (resolved transferB)) 0 (.gate b)
def s6 := issue s5 0 (.use b)
def s7 := finish s6 0 gateA
def s8 := finish s7 3 gateB
def s9 := finish s8 1 useA
def s10 := finish s9 4 useB
def s11 : State CPU := { s10 with phase := .quiescent }
def s12 : State CPU := { s11 with generation := 1, phase := .active }
def s13 := issue s12 1 (.gate a)
def s14 := issue s13 1 (.use a)

/-- The receiver activates during Closing; no global instantaneous fence. -/
theorem closing_activation : s4.phase = .closing ∧ Step s4 .internal s5 := by
  exact ⟨rfl, .activate s4 2 transferB b rfl rfl rfl⟩

/-- Both authorities are retired while two admitted uses can still execute. -/
theorem authority_before_drain :
    (s8.entries 0).map Entry.live = some false ∧
    (s8.entries 3).map Entry.live = some false ∧
    Step s8 (.access 0 1) s8 ∧ Step s8 (.access 0 4) s8 := by
  exact ⟨rfl, rfl, .access s8 1 useA a rfl rfl rfl,
    .access s8 4 useB b rfl rfl rfl⟩

theorem finish_entries (s : State Cpu) (i j : Nat) (e : Entry Cpu) :
    (finish s i e).entries j =
      if j = i then some (retired (acknowledged (stopped e))) else s.entries j := by
  by_cases same : j = i <;> simp [finish, put, same]

theorem issue_entries (s : State Cpu) (g : Nat) (k : Kind Cpu) (j : Nat) :
    (issue s g k).entries j =
      if j = s.next then some ⟨g, k, true, true, false⟩ else s.entries j := by
  rfl

theorem entries10 (i : Nat) : s10.entries i =
    if i = 4 then some (retired (acknowledged (stopped useB))) else
    if i = 1 then some (retired (acknowledged (stopped useA))) else
    if i = 3 then some (retired (acknowledged (stopped gateB))) else
    if i = 0 then some (retired (acknowledged (stopped gateA))) else
    if i = 2 then some (resolved transferB) else none := by
  rw [s10, finish_entries, s9, finish_entries, s8, finish_entries, s7, finish_entries]
  by_cases h4 : i = 4
  · simp [h4]
  simp only [if_neg h4]
  by_cases h1 : i = 1
  · simp [h1]
  simp only [if_neg h1]
  by_cases h3 : i = 3
  · simp [h3]
  simp only [if_neg h3]
  by_cases h0 : i = 0
  · simp [h0]
  simp only [if_neg h0]
  by_cases h2 : i = 2 <;> simp [h2, s6, s5, s4, s3, s2, s1, s0, issue, put, initial, h4, h1, h3, h0]

theorem empty10 : LedgerEmpty s10 := by
  intro i e found
  rw [entries10] at found
  split at found
  · cases Option.some.inj found; rfl
  split at found
  · cases Option.some.inj found; rfl
  split at found
  · cases Option.some.inj found; rfl
  split at found
  · cases Option.some.inj found; rfl
  split at found
  · cases Option.some.inj found; rfl
  · cases found

theorem gates10 : GatesAcknowledged s10 := by
  intro i e c found gate
  rw [entries10] at found
  split at found
  · cases Option.some.inj found; rfl
  split at found
  · cases Option.some.inj found; rfl
  split at found
  · cases Option.some.inj found; rfl
  split at found
  · cases Option.some.inj found; rfl
  split at found
  · cases Option.some.inj found; rfl
  · cases found

theorem reaches12 : Reaches s0 s12 := by
  apply Reaches.trans (Reaches.single (.root s0 a rfl))
  apply Reaches.trans (Reaches.single (.admit s1 0 gateA a rfl rfl rfl))
  apply Reaches.trans (Reaches.single (.send s2 0 gateA a b rfl rfl rfl))
  apply Reaches.trans (Reaches.single (.beginClose s3 rfl))
  apply Reaches.trans (Reaches.single closing_activation.2)
  apply Reaches.trans (Reaches.single (.admit s5 3 gateB b rfl rfl rfl))
  apply Reaches.trans (finish_reaches (s := s6) (i := 0) (e := gateA) rfl)
  apply Reaches.trans (finish_reaches (s := s7) (i := 3) (e := gateB) rfl)
  apply Reaches.trans (finish_reaches (s := s8) (i := 1) (e := useA) rfl)
  apply Reaches.trans (finish_reaches (s := s9) (i := 4) (e := useB) rfl)
  apply Reaches.trans (Reaches.single (.quiesce s10 rfl empty10 gates10))
  exact Reaches.single (.reuse s11 rfl)

/-- Constructive success witness, not a fairness or universal progress theorem. -/
theorem successful_reuse : Reachable s14 ∧ Step s14 (.access 1 6) s14 := by
  constructor
  · apply Reaches.trans reaches12
    apply Reaches.trans (Reaches.single (.root s12 a rfl))
    exact Reaches.single (.admit s13 5 ⟨1, .gate a, true, true, false⟩ a rfl rfl rfl)
  · exact .access s14 6 ⟨1, .use a, true, true, false⟩ a rfl rfl rfl

/-- The resolved ticket cannot satisfy the physical premise of `Step.activate`.
    Packet duplicate rejection is abstracted by this permanent resolution state,
    not proved for a concrete receiver or packet queue. -/
theorem resolved_transfer_cannot_activate (e : Entry CPU)
    (found : s12.entries 2 = some e) : e.possible ≠ true := by
  change some (resolved transferB) = some e at found
  cases Option.some.inj found
  decide

theorem old_ack_after_reuse_inert : receiveAck s12 1 0 = s12 :=
  duplicate_ack_inert (e := retired (acknowledged (stopped useA))) rfl rfl

end Witness
end Aurora.Q
