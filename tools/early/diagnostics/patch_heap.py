import os,re,sys
# Plan C diagnostic: instrument the game heap allocator in YOUR local lifted output (no game code in this file).
# Adds [sfC-heap] logs at func_0024B078 (alloc), loc_0024B088 (fail path) and func_0049ECBC (heap setup).
# Addresses are specific to BLUS30471 as lifted by ps3recomp v0.20.0. Diagnostic only; revert before publishing builds.
R=sys.argv[1] if len(sys.argv)>1 else sys.exit('usage: patch_heap.py <port/recompiled dir>  (patches YOUR local lifted output only)')
def patch(fn, edits):
    p=os.path.join(R,fn); s=open(p,encoding='utf-8',errors='surrogateescape',newline='').read()
    nl='\r\n' if '\r\n' in s[:5000] else '\n'
    edits=[(o.replace('\n',nl),n.replace('\n',nl),c) for o,n,c in edits]
    if 'sfC-' in s: print(fn,'already patched'); return
    for old,new,count in edits:
        n=s.count(old)
        if n<1: print('MISSING in',fn,':',old[:80]); sys.exit(1)
        s=s.replace(old,new,count)
    open(p,'w',encoding='utf-8',errors='surrogateescape',newline='').write(s); print('patched',fn)
helper=r'''
/* sfC- Plan C heap instrumentation */
static void sfC_heap_dump(uint32_t heap, uint32_t sz, uint32_t al, uint32_t lr)
{
    uint32_t head = heap + 4, blk = vm_read32(heap + 0x10);
    uint32_t nfree=0,nused=0,maxfree=0,totfree=0,totused=0,n=0;
    uint32_t top[8]={0},topa[8]={0};
    while (blk && blk != head && n < 200000) {
        uint32_t bs = vm_read32(blk + 0), used = vm_read32(blk + 4);
        if (used) { nused++; totused += bs;
            for (int i=0;i<8;i++) if (bs>top[i]) { for(int j=7;j>i;j--){top[j]=top[j-1];topa[j]=topa[j-1];} top[i]=bs; topa[i]=blk; break; }
        } else { nfree++; totfree += bs; if (bs>maxfree) maxfree=bs; }
        blk = vm_read32(blk + 0xC); n++;
    }
    fprintf(stderr,"[sfC-heap] ALLOC FAIL heap=0x%08X size=0x%X align=0x%X lr=0x%08X hdr4=0x%08X first=0x%08X blocks=%u used=%u(0x%X) free=%u(0x%X) maxfree=0x%X\n",
        heap,sz,al,lr,vm_read32(heap+4),vm_read32(heap+0x10),n,nused,totused,nfree,totfree,maxfree);
    for (int i=0;i<8;i++) if (top[i]) fprintf(stderr,"[sfC-heap]   used#%d blk=0x%08X size=0x%X tag=0x%08X\n",i,topa[i],top[i],vm_read32(topa[i]+4));
    fflush(stderr);
}
'''
patch('ppu_recomp_004.cpp',[
 ('#include <math.h>\n','#include <math.h>\n'+helper,1),
 ('void func_0024B078(ppu_context* ctx) {\n    PPU_MM_SNAP\n','void func_0024B078(ppu_context* ctx) {\n    PPU_MM_SNAP\n    uint32_t _sfC_h=(uint32_t)ctx->gpr[3], _sfC_sz=(uint32_t)ctx->gpr[4], _sfC_al=(uint32_t)ctx->gpr[5], _sfC_lr=(uint32_t)ctx->lr;\n',1),
])
# insert dump at loc_0024B088 and big-alloc log at loc_0024B08C
p=os.path.join(R,'ppu_recomp_004.cpp'); s=open(p,encoding='utf-8',errors='surrogateescape',newline='').read(); L='\r\n' if '\r\n' in s[:5000] else '\n'
i=s.index('void func_0024B078(ppu_context* ctx) {')
j=s.index('loc_0024B088:'+L,i)
s=s[:j]+'loc_0024B088:\n        if (_sfC_sz >= 0x1000) sfC_heap_dump(_sfC_h,_sfC_sz,_sfC_al,_sfC_lr);'+L+s[j+len('loc_0024B088:'+L):]
j=s.index('loc_0024B08C:'+L,i)
s=s[:j]+'loc_0024B08C:\n        if (_sfC_sz >= 0x40000) { fprintf(stderr,"[sfC-heap] alloc heap=0x%08X size=0x%X align=0x%X lr=0x%08X -> 0x%08X\\n",_sfC_h,_sfC_sz,_sfC_al,_sfC_lr,(uint32_t)ctx->gpr[3]); }'+L+s[j+len('loc_0024B08C:'+L):]
open(p,'w',encoding='utf-8',errors='surrogateescape',newline='').write(s)
patch('ppu_recomp_002.cpp',[
 ('void func_0049ECBC(ppu_context* ctx) {\n    PPU_MM_SNAP\n','void func_0049ECBC(ppu_context* ctx) {\n    PPU_MM_SNAP\n    fprintf(stderr,"[sfC-heap] setup obj=0x%08X base=0x%08X size=0x%08X r6=0x%08X r7=0x%08X lr=0x%08X\\n",(uint32_t)ctx->gpr[3],(uint32_t)ctx->gpr[4],(uint32_t)ctx->gpr[5],(uint32_t)ctx->gpr[6],(uint32_t)ctx->gpr[7],(uint32_t)ctx->lr);\n',1),
])


