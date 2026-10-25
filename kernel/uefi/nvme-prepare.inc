// Included only in the platform fixture image; the bar-prepare row alone calls it.
// Persistent storage prevents accidental reconstruction over retained leases.
constinit std::optional<NvmeQueueBundle> nvme_pages;

[[gnu::noinline]] auto prepare_nvme_pages(U64 arena, memory::PhysicalPages &pool, const NvmeBarGrant &grant,
                                         const WindowAuthority &authority, const PciBarSnapshot &current) -> bool {
    constexpr auto bytes = NvmeQueueBundle::page_count * NvmeQueueBundle::page_bytes;
    const auto base = arena + Handoff::pool_offset;
    if (nvme_pages || pool.used() != 0 || !pool.arena_matches(base, NvmeQueueBundle::pool_pages))
        return false;
    const auto backing = std::span<std::byte>{reinterpret_cast<std::byte *>(base),
                                             NvmeQueueBundle::pool_pages * NvmeQueueBundle::page_bytes};
    volatile std::byte *data = backing.data();
    // The empty existing allocator deterministically gives the first five pages.
    // Poisoned fixture bytes make initialization and cancellation observable.
    for (std::size_t at = 0; at < bytes; ++at)
        data[at] = std::byte{0xa5};
    nvme_pages.emplace(pool, backing, base);
    const auto handle = nvme_pages->prepare(grant, authority, current);
    if (!handle || handle->generation() != 1 || pool.used() != 5 || nvme_pages->held_pages() != 5)
        return false;
    for (std::size_t index = 0; index < NvmeQueueBundle::page_count; ++index) {
        const auto role = static_cast<NvmeQueueBundle::Role>(index);
        const auto direction = index == 0 || index == 2 ? NvmeQueueBundle::Direction::device_reads
                                                       : NvmeQueueBundle::Direction::device_writes;
        if (!nvme_pages->ready(*handle, authority, current, role, direction))
            return false;
    }
    for (std::size_t at = 0; at < bytes; ++at)
        if (data[at] != std::byte{0})
            return false;
    Serial::text("AURORA_NVME_PREPARED: pages=5 bytes=20480 generation=1 unpublished=1\r\n");
    for (std::size_t at = 0; at < bytes; ++at)
        data[at] = std::byte{0x5a};
    if (!nvme_pages->cancel(*handle) || nvme_pages->cancel(*handle)
        || nvme_pages->held_pages() != 0 || pool.used() != 0)
        return false;
    for (std::size_t at = 0; at < bytes; ++at)
        if (data[at] != std::byte{0})
            return false;
    Serial::text("AURORA_NVME_CANCELLED: pages=0 pool=0 scrubbed=20480\r\n");
    return true;
}
