import SourceBinding.CallArgumentValues
open Aurora.SourceBinding

def argumentState : SourceState := ⟨fun _ => none, fun n =>
  if n = 0 then some (.word 7) else if n = 1 then some (.boolean true) else none⟩

example : evalGuard argumentState (.parameter .word "x".toUTF8 0) = .value (.word 7) := by decide
example : evalGuard argumentState (.parameter .boolean "x".toUTF8 0) = .trap .type := by decide
example : evalGuard argumentState (.parameter .word "x".toUTF8 2) = .trap .type := by decide
example : evalGuard argumentState (.wordLit wordLimit) = .trap .range := by decide
example : evalGuard argumentState (.sub (.wordLit 1) (.wordLit 2)) = .trap .underflow := by decide
example : evalGuard argumentState (.and (.boolLit false) (.parameter .boolean "absent".toUTF8 2)) =
    .value (.boolean false) := by decide
example : evalGuard argumentState (.or (.boolLit true) (.parameter .boolean "absent".toUTF8 2)) =
    .value (.boolean true) := by decide
example : readScalar .word (some (.word 7)) = .value (.word 7) :=
  eval_value_typed argumentState (.parameter .word "x".toUTF8 0) (.word 7) (by decide)

example : evalCallArguments argumentState (.cons (.wordLit 4) (.cons (.boolLit true) .nil)) =
    .value [.word 4,.boolean true] := by decide
example : evalCallArguments argumentState
    (.cons (.sub (.wordLit 1) (.wordLit 2)) (.cons (.parameter .word "absent".toUTF8 2) .nil)) =
    .trap .underflow := by decide
example : evalCallArguments argumentState
    (.cons (.parameter .word "absent".toUTF8 2) (.cons (.sub (.wordLit 1) (.wordLit 2)) .nil)) =
    .trap .type := by decide
example : ReadyArguments [.word,.boolean] [.word 4,.boolean true] :=
  eval_call_arguments_ready argumentState (.cons (.wordLit 4) (.cons (.boolLit true) .nil)) (by decide)
