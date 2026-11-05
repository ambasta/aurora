import SourceBinding.EffectSourceFunction
import SourceBinding.EffectSourceNames
import SourceBinding.EffectSourceOperations
import SourceBinding.ResourceStatementRules
namespace Aurora.SourceBinding

abbrev EffectScopedStatement (context : EffectContext) :=
  ScopedStatementWith context.profile context.uses context.writes context.lexical.members
    context.lexical.module context.lexical.path context.lexical.formals
abbrev EffectScopedStatements (context : EffectContext) :=
  ScopedStatementsWith context.profile context.uses context.writes context.lexical.members
    context.lexical.module context.lexical.path context.lexical.formals

def EffectSourceFunction.initialCursor (source : EffectSourceFunction) : LocalContext :=
  ⟨[],0,1,source.context.lexical.formals.length⟩

def SourceShared.store (shared : SourceShared World) (ordinal : Nat) (value : Value) : SourceShared World :=
  {shared with receiver := fun other => if other = ordinal then some value else shared.receiver other}

/- The ONE effect-aware raw source judgement. RuntimeEvaluation's former API
   becomes its legacy-profile specialization after the migration equivalence.
   There is intentionally NO general resource-expression constructor. -/
mutual
  inductive EffectEvaluation (functions : List EffectSourceFunction)
      (response : SourceExternalRelation World ExternalFault) :
      EffectContext → SourceEffectState World → SourceExpr → RuntimeType →
      SourceEffectOutcome World ExternalFault → SourceShared World →
      List (SourceEffectEvent World ExternalFault) → Prop
    | word : EffectEvaluation functions response context state (.word value) (.scalar .word)
        (sourceLift (readScalar .word (some (.word value)))) state.shared []
    | boolean : EffectEvaluation functions response context state (.boolean value) (.scalar .boolean)
        (.value (some (.boolean value))) state.shared []
    | readVariable : RuntimeVariableBinding context.lexical name binding →
        EffectEvaluation functions response context state (.name [name]) binding.kind
          (sourceLift (state.locals.readBound binding)) state.shared []
    | readField : EffectFieldResolved context name field →
        EffectEvaluation functions response context state (.name [name]) (.scalar field.kind)
          (sourceLift (readScalar field.kind (state.shared.receiver field.ordinal))) state.shared []
    | enumValue : EffectEnumValue context name identity ordinal →
        EffectEvaluation functions response context state (.name name) (.nominal identity)
          (sourceLift (readRuntime (.nominal identity) (some (.nominal identity.name ordinal)))) state.shared []
    | not : EffectEvaluation functions response context state raw (.scalar .boolean) outcome after events →
        EffectEvaluation functions response context state (.not raw) (.scalar .boolean)
          (sourceThen outcome notValue) after events
    | wordBinaryStop : RuntimeWordOperator operator primitive result →
        EffectEvaluation functions response context state left (.scalar .word) (.stopped stop) after events →
        EffectEvaluation functions response context state (.binary operator left right) (.scalar result)
          (.stopped stop) after events
    | wordBinaryMissing : RuntimeWordOperator operator primitive result →
        EffectEvaluation functions response context state left (.scalar .word) (.value none) after events →
        EffectEvaluation functions response context state (.binary operator left right) (.scalar result)
          (.stopped (.localFault (.scalar .type))) after events
    | wordBinary : RuntimeWordOperator operator primitive result →
        EffectEvaluation functions response context state left (.scalar .word) (.value (some value)) middle first →
        EffectEvaluation functions response context {state with shared := middle} right (.scalar .word) outcome after rest →
        EffectEvaluation functions response context state (.binary operator left right) (.scalar result)
          (sourceThen outcome (binaryValue primitive value)) after (first ++ rest)
    | enumCompareStop {equal : Bool} :
        EffectEvaluation functions response context state left (.nominal identity) (.stopped stop) after events →
        EffectEvaluation functions response context state (.binary (.compare (if equal then .eq else .ne)) left right)
          (.scalar .boolean) (.stopped stop) after events
    | enumCompareMissing {equal : Bool} :
        EffectEvaluation functions response context state left (.nominal identity) (.value none) after events →
        EffectEvaluation functions response context state (.binary (.compare (if equal then .eq else .ne)) left right)
          (.scalar .boolean) (.stopped (.localFault (.scalar .type))) after events
    | enumCompare {equal : Bool} :
        EffectEvaluation functions response context state left (.nominal identity) (.value (some value)) middle first →
        EffectEvaluation functions response context {state with shared := middle} right (.nominal identity) outcome after rest →
        EffectEvaluation functions response context state (.binary (.compare (if equal then .eq else .ne)) left right)
          (.scalar .boolean) (sourceThen outcome (compareNominal identity equal value)) after (first ++ rest)
    | shiftLeft : EffectEvaluation functions response context state left (.scalar .word) outcome after events →
        SourceShiftCount right count →
        EffectEvaluation functions response context state (.binary .shift left right) (.scalar .word)
          (sourceThen outcome (fun value => binaryValue .leftShift value count.runtimeValue)) after events
    | shiftRight : EffectEvaluation functions response context state left (.scalar .word) outcome after events →
        SourceShiftCount right count →
        EffectEvaluation functions response context state (.binary .rightShift left right) (.scalar .word)
          (sourceThen outcome (fun value => binaryValue .rightShift value count.runtimeValue)) after events
    | andStopped : EffectEvaluation functions response context state left (.scalar .boolean)
        (.stopped reason) after events →
        EffectEvaluation functions response context state (.binary .and left right) (.scalar .boolean)
          (.stopped reason) after events
    | andMalformed : EffectEvaluation functions response context state left (.scalar .boolean) (.value raw) after events →
        readScalar .boolean raw = .trap fault →
        EffectEvaluation functions response context state (.binary .and left right) (.scalar .boolean)
          (.stopped (.localFault (.scalar fault))) after events
    | andStop : EffectEvaluation functions response context state left (.scalar .boolean)
        (.value (some (.boolean false))) after events →
        EffectEvaluation functions response context state (.binary .and left right) (.scalar .boolean)
          (.value (some (.boolean false))) after events
    | andContinue : EffectEvaluation functions response context state left (.scalar .boolean)
        (.value (some (.boolean true))) middle first →
        EffectEvaluation functions response context {state with shared := middle} right (.scalar .boolean) outcome after rest →
        EffectEvaluation functions response context state (.binary .and left right) (.scalar .boolean)
          outcome after (first ++ rest)
    | orStopped : EffectEvaluation functions response context state left (.scalar .boolean)
        (.stopped reason) after events →
        EffectEvaluation functions response context state (.binary .or left right) (.scalar .boolean)
          (.stopped reason) after events
    | orMalformed : EffectEvaluation functions response context state left (.scalar .boolean) (.value raw) after events →
        readScalar .boolean raw = .trap fault →
        EffectEvaluation functions response context state (.binary .or left right) (.scalar .boolean)
          (.stopped (.localFault (.scalar fault))) after events
    | orStop : EffectEvaluation functions response context state left (.scalar .boolean)
        (.value (some (.boolean true))) after events →
        EffectEvaluation functions response context state (.binary .or left right) (.scalar .boolean)
          (.value (some (.boolean true))) after events
    | orContinue : EffectEvaluation functions response context state left (.scalar .boolean)
        (.value (some (.boolean false))) middle first →
        EffectEvaluation functions response context {state with shared := middle} right (.scalar .boolean) outcome after rest →
        EffectEvaluation functions response context state (.binary .or left right) (.scalar .boolean)
          outcome after (first ++ rest)
    | callArgumentsStop : callee ∈ functions → callee.Resolves context name →
        EffectArguments functions response context state sources callee.parameters (.stopped stop) after events →
        EffectEvaluation functions response context state (.call (.named name) sources) callee.result
          (.stopped stop) after events
    | callEntryFault : callee ∈ functions → callee.Resolves context name →
        EffectArguments functions response context state sources callee.parameters (.values values) after events →
        checkSourceArguments callee.parameters values = .trap fault →
        EffectEvaluation functions response context state (.call (.named name) sources) callee.result
          (.stopped (.localFault (.scalar fault))) after (events ++ [.invoke callee.key values])
    | callValue : callee ∈ functions → callee.Resolves context name →
        EffectArguments functions response context state sources callee.parameters (.values values) middle first →
        checkSourceArguments callee.parameters values = .value () →
        EffectStatements functions response callee.context callee.result callee.initialCursor
          ⟨formalSourceLocals callee.parameters (fun i => values[i]?),middle⟩ callee.parsed.statements
          afterCursor (.returned value finished) body →
        EffectEvaluation functions response context state (.call (.named name) sources) callee.result
          (.value (some value)) finished.shared
          (first ++ [.invoke callee.key values] ++ body ++ [.returned callee.key value])
    | callStop : callee ∈ functions → callee.Resolves context name →
        EffectArguments functions response context state sources callee.parameters (.values values) middle first →
        checkSourceArguments callee.parameters values = .value () →
        EffectStatements functions response callee.context callee.result callee.initialCursor
          ⟨formalSourceLocals callee.parameters (fun i => values[i]?),middle⟩ callee.parsed.statements
          afterCursor (.stopped stop finished) body →
        EffectEvaluation functions response context state (.call (.named name) sources) callee.result
          (.stopped stop) finished.shared (first ++ [.invoke callee.key values] ++ body)

  inductive EffectArguments (functions : List EffectSourceFunction)
      (response : SourceExternalRelation World ExternalFault) :
      EffectContext → SourceEffectState World → List SourceExpr → List RuntimeType →
      EffectArgumentOutcome World ExternalFault → SourceShared World →
      List (SourceEffectEvent World ExternalFault) → Prop
    | nil : EffectArguments functions response context state [] [] (.values []) state.shared []
    | stopped : EffectEvaluation functions response context state raw kind (.stopped stop) after events →
        EffectArguments functions response context state (raw::rest) (kind::kinds) (.stopped stop) after events
    | missing : EffectEvaluation functions response context state raw kind (.value none) after events →
        EffectArguments functions response context state (raw::rest) (kind::kinds)
          (.stopped (.localFault (.scalar .type))) after events
    | cons : EffectEvaluation functions response context state raw kind (.value (some value)) middle first →
        EffectArguments functions response context {state with shared := middle} rest kinds outcome after later →
        EffectArguments functions response context state (raw::rest) (kind::kinds)
          (outcome.prepend value) after (first ++ later)

  inductive EffectStatement (functions : List EffectSourceFunction)
      (response : SourceExternalRelation World ExternalFault) :
      EffectContext → RuntimeType → LocalContext → SourceEffectState World →
      SourceStatement → LocalContext → SourceEffectBodyOutcome World ExternalFault →
      List (SourceEffectEvent World ExternalFault) → Prop
    | declarationStop {declaration : Formal} : EffectScopedStatement context before (.localDecl declaration raw) after [binding] →
        EffectEvaluation functions response (context.atCursor before) state raw binding.kind (.stopped stop) shared events →
        EffectStatement functions response context result before state (.localDecl declaration raw) after
          (.stopped stop {state with shared := shared}) events
    | declarationMalformed {declaration : Formal} : EffectScopedStatement context before (.localDecl declaration raw) after [binding] →
        EffectEvaluation functions response (context.atCursor before) state raw binding.kind (.value rawValue) shared events →
        readRuntime binding.kind rawValue = .trap fault →
        EffectStatement functions response context result before state (.localDecl declaration raw) after
          (.stopped (.localFault (.scalar fault)) {state with shared := shared}) events
    | declarationValue {declaration : Formal} : EffectScopedStatement context before (.localDecl declaration raw) after [binding] →
        EffectEvaluation functions response (context.atCursor before) state raw binding.kind (.value rawValue) shared events →
        readRuntime binding.kind rawValue = .value value → state.locals.initialize binding.slot binding.runtimeDeclaration value = some next →
        EffectStatement functions response context result before state (.localDecl declaration raw) after
          (.continued ⟨next,shared⟩) events
    | assignmentStop : binding ∈ before.visible → binding.name = name → binding.mutable = true →
        EffectEvaluation functions response (context.atCursor before) state raw binding.kind (.stopped stop) shared events →
        EffectStatement functions response context result before state (.assign name raw) before
          (.stopped stop {state with shared := shared}) events
    | assignmentMalformed : binding ∈ before.visible → binding.name = name → binding.mutable = true →
        EffectEvaluation functions response (context.atCursor before) state raw binding.kind (.value rawValue) shared events →
        readRuntime binding.kind rawValue = .trap fault →
        EffectStatement functions response context result before state (.assign name raw) before
          (.stopped (.localFault (.scalar fault)) {state with shared := shared}) events
    | assignmentValue : binding ∈ before.visible → binding.name = name → binding.mutable = true →
        EffectEvaluation functions response (context.atCursor before) state raw binding.kind (.value rawValue) shared events →
        readRuntime binding.kind rawValue = .value value → state.locals.assign binding.slot value = some next →
        EffectStatement functions response context result before state (.assign name raw) before
          (.continued ⟨next,shared⟩) events
    | resourceDeclareArgumentsStop {declaration : Formal} : context.profile = .receiverEffects →
        EffectScopedStatement context before (.localDecl declaration (.call (.receiver field method) sources)) after [binding] →
        EffectResourceResolved (context.atCursor before) resource →
        resource.field = field → resource.method = method → binding.kind = .scalar resource.result →
        EffectArguments functions response (context.atCursor before) state sources
          (resource.parameters.map RuntimeType.scalar) (.stopped stop) shared first →
        EffectStatement functions response context result before state (.localDecl declaration (.call (.receiver field method) sources)) after
          (.stopped stop {state with shared := shared}) first
    | resourceDeclare {declaration : Formal} : context.profile = .receiverEffects →
        EffectScopedStatement context before (.localDecl declaration (.call (.receiver field method) sources)) after [binding] →
        EffectResourceResolved (context.atCursor before) resource →
        resource.field = field → resource.method = method → binding.kind = .scalar resource.result →
        EffectArguments functions response (context.atCursor before) state sources
          (resource.parameters.map RuntimeType.scalar) (.values values) shared first →
        SourceResourceInitialize response resource values binding {state with shared := shared} outcome later →
        EffectStatement functions response context result before state (.localDecl declaration (.call (.receiver field method) sources)) after
          outcome (first ++ later)
    | resourceRequireArgumentsStop : context.profile = .receiverEffects →
        EffectResourceResolved (context.atCursor before) resource →
        resource.field = field → resource.method = method → resource.result = .boolean →
        EffectArguments functions response (context.atCursor before) state sources
          (resource.parameters.map RuntimeType.scalar) (.stopped stop) shared first →
        EffectStatement functions response context result before state (.call (.named ["builtin".toUTF8,"require".toUTF8]) [.call (.receiver field method) sources]) before
          (.stopped stop {state with shared := shared}) first
    | resourceRequire : context.profile = .receiverEffects →
        EffectResourceResolved (context.atCursor before) resource →
        resource.field = field → resource.method = method → resource.result = .boolean →
        EffectArguments functions response (context.atCursor before) state sources
          (resource.parameters.map RuntimeType.scalar) (.values values) shared first →
        SourceResourceAssert response resource values {state with shared := shared} outcome later →
        EffectStatement functions response context result before state (.call (.named ["builtin".toUTF8,"require".toUTF8]) [.call (.receiver field method) sources]) before
          outcome (first ++ later)
    | fieldAssignmentStop : EffectFieldWritable (context.atCursor before) name field →
        EffectEvaluation functions response (context.atCursor before) state raw (.scalar field.kind) (.stopped stop) shared events →
        EffectStatement functions response context result before state (.assign name raw) before
          (.stopped stop {state with shared := shared}) events
    | fieldAssignmentMalformed : EffectFieldWritable (context.atCursor before) name field →
        EffectEvaluation functions response (context.atCursor before) state raw (.scalar field.kind) (.value rawValue) shared events →
        readScalar field.kind rawValue = .trap fault →
        EffectStatement functions response context result before state (.assign name raw) before
          (.stopped (.localFault (.scalar fault)) {state with shared := shared}) events
    | fieldAssignmentValue : EffectFieldWritable (context.atCursor before) name field →
        EffectEvaluation functions response (context.atCursor before) state raw (.scalar field.kind) (.value rawValue) shared events →
        readScalar field.kind rawValue = .value value →
        EffectStatement functions response context result before state (.assign name raw) before
          (.continued {state with shared := shared.store field.ordinal value}) (events ++ [.fieldStore name value])
    | returnStop : EffectEvaluation functions response (context.atCursor before) state raw result (.stopped stop) shared events →
        EffectStatement functions response context result before state (.returnValue raw) before
          (.stopped stop {state with shared := shared}) events
    | returnMissing : EffectEvaluation functions response (context.atCursor before) state raw result (.value none) shared events →
        EffectStatement functions response context result before state (.returnValue raw) before
          (.stopped (.localFault (.scalar .type)) {state with shared := shared}) events
    | returnValue : EffectEvaluation functions response (context.atCursor before) state raw result (.value (some value)) shared events →
        EffectStatement functions response context result before state (.returnValue raw) before
          (.returned value {state with shared := shared}) events
    | branchStop : EffectScopedStatements context (enterLocalScope before) yes yesAfter yesItems →
        EffectEvaluation functions response (context.atCursor before) state condition (.scalar .boolean)
          (.stopped stop) shared events → EffectStatement functions response context result before state (.ifThen condition yes) (leaveLocalScope before yesAfter)
          (.stopped stop {state with shared := shared}) events
    | branchMalformed : EffectScopedStatements context (enterLocalScope before) yes yesAfter yesItems →
        EffectEvaluation functions response (context.atCursor before) state condition (.scalar .boolean)
          (.value rawValue) shared events → readScalar .boolean rawValue = .trap fault →
        EffectStatement functions response context result before state (.ifThen condition yes) (leaveLocalScope before yesAfter)
          (.stopped (.localFault (.scalar fault)) {state with shared := shared}) events
    | branchFalse : EffectScopedStatements context (enterLocalScope before) yes yesAfter yesItems →
        EffectEvaluation functions response (context.atCursor before) state condition (.scalar .boolean)
          (.value (some (.boolean false))) shared events →
        state.locals.reserveScopes yesAfter.nextScope = some next →
        EffectStatement functions response context result before state (.ifThen condition yes) (leaveLocalScope before yesAfter)
          (.continued ⟨next,shared⟩) events
    | branchTrueContinue : EffectScopedStatements context (enterLocalScope before) yes yesAfter yesItems →
        EffectEvaluation functions response (context.atCursor before) state condition (.scalar .boolean)
          (.value (some (.boolean true))) shared first →
        state.locals.enterAt before.nextScope = some entered →
        EffectStatements functions response context result (enterLocalScope before) ⟨entered,shared⟩ yes yesAfter (.continued finished) later →
        finished.locals.leave.reserveScopes yesAfter.nextScope = some next →
        EffectStatement functions response context result before state (.ifThen condition yes) (leaveLocalScope before yesAfter)
          (.continued {finished with locals := next}) (first ++ later)
    | branchTrueReturn : EffectScopedStatements context (enterLocalScope before) yes yesAfter yesItems →
        EffectEvaluation functions response (context.atCursor before) state condition (.scalar .boolean)
          (.value (some (.boolean true))) shared first →
        state.locals.enterAt before.nextScope = some entered →
        EffectStatements functions response context result (enterLocalScope before) ⟨entered,shared⟩ yes yesAfter (.returned value finished) later →
        EffectStatement functions response context result before state (.ifThen condition yes) (leaveLocalScope before yesAfter)
          (.returned value finished) (first ++ later)
    | branchTrueStop : EffectScopedStatements context (enterLocalScope before) yes yesAfter yesItems →
        EffectEvaluation functions response (context.atCursor before) state condition (.scalar .boolean)
          (.value (some (.boolean true))) shared first →
        state.locals.enterAt before.nextScope = some entered →
        EffectStatements functions response context result (enterLocalScope before) ⟨entered,shared⟩ yes yesAfter (.stopped stop finished) later →
        EffectStatement functions response context result before state (.ifThen condition yes) (leaveLocalScope before yesAfter)
          (.stopped stop finished) (first ++ later)
    | branchElseStop : context.profile = .receiverEffects →
        EffectScopedStatements context (enterLocalScope before) yes yesAfter yesItems →
        EffectScopedStatements context (enterLocalScope (leaveLocalScope before yesAfter)) no noAfter noItems →
        EffectEvaluation functions response (context.atCursor before) state condition (.scalar .boolean)
          (.stopped stop) shared events → EffectStatement functions response context result before state (.ifElse condition yes no) (leaveLocalScope before noAfter)
          (.stopped stop {state with shared := shared}) events
    | branchElseMalformed : context.profile = .receiverEffects →
        EffectScopedStatements context (enterLocalScope before) yes yesAfter yesItems →
        EffectScopedStatements context (enterLocalScope (leaveLocalScope before yesAfter)) no noAfter noItems →
        EffectEvaluation functions response (context.atCursor before) state condition (.scalar .boolean)
          (.value rawValue) shared events → readScalar .boolean rawValue = .trap fault →
        EffectStatement functions response context result before state (.ifElse condition yes no) (leaveLocalScope before noAfter)
          (.stopped (.localFault (.scalar fault)) {state with shared := shared}) events
    | branchElseTrueContinue : context.profile = .receiverEffects →
        EffectScopedStatements context (enterLocalScope before) yes yesAfter yesItems →
        EffectScopedStatements context (enterLocalScope (leaveLocalScope before yesAfter)) no noAfter noItems →
        EffectEvaluation functions response (context.atCursor before) state condition (.scalar .boolean)
          (.value (some (.boolean true))) shared first →
        state.locals.enterAt before.nextScope = some entered →
        EffectStatements functions response context result (enterLocalScope before) ⟨entered,shared⟩ yes yesAfter (.continued finished) later →
        finished.locals.leave.reserveScopes noAfter.nextScope = some next →
        EffectStatement functions response context result before state (.ifElse condition yes no) (leaveLocalScope before noAfter)
          (.continued {finished with locals := next}) (first ++ later)
    | branchElseTrueReturn : context.profile = .receiverEffects →
        EffectScopedStatements context (enterLocalScope before) yes yesAfter yesItems →
        EffectScopedStatements context (enterLocalScope (leaveLocalScope before yesAfter)) no noAfter noItems →
        EffectEvaluation functions response (context.atCursor before) state condition (.scalar .boolean)
          (.value (some (.boolean true))) shared first →
        state.locals.enterAt before.nextScope = some entered →
        EffectStatements functions response context result (enterLocalScope before) ⟨entered,shared⟩ yes yesAfter (.returned value finished) later →
        EffectStatement functions response context result before state (.ifElse condition yes no) (leaveLocalScope before noAfter)
          (.returned value finished) (first ++ later)
    | branchElseTrueStop : context.profile = .receiverEffects →
        EffectScopedStatements context (enterLocalScope before) yes yesAfter yesItems →
        EffectScopedStatements context (enterLocalScope (leaveLocalScope before yesAfter)) no noAfter noItems →
        EffectEvaluation functions response (context.atCursor before) state condition (.scalar .boolean)
          (.value (some (.boolean true))) shared first →
        state.locals.enterAt before.nextScope = some entered →
        EffectStatements functions response context result (enterLocalScope before) ⟨entered,shared⟩ yes yesAfter (.stopped stop finished) later →
        EffectStatement functions response context result before state (.ifElse condition yes no) (leaveLocalScope before noAfter)
          (.stopped stop finished) (first ++ later)
    | branchElseFalseContinue : context.profile = .receiverEffects →
        EffectScopedStatements context (enterLocalScope before) yes yesAfter yesItems →
        EffectScopedStatements context (enterLocalScope (leaveLocalScope before yesAfter)) no noAfter noItems →
        EffectEvaluation functions response (context.atCursor before) state condition (.scalar .boolean)
          (.value (some (.boolean false))) shared first →
        state.locals.reserveScopes yesAfter.nextScope = some skipped →
        skipped.enterAt yesAfter.nextScope = some entered →
        EffectStatements functions response context result (enterLocalScope (leaveLocalScope before yesAfter)) ⟨entered,shared⟩ no noAfter (.continued finished) later →
        finished.locals.leave.reserveScopes noAfter.nextScope = some next →
        EffectStatement functions response context result before state (.ifElse condition yes no) (leaveLocalScope before noAfter)
          (.continued {finished with locals := next}) (first ++ later)
    | branchElseFalseReturn : context.profile = .receiverEffects →
        EffectScopedStatements context (enterLocalScope before) yes yesAfter yesItems →
        EffectScopedStatements context (enterLocalScope (leaveLocalScope before yesAfter)) no noAfter noItems →
        EffectEvaluation functions response (context.atCursor before) state condition (.scalar .boolean)
          (.value (some (.boolean false))) shared first →
        state.locals.reserveScopes yesAfter.nextScope = some skipped →
        skipped.enterAt yesAfter.nextScope = some entered →
        EffectStatements functions response context result (enterLocalScope (leaveLocalScope before yesAfter)) ⟨entered,shared⟩ no noAfter (.returned value finished) later →
        EffectStatement functions response context result before state (.ifElse condition yes no) (leaveLocalScope before noAfter)
          (.returned value finished) (first ++ later)
    | branchElseFalseStop : context.profile = .receiverEffects →
        EffectScopedStatements context (enterLocalScope before) yes yesAfter yesItems →
        EffectScopedStatements context (enterLocalScope (leaveLocalScope before yesAfter)) no noAfter noItems →
        EffectEvaluation functions response (context.atCursor before) state condition (.scalar .boolean)
          (.value (some (.boolean false))) shared first →
        state.locals.reserveScopes yesAfter.nextScope = some skipped →
        skipped.enterAt yesAfter.nextScope = some entered →
        EffectStatements functions response context result (enterLocalScope (leaveLocalScope before yesAfter)) ⟨entered,shared⟩ no noAfter (.stopped stop finished) later →
        EffectStatement functions response context result before state (.ifElse condition yes no) (leaveLocalScope before noAfter)
          (.stopped stop finished) (first ++ later)

  inductive EffectStatements (functions : List EffectSourceFunction)
      (response : SourceExternalRelation World ExternalFault) :
      EffectContext → RuntimeType → LocalContext → SourceEffectState World →
      List SourceStatement → LocalContext → SourceEffectBodyOutcome World ExternalFault →
      List (SourceEffectEvent World ExternalFault) → Prop
    | nil : EffectStatements functions response context result before state [] before (.continued state) []
    | next : EffectStatement functions response context result before state first middle (.continued next) firstEvents →
        EffectStatements functions response context result middle next rest after outcome restEvents →
        EffectStatements functions response context result before state (first::rest) after outcome (firstEvents ++ restEvents)
    | returned : EffectStatement functions response context result before state first middle (.returned value finished) events →
        EffectScopedStatements context middle rest after declaredItems →
        EffectStatements functions response context result before state (first::rest) after (.returned value finished) events
    | stopped : EffectStatement functions response context result before state first middle (.stopped stop finished) events →
        EffectScopedStatements context middle rest after declaredItems →
        EffectStatements functions response context result before state (first::rest) after (.stopped stop finished) events
end
end Aurora.SourceBinding
