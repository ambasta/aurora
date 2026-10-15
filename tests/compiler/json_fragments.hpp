#pragma once
#include <stdexcept>
#include <string_view>

namespace aurora::test {
// Test-only observations of compact JSON. Visit immediate members without
// decoding values or reconstructing production stack-fact types.
template <class Visitor> void jsonMembers(std::string_view object, Visitor visit) {
    if (!object.empty() && object.back() == '\n')
        object.remove_suffix(1);
    const auto invalid = [] {
        throw std::runtime_error("invalid test JSON object fragment");
    };
    if (object.size() < 2 || object.front() != '{' || object.back() != '}')
        invalid();
    std::size_t at = 1;
    while (at + 1 < object.size()) {
        if (object[at++] != '"')
            invalid();
        const auto key = at;
        while (at < object.size() && object[at] != '"') {
            if (object[at] == '\\')
                ++at;
            ++at;
        }
        if (at + 1 >= object.size() || object[at + 1] != ':')
            invalid();
        const auto name = object.substr(key, at - key);
        at += 2;
        const auto begin = at;
        int depth = 0;
        bool quoted = false;
        for (; at < object.size(); ++at) {
            const char byte = object[at];
            if (quoted) {
                if (byte == '\\')
                    ++at;
                else if (byte == '"')
                    quoted = false;
            } else if (byte == '"') {
                quoted = true;
            } else if (byte == '{' || byte == '[') {
                ++depth;
            } else if (byte == '}' || byte == ']') {
                if (depth == 0)
                    break;
                --depth;
            } else if (byte == ',' && depth == 0) {
                break;
            }
        }
        if (at == begin || at >= object.size() || depth != 0 || quoted)
            invalid();
        visit(name, object.substr(begin, at - begin));
        if (object[at] == '}') {
            if (at + 1 != object.size())
                invalid();
            return;
        }
        if (object[at++] != ',' || at + 1 == object.size())
            invalid();
    }
}
inline std::string_view jsonMember(std::string_view object, std::string_view key) {
    std::string_view result;
    jsonMembers(object, [&](std::string_view name, std::string_view value) {
        if (name == key) {
            if (!result.empty())
                throw std::runtime_error("duplicate test JSON object member");
            result = value;
        }
    });
    return result;
}
inline std::size_t jsonMemberCount(std::string_view object) {
    std::size_t count = 0;
    jsonMembers(object, [&](std::string_view, std::string_view) {
        ++count;
    });
    return count;
}
} // namespace aurora::test
