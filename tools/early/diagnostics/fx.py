import sys,os,re,json,glob
# Plan D helper: index func_XXXXXXXX bodies in your local lifted ppu_recomp_*.cpp, then print one quickly.
#   python fx.py index            python fx.py show func_0007C008 [...]
R=os.environ.get('SF_RECOMP_DIR') or sys.exit('set SF_RECOMP_DIR to your local port/recompiled folder')
IDX=os.path.join(R,'funcidx.json')
if sys.argv[1]=='index':
    idx={}
    for f in sorted(glob.glob(os.path.join(R,'ppu_recomp_*.cpp'))):
        off=0
        with open(f,'rb') as fh:
            for line in fh:
                if line.startswith(b'void func_'):
                    idx[line[5:18].decode()]=(os.path.basename(f),off)
                off+=len(line)
    json.dump(idx,open(IDX,'w')); print(len(idx))
else:
    idx=json.load(open(IDX)); out=[]
    for name in sys.argv[2:]:
        fn,off=idx[name]
        with open(os.path.join(R,fn),'rb') as fh:
            fh.seek(off); first=True
            for line in fh:
                if not first and line.startswith(b'void func_'): break
                first=False; out.append(line.decode('latin-1').rstrip())
    print('\n'.join(out))
