import SourceBinding.CallBodySupport
import SourceBinding.GuardSafety
namespace Aurora.SourceBinding

def argumentAccumulator (values : List Value) (initial : Option Value) : Option Value :=
  values.foldl (fun _ value => some value) initial

theorem LabelRun.effect_runs {program : EffectProgram} (code : LabelRun (pureView program) start stop)
    (base : Machine) (accumulator : Option Value) (stack : List Value) :
    EffectRuns program (frameState base start accumulator stack) []
      (.next (frameState base stop accumulator stack)) := by
  induction code with
  | nil => exact .reflexive
  | @cons start stop label rest ih =>
    have first : Runs (pureView program) (frameState base start accumulator stack)
        (.next (frameState base (start + 1) accumulator stack)) := by
      apply Runs.one
      simp only [step,frameState,label]
    exact (pure_next_lift first).trans ih

theorem PushedArgumentsCode.effect_values {program : EffectProgram}
    (code : PushedArgumentsCode (pureView program) slots arguments start stop)
    (source : SourceState) (base : Machine) (context : ContextRelated source base slots)
    (accumulator : Option Value) (stack : List Value) (values : List Value)
    (evaluated : evalCallArguments source arguments = .value values) :
    EffectRuns program (frameState base start accumulator stack) []
      (.next (frameState base stop (argumentAccumulator values accumulator) (values.reverse ++ stack))) := by
  induction code generalizing accumulator stack values with
  | nil =>
    cases evaluated
    exact .reflexive
  | @cons kind argument start middle kinds arguments stop expression push rest ih =>
    cases firstValue : evalGuard source argument with
    | trap fault => simp only [evalCallArguments,firstValue,Outcome.then] at evaluated; cases evaluated
    | value value =>
      cases tailValue : evalCallArguments source arguments with
      | trap fault => simp only [evalCallArguments,firstValue,Outcome.then,tailValue] at evaluated; cases evaluated
      | value tail =>
        simp only [evalCallArguments,firstValue,Outcome.then,tailValue,Outcome.value.injEq] at evaluated
        subst values
        have first := expression.effect_value source base context accumulator stack value firstValue
        have pushed : Runs (pureView program) (frameState base middle (some value) stack)
            (.next (frameState base (middle + 1) (some value) (value :: stack))) := by
          apply Runs.one
          simp only [step,frameState,push]
        have later := ih (some value) (value :: stack) tail tailValue
        have run := (first.trans (pure_next_lift pushed)).trans later
        simpa only [argumentAccumulator,List.foldl_cons,List.reverse_cons,List.append_assoc,
          List.singleton_append] using run
theorem PushedArgumentsCode.effect_fault {program : EffectProgram}
    (code : PushedArgumentsCode (pureView program) slots arguments start stop)
    (source : SourceState) (base : Machine) (context : ContextRelated source base slots)
    (accumulator : Option Value) (stack : List Value) (fault : Fault)
    (evaluated : evalCallArguments source arguments = .trap fault) :
    ∃ final, EffectRuns program (frameState base start accumulator stack) [] (.trap (.scalar fault) final) ∧
      final.receiver = base.receiver ∧ final.arguments = base.arguments := by
  induction code generalizing accumulator stack with
  | nil => cases evaluated
  | @cons kind argument start middle kinds arguments stop expression push rest ih =>
    cases firstValue : evalGuard source argument with
    | trap firstFault =>
      simp only [evalCallArguments,firstValue,Outcome.then,Outcome.trap.injEq] at evaluated
      subst firstFault
      obtain ⟨result,run,related⟩ := expression.effect_simulates source base context accumulator stack
      simp only [ExpressionResult,firstValue] at related
      obtain ⟨final,same,receiver,parameters⟩ := related
      subst result
      exact ⟨final,run,receiver,parameters⟩
    | value value =>
      cases tailValue : evalCallArguments source arguments with
      | value tail => simp only [evalCallArguments,firstValue,Outcome.then,tailValue] at evaluated; cases evaluated
      | trap tailFault =>
        simp only [evalCallArguments,firstValue,Outcome.then,tailValue,Outcome.trap.injEq] at evaluated
        subst tailFault
        have first := expression.effect_value source base context accumulator stack value firstValue
        have pushed : Runs (pureView program) (frameState base middle (some value) stack)
            (.next (frameState base (middle + 1) (some value) (value :: stack))) := by
          apply Runs.one
          simp only [step,frameState,push]
        obtain ⟨final,later,receiver,parameters⟩ := ih (some value) (value :: stack) tailValue
        exact ⟨final,(first.trans (pure_next_lift pushed)).trans later,receiver,parameters⟩
