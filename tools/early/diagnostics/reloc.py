"""Plan D trick: reuse a finished Ninja build in a COPIED work folder without a full ~16 min rebuild.

After copying <old>/port/bld to <new>/port/bld_src, this rewrites absolute paths (old folder name ->
new) in text build files, in .ninja_deps path records, and re-hashes .ninja_log command hashes
(Ninja uses rapidhash of the command line) so Ninja sees the copy as up to date.
  python reloc.py verify   check that hashtool reproduces the existing .ninja_log hashes
  python reloc.py apply    rename bld_src -> bld and rewrite
Needs hashtool.exe built from hashtool.cpp + rapidhash.h (https://github.com/Nicoshev/rapidhash, MIT; not bundled).
Experimental; verify before trusting.
"""
import os, sys, re, json, struct, subprocess, shutil
OLD=os.environ.get('SF_RELOC_OLD','work-a'); NEW=os.environ.get('SF_RELOC_NEW','work-b')   # old/new folder names
D=os.environ.get('SF_RELOC_PORT') or sys.exit('set SF_RELOC_PORT to the NEW copy\'s port folder (with bld_src = copied bld)')
SRC=os.path.join(D,'bld_src'); BLD=os.path.join(D,'bld')
NINJA=os.environ.get('NINJA','ninja')
HT=os.environ.get('SF_HASHTOOL', os.path.join(os.path.dirname(os.path.abspath(__file__)),'hashtool.exe'))
pat=re.compile(re.escape(OLD),re.I)
def hashes(cmds):
    p=subprocess.run([HT],input='\n'.join(cmds)+'\n',capture_output=True,text=True)
    return p.stdout.split()
def readlog(path):
    lines=open(path,encoding='utf-8',errors='surrogateescape').read().split('\n')
    return lines
mode=sys.argv[1]
if mode=='verify':
    cdb=json.loads(subprocess.run([NINJA,'-C',SRC,'-t','compdb'],capture_output=True,text=True).stdout)
    m={}
    for e in cdb: m[e['output'].replace('\\','/')]=e['command']
    lines=readlog(os.path.join(SRC,'.ninja_log'))[1:]
    outs=[];cmds=[];old=[]
    for l in lines:
        f=l.split('\t')
        if len(f)<5: continue
        if f[3] in m: outs.append(f[3]); cmds.append(m[f[3]]); old.append(f[4])
    hs=hashes(cmds); ok=sum(1 for a,b in zip(hs,old) if a==b)
    print('compdb',len(m),'log-matched',len(outs),'hash-equal',ok)
    for o,a,b in list(zip(outs,hs,old))[:3]: print(o,a,b)
elif mode=='apply':
    if os.path.exists(BLD): sys.exit('bld exists')
    os.rename(SRC,BLD)
    # rename dirs containing OLD
    for root,dirs,files in os.walk(BLD,topdown=False):
        for dn in dirs:
            if pat.search(dn): os.rename(os.path.join(root,dn),os.path.join(root,pat.sub(NEW,dn)))
    # text files
    n=0
    for root,dirs,files in os.walk(BLD):
        for fn in files:
            p=os.path.join(root,fn)
            if fn.endswith(('.obj','.lib','.exe','.pdb','.ilk','.ninja_deps','.ninja_log')) or fn in('.ninja_deps','.ninja_log'): continue
            try: b=open(p,'rb').read()
            except: continue
            if len(b)>50_000_000 or b'\0' in b[:4096]: continue
            t=b.decode('latin-1')
            if pat.search(t):
                st=os.stat(p); open(p,'wb').write(pat.sub(NEW,t).encode('latin-1')); os.utime(p,ns=(st.st_atime_ns,st.st_mtime_ns)); n+=1
    print('text files rewritten',n)
    # deps
    p=os.path.join(BLD,'.ninja_deps'); b=open(p,'rb').read(); st=os.stat(p)
    hdr=b'# ninjadeps\n'; assert b.startswith(hdr); i=len(hdr)+4; out=bytearray(b[:i]); npath=0
    while i<len(b):
        sz,=struct.unpack_from('<I',b,i); isdeps=sz>>31; sz&=0x7fffffff; rec=b[i+4:i+4+sz]; i+=4+sz
        if isdeps: out+=struct.pack('<I',sz|0x80000000)+rec; continue
        path=rec[:-4].rstrip(b'\0'); chk=rec[-4:]
        path=pat.sub(NEW,path.decode('latin-1')).encode('latin-1'); npath+=1
        pad=(4-len(path)%4)%4; body=path+b'\0'*pad+chk
        out+=struct.pack('<I',len(body))+body
    open(p,'wb').write(out); os.utime(p,ns=(st.st_atime_ns,st.st_mtime_ns)); print('deps paths',npath)
    # log
    cdb=json.loads(subprocess.run([NINJA,'-C',BLD,'-t','compdb'],capture_output=True,text=True).stdout)
    m={e['output'].replace('\\','/'):e['command'] for e in cdb}
    p=os.path.join(BLD,'.ninja_log'); lines=readlog(p); st=os.stat(p)
    ents=[]
    for l in lines[1:]:
        f=l.split('\t')
        if len(f)<5: continue
        f[3]=pat.sub(NEW,f[3]); ents.append(f)
    idx=[k for k,f in enumerate(ents) if f[3] in m]
    hs=hashes([m[ents[k][3]] for k in idx])
    for k,h in zip(idx,hs): ents[k][4]=h
    open(p,'w',encoding='utf-8',errors='surrogateescape',newline='\n').write(lines[0]+'\n'+''.join('\t'.join(f)+'\n' for f in ents))
    print('log entries',len(ents),'rehashed',len(idx))
