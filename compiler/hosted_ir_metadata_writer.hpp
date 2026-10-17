#pragma once
#include "hosted_ir_metadata.hpp"
#include "hosted_frontend_abi.hpp"
#include <map>
#include <string>

namespace aurora::ir::detail {
// One copied source table is shared by both native ingress paths and readers.
const hosted_abi::compiler_ir_metadata::FlagMasks &metadataFlagMasks();
// Closed bootstrap writer: count one walk, allocate the existing owner, then
// repeat that walk into its exact raw prefixes. It never publishes a view.
class MetadataWriter {
    using Counts = hosted_abi::compiler_ir_metadata::InputCounts;
    MetadataIngress pending_;
    Counts position_{};
    std::int64_t callableCount_ = 0;
    std::int64_t slotCount_ = 0;
    std::int64_t instructionBegin_ = -1;
    bool allocated_ = false;
    // Exact owned keys live only during each writer pass, never in Metadata.
    std::map<std::string, hosted_abi::compiler_ir_metadata::ByteRange, std::less<>> textRanges_;
    void type(std::int64_t position, const Type &value);

public:
    const Counts &position() const {
        return position_;
    }
    std::int64_t callableCount() const {
        return callableCount_;
    }
    std::int64_t slotCount() const {
        return slotCount_;
    }
    void allocate();
    void project(const void *plan);
    void declarations(const Module &module);
    void beginInstructions();
    std::int64_t instructionType(const Type &value);
    hosted_abi::compiler_ir_metadata::ByteRange text(std::string_view value);
    void leaf(const Type &value);
    void callableType(const Type &value);
    std::int64_t slotType(const Type &value);
    void field(const ClassField &value);
    void index(std::int64_t value);
    void append(const hosted_abi::compiler_ir_metadata::ClassRow &value);
    void append(const hosted_abi::compiler_ir_metadata::StorageRow &value);
    void append(const hosted_abi::compiler_ir_metadata::DescriptorRow &value);
    void append(const hosted_abi::compiler_ir_metadata::ViewRow &value);
    void append(const hosted_abi::compiler_ir_metadata::EnumRow &value);
    void append(const hosted_abi::compiler_ir_metadata::CallableRow &value);
    void append(const hosted_abi::compiler_ir_metadata::SlotRow &value);
    MetadataIngress take() &&;
};
} // namespace aurora::ir::detail
