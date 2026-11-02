import SourceBinding.FreeSelection
import SourceBinding.LocalBinding
namespace Aurora.SourceBinding

private def fixture (profile : ScopeProfile) (body : String) : Option (List SourceLocal × LocalContext) := do
  let text := "module r; namespace n { auto f(u64 input) -> u64 { " ++ body ++ " } }"
  let checked ← namedSource text.toUTF8
  let source : SourceFile := ⟨text.toUTF8,checked⟩
  let selected ← checkFreeSelection [source] ["r".toUTF8] ["r".toUTF8] ["n".toUTF8] "f".toUTF8
  let parsed ← methodSyntax text.toUTF8 selected.function.function
  let members := selected.scope.members
  let formals := selected.function.function.formals
  let result ← scopeStatementsWith profile
    (fun cursor raw => ExpressionNames members ["n".toUTF8] formals cursor.visible raw)
    (fun _ _ => False)
    (fun cursor raw => checkExpressionNames members ["n".toUTF8] formals cursor.visible 4096 raw)
    (fun _ _ => none) members ["r".toUTF8] ["n".toUTF8] formals 4096
    ⟨[],0,1,formals.length⟩ parsed.statements
  return (result.declaredItems,result.after)

/- Native parser/scoper fixtures, not actual receiver binding or concrete kernel
   certification. Name checking here is exactly the old local-only checker. -/
#eval do
  let cases := [
    ("if (true) {} else {} return input;",true),
    ("if (true) { if (false) {} else {} } else {} return input;",true),
    ("if (true) {} else return input;",false),
    ("if (true) {} else { return input;",false),
    ("if (true) {} else",false),
    ("if (true) {} else {} else {} return input;",false),
    ("if (true) { u64 x = input; } else { u64 x = input; } return input;",true),
    ("if (true) { u64 x = input; } else {} return x;",false),
    ("if (true) {} else { return missing; } return input;",false)]
  for (body,expected) in cases do
    unless (fixture .receiverEffects body).isSome == expected do
      throw (IO.userError s!"ifElse source scope control failed: {body}")
  for body in ["if (true) {} else {} return input;",
      "return input; if (true) {} else {}",
      "if (false) { if (true) {} else {} } return input;"] do
    unless (fixture .legacy body).isNone do
      throw (IO.userError "legacy admitted ifElse in executed/dead syntax")
  let some (items,after) := fixture .receiverEffects
    "if (true) { u64 x = input; } else { const u64 y = input; } return input;"
    | throw (IO.userError "two-arm inventory fixture rejected")
  unless items.map (fun (x : SourceLocal) => x.slot) == [16,24] &&
      items.map (fun (x : SourceLocal) => x.scope) == [1,2] && after.nextScope == 3 &&
      after.nextSlot == 3 && after.visible.isEmpty do
    throw (IO.userError "ifElse did not reserve both static arms")

example : ¬ ScopedStatement members module path formals before (.ifElse condition yes no) after items := by
  intro proof
  cases proof with
  | branchElse enabled => cases enabled

example : ¬ ScopedStatements members module path formals before
    [.returnValue value,.ifElse condition yes no] after items := by
  intro proof
  cases proof with
  | cons first rest =>
    cases rest with
    | cons impossible tail =>
      cases impossible with
      | branchElse enabled => cases enabled

end Aurora.SourceBinding
