// Runs textual IR (.air) cases: verify, emit and fact checks over one module
// per case. The file format is described in tests/compiler/ir/README.md.
#include "ir_text.hpp"
#include "ir_verify.hpp"
#include "hosted_resolver.hpp"
#include "x86.hpp"
#include "../compiler/json_fragments.hpp"
#include "air_cases.hpp"
#include <algorithm>
#include <cctype>
#include <charconv>
#include <climits>
#include <fstream>
#include <iostream>
#include <map>
#include <optional>
#include <regex>
#include <sstream>
#include <string>
#include <vector>

using namespace aurora;
using namespace aurora::ir;
using namespace aurora::test::air;

namespace {

std::vector<std::string> words(const std::string &text) {
    std::istringstream stream(text);
    std::vector<std::string> result;
    for (std::string word; stream >> word;)
        result.push_back(word);
    return result;
}
AbiDeclarations declarations(const Run &item) {
    // ; ABI: function|record|enum <symbol> <source name> [member...]
    AbiDeclarations result;
    for (const auto &line : item.abi) {
        auto fields = words(line);
        if (fields.size() < 3)
            throw Error("ABI declaration needs kind, symbol and source name: " + line);
        AbiDeclaration declaration{fields[2], {fields.begin() + 3, fields.end()}};
        auto &group = fields[0] == "function" ? result.functions
                      : fields[0] == "record" ? result.records
                      : fields[0] == "enum"   ? result.enums
                                              : throw Error("unknown ABI declaration kind " + fields[0]);
        group[fields[1]] = std::move(declaration);
    }
    return result;
}
std::string quotedJson(std::string_view text) {
    std::string out = "\"";
    for (const char character : text) {
        if (character == '"' || character == '\\')
            out += '\\';
        out += character;
    }
    return out + '"';
}
template <class Range> std::string integers(const Range &values) {
    std::string out = "[";
    for (const auto value : values)
        out += (out.size() > 1 ? " " : "") + std::to_string(value);
    return out + "]";
}
std::string optionalText(const std::optional<int> &value) {
    return value ? std::to_string(*value) : "-";
}
// Published metadata of a validated module, one fact per line, for CHECK lines.
std::string metadataText(const ValidatedModule &checked) {
    const auto &metadata = checked.metadata();
    std::string out;
    for (std::size_t index = 0; index < metadata.classCount(); ++index) {
        const auto id = metadata.classAt(index);
        const auto storage = metadata.storage(id);
        out += "class " + metadata.className(id) + " storage " + integers(storage.leafOffsets) + ' ' +
               integers(storage.fieldOffsets) + ' ' + std::to_string(storage.sizeBytes) + ' ' +
               std::to_string(storage.alignment) + ' ' + std::to_string(storage.reservedBytes) +
               (metadata.isOwning(id) ? " owning" : "") + (metadata.isCarrier(id) ? " carrier" : "") + '\n';
    }
    for (std::size_t index = 0; index < metadata.enumCount(); ++index) {
        const auto id = metadata.enumAt(index);
        out += "enum " + metadata.enumName(id) + ' ' + std::to_string(metadata.enumCases(id)) + '\n';
    }
    for (std::size_t id = 0; id < metadata.callableCount(); ++id) {
        const auto callable = metadata.callable(id);
        const auto name = callable.name();
        const auto frame = metadata.frame(id);
        out += "callable " + std::to_string(id) + ' ' + name + " scope " + std::to_string(callable.moduleScope()) +
               " result " + text::printType(callable.result()) + " frame " + std::to_string(frame.frameBytes()) + '\n';
        for (const auto &[offset, type] : frame.scalarSlots())
            out += "slot " + name + ' ' + std::to_string(offset) + ' ' + text::printType(type) + '\n';
        for (const auto &[offset, slot] : frame.objectSlots())
            out += "object " + name + ' ' + std::to_string(offset) + ' ' + slot.className +
                   (slot.mutableValue ? " mutable" : "") + '\n';
        for (const auto &[offset, length] : frame.arraySlots())
            out += "array " + name + ' ' + std::to_string(offset) + ' ' + std::to_string(length) + '\n';
        for (const auto offset : frame.spanSlots())
            out += "span " + name + ' ' + std::to_string(offset) + '\n';
        for (const auto offset : frame.serviceSlots())
            out += "service " + name + ' ' + std::to_string(offset) + '\n';
        for (const auto offset : frame.regionSlots())
            out += "region " + name + ' ' + std::to_string(offset) + '\n';
        for (const auto &[offset, mutableValue] : frame.byteSlots())
            out += "bytes " + name + ' ' + std::to_string(offset) + (mutableValue ? " mutable" : "") + '\n';
        for (const auto &[offset, className] : frame.ownedValueTypes())
            out += "values " + name + ' ' + std::to_string(offset) + ' ' + className + '\n';
        for (const auto &[offset, className] : frame.spanValueTypes())
            out += "spanvalues " + name + ' ' + std::to_string(offset) + ' ' + className + '\n';
        // Storage origins of every frame byte and the extreme offsets.
        std::vector<int> offsets{INT_MIN};
        for (int offset = -1; offset <= frame.frameBytes() + 1; ++offset)
            offsets.push_back(offset);
        offsets.push_back(INT_MAX);
        for (const auto offset : offsets)
            out += "origin " + name + ' ' + std::to_string(offset) + " object " +
                   optionalText(metadata.objectLeafRoot(id, offset)) + " byte " +
                   optionalText(metadata.byteArrayElementRoot(id, offset)) + '\n';
    }
    out += "retained";
    for (const auto &body : checked.get().functions)
        out += ' ' + metadata.callable(body.callableId).name();
    out += '\n';
    // Retained bodies: code position, stable instruction ID and operation.
    for (const auto &body : checked.get().functions) {
        const auto name = metadata.callable(body.callableId).name();
        out += "body " + name + ' ' + std::to_string(body.callableId) + '\n';
        for (std::size_t position = 0; position < body.code.size(); ++position) {
            const auto flow = body.code.flowAt(position);
            out += "code " + name + ' ' + std::to_string(position) + " id " + std::to_string(body.code.idAt(position)) +
                   (flow.target ? " target " + std::to_string(*flow.target) : "") +
                   (flow.fallsThrough ? " falls" : "") + (flow.blockEntry ? " entry" : "") +
                   (flow.unreachableSemanticAfter ? " dead" : "") + " : " +
                   text::printInstruction(body.code[position]) + '\n';
        }
    }
    return out;
}
// Runs the case action; returns its textual output for CHECK lines.
std::string execute(const Run &item, Module module) {
    const auto run = words(item.action);
    if (run.empty())
        throw Error("empty RUN");
    const auto &action = run[0];
    if (action == "verify") {
        auto checked = validate(std::move(module));
        (void)checked;
        return {};
    }
    if (action == "metrics") {
        // Verifier metrics after real ingress; "null" passes no metrics object and
        // the sentinels show whether the verifier started.
        verification::Metrics sentinel{1000000001, 1000000002, 1000000003, 1000000004, 1000000005};
        auto metrics = sentinel;
        const bool null = run.size() > 1 && run[1] == "null";
        std::string outcome;
        try {
            auto ingress = InstructionIngress::import(std::move(module));
            auto checked = validate(std::move(ingress), null ? nullptr : &metrics);
            (void)checked;
            outcome = "\"outcome\":\"accepted\",\"diagnostic\":null";
        } catch (const Error &error) {
            outcome = "\"outcome\":\"rejected\",\"diagnostic\":{\"code\":" +
                      std::to_string(static_cast<int>(error.diagnostic.code)) +
                      ",\"name\":" + quotedJson(diagnosticCode(error.diagnostic.code)) +
                      ",\"text\":" + quotedJson(error.diagnostic.message) + "}";
        }
        if (null)
            return "{" + outcome + ",\"metrics_started\":null,\"metrics\":null}\n";
        const bool started =
            metrics.snapshots != sentinel.snapshots || metrics.peakOperandDepth != sentinel.peakOperandDepth ||
            metrics.peakRetainedOperandFacts != sentinel.peakRetainedOperandFacts ||
            metrics.peakRetainedValueFacts != sentinel.peakRetainedValueFacts ||
            metrics.peakRetainedInitializationPayloadBytes != sentinel.peakRetainedInitializationPayloadBytes;
        return "{" + outcome + ",\"metrics_started\":" + (started ? "true" : "false") +
               ",\"metrics\":{\"snapshots\":" + std::to_string(metrics.snapshots) +
               ",\"peakOperandDepth\":" + std::to_string(metrics.peakOperandDepth) +
               ",\"peakRetainedOperandFacts\":" + std::to_string(metrics.peakRetainedOperandFacts) +
               ",\"peakRetainedValueFacts\":" + std::to_string(metrics.peakRetainedValueFacts) +
               ",\"peakRetainedInitializationPayloadBytes\":" +
               std::to_string(metrics.peakRetainedInitializationPayloadBytes) + "}}\n";
    }
    if (action == "metadata") {
        const auto checked = validate(std::move(module));
        return metadataText(checked);
    }
    if (action == "emit" || action == "stack-facts" || action == "abi-facts") {
        auto binding = SymbolBinding::Default;
        auto reflection = ReflectionEmission::All;
        for (std::size_t index = 1; index < run.size(); ++index) {
            if (run[index] == "local")
                binding = SymbolBinding::Local;
            else if (run[index] == "referenced")
                reflection = ReflectionEmission::Referenced;
            else
                throw Error("unknown emit option " + run[index]);
        }
        const auto checked = validate(std::move(module));
        X86Emitter emitter;
        auto assembly = emitter.emit(checked, binding, reflection);
        if (action == "stack-facts")
            return emitter.stackFactsJson(checked);
        if (action == "abi-facts")
            return emitter.abiFactsJson(checked, declarations(item));
        return assembly;
    }
    throw Error("unknown RUN action '" + action + "'");
}

std::string jsonPath(std::string_view json, const std::string &path) {
    std::string_view value = json;
    std::size_t begin = 0;
    while (begin <= path.size()) {
        auto end = path.find('.', begin);
        if (end == std::string::npos)
            end = path.size();
        value = aurora::test::jsonMember(value, std::string_view(path).substr(begin, end - begin));
        if (value.empty())
            return "<missing>";
        begin = end + 1;
    }
    return std::string(value);
}
// Patterns may span lines with \n; \t and \\ are the other escapes.
std::string unescape(const std::string &pattern) {
    std::string out;
    for (std::size_t index = 0; index < pattern.size(); ++index) {
        if (pattern[index] == '\\' && index + 1 < pattern.size()) {
            const char next = pattern[index + 1];
            if (next == 'n' || next == 't' || next == '\\') {
                out += next == 'n' ? '\n' : next == 't' ? '\t' : '\\';
                ++index;
                continue;
            }
        }
        out += pattern[index];
    }
    return out;
}
// Pattern variables of one case, kept across its RUN lines as in FileCheck:
// [[NAME:regex]] and [[#NAME:]] (a decimal integer) define NAME from a match,
// [[NAME]] matches its text and [[#EXPR]] the value of EXPR.
class Variables {
public:
    std::map<std::string, std::string> text;
    std::map<std::string, long long> numbers;
};
bool integer(std::string_view text, long long &value) {
    const auto [last, error] = std::from_chars(text.data(), text.data() + text.size(), value);
    return !text.empty() && error == std::errc{} && last == text.data() + text.size();
}
bool identifier(std::string_view text) {
    if (text.empty() || !(std::isalpha(static_cast<unsigned char>(text[0])) || text[0] == '_'))
        return false;
    return std::all_of(text.begin(), text.end(), [](char character) {
        return std::isalnum(static_cast<unsigned char>(character)) || character == '_';
    });
}
// EXPR combines integers and defined numeric names with + - * %, unary minus
// and parentheses, with the usual precedence.
class Expression {
    std::string_view text_;
    const Variables &variables_;
    std::size_t at_ = 0;

