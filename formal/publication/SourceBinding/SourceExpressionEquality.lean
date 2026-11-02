import SourceBinding.Expressions
namespace Aurora.SourceBinding
/- Constructive equality for the existing raw expression tree, including nested
   argument lists. Used only for finite environment ambiguity checks. -/
mutual
  def sourceExpressionDecidableEq (left right : SourceExpr) : Decidable (left = right) :=
    match left, right with
    | .signed12, .signed12 => .isTrue rfl
    | .signedCount a, .signedCount b =>
      if same : a = b then .isTrue (by cases same; rfl) else .isFalse (fun equal => same (SourceExpr.signedCount.inj equal))
    | .word a, .word b =>
      if same : a = b then .isTrue (by cases same; rfl) else .isFalse (fun equal => same (SourceExpr.word.inj equal))
    | .boolean a, .boolean b =>
      if same : a = b then .isTrue (by cases same; rfl) else .isFalse (fun equal => same (SourceExpr.boolean.inj equal))
    | .name a, .name b =>
      if same : a = b then .isTrue (by cases same; rfl) else .isFalse (fun equal => same (SourceExpr.name.inj equal))
    | .call a xs, .call b ys =>
      if ab : a = b then
        match sourceExpressionsDecidableEq xs ys with
        | .isTrue same => .isTrue (by cases ab; cases same; rfl)
        | .isFalse different => .isFalse (fun same => different (SourceExpr.call.inj same).2)
      else .isFalse (fun same => ab (SourceExpr.call.inj same).1)
    | .not a, .not b =>
      match sourceExpressionDecidableEq a b with
      | .isTrue same => .isTrue (by cases same; rfl)
      | .isFalse different => .isFalse (fun same => different (SourceExpr.not.inj same))
    | .binary a b c, .binary d e f =>
      if ad : a = d then
        match sourceExpressionDecidableEq b e, sourceExpressionDecidableEq c f with
        | .isTrue be, .isTrue cf => .isTrue (by cases ad; cases be; cases cf; rfl)
        | .isFalse different, _ => .isFalse (fun same => different (SourceExpr.binary.inj same).2.1)
        | _, .isFalse different => .isFalse (fun same => different (SourceExpr.binary.inj same).2.2)
      else .isFalse (fun same => ad (SourceExpr.binary.inj same).1)
    | .signed12 .., .signedCount .. | .signed12 .., .word .. | .signed12 .., .boolean .. | .signed12 .., .name .. | .signed12 .., .call .. | .signed12 .., .not .. | .signed12 .., .binary ..
    | .signedCount .., .signed12 .. | .signedCount .., .word .. | .signedCount .., .boolean .. | .signedCount .., .name .. | .signedCount .., .call .. | .signedCount .., .not .. | .signedCount .., .binary ..
    | .word .., .signed12 .. | .word .., .signedCount .. | .word .., .boolean .. | .word .., .name .. | .word .., .call .. | .word .., .not .. | .word .., .binary ..
    | .boolean .., .signed12 .. | .boolean .., .signedCount .. | .boolean .., .word .. | .boolean .., .name .. | .boolean .., .call .. | .boolean .., .not .. | .boolean .., .binary ..
    | .name .., .signed12 .. | .name .., .signedCount .. | .name .., .word .. | .name .., .boolean .. | .name .., .call .. | .name .., .not .. | .name .., .binary ..
    | .call .., .signed12 .. | .call .., .signedCount .. | .call .., .word .. | .call .., .boolean .. | .call .., .name .. | .call .., .not .. | .call .., .binary ..
    | .not .., .signed12 .. | .not .., .signedCount .. | .not .., .word .. | .not .., .boolean .. | .not .., .name .. | .not .., .call .. | .not .., .binary ..
    | .binary .., .signed12 .. | .binary .., .signedCount .. | .binary .., .word .. | .binary .., .boolean .. | .binary .., .name .. | .binary .., .call .. | .binary .., .not .. => .isFalse (by intro same; cases same)
  termination_by sizeOf left
  def sourceExpressionsDecidableEq (left right : List SourceExpr) : Decidable (left = right) :=
    match left, right with
    | [], [] => .isTrue rfl
    | first :: rest, other :: tail =>
      match sourceExpressionDecidableEq first other, sourceExpressionsDecidableEq rest tail with
      | .isTrue same, .isTrue remaining => .isTrue (by cases same; cases remaining; rfl)
      | .isFalse different, _ => .isFalse (fun same => different (List.cons.inj same).1)
      | _, .isFalse different => .isFalse (fun same => different (List.cons.inj same).2)
    | [], _ :: _ | _ :: _, [] => .isFalse (by intro same; cases same)
  termination_by sizeOf left
end
instance : DecidableEq SourceExpr := sourceExpressionDecidableEq
end Aurora.SourceBinding
