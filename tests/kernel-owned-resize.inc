// Included inside the existing real-kernel-adapter host test namespace.
using aurora::hosted::bytes::__au_runtime_bytes_resize;
static_assert(noexcept(__au_runtime_bytes_resize(nullptr, 0)));

void require_resize_inert(
    Fixture &fixture, NativeOwner &owner, std::int64_t length, bool expected, const char *message) {
    const auto before = owner;
    const auto metrics = fixture.region.metrics();
    const auto backing = fixture.arena.backing;
    const auto used = fixture.arena.pool.used();
    require(__au_runtime_bytes_resize(&owner, length) == static_cast<std::uint64_t>(expected) &&
                same_owner(owner, before) && fixture.region.metrics() == metrics && fixture.arena.backing == backing &&
                fixture.arena.pool.used() == used && !fixture.region.faulted() && fixture.region.is_open() &&
                fixture.region.preparing_records_for_test() == 0 && fixture.region.retained_records_for_test() == 0 &&
                fixture.region.inactive_records_clean_for_test(),
            message);
}

// Exhaustion is permanent, so these positive cases run in forked processes.
// Unlike the fail-stop observer, an ordinary successful case must return and
// destroy its fixtures before the child exits. Unexpected faults cannot pass.
template <typename Action> void isolated_resize_case(const char *label, Action action) {
    std::fflush(nullptr);
    const pid_t child = fork();
    require(child >= 0, "fork isolated resize success case");
    if (child == 0) {
        alarm(10);
        fault_observation = FaultObservation{};
        action();
        std::_Exit(0);
    }
    int status = 0;
    pid_t waited;
    do {
        waited = waitpid(child, &status, 0);
    } while (waited < 0 && errno == EINTR);
    require(waited == child, "reap isolated resize success case");
    if (!WIFEXITED(status) || WEXITSTATUS(status) != 0) {
        std::fprintf(stderr, "FAIL kernel owned bytes resize %s: status=%d\n", label, status);
        std::exit(1);
    }
    ++checks;
    std::printf("PASS kernel owned bytes resize: %s\n", label);
}

void resize_live_hygiene() {
    for (const std::int64_t old_length : {0, 1, 4095, 4096, 4097, 8193}) {
        for (const std::int64_t length : {0, 1, 4095, 4096, 4097, 8193}) {
            if (old_length == length) {
                continue;
            }
            Fixture fixture;
            NativeOwner owner;
            __au_runtime_bytes_allocate(fixture.region.id(), old_length, &owner);
            const auto old_pages = static_cast<std::size_t>((old_length + page_bytes - 1) / page_bytes);
            const auto new_pages = static_cast<std::size_t>((length + page_bytes - 1) / page_bytes);
            // Deliberately dirty even the old padding. It must neither be
            // copied into the extension nor survive retirement.
            std::fill(
                fixture.arena.backing.begin(), fixture.arena.backing.begin() + old_pages * page_bytes, std::byte{0x6d});
            for (std::int64_t i = 0; i < old_length; ++i) {
                require(__au_runtime_bytes_set(&owner, i, static_cast<std::uint64_t>(i % 251 + 1)),
                        "seed independent live-hygiene prefix");
            }
            const auto old_id = owner.allocation;
            require(__au_runtime_bytes_resize(&owner, length), "live-hygiene resize succeeds");
            require(owner.allocation == old_id + 1, "replacement commits exactly the next identity");
            require(fixture.region.preparing_records_for_test() == 0 &&
                        fixture.region.inactive_records_clean_for_test(),
                    "successful resize clears every retired metadata field and lease optional");
            for (std::size_t offset = 0; offset < arena_bytes; ++offset) {
                std::byte expected{0xa5};
                if (offset < old_pages * page_bytes) {
                    expected = std::byte{0};
                } else if (offset < (old_pages + new_pages) * page_bytes) {
                    const auto logical = offset - old_pages * page_bytes;
                    expected = logical < static_cast<std::size_t>(std::min(old_length, length))
                                   ? std::byte{static_cast<unsigned char>(logical % 251 + 1)}
                                   : std::byte{0};
                }
                require(
                    fixture.arena.backing[offset] == expected,
                    "before drop: retired pages zero, live prefix exact, extension/padding zero, free pages untouched");
            }
            require_resize_inert(fixture, owner, length, true, "same-size leaves the complete live arena untouched");
            __au_runtime_bytes_drop(&owner);
        }
    }
}

