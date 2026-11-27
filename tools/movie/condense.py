import re,sys
src,a,b,out=sys.argv[1],int(sys.argv[2]),int(sys.argv[3]),sys.argv[4]
L=open(src,encoding='utf-8',errors='replace').read().split('\n')[a-1:b]
o=[]
for s in L:
    s=s.strip()
    if 'DRAIN_TRAMPOLINE' in s: s=s.replace(' DRAIN_TRAMPOLINE(ctx);','')
    if s=='ctx->gpr[2] = vm_read64(ctx->gpr[1] + 0x28);': continue
    m=re.match(r'\{ int64_t a = \(int(\d+)_t\)ctx->gpr\[(\d+)\]; int64_t b = (?:\(int64_t\)|\(u?int\d+_t\)ctx->gpr\[)?([^;\]]*)\]?; .*cr & ~\(0xFu << (\d+)\)',s)
    m2=re.match(r'\{ uint(\d+)_t a = \(uint\d+_t\)ctx->gpr\[(\d+)\]; uint\d+_t b = (?:\(uint\d+_t\))?([^;]*); .*cr & ~\(0xFu << (\d+)\)',s)
    if m: s=f'cmp{m.group(1)} cr{7-int(m.group(4))//4}, r{m.group(2)}, {m.group(3)}'
    elif m2: s=f'cmpl{m2.group(1)} cr{7-int(m2.group(4))//4}, r{m2.group(2)}, {m2.group(3).replace("ctx->gpr[","r").replace("]","")}'
    s=re.sub(r'ctx->gpr\[(\d+)\]',r'r\1',s)
    s=re.sub(r'\(\(ctx->cr >> (\d+)\) & 1\)',lambda m:f'cr{7-int(m.group(1))//4}.{["so","eq","gt","lt"][int(m.group(1))%4]}',s)
    s=s.replace('(int64_t)(int32_t)','').replace('(int64_t)','')
    o.append(s)
open(out,'w').write('\n'.join(o))
