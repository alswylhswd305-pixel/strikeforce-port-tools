#!/bin/sh
# Box harness: builds the PATCHED decompiler (from ../patched or $PATCHED) and the key logic
# extracted from the patched backend, then runs the checks against the 1776 dumps.
set -e
H=$(cd "$(dirname "$0")" && pwd)
P=${PATCHED:-$H/../patched}
INC=${PS3INC:-/workspace/ps3recomp-study/include}
DUMPS=${DUMPS:-/workspace/clothv2/r1776/cwd_1776}
W=$(mktemp -d)
tr -d '\r' < "$P/rsx_vp_decompiler.c" > "$W/rsx_vp_decompiler.c"
tr -d '\r' < "$P/rsx_vp_decompiler.h" > "$W/rsx_vp_decompiler.h"
# key logic: vp_hash_ucode + vp_branch_key_bits from the patched backend, verbatim
tr -d '\r' < "$P/sh_work.c" > "$W/be.c"
{ sed -n '/^static u32 vp_hash_ucode/,/^}/p' "$W/be.c"
  echo '#define PS3_LOG_FIRST(v,n) ((v)++ < (n))'
  sed -n '/^static u32 vp_branch_key_bits/,/^}/p' "$W/be.c"
  # the fold, verbatim from vp_get_vs, wrapped in a function
  echo 'static u32 key_of(const rsx_state* st, const u8* vuc, u32 vlen) {'
  sed -n '/^static int vp_get_vs/,/^}/p' "$W/be.c" | sed -n '/u32 hash = vp_hash_ucode(vuc, vlen);/,/^    }$/p'
  echo '    (void)ucode_hash; return hash; }'
} > "$W/key_logic.inc"
cp "$H/test_branch_bits.c" "$W/"
cd "$W"
for CC in gcc clang; do
  command -v $CC >/dev/null || continue
  $CC -std=c99 -Wall -Wextra -Wno-unused-parameter -I"$INC" -I. -o t_$CC test_branch_bits.c rsx_vp_decompiler.c 2> build_$CC.log
  echo "== $CC ($(wc -l < build_$CC.log) warning lines)"; cat build_$CC.log
  ./t_$CC "$DUMPS" || echo "exit $?"
done
cp out_6A46C9BA_bits0.hlsl out_6A46C9BA_bits1.hlsl key_logic.inc "$H/"