void resize_quota_peers() {
    Fixture fixture(8193);
    NativeOwner owner, peer;
    __au_runtime_bytes_allocate(fixture.region.id(), 4096, &owner);
    __au_runtime_bytes_allocate(fixture.region.id(), 65, &peer);
    require(__au_runtime_bytes_set(&owner, 4095, 191) && __au_runtime_bytes_set(&peer, 64, 211),
            "seed resizing and unrelated owners");
    const auto old = owner;
    const auto unchanged_peer = peer;
    require_resize_inert(fixture, owner, 8129, false, "final quota includes unrelated committed payload");
    require(__au_runtime_bytes_resize(&owner, 8128), "final-quota equality succeeds while old and new coexist");
    auto expected = Metrics{};
    expected.quota = 8193;
    expected.used = expected.peak_used = 8193;
    expected.live_allocations = expected.peak_live_allocations = 2;
    expected.successful_allocations = 3;
    expected.releases = 1;
    expected.last_allocation_id = owner.allocation;
    expected.last_released_id = old.allocation;
    expected.held_pages = 3;
    expected.peak_held_pages = 4;
    require(fixture.region.metrics() == expected && same_owner(peer, unchanged_peer) &&
                __au_runtime_bytes_at(&peer, 64) == 211 && __au_runtime_bytes_at(&owner, 4095) == 191,
            "replacement commits exact metrics without charging a temporary logical owner");
    require(owner.allocation == peer.allocation + 1, "quota failure did not consume the next identity");
    require_resize_inert(fixture, owner, 8129, false, "full quota leaves peer and resized owner untouched");
    __au_runtime_bytes_drop(&owner);
    require(__au_runtime_bytes_at(&peer, 64) == 211, "peer remains usable after resized owner drops");
    __au_runtime_bytes_drop(&peer);

    Fixture rounded(2, default_base + arena_bytes);
    NativeOwner first, second;
    __au_runtime_bytes_allocate(rounded.region.id(), 1, &first);
    __au_runtime_bytes_allocate(rounded.region.id(), 1, &second);
    require(__au_runtime_bytes_resize(&first, 0) && __au_runtime_bytes_resize(&first, 1),
            "one-byte final quota can require independent complete pages");
    require(rounded.region.metrics().used == 2 && rounded.region.metrics().held_pages == 2 &&
                rounded.region.metrics().peak_held_pages == 2 && rounded.region.metrics().peak_used == 2,
            "logical bytes and actual held pages have independent units");
    __au_runtime_bytes_drop(&first);
    __au_runtime_bytes_drop(&second);
}

