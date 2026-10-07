#include "../compiler/lsp/positions.hpp"
#include <iostream>
#include <sstream>

namespace {
int checks = 0;
void require(bool value, const char *name) {
    ++checks;
    if (!value)
        throw std::runtime_error(name);
}
template <class F> void rejects(F operation, const char *name) {
    bool failed = false;
    try {
        operation();
    } catch (const aurora::lsp::ProtocolError &) {
        failed = true;
    }
    require(failed, name);
}
} // namespace
int main() {
    using namespace aurora::lsp;
    try {
        std::istringstream stream("cOnTeNt-LeNgTh: 2\r\nContent-Type: application/vscode-jsonrpc; "
                                  "charset=utf-8\r\n\r\n{}Content-Length: 0\r\n\r\n");
        require(readFrame(stream) == "{}", "case insensitive header");
        require(readFrame(stream) == "", "zero-length payload is framed, then JSON rejects it");
        require(!readFrame(stream), "EOF at frame boundary");
        for (const auto &header :
             {"Content-Length: -1\r\n\r\n",
              "Content-Length: +2\r\n\r\n{}",
              "Content-Length: 2x\r\n\r\n{}",
              "Content-Length: 8388609\r\n\r\n",
              "Content-Length: 999999999999999999999999999999\r\n\r\n",
              "Content-Length: 2\r\ncontent-length: 2\r\n\r\n{}",
              "Content-Length: 2\n\n{}",
              "Content-Length: 2\r\n\r\n{",
              "Other: yes\r\n\r\n{}",
              "Content-Length: ",
              "Content-Length: 2\r\nContent-Type: application/vscode-jsonrpc; charset=utf-16\r\n\r\n{}",
              "Content-Length : 2\r\n\r\n{}",
              "Content-Length: 2\rX\r\n\r\n{}"})
            rejects(
                [&] {
                    std::istringstream in(header);
                    (void)readFrame(in);
                },
                "invalid frame rejected");
        rejects(
            [] {
                std::istringstream in(std::string(8193, 'a'));
                (void)readFrame(in);
            },
            "header bound");
        std::ostringstream out;
        writeFrame(out, "😀");
        require(out.str() == "Content-Length: 4\r\n\r\n😀", "wire length is bytes");
        const std::string unicode = "aé中😀z\r\nnext\rfinal\n";
        require(utf16Position(unicode, 10).character == 5, "UTF-16 counts supplementary scalar twice");
        require(utf16Position(unicode, 7).character == 3, "start rounds down inside scalar");
        require(utf16Position(unicode, 7, true).character == 5, "end rounds up inside scalar");
        require(utf16Position(unicode, 13).line == 1 && utf16Position(unicode, 13).character == 0,
                "CRLF is one newline");
        require(utf16Position(unicode, 12).line == 0 && utf16Position(unicode, 12).character == 6,
                "CRLF midpoint start rounds down");
        require(utf16Position(unicode, 12, true).line == 1 && utf16Position(unicode, 12, true).character == 0,
                "CRLF midpoint end rounds up");
        require(utf16Position(unicode, 18).line == 2, "bare CR newline");
        require(utf16Position(unicode, 9999).line == 3, "clamped EOF position");
        require(validUtf8(unicode), "valid UTF-8");
        for (const std::string &bad : {std::string("\xc0\xaf"),
                                       std::string("\xed\xa0\x80"),
                                       std::string("\xf4\x90\x80\x80"),
                                       std::string("\xe2\x82"),
                                       std::string("\x80")})
            require(!validUtf8(bad), "reject malformed UTF-8");
        require(pathFromUri("file:///tmp/%E4%B8%AD%20test.au") == "/tmp/中 test.au", "decoded UTF-8 URI");
        require(pathFromUri("file://localhost/tmp/test.au") == "/tmp/test.au", "localhost URI");
        require(pathFromUri("file:///tmp/./b.au") == "/tmp/b.au", "lexical normalization without parent walks");
        require(uriFromPath("/tmp/中 #%.au") == "file:///tmp/%E4%B8%AD%20%23%25.au", "URI percent encoding");
        for (const auto *uri : {"untitled:test.au",
                                "file://remote/tmp/x.au",
                                "file:///tmp/%",
                                "file:///tmp/%0G",
                                "file:///tmp/%00.au",
                                "file:///tmp/%FF.au",
                                "file:///tmp/x?y",
                                "file:///tmp/x#y",
                                "file:///",
                                "file://localhost",
                                "file:tmp/test.au",
                                "file:///tmp/a/../b.au",
                                "file:///tmp/a/%2e%2e/b.au"})
            rejects(
                [&] {
                    (void)pathFromUri(uri);
                },
                "invalid URI rejected");
        std::cout << checks << " LSP transport/position checks passed\n";
        return 0;
    } catch (const std::exception &failure) {
        std::cerr << "LSP unit failure: " << failure.what() << '\n';
        return 1;
    }
}
