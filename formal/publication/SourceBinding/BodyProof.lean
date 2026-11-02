import SourceBinding.BodySemantics
import SourceBinding.EffectCode
namespace Aurora.SourceBinding

@[simp] theorem frame_self (machine : Machine) :
    frameState machine machine.pc machine.accumulator machine.stack = machine := by cases machine; rfl

theorem ContextRelated.frame (context : ContextRelated source base slots) (pc : Nat)
    (accumulator : Option Value) (stack : List Value) :
    ContextRelated source (frameState base pc accumulator stack) slots := ⟨context.fields,context.parameters⟩

theorem assign_simulates {program : EffectProgram} {slots : Nat → Nat} {kind : GuardType}
    {value : GuardExpr kind} {start middle ordinal : Nat}
    (expression : ExprCode (pureView program) slots value start middle)
    (store : program middle = some (.store kind ordinal))
    (source : SourceState) (base : Machine) (context : ContextRelated source base slots)
    (accumulator : Option Value) (stack : List Value) :
    ∃ result, EffectRuns program (frameState base start accumulator stack)
      (evalBody (.assign kind ordinal value) source).stores result ∧
      BodyResultRelated slots stack (middle + 1) (evalBody (.assign kind ordinal value) source).execution result := by
  cases evaluated : evalGuard source value with
  | trap fault =>
    obtain ⟨final,run,receiver⟩ := expression.effect_fault source base context accumulator stack fault evaluated
    exact ⟨.trap (.scalar fault) final,by simpa [evalBody,sourceExpression,evaluated] using run,
      by simpa [evalBody,sourceExpression,evaluated,BodyResultRelated] using receiver⟩
  | value scalar =>
    have run := expression.effect_value source base context accumulator stack scalar evaluated
    cases checked : readScalar kind (some scalar) with
    | trap fault =>
      have last : EffectRuns program (frameState base middle (some scalar) stack) []
          (.trap (.scalar fault) (frameState base middle (some scalar) stack)) := by
        simpa [effectStep,frameState,store,checked] using
          (EffectRuns.one (program := program) (state := frameState base middle (some scalar) stack))
      refine ⟨.trap (.scalar fault) (frameState base middle (some scalar) stack),?_,?_⟩
      · simpa [evalBody,sourceExpression,evaluated,checked] using run.trans last
      · simp [evalBody,sourceExpression,evaluated,checked,BodyResultRelated,frameState,funext context.fields]
    | value checkedValue =>
      let final : Machine := {base with
        pc := middle + 1
        accumulator := some scalar
        stack := stack
        receiver := fun index => if index = ordinal then some checkedValue else base.receiver index}
      have last : EffectRuns program (frameState base middle (some scalar) stack) [⟨ordinal,checkedValue⟩]
          (.next final) := by
        simpa [effectStep,frameState,store,checked,final] using
          (EffectRuns.one (program := program) (state := frameState base middle (some scalar) stack))
      refine ⟨.next final,?_,?_⟩
      · simpa [evalBody,sourceExpression,evaluated,checked] using run.trans last
      · simp only [evalBody,sourceExpression,evaluated,checked,BodyResultRelated]
        refine ⟨rfl,rfl,?_,?_⟩
        · intro index; simp only [final]; split <;> first | rfl | exact context.fields index
        · exact context.parameters