void resize_boundaries() {
    for (const std::int64_t old_length : {0, 1, 65, 4095, 4096, 4097}) {
        for (const std::int64_t length : {0, 1, 65, 4095, 4096, 4097}) {
            Fixture fixture(8194);
            NativeOwner owner;
            __au_runtime_bytes_allocate(fixture.region.id(), old_length, &owner);
            for (std::int64_t i = 0; i < old_length; ++i) {
                require(__au_runtime_bytes_set(&owner, i, static_cast<std::uint64_t>(i % 251 + 1)), "seed prefix");
            }
            const auto before = owner;
            const auto metrics = fixture.region.metrics();
            require(__au_runtime_bytes_resize(&owner, length) == 1, "bounded resize succeeds");
            require_live(owner, fixture.region, length);
            require((owner.allocation == before.allocation) == (old_length == length), "replacement identity exact");
            if (old_length == length) {
                require(fixture.region.metrics() == metrics, "same-size is completely inert");
            } else {
                const auto state = fixture.region.metrics();
                require(state.live_allocations == 1 && state.used == static_cast<std::uint64_t>(length) &&
                            state.successful_allocations == 2 && state.releases == 1 &&
                            state.last_released_id == before.allocation && state.last_allocation_id == owner.allocation,
                        "replacement final accounting");
                const auto pages = [](std::int64_t n) {
                    return (static_cast<std::uint64_t>(n) + page_bytes - 1) / page_bytes;
                };
                require(state.held_pages == pages(length) && state.peak_held_pages == pages(old_length) + pages(length),
                        "physical peak includes successful staging");
            }
            for (std::int64_t i = 0; i < length; ++i) {
                require(__au_runtime_bytes_at(&owner, i) ==
                            (i < old_length ? static_cast<std::uint64_t>(i % 251 + 1) : 0),
                        "full prefix and zero extension");
            }
            __au_runtime_bytes_drop(&owner);
            require(fixture.region.metrics().used == 0 && fixture.region.metrics().held_pages == 0 &&
                        fixture.region.metrics().successful_allocations == fixture.region.metrics().releases,
                    "resize normal cleanup exact");
        }
    }
    Fixture fixture(4097);
    NativeOwner owner;
    __au_runtime_bytes_allocate(fixture.region.id(), 4096, &owner);
    require(__au_runtime_bytes_set(&owner, 4095, 79), "seed discarded byte");
    require(__au_runtime_bytes_resize(&owner, 4097), "final quota, not old-plus-new quota");
    require(__au_runtime_bytes_resize(&owner, 1) && __au_runtime_bytes_resize(&owner, 4097), "shrink and regrow");
    for (std::int64_t i = 1; i < 4097; ++i) {
        require(__au_runtime_bytes_at(&owner, i) == 0, "discarded suffix never revives");
    }
    for (const auto length : {std::int64_t{-1}, std::int64_t{4098}, INT64_MAX}) {
        const auto before = owner;
        const auto metrics = fixture.region.metrics();
        require(!__au_runtime_bytes_resize(&owner, length) && same_owner(owner, before) &&
                    fixture.region.metrics() == metrics,
                "invalid and quota requests preserve committed state");
    }
    NativeOwner failed;
    __au_runtime_bytes_allocate(fixture.region.id(), -1, &failed);
    const auto before = failed;
    for (const auto length : {std::int64_t{-1}, std::int64_t{0}, std::int64_t{1}, INT64_MAX}) {
        require_resize_inert(fixture, failed, length, false, "canonical failed owner is inert for every request");
        require(same_owner(failed, before), "failed owner never revived");
    }
    __au_runtime_bytes_drop(&failed);
    __au_runtime_bytes_drop(&owner);
}

