import B.Basic
namespace Aurora.B
/-- All payload AND control writes are accounted in the same address space. -/
def written : Event → Option (Nat × Byte)
  | .payload _ _ _ cell value | .write _ _ cell value | .control cell value => some (cell,value)
  | _ => none

def applyEvent (heap : Heap) (event : Event) : Heap :=
  match written event with
  | none => heap
  | some (cell,value) => store heap cell value

def replay (heap : Heap) : List Event → Heap
  | [] => heap
  | event :: events => replay (applyEvent heap event) events

theorem step_heap (step : Step issuer subject config s event t) : t.heap = applyEvent s.heap event := by
  cases step <;> rfl

theorem trace_heap (trace : Trace issuer subject config s events t) : t.heap = replay s.heap events := by
  induction trace with
  | nil => rfl
  | cons step tail ih => exact ih.trans (congrArg (fun heap => replay heap _) (step_heap step))

theorem applyEvent_frame (untouched : ∀ value, written event ≠ some (cell,value)) :
    applyEvent heap event cell = heap cell := by
  cases found : written event with
  | none => simp only [applyEvent,found]
  | some pair =>
    obtain ⟨address,value⟩ := pair
    simp only [applyEvent,found]
    exact store_other _ _ _ _ (by intro same; subst address; exact untouched value found)

/-- Global interleaving frame: excludes ALL actual write events, not just one
cursor's destination. Other independent writers may change their own bytes. -/
theorem trace_frame (trace : Trace issuer subject config s events t)
    (untouched : ∀ event ∈ events, ∀ value, written event ≠ some (cell,value)) : t.heap cell = s.heap cell := by
  induction trace with
  | nil => rfl
  | cons step tail ih =>
    have rest := ih (fun event member => untouched event (List.mem_cons_of_mem _ member))
    rw [rest,step_heap step]
    exact applyEvent_frame (untouched _ (List.mem_cons_self))

theorem step_spent (step : Step issuer subject config s event t) (spent : s.spent ticket = true) :
    t.spent ticket = true := by
  cases step with
  | beginCopy i d fresh empty valid admission =>
    by_cases same : ticket = i
    · simp [start,same]
    · simpa [start,same] using spent
  | protocol | payload | write | control | fault | release => exact spent

theorem trace_spent (trace : Trace issuer subject config s events t) (spent : s.spent ticket = true) :
    t.spent ticket = true := by
  induction trace with
  | nil => exact spent
  | cons step tail ih => exact ih (step_spent step spent)

theorem no_restart (trace : Trace issuer subject config s events t) (spent : s.spent ticket = true) :
    ¬ t.spent ticket = false := by
  rw [trace_spent trace spent]
  exact Bool.noConfusion

/-- Fault is not rollback, completion, authority return, or control cleanup. -/
theorem fault_frame (s : State Agent) (c : Cursor) : (putCursor s ticket (some {c with phase := .faulted})).heap = s.heap := rfl
end Aurora.B
