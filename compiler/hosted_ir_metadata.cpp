#include "hosted_ir_metadata_writer.hpp"
#include "ir.hpp"
#include "../runtime/hosted_bytes.hpp"
#include <algorithm>
#include <array>
#include <cstring>
#include <limits>
#include <span>
#include <type_traits>

extern "C" {
void aurora_hosted_metadata_create(const void *, void *) noexcept;
void aurora_hosted_metadata_release(void *) noexcept;
std::int64_t aurora_hosted_metadata_allocated(const void *) noexcept;
std::int64_t aurora_hosted_metadata_run(void *) noexcept;
std::int64_t aurora_hosted_metadata_error(const void *) noexcept;
}

namespace aurora::ir {
namespace {
namespace wire = hosted_abi::compiler_ir_metadata;
namespace bytes = hosted::bytes;
[[noreturn]] void invalidTransport() {
    throw Error(DiagnosticCode::Internal, "invalid hosted IR metadata transport");
}
[[noreturn]] void allocationFailure() {
    throw Error(DiagnosticCode::Internal, "hosted IR metadata allocation failed");
}
std::int64_t count(std::size_t value) {
    if (value > static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max()))
        invalidTransport();
    return static_cast<std::int64_t>(value);
}
std::int64_t add(std::int64_t left, std::int64_t right) {
    if (left < 0 || right < 0 || left > std::numeric_limits<std::int64_t>::max() - right)
        invalidTransport();
    return left + right;
}
std::size_t index(std::int64_t value) {
    if (value < 0 || static_cast<std::uint64_t>(value) > std::numeric_limits<std::size_t>::max())
        invalidTransport();
    return static_cast<std::size_t>(value);
}
int integer(std::int64_t value) {
    if (value < std::numeric_limits<int>::min() || value > std::numeric_limits<int>::max())
        invalidTransport();
    return static_cast<int>(value);
}
void checkIndex(std::size_t value, std::size_t extent) {
    if (value >= extent)
        throw std::out_of_range("IR metadata index");
}
void checkRange(std::size_t begin, std::size_t size, std::size_t extent) {
    if (begin > extent || size > extent - begin)
        invalidTransport();
}
void checkSubrange(std::size_t begin, std::size_t size, std::size_t extent) {
    if (begin > extent || size > extent - begin)
        throw std::out_of_range("IR metadata subrange");
}

// This closed binding is reviewed bootstrap machinery. The predecessor supplies
// physical owner-field/row facts, but does not claim to export element identity.
// No caller can choose a field offset, copied row type, or byte stride.
enum class Pool : std::size_t {
    bytes,
    types,
    classes,
    fields,
    storage,
    indices,
    descriptors,
    views,
    enums,
    callables,
    results,
    frames,
    count
};
struct Binding {
    std::size_t offset, ownerBytes, stride;
};
constexpr std::array bindings{
    Binding{hosted_abi::metadataStore_bytesOffset, hosted_abi::metadataStore_bytesBytes, 1},
    Binding{hosted_abi::metadataStore_typesOffset,
            hosted_abi::metadataStore_typesBytes,
            hosted_abi::metadataRawTypeRowPhysicalBytes},
    Binding{hosted_abi::metadataStore_classesOffset,
            hosted_abi::metadataStore_classesBytes,
            hosted_abi::metadataClassRowPhysicalBytes},
    Binding{hosted_abi::metadataStore_fieldsOffset,
            hosted_abi::metadataStore_fieldsBytes,
            hosted_abi::metadataFieldRowPhysicalBytes},
    Binding{hosted_abi::metadataStore_storageOffset,
            hosted_abi::metadataStore_storageBytes,
            hosted_abi::metadataStorageRowPhysicalBytes},
    Binding{hosted_abi::metadataStore_indicesOffset,
            hosted_abi::metadataStore_indicesBytes,
            hosted_abi::metadataIndexRowPhysicalBytes},
    Binding{hosted_abi::metadataStore_descriptorsOffset,
            hosted_abi::metadataStore_descriptorsBytes,
            hosted_abi::metadataDescriptorRowPhysicalBytes},
    Binding{hosted_abi::metadataStore_viewsOffset,
            hosted_abi::metadataStore_viewsBytes,
            hosted_abi::metadataViewRowPhysicalBytes},
    Binding{hosted_abi::metadataStore_enumsOffset,
            hosted_abi::metadataStore_enumsBytes,
            hosted_abi::metadataEnumRowPhysicalBytes},
    Binding{hosted_abi::metadataStore_callablesOffset,
            hosted_abi::metadataStore_callablesBytes,
            hosted_abi::metadataCallableRowPhysicalBytes},
    Binding{hosted_abi::metadataStore_resultsOffset,
            hosted_abi::metadataStore_resultsBytes,
            hosted_abi::metadataClassResultRowPhysicalBytes},
    Binding{hosted_abi::metadataStore_framesOffset,
            hosted_abi::metadataStore_framesBytes,
            hosted_abi::metadataFrameRowPhysicalBytes},
};
template <Pool> struct Row;
template <> struct Row<Pool::types> {
    using Type = wire::RawTypeRow;
};
template <> struct Row<Pool::classes> {
    using Type = wire::ClassRow;
};
template <> struct Row<Pool::fields> {
    using Type = wire::FieldRow;
};
template <> struct Row<Pool::storage> {
    using Type = wire::StorageRow;
};
template <> struct Row<Pool::indices> {
    using Type = wire::IndexRow;
};
template <> struct Row<Pool::descriptors> {
    using Type = wire::DescriptorRow;
};
template <> struct Row<Pool::views> {
    using Type = wire::ViewRow;
};
template <> struct Row<Pool::enums> {
    using Type = wire::EnumRow;
};
template <> struct Row<Pool::callables> {
    using Type = wire::CallableRow;
};
template <> struct Row<Pool::results> {
    using Type = wire::ClassResultRow;
};
template <> struct Row<Pool::frames> {
    using Type = wire::FrameRow;
};
template <Pool pool> using RowType = typename Row<pool>::Type;
static_assert(bindings.size() == static_cast<std::size_t>(Pool::count));
static_assert([] {
    for (std::size_t i = 0; i < bindings.size(); ++i) {
        const auto binding = bindings[i];
        if (binding.ownerBytes != sizeof(bytes::NativeOwner) ||
            binding.offset % alignof(bytes::NativeOwner) != 0 ||
            binding.offset > sizeof(wire::MetadataStore) ||
            binding.ownerBytes > sizeof(wire::MetadataStore) - binding.offset)
            return false;
        for (std::size_t j = 0; j < i; ++j)
            if (binding.offset < bindings[j].offset + bindings[j].ownerBytes &&
                bindings[j].offset < binding.offset + binding.ownerBytes)
                return false;
    }
    return true;
}());
template <Pool pool> constexpr bool exactRow =
    std::is_standard_layout_v<RowType<pool>> && std::is_trivially_copyable_v<RowType<pool>> &&
    alignof(RowType<pool>) == 8 && sizeof(RowType<pool>) % 8 == 0 &&
    sizeof(RowType<pool>) == bindings[static_cast<std::size_t>(pool)].stride;
static_assert(exactRow<Pool::types> && exactRow<Pool::classes> && exactRow<Pool::fields> &&
              exactRow<Pool::storage> && exactRow<Pool::indices> && exactRow<Pool::descriptors> &&
              exactRow<Pool::views> && exactRow<Pool::enums> && exactRow<Pool::callables> &&
              exactRow<Pool::results> && exactRow<Pool::frames>);

static_assert(static_cast<std::int64_t>(TypeKind::I64) ==
              static_cast<std::int64_t>(wire::MetadataTypeKind::I64));
static_assert(static_cast<std::int64_t>(TypeKind::Bool) ==
              static_cast<std::int64_t>(wire::MetadataTypeKind::Bool));
static_assert(static_cast<std::int64_t>(TypeKind::Own) ==
              static_cast<std::int64_t>(wire::MetadataTypeKind::Own));
static_assert(static_cast<std::int64_t>(TypeKind::Ref) ==
              static_cast<std::int64_t>(wire::MetadataTypeKind::Ref));
static_assert(static_cast<std::int64_t>(TypeKind::MutRef) ==
              static_cast<std::int64_t>(wire::MetadataTypeKind::MutRef));
static_assert(static_cast<std::int64_t>(TypeKind::Class) ==
              static_cast<std::int64_t>(wire::MetadataTypeKind::Class));
static_assert(static_cast<std::int64_t>(TypeKind::Array) ==
              static_cast<std::int64_t>(wire::MetadataTypeKind::Array));
static_assert(static_cast<std::int64_t>(TypeKind::U64) ==
              static_cast<std::int64_t>(wire::MetadataTypeKind::U64));
static_assert(static_cast<std::int64_t>(TypeKind::Parameter) ==
              static_cast<std::int64_t>(wire::MetadataTypeKind::Parameter));
static_assert(static_cast<std::int64_t>(TypeKind::Enum) ==
              static_cast<std::int64_t>(wire::MetadataTypeKind::Enum));
static_assert(static_cast<std::int64_t>(TypeKind::U8) ==
              static_cast<std::int64_t>(wire::MetadataTypeKind::U8));
static_assert(static_cast<std::int64_t>(TypeKind::ByteSpan) ==
              static_cast<std::int64_t>(wire::MetadataTypeKind::ByteSpan));
static_assert(static_cast<std::int64_t>(TypeKind::ByteRegion) ==
              static_cast<std::int64_t>(wire::MetadataTypeKind::ByteRegion));
static_assert(static_cast<std::int64_t>(TypeKind::OwnedBytes) ==
              static_cast<std::int64_t>(wire::MetadataTypeKind::OwnedBytes));
static_assert(static_cast<std::int64_t>(TypeKind::ConsoleSession) ==
              static_cast<std::int64_t>(wire::MetadataTypeKind::ConsoleSession));
static_assert(static_cast<std::int64_t>(TypeKind::DisplaySession) ==
              static_cast<std::int64_t>(wire::MetadataTypeKind::DisplaySession));
static_assert(static_cast<std::int64_t>(TypeKind::IommuEventSession) ==
              static_cast<std::int64_t>(wire::MetadataTypeKind::IommuEventSession));
static_assert(static_cast<std::int64_t>(TypeKind::OwnedValues) ==
              static_cast<std::int64_t>(wire::MetadataTypeKind::OwnedValues));

using Capacities = std::array<std::int64_t, static_cast<std::size_t>(Pool::count)>;
Capacities capacities(const wire::InputCounts &counts, std::int64_t callableCount) {
    const auto &core = counts.coreCounts;
    const auto &maps = counts.mapCounts;
    return {core.bytes,
            core.types,
            core.classes,
            add(core.fields, core.leaves),
            add(maps.storage, core.classes),
            add(maps.indices, add(core.fields, add(core.leaves, core.leaves))),
            maps.descriptors,
            maps.views,
            maps.enums,
            callableCount,
            core.classes,
            4};
}
std::uint64_t quota(const Capacities &capacities) {
    std::uint64_t total = 0;
    const auto maximum = static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max());
    for (std::size_t pool = 0; pool < capacities.size(); ++pool) {
        if (capacities[pool] < 0)
            invalidTransport();
        const auto rows = static_cast<std::uint64_t>(capacities[pool]);
        if (rows > (maximum - total) / bindings[pool].stride)
            invalidTransport();
        total += rows * bindings[pool].stride;
    }
    return total;
}
class SourceOwner {
    hosted_abi::MetadataRelease release_;

public:
    SourceOwner(std::uint64_t region, const wire::InputCounts &counts, std::int64_t callableCount) {
        release_.region = region;
        hosted_abi::MetadataCreate create;
        create.region = region;
        create.counts = counts;
        create.callableCount = callableCount;
        aurora_hosted_metadata_create(&create, data());
    }
    ~SourceOwner() {
        aurora_hosted_metadata_release(&release_);
    }
    SourceOwner(const SourceOwner &) = delete;
    SourceOwner &operator=(const SourceOwner &) = delete;
    void *data() {
        return release_.store.storage.data();
    }
    const void *data() const {
        return release_.store.storage.data();
    }
    bytes::NativeOwner descriptor(Pool pool) const {
        const auto offset = bindings[static_cast<std::size_t>(pool)].offset;
        bytes::NativeOwner observation;
        std::memcpy(&observation, release_.store.storage.data() + offset, sizeof(observation));
        return observation;
    }
};
} // namespace

