import sys
from minidump.minidumpfile import MinidumpFile
md=MinidumpFile.parse(sys.argv[1]); tids=[int(x) for x in sys.argv[2].split(',')] if len(sys.argv)>2 else None
mods=[(m.baseaddress,m.baseaddress+m.size,m.name.split('\\')[-1]) for m in md.modules.modules]
def where(a):
    for b,e,n in mods:
        if b<=a<e: return n,a-b
    return None
rd=md.get_reader()
for t in md.threads.threads:
    if tids and t.ThreadId not in tids: continue
    ctx=t.ContextObject
    rip=getattr(ctx,'Rip',0); rsp=getattr(ctx,'Rsp',0)
    print(f"== tid {t.ThreadId} rip={where(rip)} rsp={rsp:#x}")
    try: data=rd.read(rsp, 0x6000)
    except Exception as ex:
        try: data=rd.read(rsp,0x1000)
        except Exception as ex2: print(' stack unreadable',ex2); continue
    out=[]
    for i in range(0,len(data)-8,8):
        v=int.from_bytes(data[i:i+8],'little'); w=where(v)
        if w and w[1]>0x1000: out.append(f"{w[0]}+{w[1]:#x}")
        if len(out)>=28: break
    print('  '+' '.join(out))
