import SourceBinding.BodyProof
import SourceBinding.EffectRuns
import SourceBinding.EntryBinding
namespace Aurora.SourceBinding
open Aurora.Publication

/-- A call-free body certificate in supplied tables. Source/class/publication
    identity is deliberately a separate obligation of its byte-backed caller.
    The complete typed source method, actual entry and every body row are retained. -/
structure LocalBodyCertificate (t : Tables) (id : Int)
    (source : BodyMethod input function fieldDecls) where
  bindings : List ParameterBinding
  stop : Nat
  entry : EntryCode (pureView (canonicalEffects t id)) function.formals bindings
  code : BodyCode (canonicalEffects t id) (parameterSlot bindings)
    source.body function.formals.length stop
  complete : stop = (functionCode t id).size

def checkLocalBody (t : Tables) (id : Int) (source : BodyMethod input function fieldDecls) :
    Option (LocalBodyCertificate t id source) := do
  let program := canonicalEffects t id
  let entry ← checkEntry (pureView program) function.formals
  let body ← checkBodyCode program (parameterSlot entry.bindings) source.body function.formals.length
  if complete : body.stop = (functionCode t id).size then
    return ⟨entry.bindings,body.stop,entry.code,body.code,complete⟩
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

variable {t : Tables} {id : Int} {input : ByteArray} {function : Function}
  {fieldDecls : List Formal} {source : BodyMethod input function fieldDecls}

/-- Constructive finite execution from actual PC zero. Bounded supplied scalar
    arguments initialize the actual slots; receiver readiness or assertion truth
    is not assumed. Malformed receiver values remain explicit scalar failures. -/
theorem LocalBodyCertificate.executes (checked : LocalBodyCertificate t id source)
    (base : Machine) (arguments : EntryArguments checked.bindings base.arguments) :
    ∃ result,
      EffectRuns (canonicalEffects t id)
        (preparedEntry base (parameterSlot checked.bindings) 0)
        (evalBody source.body (entrySource base checked.bindings.length)).stores result ∧
      BodyResultRelated (parameterSlot checked.bindings) [] checked.stop
        (evalBody source.body (entrySource base checked.bindings.length)).execution result ∧
      EffectTerminal result := by
  have entryRun := pure_next_lift (entry_runs checked.entry base arguments)
  obtain ⟨result,bodyRun,related⟩ := checked.code.simulates (entrySource base checked.bindings.length)
    (preparedEntry base (parameterSlot checked.bindings) checked.bindings.length)
    (entry_context checked.entry base) none []
  rw [← checked.entry.1,prepared_frame] at bodyRun
  refine ⟨result,?_,related,?_⟩
  · simpa only [List.nil_append] using entryRun.trans bodyRun
  · exact related_terminal related (source.returns.no_fallthrough _)

/-- Every terminal execution has the source's exact ordered store events and
    related current terminal state. This is not merely one favorable path. -/
theorem LocalBodyCertificate.terminal_correspondence (checked : LocalBodyCertificate t id source)
    (base : Machine) (arguments : EntryArguments checked.bindings base.arguments)
    (run : EffectRuns (canonicalEffects t id)
      (preparedEntry base (parameterSlot checked.bindings) 0) events result)
    (terminal : EffectTerminal result) :
    events = (evalBody source.body (entrySource base checked.bindings.length)).stores ∧
    BodyResultRelated (parameterSlot checked.bindings) [] checked.stop
      (evalBody source.body (entrySource base checked.bindings.length)).execution result := by
  obtain ⟨actual,actualRun,related,actualTerminal⟩ := checked.executes base arguments
  obtain ⟨sameEvents,sameResult⟩ := run.terminal_unique terminal actualRun actualTerminal
  exact ⟨sameEvents,sameResult ▸ related⟩

/-- No hidden infinite local execution can coexist with the constructed terminal
    run. This covers only these checked scalar bodies, not external operations. -/
theorem LocalBodyCertificate.terminates (checked : LocalBodyCertificate t id source)
    (base : Machine) (arguments : EntryArguments checked.bindings base.arguments) :
    ¬ EffectDiverges (canonicalEffects t id)
      (preparedEntry base (parameterSlot checked.bindings) 0) := by
  obtain ⟨_,run,_,terminal⟩ := checked.executes base arguments
  exact run.not_diverges terminal

theorem local_body_sound (checked : LocalBodyCertificate t id source) :
    BodyCode (canonicalEffects t id) (parameterSlot checked.bindings) source.body
      function.formals.length checked.stop ∧ checked.stop = (functionCode t id).size :=
  ⟨checked.code,checked.complete⟩

end Aurora.SourceBinding