theorem EntryCode.argument_kinds {kinds : List GuardType} (entry : EntryCode program formals bindings)
    (declared : formals.map (·.type) = kinds.map guardSourceType)
    {index : Nat} (bound : index < bindings.length) :
    kinds[index]? = some (parameterKind bindings index) := by
  have sizes := congrArg List.length declared
  simp only [List.length_map] at sizes
  have inKinds : index < kinds.length := by have length := entry.1; omega
  have atKind := List.getElem?_eq_getElem inKinds
  have atType := congrArg (fun types => types[index]?) declared
  simp only [List.getElem?_map,(entry.2.2 index bound).2.1,atKind,Option.map_some,Option.some.injEq] at atType
  have same := guardSourceType_injective atType
  exact same ▸ atKind

theorem EntryCode.evaluated_arguments {kinds : List GuardType} (entry : EntryCode program formals bindings)
    (declared : formals.map (·.type) = kinds.map guardSourceType)
    (expressions : CallArguments kinds) (source : SourceState) (values : List Value)
    (evaluated : evalCallArguments source expressions = .value values) :
    EntryArguments bindings (fun index => values[index]?) := by
  intro index bound
  exact (eval_call_arguments_ready source expressions evaluated).lookup (EntryCode.argument_kinds entry declared bound)
theorem ArgumentsCode.effect_values {program : EffectProgram} {kinds : List GuardType}
    {arguments : CallArguments kinds}
    (code : ArgumentsCode (pureView program) slots resource arguments start stop)
    (source : SourceState) (base : Machine) (context : ContextRelated source base slots)
    (accumulator : Option Value) (stack : List Value) (values : List Value)
    (evaluated : evalCallArguments source arguments = .value values) :
    ∃ acc resultStack, EffectRuns program (frameState base start accumulator stack) []
        (.next (frameState base stop acc resultStack)) ∧
      collectArguments resource kinds.length (CallFrame.ofMachine (frameState base stop acc resultStack)) =
        some (values,stack) := by
  cases code with
  | pushed mode code =>
    have sizes := (eval_call_arguments_ready source arguments evaluated).length
    have notSingle : (resource && kinds.length == 1) = false := by
      cases mode with
      | inl ordinary => subst resource; rfl
      | inr multiple =>
        have unequal : (kinds.length == 1) = false := by
          apply Bool.eq_false_iff.mpr
          intro equal
          exact multiple (beq_iff_eq.mp equal)
        rw [unequal,Bool.and_false]
    have enough : kinds.length ≤ (values.reverse ++ stack).length := by
      simp only [List.length_append,List.length_reverse]; omega
    have taken : (values.reverse ++ stack).take kinds.length = values.reverse := by
      rw [sizes]; simpa only [List.length_reverse] using (List.take_left (l₁ := values.reverse) (l₂ := stack))
    have dropped : (values.reverse ++ stack).drop kinds.length = stack := by
      rw [sizes]; simpa only [List.length_reverse] using (List.drop_left (l₁ := values.reverse) (l₂ := stack))
    refine ⟨argumentAccumulator values accumulator,values.reverse ++ stack,
      code.effect_values source base context accumulator stack values evaluated,?_⟩
    simp only [collectArguments,CallFrame.ofMachine,frameState,notSingle,Bool.false_eq_true,if_false,
      enough,if_true,taken,dropped,List.reverse_reverse]
  | @single kind expression start stop code =>
    cases valueEq : evalGuard source expression with
    | trap fault => simp only [evalCallArguments,valueEq,Outcome.then] at evaluated; cases evaluated
    | value value =>
      simp only [evalCallArguments,valueEq,Outcome.then,Outcome.value.injEq] at evaluated
      subst values
      refine ⟨some value,stack,code.effect_value source base context accumulator stack value valueEq,?_⟩
      rfl
theorem ArgumentsCode.effect_fault {program : EffectProgram} {kinds : List GuardType}
    {arguments : CallArguments kinds}
    (code : ArgumentsCode (pureView program) slots resource arguments start stop)
    (source : SourceState) (base : Machine) (context : ContextRelated source base slots)
    (accumulator : Option Value) (stack : List Value) (fault : Fault)
    (evaluated : evalCallArguments source arguments = .trap fault) :
    ∃ final, EffectRuns program (frameState base start accumulator stack) [] (.trap (.scalar fault) final) ∧
      final.receiver = base.receiver ∧ final.arguments = base.arguments := by
  cases code with
  | pushed mode code => exact code.effect_fault source base context accumulator stack fault evaluated
  | @single kind expression start stop code =>
    cases valueEq : evalGuard source expression with
    | value value => simp only [evalCallArguments,valueEq,Outcome.then] at evaluated; cases evaluated
    | trap actual =>
      simp only [evalCallArguments,valueEq,Outcome.then,Outcome.trap.injEq] at evaluated
      subst actual
      obtain ⟨result,run,related⟩ := code.effect_simulates source base context accumulator stack
      simp only [ExpressionResult,valueEq] at related
      obtain ⟨final,same,receiver,parameters⟩ := related
      subst result
      exact ⟨final,run,receiver,parameters⟩
end Aurora.SourceBinding
