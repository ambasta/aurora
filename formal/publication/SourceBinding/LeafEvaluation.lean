import SourceBinding.LeafNumeric
import SourceBinding.ArgumentValues
namespace Aurora.SourceBinding

theorem eval_and_values (left : evalGuard state a = .value (.boolean x))
    (right : evalGuard state b = .value (.boolean y)) :
    evalGuard state (.and a b) = .value (.boolean (x && y)) := by
  cases x <;> simp [evalGuard,left,right,Outcome.then]

theorem eval_and_false (left : evalGuard state a = .value (.boolean false)) :
    evalGuard state (.and a b) = .value (.boolean false) := by
  simp [evalGuard,left,Outcome.then]

theorem eval_word_bound (expression : GuardExpr .word)
    (evaluated : evalGuard state expression = .value (.word value)) : value < wordLimit := by
  have typed := eval_value_typed state expression (.word value) evaluated
  simpa [readScalar] using typed

theorem eval_bitAnd_values (left : evalGuard state a = .value (.word x))
    (right : evalGuard state b = .value (.word y)) :
    evalGuard state (.bitAnd a b) = .value (.word (x &&& y)) := by
  have hx := eval_word_bound a left
  have hy := eval_word_bound b right
  simp [evalGuard,left,right,Outcome.then,binaryValue,hx,hy]

theorem eval_bitOr_values (left : evalGuard state a = .value (.word x))
    (right : evalGuard state b = .value (.word y)) :
    evalGuard state (.bitOr a b) = .value (.word (x ||| y)) := by
  have hx := eval_word_bound a left
  have hy := eval_word_bound b right
  simp [evalGuard,left,right,Outcome.then,binaryValue,hx,hy]

theorem eval_compare_values (left : evalGuard state a = .value (.word x))
    (right : evalGuard state b = .value (.word y)) :
    evalGuard state (.compare op a b) = .value (.boolean (compareWords op x y)) := by
  have hx := eval_word_bound a left
  have hy := eval_word_bound b right
  simp [evalGuard,left,right,Outcome.then,binaryValue,hx,hy]

/-- Total evaluation from bounded reads, not an assumed admission or no-overflow
    result. Rejected slots do not evaluate the checked shift. -/
theorem leaf_evaluation
    (el : evalGuard state leaf = .value (.word l))
    (ep : evalGuard state physical = .value (.word p))
    (em : evalGuard state mapping = .value (.word m))
    (eb : evalGuard state tableBase = .value (.word b))
    (es : evalGuard state slot = .value (.word s))
    (ex : evalGuard state limit = .value (.word x)) :
    evalGuard state (leafGuard leaf physical mapping tableBase slot limit) =
      .value (.boolean (leafNumeric l p m b s x)) := by
  have lit (n : Nat) (bound : n < wordLimit) :
      evalGuard state (.wordLit n) = .value (.word n) := by simp [evalGuard,readScalar,bound]
  have c1 := eval_compare_values (op := .eq)
    (eval_bitAnd_values el (lit 18442240474082185119 (by decide))) (lit 9223372036854775811 (by decide))
  have c2 := eval_compare_values (op := .eq)
    (eval_bitAnd_values el (lit 4503599627366400 (by decide))) ep
  have c3 := eval_compare_values (op := .ne) ep (lit 0 (by decide))
  have c4 := eval_compare_values (op := .lt) ep ex
  have c5 := eval_compare_values (op := .eq)
    (eval_bitAnd_values eb (lit 2097151 (by decide))) (lit 0 (by decide))
  have c6 := eval_compare_values (op := .lt) es (lit 512 (by decide))
  have before := eval_and_values (eval_and_values (eval_and_values (eval_and_values
    (eval_and_values c1 c2) c3) c4) c5) c6
  by_cases bound : s < 512
  · have wordBound := eval_word_bound slot es
    have shifted : s * 4096 < wordLimit := by unfold wordLimit; omega
    have shift : evalGuard state (.shift12 slot) = .value (.word (s * 4096)) := by
      simp [evalGuard,es,Outcome.then,binaryValue,wordBound,shifted]
    have last := eval_compare_values (op := .eq) em
      (eval_bitOr_values (eval_bitOr_values eb shift) (lit 3 (by decide)))
    simpa only [leafGuard,leafNumeric,compareWords] using eval_and_values before last
  · simp only [compareWords,decide_eq_false bound,Bool.and_false] at before
    simpa [leafGuard,leafNumeric,bound] using eval_and_false (b := .compare .eq mapping
      (.bitOr (.bitOr tableBase (.shift12 slot)) (.wordLit 3))) before
end Aurora.SourceBinding
