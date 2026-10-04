#!/usr/bin/env python3
import hashlib,json,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
main=root.parent/'aurora'
exclude={'build','baseline','tmp','review','evidence','.git','__pycache__'}
paths=[p for p in root.rglob('*') if p.is_file() and not (set(p.relative_to(root).parts)&exclude)]
data={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
path=root/'evidence'/sys.argv[1]
path.write_text(json.dumps(data,sort_keys=True,indent=2)+'\n')
