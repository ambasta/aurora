import SourceBinding.Lexer
namespace Aurora.SourceBinding

/-- Text predicates use exact source byte slices, never a normalized copy. -/
def Is (input : ByteArray) (token : Lexeme) (text : String) : Prop :=
  spelling input token = text.toUTF8
instance (input : ByteArray) (token : Lexeme) (text : String) : Decidable (Is input token text) := by
  unfold Is; infer_instance

/-- Reserved spellings cannot become declaration names in the supported shell. -/
def reserved : List String := ["module", "import", "export", "namespace", "class", "enum", "auto",
  "const", "public", "private", "protected", "if", "else", "return", "while", "for", "true", "false",
  "using", "template", "static", "extern", "struct", "virtual", "override", "friend", "union", "typedef"]
def Identifier (input : ByteArray) (token : Lexeme) : Prop :=
  token.kind = .identifier ∧ ∀ keyword ∈ reserved, ¬ Is input token keyword
instance (input : ByteArray) (token : Lexeme) : Decidable (Identifier input token) := by
  unfold Identifier; infer_instance

abbrev Name := List ByteArray

/-- Finite membership uses propositional equality, not an unaudited BEq assumption. -/
def memberDecision {α : Type} [DecidableEq α] (value : α) : (xs : List α) → Decidable (value ∈ xs)
  | [] => isFalse (by simp)
  | head :: tail =>
    if equal : value = head then isTrue (List.mem_cons.mpr (Or.inl equal))
    else match memberDecision value tail with
      | isTrue member => isTrue (List.mem_cons.mpr (Or.inr member))
      | isFalse absent => isFalse (fun member => (List.mem_cons.mp member).elim equal absent)
instance (value : ByteArray) (xs : List ByteArray) : Decidable (value ∈ xs) := memberDecision value xs
instance (value : Name) (xs : List Name) : Decidable (value ∈ xs) := memberDecision value xs

/-- Name grammar consumes an explicit token prefix. The unconsumed remaining is retained. -/
inductive Qualified (input : ByteArray) (separator : String) : List Lexeme → Name → List Lexeme → Prop
  | last : Identifier input token → (∀ next ∈ rest.head?, ¬ Is input next separator) →
      Qualified input separator (token :: rest) [spelling input token] rest
  | more : Identifier input token → Is input dot separator → Qualified input separator rest names remaining →
      Qualified input separator (token :: dot :: rest) (spelling input token :: names) remaining

structure ParsedName (input : ByteArray) (separator : String) (tokens : List Lexeme) where
  name : Name
  rest : List Lexeme
  grammar : Qualified input separator tokens name rest

def qualified (input : ByteArray) (separator : String) :
    (fuel : Nat) → (tokens : List Lexeme) → Option (ParsedName input separator tokens)
  | 0, _ => none
  | fuel + 1, tokens => match tokens with
    | [] => none
    | token :: rest =>
      if ident : Identifier input token then
        match rest with
        | [] => some ⟨[spelling input token], [], .last ident (by simp)⟩
        | next :: tail =>
          if dot : Is input next separator then do
            let parsed ← qualified input separator fuel tail
            return ⟨spelling input token :: parsed.name, parsed.rest, .more ident dot parsed.grammar⟩
          else some ⟨[spelling input token], next :: tail, .last ident (by simpa using dot)⟩
      else none

inductive ModuleDecl (input : ByteArray) : List Lexeme → Bool → Name → List Lexeme → Prop
  | plain : Is input keyword "module" → Qualified input "." rest name (semicolon :: tail) →
      Is input semicolon ";" → ModuleDecl input (keyword :: rest) false name tail
  | exported : Is input keyword "export" → ModuleDecl input rest false name tail →
      ModuleDecl input (keyword :: rest) true name tail

structure ParsedModule (input : ByteArray) (tokens : List Lexeme) where
  exported : Bool
  name : Name
  rest : List Lexeme
  grammar : ModuleDecl input tokens exported name rest

def modulePlain (input : ByteArray) (tokens : List Lexeme) : Option (ParsedModule input tokens) := do
  let keyword :: rest := tokens | none
  if word : Is input keyword "module" then
    let parsed ← qualified input "." 64 rest
    match eq : parsed.rest with
    | semicolon :: tail =>
      if semi : Is input semicolon ";" then
        return ⟨false, parsed.name, tail, .plain word (eq ▸ parsed.grammar) semi⟩
      else none
    | [] => none
  else none

