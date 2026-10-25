#include "ir_text.hpp"
#include "ir_instruction_codec.hpp"
#include <array>
#include <charconv>
#include <limits>
#include <optional>
#include <utility>

namespace aurora::ir::text {
namespace {
using hosted_abi::compiler_lowering::OperandRole;

// ---- closed enum spellings; values outside a table print as raw integers so
// hostile fixtures with out-of-range enumerators still round-trip.
template <class E> class Name {
public:
    E value;
    std::string_view text;
};
constexpr Name<TypeKind> typeKinds[] = {
    {TypeKind::I64, "i64"},
    {TypeKind::Bool, "bool"},
    {TypeKind::Own, "own"},
    {TypeKind::Ref, "ref"},
    {TypeKind::MutRef, "mutref"},
    {TypeKind::Class, "class"},
    {TypeKind::Array, "array"},
    {TypeKind::U64, "u64"},
    {TypeKind::Parameter, "param"},
    {TypeKind::Enum, "enum"},
    {TypeKind::U8, "u8"},
    {TypeKind::ByteSpan, "span"},
    {TypeKind::ByteRegion, "region"},
    {TypeKind::OwnedBytes, "bytes"},
    {TypeKind::ConsoleSession, "console"},
    {TypeKind::DisplaySession, "display"},
    {TypeKind::IommuEventSession, "iommu"},
    {TypeKind::OwnedValues, "values"},
    {TypeKind::CallSession, "call"},
    {TypeKind::Com1UartGrant, "uart"},
    {TypeKind::ServeSession, "serve"},
    {TypeKind::ValueSpan, "spanof"},
};
constexpr Name<Unary> unaries[] = {
    {Unary::CheckedNegate, "CheckedNegate"}, {Unary::LogicalNot, "LogicalNot"}, {Unary::BitNot, "BitNot"}};
constexpr Name<Binary> binaries[] = {{Binary::CheckedAdd, "CheckedAdd"},
                                     {Binary::CheckedSubtract, "CheckedSubtract"},
                                     {Binary::CheckedMultiply, "CheckedMultiply"},
                                     {Binary::CheckedDivide, "CheckedDivide"},
                                     {Binary::CheckedRemainder, "CheckedRemainder"},
                                     {Binary::BitAnd, "BitAnd"},
                                     {Binary::BitOr, "BitOr"},
                                     {Binary::BitXor, "BitXor"},
                                     {Binary::ShiftLeft, "ShiftLeft"},
                                     {Binary::ShiftRight, "ShiftRight"}};
constexpr Name<Comparison> comparisons[] = {{Comparison::Equal, "Equal"},
                                            {Comparison::NotEqual, "NotEqual"},
                                            {Comparison::Less, "Less"},
                                            {Comparison::Greater, "Greater"},
                                            {Comparison::LessEqual, "LessEqual"},
                                            {Comparison::GreaterEqual, "GreaterEqual"}};
constexpr Name<Query> queries[] = {{Query::Size, "Size"}, {Query::PublicFieldCount, "PublicFieldCount"}};
constexpr Name<service::Kind> serviceKinds[] = {{service::Kind::Console, "Console"},
                                                {service::Kind::Display, "Display"},
                                                {service::Kind::IommuEvent, "IommuEvent"},
                                                {service::Kind::Call, "Call"},
                                                {service::Kind::Port, "Port"},
                                                {service::Kind::Serve, "Serve"}};
constexpr Name<service::Operation> serviceOperations[] = {{service::Operation::Next, "Next"},
                                                          {service::Operation::Put, "Put"},
                                                          {service::Operation::Pixel, "Pixel"},
                                                          {service::Operation::IommuPoll, "IommuPoll"},
                                                          {service::Operation::IommuAcknowledge, "IommuAcknowledge"},
                                                          {service::Operation::Call, "Call"},
                                                          {service::Operation::PortRead8, "PortRead8"},
                                                          {service::Operation::PortWrite8, "PortWrite8"},
                                                          {service::Operation::ServeExchange, "ServeExchange"}};

template <class E, std::size_t N> std::string enumText(const Name<E> (&table)[N], E value) {
    for (const auto &entry : table)
        if (entry.value == value)
            return std::string(entry.text);
    return std::to_string(static_cast<long long>(value));
}

// ---- instruction names come from the operation variant itself: the class
// name without namespace, template arguments or the Basic prefix.
template <class T> constexpr std::string_view prettyName() {
    std::string_view name = __PRETTY_FUNCTION__;
    const auto begin = name.find("T = ") + 4;
    auto end = begin;
    for (int depth = 0; end < name.size(); ++end) {
        if (name[end] == '<')
            ++depth;
        else if (name[end] == '>')
            --depth;
        else if (depth == 0 && (name[end] == ';' || name[end] == ']'))
            break;
    }
    name = name.substr(begin, end - begin);
    name = name.substr(0, name.find('<'));
    name = name.substr(name.rfind(':') + 1);
    if (name.starts_with("Basic"))
        name.remove_prefix(5);
    return name;
}
constexpr std::size_t instructionKinds = std::variant_size_v<Instruction>;
template <std::size_t... I> constexpr auto instructionNameTable(std::index_sequence<I...>) {
    return std::array<std::string_view, sizeof...(I)>{prettyName<std::variant_alternative_t<I, Instruction>>()...};
}
constexpr auto instructionNames = instructionNameTable(std::make_index_sequence<instructionKinds>{});

template <class Operation> Operation defaultOperation() {
    if constexpr (std::is_same_v<Operation, UnaryValue>)
        return Operation{Unary::CheckedNegate};
    else
        return Operation{};
}

// ---- output tokens
bool bareCharacter(char value) {
    return (value >= 'a' && value <= 'z') || (value >= 'A' && value <= 'Z') || (value >= '0' && value <= '9') ||
           value == '_' || value == '.' || value == ':' || value == '$' || value == '@' || value == '-' ||
           value == '<' || value == '>';
}
std::string quoted(std::string_view value) {
    static constexpr char digits[] = "0123456789abcdef";
    std::string out = "\"";
    for (const unsigned char character : value) {
        if (character == '"' || character == '\\') {
            out += '\\';
            out += static_cast<char>(character);
        } else if (character == '\n') {
            out += "\\n";
        } else if (character == '\t') {
            out += "\\t";
        } else if (character < 0x20 || character >= 0x7f) {
            out += "\\x";
            out += digits[character >> 4];
            out += digits[character & 15];
        } else {
            out += static_cast<char>(character);
        }
    }
    return out + '"';
}
std::string stringText(std::string_view value) {
    if (value.empty())
        return quoted(value);
    for (const char character : value)
        if (!bareCharacter(character))
            return quoted(value);
    return std::string(value);
}
std::string boolText(bool value) {
    return value ? "true" : "false";
}
// Runs of three or more items that differ only by integers in arithmetic
// progression print once as a template with a *count suffix: equal items as
// item*N, progressions with {start,step} in place of each varying integer.
std::optional<std::string> expandTemplate(std::string_view text, long long index);
class NumberTemplate {
public:
    std::vector<std::string> parts;
    std::vector<long long> numbers;
};
std::optional<NumberTemplate> numberTemplate(const std::string &text) {
    NumberTemplate result;
    // Quoted text, templates and nested counts are never templated again.
    if (text.find_first_of("{}\"*") != std::string::npos)
        return std::nullopt;
    std::size_t at = 0, part = 0;
    while (at < text.size()) {
        const bool negative = text[at] == '-' && at + 1 < text.size() && text[at + 1] >= '0' && text[at + 1] <= '9';
        if (!negative && !(text[at] >= '0' && text[at] <= '9')) {
            ++at;
            continue;
        }
        auto end = at + (negative ? 1 : 0);
        while (end < text.size() && text[end] >= '0' && text[end] <= '9')
            ++end;
        long long value = 0;
        const auto [last, error] = std::from_chars(text.data() + at, text.data() + end, value);
        if (error != std::errc{} || last != text.data() + end)
            return std::nullopt;
        result.parts.push_back(text.substr(part, at - part));
        result.numbers.push_back(value);
        part = at = end;
    }
    result.parts.push_back(text.substr(part));
    return result;
}
std::string compressList(const std::vector<std::string> &items) {
    std::vector<std::optional<NumberTemplate>> templates;
    for (const auto &item : items)
        templates.push_back(numberTemplate(item));
    std::string out = "[";
    for (std::size_t index = 0; index < items.size();) {
        auto end = index + 1;
        std::vector<long long> steps;
        const auto &first = templates[index];
        if (first && index + 1 < items.size() && templates[index + 1] && templates[index + 1]->parts == first->parts) {
            bool representable = true;
            for (std::size_t at = 0; at < first->numbers.size(); ++at) {
                long long step = 0;
                representable &= !__builtin_sub_overflow(templates[index + 1]->numbers[at], first->numbers[at], &step);
                steps.push_back(step);
            }
            while (representable && end < items.size() && templates[end] && templates[end]->parts == first->parts) {
                bool matches = true;
                for (std::size_t at = 0; at < steps.size(); ++at) {
                    long long offset = 0, value = 0;
                    matches &= !__builtin_mul_overflow(steps[at], static_cast<long long>(end - index), &offset) &&
                               !__builtin_add_overflow(first->numbers[at], offset, &value) &&
                               templates[end]->numbers[at] == value;
                }
                if (!matches)
                    break;
                ++end;
            }
        } else if (items[index].find('{') == std::string::npos) {
            // A repeated item that already spells a template would read back as one.
            while (end < items.size() && items[end] == items[index])
                ++end;
        }
        if (out.size() > 1)
            out += ' ';
        if (end - index < 3) {
            out += items[index++];
            continue;
        }
        std::string text = items[index];
        if (!steps.empty()) {
            text = first->parts[0];
            for (std::size_t at = 0; at < steps.size(); ++at) {
                text += steps[at] ? "{" + std::to_string(first->numbers[at]) + ',' + std::to_string(steps[at]) + '}'
                                  : std::to_string(first->numbers[at]);
                text += first->parts[at + 1];
            }
            // Keep only templates that spell every item back exactly.
            for (auto at = index; at < end && end - index >= 3; ++at)
                if (expandTemplate(text, static_cast<long long>(at - index)) != items[at])
                    end = index + 1;
            if (end - index < 3) {
                out += items[index++];
                continue;
            }
        }
        out += text + '*' + std::to_string(end - index);
        index = end;
    }
    return out + ']';
}
template <class Range, class Each> std::string listText(const Range &values, Each each) {
    std::vector<std::string> items;
    for (const auto &value : values)
        items.push_back(each(value));
    return compressList(items);
}
std::string integerList(const std::vector<int> &values) {
    return listText(values, [](int value) {
        return std::to_string(value);
    });
}
std::string typeText(const Type &type);
std::string templateArgumentText(const TemplateArgument &argument) {
    std::string out;
    if (argument.kind == TemplateArgumentKind::Value) {
        out = "(value " + std::to_string(argument.value);
        if (argument.type != TypeKind::I64)
            out += " type=" + enumText(typeKinds, argument.type);
    } else {
        out = "(type " + enumText(typeKinds, argument.type);
        if (argument.value != 0)
            out += " value=" + std::to_string(argument.value);
        if (argument.kind != TemplateArgumentKind::Type)
            out += " kind=" + std::to_string(static_cast<long long>(argument.kind));
    }
    if (!argument.className.empty())
        out += " name=" + stringText(argument.className);
    if (!argument.displayName.empty())
        out += " display=" + stringText(argument.displayName);
    if (argument.resolvedClass)
        out += " resolved=true";
    if (!argument.templateArguments.empty())
        out += " targs=" + listText(argument.templateArguments, templateArgumentText);
    return out + ')';
}
std::string typeText(const Type &type) {
    const bool simple = type.className.empty() && type.displayName.empty() && !type.resolvedClass &&
                        type.templateArguments.empty() && type.elementKind == TypeKind::I64 && type.length == 0 &&
                        type.elementParameter.empty() && type.lengthParameter.empty();
    if (simple)
        return enumText(typeKinds, type.kind);
    std::string out = "(" + enumText(typeKinds, type.kind);
    if (!type.className.empty())
        out += ' ' + stringText(type.className);
    if (!type.displayName.empty())
        out += " display=" + stringText(type.displayName);
    if (type.resolvedClass)
        out += " resolved=true";
    if (type.elementKind != TypeKind::I64)
        out += " elem=" + enumText(typeKinds, type.elementKind);
    if (type.length != 0)
        out += " len=" + std::to_string(type.length);
    if (!type.elementParameter.empty())
        out += " eparam=" + stringText(type.elementParameter);
    if (!type.lengthParameter.empty())
        out += " lparam=" + stringText(type.lengthParameter);
    if (!type.templateArguments.empty())
        out += " targs=" + listText(type.templateArguments, templateArgumentText);
    return out + ')';
}
std::string typeList(const std::vector<Type> &types) {
    return listText(types, typeText);
}

// One codec walk spells each operand as one token (a constant spells two).
class PrintCursor {
public:
    std::vector<std::string> tokens;
    void form(detail::InstructionForm) {
    }
    void finish() {
    }
    void integer(OperandRole, const int &value) {
        tokens.push_back(std::to_string(value));
    }
    void boolean(OperandRole, const bool &value) {
        tokens.push_back(boolText(value));
    }
    void type(OperandRole, const Type &value) {
        tokens.push_back(typeText(value));
    }
    void callee(const std::string &value) {
        tokens.push_back(stringText(value));
    }
    void className(const std::string &value) {
        tokens.push_back(stringText(value));
    }
    void moduleScope(const int &value) {
        tokens.push_back(std::to_string(value));
    }
    // Ranges also print borrowed production observations.
    template <class Range> void offsets(OperandRole, const Range &value) {
        tokens.push_back(listText(value, [](int item) {
            return std::to_string(item);
        }));
    }
    template <class Range> void services(const Range &value) {
        tokens.push_back(listText(value, [](const ServiceArgument &argument) {
            return "(" + std::to_string(argument.loanId) + ' ' + enumText(serviceKinds, argument.kind) + ')';
        }));
    }
    template <class Range> void roots(const Range &value) {
        tokens.push_back(listText(value, [](const BorrowedRootArgument &argument) {
            return "(" + std::to_string(argument.root) + ' ' + std::to_string(argument.loanId) + ' ' +
                   std::to_string(argument.fieldIndex) + ')';
        }));
    }
    template <class Range> void literal(const Range &value) {
        std::string bytes;
        for (const unsigned char item : value)
            bytes += static_cast<char>(item);
        tokens.push_back(quoted(bytes));
    }
    void constant(const std::int64_t &value, const Type &valueType) {
        tokens.push_back(std::to_string(value));
        tokens.push_back(typeText(valueType));
    }
    void unary(const Unary &value) {
        tokens.push_back(enumText(unaries, value));
    }
    void binary(const Binary &value) {
        tokens.push_back(enumText(binaries, value));
    }
    void comparison(const Comparison &value) {
        tokens.push_back(enumText(comparisons, value));
    }
    void query(const Query &value) {
        tokens.push_back(enumText(queries, value));
    }
    void serviceKind(const service::Kind &value) {
        tokens.push_back(enumText(serviceKinds, value));
    }
    void serviceOperation(const service::Operation &value) {
        tokens.push_back(enumText(serviceOperations, value));
    }
};
template <class Variant, class T, std::size_t Index = 0> constexpr std::size_t alternativeIndex() {
    if constexpr (std::is_same_v<std::variant_alternative_t<Index, Variant>, T>)
        return Index;
    else
        return alternativeIndex<Variant, T, Index + 1>();
}
template <class Variant> std::string instructionText(const Variant &instruction) {
    static_assert(std::variant_size_v<Variant> == instructionKinds);
    std::string out(instructionNames[instruction.index()]);
    std::visit(
        [&](const auto &value) {
            using Operation = std::remove_cvref_t<decltype(value)>;
            PrintCursor actual, defaults;
            detail::InstructionCodec<Operation>::fields(actual, value);
            // Observations compare against the owning spelling's defaults.
            using Owning = std::variant_alternative_t<alternativeIndex<Variant, Operation>(), Instruction>;
            const auto initial = defaultOperation<Owning>();
            detail::InstructionCodec<Owning>::fields(defaults, initial);
            // Omitted trailing operands keep their default-constructed values.
            auto count = actual.tokens.size();
            while (count > 0 && count <= defaults.tokens.size() &&
                   actual.tokens[count - 1] == defaults.tokens[count - 1])
                --count;
            for (std::size_t index = 0; index < count; ++index)
                out += ' ' + actual.tokens[index];
        },
        instruction);
    return out;
}

// ---- input: each line is a sequence of nodes.
class Node {
public:
    enum class Kind {
        Atom,
        String,
        List,
        Tuple,
        Pair
    };
    Kind kind = Kind::Atom;
    std::string text;
    std::vector<Node> items;
};
// Template text spells a + s*i as {a,s} for the zero-based repetition i; line
// repeat blocks and list items with a *count suffix use it. Input sugar only.
std::optional<std::string> expandTemplate(std::string_view text, long long index) {
    std::string out;
    std::size_t at = 0;
    while (at < text.size()) {
        const auto open = text.find('{', at);
        if (open == std::string_view::npos) {
            out += text.substr(at);
            break;
        }
        const auto close = text.find('}', open);
        const auto comma = text.find(',', open);
        if (close == std::string_view::npos || comma == std::string_view::npos || comma > close)
            return std::nullopt;
        long long start = 0, step = 0, offset = 0, value = 0;
        const auto parse = [&](std::size_t from, std::size_t to, long long &result) {
            const auto [last, error] = std::from_chars(text.data() + from, text.data() + to, result);
            return error == std::errc{} && last == text.data() + to && from != to;
        };
        if (!parse(open + 1, comma, start) || !parse(comma + 1, close, step) ||
            __builtin_mul_overflow(step, index, &offset) || __builtin_add_overflow(start, offset, &value))
            return std::nullopt;
        out += text.substr(at, open - at);
        out += std::to_string(value);
        at = close + 1;
    }
    return out;
}

class Line {
    std::string_view source_;
    std::size_t position_ = 0;
    int number_;

