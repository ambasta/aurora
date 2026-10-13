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
        std::set_intersection(must.begin(), must.end(), incoming.must.begin(), incoming.must.end(),
                              std::inserter(common, common.end()));
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
                check(actual.scalarState(offsets[index]) == expected.state(offsets[index]), "boundary membership differs");
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
void objectAndFailureTests() {
    Module module;
    module.classLayouts["Box"] = {Type::U8, Type::U8};
    module.classLayouts["Empty"] = {};
    aurora::ir::Function function;
    function.name = "objects";
    function.result = Type::I64;
    function.frameBytes = 16;
    function.slots = {{8, Type::U8}, {7, Type::U8}};
    function.objectSlots = {{8, {"Box", false}}, {16, {"Empty", false}}};
    module.functions.push_back(function);
    auto metadata = Metadata::import(module);
    {
        InitializationWorkspace workspace(*metadata, 0);
        check(workspace.objectPristine(8) && !workspace.objectInitialized(8), "fresh object facts");
        check(workspace.objectInitialized(16) && workspace.objectPristine(16),
              "zero-leaf facts acquired logical empty-object completion responsibility");
        workspace.markObject(8);
        const auto full = workspace.retain();
        check(workspace.objectInitialized(8) && !workspace.objectPristine(8), "complete object facts");
        workspace.clearObject(8);
        check(workspace.objectPristine(8) && workspace.arrayFirstMissing(8, 2, 1) == 0,
              "lifetime clear kept must/may facts");
        workspace.writeScalar(8);
        check(workspace.arrayFirstMissing(8, 2, 1) == 1, "first missing element order differs");
        workspace.writeScalar(7);
        check(!workspace.arrayFirstMissing(8, 2, 1), "complete array still has a missing element");
        workspace.load(full);
        check(workspace.objectInitialized(8), "object clear mutated the retained snapshot");
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
    rejects([&] { InitializationWorkspace workspace(*metadata, metadata->callableCount()); });
}
} // namespace

int main() {
    try {
        boundaryAndIsolationTests();
        differentialJoins();
        randomizedRetainedRows();
        objectAndFailureTests();
        std::cout << "PASS initialization workspace: " << checks << " checks against reference sets\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "FAIL initialization workspace: " << error.what() << '\n';
        return 1;
    }
}
