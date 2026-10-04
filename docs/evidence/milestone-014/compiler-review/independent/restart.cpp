#include "ir_verify.hpp"
#include <iostream>
using namespace aurora; using namespace aurora::ir;
int main(){Module m; aurora::ir::Function f;f.name="test";f.result=Type::U8;f.frameBytes=32;f.slots={{8,Type::U8}};f.arraySlots={{8,1}};f.spanSlots={24};f.code={BeginArray{8},Constant{42,Type::U8},Store{8,Type::U8},BorrowSpan{8,24},Constant{1,Type::Bool},BranchFalse{1},EndSpan{24},EndArray{8},BeginArray{8},Constant{43,Type::U8},Store{8,Type::U8},BorrowSpan{8,24},Label{1},Constant{0,Type::I64},SpanLoad{24},EndSpan{24},EndArray{8},Return{}};m.functions.push_back(f);try{auto valid=validate(m);std::cout<<"ACCEPT same-slot restarted lifetime joins unchanged lifetime\n";}catch(const Error&e){std::cout<<e.what()<<'\n';return 1;}}
