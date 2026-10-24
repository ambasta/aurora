// Case files for textual IR (.air): directives, cases and zero-context
// patches against a named base case. See tests/compiler/ir/README.md.
#pragma once
#include "ir_text.hpp"
#include <charconv>
#include <fstream>
#include <map>
#include <optional>
#include <sstream>
#include <string>
#include <string_view>
#include <vector>

namespace aurora::test::air {
class Check {
public:
    std::string kind; // CHECK, CHECK-NEXT, ..., CHECK-JSON-RANGE, CHECK-RUN-EQUAL
    std::string pattern;
    int line;
};
// One RUN line and the expectations that follow it.
class Run {
public:
    std::string action;
    std::vector<std::string> errors; // every EXPECT-ERROR must be a substring of what()
    std::optional<std::string> message, code;
    bool expectOk = false;
    std::vector<Check> checks;
    std::vector<std::string> abi;
};
class Case {
public:
    std::string name;
    std::string base;      // empty: the file's header module
    std::vector<Run> runs; // empty: the case is only a base for others
    std::vector<std::string> body;
    int line = 0;
};
class CaseFile {
public:
    std::string path;
    std::vector<Case> cases; // cases[0] is the header
};

inline std::string trim(std::string_view text) {
    const auto begin = text.find_first_not_of(" \t\r");
    if (begin == std::string_view::npos)
        return {};
    const auto end = text.find_last_not_of(" \t\r");
    return std::string(text.substr(begin, end - begin + 1));
}
inline bool directive(const std::string &line, std::string &keyword, std::string &value) {
    const auto text = trim(line);
    if (text.empty() || text[0] != ';')
        return false;
    const auto body = trim(std::string_view(text).substr(1));
    static const char *const keywords[] = {"RUN",
                                           "EXPECT-OK",
                                           "EXPECT-ERROR",
                                           "EXPECT-MESSAGE",
                                           "EXPECT-CODE",
                                           "CHECK",
                                           "CHECK-NEXT",
                                           "CHECK-SAME",
                                           "CHECK-NOT",
                                           "CHECK-JSON",
                                           "CHECK-JSON-COUNT",
                                           "CHECK-JSON-NOT",
                                           "CHECK-JSON-ONEOF",
                                           "CHECK-JSON-DIFF",
                                           "CHECK-JSON-RATIO",
                                           "CHECK-JSON-RANGE",
                                           "CHECK-RUN-EQUAL",
                                           "CHECK-DAG",
                                           "CHECK-PROBES",
                                           "CASE",
                                           "BASE",
                                           "ABI"};
    for (const auto *candidate : keywords) {
        const std::string name = candidate;
        if (body == name || body.starts_with(name + ":")) {
            keyword = name;
            value = body.size() > name.size() ? trim(std::string_view(body).substr(name.size() + 1)) : "";
            // Patterns keep their exact text after one separating space.
            if (keyword.starts_with("CHECK") || keyword.starts_with("EXPECT-")) {
                value = line.substr(line.find(':') + 1);
                if (!value.empty() && value.back() == '\r')
                    value.pop_back();
                if (!value.empty() && value[0] == ' ')
                    value.erase(0, 1);
            }
            return true;
        }
    }
    return false;
}
inline CaseFile parse(const std::string &path) {
    std::ifstream stream(path);
    if (!stream)
        throw Error("cannot read " + path);
    CaseFile file{path, {Case{}}};
    file.cases[0].name = "<base>";
    std::string line;
    int number = 0;
    while (std::getline(stream, line)) {
        ++number;
        std::string keyword, value;
        auto &current = file.cases.back();
        if (!directive(line, keyword, value)) {
            const auto text = trim(line);
            // A comment that looks like a directive but does not parse is an error.
            const auto comment = text.empty() || text[0] != ';' ? std::string() : trim(text.substr(1));
            for (const auto *prefix : {"RUN", "EXPECT", "CHECK", "CASE", "BASE", "ABI"})
                if (comment.starts_with(prefix))
                    throw Error(path + ":" + std::to_string(number) + ": malformed directive: " + text);
            if (text.empty() || text[0] == ';')
                continue;
            current.body.push_back(line);
            continue;
        }
        if (keyword == "CASE") {
            file.cases.push_back(Case{});
            file.cases.back().name = value;
            file.cases.back().line = number;
        } else if (keyword == "BASE") {
            current.base = value;
        } else if (keyword == "RUN") {
            current.runs.emplace_back();
            current.runs.back().action = value;
        } else if (current.runs.empty()) {
            throw Error(path + ":" + std::to_string(number) + ": " + keyword + " before RUN");
        } else if (keyword == "EXPECT-OK") {
            current.runs.back().expectOk = true;
        } else if (keyword == "EXPECT-ERROR") {
            current.runs.back().errors.push_back(value);
        } else if (keyword == "EXPECT-MESSAGE") {
            current.runs.back().message = value;
        } else if (keyword == "EXPECT-CODE") {
            current.runs.back().code = value;
        } else if (keyword == "ABI") {
            current.runs.back().abi.push_back(value);
        } else {
            if (value.empty())
                throw Error(path + ":" + std::to_string(number) + ": empty " + keyword + " pattern");
            current.runs.back().checks.push_back({keyword, value, number});
        }
    }
    for (const auto &item : file.cases)
        for (const auto &run : item.runs)
            if ((!run.errors.empty() || run.message || run.code) && !run.checks.empty())
                throw Error(path + ":" + std::to_string(item.line) + ": CHECK lines on a run that expects an error");
    return file;
}

// Zero-context unified hunks (@@ -a,b +c,d @@) against the base module lines.
inline std::vector<std::string>
patch(const std::vector<std::string> &base, const Case &item, const std::string &where) {
    std::vector<std::string> out;
    std::size_t consumed = 0;
    std::size_t index = 0;
    const auto fail = [&](const std::string &message) {
        throw Error(where + ": patch: " + message);
    };
    const auto &body = item.body;
    // Strict "@@ -A[,B] +C[,D] @@" with non-negative decimal fields.
    const auto range = [&](std::string_view text, char sign, long &start, long &count, const std::string &header) {
        if (text.empty() || text[0] != sign)
            fail("bad hunk header '" + header + "'");
        text.remove_prefix(1);
        const auto number = [&](std::string_view digits, long &result) {
            const auto [last, error] = std::from_chars(digits.data(), digits.data() + digits.size(), result);
            if (digits.empty() || error != std::errc{} || last != digits.data() + digits.size() || result < 0)
                fail("bad hunk header '" + header + "'");
        };
        const auto comma = text.find(',');
        number(text.substr(0, comma), start);
        count = 1;
        if (comma != std::string_view::npos)
            number(text.substr(comma + 1), count);
    };
    while (index < body.size()) {
        const auto &header = body[index++];
        long oldStart = 0, oldCount = 1, newStart = 0, newCount = 1;
        std::istringstream parser(header);
        std::string at, oldRange, newRange, closing, extra;
        parser >> at >> oldRange >> newRange >> closing;
        if (at != "@@" || closing != "@@" || (parser >> extra))
            fail("expected @@ -a,b +c,d @@ hunk header, got '" + header + "'");
        range(oldRange, '-', oldStart, oldCount, header);
        range(newRange, '+', newStart, newCount, header);
        if ((oldCount != 0 && oldStart == 0) || (newCount != 0 && newStart == 0))
            fail("bad hunk header '" + header + "'");
        // A pure insertion names the line it follows; a change names its first line.
        const auto first = static_cast<std::size_t>(oldCount == 0 ? oldStart : oldStart - 1);
        if (first < consumed || first > base.size() || first + oldCount > base.size())
            fail("hunk out of order or range '" + header + "'");
        out.insert(out.end(), base.begin() + consumed, base.begin() + first);
        if (static_cast<std::size_t>(newStart) != out.size() + (newCount == 0 ? 0 : 1))
            fail("new range does not follow the old range in '" + header + "'");
        for (long removed = 0; removed < oldCount; ++removed) {
            if (index >= body.size() || body[index].empty() || body[index][0] != '-')
                fail("missing '-' line in '" + header + "'");
            if (body[index].substr(1) != base[first + removed])
                fail("'-' line does not match base line " + std::to_string(first + removed + 1) + ": '" +
                     body[index].substr(1) + "' vs '" + base[first + removed] + "'");
            ++index;
        }
        for (long added = 0; added < newCount; ++added) {
            if (index >= body.size() || body[index].empty() || body[index][0] != '+')
                fail("missing '+' line in '" + header + "'");
            out.push_back(body[index++].substr(1));
        }
        consumed = first + oldCount;
    }
    out.insert(out.end(), base.begin() + consumed, base.end());
    return out;
}
inline bool isPatch(const Case &item) {
    return !item.body.empty() && item.body[0].starts_with("@@");
}
// Resolved module lines for every case, by name; later cases may name earlier ones.
inline std::vector<std::string>
resolve(const CaseFile &file, std::size_t index, std::map<std::string, std::vector<std::string>> &done) {
    const auto &item = file.cases[index];
    const auto where = file.path + ":" + std::to_string(item.line) + " (" + item.name + ")";
    if (!isPatch(item)) {
        if (item.body.empty() && index != 0) {
            const auto base = item.base.empty() ? "<base>" : item.base;
            if (!done.contains(base))
                throw Error(where + ": unknown base '" + base + "'");
            return done.at(base);
        }
        return item.body;
    }
    if (index == 0)
        throw Error(where + ": the header cannot be a patch");
    const auto base = item.base.empty() ? "<base>" : item.base;
    if (!done.contains(base))
        throw Error(where + ": unknown base '" + base + "'");
    return patch(done.at(base), item, where);
}
inline std::string join(const std::vector<std::string> &lines) {
    std::string out;
    for (const auto &line : lines)
        out += line + '\n';
    return out;
}
inline const Case &findCase(const CaseFile &file, const std::string &name, std::vector<std::string> &moduleLines) {
    std::map<std::string, std::vector<std::string>> resolved;
    for (std::size_t index = 0; index < file.cases.size(); ++index) {
        auto current = resolve(file, index, resolved);
        if (file.cases[index].name == name) {
            moduleLines = std::move(current);
            return file.cases[index];
        }
        resolved.emplace(file.cases[index].name, std::move(current));
    }
    throw Error(file.path + ": no case named '" + name + "'");
}
// The resolved module of one named case, read without validation.
inline ir::Module loadCase(const std::string &path, const std::string &name) {
    const auto file = parse(path);
    std::vector<std::string> moduleLines;
    findCase(file, name, moduleLines);
    return ir::text::read(join(moduleLines));
}
} // namespace aurora::test::air
