static u32 vp_hash_ucode(const u8* p, u32 n)
{
    u32 h = 2166136261u;
    for (u32 i = 0; i < n; i++) { h ^= p[i]; h *= 16777619u; }
    return h ? h : 1u;
}
#define PS3_LOG_FIRST(v,n) ((v)++ < (n))
static u32 vp_branch_key_bits(const rsx_state* st, const u8* vuc, u32 vlen)
{
    extern u32 rsx_vp_branch_bits_mask(const u8*, u32);
    static int off = -1;
    if (off < 0) off = getenv("VP_BRANCH_BITS_OFF") ? 1 : 0;
    if (off || !st) return 0;
    return st->transform_branch_bits & rsx_vp_branch_bits_mask(vuc, vlen);
}
static u32 key_of(const rsx_state* st, const u8* vuc, u32 vlen) {
    u32 hash = vp_hash_ucode(vuc, vlen);
    const u32 ucode_hash = hash;
    const u32 vp_bb = vp_branch_key_bits(st, vuc, vlen);
    if (vp_bb) {   /* fold the tested bits into the cache key (and the PSO's vs_hash) */
        for (int k = 0; k < 4; k++) { hash ^= (vp_bb >> (8 * k)) & 0xFFu; hash *= 16777619u; }
        if (!hash) hash = 1u;
    }
    (void)ucode_hash; return hash; }
