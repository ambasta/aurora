import SourceBinding.IRSemantics
import SourceBinding.MethodSyntax
import SourceBinding.EntryBinding
import SourceBinding.GuardCode
import SourceBinding.PrefixPurity
import SourceBinding.GuardSafety
namespace Aurora.SourceBinding
open Aurora.Publication

/-- The public composition retains the SAME raw graph selection, typed leading
    guard, metadata identity and decoded closure. No independently chosen AST,
    receiver field map, callable ID or continuation cut is accepted. -/
structure SemanticBinding (files : List SourceFile) (root module path : Name) (member : ByteArray)
    (bytes : ByteArray) where
  source : SelectedGuard files root module path member
  ir : BoundIR files root module path member source.selected bytes
  bindings : List ParameterBinding
  endExpr : Nat
  entry : EntryCode (stallAt (canonicalProgram (tables ir.publication.artifact.document.reversed.reverse) ir.id)
      (endExpr + 4)) source.selected.selected.method.function.formals bindings
  pure : ClosedRawPrefix (tables ir.publication.artifact.document.reversed.reverse) ir.id (endExpr + 4)
  code : GuardCode (canonicalProgram (tables ir.publication.artifact.document.reversed.reverse) ir.id)
    (parameterSlot bindings) source.method.guard source.selected.selected.method.function.formals.length endExpr

def bindSemantics (files : List SourceFile) (root module path : Name) (member : ByteArray) (bytes : ByteArray) :
    Option (SemanticBinding files root module path member bytes) := do
  let source ← selectGuard files root module path member
  let ir ← bindIR files root module path member source.selected bytes
  let program := canonicalProgram (tables ir.publication.artifact.document.reversed.reverse) ir.id
  let formals := source.selected.selected.method.function.formals
  let originalEntry ← checkEntry program formals
  let guardCode ← checkGuardCode program (parameterSlot originalEntry.bindings) source.method.guard formals.length
  let entry ← checkEntry (stallAt program (guardCode.endExpr + 4)) formals
  if same : entry.bindings = originalEntry.bindings then
    if pure : ClosedRawPrefix (tables ir.publication.artifact.document.reversed.reverse) ir.id (guardCode.endExpr + 4) then
      return ⟨source,ir,originalEntry.bindings,guardCode.endExpr,by simpa only [same] using entry.code,pure,guardCode.grammar⟩
    else none
  else none

/-- Exact source/IR first-exit correspondence from actual PC zero, with parameter
    slots initialized by actual binding instructions. All source argument values
    are arbitrary declared bounded scalars; receiver values are not assumed to
    satisfy the rejection predicate. General evaluation faults remain explicit. -/
theorem SemanticBinding.first_exit (checked : SemanticBinding files root module path member bytes)
    (base : Machine) (arguments : EntryArguments checked.bindings base.arguments) :
    FirstExit (canonicalProgram (tables checked.ir.publication.artifact.document.reversed.reverse) checked.ir.id)
      (checked.endExpr + 4) (preparedEntry base (parameterSlot checked.bindings) 0)
      (rejectionOutcome (preparedEntry base (parameterSlot checked.bindings) checked.bindings.length)
        (checked.endExpr + 4) (evalGuard (entrySource base checked.bindings.length) checked.source.method.guard)) := by
  have entryRun := entry_runs checked.entry base arguments
  have body := checked.code.runs (entrySource base checked.bindings.length)
    (preparedEntry base (parameterSlot checked.bindings) checked.bindings.length)
    (entry_context checked.entry base) none
  rw [← checked.entry.1,prepared_frame] at body
  exact (entryRun.trans body).stalled_first_exit (rejection_at_exit _ _ _)

theorem SemanticBinding.unique_outcome (checked : SemanticBinding files root module path member bytes)
    (base : Machine) (arguments : EntryArguments checked.bindings base.arguments)
    (other : FirstExit (canonicalProgram (tables checked.ir.publication.artifact.document.reversed.reverse) checked.ir.id)
      (checked.endExpr + 4) (preparedEntry base (parameterSlot checked.bindings) 0) result) :
    result = rejectionOutcome (preparedEntry base (parameterSlot checked.bindings) checked.bindings.length)
      (checked.endExpr + 4) (evalGuard (entrySource base checked.bindings.length) checked.source.method.guard) :=
  other.unique (checked.first_exit base arguments)

theorem SemanticBinding.terminates_before_tail (checked : SemanticBinding files root module path member bytes)
    (base : Machine) (arguments : EntryArguments checked.bindings base.arguments) :
    ¬ DivergesBefore (canonicalProgram (tables checked.ir.publication.artifact.document.reversed.reverse) checked.ir.id)
      (checked.endExpr + 4) (preparedEntry base (parameterSlot checked.bindings) 0) :=
  (checked.first_exit base arguments).not_diverges_before

