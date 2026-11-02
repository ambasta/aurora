import SourceBinding.RuntimeStatementProof
import SourceBinding.RuntimeBodyNoFallthrough
import SourceBinding.RuntimeInitialState
namespace Aurora.SourceBinding

/-- A complete root return has executed its actual ret. Faults retain the actual
    active machine (possibly a nested callee), not fabricated caller cleanup. -/
def RuntimeBodyTerminal (base : Machine) (world : World) : RuntimeBodyOutcome → CallPhase World ExternalFault → Prop
  | .continued _, _ => False
  | .returned value source, .returned actual active =>
      actual = value ∧ active.frame.locals = source.values ∧
      active.shared = ⟨base.receiver,world⟩ ∧ active.saved = []
  | .trapped fault _, .trapped (.local (.scalar actual)) active =>
      actual = fault ∧ active.shared = ⟨base.receiver,world⟩
  | _, _ => False

theorem RuntimeBodyRun.finish
    (run : RuntimeBodyRun program external caller [] world base source start stop accumulator outcome events)
    (terminal : ∀ final, outcome ≠ .continued final) :
    ∃ final, CallRuns program external
      (.running (activeAt caller [] world (runtimeBodyFrame base source start accumulator))) events final ∧
      RuntimeBodyTerminal base world outcome final := by
  obtain ⟨final,actual,related⟩ := run
  cases outcome with
  | continued next => exact False.elim (terminal next rfl)
  | trapped fault next =>
    obtain ⟨active,equal,shared⟩ := related
    subst final
    exact ⟨_,actual,rfl,shared⟩
  | returned value next =>
    obtain ⟨pc,code,equal⟩ := related
    subst final
    have last : EffectRuns (localProgram program caller)
        (runtimeBodyFrame base next pc (some value)) []
        (.returned value (runtimeBodyFrame base next pc (some value))) := by
      apply EffectRuns.returned
      simp only [effectStep,runtimeBodyFrame,code,pureView,step,retainState]
    have lastCall := last.call_lift (by trivial) [] world external
    refine ⟨.returned value (activeAt caller [] world (runtimeBodyFrame base next pc (some value))),?_,rfl,rfl,rfl,rfl⟩
    simpa only [List.map_nil,List.nil_append,finishEffect,returnToCaller,activeAt,List.append_nil] using actual.trans lastCall

end Aurora.SourceBinding
