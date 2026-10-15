#pragma once
#include "ir.hpp"
#include "hosted_ir_metadata_writer.hpp"
#include "ir_instruction_codec.hpp"
#include <bit>

namespace aurora::ir {
// An immovable capsule. Views survive moves of the unique owner in a validated
// module; source mutation is confined to admission and CFG/entry normalization.
class Instructions final {
    class State;
    class ReadCursor;
    std::unique_ptr<State> state_;
    Instructions();
    const void *sourceOwner(const Metadata &metadata) const;
    friend class ::aurora::X86Emitter;
    void admit(const Metadata &metadata);
    void structure();
    void publish();
    InstructionObservation read(InstructionId id, bool checkPayload = false) const;
    std::size_t bodySize(Metadata::CallableId callable) const;
    InstructionId codeId(Metadata::CallableId callable, CodePosition position) const;
    InstructionFlow codeFlow(Metadata::CallableId callable, CodePosition position) const;
    InstructionObservation bodyInstruction(Metadata::CallableId callable, InstructionId id) const;
    int offsetAt(std::size_t index) const;
    ServiceArgument serviceAt(std::size_t index) const;
    BorrowedRootArgument rootAt(std::size_t index) const;
    unsigned char literalAt(std::size_t index) const;
    OffsetRange offsets(std::size_t begin, std::size_t count) const;
    ServiceArgumentRange services(std::size_t begin, std::size_t count) const;
    BorrowedRootArgumentRange roots(std::size_t begin, std::size_t count) const;
    LiteralRange literals(std::size_t begin, std::size_t count) const;
    friend class InstructionRange;
    friend class InstructionIngress;
    friend class detail::InstructionWriter;
    template <class> friend class InstructionPayloadRange;
    friend ValidatedModule validate(InstructionIngress pending, verification::Metrics *metrics);

public:
    ~Instructions();
    Instructions(const Instructions &) = delete;
    Instructions &operator=(const Instructions &) = delete;
    Instructions(Instructions &&) = delete;
    Instructions &operator=(Instructions &&) = delete;
    std::size_t bodyCount() const;
    InstructionRange range(Metadata::CallableId callable) const;
};

namespace detail {
// The writer walks the same codec twice, first counting exact storage, then
// filling it. It never admits rows, exposes owner descriptors or stores payloads.
class InstructionWriter final {
    using Counts = hosted_abi::compiler_ir_instructions::InstructionCounts;
    using Row = hosted_abi::compiler_ir_instructions::RawInstructionRow;
    using Operand = hosted_abi::compiler_ir_instructions::RawOperandRow;
    MetadataWriter &metadata_;
    std::unique_ptr<Instructions> instructions_;
    Counts position_{};
    std::int64_t bodyBegin_ = 0;
    bool inBody_ = false;
    bool allocated_ = false;
    static std::int64_t count(std::size_t value);
    static std::int64_t add(std::int64_t left, std::int64_t right);
    void operand(std::int64_t at, const Operand &value);
    void literal(std::int64_t at, unsigned char value);
    void instruction(const Row &value);
    class Cursor {
        InstructionWriter &writer_;
        bool measuring_;
        Row row_{};
        std::int64_t prefix_ = 0, nested_ = 0, prefixLimit_ = 0;
        void emit(Operand value);
        void scalar(OperandRole role, std::int64_t value);
        void name(OperandRole role, const std::string &value);
        void slice(OperandRole role, std::int64_t begin, std::int64_t count);

    public:
        Cursor(InstructionWriter &writer, bool measuring, std::int64_t prefixLimit = 0);
        std::int64_t prefixCount() const {
            return prefix_;
        }
        void form(InstructionForm value);
        void finish();
        void integer(OperandRole role, const int &value);
        void boolean(OperandRole role, const bool &value);
        void type(OperandRole role, const Type &value);
        void callee(const std::string &value);
        void className(const std::string &value);
        void moduleScope(const int &value);
        void serviceKind(const service::Kind &value);
        void serviceOperation(const service::Operation &value);
        void unary(const Unary &value);
        void binary(const Binary &value);
        void comparison(const Comparison &value);
        void query(const Query &value);
        void constant(const std::int64_t &value, const Type &type);
        template <class Payload> void offsets(OperandRole role, const Payload &values) {
            const auto size = count(values.size());
            const auto begin = add(add(row_.operandBegin, prefixLimit_), nested_);
            const auto nextNested = add(nested_, size);
            (void)add(begin, size);
            slice(role, begin, size);
            if (!measuring_) {
                std::int64_t at = begin;
                for (const auto value : values) {
                    Operand row{};
                    row.operandRole = static_cast<std::int64_t>(OperandRole::Offset);
                    row.signedValue = value;
                    writer_.operand(at++, row);
                }
            }
            nested_ = nextNested;
        }
        template <class Payload> void services(const Payload &values) {
            const auto size = add(count(values.size()), count(values.size()));
            const auto begin = add(add(row_.operandBegin, prefixLimit_), nested_);
            const auto nextNested = add(nested_, size);
            (void)add(begin, size);
            slice(OperandRole::AdditionalServices, begin, size);
            if (!measuring_) {
                std::int64_t at = begin;
                for (const auto value : values) {
                    Operand row{};
                    row.operandRole = static_cast<std::int64_t>(OperandRole::ServiceLoanId);
                    row.signedValue = value.loanId;
                    writer_.operand(at++, row);
                    row.operandRole = static_cast<std::int64_t>(OperandRole::ServiceKindId);
                    row.signedValue = static_cast<std::int64_t>(value.kind);
                    writer_.operand(at++, row);
                }
            }
            nested_ = nextNested;
        }
        template <class Payload> void roots(const Payload &values) {
            const auto size = add(count(values.size()), count(values.size()));
            const auto begin = add(add(row_.operandBegin, prefixLimit_), nested_);
            const auto nextNested = add(nested_, size);
            (void)add(begin, size);
            slice(OperandRole::BorrowedRoots, begin, size);
            if (!measuring_) {
                std::int64_t at = begin;
                for (const auto value : values) {
                    Operand row{};
                    row.operandRole = static_cast<std::int64_t>(OperandRole::Root);
                    row.signedValue = value.root;
                    writer_.operand(at++, row);
                    row.operandRole = static_cast<std::int64_t>(OperandRole::LoanId);
                    row.signedValue = value.loanId;
                    writer_.operand(at++, row);
                }
            }
            nested_ = nextNested;
        }
        template <class Payload> void literal(const Payload &values) {
            const auto size = count(values.size());
            const auto begin = writer_.position_.literalCount;
            const auto end = add(begin, size);
            slice(OperandRole::LiteralBytes, begin, size);
            if (!measuring_) {
                if (writer_.allocated_) {
                    std::int64_t at = begin;
                    for (const auto value : values)
                        writer_.literal(at++, value);
                }
                writer_.position_.literalCount = end;
            }
        }
    };

public:
    explicit InstructionWriter(MetadataWriter &metadata) : metadata_(metadata) {
    }
    void beginBody(std::size_t callableId);
    void endBody();
    void allocate();
    template <class Variant> void append(const Variant &value) {
        Cursor measure(*this, true);
        writeInstruction(value, measure);
        Cursor write(*this, false, measure.prefixCount());
        writeInstruction(value, write);
    }
    InstructionIngress take() &&;
};
} // namespace detail
} // namespace aurora::ir
