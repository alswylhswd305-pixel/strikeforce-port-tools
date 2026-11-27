/* Strikeforce port override: cellL10n UCS2stoUTF8s (NID 0x2AD091C6), clean-room.
 * s32 UCS2stoUTF8s(const u16* src, u32* src_len, u8* dst, u32* dst_len)
 * src_len in UCS-2 units; dst_len in = capacity, out = bytes produced.
 * Returns 0 ConversionOK, 1 SRCIllegal (surrogate), 2 DSTExhausted.
 * v0.20.0 fakes this as CELL_OK without writing, so the game's message
 * dialog text arrives empty. Relies on sf_lfq::r16/r32/w32/P helpers. */
namespace sf_l10n {
using sf_lfq::P; using sf_lfq::r16; using sf_lfq::r32; using sf_lfq::w32;
static std::atomic<unsigned> g_n{0};
static void hle_ucs2_to_utf8s(ppu_context* ctx)
{
    const uint32_t src = (uint32_t)ctx->gpr[3], pslen = (uint32_t)ctx->gpr[4];
    const uint32_t dst = (uint32_t)ctx->gpr[5], pdlen = (uint32_t)ctx->gpr[6];
    if (!pslen || !pdlen) { ctx->gpr[3] = 1; return; }
    const uint32_t slen = r32(pslen), cap = r32(pdlen);
    uint32_t out = 0, i = 0, rc = 0;
    for (; i < slen; i++) {
        const uint32_t c = r16(src + 2 * i);
        uint8_t b[3]; uint32_t n;
        if (c >= 0xD800 && c <= 0xDFFF) { rc = 1; break; }
        if (c < 0x80) { b[0] = (uint8_t)c; n = 1; }
        else if (c < 0x800) { b[0] = (uint8_t)(0xC0 | (c >> 6)); b[1] = (uint8_t)(0x80 | (c & 0x3F)); n = 2; }
        else { b[0] = (uint8_t)(0xE0 | (c >> 12)); b[1] = (uint8_t)(0x80 | ((c >> 6) & 0x3F)); b[2] = (uint8_t)(0x80 | (c & 0x3F)); n = 3; }
        if (dst) {
            if (out + n > cap) { rc = 2; break; }
            memcpy(P(dst + out), b, n);
        }
        out += n;
    }
    if (rc) w32(pslen, slen - i);
    w32(pdlen, out);
    if (dst && rc == 0 && out < cap) *P(dst + out) = 0;
    if (g_n++ < 16) {
        char preview[96] = {0};
        if (dst) { uint32_t k = out < 95 ? out : 95; memcpy(preview, P(dst), k); }
        fprintf(stderr, "[sf-l10n] UCS2stoUTF8s(src=0x%08X len=%u cap=%u) -> rc=%u out=%u \"%s\"\n",
                src, slen, cap, rc, out, preview);
    }
    ctx->gpr[3] = rc;
}
} /* namespace sf_l10n */
static void sf_register_l10n_overrides(void)
{
    ps3_hle_register_ctx(0x2AD091C6u, "UCS2stoUTF8s[sf-port]", sf_l10n::hle_ucs2_to_utf8s);
}