class Metadata::State {
public:
    // Reverse destruction removes retained views, consumes the source owner,
    // then closes Region. This also covers every exceptional importer exit.
    bytes::Region region;
    SourceOwner owner;
    wire::InputCounts counts;
    Capacities capacities;
    std::array<std::span<const std::byte>, static_cast<std::size_t>(Pool::count)> pools;

    State(const wire::InputCounts &input, std::int64_t callableCount, const Capacities &limits)
        : region(quota(limits)), owner(region.id(), input, callableCount), counts(input), capacities(limits) {
    }
    template <Pool pool> void set(std::int64_t position, const RowType<pool> &value) {
        // Runtime set borrows this descriptor observation; it only changes the
        // checked allocation payload, never descriptor identity or ownership.
        auto descriptor = owner.descriptor(pool);
        if (bytes::__au_runtime_values_set(&descriptor,
                                          position,
                                          static_cast<std::int64_t>(sizeof(value)),
                                          &value) != 1)
            invalidTransport();
    }
    template <Pool pool> RowType<pool> row(std::size_t position) const {
        const auto data = pools[static_cast<std::size_t>(pool)];
        if (position >= data.size() / sizeof(RowType<pool>))
            invalidTransport();
        RowType<pool> value;
        std::memcpy(&value, data.data() + position * sizeof(value), sizeof(value));
        return value;
    }
    std::string_view text(wire::ByteRange range) const {
        const auto data = pools[static_cast<std::size_t>(Pool::bytes)];
        const auto begin = index(range.firstByte), size = index(range.byteCount);
        checkRange(begin, size, data.size());
        if (size == 0)
            return {};
        return {reinterpret_cast<const char *>(data.data() + begin), size};
    }
    void range(wire::IndexRange value, Pool pool) const {
        checkRange(index(value.firstIndex), index(value.indexCount), index(capacities[static_cast<std::size_t>(pool)]));
    }
};

