#include "frontend.hpp"
#include <fstream>
#include <iostream>
#include <iterator>

namespace {
using aurora::DiagnosticCode;
using aurora::SourceOverlays;
namespace fs = std::filesystem;
int cases = 0;
void require(bool value, const std::string &message) {
    if (!value)
        throw std::runtime_error(message);
}
void write(const fs::path &path, const std::string &text) {
    std::ofstream output(path, std::ios::binary);
    output << text;
    require(output.good(), "fixture write failed");
}
std::string read(const fs::path &path) {
    std::ifstream input(path, std::ios::binary);
    require(input.good(), "fixture read failed");
    return {std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>()};
}
std::shared_ptr<const aurora::SourceText> snapshot(const fs::path &path, const std::string &text) {
    return std::make_shared<const aurora::SourceText>(path.string(), text);
}
void accept(const fs::path &input, const std::vector<fs::path> &roots, const SourceOverlays &overlays = {}) {
    const auto checked = aurora::checkSource(input, roots, overlays, aurora::AnalysisMode::Check, {.emit = true});
    require(!checked.code.empty(), "missing checked functions");
    require(!checked.sourceIdentities.empty(), "overlay lost opened-file identities");
    ++cases;
}
aurora::Diagnostic reject(const fs::path &input,
                          const std::vector<fs::path> &roots,
                          const SourceOverlays &overlays,
                          DiagnosticCode code,
                          const std::string &message) {
    try {
        aurora::checkSource(input, roots, overlays);
    } catch (const aurora::Error &error) {
        require(error.diagnostic.code == code, "wrong diagnostic family: " + std::string(error.what()));
        require(std::string(error.what()).find(message) != std::string::npos, "wrong rejection message");
        ++cases;
        return error.diagnostic;
    }
    throw std::runtime_error("expected rejection: " + message);
}
void run(const fs::path &directory) {
    constexpr std::size_t limit = 1024 * 1024;
    const auto app = directory / "app.au";
    const auto dep = directory / "dep.au";
    const std::string good = "module app; auto app() -> i64 { return 42; }";
    const std::string imported = "module app; import dep; auto app() -> i64 { return answer(); }";
    const std::string depGood = "export module dep; export auto answer() -> i64 { return 42; }";
    write(app, good);
    accept(app, {});
    const auto replacement = snapshot(app, good);
    write(app, "@");
    accept(app, {}, {{app, replacement}});
    require(read(app) == "@", "checking overlay changed disk source");
    reject(app, {}, {}, DiagnosticCode::UnsupportedCharacter, "unsupported character");
    write(app, good);
    const auto lexical = snapshot(app, "module app;\n@");
    const auto error = reject(app, {}, {{app, lexical}}, DiagnosticCode::UnsupportedCharacter, "unsupported character");
    require(error.span.source == lexical && error.span.begin.line == 2, "root overlay diagnostic provenance");
    const auto badType = snapshot(app, "module app; auto app() -> i64 { return true; }");
    const auto semantic = reject(app, {}, {{app, badType}}, DiagnosticCode::Semantic, "expected i64");
    require(semantic.span.source == badType, "semantic overlay snapshot identity");
    require(read(app) == good, "rejected overlay changed disk source");

    write(app, imported);
    write(dep, "@");
    const auto importedSnapshot = snapshot(dep, depGood);
    accept(app, {directory}, {{dep, importedSnapshot}});
    require(read(dep) == "@", "imported overlay changed disk source");
    const auto importedChecked = aurora::checkSource(app, {directory}, {{dep, importedSnapshot}});
    const std::set<aurora::host::Identity> expectedIdentities = {aurora::host::SourceFile::explicitPath(app).identity,
                                                                 aurora::host::SourceFile::explicitPath(dep).identity};
    require(importedChecked.sourceIdentities == expectedIdentities, "exact root/import inode identities");
    ++cases;
    const auto importedBad = snapshot(dep, "export module dep;\n@");
    const auto importedError = reject(app,
                                      {directory},
                                      {{dep, importedBad}},
                                      DiagnosticCode::UnsupportedCharacter,
                                      "module dep: unsupported character");
    require(importedError.span.source == importedBad, "import context lost supplied snapshot");
    reject(app, {}, {{dep, importedSnapshot}}, DiagnosticCode::Module, "explicit --module-root");
    fs::remove(dep);
    reject(app, {directory}, {{dep, importedSnapshot}}, DiagnosticCode::Module, "module not found");
    require(!fs::exists(dep), "overlay created a missing import");
    const auto missing = directory / "missing.au";
    reject(missing, {}, {{missing, snapshot(missing, good)}}, DiagnosticCode::Module, "cannot open input");
    require(!fs::exists(missing), "overlay created a missing root");

    write(app, good);
    const auto alias = directory / "alias.au";
    fs::create_symlink(app, alias);
    reject(alias, {}, {{alias, snapshot(alias, good)}}, DiagnosticCode::Module, "cannot open input");
    fs::create_directory(directory / "sub");
    fs::create_directory_symlink(directory / "sub", directory / "link");
    reject(directory / "link/../app.au", {}, {{app, replacement}}, DiagnosticCode::Module, "cannot open input");
    fs::create_directory_symlink(directory, directory / "root-link");
    reject(app, {directory / "root-link"}, {{app, replacement}}, DiagnosticCode::Module, "module root");
    write(app, imported);
    fs::create_symlink(app, dep);
    reject(app, {directory}, {{dep, importedSnapshot}}, DiagnosticCode::Module, "module");
    fs::remove(dep);
    write(dep, depGood);
    fs::create_directory(directory / "other");
    write(directory / "other/dep.au", depGood);
    reject(
        app, {directory, directory / "other"}, {{dep, importedSnapshot}}, DiagnosticCode::Module, "ambiguous module");

    write(app, good);
    const auto hard = directory / "hard.au";
    fs::create_hard_link(app, hard);
    const auto hardInvalid = snapshot(hard, "module app; auto app() -> i64 { return true; }");
    const SourceOverlays hardOverlays = {{app, replacement}, {hard, hardInvalid}};
    accept(app, {}, hardOverlays);
    const auto hardError = reject(hard, {}, hardOverlays, DiagnosticCode::Semantic, "expected i64");
    require(hardError.span.source == hardInvalid, "hard-link paths must select independent snapshots");
    const auto hardChecked = aurora::checkSource(app, {}, hardOverlays);
    require(hardChecked.sourceIdentities ==
                std::set<aurora::host::Identity>{aurora::host::SourceFile::explicitPath(hard).identity},
            "overlay must retain the opened physical inode identity");
    ++cases;
    try {
        aurora::host::ArtifactWriter writer(hard, hardChecked.sourceIdentities);
        require(false, "artifact writer accepted a hard-link alias of an overlaid source");
    } catch (const aurora::Error &error) {
        require(std::string(error.what()).find("aliases a root or imported source") != std::string::npos,
                "wrong hard-link output rejection");
        ++cases;
    }
    require(read(app) == good && read(hard) == good, "output-alias rejection changed disk bytes");
    const auto repeatedSeparator = fs::path(directory.string() + "//app.au");
    reject(app,
           {},
           {{repeatedSeparator, snapshot(repeatedSeparator, good)}},
           DiagnosticCode::Module,
           "absolute normalized path");
    std::string nulText = directory.string() + "/nul";
    nulText.push_back('\0');
    nulText += ".au";
    const fs::path nulPath(nulText);
    reject(app, {}, {{nulPath, snapshot(nulPath, good)}}, DiagnosticCode::Module, "absolute normalized path");
    reject(app, {}, {{app, nullptr}}, DiagnosticCode::Module, "absolute normalized path");
    reject(app, {}, {{app, snapshot(dep, good)}}, DiagnosticCode::Module, "matching its snapshot");
    reject(
        app, {}, {{fs::path("app.au"), snapshot("app.au", good)}}, DiagnosticCode::Module, "absolute normalized path");
    const auto unnormalized = directory / "sub/../app.au";
    reject(app, {}, {{unnormalized, snapshot(unnormalized, good)}}, DiagnosticCode::Module, "absolute normalized path");
    reject(app, {}, {{app, snapshot(app, std::string(limit + 1, ' '))}}, DiagnosticCode::Module, "1048576 bytes");
    SourceOverlays many;
    for (int index = 0; index < 65; ++index) {
        const auto path = directory / ("unused" + std::to_string(index) + ".au");
        many.emplace(path, snapshot(path, ""));
    }
    reject(app, {}, many, DiagnosticCode::Module, "64 files");
    many.erase(directory / "unused64.au");
    accept(app, {}, many);
    many.clear();
    for (int index = 0; index < 4; ++index) {
        const auto path = directory / ("unused" + std::to_string(index) + ".au");
        many.emplace(path, snapshot(path, std::string(limit, ' ')));
    }
    accept(app, {}, many);
    many.emplace(missing, snapshot(missing, " "));
    reject(app, {}, many, DiagnosticCode::Module, "4194304 bytes");
    many.clear();
    const std::string exact = good + "//" + std::string(limit - good.size() - 2, ' ');
    accept(app, {}, {{app, snapshot(app, exact)}});
    const auto relativeRoot = fs::relative(directory, fs::current_path());
    accept(relativeRoot / "app.au", {}, {{app, replacement}});

    write(app, "module app; import a; import b; import c; import d; auto app()->i64{return 0;}");
    for (const std::string name : {"a", "b", "c", "d"}) {
        const auto path = directory / (name + ".au");
        const auto header = "export module " + name + "; //";
        const auto contents = header + std::string(limit - header.size(), ' ');
        write(path, name == "d" ? contents : header);
        if (name != "d")
            many.emplace(path, snapshot(path, contents));
    }
    const auto fourth = directory / "d.au";
    const auto fourthContents = read(fourth);
    const auto exactFourthSize = limit - read(app).size();
    write(fourth, fourthContents.substr(0, exactFourthSize));
    accept(app, {directory}, many);
    write(fourth, fourthContents.substr(0, exactFourthSize + 1));
    reject(app, {directory}, many, DiagnosticCode::Module, "module graph exceeds 4194304 bytes");
    write(fourth, fourthContents);
    reject(app, {directory}, many, DiagnosticCode::Module, "module graph exceeds 4194304 bytes");
}
} // namespace
int main(int argc, char **argv) {
    try {
        require(argc == 2, "expected one fresh fixture directory");
        const auto directory = fs::absolute(argv[1]).lexically_normal();
        require(fs::is_directory(directory) && fs::is_empty(directory), "fixture directory must be empty");
        run(directory);
        std::cout << "PASS " << cases << " existing-file overlay cases\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "FAIL " << error.what() << '\n';
        return 1;
    }
}
