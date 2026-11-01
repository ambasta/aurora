import SourceBinding.Callables
namespace Aurora.SourceBinding

inductive Scope where
  | outer | classBody (owner : ByteArray)
  deriving BEq, DecidableEq

inductive Declaration where
  | namespaceDecl (name : ByteArray) (exported : Bool) (declarations : List Declaration)
  | classDecl (name : ByteArray) (members : List Declaration)
  | enumDecl (name : ByteArray) (cases : List ByteArray)
  | functionDecl (function : Function)
  | constructorDecl (constructor : Constructor)
  | fieldDecl (field : Formal)
  | access (visibility : String)
  deriving BEq

inductive EnumCases (input : ByteArray) : List Lexeme → List ByteArray → List Lexeme → Prop
  | last : Identifier input name → Is input closing "}" →
      EnumCases input (name :: closing :: rest) [spelling input name] rest
  | more : Identifier input name → Is input comma "," → EnumCases input tokens names rest →
      EnumCases input (name :: comma :: tokens) (spelling input name :: names) rest

structure ParsedCases (input : ByteArray) (tokens : List Lexeme) where
  names : List ByteArray
  rest : List Lexeme
  grammar : EnumCases input tokens names rest

def enumCases (input : ByteArray) : (fuel : Nat) → (tokens : List Lexeme) → Option (ParsedCases input tokens)
  | 0, _ => none
  | fuel + 1, tokens => do
    let name :: separator :: tail := tokens | none
    if ident : Identifier input name then
      if close : Is input separator "}" then
        return ⟨[spelling input name],tail,.last ident close⟩
      else if comma : Is input separator "," then
        let others ← enumCases input fuel tail
        return ⟨spelling input name :: others.names,others.rest,.more ident comma others.grammar⟩
      else none
    else none

mutual
  inductive DeclarationSyntax (input : ByteArray) : Scope → List Lexeme → Declaration → List Lexeme → Prop
    | namespaceDecl : Is input keyword "namespace" → Identifier input name → Is input opening "{" →
        Declarations input .outer true tokens declarations (closing :: rest) → Is input closing "}" →
        DeclarationSyntax input .outer (keyword :: name :: opening :: tokens)
          (.namespaceDecl (spelling input name) false declarations) rest
    | exportedNamespace : Is input keyword "export" →
        DeclarationSyntax input .outer tokens (.namespaceDecl name false declarations) rest →
        DeclarationSyntax input .outer (keyword :: tokens) (.namespaceDecl name true declarations) rest
    | classDecl : Is input keyword "class" → Identifier input name → Is input opening "{" →
        Declarations input (.classBody (spelling input name)) true tokens members (closing :: semicolon :: rest) →
        Is input closing "}" → Is input semicolon ";" →
        DeclarationSyntax input .outer (keyword :: name :: opening :: tokens)
          (.classDecl (spelling input name) members) rest
    | enumDecl : Is input keyword "enum" → Is input cls "class" → Identifier input name → Is input opening "{" →
        EnumCases input tokens names (semicolon :: rest) → Is input semicolon ";" →
        DeclarationSyntax input .outer (keyword :: cls :: name :: opening :: tokens)
          (.enumDecl (spelling input name) names) rest
    | functionDecl : FunctionSyntax input tokens function rest →
        (scope = .outer → function.mode = .ordinary) →
        DeclarationSyntax input scope tokens (.functionDecl function) rest
    | constructorDecl : ConstructorSyntax input owner tokens constructor rest →
        DeclarationSyntax input (.classBody owner) tokens (.constructorDecl constructor) rest
    | fieldDecl : FormalSyntax input tokens field (semicolon :: rest) → Is input semicolon ";" →
        DeclarationSyntax input (.classBody owner) tokens (.fieldDecl field) rest
    | access : visibility ∈ (["public","private","protected"] : List String) →
        Is input keyword visibility → Is input colon ":" →
        DeclarationSyntax input (.classBody owner) (keyword :: colon :: rest) (.access visibility) rest
  inductive Declarations (input : ByteArray) : Scope → Bool → List Lexeme → List Declaration → List Lexeme → Prop
    | eof : Declarations input scope false [] [] []
    | closing : Is input close "}" → Declarations input scope true (close :: rest) [] (close :: rest)
    | next : DeclarationSyntax input scope tokens declaration after →
        Declarations input scope nested after declarations rest →
        Declarations input scope nested tokens (declaration :: declarations) rest
end

structure ParsedDeclaration (input : ByteArray) (scope : Scope) (tokens : List Lexeme) where
  declaration : Declaration
  rest : List Lexeme
  grammar : DeclarationSyntax input scope tokens declaration rest

structure ParsedDeclarations (input : ByteArray) (scope : Scope) (nested : Bool) (tokens : List Lexeme) where
  declarations : List Declaration
  rest : List Lexeme
  grammar : Declarations input scope nested tokens declarations rest

