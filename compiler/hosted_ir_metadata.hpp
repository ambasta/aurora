#pragma once

#include "types.hpp"
#include <cstddef>
#include <cstdint>
#include <iterator>
#include <memory>
#include <optional>
#include <string_view>
#include <type_traits>
#include <vector>

namespace aurora::ir {
class Module;
class ClassField;
class Descriptor;
class Metadata;
class FunctionBody;
class Receiver;
class ObjectSlot;
class CallableView;
class FrameView;
namespace verification {
class Metrics;
}
class ValidatedModule;
class MetadataIngress;
class InstructionIngress;
class Instructions;
namespace detail {
class MetadataWriter;
class InstructionWriter;
}

// All ranges borrow the immovable Metadata capsule. Dereferencing copies a
// value; neither a payload pointer nor an Aurora owner escapes this interface.
template <class Range> class MetadataIterator {
    Range range_;
    std::size_t index_ = 0;

public:
    using value_type = typename Range::value_type;
    using difference_type = std::ptrdiff_t;
    using iterator_category = std::input_iterator_tag;
    using reference = value_type;
    using pointer = void;
    MetadataIterator() = default;
    MetadataIterator(Range range, std::size_t index) : range_(range), index_(index) {
    }
    value_type operator*() const {
        // Map-like slot views reserve at() for keyed lookup.
        if constexpr (requires { range_.itemAt(index_); })
            return range_.itemAt(index_);
        else
            return range_.at(index_);
    }
    MetadataIterator &operator++() {
        ++index_;
        return *this;
    }
    MetadataIterator operator++(int) {
        auto previous = *this;
        ++*this;
        return previous;
    }
    bool operator==(const MetadataIterator &) const = default;
};

class TypeRange {
    const Metadata *metadata_ = nullptr;
    std::size_t begin_ = 0, count_ = 0;
    TypeRange(const Metadata &metadata, std::size_t begin, std::size_t count)
        : metadata_(&metadata), begin_(begin), count_(count) {
    }
    friend class Metadata;
    friend class CallableView;

public:
    using value_type = Type;
    TypeRange() = default;
    std::size_t size() const noexcept {
        return count_;
    }
    bool empty() const noexcept {
        return count_ == 0;
    }
    Type at(std::size_t index) const;
    TypeRange subrange(std::size_t begin, std::size_t count) const;
    Type operator[](std::size_t index) const {
        return at(index);
    }
    Type front() const {
        return at(0);
    }
    Type back() const {
        return at(count_ - 1);
    }
    auto begin() const {
        return MetadataIterator<TypeRange>(*this, 0);
    }
    auto end() const {
        return MetadataIterator<TypeRange>(*this, count_);
    }
    bool operator==(const TypeRange &) const = default;
};

class FieldRange {
    const Metadata *metadata_ = nullptr;
    std::size_t begin_ = 0, count_ = 0;
    FieldRange(const Metadata &metadata, std::size_t begin, std::size_t count)
        : metadata_(&metadata), begin_(begin), count_(count) {
    }
    friend class Metadata;

public:
    using value_type = ClassField;
    FieldRange() = default;
    std::size_t size() const noexcept {
        return count_;
    }
    bool empty() const noexcept {
        return count_ == 0;
    }
    ClassField at(std::size_t index) const;
    FieldRange subrange(std::size_t begin, std::size_t count) const;
    ClassField operator[](std::size_t index) const;
    ClassField front() const;
    ClassField back() const;
    auto begin() const {
        return MetadataIterator<FieldRange>(*this, 0);
    }
    auto end() const {
        return MetadataIterator<FieldRange>(*this, count_);
    }
    bool operator==(const FieldRange &) const = default;
};

class IndexRange {
    const Metadata *metadata_ = nullptr;
    std::size_t begin_ = 0, count_ = 0;
    IndexRange(const Metadata &metadata, std::size_t begin, std::size_t count)
        : metadata_(&metadata), begin_(begin), count_(count) {
    }
    friend class Metadata;

public:
    using value_type = int;
    IndexRange() = default;
    std::size_t size() const noexcept {
        return count_;
    }
    bool empty() const noexcept {
        return count_ == 0;
    }
    int at(std::size_t index) const;
    IndexRange subrange(std::size_t begin, std::size_t count) const;
    int operator[](std::size_t index) const {
        return at(index);
    }
    int front() const {
        return at(0);
    }
    int back() const {
        return at(count_ - 1);
    }
    auto begin() const {
        return MetadataIterator<IndexRange>(*this, 0);
    }
    auto end() const {
        return MetadataIterator<IndexRange>(*this, count_);
    }
    bool operator==(const IndexRange &) const = default;
};

class StorageView {
public:
    IndexRange leafOffsets;
    IndexRange fieldOffsets;
    int sizeBytes = 0;
    int alignment = 1;
    int reservedBytes = 0;
};

// Frame declarations are sorted source-owned rows. These small views borrow
// their admitted range; lookup and iteration copy only the requested value.
class SlotRange {
    const Metadata *metadata_ = nullptr;
    std::size_t begin_ = 0, count_ = 0;
    SlotRange(const Metadata &metadata, std::size_t begin, std::size_t count)
        : metadata_(&metadata), begin_(begin), count_(count) {
    }
    friend class FrameView;

protected:
    int offsetAt(std::size_t index) const;
    Type typeAt(std::size_t index) const;
    int lengthAt(std::size_t index) const;
    bool mutableAt(std::size_t index) const;
    std::size_t position(int offset) const;

public:
    SlotRange() = default;
    std::size_t size() const noexcept {
        return count_;
    }
    bool empty() const noexcept {
        return count_ == 0;
    }
    bool contains(int offset) const {
        return position(offset) != size();
    }
    bool operator==(const SlotRange &) const = default;
};

template <class Value> class SlotMapRange : public SlotRange {
    explicit SlotMapRange(SlotRange range) : SlotRange(range) {
    }
    friend class FrameView;
    Value valueAt(std::size_t index) const {
        if constexpr (std::is_same_v<Value, Type>)
            return typeAt(index);
        else if constexpr (std::is_same_v<Value, int>)
            return lengthAt(index);
        else if constexpr (std::is_same_v<Value, bool>)
            return mutableAt(index);
        else if constexpr (std::is_same_v<Value, std::string>)
            return typeAt(index).className;
        else
            return Value{typeAt(index).className, mutableAt(index)};
    }

public:
    using value_type = std::pair<int, Value>;
    SlotMapRange() = default;
    Value at(int offset) const {
        const auto found = position(offset);
        if (found == size())
            throw std::out_of_range("IR frame slot");
        return valueAt(found);
    }
    value_type itemAt(std::size_t index) const {
        return {offsetAt(index), valueAt(index)};
    }
    auto begin() const {
        return MetadataIterator<SlotMapRange>(*this, 0);
    }
    auto end() const {
        return MetadataIterator<SlotMapRange>(*this, size());
    }
    bool operator==(const SlotMapRange &) const = default;
};

class SlotSetRange : public SlotRange {
    explicit SlotSetRange(SlotRange range) : SlotRange(range) {
    }
    friend class FrameView;

public:
    using value_type = int;
    SlotSetRange() = default;
    int itemAt(std::size_t index) const {
        return offsetAt(index);
    }
    auto begin() const {
        return MetadataIterator<SlotSetRange>(*this, 0);
    }
    auto end() const {
        return MetadataIterator<SlotSetRange>(*this, size());
    }
    bool operator==(const SlotSetRange &) const = default;
};

class FrameView {
    const Metadata *metadata_ = nullptr;
    std::size_t id_ = 0;
    FrameView(const Metadata &metadata, std::size_t id) : metadata_(&metadata), id_(id) {
    }
    SlotRange range(std::int64_t kind) const;
    friend class Metadata;

public:
    int frameBytes() const;
    SlotMapRange<Type> scalarSlots() const;
    SlotMapRange<ObjectSlot> objectSlots() const;
    SlotMapRange<int> arraySlots() const;
    SlotSetRange spanSlots() const;
    SlotSetRange serviceSlots() const;
    SlotSetRange regionSlots() const;
    SlotMapRange<bool> byteSlots() const;
    SlotMapRange<std::string> ownedValueTypes() const;
};

// A borrowed callable identity. Every accessor reads the admitted owner; no
// signature payload is retained in native function bodies.
class CallableView {
    const Metadata *metadata_ = nullptr;
    std::size_t id_ = 0;
    CallableView(const Metadata &metadata, std::size_t id) : metadata_(&metadata), id_(id) {
    }
    friend class Metadata;

public:
    std::string name() const;
    int moduleScope() const;
    Type result() const;
    TypeRange parameters() const;
    std::optional<Receiver> receiver() const;
    bool borrowedParameter() const;
    std::optional<Receiver> secondBorrowedParameter() const;
    std::optional<int> receiverSpanField() const;
    FrameView frame() const;
};

class Metadata final {
public:
    using ClassId = std::size_t;
    using EnumId = std::size_t;
    using CallableId = std::size_t;
    // Hostile fixtures import raw maps. Production supplies a pending owning
    // ingress; both paths independently verify before publishing any view.
    static std::unique_ptr<Metadata> import(const Module &module);
    ~Metadata();
    Metadata(const Metadata &) = delete;
    Metadata &operator=(const Metadata &) = delete;
    Metadata(Metadata &&) = delete;
    Metadata &operator=(Metadata &&) = delete;

