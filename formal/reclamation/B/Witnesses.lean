import B.Admission
import B.Model
import B.Finish
namespace Aurora.B.Witnesses

def config : Config := ⟨[0,1],4096,2,[8192]⟩
def initialHeap : Heap := fun cell => if cell = 4096 then ⟨7,by decide⟩ else if cell = 4097 then ⟨9,by decide⟩ else ⟨0,by decide⟩
def gateEntry : R.Entry Unit := {generation := 0,kind := .gate ()}
def root : A.State Unit := A.mint (A.putGrant (A.atProtocol A.initial
  (R.enqueue (R.issue R.initial 0 (.gate ())) (.publish 0))) 0 ⟨(),(),0,[0,1],true,true⟩) 0 0 [0,1]
def owner : A.State Unit := A.atProtocol root (R.put root.protocol 0 {gateEntry with published := true})
def grant : A.Grant Unit := ⟨(),(),0,[0,1],true,true⟩
def descriptor : Descriptor := ⟨0,4096,0,2⟩
def admitted : A.State Unit := writerState owner 0 0 {gateEntry with published := true} grant [0,1]

theorem root_reachable : A.Reachable () () config.allocation owner := by
  refine ⟨[.internal,.internal],.cons (t := root) ?_ (.cons ?_ (.nil _))⟩
  · exact A.Step.root A.initial rfl rfl
  · exact .passive root _ (.publish root.protocol 0 gateEntry (by exact List.mem_cons_self) rfl (by trivial) rfl)

theorem admitted_reachable : A.Reachable () () config.allocation admitted := by
  exact (admit_writer (source := 0) (e := {gateEntry with published := true}) (g := grant) (nonce := 0) (footprint := [0,1]) root_reachable (by rfl) rfl (by rfl)
    rfl rfl rfl (fun _ h => h) rfl (fun _ h => h)).1

theorem config_valid : config.Valid := by
  refine ⟨by decide,by decide,?_,?_⟩
  · intro cell range member
    simp only [config,List.mem_cons,List.not_mem_nil,or_false] at member
    rcases member with rfl | rfl <;> dsimp [config,inRange] at range <;> omega
  · intro cell member
    simp only [config,List.mem_cons,List.not_mem_nil,or_false] at member
    subst cell
    dsimp [config,inRange]
    decide

theorem descriptor_valid : descriptor.Valid config := by
  unfold Descriptor.Valid descriptor config wordLimit
  decide

theorem admitted_authorized : Authorized admitted 1 descriptor := by
  obtain ⟨entry,granted⟩ := writer_state_facts owner 0 0 {gateEntry with published := true} grant [0,1]
  refine ⟨writerEntry 0 (),A.child grant none [0,1] true false,entry,granted,rfl,by decide,rfl,rfl,?_⟩
  intro offset bound
  change offset < 2 at bound
  change 0 + offset ∈ [0,1]
  have : offset = 0 ∨ offset = 1 := by omega
  rcases this with rfl | rfl <;> decide

def s0 : State Unit := initial admitted initialHeap
def s1 := start s0 1 descriptor
def c0 : Cursor := ⟨descriptor,0,.running⟩
def s2 := copy s1 1 c0
def s3 := copy s2 1 (advance c0)
def failed := putCursor s2 1 (some {(advance c0) with phase := .faulted})

theorem begin_step : Step () () config s0 (.beginCopy 1) s1 :=
  .beginCopy s0 1 descriptor rfl rfl descriptor_valid admitted_authorized

theorem first_byte : Step () () config s1 (.payload 0 1 4096 0 ⟨7,by decide⟩) s2 :=
  .payload s1 1 c0 rfl rfl (by decide)

theorem second_byte : Step () () config s2 (.payload 0 1 4097 1 ⟨9,by decide⟩) s3 :=
  .payload s2 1 (advance c0) rfl rfl (by decide)

theorem successful_copy : Trace () () config s0
    [.beginCopy 1,.payload 0 1 4096 0 ⟨7,by decide⟩,.payload 0 1 4097 1 ⟨9,by decide⟩] s3 :=
  .cons begin_step (.cons first_byte (.cons second_byte (.nil _)))

theorem partial_fault : Trace () () config s0
    [.beginCopy 1,.payload 0 1 4096 0 ⟨7,by decide⟩,.fault 1] failed :=
  .cons begin_step (.cons first_byte (.cons (.fault s2 1 (advance c0) rfl rfl) (.nil _)))

theorem successful_bytes : s3.heap 0 = ⟨7,by decide⟩ ∧ s3.heap 1 = ⟨9,by decide⟩ ∧
    s3.cursors 1 = some ⟨descriptor,2,.done⟩ := by decide

theorem partial_bytes : failed.heap 0 = ⟨7,by decide⟩ ∧ failed.heap 1 = ⟨0,by decide⟩ ∧
    failed.authority = admitted := by exact ⟨rfl,rfl,rfl⟩
/-- Closing the use does not discard queued work or prevent the held byte stream. -/
def closeQueued : State Unit := {s1 with authority := A.atProtocol admitted (R.enqueue admitted.protocol (.close 1))}
def closed : State Unit := {closeQueued with authority := A.atProtocol closeQueued.authority (R.put closeQueued.authority.protocol 1 {(writerEntry 0 ()) with closed := true})}

theorem request_close : Step () () config s1 (.protocol .internal) closeQueued := by
  apply Step.protocol s1 _ .internal
    (A.Step.passive _ _ (A.Passive.requestUseClose _ 1 (writerEntry 0 ()) () rfl rfl rfl)) trivial
  intro ticket finish
  apply False.elim
  apply no_finish_of_nondecreasing (action := A.Step.passive s1.authority _
    (A.Passive.requestUseClose _ 1 (writerEntry 0 ()) () rfl rfl rfl)) ?_ finish
  intro i e found
  exact ⟨e,found,Nat.le_refl _⟩

theorem close_step : Step () () config closeQueued (.protocol .internal) closed := by
  apply Step.protocol closeQueued _ .internal
    (A.Step.passive _ _ (A.Passive.close _ 1 (writerEntry 0 ()) (by exact List.mem_cons_self) rfl (by trivial))) trivial
  intro ticket finish
  apply False.elim
  apply no_finish_of_nondecreasing (action := A.Step.passive closeQueued.authority _
    (A.Passive.close _ 1 (writerEntry 0 ()) (by exact List.mem_cons_self) rfl (by trivial))) ?_ finish
  intro i e found
  by_cases same : i = 1
  · subst i
    have eq : e = writerEntry 0 () := Option.some.inj found.symm
    subst e
    exact ⟨{writerEntry 0 () with closed := true},by simp [A.atProtocol,R.put],Nat.le_refl _⟩
  · exact ⟨e,by simpa [A.atProtocol,R.put,same] using found,Nat.le_refl _⟩

theorem closed_byte : Step () () config closed (.payload 0 1 4096 0 ⟨7,by decide⟩) (copy closed 1 c0) :=
  .payload closed 1 c0 rfl rfl (by decide)

theorem close_before_drain : Trace () () config s0
    [.beginCopy 1,.protocol .internal,.protocol .internal,.payload 0 1 4096 0 ⟨7,by decide⟩] (copy closed 1 c0) :=
  .cons begin_step (.cons request_close (.cons close_step (.cons closed_byte (.nil _))))

end Aurora.B.Witnesses
