from pathlib import Path
import os,socket,subprocess,json,time,hashlib,traceback
r=Path('/tmp/aurora-msix-trace-control')
qemu='/tmp/aurora-qemu/root/usr/bin/qemu-system-x86_64'
args=[qemu,'-L','/tmp/aurora-qemu/firmware','-machine','q35,accel=tcg','-m','128M','-nodefaults','-display','none','-serial','none','-monitor','none','-S','-no-reboot','-no-shutdown','-device','nvme,id=control_nvme,serial=AURORA-MSIX-TRACE-CONTROL,bus=pcie.0,addr=02.0,romfile=','-qtest',f'unix:{r}/qtest.sock,server=on,wait=off','-qtest-log',str(r/'qtest-native.log'),'-qmp',f'unix:{r}/qmp.sock,server=on,wait=off','-trace',f'events=/tmp/aurora-clean-ovmf/provenance/trace-enable-events.txt,file={r}/trace.log']
env=os.environ.copy();env['LD_LIBRARY_PATH']='/tmp/aurora-qemu/root/usr/lib/x86_64-linux-gnu'
(r/'invocation.json').write_text(json.dumps({'argv':args,'environment_override':{'LD_LIBRARY_PATH':env['LD_LIBRARY_PATH']},'purpose':'Separate disposable MSI-X trace coverage control. CPUs stopped throughout; no disks or namespace; never an accepted clean-controller run.'},indent=2)+'\n')
log=(r/'protocol.jsonl').open('w')
def record(kind,data):log.write(json.dumps({'kind':kind,'data':data})+'\n');log.flush()
p=subprocess.Popen(args,env=env,stdout=(r/'stdout.log').open('w'),stderr=(r/'stderr.log').open('w'))
qm=None
try:
    def connect(name):
        for i in range(100):
            if p.poll() is not None:raise RuntimeError('QEMU exited before socket')
            try:
                s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);s.connect(str(r/name));s.settimeout(5);return s.makefile('rwb',buffering=0)
            except (FileNotFoundError,ConnectionRefusedError):time.sleep(.03)
        raise RuntimeError('socket unavailable')
    qm=connect('qmp.sock');record('qmp-greeting',json.loads(qm.readline()))
    def qmp(name,arguments=None):
        req={'execute':name}
        if arguments is not None:req['arguments']=arguments
        qm.write((json.dumps(req)+'\n').encode());record('qmp-request',req)
        while True:
            out=json.loads(qm.readline());record('qmp-response',out)
            if 'return' in out:return out['return']
            if 'error' in out:raise RuntimeError(out)
    qmp('qmp_capabilities')
    assert qmp('query-status')['running'] is False
    assert qmp('query-block')==[]
    topology=qmp('query-pci');(r/'query-pci.json').write_text(json.dumps(topology,indent=2)+'\n')
    tree=qmp('human-monitor-command',{'command-line':'info qtree'});(r/'qtree.txt').write_text(tree)
    qt=connect('qtest.sock')
    def cmd(line):
        qt.write((line+'\n').encode());record('qtest-request',line)
        out=qt.readline().decode().strip();record('qtest-response',out)
        if not out.startswith('OK'):raise RuntimeError(out)
        v=out.split();return int(v[1],0) if len(v)>1 else None
    def select(off):cmd(f'outl 0xcf8 {0x80001000|(off&0xfc):#x}')
    def rd(off,width=4):
        select(off);return cmd(f'in{ {1:"b",2:"w",4:"l"}[width]} {0xcfc+(off&3):#x}')
    def wr(off,value,width=4):
        select(off);cmd(f'out{ {2:"w",4:"l"}[width]} {0xcfc+(off&3):#x} {value:#x}')
    assert rd(0)==0x00101b36
    assert rd(8)>>8==0x010802
    assert rd(0x0e,1)==0
    initial=rd(4,2);assert initial==0
    assert rd(0x10)==4 and rd(0x14)==0
    cap=rd(0x34,1);seen=set();msix=None
    while cap:
        assert 0x40<=cap<0x100 and cap not in seen
        seen.add(cap)
        if rd(cap,1)==0x11:msix=cap;break
        cap=rd(cap+1,1)
    assert msix is not None
    ctrl=rd(msix+2,2);assert not(ctrl&0x8000)
    table=rd(msix+4);assert(table&7)==0
    offset=table&~7
    # Prerequisites: map BAR0 only, then MEMORY decode only. No BME bit ever set.
    wr(0x10,0xc0000004);wr(0x14,0)
    assert rd(0x10)==0xc0000004 and rd(0x14)==0
    wr(4,2,2);assert rd(4,2)==2
    def regs():
        return {hex(o):cmd(f'readl {0xc0000000+o:#x}') for o in [0x14,0x1c,0x24,0x28,0x2c,0x30,0x34]}
    before=regs();assert all(v==0 for v in before.values())
    assert rd(msix+2,2)&0x8000==0
    target=0xc0000000+offset+12
    vector=cmd(f'readl {target:#x}');assert vector==1
    # Exactly one approved same-value, masked MSI-X vector-control write.
    cmd(f'writel {target:#x} {vector:#x}')
    assert cmd(f'readl {target:#x}')==vector
    after=regs();assert after==before
    assert rd(4,2)==2 and rd(msix+2,2)==ctrl
    assert qmp('query-status')['running'] is False
    result={'control_passed':True,'bdf':'0000:00:02.0','vendor_device':'1b36:0010','class':'010802','header_type':0,'pci_command_initial':initial,'pci_command_final':2,'bme_never_requested':True,'bar0':hex(0xc0000000),'msix_capability_offset':hex(msix),'msix_control_before_after':hex(ctrl),'msix_table_offset':hex(offset),'single_table_write':{'address':hex(target),'value':vector,'size':4,'vector':0,'field':'vector control mask bit already set'},'registers_before':before,'registers_after':after,'cpu_running':False,'namespace_backends':[]}
    (r/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
except Exception:
    (r/'failure.txt').write_text(traceback.format_exc());raise
finally:
    if qm is not None:
        try:qm.write(b'{"execute":"quit"}\n')
        except Exception:pass
    try:p.wait(timeout=5)
    except subprocess.TimeoutExpired:p.terminate();p.wait(timeout=5)
    log.close()
