import SourceBinding
open Aurora.SourceBinding

/-- Native fixtures: these are not concrete kernel acceptance theorems. -/
def cases : List (String × Bool) := [
  ("module root;", true),
  ("export module a.b; import c.d; class X {}", true),
  ("// export module forged;\nmodule real;", true),
  ("module real; // class Forged {}", true),
  ("\r\n\tmodule root;\r\n", true),
  ("module root; /* class Forged {} */", false),
  ("module root; \"class Forged {}\"", true),
  ("module root; '\\n'", false),
  ("module r; // nonascii: é", false),
  ("module r; #define x", false),
  ("module;", false),
  ("module a.;", false),
  ("module module;", false),
  ("export export module root;", false),
  ("module root; import a.", false),
  ("module root; import;", false),
  ("module root; 18446744073709551615u64", true),
  ("module root; 18446744073709551616u64", false),
  ("module root; 256u8", false),
  ("module root; 10u64bad", false),
  ("module root; 00", false)]

#eval do
  for (text, expected) in cases do
    unless (headerSource text.toUTF8).isSome == expected do
      throw (IO.userError s!"header fixture failed: {text}")
  let pairs : List (String × List String) := [("a::b && c!=2u64", ["a","::","b","&&","c","!=","2u64"]),
    ("a: :b & & c! =2u64", ["a",":",":","b","&","&","c","!","=","2u64"]),
    ("//module forged;", [])]
  for (text, expected) in pairs do
    let got := (lex text.toUTF8).map fun (r : Lexed text.toUTF8) =>
      (significant r.reversed.reverse).map (spelling text.toUTF8)
    unless got == some (expected.map String.toUTF8) do
      throw (IO.userError s!"token fixture failed: {text}")
  unless (lex "abcdef".toUTF8 100 2).isNone do
    throw (IO.userError "token exhaustion accepted")
  IO.println s!"NATIVE source fixtures: {cases.length + pairs.length + 1} passed"

/-- Complete shell/duplicate controls, still native execution rather than kernel acceptance. -/
def shellCases : List (String × Bool) := [
  ("module r; class C { u64 before; auto f(u64 x) -> bool { return x == 0u64; } u64 after; };", true),
  ("module r; class C { u64 x; u64 x; };", false),
  ("module r; class C { auto f() -> bool { return true; } auto f() -> bool { return false; } };", false),
  ("module r; class C { u64 x; auto f(u64 x) -> bool { return true; } };", false),
  ("module r; class C { auto f(u64 a, u64 a) -> bool { return true; } };", false),
  ("module r; class C { u64 x; C(u64 a) : x(a) {} };", true),
  ("module r; class C { u64 x; C(u64 a) : missing(a) {} };", false),
  ("module r; class C { u64 x; C(u64 a) : x(a), x(a) {} };", false),
  ("module r; class C { u64 x; C(u64 a) : x(move(a)) {} };", true),
  ("module r; class C { u64 x; D(u64 a) : x(a) {} };", false),
  ("module r; module forged;", false),
  ("module r; class C {}; import late;", false),
  ("module r; class C {}; class C {};", false),
  ("module r; namespace a {} namespace a {}", false),
  ("module r; namespace builtin {}", false),
  ("module r; class u64 {};", false),
  ("module r; using X = u64;", false),
  ("module r; template<class T> class C {};", false),
  ("module r; auto f() const -> bool { return true; }", false),
  ("module r; class C { auto f() const -> bool { return true; } };", true),
  ("module r; class C { auto f() && -> bool { return true; } };", true),
  ("module r; auto f(builtin::span<const u8> x) -> bool { return true; }", true),
  ("module r; class C { auto f() -> bool { (] } };", false),
  ("module r; class C { auto f() -> bool { // } class Fake {\nreturn true; } };", true),
  ("module r; class C { auto f() -> bool { \"} class Fake {\" } };", true),
  ("module r; class C { u64 x; C(u64 a) : x(a } };", false),
  ("module r; enum class E { a, b };", true),
  ("module r; enum class E { a, a };", false)]

def sourceFile (text : String) : Option SourceFile := do
  let source ← namedSource text.toUTF8
  return ⟨text.toUTF8,source⟩

#eval do
  for (text, expected) in shellCases do
    unless (namedSource text.toUTF8).isSome == expected do
      throw (IO.userError s!"shell fixture failed: {text}")
  let graphCases : List (List String × Bool) := [
    (["module r; import a;", "export module a;"], true),
    (["module r; import missing;"], false),
    (["module r;", "module r;"], false),
    (["module r;", "module extra;"], false),
    (["module r; import a; import a;", "module a;"], false),
    (["module r; import a;", "module a; import r;"], true),
    (["module r; import a; namespace n { class C {}; }", "module a; namespace n { class C {}; }"], false),
    (["module r; import a; namespace N { class X {}; }", "module a; class N {};"], false),
    (["module r; import a; namespace N {}", "module a; auto N() -> bool { return true; }"], false),
    (["module r; import a; namespace N { namespace X {} }", "module a; namespace N { class X {}; }"], false),
    (["module r; import a; namespace N { class X {}; }", "module a; namespace N { class Y {}; }"], true)]
  for (texts, expected) in graphCases do
    let some files := texts.mapM sourceFile | throw (IO.userError "graph fixture shell rejected")
    unless (checkGraph files ["r".toUTF8]).isSome == expected do
      throw (IO.userError "graph fixture failed")
  let text := "module r; namespace n { class C { u64 first; auto f() -> bool { return true; } u64 last; }; }"
  let some file := sourceFile text | throw (IO.userError "selection source rejected")
  let some checked := checkedSelection [file] ["r".toUTF8] ["r".toUTF8] ["n".toUTF8,"C".toUTF8] "f".toUTF8 |
    throw (IO.userError "selection failed")
  let selected := checked.selected
  unless (checkedSelection [file,file] ["r".toUTF8] ["r".toUTF8] ["n".toUTF8,"C".toUTF8] "f".toUTF8).isNone do
    throw (IO.userError "ambiguous module selection accepted")
  let some first := fieldAt selected.classDecl.members "first".toUTF8 | throw (IO.userError "first field lost")
  let some last := fieldAt selected.classDecl.members "last".toUTF8 | throw (IO.userError "later field lost")
  unless first.ordinal == 0 && last.ordinal == 1 do throw (IO.userError "field order changed")
  IO.println s!"NATIVE shell/graph/selection fixtures: {shellCases.length + graphCases.length + 2} passed"
