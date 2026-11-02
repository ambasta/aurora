import SourceBinding.Declarations
namespace Aurora.SourceBinding

/- Constructive equality for the existing nested declaration shell. This adds
    no syntax or acceptance rule; it is used to retain exact scope identity. -/
mutual
  def declarationDecidableEq (left right : Declaration) : Decidable (left = right) :=
    match left, right with
    | .namespaceDecl a b xs, .namespaceDecl c d ys =>
      let nested := declarationsDecidableEq xs ys
      if ac : a = c then
        if bd : b = d then
          match nested with
          | .isTrue same => .isTrue (by cases ac; cases bd; cases same; rfl)
          | .isFalse different => .isFalse (fun same => different (Declaration.namespaceDecl.inj same).2.2)
        else .isFalse (fun same => bd (Declaration.namespaceDecl.inj same).2.1)
      else .isFalse (fun same => ac (Declaration.namespaceDecl.inj same).1)
    | .classDecl a xs, .classDecl b ys =>
      if ab : a = b then
        match declarationsDecidableEq xs ys with
        | .isTrue same => .isTrue (by cases ab; cases same; rfl)
        | .isFalse different => .isFalse (fun same => different (Declaration.classDecl.inj same).2)
      else .isFalse (fun same => ab (Declaration.classDecl.inj same).1)
    | .enumDecl a xs, .enumDecl b ys =>
      if same : a = b ∧ xs = ys then .isTrue (by rcases same with ⟨rfl,rfl⟩; rfl)
      else .isFalse (fun equal => same (Declaration.enumDecl.inj equal))
    | .functionDecl a, .functionDecl b =>
      if same : a = b then .isTrue (by cases same; rfl) else .isFalse (fun equal => same (Declaration.functionDecl.inj equal))
    | .constructorDecl a, .constructorDecl b =>
      if same : a = b then .isTrue (by cases same; rfl) else .isFalse (fun equal => same (Declaration.constructorDecl.inj equal))
    | .fieldDecl a, .fieldDecl b =>
      if same : a = b then .isTrue (by cases same; rfl) else .isFalse (fun equal => same (Declaration.fieldDecl.inj equal))
    | .access a, .access b =>
      if same : a = b then .isTrue (by cases same; rfl) else .isFalse (fun equal => same (Declaration.access.inj equal))
    | .namespaceDecl .., .classDecl .. | .namespaceDecl .., .enumDecl .. | .namespaceDecl .., .functionDecl ..
    | .namespaceDecl .., .constructorDecl .. | .namespaceDecl .., .fieldDecl .. | .namespaceDecl .., .access ..
    | .classDecl .., .namespaceDecl .. | .classDecl .., .enumDecl .. | .classDecl .., .functionDecl ..
    | .classDecl .., .constructorDecl .. | .classDecl .., .fieldDecl .. | .classDecl .., .access ..
    | .enumDecl .., .namespaceDecl .. | .enumDecl .., .classDecl .. | .enumDecl .., .functionDecl ..
    | .enumDecl .., .constructorDecl .. | .enumDecl .., .fieldDecl .. | .enumDecl .., .access ..
    | .functionDecl .., .namespaceDecl .. | .functionDecl .., .classDecl .. | .functionDecl .., .enumDecl ..
    | .functionDecl .., .constructorDecl .. | .functionDecl .., .fieldDecl .. | .functionDecl .., .access ..
    | .constructorDecl .., .namespaceDecl .. | .constructorDecl .., .classDecl .. | .constructorDecl .., .enumDecl ..
    | .constructorDecl .., .functionDecl .. | .constructorDecl .., .fieldDecl .. | .constructorDecl .., .access ..
    | .fieldDecl .., .namespaceDecl .. | .fieldDecl .., .classDecl .. | .fieldDecl .., .enumDecl ..
    | .fieldDecl .., .functionDecl .. | .fieldDecl .., .constructorDecl .. | .fieldDecl .., .access ..
    | .access .., .namespaceDecl .. | .access .., .classDecl .. | .access .., .enumDecl ..
    | .access .., .functionDecl .. | .access .., .constructorDecl .. | .access .., .fieldDecl .. => .isFalse (by intro same; cases same)
  termination_by sizeOf left
  def declarationsDecidableEq (left right : List Declaration) : Decidable (left = right) :=
    match left, right with
    | [], [] => .isTrue rfl
    | first :: rest, other :: tail =>
      match declarationDecidableEq first other, declarationsDecidableEq rest tail with
      | .isTrue same, .isTrue remaining => .isTrue (by cases same; cases remaining; rfl)
      | .isFalse different, _ => .isFalse (fun same => different (List.cons.inj same).1)
      | _, .isFalse different => .isFalse (fun same => different (List.cons.inj same).2)
    | [], _ :: _ | _ :: _, [] => .isFalse (by intro same; cases same)
  termination_by sizeOf left
end
instance : DecidableEq Declaration := declarationDecidableEq
end Aurora.SourceBinding
