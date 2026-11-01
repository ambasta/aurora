import B.Model
namespace Aurora.B

variable {Agent : Type} {s t : A.State Agent} {config : Config} {d : Descriptor}

@[simp] theorem store_same (heap : Heap) (cell : Nat) (value : Byte) : store heap cell value cell = value := by
  simp [store]
theorem store_other (heap : Heap) (cell index : Nat) (value : Byte) (different : index ≠ cell) :
    store heap cell value index = heap index := by simp only [store,if_neg different]

theorem Authorized.enabled (admitted : Authorized s ticket d) (bound : offset < d.count) :
    A.Enabled s ticket (d.destination + offset) true := by
  obtain ⟨e,g,found,grant,kind,work,writer,epoch,range⟩ := admitted
  exact ⟨e,g,found,grant,kind,work,range offset bound,writer⟩

theorem Authorized.effect (admitted : Authorized s ticket d) (bound : offset < d.count) :
    A.Step issuer subject allocation s (.access d.generation ticket (d.destination + offset) true) s := by
  obtain ⟨e,g,found,grant,kind,work,writer,epoch,range⟩ := admitted
  have effect := A.Step.effect (issuer := issuer) (initialSubject := subject) (allocation := allocation)
    s ticket e g (d.destination + offset) found kind grant work (range offset bound)
  simpa only [epoch,writer] using effect

theorem access_enabled (action : A.Step issuer subject allocation s event t)
    (same : event = .access generation ticket cell write) : A.Enabled s ticket cell write := by
  cases action <;> try cases same
  case effect e g kind work found grant within =>
    exact ⟨e,g,found,grant,kind,work,within,rfl⟩

theorem access_state (action : A.Step issuer subject allocation s event t)
    (same : event = .access generation ticket cell write) : t = s := by
  cases action <;> cases same
  rfl

theorem write_enabled (action : A.Step issuer subject allocation s (.access generation ticket cell true) t) :
    A.Enabled s ticket cell true := access_enabled action rfl

theorem Descriptor.source_inside (valid : d.Valid config) (bound : offset < d.count) :
    inRange config.source config.sourceBytes (d.source + offset) := by
  obtain ⟨positive,start,finish,_,_⟩ := valid
  constructor <;> omega

theorem Authorized.distinct (h : A.Invariant allocation s)
    (one : Authorized s first d) (other : A.Enabled s second cell true)
    (different : first ≠ second) (bound : offset < d.count) : d.destination + offset ≠ cell := by
  intro equal
  have conflict := A.overlapping_enabled_streams_are_readers h (one.enabled bound)
    (equal ▸ other) different
  exact Bool.noConfusion conflict.1

theorem enabled_in_allocation (h : A.Invariant allocation s) (enabled : A.Enabled s ticket cell write) :
    cell ∈ allocation := by
  obtain ⟨e,g,found,grant,kind,work,within,writer⟩ := enabled
  exact (A.grant_entry h grant found).2.2 within

theorem Authorized.in_allocation (h : A.Invariant allocation s) (one : Authorized s ticket d)
    (bound : offset < d.count) : d.destination + offset ∈ allocation :=
  enabled_in_allocation h (one.enabled bound)

/-- The copied prefix is asserted only while the use remains HELD. Explicit
release removes that obligation; later authorized writes need not preserve it. -/
structure Invariant (config : Config) (original : Heap) (s : State Agent) : Prop where
  authority : A.Invariant config.allocation s.authority
  source : ∀ cell, inRange config.source config.sourceBytes cell → s.heap cell = original cell
  cursors : ∀ ticket cursor, s.cursors ticket = some cursor →
    cursor.descriptor.Valid config ∧ cursor.copied ≤ cursor.descriptor.count ∧
    Authorized s.authority ticket cursor.descriptor ∧ s.spent ticket = true ∧
    ∀ offset, offset < cursor.copied →
      s.heap (cursor.descriptor.destination + offset) = original (cursor.descriptor.source + offset)

theorem initial_invariant (h : A.Invariant config.allocation authority) :
    Invariant config original (initial authority original) := by
  exact ⟨h,fun _ _ => rfl,by intro i c found; cases found⟩

theorem step_erases (h : Invariant config original before)
    (action : Step issuer subject config before event after) :
    A.Step issuer subject config.allocation before.authority (erase event) after.authority := by
  cases action with
  | protocol _ _ action nonwrite held => exact action
  | write _ _ _ _ _ action idle => exact action
  | payload ticket cursor found running remaining =>
    exact (h.cursors ticket cursor found).2.2.1.effect remaining
  | beginCopy | control | fault | release => exact .passive _ _ (.stutter _)

end Aurora.B