Metadata::Metadata() = default;
Metadata::~Metadata() = default;
MetadataIngress::MetadataIngress() = default;
MetadataIngress::~MetadataIngress() = default;
MetadataIngress::MetadataIngress(MetadataIngress &&) noexcept = default;
MetadataIngress &MetadataIngress::operator=(MetadataIngress &&) noexcept = default;
std::unique_ptr<Metadata> MetadataIngress::finish() && {
    if (!state_)
        invalidTransport();
    std::unique_ptr<Metadata> metadata(new Metadata);
    metadata->state_ = std::move(state_);
    metadata->verify();
    metadata->publish();
    return metadata;
}

void detail::MetadataWriter::allocate() {
    if (allocated_)
        invalidTransport();
    pending_.state_ =
        std::make_unique<Metadata::State>(position_, callableCount_, capacities(position_, callableCount_));
    const auto allocated = aurora_hosted_metadata_allocated(pending_.state_->owner.data());
    if (allocated == 0)
        allocationFailure();
    if (allocated != 1)
        invalidTransport();
    allocated_ = true;
    position_ = {};
    callableCount_ = 0;
}
wire::ByteRange detail::MetadataWriter::text(std::string_view value) {
    wire::ByteRange range;
    range.firstByte = position_.coreCounts.bytes;
    range.byteCount = count(value.size());
    position_.coreCounts.bytes = add(range.firstByte, range.byteCount);
    if (allocated_) {
        if (!pending_.state_)
            invalidTransport();
        auto descriptor = pending_.state_->owner.descriptor(Pool::bytes);
        auto at = range.firstByte;
        for (unsigned char character : value)
            if (bytes::__au_runtime_bytes_set(&descriptor, at++, character) != 1)
                invalidTransport();
    }
    return range;
}
void detail::MetadataWriter::type(std::int64_t position, const Type &value) {
    wire::RawTypeRow row;
    row.typeKind = static_cast<std::int64_t>(value.kind);
    row.nameRange = text(value.className);
    row.rawTail.elementKind = static_cast<std::int64_t>(value.elementKind);
    row.rawTail.arrayLength = value.length;
    row.rawTail.elementParameterBytes = value.elementParameter.size();
    row.rawTail.lengthParameterBytes = value.lengthParameter.size();
    row.rawTail.templateArgumentCount = value.templateArguments.size();
    if (allocated_)
        pending_.state_->set<Pool::types>(position, row);
    position_.coreCounts.types = add(position_.coreCounts.types, 1);
}
void detail::MetadataWriter::callableType(const Type &value) {
    type(position_.coreCounts.types, value);
}
void detail::MetadataWriter::leaf(const Type &value) {
    type(position_.coreCounts.leaves, value);
    position_.coreCounts.leaves = add(position_.coreCounts.leaves, 1);
}
void detail::MetadataWriter::field(const ClassField &value) {
    if (allocated_ && !pending_.state_)
        invalidTransport();
    wire::FieldRow row;
    row.typeIndex = add(allocated_ ? pending_.state_->counts.coreCounts.leaves : 0, position_.coreCounts.fields);
    type(row.typeIndex, value.elementType);
    row.firstLeaf = value.firstLeaf;
    row.leafCount = value.length;
    row.arrayFlag = value.array;
    row.elementCount = value.elementCount;
    if (allocated_)
        pending_.state_->set<Pool::fields>(position_.coreCounts.fields, row);
    position_.coreCounts.fields = add(position_.coreCounts.fields, 1);
}
void detail::MetadataWriter::index(std::int64_t value) {
    wire::IndexRow row;
    row.indexValue = value;
    if (allocated_) {
        if (!pending_.state_)
            invalidTransport();
        pending_.state_->set<Pool::indices>(position_.mapCounts.indices, row);
    }
    position_.mapCounts.indices = add(position_.mapCounts.indices, 1);
}
void detail::MetadataWriter::append(const wire::ClassRow &value) {
    if (allocated_) {
        if (!pending_.state_)
            invalidTransport();
        pending_.state_->set<Pool::classes>(position_.coreCounts.classes, value);
    }
    position_.coreCounts.classes = add(position_.coreCounts.classes, 1);
}
void detail::MetadataWriter::append(const wire::StorageRow &value) {
    if (allocated_) {
        if (!pending_.state_)
            invalidTransport();
        pending_.state_->set<Pool::storage>(position_.mapCounts.storage, value);
    }
    position_.mapCounts.storage = add(position_.mapCounts.storage, 1);
}
void detail::MetadataWriter::append(const wire::DescriptorRow &value) {
    if (allocated_) {
        if (!pending_.state_)
            invalidTransport();
        pending_.state_->set<Pool::descriptors>(position_.mapCounts.descriptors, value);
    }
    position_.mapCounts.descriptors = add(position_.mapCounts.descriptors, 1);
}
void detail::MetadataWriter::append(const wire::ViewRow &value) {
    if (allocated_) {
        if (!pending_.state_)
            invalidTransport();
        pending_.state_->set<Pool::views>(position_.mapCounts.views, value);
    }
    position_.mapCounts.views = add(position_.mapCounts.views, 1);
}
void detail::MetadataWriter::append(const wire::EnumRow &value) {
    if (allocated_) {
        if (!pending_.state_)
            invalidTransport();
        pending_.state_->set<Pool::enums>(position_.mapCounts.enums, value);
    }
    position_.mapCounts.enums = add(position_.mapCounts.enums, 1);
}
void detail::MetadataWriter::append(const wire::CallableRow &value) {
    if (allocated_) {
        if (!pending_.state_)
            invalidTransport();
        pending_.state_->set<Pool::callables>(callableCount_, value);
    }
    callableCount_ = add(callableCount_, 1);
}
MetadataIngress detail::MetadataWriter::take() && {
    if (!allocated_ || !pending_.state_)
        invalidTransport();
    const auto &expected = pending_.state_->counts;
    if (capacities(position_, callableCount_) != pending_.state_->capacities ||
        position_.coreCounts.fields != expected.coreCounts.fields ||
        position_.coreCounts.leaves != expected.coreCounts.leaves ||
        position_.mapCounts.indices != expected.mapCounts.indices)
        invalidTransport();
    return std::move(pending_);
}