void resize_identity_ceilings() {
    for (const std::int64_t length : {0, 4097}) {
        isolated_resize_case("last allocation identity commits only after successful replacement", [length] {
            aurora::kernel::bytes::testing::advance_next_ids(UINT64_MAX - 1, UINT64_MAX - 1);
            Fixture fixture;
            NativeOwner owner;
            __au_runtime_bytes_allocate(fixture.region.id(), 1, &owner);
            require(owner.allocation == UINT64_MAX - 1 && __au_runtime_bytes_set(&owner, 0, 229),
                    "penultimate identity belongs to seeded old owner");
            require_resize_inert(fixture, owner, -1, false, "negative request cannot consume the final identity");
            require_resize_inert(
                fixture, owner, arena_bytes + 1, false, "quota refusal cannot consume the final identity");
            require_resize_inert(fixture, owner, 1, true, "same-size cannot consume the final identity");
            Leases holders;
            for (std::size_t i = 0; i < pool_pages - 3; ++i) {
                hold(fixture.arena, holders[i]);
            }
            const auto before = owner;
            const auto metrics = fixture.region.metrics();
            require(!__au_runtime_bytes_resize(&owner, 8193) && same_owner(owner, before) &&
                        fixture.region.metrics() == metrics && fixture.arena.pool.used() == pool_pages - 2 &&
                        __au_runtime_bytes_at(&owner, 0) == 229,
                    "partial rollback leaves the final allocation identity uncommitted");
            release_holders(fixture.arena, holders);
            require(__au_runtime_bytes_resize(&owner, length) && owner.allocation == UINT64_MAX,
                    "replacement can commit the exact maximum allocation identity");
            require_live(owner, fixture.region, length);
            require(fixture.region.metrics().successful_allocations == 2 && fixture.region.metrics().releases == 1 &&
                        fixture.region.metrics().last_released_id == UINT64_MAX - 1 &&
                        fixture.region.metrics().last_allocation_id == UINT64_MAX,
                    "maximum-ID replacement commits exact observations");
            if (length != 0) {
                require(__au_runtime_bytes_at(&owner, 0) == 229, "maximum-ID replacement preserves prefix");
            }
            require_resize_inert(
                fixture, owner, length, true, "same-size remains inert after replacement exhausts IDs");
            for (const std::int64_t changed : {0, 1, 4097}) {
                if (changed != length) {
                    require_resize_inert(
                        fixture, owner, changed, false, "exhausted IDs reject shrink, zero and growth before staging");
                }
            }
            __au_runtime_bytes_drop(&owner);
            require(fixture.region.metrics().releases == 2 && fixture.region.metrics().last_released_id == UINT64_MAX,
                    "maximum-ID replacement remains normally droppable");
        });
    }
}

void resize_counter_ceilings() {
    for (const std::int64_t length : {0, 4097}) {
        Fixture fixture;
        NativeOwner owner, peer;
        __au_runtime_bytes_allocate(fixture.region.id(), 1, &owner);
        __au_runtime_bytes_allocate(fixture.region.id(), 1, &peer);
        require(__au_runtime_bytes_set(&owner, 0, 227) && __au_runtime_bytes_set(&peer, 0, 223),
                "seed counter-ceiling transaction and peer");
        require(!fixture.region.advance_counters_for_test(UINT64_MAX, UINT64_MAX),
                "counter hook rejects an inconsistent live-owner difference");
        require(fixture.region.advance_counters_for_test(UINT64_MAX - 1, UINT64_MAX - 3),
                "counter hook skips forward preserving both committed owners");
        require(!fixture.region.advance_counters_for_test(UINT64_MAX - 2, UINT64_MAX - 4),
                "counter hook cannot rewind observations");
        require_resize_inert(fixture, owner, 1, true, "near-exhausted counters do not affect validated same-size");
        require_resize_inert(fixture, owner, -1, false, "invalid length leaves near-maximum counters unchanged");
        require_resize_inert(fixture, owner, arena_bytes, false, "peer-aware quota failure leaves counters unchanged");
        const auto before = owner;
        const auto unchanged_peer = peer;
        require(__au_runtime_bytes_resize(&owner, length), "last representable successful-allocation count commits");
        require(fixture.region.metrics().successful_allocations == UINT64_MAX &&
                    fixture.region.metrics().releases == UINT64_MAX - 2 &&
                    fixture.region.metrics().live_allocations == 2 &&
                    fixture.region.metrics().last_allocation_id == owner.allocation &&
                    fixture.region.metrics().last_released_id == before.allocation &&
                    owner.allocation == peer.allocation + 1 && same_owner(peer, unchanged_peer) &&
                    __au_runtime_bytes_at(&peer, 0) == 223,
                "counter-ceiling commit preserves peer and exact accounting without wrap");
        for (const std::int64_t changed : {0, 1, 4097}) {
            require_resize_inert(fixture,
                                 owner,
                                 changed,
                                 changed == length,
                                 "exhausted successful-allocation counter permits only same-size");
        }
        __au_runtime_bytes_drop(&owner);
        require(fixture.region.metrics().releases == UINT64_MAX - 1 && fixture.region.metrics().live_allocations == 1 &&
                    __au_runtime_bytes_at(&peer, 0) == 223,
                "counter-exhausted resized owner drops without releasing its peer");
        __au_runtime_bytes_drop(&peer);
        require(fixture.region.metrics().successful_allocations == UINT64_MAX &&
                    fixture.region.metrics().releases == UINT64_MAX && fixture.region.metrics().live_allocations == 0,
                "maximum release count is reached exactly on the final normal cleanup");
    }
}