    [[noreturn]] void fail() const {
        throw Error("bad numeric expression [[#" + std::string(text_) + "]]");
    }
    char peek() {
        while (at_ < text_.size() && text_[at_] == ' ')
            ++at_;
        return at_ < text_.size() ? text_[at_] : '\0';
    }
    long long factor() {
        const char next = peek();
        if (next == '-') {
            ++at_;
            return -factor();
        }
        if (next == '(') {
            ++at_;
            const auto value = sum();
            if (peek() != ')')
                fail();
            ++at_;
            return value;
        }
        const auto begin = at_;
        while (at_ < text_.size() && (std::isalnum(static_cast<unsigned char>(text_[at_])) || text_[at_] == '_'))
            ++at_;
        const auto operand = text_.substr(begin, at_ - begin);
        long long value = 0;
        if (identifier(operand)) {
            const auto found = variables_.numbers.find(std::string(operand));
            if (found == variables_.numbers.end())
                throw Error("undefined numeric variable " + std::string(operand));
            return found->second;
        }
        if (!integer(operand, value))
            fail();
        return value;
    }
    long long product() {
        auto value = factor();
        for (char next = peek(); next == '*' || next == '%'; next = peek()) {
            ++at_;
            const auto right = factor();
            if (next == '%' && right == 0)
                fail();
            value = next == '*' ? value * right : value % right;
        }
        return value;
    }
    long long sum() {
        auto value = product();
        for (char next = peek(); next == '+' || next == '-'; next = peek()) {
            ++at_;
            const auto right = product();
            value = next == '+' ? value + right : value - right;
        }
        return value;
    }

public:
    Expression(std::string_view text, const Variables &variables) : text_(text), variables_(variables) {
    }
    long long value() {
        const auto result = sum();
        if (peek() != '\0')
            fail();
        return result;
    }
};
long long evaluate(std::string_view expression, const Variables &variables) {
    return Expression(expression, variables).value();
}
// Replaces each [[#EXPR]] by its value, for directives that take numbers.
std::string substituteNumbers(const std::string &text, const Variables &variables) {
    std::string out;
    std::size_t at = 0;
    while (true) {
        const auto open = text.find("[[#", at);
        out += text.substr(at, open == std::string::npos ? std::string::npos : open - at);
        if (open == std::string::npos)
            return out;
        const auto close = text.find("]]", open);
        if (close == std::string::npos)
            throw Error("unterminated [[# in " + text);
        out += std::to_string(evaluate(std::string_view(text).substr(open + 3, close - open - 3), variables));
        at = close + 2;
    }
}
// Capturing groups opened by an ECMAScript regular expression fragment.
std::size_t groups(std::string_view expression) {
    std::size_t count = 0;
    bool inClass = false;
    for (std::size_t index = 0; index < expression.size(); ++index) {
        const char character = expression[index];
        if (character == '\\')
            ++index;
        else if (inClass)
            inClass = character != ']';
        else if (character == '[')
            inClass = true;
        else if (character == '(' && (index + 1 == expression.size() || expression[index + 1] != '?'))
            ++count;
    }
    return count;
}
// A CHECK pattern is literal text; {{...}} spans are ECMAScript regular
// expressions matched with multiline anchors, and [[...]] spans are variables.
class Pattern {
    std::string literal_;
    std::optional<std::regex> regex_;
    std::vector<std::pair<std::string, bool>> defines_; // name, numeric; by capture group
    std::vector<std::size_t> groupOf_;

public:
    Pattern(const std::string &text, const Variables &variables) : literal_(text) {
        std::string expression, plain;
        bool special = false;
        std::size_t group = 0;
        const auto escape = [](std::string_view literal) {
            std::string out;
            for (const char character : literal) {
                if (std::string_view("\\^$.|?*+()[]{}").find(character) != std::string_view::npos)
                    out += '\\';
                out += character;
            }
            return out;
        };
        const auto define = [&](const std::string &name, bool numeric, const std::string &fragment) {
            if (std::any_of(defines_.begin(), defines_.end(), [&](const auto &item) {
                    return item.first == name;
                }))
                throw Error("variable " + name + " is defined twice in " + text);
            defines_.emplace_back(name, numeric);
            groupOf_.push_back(++group);
            expression += "(" + fragment + ")";
            group += groups(fragment);
        };
        std::size_t at = 0;
        while (at < text.size()) {
            const auto regex = text.find("{{", at), variable = text.find("[[", at);
            const auto open = std::min(regex, variable);
            const auto literal = text.substr(at, open == std::string::npos ? std::string::npos : open - at);
            expression += escape(literal);
            plain += literal;
            if (open == std::string::npos)
                break;
            if (open == regex) {
                const auto close = text.find("}}", open + 2);
                if (close == std::string::npos)
                    throw Error("unterminated {{regex}} in " + text);
                const auto fragment = text.substr(open + 2, close - open - 2);
                expression += "(?:" + fragment + ")";
                group += groups(fragment);
                special = true;
                at = close + 2;
                continue;
            }
            const auto close = text.find("]]", open + 2);
            const auto inner = close == std::string::npos ? std::string() : text.substr(open + 2, close - open - 2);
            const auto colon = inner.find(':');
            if (inner.starts_with("#")) {
                if (inner.ends_with(":") && identifier(std::string_view(inner).substr(1, inner.size() - 2))) {
                    define(inner.substr(1, inner.size() - 2), true, "-?[0-9]+");
                } else {
                    const auto value = std::to_string(evaluate(std::string_view(inner).substr(1), variables));
                    expression += escape(value);
                    plain += value;
                }
            } else if (colon != std::string::npos && identifier(std::string_view(inner).substr(0, colon))) {
                define(inner.substr(0, colon), false, inner.substr(colon + 1));
            } else if (const auto local = std::find_if(defines_.begin(),
                                                       defines_.end(),
                                                       [&](const auto &item) {
                                                           return item.first == inner && !item.second;
                                                       });
                       local != defines_.end()) {
                // A use after its definition in the same pattern is a backreference.
                expression += "\\" + std::to_string(groupOf_[static_cast<std::size_t>(local - defines_.begin())]);
            } else if (identifier(inner)) {
                const auto found = variables.text.find(inner);
                if (found == variables.text.end())
                    throw Error("undefined variable " + inner);
                expression += escape(found->second);
                plain += found->second;
            } else {
                // Not a variable, for example a nested JSON array.
                expression += escape("[[");
                plain += "[[";
                at = open + 2;
                continue;
            }
            special = special || !defines_.empty();
            at = close + 2;
        }
        if (!special && defines_.empty()) {
            literal_ = plain;
            return;
        }
        regex_.emplace(expression, std::regex::ECMAScript | std::regex::multiline);
    }
    bool defines() const {
        return !defines_.empty();
    }
    // Position and length of the first match at or after from; the values of
    // the variables it defines go to captured.
    std::optional<std::pair<std::size_t, std::size_t>>
    find(const std::string &text, std::size_t from, Variables *captured = nullptr) const {
        if (from > text.size())
            return std::nullopt;
        if (!regex_) {
            const auto found = text.find(literal_, from);
            if (found == std::string::npos)
                return std::nullopt;
            return std::pair{found, literal_.size()};
        }
        std::smatch match;
        if (!std::regex_search(text.cbegin() + static_cast<std::ptrdiff_t>(from),
                               text.cend(),
                               match,
                               *regex_,
                               from == 0 ? std::regex_constants::match_default
                                         : std::regex_constants::match_prev_avail))
            return std::nullopt;
        if (captured)
            for (std::size_t index = 0; index < defines_.size(); ++index) {
                const auto &[name, numeric] = defines_[index];
                const auto value = match.str(groupOf_[index]);
                long long number = 0;
                if (numeric && !integer(value, number))
                    throw Error("numeric variable " + name + " matched " + value);
                if (numeric)
                    captured->numbers[name] = number;
                else
                    captured->text[name] = value;
            }
        return std::pair{from + static_cast<std::size_t>(match.position(0)), static_cast<std::size_t>(match.length(0))};
    }
};
// Stack reservation property from the emitted prologue: page-sized steps
// then the remainder, each immediately probed at the new RSP. With an exact
// byte count no further step may follow; otherwise the steps end at the first
// step below a page and their total is returned.
std::string probes(const std::string &output, std::size_t &position, std::optional<int> expected, int &total) {
    auto at = output.find('\n', position);
    const auto line = [&](std::size_t begin) -> std::optional<std::string> {
        if (begin == std::string::npos || begin + 1 >= output.size())
            return std::nullopt;
        ++begin;
        const auto end = output.find('\n', begin);
        return output.substr(begin, (end == std::string::npos ? output.size() : end) - begin);
    };
    const std::string prefix = "    subq $", suffix = ", %rsp", probe = "    orq $0, (%rsp)";
    const auto advance = [&](std::size_t from) {
        return output.find('\n', from + 1);
    };
    total = 0;
    if (expected == 0 || (!expected && line(at) == "    subq $0, %rsp")) {
        if (line(at) != "    subq $0, %rsp")
            return "zero reservation";
        const auto subq = advance(at);
        if (line(subq) == probe)
            return "zero reservation must not touch storage";
        position = subq;
        return {};
    }
    while (!expected || total < *expected) {
        const auto step = line(at);
        const bool isStep = step && step->starts_with(prefix) && step->ends_with(suffix);
        if (!expected && total > 0 && !isStep)
            break;
        if (!isStep)
            return "missing reservation step";
        const auto amount = step->substr(prefix.size(), step->size() - prefix.size() - suffix.size());
        int value = 0;
        const auto [last, error] = std::from_chars(amount.data(), amount.data() + amount.size(), value);
        if (error != std::errc{} || last != amount.data() + amount.size() || value <= 0 || value > 4096 ||
            value % 16 != 0 || (expected && value > *expected - total))
            return "invalid or oversized reservation step";
        if (expected && value != 4096 && value != *expected - total)
            return "noncanonical page step";
        const auto probed = advance(at);
        if (line(probed) != probe)
            return "missing immediate endpoint probe";
        total += value;
        at = advance(probed);
        position = at == std::string::npos ? output.size() : at;
        if (!expected && value != 4096)
            break;
    }
    if (const auto next = line(at); expected && next && next->starts_with(prefix))
        return "extra reservation step";
    return {};
}
// FileCheck subset over the whole output: CHECK finds the pattern at or after
// the end of the previous match, CHECK-NEXT must start on the following line,
// CHECK-SAME on the same line, consecutive CHECK-DAG lines match in any order
// after it, and CHECK-NOT excludes the pattern up to the next positive match.
// CHECK-JSON compares one dotted member path of compact JSON, CHECK-JSON-NOT
// requires a different value (for example <missing> or null) and
// CHECK-JSON-RANGE path LO..HI bounds an integer (either side may be empty).
// CHECK-JSON-ONEOF path A|B accepts any listed value; CHECK-JSON-DIFF A B N
// and CHECK-JSON-RATIO A B N require integer members with A - B == N and
// A == B * N. CHECK-RUN-EQUAL N requires the output of the case's earlier RUN
// N (from 1); with N FROM|TO only the text from FROM up to the next TO.
// CHECK-PROBES [ [[#NAME:]] ] [N | LO..HI] checks the page-stepped stack
// reservation on the lines after the last match: exactly N bytes, or any total
// within the bounds, optionally defining NAME as that total. CHECK-RANGE
// VALUE LO..HI bounds an integer. [[#EXPR]] in CHECK-JSON*, CHECK-RANGE and
// CHECK-PROBES operands is replaced by its value first.
std::string matchChecks(const std::vector<Check> &checks,
                        const std::string &output,
                        const std::vector<std::string> &earlier,
                        Variables &variables) {
    std::size_t position = 0;
    bool matched = false;
    std::optional<std::size_t> dagStart;
    std::size_t dagEnd = 0;
    std::vector<std::pair<std::size_t, std::size_t>> dagMatches; // matches of the current group never overlap
    std::vector<std::pair<const Check *, Pattern>> pending;
    const auto lineStart = [&](std::size_t at) {
        const auto newline = at == 0 ? std::string::npos : output.rfind('\n', at - 1);
        return newline == std::string::npos ? std::size_t{0} : newline + 1;
    };
    const auto excluded = [&](std::size_t end) -> std::string {
        for (const auto &[check, pattern] : pending) {
            const auto found = pattern.find(output, position);
            if (found && found->first + found->second <= end)
                return "line " + std::to_string(check->line) + ": CHECK-NOT matched: " + check->pattern;
        }
        pending.clear();
        return {};
    };
    const auto where = [](const Check &check) {
        return "line " + std::to_string(check.line) + ": " + check.kind + " ";
    };
    // LO..HI with optional sides.
    const auto bounds = [](std::string_view range, long long &low, long long &high) {
        const auto dots = range.find("..");
        low = LLONG_MIN;
        high = LLONG_MAX;
        return dots != std::string_view::npos && (dots == 0 || integer(range.substr(0, dots), low)) &&
               (dots + 2 == range.size() || integer(range.substr(dots + 2), high));
    };
    for (const auto &original : checks) {
        Check substituted;
        const bool numeric = original.kind.starts_with("CHECK-JSON") || original.kind == "CHECK-RANGE";
        if (numeric)
            substituted = {original.kind, substituteNumbers(original.pattern, variables), original.line};
        const auto &check = numeric ? substituted : original;
        if (check.kind == "CHECK-RANGE") {
            const auto fields = words(check.pattern);
            long long value = 0, low = 0, high = 0;
            if (fields.size() != 2 || !integer(fields[0], value) || !bounds(fields[1], low, high))
                return where(check) + "expects VALUE LO..HI";
            if (value < low || value > high)
                return where(check) + original.pattern + ": " + std::to_string(value) + " outside " + fields[1];
            continue;
        }
        if (check.kind == "CHECK-JSON-COUNT") {
            const auto space = check.pattern.find(' ');
            const auto path = check.pattern.substr(0, space);
            const auto expected = space == std::string::npos ? "" : check.pattern.substr(space + 1);
            const auto value = path == "." ? output : jsonPath(output, path);
            const auto actual = value == "<missing>" ? value : std::to_string(aurora::test::jsonMemberCount(value));
            if (actual != expected)
                return where(check) + path + ": expected " + expected + " members, got " + actual;
            continue;
        }
        if (check.kind == "CHECK-JSON" || check.kind == "CHECK-JSON-NOT") {
            const auto space = check.pattern.find(' ');
            const auto path = check.pattern.substr(0, space);
            const auto expected = space == std::string::npos ? "" : check.pattern.substr(space + 1);
            const auto actual = jsonPath(output, path);
            if (check.kind == "CHECK-JSON" && actual != expected)
                return where(check) + path + ": expected " + expected + ", got " + actual;
            if (check.kind == "CHECK-JSON-NOT" && actual == expected)
                return where(check) + path + ": unexpected " + actual;
            continue;
        }
        if (check.kind == "CHECK-JSON-ONEOF") {
            const auto space = check.pattern.find(' ');
            const auto path = check.pattern.substr(0, space);
            const auto choices = space == std::string::npos ? "" : check.pattern.substr(space + 1);
            const auto actual = jsonPath(output, path);
            bool found = false;
            for (std::size_t begin = 0; begin <= choices.size() && !found;) {
                auto end = choices.find('|', begin);
                if (end == std::string::npos)
                    end = choices.size();
                found = choices.compare(begin, end - begin, actual) == 0;
                begin = end + 1;
            }
            if (!found)
                return where(check) + path + ": expected one of " + choices + ", got " + actual;
            continue;
        }
        if (check.kind == "CHECK-JSON-DIFF" || check.kind == "CHECK-JSON-RATIO") {
            const auto fields = words(check.pattern);
            long long minuend = 0, subtrahend = 0, difference = 0;
            if (fields.size() != 3 || !integer(fields[2], difference))
                return where(check) + "expects PATH PATH N";
            const auto first = jsonPath(output, fields[0]), second = jsonPath(output, fields[1]);
            const bool ratio = check.kind == "CHECK-JSON-RATIO";
            if (!integer(first, minuend) || !integer(second, subtrahend) ||
                (ratio ? minuend != subtrahend * difference : minuend - subtrahend != difference))
                return where(check) + fields[0] + (ratio ? " / " : " - ") + fields[1] + ": expected " + fields[2] +
                       ", got " + first + (ratio ? " / " : " - ") + second;
            continue;
        }
        if (check.kind == "CHECK-JSON-RANGE") {
            const auto space = check.pattern.find(' ');
            const auto path = check.pattern.substr(0, space);
            const auto range = space == std::string::npos ? "" : check.pattern.substr(space + 1);
            long long low = 0, high = 0, value = 0;
            if (!bounds(range, low, high))
                return where(check) + "expects PATH LO..HI";
            const auto actual = jsonPath(output, path);
            if (!integer(actual, value) || value < low || value > high)
                return where(check) + path + ": expected " + range + ", got " + actual;
            continue;
        }
        if (check.kind == "CHECK-RUN-EQUAL") {
            std::size_t run = 0;
            const auto space = check.pattern.find(' ');
            const auto text = check.pattern.substr(0, space);
            const auto [last, error] = std::from_chars(text.data(), text.data() + text.size(), run);
            if (error != std::errc{} || last != text.data() + text.size() || run == 0 || run > earlier.size())
                return where(check) + "expects the number of an earlier RUN of this case";
            if (space == std::string::npos) {
                if (output != earlier[run - 1])
                    return where(check) + "output differs from RUN " + text;
                continue;
            }
            const auto bounds = unescape(check.pattern.substr(space + 1));
            const auto bar = bounds.find('|');
            if (bar == std::string::npos || bar == 0 || bar + 1 == bounds.size())
                return where(check) + "expects N FROM|TO";
            const auto from = bounds.substr(0, bar), to = bounds.substr(bar + 1);
            const auto section = [&](const std::string &text) -> std::optional<std::string> {
                const auto begin = text.find(from);
                const auto end = begin == std::string::npos ? begin : text.find(to, begin + from.size());
                if (end == std::string::npos)
                    return std::nullopt;
                return text.substr(begin, end - begin);
            };
            const auto mine = section(output), theirs = section(earlier[run - 1]);
            if (!mine || !theirs)
                return where(check) + "section " + check.pattern.substr(space + 1) + " missing";
            if (*mine != *theirs)
                return where(check) + "section differs from RUN " + text;
            continue;
        }
        const auto unescaped = unescape(check.pattern);
        const Pattern pattern(unescaped, variables);
        if (check.kind == "CHECK-DAG") {
            if (!dagStart) {
                dagStart = position;
                dagMatches.clear();
            }
            auto found = pattern.find(output, *dagStart, &variables);
            while (found && std::any_of(dagMatches.begin(), dagMatches.end(), [&](const auto &match) {
                       return found->first < match.first + match.second && match.first < found->first + found->second;
                   }))
                found = pattern.find(output, found->first + 1, &variables);
            if (!found)
                return where(check) + "not found: " + check.pattern;
            dagMatches.push_back(*found);
            if (auto error = excluded(found->first); !error.empty())
                return error;
            dagEnd = std::max(dagEnd, found->first + found->second);
            matched = true;
            continue;
        }
        if (dagStart) {
            position = std::max(position, dagEnd);
            dagStart.reset();
        }
        if (check.kind == "CHECK-NOT") {
            if (pattern.defines())
                return where(check) + "cannot define variables";
            pending.emplace_back(&check, pattern);
            continue;
        }
        if (check.kind == "CHECK-PROBES") {
            if (!pending.empty())
                return where(check) + "cannot follow CHECK-NOT";
            auto spec = trim(unescaped);
            std::string name;
            if (spec.starts_with("[[#")) {
                const auto close = spec.find(":]]");
                name = close == std::string::npos ? "" : spec.substr(3, close - 3);
                if (!identifier(name))
                    return where(check) + "expects [[#NAME:]] [N | LO..HI]";
                spec = trim(spec.substr(close + 3));
            }
            spec = substituteNumbers(spec, variables);
            long long exact = 0, low = LLONG_MIN, high = LLONG_MAX;
            const bool isExact = integer(spec, exact);
            if ((isExact && (exact < 0 || exact > INT_MAX)) || (!isExact && !spec.empty() && !bounds(spec, low, high)))
                return where(check) + "expects a byte count or LO..HI";
            int total = 0;
            if (auto failure = probes(output, position, isExact ? std::optional<int>(exact) : std::nullopt, total);
                !failure.empty())
                return where(check) + unescaped + ": " + failure;
            if (total < low || total > high)
                return where(check) + unescaped + ": reservation " + std::to_string(total) + " outside " + spec;
            if (!name.empty())
                variables.numbers[name] = total;
            matched = true;
            continue;
        }
        // A CHECK-NEXT/SAME candidate outside its line must not define variables.
        Variables candidate = variables;
        auto found = pattern.find(output, position, &candidate);
        if (check.kind == "CHECK-SAME" || check.kind == "CHECK-NEXT") {
            if (!matched)
                return where(check) + "without a previous match";
            const auto next = output.find('\n', position);
            if (check.kind == "CHECK-SAME") {
                if (found && next != std::string::npos && found->first > next)
                    found.reset();
            } else if (!found || next == std::string::npos || lineStart(found->first) != next + 1) {
                found.reset();
            }
        }
        if (!found)
            return where(check) + "not found: " + check.pattern;
        if (auto error = excluded(found->first); !error.empty())
            return error;
        variables = std::move(candidate);
        position = found->first + found->second;
        matched = true;
    }
    return excluded(output.size());
}

// Returns an empty string on success, else the failure explanation.
std::string runOnce(const Run &run,
                    const std::vector<std::string> &moduleLines,
                    std::vector<std::string> &outputs,
                    Variables &variables) {
    Module module;
    try {
        module = text::read(join(moduleLines));
    } catch (const Error &error) {
        return std::string("cannot read module: ") + error.what();
    }
    const bool expectsError = !run.errors.empty() || run.message || run.code;
    if (expectsError && run.expectOk)
        return "EXPECT-OK conflicts with an expected error";
    std::string output;
    try {
        output = execute(run, std::move(module));
    } catch (const Error &error) {
        outputs.emplace_back();
        if (!expectsError)
            return std::string("unexpected error: ") + error.what();
        for (const auto &expected : run.errors)
            if (std::string(error.what()).find(expected) == std::string::npos)
                return "expected error containing '" + expected + "', got '" + error.what() + "'";
        if (run.message && error.diagnostic.message != *run.message)
            return "expected message '" + *run.message + "', got '" + error.diagnostic.message + "'";
        if (run.code && std::string(diagnosticCode(error.diagnostic.code)) != *run.code)
            return "expected code " + *run.code + ", got " + std::string(diagnosticCode(error.diagnostic.code));
        return {};
    }
    if (expectsError)
        return "expected an error, but the case succeeded";
    auto failure = matchChecks(run.checks, output, outputs, variables);
    outputs.push_back(std::move(output));
    return failure;
}
std::string runCase(const Case &item, const std::vector<std::string> &moduleLines) {
    std::vector<std::string> outputs; // earlier RUN outputs for CHECK-RUN-EQUAL
    Variables variables;              // shared by the case's RUN lines
    for (const auto &run : item.runs)
        if (auto failure = runOnce(run, moduleLines, outputs, variables); !failure.empty())
            return "RUN " + run.action + ": " + failure;
    return {};
}

int runFile(const std::string &path) {
    CaseFile file;
    try {
        file = parse(path);
    } catch (const std::exception &error) {
        std::cout << "FAIL " << path << ": " << error.what() << '\n';
        return 1;
    }
    std::map<std::string, std::vector<std::string>> resolved;
    int failures = 0, passed = 0;
    for (std::size_t index = 0; index < file.cases.size(); ++index) {
        const auto &item = file.cases[index];
        std::string failure;
        try {
            auto moduleLines = resolve(file, index, resolved);
            if (!item.runs.empty())
                failure = runCase(item, moduleLines);
            if (!resolved.emplace(item.name, std::move(moduleLines)).second)
                failure = "duplicate case name";
        } catch (const std::exception &error) {
            failure = error.what();
        }
        if (item.runs.empty() && failure.empty())
            continue;
        if (failure.empty()) {
            ++passed;
        } else {
            ++failures;
            std::cout << "FAIL " << path << ':' << item.line << ": " << item.name << ": " << failure << '\n';
        }
    }
    if (passed + failures == 0) {
        std::cout << "FAIL " << path << ": no case has a RUN line\n";
        return 1;
    }
    std::cout << (failures ? "FAIL " : "PASS ") << path << ": " << passed << " passed, " << failures << " failed\n";
    return failures;
}
} // namespace

