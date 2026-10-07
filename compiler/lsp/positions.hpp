#pragma once
#include "transport.hpp"
#include <algorithm>
#include <cstdint>
#include <filesystem>

namespace aurora::lsp {
class Scalar {
public:
    std::size_t bytes = 1;
    unsigned value = 0xfffd;
    bool valid = false;
};
inline Scalar scalarAt(std::string_view text, std::size_t at) {
    if (at >= text.size())
        return {};
    const auto first = static_cast<unsigned char>(text[at]);
    if (first < 0x80)
        return {1, first, true};
    const std::size_t width = first >= 0xc2 && first <= 0xdf   ? 2
                              : first >= 0xe0 && first <= 0xef ? 3
                              : first >= 0xf0 && first <= 0xf4 ? 4
                                                               : 0;
    if (!width || width > text.size() - at)
        return {};
    unsigned scalar = first & (width == 2 ? 0x1f : width == 3 ? 0x0f : 0x07);
    for (std::size_t i = 1; i < width; ++i) {
        const auto next = static_cast<unsigned char>(text[at + i]);
        if (next < 0x80 || next > 0xbf)
            return {};
        scalar = (scalar << 6) | (next & 0x3f);
    }
    if ((width == 3 && scalar < 0x800) || (width == 4 && scalar < 0x10000) || scalar > 0x10ffff ||
        (scalar >= 0xd800 && scalar <= 0xdfff))
        return {};
    return {width, scalar, true};
}
inline bool validUtf8(std::string_view text) {
    for (std::size_t at = 0; at < text.size();) {
        const auto scalar = scalarAt(text, at);
        if (!scalar.valid)
            return false;
        at += scalar.bytes;
    }
    return true;
}
class Position {
public:
    std::size_t line = 0;
    std::size_t character = 0;
};
// An offset within a scalar rounds down for starts and up for ends.
inline Position utf16Position(std::string_view text, std::size_t offset, bool end = false) {
    offset = std::min(offset, text.size());
    Position result;
    for (std::size_t at = 0; at < offset;) {
        if (text[at] == '\r' || text[at] == '\n') {
            const bool pair = text[at] == '\r' && at + 1 < text.size() && text[at + 1] == '\n';
            if (pair && !end && offset == at + 1)
                break;
            at += pair ? 2 : 1;
            ++result.line;
            result.character = 0;
        } else {
            const auto scalar = scalarAt(text, at);
            if (!end && scalar.bytes > offset - at)
                break;
            result.character += scalar.value > 0xffff ? 2 : 1;
            at += scalar.bytes;
        }
    }
    return result;
}
inline int hexValue(char c) {
    if (c >= '0' && c <= '9')
        return c - '0';
    if (c >= 'a' && c <= 'f')
        return c - 'a' + 10;
    if (c >= 'A' && c <= 'F')
        return c - 'A' + 10;
    return -1;
}
inline void rejectParentTraversal(const std::filesystem::path &path) {
    for (const auto &component : path)
        if (component == "..")
            throw ProtocolError("parent traversal components are unsupported in source paths");
}
inline std::filesystem::path pathFromUri(std::string_view uri) {
    if (uri.size() > 16384 || !uri.starts_with("file://"))
        throw ProtocolError("only local file URIs are supported");
    uri.remove_prefix(7);
    const auto slash = uri.find('/');
    if (slash == std::string_view::npos || (slash != 0 && uri.substr(0, slash) != "localhost"))
        throw ProtocolError("remote file URI authority is unsupported");
    uri.remove_prefix(slash);
    std::string decoded;
    for (std::size_t i = 0; i < uri.size(); ++i) {
        char c = uri[i];
        if (c == '?' || c == '#')
            throw ProtocolError("URI query and fragment are unsupported");
        if (c == '%') {
            if (i + 2 >= uri.size() || hexValue(uri[i + 1]) < 0 || hexValue(uri[i + 2]) < 0)
                throw ProtocolError("malformed URI percent escape");
            c = static_cast<char>((hexValue(uri[i + 1]) << 4) | hexValue(uri[i + 2]));
            i += 2;
        }
        if (c == '\0')
            throw ProtocolError("NUL is forbidden in file URIs");
        decoded.push_back(c);
    }
    if (!validUtf8(decoded))
        throw ProtocolError("file URI path must be UTF-8");
    // Do not normalize away a symlink or missing component before the shared
    // frontend can authorize it. This bounded client rejects all parent walks.
    rejectParentTraversal(std::filesystem::path(decoded));
    const auto path = std::filesystem::path(decoded).lexically_normal();
    if (!path.is_absolute() || path.filename().empty())
        throw ProtocolError("file URI requires an absolute filename");
    return path;
}
inline std::string uriFromPath(const std::filesystem::path &path) {
    constexpr char hex[] = "0123456789ABCDEF";
    std::string uri = "file://";
    for (const auto raw : std::filesystem::absolute(path).lexically_normal().string()) {
        const auto c = static_cast<unsigned char>(raw);
        if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '/' || c == '-' ||
            c == '.' || c == '_' || c == '~')
            uri.push_back(static_cast<char>(c));
        else {
            uri.push_back('%');
            uri.push_back(hex[c >> 4]);
            uri.push_back(hex[c & 15]);
        }
    }
    return uri;
}
} // namespace aurora::lsp