mutual
  def declarations (input : ByteArray) : (fuel : Nat) → (scope : Scope) → (nested : Bool) →
      (tokens : List Lexeme) → Option (ParsedDeclarations input scope nested tokens)
    | 0, _, _, _ => none
    | fuel + 1, scope, nested, tokens => match tokens with
      | [] =>
        if top : nested = false then some ⟨[],[],top ▸ .eof⟩ else none
      | token :: tail => do
        if closing : Is input token "}" then
          if inside : nested = true then
            return ⟨[],token :: tail,inside ▸ .closing closing⟩
          else none
        else
          let first ← declaration input fuel scope (token :: tail)
          let others ← declarations input fuel scope nested first.rest
          return ⟨first.declaration :: others.declarations,others.rest,.next first.grammar others.grammar⟩
  def declaration (input : ByteArray) : (fuel : Nat) → (scope : Scope) →
      (tokens : List Lexeme) → Option (ParsedDeclaration input scope tokens)
    | 0, _, _ => none
    | fuel + 1, scope, tokens => match tokens with
      | [] => none
      | token :: tail => do
        if Is input token "auto" then
          let result ← functionSyntax input (token :: tail)
          if receiver : scope = .outer → result.function.mode = .ordinary then
            return ⟨.functionDecl result.function,result.rest,.functionDecl result.grammar receiver⟩
          else none
        else match scope with
        | .classBody owner =>
          let visibility := if Is input token "public" then "public" else if Is input token "private" then "private" else "protected"
          if access : Is input token visibility then
            let colon :: remaining := tail | none
            if separator : Is input colon ":" then
              if allowed : visibility ∈ (["public","private","protected"] : List String) then
                return ⟨.access visibility,remaining,.access allowed access separator⟩
              else none
            else none
          else
            let isConstructor := spelling input token == owner &&
              (match tail with | next :: _ => decide (Is input next "(") | [] => false)
            if isConstructor then
              let result ← constructorSyntax input owner (token :: tail)
              return ⟨.constructorDecl result.constructor,result.rest,.constructorDecl result.grammar⟩
            else
              let field ← formal input (token :: tail)
              match eq : field.rest with
              | semicolon :: remaining =>
                if semi : Is input semicolon ";" then
                  return ⟨.fieldDecl field.formal,remaining,.fieldDecl (eq ▸ field.grammar) semi⟩
                else none
              | [] => none
        | .outer =>
          if exportedToken : Is input token "export" then
            let child ← declaration input fuel .outer tail
            match eq : child.declaration with
            | .namespaceDecl name false children =>
              return ⟨.namespaceDecl name true children,child.rest,.exportedNamespace exportedToken (eq ▸ child.grammar)⟩
            | _ => none
          else if ns : Is input token "namespace" then
            let name :: opening :: remaining := tail | none
            if ident : Identifier input name then
              if brace : Is input opening "{" then
                let children ← declarations input fuel .outer true remaining
                match eq : children.rest with
                | closing :: rest =>
                  if close : Is input closing "}" then
                    return ⟨.namespaceDecl (spelling input name) false children.declarations,rest,
                      .namespaceDecl ns ident brace (eq ▸ children.grammar) close⟩
                  else none
                | [] => none
              else none
            else none
          else if cls : Is input token "class" then
            let name :: opening :: remaining := tail | none
            if ident : Identifier input name then
              if brace : Is input opening "{" then
                let members ← declarations input fuel (.classBody (spelling input name)) true remaining
                match eq : members.rest with
                | closing :: semicolon :: rest =>
                  if close : Is input closing "}" then
                    if semi : Is input semicolon ";" then
                      return ⟨.classDecl (spelling input name) members.declarations,rest,
                        .classDecl cls ident brace (eq ▸ members.grammar) close semi⟩
                    else none
                  else none
                | _ => none
              else none
            else none
          else if en : Is input token "enum" then
            let cls :: name :: opening :: remaining := tail | none
            if cl : Is input cls "class" then
              if ident : Identifier input name then
                if brace : Is input opening "{" then
                  let cases ← enumCases input 4096 remaining
                  match eq : cases.rest with
                  | semicolon :: rest =>
                    if semi : Is input semicolon ";" then
                      return ⟨.enumDecl (spelling input name) cases.names,rest,
                        .enumDecl en cl ident brace (eq ▸ cases.grammar) semi⟩
                    else none
                  | [] => none
                else none
              else none
            else none
          else none
end

structure ShellSource (input : ByteArray) where
  header : HeaderSource input
  shell : ParsedDeclarations input .outer false header.declarations.imports.rest
  complete : shell.rest = []

/-- No unparsed suffix can be promoted to a complete shell. -/
def shellSource (input : ByteArray) : Option (ShellSource input) := do
  let head ← headerSource input
  let parsed ← declarations input 4096 .outer false head.declarations.imports.rest
  if complete : parsed.rest = [] then return ⟨head,parsed,complete⟩ else none

theorem shell_source_sound (input : ByteArray) (result : ShellSource input)
    (_accepted : shellSource input = some result) :
    Coverage input result.header.lexical.reversed input.size ∧
    ModuleDecl input (significant result.header.lexical.reversed.reverse)
      result.header.declarations.module.exported result.header.declarations.module.name
      result.header.declarations.module.rest ∧
    Imports input result.header.declarations.module.rest result.header.declarations.imports.names
      result.header.declarations.imports.rest ∧
    Declarations input .outer false result.header.declarations.imports.rest result.shell.declarations [] :=
  ⟨result.header.lexical.grammar,result.header.declarations.module.grammar,
    result.header.declarations.imports.grammar,result.complete ▸ result.shell.grammar⟩

end Aurora.SourceBinding
