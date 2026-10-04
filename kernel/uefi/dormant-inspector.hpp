#pragma once
#if !defined(AURORA_UEFI_TABLES) || !defined(AURORA_DORMANT_TABLE_TESTING) || AURORA_DORMANT_TABLE_TESTING != 1
#error "Dormant table inspector is restricted to explicit CPU-only test images"
#endif
#include "../dormant-tables.hpp"
#include "../dormant-decoder.hpp"
namespace aurora::memory {
// Trusted compile-selected guest harness. No service-visible binding exists.
class DormantTableTestAccess final {
public:
    [[nodiscard]] static auto snapshot(DormantTables& owner) -> independent::Input {
        independent::Input result;
        result.dte=owner.arena_.subspan(owner.pages_[0]-owner.arena_base_,8192);
        result.root=owner.page(2);result.pages=owner.pages_;result.data_count=owner.data_count_;
        result.physical_bits=owner.physical_bits_;result.iovas=owner.iovas_;result.writable=owner.writable_;
        return result;
    }
    [[nodiscard]] static auto flip(DormantTables& owner,std::size_t role,std::size_t offset,unsigned mask) -> bool {
        if(role>=3 || offset>=4096 || mask>255) return false;
        auto bytes=owner.page(role);if(bytes.size()!=4096)return false;
        bytes[offset]^=std::byte(mask);return true;
    }
};
}
