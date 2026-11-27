import json,re,glob,os,sys
sys.path.insert(0,r'<TEST_COPY>\ps3recomp\tools')
from nid_database import compute_nid
imp=json.load(open(r'<TEST_COPY>\out\EBOOT.imports.json'))
reg=set(int(m,16) for m in re.findall(r'ps3_hle_register\(\s*0x([0-9A-Fa-f]{8})',open(r'<TEST_COPY>\port\bld\ppu_hle_nids.cpp').read()))
txt=''
for f in glob.glob(r'<TEST_COPY>\ps3recomp\runtime\**\*.c*',recursive=True)+glob.glob(r'<TEST_COPY>\ps3recomp\libs\**\*.c*',recursive=True):
    txt+=open(f,errors='ignore').read()
extra=set(int(m,16) for m in re.findall(r'(?:register|REG|NID)[^\n]{0,80}?0x([0-9A-Fa-f]{8})',txt))
names={}
try:
    for k,v in json.load(open(r'<TEST_COPY>\ps3recomp\tools\nid_from_protos.json')).items():
        if isinstance(v,str) and v.startswith('0x'): names[int(v,16)]=k
except Exception as e: print('protos',e)
miss=[]
for i in imp:
    n=int(i['nid'],16)
    if n not in reg and n not in extra: miss.append((i['library'],'0x%08X'%n,names.get(n,'?')))
print('imports',len(imp),'registered_in_table',sum(int(i['nid'],16) in reg for i in imp),'missing',len(miss))
for m in sorted(miss): print('%-22s %s %s'%m)
