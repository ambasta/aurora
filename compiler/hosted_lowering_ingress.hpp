#pragma once
#include "hosted_ir_metadata.hpp"
#include "hosted_frontend_abi.hpp"
#include "../runtime/hosted_bytes.hpp"

namespace aurora::ir::detail {
// Private allocation/fill capsule for the successful source lowering projection.
// It grants only pending raw storage to the one closed source fill operation;
// no destination owner, descriptor or mutable handle escapes to the caller.
class LoweringIngress final {
    MetadataIngress metadata_;
    std::unique_ptr<Instructions> instructions_;
    bool started_ = false;
    bool complete_ = false;
    void allocateMetadata(const hosted_abi::compiler_ir_metadata::InputCounts &counts,
                          std::int64_t callableCount,
                          std::int64_t slotCount,
                          std::int64_t instructionBegin,
                          hosted::bytes::Allocator allocator);
    void *metadataOwner();

public:
    static std::int64_t measure(const void *session,
                                void *workspace,
                                std::int64_t root,
                                std::int64_t diagnostic,
                                hosted::bytes::Allocator allocator = hosted::bytes::system_allocator());
    LoweringIngress(const hosted_abi::compiler_ir_metadata::InputCounts &metadata,
                    std::int64_t callableCount,
                    std::int64_t slotCount,
                    std::int64_t instructionBegin,
                    const hosted_abi::compiler_ir_instructions::InstructionCounts &instructions,
                    hosted::bytes::Allocator allocator = hosted::bytes::system_allocator());
    ~LoweringIngress();
    LoweringIngress(const LoweringIngress &) = delete;
    LoweringIngress &operator=(const LoweringIngress &) = delete;
    void fill(const void *session, void *workspace);
    InstructionIngress take() &&;
};
} // namespace aurora::ir::detail
