#include "hosted_ir_metadata.hpp"
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
              exactRow<Pool::views> && exactRow<Pool::enums> && exactRow<Pool::results> && exactRow<Pool::frames>);

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
Capacities capacities(const wire::InputCounts &counts) {
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
    SourceOwner(std::uint64_t region, const wire::InputCounts &counts) {
        release_.region = region;
        hosted_abi::MetadataCreate create;
        create.region = region;
        create.counts = counts;
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

    State(const wire::InputCounts &input, const Capacities &limits)
        : region(quota(limits)), owner(region.id(), input), counts(input), capacities(limits) {
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
std::unique_ptr<Metadata> Metadata::import(const Module &module) {
    std::unique_ptr<Metadata> metadata(new Metadata);
    metadata->ingest(module);
    metadata->publish();
    return metadata;
}

void Metadata::ingest(const Module &module) {
    // Only ephemeral key references are sorted. There is no retained native
    // metadata map or second normalized metadata payload.
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
    wire::InputCounts counts;
    auto &core = counts.coreCounts;
    auto &maps = counts.mapCounts;
    core.classes = count(names.size());
    maps.storage = count(module.classStorage.size());
    maps.descriptors = count(module.descriptors.size());
    maps.views = count(module.descriptorViews.size());
    maps.enums = count(module.enumCases.size());
    for (auto name : names)
        core.bytes = add(core.bytes, count(name.size()));
    for (const auto &[name, leaves] : module.classLayouts) {
        (void)name;
        core.leaves = add(core.leaves, count(leaves.size()));
        for (const auto &type : leaves)
            core.bytes = add(core.bytes, count(type.className.size()));
    }
    for (const auto &[name, fields] : module.classFields) {
        (void)name;
        core.fields = add(core.fields, count(fields.size()));
        for (const auto &field : fields)
            core.bytes = add(core.bytes, count(field.elementType.className.size()));
    }
    core.types = add(core.leaves, core.fields);
    for (const auto &[name, storage] : module.classStorage) {
        (void)name;
        maps.indices = add(maps.indices, add(count(storage.leafOffsets.size()), count(storage.fieldOffsets.size())));
    }
    for (const auto &[scope, descriptors] : module.descriptorViews) {
        (void)scope;
        maps.indices = add(maps.indices, count(descriptors.size()));
    }
    for (const auto &[name, cases] : module.enumCases) {
        (void)cases;
        core.bytes = add(core.bytes, count(name.size()));
    }
    const auto limits = capacities(counts);
    state_ = std::make_unique<State>(counts, limits);
    const auto allocated = aurora_hosted_metadata_allocated(state_->owner.data());
    if (allocated == 0)
        allocationFailure();
    if (allocated != 1)
        invalidTransport();
    std::int64_t byte = 0, leaf = 0, field = 0, storage = 0, integerIndex = 0;
    auto byteDescriptor = state_->owner.descriptor(Pool::bytes);
    const auto copyText = [&](std::string_view value) {
        wire::ByteRange range;
        range.firstByte = byte;
        range.byteCount = count(value.size());
        for (unsigned char character : value)
            if (bytes::__au_runtime_bytes_set(&byteDescriptor, byte++, character) != 1)
                invalidTransport();
        return range;
    };
    const auto copyType = [&](std::int64_t position, const Type &type) {
        wire::RawTypeRow row;
        row.typeKind = static_cast<std::int64_t>(type.kind);
        row.nameRange = copyText(type.className);
        row.rawTail.elementKind = static_cast<std::int64_t>(type.elementKind);
        row.rawTail.arrayLength = type.length;
        row.rawTail.elementParameterBytes = type.elementParameter.size();
        row.rawTail.lengthParameterBytes = type.lengthParameter.size();
        row.rawTail.templateArgumentCount = type.templateArguments.size();
        state_->set<Pool::types>(position, row);
    };
    const auto copyIndices = [&](const auto &values) {
        wire::IndexRange range;
        range.firstIndex = integerIndex;
        range.indexCount = count(values.size());
        for (auto value : values) {
            wire::IndexRow row;
            row.indexValue = value;
            state_->set<Pool::indices>(integerIndex++, row);
        }
        return range;
    };
    for (std::size_t classIndex = 0; classIndex < names.size(); ++classIndex) {
        const std::string name(names[classIndex]);
        wire::ClassRow row;
        row.nameRange = copyText(name);
        row.leafRange.firstIndex = leaf;
        row.fieldRange.firstIndex = field;
        row.suppliedStorage = -1;
        if (const auto entry = module.classLayouts.find(name); entry != module.classLayouts.end()) {
            row.membershipBits |= 1;
            row.leafRange.indexCount = count(entry->second.size());
            for (const auto &type : entry->second)
                copyType(leaf++, type);
        }
        if (const auto entry = module.classFields.find(name); entry != module.classFields.end()) {
            row.membershipBits |= 2;
            row.fieldRange.indexCount = count(entry->second.size());
            for (const auto &value : entry->second) {
                wire::FieldRow copied;
                copied.typeIndex = add(core.leaves, field);
                copyType(copied.typeIndex, value.elementType);
                copied.firstLeaf = value.firstLeaf;
                copied.leafCount = value.length;
                copied.arrayFlag = value.array;
                copied.elementCount = value.elementCount;
                state_->set<Pool::fields>(field++, copied);
            }
        }
        if (const auto entry = module.classStorage.find(name); entry != module.classStorage.end()) {
            row.membershipBits |= 4;
            row.suppliedStorage = storage;
            wire::StorageRow copied;
            copied.leafOffsetRange = copyIndices(entry->second.leafOffsets);
            copied.fieldOffsetRange = copyIndices(entry->second.fieldOffsets);
            copied.physicalExtent.sizeBytes = entry->second.sizeBytes;
            copied.physicalExtent.alignmentBytes = entry->second.alignment;
            copied.physicalExtent.reservedBytes = entry->second.reservedBytes;
            state_->set<Pool::storage>(storage++, copied);
        }
        if (module.classArrayCarriers.contains(name))
            row.membershipBits |= 8;
        state_->set<Pool::classes>(count(classIndex), row);
    }
    std::int64_t descriptor = 0;
    for (const auto &[id, value] : module.descriptors) {
        wire::DescriptorRow row;
        row.descriptorId = id;
        row.sizeValue = value.size;
        row.publicFieldCount = value.publicFields;
        state_->set<Pool::descriptors>(descriptor++, row);
    }
    std::int64_t view = 0;
    for (const auto &[scope, values] : module.descriptorViews) {
        wire::ViewRow row;
        row.moduleScope = scope;
        row.descriptorRange = copyIndices(values);
        state_->set<Pool::views>(view++, row);
    }
    std::int64_t enumeration = 0;
    for (const auto &[name, cases] : module.enumCases) {
        wire::EnumRow row;
        row.nameRange = copyText(name);
        row.caseCount = cases;
        state_->set<Pool::enums>(enumeration++, row);
    }
    if (byte != core.bytes || leaf != core.leaves || field != core.fields || storage != maps.storage ||
        integerIndex != maps.indices || descriptor != maps.descriptors || view != maps.views ||
        enumeration != maps.enums)
        invalidTransport();
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
