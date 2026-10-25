#include "../kernel/dormant-tables.hpp"
#include <type_traits>

namespace kernel_dormant_api {
using aurora::memory::DormantTables;
static_assert(!std::is_copy_constructible_v<DormantTables>);
static_assert(!std::is_move_constructible_v<DormantTables>);
template <class T>
concept ExportsAddress = requires(T &value) { value.address(); };
template <class T>
concept ExportsView = requires(T &value) { value.view(); };
template <class T>
concept CanPublish = requires(T &value) { value.publish(); };
template <class T>
concept CanComplete = requires(T &value) { value.complete(); };
static_assert(!ExportsAddress<DormantTables> && !ExportsView<DormantTables>);
static_assert(!CanPublish<DormantTables> && !CanComplete<DormantTables>);
// Storage, page views and the raw writer stay private: no member pointer escapes.
template <class T> concept PagesVisible = requires { &T::pages_; };
template <class T> concept ArenaVisible = requires { &T::arena_; };
template <class T> concept GroupsVisible = requires { &T::groups_; };
template <class T> concept DteWordVisible = requires { &T::dte_word; };
template <class T> concept PageVisible = requires { &T::page; };
template <class T> concept PutVisible = requires { &T::put; };
static_assert(!PagesVisible<DormantTables> && !ArenaVisible<DormantTables> && !GroupsVisible<DormantTables>);
static_assert(!DteWordVisible<DormantTables> && !PageVisible<DormantTables> && !PutVisible<DormantTables>);
auto main() -> int {
    return 0;
}
} // namespace kernel_dormant_api