std::unique_ptr<Metadata> Metadata::import(const Module &module) {
    // Union membership preserves absent, empty and extra hostile map entries.
    std::vector<std::string_view> names;
    for (const auto &[name, value] : module.classLayouts) {
        (void)value;
        names.push_back(name);
    }
    for (const auto &[name, value] : module.classFields) {
        (void)value;
        names.push_back(name);
    }
    for (const auto &[name, value] : module.classStorage) {
        (void)value;
        names.push_back(name);
    }
    for (const auto &name : module.classArrayCarriers)
        names.push_back(name);
    std::sort(names.begin(), names.end());
    names.erase(std::unique(names.begin(), names.end()), names.end());
    detail::MetadataWriter writer;
    const auto copyIndices = [&](const auto &values) {
        wire::IndexRange range;
        range.firstIndex = writer.position().mapCounts.indices;
        range.indexCount = count(values.size());
        for (auto value : values)
            writer.index(value);
        return range;
    };
    for (int pass = 0; pass < 2; ++pass) {
        for (auto key : names) {
            const std::string name(key);
            wire::ClassRow row;
            row.nameRange = writer.text(name);
            row.leafRange.firstIndex = writer.position().coreCounts.leaves;
            row.fieldRange.firstIndex = writer.position().coreCounts.fields;
            row.suppliedStorage = -1;
            if (const auto entry = module.classLayouts.find(name); entry != module.classLayouts.end()) {
                row.membershipBits |= 1;
                row.leafRange.indexCount = count(entry->second.size());
                for (const auto &value : entry->second)
                    writer.leaf(value);
            }
            if (const auto entry = module.classFields.find(name); entry != module.classFields.end()) {
                row.membershipBits |= 2;
                row.fieldRange.indexCount = count(entry->second.size());
                for (const auto &value : entry->second)
                    writer.field(value);
            }
            if (const auto entry = module.classStorage.find(name); entry != module.classStorage.end()) {
                row.membershipBits |= 4;
                row.suppliedStorage = writer.position().mapCounts.storage;
                wire::StorageRow copied;
                copied.leafOffsetRange = copyIndices(entry->second.leafOffsets);
                copied.fieldOffsetRange = copyIndices(entry->second.fieldOffsets);
                copied.physicalExtent.sizeBytes = entry->second.sizeBytes;
                copied.physicalExtent.alignmentBytes = entry->second.alignment;
                copied.physicalExtent.reservedBytes = entry->second.reservedBytes;
                writer.append(copied);
            }
            if (module.classArrayCarriers.contains(name))
                row.membershipBits |= 8;
            writer.append(row);
        }
        for (const auto &[id, value] : module.descriptors) {
            wire::DescriptorRow row;
            row.descriptorId = id;
            row.sizeValue = value.size;
            row.publicFieldCount = value.publicFields;
            writer.append(row);
        }
        for (const auto &[scope, values] : module.descriptorViews) {
            wire::ViewRow row;
            row.moduleScope = scope;
            row.descriptorRange = copyIndices(values);
            writer.append(row);
        }
        for (const auto &[name, cases] : module.enumCases) {
            wire::EnumRow row;
            row.nameRange = writer.text(name);
            row.caseCount = cases;
            writer.append(row);
        }
        // Signatures remain raw until the source verifier admits the complete
        // capsule. Their types occupy one packed result-first range per ID.
        for (const auto &function : module.functions) {
            wire::CallableRow row;
            row.nameRange = writer.text(function.name);
            row.typeRange.firstIndex = writer.position().coreCounts.types;
            row.typeRange.indexCount = add(1, count(function.parameters.size()));
            row.moduleScope = function.moduleScope;
            writer.callableType(function.result);
            for (const auto &parameter : function.parameters)
                writer.callableType(parameter);
            const auto receiver = [&](const Receiver &value) {
                wire::ReceiverShape shape;
                shape.nameRange = writer.text(value.className);
                shape.flags = (value.mutableValue ? 1 : 0) | (value.constructor ? 2 : 0) |
                              (value.publicAccess ? 4 : 0);
                return shape;
            };
            if (function.receiver) {
                row.flags |= 1;
                row.receiver = receiver(*function.receiver);
            }
            if (function.borrowedParameter)
                row.flags |= 2;
            if (function.secondBorrowedParameter) {
                row.flags |= 4;
                row.secondReceiver = receiver(*function.secondBorrowedParameter);
            }
            if (function.receiverSpanField) {
                row.flags |= 8;
                row.receiverSpanField = *function.receiverSpanField;
            }
            writer.append(row);
        }
        // Source checks this sorted (name, stable ID) suffix independently.
        // Sorting never erases duplicate or malformed callable declarations.
        std::vector<std::size_t> callableIds(module.functions.size());
        for (std::size_t id = 0; id < callableIds.size(); ++id)
            callableIds[id] = id;
        std::sort(callableIds.begin(), callableIds.end(), [&](auto left, auto right) {
            const auto &a = module.functions[left].name;
            const auto &b = module.functions[right].name;
            return a < b || (a == b && left < right);
        });
        for (auto id : callableIds)
            writer.index(count(id));
        if (pass == 0)
            writer.allocate();
    }
    return std::move(writer).take().finish();
}
void Metadata::verify() {
    const auto status = aurora_hosted_metadata_run(state_->owner.data());
    const auto reason = aurora_hosted_metadata_error(state_->owner.data());
    if (status == static_cast<std::int64_t>(wire::MetadataStatus::allocation)) {
        if (reason != static_cast<std::int64_t>(wire::MetadataError::none))
            invalidTransport();
        allocationFailure();
    }
    if (status == static_cast<std::int64_t>(wire::MetadataStatus::invalid)) {
        const auto message = wire::metadataErrorMessage(static_cast<wire::MetadataError>(reason));
        if (reason == static_cast<std::int64_t>(wire::MetadataError::none) || message == nullptr)
            invalidTransport();
        throw Error(std::string(message));
    }
    if (status != static_cast<std::int64_t>(wire::MetadataStatus::success) ||
        reason != static_cast<std::int64_t>(wire::MetadataError::none))
        invalidTransport();
}