theorem require_simulates {program : EffectProgram} {slots : Nat → Nat}
    {condition : GuardExpr .boolean} {start middle : Nat}
    (expression : ExprCode (pureView program) slots condition start middle)
    (require : program middle = some .require)
    (source : SourceState) (base : Machine) (context : ContextRelated source base slots)
    (accumulator : Option Value) (stack : List Value) :
    ∃ result, EffectRuns program (frameState base start accumulator stack)
      (evalBody (.require condition) source).stores result ∧
      BodyResultRelated slots stack (middle + 1) (evalBody (.require condition) source).execution result := by
  cases evaluated : evalGuard source condition with
  | trap fault =>
    obtain ⟨final,run,receiver⟩ := expression.effect_fault source base context accumulator stack fault evaluated
    exact ⟨.trap (.scalar fault) final,by simpa [evalBody,sourceExpression,evaluated] using run,
      by simpa [evalBody,sourceExpression,evaluated,BodyResultRelated] using receiver⟩
  | value scalar =>
    have run := expression.effect_value source base context accumulator stack scalar evaluated
    have last := EffectRuns.one (program := program) (state := frameState base middle (some scalar) stack)
    cases scalar with
    | word n =>
      refine ⟨.trap (.scalar .type) (frameState base middle (some (.word n)) stack),?_,?_⟩
      · simpa [evalBody,sourceExpression,evaluated,effectStep,frameState,require] using run.trans last
      · simp [evalBody,sourceExpression,evaluated,BodyResultRelated,frameState,funext context.fields]
    | signedCount12 =>
      refine ⟨.trap (.scalar .type) (frameState base middle (some .signedCount12) stack),?_,?_⟩
      · simpa [evalBody,sourceExpression,evaluated,effectStep,frameState,require] using run.trans last
      · simp [evalBody,sourceExpression,evaluated,BodyResultRelated,frameState,funext context.fields]
    | signedCount4 =>
      refine ⟨.trap (.scalar .type) (frameState base middle (some .signedCount4) stack),?_,?_⟩
      · simpa [evalBody,sourceExpression,evaluated,effectStep,frameState,require] using run.trans last
      · simp [evalBody,sourceExpression,evaluated,BodyResultRelated,frameState,funext context.fields]
    | signedCount32 =>
      refine ⟨.trap (.scalar .type) (frameState base middle (some .signedCount32) stack),?_,?_⟩
      · simpa [evalBody,sourceExpression,evaluated,effectStep,frameState,require] using run.trans last
      · simp [evalBody,sourceExpression,evaluated,BodyResultRelated,frameState,funext context.fields]
    | nominal name ordinal =>
      refine ⟨.trap (.scalar .type) (frameState base middle (some (.nominal name ordinal)) stack),?_,?_⟩
      · simpa [evalBody,sourceExpression,evaluated,effectStep,frameState,require] using run.trans last
      · simp [evalBody,sourceExpression,evaluated,BodyResultRelated,frameState,funext context.fields]
    | boolean b =>
      cases b with
      | false =>
        refine ⟨.trap .assertion (frameState base middle (some (.boolean false)) stack),?_,?_⟩
        · simpa [evalBody,sourceExpression,evaluated,effectStep,frameState,require] using run.trans last
        · simp [evalBody,sourceExpression,evaluated,BodyResultRelated,frameState,funext context.fields]
      | true =>
        refine ⟨.next (frameState base (middle + 1) none stack),?_,?_⟩
        · simpa [evalBody,sourceExpression,evaluated,effectStep,frameState,require] using run.trans last
        · simp only [evalBody,sourceExpression,evaluated,BodyResultRelated]
          exact ⟨rfl,rfl,context.frame _ _ _⟩

theorem return_simulates {program : EffectProgram} {slots : Nat → Nat} {kind : GuardType}
    {value : GuardExpr kind} {start middle : Nat}
    (expression : ExprCode (pureView program) slots value start middle)
    (ret : program middle = some (.pure .ret))
    (source : SourceState) (base : Machine) (context : ContextRelated source base slots)
    (accumulator : Option Value) (stack : List Value) :
    ∃ result, EffectRuns program (frameState base start accumulator stack)
      (evalBody (.returnValue kind value) source).stores result ∧
      BodyResultRelated slots stack (middle + 1) (evalBody (.returnValue kind value) source).execution result := by
  cases evaluated : evalGuard source value with
  | trap fault =>
    obtain ⟨final,run,receiver⟩ := expression.effect_fault source base context accumulator stack fault evaluated
    exact ⟨.trap (.scalar fault) final,by simpa [evalBody,sourceExpression,evaluated] using run,
      by simpa [evalBody,sourceExpression,evaluated,BodyResultRelated] using receiver⟩
  | value scalar =>
    have run := expression.effect_value source base context accumulator stack scalar evaluated
    have last := EffectRuns.one (program := program) (state := frameState base middle (some scalar) stack)
    refine ⟨.returned scalar (frameState base middle (some scalar) stack),?_,?_⟩
    · simpa [evalBody,sourceExpression,evaluated,effectStep,frameState,ret,pureView,step,retainState] using run.trans last
    · simp [evalBody,sourceExpression,evaluated,BodyResultRelated,frameState,funext context.fields]

