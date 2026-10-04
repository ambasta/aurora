#include "initialization_facts.hpp"
#include <set>
#include <random>
#include <iostream>
#include <numeric>
#include <cstdlib>
using aurora::ir::verification::InitializationFacts;
using aurora::ir::verification::InitializationSlotUniverse;
using U = std::shared_ptr<const InitializationSlotUniverse>;
static unsigned long checks=0;
void chk(bool b){++checks;if(!b)throw std::runtime_error("model mismatch");}
U universe(std::vector<int> v){return std::make_shared<const InitializationSlotUniverse>(std::move(v),65536);}
void check(const InitializationFacts &f,const std::set<int>&s,const U &u){chk(f.size()==s.size());chk(f.payloadBytes()==8*(u->size()/64+(u->size()%64!=0)));for(std::size_t i=0;i<u->size();++i)chk(f.contains(u->offset(i))==s.contains(u->offset(i)));chk(!f.contains(-1)&&!f.contains(0)&&!f.contains(65537));}
void checkError(auto op){bool rejected=false;try{op();}catch(const aurora::Error&){rejected=true;}chk(rejected);}
int main(){
 std::mt19937 rng(0xa11ce);
 for(int n=0;n<=257;++n){
  std::vector<int> v(n);for(int i=0;i<n;++i)v[i]=1+i*251;std::shuffle(v.begin(),v.end(),rng);
  U u=universe(v),other=universe(v);InitializationFacts a(u),b(other);std::set<int> sa,sb;
  for(int k=0;k<512;++k){int x=n?v[rng()%n]:0;unsigned op=rng()%6;
   if(op==0&&n){chk(a.insert(x)==sa.insert(x).second);}
   if(op==1&&n){chk(b.insert(x)==sb.insert(x).second);}
   if(op==2){chk(a.erase(x)==sa.erase(x));}
   if(op==3){a.unionWith(b);sa.insert(sb.begin(),sb.end());}
   if(op==4){a.intersectWith(b);for(auto p=sa.begin();p!=sa.end();)if(!sb.contains(*p))p=sa.erase(p);else ++p;}
   if(op==5){auto c=a;c=b;chk(c==b);auto moved=std::move(c);chk(moved==b);chk(c.size()==0&&c.wordCount()==0);c.intersectWith(a);chk(c.size()==0);c=std::move(moved);chk(c==b);}
   check(a,sa,u);check(b,sb,other);chk((a==b)==(sa==sb));
  }
 }
 // Cross-domain equality, meet and join against independent set models.
 for(int iteration=0;iteration<10000;++iteration){
  std::vector<int> v,w;std::set<int> sa,sb;
  for(int j=1;j<=130;++j){if(rng()%3){v.push_back(j*499);if(rng()%2)sa.insert(j*499);}if(rng()%3){w.push_back(j*499);if(rng()%2)sb.insert(j*499);}}
  U u=universe(v),q=universe(w);InitializationFacts a(u),b(q);for(int x:sa)a.insert(x);for(int x:sb)b.insert(x);
  chk((a==b)==(sa==sb));auto meet=a;meet.intersectWith(b);auto si=sa;for(auto p=si.begin();p!=si.end();)if(!sb.contains(*p))p=si.erase(p);else ++p;check(meet,si,u);
  auto join=a;bool valid=true;for(int x:sb)valid=valid&&u->index(x).has_value();
  if(valid){join.unionWith(b);auto su=sa;su.insert(sb.begin(),sb.end());check(join,su,u);}else {checkError([&]{join.unionWith(b);});check(join,sa,u);}
 }
 // Boundaries at maximum frame, plus empty and sparse domains.
 for(int n:{0,1,63,64,65,127,128,129,65535,65536}){std::vector<int>v(n);std::iota(v.begin(),v.end(),1);U u=universe(v);InitializationFacts a(u);std::set<int>s;for(int x:v){a.insert(x);s.insert(x);}check(a,s,u);a.intersectWith(a);a.unionWith(a);check(a,s,u);InitializationFacts z;checkError([&]{a.insert(0);});checkError([&]{a.insert(65537);});checkError([&]{z.insert(1);});if(n)checkError([&]{z.unionWith(a);});chk(z.size()==0);a.intersectWith(z);chk(a.size()==0);}
 checkError([]{InitializationFacts a(nullptr);});checkError([]{InitializationSlotUniverse u({1,1},16);});checkError([]{InitializationSlotUniverse u({0},16);});checkError([]{InitializationSlotUniverse u({17},16);});checkError([]{InitializationSlotUniverse u({},-1);});checkError([]{InitializationSlotUniverse u({},65537);});
 std::cout<<"PASS independent facts: "<<checks<<" checks, seeds 0xa11ce; all 0..257 slot counts; 10000 unequal-domain pairs; max 65536 slots\n";
}
