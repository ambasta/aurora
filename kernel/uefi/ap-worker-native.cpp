#include "ap-worker-native.hpp"

namespace aurora::uefi {
extern auto enter() -> void asm("ap_worker_enter") __attribute__((visibility("hidden")));
class ChecksumResult final {
public:
    std::uint64_t status, value;
};
extern auto helper(ChecksumResult *, const std::byte *, std::int64_t, std::int64_t, std::int64_t)
    -> void asm("__au_runtime_ap_worker_crc32c") __attribute__((visibility("hidden")));
namespace {
using U64 = std::uint64_t;
using U32 = std::uint32_t;
using L = ApWorkerLayout;
constexpr U64 address_mask = 0x000ffffffffff000ULL;
constexpr U64 accessed_dirty = 0x60;
constexpr U32 wait_limit = 3'579'546;  // One second plus one PM counter phase.
constexpr U64 poll_limit = 50'000'000; // Exhaustion is refusal, never elapsed-time evidence.
constexpr U64 state_ready = 1, state_done = 2, state_fault = 3;
class alignas(64) Request final {
public:
    U64 publication, closed, incarnation, apic, bsp, root, stack_bottom, stack_top, reply, apic_base, pat, fixture;
    std::int64_t start, count;
    U64 payload, release;
};
class alignas(64) Reply final {
public:
    U64 state, apic, incarnation, sequence;
    std::int64_t result;
    U64 root, stack, apic_base, vector, error, rip, cr2, trap_guard;
    U64 started;
};
static_assert(offsetof(Reply, vector) == 64 && offsetof(Reply, cr2) == 88 && offsetof(Reply, trap_guard) == 96);
static_assert(__atomic_always_lock_free(sizeof(U64), nullptr));
extern const std::byte text_begin asm("__ap_worker_text_begin");
extern const std::byte text_end asm("__ap_worker_text_end");
extern const std::byte start_begin asm("ap_worker_start_begin");
extern const std::byte start_end asm("ap_worker_start_end");
extern const std::byte start_gdt asm("ap_worker_start_gdt");
extern const std::byte start_gdtr asm("ap_worker_start_gdtr");
extern const std::byte start_far32 asm("ap_worker_start_far32");
extern const std::byte start_far64 asm("ap_worker_start_far64");
extern const std::byte start_protected asm("ap_worker_start_protected");
extern const std::byte start_long asm("ap_worker_start_long");
extern const std::byte start_parameters asm("ap_worker_start_parameters");
extern const std::int32_t vector_offsets[256] asm("ap_worker_vector_offsets");
auto address(const void *p) -> U64 {
    return reinterpret_cast<U64>(p);
}
auto request(U64 block) -> Request & {
    return *reinterpret_cast<Request *>(block + L::request);
}
auto reply(U64 block) -> const Reply & {
    return *reinterpret_cast<const Reply *>(block + L::reply);
}
auto store(std::byte *p, U64 value, unsigned n) -> void {
    for (unsigned i = 0; i < n; ++i)
        p[i] = std::byte((value >> (8 * i)) & 255);
}
auto read_msr(U32 index) -> U64 {
    U32 low, high;
    asm volatile("rdmsr" : "=a"(low), "=d"(high) : "c"(index));
    return (U64(high) << 32) | low;
}
auto read_root() -> U64 {
    U64 value;
    asm volatile("mov %%cr3,%0" : "=r"(value));
    return value;
}
auto write_protected() -> bool {
    U64 value;
    asm volatile("mov %%cr0,%0" : "=r"(value));
    return (value & 0x10000) != 0;
}
auto overlap(U64 a, U64 n, U64 b, U64 m) -> bool {
    return a < b + m && b < a + n;
}
auto expected_leaf(U64 block, U64 low, U64 va, bool startup) -> U64 {
    if (va >= address(&text_begin) && va < address(&text_end))
        return va | 1;
    if (startup && va == low)
        return va | 1;
    if (va == block + L::request || va == block + L::idt || va == block + L::payload)
        return va | 1 | L::nx;
    if (va == block + L::reply || va == block + L::descriptors ||
        (va >= block + L::stack_bottom && va < block + L::stack_top) ||
        (va >= block + L::ist_bottom && va < block + L::ist_top))
        return va | 3 | L::nx;
    return 0;
}
auto map_page(U64 base, unsigned &used, U64 va, U64 leaf) -> bool {
    auto table = base;
    for (const auto shift : {39U, 30U, 21U}) {
        auto &link = reinterpret_cast<U64 *>(table)[(va >> shift) & 511];
        if (!link) {
            if (used == L::table_pages)
                return false;
            link = (base + used++ * L::page) | 3;
        }
        table = link & address_mask;
        if (table < base || table >= base + used * L::page)
            return false;
    }
    auto &slot = reinterpret_cast<U64 *>(table)[(va >> 12) & 511];
    if (slot)
        return false;
    slot = leaf;
    return true;
}
auto build_root(U64 base, unsigned &used, U64 block, U64 low, bool startup) -> bool {
    used = 1;
    for (U64 code = address(&text_begin); code < address(&text_end); code += L::page)
        if (!map_page(base, used, code, code | 1))
            return false;
    if (startup && !map_page(base, used, low, low | 1))
        return false;
    for (U64 va = block; va < block + L::bytes; va += L::page)
        if (const auto leaf = expected_leaf(block, low, va, startup); leaf && !map_page(base, used, va, leaf))
            return false;
    return true;
}
auto verify_root(U64 base, unsigned used, U64 block, U64 low, bool startup) -> bool {
    if (!used || used > L::table_pages)
        return false;
    bool visited[L::table_pages]{};
    class Frame final {
    public:
        U64 table, prefix, next;
    };
    Frame frames[4]{{base, 0, 0}};
    unsigned depth = 0, leaves = 0, tables = 0;
    for (;;) {
        auto &frame = frames[depth];
        if (!frame.next) {
            if (frame.table < base || frame.table >= base + used * L::page || frame.table % L::page)
                return false;
            const auto index = (frame.table - base) / L::page;
            if (visited[index])
                return false;
            visited[index] = true;
            ++tables;
        }
        if (frame.next == 512) {
            if (!depth)
                break;
            --depth;
            continue;
        }
        const auto index = frame.next++;
        const auto entry = reinterpret_cast<const U64 *>(frame.table)[index];
        if (!entry)
            continue;
        const auto va = frame.prefix | (index << (39 - 9 * depth));
        if (depth != 3) {
            // No huge leaves, supervisor-only, and no shared/foreign ancestor.
            if ((entry & ~(address_mask | accessed_dirty)) != 3)
                return false;
            frames[++depth] = {entry & address_mask, va, 0};
        } else {
            const auto wanted = expected_leaf(block, low, va, startup);
            if (!wanted || (entry & ~accessed_dirty) != wanted)
                return false;
            ++leaves;
        }
    }
    const auto code_pages = (address(&text_end) - address(&text_begin)) / L::page;
    // request/reply/descriptors/IDT/payload + four main-stack + two IST pages.
    return tables == used && leaves == code_pages + 11 + (startup ? 1 : 0);
}
} // namespace

// The only C++ body reachable from the AP. All helper code and trap entries are
// in the same linker-delimited RX closure; build facts check this call graph.
extern "C" [[gnu::section(".text.ap_worker.main"), gnu::noinline, noreturn]]
auto ap_worker_main(const Request *input) -> void {
    auto *output = reinterpret_cast<Reply *>(input->reply);
    U32 a, b, c, d;
    asm volatile("cpuid" : "=a"(a), "=b"(b), "=c"(c), "=d"(d) : "a"(0), "c"(0));
    bool valid = a >= 1 && b == 0x756e6547 && d == 0x49656e69 && c == 0x6c65746e;
    asm volatile("cpuid" : "=a"(a), "=b"(b), "=c"(c), "=d"(d) : "a"(1), "c"(0));
    const U64 id = b >> 24;
    valid = valid && id == input->apic && id != input->bsp && ((b >> 16) & 255) == 2 &&
            (d & ((1U << 5) | (1U << 6) | (1U << 9) | (1U << 16))) == ((1U << 5) | (1U << 6) | (1U << 9) | (1U << 16));
    asm volatile("cpuid" : "=a"(a), "=b"(b), "=c"(c), "=d"(d) : "a"(0x80000000U), "c"(0));
    valid = valid && a >= 0x80000001U;
    asm volatile("cpuid" : "=a"(a), "=b"(b), "=c"(c), "=d"(d) : "a"(0x80000001U), "c"(0));
    valid = valid && (d & ((1U << 20) | (1U << 29))) == ((1U << 20) | (1U << 29));
    asm volatile("rdmsr" : "=a"(a), "=d"(d) : "c"(0x1b));
    const U64 apic_base = (U64(d) << 32) | a;
    U64 root, stack, cr0, cr4;
    asm volatile("mov %%cr3,%0; mov %%rsp,%1; mov %%cr0,%2; mov %%cr4,%3"
                 : "=r"(root), "=r"(stack), "=r"(cr0), "=r"(cr4));
    valid = valid && apic_base == input->apic_base && root == input->root && stack >= input->stack_bottom &&
            stack < input->stack_top && (cr0 & 0x80010009ULL) == 0x80010009ULL && (cr4 & 0x20) != 0;
    asm volatile("rdmsr" : "=a"(a), "=d"(d) : "c"(0x277));
    valid = valid && ((U64(d) << 32) | a) == input->pat;
    output->apic = id;
    output->incarnation = input->incarnation;
    output->root = root;
    output->stack = stack;
    output->apic_base = apic_base;
    if (!valid) {
        __atomic_store_n(&output->trap_guard, U64{1}, __ATOMIC_RELEASE);
        output->vector = 256;
        __atomic_store_n(&output->state, state_fault, __ATOMIC_RELEASE);
        for (;;)
            asm volatile("cli; hlt");
    }
    if (input->fixture == U64(ApWorkerFixture::no_readiness))
        for (;;)
            asm volatile("pause");
    __atomic_store_n(&output->state, state_ready, __ATOMIC_RELEASE);
    U64 previous = 0;
    for (;;) {
        if (__atomic_load_n(&input->closed, __ATOMIC_ACQUIRE))
            for (;;)
                asm volatile("cli; hlt");
        const auto sequence = __atomic_load_n(&input->publication, __ATOMIC_ACQUIRE);
        if (sequence == previous) {
            asm volatile("pause");
            continue;
        }
        if (!sequence || sequence != previous + 1) {
            __atomic_store_n(&output->trap_guard, U64{1}, __ATOMIC_RELEASE);
            output->vector = 257;
            __atomic_store_n(&output->state, state_fault, __ATOMIC_RELEASE);
            for (;;)
                asm volatile("cli; hlt");
        }
        // Copy bounded coordinates after acquire; the AP constructs its own invocation-only view.
        // No source owner or source loan crosses CPUs.
        const auto start = input->start, count = input->count;
        if (input->fixture == U64(ApWorkerFixture::fault))
            asm volatile("ud2");
        if (start < 0 || count < 0 || count > 1024 || start > 4096 - count ||
            input->payload != input->reply - L::reply + L::payload) {
            __atomic_store_n(&output->trap_guard, U64{1}, __ATOMIC_RELEASE);
            output->vector = 258;
            __atomic_store_n(&output->state, state_fault, __ATOMIC_RELEASE);
            for (;;)
                asm volatile("cli; hlt");
        }
        // This receipt precedes helper entry, rather than withholding a result.
        __atomic_store_n(&output->started, sequence, __ATOMIC_RELEASE);
        if (input->fixture == U64(ApWorkerFixture::overlap)) {
            U64 spins = 0;
            while (__atomic_load_n(&input->release, __ATOMIC_ACQUIRE) != sequence) {
                if (__atomic_load_n(&input->closed, __ATOMIC_ACQUIRE))
                    for (;;)
                        asm volatile("cli; hlt");
                if (++spins == poll_limit) {
                    __atomic_store_n(&output->trap_guard, U64{1}, __ATOMIC_RELEASE);
                    output->vector = 259;
                    __atomic_store_n(&output->state, state_fault, __ATOMIC_RELEASE);
                    for (;;)
                        asm volatile("cli; hlt");
                }
                asm volatile("pause");
            }
        }
        ChecksumResult result{};
        helper(&result, reinterpret_cast<const std::byte *>(input->payload), 4096, start, count);
        if (result.status != 0 || result.value > 0xffffffffULL) {
            __atomic_store_n(&output->trap_guard, U64{1}, __ATOMIC_RELEASE);
            output->vector = 260;
            __atomic_store_n(&output->state, state_fault, __ATOMIC_RELEASE);
            for (;;)
                asm volatile("cli; hlt");
        }
        if (input->fixture == U64(ApWorkerFixture::withheld))
            for (;;)
                asm volatile("pause");
        if (input->fixture == U64(ApWorkerFixture::late))
            while (!__atomic_load_n(&input->closed, __ATOMIC_ACQUIRE))
                asm volatile("pause");
        output->result = static_cast<std::int64_t>(result.value);
        previous = sequence;
        // After release no access to this job's arguments/result remains. The
        // BSP may publish new control only after this exact completion is settled.
        __atomic_store_n(&output->state,
                         input->fixture == U64(ApWorkerFixture::malformed_status) ? U64{4} : state_done,
                         __ATOMIC_RELAXED);
        __atomic_store_n(&output->sequence, sequence, __ATOMIC_RELEASE);
    }
}

auto ApWorkerNative::prepare(
    const ApWorkerAdmission &grant, const MemoryMap &map, U64 block, U64 low, U64 incarnation, ApWorkerFixture fixture)
    -> bool {
    if (prepared_ || closed_ || !incarnation || U64(fixture) > U64(ApWorkerFixture::overlap) || block % L::page ||
        block < 0x100000 || block > 0x100000000ULL - L::bytes || low % L::page || !low || low > 0xff000 ||
        !map.owns(block, L::bytes) || !map.owns(low, L::page) ||
        overlap(block, L::bytes, grant.owned_arena(), Handoff::arena_bytes) || overlap(block, L::bytes, low, L::page) ||
        address(&text_begin) % L::page || address(&text_end) % L::page || address(&text_begin) >= address(&text_end) ||
        address(&text_begin) < grant.owned_arena() + Handoff::payload_offset ||
        address(&text_end) > grant.owned_arena() + Handoff::arena_bytes ||
        address(&start_end) - address(&start_begin) > L::page || read_root() != grant.kernel_root())
        return false;
    grant_ = &grant;
    block_ = block;
    low_ = low;
    incarnation_ = incarnation;
    fixture_ = fixture;
    {
        U32 observed;
        const auto port = grant.pm_timer().port();
        asm volatile("inl %w1,%0" : "=a"(observed) : "d"(port));
        frozen_timer_ = observed & grant.pm_timer().counter_mask();
    }
    for (U64 at = 0; at < L::bytes; at += sizeof(U64))
        *reinterpret_cast<U64 *>(block + at) = 0;
    auto *low_bytes = reinterpret_cast<std::byte *>(low);
    for (U64 at = 0; at < L::page; ++at)
        low_bytes[at] = at < address(&start_end) - address(&start_begin) ? (&start_begin)[at] : std::byte{};
    auto patch = [&](const std::byte &symbol, U64 value, unsigned bytes, unsigned extra = 0) {
        store(low_bytes + address(&symbol) - address(&start_begin) + extra, value, bytes);
    };
    patch(start_gdtr, low + address(&start_gdt) - address(&start_begin), 4, 2);
    patch(start_far32, low + address(&start_protected) - address(&start_begin), 4);
    patch(start_far64, low + address(&start_long) - address(&start_begin), 4);
    auto &in = request(block);
    in.incarnation = incarnation;
    in.apic = grant.ap_id();
    in.bsp = grant.bsp_id();
    in.root = block + L::permanent;
    in.stack_bottom = block + L::stack_bottom;
    in.stack_top = block + L::stack_top;
    in.reply = block + L::reply;
    in.apic_base = ApWorkerAdmission::physical_address | 0x800;
    in.pat = read_msr(0x277);
    in.fixture = U64(fixture);
    in.payload = block + L::payload;
    // Initialized once before sealing. This backing never changes or reclaims.
    for (U64 i = 0; i < L::page; ++i)
        reinterpret_cast<std::byte *>(in.payload)[i] = std::byte((i * 37 + 11) & 255);
    // Boot-selected negative observations cannot change the actual grant/root.
    if (fixture == ApWorkerFixture::wrong_identity)
        in.apic ^= 1;
    if (fixture == ApWorkerFixture::wrong_root)
        in.root ^= L::page;
    auto *gdt = reinterpret_cast<U64 *>(block + L::descriptors);
    gdt[1] = 0x00af9b000000ffffULL;
    gdt[2] = 0x00cf93000000ffffULL;
    const auto tss = block + L::descriptors + 0x100;
    gdt[3] = 103 | ((tss & 0xffffff) << 16) | (0x89ULL << 40) | ((tss & 0xff000000) << 32);
    gdt[4] = tss >> 32;
    auto *tss_bytes = reinterpret_cast<std::byte *>(tss);
    store(tss_bytes + 4, block + L::stack_top, 8);
    store(tss_bytes + 36, block + L::ist_top, 8);
    store(tss_bytes + 102, 104, 2);
    for (unsigned vector = 0; vector != 256; ++vector) {
        const auto target = address(vector_offsets) + vector_offsets[vector];
        if (target < address(&text_begin) || target >= address(&text_end))
            return false;
        auto *descriptor = reinterpret_cast<std::byte *>(block + L::idt + vector * 16);
        store(descriptor, target, 2);
        store(descriptor + 2, 8, 2);
        store(descriptor + 4, 1, 1); // IST1 even for NMI/#DF and CPL0 exceptions.
        store(descriptor + 5, 0x8e, 1);
        store(descriptor + 6, target >> 16, 2);
        store(descriptor + 8, target >> 32, 4);
    }
    patch(start_parameters, block + L::startup, 8);
    patch(start_parameters, block + L::permanent, 8, 8);
    patch(start_parameters, block + L::stack_top, 8, 16);
    patch(start_parameters, block + L::request, 8, 24);
    patch(start_parameters, block + L::reply, 8, 32);
    patch(start_parameters, address(reinterpret_cast<const void *>(&enter)), 8, 40);
    patch(start_parameters, 39, 2, 48);
    patch(start_parameters, block + L::descriptors, 8, 50);
    patch(start_parameters, 4095, 2, 58);
    patch(start_parameters, block + L::idt, 8, 60);
    if (!build_root(block + L::startup, startup_used_, block, low, true) ||
        !build_root(block + L::permanent, permanent_used_, block, low, false))
        return false;
    prepared_ = true;
    return verify_roots();
}

auto ApWorkerNative::verify_roots() const -> bool {
    return prepared_ && verify_root(block_ + L::startup, startup_used_, block_, low_, true) &&
           verify_root(block_ + L::permanent, permanent_used_, block_, low_, false);
}

auto ApWorkerNative::bsp_leaf(U64 va) const -> U64 * {
    auto table = grant_->kernel_root();
    for (const auto shift : {39U, 30U, 21U}) {
        if (table < grant_->kernel_root() || table >= grant_->kernel_root() + Handoff::table_pages * L::page)
            return nullptr;
        const auto link = reinterpret_cast<const U64 *>(table)[(va >> shift) & 511];
        if ((link & ~(address_mask | accessed_dirty)) != 3)
            return nullptr;
        table = link & address_mask;
    }
    if (table < grant_->kernel_root() || table >= grant_->kernel_root() + Handoff::table_pages * L::page)
        return nullptr;
    return reinterpret_cast<U64 *>(table) + ((va >> 12) & 511);
}

auto ApWorkerNative::seal() -> bool {
    if (!prepared_ || sealed_ || closed_ || !verify_roots() || read_root() != grant_->kernel_root() ||
        !write_protected())
        return false;
    for (unsigned pass = 0; pass != 2; ++pass) {
        for (U64 index = 0; index <= L::bytes / L::page; ++index) {
            const auto va = index == L::bytes / L::page ? low_ : block_ + index * L::page;
            auto *leaf = bsp_leaf(va);
            if (!leaf || (*leaf & ~accessed_dirty) != (va | 3 | L::nx))
                return false;
            if (pass) {
                *leaf = va | (va == block_ + L::request ? 3 : 1) | L::nx;
                asm volatile("invlpg (%0)" ::"r"(va) : "memory");
            }
        }
    }
    sealed_ = true;
    return true;
}

auto ApWorkerNative::clock() const -> U32 {
    if (fixture_ == ApWorkerFixture::stagnant_timer)
        return frozen_timer_; // Freeze an actual observation; never claim elapsed time.
    U32 value;
    const auto port = grant_->pm_timer().port();
    asm volatile("inl %w1,%0" : "=a"(value) : "d"(port));
    return value & grant_->pm_timer().counter_mask();
}
auto ApWorkerNative::wait_ticks(U32 ticks) const -> bool {
    if (!grant_->pm_timer().bounded_ticks(ticks))
        return false;
    const auto begin = clock();
    auto previous = begin;
    unsigned stagnant = 0;
    for (U64 count = 0; count != poll_limit; ++count) {
        const auto observed = clock();
        if (observed == previous) {
            if (++stagnant == 65536)
                return false;
        } else {
            previous = observed;
            stagnant = 0;
        }
        const auto elapsed = grant_->pm_timer().delta(begin, observed);
        if (elapsed >= ticks)
            return true;
        asm volatile("pause");
    }
    return false;
}
auto ApWorkerNative::wait_icr() const -> bool {
    const auto begin = clock();
    auto *apic = reinterpret_cast<volatile U32 *>(ApWorkerAdmission::virtual_address);
    for (U64 count = 0; count != poll_limit; ++count) {
        if (!(apic[0x300 / 4] & 0x1000))
            return true;
        if (grant_->pm_timer().delta(begin, clock()) >= wait_limit)
            return false;
        asm volatile("pause");
    }
    return false;
}
auto ApWorkerNative::send_ipi(U32 command) -> bool {
    if (!wait_icr())
        return false;
    auto *apic = reinterpret_cast<volatile U32 *>(ApWorkerAdmission::virtual_address);
    apic[0x310 / 4] = grant_->ap_id() << 24;
    ipi_attempted_ = true;
    asm volatile("" ::: "memory");
    apic[0x300 / 4] = command;
    return wait_icr();
}
auto ApWorkerNative::close() -> void {
    closed_ = true;
    ready_ = false;
    if (prepared_)
        __atomic_store_n(&request(block_).closed, U64{1}, __ATOMIC_RELEASE);
}
auto ApWorkerNative::fault_or_timeout(ApWorkerStatus status) -> ApWorkerResult {
    close();
    ApWorkerResult result;
    result.status = status;
    result.apic = grant_ ? grant_->ap_id() : 0;
    result.incarnation = incarnation_;
    result.sequence = sequence_;
    if (prepared_ && status == ApWorkerStatus::fault) {
        const auto &out = reply(block_);
        result.vector = out.vector;
        result.error = out.error;
        result.rip = out.rip;
        result.cr2 = out.cr2;
    }
    return result;
}
auto ApWorkerNative::await_ready() -> ApWorkerResult {
    const auto begin = clock();
    const auto &out = reply(block_);
    for (U64 count = 0; count != poll_limit; ++count) {
        const auto state = __atomic_load_n(&out.state, __ATOMIC_ACQUIRE);
        if (state == state_fault)
            return fault_or_timeout(ApWorkerStatus::fault);
        if (state == state_ready) {
            if (out.apic != grant_->ap_id() || out.incarnation != incarnation_ || out.root != permanent_root() ||
                out.stack < block_ + L::stack_bottom || out.stack >= block_ + L::stack_top ||
                out.apic_base != (ApWorkerAdmission::physical_address | 0x800))
                return fault_or_timeout(ApWorkerStatus::rejected);
            ApWorkerResult result;
            result.status = ApWorkerStatus::ready;
            result.apic = out.apic;
            result.incarnation = out.incarnation;
            return result;
        }
        if (state != 0 || grant_->pm_timer().delta(begin, clock()) >= wait_limit)
            return fault_or_timeout(state != 0 ? ApWorkerStatus::rejected : ApWorkerStatus::timeout);
        asm volatile("pause");
    }
    return fault_or_timeout(ApWorkerStatus::timeout);
}
auto ApWorkerNative::start() -> ApWorkerResult {
    if (!prepared_ || !sealed_ || started_ || closed_ || read_root() != grant_->kernel_root() || !write_protected() ||
        !verify_roots())
        return ApWorkerResult{};
    auto *apic = reinterpret_cast<volatile U32 *>(ApWorkerAdmission::virtual_address);
    if (!grant_->matches_registers(apic[0x20 / 4], apic[0x30 / 4]) || !wait_ticks(PmTimerAdmission::ticks_200us))
        return fault_or_timeout(ApWorkerStatus::rejected);
    __atomic_thread_fence(__ATOMIC_RELEASE);
    started_ = true; // Never retry an uncertain hardware start.
    // Intel SDM 3A 8.4.4 known-count INIT/SIPI. All delays use the admitted
    // read-only PM counter; delivery-status clear is not AP completion.
    if (!send_ipi(0xc500) || !wait_ticks(PmTimerAdmission::ticks_10ms) || !send_ipi(0x8500) ||
        !send_ipi(0x600 | U32(low_ >> 12)) || !wait_ticks(PmTimerAdmission::ticks_200us))
        return fault_or_timeout(ApWorkerStatus::timeout);
    if (__atomic_load_n(&reply(block_).state, __ATOMIC_ACQUIRE) == 0 && !send_ipi(0x600 | U32(low_ >> 12)))
        return fault_or_timeout(ApWorkerStatus::timeout);
    auto result = await_ready();
    ready_ = result.status == ApWorkerStatus::ready;
    return result;
}
auto ApWorkerNative::publish(U64 incarnation, U64 sequence, std::int64_t offset, std::int64_t count) -> ApWorkerResult {
    if (!ready_ || closed_ || outstanding_ || incarnation != incarnation_ || !sequence || sequence_ == ~U64{0} ||
        sequence != sequence_ + 1 || read_root() != grant_->kernel_root() || !write_protected() || offset < 0 ||
        count < 0 || count > 1024 || offset > 4096 - count) {
        return fault_or_timeout(ApWorkerStatus::rejected);
    }
    auto &in = request(block_);
    outstanding_ = true;
    terminal_ = false;
    started_observation_ = 0;
    sequence_ = sequence;
    in.start = offset;
    in.count = count;
    previous_sample_ = clock();
    __atomic_store_n(&in.publication, sequence, __ATOMIC_RELEASE);
    ApWorkerResult result;
    result.status = ApWorkerStatus::pending;
    result.apic = grant_->ap_id();
    result.incarnation = incarnation_;
    result.sequence = sequence_;
    return result;
}
auto ApWorkerNative::progress(U64 incarnation, U64 sequence, U64 ordinal) -> ApWorkerResult {
    if (!ready_ || closed_ || !outstanding_ || terminal_ || incarnation != incarnation_ || sequence != sequence_ ||
        !ordinal || observation_ == ~U64{0} || ordinal != observation_ + 1 || read_root() != grant_->kernel_root() ||
        !write_protected())
        return fault_or_timeout(ApWorkerStatus::rejected);
    // Native tracks protocol freshness only. Source owns all work/time budgets.
    observation_ = ordinal;
    const auto &out = reply(block_);
    const auto completed = __atomic_load_n(&out.sequence, __ATOMIC_ACQUIRE);
    const auto state = __atomic_load_n(&out.state, __ATOMIC_ACQUIRE);
    const auto begun = __atomic_load_n(&out.started, __ATOMIC_ACQUIRE);
    const auto sampled = clock();
    ApWorkerResult result;
    result.ticks = grant_->pm_timer().delta(previous_sample_, sampled);
    previous_sample_ = sampled;
    result.ordinal = ordinal;
    if (state == state_fault)
        return fault_or_timeout(ApWorkerStatus::fault);
    if (out.apic != grant_->ap_id() || out.incarnation != incarnation_ || out.root != permanent_root() ||
        out.stack < block_ + L::stack_bottom || out.stack >= block_ + L::stack_top ||
        out.apic_base != (ApWorkerAdmission::physical_address | 0x800) || completed < sequence_ - 1 ||
        completed > sequence_ || begun < sequence_ - 1 || begun > sequence_ ||
        (state == state_ready && sequence_ != 1) || (completed == sequence_ && begun != sequence_) ||
        (state != state_ready && state != state_done) || (completed == sequence_ && state != state_done))
        return fault_or_timeout(ApWorkerStatus::rejected);
    result.status = completed == sequence_ ? ApWorkerStatus::done : ApWorkerStatus::pending;
    result.apic = out.apic;
    result.incarnation = out.incarnation;
    result.sequence = sequence_;
    result.started = begun == sequence_;
    if (result.started)
        started_observation_ = ordinal;
    if (result.status == ApWorkerStatus::done) {
        if (out.result < 0 || static_cast<U64>(out.result) > 0xffffffffULL)
            return fault_or_timeout(ApWorkerStatus::rejected);
        result.value = out.result;
        terminal_ = true;
    }
    return result;
}
auto ApWorkerNative::settle(U64 incarnation, U64 sequence) -> bool {
    if (closed_ || !outstanding_ || !terminal_ || incarnation != incarnation_ || sequence != sequence_ ||
        read_root() != grant_->kernel_root() || !write_protected()) {
        close();
        return false;
    }
    outstanding_ = false;
    terminal_ = false;
    return true;
}
auto ApWorkerNative::release_overlap(U64 incarnation, U64 sequence, U64 ordinal) -> bool {
    if (fixture_ != ApWorkerFixture::overlap || closed_ || !outstanding_ || terminal_ || incarnation != incarnation_ ||
        sequence != sequence_ || !ordinal || ordinal != started_observation_ || ordinal != observation_ ||
        read_root() != grant_->kernel_root() || !write_protected() ||
        __atomic_load_n(&request(block_).release, __ATOMIC_ACQUIRE) >= sequence_) {
        close();
        return false;
    }
    __atomic_store_n(&request(block_).release, sequence, __ATOMIC_RELEASE);
    return true;
}
auto ApWorkerNative::late_completion_seen() const -> bool {
    if (!closed_ || !started_)
        return false;
    const auto &out = reply(block_);
    return sequence_ != 0 && __atomic_load_n(&out.sequence, __ATOMIC_ACQUIRE) == sequence_ &&
           __atomic_load_n(&out.state, __ATOMIC_ACQUIRE) == state_done;
}
} // namespace aurora::uefi