void Metadata::publish() {
    // The source has completed successfully and can never be called mutably
    // again. Observe each allocation once, with exact Region/length identity.
    for (std::size_t pool = 0; pool < bindings.size(); ++pool) {
        const auto data = state_->region.observeMetadataBytes(state_->owner.descriptor(static_cast<Pool>(pool)));
        const auto expected = index(state_->capacities[pool]) * bindings[pool].stride;
        if (data.size() != expected)
            invalidTransport();
        state_->pools[pool] = data;
    }
    const auto &counts = state_->counts;
    // These are transport checks on the published references and conversions,
    // not duplicate native validity/layout policy. Raw input-only tails and
    // source workspace never gain a public accessor.
    for (std::size_t id = 0; id < classCount(); ++id) {
        const auto raw = state_->row<Pool::classes>(id);
        (void)state_->text(raw.nameRange);
        checkRange(index(raw.leafRange.firstIndex), index(raw.leafRange.indexCount), index(counts.coreCounts.leaves));
        const auto result = state_->row<Pool::results>(id);
        state_->range(result.fieldRange, Pool::fields);
        if (result.canonicalStorage < counts.mapCounts.storage ||
            result.canonicalStorage >= state_->capacities[static_cast<std::size_t>(Pool::storage)])
            invalidTransport();
        const auto storage = state_->row<Pool::storage>(index(result.canonicalStorage));
        for (const auto range : {storage.leafOffsetRange, storage.fieldOffsetRange}) {
            state_->range(range, Pool::indices);
            if (range.firstIndex < counts.mapCounts.indices)
                invalidTransport();
            for (std::size_t i = 0; i < index(range.indexCount); ++i)
                (void)indexAt(index(range.firstIndex) + i);
        }
        (void)integer(storage.physicalExtent.sizeBytes);
        (void)integer(storage.physicalExtent.alignmentBytes);
        (void)integer(storage.physicalExtent.reservedBytes);
        for (std::size_t i = 0; i < index(result.fieldRange.indexCount); ++i) {
            const auto field = state_->row<Pool::fields>(index(result.fieldRange.firstIndex) + i);
            if (field.typeIndex < 0 || field.typeIndex >= counts.coreCounts.types)
                invalidTransport();
            (void)integer(field.firstLeaf);
            (void)integer(field.leafCount);
            (void)integer(field.elementCount);
            if (field.arrayFlag != 0 && field.arrayFlag != 1)
                invalidTransport();
        }
    }
    for (std::size_t i = 0; i < index(counts.coreCounts.types); ++i) {
        const auto type = state_->row<Pool::types>(i);
        (void)state_->text(type.nameRange);
        (void)integer(type.typeKind);
        (void)integer(type.rawTail.elementKind);
        (void)integer(type.rawTail.arrayLength);
    }
    for (std::size_t id = 0; id < callableCount(); ++id) {
        const auto row = state_->row<Pool::callables>(id);
        (void)state_->text(row.nameRange);
        checkRange(index(row.typeRange.firstIndex),
                   index(row.typeRange.indexCount),
                   index(counts.coreCounts.types));
        if (row.typeRange.indexCount == 0)
            invalidTransport();
        (void)integer(row.moduleScope);
        for (const auto shape : {row.receiver, row.secondReceiver})
            (void)state_->text(shape.nameRange);
        if ((row.flags & 8) != 0)
            (void)integer(row.receiverSpanField);
    }
    if (counts.mapCounts.indices < count(callableCount()))
        invalidTransport();
    const auto callableIndex = index(counts.mapCounts.indices - count(callableCount()));
    for (std::size_t i = 0; i < callableCount(); ++i)
        if (index(state_->row<Pool::indices>(callableIndex + i).indexValue) >= callableCount())
            invalidTransport();
    for (std::size_t i = 0; i < enumCount(); ++i) {
        const auto enumeration = state_->row<Pool::enums>(i);
        (void)state_->text(enumeration.nameRange);
        (void)integer(enumeration.caseCount);
    }
    for (std::size_t i = 0; i < scopeCount(); ++i) {
        const auto view = state_->row<Pool::views>(i);
        checkRange(index(view.descriptorRange.firstIndex),
                   index(view.descriptorRange.indexCount),
                   index(counts.mapCounts.indices));
        for (std::size_t j = 0; j < index(view.descriptorRange.indexCount); ++j)
            (void)indexAt(index(view.descriptorRange.firstIndex) + j);
    }
}

