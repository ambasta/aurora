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
  ("module root; \"class Forged {}\"", false),
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
