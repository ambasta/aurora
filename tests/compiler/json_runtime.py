"""Shared POD transport for the JSON library's runtime fixture drivers.

The individual gates own their AU program, record schema, fixture corpus and
semantic comparator. This helper only checks ABI facts, links the borrowed
receiver bridge, streams plain records and retains full-width observations.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import os
import shlex
import struct

import utf8_range as harness

require = harness.require


def run(suite, name, source, record_name, entry_name, fields, records, kind, compare):
    require(kind in ("i64", "u64"), "JSON runtime observation kind")
    require(len(source.encode()) <= 65536, "JSON runtime source byte cap")
    size = fields[-1][1] + fields[-1][2]
    require(size % 8 == 0, "JSON runtime aligned input extent")
    suite.budget()
    directory = suite.output / name
    directory.mkdir()
    source_path, assembly, facts = (directory / item for item in ("input.au", "compiled.s", "abi.json"))
    source_path.write_text(source)
    records = iter(records)
    wanted, observed, labels, chunks = [], [], [], []
    receipt = dict(
        labels=labels,
        expected=wanted,
        observed=observed,
        chunks=chunks,
        chunk_case_limit=128,
        source_sha256=harness.sha(source_path),
        status="running",
    )
    try:
        suite.command(
            [
                suite.compiler,
                "--module-root",
                suite.root / "library",
                source_path,
                "-o",
                assembly,
                "--abi-facts",
                facts,
            ],
            directory,
            "compiler",
        )
        abi = json.loads(facts.read_text())
        entries = [(symbol, row) for symbol, row in abi["functions"].items() if row["source_name"] == entry_name]
        inputs = [(symbol, row) for symbol, row in abi["records"].items() if row["source_name"] == record_name]
        require(len(entries) == len(inputs) == 1, "unique JSON runtime ABI")
        symbol, method = entries[0]
        record_symbol, record = inputs[0]
        require(
            record["size"] == record["reserved"] == size
            and record["alignment"] == 8
            and [(f["name"], f["offset"], f["bytes"], f["kind"], f.get("array_length", 0)) for f in record["fields"]]
            == fields,
            "JSON runtime input layout",
        )
        require(
            method["receiver"] == record_symbol
            and not method["receiver_mutable"]
            and method["borrowed_root_count"] == 0
            and method["parameter_bytes"] == 8
            and method["result"] == {"bytes": 8, "kind": kind}
            and method["parameters"] == [{"offset": 0, "bytes": 8, "kind": "i64"}],
            "JSON runtime call ABI",
        )
        with assembly.open("a") as stream:
            stream.write(f"\n.text\n.globl json_invoke\njson_invoke:\nmovq %rdi,%r10\nmovq %rsi,%rdi\njmp {symbol}\n")
        object_path = directory / "program.o"
        suite.command(["as", "--64", assembly, "-o", object_path], directory, "assemble")
        require(
            not suite.command(["nm", "-u", object_path], directory, "undefined-object").strip(),
            "unresolved Aurora runtime import",
        )
        host = directory / "driver.cpp"
        types = {"u8": "std::uint8_t", "i64": "std::int64_t", "u64": "std::uint64_t"}
        declarations = "".join(
            f"{types[typ]} {field}" + (f"[{length}]" if length else "") + ";\n" for field, _, _, typ, length in fields
        )
        offsets = "".join(f"static_assert(offsetof(Input,{field})=={offset});\n" for field, offset, _, _, _ in fields)
        host.write_text(
            "#include <cstdint>\n#include <cstdio>\n#include <cstddef>\nstruct Input {\n"
            + declarations
            + f"}};static_assert(sizeof(Input)=={size});\n"
            + offsets
            + f'extern "C" {types[kind]} json_invoke(const Input *,std::int64_t);\n'
            + 'int main(int argc,char **argv){if(argc!=2)return 1;auto *file=std::fopen(argv[1],"rb");'
            "if(!file)return 2;Input input{};std::uint64_t fields=0;while(true){"
            "auto count=std::fread(&fields,1,sizeof(fields),file);if(count==0)break;"
            "if(count!=sizeof(fields)||fields==0||fields>128)return 3;"
            "if(std::fread(&input,1,sizeof(input),file)!=sizeof(input))return 3;"
            "for(std::uint64_t field=0;field<fields;++field){auto value=json_invoke(&input,field);"
            "if(std::fwrite(&value,sizeof(value),1,stdout)!=1)return 4;}}"
            "int result=std::ferror(file)?5:0;if(std::fclose(file)!=0)return 6;return result;}\n"
        )
        suite.command(
            [
                *shlex.split(os.environ.get("CXX", "g++")),
                "-std=c++23",
                "-O2",
                "-Wall",
                "-Wextra",
                "-Werror",
                host,
                object_path,
                "-o",
                directory / "program",
            ],
            directory,
            "link",
        )
        while chunk := list(itertools.islice(records, 128)):
            number = len(chunks)
            data = directory / f"cases-{number:04d}.bin"
            expected = [value for _, _, values in chunk for value in values]
            labels.extend(label for label, _, _ in chunk)
            wanted.extend(expected)
            with data.open("wb") as stream:
                for _, packet, values in chunk:
                    require(len(packet) == size and 0 < len(values) <= 128, "JSON runtime record extent")
                    stream.write(struct.pack("<Q", len(values)))
                    stream.write(packet)
            raw = suite.command([directory / "program", data], directory, f"native-{number:04d}")
            require(len(raw) == len(expected) * 8, "JSON runtime complete 64-bit observations")
            actual = list(struct.unpack("<" + ("q" if kind == "i64" else "Q") * len(expected), raw))
            observed.extend(actual)
            compare(actual, expected)
            chunks.append(
                dict(
                    cases=len(chunk),
                    observations=len(actual),
                    output_sha256=hashlib.sha256(raw).hexdigest(),
                    input_sha256=harness.sha(data),
                )
            )
        receipt.update(status="passed", host_sha256=harness.sha(host))
        suite.count += len(labels)
        suite.observations += len(wanted)
        suite.batches += 1
    except Exception as error:
        receipt.update(status="failed", error=str(error))
        raise
    finally:
        (directory / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"PASS JSON {name}: {len(labels)} cases, {len(wanted)} full {kind} observations", flush=True)