    [[noreturn]] void fail(const std::string &message) const {
        throw Error("air:" + std::to_string(number_) + ": " + message);
    }
    void skipSpace() {
        while (position_ < source_.size() &&
               (source_[position_] == ' ' || source_[position_] == '\t' || source_[position_] == '\r'))
            ++position_;
        if (position_ < source_.size() && source_[position_] == ';')
            position_ = source_.size();
    }
    bool delimiter(char value) const {
        return value == ' ' || value == '\t' || value == '\r' || value == '[' || value == ']' || value == '(' ||
               value == ')' || value == '"' || value == ';' || value == '=' || value == '*';
    }
    std::string string() {
        std::string out;
        ++position_;
        while (true) {
            if (position_ >= source_.size())
                fail("unterminated string");
            const char character = source_[position_++];
            if (character == '"')
                return out;
            if (character != '\\') {
                out += character;
                continue;
            }
            if (position_ >= source_.size())
                fail("unterminated escape");
            const char escape = source_[position_++];
            if (escape == 'n')
                out += '\n';
            else if (escape == 't')
                out += '\t';
            else if (escape == '"' || escape == '\\')
                out += escape;
            else if (escape == 'x' && position_ + 2 <= source_.size()) {
                unsigned value = 0;
                const auto *begin = source_.data() + position_;
                const auto [end, error] = std::from_chars(begin, begin + 2, value, 16);
                if (error != std::errc{} || end != begin + 2)
                    fail("invalid \\x escape");
                out += static_cast<char>(value);
                position_ += 2;
            } else
                fail("invalid escape");
        }
    }
    Node node() {
        skipSpace();
        if (position_ >= source_.size())
            fail("unexpected end of line");
        Node result;
        const char first = source_[position_];
        if (first == '[' || first == '(') {
            const char close = first == '[' ? ']' : ')';
            result.kind = first == '[' ? Node::Kind::List : Node::Kind::Tuple;
            ++position_;
            while (true) {
                skipSpace();
                if (position_ < source_.size() && source_[position_] == close) {
                    ++position_;
                    return result;
                }
                const auto itemBegin = position_;
                result.items.push_back(node());
                // item*N repeats one list item N times; {a,s} in it spells a + s*i.
                if (result.kind == Node::Kind::List && position_ < source_.size() && source_[position_] == '*') {
                    auto itemText = source_.substr(itemBegin, position_ - itemBegin);
                    while (!itemText.empty() && (itemText.back() == ' ' || itemText.back() == '\t'))
                        itemText.remove_suffix(1);
                    const auto begin = ++position_;
                    while (position_ < source_.size() && source_[position_] >= '0' && source_[position_] <= '9')
                        ++position_;
                    std::size_t count = 0;
                    const auto [last, error] =
                        std::from_chars(source_.data() + begin, source_.data() + position_, count);
                    if (error != std::errc{} || last == source_.data() + begin || count == 0 || count > (1u << 20))
                        fail("invalid *count in list");
                    if (itemText.find('{') == std::string_view::npos) {
                        const auto item = result.items.back();
                        result.items.insert(result.items.end(), count - 1, item);
                        continue;
                    }
                    result.items.pop_back();
                    for (std::size_t index = 0; index < count; ++index) {
                        const auto expanded = expandTemplate(itemText, static_cast<long long>(index));
                        if (!expanded)
                            fail("invalid {start,step} in list item");
                        auto items = Line(*expanded, number_).nodes();
                        if (items.size() != 1)
                            fail("list item template must spell one item");
                        result.items.push_back(std::move(items[0]));
                    }
                }
            }
        }
        if (first == ']' || first == ')' || first == '=' || first == '*')
            fail(std::string("unexpected '") + first + "'");
        if (first == '"') {
            result.kind = Node::Kind::String;
            result.text = string();
        } else {
            const auto begin = position_;
            while (position_ < source_.size() && !delimiter(source_[position_]))
                ++position_;
            result.text = std::string(source_.substr(begin, position_ - begin));
        }
        skipSpace();
        if (position_ < source_.size() && source_[position_] == '=') {
            ++position_;
            Node pair;
            pair.kind = Node::Kind::Pair;
            pair.text = std::move(result.text);
            pair.items.push_back(node());
            return pair;
        }
        return result;
    }

public:
    Line(std::string_view source, int number) : source_(source), number_(number) {
    }
    std::vector<Node> nodes() {
        std::vector<Node> result;
        while (true) {
            skipSpace();
            if (position_ >= source_.size())
                return result;
            result.push_back(node());
        }
    }
};

class Reader {
public:
    int line = 0;
    [[noreturn]] void fail(const std::string &message) const {
        throw Error("air:" + std::to_string(line) + ": " + message);
    }
    const std::string &word(const Node &node, std::string_view what) const {
        if (node.kind != Node::Kind::Atom && node.kind != Node::Kind::String)
            fail("expected " + std::string(what));
        return node.text;
    }
    std::int64_t integer64(const Node &node) const {
        if (node.kind != Node::Kind::Atom)
            fail("expected integer");
        std::int64_t value = 0;
        const auto *begin = node.text.data(), *end = begin + node.text.size();
        const auto [last, error] = std::from_chars(begin, end, value);
        if (error != std::errc{} || last != end)
            fail("invalid integer '" + node.text + "'");
        return value;
    }
    int integer(const Node &node) const {
        const auto value = integer64(node);
        if (value < std::numeric_limits<int>::min() || value > std::numeric_limits<int>::max())
            fail("integer out of range '" + node.text + "'");
        return static_cast<int>(value);
    }
    bool boolean(const Node &node) const {
        if (node.kind == Node::Kind::Atom && (node.text == "true" || node.text == "1"))
            return true;
        if (node.kind == Node::Kind::Atom && (node.text == "false" || node.text == "0"))
            return false;
        fail("expected boolean");
    }
    const std::vector<Node> &list(const Node &node) const {
        if (node.kind != Node::Kind::List)
            fail("expected [list]");
        return node.items;
    }
    const std::vector<Node> &tuple(const Node &node, std::size_t minimum, std::size_t maximum) const {
        if (node.kind != Node::Kind::Tuple || node.items.size() < minimum || node.items.size() > maximum)
            fail("expected (tuple) of " + std::to_string(minimum) + ".." + std::to_string(maximum) + " items");
        return node.items;
    }
    template <class E, std::size_t N> E enumeration(const Name<E> (&table)[N], const Node &node) const {
        if (node.kind == Node::Kind::Atom) {
            for (const auto &entry : table)
                if (entry.text == node.text)
                    return entry.value;
            if (!node.text.empty() && (node.text[0] == '-' || (node.text[0] >= '0' && node.text[0] <= '9')))
                return static_cast<E>(integer64(node));
        }
        fail("unknown enumerator '" + node.text + "'");
    }
    std::vector<int> integers(const Node &node) const {
        std::vector<int> result;
        for (const auto &item : list(node))
            result.push_back(integer(item));
        return result;
    }
    TemplateArgument templateArgument(const Node &node) const {
        const auto &items = tuple(node, 2, 16);
        TemplateArgument argument;
        const auto &kind = word(items[0], "type or value");
        if (kind == "type")
            argument.type = enumeration(typeKinds, items[1]);
        else if (kind == "value") {
            argument.kind = TemplateArgumentKind::Value;
            argument.value = integer64(items[1]);
        } else
            fail("expected (type ...) or (value ...)");
        for (std::size_t index = 2; index < items.size(); ++index) {
            const auto &item = items[index];
            if (item.kind != Node::Kind::Pair)
                fail("expected key=value");
            const auto &value = item.items[0];
            if (item.text == "type")
                argument.type = enumeration(typeKinds, value);
            else if (item.text == "kind")
                argument.kind = static_cast<TemplateArgumentKind>(integer64(value));
            else if (item.text == "value")
                argument.value = integer64(value);
            else if (item.text == "name")
                argument.className = word(value, "name");
            else if (item.text == "display")
                argument.displayName = word(value, "name");
            else if (item.text == "resolved")
                argument.resolvedClass = boolean(value);
            else if (item.text == "targs")
                for (const auto &child : list(value))
                    argument.templateArguments.push_back(templateArgument(child));
            else
                fail("unknown template argument key '" + item.text + "'");
        }
        return argument;
    }
    Type type(const Node &node) const {
        if (node.kind == Node::Kind::Atom)
            return Type(enumeration(typeKinds, node));
        const auto &items = tuple(node, 1, 16);
        Type result(enumeration(typeKinds, items[0]));
        for (std::size_t index = 1; index < items.size(); ++index) {
            const auto &item = items[index];
            if (item.kind != Node::Kind::Pair) {
                if (index != 1)
                    fail("type name must follow the kind");
                result.className = word(item, "class name");
                continue;
            }
            const auto &value = item.items[0];
            if (item.text == "display")
                result.displayName = word(value, "name");
            else if (item.text == "resolved")
                result.resolvedClass = boolean(value);
            else if (item.text == "elem")
                result.elementKind = enumeration(typeKinds, value);
            else if (item.text == "len")
                result.length = integer(value);
            else if (item.text == "eparam")
                result.elementParameter = word(value, "name");
            else if (item.text == "lparam")
                result.lengthParameter = word(value, "name");
            else if (item.text == "targs")
                for (const auto &child : list(value))
                    result.templateArguments.push_back(templateArgument(child));
            else
                fail("unknown type key '" + item.text + "'");
        }
        return result;
    }
    std::vector<Type> types(const Node &node) const {
        std::vector<Type> result;
        for (const auto &item : list(node))
            result.push_back(type(item));
        return result;
    }
};

// Operands are positional; a short line leaves trailing defaults in place.
class ReadCursor {
    const Reader &reader_;
    const std::vector<Node> &nodes_;
    std::size_t position_ = 1;
    const Node *next() {
        return position_ < nodes_.size() ? &nodes_[position_++] : nullptr;
    }

public:
    ReadCursor(const Reader &reader, const std::vector<Node> &nodes) : reader_(reader), nodes_(nodes) {
    }
    void finish() {
        if (position_ < nodes_.size())
            reader_.fail("too many operands for " + nodes_[0].text);
    }
    void integer(OperandRole, int &value) {
        if (const auto *node = next())
            value = reader_.integer(*node);
    }
    void boolean(OperandRole, bool &value) {
        if (const auto *node = next())
            value = reader_.boolean(*node);
    }
    void type(OperandRole, Type &value) {
        if (const auto *node = next())
            value = reader_.type(*node);
    }
    void callee(std::string &value) {
        if (const auto *node = next())
            value = reader_.word(*node, "callee");
    }
    void className(std::string &value) {
        if (const auto *node = next())
            value = reader_.word(*node, "class name");
    }
    void moduleScope(int &value) {
        if (const auto *node = next())
            value = reader_.integer(*node);
    }
    void offsets(OperandRole, std::vector<int> &value) {
        if (const auto *node = next())
            value = reader_.integers(*node);
    }
    void services(std::vector<ServiceArgument> &value) {
        if (const auto *node = next()) {
            value.clear();
            for (const auto &item : reader_.list(*node)) {
                const auto &fields = reader_.tuple(item, 2, 2);
                value.push_back({reader_.integer(fields[0]), reader_.enumeration(serviceKinds, fields[1])});
            }
        }
    }
    void roots(std::vector<BorrowedRootArgument> &value) {
        if (const auto *node = next()) {
            value.clear();
            for (const auto &item : reader_.list(*node)) {
                const auto &fields = reader_.tuple(item, 3, 3);
                value.push_back({reader_.integer(fields[0]), reader_.integer(fields[1]), reader_.integer(fields[2])});
            }
        }
    }
    void literal(std::vector<unsigned char> &value) {
        if (const auto *node = next()) {
            if (node->kind != Node::Kind::String)
                reader_.fail("expected quoted literal bytes");
            value.assign(node->text.begin(), node->text.end());
        }
    }
    void constant(std::int64_t &value, Type &valueType) {
        if (const auto *node = next())
            value = reader_.integer64(*node);
        if (const auto *node = next())
            valueType = reader_.type(*node);
    }
    void unary(Unary &value) {
        if (const auto *node = next())
            value = reader_.enumeration(unaries, *node);
    }
    void binary(Binary &value) {
        if (const auto *node = next())
            value = reader_.enumeration(binaries, *node);
    }
    void comparison(Comparison &value) {
        if (const auto *node = next())
            value = reader_.enumeration(comparisons, *node);
    }
    void query(Query &value) {
        if (const auto *node = next())
            value = reader_.enumeration(queries, *node);
    }
    void serviceKind(service::Kind &value) {
        if (const auto *node = next())
            value = reader_.enumeration(serviceKinds, *node);
    }
    void serviceOperation(service::Operation &value) {
        if (const auto *node = next())
            value = reader_.enumeration(serviceOperations, *node);
    }
};
using InstructionReader = Instruction (*)(ReadCursor &);
template <std::size_t I> Instruction readAlternative(ReadCursor &cursor) {
    using Operation = std::variant_alternative_t<I, Instruction>;
    auto value = defaultOperation<Operation>();
    detail::InstructionCodec<Operation>::fields(cursor, value);
    cursor.finish();
    return Instruction(std::in_place_index<I>, std::move(value));
}
template <std::size_t... I> constexpr auto instructionReaderTable(std::index_sequence<I...>) {
    return std::array<InstructionReader, sizeof...(I)>{&readAlternative<I>...};
}
constexpr auto instructionReaders = instructionReaderTable(std::make_index_sequence<instructionKinds>{});

std::string fieldText(const ClassField &field) {
    std::string out = "(" + typeText(field.elementType) + ' ' + std::to_string(field.firstLeaf) + ' ' +
                      std::to_string(field.length) + ' ' + boolText(field.array);
    if (field.elementCount != 1)
        out += ' ' + std::to_string(field.elementCount);
    return out + ')';
}
void printFunction(std::string &out, const Function &function) {
    out += "function " + stringText(function.name) + '\n';
    out += "  result " + typeText(function.result) + '\n';
    if (!function.parameters.empty())
        out += "  params " + typeList(function.parameters) + '\n';
    out += "  frame " + std::to_string(function.frameBytes) + '\n';
    if (function.moduleScope != 0)
        out += "  scope " + std::to_string(function.moduleScope) + '\n';
    if (function.receiver) {
        const auto &receiver = *function.receiver;
        out += "  receiver " + stringText(receiver.className) + ' ' + boolText(receiver.mutableValue) + ' ' +
               boolText(receiver.constructor);
        if (!receiver.publicAccess)
            out += " false";
        out += '\n';
    }
    if (function.borrowedRootCount != 0)
        out += "  roots " + std::to_string(function.borrowedRootCount) + '\n';
    if (function.borrowedRootMutability != 0)
        out += "  rootmut " + std::to_string(function.borrowedRootMutability) + '\n';
    if (function.receiverSpanField)
        out += "  spanfield " + std::to_string(*function.receiverSpanField) + '\n';
    for (const auto &[offset, type] : function.slots)
        out += "  slot " + std::to_string(offset) + ' ' + typeText(type) + '\n';
    for (const auto &[offset, slot] : function.objectSlots)
        out += "  object " + std::to_string(offset) + ' ' + stringText(slot.className) + ' ' +
               boolText(slot.mutableValue) + '\n';
    for (const auto &[offset, length] : function.arraySlots)
        out += "  array " + std::to_string(offset) + ' ' + std::to_string(length) + '\n';
    for (const auto offset : function.spanSlots)
        out += "  span " + std::to_string(offset) + '\n';
    for (const auto offset : function.serviceSlots)
        out += "  service " + std::to_string(offset) + '\n';
    for (const auto offset : function.regionSlots)
        out += "  region " + std::to_string(offset) + '\n';
    for (const auto &[offset, mutableValue] : function.byteSlots)
        out += "  bytes " + std::to_string(offset) + ' ' + boolText(mutableValue) + '\n';
    for (const auto &[offset, className] : function.ownedValueTypes)
        out += "  values " + std::to_string(offset) + ' ' + stringText(className) + '\n';
    for (const auto &[offset, className] : function.spanValueTypes)
        out += "  spanvalues " + std::to_string(offset) + ' ' + stringText(className) + '\n';
    for (const auto &instruction : function.code)
        out += "    " + instructionText(instruction) + '\n';
    out += "end\n";
}

class ModuleReader : public Reader {
    Module module_;
    Function *function_ = nullptr;

