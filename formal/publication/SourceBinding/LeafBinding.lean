import SourceBinding.FreeBinding
import SourceBinding.LeafEvaluation
import SourceBinding.GuardSafety
namespace Aurora.SourceBinding
open Aurora.Publication

/-- Exact policy profile using the actual declaration names and positions. -/
def declaredLeafGuard (a b c d e f : Formal) : GuardExpr .boolean :=
  leafGuard (.parameter .word a.name 0) (.parameter .word b.name 1) (.parameter .word c.name 2)
    (.parameter .word d.name 3) (.parameter .word e.name 4) (.parameter .word f.name 5)

/-- Generic correspondence alone cannot confer these numeric facts: the entire
    typed source body must additionally match this exact policy. -/
structure LeafShape (checked : LocalFreeBinding t files root module path name) where
  a : Formal
  b : Formal
  c : Formal
  d : Formal
  e : Formal
  f : Formal
  formals : checked.identified.selected.function.function.formals = [a,b,c,d,e,f]
  types : a.type = guardSourceType .word ∧ b.type = guardSourceType .word ∧
    c.type = guardSourceType .word ∧ d.type = guardSourceType .word ∧
    e.type = guardSourceType .word ∧ f.type = guardSourceType .word
  body : checked.method.body = .seq (.returnValue .boolean (declaredLeafGuard a b c d e f)) .skip

def checkLeafShape (checked : LocalFreeBinding t files root module path name) :
    Option (LeafShape checked) := do
  match hf : checked.identified.selected.function.function.formals with
  | [a,b,c,d,e,f] =>
    if ht : a.type = guardSourceType .word ∧ b.type = guardSourceType .word ∧
        c.type = guardSourceType .word ∧ d.type = guardSourceType .word ∧
        e.type = guardSourceType .word ∧ f.type = guardSourceType .word then
      match hb : checked.method.body with
      | .seq (.returnValue .boolean expression) .skip =>
        if he : expression = declaredLeafGuard a b c d e f then
          return ⟨a,b,c,d,e,f,hf,ht,by simpa only [he] using hb⟩
        else none
      | _ => none
    else none
  | _ => none

theorem ready_word_parameter (ready : DeclarationsReady formals state.parameters)
    (found : formals[index]? = some decl) (kind : decl.type = guardSourceType .word) :
    ∃ n, n < wordLimit ∧ state.parameters index = some (.word n) ∧
      evalGuard state (.parameter .word decl.name index) = .value (.word n) := by
  obtain ⟨value,valueEq,typed⟩ := ready index decl .word found kind
  cases value with
  | boolean value => cases typed
  | signedCount12 => cases typed
  | word n => exact ⟨n,typed,valueEq,by simp [evalGuard,valueEq,readScalar,ScalarReady] at *; assumption⟩

/-- Actual bounded input arguments derive total evaluation. Neither successful
    admission nor a no-overflow premise is supplied by the caller. -/
