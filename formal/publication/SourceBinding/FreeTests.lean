import SourceBinding.FreeIdentity
namespace Aurora.SourceBinding
private def file (text : String) : Option SourceFile := do
  let checked ← namedSource text.toUTF8
  return ⟨text.toUTF8,checked⟩
private def selected (text : String) (path : Name) : Bool :=
  match file text with
  | none => false
  | some source => (checkFreeSelection [source] ["r".toUTF8] ["r".toUTF8] path "f".toUTF8).isSome
/- Native parser controls, not kernel-certified concrete source acceptance. -/
#eval do
  let cases := [
    ("module r; auto f() -> bool { return true; }", [], true),
    ("module r; export namespace n { auto f() -> bool { return true; } }", ["n".toUTF8], true),
    ("module r; class n { auto f() -> bool { return true; } }", ["n".toUTF8], false),
    ("module r; auto g() -> bool { auto f() -> bool { return true; } }", [], false)]
  for (text,path,expected) in cases do
    unless selected text path == expected do
      throw (IO.userError "free source selection control failed")
example : freeSymbol ["r".toUTF8] ["r".toUTF8] [] "f".toUTF8 = "f".toUTF8 := by decide
example : freeSymbol ["r".toUTF8] ["m".toUTF8] ["n".toUTF8] "f".toUTF8 =
    "__au_f_m1_1m_n1_1n_d1f".toUTF8 := by decide
end Aurora.SourceBinding
