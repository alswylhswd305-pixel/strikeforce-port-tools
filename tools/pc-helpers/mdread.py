# Minimal minidump reader (stdlib): module bases + Memory64List; read host VA / guest EA.
import struct,sys,mmap,bisect
class MD:
    def __init__(s,p):
        s.f=open(p,"rb"); s.m=mmap.mmap(s.f.fileno(),0,access=mmap.ACCESS_READ)
        sig,ver,ns,sdir=struct.unpack_from("<IIII",s.m,0); s.mods={}; s.rng=[]
        for i in range(ns):
            t,sz,rva=struct.unpack_from("<III",s.m,sdir+12*i)
            if t==4:
                n=struct.unpack_from("<I",s.m,rva)[0]
                for k in range(n):
                    o=rva+4+108*k; base,size=struct.unpack_from("<QI",s.m,o); nrva=struct.unpack_from("<I",s.m,o+20)[0]
                    ln=struct.unpack_from("<I",s.m,nrva)[0]; name=s.m[nrva+4:nrva+4+ln].decode("utf-16le")
                    s.mods[name.split("\\")[-1].lower()]=(base,size)
            if t==9:
                n,brva=struct.unpack_from("<QQ",s.m,rva); off=brva
                for k in range(n):
                    st,ds=struct.unpack_from("<QQ",s.m,rva+16+16*k); s.rng.append((st,ds,off)); off+=ds
        s.rng.sort(); s.starts=[r[0] for r in s.rng]
    def read(s,va,n):
        i=bisect.bisect_right(s.starts,va)-1
        if i<0: return None
        st,ds,off=s.rng[i]
        if va+n>st+ds: return None
        return s.m[off+va-st:off+va-st+n]
    def q(s,va): b=s.read(va,8); return struct.unpack("<Q",b)[0] if b else None