std::size_t Metadata::classCount() const noexcept {
    return static_cast<std::size_t>(state_->counts.coreCounts.classes);
}
Metadata::ClassId Metadata::classAt(std::size_t position) const {
    checkIndex(position, classCount());
    return position;
}
std::optional<Metadata::ClassId> Metadata::findClass(std::string_view name) const {
    std::size_t first = 0, last = classCount();
    while (first < last) {
        const auto middle = first + (last - first) / 2;
        const auto key = state_->text(state_->row<Pool::classes>(middle).nameRange);
        if (key < name)
            first = middle + 1;
        else
            last = middle;
    }
    if (first < classCount() && state_->text(state_->row<Pool::classes>(first).nameRange) == name)
        return first;
    return std::nullopt;
}
std::string Metadata::className(ClassId id) const {
    return std::string(state_->text(state_->row<Pool::classes>(classAt(id)).nameRange));
}
TypeRange Metadata::leaves(ClassId id) const {
    const auto range = state_->row<Pool::classes>(classAt(id)).leafRange;
    return {*this, index(range.firstIndex), index(range.indexCount)};
}
FieldRange Metadata::fields(ClassId id) const {
    const auto range = state_->row<Pool::results>(classAt(id)).fieldRange;
    return {*this, index(range.firstIndex), index(range.indexCount)};
}
StorageView Metadata::storage(ClassId id) const {
    const auto result = state_->row<Pool::results>(classAt(id));
    const auto row = state_->row<Pool::storage>(index(result.canonicalStorage));
    return {{*this, index(row.leafOffsetRange.firstIndex), index(row.leafOffsetRange.indexCount)},
            {*this, index(row.fieldOffsetRange.firstIndex), index(row.fieldOffsetRange.indexCount)},
            integer(row.physicalExtent.sizeBytes),
            integer(row.physicalExtent.alignmentBytes),
            integer(row.physicalExtent.reservedBytes)};
}
bool Metadata::isCarrier(ClassId id) const {
    return (state_->row<Pool::classes>(classAt(id)).membershipBits & 8) != 0;
}
bool Metadata::isOwning(ClassId id) const {
    for (const auto field : fields(id))
        if (field.elementType.isOwnerStorage())
            return true;
    return false;
}

