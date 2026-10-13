#pragma once
#include "ir.hpp"

namespace aurora::ir {
// Bool and all pre-byte scalar representations retain their historical eight-byte
// storage slots. Numeric range and occupied storage width are distinct contracts.
inline int storageWidth(const Type &type) {
    return type == Type::U8 ? 1 : 8;
}
inline int storageAlignment(const Type &type) {
    return storageWidth(type);
}
} // namespace aurora::ir
