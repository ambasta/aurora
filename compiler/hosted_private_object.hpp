#pragma once
#include "../runtime/hosted_bytes.hpp"
#include <filesystem>
#include <string>
#include <string_view>

namespace aurora {
// Private bootstrap transport only: Aurora admits both object profiles, resolves
// selected names and composes the result. Native code never interprets ELF.
std::string composePrivateObject(std::string_view source,
                                 std::string_view wrapper,
                                 std::string_view selected,
                                 hosted::bytes::Allocator allocator = hosted::bytes::system_allocator());
void composePrivateObjectFiles(const std::filesystem::path &source,
                               const std::filesystem::path &wrapper,
                               const std::filesystem::path &selected,
                               const std::filesystem::path &output);
} // namespace aurora
