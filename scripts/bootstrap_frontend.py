#!/usr/bin/env python3
"""Emit the private hosted frontend and its compiler-described ABI.

The compiler-module root contains exact exported source copies. Generated Aurora
bindings remain local; only trusted register bridges expose host entries.
"""

from pathlib import Path
import re
import importlib.util
import json
import subprocess
import sys


# Admission tools also load this module by file path from outside scripts/.
_bridge_spec = importlib.util.spec_from_file_location(
    "_aurora_frontend_bridge", Path(__file__).with_name("frontend_bridge.py")
)
_bridge = importlib.util.module_from_spec(_bridge_spec)
_bridge_spec.loader.exec_module(_bridge)
ENTRIES, render, signatures = _bridge.ENTRIES, _bridge.render, _bridge.signatures

PASS_ENTRIES = signatures()


def abi_declaration(facts, group, source_name):
    """Find a resolved declaration; source spelling is never a mangling recipe."""
    if (
        type(facts.get("version")) is not int
        or facts["version"] not in (1, 2, 3)
        or not isinstance(facts.get(group), dict)
    ):
        raise ValueError("unsupported compiler ABI facts")
    found = [(symbol, entry) for symbol, entry in facts[group].items() if entry["source_name"] == source_name]
    if len(found) != 1:
        raise ValueError(f"expected one ABI declaration: {source_name}")
    return found[0]


def abi_function_symbol(facts, source_name):
    return abi_declaration(facts, "functions", source_name)[0]


def abi_record_owning(facts, symbol, ancestors=()):
    if symbol in ancestors or symbol not in facts["records"]:
        raise ValueError("invalid private ABI record dependency")
    return any(
        field["kind"] == "owner"
        or (field["kind"] == "class" and abi_record_owning(facts, field["type_name"], (*ancestors, symbol)))
        for field in facts["records"][symbol]["fields"]
    )


