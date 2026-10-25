// The normal header must not contain the fault-injection interface, and clients
// cannot mint bindings, publish frames, import leases, or report completion.
#include "../kernel/pin-ledger.hpp"
#include <type_traits>

namespace kernel_pin_api {
using aurora::memory::PinHandle;
using aurora::memory::PinLedger;
using aurora::user::DomainHandle;
template <class T>
concept HasInjection =
    requires(T &ledger, PinHandle pin, DomainHandle domain) { ledger.inject_uncertainty(pin, domain); };
template <class T>
concept HasPublication = requires(T &ledger, PinHandle pin) { ledger.publish(pin); };
template <class T>
concept HasCompletion = requires(T &ledger, PinHandle pin) { ledger.complete(pin); };
static_assert(!HasInjection<PinLedger> && !HasPublication<PinLedger> && !HasCompletion<PinLedger>);
static_assert(!std::is_constructible_v<PinHandle, PinLedger &, unsigned long, unsigned long, unsigned long>);
auto main() -> int {
    return 0;
}
} // namespace kernel_pin_api
