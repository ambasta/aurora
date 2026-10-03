# Closed enums and composed method results

Milestone012 integrates the separately developed enum/decimal language slice with
the verified milestone011 value-composition baseline. This document describes the
milestone012 implementation. Independent compiler review and final kernel/parent
integration verification passed. The later u8/layout extension described in
BYTES.md remains a separately tested milestone013 candidate.
The earlier frozen checkout and its receipts remain separate evidence.

## Nominal enums and Value

A module or namespace can declare `enum class Status { ready, failed };`.
`Status::ready` is a named value of that exact nominal type. Enums support equality,
inequality, initialized local/field values, and function/method parameters and
results. There is no integer or boolean conversion, ordering, arithmetic,
explicit case ordinal, unspecified default value or source address conversion.
The graph permits at most 64 enum declarations, each with 1..256 unique cases.

Value explicitly accepts closed enum types as well as numeric/bool and named
concrete class types. At milestone012 Scalar was exactly i64/u64/bool; the
milestone013 development candidate adds u8 to both domains while retaining
enum exclusion from Scalar. Builtin arrays and
std::array continue to reject enum elements. Named enum arguments retain their
defining-module identity, so std::pair<Status,Report> is distinct from an otherwise
equal-layout pair using another enum. Nested template-id arguments, deduction,
function templates and recursive template instantiation remain unsupported.

Enum names and cases obey module visibility. Exported signatures, public member
signatures and template argument visibility include enum dependencies. A generated
template body may use its fixed instance and exact nominal arguments internally;
this does not import arbitrary names from the caller or widen runtime reflection
views. The same nominal identity is preserved in enum constants, slots, fields,
comparisons and calls through lowering.

Enum storage is eight bytes, size_of is eight and field_count is zero. Type IDs
are graph-local and allocated after the class descriptors. Existing programs
without enum declarations retain their descriptor behavior. Reflection does not
provide enumeration of case names, a runtime cast or an external serialization
contract.

## Complete copied method results

A method may return a complete named class local. Its caller must initialize a
fresh explicitly typed local from that call. This includes composed classes with
private array, enum and empty-class descendants. The result has independent
storage; changing the original receiver or the extracted copy cannot change the
other. Const receivers may return copies that the caller binds mutably.

All milestone011 construction rules remain: exact nominal class-field copies,
complete logical initialization including empty children, left-to-right readonly
constructor snapshots, acyclic containment, four class levels and 64 flattened
leaves for composed values. Class-valued method arguments remain unsupported.
Constructors still return the internal i64 status and have empty bodies; their
explicit class arguments remain supported.

A result call acquires receiver identity and evaluates explicit arguments before
making the new result binding visible. Returning a method call or receiver field
directly is still unsupported: first create a complete named local. Chained
mutation, source references to subobjects and implicit class-valued temporaries
remain outside this subset.

## Internal calling convention

MethodCall retains its objectArguments vector and adds a trailing resultOffset.
Constructor calls with class parameters use a receiver in R10 and packed argument
record in R11. Class-returning methods use a receiver in R10 and fresh result
destination in R11; their explicit arguments are scalar or enum register values.
These modes are mutually exclusive. The receiver and record/result are saved in
separate private frame slots before evaluating the body. Ordinary aggregate
functions retain their previous convention.

CopyObject, ObjectFieldCopy and InitializeObjectField retain recursive nominal
layout and logical-completion evidence. Result destinations must be exact, fresh
and separate from active inputs. ReturnObject copies a complete value. EnumConstant
retains a declared nominal enum and valid named case index; generic scalar
constants cannot create enum values. These mechanisms are compiler-private and do
not add a C ABI or source-visible pointers.

## Recoverable numeric library

`import std.decimal;` supplies DecimalStatus, DecimalAccumulator and DecimalResult.
A new accumulator is empty. push_digit(u64) accepts numeric digits 0..9; it is not a
text or Unicode parser. It reports invalid_digit for larger values and out_of_range
before a u64 value or the i64 accepted-digit counter could overflow. Leading zeros
are accepted and counted. Errors are sticky until reset(), which returns empty.

finish() const returns an independent DecimalResult. status() reports success,
empty, invalid_digit or out_of_range. position() is the number of accepted digits,
which is the first error's zero-based position. value_or(fallback) returns the
parsed value only on success; its fallback expression is evaluated eagerly.
Accumulator-produced error reports initialize the unused numeric slot to zero.
The public DecimalResult constructor creates an explicit report, not a certificate
that parsing occurred. There is no error-payload accessor.

`library/examples/enum_composition.au` combines an enum/class pair, a nested
DecimalResult constructor copy, a class-valued method and independent accumulator
reset, returning 42. Compact character/byte types, UTF-8 and public text storage
contracts, plus genuine active-alternative expected/optional values, remain future
work. No heap or host parsing routine is used by this library.

## Validation and resource limits

The compiler gate includes historical composition cases, the decimal model suite,
new combined source cases and direct IR enum/result cases. Coverage distinguishes
source execution, ordinary rejection, lower-level IR rejection and exact trap
observations. Counts and final artifact hashes belong to the completed receipt;
these tests are not a formal proof or a performance claim.

The scalar oracle's explicit --sanitized-compiler mode omits only compiler
RLIMIT_AS assignment for sanitizer shadow mappings. Native programs and toolchain
commands retain 512 MiB address-space limits; timeouts, CPU limits and regular-file
size limits are unchanged. Captured stdout/stderr pipes have no explicit byte or
memory cap. Instrumented compiler runs do not establish resource or performance
bounds. Global compiler budgets and compact verifier fact storage remain separate
hardening work.

## Reviewed compiler evidence

The frozen compiler passes the complete release and ASan/UBSan compiler targets:
207 source, 74 constructor/method, 59 value-call, 117 template, 216 fixed-container,
161 composition, 196 decimal and 107 combined enum/composition cases; 84 signed
and 95 unsigned cases; both numeric oracles; 592 direct IR cases (529 preserved
and 63 added), ten exhaustive controls, and native IR groups of 18 array, eight
composition and 13 enum/method-result checks. Module, depth and source/artifact
adapter suites also pass. Scalar oracles pass 630 default and 1,526 stress cases
on release and sanitized builds, plus nine runner selftests; 64 baseline/candidate
equivalence cases pass. Model steps and alternate seeds overlap this coverage.

Independent compiler review reports no reproduced defect: combined 107, decimal 196
and 64 additional ABI cases pass both frozen builds; sanitized composition 161,
direct IR 592 and all native/exhaustive groups pass. Final parent/kernel receipts
remain separate. Historical method-result rejection fixtures were deliberately
migrated to typed-copy success or the still-required named-local return rule.