    std::size_t classCount() const noexcept;
    ClassId classAt(std::size_t index) const;
    std::optional<ClassId> findClass(std::string_view name) const;
    std::string className(ClassId id) const;
    TypeRange leaves(ClassId id) const;
    FieldRange fields(ClassId id) const;
    StorageView storage(ClassId id) const;
    bool isCarrier(ClassId id) const;
    bool isOwning(ClassId id) const;

    std::size_t enumCount() const noexcept;
    EnumId enumAt(std::size_t index) const;
    std::optional<EnumId> findEnum(std::string_view name) const;
    std::string enumName(EnumId id) const;
    int enumCases(EnumId id) const;

    std::size_t callableCount() const noexcept;
    CallableView callable(CallableId id) const;
    FrameView frame(CallableId id) const;
    std::optional<CallableId> findCallable(std::string_view name) const;

    std::size_t scopeCount() const noexcept;
    std::int64_t scopeAt(std::size_t index) const;
    bool hasScope(std::int64_t scope) const;
    IndexRange visibleDescriptors(std::int64_t scope) const;
    std::size_t descriptorCount() const noexcept;
    std::int64_t descriptorIdAt(std::size_t index) const;
    Descriptor descriptorAt(std::size_t index) const;
    std::optional<Descriptor> findDescriptor(std::int64_t id) const;

private:
    class State;
    std::unique_ptr<State> state_;
    Metadata();
    void verify();
    void publish();
    Type typeAt(std::size_t index) const;
    Type instructionTypeAt(std::size_t index) const;
    std::string instructionText(std::size_t begin, std::size_t count) const;
    const void *sourceOwner() const noexcept;
    friend class Instructions;
    friend class InstructionIngress;
    ClassField fieldAt(std::size_t index) const;
    int indexAt(std::size_t index) const;
    std::optional<std::size_t> findScope(std::int64_t scope) const;
    friend class MetadataIngress;
    friend class detail::MetadataWriter;
    friend class detail::InstructionWriter;
    friend class TypeRange;
    friend class FieldRange;
    friend class IndexRange;
    friend class CallableView;
    friend class FrameView;
    friend class SlotRange;
};
// An opaque, move-only raw owner. Only validate can consume it to run the
// independent symbol, module, callable and frame checks before publishing views.
class MetadataIngress final {
    std::unique_ptr<Metadata::State> state_;
    std::unique_ptr<Metadata> finish() &&;
    friend class Metadata;
    friend class detail::MetadataWriter;
    friend class InstructionIngress;
    friend class detail::InstructionWriter;
    friend ValidatedModule validate(InstructionIngress pending, verification::Metrics *metrics);

public:
    MetadataIngress();
    ~MetadataIngress();
    MetadataIngress(const MetadataIngress &) = delete;
    MetadataIngress &operator=(const MetadataIngress &) = delete;
    MetadataIngress(MetadataIngress &&) noexcept;
    MetadataIngress &operator=(MetadataIngress &&) noexcept;
};

// Metadata and executable storage have one construction/admission identity.
// The bundle cannot be paired with a separately admitted metadata capsule.
class InstructionIngress final {
    MetadataIngress metadata_;
    std::unique_ptr<Instructions> instructions_;
    friend class detail::InstructionWriter;
    friend ValidatedModule validate(InstructionIngress pending, verification::Metrics *metrics);

public:
    InstructionIngress();
    ~InstructionIngress();
    InstructionIngress(const InstructionIngress &) = delete;
    InstructionIngress &operator=(const InstructionIngress &) = delete;
    InstructionIngress(InstructionIngress &&) noexcept;
    InstructionIngress &operator=(InstructionIngress &&) noexcept;
    static InstructionIngress import(Module module);
};
} // namespace aurora::ir
