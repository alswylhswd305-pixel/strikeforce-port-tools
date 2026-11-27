# Lift YOUR decrypted EBOOT with ps3recomp's own tools. Output stays in $SF_ROOT (git-ignored, never published).
$ErrorActionPreference = 'Continue'; $d = $env:SF_ROOT; $t = "$d\ps3recomp\tools"
python "$t\ppu_loader.py" $env:SF_ELF -o "$d\out" *> "$d\logs\01_ppu_loader.log"
python "$t\ppu_lifter.py" $env:SF_ELF --functions "$d\out\EBOOT.functions.json" --hle-stubs "$d\out\EBOOT.imports.json" --output "$d\port\recompiled" *> "$d\logs\02_ppu_lifter.log"
# SPU: v0.20.0's PORT_SPU_INPUTS configure fails on image 375200614 (overlapping PT_LOAD), so use the documented
# partial path: 40/41 images lifted into port\spu, then the SPU_DIR workflow.
python "$t\build_spu_workloads.py" --input $env:SF_ELF --lifted "$d\port\spu" --out "$d\port\spu\spu_workloads.c" --constructor --allow-partial *> "$d\logs\03a_spu_workloads.log"
"lift done (see $d\logs)"