theorem LeafShape.evaluates (shape : LeafShape checked) (base : Machine)
    (arguments : EntryArguments checked.core.bindings base.arguments) :
    ∃ l p m b s x,
      l < wordLimit ∧ p < wordLimit ∧ m < wordLimit ∧ b < wordLimit ∧ s < wordLimit ∧ x < wordLimit ∧
      base.arguments 0 = some (.word l) ∧ base.arguments 1 = some (.word p) ∧
      base.arguments 2 = some (.word m) ∧ base.arguments 3 = some (.word b) ∧
      base.arguments 4 = some (.word s) ∧ base.arguments 5 = some (.word x) ∧
      evalBody checked.method.body (entrySource base checked.core.bindings.length) =
        ⟨.returned (.boolean (leafNumeric l p m b s x))
          (entrySource base checked.core.bindings.length),[]⟩ := by
  have ready := checked.core.entry.arguments_ready base arguments
  rw [shape.formals] at ready
  obtain ⟨l,hl,vl,el⟩ := ready_word_parameter ready (index := 0) (by rfl) shape.types.1
  obtain ⟨p,hp,vp,ep⟩ := ready_word_parameter ready (index := 1) (by rfl) shape.types.2.1
  obtain ⟨m,hm,vm,em⟩ := ready_word_parameter ready (index := 2) (by rfl) shape.types.2.2.1
  obtain ⟨b,hb,vb,eb⟩ := ready_word_parameter ready (index := 3) (by rfl) shape.types.2.2.2.1
  obtain ⟨s,hs,vs,es⟩ := ready_word_parameter ready (index := 4) (by rfl) shape.types.2.2.2.2.1
  obtain ⟨x,hx,vx,ex⟩ := ready_word_parameter ready (index := 5) (by rfl) shape.types.2.2.2.2.2
  have length : checked.core.bindings.length = 6 := by rw [checked.core.entry.1,shape.formals]; rfl
  simp only [entrySource,length] at vl vp vm vb vs vx
  refine ⟨l,p,m,b,s,x,hl,hp,hm,hb,hs,hx,vl,vp,vm,vb,vs,vx,?_⟩
  have evaluation := leaf_evaluation el ep em eb es ex
  rw [shape.body]
  simp [evalBody,sourceExpression,declaredLeafGuard,evaluation]

theorem LeafShape.executes_numeric {checked : LocalFreeBinding t files root module path name}
    (shape : LeafShape checked) (base : Machine)
    (arguments : EntryArguments checked.core.bindings base.arguments) :
    ∃ l p m b s x final,
      base.arguments 0 = some (.word l) ∧ base.arguments 1 = some (.word p) ∧
      base.arguments 2 = some (.word m) ∧ base.arguments 3 = some (.word b) ∧
      base.arguments 4 = some (.word s) ∧ base.arguments 5 = some (.word x) ∧
      EffectRuns (canonicalEffects t checked.identified.id)
        (preparedEntry base (parameterSlot checked.core.bindings) 0) []
        (.returned (.boolean (leafNumeric l p m b s x)) final) ∧
      final.receiver = base.receiver ∧ final.stack = [] ∧
      (leafNumeric l p m b s x = true ↔ LeafAccepted l p m b s x) := by
  obtain ⟨l,p,m,b,s,x,_,_,_,_,_,_,vl,vp,vm,vb,vs,vx,evaluation⟩ := shape.evaluates base arguments
  obtain ⟨result,run,related,terminal⟩ := checked.executes base arguments
  rw [evaluation] at run related
  cases result with
  | next final => cases related
  | trap fault final => cases related
  | returned value final =>
    obtain ⟨same,receiver,stack⟩ := related
    cases same
    exact ⟨l,p,m,b,s,x,final,vl,vp,vm,vb,vs,vx,run,receiver,stack,leaf_numeric_iff⟩

/-- Arbitrary actual true-return execution, not a favorable-path premise. -/
theorem LeafShape.accepted_true {checked : LocalFreeBinding t files root module path name}
    (shape : LeafShape checked) (base : Machine)
    (arguments : EntryArguments checked.core.bindings base.arguments)
    (run : EffectRuns (canonicalEffects t checked.identified.id)
      (preparedEntry base (parameterSlot checked.core.bindings) 0) events
      (.returned (.boolean true) final)) :
    ∃ l p m b s x,
      base.arguments 0 = some (.word l) ∧ base.arguments 1 = some (.word p) ∧
      base.arguments 2 = some (.word m) ∧ base.arguments 3 = some (.word b) ∧
      base.arguments 4 = some (.word s) ∧ base.arguments 5 = some (.word x) ∧
      LeafAccepted l p m b s x := by
  obtain ⟨l,p,m,b,s,x,last,vl,vp,vm,vb,vs,vx,canonical,_,_,policy⟩ := shape.executes_numeric base arguments
  have same := (canonical.terminal_unique True.intro run True.intro).2
  have accepted : leafNumeric l p m b s x = true :=
    Value.boolean.inj (EffectExecution.returned.inj same).1
  exact ⟨l,p,m,b,s,x,vl,vp,vm,vb,vs,vx,policy.mp accepted⟩
end Aurora.SourceBinding