std::size_t Metadata::enumCount() const noexcept {
    return static_cast<std::size_t>(state_->counts.mapCounts.enums);
}
Metadata::EnumId Metadata::enumAt(std::size_t position) const {
    checkIndex(position, enumCount());
    return position;
}
std::optional<Metadata::EnumId> Metadata::findEnum(std::string_view name) const {
    std::size_t first = 0, last = enumCount();
    while (first < last) {
        const auto middle = first + (last - first) / 2;
        const auto key = state_->text(state_->row<Pool::enums>(middle).nameRange);
        if (key < name)
            first = middle + 1;
        else
            last = middle;
    }
    if (first < enumCount() && state_->text(state_->row<Pool::enums>(first).nameRange) == name)
        return first;
    return std::nullopt;
}
std::string Metadata::enumName(EnumId id) const {
    return std::string(state_->text(state_->row<Pool::enums>(enumAt(id)).nameRange));
}
int Metadata::enumCases(EnumId id) const {
    return integer(state_->row<Pool::enums>(enumAt(id)).caseCount);
}

std::size_t Metadata::callableCount() const noexcept {
    return state_->pools[static_cast<std::size_t>(Pool::callables)].size() / sizeof(wire::CallableRow);
}
CallableView Metadata::callable(CallableId id) const {
    checkIndex(id, callableCount());
    return {*this, id};
}
std::optional<Metadata::CallableId> Metadata::findCallable(std::string_view name) const {
    const auto begin = index(state_->counts.mapCounts.indices - count(callableCount()));
    const auto callableId = [&](std::size_t at) {
        return index(state_->row<Pool::indices>(begin + at).indexValue);
    };
    std::size_t first = 0, last = callableCount();
    while (first < last) {
        const auto middle = first + (last - first) / 2;
        const auto key = state_->text(state_->row<Pool::callables>(callableId(middle)).nameRange);
        if (key < name)
            first = middle + 1;
        else
            last = middle;
    }
    if (first < callableCount()) {
        const auto id = callableId(first);
        if (state_->text(state_->row<Pool::callables>(id).nameRange) == name)
            return id;
    }
    return std::nullopt;
}
std::string CallableView::name() const {
    return std::string(metadata_->state_->text(metadata_->state_->row<Pool::callables>(id_).nameRange));
}
int CallableView::moduleScope() const {
    return integer(metadata_->state_->row<Pool::callables>(id_).moduleScope);
}
Type CallableView::result() const {
    const auto range = metadata_->state_->row<Pool::callables>(id_).typeRange;
    return metadata_->typeAt(index(range.firstIndex));
}
TypeRange CallableView::parameters() const {
    const auto range = metadata_->state_->row<Pool::callables>(id_).typeRange;
    return {*metadata_, index(range.firstIndex) + 1, index(range.indexCount) - 1};
}
std::optional<Receiver> CallableView::receiver() const {
    const auto row = metadata_->state_->row<Pool::callables>(id_);
    if ((row.flags & 1) == 0)
        return std::nullopt;
    const auto &shape = row.receiver;
    return Receiver{std::string(metadata_->state_->text(shape.nameRange)),
                    (shape.flags & 1) != 0,
                    (shape.flags & 2) != 0,
                    (shape.flags & 4) != 0};
}
bool CallableView::borrowedParameter() const {
    return (metadata_->state_->row<Pool::callables>(id_).flags & 2) != 0;
}
std::optional<Receiver> CallableView::secondBorrowedParameter() const {
    const auto row = metadata_->state_->row<Pool::callables>(id_);
    if ((row.flags & 4) == 0)
        return std::nullopt;
    const auto &shape = row.secondReceiver;
    return Receiver{std::string(metadata_->state_->text(shape.nameRange)),
                    (shape.flags & 1) != 0,
                    (shape.flags & 2) != 0,
                    (shape.flags & 4) != 0};
}
std::optional<int> CallableView::receiverSpanField() const {
    const auto row = metadata_->state_->row<Pool::callables>(id_);
    if ((row.flags & 8) == 0)
        return std::nullopt;
    return integer(row.receiverSpanField);
}

