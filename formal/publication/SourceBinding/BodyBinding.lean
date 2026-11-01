import SourceBinding.BodyProof
import SourceBinding.EffectRuns
import SourceBinding.EntryBinding
namespace Aurora.SourceBinding
open Aurora.Publication

/-- Same selected source member and metadata identity, actual typed entry, and
    complete canonical body coverage. No independently supplied field catalogue,
    source AST, callee summary or successful-assertion assumption is accepted. -/
structure BodyBinding (files : List SourceFile) (root module path : Name) (member : ByteArray) (bytes : ByteArray) where
  source : SelectedBody files root module path member
  ir : BoundIR files root module path member source.selected bytes
  bindings : List ParameterBinding
  stop : Nat
  entry : EntryCode (pureView (canonicalEffects (tables ir.publication.artifact.document.reversed.reverse) ir.id))
    source.selected.selected.method.function.formals bindings
  code : BodyCode (canonicalEffects (tables ir.publication.artifact.document.reversed.reverse) ir.id)
    (parameterSlot bindings) source.method.body source.selected.selected.method.function.formals.length stop
  complete : stop = (functionCode (tables ir.publication.artifact.document.reversed.reverse) ir.id).size

def bindBody (files : List SourceFile) (root module path : Name) (member : ByteArray) (bytes : ByteArray) :
    Option (BodyBinding files root module path member bytes) := do
  let source ← selectBody files root module path member
  let ir ← bindIR files root module path member source.selected bytes
  let program := canonicalEffects (tables ir.publication.artifact.document.reversed.reverse) ir.id
  let entry ← checkEntry (pureView program) source.selected.selected.method.function.formals
  let body ← checkBodyCode program (parameterSlot entry.bindings) source.method.body
    source.selected.selected.method.function.formals.length
  if complete : body.stop = (functionCode (tables ir.publication.artifact.document.reversed.reverse) ir.id).size then
    return ⟨source,ir,entry.bindings,body.stop,entry.code,body.code,complete⟩
  else none

theorem pure_next_lift {program : EffectProgram} {initial final : Machine}
    (run : Runs (pureView program) initial (.next final)) : EffectRuns program initial [] (.next final) := by
  obtain ⟨result,actual,erased,_,_⟩ := pure_runs_lift run (by intro h; cases h)
  cases result with
  | next state => simp only [eraseEffect,Option.some.injEq,Execution.next.injEq] at erased; exact erased ▸ actual
  | returned value state => cases erased
  | trap fault state => cases fault <;> cases erased

theorem related_terminal {slots : Nat → Nat} {stack : List Value} {stop : Nat}
    {source : SourceExecution} {result : EffectExecution}
    (related : BodyResultRelated slots stack stop source result)
    (terminal : ∀ state, source ≠ .next state) : EffectTerminal result := by
  cases source with
  | next state => exact False.elim (terminal state rfl)
  | returned value state => cases result <;> first | exact True.intro | contradiction
  | trap fault state => cases result <;> first | exact True.intro | contradiction

/-- Constructive finite execution from actual PC zero. Bounded supplied scalar
    arguments initialize the actual slots; receiver readiness or assertion truth
    is not assumed. Malformed receiver values remain explicit scalar failures. -/
theorem BodyBinding.executes (checked : BodyBinding files root module path member bytes)
    (base : Machine) (arguments : EntryArguments checked.bindings base.arguments) :
    ∃ result,
      EffectRuns (canonicalEffects (tables checked.ir.publication.artifact.document.reversed.reverse) checked.ir.id)
        (preparedEntry base (parameterSlot checked.bindings) 0)
        (evalBody checked.source.method.body (entrySource base checked.bindings.length)).stores result ∧
      BodyResultRelated (parameterSlot checked.bindings) [] checked.stop
        (evalBody checked.source.method.body (entrySource base checked.bindings.length)).execution result ∧
      EffectTerminal result := by
  have entryRun := pure_next_lift (entry_runs checked.entry base arguments)
  obtain ⟨result,bodyRun,related⟩ := checked.code.simulates (entrySource base checked.bindings.length)
    (preparedEntry base (parameterSlot checked.bindings) checked.bindings.length)
    (entry_context checked.entry base) none []
  rw [← checked.entry.1,prepared_frame] at bodyRun
  refine ⟨result,?_,related,?_⟩
  · simpa only [List.nil_append] using entryRun.trans bodyRun
  · exact related_terminal related (checked.source.method.returns.no_fallthrough _)

/-- Every terminal execution has the source's exact ordered store events and
    related current terminal state. This is not merely one favorable path. -/
theorem BodyBinding.terminal_correspondence (checked : BodyBinding files root module path member bytes)
    (base : Machine) (arguments : EntryArguments checked.bindings base.arguments)
    (run : EffectRuns (canonicalEffects (tables checked.ir.publication.artifact.document.reversed.reverse) checked.ir.id)
      (preparedEntry base (parameterSlot checked.bindings) 0) events result)
    (terminal : EffectTerminal result) :
    events = (evalBody checked.source.method.body (entrySource base checked.bindings.length)).stores ∧
    BodyResultRelated (parameterSlot checked.bindings) [] checked.stop
      (evalBody checked.source.method.body (entrySource base checked.bindings.length)).execution result := by
  obtain ⟨actual,actualRun,related,actualTerminal⟩ := checked.executes base arguments
  obtain ⟨sameEvents,sameResult⟩ := run.terminal_unique terminal actualRun actualTerminal
  exact ⟨sameEvents,sameResult ▸ related⟩

/-- No hidden infinite local execution can coexist with the constructed terminal
    run. This covers only these checked scalar bodies, not external operations. -/
theorem BodyBinding.terminates (checked : BodyBinding files root module path member bytes)
    (base : Machine) (arguments : EntryArguments checked.bindings base.arguments) :
    ¬ EffectDiverges (canonicalEffects (tables checked.ir.publication.artifact.document.reversed.reverse) checked.ir.id)
      (preparedEntry base (parameterSlot checked.bindings) 0) := by
  obtain ⟨_,run,_,terminal⟩ := checked.executes base arguments
  exact run.not_diverges terminal

theorem bind_body_sound (files : List SourceFile) (root module path : Name) (member : ByteArray) (bytes : ByteArray)
    (checked : BodyBinding files root module path member bytes) (_accepted : bindBody files root module path member bytes = some checked) :
    BodyCode (canonicalEffects (tables checked.ir.publication.artifact.document.reversed.reverse) checked.ir.id)
      (parameterSlot checked.bindings) checked.source.method.body
      checked.source.selected.selected.method.function.formals.length checked.stop ∧
    checked.stop = (functionCode (tables checked.ir.publication.artifact.document.reversed.reverse) checked.ir.id).size :=
  ⟨checked.code,checked.complete⟩

end Aurora.SourceBinding
