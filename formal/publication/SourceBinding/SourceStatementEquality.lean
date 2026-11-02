import SourceBinding.MethodSyntax
import SourceBinding.SourceExpressionEquality
namespace Aurora.SourceBinding
/- Constructive equality on the existing raw statements, used only for finite
   source-environment compatibility. No evaluator or new statement AST. -/
mutual
def sourceStatementDecidableEq (left right : SourceStatement) : Decidable (left = right) :=
  match left,right with
  | .ifThen a xs,.ifThen b ys =>
    if same : a = b then
      match sourceStatementsDecidableEq xs ys with
      | .isTrue rest => .isTrue (by cases same; cases rest; rfl)
      | .isFalse different => .isFalse (fun equal => different (SourceStatement.ifThen.inj equal).2)
    else .isFalse (fun equal => same (SourceStatement.ifThen.inj equal).1)
  | .returnValue a,.returnValue b =>
    if same : a = b then .isTrue (by cases same; rfl)
    else .isFalse (fun equal => same (SourceStatement.returnValue.inj equal))
  | .call a x,.call b y =>
    if same : a = b then
      if rest : x = y then .isTrue (by cases same; cases rest; rfl)
      else .isFalse (fun equal => rest (SourceStatement.call.inj equal).2)
    else .isFalse (fun equal => same (SourceStatement.call.inj equal).1)
  | .localDecl a x,.localDecl b y =>
    if same : a = b then
      if rest : x = y then .isTrue (by cases same; cases rest; rfl)
      else .isFalse (fun equal => rest (SourceStatement.localDecl.inj equal).2)
    else .isFalse (fun equal => same (SourceStatement.localDecl.inj equal).1)
  | .assign a x,.assign b y =>
    if same : a = b then
      if rest : x = y then .isTrue (by cases same; cases rest; rfl)
      else .isFalse (fun equal => rest (SourceStatement.assign.inj equal).2)
    else .isFalse (fun equal => same (SourceStatement.assign.inj equal).1)
  | .ifThen ..,.returnValue .. | .ifThen ..,.call .. | .ifThen ..,.localDecl .. | .ifThen ..,.assign .. | .returnValue ..,.ifThen .. | .returnValue ..,.call .. | .returnValue ..,.localDecl .. | .returnValue ..,.assign .. | .call ..,.ifThen .. | .call ..,.returnValue .. | .call ..,.localDecl .. | .call ..,.assign .. | .localDecl ..,.ifThen .. | .localDecl ..,.returnValue .. | .localDecl ..,.call .. | .localDecl ..,.assign .. | .assign ..,.ifThen .. | .assign ..,.returnValue .. | .assign ..,.call .. | .assign ..,.localDecl .. => .isFalse (by intro same; cases same)
  termination_by sizeOf left

def sourceStatementsDecidableEq (left right : List SourceStatement) : Decidable (left = right) :=
  match left,right with
  | [],[] => .isTrue rfl
  | first::rest,other::tail =>
    match sourceStatementDecidableEq first other,sourceStatementsDecidableEq rest tail with
    | .isTrue same,.isTrue remaining => .isTrue (by cases same; cases remaining; rfl)
    | .isFalse different,_ => .isFalse (fun same => different (List.cons.inj same).1)
    | _,.isFalse different => .isFalse (fun same => different (List.cons.inj same).2)
  | [],_::_ | _::_,[] => .isFalse (by intro same; cases same)
  termination_by sizeOf left
end
instance : DecidableEq SourceStatement := sourceStatementDecidableEq
end Aurora.SourceBinding
