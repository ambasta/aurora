#pragma once
#include "hosted_ir_metadata.hpp"
#include "hosted_frontend_abi.hpp"

namespace aurora::ir::detail {
// Closed bootstrap writer: count one walk, allocate the existing owner, then
// repeat that walk into its exact raw prefixes. It never publishes a view.
class MetadataWriter {
    using Counts = hosted_abi::compiler_ir_metadata::InputCounts;
    MetadataIngress pending_;
    Counts position_{};
    bool allocated_ = false;
    void type(std::int64_t position, const Type &value);

public:
    const Counts &position() const {
        return position_;
    }
    void allocate();
    hosted_abi::compiler_ir_metadata::ByteRange text(std::string_view value);
    void leaf(const Type &value);
    void field(const ClassField &value);
    void index(std::int64_t value);
    void append(const hosted_abi::compiler_ir_metadata::ClassRow &value);
    void append(const hosted_abi::compiler_ir_metadata::StorageRow &value);
    void append(const hosted_abi::compiler_ir_metadata::DescriptorRow &value);
    void append(const hosted_abi::compiler_ir_metadata::ViewRow &value);
    void append(const hosted_abi::compiler_ir_metadata::EnumRow &value);
    MetadataIngress take() &&;
};
} // namespace aurora::ir::detail
