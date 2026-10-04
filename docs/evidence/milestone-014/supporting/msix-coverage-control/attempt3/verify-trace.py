from pathlib import Path
import json,hashlib
r=Path('/tmp/aurora-msix-trace-control/attempt3')
lines=(r/'trace.log').read_text().splitlines()
keys=['pci_cfg_write nvme 00:02.0 @0x4 <- 0x2','name \'msix-table\'','pci_nvme_mmio_write','pci_nvme_mmio_start_success','pci_nvme_create_sq','pci_nvme_create_cq','pci_nvme_dma_read']
summary={k:[l for l in lines if k in l] for k in keys}
assert len(summary[keys[0]])==1,summary[keys[0]]
assert len(summary[keys[1]])==1,summary[keys[1]]
assert "addr 0xc000200c value 0x1 size 4 name 'msix-table'" in summary[keys[1]][0]
assert all(not summary[k] for k in keys[2:])
summary['all_nvme_config_writes']=[l for l in lines if 'pci_cfg_write nvme 00:02.0' in l]
assert len(summary['all_nvme_config_writes'])==3
(r/'trace-verification.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
records=[]
for p in sorted(r.iterdir()):
 if p.is_file() and p.name!='SHA256SUMS':records.append(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}')
(r/'SHA256SUMS').write_text('\n'.join(records)+'\n')
