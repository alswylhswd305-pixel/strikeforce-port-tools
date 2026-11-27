import struct, math
f32=lambda x: struct.unpack('f',struct.pack('f',x))[0]
def mul(a,b): return f32(f32(a)*f32(b))
# UB normalized decode k/255 (float32, correctly rounded as on CPU), then shader rescales
for scale,name in ((255.0,'x255'),(765.0,'x765 (3 vec4 per bone)'),(1020.0,'x1020 (4 vec4 per bone)')):
    bad=[k for k in range(256) if math.floor(mul(f32(k/255.0),scale)) != round(k*scale/255.0)]
    print(f"UB k/255 then {name}: floor() differs from exact for {len(bad)} of 256 k values; first: {bad[:12]}")
# UB256 decoded as UB by mistake: index collapses
for k in (0,1,7,30,255):
    print(f" byte {k}: UB256 raw -> {float(k)}; if wrongly /255 -> {f32(k/255.0):.6f} -> c[base + floor(x*3)] uses offset {math.floor(f32(k/255.0)*3)} instead of {k*3}")
# constant limit
for base,idx in ((400,20),(440,10),(460,4)):
    c=base+idx*3
    print(f" bone {idx} at base c{base}, 3 vec4/bone -> rows c{c}..c{c+2}: {'beyond 467 -> RPCS3 reads 0 / write dropped' if c+2>=468 else 'inside 0..467'}")
print(" (a0+imm)&511:", (500+20)&511, (0+511)&511)