    template <class Map, class Key> void insertOnce(Map &map, const Key &key, auto value, std::string_view what) {
        if (!map.emplace(key, std::move(value)).second)
            fail("duplicate " + std::string(what));
    }
    void arity(const std::vector<Node> &nodes, std::size_t minimum, std::size_t maximum) const {
        if (nodes.size() < minimum || nodes.size() > maximum)
            fail("wrong operand count for '" + nodes[0].text + "'");
    }
    void moduleLine(const std::vector<Node> &nodes) {
        const auto &keyword = nodes[0].text;
        if (keyword == "function") {
            arity(nodes, 2, 2);
            module_.functions.emplace_back();
            function_ = &module_.functions.back();
            function_->name = word(nodes[1], "function name");
        } else if (keyword == "layout") {
            arity(nodes, 3, 3);
            insertOnce(module_.classLayouts, word(nodes[1], "class"), types(nodes[2]), "layout");
        } else if (keyword == "fields") {
            arity(nodes, 3, 3);
            std::vector<ClassField> fields;
            for (const auto &item : list(nodes[2])) {
                const auto &values = tuple(item, 4, 5);
                ClassField field{type(values[0]), integer(values[1]), integer(values[2]), boolean(values[3])};
                if (values.size() == 5)
                    field.elementCount = integer(values[4]);
                fields.push_back(std::move(field));
            }
            insertOnce(module_.classFields, word(nodes[1], "class"), std::move(fields), "fields");
        } else if (keyword == "storage") {
            arity(nodes, 7, 7);
            ClassStorage storage;
            storage.leafOffsets = integers(nodes[2]);
            storage.fieldOffsets = integers(nodes[3]);
            storage.sizeBytes = integer(nodes[4]);
            storage.alignment = integer(nodes[5]);
            storage.reservedBytes = integer(nodes[6]);
            insertOnce(module_.classStorage, word(nodes[1], "class"), std::move(storage), "storage");
        } else if (keyword == "carrier") {
            arity(nodes, 2, 2);
            if (!module_.classArrayCarriers.insert(word(nodes[1], "class")).second)
                fail("duplicate carrier");
        } else if (keyword == "descriptor") {
            arity(nodes, 4, 4);
            insertOnce(module_.descriptors,
                       integer(nodes[1]),
                       Descriptor{integer64(nodes[2]), integer64(nodes[3])},
                       "descriptor");
        } else if (keyword == "views") {
            arity(nodes, 2, 2);
            module_.descriptorViews.clear();
            for (const auto &item : list(nodes[1])) {
                const auto &values = tuple(item, 2, 2);
                const auto members = integers(values[1]);
                insertOnce(
                    module_.descriptorViews, integer(values[0]), std::set<int>(members.begin(), members.end()), "view");
            }
        } else if (keyword == "enum") {
            arity(nodes, 3, 3);
            insertOnce(module_.enumCases, word(nodes[1], "enum"), integer(nodes[2]), "enum");
        } else {
            fail("unknown declaration '" + keyword + "'");
        }
    }
    void functionLine(const std::vector<Node> &nodes) {
        auto &function = *function_;
        const auto &keyword = nodes[0].text;
        for (std::size_t index = 0; index < instructionKinds; ++index)
            if (instructionNames[index] == keyword) {
                ReadCursor cursor(*this, nodes);
                function.code.push_back(instructionReaders[index](cursor));
                return;
            }
        if (keyword == "end") {
            arity(nodes, 1, 1);
            function_ = nullptr;
        } else if (keyword == "result") {
            arity(nodes, 2, 2);
            function.result = type(nodes[1]);
        } else if (keyword == "params") {
            arity(nodes, 2, 2);
            function.parameters = types(nodes[1]);
        } else if (keyword == "frame") {
            arity(nodes, 2, 2);
            function.frameBytes = integer(nodes[1]);
        } else if (keyword == "scope") {
            arity(nodes, 2, 2);
            function.moduleScope = integer(nodes[1]);
        } else if (keyword == "receiver") {
            arity(nodes, 4, 5);
            function.receiver = Receiver{word(nodes[1], "class"), boolean(nodes[2]), boolean(nodes[3])};
            if (nodes.size() == 5)
                function.receiver->publicAccess = boolean(nodes[4]);
        } else if (keyword == "roots") {
            arity(nodes, 2, 2);
            function.borrowedRootCount = integer64(nodes[1]);
        } else if (keyword == "rootmut") {
            arity(nodes, 2, 2);
            function.borrowedRootMutability = integer64(nodes[1]);
        } else if (keyword == "spanfield") {
            arity(nodes, 2, 2);
            function.receiverSpanField = integer(nodes[1]);
        } else if (keyword == "slot") {
            arity(nodes, 3, 3);
            insertOnce(function.slots, integer(nodes[1]), type(nodes[2]), "slot");
        } else if (keyword == "object") {
            arity(nodes, 4, 4);
            insertOnce(function.objectSlots,
                       integer(nodes[1]),
                       ObjectSlot{word(nodes[2], "class"), boolean(nodes[3])},
                       "object slot");
        } else if (keyword == "array") {
            arity(nodes, 3, 3);
            insertOnce(function.arraySlots, integer(nodes[1]), integer(nodes[2]), "array slot");
        } else if (keyword == "span" || keyword == "service" || keyword == "region") {
            arity(nodes, 2, 2);
            auto &slots = keyword == "span"      ? function.spanSlots
                          : keyword == "service" ? function.serviceSlots
                                                 : function.regionSlots;
            if (!slots.insert(integer(nodes[1])).second)
                fail("duplicate " + keyword + " slot");
        } else if (keyword == "bytes") {
            arity(nodes, 3, 3);
            insertOnce(function.byteSlots, integer(nodes[1]), boolean(nodes[2]), "bytes slot");
        } else if (keyword == "values") {
            arity(nodes, 3, 3);
            insertOnce(function.ownedValueTypes, integer(nodes[1]), word(nodes[2], "class"), "values slot");
        } else if (keyword == "spanvalues") {
            arity(nodes, 3, 3);
            insertOnce(function.spanValueTypes, integer(nodes[1]), word(nodes[2], "class"), "span values slot");
        } else {
            fail("unknown function line '" + keyword + "'");
        }
    }