/-- Checked administrative paths change only the PC and emit no store events. -/
def SkipPath (program : EffectProgram) (start stop : Nat) : Prop :=
  ∀ base accumulator stack, EffectRuns program (frameState base start accumulator stack) []
    (.next (frameState base stop accumulator stack))

theorem label_path (program : EffectProgram) (pc : Nat) (code : program pc = some (.pure .label)) :
    SkipPath program pc (pc + 1) := by
  intro base accumulator stack
  simpa [effectStep,frameState,code,pureView,step,retainState] using
    (EffectRuns.one (program := program) (state := frameState base pc accumulator stack))

theorem jump_path (program : EffectProgram) (pc target : Nat) (code : program pc = some (.pure (.jump target))) :
    SkipPath program pc target := by
  intro base accumulator stack
  simpa [effectStep,frameState,code,pureView,step,retainState] using
    (EffectRuns.one (program := program) (state := frameState base pc accumulator stack))

theorem SkipPath.trans (first : SkipPath program start middle) (rest : SkipPath program middle stop) :
    SkipPath program start stop := by
  intro base accumulator stack
  exact (first base accumulator stack).trans (rest base accumulator stack)

theorem branch_simulates {program : EffectProgram} {slots : Nat → Nat}
    {condition : GuardExpr .boolean} {body : EffectBody} {start conditionEnd bodyEnd falseTarget stop : Nat}
    (expression : ExprCode (pureView program) slots condition start conditionEnd)
    (branch : program conditionEnd = some (.pure (.branchFalse falseTarget)))
    (afterTrue : SkipPath program bodyEnd stop) (afterFalse : SkipPath program falseTarget stop)
    (bodyRun : ∀ source base, ContextRelated source base slots → ∀ accumulator stack,
      ∃ result, EffectRuns program (frameState base (conditionEnd + 1) accumulator stack)
        (evalBody body source).stores result ∧
        BodyResultRelated slots stack bodyEnd (evalBody body source).execution result)
    (source : SourceState) (base : Machine) (context : ContextRelated source base slots)
    (accumulator : Option Value) (stack : List Value) :
    ∃ result, EffectRuns program (frameState base start accumulator stack)
      (evalBody (.branch condition body) source).stores result ∧
      BodyResultRelated slots stack stop (evalBody (.branch condition body) source).execution result := by
  cases evaluated : evalGuard source condition with
  | trap fault =>
    obtain ⟨final,run,receiver⟩ := expression.effect_fault source base context accumulator stack fault evaluated
    exact ⟨.trap (.scalar fault) final,by simpa [evalBody,sourceExpression,evaluated] using run,
      by simpa [evalBody,sourceExpression,evaluated,BodyResultRelated] using receiver⟩
  | value scalar =>
    have run := expression.effect_value source base context accumulator stack scalar evaluated
    have test := EffectRuns.one (program := program) (state := frameState base conditionEnd (some scalar) stack)
    cases scalar with
    | word n =>
      refine ⟨.trap (.scalar .type) (frameState base conditionEnd (some (.word n)) stack),?_,?_⟩
      · simpa [evalBody,sourceExpression,evaluated,effectStep,frameState,branch,pureView,step,retainState] using run.trans test
      · simp [evalBody,sourceExpression,evaluated,BodyResultRelated,frameState,funext context.fields]
    | signedCount12 =>
      refine ⟨.trap (.scalar .type) (frameState base conditionEnd (some .signedCount12) stack),?_,?_⟩
      · simpa [evalBody,sourceExpression,evaluated,effectStep,frameState,branch,pureView,step,retainState] using run.trans test
      · simp [evalBody,sourceExpression,evaluated,BodyResultRelated,frameState,funext context.fields]
    | signedCount4 =>
      refine ⟨.trap (.scalar .type) (frameState base conditionEnd (some .signedCount4) stack),?_,?_⟩
      · simpa [evalBody,sourceExpression,evaluated,effectStep,frameState,branch,pureView,step,retainState] using run.trans test
      · simp [evalBody,sourceExpression,evaluated,BodyResultRelated,frameState,funext context.fields]
    | signedCount32 =>
      refine ⟨.trap (.scalar .type) (frameState base conditionEnd (some .signedCount32) stack),?_,?_⟩
      · simpa [evalBody,sourceExpression,evaluated,effectStep,frameState,branch,pureView,step,retainState] using run.trans test
      · simp [evalBody,sourceExpression,evaluated,BodyResultRelated,frameState,funext context.fields]
    | nominal name ordinal =>
      refine ⟨.trap (.scalar .type) (frameState base conditionEnd (some (.nominal name ordinal)) stack),?_,?_⟩
      · simpa [evalBody,sourceExpression,evaluated,effectStep,frameState,branch,pureView,step,retainState] using run.trans test
      · simp [evalBody,sourceExpression,evaluated,BodyResultRelated,frameState,funext context.fields]
    | boolean b =>
      cases b with
      | false =>
        have tested : EffectRuns program (frameState base start accumulator stack) []
            (.next (frameState base falseTarget (some (.boolean false)) stack)) := by
          simpa [effectStep,frameState,branch,pureView,step,retainState] using run.trans test
        refine ⟨.next (frameState base stop (some (.boolean false)) stack),?_,?_⟩
        · simpa [evalBody,sourceExpression,evaluated] using tested.trans (afterFalse base _ stack)
        · simp only [evalBody,sourceExpression,evaluated,BodyResultRelated]
          exact ⟨rfl,rfl,context.frame _ _ _⟩
      | true =>
        have tested : EffectRuns program (frameState base start accumulator stack) []
            (.next (frameState base (conditionEnd + 1) (some (.boolean true)) stack)) := by
          simpa [effectStep,frameState,branch,pureView,step,retainState] using run.trans test
        obtain ⟨result,bodyExec,related⟩ := bodyRun source base context (some (.boolean true)) stack
        have prior := tested.trans bodyExec
        cases sourceResult : (evalBody body source).execution with
        | next nextSource =>
          rw [sourceResult] at related
          cases result with
          | returned value machine => contradiction
          | trap fault machine => contradiction
          | next machine =>
            obtain ⟨pc,sameStack,nextContext⟩ := related
            have finish := afterTrue machine machine.accumulator machine.stack
            rw [← pc,frame_self] at finish
            refine ⟨.next (frameState machine stop machine.accumulator machine.stack),?_,?_⟩
            · simpa [evalBody,sourceExpression,evaluated] using prior.trans finish
            · simp only [evalBody,sourceExpression,evaluated,sourceResult,BodyResultRelated]
              exact ⟨rfl,sameStack,nextContext.frame _ _ _⟩
        | returned value nextSource =>
          rw [sourceResult] at related
          cases result with
          | next machine => contradiction
          | trap fault machine => contradiction
          | returned scalar machine =>
            refine ⟨.returned scalar machine,?_,?_⟩
            · simpa [evalBody,sourceExpression,evaluated] using prior
            · simpa only [evalBody,sourceExpression,evaluated,sourceResult,BodyResultRelated] using related
        | trap fault nextSource =>
          rw [sourceResult] at related
          cases result with
          | next machine => contradiction
          | returned value machine => contradiction
          | trap error machine =>
            refine ⟨.trap error machine,?_,?_⟩
            · simpa [evalBody,sourceExpression,evaluated] using prior
            · simpa only [evalBody,sourceExpression,evaluated,sourceResult,BodyResultRelated] using related

