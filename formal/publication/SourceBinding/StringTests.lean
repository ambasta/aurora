import SourceBinding.MethodSyntax
namespace Aurora.SourceBinding
private def accepts (s : String) : Bool := (lex s.toUTF8).isSome
example : accepts "\"\"" = true := by decide
example : accepts "\"0123456789ABCDEF\"" = true := by decide
example : accepts "\"{//} class Fake {}\"" = true := by decide
example : accepts "\"unterminated" = false := by decide
example : accepts "\"a\\b\"" = false := by decide
example : accepts "\"a\nb\"" = false := by decide
example : accepts "\"é\"" = false := by decide
example : accepts "'a'" = false := by decide
example : accepts "\"a\rb\"" = false := by decide
example : accepts "\"a\tb\"" = false := by decide
example : (lex ⟨#[34,0,34]⟩).isSome = false := by decide
example : (lexOne "\"class\"".toUTF8 32 0).map (·.kind) = some .stringLiteral := by decide
example : ¬ Identifier "\"class\"".toUTF8 ⟨⟨0,7⟩,.stringLiteral⟩ := by decide
private def expressionAccepts (s : String) : Bool :=
  match lex s.toUTF8 with
  | none => false
  | some tokens => (expressionSyntax s.toUTF8 64 1 (significant tokens.reversed.reverse)).isSome
example : expressionAccepts "\"class\"" = false := by decide
end Aurora.SourceBinding
