// Direct typed-IR provenance/operand/lifetime tests. No parser or source lowering.
#include "ir_verify.hpp"
#include "x86.hpp"
#include <functional>
#include <iostream>
using namespace aurora;
using namespace aurora::ir;
using F = aurora::ir::Function;
namespace {
int accepted=0,rejected=0;
void require(bool v,const std::string &m){if(!v) throw Error(m);}
Module base(bool size=false) {
    F f;f.name=size?"window_size":"window_dynamic";f.result=Type::I64;
    f.parameters={Type::I64,Type::I64,Type::I64};f.frameBytes=256;
    f.slots={{8,Type::U8},{7,Type::U8},{6,Type::U8},{56,Type::I64},{64,Type::I64},{72,Type::I64}};
    f.arraySlots={{8,3}};f.spanSlots={128,184};
    f.code={BindParameter{0,56,Type::I64},BindParameter{1,64,Type::I64},BindParameter{2,72,Type::I64},
            BeginArray{8},Constant{11,Type::U8},Store{8,Type::U8},Constant{128,Type::U8},Store{7,Type::U8},
            Constant{255,Type::U8},Store{6,Type::U8},BorrowSpan{8,128},Load{56,Type::I64},Push{},
            Load{64,Type::I64},Subspan{128,184}};
    if(size) f.code.push_back(SpanLength{184});
    else {f.code.push_back(Load{72,Type::I64});f.code.push_back(SpanLoad{184});f.code.push_back(Convert{Type::U8,Type::I64});}
    f.code.insert(f.code.end(),{EndSpan{184},EndSpan{128},EndArray{8},Return{}});
    Module m;m.functions={f};return m;
}
void accept(const std::string&n,Module m){require(!X86Emitter{}.emit(validate(std::move(m))).empty(),"empty assembly");++accepted;std::cout<<"PASS window IR "<<n<<'\n';}
void reject(const std::string&n,const std::function<void(F&)>&change,const std::string&diagnostic){
    auto m=base();change(m.functions[0]);
    try{(void)validate(std::move(m));}catch(const Error&e){require(std::string(e.what()).find(diagnostic)!=std::string::npos,n+": wrong rejection: "+e.what());++rejected;std::cout<<"PASS window IR "<<n<<'\n';return;}throw Error(n+": malformed IR accepted");
}
void tests(){
    accept("checked dynamic window",base());accept("window exact length",base(true));
    reject("offset stack absent",[](F&f){f.code.erase(f.code.begin()+12);},"value stack underflow");
    for(const Type&t:{Type::U64,Type::U8,Type::Bool}){
        reject("wrong offset "+typeName(t),[=](F&f){f.code[11]=Constant{0,t};},"subspan offset requires i64");
        reject("wrong count "+typeName(t),[=](F&f){f.code[13]=Constant{0,t};},"missing or mistyped current value");
    }
    reject("inactive parent",[](F&f){f.code[14]=Subspan{184,128};},"span capability is not active");
    reject("unknown parent",[](F&f){f.code[14]=Subspan{112,184};},"span requires exact typed spill");
    reject("parent interior",[](F&f){f.code[14]=Subspan{23,184};},"span requires exact typed spill");
    reject("array cannot be parent",[](F&f){f.code[14]=Subspan{8,184};},"span requires exact typed spill");
    reject("unknown destination",[](F&f){f.code[14]=Subspan{128,168};},"exact typed spill");
    reject("destination interior",[](F&f){f.code[14]=Subspan{128,39};},"exact typed spill");
    reject("overwrite parent",[](F&f){f.code[14]=Subspan{128,128};},"span spill is already active");
    reject("scalar overlaps destination",[](F&f){f.slots[136]=Type::I64;},"span spill overlaps");
    reject("ended parent",[](F&f){f.code.insert(f.code.begin()+14,EndSpan{128});},"span capability is not active");
    reject("incomplete owner",[](F&f){f.code.erase(f.code.begin()+9);},"array element not initialized");
    reject("end parent with window",[](F&f){f.code.insert(f.code.begin()+15,EndSpan{128});},"live child reborrow");
    reject("end owner with window",[](F&f){f.code.insert(f.code.begin()+15,EndArray{8});},"live readonly span");
    reject("write root with window",[](F&f){f.code.insert(f.code.begin()+15,{Constant{9,Type::U8},Store{7,Type::U8}});},"write to byte array with live readonly span");
    reject("return leaks window",[](F&f){f.code.erase(f.code.end()-4);},"live child reborrow");
    reject("load ended window",[](F&f){f.code.insert(f.code.begin()+15,EndSpan{184});},"span capability is not active");
    reject("forks create different child sites",[](F&f){
        f.code.erase(f.code.begin()+11,f.code.begin()+15);
        f.code.insert(f.code.begin()+11,{Constant{0,Type::Bool},BranchFalse{1},Constant{0,Type::I64},Push{},Constant{1,Type::I64},Subspan{128,184},Jump{2},Label{1},Constant{1,Type::I64},Push{},Constant{1,Type::I64},Subspan{128,184},Label{2}});
    },"incompatible active span capabilities");
    reject("window restarts on only one branch",[](F&f){
        f.code.insert(f.code.begin()+15,{Constant{0,Type::Bool},BranchFalse{1},EndSpan{184},Constant{0,Type::I64},Push{},Constant{1,Type::I64},Subspan{128,184},Jump{2},Label{1},Label{2}});
    },"incompatible active span capabilities");
    auto nested=base();auto&f=nested.functions[0];f.frameBytes=256;f.spanSlots.insert(240);
    f.code.insert(f.code.begin()+15,{Constant{0,Type::I64},Push{},Constant{0,Type::I64},Subspan{184,240},SpanLength{240},EndSpan{240}});
    accept("nested child root and parent provenance",nested);
    auto empty=base();empty.functions[0].code[11]=Constant{3,Type::I64};empty.functions[0].code[13]=Constant{0,Type::I64};
    accept("empty endpoint capability remains typed",empty);
    auto loop=base();loop.functions[0].code.insert(loop.functions[0].code.begin()+11,{Label{1},Constant{0,Type::I64},Push{},Constant{0,Type::I64},Subspan{128,184},EndSpan{184},Constant{0,Type::Bool},BranchFalse{2},Jump{1},Label{2}});
    accept("fully closed child lifetime reused in loop",loop);
    auto rewrite=base();rewrite.functions[0].code.insert(rewrite.functions[0].code.end()-2,{Constant{42,Type::U8},Store{8,Type::U8},Convert{Type::U8,Type::I64}});
    accept("write owner only after every child and parent release",rewrite);
    // A parameter root must remain live, and its reserved entry spill cannot be rebound.
    F p;p.name="window_parameter";p.result=Type::I64;p.parameters={Type::ByteSpan};p.frameBytes=256;p.spanSlots={56,112,168};
    p.code={BindSpanParameter{0,56},Constant{0,Type::I64},Push{},Constant{0,Type::I64},Subspan{56,112},Constant{0,Type::I64},Push{},Constant{0,Type::I64},Subspan{112,168},SpanLength{168},EndSpan{168},EndSpan{112},EndSpan{56},Return{}};
    Module pm;pm.functions={p};accept("parameter provenance through nested empty windows",pm);
    auto bad=pm;bad.functions[0].code.insert(bad.functions[0].code.begin()+10,EndSpan{112});
    try{(void)validate(bad);throw Error("early parameter child end accepted");}catch(const Error&e){require(std::string(e.what()).find("live child reborrow")!=std::string::npos,"wrong parameter rejection");++rejected;}
    std::cout<<"PASS readonly window IR: "<<accepted<<" accepted and "<<rejected<<" rejected\n";
}
}
int main(int argc,char**argv){try{if(argc==2&&std::string(argv[1])=="--emit-native"){auto m=base();m.functions.push_back(base(true).functions[0]);std::cout<<X86Emitter{}.emit(validate(std::move(m)));}else if(argc==1)tests();else throw Error("invalid arguments");return 0;}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
