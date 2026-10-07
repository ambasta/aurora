#pragma once
#include <cstddef>
#include <istream>
#include <optional>
#include <ostream>
#include <stdexcept>
#include <string>
#include <string_view>

namespace aurora::lsp {
inline constexpr std::size_t maxHeaderBytes = 8192;
inline constexpr std::size_t maxMessageBytes = 8 * 1024 * 1024;
class ProtocolError : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};
inline std::string asciiLower(std::string value) {
    for (auto &c : value)
        if (c >= 'A' && c <= 'Z')
            c = static_cast<char>(c + ('a' - 'A'));
    return value;
}
inline std::string_view trim(std::string_view value) {
    while (!value.empty() && (value.front() == ' ' || value.front() == '\t'))
        value.remove_prefix(1);
    while (!value.empty() && (value.back() == ' ' || value.back() == '\t'))
        value.remove_suffix(1);
    return value;
}
// Bad framing cannot safely be resynchronized. EOF is normal only between frames.
inline std::optional<std::string> readFrame(std::istream &input) {
    std::size_t headerBytes = 0;
    std::optional<std::size_t> length;
    bool contentTypeSeen = false;
    while (true) {
        std::string line;
        while (true) {
            const int next = input.get();
            if (next == std::char_traits<char>::eof()) {
                if (headerBytes == 0)
                    return std::nullopt;
                throw ProtocolError("truncated message header");
            }
            if (++headerBytes > maxHeaderBytes)
                throw ProtocolError("message header exceeds limit");
            if (next == '\n') {
                if (line.empty() || line.back() != '\r')
                    throw ProtocolError("header requires CRLF");
                line.pop_back();
                break;
            }
            if (next != '\r' && next != '\t' && (next < 0x20 || next > 0x7e))
                throw ProtocolError("non-ASCII message header");
            line.push_back(static_cast<char>(next));
        }
        if (line.empty())
            break;
        const auto colon = line.find(':');
        if (colon == std::string::npos || colon == 0)
            throw ProtocolError("invalid message header");
        const auto name = asciiLower(line.substr(0, colon));
        for (const char c : name)
            if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '-'))
                throw ProtocolError("invalid header name");
        const auto value = trim(std::string_view(line).substr(colon + 1));
        if (value.find('\r') != std::string_view::npos)
            throw ProtocolError("invalid header value");
        if (name == "content-length") {
            if (length || value.empty())
                throw ProtocolError("missing or duplicate Content-Length");
            std::size_t parsed = 0;
            for (const char c : value) {
                if (c < '0' || c > '9' || parsed > (maxMessageBytes - static_cast<unsigned>(c - '0')) / 10)
                    throw ProtocolError("invalid or excessive Content-Length");
                parsed = parsed * 10 + static_cast<unsigned>(c - '0');
            }
            length = parsed;
        } else if (name == "content-type") {
            if (contentTypeSeen)
                throw ProtocolError("duplicate Content-Type");
            contentTypeSeen = true;
            auto normalized = asciiLower(std::string(value));
            const auto semicolon = normalized.find(';');
            if (trim(std::string_view(normalized).substr(0, semicolon)) != "application/vscode-jsonrpc")
                throw ProtocolError("unsupported Content-Type");
            if (semicolon != std::string::npos) {
                const auto charset = trim(std::string_view(normalized).substr(semicolon + 1));
                if (charset != "charset=utf-8" && charset != "charset=utf8")
                    throw ProtocolError("unsupported message charset");
            }
        }
    }
    if (!length)
        throw ProtocolError("missing Content-Length");
    std::string payload(*length, '\0');
    input.read(payload.data(), static_cast<std::streamsize>(payload.size()));
    if (static_cast<std::size_t>(input.gcount()) != payload.size())
        throw ProtocolError("truncated message body");
    return payload;
}
inline void writeFrame(std::ostream &output, std::string_view payload) {
    output << "Content-Length: " << payload.size() << "\r\n\r\n";
    output.write(payload.data(), static_cast<std::streamsize>(payload.size()));
    output.flush();
    if (!output)
        throw ProtocolError("message output failed");
}
} // namespace aurora::lsp
