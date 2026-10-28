// The reference sets live only in this fixture. Every observed operation goes
// through the current eleven-pool VerificationWorkspace and test-only generated probes.
#include "initialization_workspace.hpp"
#include <algorithm>
#include <array>
#include <functional>
#include <iostream>
#include <map>
#include <limits>
#include <numeric>
#include <random>
#include <set>
#include <string>
#include <type_traits>

using aurora::Error;
using aurora::testing::InitializationWorkspace;
using aurora::testing::Metadata;
using ObjectCompletion = InitializationWorkspace::ObjectCompletion;
using ReceiverCompletion = InitializationWorkspace::ReceiverCompletion;
using ReceiverFieldFact = InitializationWorkspace::ReceiverFieldFact;

std::size_t initializationOwnershipChecks();

namespace {
std::size_t checks = 0;
void check(bool condition, const std::string &message) {
    if (!condition)
        throw Error(message);
    ++checks;
}
void rejects(const std::function<void()> &operation) {
    try {
        operation();
    } catch (const Error &) {
        ++checks;
        return;
    }
    throw Error("invalid initialization workspace operation was accepted");
}
std::vector<int> denseOffsets(std::size_t count) {
    std::vector<int> offsets(count);
    std::iota(offsets.begin(), offsets.end(), 1);
    return offsets;
}
// Fixture metadata is textual IR (tests/compiler/ir/README.md), read and
// admitted by the Aurora reader and metadata admission.
std::unique_ptr<Metadata> declarations(const std::vector<int> &offsets) {
    std::string module = "function facts\n  result i64\n  frame " + std::to_string(offsets.empty() ? 0 : 65536) + "\n";
    for (int offset : offsets)
        module += "  slot " + std::to_string(offset) + " u8\n";
    return Metadata::read(module + "end\n", offsets.size());
}
struct Reference {
    std::set<int> must, may;
    std::size_t count() const {
        return must.size() + may.size();
    }
    unsigned state(int offset) const {
        return unsigned(must.contains(offset)) | (unsigned(may.contains(offset)) << 1);
    }
    unsigned write(int offset) {
        const auto previous = state(offset);
        must.insert(offset);
        may.insert(offset);
        return previous;
    }
    void clear(int offset) {
        must.erase(offset);
        may.erase(offset);
    }
    bool join(const Reference &incoming) {
        const auto previousMust = must, previousMay = may;
        std::set<int> common;
        std::set_intersection(
            must.begin(), must.end(), incoming.must.begin(), incoming.must.end(), std::inserter(common, common.end()));
        must = std::move(common);
        may.insert(incoming.may.begin(), incoming.may.end());
        return must != previousMust || may != previousMay;
    }
};
void matches(InitializationWorkspace &actual, const Reference &expected, const std::vector<int> &offsets) {
    check(actual.currentCount() == expected.count(), "logical must/may count differs from reference sets");
    check(actual.slotCount() == offsets.size() && actual.wordCount() == (offsets.size() + 63) / 64,
          "word storage does not follow the canonical dense slot domain");
    check(actual.logicalPayloadBytesPerSnapshot() == 2 * actual.wordCount() * sizeof(std::uint64_t),
          "logical snapshot payload includes spare capacity or owner overhead");
    // Cover every bit in small domains, and every present fact plus boundary
    // probes in the maximal domain without turning bridge calls into a benchmark.
    if (offsets.size() <= 129) {
        for (int offset : offsets)
            check(actual.scalarState(offset) == expected.state(offset), "membership differs from reference sets");
    } else {
        for (std::size_t index : {0u, 62u, 63u, 64u, 127u, 128u, 65535u})
            if (index < offsets.size())
                check(actual.scalarState(offsets[index]) == expected.state(offsets[index]),
                      "boundary membership differs");
        for (int offset : expected.may)
            check(actual.scalarState(offset) == expected.state(offset), "retained fact differs from reference sets");
    }
    for (int offset : {-1, 0, 65537})
        check(actual.scalarState(offset) == 0, "absent offset acquired a scalar fact");
}
void factRestoreTests() {
    auto metadata = declarations({});
    for (std::size_t count :
         {0u, 1u, 2u, 3u, 4u, 7u, 8u, 9u, 15u, 16u, 17u, 31u, 32u, 33u, 127u, 128u, 129u, 257u, 513u, 1025u}) {
        InitializationWorkspace workspace(*metadata, 0);
        check(workspace.restoreFacts(count), "dynamic fact restoration failed at count " + std::to_string(count));
    }
}
void boundaryAndIsolationTests() {
    static_assert(!std::is_copy_constructible_v<InitializationWorkspace> &&
                  !std::is_move_constructible_v<InitializationWorkspace>);
    for (std::size_t count : {0u, 1u, 63u, 64u, 65u, 127u, 128u, 129u, 65536u}) {
        const auto offsets = denseOffsets(count);
        auto metadata = declarations(offsets);
        InitializationWorkspace workspace(*metadata, 0);
        Reference expected;
        matches(workspace, expected, offsets);
        const auto empty = workspace.retain();
        check(empty == 0 && workspace.retainedCountAt(empty) == 0, "first retained ordinal or count differs");
        for (int offset : offsets) {
            if (count > 129 && offset != 1 && offset != 63 && offset != 64 && offset != 65 && offset != 65536)
                continue;
            check(workspace.writeScalar(offset) == expected.write(offset), "first write lost previous state");
            check(workspace.writeScalar(offset) == expected.write(offset), "repeated write changed membership");
        }
        const auto full = workspace.retain();
        const auto saved = expected;
        check(workspace.retainedCountAt(empty) == 0, "current writes mutated a retained row");
        check(!workspace.join(full), "self join reported a change");
        workspace.load(empty);
        matches(workspace, {}, offsets);
        check(workspace.retainedCountAt(full) == saved.count(), "load mutated another retained row");
        workspace.load(full);
        expected = saved;
        for (int offset : saved.may) {
            workspace.clearArray(offset, 1, 1);
            expected.clear(offset);
        }
        matches(workspace, expected, offsets);
        workspace.load(full);
        matches(workspace, saved, offsets);
        // Append enough rows to relocate every retained owner repeatedly. Old
        // ordinals remain valid; no cached native payload span may survive growth.
        for (std::size_t index = 2; index < 130; ++index) {
            check(workspace.retain() == index, "retained ordinals are not append-only");
            check(workspace.retainedCountAt(index) == saved.count(), "growth lost a logical count");
        }
        workspace.load(empty);
        matches(workspace, {}, offsets);
        workspace.load(full);
        matches(workspace, saved, offsets);
    }
    const std::vector<int> sparse{1, 32, 64, 4096, 65535, 65536};
    auto metadata = declarations(sparse);
    InitializationWorkspace workspace(*metadata, 0);
    Reference expected;
    for (int offset : sparse) {
        workspace.writeScalar(offset);
        expected.write(offset);
    }
    matches(workspace, expected, sparse);
    check(workspace.wordCount() == 1 && workspace.scalarState(2) == 0, "sparse frame used raw offsets as bit indices");
}
void differentialJoins() {
    const std::vector<int> offsets{1, 8, 127, 65536};
    auto metadata = declarations(offsets);
    InitializationWorkspace workspace(*metadata, 0);
    std::array<InitializationWorkspace::Id, 16> rows{};
    std::array<Reference, 16> values{};
    const auto empty = workspace.retain();
    for (unsigned mask = 0; mask < rows.size(); ++mask) {
        workspace.load(empty);
        for (unsigned bit = 0; bit < offsets.size(); ++bit)
            if ((mask & (1u << bit)) != 0) {
                workspace.writeScalar(offsets[bit]);
                values[mask].write(offsets[bit]);
            }
        rows[mask] = workspace.retain();
    }
    for (unsigned left = 0; left < rows.size(); ++left)
        for (unsigned right = 0; right < rows.size(); ++right) {
            workspace.load(rows[left]);
            const auto target = workspace.retain();
            workspace.load(rows[right]);
            auto expected = values[left];
            const auto changed = expected.join(values[right]);
            check(workspace.join(target) == changed, "must AND/may OR changed result differs");
            matches(workspace, values[right], offsets);
            check(workspace.retainedCountAt(target) == expected.count(), "join retained cardinality differs");
            check(!workspace.join(target), "unchanged backedge reported a change");
            workspace.load(target);
            matches(workspace, expected, offsets);
            if (left == 1 && right == 2)
                check(changed && expected.count() == values[left].count(),
                      "cardinality-canceling must removal/may insertion was not a changed join");
        }
}
void randomizedRetainedRows() {
    std::mt19937 random(0x1faca5u);
    for (std::size_t count : {0u, 1u, 63u, 64u, 65u, 129u, 65536u}) {
        const auto offsets = denseOffsets(count);
        auto metadata = declarations(offsets);
        InitializationWorkspace workspace(*metadata, 0);
        Reference current;
        std::vector<Reference> rows{current};
        check(workspace.retain() == 0, "random initial retain");
        for (unsigned step = 0; step < 400; ++step) {
            const auto row = random() % rows.size();
            const int offset = count == 0 ? 1 : offsets[random() % count];
            switch (random() % 5) {
            case 0:
                if (count != 0)
                    check(workspace.writeScalar(offset) == current.write(offset), "random previous write state");
                break;
            case 1:
                if (count != 0) {
                    workspace.clearArray(offset, 1, 1);
                    current.clear(offset);
                }
                break;
            case 2:
                workspace.load(row);
                current = rows[row];
                break;
            case 3:
                check(workspace.join(row) == rows[row].join(current), "random changed join differs");
                break;
            case 4:
                check(workspace.retain() == rows.size(), "random ordinal differs");
                rows.push_back(current);
                break;
            }
            check(workspace.currentCount() == current.count() && workspace.retainedCountAt(row) == rows[row].count(),
                  "random logical counts differ");
            if (step % 41 == 0)
                matches(workspace, current, offsets);
        }
        for (std::size_t row = 0; row < rows.size(); ++row) {
            workspace.load(row);
            matches(workspace, rows[row], offsets);
        }
    }
}
struct ObjectFacts {
    int base;
    std::vector<int> leaves;
    ObjectCompletion incomplete;
};
const std::vector<ObjectFacts> objectFacts{{8, {8, 7}, ObjectCompletion::physical},
                                           {16, {}, ObjectCompletion::missing_empty},
                                           {32, {32, 31}, ObjectCompletion::missing_nested},
                                           {40, {}, ObjectCompletion::missing_nested}};
const std::vector<int> objectScalars{7, 8, 31, 32};
enum class ReceiverEntry {
    none,
    constructor,
    method,
    mutable_method,
    borrowed,
    mutable_borrowed,
    borrowed_pair
};
// A logical receiver field: a scalar ("u8"), owned bytes ("bytes") or a class name.
struct Field {
    std::string type;
    int firstLeaf;
    int length;
    bool array;
    int elementCount = 1;
    bool isClass() const {
        return type != "u8" && type != "bytes";
    }
    std::string text() const {
        return "(" + (isClass() ? "(class " + type + ")" : type) + ' ' + std::to_string(firstLeaf) + ' ' +
               std::to_string(length) + ' ' + (array ? "true" : "false") + ' ' + std::to_string(elementCount) + ')';
    }
};
const std::vector<Field> receiverFields{{"u8", 0, 1, false},
                                        {"u8", 1, 3, true},
                                        {"Nested", 4, 2, false},
                                        {"Empty", 6, 0, false},
                                        {"bytes", 6, 0, false},
                                        {"Nested", 6, 4, true, 2},
                                        {"Empty", 10, 0, true, 3},
                                        {"NestedEmpty", 10, 0, false}};
std::unique_ptr<Metadata> objectDeclarations(const std::vector<int> &scalars = objectScalars,
                                             const std::vector<ObjectFacts> &objects = objectFacts,
                                             const std::vector<Field> &fields = {},
                                             ReceiverEntry entry = ReceiverEntry::none) {
    const std::map<std::string, int> childLeaves{{"Box", 2}, {"Empty", 0}, {"Nested", 2}, {"NestedEmpty", 0}};
    std::string module = "layout Box [u8 u8]\nlayout Empty []\nlayout Nested [u8 u8]\nlayout NestedEmpty []\n"
                         "layout Octet [u8*8]\nfields Nested [((class Box) 0 2 false)]\n"
                         "fields NestedEmpty [((class Empty) 0 0 false)]\n";
    std::string function = "function object_facts\n  result i64\n  frame 65536\n";
    for (int offset : scalars)
        function += "  slot " + std::to_string(offset) + " u8\n";
    for (const auto &object : objects) {
        const auto name = object.incomplete == ObjectCompletion::physical
                              ? (object.leaves.size() == 8 ? "Octet" : "Box")
                          : object.incomplete == ObjectCompletion::missing_empty ? "Empty"
                          : object.leaves.empty()                                ? "NestedEmpty"
                                                                                 : "Nested";
        function += "  object " + std::to_string(object.base) + ' ' + name + " false\n";
    }
    if (entry != ReceiverEntry::none) {
        // The receiver's leaves are its fields' scalars and their classes' leaves.
        std::string leaves, logical;
        for (const auto &field : fields) {
            const auto count = field.isClass() ? childLeaves.at(field.type) * field.elementCount : field.length;
            for (int leaf = 0; leaf < count; ++leaf)
                leaves += field.type == "bytes" ? "bytes " : "u8 ";
            logical += field.text() + ' ';
        }
        module += "layout Receiver [" + leaves + "]\nfields Receiver [" + logical + "]\n";
        if (entry == ReceiverEntry::borrowed || entry == ReceiverEntry::mutable_borrowed ||
            entry == ReceiverEntry::borrowed_pair) {
            function += "  params [(class Receiver)";
            if (entry == ReceiverEntry::borrowed_pair) {
                module += "layout OtherOwner []\nfields OtherOwner [(bytes 0 0 false)]\n";
                function += " (class OtherOwner)";
            }
            function += std::string("]\n  roots ") + (entry == ReceiverEntry::borrowed_pair ? "2" : "1") +
                        "\n  rootmut " + (entry == ReceiverEntry::mutable_borrowed ? "1" : "0") + "\n";
        } else {
            function += std::string("  receiver Receiver ") + (entry != ReceiverEntry::method ? "true" : "false") +
                        (entry == ReceiverEntry::constructor ? " true\n" : " false\n");
            if (entry == ReceiverEntry::constructor && std::any_of(fields.begin(), fields.end(), [](const auto &field) {
                    return field.type == "bytes";
                }))
                function += "  params [region]\n";
        }
    }
    const auto facts = scalars.size() + objects.size() + (entry == ReceiverEntry::none ? 0 : fields.size());
    return Metadata::read(module + function + "end\n", facts);
}
// Negative keys keep logical object facts disjoint from physical scalar facts
// in the test-only set oracle, even when their canonical offsets are identical.
void referenceObject(Reference &expected, const ObjectFacts &object, bool clear = false) {
    for (int offset : object.leaves)
        if (clear)
            expected.clear(offset);
        else
            expected.write(offset);
    if (clear)
        expected.clear(-object.base);
    else
        expected.write(-object.base);
}
void matchesObjects(InitializationWorkspace &actual,
                    const Reference &expected,
                    const std::vector<int> &scalars = objectScalars,
                    const std::vector<ObjectFacts> &objects = objectFacts,
                    std::size_t receiverCount = 0) {
    check(actual.currentCount() == expected.count(), "combined initialization count differs from reference sets");
    check(actual.slotCount() == scalars.size() &&
              actual.wordCount() == (scalars.size() + objects.size() + receiverCount + 63) / 64,
          "combined word domain changed scalar slot count or omitted object/receiver bits");
    check(actual.logicalPayloadBytesPerSnapshot() == 2 * actual.wordCount() * sizeof(std::uint64_t),
          "object facts changed paired-word snapshot payload");
    for (int offset : scalars)
        check(actual.scalarState(offset) == expected.state(offset), "object operation changed wrong scalar bit");
    for (const auto &object : objects) {
        const bool initialized = std::all_of(object.leaves.begin(), object.leaves.end(), [&](int offset) {
            return expected.must.contains(offset);
        });
        const bool pristine = std::none_of(object.leaves.begin(), object.leaves.end(), [&](int offset) {
            return expected.may.contains(offset);
        });
        check(actual.objectInitialized(object.base) == initialized,
              "physical object must query includes logical facts");
        check(actual.objectPristine(object.base) == pristine, "physical object may query includes logical facts");
        check(actual.objectWasConstructed(object.base) == expected.may.contains(-object.base),
              "object construction query differs from logical may set");
        const auto completion = expected.must.contains(-object.base) ? ObjectCompletion::whole : object.incomplete;
        check(actual.objectCompletion(object.base) == completion, "object completion differs from logical must set");
    }
}
void objectCompletionAndIsolationTests() {
    auto metadata = objectDeclarations();
    InitializationWorkspace workspace(*metadata, 0);
    Reference expected;
    const auto empty = workspace.retain();
    matchesObjects(workspace, expected);
    // Leaf writes suffice for ordinary scalar-only use but do not mark whole completion.
    for (int offset : objectScalars) {
        workspace.writeScalar(offset);
        expected.write(offset);
    }
    matchesObjects(workspace, expected);
    const auto physical = workspace.retain();
    const auto physicalReference = expected;
    for (const auto &object : objectFacts) {
        workspace.markObject(object.base);
        referenceObject(expected, object);
        workspace.markObject(object.base);
        matchesObjects(workspace, expected);
    }
    const auto whole = workspace.retain();
    const auto wholeReference = expected;
    // Physical clearing must leave logical completion untouched.
    workspace.clearArray(8, 2, 1);
    expected.clear(8);
    expected.clear(7);
    matchesObjects(workspace, expected);
    check(workspace.arrayFirstMissing(8, 2, 1) == 0, "physical clear retained first scalar fact");
    workspace.writeScalar(8);
    expected.write(8);
    check(workspace.arrayFirstMissing(8, 2, 1) == 1, "first missing element order differs");
    for (const auto &object : objectFacts) {
        workspace.clearObject(object.base);
        referenceObject(expected, object, true);
        matchesObjects(workspace, expected);
    }
    for (const auto &[row, value] : std::array<std::pair<InitializationWorkspace::Id, Reference>, 3>{
             {{empty, {}}, {physical, physicalReference}, {whole, wholeReference}}}) {
        check(workspace.retainedCountAt(row) == value.count(), "object clear mutated retained row");
        workspace.load(row);
        matchesObjects(workspace, value);
    }
    for (std::size_t index = 3; index < 130; ++index) {
        check(workspace.retain() == index, "object retained ordinals changed during growth");
        check(workspace.retainedCountAt(index) == wholeReference.count(), "pool growth lost object facts");
    }
    workspace.load(empty);
    matchesObjects(workspace, {});
    workspace.load(whole);
    matchesObjects(workspace, wholeReference);
}
void differentialObjectJoins() {
    auto metadata = objectDeclarations();
    InitializationWorkspace workspace(*metadata, 0);
    std::array<InitializationWorkspace::Id, 16> rows{};
    std::array<Reference, 16> values{};
    const auto empty = workspace.retain();
    for (unsigned mask = 0; mask < rows.size(); ++mask) {
        workspace.load(empty);
        for (unsigned bit = 0; bit < objectFacts.size(); ++bit)
            if ((mask & (1u << bit)) != 0) {
                workspace.markObject(objectFacts[bit].base);
                referenceObject(values[mask], objectFacts[bit]);
            }
        rows[mask] = workspace.retain();
    }
    for (unsigned left = 0; left < rows.size(); ++left)
        for (unsigned right = 0; right < rows.size(); ++right) {
            workspace.load(rows[left]);
            const auto target = workspace.retain();
            workspace.load(rows[right]);
            auto expected = values[left];
            const bool changed = expected.join(values[right]);
            check(workspace.join(target) == changed, "object must AND/may OR changed result differs");
            matchesObjects(workspace, values[right]);
            check(workspace.retainedCountAt(target) == expected.count(), "object join retained cardinality differs");
            check(!workspace.join(target), "unchanged object backedge reported a change");
            workspace.load(target);
            matchesObjects(workspace, expected);
            if (left == 2 && right == 8)
                check(changed && expected.count() == values[left].count(),
                      "cardinality-canceling empty-object join did not report changed membership");
        }
    // Both paths have all physical leaves; only one completed the whole objects.
    workspace.load(empty);
    Reference leafOnly;
    for (int offset : objectScalars) {
        workspace.writeScalar(offset);
        leafOnly.write(offset);
    }
    const auto physical = workspace.retain();
    workspace.load(rows.back());
    check(workspace.join(physical), "whole/leaf-only branch did not change logical may bits");
    leafOnly.join(values.back());
    workspace.load(physical);
    matchesObjects(workspace, leafOnly);
}
void objectDomainBoundaryTests() {
    // Shared words, bits 63/64, 8,192 objects, and the combined 73,728-bit maximum.
    for (const auto [scalarCount, objectCount] : std::array<std::pair<std::size_t, std::size_t>, 13>{{{0, 1},
                                                                                                      {0, 63},
                                                                                                      {0, 64},
                                                                                                      {0, 65},
                                                                                                      {1, 63},
                                                                                                      {1, 64},
                                                                                                      {63, 1},
                                                                                                      {63, 2},
                                                                                                      {64, 1},
                                                                                                      {65, 64},
                                                                                                      {127, 2},
                                                                                                      {0, 8192},
                                                                                                      {65536, 8192}}}) {
        const auto scalars = denseOffsets(scalarCount);
        std::vector<ObjectFacts> objects;
        for (std::size_t index = 0; index < objectCount; ++index) {
            if (scalarCount == 65536) {
                const int base = static_cast<int>((index + 1) * 8);
                objects.push_back({base,
                                   {base, base - 1, base - 2, base - 3, base - 4, base - 5, base - 6, base - 7},
                                   ObjectCompletion::physical});
            } else
                objects.push_back(
                    {static_cast<int>(((scalarCount + 7) / 8 + index + 1) * 8), {}, ObjectCompletion::missing_empty});
        }
        auto metadata = objectDeclarations(scalars, objects);
        InitializationWorkspace workspace(*metadata, 0);
        Reference expected;
        const auto empty = workspace.retain();
        for (int offset : scalars) {
            workspace.writeScalar(offset);
            expected.write(offset);
        }
        for (std::size_t index = 0; index < objects.size(); ++index) {
            if (scalarCount != 65536 && objects.size() > 129 && index != 0 && index != 62 && index != 63 &&
                index != 64 && index + 1 != objects.size())
                continue;
            workspace.markObject(objects[index].base);
            referenceObject(expected, objects[index]);
        }
        matchesObjects(workspace, expected, scalars, objects);
        const auto marked = workspace.retain();
        workspace.clearObject(objects.back().base);
        workspace.load(empty);
        matchesObjects(workspace, {}, scalars, objects);
        check(workspace.retainedCountAt(marked) == expected.count(), "boundary clear changed retained row");
        workspace.load(marked);
        matchesObjects(workspace, expected, scalars, objects);
    }
}
// Receiver fields share the same pair of sets, independently of their physical
// leaves and logical class observations. Keep their keys below all frame bases.
int receiverKey(std::size_t field) {
    return -65537 - static_cast<int>(field);
}
bool tracksReceiver(const Field &field) {
    return field.length > 0 || field.isClass();
}
unsigned receiverState(const Reference &expected, const Field &field, std::size_t index) {
    const bool must = expected.must.contains(receiverKey(index)), may = expected.may.contains(receiverKey(index));
    return (unsigned(field.length == 0 || must) * ReceiverFieldFact::physical_initialized) |
           (unsigned(field.length > 0 && may) * ReceiverFieldFact::physical_written) |
           (unsigned(field.isClass() && must) * ReceiverFieldFact::logical_initialized) |
           (unsigned(field.isClass() && may) * ReceiverFieldFact::logical_written);
}
void matchesReceiver(InitializationWorkspace &actual,
                     const Reference &expected,
                     const std::vector<Field> &fields = receiverFields,
                     const std::vector<int> &scalars = objectScalars,
                     const std::vector<ObjectFacts> &objects = objectFacts) {
    matchesObjects(actual, expected, scalars, objects, fields.size());
    for (std::size_t index = 0; index < fields.size(); ++index)
        if (fields.size() <= 129 || index == 0 || index == 62 || index == 63 || index == 64 || index == 127 ||
            index == 128 || index == 8192 || index == 65536 || index + 1 == fields.size())
            check(actual.receiverFieldState(static_cast<int>(index)) == receiverState(expected, fields[index], index),
                  "receiver field flags differ from the shared reference sets");
    auto completion = ReceiverCompletion::complete;
    for (std::size_t index = 0; index < fields.size(); ++index)
        if (!expected.must.contains(receiverKey(index))) {
            if (fields[index].length > 0) {
                completion = ReceiverCompletion::missing_physical;
                break;
            }
            if (fields[index].isClass())
                completion = ReceiverCompletion::missing_logical;
        }
    check(actual.receiverCompletion() == completion, "receiver completion lost physical-before-logical precedence");
}
void receiverEntryAndIsolationTests() {
    for (const auto entry : {ReceiverEntry::constructor,
                             ReceiverEntry::method,
                             ReceiverEntry::mutable_method,
                             ReceiverEntry::borrowed,
                             ReceiverEntry::mutable_borrowed,
                             ReceiverEntry::borrowed_pair}) {
        auto metadata = objectDeclarations(objectScalars, objectFacts, receiverFields, entry);
        InitializationWorkspace workspace(*metadata, 0), independent(*metadata, 0);
        Reference expected;
        if (entry != ReceiverEntry::constructor)
            for (std::size_t index = 0; index < receiverFields.size(); ++index)
                if (tracksReceiver(receiverFields[index]))
                    expected.write(receiverKey(index));
        const auto initialReference = expected;
        const auto initial = workspace.retain();
        matchesReceiver(workspace, expected);
        for (std::size_t index = 0; index < receiverFields.size(); ++index) {
            const auto &field = receiverFields[index];
            if (!tracksReceiver(field))
                continue;
            check(workspace.writeReceiverField(static_cast<int>(index)) == receiverState(expected, field, index),
                  "receiver write lost previous physical/logical flags");
            expected.write(receiverKey(index));
            check(workspace.writeReceiverField(static_cast<int>(index)) == receiverState(expected, field, index),
                  "repeated receiver write changed previous flags");
            matchesReceiver(workspace, expected);
        }
        for (const auto &object : objectFacts) {
            workspace.markObject(object.base);
            referenceObject(expected, object);
        }
        matchesReceiver(workspace, expected);
        matchesReceiver(independent, initialReference);
        const auto written = workspace.retain();
        check(workspace.retainedCountAt(initial) == initialReference.count(), "receiver writes mutated entry row");
        auto cleared = expected;
        for (const auto &object : objectFacts) {
            workspace.clearObject(object.base);
            referenceObject(cleared, object, true);
        }
        matchesReceiver(workspace, cleared);
        workspace.load(initial);
        matchesReceiver(workspace, initialReference);
        check(workspace.retainedCountAt(written) == expected.count(), "local clear mutated receiver snapshot");
        workspace.load(written);
        matchesReceiver(workspace, expected);
        for (std::size_t index = 2; index < 130; ++index)
            check(workspace.retain() == index && workspace.retainedCountAt(index) == expected.count(),
                  "retained pool growth lost receiver row or fact count");
        workspace.load(initial);
        matchesReceiver(workspace, initialReference);
        workspace.load(written);
        matchesReceiver(workspace, expected);
    }
}
void differentialReceiverJoins() {
    auto metadata = objectDeclarations(objectScalars, objectFacts, receiverFields, ReceiverEntry::constructor);
    InitializationWorkspace workspace(*metadata, 0);
    std::array<InitializationWorkspace::Id, 16> rows{};
    std::array<Reference, 16> values{};
    const auto empty = workspace.retain();
    // Exhaust every subset of scalar, array, nonempty class and empty class fields.
    for (unsigned mask = 0; mask < rows.size(); ++mask) {
        workspace.load(empty);
        for (unsigned bit = 0; bit < 4; ++bit)
            if ((mask & (1u << bit)) != 0) {
                workspace.writeReceiverField(bit);
                values[mask].write(receiverKey(bit));
            }
        rows[mask] = workspace.retain();
    }
    for (unsigned left = 0; left < rows.size(); ++left)
        for (unsigned right = 0; right < rows.size(); ++right) {
            workspace.load(rows[left]);
            const auto target = workspace.retain();
            workspace.load(rows[right]);
            auto expected = values[left];
            const bool changed = expected.join(values[right]);
            check(workspace.join(target) == changed, "receiver must AND/may OR changed result differs");
            matchesReceiver(workspace, values[right]);
            check(workspace.retainedCountAt(target) == expected.count(), "receiver join retained count differs");
            check(!workspace.join(target), "unchanged receiver backedge reported a change");
            workspace.load(target);
            matchesReceiver(workspace, expected);
            if (left == 1 && right == 8)
                check(changed && expected.count() == values[left].count(),
                      "cardinality-canceling scalar/empty receiver join did not report changed membership");
            for (unsigned bit = 0; bit < 4; ++bit) {
                check(workspace.writeReceiverField(bit) == receiverState(expected, receiverFields[bit], bit),
                      "receiver write after join lost may-only flags");
                expected.write(receiverKey(bit));
            }
            matchesReceiver(workspace, expected);
        }
    workspace.load(empty);
    workspace.markObject(objectFacts[1].base);
    Reference expected;
    referenceObject(expected, objectFacts[1]);
    const auto local = workspace.retain();
    workspace.load(rows[8]);
    check(workspace.join(local) == expected.join(values[8]), "cross-domain receiver/object join differs");
    check(expected.count() == 2, "cross-domain join did not preserve the canceling cardinality");
    workspace.load(local);
    matchesReceiver(workspace, expected);
}
void receiverDomainBoundaryTests() {
    // Receiver bits follow both local domains, including when all three share a
    // word. Empty fields obey the same admitted class-field ceiling as scalar fields.
    for (const auto [scalarCount, objectCount, fieldCount] :
         std::array<std::array<std::size_t, 3>, 15>{{{0, 0, 0},
                                                     {0, 0, 1},
                                                     {0, 0, 63},
                                                     {0, 0, 64},
                                                     {0, 0, 65},
                                                     {1, 0, 63},
                                                     {1, 0, 64},
                                                     {0, 1, 63},
                                                     {0, 1, 64},
                                                     {63, 1, 1},
                                                     {63, 1, 65},
                                                     {64, 1, 1},
                                                     {65, 2, 63},
                                                     {0, 0, 8191},
                                                     {0, 0, 8192}}}) {
        const auto scalars = denseOffsets(scalarCount);
        std::vector<ObjectFacts> objects;
        for (std::size_t index = 0; index < objectCount; ++index)
            objects.push_back(
                {static_cast<int>(((scalarCount + 7) / 8 + index + 1) * 8), {}, ObjectCompletion::missing_empty});
        std::vector<Field> fields(fieldCount, {"Empty", 0, 0, false});
        if (fieldCount == 8191)
            fields.back() = {"Empty", 0, 0, true, 64};
        if (fieldCount == 8192)
            fields.back() = {"NestedEmpty", 0, 0, false};
        if (fieldCount == 65 || fieldCount >= 8191)
            fields[0] = {"bytes", 0, 0, false}; // Resource gaps still occupy canonical domain bits.
        for (const auto entry : {ReceiverEntry::constructor, ReceiverEntry::method}) {
            auto metadata = objectDeclarations(scalars, objects, fields, entry);
            InitializationWorkspace workspace(*metadata, 0);
            Reference expected;
            if (entry == ReceiverEntry::method)
                for (std::size_t index = 0; index < fieldCount; ++index)
                    if (tracksReceiver(fields[index]))
                        expected.write(receiverKey(index));
            const auto initialReference = expected;
            const auto initial = workspace.retain();
            matchesReceiver(workspace, expected, fields, scalars, objects);
            for (int offset : scalars) {
                workspace.writeScalar(offset);
                expected.write(offset);
            }
            for (const auto &object : objects) {
                workspace.markObject(object.base);
                referenceObject(expected, object);
            }
            for (std::size_t index = 0; index < fieldCount; ++index) {
                if (!tracksReceiver(fields[index]))
                    continue;
                if (fieldCount > 129 && index != 0 && index != 62 && index != 63 && index != 64 && index != 127 &&
                    index != 128 && index != 8192 && index != 65536 && index + 1 != fieldCount)
                    continue;
                check(workspace.writeReceiverField(static_cast<int>(index)) ==
                          receiverState(expected, fields[index], index),
                      "receiver boundary write lost previous flags");
                expected.write(receiverKey(index));
            }
            const auto written = workspace.retain();
            matchesReceiver(workspace, expected, fields, scalars, objects);
            workspace.load(initial);
            matchesReceiver(workspace, initialReference, fields, scalars, objects);
            check(workspace.retainedCountAt(written) == expected.count(), "receiver boundary row changed after load");
            workspace.load(written);
            matchesReceiver(workspace, expected, fields, scalars, objects);
        }
    }
}
void receiverFailureTests() {
    for (std::size_t count : {8193u, 73729u}) {
        const std::vector<Field> fields(count, {"Empty", 0, 0, false});
        rejects([&] {
            objectDeclarations({}, {}, fields, ReceiverEntry::constructor);
        });
    }
    auto metadata = objectDeclarations(objectScalars, objectFacts, receiverFields, ReceiverEntry::constructor);
    for (int invalid : {-1, static_cast<int>(receiverFields.size()), 65536, std::numeric_limits<int>::max()})
        for (bool write : {false, true}) {
            InitializationWorkspace workspace(*metadata, 0);
            rejects([&] {
                if (write)
                    (void)workspace.writeReceiverField(invalid);
                else
                    (void)workspace.receiverFieldState(invalid);
            });
        }
    for (std::size_t index = 0; index < receiverFields.size(); ++index)
        if (!tracksReceiver(receiverFields[index])) {
            InitializationWorkspace workspace(*metadata, 0);
            check(workspace.receiverFieldState(static_cast<int>(index)) == ReceiverFieldFact::physical_initialized,
                  "resource-only receiver field acquired a tracked fact");
            rejects([&] {
                (void)workspace.writeReceiverField(static_cast<int>(index));
            });
        }
    for (const auto &fields : std::vector<std::vector<Field>>{{}, {{"bytes", 0, 0, false}}}) {
        auto leafless = objectDeclarations({}, {}, fields, ReceiverEntry::constructor);
        InitializationWorkspace workspace(*leafless, 0);
        matchesReceiver(workspace, {}, fields, {}, {});
        check(workspace.receiverCompletion() == ReceiverCompletion::complete,
              "zero-field or resource-only receiver requires an initialization bit");
        rejects([&] {
            (void)workspace.writeReceiverField(0);
        });
    }
    auto noReceiver = objectDeclarations();
    for (unsigned operation = 0; operation < 3; ++operation) {
        InitializationWorkspace workspace(*noReceiver, 0);
        rejects([&] {
            if (operation == 0)
                (void)workspace.receiverFieldState(0);
            else if (operation == 1)
                (void)workspace.writeReceiverField(0);
            else
                (void)workspace.receiverCompletion();
        });
    }
}
std::unique_ptr<Metadata> serviceDeclarations(std::size_t count) {
    std::string parameters, slots;
    for (std::size_t index = 0; index < count; ++index) {
        parameters += index == 0 ? "console " : "display ";
        slots += "  service " + std::to_string((index + 1) * 16) + "\n";
    }
    return Metadata::read("function service_facts\n  result i64\n  params [" + parameters + "]\n  frame " +
                              std::to_string(count * 16) + "\n" + slots + "end\n",
                          0);
}
void serviceLoanLifecycleTests() {
    using Kind = aurora::testing::ServiceKind;
    using CallState = InitializationWorkspace::ServiceCallState;
    const std::array<int, 2> ids{7, std::numeric_limits<int>::max()};
    const std::array<Kind, 2> kinds{Kind::Console, Kind::Display};
    for (std::size_t count : {0u, 1u, 2u}) {
        auto metadata = serviceDeclarations(count);
        InitializationWorkspace workspace(*metadata, 0), independent(*metadata, 0);
        const auto empty = workspace.retain();
        check(workspace.slotCount() == 0 && workspace.wordCount() == 0,
              "service-only workspace allocated initialization bits");
        check(workspace.logicalPayloadBytesPerSnapshot() == count * 32,
              "service storage must follow leading capacity, independently of sparse loan IDs");
        check(workspace.currentCount() == 0 && workspace.retainedCountAt(empty) == 0 &&
                  workspace.serviceLoansClosed() && workspace.sameServiceLoans(empty),
              "service entry authority became a dynamic fact");
        if (count == 0) {
            check(!workspace.join(empty), "empty service-only join changed initialization");
            workspace.load(empty);
            check(workspace.logicalPayloadBytesPerSnapshot() == 0 && workspace.serviceLoansClosed(),
                  "zero-service snapshot acquired storage or a loan");
            continue;
        }
        for (std::size_t index = 0; index < count; ++index) {
            const int root = static_cast<int>((index + 1) * 16);
            check(workspace.serviceUnsuspended(root), "entry root starts suspended");
            check(workspace.acquireServiceLoan(ids[index], root, kinds[index]), "valid service acquisition failed");
            check(!workspace.serviceUnsuspended(root) && workspace.currentCount() == index + 1,
                  "active service loan missing from count or suspension query");
        }
        const auto acquired = workspace.retain();
        check(!workspace.serviceLoansClosed() && !workspace.sameServiceLoans(empty),
              "unused service loans were treated as a closed row");
        const int second = count == 2 ? ids[1] : 0;
        const auto callState = [&] {
            return workspace.validateServiceCall(ids[0], Kind::Console, second, Kind::Display);
        };
        check(callState() == CallState::ready && callState() == CallState::ready &&
                  workspace.sameServiceLoans(acquired),
              "call validation consumed a loan before ordinary argument validation");
        check(independent.serviceLoansClosed() && independent.currentCount() == 0,
              "service loans escaped their per-function workspace");
        for (std::size_t index = 0; index < count; ++index) {
            const int root = static_cast<int>((index + 1) * 16);
            check(!workspace.acquireServiceLoan(ids[index], root, kinds[index]) &&
                      !workspace.acquireServiceLoan(8, root, kinds[index]) &&
                      !workspace.releaseServiceLoan(ids[index], kinds[index]),
                  "duplicate acquisition or premature release was accepted");
            check(workspace.sameServiceLoans(acquired) && workspace.currentCount() == count,
                  "failed service transition changed the current row");
        }
        check(workspace.validateServiceCall(8, Kind::Console) == CallState::missing &&
                  workspace.validateServiceCall(ids[0], Kind::Display) == CallState::provenance &&
                  workspace.sameServiceLoans(acquired),
              "missing or mismatched call validation changed service facts");
        workspace.load(empty);
        for (std::size_t reverse = count; reverse > 0; --reverse) {
            const auto index = reverse - 1;
            check(workspace.acquireServiceLoan(ids[index], static_cast<int>((index + 1) * 16), kinds[index]),
                  "reverse-order service acquisition failed");
        }
        check(workspace.sameServiceLoans(acquired) && !workspace.join(acquired),
              "equal service states depend on acquisition order or change initialization join");
        workspace.completeServiceCall(ids[0]);
        const auto firstCalled = workspace.retain();
        check(!workspace.sameServiceLoans(acquired) && workspace.currentCount() == count &&
                  workspace.retainedCountAt(firstCalled) == count && callState() == CallState::provenance,
              "exact service equality omitted called state or counted it as another fact");
        check(!workspace.releaseServiceLoan(ids[0], Kind::Display) && workspace.sameServiceLoans(firstCalled),
              "wrong-kind release changed a called loan");
        if (count == 2)
            check(workspace.validateServiceCall(ids[1], Kind::Display) == CallState::ready &&
                      workspace.validateServiceCall(ids[0], Kind::Console, 8, Kind::Display) == CallState::provenance &&
                      workspace.validateServiceCall(8, Kind::Console, ids[0], Kind::Console) == CallState::missing,
                  "partial completion changed another loan or call-position diagnostic precedence");
        check(workspace.releaseServiceLoan(ids[0], Kind::Console) &&
                  workspace.acquireServiceLoan(ids[0], 16, Kind::Console) && workspace.sameServiceLoans(acquired),
              "released lexical identity preserved old called state");
        workspace.completeServiceCall(ids[0], second);
        const auto called = workspace.retain();
        check(!workspace.sameServiceLoans(acquired) && callState() == CallState::provenance,
              "completed service call remained reusable");
        for (std::size_t index = 0; index < count; ++index) {
            check(workspace.releaseServiceLoan(ids[index], kinds[index]), "completed service release failed");
            check(workspace.serviceUnsuspended(static_cast<int>((index + 1) * 16)) &&
                      workspace.currentCount() == count - index - 1,
                  "release retained a service loan or root suspension");
        }
        check(workspace.serviceLoansClosed() && workspace.sameServiceLoans(empty) &&
                  workspace.retainedCountAt(acquired) == count && workspace.retainedCountAt(called) == count,
              "release changed retained service facts");
        workspace.load(called);
        check(callState() == CallState::provenance && !workspace.serviceLoansClosed(),
              "load lost the retained called state");
        workspace.load(acquired);
        check(callState() == CallState::ready, "load did not restore unused loans");
        for (std::size_t row = workspace.retainedCount(); row < 130; ++row)
            check(workspace.retain() == row && workspace.retainedCountAt(row) == count,
                  "service snapshot growth lost stable ordinals or logical counts");
        workspace.load(firstCalled);
        check(workspace.sameServiceLoans(firstCalled) && !workspace.sameServiceLoans(acquired),
              "service pool growth changed an earlier called-state row");
        workspace.load(empty);
        check(workspace.serviceLoansClosed() && workspace.currentCount() == 0,
              "service snapshot growth changed the empty row");
        rejects([&] {
            (void)workspace.sameServiceLoans(workspace.retainedCount());
        });
    }
}
void objectAndFailureTests() {
    auto metadata = objectDeclarations();
    for (int invalid : {-1, 0, 7, 9, 15, 17, 65537})
        for (unsigned operation = 0; operation != 6; ++operation) {
            InitializationWorkspace workspace(*metadata, 0);
            rejects([&] {
                if (operation == 0)
                    (void)workspace.objectInitialized(invalid);
                else if (operation == 1)
                    (void)workspace.objectPristine(invalid);
                else if (operation == 2)
                    (void)workspace.objectWasConstructed(invalid);
                else if (operation == 3)
                    (void)workspace.objectCompletion(invalid);
                else if (operation == 4)
                    workspace.markObject(invalid);
                else
                    workspace.clearObject(invalid);
            });
        }
    for (unsigned operation = 0; operation != 3; ++operation) {
        InitializationWorkspace workspace(*metadata, 0);
        workspace.markObject(8);
        const auto retained = workspace.retain();
        rejects([&] {
            if (operation == 0)
                workspace.load(retained + 1);
            else if (operation == 1)
                workspace.join(retained + 1);
            else
                workspace.writeScalar(6);
        });
    }
    rejects([&] {
        InitializationWorkspace workspace(*metadata, metadata->callableCount());
    });
}
} // namespace

int main() {
    try {
        checks += initializationOwnershipChecks();
        factRestoreTests();
        boundaryAndIsolationTests();
        differentialJoins();
        randomizedRetainedRows();
        objectCompletionAndIsolationTests();
        differentialObjectJoins();
        objectDomainBoundaryTests();
        receiverEntryAndIsolationTests();
        differentialReceiverJoins();
        receiverDomainBoundaryTests();
        receiverFailureTests();
        serviceLoanLifecycleTests();
        objectAndFailureTests();
        std::cout << "PASS initialization workspace: " << checks << " checks against reference sets\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "FAIL initialization workspace: " << error.what() << '\n';
        return 1;
    }
}
