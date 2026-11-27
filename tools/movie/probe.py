import struct,sys,os,collections
d=sys.argv[1]
for f in sorted(os.listdir(d))[:int(sys.argv[2]) if len(sys.argv)>2 else 99]:
    p=os.path.join(d,f); sz=os.path.getsize(p)
    h=open(p,'rb').read(0x800)
    print(f"== {f} size={sz}")
    if h[:4]!=b'PAMF': print(' not PAMF', h[:16].hex()); continue
    hs=struct.unpack_from('>I',h,8)[0]; ds=struct.unpack_from('>I',h,12)[0]
    print(' ver',h[4:8], 'hdr_sectors',hs,'data_size_sectors',ds)
    print(' hdr hex 0x00-0x100:'); 
    for o in range(0,0x100,16): print('  %03X'%o, h[o:o+16].hex(' '))
    n=h[0x87]
    for i in range(n):
        o=0x88+i*0x30; print('  st%d'%i, h[o:o+0x30].hex(' '))
    # scan first 2MB of data for PES ids
    fp=open(p,'rb'); fp.seek(hs*0x800); data=fp.read(min(4<<20,sz-hs*0x800))
    c=collections.Counter(); i=0; sub=collections.Counter()
    while True:
        j=data.find(b'\x00\x00\x01',i)
        if j<0 or j+4>len(data): break
        sid=data[j+3]
        if sid>=0xB9: c[sid]+=1
        if sid==0xBD and j+9<len(data):
            hl=data[j+8]; sub[data[j+9+hl]]+=1
        i=j+3
    print(' ids',{hex(k):v for k,v in c.items()}, 'bd_sub',{hex(k):v for k,v in sub.items()})
    # find SPS
    k=data.find(b'\x00\x00\x01\x67')
    if k>=0: print(' SPS profile',data[k+4],'level',data[k+6])
    print(' first pack', data[:64].hex(' '))