/-- Whole compositional source/IR correspondence, including exact ordered stores
    and current final receivers on both return and failure. -/
theorem BodyCode.simulates {program : EffectProgram} {slots : Nat → Nat}
    {body : EffectBody} {start stop : Nat} (code : BodyCode program slots body start stop)
    (source : SourceState) (base : Machine) (context : ContextRelated source base slots)
    (accumulator : Option Value) (stack : List Value) :
    ∃ result, EffectRuns program (frameState base start accumulator stack) (evalBody body source).stores result ∧
      BodyResultRelated slots stack stop (evalBody body source).execution result := by
  induction code generalizing source base accumulator stack with
  | skip => exact ⟨.next _,.reflexive,rfl,rfl,context.frame _ _ _⟩
  | assign expression store => exact assign_simulates expression store source base context accumulator stack
  | require expression require => exact require_simulates expression require source base context accumulator stack
  | returnValue expression ret => exact return_simulates expression ret source base context accumulator stack
  | @seq first start middle rest stop head tail headIH tailIH =>
    obtain ⟨result,prior,related⟩ := headIH source base context accumulator stack
    cases sourceResult : (evalBody first source).execution with
    | next nextSource =>
      rw [sourceResult] at related
      cases result with
      | returned value machine => contradiction
      | trap fault machine => contradiction
      | next machine =>
        obtain ⟨pc,sameStack,nextContext⟩ := related
        obtain ⟨final,later,finalRelated⟩ := tailIH nextSource machine nextContext machine.accumulator stack
        have same : frameState machine middle machine.accumulator stack = machine := by
          rw [← pc,← sameStack]; exact frame_self machine
        rw [same] at later
        refine ⟨final,?_,?_⟩
        · simpa only [evalBody,sourceResult] using prior.trans later
        · simpa only [evalBody,sourceResult] using finalRelated
    | returned value nextSource =>
      rw [sourceResult] at related
      cases result with
      | next machine => contradiction
      | trap fault machine => contradiction
      | returned scalar machine =>
        refine ⟨.returned scalar machine,?_,?_⟩
        · simpa only [evalBody,sourceResult] using prior
        · simpa only [evalBody,sourceResult,BodyResultRelated] using related
    | trap fault nextSource =>
      rw [sourceResult] at related
      cases result with
      | next machine => contradiction
      | returned value machine => contradiction
      | trap error machine =>
        refine ⟨.trap error machine,?_,?_⟩
        · simpa only [evalBody,sourceResult] using prior
        · simpa only [evalBody,sourceResult,BodyResultRelated] using related
  | @branchSingle condition start conditionEnd bodyEnd body expression branch bodyCode label ih =>
    exact branch_simulates expression branch (label_path program bodyEnd label) (label_path program bodyEnd label)
      ih source base context accumulator stack
  | @branchJoined condition start conditionEnd bodyEnd body expression branch bodyCode jump falseLabel endLabel ih =>
    have ending : SkipPath program (bodyEnd + 2) (bodyEnd + 3) := by
      simpa only [Nat.add_assoc] using label_path program (bodyEnd + 2) endLabel
    have truePath := (jump_path program bodyEnd (bodyEnd + 2) jump).trans ending
    have falsePath : SkipPath program (bodyEnd + 1) (bodyEnd + 3) := by
      have first : SkipPath program (bodyEnd + 1) (bodyEnd + 2) := by
        simpa only [Nat.add_assoc] using label_path program (bodyEnd + 1) falseLabel
      exact first.trans ending
    exact branch_simulates expression branch truePath falsePath ih source base context accumulator stack

end Aurora.SourceBinding
