#include "../kernel/dormant-tables.hpp"
#include <algorithm>
#include <cstdio>
#include <cstdlib>
using namespace aurora;
auto require(bool b)->void{if(!b)std::abort();}
class Memory final {
public:
 alignas(4096) std::array<std::byte,16*4096> data{};
 auto base()const->std::uint64_t{return reinterpret_cast<std::uintptr_t>(data.data());}
 static auto scrub(void* p,std::uint64_t pa,std::size_t count)->bool{
  auto& m=*static_cast<Memory*>(p);require(count==4096&&pa>=m.base()&&pa-m.base()<=m.data.size()-count);
  std::fill_n(m.data.begin()+static_cast<std::ptrdiff_t>(pa-m.base()),count,std::byte{0});return true;
 }
};
auto main()->int{
 Memory m;memory::PhysicalPages pool;require(pool.initialize(m.base(),16));
 user::DomainRegistry registry;const auto owner=registry.create();require(owner.has_value());
 memory::PinLedger ledger(pool,registry,Memory::scrub,&m);
 memory::DormantTables tables(ledger,m.data,m.base());
 const std::array<std::uint64_t,2> io{0,4096};const std::array<bool,2> rw{false,true};
 unsigned successes=0;
 for(unsigned cycle=0;cycle<20;++cycle){
  if(tables.prepare(*owner,52,io,rw)){++successes;require(tables.validate(*owner));require(tables.cancel(*owner));}
  require(pool.used()==0&&ledger.pinned_pages()==0);
 }
 require(successes==3);require(ledger.available_entries()==0);
 std::puts("PASS generation-bound3:3 complete constructions,17 rejected, no wrap or retained allocation");
}
