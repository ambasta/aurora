// The reference sets live only in this fixture. Every observed operation goes
// through the real per-function Aurora owner and its private generated bridge.
#include "hosted_ir_initialization.hpp"
#include "ir.hpp"
#include <algorithm>
#include <array>
#include <functional>
#include <iostream>
#include <numeric>
#include <random>
#include <set>
#include <type_traits>

using aurora::Error;
using aurora::Type;
using aurora::ir::InitializationWorkspace;
using aurora::ir::Metadata;
using aurora::ir::Module;
using ObjectCompletion = InitializationWorkspace::ObjectCompletion;

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
std::unique_ptr<Metadata> declarations(const std::vector<int> &offsets) {
    aurora::ir::Function function;
    function.name = "facts";
    function.result = Type::I64;
    function.frameBytes = offsets.empty() ? 0 : 65536;
    for (int offset : offsets)
        function.slots.emplace(offset, Type::U8);
    Module module;
    module.functions.push_back(std::move(function));
    return Metadata::import(module);
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
std::unique_ptr<Metadata> objectDeclarations(const std::vector<int> &scalars = objectScalars,
                                             const std::vector<ObjectFacts> &objects = objectFacts) {
    Module module;
    module.classLayouts = {
        {"Box", {Type::U8, Type::U8}}, {"Empty", {}}, {"Nested", {Type::U8, Type::U8}}, {"NestedEmpty", {}}};
    module.classLayouts["Octet"] = std::vector<Type>(8, Type::U8);
    module.classFields["Nested"] = {{Type("Box"), 0, 2, false}};
    module.classFields["NestedEmpty"] = {{Type("Empty"), 0, 0, false}};
    aurora::ir::Function function;
    function.name = "object_facts";
    function.result = Type::I64;
    function.frameBytes = 65536;
    for (int offset : scalars)
        function.slots[offset] = Type::U8;
    for (const auto &object : objects) {
        const auto name = object.incomplete == ObjectCompletion::physical
                              ? (object.leaves.size() == 8 ? "Octet" : "Box")
                          : object.incomplete == ObjectCompletion::missing_empty ? "Empty"
                          : object.leaves.empty()                                ? "NestedEmpty"
                                                                                 : "Nested";
        function.objectSlots[object.base] = {name, false};
    }
    module.functions.push_back(std::move(function));
    return Metadata::import(module);
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
                    const std::vector<ObjectFacts> &objects = objectFacts) {
    check(actual.currentCount() == expected.count(), "combined scalar/object count differs from reference sets");
    check(actual.slotCount() == scalars.size() && actual.wordCount() == (scalars.size() + objects.size() + 63) / 64,
          "combined word domain changed scalar slot count or omitted object bits");
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
        boundaryAndIsolationTests();
        differentialJoins();
        randomizedRetainedRows();
        objectCompletionAndIsolationTests();
        differentialObjectJoins();
        objectDomainBoundaryTests();
        objectAndFailureTests();
        std::cout << "PASS initialization workspace: " << checks << " checks against reference sets\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "FAIL initialization workspace: " << error.what() << '\n';
        return 1;
    }
}