std::size_t Metadata::scopeCount() const noexcept {
    return static_cast<std::size_t>(state_->counts.mapCounts.views);
}
std::int64_t Metadata::scopeAt(std::size_t position) const {
    checkIndex(position, scopeCount());
    return state_->row<Pool::views>(position).moduleScope;
}
std::optional<std::size_t> Metadata::findScope(std::int64_t scope) const {
    std::size_t first = 0, last = scopeCount();
    while (first < last) {
        const auto middle = first + (last - first) / 2;
        if (scopeAt(middle) < scope)
            first = middle + 1;
        else
            last = middle;
    }
    if (first < scopeCount() && scopeAt(first) == scope)
        return first;
    return std::nullopt;
}
bool Metadata::hasScope(std::int64_t scope) const {
    return findScope(scope).has_value();
}
IndexRange Metadata::visibleDescriptors(std::int64_t scope) const {
    const auto found = findScope(scope);
    if (!found)
        throw std::out_of_range("IR metadata scope");
    const auto range = state_->row<Pool::views>(*found).descriptorRange;
    return {*this, index(range.firstIndex), index(range.indexCount)};
}
std::size_t Metadata::descriptorCount() const noexcept {
    return static_cast<std::size_t>(state_->counts.mapCounts.descriptors);
}
std::int64_t Metadata::descriptorIdAt(std::size_t position) const {
    checkIndex(position, descriptorCount());
    return state_->row<Pool::descriptors>(position).descriptorId;
}
Descriptor Metadata::descriptorAt(std::size_t position) const {
    checkIndex(position, descriptorCount());
    const auto row = state_->row<Pool::descriptors>(position);
    return {row.sizeValue, row.publicFieldCount};
}
std::optional<Descriptor> Metadata::findDescriptor(std::int64_t id) const {
    std::size_t first = 0, last = descriptorCount();
    while (first < last) {
        const auto middle = first + (last - first) / 2;
        if (descriptorIdAt(middle) < id)
            first = middle + 1;
        else
            last = middle;
    }
    if (first < descriptorCount() && descriptorIdAt(first) == id)
        return descriptorAt(first);
    return std::nullopt;
}

Type Metadata::typeAt(std::size_t position) const {
    const auto row = state_->row<Pool::types>(position);
    Type type(static_cast<TypeKind>(integer(row.typeKind)));
    type.className = state_->text(row.nameRange);
    type.elementKind = static_cast<TypeKind>(integer(row.rawTail.elementKind));
    type.length = integer(row.rawTail.arrayLength);
    // Aurora established that every accepted metadata Type has empty unresolved
    // parameter strings/arguments. Display spelling and resolution provenance
    // never participate in metadata equality, validation or backend layout.
    return type;
}
ClassField Metadata::fieldAt(std::size_t position) const {
    const auto row = state_->row<Pool::fields>(position);
    return {typeAt(index(row.typeIndex)),
            integer(row.firstLeaf),
            integer(row.leafCount),
            row.arrayFlag != 0,
            integer(row.elementCount)};
}
int Metadata::indexAt(std::size_t position) const {
    return integer(state_->row<Pool::indices>(position).indexValue);
}
Type TypeRange::at(std::size_t position) const {
    checkIndex(position, count_);
    return metadata_->typeAt(begin_ + position);
}
TypeRange TypeRange::subrange(std::size_t begin, std::size_t size) const {
    checkSubrange(begin, size, count_);
    auto result = *this;
    result.begin_ += begin;
    result.count_ = size;
    return result;
}
ClassField FieldRange::at(std::size_t position) const {
    checkIndex(position, count_);
    return metadata_->fieldAt(begin_ + position);
}
FieldRange FieldRange::subrange(std::size_t begin, std::size_t size) const {
    checkSubrange(begin, size, count_);
    auto result = *this;
    result.begin_ += begin;
    result.count_ = size;
    return result;
}
ClassField FieldRange::operator[](std::size_t position) const {
    return at(position);
}
ClassField FieldRange::front() const {
    return at(0);
}
ClassField FieldRange::back() const {
    return at(count_ - 1);
}
int IndexRange::at(std::size_t position) const {
    checkIndex(position, count_);
    return metadata_->indexAt(begin_ + position);
}
IndexRange IndexRange::subrange(std::size_t begin, std::size_t size) const {
    checkSubrange(begin, size, count_);
    auto result = *this;
    result.begin_ += begin;
    result.count_ = size;
    return result;
}
} // namespace aurora::ir
