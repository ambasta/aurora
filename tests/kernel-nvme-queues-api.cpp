// The shipping type exports only copied identity/counts and CPU preparation checks.
#include "../kernel/uefi/nvme-queues.hpp"
#include <type_traits>

namespace kernel_nvme_queues_api {
using namespace aurora::uefi;
template <class T>
concept Inject = requires(T &q) { q.fail_scrub_for_test(0); };
template <class T>
concept Address = requires(T &q, NvmeQueueHandle h) { q.address(h); };
template <class T>
concept Publish = requires(T &q, NvmeQueueHandle h) { q.publish(h); };
template <class T>
concept Complete = requires(T &q, NvmeQueueHandle h) { q.complete(h); };
template <class T>
concept Activate = requires(T &q) { q.activate(); };
static_assert(!Inject<NvmeQueueBundle> && !Address<NvmeQueueBundle> && !Publish<NvmeQueueBundle>);
static_assert(!Complete<NvmeQueueBundle> && !Activate<NvmeQueueBundle>);
static_assert(!std::is_convertible_v<NvmeQueueHandle, aurora::memory::PageLease>);
static_assert(!std::is_default_constructible_v<NvmeQueueBundle>);
auto main() -> int {
    return 0;
}
} // namespace kernel_nvme_queues_api
