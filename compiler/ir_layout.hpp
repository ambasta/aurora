#pragma once
#include "ir.hpp"
#include <algorithm>
#include <functional>

namespace aurora::ir {
// Bool and all pre-byte scalar representations retain their historical eight-byte
// storage slots. Numeric range and occupied storage width are distinct contracts.
inline int storageWidth(const Type &type) {
    return type == Type::U8 ? 1 : 8;
}
inline int storageAlignment(const Type &type) {
    return storageWidth(type);
}
inline bool copiedClassLeavesSupported(const std::vector<Type> &leaves) {
    if (leaves.size() > maximumCopiedClassLeaves)
        return false;
    const auto bytes = std::count(leaves.begin(), leaves.end(), Type::U8);
    return bytes <= maximumCopiedByteLeaves &&
           leaves.size() - static_cast<std::size_t>(bytes) <= maximumCopiedNonByteLeaves;
}
inline int roundedStorage(int bytes) {
    if (bytes < 0 || bytes > 65536)
        throw Error("IR: storage extent exceeds 65536 bytes");
    return (std::max(bytes, 1) + 7) / 8 * 8;
}

// This computation consumes logical shape, not caller-provided byte offsets.
// validate() checks the shape first and compares any supplied physical metadata
// with this canonical result. Semantic lowering uses the same representation rule.
inline std::map<std::string, ClassStorage>
computeClassStorageLayouts(const std::map<std::string, std::vector<Type>> &leaves,
                           const std::map<std::string, std::vector<ClassField>> &fields) {
    std::map<std::string, ClassStorage> result;
    std::set<std::string> visiting;
    std::function<const ClassStorage &(const std::string &, int)> build;
    build = [&](const std::string &name, int depth) -> const ClassStorage & {
        if (depth > 4 || visiting.contains(name))
            throw Error("IR: cyclic or excessive class storage depth");
        if (result.contains(name))
            return result.at(name);
        if (!leaves.contains(name) || !fields.contains(name))
            throw Error("IR: missing logical class storage shape");
        visiting.insert(name);
        ClassStorage layout;
        layout.alignment = 1;
        int cursor = 0;
        auto align = [&](int alignment) {
            if (alignment != 1 && alignment != 8)
                throw Error("IR: invalid class storage alignment");
            cursor = (cursor + alignment - 1) / alignment * alignment;
            layout.alignment = std::max(layout.alignment, alignment);
        };
        for (const auto &field : fields.at(name)) {
            if (field.firstLeaf != static_cast<int>(layout.leafOffsets.size()) || field.length < 0 ||
                (!(field.array && field.elementType.isClass()) && field.elementCount != 1))
                throw Error("IR: invalid logical field range for storage");
            if (field.elementType == Type::OwnedBytes) {
                if (field.array || field.length != 0)
                    throw Error("IR: owned byte field requires one non-scalar descriptor");
                align(8);
                layout.fieldOffsets.push_back(cursor);
                cursor += 32;
            } else if (field.elementType.isClass()) {
                if (owningClass(fields, field.elementType.className))
                    throw Error("IR: nested owning class fields are unsupported");
                const auto &child = build(field.elementType.className, depth + 1);
                const int count = field.array ? field.elementCount : 1;
                if (count < 1 || count > maximumClassScalarArrayLength || (!field.array && field.elementCount != 1) ||
                    field.length != static_cast<int>(child.leafOffsets.size()) * count)
                    throw Error("IR: invalid nested field storage shape");
                // Empty nested values carry logical completion but no scalar payload.
                // Their standalone eight-byte reservation must not widen old parents.
                const bool empty = child.leafOffsets.empty();
                align(empty ? 1 : child.alignment);
                layout.fieldOffsets.push_back(cursor);
                for (int element = 0; element < count; ++element)
                    for (int offset : child.leafOffsets)
                        layout.leafOffsets.push_back(cursor + element * child.sizeBytes + offset);
                if (!empty)
                    cursor += count * child.sizeBytes;
            } else {
                if (!(field.array ? scalar(field.elementType) : scalarValue(field.elementType)) || field.length < 1 ||
                    (!field.array && field.length != 1) ||
                    (field.array && field.length > maximumClassArrayLength(field.elementType)))
                    throw Error("IR: invalid scalar field storage shape");
                align(storageAlignment(field.elementType));
                layout.fieldOffsets.push_back(cursor);
                for (int index = 0; index < field.length; ++index) {
                    layout.leafOffsets.push_back(cursor);
                    cursor += storageWidth(field.elementType);
                }
            }
            if (cursor > 65536)
                throw Error("IR: class storage exceeds 65536 bytes");
        }
        if (layout.leafOffsets.size() != leaves.at(name).size())
            throw Error("IR: class storage does not cover logical leaves");
        if (cursor == 0) {
            layout.sizeBytes = 8;
            layout.alignment = 8;
        } else {
            align(layout.alignment);
            layout.sizeBytes = cursor;
        }
        layout.reservedBytes = roundedStorage(layout.sizeBytes);
        visiting.erase(name);
        return result.emplace(name, std::move(layout)).first->second;
    };
    for (const auto &[name, unused] : leaves) {
        (void)unused;
        build(name, 1);
    }
    return result;
}
} // namespace aurora::ir
