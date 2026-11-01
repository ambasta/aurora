import B.Admission
import B.Model
namespace Aurora.B

/-- A finite canonical-address destination interval, with no region-tag shortcut. -/
def intervalFootprint (destination count : Nat) : A.Footprint :=
  (List.range count).map (fun offset => destination + offset)

theorem interval_offset_member (destination count offset : Nat) (bound : offset < count) :
    destination + offset ∈ intervalFootprint destination count := by
  exact List.mem_map.mpr ⟨offset,List.mem_range.mpr bound,rfl⟩

theorem interval_member_iff (destination count cell : Nat) :
    cell ∈ intervalFootprint destination count ↔ inRange destination count cell := by
  constructor
  · intro member
    obtain ⟨offset,bound,equal⟩ := List.mem_map.mp member
    have lt := List.mem_range.mp bound
    constructor <;> omega
  · intro range
    obtain ⟨lower,upper⟩ := range
    exact List.mem_map.mpr ⟨cell - destination,List.mem_range.mpr (by omega),by omega⟩

/-- The actual admission result contains the use entry, immutable writable grant
    and outstanding work required by B. This is not an assumed Enabled oracle. -/
theorem writer_authorized (s : A.State Agent) (source nonce : Nat) (e : R.Entry Agent)
    (g : A.Grant Agent) (d : Descriptor) (generation : d.generation = e.generation) :
    Authorized (writerState s source nonce e g (intervalFootprint d.destination d.count))
      s.protocol.next d := by
  obtain ⟨entry,grant⟩ := writer_state_facts s source nonce e g (intervalFootprint d.destination d.count)
  refine ⟨writerEntry e.generation g.subject,A.child g none (intervalFootprint d.destination d.count) true false,
    entry,grant,rfl,Nat.zero_lt_succ 0,rfl,generation.symm,?_⟩
  intro offset bound
  exact interval_offset_member d.destination d.count offset bound

/-- A reachable gate's ordinary local admission guards construct all five A
    transitions, then a real B.beginCopy step on a fresh byte interpretation.
    Config.Valid can be retained by clients for safety; operational beginCopy
    itself needs Descriptor.Valid, not a new global-state permission test. -/
theorem admit_begin_copy {Agent : Type} {issuer owner : Agent} {config : Config}
    {s : A.State Agent} {source nonce : Nat} {e : R.Entry Agent} {g : A.Grant Agent}
    (d : Descriptor) (heap : Heap)
    (reachable : A.Reachable issuer owner config.allocation s)
    (found : s.protocol.entries source = some e) (gate : e.kind = .gate g.subject)
    (granted : s.grants source = some g) (published : e.published = true) (openGate : e.closed = false)
    (fresh : s.protocol.requests (source,nonce) = none)
    (within : (intervalFootprint d.destination d.count).Within g.footprint)
    (writable : g.writable = true)
    (free : (intervalFootprint d.destination d.count).Within (s.holdings g.generation (.gate source)))
    (generation : d.generation = e.generation) (valid : d.Valid config) :
    let authority := writerState s source nonce e g (intervalFootprint d.destination d.count)
    A.Reachable issuer owner config.allocation authority ∧
      Authorized authority s.protocol.next d ∧
      Step issuer owner config (initial authority heap) (.beginCopy s.protocol.next)
        (start (initial authority heap) s.protocol.next d) := by
  obtain ⟨reached,_,_,_⟩ := admit_writer reachable found gate granted published openGate fresh within writable free
  have authorized := writer_authorized s source nonce e g d generation
  exact ⟨reached,authorized,.beginCopy _ _ _ rfl rfl valid authorized⟩

end Aurora.B
