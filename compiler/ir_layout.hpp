#pragma once
#include "ir.hpp"
#include <algorithm>

namespace aurora::ir {
// Bool and all pre-byte scalar representations retain their historical eight-byte
// storage slots. Numeric range and occupied storage width are distinct contracts.
inline int storageWidth(const Type &type) {
    return type == Type::U8 ? 1 : 8;
}
inline int storageAlignment(const Type &type) {
    return storageWidth(type);
}
template <class Leaves> inline bool copiedClassLeavesSupported(const Leaves &leaves) {
    if (leaves.size() > maximumCopiedClassLeaves)
        return false;
    const auto bytes = std::count(leaves.begin(), leaves.end(), Type::U8);
    return bytes <= maximumCopiedByteLeaves &&
           leaves.size() - static_cast<std::size_t>(bytes) <= maximumCopiedNonByteLeaves;
}
} // namespace aurora::ir
