// API unit tests of the validated IR owners, metadata views, ingress writers
// and the emitter object. Plain accept/reject/emit cases are textual IR data in
// tests/compiler/ir; the modules here are loaded from those case files.
#include "../tools/air_cases.hpp"
#include "hosted_ir_instructions.hpp"
#include "hosted_ir_metadata_writer.hpp"
#include "hosted_resolver.hpp"
#include "ir_verify.hpp"
#include "json_fragments.hpp"
#include "x86.hpp"
#include <algorithm>
#include <functional>
#include <iostream>
#include <limits>
#include <string>
#include <type_traits>

using namespace aurora;
using namespace aurora::ir;
using aurora::test::jsonMember;
using aurora::test::jsonMemberCount;
// The public span record width is part of the private span ABI.
static_assert(spanBytes == 56);
namespace {
int passed = 0;
std::string root;
void require(bool condition, const std::string &message) {
    if (!condition)
        throw Error(message);
}
void diagnosticMismatch(const std::string &name, const std::string &expected, const Error &error, bool exact) {
    throw Error("IR " + name + ": expected " + (exact ? "exact " : "containing ") + expected +
                "; actual: " + error.what());
}
Module load(const std::string &file, const std::string &name) {
    return aurora::test::air::loadCase(root + "/" + file, name);
}
Module baseline() {
    return load("ir-tests/core.air", "typed load/store");
}
Module receiverBaseline() {
    return load("ir-tests/core.air", "constructor, const object and receiver forwarding");
}
Module spanBaseline() {
    return load("ir-tests/spans.air", "readonly local byte span and reborrow");
}
Module packedMethodModule() {
    return load("ir-tests/packed-storage.air", "packed bytes preserve composed receiver/results and tiny aggregate");
}
Module moving() {
    return load("owning-classes-ir/layout.air", "literal two-descriptor layout");
}
bool storageMatches(StorageView actual, const ClassStorage &expected) {
    return actual.sizeBytes == expected.sizeBytes && actual.alignment == expected.alignment &&
           actual.reservedBytes == expected.reservedBytes &&
           std::equal(actual.leafOffsets.begin(),
                      actual.leafOffsets.end(),
                      expected.leafOffsets.begin(),
                      expected.leafOffsets.end()) &&
           std::equal(actual.fieldOffsets.begin(),
                      actual.fieldOffsets.end(),
                      expected.fieldOffsets.begin(),
                      expected.fieldOffsets.end());
}
void instructionOwnerTests() {
    static_assert(!std::is_copy_constructible_v<InstructionIngress> &&
                  std::is_nothrow_move_constructible_v<InstructionIngress> &&
                  std::is_nothrow_move_assignable_v<InstructionIngress>);
    auto source = baseline();
    aurora::ir::Function literal;
    literal.name = "literal_second";
    literal.result = Type::U8;
    literal.frameBytes = 64;
    literal.spanSlots = {56};
    literal.code = {Jump{7},
                    Label{6},
                    Jump{7},
                    Label{7},
                    BorrowLiteralSpan{{0, 42, 255}, 56},
                    Constant{1, Type::I64},
                    SpanLoad{56},
                    EndSpan{56},
                    Return{}};
    source.functions.push_back(std::move(literal));
    auto checked = validate(source);
    const auto code = checked.get().functions.at(1).code;
    const auto id = code.idAt(2);
    const auto observation = code.instructionById(id);
    const auto bytes = std::get<BorrowLiteralSpanObservation>(observation).bytes;
    source = Module{};
    auto moved = std::move(checked);
    auto replacement = validate(baseline());
    replacement = std::move(moved);
    if (id != 9 || code.size() != 7 || code.idAt(2) != id || bytes.size() != 3 || bytes[0] != 0 || bytes[1] != 42 ||
        bytes[2] != 255 || replacement.get().functions.at(1).code.idAt(2) != id ||
        code.flowAt(0).target != CodePosition{1} || code.flowAt(0).fallsThrough || !code.flowAt(1).blockEntry ||
        !code.flowAt(1).fallsThrough || replacement.get().functions.at(1).code.flowAt(0).target != CodePosition{1})
        throw Error("instruction identity, CFG target or borrowed payload changed after compaction, ingress "
                    "destruction or owner move");
    const auto assembly = X86Emitter{}.emit(replacement);
    if (assembly.find("leaq .Laurora_literal_9(%rip)") == std::string::npos ||
        assembly.find(".Laurora_literal_9:\n") == std::string::npos ||
        assembly.find(".Laurora_literal_1:\n") != std::string::npos)
        throw Error("nonfirst function literal lost its global immutable instruction ID");
    ++passed;
    std::cout << "PASS IR instruction ranges and literal IDs survive compaction and owner replacement\n";
    for (const auto &read : std::vector<std::function<void()>>{[&] {
                                                                   static_cast<void>(code.at(code.size()));
                                                               },
                                                               [&] {
                                                                   static_cast<void>(code.flowAt(code.size()));
                                                               },
                                                               [&] {
                                                                   static_cast<void>(code.instructionById(0));
                                                               },
                                                               [&] {
                                                                   static_cast<void>(code.instructionById(1));
                                                               },
                                                               [&] {
                                                                   static_cast<void>(bytes.at(bytes.size()));
                                                               }}) {
        bool rejected = false;
        try {
            read();
        } catch (const Error &) {
            rejected = true;
        } catch (const std::out_of_range &) {
            rejected = true;
        }
        if (!rejected)
            throw Error("instruction range accepted an out-of-domain position, ID or payload index");
        ++passed;
    }
}

void callableOwnerTests() {
    for (bool imported : {false, true}) {
        for (int mutation = 0; mutation < 3; ++mutation) {
            auto uncalled = receiverBaseline();
            uncalled.functions.erase(uncalled.functions.begin());
            auto &constructor = uncalled.functions[0];
            if (mutation == 0)
                constructor.receiver->mutableValue = false;
            else
                constructor.result = mutation == 1 ? Type::Bool : Type::U64;
            if (imported) {
                uncalled.descriptorViews[1] = {};
                constructor.moduleScope = 1;
            }
            // Canonical metadata views alone do not grant executable authority.
            // The mandatory source instruction phase still rejects uncalled and
            // imported constructor policies before graph pruning/publication.
            const auto shape = Metadata::import(uncalled);
            if (!shape->callable(0).receiver()->constructor || shape->callable(0).result() != constructor.result)
                throw Error("intermediate constructor metadata changed declaration shape");
        }
    }
    auto input = receiverBaseline();
    auto checked = validate(input);
    const auto *identity = &checked.metadata();
    const auto id = checked.metadata().findCallable("construct_pair").value();
    const auto callable = checked.metadata().callable(id);
    const auto parameters = callable.parameters();
    const auto frame = callable.frame();
    const auto scalars = frame.scalarSlots();
    const auto objects = checked.metadata().frame(0).objectSlots();
    auto copiedObject = objects.at(16);
    copiedObject.className = "changed frame observation";
    auto receiver = callable.receiver().value();
    receiver.className = "changed observation";
    input = Module{};
    auto moved = std::move(checked);
    if (&moved.metadata() != identity || id != 1 || callable.name() != "construct_pair" ||
        callable.moduleScope() != 0 || callable.result() != Type::I64 || parameters.size() != 2 ||
        parameters[0] != Type::I64 || parameters[1] != Type::Bool || callable.receiver()->className != "Pair" ||
        receiver.className != "changed observation" || !callable.receiver()->constructor ||
        !callable.receiver()->mutableValue || callable.borrowedRootCount() || callable.receiverSpanField() ||
        frame.frameBytes() != 16 || scalars.size() != 2 || scalars.at(8) != Type::I64 || scalars.at(16) != Type::Bool ||
        objects.size() != 1 || objects.at(16).className != "Pair" || objects.at(16).mutableValue ||
        copiedObject.className != "changed frame observation" || moved.get().functions[id].callableId != id)
        throw Error("callable observations lost independent ingress lifetime, owner move or immutable receiver");
    ++passed;
    std::cout << "PASS IR callable and frame views survive raw ingress destruction and validated owner move\n";
}

void metadataOwnerTests() {
    auto source = baseline();
    const std::string binaryName("A\0\xff", 3);
    const std::string highName("\xff", 1);
    source.classLayouts[binaryName] = {Type::U8, Type::I64};
    source.classLayouts[highName] = {};
    source.classLayouts["A"] = {};
    source.classLayouts[std::string("A\0", 2)] = {};
    source.classLayouts[std::string("A\x7f", 2)] = {};
    source.classLayouts[std::string("A\x80", 2)] = {};
    source.classLayouts["Empty"] = {};
    source.classFields["Empty"] = {};
    source.enumCases["Mode"] = 2;
    source.descriptors[7] = Descriptor{16, 2};
    source.descriptorViews[0] = {7};
    const auto checked = validate(source);
    source.classLayouts.clear();
    source.classFields.clear();
    source.classStorage.clear();
    source.enumCases.clear();
    source.descriptors.clear();
    source.descriptorViews.clear();
    const auto &metadata = checked.metadata();
    const auto binary = metadata.findClass(binaryName);
    const auto high = metadata.findClass(highName);
    const auto empty = metadata.findClass("Empty");
    const auto mode = metadata.findEnum("Mode");
    const auto descriptor = metadata.findDescriptor(7);
    if (!binary || !high || !empty || !mode || metadata.className(*binary) != binaryName ||
        metadata.className(*high) != highName || *high <= *empty || metadata.leaves(*binary).size() != 2 ||
        metadata.leaves(*binary).at(0) != Type::U8 || metadata.fields(*binary).size() != 2 ||
        metadata.fields(*binary).at(1).firstLeaf != 1 || metadata.fields(*binary).at(1).elementType != Type::I64 ||
        !metadata.fields(*empty).empty() ||
        !storageMatches(metadata.storage(*binary), ClassStorage{{0, 8}, {0, 8}, 16, 8, 16}) ||
        !storageMatches(metadata.storage(*empty), ClassStorage{{}, {}, 8, 8, 8}) || metadata.enumCases(*mode) != 2 ||
        !descriptor || descriptor->size != 16 || metadata.visibleDescriptors(0).size() != 1 ||
        metadata.visibleDescriptors(0).at(0) != 7)
        throw Error("durable metadata lost normalized fields, byte names or independent input lifetime");
    ++passed;
    std::cout << "PASS IR durable metadata preserves normalized fields and exact byte names\n";

    const auto prefix = metadata.findClass("A");
    const auto nulPrefix = metadata.findClass(std::string("A\0", 2));
    const auto lowByte = metadata.findClass(std::string("A\x7f", 2));
    const auto highByte = metadata.findClass(std::string("A\x80", 2));
    if (!prefix || !nulPrefix || !lowByte || !highByte ||
        !(*prefix < *nulPrefix && *nulPrefix < *binary && *binary < *lowByte && *lowByte < *highByte))
        throw Error("metadata name comparison lost prefix, embedded NUL or unsigned-byte ordering");
    ++passed;
    std::cout << "PASS IR metadata names preserve prefix and unsigned-byte ordering\n";
}

void pendingBodies(detail::InstructionWriter &writer, std::size_t count = 1, bool wrongId = false) {
    const std::vector<Instruction> code{Constant{42, Type::I64}, Store{8, Type::I64}, Load{8, Type::I64}, Return{}};
    for (std::size_t id = 0; id < count; ++id) {
        writer.beginBody(wrongId ? id + 1 : id);
        for (const auto &instruction : code)
            writer.append(instruction);
        writer.endBody();
    }
}

enum class CallableMutation {
    None,
    NegativeNameBegin,
    NegativeNameCount,
    NameBeginOverflow,
    NameCountOverflow,
    AbsentReceiver,
    UnknownFlag,
    UnknownReceiverFlag,
    ReservedCallableBit2,
    ReservedCallableBit4,
    HighCallableFlag,
    HighReceiverFlag,
    NegativeCallableFlags,
    NegativeReceiverFlags,
    ZeroClassFlags,
    UnknownClassFlag,
    HighClassFlag,
    NegativeClassFlags,
    RangeBegin,
    RangeCount,
    IndexOverflow,
    IndexDuplicate,
    IndexOrder,
    SlotRangeBegin,
    SlotRangeCount,
    SlotKind,
    SlotTypePrefix,
    SlotTypeGap,
    SlotLength,
    SlotMutable,
    SlotDuplicate,
    SlotOrder,
    SlotUncovered,
    TypeUncovered,
    ScalarTail,
    ObjectTail,
    OwnerTail,
    OrphanOwner,
    FrameSize,
    SlotKindOrder,
    SlotUnusedType,
    NegativeSingleSlot,
    NegativePairedSlot,
    NegativeRootMutability,
    NoncanonicalRootMutability,
    MutableWithoutRoots
};

void pendingCallables(detail::MetadataWriter &writer,
                      const std::vector<std::string> &names,
                      CallableMutation mutation = CallableMutation::None) {
    namespace wire = aurora::hosted_abi::compiler_ir_metadata;
    for (const auto &name : names) {
        wire::CallableRow callable{};
        callable.nameRange = writer.text(name);
        callable.typeRange = {writer.position().coreCounts.types, 1};
        callable.frameBytes = 16;
        callable.slotRange = {writer.slotCount(), 2};
        const bool first = writer.callableCount() == 0;
        if (first) {
            if (mutation == CallableMutation::NegativeRootMutability)
                callable.borrowedRootMutability = -1;
            else if (mutation == CallableMutation::NoncanonicalRootMutability)
                callable.borrowedRootMutability = 2;
            else if (mutation == CallableMutation::MutableWithoutRoots)
                callable.borrowedRootMutability = 1;
            else if (mutation == CallableMutation::NegativeNameBegin)
                callable.nameRange.firstByte = -1;
            else if (mutation == CallableMutation::NegativeNameCount)
                callable.nameRange.byteCount = -1;
            else if (mutation == CallableMutation::NameBeginOverflow)
                callable.nameRange.firstByte = std::numeric_limits<std::int64_t>::max();
            else if (mutation == CallableMutation::NameCountOverflow)
                callable.nameRange.byteCount = std::numeric_limits<std::int64_t>::max();
            else if (mutation == CallableMutation::AbsentReceiver)
                callable.receiver.flags = 1;
            else if (mutation == CallableMutation::UnknownFlag)
                callable.flags = 16;
            else if (mutation == CallableMutation::UnknownReceiverFlag)
                callable.receiver.flags = 8;
            else if (mutation == CallableMutation::ReservedCallableBit2)
                callable.flags = 2;
            else if (mutation == CallableMutation::ReservedCallableBit4)
                callable.flags = 4;
            else if (mutation == CallableMutation::HighCallableFlag)
                callable.flags = std::uint64_t{1} << 63;
            else if (mutation == CallableMutation::HighReceiverFlag)
                callable.receiver.flags = std::uint64_t{1} << 63;
            else if (mutation == CallableMutation::NegativeCallableFlags)
                callable.flags = UINT64_MAX;
            else if (mutation == CallableMutation::NegativeReceiverFlags)
                callable.receiver.flags = UINT64_MAX;
            else if (mutation == CallableMutation::RangeBegin)
                ++callable.typeRange.firstIndex;
            else if (mutation == CallableMutation::RangeCount)
                ++callable.typeRange.indexCount;
            else if (mutation == CallableMutation::SlotRangeBegin)
                ++callable.slotRange.firstIndex;
            else if (mutation == CallableMutation::SlotRangeCount)
                ++callable.slotRange.indexCount;
            else if (mutation == CallableMutation::FrameSize)
                callable.frameBytes = 8;
        }
        writer.callableType(Type::I64);
        const int slotCount = first && mutation == CallableMutation::NegativeSingleSlot ? 1 : 2;
        if (slotCount == 1)
            callable.slotRange.indexCount = 1;
        for (int ordinal = 0; ordinal < slotCount; ++ordinal) {
            wire::SlotRow slot{};
            slot.recordKind = static_cast<std::int64_t>(aurora::hosted_abi::compiler_lowering::RecordKind::ScalarSlot);
            slot.slotOffset = (ordinal + 1) * 8;
            auto type = Type::I64;
            if (first && ordinal == 0 && mutation == CallableMutation::ScalarTail)
                type.lengthParameter = "N";
            slot.typeIndex = writer.slotType(type);
            if (first) {
                if (ordinal == 0) {
                    if (mutation == CallableMutation::SlotKind)
                        slot.recordKind = 9;
                    else if (mutation == CallableMutation::SlotKindOrder)
                        slot.recordKind = 11;
                    else if (mutation == CallableMutation::SlotUnusedType)
                        slot.recordKind = 13;
                    else if (mutation == CallableMutation::NegativeSingleSlot ||
                             mutation == CallableMutation::NegativePairedSlot)
                        slot.slotOffset = -8;
                    else if (mutation == CallableMutation::SlotTypePrefix)
                        slot.typeIndex = callable.typeRange.firstIndex;
                    else if (mutation == CallableMutation::SlotTypeGap)
                        ++slot.typeIndex;
                    else if (mutation == CallableMutation::SlotLength)
                        slot.slotLength = 1;
                    else if (mutation == CallableMutation::SlotMutable)
                        slot.mutableValue = 1;
                }
                if (mutation == CallableMutation::SlotDuplicate)
                    slot.slotOffset = 8;
                else if (mutation == CallableMutation::SlotOrder)
                    slot.slotOffset = (2 - ordinal) * 8;
            }
            writer.append(slot);
        }
        if (first && (mutation == CallableMutation::ObjectTail || mutation == CallableMutation::OwnerTail ||
                      mutation == CallableMutation::OrphanOwner)) {
            wire::SlotRow extra{};
            const auto nominal = Type(std::string("A\0\xff", 3));
            if (mutation == CallableMutation::ObjectTail) {
                extra.recordKind = 11;
                extra.slotOffset = 16;
                auto type = nominal;
                type.elementParameter = "T";
                extra.typeIndex = writer.slotType(type);
            } else {
                callable.frameBytes = 64;
                if (mutation == CallableMutation::OwnerTail) {
                    wire::SlotRow owner{};
                    owner.recordKind = 16;
                    owner.slotOffset = 64;
                    owner.mutableValue = 1;
                    writer.append(owner);
                    ++callable.slotRange.indexCount;
                }
                extra.recordKind = 17;
                extra.slotOffset = 64;
                auto type = Type::ownedValues(nominal);
                if (mutation == CallableMutation::OwnerTail)
                    type.lengthParameter = "N";
                extra.typeIndex = writer.slotType(type);
            }
            writer.append(extra);
            ++callable.slotRange.indexCount;
        }
        writer.append(callable);
    }
    if (mutation == CallableMutation::SlotUncovered) {
        wire::SlotRow extra{};
        extra.recordKind = static_cast<std::int64_t>(aurora::hosted_abi::compiler_lowering::RecordKind::ArraySlot);
        extra.slotOffset = 1;
        extra.slotLength = 1;
        writer.append(extra);
    }
    if (mutation == CallableMutation::TypeUncovered)
        writer.slotType(Type::I64);
    std::vector<std::size_t> ids(names.size());
    for (std::size_t id = 0; id < ids.size(); ++id)
        ids[id] = id;
    std::sort(ids.begin(), ids.end(), [&](auto left, auto right) {
        return names[left] < names[right] || (names[left] == names[right] && left < right);
    });
    if (mutation == CallableMutation::IndexOrder)
        std::reverse(ids.begin(), ids.end());
    for (const auto id : ids)
        writer.index(static_cast<std::int64_t>(mutation == CallableMutation::IndexOverflow    ? names.size()
                                               : mutation == CallableMutation::IndexDuplicate ? 0
                                                                                              : id));
}

InstructionIngress pendingMetadata(bool badStorage = false,
                                   bool badDescriptor = false,
                                   const std::vector<std::string> &names = {"test"},
                                   CallableMutation mutation = CallableMutation::None,
                                   std::optional<std::size_t> bodyCount = std::nullopt,
                                   bool wrongId = false) {
    namespace wire = aurora::hosted_abi::compiler_ir_metadata;
    detail::MetadataWriter writer;
    detail::InstructionWriter instructions(writer);
    const auto fill = [&] {
        wire::ClassRow shape{};
        shape.nameRange = writer.text(std::string("A\0\xff", 3));
        shape.membershipBits = 1 | 2 | 4;
        if (mutation == CallableMutation::ZeroClassFlags)
            shape.membershipBits = 0;
        else if (mutation == CallableMutation::UnknownClassFlag)
            shape.membershipBits |= 16;
        else if (mutation == CallableMutation::HighClassFlag)
            shape.membershipBits = std::uint64_t{1} << 63;
        else if (mutation == CallableMutation::NegativeClassFlags)
            shape.membershipBits = UINT64_MAX;
        shape.leafRange = {writer.position().coreCounts.leaves, 2};
        writer.leaf(Type::U8);
        writer.leaf(Type::I64);
        shape.fieldRange = {writer.position().coreCounts.fields, 2};
        writer.field(ClassField{Type::U8, 0, 1, false});
        writer.field(ClassField{Type::I64, 1, 1, false});
        shape.suppliedStorage = writer.position().mapCounts.storage;
        wire::StorageRow storage{};
        storage.leafOffsetRange = {writer.position().mapCounts.indices, 2};
        writer.index(0);
        writer.index(badStorage ? 9 : 8);
        storage.fieldOffsetRange = {writer.position().mapCounts.indices, 2};
        writer.index(0);
        writer.index(8);
        storage.physicalExtent = {16, 8, 16};
        writer.append(storage);
        writer.append(shape);
        wire::DescriptorRow descriptor{};
        descriptor.descriptorId = 7;
        descriptor.sizeValue = badDescriptor ? -1 : 16;
        descriptor.publicFieldCount = 2;
        writer.append(descriptor);
        wire::ViewRow view{};
        view.moduleScope = 0;
        view.descriptorRange = {writer.position().mapCounts.indices, 1};
        writer.index(7);
        writer.append(view);
        pendingCallables(writer, names, mutation);
        writer.beginInstructions();
        pendingBodies(instructions, bodyCount.value_or(names.size()), wrongId);
    };
    fill();
    writer.allocate();
    instructions.allocate();
    fill();
    return std::move(instructions).take();
}

void metadataIngressTests() {
    static_assert(!std::is_copy_constructible_v<MetadataIngress> && !std::is_copy_assignable_v<MetadataIngress> &&
                  std::is_nothrow_move_constructible_v<MetadataIngress> &&
                  std::is_nothrow_move_assignable_v<MetadataIngress>);
    const auto rejects = [](const char *name, const auto &operation, const char *expected, bool exact = false) {
        try {
            operation();
        } catch (const Error &error) {
            if (exact ? error.diagnostic.code != DiagnosticCode::Unclassified || error.diagnostic.message != expected
                      : std::string(error.what()).find(expected) == std::string::npos) {
                diagnosticMismatch(name, expected, error, exact);
                return;
            }
            ++passed;
            std::cout << "PASS IR " << name << '\n';
            return;
        }
        throw Error(std::string(name) + ": invalid pending metadata was accepted");
    };
    {
        detail::MetadataWriter writer;
        detail::InstructionWriter instructions(writer);
        const auto fill = [&] {
            std::string temporary("A\0\x80", 3);
            const auto first = writer.text(temporary);
            temporary[0] = 'B';
            const auto duplicate = writer.text(std::string("A\0\x80", 3));
            const auto different = writer.text(temporary);
            const auto prefix = writer.text("A");
            writer.text("");
            if (first.firstByte != duplicate.firstByte || first.byteCount != duplicate.byteCount ||
                different.firstByte == first.firstByte || prefix.byteCount != 1 ||
                writer.position().coreCounts.bytes != 7)
                throw Error("metadata text sharing lost exact bytes or short-lived string ownership");
            writer.declarations(baseline());
            writer.beginInstructions();
            pendingBodies(instructions);
            return first;
        };
        const auto counted = fill();
        const auto byteCount = writer.position().coreCounts.bytes;
        writer.allocate();
        instructions.allocate();
        const auto replayed = fill();
        if (counted.firstByte != replayed.firstByte || counted.byteCount != replayed.byteCount ||
            writer.position().coreCounts.bytes != byteCount)
            throw Error("metadata text replay changed shared ranges or exact byte accounting");
        const auto shared = validate(std::move(instructions).take());
        if (shared.metadata().callable(0).name() != "test")
            throw Error("metadata text replay did not publish the counted callable name");
        rejects(
            "consumed metadata writer rejects repeated text",
            [&] {
                writer.text(std::string("A\0\x80", 3));
            },
            "invalid hosted IR metadata transport");
        ++passed;
        std::cout << "PASS IR temporary metadata text sharing preserves count and replay\n";
    }
    auto pending = pendingMetadata();
    InstructionIngress moved(std::move(pending));
    pending = pendingMetadata();
    pending = std::move(moved);
    const auto checked = validate(std::move(pending));
    const auto &metadata = checked.metadata();
    const auto id = metadata.findClass(std::string("A\0\xff", 3));
    if (!id || metadata.leaves(*id).size() != 2 || metadata.fields(*id).at(1).elementType != Type::I64 ||
        !storageMatches(metadata.storage(*id), ClassStorage{{0, 8}, {0, 8}, 16, 8, 16}) ||
        metadata.visibleDescriptors(0).size() != 1 || metadata.visibleDescriptors(0).front() != 7 ||
        metadata.callableCount() != 1 || metadata.findCallable("test") != 0 ||
        metadata.callable(0).result() != Type::I64 || !metadata.callable(0).parameters().empty() ||
        metadata.frame(0).frameBytes() != 16 || metadata.frame(0).scalarSlots().size() != 2 ||
        metadata.frame(0).scalarSlots().at(8) != Type::I64 || metadata.frame(0).scalarSlots().at(16) != Type::I64)
        throw Error(
            "pending metadata moves lost copied names, fields, storage, callable headers or frame declarations");
    ++passed;
    std::cout << "PASS IR pending metadata move construction, replacement and publication\n";
    rejects(
        "pending metadata cannot publish twice",
        [&] {
            static_cast<void>(validate(std::move(pending)));
        },
        "invalid hosted IR metadata transport");
    // Real Region destruction rejects any leaked owner. Exercise abandonment
    // and exception cleanup without substituting the generated owner/runtime.
    {
        const auto abandoned = pendingMetadata();
        (void)abandoned;
    }
    rejects(
        "partially filled metadata cleans up without publication",
        [] {
            detail::MetadataWriter partial;
            partial.text("partial");
            partial.allocate();
            partial.text("p");
            static_cast<void>(std::move(partial).take());
        },
        "invalid hosted IR metadata transport");
    rejects(
        "partially filled instruction bundle releases both owners",
        [] {
            detail::MetadataWriter metadata;
            detail::InstructionWriter instructions(metadata);
            const auto fill = [&](bool partial) {
                metadata.declarations(baseline());
                metadata.beginInstructions();
                instructions.beginBody(0);
                instructions.append(Instruction{Push{}});
                if (!partial)
                    instructions.append(Instruction{Pop{}});
                instructions.endBody();
            };
            fill(false);
            metadata.allocate();
            instructions.allocate();
            fill(true);
            static_cast<void>(std::move(instructions).take());
        },
        "invalid hosted IR instruction transport");
    {
        detail::MetadataWriter writer;
        detail::InstructionWriter instructions(writer);
        aurora::hosted_abi::compiler_ir_metadata::ViewRow root{};
        const auto fill = [&] {
            writer.append(root);
            pendingCallables(writer, {"test"});
            writer.beginInstructions();
            pendingBodies(instructions);
        };
        fill();
        writer.allocate();
        instructions.allocate();
        fill();
        auto sealed = std::move(instructions).take();
        rejects(
            "consumed metadata writer cannot append fields",
            [&] {
                writer.field(ClassField{Type::I64, 0, 1, false});
            },
            "invalid hosted IR metadata transport");
        static_cast<void>(validate(std::move(sealed)));
    }
    for (const int mode : {0, 1, 2}) {
        rejects(
            "source callable symbols precede pending metadata semantics",
            [=] {
                const std::vector<std::string> names = mode == 0   ? std::vector<std::string>{}
                                                       : mode == 1 ? std::vector<std::string>{"__au_runtime_reserved"}
                                                                   : std::vector<std::string>{"test", "test"};
                static_cast<void>(validate(pendingMetadata(false, true, names)));
            },
            mode == 0   ? "empty module"
            : mode == 1 ? "invalid or reserved function symbol"
                        : "duplicate function");
    }
    for (const std::string &name :
         {std::string("bad\nname"), std::string("bad\"name"), std::string("bad") + char(0xff), std::string("9bad")}) {
        rejects(
            "stack fact symbols remain admitted ASCII identifiers",
            [=] {
                static_cast<void>(validate(pendingMetadata(false, true, {name})));
            },
            "invalid or reserved function symbol");
    }
    rejects(
        "source duplicate symbol precedes later reserved symbol",
        [] {
            const std::vector<std::string> names{"test", "test", "__au_runtime_reserved"};
            static_cast<void>(validate(pendingMetadata(false, true, names)));
        },
        "duplicate function");
    rejects(
        "source reserved symbol precedes later duplicate symbol",
        [] {
            const std::vector<std::string> names{"__au_runtime_reserved", "test", "test"};
            static_cast<void>(validate(pendingMetadata(false, true, names)));
        },
        "invalid or reserved function symbol");
    for (const auto &[name, mutation] : std::vector<std::pair<const char *, CallableMutation>>{
             {"unknown receiver flag bit", CallableMutation::UnknownReceiverFlag},
             {"reserved callable flag bit 2", CallableMutation::ReservedCallableBit2},
             {"reserved callable flag bit 4", CallableMutation::ReservedCallableBit4},
             {"isolated high callable flag bit", CallableMutation::HighCallableFlag},
             {"isolated high receiver flag bit", CallableMutation::HighReceiverFlag},
             {"negative signed callable flag encoding", CallableMutation::NegativeCallableFlags},
             {"negative signed receiver flag encoding", CallableMutation::NegativeReceiverFlags},
             {"zero class membership", CallableMutation::ZeroClassFlags},
             {"unknown class membership bit", CallableMutation::UnknownClassFlag},
             {"isolated high class membership bit", CallableMutation::HighClassFlag},
             {"negative signed class membership encoding", CallableMutation::NegativeClassFlags}}) {
        rejects(
            name,
            [=] {
                static_cast<void>(validate(pendingMetadata(false, false, {"alpha", "omega"}, mutation)));
            },
            "invalid hosted IR metadata transport",
            true);
    }
    for (const auto &[name, mutation] : std::vector<std::pair<const char *, CallableMutation>>{
             {"negative borrowed-root mutability mask", CallableMutation::NegativeRootMutability},
             {"out-of-range borrowed-root mutability mask", CallableMutation::NoncanonicalRootMutability},
             {"borrowed-root mutability without roots", CallableMutation::MutableWithoutRoots},
             {"negative callable name begin", CallableMutation::NegativeNameBegin},
             {"negative callable name count", CallableMutation::NegativeNameCount},
             {"overflowing callable name begin", CallableMutation::NameBeginOverflow},
             {"overflowing callable name count", CallableMutation::NameCountOverflow},
             {"absent receiver payload", CallableMutation::AbsentReceiver},
             {"unknown callable flags", CallableMutation::UnknownFlag},
             {"nonpacked callable type begin", CallableMutation::RangeBegin},
             {"overlapping callable type range", CallableMutation::RangeCount},
             {"callable name index overflow", CallableMutation::IndexOverflow},
             {"duplicate callable index and missing ID", CallableMutation::IndexDuplicate},
             {"unsorted callable name index", CallableMutation::IndexOrder},
             {"nonpacked callable slot begin", CallableMutation::SlotRangeBegin},
             {"overlapping callable slot ranges", CallableMutation::SlotRangeCount},
             {"unknown frame record kind", CallableMutation::SlotKind},
             {"reversed frame declaration kinds", CallableMutation::SlotKindOrder},
             {"untyped spill has a type index", CallableMutation::SlotUnusedType},
             {"slot type aliases signature prefix", CallableMutation::SlotTypePrefix},
             {"slot type skips packed prefix", CallableMutation::SlotTypeGap},
             {"scalar slot has unused length payload", CallableMutation::SlotLength},
             {"scalar slot has unused mutable payload", CallableMutation::SlotMutable},
             {"duplicate scalar declaration rows", CallableMutation::SlotDuplicate},
             {"reversed scalar declaration rows", CallableMutation::SlotOrder},
             {"uncovered frame declaration suffix", CallableMutation::SlotUncovered},
             {"uncovered frame type suffix", CallableMutation::TypeUncovered}}) {
        rejects(
            name,
            [=] {
                static_cast<void>(validate(pendingMetadata(false, false, {"alpha", "omega"}, mutation)));
            },
            "invalid hosted IR metadata transport");
    }
    // These exercise source admission for both row counts. They do not
    // substitute for a successful hosted-lowering projection/sort fixture.
    for (const auto mutation : {CallableMutation::NegativeSingleSlot, CallableMutation::NegativePairedSlot}) {
        rejects(
            "negative slot offset is independent of declaration count",
            [=] {
                static_cast<void>(validate(pendingMetadata(false, false, {"test"}, mutation)));
            },
            "invalid typed IR: invalid slot offset");
    }
    rejects(
        "pending scalar declaration preserves malformed raw tail",
        [] {
            static_cast<void>(validate(pendingMetadata(false, false, {"test"}, CallableMutation::ScalarTail)));
        },
        "invalid slot payload type");
    rejects(
        "pending object declaration preserves malformed nominal tail",
        [] {
            static_cast<void>(validate(pendingMetadata(false, false, {"test"}, CallableMutation::ObjectTail)));
        },
        "unknown object class");
    rejects(
        "pending typed owner preserves malformed raw tail",
        [] {
            static_cast<void>(validate(pendingMetadata(false, false, {"test"}, CallableMutation::OwnerTail)));
        },
        "invalid canonical owned value type");
    rejects(
        "pending owner annotation cannot omit owner declaration",
        [] {
            static_cast<void>(validate(pendingMetadata(false, false, {"test"}, CallableMutation::OrphanOwner)));
        },
        "owned value metadata requires exact owner spill");
    rejects(
        "pending frame extent receives independent validation",
        [] {
            static_cast<void>(validate(pendingMetadata(false, false, {"test"}, CallableMutation::FrameSize)));
        },
        "invalid frame size");
    rejects(
        "pending descriptor still receives independent validation",
        [] {
            static_cast<void>(validate(pendingMetadata(false, true)));
        },
        "invalid metadata descriptor");
    rejects(
        "pending supplied physical offsets cannot become canonical by assertion",
        [] {
            static_cast<void>(validate(pendingMetadata(true)));
        },
        "noncanonical class storage metadata");
    rejects(
        "pending callable header requires its body",
        [] {
            static_cast<void>(validate(pendingMetadata(false, false, {"test"}, CallableMutation::None, 0)));
        },
        "invalid hosted IR instruction transport");
    rejects(
        "pending body cannot substitute another callable ID",
        [] {
            static_cast<void>(pendingMetadata(false, false, {"test"}, CallableMutation::None, 1, true));
        },
        "invalid hosted IR instruction transport");
}

// Validated owners keep frame views across moves; origin queries reject
// callable identities outside the module.
void validatedViewTests() {
    auto checked = validate(spanBaseline());
    const auto frame = checked.metadata().frame(0);
    auto moved = std::move(checked);
    require(frame.arraySlots().at(8) == 3 && moved.metadata().frame(0).arraySlots().at(8) == 3,
            "frame array observations lost source ownership after a validated move");
    const auto packed = validate(packedMethodModule());
    const auto &metadata = packed.metadata();
    for (const auto query : {&Metadata::objectLeafRoot, &Metadata::byteArrayElementRoot}) {
        bool rejected = false;
        try {
            static_cast<void>((metadata.*query)(metadata.callableCount(), 8));
        } catch (const std::out_of_range &) {
            rejected = true;
        }
        require(rejected, "storage origin query accepted invalid callable identity");
    }
    passed += 2;
}

// One emitter object reused across modules and emission options keeps no
// stale literal bytes, metadata or reflection selection.
void emitterReuseTests() {
    const auto literal = validate(load("readonly-windows-ir/cases.air", "literal window emission"));
    const auto ordinary = validate(load("readonly-windows-ir/cases.air", "ordinary window emission"));
    const auto expectedLiteral = X86Emitter{}.emit(literal);
    const auto expectedOrdinary = X86Emitter{}.emit(ordinary);
    X86Emitter reused;
    require(reused.emit(literal) == expectedLiteral && reused.emit(literal) == expectedLiteral &&
                reused.emit(ordinary) == expectedOrdinary,
            "emitter retained literal bytes across modules");
    ++passed;

    X86Emitter emitter;
    const auto branches = validate(
        load("stack-probes/stack-fact.air", "branch and loop call maxima, reflection edges and pruned imports"));
    (void)emitter.emit(branches);
    const auto stack = emitter.stackFactsJson(branches);
    require(emitter.emit(branches, SymbolBinding::Local).find(".globl ") == std::string::npos &&
                emitter.stackFactsJson(branches) == stack,
            "local binding changed stack facts");
    const auto scalar = validate(load("stack-probes/stack-fact.air", "compact deterministic stack facts"));
    (void)emitter.emit(scalar);
    const auto functions = jsonMember(emitter.stackFactsJson(scalar), "functions");
    require(jsonMemberCount(functions) == 3 && jsonMember(functions, "branches").empty() &&
                jsonMember(jsonMember(functions, "probe_scalar"), "service_abi").empty(),
            "reused emitter retained stale metadata or service facts");
    ++passed;

    const auto reflected = validate(
        load("ir-tests/reflection-emission.air", "referenced reflection retains referenced helper bodies and facts"));
    X86Emitter selector;
    const auto complete = selector.emit(reflected);
    const auto completeFacts = selector.stackFactsJson(reflected);
    (void)selector.emit(reflected, SymbolBinding::Default, ReflectionEmission::Referenced);
    require(selector.emit(reflected) == complete && selector.stackFactsJson(reflected) == completeFacts,
            "referenced reflection changed default output or leaked emitter state");
    ++passed;
}

// Object and text sinks share lowering and facts, but a rejected object must
// invalidate the previous published artifact and its optional sidecars.
void objectEmissionTests() {
    const auto checked = validate(load("ir-tests/object.air", "native object values"));
    AbiDeclarations declarations;
    declarations.functions["object_minimum"] = {"object_minimum", {}};
    X86Emitter emitter;
    const auto assembly = emitter.emit(checked, SymbolBinding::Local, ReflectionEmission::Referenced);
    const auto stack = emitter.stackFactsJson(checked);
    const auto abi = emitter.abiFactsJson(checked, declarations);
    const auto emitObject = [&] {
        return emitter.emit(checked, SymbolBinding::Local, ReflectionEmission::Referenced, CodeEmission::Object);
    };
    const auto object = emitObject();
    require(emitter.stackFactsJson(checked) == stack && emitter.abiFactsJson(checked, declarations) == abi &&
                emitter.stackFactsJson(checked) == stack,
            "object emission changed stack/ABI facts or optional sidecar reuse");
    require(emitObject() == object &&
                emitter.emit(checked, SymbolBinding::Local, ReflectionEmission::Referenced) == assembly &&
                emitObject() == object,
            "object/text emission reuse retained stale bytes or sink selection");
    ++passed;

    const auto rejectUnsupported = [&](const ValidatedModule &unsupported) {
        bool rejected = false;
        try {
            (void)emitter.emit(unsupported, SymbolBinding::Local, ReflectionEmission::Referenced, CodeEmission::Object);
        } catch (const Error &error) {
            rejected = std::string(error.what()).find("does not support") != std::string::npos;
        }
        require(rejected, "unsupported object form did not fail with an unsupported diagnostic");
        bool stackRejected = false;
        bool abiRejected = false;
        try {
            (void)emitter.stackFactsJson(checked);
        } catch (const Error &error) {
            stackRejected = std::string(error.what()) == "stack facts require the same emitted module";
        }
        try {
            (void)emitter.abiFactsJson(checked, declarations);
        } catch (const Error &error) {
            abiRejected = std::string(error.what()) == "ABI facts require the same emitted module";
        }
        require(stackRejected && abiRejected, "failed object emission retained earlier sidecar ownership");
        require(emitObject() == object && emitter.stackFactsJson(checked) == stack,
                "failed object emission poisoned a subsequent supported module");
        ++passed;
    };
    const auto literal = validate(load("readonly-windows-ir/cases.air", "literal window emission"));
    rejectUnsupported(literal);
    const auto reflection = validate(
        load("ir-tests/reflection-emission.air", "referenced reflection retains referenced helper bodies and facts"));
    rejectUnsupported(reflection);
}

void metadataLifetimeTests() {
    static_assert(!std::is_copy_constructible_v<ValidatedModule>);
    static_assert(std::is_move_constructible_v<ValidatedModule>);
    static_assert(!std::is_constructible_v<ValidatedModule, std::vector<FunctionBody>, std::unique_ptr<Metadata>>);
    auto input = moving();
    input.descriptors = {{7, {88, 5}}};
    input.descriptorViews = {{0, {7}}};
    input.enumCases = {{"Phase", 2}};
    auto checked = validate(input);
    const auto independent = validate(input);
    const auto *identity = &checked.metadata();
    const auto parcelId = checked.metadata().findClass("Parcel").value();
    const auto leaves = checked.metadata().leaves(parcelId);
    const auto fields = checked.metadata().fields(parcelId);
    const auto offsets = checked.metadata().storage(parcelId).fieldOffsets;
    const auto visible = checked.metadata().visibleDescriptors(0);
    const auto frame = checked.metadata().frame(0);
    const auto regions = frame.regionSlots();
    const auto owners = frame.byteSlots();
    const auto objects = frame.objectSlots();
    AbiDeclarations declarations;
    declarations.records["Parcel"] = {"Parcel", {"tag", "first", "value", "second", "tail"}};
    declarations.enums["Phase"] = {"Phase", {"ready", "done"}};
    declarations.functions["owning_entry"] = {"owning_entry", {}};
    const auto rejectStackOwner = [](X86Emitter &owner, const ValidatedModule &module) {
        bool rejectedOwner = false;
        try {
            (void)owner.stackFactsJson(module);
        } catch (const Error &error) {
            rejectedOwner = std::string(error.what()) == "stack facts require the same emitted module";
        }
        require(rejectedOwner, "stack facts accepted an absent or different emitted-module owner");
        ++passed;
    };
    const auto rejectAbiOwner = [&](X86Emitter &owner, const ValidatedModule &module) {
        bool rejectedOwner = false;
        try {
            (void)owner.abiFactsJson(module, declarations);
        } catch (const Error &error) {
            rejectedOwner = std::string(error.what()) == "ABI facts require the same emitted module";
        }
        require(rejectedOwner, "ABI facts accepted an absent or different emitted-module owner");
        ++passed;
    };
    X86Emitter emitter;
    rejectStackOwner(emitter, checked);
    rejectAbiOwner(emitter, checked);
    const auto assembly = emitter.emit(checked);
    const auto stack = emitter.stackFactsJson(checked);
    const auto facts = emitter.abiFactsJson(checked, declarations);
    require(emitter.stackFactsJson(checked) == stack &&
                !jsonMember(jsonMember(stack, "functions"), "owning_entry").empty(),
            "stack-to-ABI-to-stack observation changed facts or lost the owning entry");
    rejectStackOwner(emitter, independent);
    require(emitter.stackFactsJson(checked) == stack, "rejected stack owner poisoned the emitted module");
    // Both capsules remain alive. Re-emission changes the accepted owner even
    // when the separately validated input and complete output are identical.
    X86Emitter reemittedOwner;
    require(reemittedOwner.emit(checked) == assembly && reemittedOwner.stackFactsJson(checked) == stack,
            "independent emitter changed assembly or stack facts");
    require(reemittedOwner.emit(independent) == assembly && reemittedOwner.stackFactsJson(independent) == stack,
            "re-emission changed exact assembly or stack facts");
    rejectStackOwner(reemittedOwner, checked);
    require(reemittedOwner.stackFactsJson(independent) == stack && reemittedOwner.emit(independent) == assembly &&
                reemittedOwner.stackFactsJson(independent) == stack,
            "repeated emission or rejected earlier owner changed stack observations");
    ++passed;
    auto changed = declarations;
    changed.records.at("Parcel").sourceName = "RenamedParcel";
    changed.records.at("Parcel").members[0] = "renamed_tag";
    changed.enums.at("Phase").members[0] = "renamed_ready";
    changed.functions.at("owning_entry").sourceName = "RenamedEntry";
    changed.functions["not_in_metadata"] = {"ignored", {"ignored_member"}};
    const auto changedFacts = emitter.abiFactsJson(checked, changed);
    require(changedFacts != facts && changedFacts.find("RenamedParcel") != std::string::npos &&
                changedFacts.find("renamed_tag") != std::string::npos &&
                changedFacts.find("renamed_ready") != std::string::npos &&
                changedFacts.find("RenamedEntry") != std::string::npos &&
                changedFacts.find("not_in_metadata") == std::string::npos,
            "repeat ABI request reused stale names or admitted an unrelated function");
    auto malformed = declarations;
    malformed.records.at("Parcel").members.pop_back();
    bool badNamesRejected = false;
    try {
        (void)emitter.abiFactsJson(checked, malformed);
    } catch (const Error &) {
        badNamesRejected = true;
    }
    require(badNamesRejected && emitter.stackFactsJson(checked) == stack &&
                emitter.abiFactsJson(checked, declarations) == facts,
            "malformed ABI names were accepted or poisoned stack facts or the corrected ABI request");
    auto hostileNames = declarations;
    hostileNames.records.at("Parcel").sourceName = std::string("bad") + char(0xff) + char(0) + char(0xc3) + "(";
    const auto hostileFacts = emitter.abiFactsJson(checked, hostileNames);
    require(hostileFacts.find("bad\\u00ff\\u0000\\u00c3(") != std::string::npos &&
                emitter.abiFactsJson(checked, declarations) == facts,
            "ABI name escaping changed bytes or retained a prior optional suffix");
    passed += 3;
    // Drop every hostile ingress container, then move only the capsule's native
    // owning handle. Previously acquired views still read that same source owner.
    input = Module{};
    auto moved = std::move(checked);
    bool movedFromRejected = false;
    try {
        (void)checked.metadata();
    } catch (const Error &error) {
        movedFromRejected = std::string(error.what()) == "metadata access on moved-from validated module";
    }
    require(movedFromRejected, "moved-from validated module did not reject metadata access");
    ++passed;
    rejectStackOwner(emitter, checked);
    rejectAbiOwner(emitter, checked);
    require(&moved.metadata() == identity, "validated move changed metadata identity");
    require(leaves.size() == 3 && leaves[0] == Type::U8 && leaves[1] == Type::U64 && leaves[2] == Type::U8 &&
                fields.size() == 5 && fields[1].elementType == Type::OwnedBytes && offsets.size() == 5 &&
                offsets[1] == 8 && offsets[3] == 48 && visible.size() == 1 && visible[0] == 7,
            "metadata views did not survive ingress destruction and validated move");
    require(frame.frameBytes() == 416 && regions.size() == 2 && regions.contains(8) && regions.contains(416) &&
                owners.size() == 2 && owners.at(304) && owners.at(336) && objects.size() == 3 &&
                objects.at(96).className == "Parcel" && objects.at(96).mutableValue,
            "resource frame views did not survive ingress destruction and validated move");
    auto copiedField = fields[1];
    copiedField.elementType = Type::U64;
    require(copiedField.elementType == Type::U64 && fields[1].elementType == Type::OwnedBytes,
            "metadata field observation exposed mutable source storage");
    require(emitter.stackFactsJson(moved) == stack && emitter.abiFactsJson(moved, declarations) == facts &&
                emitter.stackFactsJson(moved) == stack,
            "stack or ABI facts lost same-owner identity after validated move");
    require(X86Emitter{}.emit(moved) == assembly, "validated move changed emitted assembly");
    ++passed;
    rejectAbiOwner(emitter, independent);
    rejectStackOwner(emitter, independent);
    require(emitter.stackFactsJson(moved) == stack && emitter.abiFactsJson(moved, declarations) == facts,
            "independent owner rejection changed exact stack or ABI observations");

    // The emitted temporary dies at the semicolon. This checks rejection of a
    // later equal module without depending on whether the allocator reuses it.
    X86Emitter expiredOwner;
    (void)expiredOwner.emit(validate(moving()));
    const auto replacement = validate(moving());
    rejectStackOwner(expiredOwner, replacement);
    rejectAbiOwner(expiredOwner, replacement);

    bool failedEmission = false;
    try {
        (void)emitter.emit(checked);
    } catch (const Error &) {
        failedEmission = true;
    }
    require(failedEmission, "emission accepted a moved-from validated module");
    ++passed;
    rejectStackOwner(emitter, moved);
    rejectAbiOwner(emitter, moved);
}
} // namespace

int main(int argc, char **argv) {
    try {
        require(argc == 2, "usage: ir-api CASE-DIRECTORY");
        root = argv[1];
        instructionOwnerTests();
        callableOwnerTests();
        metadataOwnerTests();
        metadataIngressTests();
        validatedViewTests();
        emitterReuseTests();
        objectEmissionTests();
        metadataLifetimeTests();
        std::cout << "PASS IR API: " << passed << " checks\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "FAIL IR API: " << error.what() << '\n';
        return 1;
    }
}