void resize_resource_failures() {
    resize_identity_ceilings();
    resize_counter_ceilings();
    {
        Fixture fixture;
        std::array<NativeOwner, 4> owners{};
        for (auto &owner : owners) {
            __au_runtime_bytes_allocate(fixture.region.id(), 1, &owner);
        }
        const auto before = owners[0];
        const auto metrics = fixture.region.metrics();
        require(__au_runtime_bytes_resize(&owners[0], 1), "same-size succeeds with four occupied records");
        for (const auto length : {0, 2}) {
            require_resize_inert(
                fixture, owners[0], length, false, "metadata exhaustion fails without backing mutation");
        }
        require(same_owner(owners[0], before) && fixture.region.metrics() == metrics,
                "metadata refusal leaves committed owner observations exact");
        for (auto &owner : owners) {
            __au_runtime_bytes_drop(&owner);
        }
    }
    // Every possible partial acquisition prefix, including a completely full pool.
    for (std::size_t available = 0; available < pool_pages - 1; ++available) {
        Fixture fixture;
        NativeOwner owner;
        __au_runtime_bytes_allocate(fixture.region.id(), 1, &owner);
        require(__au_runtime_bytes_set(&owner, 0, 197), "old payload sentinel");
        Leases holders;
        const auto held = pool_pages - 1 - available;
        for (std::size_t i = 0; i < held; ++i) {
            hold(fixture.arena, holders[i]);
        }
        const auto before = owner;
        const auto metrics = fixture.region.metrics();
        require(!__au_runtime_bytes_resize(&owner, static_cast<std::int64_t>((available + 1) * page_bytes)),
                "insufficient transient physical headroom fails");
        require(same_owner(owner, before) && fixture.region.metrics() == metrics &&
                    __au_runtime_bytes_at(&owner, 0) == 197 && fixture.arena.pool.used() == held + 1 &&
                    fixture.region.preparing_records_for_test() == 0 &&
                    fixture.region.inactive_records_clean_for_test(),
                "rollback leaves old payload/accounting intact and clears all private staging metadata");
        for (std::size_t i = 0; i < held; ++i) {
            require(fixture.arena.pool.address(*holders[i]) == fixture.arena.base + (i + 1) * page_bytes &&
                        bytes_are(fixture.arena.page(i + 1), std::byte{0xa5}),
                    "foreign holder bytes and identity unchanged");
        }
        for (std::size_t i = held + 1; i < pool_pages; ++i) {
            require(bytes_are(fixture.arena.page(i), std::byte{0}), "every rolled-back page fully scrubbed");
        }
        release_holders(fixture.arena, holders);
        require(__au_runtime_bytes_resize(&owner, 4097) && owner.allocation == before.allocation + 1,
                "staging record reusable after rollback without burning allocation identity");
        __au_runtime_bytes_drop(&owner);
        // All four records reusable, not just the slot found first by resize.
        std::array<NativeOwner, 4> empties{};
        for (auto &empty : empties) {
            __au_runtime_bytes_allocate(fixture.region.id(), 0, &empty);
            require_live(empty, fixture.region, 0);
        }
        for (auto &empty : empties) {
            __au_runtime_bytes_drop(&empty);
        }
    }
    Fixture fixture;
    NativeOwner owner;
    __au_runtime_bytes_allocate(fixture.region.id(), arena_bytes, &owner);
    const auto before = owner;
    const auto metrics = fixture.region.metrics();
    require_resize_inert(fixture, owner, arena_bytes, true, "same-size succeeds with no free physical pages");
    require(!__au_runtime_bytes_resize(&owner, 1) && same_owner(owner, before) && fixture.region.metrics() == metrics,
            "full-pool shrink needs replacement page");
    require(__au_runtime_bytes_resize(&owner, 0), "zero replacement needs metadata but no page");
    __au_runtime_bytes_drop(&owner);
    require(bytes_are(fixture.arena.backing, std::byte{0}), "entire retired pool scrubbed");
}

