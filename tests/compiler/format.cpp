#include "format.hpp"
#include <fstream>
#include <iostream>
#include <iterator>
#include <random>

namespace {
void require(bool condition, const std::string &message) {
    if (!condition)
        throw std::runtime_error(message);
}
std::string read(const std::string &path) {
    std::ifstream input(path, std::ios::binary);
    require(input.good(), "cannot open fixture: " + path);
    return {std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>()};
}
void verify(const std::string &text, const std::string &path) {
    const auto result = aurora::format::source(text, path);
    const auto original = aurora::lexSource(text, path);
    const auto formatted = aurora::lexSource(result.text, path);
    // Independent public-API observations, in addition to formatter safeguards.
    require(original.tokens.size() == formatted.tokens.size(), "token count differs: " + path);
    for (std::size_t index = 0; index < original.tokens.size(); ++index)
        require(original.tokens[index].text == formatted.tokens[index].text, "token spelling differs: " + path);
    std::vector<std::pair<std::size_t, std::string>> before, after;
    for (const auto *source : {&original, &formatted}) {
        auto &list = source == &original ? before : after;
        for (const auto &trivia : source->trivia) {
            if (trivia.kind != aurora::TriviaKind::LineComment)
                continue;
            std::size_t preceding = 0;
            for (const auto &token : source->tokens) {
                if (token.text != "<eof>" && token.span.end.offset <= trivia.span.begin.offset)
                    ++preceding;
            }
            list.emplace_back(preceding, std::string(aurora::format::spelling(trivia.span)));
        }
    }
    require(before == after, "comment bytes or token-relative position differ: " + path);
    aurora::Parser(formatted.tokens).parse();
    const auto again = aurora::format::source(result.text, path);
    require(!again.changed && again.text == result.text, "formatter is not idempotent: " + path);
    require(result.changed == (result.text != text), "changed flag differs: " + path);
}
void golden(const std::string &text, const std::string &expected) {
    verify(text, "golden.au");
    const auto result = aurora::format::source(text);
    require(result.text == expected, "golden differs; actual:\n" + result.text + "expected:\n" + expected);
}
void rejected(const std::string &text, aurora::DiagnosticCode expected) {
    try {
        aurora::format::source(text, "rejected.au");
        throw std::runtime_error("invalid source accepted");
    } catch (const aurora::Error &error) {
        require(error.diagnostic.code == expected, "original diagnostic code was not retained");
    }
}
void qualifiedNames() {
    const auto unbroken = [](const std::string &text) {
        const auto formatted = aurora::format::source(text);
        const auto tokens = aurora::lexSource(formatted.text).tokens;
        for (std::size_t index = 1; index + 1 < tokens.size(); ++index)
            if (tokens[index].text == "::")
                require(tokens[index - 1].span.end.line == tokens[index].span.begin.line &&
                            tokens[index].span.end.line == tokens[index + 1].span.begin.line,
                        "formatter soft-wrapped inside a qualified name: " + formatted.text);
        verify(text, "qualified-boundary.au");
        return formatted;
    };
    const auto name = std::string(100, 'f');
    golden("module x;auto " + name + "()->std::ByteWriteStatus{return std::ByteWriteStatus::success;}",
           "module x;\nauto " + name +
               "() ->\n    std::ByteWriteStatus {\n"
               "    return std::ByteWriteStatus::success;\n}\n");
    // Sweep the soft limit through every part of multi-scope types, calls and
    // enum values. The formatter must wrap before the group, never at ::.
    for (std::size_t width = 60; width <= 130; ++width) {
        const std::string padding(width, 'f');
        unbroken("module x;auto " + padding +
                 "()->outer::inner::ByteWriteStatus{"
                 "return outer::inner::ByteWriteStatus::success;}");
        unbroken("module x;auto f()->i64{return " + padding + "(outer::inner::value());}");
        unbroken("module x;auto f()->i64{const i64 " + padding + "=outer::inner::Value::ready;return 0;}");
    }
    // Original newlines around a scope token are canonicalized without changing
    // tokens. An explicitly anchored comment remains an intentional hard break.
    unbroken("module x;auto f()->std::\nByteWriteStatus{return std\n::ByteWriteStatus::success;}");
    for (const auto &qualified : {"std // before scope\n::ByteWriteStatus",
                                  "std:: // after scope\nByteWriteStatus",
                                  "outer::inner // middle scope\n::ByteWriteStatus"})
        verify("module x;auto f()->" + std::string(qualified) + "{return 0;}", "qualified-comments.au");
    std::string oversized = "outer";
    for (int count = 0; count < 256; ++count)
        oversized += "::nested";
    const auto longName = unbroken("module x;auto f()->" + oversized + "{return 0;}");
    require(longName.text.find(oversized) != std::string::npos, "oversized qualified name was split");
    require(std::any_of(longName.remainingFindings.begin(),
                        longName.remainingFindings.end(),
                        [](const auto &finding) {
                            return finding.code == "AUF1001";
                        }),
            "oversized qualified group must retain the soft-width finding");
}
void structuralWrapping() {
    const auto check = [](const std::string &input) {
        verify(input, "structural-boundary.au");
        const auto output = aurora::format::source(input);
        const auto tokens = aurora::lexSource(output.text).tokens;
        for (std::size_t index = 1; index + 1 < tokens.size(); ++index) {
            if (tokens[index].text == "." || tokens[index].text == "::")
                require(tokens[index - 1].span.end.line == tokens[index].span.begin.line &&
                            tokens[index].span.end.line == tokens[index + 1].span.begin.line,
                        "member/scope access split at soft limit: " + output.text);
        }
        return output;
    };
    // Move every token boundary across the soft limit, both with nested call
    // arguments and without any legal internal break in a chained access atom.
    for (std::size_t width = 1; width <= 180; ++width) {
        const auto padding = std::string(width, 'p');
        check("module x;auto f()->u64{return pick(" + padding + ", token.value_or(0u64));}");
        check("module x;auto f()->u64{return outer::pick(inner::read(" + padding +
              ", device.flush()), token.value_or(0u64));}");
        check("module x;auto f()->u64{return " + padding + ".child.value_or(0u64);}");
        check("module x;auto f()->u64{return source.open().child.read(" + padding + ", 0u64).value;}");
        check("module x;auto f()->bool{return " + padding + "==1&&(token.value_or(0u64)<2)||!(false);}");
        check("module x;auto f()->i64{return " + padding + "+(2)*-(3);}");
        verify("// café 😀\r\nmodule x;auto f()->u64{return pick(" + padding +
                   ", token. // anchored café 😀\nvalue_or(0u64));}",
               "structural-comment-boundary.au");
    }
    const auto padding = std::string(80, 'a');
    golden("module x;auto f()->u64{return choose(" + padding + ", token.value_or(0u64));}",
           "module x;\nauto f() -> u64 {\n    return choose(" + padding + ",\n        token.value_or(0u64));\n}\n");
    const auto lhs = std::string(100, 'a');
    golden("module x;auto f()->bool{return " + lhs + "&&(token.value_or(0u64)==1);}",
           "module x;\nauto f() -> bool {\n    return " + lhs + "\n        && (token.value_or(0u64) == 1);\n}\n");
    const auto oversized = std::string(140, 'a') + ".child.value";
    const auto result = check("module x;auto f()->i64{return " + oversized + ";}");
    require(result.text.find(oversized) != std::string::npos, "oversized member atom was split");
    require(std::any_of(result.remainingFindings.begin(),
                        result.remainingFindings.end(),
                        [](const auto &finding) {
                            return finding.code == "AUF1001";
                        }),
            "oversized member atom lost its long-line finding");
}
void parenthesizedReturns() {
    golden("module x;auto f()->i64{return(1+2);}", "module x;\nauto f() -> i64 {\n    return (1 + 2);\n}\n");
    golden("module x;auto f()->bool{return(true)&&(false);}",
           "module x;\nauto f() -> bool {\n    return (true) && (false);\n}\n");
    // Function calls keep their tight opening parenthesis.
    golden("module x;auto f()->i64{return g(1);}", "module x;\nauto f() -> i64 {\n    return g(1);\n}\n");
}
void byteLiterals() {
    golden("module x;auto f()->u8{return '[';}", "module x;\nauto f() -> u8 {\n    return '[';\n}\n");
    golden(R"(module x;auto f()->u8{return '~'&('\xff');})",
           "module x;\nauto f() -> u8 {\n    return '~' & ('\\xff');\n}\n");
    verify(R"(module x;auto f()->bool{return '/'=='/' // preserve '/'
&&'\''!='\\'&&'{'!='}'&&'('!=')'&&'<'!='>'&&'"'=='"';})",
           "byte-operators.au");
    verify(R"(module x;auto f()->u8{const array<u8,4> a={'\0','\n','\xFF',' '};return a[0];})", "byte-array.au");
    for (const std::string spelling : {"''", "'ab'", "'\\x100'", "'\\q'", "'a'u8"})
        rejected("module x;auto f()->u8{return " + spelling + ";}", aurora::DiagnosticCode::InvalidByteLiteral);
}
void byteStrings() {
    golden(R"(module x;auto f()->u8{const array<u8,6> a="IOMMU ";return a[0];})",
           "module x;\nauto f() -> u8 {\n    const array<u8, 6> a = \"IOMMU \";\n    return a[0];\n}\n");
    verify(R"(module x;auto f()->u8{const array<u8,20> a="é😀 // { } ; \" \\ \0\xff";return a[0];})",
           "byte-string-punctuation.au");
    verify("module x;auto f()->u8{const array<u8,4096> a=\"" + std::string(4096, 'a') + "\";return a[0];}",
           "byte-string-soft-width.au");
    for (const std::string spelling : {"\"\\q\"", "\"\\x0\"", "\"a\"u8", "\"unclosed"})
        rejected("module x;auto f()->u8{const array<u8,1> a=" + spelling + ";return a[0];}",
                 aurora::DiagnosticCode::InvalidByteStringLiteral);
}
void oversizedStrings() {
    const auto has = [](const std::vector<aurora::format::Finding> &findings, const std::string &code) {
        return std::any_of(findings.begin(), findings.end(), [&](const auto &finding) {
            return finding.code == code;
        });
    };
    const std::string literal = "\"" + std::string(119, 'x') + "\""; // 121 source bytes
    for (const auto &suffix : {";", ");", "));", ",", "]);"}) {
        const auto findings = aurora::format::styleFindings(aurora::lexSource("        " + literal + suffix + "\n"));
        require(findings.empty(), "standalone oversized literal was not exempted");
    }
    for (const auto &line :
         {"        \"" + std::string(118, 'x') + "\";", std::string(24, ' ') + "\"" + std::string(100, 'x') + "\";"}) {
        require(aurora::format::styleFindings(aurora::lexSource(line + "\n")).empty(),
                "standalone literal at canonical indentation was not exempted");
    }
    for (const auto &line : {std::string(120, ' ') + literal + ";", // indentation itself is too wide
                             "        return " + literal + ";",
                             "        " + literal + " + value;",
                             "        " + literal + ".member;",
                             "\t" + literal + ";",
                             "        " + literal + " \"second\";",
                             "        " + literal + "; // comment",
                             "        " + std::string(121, 'x') + ";",
                             "        // " + literal}) {
        require(has(aurora::format::styleFindings(aurora::lexSource(line + "\n")), "AUF1001"),
                "non-literal excess incorrectly exempted: " + line);
    }
    const auto whitespace = aurora::format::styleFindings(aurora::lexSource(" " + literal + "; \n"));
    require(has(whitespace, "AUF1002") && has(whitespace, "AUF1003"), "literal hid whitespace findings");
    const auto formatted = aurora::format::source("module x;auto f()->i64{return g(" + literal + ");}");
    require(formatted.changed, "literal exception hid noncanonical layout");
    const auto canonical = aurora::format::source(formatted.text);
    require(!canonical.changed && canonical.findings.empty(), "canonical oversized literal fails check");
    verify(formatted.text, "oversized-string.au");
}
void cases() {
    golden("module x;auto f()->u64{return 0b10001'10001'10001'11111'10001'10001'01110u64;}",
           "module x;\nauto f() -> u64 {\n"
           "    return 0b10001'10001'10001'11111'10001'10001'01110u64;\n}\n");
    verify("module x;auto f()->u8{return 0B0000'0001u8+'\\0';}", "binary-byte.au");
    verify("module x;auto f()->i64{return -0b1'000000000000000000000000000000000000000000000000000000000000000;}",
           "binary-minimum.au");
    qualifiedNames();
    structuralWrapping();
    golden("module x;auto f(i64 a,i64 b)->bool{return a==1&&(b<1)||!(a==2);}",
           "module x;\nauto f(i64 a, i64 b) -> bool {\n"
           "    return a == 1 && (b < 1) || !(a == 2);\n}\n");
    golden("module x;auto f(i64 a,i64 b)->bool{return a==1||(b<1)&&!(a==2);}",
           "module x;\nauto f(i64 a, i64 b) -> bool {\n"
           "    return a == 1 || (b < 1) && !(a == 2);\n}\n");
    golden("module x;auto f(i64 a)->i64{return a+(2)*-(3);}",
           "module x;\nauto f(i64 a) -> i64 {\n    return a + (2) * -(3);\n}\n");
    golden("module x;auto f(const pkg::Buffer& input,builtin::span<const u8> bytes,u64 mask)->u64{"
           "return mask&7u64;}",
           "module x;\nauto f(const pkg::Buffer& input, builtin::span<const u8> bytes, u64 mask) -> u64 {\n"
           "    return mask & 7u64;\n}\n");
    golden("module x;auto f(pkg::Buffer & output,u64 value)->u64{return value & 3u64;}",
           "module x;\nauto f(pkg::Buffer& output, u64 value) -> u64 {\n    return value & 3u64;\n}\n");
    golden("module x;auto f()->i64{return 1+2;}", "module x;\nauto f() -> i64 {\n    return 1 + 2;\n}\n");
    golden("// header\r\nmodule x;// module\nauto f()->i64{ // body\nreturn -42; // result\n}// eof",
           "// header\r\nmodule x; // module\nauto f() -> i64 { // body\n    return -42; // result\n} // eof\n");
    golden("export module x;class C{private:i64 x;public:C():x(0){}auto get()const->i64{return x;}};",
           "export module x;\nclass C {\nprivate:\n    i64 x;\npublic:\n    C() : x(0) {\n    }\n    auto get() const "
           "-> i64 {\n        return x;\n    }\n};\n");
    golden("module x;auto f()->i64{if(true){return 1;}else{return 2;}}",
           "module x;\nauto f() -> i64 {\n    if (true) {\n        return 1;\n    } else {\n        return 2;\n    "
           "}\n}\n");
    golden("export module x;class C{array<i64,2> a;public:C():a{}{}};",
           "export module x;\nclass C {\n    array<i64, 2> a;\npublic:\n    C() : a{} {\n    }\n};\n");
    golden("export module x;enum class E{a,b,c,};", "export module x;\nenum class E {\n    a,\n    b,\n    c,\n};\n");
    // Retain user grouping at structural boundaries, normalizing each blank run
    // to one empty line. Whitespace inside expressions and block/file edges is noise.
    golden("\n\nmodule x;\n \t\r\n\nimport y;\n\nauto f()->i64{\n\n"
           "i64 a=1;\n \t\n\n// group \t\r\n\n// next\n\nreturn a;\n\n}\n\n\n"
           "auto g()->i64{return 2;}\n\n",
           "module x;\n\nimport y;\n\nauto f() -> i64 {\n    i64 a = 1;\n\n"
           "    // group \t\r\n\n    // next\n\n    return a;\n}\n\nauto g() -> i64 {\n    return 2;\n}\n");
    golden("module x;\nauto f()->i64{\ni64 a=1; // trailing\n\nreturn a;\n}\n\n// footer\n\n",
           "module x;\nauto f() -> i64 {\n    i64 a = 1; // trailing\n\n    return a;\n}\n\n// footer\n");
    golden("export module x;\n\nclass C{\n\nprivate:i64 a;\n\ni64 b;\n\npublic:\n"
           "C():a(0),b(0){}\n\nauto get()const->i64{return a+b;}\n\n};\n",
           "export module x;\n\nclass C {\nprivate:\n    i64 a;\n\n    i64 b;\n\npublic:\n"
           "    C() : a(0), b(0) {\n    }\n\n    auto get() const -> i64 {\n        return a + b;\n    }\n};\n");
    golden("module x;auto f()->i64{if(true){\n\nreturn 1;\n\n}\n\nelse{\n\nreturn 2;\n\n}}",
           "module x;\nauto f() -> i64 {\n    if (true) {\n        return 1;\n    } else {\n"
           "        return 2;\n    }\n}\n");
    golden("module\n\nx;auto f(\n\n)->i64{array<i64,2> a={\n\n1,\n\n2\n\n};\n\n"
           "return\n\na[0]\n\n+\n\n1;}",
           "module x;\nauto f() -> i64 {\n    array<i64, 2> a = {\n        1,\n\n        2\n    };\n\n"
           "    return a[0] + 1;\n}\n");
    golden("// header\n\nmodule x;\r\n\r\nauto f()->i64{return 1;}\n// attached\n// next\n",
           "// header\n\nmodule x;\n\nauto f() -> i64 {\n    return 1;\n}\n// attached\n// next\n");
    const std::vector<std::string> fixtures = {
        "module x;auto f()->i64{return -(1+2)*~3/-4;}",
        "module x;auto f()->bool{return 1<2&&2>=1||!false;}",
        "module x;auto f()->i64{return 16>>1<<2;}",
        "module x;auto f()->i64{array<i64,2> a={1,2};return a[0];}",
        "module x;auto f()->i64{A a=A{.v=B{.n=1},.x=2};return a.v.n;}",
        "module x;auto f()->i64{A<B<i64>> a=A<B<i64>>{.v=B<i64>{.n=1}};return a.v.n;}",
        "module x;auto f()->i64{A<B<i64> > a=A<B<i64> >{.v=B<i64>{.n=1}};return a.v.n;}",
        "export module x;template<Scalar T>class A{T v;public:A(T x):v(x){}auto get()const->T{return v;}};",
        "export module x;template<Scalar T>auto f(T x)->T{return x;}",
        "module x;auto f()->i64{return ns::f<i64>(1)+a.get();}",
        "module x;auto f()->i64{A a=A{.v=one(1,2),.x=two(3,4)};return 1;}",
        "module x;auto f()->i64{while(true){{return 1;}}return 0;}",
        "module x;auto f()->i64{return 1;// comment with trailing space \t\n}",
        "module x;auto f()->i64{return 1;}\n// café 😀",
        "module x;auto f()->i64{return 1;} //" + std::string(160, 'x'),
        "module x;auto f()->i64{return " + std::string(150, 'a') + ";}",
        "module x;auto f()->i64{return " + std::string(110, 'a') + "+" + std::string(110, 'b') + ";}",
    };
    for (std::size_t index = 0; index < fixtures.size(); ++index) {
        verify(fixtures[index], "syntax-" + std::to_string(index) + ".au");
    }
    std::string chain = "module x;auto f()->i64{return a";
    for (int index = 0; index < 60; ++index)
        chain += ".member";
    chain += ";}";
    verify(chain, "member-chain.au");
    const auto wrapped = aurora::format::source(chain);
    require(wrapped.text.find("\n\n") == std::string::npos, "automatic wrapping added a blank line");
    require(std::any_of(wrapped.remainingFindings.begin(),
                        wrapped.remainingFindings.end(),
                        [](const auto &finding) {
                            return finding.code == "AUF1001";
                        }),
            "oversized member-only chain must stay intact and retain its soft-width finding");
    std::string bytes = "module x;auto f()->i64{return 1;}\n//";
    for (int byte = 0; byte <= 255; ++byte) {
        if (byte != '\n')
            bytes += static_cast<char>(byte);
    }
    verify(bytes, "opaque-comment.au");
    rejected("module x;auto f()->i64{return @;}", aurora::DiagnosticCode::UnsupportedCharacter);
    rejected("module x;auto f()->i64{return ;}", aurora::DiagnosticCode::UnexpectedToken);
    rejected("module x;auto f()->i64{/* no block comments */return 1;}", aurora::DiagnosticCode::UnexpectedToken);
    rejected(std::string(aurora::format::sourceLimit + 1, ' '), aurora::DiagnosticCode::Module);
    const auto style = aurora::format::source("module x;\n auto f()->i64{\t\n\treturn 1; \n}\n", "style.au");
    std::set<std::string> codes;
    for (const auto &finding : style.findings) {
        codes.insert(finding.code);
        require(finding.span.source->path == "style.au", "style source path");
        require(finding.span.begin.offset <= finding.span.end.offset &&
                    finding.span.end.offset <= finding.span.source->text.size(),
                "style range bounds");
        std::size_t offset = 0;
        int line = 1, column = 1;
        for (const char byte : finding.span.source->text) {
            if (offset == finding.span.begin.offset)
                break;
            ++offset;
            if (byte == '\n') {
                ++line;
                column = 1;
            } else {
                ++column;
            }
        }
        require(line == finding.span.begin.line && column == finding.span.begin.column, "style range coordinates");
    }
    require(codes.contains("AUF1002") && codes.contains("AUF1003"), "missing whitespace/indent findings");
    const auto longLine = aurora::format::source("module x;auto f()->i64{return 1;} //" + std::string(130, 'x'));
    require(std::any_of(longLine.findings.begin(),
                        longLine.findings.end(),
                        [](const auto &finding) {
                            return finding.code == "AUF1001";
                        }),
            "missing long-line finding");
    // Randomize only trivia of known accepted source, using the actual lexer.
    const auto seed =
        aurora::lexSource("module x;auto f()->i64{A<B<i64> > a=A<B<i64> >{.v=B<i64>{.n=1}};return -(1+2)>>1;}");
    std::mt19937 random(1708);
    const std::vector<std::string> gaps = {" ", "\t", "\r\n", "\n\n", " // retained\n", "\v\f"};
    for (int sample = 0; sample < 128; ++sample) {
        std::string text;
        for (const auto &token : seed.tokens) {
            if (token.text == "<eof>")
                break;
            text += gaps[random() % gaps.size()] + token.text;
        }
        verify(text, "random-trivia.au");
    }
}
} // namespace
int main(int argc, char **argv) {
    try {
        parenthesizedReturns();
        byteLiterals();
        byteStrings();
        oversizedStrings();
        cases();
        for (int index = 1; index < argc; ++index)
            verify(read(argv[index]), argv[index]);
        std::cout << "PASS formatter goldens, current-syntax/adversarial cases, 128 trivia variants, and " << argc - 1
                  << " corpus sources\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "FAIL " << error.what() << '\n';
        return 1;
    }
}
