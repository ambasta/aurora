#include "/workspace/scratch/48c5de6446f8/aurora-dma-tables-candidate/normative/include/dormant-tables.hpp"
#include "/workspace/scratch/48c5de6446f8/aurora-dma-tables-candidate/normative/independent-decoder.hpp"
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <memory>
using namespace aurora;
namespace {
std::size_t checks=0;
void ck(bool b){++checks;if(!b){std::fprintf(stderr,"reviewer FAIL %zu\n",checks);std::abort();}}
class F {
public:
 std::array<std::byte,16*4096+1> storage{};
 std::span<std::byte> bytes{storage.data()+1,16*4096}; // byte operations require no virtual alignment
 std::uint64_t base;
 memory::PhysicalPages pool;
 user::DomainRegistry registry;
 user::DomainHandle owner,peer;
 std::array<std::optional<memory::PageLease>,16> held{};
 std::size_t held_n=0,fail_at=0,scrubs=0;
 bool reenter=false;
 memory::DormantTables *active=nullptr,*other=nullptr;
 memory::PinLedger ledger;
 F(std::uint64_t b=0x100000):base(b),ledger(pool,registry,scrub,this){
  ck(pool.initialize(base,16));owner=*registry.create();peer=*registry.create();
  storage.fill(std::byte{0xa5});
 }
 void hold(std::size_t n){for(std::size_t i=0;i<n;++i){auto p=pool.acquire();ck(bool(p));held[held_n++].emplace(std::move(*p));}}
 static bool scrub(void *ctx,std::uint64_t pa,std::size_t n){
  auto &f=*static_cast<F*>(ctx);ck(n==4096&&pa>=f.base&&pa-f.base<=f.bytes.size()-n);
  for(const auto &h:f.held)if(h)ck(f.pool.address(*h)!=pa);
  if(f.reenter){
   const std::array<std::uint64_t,1> io{0};const std::array<bool,1> rw{false};
   ck(!f.active->validate(f.owner));ck(!f.active->cancel(f.owner));
   ck(!f.active->prepare(f.owner,52,io,rw));
   ck(!f.other->prepare(f.peer,52,io,rw));
   ck(!f.ledger.grant(f.peer,1));ck(f.ledger.borrower_dispose(f.owner)==0);ck(f.ledger.reap_dead()==0);
  }
  if(++f.scrubs==f.fail_at)return false;
  std::fill_n(f.bytes.begin()+static_cast<std::ptrdiff_t>(pa-f.base),n,std::byte{0});
  return std::all_of(f.bytes.begin()+static_cast<std::ptrdiff_t>(pa-f.base),f.bytes.begin()+static_cast<std::ptrdiff_t>(pa-f.base+n),[](auto x){return x==std::byte{0};});
 }
 void check_held(){ck(storage[0]==std::byte{0xa5});for(const auto &p:held)if(p){const auto pa=pool.address(*p);ck(bool(pa));for(std::size_t j=0;j<4096;++j)ck(bytes[*pa-base+j]==std::byte{0xa5});}}
};
const std::array<std::uint64_t,2> io{0,0x1ff000};
const std::array<bool,2> rw{false,true};
independent::Input snapshot(F& f,std::size_t first,std::size_t count=2){
 independent::Input in;in.dte=f.bytes.subspan(first*4096,8192);in.root=f.bytes.subspan((first+2)*4096,4096);
 in.data_count=count;in.physical_bits=52;in.iovas=io;in.writable=rw;
 for(std::size_t j=0;j<3+count;++j)in.pages[j]=f.base+(first+j)*4096;
 if(count==1){in.iovas[1]=0;in.writable[1]=false;}return in;
}
void widths(){
 for(unsigned width=32;width<=52;++width){
  const auto end=std::uint64_t{1}<<width;
  auto f=std::make_unique<F>(end-16*4096);f->hold(11);
  memory::DormantTables t(f->ledger,f->bytes,f->base);ck(t.prepare(f->owner,static_cast<std::uint8_t>(width),io,rw));
  auto in=snapshot(*f,11);in.physical_bits=static_cast<std::uint8_t>(width);ck(independent::validate(in));ck(t.validate(f->owner));
  for(std::size_t j=14*4096;j<16*4096;++j)ck(f->bytes[j]==std::byte{0});
  ck(t.cancel(f->owner));ck(f->pool.used()==11);f->check_held();
  auto g=std::make_unique<F>(end-15*4096);g->hold(11);
  memory::DormantTables u(g->ledger,g->bytes,g->base);ck(!u.prepare(g->owner,static_cast<std::uint8_t>(width),io,rw));
  ck(g->pool.used()==11);ck(g->ledger.pinned_pages()==0);g->check_held();
 }
}
void arena_denials(){
 for(unsigned mode=0;mode<6;++mode){auto f=std::make_unique<F>();
  auto span=f->bytes;auto base=f->base;
  if(mode==0)span={};
  if(mode==1)span=span.first(4095);
  if(mode==2)span=span.first(4*4096);
  if(mode==3)++base;
  if(mode==4)base+=4096;
  if(mode==5)base=UINT64_MAX-4095;
  memory::DormantTables t(f->ledger,span,base);ck(!t.prepare(f->owner,52,io,rw));ck(f->pool.used()==0);ck(f->ledger.pinned_pages()==0);ck(!t.validate(f->owner));
 }
}
void stale_and_reentry(){
 auto f=std::make_unique<F>();memory::DormantTables old(f->ledger,f->bytes,f->base),fresh(f->ledger,f->bytes,f->base);
 ck(old.prepare(f->owner,52,io,rw));ck(f->ledger.borrower_dispose(f->owner)==3);
 ck(fresh.prepare(f->owner,52,io,rw));const auto saved=f->storage;
 ck(!old.validate(f->owner));ck(!old.cancel(f->owner));ck(f->storage==saved);ck(fresh.validate(f->owner));
 f->active=&fresh;f->other=&old;f->reenter=true;ck(fresh.cancel(f->owner));ck(f->pool.used()==0);
 for(std::size_t failure=1;failure<=5;++failure){
  auto g=std::make_unique<F>();memory::DormantTables a(g->ledger,g->bytes,g->base),b(g->ledger,g->bytes,g->base);
  g->active=&a;g->other=&b;g->reenter=true;g->fail_at=failure;
  ck(a.prepare(g->owner,52,io,rw));ck(!a.cancel(g->owner));
  const auto q=g->ledger.quarantined_pages();ck(q==(failure<=2?2U:(failure==3?1U:2U)));
  ck(g->pool.used()==q);ck(g->ledger.pinned_pages()==q);ck(!a.cancel(g->owner));
  ck(g->registry.destroy(g->owner));ck(g->ledger.reap_dead()==0);ck(g->pool.used()==q);
 }
}
void all_bits(){
 auto f=std::make_unique<F>();memory::DormantTables t(f->ledger,f->bytes,f->base);ck(t.prepare(f->owner,52,io,rw));
 for(std::size_t b=0;b<3*4096;++b)for(unsigned bit=0;bit<8;++bit){f->bytes[b]^=std::byte(1U<<bit);ck(!t.validate(f->owner));f->bytes[b]^=std::byte(1U<<bit);}
 ck(t.validate(f->owner));ck(t.cancel(f->owner));
}
void slot_sweep(){
 for(std::size_t slot=0;slot<512;++slot)for(bool writable:{false,true}){
  auto f=std::make_unique<F>();memory::DormantTables t(f->ledger,f->bytes,f->base);
  const std::array<std::uint64_t,1> addr{slot*4096};const std::array<bool,1> rights{writable};
  ck(t.prepare(f->owner,32,addr,rights));auto in=snapshot(*f,0,1);in.physical_bits=32;in.iovas[0]=addr[0];in.writable[0]=writable;
  ck(independent::validate(in));ck(independent::permits(in,16,slot*4096+4095,1,false));
  ck(independent::permits(in,16,slot*4096+4095,1,true)==writable);ck(!independent::permits(in,16,slot*4096+4095,2,false));ck(t.cancel(f->owner));
 }
}
}
int main(){widths();arena_denials();stale_and_reentry();all_bits();slot_sweep();std::printf("PASS %zu independent reviewer checks; CPU construction only\n",checks);}
