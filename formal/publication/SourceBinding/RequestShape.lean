import SourceBinding.CallGuardPrefix
import SourceBinding.RequestBounds
namespace Aurora.SourceBinding

/-- Parameters are read from the protected caller map, not the mutable receiver. -/
def WordParameter : GuardExpr .word → Prop
  | .parameter _ _ _ => True
  | _ => False

inductive RequestArguments (epoch offset count : GuardExpr .word) :
    {kinds : List GuardType} → CallArguments kinds → Prop
  | exact : RequestArguments epoch offset count
      (.cons epoch (.cons offset (.cons (.wordLit 0) (.cons count .nil))))

/-- Optional source-derived policy shape. The base byte/graph/IR/callee binding is
    retained intact, and every repeated operand is checked as the SAME typed AST. -/
structure RequestShape (checked : CallBinding files root module path member bytes) where
  guarded : GuardedCallPrefix checked
  prior : GuardExpr .boolean
  bytes : GuardExpr .word
  epoch : GuardExpr .word
  offset : GuardExpr .word
  count : GuardExpr .word
  epochParameter : WordParameter epoch
  offsetParameter : WordParameter offset
  countParameter : WordParameter count
  guardEq : guarded.guard = requestRange prior offset bytes count
  arguments : RequestArguments epoch offset count guarded.resourceArguments

structure RequestArgumentShape {kinds : List GuardType} (arguments : CallArguments kinds) where
  epoch : GuardExpr .word
  offset : GuardExpr .word
  count : GuardExpr .word
  epochParameter : WordParameter epoch
  offsetParameter : WordParameter offset
  countParameter : WordParameter count
  exactArguments : RequestArguments epoch offset count arguments

def requestArgumentShape : {kinds : List GuardType} → (arguments : CallArguments kinds) →
    Option (RequestArgumentShape arguments)
  | _, .cons (.parameter .word en ei) (.cons (.parameter .word on oi)
      (.cons (.wordLit 0) (.cons (.parameter .word cn ci) .nil))) =>
    some ⟨.parameter .word en ei,.parameter .word on oi,.parameter .word cn ci,
      True.intro,True.intro,True.intro,.exact⟩
  | _, _ => none

def checkRequestShape (checked : CallBinding files root module path member bytes) : Option (RequestShape checked) := do
  let guarded ← checkGuardedCallPrefix checked
  let args ← requestArgumentShape guarded.resourceArguments
  match guarded.guard with
  | .or (.or (.or prior _) (.compare .gt _ bytes)) _ =>
    if same : guarded.guard = requestRange prior args.offset bytes args.count then
      return ⟨guarded,prior,bytes,args.epoch,args.offset,args.count,args.epochParameter,
        args.offsetParameter,args.countParameter,same,args.exactArguments⟩
    else none
  | _ => none

/-- Successful ordered argument evaluation exposes each actual operand result. -/
theorem eval_arguments_cons (state : SourceState) (first : GuardExpr kind)
    (rest : CallArguments kinds) (values : List Value)
    (evaluated : evalCallArguments state (.cons first rest) = .value values) :
    ∃ head tail, evalGuard state first = .value head ∧
      evalCallArguments state rest = .value tail ∧ values = head :: tail := by
  cases a : evalGuard state first with
  | trap fault => simp [evalCallArguments,a,Outcome.then] at evaluated
  | value head =>
    cases b : evalCallArguments state rest with
    | trap fault => simp [evalCallArguments,a,b,Outcome.then] at evaluated
    | value tail =>
      exact ⟨head,tail,rfl,rfl,by
        simpa only [evalCallArguments,a,b,Outcome.then,Outcome.value.injEq] using evaluated.symm⟩

theorem eval_word_result (state : SourceState) (expression : GuardExpr .word) (value : Value)
    (evaluated : evalGuard state expression = .value value) :
    ∃ n, value = .word n ∧ n < wordLimit := by
  have typed := eval_value_typed state expression value evaluated
  cases value with
  | boolean _ | signedCount12 => simp [readScalar] at typed
  | word n => exact ⟨n,rfl,by simpa [readScalar] using typed⟩

/-- The request's ordered scalar values are obtained from its actual pure
    argument evaluation, not from a parallel handwritten policy calculation. -/
theorem RequestArguments.values (shape : RequestArguments epoch offset count arguments)
    (state : SourceState) (values : List Value)
    (evaluated : evalCallArguments state arguments = .value values) :
    ∃ e o c, values = [.word e,.word o,.word 0,.word c] ∧
      evalGuard state epoch = .value (.word e) ∧
      evalGuard state offset = .value (.word o) ∧
      evalGuard state count = .value (.word c) ∧ e < wordLimit ∧ o < wordLimit ∧ c < wordLimit := by
  cases shape
  obtain ⟨ev,tail,ee,et,order⟩ := eval_arguments_cons state _ _ _ evaluated
  obtain ⟨ov,tail2,eo,et2,order2⟩ := eval_arguments_cons state _ _ _ et
  obtain ⟨zero,tail3,ez,et3,order3⟩ := eval_arguments_cons state _ _ _ et2
  obtain ⟨cv,tail4,ec,et4,order4⟩ := eval_arguments_cons state _ _ _ et3
  obtain ⟨e,rfl,eb⟩ := eval_word_result state _ _ ee
  obtain ⟨o,rfl,ob⟩ := eval_word_result state _ _ eo
  obtain ⟨c,rfl,cb⟩ := eval_word_result state _ _ ec
  have z : zero = .word 0 := (Outcome.value.inj ez).symm
  have empty : tail4 = [] := (Outcome.value.inj et4).symm
  exact ⟨e,o,c,by simp only [order,order2,order3,order4,z,empty],ee,eo,ec,eb,ob,cb⟩

example : WordParameter (.parameter .word "arbitrary".toUTF8 17) := True.intro
example : ¬ WordParameter (.field .word "arbitrary".toUTF8 17) := id
example : RequestArguments (.wordLit 4) (.wordLit 2) (.wordLit 1)
    (.cons (.wordLit 4) (.cons (.wordLit 2) (.cons (.wordLit 0) (.cons (.wordLit 1) .nil)))) := .exact

-- Isolated syntax-profile controls, not artifact acceptance fixtures.
#eval do
  let parameter := GuardExpr.parameter .word "any".toUTF8 8
  let good := CallArguments.cons parameter (.cons parameter (.cons (.wordLit 0) (.cons parameter .nil)))
  let wrongZero := CallArguments.cons parameter (.cons parameter (.cons (.wordLit 1) (.cons parameter .nil)))
  let field := CallArguments.cons (.field .word "any".toUTF8 8) (.cons parameter (.cons (.wordLit 0) (.cons parameter .nil)))
  unless (requestArgumentShape good).isSome && (requestArgumentShape wrongZero).isNone &&
      (requestArgumentShape field).isNone do throw (IO.userError "request argument shape controls")
  IO.println "request argument shape controls: 3 passed"

end Aurora.SourceBinding