int main(int argc, char **argv) {
    try {
        const std::vector<std::string> args(argv + 1, argv + argc);
        // --module FILE CASE prints the resolved, reprinted module; --output
        // FILE CASE [DEST] writes the first RUN action's output (for example
        // assembly) to stdout or DEST.
        if ((args.size() == 3 || args.size() == 4) && (args[0] == "--module" || args[0] == "--output")) {
            const auto file = parse(args[1]);
            std::vector<std::string> moduleLines;
            const auto &item = findCase(file, args[2], moduleLines);
            auto module = text::read(join(moduleLines));
            std::string output;
            if (args[0] == "--module")
                output = text::print(module);
            else if (item.runs.empty())
                throw Error("case has no RUN line");
            else
                output = execute(item.runs.front(), std::move(module));
            if (args.size() == 3) {
                std::cout << output;
                return std::cout ? 0 : 2;
            }
            std::ofstream destination(args[3], std::ios::binary);
            destination << output;
            destination.flush();
            if (!destination)
                throw Error("cannot write " + args[3]);
            return 0;
        }
        if (args.empty() || args[0].starts_with("--")) {
            std::cerr << "usage: aurora-ir-check FILE.air... | --module|--output FILE.air CASE [DEST]\n";
            return 2;
        }
        int failures = 0;
        for (const auto &path : args)
            failures += runFile(path);
        return failures ? 1 : 0;
    } catch (const std::exception &error) {
        std::cerr << "aurora-ir-check: " << error.what() << '\n';
        return 2;
    }
}
