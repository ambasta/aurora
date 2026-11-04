#pragma once
#include <cstddef>
#include <cstdint>

namespace aurora::nvme {
using U64 = std::uint64_t;
enum class Stage : U64 {
    idle,
    reserved,
    submitted,
    completion_selected,
    poisoned
};
enum class CompletionKind : U64 {
    rejected,
    complete
};
struct Plan final {
    U64 qid{}, cid{}, sq_slot{}, new_tail{}, cq_slot{}, phase{};
};
struct Observation final {
    U64 first_last{}, result{}, reserved{}, position{}, second_last{};
};
struct Completion final {
    CompletionKind kind{};
    U64 status{}, new_cq_head{};
};
struct CompletionInput final {
    U64 qid, cid;
    Observation observation;
};
static_assert(sizeof(Observation) == 40 && sizeof(CompletionInput) == 56 &&
              offsetof(CompletionInput, observation) == 16);
// A shared predicate, not authority to select a root. Only the boot handoff or
// an authenticated process broker supplies expected_root in production.
[[nodiscard]] constexpr auto
quiet_context(U64 current_root, U64 expected_root, U64 flags, bool slot_present, U64 slot_value, bool mapped) -> bool {
    return expected_root && current_root == expected_root && (flags & 0x202) == 2 && slot_present && slot_value == 0 &&
           !mapped;
}
extern "C" {
void __au_runtime_nvme_transport_create(void *);
bool __au_runtime_nvme_transport_reserve(void *, U64, U64);
bool __au_runtime_nvme_transport_published(void *, U64, U64);
CompletionKind __au_runtime_nvme_transport_accept_completion(void *, const CompletionInput *);
bool __au_runtime_nvme_transport_acknowledged(void *, U64, U64);
bool __au_runtime_nvme_transport_poison(void *);
bool __au_runtime_nvme_transport_available(const void *, U64);
bool __au_runtime_nvme_transport_poisoned(const void *);
Stage __au_runtime_nvme_transport_stage(const void *);
U64 __au_runtime_nvme_transport_active_qid(const void *);
U64 __au_runtime_nvme_transport_active_cid(const void *);
U64 __au_runtime_nvme_transport_remaining(const void *, U64);
U64 __au_runtime_nvme_transport_next_cid(const void *, U64);
U64 __au_runtime_nvme_transport_tail(const void *, U64);
U64 __au_runtime_nvme_transport_head(const void *, U64);
U64 __au_runtime_nvme_transport_phase(const void *, U64);
U64 __au_runtime_nvme_transport_status(const void *, U64);
}
// Native owns only storage lifetime and synchronous exclusion. The compiler's
// retained-root facts admit this opaque reservation and each bridge signature.
// No borrow spans DMA access, a fence, MMIO, polling, user copying or CR3 change.
template <class Platform> class Root final {
    alignas(16) std::byte storage_[128]{};
    bool live_{};
    mutable bool borrowed_{};
    mutable U64 entered_root_{};
    static void require(bool condition) {
        if (!condition)
            Platform::fail();
    }
    [[gnu::noinline]] void enter(bool live) const {
        require(live_ == live && !borrowed_ && Platform::quiet());
        entered_root_ = Platform::context();
        borrowed_ = true;
        require(entered_root_ && Platform::quiet());
    }
    [[gnu::noinline]] void leave() const {
        require(borrowed_ && Platform::quiet() && Platform::context() == entered_root_);
        borrowed_ = false;
        entered_root_ = 0;
    }
    template <auto Entry, U64 Maximum> auto query(U64 qid) const -> U64 {
        if (!live_)
            return 0;
        enter(true);
        const auto value = Entry(storage_, qid);
        require(value <= Maximum);
        leave();
        return value;
    }

public:
    constexpr Root() = default;
    Root(const Root &) = delete;
    Root(Root &&) = delete;
    auto operator=(const Root &) -> Root & = delete;
    auto operator=(Root &&) -> Root & = delete;
    auto created() const -> bool {
        return live_;
    }
    void create() {
        enter(false);
        __au_runtime_nvme_transport_create(storage_);
        live_ = true;
        require(__au_runtime_nvme_transport_stage(storage_) == Stage::idle);
        leave();
    }
    auto available(U64 qid) const -> bool {
        if (!live_)
            return false;
        enter(true);
        const auto value = __au_runtime_nvme_transport_available(storage_, qid);
        leave();
        return value;
    }
    auto poisoned() const -> bool {
        if (!live_)
            return false;
        enter(true);
        const auto value = __au_runtime_nvme_transport_poisoned(storage_);
        leave();
        return value;
    }
    auto stage() const -> Stage {
        if (!live_)
            return Stage::idle;
        enter(true);
        const auto value = __au_runtime_nvme_transport_stage(storage_);
        require(value <= Stage::poisoned);
        leave();
        return value;
    }
    auto active_qid() const -> U64 {
        if (!live_)
            return 0;
        enter(true);
        const auto value = __au_runtime_nvme_transport_active_qid(storage_);
        require(value <= 2);
        leave();
        return value;
    }
    auto active_cid() const -> U64 {
        if (!live_)
            return 0;
        enter(true);
        const auto value = __au_runtime_nvme_transport_active_cid(storage_);
        require(value <= 65535);
        leave();
        return value;
    }
    auto remaining(U64 qid) const -> U64 {
        return query<__au_runtime_nvme_transport_remaining, 65535>(qid);
    }
    auto next_cid(U64 qid) const -> U64 {
        return query<__au_runtime_nvme_transport_next_cid, 65536>(qid);
    }
    auto tail(U64 qid) const -> U64 {
        return query<__au_runtime_nvme_transport_tail, 1>(qid);
    }
    auto head(U64 qid) const -> U64 {
        return query<__au_runtime_nvme_transport_head, 1>(qid);
    }
    auto phase(U64 qid) const -> U64 {
        return query<__au_runtime_nvme_transport_phase, 1>(qid);
    }
    auto status(U64 qid) const -> U64 {
        return query<__au_runtime_nvme_transport_status, 32767>(qid);
    }
    auto reserve(U64 qid, U64 prefilled_cid = 0) -> Plan {
        if (!live_)
            return {};
        enter(true);
        Plan plan{};
        if (__au_runtime_nvme_transport_reserve(storage_, qid, prefilled_cid)) {
            plan = {__au_runtime_nvme_transport_active_qid(storage_),
                    __au_runtime_nvme_transport_active_cid(storage_),
                    __au_runtime_nvme_transport_tail(storage_, qid) ^ 1,
                    __au_runtime_nvme_transport_tail(storage_, qid),
                    __au_runtime_nvme_transport_head(storage_, qid),
                    __au_runtime_nvme_transport_phase(storage_, qid)};
            require(__au_runtime_nvme_transport_stage(storage_) == Stage::reserved && plan.qid == qid && qid <= 1 &&
                    plan.cid && plan.cid <= 65535 && plan.sq_slot <= 1 && plan.new_tail <= 1 && plan.cq_slot <= 1 &&
                    plan.phase <= 1);
        }
        leave();
        return plan;
    }
    auto published(U64 qid, U64 cid) -> bool {
        enter(true);
        const auto value = __au_runtime_nvme_transport_published(storage_, qid, cid);
        leave();
        return value;
    }
    auto accept_completion(U64 qid, U64 cid, Observation observation) -> Completion {
        enter(true);
        const CompletionInput input{qid, cid, observation};
        Completion value;
        value.kind = __au_runtime_nvme_transport_accept_completion(storage_, &input);
        require(value.kind == CompletionKind::rejected || value.kind == CompletionKind::complete);
        value.status = __au_runtime_nvme_transport_status(storage_, qid);
        require(value.status <= 32767);
        if (value.kind == CompletionKind::complete) {
            value.new_cq_head = __au_runtime_nvme_transport_head(storage_, qid) ^ 1;
            require(__au_runtime_nvme_transport_stage(storage_) == Stage::completion_selected &&
                    __au_runtime_nvme_transport_active_qid(storage_) == qid &&
                    __au_runtime_nvme_transport_active_cid(storage_) == cid && value.new_cq_head <= 1);
        }
        leave();
        return value;
    }
    auto acknowledged(U64 qid, U64 cid) -> bool {
        enter(true);
        const auto value = __au_runtime_nvme_transport_acknowledged(storage_, qid, cid);
        leave();
        return value;
    }
    auto poison() -> bool {
        if (!live_)
            return false;
        enter(true);
        const auto value = __au_runtime_nvme_transport_poison(storage_);
        leave();
        return value;
    }
};
// Frozen native physical binding. A copied plan cannot select another queue or
// another boot owner, nor substitute any of the immutable DMA pages.
struct Binding final {
    const void *owner{};
    const std::byte *submission{}, *completion{};
    U64 qid{};
    auto operator==(const Binding &) const -> bool = default;
    auto valid() const -> bool {
        return owner && submission && completion && submission != completion && qid <= 1 &&
               reinterpret_cast<std::uintptr_t>(submission) % 4096 == 0 &&
               reinterpret_cast<std::uintptr_t>(completion) % 4096 == 0;
    }
};
// A stack-local, noncopyable record of physical effect receipts, not a second
// queue ledger. Each receipt is consumed once and must name the exact effect.
class Effects final {
    const Binding binding_;
    const Plan plan_;
    enum class Receipt {
        invalid,
        reserved,
        published,
        selected,
        acknowledged
    };
    Receipt receipt_;

public:
    Effects(Binding binding, Plan plan)
        : binding_(binding), plan_(plan),
          receipt_(binding.valid() && binding.qid == plan.qid && plan.cid && plan.cid <= 65535 && plan.sq_slot <= 1 &&
                           plan.new_tail == (plan.sq_slot ^ 1) && plan.cq_slot <= 1 && plan.phase <= 1
                       ? Receipt::reserved
                       : Receipt::invalid) {
    }
    Effects(const Effects &) = delete;
    Effects(Effects &&) = delete;
    auto operator=(const Effects &) -> Effects & = delete;
    auto operator=(Effects &&) -> Effects & = delete;
    auto authenticates(Binding expected) const -> bool {
        return receipt_ != Receipt::invalid && expected.valid() && expected == binding_;
    }
    auto published(Binding expected, U64 slot, U64 cid, U64 tail) -> bool {
        if (!authenticates(expected) || receipt_ != Receipt::reserved || slot != plan_.sq_slot || cid != plan_.cid ||
            tail != plan_.new_tail)
            return false;
        receipt_ = Receipt::published;
        return true;
    }
    auto selected(Binding expected, U64 cid, U64 head) -> bool {
        if (!authenticates(expected) || receipt_ != Receipt::published || cid != plan_.cid ||
            head != (plan_.cq_slot ^ 1))
            return false;
        receipt_ = Receipt::selected;
        return true;
    }
    auto acknowledged(Binding expected, U64 cid, U64 head) -> bool {
        if (!authenticates(expected) || receipt_ != Receipt::selected || cid != plan_.cid ||
            head != (plan_.cq_slot ^ 1))
            return false;
        receipt_ = Receipt::acknowledged;
        return true;
    }
};
} // namespace aurora::nvme
