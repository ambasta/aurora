#include "hosted_private_object.hpp"
#include "host_sources.hpp"
#include "hosted_frontend_abi.hpp"
#include <algorithm>
#include <cstdint>
#include <limits>

namespace aurora {
namespace {
namespace wire = hosted_abi::compiler_private_object;
using Status = hosted_abi::compiler_x86::EmitStatus;

[[noreturn]] void invalidTransport() {
    throw Error(DiagnosticCode::Internal, "invalid private object composition transport");
}
void addExtent(std::uint64_t &total, std::uint64_t count, std::uint64_t stride) {
    if (stride != 0 && count > (std::numeric_limits<std::uint64_t>::max() - total) / stride)
        throw Error(DiagnosticCode::Internal, "private object workspace extent overflow");
    total += count * stride;
}
std::uint64_t quota(std::size_t source, std::size_t wrapper, std::size_t selected) {
    if (source > host::artifactLimit || wrapper > host::artifactLimit || selected > host::artifactLimit)
        throw Error("private object input exceeds 67108864 bytes");
    // Source admission derives exact row counts. These are upper extents, not
    // allocations: one name row per 24 input bytes, one selected row per name
    // plus newline (at least two bytes), and one wrapper remapping row per name.
    // Every owner resizes once to its exact extent; output has the artifact cap.
    std::uint64_t result = host::artifactLimit;
    addExtent(result, source / 24, sizeof(wire::NameRow));
    addExtent(result, wrapper / 24, sizeof(wire::NameRow) + sizeof(hosted_abi::compiler_x86::ObjectIndexRow));
    addExtent(result, selected / 2, sizeof(wire::NameRow));
    return result;
}
class Operation {
    hosted::bytes::Region region;
    hosted_abi::PrivateObjectRelease owner{};

public:
    Operation(std::size_t source, std::size_t wrapper, std::size_t selected, hosted::bytes::Allocator allocator)
        : region(quota(source, wrapper, selected), allocator) {
        if (!region.is_open())
            throw Error(DiagnosticCode::Internal, "private object composition region allocation failed");
        owner.region = region.id();
        hosted_abi::PrivateObjectCreate input{};
        input.region = region.id();
        aurora_hosted_private_object_create(&input, data());
    }
    ~Operation() {
        aurora_hosted_private_object_release(&owner);
    }
    Operation(const Operation &) = delete;
    Operation &operator=(const Operation &) = delete;
    void *data() {
        return owner.workspace.storage.data();
    }
    std::string run(std::string_view source, std::string_view wrapper, std::string_view selected) {
        hosted_abi::PrivateObjectRun input{};
        input.source.backing = source.data();
        input.source.length = static_cast<std::int64_t>(source.size());
        input.wrapper.backing = wrapper.data();
        input.wrapper.length = static_cast<std::int64_t>(wrapper.size());
        input.selected.backing = selected.data();
        input.selected.length = static_cast<std::int64_t>(selected.size());
        const auto status = aurora_hosted_private_object_run(data(), &input);
        if (status == static_cast<std::int64_t>(Status::allocation))
            throw Error(DiagnosticCode::Internal, "private object composition allocation failed");
        if (status == static_cast<std::int64_t>(Status::limit))
            throw Error("private object composition exceeds its bounded output or workspace");
        if (status == static_cast<std::int64_t>(Status::invalid) ||
            status == static_cast<std::int64_t>(Status::unsupported))
            throw Error("private object inputs do not match the admitted private object profiles");
        if (status != static_cast<std::int64_t>(Status::complete))
            invalidTransport();
        const auto size = aurora_hosted_private_object_size(data());
        if (size < 0 || static_cast<std::uint64_t>(size) > host::artifactLimit)
            invalidTransport();
        std::string result;
        result.reserve(static_cast<std::size_t>(size));
        for (std::int64_t offset = 0; offset < size;) {
            hosted_abi::compiler_x86::EmitChunk chunk{};
            aurora_hosted_private_object_chunk(data(), offset, &chunk);
            if (chunk.byteCount != std::min<std::int64_t>(512, size - offset))
                invalidTransport();
            result.append(reinterpret_cast<const char *>(chunk.payload.data()),
                          static_cast<std::size_t>(chunk.byteCount));
            offset += chunk.byteCount;
        }
        return result;
    }
};
} // namespace

std::string composePrivateObject(std::string_view source,
                                 std::string_view wrapper,
                                 std::string_view selected,
                                 hosted::bytes::Allocator allocator) {
    return Operation(source.size(), wrapper.size(), selected.size(), allocator).run(source, wrapper, selected);
}
void composePrivateObjectFiles(const std::filesystem::path &sourcePath,
                               const std::filesystem::path &wrapperPath,
                               const std::filesystem::path &selectedPath,
                               const std::filesystem::path &outputPath) {
    host::ArtifactFile sourceFile(sourcePath), wrapperFile(wrapperPath), selectedFile(selectedPath);
    const auto source = sourceFile.readAtMost();
    const auto wrapper = wrapperFile.readAtMost();
    const auto selected = selectedFile.readAtMost();
    const auto result = composePrivateObject(source, wrapper, selected);
    host::ArtifactWriter output(outputPath, {sourceFile.identity, wrapperFile.identity, selectedFile.identity});
    output.write(result);
    output.commit();
}
} // namespace aurora