void resize_fragmentation() {
    Fixture fixture;
    Leases holders;
    for (auto &holder : holders) {
        hold(fixture.arena, holder);
    }
    for (std::size_t i = 1; i < pool_pages; i += 2) {
        require(fixture.arena.pool.release(*holders[i]), "free odd page");
    }
    NativeOwner owner;
    __au_runtime_bytes_allocate(fixture.region.id(), 4097, &owner); // pages 1,3
    for (std::int64_t i = 0; i < 4097; ++i) {
        require(__au_runtime_bytes_set(&owner, i, static_cast<std::uint64_t>(i % 251)), "fragment prefix seed");
    }
    require(__au_runtime_bytes_resize(&owner, 8193), "fragmented replacement on pages 5,7,9");
    for (std::int64_t i = 0; i < 8193; ++i) {
        require(__au_runtime_bytes_at(&owner, i) == (i < 4097 ? static_cast<std::uint64_t>(i % 251) : 0),
                "fragmented full prefix/extension");
    }
    __au_runtime_bytes_drop(&owner);
    for (std::size_t i = 0; i < pool_pages; ++i) {
        const bool touched = i == 1 || i == 3 || i == 5 || i == 7 || i == 9;
        require(bytes_are(fixture.arena.page(i), touched ? std::byte{0} : std::byte{0xa5}),
                "all padding scrubbed, neighbors untouched");
        if (i % 2 == 0) {
            require(fixture.arena.pool.address(*holders[i]) == fixture.arena.base + i * page_bytes,
                    "foreign lease survives resize");
        }
    }
    release_holders(fixture.arena, holders);
}