def normalize_function_abi(facts, function):
    """Normalize exactly the selected paired predecessor and current root facts.

    This version-1 branch belongs only to the immutable paired-root source
    predecessor. Remove it when that predecessor no longer builds this frontend;
    missing lanes never imply additional roots or a later compatibility version.
    """
    version = facts.get("version")
    if type(version) is not int or version not in (1, 2, 3) or type(function) is not dict:
        raise ValueError("unsupported compiler ABI root facts")
    old_fields = {"borrowed_parameter", "second_receiver", "root_count", "root_tuple_bytes", "root_order"}
    new_fields = {"borrowed_roots", "borrowed_root_count", "borrowed_root_abi"}
    common_fields = {"source_name", "receiver", "receiver_mutable", "parameter_bytes", "parameters", "result"}
    if (new_fields if version == 1 else old_fields) & function.keys():
        raise ValueError("conflicting compiler ABI root representations")
    if not (old_fields if version == 1 else new_fields) <= function.keys():
        raise ValueError("incomplete compiler ABI root facts")
    if function.keys() != common_fields | (old_fields if version == 1 else new_fields):
        raise ValueError("unknown compiler ABI function facts")
    receiver, mutable = function.get("receiver"), function.get("receiver_mutable")
    records = facts.get("records", {})
    if (
        "receiver" not in function
        or "receiver_mutable" not in function
        or (receiver is None and mutable is not None)
        or (
            receiver is not None and (type(receiver) is not str or receiver not in records or type(mutable) is not bool)
        )
    ):
        raise ValueError("invalid compiler ABI receiver facts")

    if version == 1:
        borrowed, second = function["borrowed_parameter"], function["second_receiver"]
        if type(borrowed) is not bool or (borrowed and receiver is None):
            raise ValueError("invalid predecessor borrowed root")
        if second is not None and (
            not borrowed
            or mutable is not True
            or type(second) is not dict
            or set(second) != {"type_name", "mutable"}
            or second["mutable"] is not False
            or type(second["type_name"]) is not str
            or second["type_name"] not in records
        ):
            raise ValueError("invalid predecessor second borrowed root")
        count = 2 if second is not None else int(receiver is not None)
        if (
            type(function["root_count"]) is not int
            or function["root_count"] != count
            or type(function["root_tuple_bytes"]) is not int
            or function["root_tuple_bytes"] != (16 if count == 2 else 0)
            or function["root_order"]
            != (["receiver", "second_receiver"] if count == 2 else ["receiver"] if count else [])
        ):
            raise ValueError("invalid predecessor root count, order or tuple")
        roots = []
        if borrowed:
            roots.append(dict(ordinal=0, selector=0, type_name=receiver, mutable=mutable))
            if second is not None:
                roots.append(dict(ordinal=1, selector=-1, type_name=second["type_name"], mutable=False))
            receiver, mutable = None, None
    else:
        roots = function["borrowed_roots"]
        count = function["borrowed_root_count"]
        if type(count) is not int or not 0 <= count <= 3 or type(roots) is not list or len(roots) != count:
            raise ValueError("invalid compiler ABI borrowed root count")
        if count and receiver is not None:
            raise ValueError("borrowed roots cannot also grant a method receiver")

    builtin_root = False
    for ordinal, root in enumerate(roots):
        if type(root) is not dict:
            raise ValueError("invalid compiler ABI borrowed root lane")
        builtin = root.get("kind") == "owned_values"
        keys = {"ordinal", "selector", "type_name", "mutable"}
        if builtin:
            keys |= {"kind", "element_type_name", "descriptor_bytes"}
        if (
            set(root) != keys
            or type(root["ordinal"]) is not int
            or root["ordinal"] != ordinal
            or type(root["selector"]) is not int
            or root["selector"] != -ordinal
            or type(root["mutable"]) is not bool
            or (ordinal > 0 and root["mutable"])
            or type(root["type_name"]) is not str
        ):
            raise ValueError("invalid compiler ABI borrowed root lane")
        if builtin:
            element = root["element_type_name"]
            if (
                version != 3
                or len(roots) != 1
                or root["mutable"] is not True
                or root["type_name"] != "builtin::OwnedValues"
                or type(root["descriptor_bytes"]) is not int
                or root["descriptor_bytes"] != 32
                or type(element) is not str
                or element not in records
                or abi_record_owning(facts, element)
            ):
                raise ValueError("invalid compiler ABI borrowed typed buffer")
            builtin_root = True
        elif root["type_name"] not in records or not any(
            field.get("kind") == "owner" for field in records[root["type_name"]]["fields"]
        ):
            raise ValueError("invalid compiler ABI borrowed root lane")
    if builtin_root and (
        function["result"]["kind"] not in ("i64", "u64", "u8", "bool", "enum")
        or any(
            parameter["kind"] not in ("i64", "u64", "u8", "bool", "enum", "class")
            for parameter in function["parameters"]
        )
    ):
        raise ValueError("invalid compiler ABI borrowed typed buffer tail")
    count = len(roots)
    if count + len(function["parameters"]) > 6 or (
        count >= 2
        and (
            any(parameter["kind"] not in ("i64", "u64", "u8", "bool", "enum") for parameter in function["parameters"])
            or function["result"]["kind"] not in ("i64", "u64", "u8", "bool", "enum")
        )
    ):
        raise ValueError("invalid compiler ABI borrowed root tail")
    root_abi = dict(
        kind="tuple" if count >= 2 else "direct" if count else "none",
        register="r10" if count else None,
        tuple_payload_bytes=8 * count if count >= 2 else 0,
        tuple_reserved_bytes=((8 * count + 15) // 16) * 16 if count >= 2 else 0,
        saved_root_reserved_bytes=((8 * count + 15) // 16) * 16 if count else 0,
    )
    if version in (2, 3) and json.dumps(function["borrowed_root_abi"], sort_keys=True) != json.dumps(
        root_abi, sort_keys=True
    ):
        raise ValueError("invalid compiler ABI borrowed root transport")
    return {
        **{key: value for key, value in function.items() if key not in old_fields},
        "receiver": receiver,
        "receiver_mutable": mutable,
        "borrowed_roots": roots,
        "borrowed_root_count": count,
        "borrowed_root_abi": root_abi,
    }


def frontend_abi_entries(facts):
    """Check the fixed register bridges before allowing generated record writes."""

    def shape(source):
        if source in ("i64", "u64", "u8", "bool", "region", "span"):
            return source, None, facts["span_bytes"] if source == "span" else 8
        group = "enums" if any(value["source_name"] == source for value in facts["enums"].values()) else "records"
        symbol, record = abi_declaration(facts, group, source)
        return "enum" if group == "enums" else "class", symbol, 8 if group == "enums" else record["reserved"]

    def matches(actual, expected):
        kind, symbol, width = shape(expected)
        return actual["kind"] == kind and actual.get("type_name") == symbol and actual["bytes"] == width

    entries = {}
    for alias, (roots, parameters, result, _, _) in PASS_ENTRIES.items():
        source = "compiler_frontend::" + alias
        symbol, raw_function = abi_declaration(facts, "functions", source)
        function = normalize_function_abi(facts, raw_function)
        expected_roots = [(abi_declaration(facts, "records", name)[0], mutable) for name, mutable in roots]
        if (
            function["receiver"] is not None
            or [(root["type_name"], root["mutable"]) for root in function["borrowed_roots"]] != expected_roots
            or len(function["parameters"]) != len(parameters)
            or not matches(function["result"], result)
        ):
            raise ValueError(f"private bridge signature or root authority changed: {source}")
        offset = 0
        for actual, expected in zip(function["parameters"], parameters):
            if not matches(actual, expected) or actual["offset"] != offset:
                raise ValueError(f"private bridge parameter changed: {source}")
            offset += actual["bytes"]
        if function["parameter_bytes"] != offset:
            raise ValueError(f"private bridge record changed: {source}")
        entries[alias] = symbol
    # Cleanup receives a generated prefix of the live transfer record. Refuse
    # layout drift before any host code can reinterpret that enclosing prefix.
    _, ingest = abi_declaration(facts, "functions", "compiler_frontend::resolver_ingest")
    for source, count in (("compiler_frontend::resolver_release", 2), ("compiler_frontend::resolver_release_pair", 3)):
        _, release = abi_declaration(facts, "functions", source)
        if (
            release["parameters"] != ingest["parameters"][:count]
            or release["parameter_bytes"] != ingest["parameters"][count]["offset"]
        ):
            raise ValueError(f"private resolver owner prefix changed: {source}")
    verification_abi(facts)
    return entries


MESSAGE_ROLES = {"name": "DiagnosticNameId", "type": "DiagnosticTypeId", "integer": "DiagnosticInteger"}
MESSAGE_ORIGINS = {
    "": "source_or_synthetic",
    "unlocated": "unlocated",
    "synthetic": "synthetic",
    "integrity": "unlocated",
}


def lowering_messages(source, facts):
    """Host message table from the `//:` lines above each LoweringError case."""
    start = source.index("enum class LoweringError {")
    block = source[start : source.index("};", start)].splitlines()[1:]
    messages, pending = {}, []
    for line in (raw.strip() for raw in block):
        if line.startswith("//:"):
            pending.append(line[3:].strip())
        elif not line or line.startswith("//"):
            if pending:
                raise ValueError("lowering message text must directly precede its reason")
        else:
            name = line.removesuffix(",")
            if not re.fullmatch(r"[a-z][a-z0-9_]*", name) or name in messages:
                raise ValueError("unsupported or repeated lowering reason: " + line)
            messages[name] = " ".join(pending)
            pending = []
    if pending:
        raise ValueError("lowering message text must directly precede its reason")
    _, reasons = abi_declaration(facts, "enums", "compiler_lowering::LoweringError")
    if list(messages) != list(reasons["cases"]) or list(reasons["cases"].values()) != list(range(len(messages))):
        raise ValueError("lowering messages differ from the compiled LoweringError reasons")
    rows = []
    for name, text in messages.items():
        if name == "none":
            if text:
                raise ValueError("the none reason has no message")
            rows.append(
                "    {nullptr, MessageOrigin::unlocated, false, "
                "{OperandRole::NoDiagnosticValue, OperandRole::NoDiagnosticValue}},"
            )
            continue
        flag, _, body = text.partition("] ") if text.startswith("[") else ("", "", text)
        flag = flag.removeprefix("[")
        holes = re.findall(r"\{([^}]*)\}", body)
        if (
            not body
            or flag not in MESSAGE_ORIGINS
            or len(holes) > 2
            or any(h not in MESSAGE_ROLES for h in holes)
            or body.count("{") != len(holes)
            or body.count("}") != len(holes)
        ):
            raise ValueError("unsupported lowering message for " + name)
        if flag == "integrity" and holes:
            raise ValueError("integrity messages carry no payload values: " + name)
        roles = [MESSAGE_ROLES[h] for h in holes] + ["NoDiagnosticValue"] * (2 - len(holes))
        literal = '"' + body.replace("\\", "\\\\").replace('"', '\\"') + '"'
        rows.append(
            f"    {{{literal}, MessageOrigin::{MESSAGE_ORIGINS[flag]}, {'true' if flag == 'integrity' else 'false'}, "
            f"{{OperandRole::{roles[0]}, OperandRole::{roles[1]}}}}},"
        )
    return [
        "namespace aurora::hosted_abi::compiler_lowering {",
        "enum class MessageOrigin : std::uint8_t { source_or_synthetic, synthetic, unlocated };",
        "struct LoweringMessage {",
        "    const char *text;",
        "    MessageOrigin origin;",
        "    bool integrity;",
        "    std::array<OperandRole, 2> values;",
        "};",
        f"inline constexpr std::array<LoweringMessage, {len(rows)}> loweringMessages{{{{",
        *rows,
        "}};",
        "}",
    ]


def owner_messages(source, facts, namespace, enumeration, function):
    """Render constant owner diagnostics from their source-owned reasons."""
    start = source.index("enum class " + enumeration + " {")
    block = source[start : source.index("};", start)].splitlines()[1:]
    messages, pending = {}, []
    for line in (raw.strip() for raw in block):
        if line.startswith("//:"):
            pending.append(line[3:].strip())
        elif not line or line.startswith("//"):
            if pending:
                raise ValueError("owner message must directly precede its reason")
        else:
            name = line.removesuffix(",")
            if not re.fullmatch(r"[a-z][a-z0-9_]*", name) or name in messages:
                raise ValueError("unsupported or repeated owner reason: " + line)
            text = " ".join(pending)
            if (name == "none") != (not text):
                raise ValueError("owner reason requires exactly one constant message: " + name)
            messages[name] = text
            pending = []
    _, reasons = abi_declaration(facts, "enums", namespace + "::" + enumeration)
    if pending or list(messages) != list(reasons["cases"]):
        raise ValueError("owner messages differ from the compiled reasons")
    return [
        "namespace aurora::hosted_abi::" + namespace + " {",
        "inline constexpr const char *" + function + "(" + enumeration + " reason) {",
        "    switch (reason) {",
        *[
            f"    case {enumeration}::{name}: return {json.dumps(text, ensure_ascii=True) if text else 'nullptr'};"
            for name, text in messages.items()
        ],
        "    }",
        "    return nullptr;",
        "}",
        "}",
    ]


def metadata_messages(source, facts):
    return owner_messages(source, facts, "compiler_ir_metadata", "MetadataError", "metadataErrorMessage")


def instruction_messages(source, facts):
    return owner_messages(source, facts, "compiler_ir_instructions", "InstructionError", "instructionErrorMessage")


def verification_messages(source, facts):
    """Exact split reasons, with no host fallback diagnostic or semantic policy."""
    namespace = "compiler_ir_verification"
    lines = []
    for suffix, count in (("First", 200), ("Second", 117)):
        enumeration = "VerificationError" + suffix
        _, reasons = abi_declaration(facts, "enums", namespace + "::" + enumeration)
        if len(reasons["cases"]) != count or list(reasons["cases"].values()) != list(range(count)):
            raise ValueError("private verification split reasons changed: " + enumeration)
        lines += owner_messages(source, facts, namespace, enumeration, "verificationError" + suffix + "Message")
    lines += [
        "namespace aurora::hosted_abi::compiler_ir_verification {",
        "inline constexpr const char *verificationErrorMessage(VerificationError reason) {",
        "    if (!validRaw(reason.firstValue) || !validRaw(reason.secondValue)) return nullptr;",
        "    if (reason.firstValue != VerificationErrorFirst::none) {",
        "        if (reason.secondValue != VerificationErrorSecond::none) return nullptr;",
        "        return verificationErrorFirstMessage(reason.firstValue);",
        "    }",
        "    return verificationErrorSecondMessage(reason.secondValue);",
        "}",
        "}",
    ]
    return lines


def verification_abi(facts):
    """Check the closed owner and copied-report contract against actual facts.

    Field identities below constrain authority, not physical layouts or symbols.
    All byte extents, offsets and symbols are obtained from this emitted root.
    The original initialization owner remains separate for the comparison body.
    """
    namespace = "compiler_ir_verification::"
    records = {}
    for name in ("InitializationStatus", "VerificationStatus"):
        _, status = abi_declaration(facts, "enums", namespace + name)
        if status["cases"] != dict(pending=0, success=1, allocation=2, invalid=3):
            raise ValueError("private verification status changed: " + name)
    for suffix, count in (("First", 200), ("Second", 117)):
        _, errors = abi_declaration(facts, "enums", namespace + "VerificationError" + suffix)
        prefix = ["none", "internal", "allocation"] if suffix == "First" else ["none"]
        if (
            len(errors["cases"]) != count
            or list(errors["cases"])[: len(prefix)] != prefix
            or list(errors["cases"].values()) != list(range(count))
        ):
            raise ValueError("private verification split reasons changed: " + suffix)

    def shape(name, fields):
        symbol, row = abi_declaration(facts, "records", namespace + name)
        if row["alignment"] != 8 or row["reserved"] != row["size"] or len(row["fields"]) != len(fields):
            raise ValueError("private verification record changed: " + name)
        end = 0
        for actual, (field, kind) in zip(row["fields"], fields):
            expected_kind, expected_type, width = kind, None, 32 if kind == "owner" else 8
            if kind not in ("i64", "u64", "bool", "owner"):
                group = (
                    "enums"
                    if kind
                    in (
                        "InitializationStatus",
                        "VerificationStatus",
                        "VerificationErrorFirst",
                        "VerificationErrorSecond",
                    )
                    else "records"
                )
                expected_type, nested = abi_declaration(facts, group, namespace + kind)
                expected_kind = "enum" if group == "enums" else "class"
                width = 8 if group == "enums" else nested["reserved"]
            if (
                actual["name"] != field
                or actual["kind"] != expected_kind
                or actual.get("type_name") != expected_type
                or actual.get("array_length", 0)
                or actual["offset"] != end
                or actual["bytes"] != width
            ):
                raise ValueError("private verification field changed: " + name + "." + field)
            end += width
        if end != row["size"]:
            raise ValueError("private verification extent changed: " + name)
        records[name] = (symbol, row)

    shape("VerificationError", (("firstValue", "VerificationErrorFirst"), ("secondValue", "VerificationErrorSecond")))
    shape(
        "MetricsRow",
        tuple(
            (name, "i64")
            for name in (
                "snapshotsValue",
                "peakOperandDepth",
                "peakRetainedOperandFacts",
                "peakRetainedValueFacts",
                "peakRetainedInitializationPayloadBytes",
            )
        ),
    )
    shape(
        "VerificationReport",
        (
            ("statusValue", "VerificationStatus"),
            ("errorValue", "VerificationError"),
            ("metricsStarted", "bool"),
            ("metricsValue", "MetricsRow"),
        ),
    )
    shape(
        "ControlRow",
        (
            ("metricsStarted", "bool"),
            ("codeBegin", "i64"),
            ("codeCount", "i64"),
            ("activeFactCount", "i64"),
            ("retainedFactCount", "i64"),
            ("currentOperandCount", "i64"),
            ("retainedOperandCount", "i64"),
            ("pendingHead", "i64"),
            ("pendingCount", "i64"),
            ("pendingTail", "i64"),
            ("pendingEnqueued", "i64"),
            ("blockSnapshotCount", "i64"),
            ("currentPosition", "i64"),
            ("instructionId", "i64"),
            ("currentKnown", "bool"),
            ("currentValue", "ValueRow"),
            ("regionOffset", "i64"),
            ("regionSite", "i64"),
            ("hasRegion", "bool"),
            ("receiverClass", "i64"),
            ("hasReceiver", "bool"),
            ("owningConstructor", "bool"),
            ("builtinBorrowedOwner", "bool"),
            ("borrowedRootCount", "i64"),
            ("metricsValue", "MetricsRow"),
            ("retainedValueFacts", "i64"),
            ("retainedInitializationPayload", "i64"),
            ("initializationPayloadPerSnapshot", "i64"),
            ("traversalEpoch", "i64"),
            ("dynamicFactLimit", "i64"),
        ),
    )
    shape("ActiveFact", (("factValue", "FactRow"), ("visitEpoch", "i64")))
    pools = {
        "currentWords": "WordPair",
        "retainedWords": "WordPair",
        "retainedCounts": "CountPair",
        "serviceLoans": "ServiceLoan",
        "currentFacts": "ActiveFact",
        "retainedFacts": "FactRow",
        "currentOperands": "ValueRow",
        "retainedOperands": "ValueRow",
        "codeStates": "CodeStateRow",
        "pendingQueue": "IndexRow",
        "controls": "ControlRow",
    }
    shape(
        "VerificationWorkspace",
        (
            *((name, "owner") for name in pools),
            *(
                (name, "i64")
                for name in (
                    "callableId",
                    "scalarBegin",
                    "scalarCount",
                    "objectBegin",
                    "objectCount",
                    "receiverBegin",
                    "receiverCount",
                    "serviceCapacity",
                    "factCount",
                    "wordCount",
                    "retainedCount",
                    "retainedCapacity",
                    "currentMust",
                    "currentMay",
                )
            ),
            ("statusValue", "InitializationStatus"),
            ("verificationStatus", "VerificationStatus"),
            ("verificationError", "VerificationError"),
        ),
    )
    # Element identity is a closed, source-reviewed association. Facts establish
    # each actual element's copied shape and stride, never a host payload view.
    for name in dict.fromkeys(pools.values()):
        symbol, row = abi_declaration(facts, "records", namespace + name)
        if abi_record_owning(facts, symbol) or row["alignment"] != 8 or row["size"] != row["reserved"]:
            raise ValueError("private verification pool row changed: " + name)
        records[name] = (symbol, row)
    _, raw_run = abi_declaration(facts, "functions", "compiler_frontend::verification_run")
    run = normalize_function_abi(facts, raw_run)
    if run["borrowed_root_count"] != 3 or run["borrowed_root_abi"]["kind"] != "tuple":
        raise ValueError("private verification root tuple changed")
    return records, run


def frontend_abi_header(facts, messages=None, metadata_source=None, instruction_source=None, verification_source=None):
    """Render compiler-described classes and enums without a second field schema."""
    frontend_abi_entries(facts)
    lines = [
        "// Generated from compiler ABI facts; do not edit.",
        "#pragma once",
        "#include <array>",
        "#include <cstddef>",
        "#include <cstdint>",
    ]

    def number(value):
        if type(value) is not int or not 0 <= value <= 65536:
            raise ValueError("invalid private ABI extent")
        return value

    def identifier(name):
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise ValueError("unsupported private ABI identifier")
        return name

    names = {}
    for group in ("enums", "records"):
        for symbol, declaration in facts[group].items():
            name = "::".join(identifier(part) for part in declaration["source_name"].split("::"))
            if name in names.values():
                raise ValueError("ambiguous private ABI source name")
            names[symbol] = name

    def cpp_name(symbol):
        if symbol not in names:
            raise ValueError("unknown private ABI type")
        return "aurora::hosted_abi::" + names[symbol]

    for symbol, declaration in sorted(facts["enums"].items(), key=lambda item: names[item[0]]):
        namespace, _, name = names[symbol].rpartition("::")
        lines += [
            "namespace aurora::hosted_abi" + ("::" + namespace if namespace else "") + " {",
            f"enum class {name} : std::int64_t {{",
        ]
        for case, value in declaration["cases"].items():
            identifier(case)
            if type(value) is not int or not -(2**63) <= value < 2**63:
                raise ValueError("unsupported private ABI enum value")
            lines.append(f"    {case} = {value},")
        lines += [
            "};",
            f"inline constexpr bool validRaw({name} value) {{",
            "    switch (static_cast<std::int64_t>(value)) {",
        ]
        for value in sorted(set(declaration["cases"].values())):
            lines.append(f"    case {value}: return true;")
        lines += ["    default: return false;", "    }", "}", "}"]

    def record(name, size, alignment, members):
        nonlocal lines
        size, alignment = number(size), number(alignment)
        if alignment not in (1, 8) or not size:
            raise ValueError("unsupported private ABI alignment/size")
        lines.append(f"struct alignas({alignment}) {name} {{")
        field_names = {field for _, _, _, field in members}

        def padding_name(candidate):
            while candidate in field_names:
                candidate += "_"
            return candidate

        cursor = 0
        for index, (offset, width, cpp, field) in enumerate(members):
            offset, width = number(offset), number(width)
            if offset < cursor or width <= 0 or offset + width > size:
                raise ValueError("overlapping private ABI fields")
            if offset > cursor:
                lines.append(
                    f"    std::array<std::byte, {offset - cursor}> {padding_name(f'abi_padding_{index}')}{{}};"
                )
            lines.append(f"    {cpp} {field}{{}};")
            cursor = offset + width
        if cursor < size:
            lines.append(f"    std::array<std::byte, {size - cursor}> {padding_name('abi_tail_padding')}{{}};")
        lines += ["};", f"static_assert(sizeof({name}) == {size} && alignof({name}) == {alignment});"]
        for offset, width, _, field in members:
            lines.append(f"static_assert(offsetof({name}, {field}) == {offset});")
            lines.append(f"static_assert(sizeof({name}::{field}) == {width});")

    emitted, active = set(), set()

    def owning(symbol, ancestors=()):
        return abi_record_owning(facts, symbol, ancestors)

    def copied_type(field):
        kind, width = field["kind"], field["bytes"]
        if field.get("array_length", 0):
            length = number(field["array_length"])
            if kind != "u8" or not 1 <= length <= 512 or width != length:
                raise ValueError("private copied array requires bounded exact bytes")
            return f"std::array<std::uint8_t, {length}>"
        if kind in ("enum", "class"):
            symbol = field["type_name"]
            if kind == "class":
                emit_record(symbol)
            expected = 8 if kind == "enum" else facts["records"][symbol]["reserved"]
            if width != expected:
                raise ValueError("private nested ABI extent mismatch")
            return cpp_name(symbol)
        if kind not in ("i64", "u64", "u8", "bool") or width != (1 if kind == "u8" else 8):
            raise ValueError("unsupported private copied field")
        return "std::uint8_t" if kind == "u8" else "std::uint64_t" if kind == "u64" else "std::int64_t"

    def emit_record(symbol):
        if symbol in emitted:
            return
        if symbol in active or symbol not in facts["records"]:
            raise ValueError("invalid private ABI record dependency")
        active.add(symbol)
        declaration = facts["records"][symbol]
        # Owning descriptors never become host-inspectable fields. The host only
        # supplies storage which Aurora constructs and consumes through bridges.
        opaque = owning(symbol)
        members = []
        for field in declaration["fields"] if not opaque else []:
            name = identifier(field["name"])
            members.append((field["offset"], field["bytes"], copied_type(field), name))
        namespace, _, name = names[symbol].rpartition("::")
        lines.append("namespace aurora::hosted_abi" + ("::" + namespace if namespace else "") + " {")
        if opaque:
            size = number(declaration["reserved"])
            members = [(0, size, f"std::array<std::byte, {size}>", "storage")]
        record(name, declaration["reserved"], declaration["alignment"], members)
        lines.append("}")
        active.remove(symbol)
        emitted.add(symbol)

    for symbol in sorted(facts["records"], key=lambda symbol: names[symbol]):
        emit_record(symbol)

    lines.append("namespace aurora::hosted_abi {")
    # A closed host binding, not general access to owning objects. Source review
    # binds each pool name to its row type; predecessor facts provide the physical
    # offsets and copied row shape, but do not claim to encode owner element identity.
    _, metadata_store = abi_declaration(facts, "records", "compiler_ir_metadata::MetadataStore")
    metadata_pools = {
        "bytes": None,
        "types": "RawTypeRow",
        "classes": "ClassRow",
        "fields": "FieldRow",
        "storage": "StorageRow",
        "indices": "IndexRow",
        "descriptors": "DescriptorRow",
        "views": "ViewRow",
        "enums": "EnumRow",
        "callables": "CallableRow",
        "slots": "SlotRow",
        "results": "ClassResultRow",
        "frames": "FrameRow",
    }
    owners = {field["name"]: field for field in metadata_store["fields"] if field["kind"] == "owner"}
    if owners.keys() != metadata_pools.keys():
        raise ValueError("private metadata owner pools changed")

    def qword_row(symbol, ancestors=()):
        if symbol in ancestors:
            raise ValueError("cyclic private metadata row")
        for field in facts["records"][symbol]["fields"]:
            if field.get("array_length", 0):
                raise ValueError("array in private metadata row")
            if field["kind"] == "class":
                qword_row(field["type_name"], (*ancestors, symbol))
            elif field["kind"] not in ("i64", "u64") or field["bytes"] != 8:
                raise ValueError("private metadata row requires integer words")

    for field_name, row_name in metadata_pools.items():
        field = owners[field_name]
        offset, width = number(field["offset"]), number(field["bytes"])
        if width != 32 or field.get("array_length", 0) or offset + width > metadata_store["size"]:
            raise ValueError("private metadata owner descriptor changed: " + field_name)
        lines += [
            f"inline constexpr std::size_t metadataStore_{field_name}Offset = {offset};",
            f"inline constexpr std::size_t metadataStore_{field_name}Bytes = {width};",
        ]
        if row_name is not None:
            symbol, row = abi_declaration(facts, "records", "compiler_ir_metadata::" + row_name)
            qword_row(symbol)
            stride = number(row["size"])
            if stride == 0 or stride > 520 or stride != row["reserved"] or row["alignment"] != 8:
                raise ValueError("private metadata row stride changed: " + row_name)
            lines += [
                f"inline constexpr std::size_t metadata{row_name}PhysicalBytes = {stride};",
                f"static_assert(sizeof({cpp_name(symbol)}) == metadata{row_name}PhysicalBytes);",
            ]
    _, instruction_store = abi_declaration(facts, "records", "compiler_ir_instructions::InstructionStore")
    instruction_pools = {
        "instructions": "RawInstructionRow",
        "operands": "RawOperandRow",
        "literals": None,
        "codeOrder": "CodeRow",
        "bodies": "BodyRow",
    }
    owners = {field["name"]: field for field in instruction_store["fields"] if field["kind"] == "owner"}
    if owners.keys() != instruction_pools.keys():
        raise ValueError("private instruction owner pools changed")
    for field_name, row_name in instruction_pools.items():
        field = owners[field_name]
        offset, width = number(field["offset"]), number(field["bytes"])
        if width != 32 or field.get("array_length", 0) or offset + width > instruction_store["size"]:
            raise ValueError("private instruction owner descriptor changed: " + field_name)
        lines += [
            f"inline constexpr std::size_t instructionStore_{field_name}Offset = {offset};",
            f"inline constexpr std::size_t instructionStore_{field_name}Bytes = {width};",
        ]
        if row_name is not None:
            symbol, row = abi_declaration(facts, "records", "compiler_ir_instructions::" + row_name)
            qword_row(symbol)
            stride = number(row["size"])
            if stride == 0 or stride > 520 or stride != row["reserved"] or row["alignment"] != 8:
                raise ValueError("private instruction row stride changed: " + row_name)
            lines += [
                f"inline constexpr std::size_t instruction{row_name}PhysicalBytes = {stride};",
                f"static_assert(sizeof({cpp_name(symbol)}) == instruction{row_name}PhysicalBytes);",
            ]
    verification_records, verification_run = verification_abi(facts)
    for row_name, (symbol, row) in verification_records.items():
        size = number(row["reserved"])
        if not size:
            raise ValueError("empty private verification row: " + row_name)
        constant = {
            "VerificationWorkspace": "verificationWorkspaceBytes",
            "VerificationReport": "verificationReportBytes",
            "VerificationError": "verificationErrorBytes",
        }.get(row_name, "verification" + row_name + "PhysicalBytes")
        lines += [
            f"inline constexpr std::size_t {constant} = {size};",
            f"static_assert(sizeof({cpp_name(symbol)}) == {constant});",
        ]
        if row_name in ("VerificationWorkspace", "VerificationReport"):
            name = "verification" + row_name.removeprefix("Verification") + "Alignment"
            lines.append(f"inline constexpr std::size_t {name} = {number(row['alignment'])};")
        # Copied report lanes remain integer words, including Aurora bool. Host
        # validation can reject noncanonical 0/1 without reading a native bool.
        if row_name in ("VerificationReport", "VerificationError", "MetricsRow"):
            prefix = "verification" + row_name.removeprefix("Verification")
            for field in row["fields"]:
                field_name = identifier(field["name"])
                lines += [
                    f"inline constexpr std::size_t {prefix}_{field_name}Offset = {number(field['offset'])};",
                    f"inline constexpr std::size_t {prefix}_{field_name}Bytes = {number(field['bytes'])};",
                ]
    root_abi = verification_run["borrowed_root_abi"]
    lines += [
        f"inline constexpr std::size_t verificationRunRootCount = {verification_run['borrowed_root_count']};",
        f"inline constexpr std::size_t verificationRunTuplePayloadBytes = {root_abi['tuple_payload_bytes']};",
        f"inline constexpr std::size_t verificationRunTupleReservedBytes = {root_abi['tuple_reserved_bytes']};",
    ]
    record(
        "VerificationRunRoots",
        root_abi["tuple_reserved_bytes"],
        8,
        [
            (8 * root["ordinal"], 8, "void *" if root["mutable"] else "const void *", name)
            for root, name in zip(verification_run["borrowed_roots"], ("workspace", "metadata", "instructions"))
        ],
    )
    # The only manual physical shape is the trusted contiguous readonly span.
    # Source records and their nesting use the compiler's names and field facts.
    if facts["span_bytes"] != 56:
        raise ValueError("unsupported builtin span ABI")
    record(
        "BuiltinSpan",
        56,
        8,
        [
            (0, 8, "std::uint64_t", "kind"),
            (8, 8, "const char *", "backing"),
            (16, 24, "std::array<std::uint64_t, 3>", "reserved"),
            (40, 8, "std::int64_t", "start"),
            (48, 8, "std::int64_t", "length"),
        ],
    )
    pass_records = tuple(
        (record[0], "compiler_frontend::" + alias, record[1])
        for alias, (_, _, _, record, _) in PASS_ENTRIES.items()
        if record is not None
    )
    for name, source, fields in pass_records:
        _, function = abi_declaration(facts, "functions", source)
        if len(fields) != len(function["parameters"]):
            raise ValueError(f"private ABI argument names changed: {source}")
        members = []
        for field, parameter in zip(fields, function["parameters"]):
            kind = parameter["kind"]
            cpp = "BuiltinSpan" if kind == "span" else "std::uint64_t" if kind == "region" else copied_type(parameter)
            members.append((parameter["offset"], parameter["bytes"], cpp, field))
        record(name, function["parameter_bytes"], 8, members)
    lines += [
        "inline constexpr std::size_t frameBytes = sizeof(compiler_parser::ParseFrame);",
        "inline constexpr std::size_t arenaBytes = sizeof(compiler_parser::AstArena);",
        "inline constexpr std::size_t arenaAlignment = alignof(compiler_parser::AstArena);",
        "inline constexpr std::size_t sessionBytes = sizeof(compiler_resolver::Session);",
        "inline constexpr std::size_t sessionAlignment = alignof(compiler_resolver::Session);",
        "static_assert(offsetof(ResolverRelease, session) == offsetof(ResolverIngest, session));",
        "static_assert(sizeof(ResolverRelease) == offsetof(ResolverIngest, parsed));",
        "static_assert(offsetof(ResolverReleasePair, session) == offsetof(ResolverIngest, session));",
        "static_assert(offsetof(ResolverReleasePair, parsed) == offsetof(ResolverIngest, parsed));",
        "static_assert(sizeof(ResolverReleasePair) == offsetof(ResolverIngest, module));",
        "static_assert(sizeof(void *) == 8);",
        "}",
    ]
    if messages is not None:
        lines += lowering_messages(messages, facts)
    if metadata_source is not None:
        lines += metadata_messages(metadata_source, facts)
    if instruction_source is not None:
        lines += instruction_messages(instruction_source, facts)
    if verification_source is not None:
        lines += verification_messages(verification_source, facts)
    lines += pass_bridges(facts)[0]
    return "\n".join(lines) + "\n"


def pass_bridges(facts):
    """Render only the five existing transports; no source ABI is introduced."""
    declarations, assembly = ['extern "C" {'], [".text"]
    registers = ("%rdi", "%rsi", "%rdx", "%rcx", "%r8", "%r9")
    scalar = {"i64", "u64", "u8", "bool", "enum"}
    policy = {row[0]: row[6:] for row in ENTRIES}
    for alias, (roots, _, _, record, discard) in PASS_ENTRIES.items():
        _, function = abi_declaration(facts, "functions", "compiler_frontend::" + alias)
        parameters, result = function["parameters"], function["result"]["kind"]
        host_alias, noexcept, _, loads, consume = policy[alias]
        host, target = "aurora_hosted_" + host_alias, abi_function_symbol(facts, "compiler_frontend::" + alias)
        moves, arguments = [], []
        if not roots:
            if record is None:
                if parameters or result != "class" or discard:
                    raise ValueError("unsupported private result-only transport: " + alias)
                arguments, moves = ["void *"], [("%rdi", "%r10")]
            else:
                if result != "class" and not (result in scalar and discard):
                    raise ValueError("unsupported private copied transport: " + alias)
                arguments, moves = ["void *" if discard or consume else "const void *"], [("%rdi", "%r11")]
                if not discard:
                    arguments.append("void *")
                    moves.append(("%rsi", "%r10"))
        else:
            if discard:
                raise ValueError("unsupported private discarded root result: " + alias)
            arguments = ["void *" if len(roots) == 1 and roots[0][1] else "const void *"]
            moves = [("%rdi", "%r10")]
            if record is not None:
                arguments.append("const void *")
                moves.append(("%rsi", "%r11"))
                for index in loads:
                    if not 0 <= index < len(parameters) or parameters[index]["kind"] not in scalar:
                        raise ValueError("unsupported private record scalar lane: " + alias)
                    moves.append((str(parameters[index]["offset"]) + "(%r11)", registers[index]))
                if result == "class":
                    arguments.append("void *")
                    moves.append(("%rdx", "%rax"))
                elif result not in scalar:
                    raise ValueError("unsupported private root record result: " + alias)
            else:
                if len(parameters) > 4 or any(parameter["kind"] not in scalar for parameter in parameters):
                    raise ValueError("unsupported private scalar tail: " + alias)
                arguments += ["std::int64_t"] * len(parameters)
                moves += [(registers[index + 1], registers[index]) for index in range(len(parameters))]
                if result == "class":
                    arguments.append("void *")
                    moves.append((registers[len(parameters) + 1], "%r11"))
                elif result not in scalar:
                    raise ValueError("unsupported private scalar result: " + alias)
        returned = "void" if discard or result == "class" else "std::int64_t"
        declarations.append(f"{returned} {host}({', '.join(arguments)}){' noexcept' if noexcept else ''};")
        assembly += [f".globl {host}", f".hidden {host}", f".type {host}, @function", f"{host}:"]
        assembly += [f"    movq {source}, {destination}" for source, destination in moves]
        assembly += [f"    jmp {target}", f".size {host}, .-{host}"]
    return declarations + ["}"], assembly


def frontend_bridge(bridge, facts):
    if bridge is None:
        frontend_abi_entries(facts)
        return "\n".join(pass_bridges(facts)[1]) + "\n"
    for alias, symbol in sorted(frontend_abi_entries(facts).items(), key=lambda item: len(item[0]), reverse=True):
        function = facts["functions"][symbol]
        for index, parameter in enumerate(function["parameters"]):
            bridge = bridge.replace(f"__aurora_parameter_{alias}_{index}", str(parameter["offset"]))
        bridge = bridge.replace("__aurora_frontend_" + alias, symbol)
    if "__aurora_frontend_" in bridge or "__aurora_parameter_" in bridge:
        raise ValueError("unknown private frontend bridge entry")
    return bridge


def stage_modules(module_root, modules):
    """Copy modules byte-for-byte, expanding only the explicit frontend scaffold."""
    for source in modules:
        declaration = re.search(r"^export module ([A-Za-z_][A-Za-z0-9_.]*);", source.read_text(), re.MULTILINE)
        if declaration is None:
            raise ValueError("frontend input requires a named exported module: " + str(source))
        parts = declaration.group(1).split(".")
        destination = module_root.joinpath(*parts[:-1])
        destination.mkdir(parents=True, exist_ok=True)
        content = source.read_bytes()
        if b"// @generated-forwarders" in content:
            content = render(content.decode()).encode()
        (destination / (parts[-1] + ".au")).write_bytes(content)


def write_frontend_header(
    facts, header, messages, metadata_source, instruction_source, compatible_header=None, *, verification_source=None
):
    """Render the admitted facts; reject incompatible shared ABI before writing."""
    content = frontend_abi_header(
        facts,
        messages.read_text(),
        metadata_source.read_text(),
        instruction_source.read_text(),
        verification_source.read_text() if verification_source is not None else None,
    ).encode()
    if compatible_header is not None and compatible_header.read_bytes() != content:
        raise ValueError("stage2 ABI header differs from the header used by shared host objects")
    if not header.exists() or header.read_bytes() != content:
        header.write_bytes(content)


def emit(
    compiler,
    source,
    output,
    module_root,
    messages,
    metadata_source,
    instruction_source,
    compatible_header=None,
    *,
    verification_source,
):
    raw = output.with_suffix(".generated.s")
    facts_output = output.with_suffix(".abi.json")
    command = ["--local-symbols", "--abi-facts", str(facts_output.resolve())]
    command += ["--module-root", str(module_root.resolve())]
    command += [str(source.resolve()), "-o", str(raw.resolve())]
    subprocess.run([str(compiler.resolve()), *command], check=True)
    facts = json.loads(facts_output.read_text())
    header = output.parent / (output.stem.replace("-", "_") + "_abi.hpp")
    write_frontend_header(
        facts,
        header,
        messages,
        metadata_source,
        instruction_source,
        compatible_header,
        verification_source=verification_source,
    )
    # Symbol spellings come from this emitted module; only register moves are trusted.
    output.write_bytes(
        b"\n".join(
            [
                raw.read_bytes(),
                frontend_bridge(None, facts).encode(),
            ]
        )
    )


def main():
    # COMPILER --output OUTPUT INPUT...: .au inputs are the compiler modules,
    # and an optional .hpp is the header that stage-2 output must reproduce.
    arguments = sys.argv[1:]
    if len(arguments) < 4 or arguments[1] != "--output":
        raise ValueError("expected COMPILER --output OUTPUT INPUT...")
    compiler, output = Path(arguments[0]), Path(arguments[2])
    inputs = [Path(argument) for argument in arguments[3:]]
    modules = [path for path in inputs if path.suffix == ".au"]
    headers = [path for path in inputs if path.suffix == ".hpp"]
    names = [path.name for path in modules]
    if (
        len(modules) + len(headers) != len(inputs)
        or len(headers) > 1
        or len(set(names)) != len(names)
        or not {
            "frontend.au",
            "lowering_errors.au",
            "ir_metadata_storage.au",
            "ir_instruction_storage.au",
            "ir_verification_errors.au",
            "ir_verification_storage.au",
            "ir_verification.au",
        }
        <= set(names)
    ):
        raise ValueError("expected unique .au modules including frontend.au and at most one .hpp header")
    module_root = output.parent / (output.stem + "-modules")
    stage_modules(module_root, modules)
    emit(
        compiler,
        module_root / "aurora/compiler/frontend.au",
        output,
        module_root,
        modules[names.index("lowering_errors.au")],
        modules[names.index("ir_metadata_storage.au")],
        modules[names.index("ir_instruction_storage.au")],
        headers[0] if headers else None,
        verification_source=modules[names.index("ir_verification_errors.au")],
    )


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as error:
        sys.exit(f"bootstrap frontend: {error}")
