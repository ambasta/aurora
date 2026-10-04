#include "ir.hpp"
#include "ir_verify.hpp"
#include <iostream>
int main(){
 using namespace aurora;using namespace aurora::ir;
 Function f;f.name="empty_facts";f.result=Type::I64;f.frameBytes=65536;
 for(int offset=1;offset<=65536;++offset)f.slots.emplace(offset,Type::U8);
 for(int branch=0;branch<512;++branch){const int alternate=branch*2,join=alternate+1;f.code.insert(f.code.end(),{Constant{1,Type::Bool},BranchFalse{alternate},Constant{1,Type::I64},Jump{join},Label{alternate},Constant{2,Type::I64},Label{join}});}
 f.code.push_back(Return{});
 std::map<std::string,const Function*> functions{{f.name,&f}};verification::Metrics metrics;verification::verifyFunction(f,functions,&metrics);
 std::cout<<"accepted slots=65536 facts="<<metrics.peakRetainedValueFacts<<" snapshots="<<metrics.snapshots<<"\n";
}