def moduleDecl (input : ByteArray) (tokens : List Lexeme) : Option (ParsedModule input tokens) := do
  match tokens with
  | [] => none
  | token :: rest =>
    if exported : Is input token "export" then
      let parsed ← modulePlain input rest
      if plain : parsed.exported = false then
        return ⟨true, parsed.name, parsed.rest, .exported exported (plain ▸ parsed.grammar)⟩
      else none
    else modulePlain input (token :: rest)

/-- All leading imports are consumed; malformed imports cannot terminate the list. -/
inductive Imports (input : ByteArray) : List Lexeme → List Name → List Lexeme → Prop
  | end : (∀ token ∈ rest.head?, ¬ Is input token "import") → Imports input rest [] rest
  | next : Is input keyword "import" → Qualified input "." rest name (semicolon :: tail) →
      Is input semicolon ";" → Imports input tail names remaining →
      Imports input (keyword :: rest) (name :: names) remaining

structure ParsedImports (input : ByteArray) (tokens : List Lexeme) where
  names : List Name
  rest : List Lexeme
  grammar : Imports input tokens names rest

def imports (input : ByteArray) : (fuel : Nat) → (tokens : List Lexeme) → Option (ParsedImports input tokens)
  | 0, _ => none
  | fuel + 1, tokens => match tokens with
    | [] => some ⟨[], [], .end (by simp)⟩
    | keyword :: rest =>
      if word : Is input keyword "import" then do
        let parsed ← qualified input "." 64 rest
        match eq : parsed.rest with
        | [] => none
        | semicolon :: tail =>
          if semi : Is input semicolon ";" then
            let remaining ← imports input fuel tail
            return ⟨parsed.name :: remaining.names, remaining.rest,
              .next word (eq ▸ parsed.grammar) semi remaining.grammar⟩
          else none
      else some ⟨[], keyword :: rest, .end (by simpa using word)⟩

structure Header (input : ByteArray) (tokens : List Lexeme) where
  module : ParsedModule input tokens
  imports : ParsedImports input module.rest

def header (input : ByteArray) (tokens : List Lexeme) : Option (Header input tokens) := do
  let m ← moduleDecl input tokens
  let i ← imports input 256 m.rest
  return ⟨m, i⟩

structure HeaderSource (input : ByteArray) where
  lexical : Lexed input
  declarations : Header input (significant lexical.reversed.reverse)

def headerSource (input : ByteArray) : Option (HeaderSource input) := do
  let lexical ← lex input
  let declarations ← header input (significant lexical.reversed.reverse)
  return ⟨lexical, declarations⟩

theorem module_sound (input : ByteArray) (tokens : List Lexeme) (result : ParsedModule input tokens)
    (_accepted : moduleDecl input tokens = some result) :
    ModuleDecl input tokens result.exported result.name result.rest := result.grammar

theorem imports_sound (input : ByteArray) (tokens : List Lexeme) (fuel : Nat)
    (result : ParsedImports input tokens) (_accepted : imports input fuel tokens = some result) :
    Imports input tokens result.names result.rest := result.grammar

/-- Prefix binding only: remaining declaration tokens are explicitly not yet admitted. -/
theorem header_source_coverage (input : ByteArray) (result : HeaderSource input)
    (_accepted : headerSource input = some result) :
    Coverage input result.lexical.reversed input.size := result.lexical.grammar

/-- Composed raw-byte/header endpoint. The unparsed remaining tokens stay visible. -/
theorem header_source_sound (input : ByteArray) (result : HeaderSource input)
    (_accepted : headerSource input = some result) :
    Coverage input result.lexical.reversed input.size ∧
    ModuleDecl input (significant result.lexical.reversed.reverse)
      result.declarations.module.exported result.declarations.module.name result.declarations.module.rest ∧
    Imports input result.declarations.module.rest result.declarations.imports.names
      result.declarations.imports.rest :=
  ⟨result.lexical.grammar, result.declarations.module.grammar, result.declarations.imports.grammar⟩

end Aurora.SourceBinding