void resize_descriptor_faults() {
    for (const auto request : {-1, 0, 1, 2}) {
        for (int variant = 0; variant < 14; ++variant) {
            expect_fault("resize validates every descriptor before shortcut", 1, [request, variant] {
                Fixture fixture;
                NativeOwner owner;
                __au_runtime_bytes_allocate(fixture.region.id(), 1, &owner);
                NativeOwner bad = owner;
                if (variant == 0) {
                    bad.success = 2;
                }
                if (variant == 1) {
                    bad.length = -1;
                }
                if (variant == 2) {
                    bad.length = 0;
                }
                if (variant == 3) {
                    bad.allocation = 0;
                }
                if (variant == 4) {
                    bad.region = 0;
                }
                if (variant == 5) {
                    bad.success = 0;
                }
                if (variant == 6) {
                    require(__au_runtime_bytes_resize(&owner, 2) && __au_runtime_bytes_resize(&owner, 1),
                            "cycle length with fresh identities");
                }
                if (variant == 7) {
                    __au_runtime_bytes_drop(&owner);
                    require(fixture.region.close() &&
                                fixture.region.open(
                                    fixture.arena.pool, fixture.arena.backing, fixture.arena.base, arena_bytes),
                            "reopen grant");
                }
                if (variant == 8) {
                    __au_runtime_bytes_drop(&owner);
                }
                if (variant == 9) {
                    bad.length = 2;
                }
                if (variant == 10) {
                    bad.allocation = UINT64_MAX;
                }
                if (variant == 11) {
                    bad.success = UINT64_MAX;
                }
                if (variant == 12) {
                    bad = NativeOwner{};
                }
                if (variant == 13) {
                    bad = NativeOwner{fixture.region.id(), 0, 1, 0};
                }
                fault_observation.immutable(fixture, &bad);
                fault_observation.other_owner = &owner;
                fault_observation.expected_other = owner;
                static_cast<void>(__au_runtime_bytes_resize(&bad, request));
            });
        }
    }
    expect_fault("resize null descriptor", 1, [] {
        static_cast<void>(__au_runtime_bytes_resize(nullptr, 0));
    });
    for (const auto request : {-1, 0, 1, 2}) {
        for (const bool swap_region : {false, true}) {
            expect_fault("resize foreign authority precedes every request shortcut", 1, [request, swap_region] {
                Fixture fixture;
                Fixture other(arena_bytes, default_base + arena_bytes);
                NativeOwner owner, foreign;
                __au_runtime_bytes_allocate(fixture.region.id(), 1, &owner);
                __au_runtime_bytes_allocate(other.region.id(), 1, &foreign);
                NativeOwner bad = owner;
                if (swap_region) {
                    bad.region = foreign.region;
                } else {
                    bad.allocation = foreign.allocation;
                }
                fault_observation.immutable(swap_region ? other : fixture, &bad);
                fault_observation.other_owner = &foreign;
                fault_observation.expected_other = foreign;
                static_cast<void>(__au_runtime_bytes_resize(&bad, request));
            });
        }
        for (const bool reopen : {false, true}) {
            expect_fault(
                "failed descriptor still validates closed/reopened grant before returning false", 1, [request, reopen] {
                    Fixture fixture;
                    NativeOwner failed;
                    __au_runtime_bytes_allocate(fixture.region.id(), -1, &failed);
                    require(fixture.region.close(), "close grant with no committed owners");
                    if (reopen) {
                        require(fixture.region.open(
                                    fixture.arena.pool, fixture.arena.backing, fixture.arena.base, arena_bytes),
                                "failed descriptor does not inherit reopened authority");
                    }
                    fault_observation.immutable(fixture, &failed);
                    static_cast<void>(__au_runtime_bytes_resize(&failed, request));
                });
        }
    }
    for (int operation = 0; operation < 4; ++operation) {
        expect_fault("pre-resize descriptor rejected by every old operation", 1, [operation] {
            Fixture fixture;
            NativeOwner owner;
            __au_runtime_bytes_allocate(fixture.region.id(), 1, &owner);
            NativeOwner stale = owner;
            require(__au_runtime_bytes_resize(&owner, 2) && __au_runtime_bytes_resize(&owner, 1),
                    "same old length cannot revive descriptor");
            fault_observation.immutable(fixture, &stale);
            if (operation == 0) {
                static_cast<void>(__au_runtime_bytes_at(&stale, 0));
            }
            if (operation == 1) {
                static_cast<void>(__au_runtime_bytes_set(&stale, 0, 1));
            }
            if (operation == 2) {
                static_cast<void>(__au_runtime_bytes_borrow_length(&stale));
            }
            if (operation == 3) {
                __au_runtime_bytes_drop(&stale);
            }
        });
    }
}

