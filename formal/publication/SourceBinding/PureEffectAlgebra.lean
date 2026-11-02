import SourceBinding.EffectPureEmbedding
import SourceBinding.RuntimeExpressions
import SourceBinding.RuntimeScopeOperations
namespace Aurora.SourceBinding

/-- A proposition algebra for the original pure constructor rules. These are
    induction handlers, not an evaluator, source certificate, or result oracle.
    The effect judgment's generic elimination proves every supplied algebra. -/
structure PureEffectAlgebra (functions : List RuntimeSourceFunction)
    (Expression : RuntimeExprContext → RuntimeLocals → SourceExpr → RuntimeType → Outcome Value → List RuntimeSourceEvent → Prop)
    (Arguments : RuntimeExprContext → RuntimeLocals → List SourceExpr → List RuntimeType → Outcome (List Value) → List RuntimeSourceEvent → Prop)
    (Statement : List Declaration → Name → Name → List Formal → RuntimeType → LocalContext → RuntimeLocals → SourceStatement → LocalContext → RuntimeBodyOutcome → List RuntimeSourceEvent → Prop)
    (Statements : List Declaration → Name → Name → List Formal → RuntimeType → LocalContext → RuntimeLocals → List SourceStatement → LocalContext → RuntimeBodyOutcome → List RuntimeSourceEvent → Prop) : Prop where
  expression_word : ∀ {context : RuntimeExprContext}
      {state : RuntimeLocals} {value : Nat},
      Expression context state (SourceExpr.word value)
        (RuntimeType.scalar Aurora.Publication.Scalar.word)
        (readScalar Aurora.Publication.Scalar.word (some (Value.word value))) []
  expression_boolean : ∀ {context : RuntimeExprContext}
      {state : RuntimeLocals} {value : Bool},
      Expression context state (SourceExpr.boolean value)
        (RuntimeType.scalar Aurora.Publication.Scalar.boolean) (Outcome.value (Value.boolean value)) []
  expression_readVariable : ∀ {context : RuntimeExprContext}
      {name : ByteArray} {binding : SourceLocal} {state : RuntimeLocals},
      RuntimeVariableBinding context name binding →
        Expression context state (SourceExpr.name [name]) binding.kind (state.readBound binding) []
  expression_enumValue : ∀ {context : RuntimeExprContext}
      {name : Name} {identity : NominalIdentity} {ordinal : Nat} {state : RuntimeLocals},
      RuntimeEnumValue context name identity ordinal →
        Expression context state (SourceExpr.name name) (RuntimeType.nominal identity)
          (readRuntime (RuntimeType.nominal identity) (some (Value.nominal identity.name ordinal))) []
  expression_not : ∀ {context : RuntimeExprContext}
      {state : RuntimeLocals} {inner : SourceExpr} {outcome : Outcome Value} {events : List RuntimeSourceEvent},
      Expression context state inner (RuntimeType.scalar Aurora.Publication.Scalar.boolean) outcome
          events →
        Expression context state inner.not (RuntimeType.scalar Aurora.Publication.Scalar.boolean)
          (outcome.then notValue) events
  expression_wordBinaryFault : ∀ {operator : SourceBinOp}
      {primitive : Binary} {result : GuardType} {context : RuntimeExprContext} {state : RuntimeLocals} {left : SourceExpr}
      {fault : Fault} {events : List RuntimeSourceEvent} {right : SourceExpr},
      RuntimeWordOperator operator primitive result →
        Expression context state left (RuntimeType.scalar Aurora.Publication.Scalar.word)
            (Outcome.trap fault) events →
          Expression context state (SourceExpr.binary operator left right) (RuntimeType.scalar result)
            (Outcome.trap fault) events
  expression_wordBinary : ∀ {operator : SourceBinOp}
      {primitive : Binary} {result : GuardType} {context : RuntimeExprContext} {state : RuntimeLocals} {left : SourceExpr}
      {value : Value} {leftEvents : List RuntimeSourceEvent} {right : SourceExpr} {outcome : Outcome Value}
      {rightEvents : List RuntimeSourceEvent},
      RuntimeWordOperator operator primitive result →
        Expression context state left (RuntimeType.scalar Aurora.Publication.Scalar.word)
            (Outcome.value value) leftEvents →
          Expression context state right (RuntimeType.scalar Aurora.Publication.Scalar.word) outcome
              rightEvents →
            Expression context state (SourceExpr.binary operator left right)
              (RuntimeType.scalar result) (outcome.then (binaryValue primitive value)) (leftEvents ++ rightEvents)
  expression_enumCompareFault : ∀ {context : RuntimeExprContext}
      {state : RuntimeLocals} {left : SourceExpr} {identity : NominalIdentity} {fault : Fault}
      {events : List RuntimeSourceEvent} {right : SourceExpr} {equal : Bool},
      Expression context state left (RuntimeType.nominal identity) (Outcome.trap fault) events →
        Expression context state
          (SourceExpr.binary (SourceBinOp.compare (if equal = true then CompareOp.eq else CompareOp.ne)) left right)
          (RuntimeType.scalar Aurora.Publication.Scalar.boolean) (Outcome.trap fault) events
  expression_enumCompare : ∀ {context : RuntimeExprContext}
      {state : RuntimeLocals} {left : SourceExpr} {identity : NominalIdentity} {value : Value}
      {leftEvents : List RuntimeSourceEvent} {right : SourceExpr} {outcome : Outcome Value}
      {rightEvents : List RuntimeSourceEvent} {equal : Bool},
      Expression context state left (RuntimeType.nominal identity) (Outcome.value value) leftEvents →
        Expression context state right (RuntimeType.nominal identity) outcome rightEvents →
          Expression context state
            (SourceExpr.binary (SourceBinOp.compare (if equal = true then CompareOp.eq else CompareOp.ne)) left right)
            (RuntimeType.scalar Aurora.Publication.Scalar.boolean) (outcome.then (compareNominal identity equal value))
            (leftEvents ++ rightEvents)
  expression_shiftLeft : ∀ {context : RuntimeExprContext}
      {state : RuntimeLocals} {left : SourceExpr} {outcome : Outcome Value} {events : List RuntimeSourceEvent}
      {right : SourceExpr} {count : SignedLiteralCount},
      Expression context state left (RuntimeType.scalar Aurora.Publication.Scalar.word) outcome
          events →
        SourceShiftCount right count →
          Expression context state (SourceExpr.binary SourceBinOp.shift left right)
            (RuntimeType.scalar Aurora.Publication.Scalar.word)
            (outcome.then fun value => binaryValue Binary.leftShift value count.runtimeValue) events
  expression_shiftRight : ∀ {context : RuntimeExprContext}
      {state : RuntimeLocals} {left : SourceExpr} {outcome : Outcome Value} {events : List RuntimeSourceEvent}
      {right : SourceExpr} {count : SignedLiteralCount},
      Expression context state left (RuntimeType.scalar Aurora.Publication.Scalar.word) outcome
          events →
        SourceShiftCount right count →
          Expression context state (SourceExpr.binary SourceBinOp.rightShift left right)
            (RuntimeType.scalar Aurora.Publication.Scalar.word)
            (outcome.then fun value => binaryValue Binary.rightShift value count.runtimeValue) events
  expression_andFault : ∀ {context : RuntimeExprContext}
      {state : RuntimeLocals} {left : SourceExpr} {fault : Fault} {events : List RuntimeSourceEvent} {right : SourceExpr},
      Expression context state left (RuntimeType.scalar Aurora.Publication.Scalar.boolean)
          (Outcome.trap fault) events →
        Expression context state (SourceExpr.binary SourceBinOp.and left right)
          (RuntimeType.scalar Aurora.Publication.Scalar.boolean) (Outcome.trap fault) events
  expression_andStop : ∀ {context : RuntimeExprContext}
      {state : RuntimeLocals} {left : SourceExpr} {events : List RuntimeSourceEvent} {right : SourceExpr},
      Expression context state left (RuntimeType.scalar Aurora.Publication.Scalar.boolean)
          (Outcome.value (Value.boolean false)) events →
        Expression context state (SourceExpr.binary SourceBinOp.and left right)
          (RuntimeType.scalar Aurora.Publication.Scalar.boolean) (Outcome.value (Value.boolean false)) events
  expression_andContinue : ∀ {context : RuntimeExprContext}
      {state : RuntimeLocals} {left : SourceExpr} {leftEvents : List RuntimeSourceEvent} {right : SourceExpr}
      {outcome : Outcome Value} {rightEvents : List RuntimeSourceEvent},
      Expression context state left (RuntimeType.scalar Aurora.Publication.Scalar.boolean)
          (Outcome.value (Value.boolean true)) leftEvents →
        Expression context state right (RuntimeType.scalar Aurora.Publication.Scalar.boolean) outcome
            rightEvents →
          Expression context state (SourceExpr.binary SourceBinOp.and left right)
            (RuntimeType.scalar Aurora.Publication.Scalar.boolean) outcome (leftEvents ++ rightEvents)
  expression_orFault : ∀ {context : RuntimeExprContext}
      {state : RuntimeLocals} {left : SourceExpr} {fault : Fault} {events : List RuntimeSourceEvent} {right : SourceExpr},
      Expression context state left (RuntimeType.scalar Aurora.Publication.Scalar.boolean)
          (Outcome.trap fault) events →
        Expression context state (SourceExpr.binary SourceBinOp.or left right)
          (RuntimeType.scalar Aurora.Publication.Scalar.boolean) (Outcome.trap fault) events
  expression_orStop : ∀ {context : RuntimeExprContext}
      {state : RuntimeLocals} {left : SourceExpr} {events : List RuntimeSourceEvent} {right : SourceExpr},
      Expression context state left (RuntimeType.scalar Aurora.Publication.Scalar.boolean)
          (Outcome.value (Value.boolean true)) events →
        Expression context state (SourceExpr.binary SourceBinOp.or left right)
          (RuntimeType.scalar Aurora.Publication.Scalar.boolean) (Outcome.value (Value.boolean true)) events
  expression_orContinue : ∀ {context : RuntimeExprContext}
      {state : RuntimeLocals} {left : SourceExpr} {leftEvents : List RuntimeSourceEvent} {right : SourceExpr}
      {outcome : Outcome Value} {rightEvents : List RuntimeSourceEvent},
      Expression context state left (RuntimeType.scalar Aurora.Publication.Scalar.boolean)
          (Outcome.value (Value.boolean false)) leftEvents →
        Expression context state right (RuntimeType.scalar Aurora.Publication.Scalar.boolean) outcome
            rightEvents →
          Expression context state (SourceExpr.binary SourceBinOp.or left right)
            (RuntimeType.scalar Aurora.Publication.Scalar.boolean) outcome (leftEvents ++ rightEvents)
  expression_callArgumentsFault : ∀ {leaf : RuntimeSourceFunction}
      {context : RuntimeExprContext} {name : Name} {state : RuntimeLocals} {sources : List SourceExpr} {fault : Fault}
      {events : List RuntimeSourceEvent},
      leaf ∈ functions →
        leaf.Resolves context name →
          Arguments context state sources leaf.parameters (Outcome.trap fault) events →
            Expression context state (SourceExpr.call (Callee.named name) sources) leaf.result
              (Outcome.trap fault) events
  expression_callValue : ∀ {leaf : RuntimeSourceFunction}
      {context : RuntimeExprContext} {name : Name} {state : RuntimeLocals} {sources : List SourceExpr} {values : List Value}
      {argumentEvents : List RuntimeSourceEvent} {after : LocalContext} {value : Value} {finished : RuntimeLocals}
      {bodyEvents : List RuntimeSourceEvent},
      leaf ∈ functions →
        leaf.Resolves context name →
          Arguments context state sources leaf.parameters (Outcome.value values)
              argumentEvents →
            Statements leaf.context.members leaf.context.module leaf.context.path
                leaf.context.formals leaf.result
                { visible := [], scope := 0, nextScope := 1, nextSlot := leaf.context.formals.length }
                (formalSourceLocals leaf.parameters fun index => values[index]?) leaf.parsed.statements after
                (RuntimeBodyOutcome.returned value finished) bodyEvents →
              Expression context state (SourceExpr.call (Callee.named name) sources) leaf.result
                (Outcome.value value)
                (argumentEvents ++ [RuntimeSourceEvent.invoke leaf.key values] ++ bodyEvents ++
                  [RuntimeSourceEvent.returned leaf.key value])
  expression_callFault : ∀ {leaf : RuntimeSourceFunction}
      {context : RuntimeExprContext} {name : Name} {state : RuntimeLocals} {sources : List SourceExpr} {values : List Value}
      {argumentEvents : List RuntimeSourceEvent} {after : LocalContext} {fault : Fault} {finished : RuntimeLocals}
      {bodyEvents : List RuntimeSourceEvent},
      leaf ∈ functions →
        leaf.Resolves context name →
          Arguments context state sources leaf.parameters (Outcome.value values)
              argumentEvents →
            Statements leaf.context.members leaf.context.module leaf.context.path
                leaf.context.formals leaf.result
                { visible := [], scope := 0, nextScope := 1, nextSlot := leaf.context.formals.length }
                (formalSourceLocals leaf.parameters fun index => values[index]?) leaf.parsed.statements after
                (RuntimeBodyOutcome.trapped fault finished) bodyEvents →
              Expression context state (SourceExpr.call (Callee.named name) sources) leaf.result
                (Outcome.trap fault) (argumentEvents ++ [RuntimeSourceEvent.invoke leaf.key values] ++ bodyEvents)
  arguments_nil : ∀ {context : RuntimeExprContext}
      {state : RuntimeLocals}, Arguments context state [] [] (Outcome.value []) []
  arguments_fault : ∀ {context : RuntimeExprContext}
      {state : RuntimeLocals} {first : SourceExpr} {kind : RuntimeType} {fault : Fault} {events : List RuntimeSourceEvent}
      {rest : List SourceExpr} {kinds : List RuntimeType},
      Expression context state first kind (Outcome.trap fault) events →
        Arguments context state (first :: rest) (kind :: kinds) (Outcome.trap fault) events
  arguments_cons : ∀ {context : RuntimeExprContext}
      {state : RuntimeLocals} {first : SourceExpr} {kind : RuntimeType} {value : Value}
      {firstEvents : List RuntimeSourceEvent} {rest : List SourceExpr} {kinds : List RuntimeType}
      {outcome : Outcome (List Value)} {restEvents : List RuntimeSourceEvent},
      Expression context state first kind (Outcome.value value) firstEvents →
        Arguments context state rest kinds outcome restEvents →
          Arguments context state (first :: rest) (kind :: kinds)
            (outcome.then fun values => Outcome.value (value :: values)) (firstEvents ++ restEvents)
  statement_declarationFault : ∀
      {members : List Declaration} {module path : Name} {formals : List Formal} {before : LocalContext} {raw : SourceExpr}
      {after : LocalContext} {binding : SourceLocal} {state : RuntimeLocals} {fault : Fault}
      {events : List RuntimeSourceEvent} {result : RuntimeType} {declaration : Formal},
      ScopedStatement members module path formals before (SourceStatement.localDecl declaration raw) after [binding] →
        Expression (runtimeStatementContext members module path formals before) state raw binding.kind
            (Outcome.trap fault) events →
          Statement members module path formals result before state
            (SourceStatement.localDecl declaration raw) after (RuntimeBodyOutcome.trapped fault state) events
  statement_declarationValue : ∀
      {members : List Declaration} {module path : Name} {formals : List Formal} {before : LocalContext} {raw : SourceExpr}
      {after : LocalContext} {binding : SourceLocal} {state : RuntimeLocals} {value : Value}
      {events : List RuntimeSourceEvent} {next : RuntimeLocals} {result : RuntimeType} {declaration : Formal},
      ScopedStatement members module path formals before (SourceStatement.localDecl declaration raw) after [binding] →
        Expression (runtimeStatementContext members module path formals before) state raw binding.kind
            (Outcome.value value) events →
          state.initialize binding.slot binding.runtimeDeclaration value = some next →
            Statement members module path formals result before state
              (SourceStatement.localDecl declaration raw) after (RuntimeBodyOutcome.continued next) events
  statement_assignmentFault : ∀ {binding : SourceLocal}
      {name : ByteArray} {members : List Declaration} {module path : Name} {formals : List Formal} {before : LocalContext}
      {state : RuntimeLocals} {raw : SourceExpr} {fault : Fault} {events : List RuntimeSourceEvent} {result : RuntimeType},
      binding ∈ before.visible →
        binding.name = name →
          binding.mutable = true →
            Expression (runtimeStatementContext members module path formals before) state raw
                binding.kind (Outcome.trap fault) events →
              Statement members module path formals result before state
                (SourceStatement.assign name raw) before (RuntimeBodyOutcome.trapped fault state) events
  statement_assignmentValue : ∀ {binding : SourceLocal}
      {name : ByteArray} {members : List Declaration} {module path : Name} {formals : List Formal} {before : LocalContext}
      {state : RuntimeLocals} {raw : SourceExpr} {value : Value} {events : List RuntimeSourceEvent} {next : RuntimeLocals}
      {result : RuntimeType},
      binding ∈ before.visible →
        binding.name = name →
          binding.mutable = true →
            Expression (runtimeStatementContext members module path formals before) state raw
                binding.kind (Outcome.value value) events →
              state.assign binding.slot value = some next →
                Statement members module path formals result before state
                  (SourceStatement.assign name raw) before (RuntimeBodyOutcome.continued next) events
  statement_returnFault : ∀ {members : List Declaration}
      {module path : Name} {formals : List Formal} {before : LocalContext} {state : RuntimeLocals} {raw : SourceExpr}
      {result : RuntimeType} {fault : Fault} {events : List RuntimeSourceEvent},
      Expression (runtimeStatementContext members module path formals before) state raw result
          (Outcome.trap fault) events →
        Statement members module path formals result before state
          (SourceStatement.returnValue raw) before (RuntimeBodyOutcome.trapped fault state) events
  statement_returnValue : ∀ {members : List Declaration}
      {module path : Name} {formals : List Formal} {before : LocalContext} {state : RuntimeLocals} {raw : SourceExpr}
      {result : RuntimeType} {value : Value} {events : List RuntimeSourceEvent},
      Expression (runtimeStatementContext members module path formals before) state raw result
          (Outcome.value value) events →
        Statement members module path formals result before state
          (SourceStatement.returnValue raw) before (RuntimeBodyOutcome.returned value state) events
  statement_branchFault : ∀ {members : List Declaration}
      {module path : Name} {formals : List Formal} {before : LocalContext} {body : List SourceStatement}
      {child : LocalContext} {declaredItems : List SourceLocal} {state : RuntimeLocals} {condition : SourceExpr}
      {fault : Fault} {events : List RuntimeSourceEvent} {result : RuntimeType},
      ScopedStatements members module path formals (enterLocalScope before) body child declaredItems →
        Expression (runtimeStatementContext members module path formals before) state condition
            (RuntimeType.scalar Aurora.Publication.Scalar.boolean) (Outcome.trap fault) events →
          Statement members module path formals result before state
            (SourceStatement.ifThen condition body) (leaveLocalScope before child) (RuntimeBodyOutcome.trapped fault state)
            events
  statement_branchFalse : ∀ {members : List Declaration}
      {module path : Name} {formals : List Formal} {before : LocalContext} {body : List SourceStatement}
      {child : LocalContext} {declaredItems : List SourceLocal} {state : RuntimeLocals} {condition : SourceExpr}
      {events : List RuntimeSourceEvent} {next : RuntimeLocals} {result : RuntimeType},
      ScopedStatements members module path formals (enterLocalScope before) body child declaredItems →
        Expression (runtimeStatementContext members module path formals before) state condition
            (RuntimeType.scalar Aurora.Publication.Scalar.boolean) (Outcome.value (Value.boolean false)) events →
          state.reserveScopes child.nextScope = some next →
            Statement members module path formals result before state
              (SourceStatement.ifThen condition body) (leaveLocalScope before child) (RuntimeBodyOutcome.continued next)
              events
  statement_branchTrueContinue : ∀
      {members : List Declaration} {module path : Name} {formals : List Formal} {before : LocalContext}
      {body : List SourceStatement} {child : LocalContext} {declaredItems : List SourceLocal} {state : RuntimeLocals}
      {condition : SourceExpr} {firstEvents : List RuntimeSourceEvent} {entered : RuntimeLocals} {result : RuntimeType}
      {finished : RuntimeLocals} {bodyEvents : List RuntimeSourceEvent} {next : RuntimeLocals},
      ScopedStatements members module path formals (enterLocalScope before) body child declaredItems →
        Expression (runtimeStatementContext members module path formals before) state condition
            (RuntimeType.scalar Aurora.Publication.Scalar.boolean) (Outcome.value (Value.boolean true)) firstEvents →
          state.enterAt before.nextScope = some entered →
            Statements members module path formals result (enterLocalScope before) entered
                body child (RuntimeBodyOutcome.continued finished) bodyEvents →
              finished.leave.reserveScopes child.nextScope = some next →
                Statement members module path formals result before state
                  (SourceStatement.ifThen condition body) (leaveLocalScope before child) (RuntimeBodyOutcome.continued next)
                  (firstEvents ++ bodyEvents)
  statement_branchTrueReturn : ∀
      {members : List Declaration} {module path : Name} {formals : List Formal} {before : LocalContext}
      {body : List SourceStatement} {child : LocalContext} {declaredItems : List SourceLocal} {state : RuntimeLocals}
      {condition : SourceExpr} {firstEvents : List RuntimeSourceEvent} {entered : RuntimeLocals} {result : RuntimeType}
      {value : Value} {finished : RuntimeLocals} {bodyEvents : List RuntimeSourceEvent},
      ScopedStatements members module path formals (enterLocalScope before) body child declaredItems →
        Expression (runtimeStatementContext members module path formals before) state condition
            (RuntimeType.scalar Aurora.Publication.Scalar.boolean) (Outcome.value (Value.boolean true)) firstEvents →
          state.enterAt before.nextScope = some entered →
            Statements members module path formals result (enterLocalScope before) entered
                body child (RuntimeBodyOutcome.returned value finished) bodyEvents →
              Statement members module path formals result before state
                (SourceStatement.ifThen condition body) (leaveLocalScope before child)
                (RuntimeBodyOutcome.returned value finished) (firstEvents ++ bodyEvents)
  statement_branchTrueFault : ∀
      {members : List Declaration} {module path : Name} {formals : List Formal} {before : LocalContext}
      {body : List SourceStatement} {child : LocalContext} {declaredItems : List SourceLocal} {state : RuntimeLocals}
      {condition : SourceExpr} {firstEvents : List RuntimeSourceEvent} {entered : RuntimeLocals} {result : RuntimeType}
      {fault : Fault} {finished : RuntimeLocals} {bodyEvents : List RuntimeSourceEvent},
      ScopedStatements members module path formals (enterLocalScope before) body child declaredItems →
        Expression (runtimeStatementContext members module path formals before) state condition
            (RuntimeType.scalar Aurora.Publication.Scalar.boolean) (Outcome.value (Value.boolean true)) firstEvents →
          state.enterAt before.nextScope = some entered →
            Statements members module path formals result (enterLocalScope before) entered
                body child (RuntimeBodyOutcome.trapped fault finished) bodyEvents →
              Statement members module path formals result before state
                (SourceStatement.ifThen condition body) (leaveLocalScope before child)
                (RuntimeBodyOutcome.trapped fault finished) (firstEvents ++ bodyEvents)
  statements_nil : ∀ {members : List Declaration}
      {module path : Name} {formals : List Formal} {result : RuntimeType} {before : LocalContext} {state : RuntimeLocals},
      Statements members module path formals result before state [] before
        (RuntimeBodyOutcome.continued state) []
  statements_next : ∀ {members : List Declaration}
      {module path : Name} {formals : List Formal} {result : RuntimeType} {before : LocalContext} {state : RuntimeLocals}
      {first : SourceStatement} {middle : LocalContext} {next : RuntimeLocals} {firstEvents : List RuntimeSourceEvent}
      {rest : List SourceStatement} {after : LocalContext} {outcome : RuntimeBodyOutcome}
      {restEvents : List RuntimeSourceEvent},
      Statement members module path formals result before state first middle
          (RuntimeBodyOutcome.continued next) firstEvents →
        Statements members module path formals result middle next rest after outcome
            restEvents →
          Statements members module path formals result before state (first :: rest) after
            outcome (firstEvents ++ restEvents)
  statements_returned : ∀ {members : List Declaration}
      {module path : Name} {formals : List Formal} {result : RuntimeType} {before : LocalContext} {state : RuntimeLocals}
      {first : SourceStatement} {middle : LocalContext} {value : Value} {final : RuntimeLocals}
      {events : List RuntimeSourceEvent} {rest : List SourceStatement} {after : LocalContext}
      {declaredItems : List SourceLocal},
      Statement members module path formals result before state first middle
          (RuntimeBodyOutcome.returned value final) events →
        ScopedStatements members module path formals middle rest after declaredItems →
          Statements members module path formals result before state (first :: rest) after
            (RuntimeBodyOutcome.returned value final) events
  statements_trapped : ∀ {members : List Declaration}
      {module path : Name} {formals : List Formal} {result : RuntimeType} {before : LocalContext} {state : RuntimeLocals}
      {first : SourceStatement} {middle : LocalContext} {fault : Fault} {final : RuntimeLocals}
      {events : List RuntimeSourceEvent} {rest : List SourceStatement} {after : LocalContext}
      {declaredItems : List SourceLocal},
      Statement members module path formals result before state first middle
          (RuntimeBodyOutcome.trapped fault final) events →
        ScopedStatements members module path formals middle rest after declaredItems →
          Statements members module path formals result before state (first :: rest) after
            (RuntimeBodyOutcome.trapped fault final) events

end Aurora.SourceBinding