/-- Every preterminal frame in the checked prefix retains the original receiver
    and argument maps. Return/trap outcomes have no final machine in this model. -/
theorem SemanticBinding.preterminal_frame (checked : SemanticBinding files root module path member bytes)
    (base : Machine)
    (run : Runs (stallAt (canonicalProgram (tables checked.ir.publication.artifact.document.reversed.reverse) checked.ir.id)
      (checked.endExpr + 4)) (preparedEntry base (parameterSlot checked.bindings) 0) (.next state)) :
    state.pc ≤ checked.endExpr + 4 ∧ state.receiver = base.receiver ∧ state.arguments = base.arguments := by
  simpa using checked.pure.trace_invariant run (by simp)

/-- Structural absence of call/store forms over ALL exact decoded prefix rows,
    not an assertion about native API scopes or effects of the unproved tail. -/
theorem SemanticBinding.no_call_store (checked : SemanticBinding files root module path member bytes) :
    NoCallStore (tables checked.ir.publication.artifact.document.reversed.reverse) checked.ir.id (checked.endExpr + 4) :=
  checked.pure.1

structure SafeSemanticBinding (files : List SourceFile) (root module path : Name) (member : ByteArray)
    (bytes : ByteArray) where
  semantic : SemanticBinding files root module path member bytes
  range : RangeGuard semantic.source.method.guard

def bindSafeSemantics (files : List SourceFile) (root module path : Name) (member : ByteArray) (bytes : ByteArray) :
    Option (SafeSemanticBinding files root module path member bytes) := do
  let semantic ← bindSemantics files root module path member bytes
  let safety ← checkRange semantic.source.method.guard
  return ⟨semantic,safety.range⟩

/-- Only bounded declared scalar inputs are assumed. Resource values, initial
    offset≤bytes and the rejection result are NOT assumptions. Stable sequential
    receiver reads are modeled by the immutable input valuation. -/
theorem SafeSemanticBinding.guard_total (checked : SafeSemanticBinding files root module path member bytes)
    (base : Machine) (arguments : EntryArguments checked.semantic.bindings base.arguments)
    (fieldsReady : DeclarationsReady (fields checked.semantic.source.selected.selected.classDecl.members) base.receiver) :
    ∃ rejection, evalGuard (entrySource base checked.semantic.bindings.length) checked.semantic.source.method.guard =
      .value (.boolean rejection) := by
  apply checked.range.total
  exact typed_guard_leaves checked.semantic.source.method.typing _ fieldsReady
    (checked.semantic.entry.arguments_ready base arguments)

/-- Every related bounded source state has exactly the source-selected refusal
    or continuation outcome; no fault or prefix divergence is possible. The
    continuation is immediately after the checked leading-if, not a tail proof. -/
theorem SafeSemanticBinding.refusal_or_continuation
    (checked : SafeSemanticBinding files root module path member bytes)
    (base : Machine) (arguments : EntryArguments checked.semantic.bindings base.arguments)
    (fieldsReady : DeclarationsReady (fields checked.semantic.source.selected.selected.classDecl.members) base.receiver) :
    ∃ rejection,
      evalGuard (entrySource base checked.semantic.bindings.length) checked.semantic.source.method.guard =
        .value (.boolean rejection) ∧
      FirstExit (canonicalProgram (tables checked.semantic.ir.publication.artifact.document.reversed.reverse) checked.semantic.ir.id)
        (checked.semantic.endExpr + 4) (preparedEntry base (parameterSlot checked.semantic.bindings) 0)
        (if rejection then .returned (.boolean false) else
          .next (frameState (preparedEntry base (parameterSlot checked.semantic.bindings) checked.semantic.bindings.length)
            (checked.semantic.endExpr + 4) (some (.boolean false)) [])) := by
  obtain ⟨rejection,value⟩ := checked.guard_total base arguments fieldsReady
  refine ⟨rejection,value,?_⟩
  have run := checked.semantic.first_exit base arguments
  rw [value] at run
  cases rejection <;> exact run

/-- No other first-exit outcome (including a trap) can occur. -/
theorem SafeSemanticBinding.no_fault (checked : SafeSemanticBinding files root module path member bytes)
    (base : Machine) (arguments : EntryArguments checked.semantic.bindings base.arguments)
    (fieldsReady : DeclarationsReady (fields checked.semantic.source.selected.selected.classDecl.members) base.receiver) :
    ¬ FirstExit (canonicalProgram (tables checked.semantic.ir.publication.artifact.document.reversed.reverse) checked.semantic.ir.id)
      (checked.semantic.endExpr + 4) (preparedEntry base (parameterSlot checked.semantic.bindings) 0) (.trap fault) := by
  obtain ⟨rejection,_,run⟩ := checked.refusal_or_continuation base arguments fieldsReady
  intro trapped
  have impossible := trapped.unique run
  cases rejection <;> cases impossible

end Aurora.SourceBinding
