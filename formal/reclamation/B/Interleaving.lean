import B.Entry
import B.Basic
namespace Aurora.B.Interleaving

/-- Two actual admissions from one gate's disjoint local free inventory. This
    fixture imports no abstract A witness states or enlarged evaluator limits. -/
def config : Config := ⟨[0,1,2],4096,2,[8192]⟩
def heap : Heap := fun cell => if cell = 4096 then ⟨7,by decide⟩ else if cell = 4097 then ⟨9,by decide⟩ else ⟨0,by decide⟩
def gateEntry : R.Entry Unit := {generation := 0,kind := .gate ()}
def grant : A.Grant Unit := ⟨(),(),0,[0,1,2],true,true⟩
def root : A.State Unit := A.mint (A.putGrant (A.atProtocol A.initial
  (R.enqueue (R.issue R.initial 0 (.gate ())) (.publish 0))) 0 grant) 0 0 [0,1,2]
def owner : A.State Unit := A.atProtocol root (R.put root.protocol 0 {gateEntry with published := true})
def first : A.State Unit := writerState owner 0 0 {gateEntry with published := true} grant [0,1]
def both : A.State Unit := writerState first 0 1 {gateEntry with published := true} grant [2]
def descriptor : Descriptor := ⟨0,4096,0,2⟩
def other : Descriptor := ⟨0,4096,2,1⟩

theorem owner_reachable : A.Reachable () () config.allocation owner := by
  refine ⟨[.internal,.internal],.cons (t := root) ?_ (.cons ?_ (.nil _))⟩
  · exact A.Step.root A.initial rfl rfl
  · exact .passive root _ (.publish root.protocol 0 gateEntry (by exact List.mem_cons_self) rfl (by trivial) rfl)
theorem first_reachable : A.Reachable () () config.allocation first :=
  (admit_writer (source := 0) (e := {gateEntry with published := true}) (g := grant)
    (nonce := 0) (footprint := [0,1]) owner_reachable rfl rfl rfl rfl rfl rfl (by decide) rfl (by decide)).1
theorem both_reachable : A.Reachable () () config.allocation both :=
  (admit_writer (source := 0) (e := {gateEntry with published := true}) (g := grant)
    (nonce := 1) (footprint := [2]) first_reachable rfl rfl rfl rfl rfl rfl (by decide) rfl (by decide)).1

theorem config_valid : config.Valid := by
  refine ⟨by decide,by decide,?_,?_⟩
  · intro cell range member
    simp only [config,List.mem_cons,List.not_mem_nil,or_false] at member
    rcases member with rfl | rfl | rfl <;> dsimp [config,inRange] at range <;> omega
  · intro cell member
    simp only [config,List.mem_cons,List.not_mem_nil,or_false] at member
    subst cell
    dsimp [config,inRange]
    decide

theorem descriptor_valid : descriptor.Valid config := by
  unfold Descriptor.Valid descriptor config wordLimit
  decide

theorem first_authorized : Authorized both 1 descriptor := by
  refine ⟨writerEntry 0 (),A.child grant none [0,1] true false,rfl,rfl,rfl,by decide,rfl,rfl,?_⟩
  intro offset bound
  change offset < 2 at bound
  change 0 + offset ∈ [0,1]
  have choice : offset = 0 ∨ offset = 1 := by omega
  rcases choice with rfl | rfl <;> decide

theorem other_authorized : Authorized both 2 other :=
  writer_authorized first 0 1 {gateEntry with published := true} grant other rfl

def s0 : State Unit := initial both heap
def s1 := start s0 1 descriptor
def cursor : Cursor := ⟨descriptor,0,.running⟩
def s2 := copy s1 1 cursor
def between : State Unit := {s2 with heap := store s2.heap 2 ⟨11,by decide⟩}
def final := copy between 1 (advance cursor)

theorem begin_step : Step () () config s0 (.beginCopy 1) s1 :=
  .beginCopy s0 1 descriptor rfl rfl descriptor_valid first_authorized
theorem first_byte : Step () () config s1 (.payload 0 1 4096 0 ⟨7,by decide⟩) s2 :=
  .payload s1 1 cursor rfl rfl (by decide)
/-- The original write constructor allows this different ticket while ticket1's
    cursor remains held; its address is outside the copied interval. -/
theorem other_write : Step () () config s2 (.write 0 2 2 ⟨11,by decide⟩) between :=
  .write s2 both 0 2 2 ⟨11,by decide⟩ (other_authorized.effect (offset := 0) (by decide)) rfl
theorem second_byte : Step () () config between (.payload 0 1 4097 1 ⟨9,by decide⟩) final :=
  .payload between 1 (advance cursor) rfl rfl (by decide)

theorem interleaved_trace : Trace () () config s0
    [.beginCopy 1,.payload 0 1 4096 0 ⟨7,by decide⟩,.write 0 2 2 ⟨11,by decide⟩,
      .payload 0 1 4097 1 ⟨9,by decide⟩] final :=
  .cons begin_step (.cons first_byte (.cons other_write (.cons second_byte (.nil _))))
theorem held_during_interleaving : between.cursors 1 = some (advance cursor) := rfl
theorem final_bytes : final.heap 0 = ⟨7,by decide⟩ ∧ final.heap 1 = ⟨9,by decide⟩ ∧
    final.heap 2 = ⟨11,by decide⟩ ∧ final.cursors 1 = some ⟨descriptor,2,.done⟩ := by decide

end Aurora.B.Interleaving
