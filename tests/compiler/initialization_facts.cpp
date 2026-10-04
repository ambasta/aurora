#include "initialization_facts.hpp"
#include <array>
#include <functional>
#include <iostream>
#include <numeric>
#include <random>
#include <set>
#include <type_traits>

using aurora::Error;
using aurora::ir::verification::InitializationFacts;
using aurora::ir::verification::InitializationSlotUniverse;

namespace {
std::size_t checks = 0;
void check(bool condition, const std::string &message) {
    if (!condition)
        throw Error(message);
    ++checks;
}
void rejects(const std::function<void()> &operation, const std::string &diagnostic) {
    try {
        operation();
    } catch (const Error &error) {
        check(std::string(error.what()).find(diagnostic) != std::string::npos,
              "wrong initialization-facts diagnostic");
        return;
    }
    throw Error("malformed initialization-facts input was accepted");
}
std::shared_ptr<const InitializationSlotUniverse> universe(std::vector<int> offsets,
                                                          int frame = 65536) {
    return std::make_shared<const InitializationSlotUniverse>(std::move(offsets), frame);
}
std::vector<int> denseOffsets(std::size_t count) {
    std::vector<int> offsets(count);
    std::iota(offsets.begin(), offsets.end(), 1);
    return offsets;
}
void matches(const InitializationFacts &actual, const std::set<int> &expected,
             const InitializationSlotUniverse &domain) {
    check(actual.size() == expected.size(), "logical fact count differs from std::set");
    check(actual.wordCount() == domain.size() / 64 + (domain.size() % 64 != 0),
          "word storage is not exact ceil(slotCount / 64)");
    check(actual.payloadBytes() == actual.wordCount() * sizeof(std::uint64_t),
          "incorrect deterministic payload byte count");
    for (std::size_t index = 0; index < domain.size(); ++index) {
        const int offset = domain.offset(index);
        check(actual.contains(offset) == expected.contains(offset),
              "membership differs from std::set");
    }
    for (int absent : {std::numeric_limits<int>::min(), -1, 0, 65537,
                       std::numeric_limits<int>::max()})
        check(!actual.contains(absent), "unknown offset appears in initialization facts");
}
std::set<int> intersect(const std::set<int> &left, const std::set<int> &right) {
    std::set<int> result;
    std::set_intersection(left.begin(), left.end(), right.begin(), right.end(),
                          std::inserter(result, result.end()));
    return result;
}
std::set<int> unite(const std::set<int> &left, const std::set<int> &right) {
    std::set<int> result = left;
    result.insert(right.begin(), right.end());
    return result;
}
void malformedAndLifetimeTests() {
    static_assert(!std::is_copy_assignable_v<InitializationSlotUniverse>);
    for (int offset : {std::numeric_limits<int>::min(), -1, 0, 65537,
                       std::numeric_limits<int>::max()})
        rejects([&] { (void)universe({offset}); }, "offset");
    rejects([] { (void)universe({1, 1}); }, "duplicate");
    rejects([] { (void)universe({}, -1); }, "extent");
    rejects([] { (void)universe({}, 65537); }, "extent");
    rejects([] { (void)universe(denseOffsets(65537)); }, "extent");
    rejects([] { (void)universe({17}, 16); }, "offset");
    rejects([] { (void)InitializationFacts(nullptr); }, "missing");

    InitializationFacts empty;
    check(empty.size() == 0 && empty.wordCount() == 0 && empty.payloadBytes() == 0,
          "default value is not empty");
    check(empty == InitializationFacts(universe({}, 0)), "empty domain affects equality");
    check(!empty.contains(1) && empty.erase(1) == 0, "default membership/removal");
    rejects([&] { empty.insert(1); }, "validated scalar slot");

    auto domain = universe({65536, 1, 127, 8});
    std::weak_ptr<const InitializationSlotUniverse> lifetime = domain;
    InitializationFacts facts(domain);
    facts.insert(1);
    facts.insert(65536);
    for (int offset : {std::numeric_limits<int>::min(), -1, 0, 2, 65535, 65537,
                       std::numeric_limits<int>::max()}) {
        check(!facts.contains(offset) && facts.erase(offset) == 0,
              "unknown membership/removal differs from std::set");
        rejects([&] { facts.insert(offset); }, "validated scalar slot");
        check(facts.size() == 2, "failed insertion changed facts");
    }
    InitializationFacts copy = facts;
    copy.erase(1);
    check(facts.contains(1) && !copy.contains(1), "copies share mutable words");
    copy = facts;
    copy = copy;
    check(copy == facts, "copy/self assignment changes facts");
    domain.reset();
    check(!lifetime.expired() && facts.contains(65536), "facts lost their slot universe");
    InitializationFacts moved = std::move(copy);
    check(moved == facts && copy.size() == 0 && !copy.contains(1), "move construction");
    check(copy.erase(1) == 0, "moved-from removal");
    rejects([&] { copy.insert(1); }, "validated scalar slot");
    copy = std::move(moved);
    check(copy == facts && moved.size() == 0 && !moved.contains(65536), "move assignment");
    auto *self = &copy;
    copy = std::move(*self);
    check(copy == facts, "self move assignment");

    InitializationFacts reordered(universe({8, 127, 65536, 1}));
    reordered.insert(1);
    reordered.insert(65536);
    check(reordered == facts, "equivalent distinct universes affect equality");
    reordered.intersectWith(facts);
    reordered.unionWith(facts);
    check(reordered == facts, "joins of equivalent distinct universes");

    InitializationFacts narrow(universe({1, 65536}));
    narrow.insert(1);
    narrow.insert(65536);
    check(narrow == facts, "different domains affect equal set values");
    narrow.intersectWith(facts);
    facts.unionWith(narrow);
    check(narrow == facts, "cross-domain join changed equal set values");
    facts.insert(8);
    const auto before = narrow;
    rejects([&] { narrow.unionWith(facts); }, "validated scalar slot");
    check(narrow == before, "cross-domain union partially changed facts before failure");
    facts.intersectWith(narrow);
    check(facts == narrow, "cross-domain intersection differs from std::set");
    empty.unionWith(InitializationFacts(universe({2})));
    check(empty.size() == 0, "union with an empty foreign domain");
    facts.intersectWith(empty);
    check(facts.size() == 0, "intersection with an empty foreign domain");
}
void boundaryTests() {
    for (std::size_t count : {0u, 1u, 63u, 64u, 65u, 127u, 128u, 129u, 4096u, 65536u}) {
        auto domain = universe(denseOffsets(count));
        InitializationFacts actual(domain);
        std::set<int> expected;
        matches(actual, expected, *domain);
        for (std::size_t index = 0; index < count; ++index) {
            const int offset = domain->offset(index);
            check(actual.insert(offset) == expected.insert(offset).second, "first insertion");
            check(!actual.insert(offset), "repeated insertion changed count");
        }
        matches(actual, expected, *domain);
        auto full = actual;
        actual.unionWith(actual);
        actual.intersectWith(actual);
        check(actual == full, "self joins changed full words or tail");
        InitializationFacts zero(domain);
        full.intersectWith(zero);
        check(full == zero && full.size() == 0, "AND did not clear all words/tail");
        zero.unionWith(actual);
        check(zero == actual, "OR did not copy all words/tail");
        for (std::size_t index = count; index > 0; --index) {
            const int offset = domain->offset(index - 1);
            check(actual.erase(offset) == expected.erase(offset), "first removal");
            check(actual.erase(offset) == 0, "repeated removal changed count");
        }
        matches(actual, expected, *domain);
    }
    // Storage tracks dense slot count, even for widely separated byte offsets.
    auto sparse = universe({1, 32, 64, 4096, 65535, 65536});
    InitializationFacts sparseFacts(sparse);
    check(sparseFacts.wordCount() == 1, "sparse offsets allocate by raw frame offset");
    for (std::size_t index = 0; index < sparse->size(); ++index)
        sparseFacts.insert(sparse->offset(index));
    matches(sparseFacts, {1, 32, 64, 4096, 65535, 65536}, *sparse);
}
void exhaustiveTests() {
    for (unsigned count = 0; count <= 6; ++count) {
        std::vector<int> offsets;
        for (unsigned index = 0; index < count; ++index)
            offsets.push_back(static_cast<int>(index * 997 + 1));
        auto domain = universe(offsets);
        for (unsigned leftMask = 0; leftMask < (1u << count); ++leftMask) {
            InitializationFacts left(domain);
            std::set<int> leftSet;
            for (unsigned index = 0; index < count; ++index)
                if ((leftMask & (1u << index)) != 0) {
                    left.insert(offsets[index]);
                    leftSet.insert(offsets[index]);
                }
            for (unsigned rightMask = 0; rightMask < (1u << count); ++rightMask) {
                InitializationFacts right(domain);
                std::set<int> rightSet;
                for (unsigned index = 0; index < count; ++index)
                    if ((rightMask & (1u << index)) != 0) {
                        right.insert(offsets[index]);
                        rightSet.insert(offsets[index]);
                    }
                check((left == right) == (leftSet == rightSet), "exhaustive equality");
                auto joined = left;
                joined.intersectWith(right);
                matches(joined, intersect(leftSet, rightSet), *domain);
                joined = left;
                joined.unionWith(right);
                matches(joined, unite(leftSet, rightSet), *domain);
            }
        }
    }
}
void randomizedTests() {
    std::mt19937 random(0x1faca5u);
    for (std::size_t count : {0u, 1u, 63u, 64u, 65u, 129u, 4096u, 65536u}) {
        auto domain = universe(denseOffsets(count));
        std::array<InitializationFacts, 3> actual{
            InitializationFacts(domain), InitializationFacts(domain), InitializationFacts(domain)};
        std::array<std::set<int>, 3> expected;
        for (unsigned step = 0; step < 3000; ++step) {
            const auto left = random() % actual.size();
            const auto right = random() % actual.size();
            const int offset = count == 0 ? 1 : domain->offset(random() % count);
            switch (random() % 7) {
            case 0:
                if (count != 0)
                    check(actual[left].insert(offset) == expected[left].insert(offset).second,
                          "random insertion");
                break;
            case 1:
                check(actual[left].erase(offset) == expected[left].erase(offset), "random erase");
                break;
            case 2:
                actual[left].intersectWith(actual[right]);
                expected[left] = intersect(expected[left], expected[right]);
                break;
            case 3:
                actual[left].unionWith(actual[right]);
                expected[left] = unite(expected[left], expected[right]);
                break;
            case 4:
                actual[left] = actual[right];
                expected[left] = expected[right];
                break;
            case 5:
                check(actual[left].contains(offset) == expected[left].contains(offset),
                      "random membership");
                break;
            case 6:
                check((actual[left] == actual[right]) == (expected[left] == expected[right]),
                      "random comparison");
                break;
            }
            check(actual[left].size() == expected[left].size(), "random logical count");
            if (step % 97 == 0)
                for (std::size_t index = 0; index < actual.size(); ++index)
                    matches(actual[index], expected[index], *domain);
        }
        for (std::size_t index = 0; index < actual.size(); ++index)
            matches(actual[index], expected[index], *domain);
    }
}
} // namespace

int main() {
    try {
        malformedAndLifetimeTests();
        boundaryTests();
        exhaustiveTests();
        randomizedTests();
        std::cout << "PASS initialization facts: " << checks
                  << " checks against std::set, including 65,536 slots\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "FAIL initialization facts: " << error.what() << '\n';
        return 1;
    }
}
