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
void cases() {
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
    require(std::none_of(wrapped.remainingFindings.begin(),
                         wrapped.remainingFindings.end(),
                         [](const auto &finding) {
                             return finding.code == "AUF1001";
                         }),
            "punctuation-adjacent short-token chain did not wrap");
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
