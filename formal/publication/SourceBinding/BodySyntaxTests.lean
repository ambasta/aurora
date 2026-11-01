import SourceBinding.BodySyntax
open Aurora.SourceBinding
namespace BodySyntaxFixtures
-- Small native parser/type fixtures; no full-input kernel acceptance or effect proof.
example : TypedStatements [] [] .boolean [] .skip := .nil
example : TypedStatement [] [] .boolean (.returnValue (.boolean true)) (.returnValue .boolean (.boolLit true)) :=
  .returnValue .boolean
example : DefinitelyReturns (.seq (.branch (.boolLit true) (.returnValue .boolean (.boolLit false)))
    (.seq (.returnValue .boolean (.boolLit true)) .skip)) := .rest (.first .returnValue)
private def parsed (body : String) : Option EffectBody := do
  let input := ("module r; class C { u64 first; bool ready; u64 last; auto f(u64 p, bool b) -> bool { " ++ body ++ " } u64 following; };").toUTF8
  let file ← namedSource input
  let selected ← selectBody [⟨input,file⟩] ["r".toUTF8] ["r".toUTF8] ["C".toUTF8] "f".toUTF8
  return selected.method.body

#eval do
  let cases : List (String × Bool) := [
    ("return true;",true),
    ("following = p; return true;",true),
    ("first = p; last = 1u64; ready = b; return true;",true),
    ("builtin::require(ready && !b); if (b) { last = 2u64; } return true;",true),
    ("if (b) { return false; } return true;",true),
    ("if (b) { return true; }",false),
    ("first = p;",false),
    ("p = 1u64; return true;",false),
    ("missing = 1u64; return true;",false),
    ("first = true; return true;",false),
    ("ready = 1u64; return true;",false),
    ("first = other(); return true;",false),
    ("first = p return true;",false),
    ("first == p; return true;",false),
    ("this.first = p; return true;",false),
    ("C::first = p; return true;",false),
    ("builtin::require(p); return true;",false),
    ("builtin::require(); return true;",false),
    ("builtin::require(true,false); return true;",false),
    ("builtin::require(other()); return true;",false),
    ("require(true); return true;",false),
    ("other::require(true); return true;",false),
    ("ready.require(true); return true;",false),
    ("other(); return true;",false),
    ("return 1u64;",false),
    ("return true; other();",false)]
  for (body, expected) in cases do
    unless (parsed body).isSome == expected do throw (IO.userError s!"body test failed: {body}")
  match parsed "last = p; return true;" with
  | some (.seq (.assign .word 2 (.parameter .word _ 0)) _) => pure ()
  | _ => throw (IO.userError "field ordinal/formal index changed")
  IO.println s!"body syntax/type fixtures: {cases.length+1} passed"
end BodySyntaxFixtures
