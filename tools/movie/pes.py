import sys,struct
p=sys.argv[1]; want=int(sys.argv[2]) if len(sys.argv)>2 else 12
f=open(p,'rb'); h=f.read(0x800); hs=struct.unpack_from('>I',h,8)[0]*0x800
f.seek(hs); data=f.read(8<<20)
i=0; shown={}
def ts(b): return ((b[0]>>1)&7)<<30 | b[1]<<22 | (b[2]>>1)<<15 | b[3]<<7 | b[4]>>1
packs=0
while i+4<=len(data) and sum(shown.values())<want*3:
    if data[i:i+3]!=b'\0\0\1': print('desync at',hex(i),data[i:i+8].hex()); break
    sid=data[i+3]
    if sid==0xBA:
        stuff=data[i+13]&7; i+=14+stuff; packs+=1; continue
    ln=struct.unpack_from('>H',data,i+4)[0]
    pkt=data[i+6:i+6+ln]
    if sid in (0xE0,0xBD):
        hl=pkt[2]; flags=pkt[1]; pts=dts=None
        if flags&0x80: pts=ts(pkt[3:8])
        if flags&0x40: dts=ts(pkt[8:13])
        pay=pkt[3+hl:]
        key=(sid,pay[0] if sid==0xBD else 0)
        n=shown.get(key,0)
        if n<want:
            print(f'pack{packs} off={hex(hs+i)} sid={sid:02X} len={ln} pts={pts} dts={dts} hl={hl} pay[:40]={pay[:40].hex()}')
            shown[key]=n+1
    i+=6+ln