    // "repeat N" ... "endrepeat" expands its lines N times; see expandTemplate.
    std::string expand(std::string_view text, long long index) const {
        auto out = expandTemplate(text, index);
        if (!out)
            fail("invalid {start,step} in repeat");
        return *out;
    }
    static std::string_view keywordOf(std::string_view text) {
        const auto begin = text.find_first_not_of(" \t");
        if (begin == std::string_view::npos)
            return {};
        text.remove_prefix(begin);
        return text.substr(0, text.find_first_of(" \t\r;"));
    }
    void parseLine(std::string_view text) {
        auto nodes = Line(text, line).nodes();
        if (nodes.empty())
            return;
        if (nodes[0].kind != Node::Kind::Atom)
            fail("line must start with a keyword");
        if (function_)
            functionLine(nodes);
        else
            moduleLine(nodes);
    }

public:
    Module read(std::string_view source) {
        std::vector<std::string_view> lines;
        for (std::size_t begin = 0; begin <= source.size();) {
            auto end = source.find('\n', begin);
            if (end == std::string_view::npos)
                end = source.size();
            lines.push_back(source.substr(begin, end - begin));
            begin = end + 1;
        }
        for (std::size_t index = 0; index < lines.size(); ++index) {
            line = static_cast<int>(index + 1);
            if (keywordOf(lines[index]) == "repeat") {
                const auto nodes = Line(lines[index], line).nodes();
                if (nodes.size() != 2)
                    fail("expected repeat COUNT");
                const auto count = integer64(nodes[1]);
                if (count < 0 || count > (1 << 24))
                    fail("repeat count out of range");
                const auto first = index + 1;
                auto last = first;
                while (last < lines.size() && keywordOf(lines[last]) != "endrepeat") {
                    if (keywordOf(lines[last]) == "repeat")
                        fail("nested repeat");
                    ++last;
                }
                if (last == lines.size())
                    fail("missing endrepeat");
                for (long long repetition = 0; repetition < count; ++repetition)
                    for (auto at = first; at < last; ++at) {
                        line = static_cast<int>(at + 1);
                        parseLine(expand(lines[at], repetition));
                    }
                index = last;
                continue;
            }
            if (keywordOf(lines[index]) == "endrepeat")
                fail("endrepeat without repeat");
            parseLine(lines[index]);
        }
        if (function_)
            fail("missing 'end' for function " + stringText(function_->name));
        return std::move(module_);
    }
};
} // namespace

std::string print(const Module &module) {
    std::string out;
    for (const auto &[name, layout] : module.classLayouts)
        out += "layout " + stringText(name) + ' ' + typeList(layout) + '\n';
    for (const auto &[name, fields] : module.classFields)
        out += "fields " + stringText(name) + ' ' + listText(fields, fieldText) + '\n';
    for (const auto &[name, storage] : module.classStorage)
        out += "storage " + stringText(name) + ' ' + integerList(storage.leafOffsets) + ' ' +
               integerList(storage.fieldOffsets) + ' ' + std::to_string(storage.sizeBytes) + ' ' +
               std::to_string(storage.alignment) + ' ' + std::to_string(storage.reservedBytes) + '\n';
    for (const auto &name : module.classArrayCarriers)
        out += "carrier " + stringText(name) + '\n';
    for (const auto &[id, descriptor] : module.descriptors)
        out += "descriptor " + std::to_string(id) + ' ' + std::to_string(descriptor.size) + ' ' +
               std::to_string(descriptor.publicFields) + '\n';
    if (module.descriptorViews != Module{}.descriptorViews)
        out += "views " +
               listText(module.descriptorViews,
                        [](const auto &entry) {
                            return "(" + std::to_string(entry.first) + ' ' +
                                   listText(entry.second,
                                            [](int value) {
                                                return std::to_string(value);
                                            }) +
                                   ')';
                        }) +
               '\n';
    for (const auto &[name, count] : module.enumCases)
        out += "enum " + stringText(name) + ' ' + std::to_string(count) + '\n';
    for (const auto &function : module.functions)
        printFunction(out, function);
    return out;
}

Module read(std::string_view source) {
    return ModuleReader().read(source);
}

std::string printType(const Type &type) {
    return typeText(type);
}

std::string printInstruction(const InstructionObservation &instruction) {
    return instructionText(instruction);
}
} // namespace aurora::ir::text
