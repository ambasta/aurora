// Independent direct-IR checks for the M022 copied method-parameter boundary.
// --emit-abi emits fixtures consumed by method_values_abi.py. No parser is used.
#include "ir_verify.hpp"
#include "x86.hpp"
#include <functional>
#include <iostream>
#include <string>

using namespace aurora;
using namespace aurora::ir;
using IRFunction = aurora::ir::Function;
namespace {
int accepted = 0, rejected = 0;
void require(bool ok, const std::string &message) { if (!ok) throw Error(message); }
IRFunction &named(Module &m, const std::string &name) {
    for (auto &f : m.functions) if (f.name == name) return f;
    throw Error("missing fixture function " + name);
}
MethodCall &method(IRFunction &f, const std::string &name) {
    for (auto &i : f.code) if (auto *c = std::get_if<MethodCall>(&i); c && c->callee == name) return *c;
    throw Error("missing fixture method call " + name);
}
void accept(const std::string &name, Module m) {
    require(!X86Emitter{}.emit(validate(std::move(m))).empty(), "empty assembly");
    ++accepted; std::cout << "PASS method IR " << name << '\n';
}
void reject(const std::string &name, Module m, const std::function<void(Module &)> &change,
            const std::string &diagnostic) {
    change(m);
    try { (void)validate(std::move(m)); }
    catch (const Error &e) {
        require(std::string(e.what()).find(diagnostic) != std::string::npos,
                name + ": wrong diagnostic: " + e.what());
        ++rejected; std::cout << "PASS method IR " << name << '\n'; return;
    }
    throw Error(name + ": malformed IR accepted");
}
Module baseline(bool result = true) {
    Module m; m.classLayouts = {{"Box", {Type::I64}}, {"Other", {Type::I64}}};
    IRFunction f; f.name = "entry"; f.result = Type::I64; f.frameBytes = 32;
    f.slots = {{8, Type::I64}, {16, Type::I64}, {24, Type::I64}, {32, Type::I64}};
    f.objectSlots = {{8, {"Box", true}}, {16, {"Box", false}},
                     {24, {"Box", false}}, {32, {"Box", false}}};
    f.code = {BeginObject{8}, Constant{40, Type::I64}, Store{8, Type::I64},
              BeginObject{16}, Constant{1, Type::I64}, Store{16, Type::I64},
              BeginObject{24}, Constant{2, Type::I64}, Store{24, Type::I64},
              BeginObject{32}, Constant{3, Type::I64}, Push{},
              MethodCall{"take", 8, {16, 0, 24}, result ? 32 : 0}};
    if (result) f.code.push_back(Load{32, Type::I64});
    f.code.push_back(Return{});
    IRFunction g; g.name = "take"; g.result = result ? Type("Box") : Type::I64;
    g.receiver = Receiver{"Box", false, false};
    g.parameters = {Type("Box"), Type::I64, Type("Box")}; g.frameBytes = 32;
    g.slots = {{8, Type::I64}, {16, Type::I64}, {24, Type::I64}};
    g.objectSlots = {{8, {"Box", false}}, {24, {"Box", false}}};
    g.code = {BindObjectParameter{0, 8, "Box"}, BindParameter{1, 16, Type::I64},
              BindObjectParameter{2, 24, "Box"}};
    if (result) g.code.push_back(ReturnObject{8});
    else { g.code.push_back(ReceiverLoad{0, Type::I64}); g.code.push_back(Return{}); }
    m.functions = {f, g}; return m;
}
Module logicalBaseline() {
    Module m; m.classLayouts = {{"Box", {Type::I64}}, {"Empty", {}}, {"Envelope", {}}};
    m.classFields["Envelope"] = {{Type("Empty"), 0, 0, false}};
    IRFunction f; f.name="entry"; f.result=Type::I64; f.frameBytes=32;
    f.slots={{8,Type::I64}};
    f.objectSlots={{8,{"Box",false}},{16,{"Empty",false}},
                   {24,{"Envelope",false}},{32,{"Envelope",false}}};
    f.code={BeginObject{8},Constant{40,Type::I64},Store{8,Type::I64},BeginObject{16},
            BeginObject{24},MethodCall{"construct_env",24,{16}},BeginObject{32},
            MethodCall{"roundtrip_env",8,{24},32},Constant{42,Type::I64},Return{}};
    IRFunction c; c.name="construct_env"; c.result=Type::I64; c.frameBytes=16;
    c.parameters={Type("Empty")}; c.receiver=Receiver{"Envelope",true,true};
    c.objectSlots={{8,{"Empty",false}}};
    c.code={BindObjectParameter{0,8,"Empty"},InitializeObjectField{0,0,8},
            Constant{0,Type::I64},Return{}};
    IRFunction g; g.name="roundtrip_env"; g.result=Type("Envelope"); g.frameBytes=16;
    g.parameters={Type("Envelope")}; g.receiver=Receiver{"Box",false,false};
    g.objectSlots={{8,{"Envelope",false}}}; g.code={BindObjectParameter{0,8,"Envelope"},ReturnObject{8}};
    m.functions={f,c,g}; return m;
}
void directTests() {
    accept("copied class params and class result",baseline());
    accept("copied class params and scalar result",baseline(false));
    auto mutableReceiver=baseline(); named(mutableReceiver,"take").receiver->mutableValue=true;
    accept("mutable receiver with readonly snapshots",mutableReceiver);
    auto check=[&](const std::string &name,const std::function<void(Module &)> &change,const std::string &d){reject(name,baseline(),change,d);};
    check("short argument vector",[](Module&m){method(m.functions[0],"take").objectArguments.pop_back();},"argument vector size mismatch");
    check("long argument vector",[](Module&m){method(m.functions[0],"take").objectArguments.push_back(0);},"argument vector size mismatch");
    check("scalar position names object",[](Module&m){method(m.functions[0],"take").objectArguments[1]=16;},"cannot name object storage");
    check("class position zero",[](Module&m){method(m.functions[0],"take").objectArguments[0]=0;},"exact object slot");
    check("class position interior",[](Module&m){method(m.functions[0],"take").objectArguments[0]=15;},"exact object slot");
    check("mutable snapshot",[](Module&m){m.functions[0].objectSlots[16].mutableValue=true;},"snapshot must be readonly");
    check("incomplete snapshot",[](Module&m){m.functions[0].code.erase(m.functions[0].code.begin()+5);},"not fully initialized");
    check("inactive snapshot",[](Module&m){m.functions[0].code.insert(m.functions[0].code.begin()+9,EndObject{16});},"outside active lifetime");
    check("wrong nominal snapshot",[](Module&m){m.functions[0].objectSlots[16].className="Other";},"nominal class mismatch");
    check("reused snapshot",[](Module&m){method(m.functions[0],"take").objectArguments[2]=16;},"snapshots must be distinct");
    check("snapshot aliases receiver",[](Module&m){method(m.functions[0],"take").objectArguments[0]=8;},"receiver aliases argument snapshot");
    check("result aliases snapshot",[](Module&m){method(m.functions[0],"take").resultOffset=16;},"result aliases argument snapshot");
    check("result aliases receiver",[](Module&m){method(m.functions[0],"take").resultOffset=8;},"result aliases receiver");
    check("result interior",[](Module&m){method(m.functions[0],"take").resultOffset=31;},"exact object slot");
    check("result inactive",[](Module&m){m.functions[0].code.erase(m.functions[0].code.begin()+9);},"result outside active object lifetime");
    check("result nonpristine",[](Module&m){m.functions[0].code.insert(m.functions[0].code.begin()+10,{Constant{9,Type::I64},Store{32,Type::I64}});},"requires uninitialized object");
    check("result wrong nominal",[](Module&m){m.functions[0].objectSlots[32].className="Other";},"result nominal class mismatch");
    check("class result missing destination",[](Module&m){method(m.functions[0],"take").resultOffset=0;},"exact object slot");
    reject("scalar result forbids destination",baseline(false),[](Module&m){method(m.functions[0],"take").resultOffset=32;},"scalar method result cannot name object storage");
    check("wrong scalar stack type",[](Module&m){m.functions[0].code[10]=Constant{1,Type::Bool};},"method argument type mismatch");
    check("missing scalar operand",[](Module&m){m.functions[0].code.erase(m.functions[0].code.begin()+11);},"value stack underflow");
    check("method cannot use plain call",[](Module&m){m.functions[0].code[12]=Call{"take"};},"plain call cannot target receiver");
    check("method cannot use ordinary aggregate call",[](Module&m){m.functions[0].code[12]=AggregateCall{"take",{16,0,24},32};},"aggregate call cannot target receiver");
    check("object binding prefix missing",[](Module&m){m.functions[1].code[0]=Constant{1,Type::I64};},"object parameter bindings must form the entry prefix");
    check("object binding wrong index",[](Module&m){std::get<BindObjectParameter>(m.functions[1].code[0]).index=2;},"entry prefix");
    check("late object binding",[](Module&m){m.functions[1].code.insert(m.functions[1].code.begin()+3,BindObjectParameter{0,8,"Box"});},"outside entry prefix");
    check("overlapping bindings",[](Module&m){std::get<BindObjectParameter>(m.functions[1].code[2]).offset=8;},"bindings overlap");
    check("object binding wrong nominal",[](Module&m){m.functions[1].objectSlots[8].className="Other";},"object parameter nominal class mismatch");
    check("object binding mutable",[](Module&m){m.functions[1].objectSlots[8].mutableValue=true;},"object parameter must be readonly");
    check("binding scalar into object",[](Module&m){std::get<BindParameter>(m.functions[1].code[1]).offset=8;},"parameter cannot bind object field");
    check("bound object cannot restart",[](Module&m){m.functions[1].code.insert(m.functions[1].code.begin()+3,BeginObject{8});},"parameter lifetime cannot restart");
    check("bound object cannot be assigned",[](Module&m){m.functions[1].code.insert(m.functions[1].code.begin()+3,{Constant{1,Type::I64},Store{8,Type::I64}});},"write to initialized const object field");
    for(const auto&t:{Type::Own,Type::Ref,Type::MutRef,Type::array(TypeKind::U8,2)})
        check("invalid method parameter "+typeName(t),[t](Module&m){m.functions[1].parameters[0]=t;},"receiver signature requires scalar, enum or class values");
    check("span method argument lacks capability vector",[](Module&m){m.functions[1].parameters[0]=Type::ByteSpan;},"method span argument vector size mismatch");
    check("const receiver cannot mutate",[](Module&m){m.functions[1].code.insert(m.functions[1].code.begin()+3,{Constant{1,Type::I64},ReceiverStore{0,Type::I64}});},"write through const receiver");
    check("const local cannot supply mutable receiver",[](Module&m){m.functions[0].objectSlots[8].mutableValue=false;m.functions[1].receiver->mutableValue=true;},"const object cannot supply mutable receiver");
    check("forward without receiver",[](Module&m){method(m.functions[0],"take").receiverOffset=0;},"forwarding without bound receiver");
    auto forwarded=baseline();
    auto leaf=named(forwarded,"take");leaf.name="take_leaf";
    auto&g=named(forwarded,"take"); g.objectSlots[32]={"Box",false};g.slots[32]=Type::I64;
    g.code.insert(g.code.begin()+3,{BeginObject{32},Load{16,Type::I64},Push{},MethodCall{"take_leaf",0,{8,0,24},32}});
    g.code.back()=ReturnObject{32};forwarded.functions.push_back(leaf);
    accept("forwarded receiver and copied arguments",forwarded);
    reject("forwarding const receiver to mutable method",forwarded,[](Module&m){
        auto h=m.functions[1];h.name="mutable_take";h.receiver->mutableValue=true;
        h.code={BindObjectParameter{0,8,"Box"},BindParameter{1,16,Type::I64},BindObjectParameter{2,24,"Box"},ReturnObject{8}};
        method(m.functions[1],"take_leaf").callee="mutable_take";m.functions.push_back(h);
    },"const receiver cannot forward mutable capability");
    accept("empty nested logical completion copied",logicalBaseline());
    reject("empty nested snapshot not logically complete",logicalBaseline(),[](Module&m){m.functions[0].code.erase(m.functions[0].code.begin()+5);},"nested class field not completely initialized");
    reject("empty nested constructor incomplete",logicalBaseline(),[](Module&m){m.functions[1].code.erase(m.functions[1].code.begin()+1);},"constructor returns before all class fields initialized");
    reject("empty logical child initialized twice",logicalBaseline(),[](Module&m){m.functions[1].code.insert(m.functions[1].code.begin()+2,InitializeObjectField{0,0,8});},"initialized more than once");
    reject("empty class result reused",logicalBaseline(),[](Module&m){m.functions[0].code.insert(m.functions[0].code.begin()+8,MethodCall{"roundtrip_env",8,{24},32});},"already initialized");
    reject("empty result aliases argument",logicalBaseline(),[](Module&m){method(m.functions[0],"roundtrip_env").resultOffset=24;},"result aliases argument snapshot");
}

// ABI fixture layouts are deliberately declared here, while all expected byte
// offsets and records in the Python/native harness are authored independently.
Module abiModule() {
    const auto mode=Type::enumeration("Mode");
    Module m; m.enumCases["Mode"]=2;
    m.classLayouts={{"Receiver",{Type::I64}},{"Tiny",{Type::U8,Type::U8}},
                    {"Empty",{}},{"Pack",{Type::U8,Type::I64,Type::U8}},
                    {"Composed",{Type::U8,Type::U8,mode,Type::U8}}};
    m.classFields["Composed"]={{Type("Tiny"),0,2,false},{Type("Empty"),2,0,false},
                              {mode,2,1,false},{Type::U8,3,1,false}};
    IRFunction ordinary;ordinary.name="abi_clobber";ordinary.result=Type::I64;
    ordinary.code={Constant{0,Type::I64},Return{}};m.functions.push_back(ordinary);
    auto probe=ordinary;probe.name="abi_receiver_probe";probe.receiver=Receiver{"Receiver",false,false};m.functions.push_back(probe);
    auto nested=probe;nested.name="abi_nested_probe";nested.parameters={Type("Tiny")};nested.frameBytes=16;
    nested.objectSlots={{8,{"Tiny",false}}};nested.slots={{8,Type::U8},{7,Type::U8}};
    nested.code={BindObjectParameter{0,8,"Tiny"},Constant{0,Type::I64},Return{}};m.functions.push_back(nested);
    for(bool result:{false,true}) {
        IRFunction g;g.name=result?"abi_in_result":"abi_in_scalar";g.result=result?Type("Pack"):Type::I64;
        g.receiver=Receiver{"Receiver",false,false};
        g.parameters={Type("Tiny"),Type::U8,Type("Empty"),mode,Type("Pack"),Type::I64};
        g.frameBytes=96;g.objectSlots={{8,{"Tiny",false}},{24,{"Empty",false}},
                                     {56,{"Pack",false}},{88,{"Pack",false}}};
        g.slots={{8,Type::U8},{7,Type::U8},{16,Type::U8},{32,mode},{56,Type::U8},
                 {48,Type::I64},{40,Type::U8},{64,Type::I64},
                 {88,Type::U8},{80,Type::I64},{72,Type::U8}};
        g.code={BindObjectParameter{0,8,"Tiny"},BindParameter{1,16,Type::U8},
                BindObjectParameter{2,24,"Empty"},BindParameter{3,32,mode},
                BindObjectParameter{4,56,"Pack"},BindParameter{5,64,Type::I64},
                Constant{84,Type::I64},Push{},Constant{2,Type::I64},BinaryValue{Binary::CheckedDivide},
                Constant{1,Type::U64},Push{},Constant{3,Type::I64},BinaryValue{Binary::ShiftLeft,Type::U64},
                Call{"abi_clobber"},MethodCall{"abi_receiver_probe",0},
                MethodCall{"abi_nested_probe",0,{8}},
                Load{32,mode},Push{},EnumConstant{mode,1},Compare{Comparison::Equal,mode},BranchFalse{1}};
        if(result) g.code.push_back(BeginObject{88});
        g.code.push_back(ReceiverLoad{0,Type::I64});
        for(auto [offset,type]:std::vector<std::pair<int,Type>>{{8,Type::U8},{7,Type::U8},{16,Type::U8},{56,Type::U8},{48,Type::I64},{40,Type::U8},{64,Type::I64}}) {
            g.code.push_back(Push{});g.code.push_back(Load{offset,type});
            if(type==Type::U8)g.code.push_back(Convert{Type::U8,Type::I64});
            g.code.push_back(BinaryValue{Binary::CheckedAdd});
        }
        if(result) {
            g.code.push_back(Store{80,Type::I64});
            g.code.insert(g.code.end(),{Load{8,Type::U8},Store{88,Type::U8},Load{40,Type::U8},Store{72,Type::U8},ReturnObject{88},Label{1},ReturnObject{56}});
        } else g.code.insert(g.code.end(),{Return{},Label{1},Constant{-1,Type::I64},Return{}});
        m.functions.push_back(g);
        auto target=g;target.name=result?"abi_out_target_result":"abi_out_target_scalar";m.functions.push_back(target);
        IRFunction f;f.name=result?"abi_out_result":"abi_out_scalar";f.result=Type::I64;f.frameBytes=96;
        f.objectSlots={{8,{"Receiver",true}},{16,{"Tiny",false}},{24,{"Empty",false}},
                       {48,{"Pack",false}},{72,{"Pack",false}}};
        f.slots={{8,Type::I64},{16,Type::U8},{15,Type::U8},{48,Type::U8},
                 {40,Type::I64},{32,Type::U8},{72,Type::U8},{64,Type::I64},{56,Type::U8}};
        f.code={BeginObject{8},Constant{1000,Type::I64},Store{8,Type::I64},
                BeginObject{16},Constant{3,Type::U8},Store{16,Type::U8},Constant{5,Type::U8},Store{15,Type::U8},
                BeginObject{24},BeginObject{48},Constant{11,Type::U8},Store{48,Type::U8},
                Constant{13,Type::I64},Store{40,Type::I64},Constant{17,Type::U8},Store{32,Type::U8},
                Constant{1,Type::I64},Push{},Constant{7,Type::U8},Push{},EnumConstant{mode,1},Push{},Constant{19,Type::I64},Push{}};
        if(result)f.code.push_back(BeginObject{72});
        f.code.push_back(MethodCall{target.name,8,{16,0,24,0,48,0},result?72:0});
        if(result) f.code.push_back(Load{64,Type::I64});
        f.code.insert(f.code.end(),{BinaryValue{Binary::CheckedAdd},Return{}});m.functions.push_back(f);
    }
    // Composed empty-child and enum shape copied in both directions.
    IRFunction c;c.name="abi_composed";c.result=Type("Composed");c.receiver=Receiver{"Receiver",false,false};
    c.parameters={Type("Composed")};c.frameBytes=32;c.objectSlots={{24,{"Composed",false}}};
    c.slots={{24,Type::U8},{23,Type::U8},{16,mode},{8,Type::U8}};
    c.code={BindObjectParameter{0,24,"Composed"},ReturnObject{24}};m.functions.push_back(c);
    // Historical ordinary aggregate, scalar-method, class-result-only method,
    // and aggregate constructor entry conventions are frozen controls.
    IRFunction old;old.name="abi_old_ordinary";old.result=Type("Pack");old.parameters={Type("Pack")};
    old.frameBytes=32;old.objectSlots={{24,{"Pack",false}}};old.slots={{24,Type::U8},{16,Type::I64},{8,Type::U8}};
    old.code={BindObjectParameter{0,24,"Pack"},ReturnObject{24}};m.functions.push_back(old);
    old.name="abi_old_result_method";old.receiver=Receiver{"Receiver",false,false};old.parameters={Type::I64};
    old.slots[32]=Type::I64;old.code={BindParameter{0,32,Type::I64},BeginObject{24},
        Constant{11,Type::U8},Store{24,Type::U8},Load{32,Type::I64},Store{16,Type::I64},
        Constant{17,Type::U8},Store{8,Type::U8},ReturnObject{24}};m.functions.push_back(old);
    old.name="abi_old_scalar_method";old.result=Type::I64;old.code={BindParameter{0,32,Type::I64},
        ReceiverLoad{0,Type::I64},Push{},Load{32,Type::I64},BinaryValue{Binary::CheckedAdd},Return{}};m.functions.push_back(old);
    old.name="abi_old_constructor";old.parameters={Type("Pack")};old.receiver=Receiver{"Pack",true,true};
    old.code={BindObjectParameter{0,24,"Pack"},Load{24,Type::U8},ReceiverStore{0,Type::U8},
        Load{16,Type::I64},ReceiverStore{1,Type::I64},Load{8,Type::U8},ReceiverStore{2,Type::U8},Constant{0,Type::I64},Return{}};m.functions.push_back(old);
    // Largest legal explicit argument record: six 64-word values = 3072 bytes.
    m.classLayouts["Wide"]=std::vector<Type>(64,Type::I64);
    for(bool result:{false,true}) {
        IRFunction g;g.name=result?"abi_max_result":"abi_max_scalar";
        g.result=result?Type("Wide"):Type::I64;g.receiver=Receiver{"Receiver",false,false};g.frameBytes=3072;
        for(int arg=0;arg<6;++arg) {
            g.parameters.push_back(Type("Wide"));const int base=(arg+1)*512;
            g.objectSlots[base]={"Wide",false};
            for(int leaf=0;leaf<64;++leaf)g.slots[base-leaf*8]=Type::I64;
            g.code.push_back(BindObjectParameter{arg,base,"Wide"});
        }
        if(result)g.code.push_back(ReturnObject{3072});
        else {
            g.code.push_back(ReceiverLoad{0,Type::I64});
            for(int arg=0;arg<6;++arg)for(int leaf:{0,63})
                g.code.insert(g.code.end(),{Push{},Load{(arg+1)*512-leaf*8,Type::I64},BinaryValue{Binary::CheckedAdd}});
            g.code.push_back(Return{});
        }
        m.functions.push_back(g);
        IRFunction f;f.name=result?"abi_out_max_result":"abi_out_max_scalar";f.result=Type::I64;f.frameBytes=3600;
        f.objectSlots[8]={"Receiver",false};f.slots[8]=Type::I64;
        f.code={BeginObject{8},Constant{1000,Type::I64},Store{8,Type::I64}};
        std::vector<int> arguments;
        for(int arg=0;arg<6;++arg) {
            const int base=8+(arg+1)*512;arguments.push_back(base);f.objectSlots[base]={"Wide",false};
            f.code.push_back(BeginObject{base});
            for(int leaf=0;leaf<64;++leaf) {
                f.slots[base-leaf*8]=Type::I64;
                f.code.insert(f.code.end(),{Constant{arg*64+leaf+1,Type::I64},Store{base-leaf*8,Type::I64}});
            }
        }
        f.code.insert(f.code.end(),{Constant{1,Type::I64},Push{}});
        if(result) {
            f.objectSlots[3592]={"Wide",false};
            for(int leaf=0;leaf<64;++leaf)f.slots[3592-leaf*8]=Type::I64;
            f.code.push_back(BeginObject{3592});
        }
        f.code.push_back(MethodCall{g.name,8,arguments,result?3592:0});
        if(result) {
            f.code.push_back(Load{3592,Type::I64});
            for(int leaf=1;leaf<64;++leaf)
                f.code.insert(f.code.end(),{Push{},Load{3592-leaf*8,Type::I64},BinaryValue{Binary::CheckedAdd}});
        }
        f.code.insert(f.code.end(),{BinaryValue{Binary::CheckedAdd},Return{}});m.functions.push_back(f);
    }
    auto relay=c;relay.name="abi_relay_composed";relay.frameBytes=64;
    relay.objectSlots[48]={"Composed",false};relay.slots[48]=Type::U8;relay.slots[47]=Type::U8;
    relay.slots[40]=mode;relay.slots[32]=Type::U8;
    relay.code={BindObjectParameter{0,24,"Composed"},BeginObject{48},
                MethodCall{"abi_composed",0,{24},48},ReturnObject{48}};m.functions.push_back(relay);
    IRFunction empty;empty.name="abi_empty";empty.result=Type("Empty");empty.parameters={Type("Empty")};
    empty.receiver=Receiver{"Receiver",false,false};empty.frameBytes=16;
    empty.objectSlots={{8,{"Empty",false}}};empty.code={BindObjectParameter{0,8,"Empty"},ReturnObject{8}};
    m.functions.push_back(empty);
    auto emptyRelay=empty;emptyRelay.name="abi_relay_empty";emptyRelay.objectSlots[16]={"Empty",false};
    emptyRelay.code={BindObjectParameter{0,8,"Empty"},BeginObject{16},MethodCall{"abi_empty",0,{8},16},ReturnObject{16}};
    m.functions.push_back(emptyRelay);
    for(const auto &kind:{"ordinary","result_method","scalar_method","constructor"}) {
        IRFunction f;f.name=std::string("abi_out_old_")+kind;f.result=Type::I64;f.frameBytes=64;
        f.objectSlots={{8,{"Receiver",false}},{32,{"Pack",false}},{56,{"Pack",false}}};
        f.slots={{8,Type::I64},{32,Type::U8},{24,Type::I64},{16,Type::U8},
                 {56,Type::U8},{48,Type::I64},{40,Type::U8}};
        f.code={BeginObject{8},Constant{1000,Type::I64},Store{8,Type::I64},
            BeginObject{32},Constant{11,Type::U8},Store{32,Type::U8},Constant{13,Type::I64},Store{24,Type::I64},
            Constant{17,Type::U8},Store{16,Type::U8},BeginObject{56},Constant{1,Type::I64},Push{}};
        const std::string k=kind;
        if(k=="ordinary")f.code.push_back(AggregateCall{"abi_old_ordinary",{32},56});
        else if(k=="constructor")f.code.push_back(MethodCall{"abi_old_constructor",56,{32}});
        else {f.code.push_back(Constant{13,Type::I64});f.code.push_back(Push{});
              f.code.push_back(MethodCall{"abi_old_"+k,8,{},k=="result_method"?56:0});}
        if(k!="scalar_method")f.code.push_back(Load{48,Type::I64});
        f.code.insert(f.code.end(),{BinaryValue{Binary::CheckedAdd},Return{}});m.functions.push_back(f);
    }
    return m;
}
}
int main(int argc,char**argv) {
    try {
        if(argc==2&&std::string(argv[1])=="--emit-abi") {std::cout<<X86Emitter{}.emit(validate(abiModule()));return 0;}
        require(argc==1,"usage: method-values-ir [--emit-abi]");directTests();
        std::cout<<"PASS method IR: "<<accepted<<" accepted, "<<rejected<<" rejected, "<<accepted+rejected<<" total\n";
        return 0;
    } catch(const std::exception&e){std::cerr<<"FAIL method IR: "<<e.what()<<'\n';return 1;}
}
