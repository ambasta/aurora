import SourceBinding.MethodSyntax
open Aurora.SourceBinding

-- Small kernel checks of independent typing/operator rules, never a complete file reduction.
example : precedence (.compare .eq) < precedence .subtract := by decide
example : precedence .or < precedence .and := by decide
example : TypedGuard [] [] (.word 1) (.wordLit 1) := .word (by decide)
example : TypedGuard [] [] (.not (.boolean false)) (.not (.boolLit false)) := .not .boolean

private def sourceFile (text : String) : Option SourceFile := do
  let checked ← namedSource text.toUTF8
  return ⟨text.toUTF8,checked⟩
private def wrap (body : String) : String :=
  "module r; class C { u64 left; u64 right; bool ready; auto f(u64 p) -> bool { " ++ body ++ " } };"
private def parseGuard (body : String) : Option (GuardExpr .boolean) := do
  let file ← sourceFile (wrap body)
  let selected ← selectGuard [file] ["r".toUTF8] ["r".toUTF8] ["C".toUTF8] "f".toUTF8
  return selected.method.guard

private def bodyCases : List (String × Bool) := [
  ("if (left != 1u64 || p > right || p > right - left) { return false; } next(); return true;",true),
  ("if (left) { return false; } next(); return true;",false),
  ("if (missing != 0u64) { return false; } next(); return true;",false),
  ("if (ready) { return false; } next(); return true;",true),
  ("if (!ready && left < p) { return false; } next(); return true;",true),
  ("if (left || ready) { return false; } next(); return true;",false),
  ("if (left != p != right) { return false; } next(); return true;",false),
  ("if (left - p > right) { return false; } next(); return true;",true),
  ("if (other()) { return false; } next(); return true;",false),
  ("if (left == 0u64) { return true; } next(); return true;",false),
  ("if (left == 0u64) { return false; }",false),
  ("before(); if (left == 0u64) { return false; } next(); return true;",false),
  ("if (left == 0u64) { return false; } next(); while (true) {}",false),
  ("if (left == 0u64) { return false; } next(); return true; garbage",false),
  ("if (left == 0u64) { return false; } next(,); return true;",false),
  ("if (left == 0u64) { return false; } next(1u64,); return true;",false),
  ("if (left == 0u64) { return false; } builtin::require(authority.fill_chunk(p, left, 0u64, right)); return true;",true),
  ("if (left == 0u64) { return false; } unknown_tail_signature(); return true;",true)]

#eval do
  for (body, expected) in bodyCases do
    unless (parseGuard body).isSome == expected do throw (IO.userError s!"method fixture failed: {body}")
  let some first := parseGuard "if (left != p || right > p && left != 0u64) { return false; } next(); return true;" |
    throw (IO.userError "precedence source rejected")
  match first with
  | .or (.compare .ne _ _) (.and (.compare .gt _ _) (.compare .ne _ _)) => pure ()
  | _ => throw (IO.userError "precedence changed")
  let some second := parseGuard "if (left - p - right > 0u64) { return false; } next(); return true;" |
    throw (IO.userError "association source rejected")
  match second with
  | .compare .gt (.sub (.sub _ _) _) (.wordLit 0) => pure ()
  | _ => throw (IO.userError "subtraction association changed")
  IO.println s!"NATIVE method/guard fixtures: {bodyCases.length + 2} passed"

