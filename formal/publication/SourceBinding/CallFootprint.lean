import SourceBinding.BodySemantics
import SourceBinding.EffectRuns
namespace Aurora.SourceBinding

/-- Conservative syntactic reads, including both short-circuit arms. -/
def guardReads : {kind : GuardType} → GuardExpr kind → List Nat
  | _, .field _ _ ordinal => [ordinal]
  | _, .not value => guardReads value
  | _, .sub left right | _, .compare _ left right | _, .and left right | _, .or left right =>
    guardReads left ++ guardReads right
  | _, _ => []

/-- Includes unreachable assignments; this is not an assumed dynamic frame. -/
def bodyWrites : EffectBody → List Nat
  | .assign _ ordinal _ => [ordinal]
  | .seq first rest => bodyWrites first ++ bodyWrites rest
  | .branch _ body => bodyWrites body
  | _ => []

theorem evalGuard_read_congr {kind : GuardType} (expression : GuardExpr kind)
    (left right : SourceState) (parameters : left.parameters = right.parameters)
    (fields : ∀ index ∈ guardReads expression, left.fields index = right.fields index) :
    evalGuard left expression = evalGuard right expression := by
  induction expression with
  | wordLit value => rfl
  | boolLit value => rfl
  | parameter kind name index => simp only [evalGuard,parameters]
  | field kind name ordinal => simp only [evalGuard,fields ordinal (by simp [guardReads])]
  | not value ih => simp only [evalGuard,ih fields]
  | sub a b ia ib | compare op a b ia ib | and a b ia ib | or a b ia ib =>
    have ha := ia (fun index member => fields index (List.mem_append_left _ member))
    have hb := ib (fun index member => fields index (List.mem_append_right _ member))
    simp only [evalGuard,ha,hb]

/-- All completed stores, including those retained before faults, are covered. -/
theorem evalBody_store_footprint (body : EffectBody) (state : SourceState) :
    ∀ event ∈ (evalBody body state).stores, event.ordinal ∈ bodyWrites body := by
  induction body generalizing state with
  | skip => simp [evalBody]
  | assign kind ordinal value =>
    simp only [evalBody,sourceExpression]
    cases evalGuard state value with
    | trap fault => simp
    | value scalar => cases checked : readScalar kind (some scalar) <;> simp [checked,bodyWrites]
  | require condition =>
    simp only [evalBody,sourceExpression]
    cases evalGuard state condition with
    | trap fault => simp
    | value scalar => cases scalar with
      | word value => simp
      | boolean value => cases value <;> simp
  | returnValue kind value =>
    simp only [evalBody,sourceExpression]
    cases evalGuard state value <;> simp
  | branch condition body ih =>
    simp only [evalBody,sourceExpression]
    cases evalGuard state condition with
    | trap fault => simp
    | value scalar => cases scalar with
      | word value => simp
      | boolean value => cases value with
        | false => simp
        | true => exact ih state
  | seq first rest firstIH restIH =>
    simp only [evalBody]
    cases result : (evalBody first state).execution with
    | next middle =>
      intro event member
      cases List.mem_append.mp member with
      | inl member => exact List.mem_append_left _ (firstIH state event member)
      | inr member => exact List.mem_append_right _ (restIH middle event member)
    | returned value final =>
      intro event member
      exact List.mem_append_left _ (firstIH state event member)
    | trap fault final =>
      intro event member
      exact List.mem_append_left _ (firstIH state event member)

theorem applyStores_untouched (receiver : Nat → Option Value) (events : List StoreEvent)
    (index : Nat) (outside : ∀ event ∈ events, index ≠ event.ordinal) :
    applyStores receiver events index = receiver index := by
  induction events generalizing receiver with
  | nil => rfl
  | cons event rest ih =>
    rw [applyStores,ih _ (fun item member => outside item (List.mem_cons_of_mem _ member))]
    simp only [outside event (by simp), ↓reduceIte]

/-- Ordered replay and the proved source write footprint, not a callee summary,
    imply preservation, even on faulting executions with completed stores. -/
theorem EffectRuns.source_footprint_frame {program : EffectProgram} {initial : Machine}
    {result : EffectExecution} (body : EffectBody) (source : SourceState)
    (run : EffectRuns program initial (evalBody body source).stores result)
    (index : Nat) (outside : index ∉ bodyWrites body) :
    result.state.receiver index = initial.receiver index := by
  rw [run.store_frame.1]
  exact applyStores_untouched _ _ index (fun event member equal =>
    outside (equal ▸ evalBody_store_footprint body source event member))

/-- Same parameters and disjoint writes preserve a guard result. No premise
    asserts that the body's assertions succeed; no external framing is implied.
    The fixed map may be saved caller arguments, distinct from callee arguments. -/
theorem EffectRuns.guard_footprint_frame {program : EffectProgram} {initial : Machine}
    {result : EffectExecution} (body : EffectBody) (source : SourceState)
    (run : EffectRuns program initial (evalBody body source).stores result)
    {kind : GuardType} (guard : GuardExpr kind)
    (parameters : Nat → Option Value)
    (disjoint : ∀ index ∈ guardReads guard, index ∉ bodyWrites body) :
    evalGuard ⟨result.state.receiver,parameters⟩ guard =
      evalGuard ⟨initial.receiver,parameters⟩ guard := by
  apply evalGuard_read_congr guard ⟨result.state.receiver,parameters⟩
    ⟨initial.receiver,parameters⟩ rfl
  intro index member
  exact run.source_footprint_frame body source index (disjoint index member)

end Aurora.SourceBinding
