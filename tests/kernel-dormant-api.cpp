#include "../kernel/dormant-tables.hpp"
#include <type_traits>
using aurora::memory::DormantTables;
static_assert(!std::is_copy_constructible_v<DormantTables>);
static_assert(!std::is_move_constructible_v<DormantTables>);
template<class T> concept ExportsAddress=requires(T& value){value.address();};
template<class T> concept ExportsView=requires(T& value){value.view();};
template<class T> concept CanPublish=requires(T& value){value.publish();};
template<class T> concept CanComplete=requires(T& value){value.complete();};
static_assert(!ExportsAddress<DormantTables> && !ExportsView<DormantTables>);
static_assert(!CanPublish<DormantTables> && !CanComplete<DormantTables>);
auto main()->int{}