void resize_retention_case(
    int phase, std::int64_t old_length, std::int64_t length, std::size_t available, std::size_t ordinal) {
    char label[160];
    std::snprintf(label,
                  sizeof(label),
                  "resize retains exactly two records phase %d old %lld new %lld available %zu ordinal %zu",
                  phase,
                  static_cast<long long>(old_length),
                  static_cast<long long>(length),
                  available,
                  ordinal);
    expect_fault(label, 3, [phase, old_length, length, available, ordinal] {
        Fixture fixture;
        NativeOwner owner, peer;
        __au_runtime_bytes_allocate(fixture.region.id(), old_length, &owner);
        const auto old_pages = static_cast<std::size_t>((old_length + page_bytes - 1) / page_bytes);
        const auto required = static_cast<std::size_t>((length + page_bytes - 1) / page_bytes);
        for (std::int64_t i = 0; i < old_length; ++i) {
            require(__au_runtime_bytes_set(&owner, i, static_cast<std::uint64_t>(i % 251 + 1)),
                    "seed every old byte before terminal transaction");
        }
        // A separate live owner is never part of the resize transaction.
        __au_runtime_bytes_allocate(fixture.region.id(), 1, &peer);
        require(__au_runtime_bytes_set(&peer, 0, 223), "seed unrelated live owner during retained transaction");
        Leases holders;
        const auto held = phase == 2 ? pool_pages - old_pages - 1 - available : std::size_t{1};
        require(held != 0, "every terminal case includes an independent physical lease");
        for (std::size_t i = 0; i < held; ++i) {
            hold(fixture.arena, holders[i]);
        }
        const auto acquired = phase == 2 ? available : required;
        const auto first_staged = old_pages + 1 + held;
        require(first_staged + acquired <= pool_pages && (phase == 1 ? ordinal < old_pages : ordinal < acquired),
                "terminal oracle stays inside exact old/staging lease sequences");
        fault_observation.immutable(fixture, &owner);
        fault_observation.mode = FaultObservation::Mode::retained;
        fault_observation.retained_records = 2;
        fault_observation.metrics.held_pages += acquired;
        fault_observation.metrics.retained_pages = old_pages + acquired;
        fault_observation.pool_used += acquired;
        fault_observation.other_owner = &peer;
        fault_observation.expected_other = peer;
        fault_observation.foreign_lease = &*holders[0];
        fault_observation.foreign_address = fixture.arena.pool.address(*holders[0]);
        if (phase == 1) {
            // Before retirement, every replacement page was zeroed and exactly
            // min(old,new) logical bytes were copied. Old padding is not copied.
            std::fill(fault_observation.backing.begin() + first_staged * page_bytes,
                      fault_observation.backing.begin() + (first_staged + acquired) * page_bytes,
                      std::byte{0});
            for (std::size_t i = 0; i < static_cast<std::size_t>(std::min(old_length, length)); ++i) {
                fault_observation.backing[first_staged * page_bytes + i] =
                    std::byte{static_cast<unsigned char>(i % 251 + 1)};
            }
        }
        const auto first_scrubbed = phase == 1 ? std::size_t{0} : first_staged;
        std::fill(fault_observation.backing.begin() + first_scrubbed * page_bytes,
                  fault_observation.backing.begin() + (first_scrubbed + ordinal + 1) * page_bytes,
                  std::byte{0});
        fault_observation.backing[(first_scrubbed + ordinal + 1) * page_bytes - 1] = std::byte{1};
        fixture.region.fail_scrub_for_test(ordinal, phase == 1 ? 1 : 0);
        static_cast<void>(__au_runtime_bytes_resize(&owner, length));
    });
}

void resize_retention() {
    // An empty old owner still owns its transaction record when replacement
    // initialization or rollback fails. Page totals alone cannot prove this.
    for (const std::int64_t old_length : {0, 4097}) {
        for (std::size_t ordinal = 0; ordinal < 3; ++ordinal) {
            resize_retention_case(0, old_length, 8193, 0, ordinal);
        }
        const auto old_pages = static_cast<std::size_t>((old_length + page_bytes - 1) / page_bytes);
        // Cover every nonempty acquired prefix and every failed page in it.
        // One other live owner and at least one foreign lease stay untouched.
        for (std::size_t available = 1; available < pool_pages - old_pages - 1; ++available) {
            const auto length = static_cast<std::int64_t>((available + 1) * page_bytes);
            for (std::size_t ordinal = 0; ordinal < available; ++ordinal) {
                resize_retention_case(2, old_length, length, available, ordinal);
            }
        }
    }
    // A zero-length replacement must retain its metadata even though it has no
    // lease; all old pages must stay retained if retirement readback fails.
    for (const std::int64_t length : {0, 1, 4097}) {
        for (std::size_t ordinal = 0; ordinal < 3; ++ordinal) {
            resize_retention_case(1, 8193, length, 0, ordinal);
        }
    }
}
