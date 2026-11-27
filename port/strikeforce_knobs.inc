/* Strikeforce port knobs: thin wrappers over the SDK HLE that the explorer
 * (sfauto) can flip with env vars. Unset env = identical to SDK behaviour,
 * plus one log line showing what the guest received.
 *   SF_FREE_KB=<n>      rewrite CellGameContentSize.hddFreeSizeKB after
 *                       cellGameBootCheck / cellGameDataCheck
 *   SF_TROPHY_REQ=<n>   rewrite sceNpTrophyGetRequiredDiskSpace's *reqSpace
 */
extern "C" s32 cellGameBootCheck(u32* type, u32* attributes, void* size, char* dirName);
extern "C" s32 cellGameDataCheck(u32 type, const char* dirName, void* size);
extern "C" s32 sceNpTrophyGetRequiredDiskSpace(s32 context, s32 handle, u64* reqSpace, u64 options);
namespace sf_knob {
using sf_lfq::r32; using sf_lfq::w32; using sf_lfq::w64;
static long envl(const char* n, long dflt) { const char* e = getenv(n); return (e && *e) ? strtol(e, 0, 0) : dflt; }
static void size_fix(const char* who, uint32_t size_ea, s32 rc)
{
    if (!size_ea) return;
    const long fk = envl("SF_FREE_KB", -1);
    if (fk >= 0) w32(size_ea, (uint32_t)fk);
    fprintf(stderr, "[sf-knob] %s rc=0x%08X hddFreeSizeKB=%d sizeKB=%d sysSizeKB=%d%s\n", who, (uint32_t)rc,
            (int32_t)r32(size_ea), (int32_t)r32(size_ea + 4), (int32_t)r32(size_ea + 8), fk >= 0 ? " (SF_FREE_KB)" : "");
}
static void hle_bootcheck(ppu_context* ctx)
{
    const uint32_t size_ea = (uint32_t)ctx->gpr[5];
    s32 rc = cellGameBootCheck((u32*)(uintptr_t)(uint32_t)ctx->gpr[3], (u32*)(uintptr_t)(uint32_t)ctx->gpr[4],
                               (void*)(uintptr_t)size_ea, (char*)(uintptr_t)(uint32_t)ctx->gpr[6]);
    size_fix("BootCheck", size_ea, rc); ctx->gpr[3] = (uint32_t)rc;
}
static void hle_datacheck(ppu_context* ctx)
{
    const uint32_t size_ea = (uint32_t)ctx->gpr[5];
    s32 rc = cellGameDataCheck((u32)ctx->gpr[3], (const char*)(uintptr_t)(uint32_t)ctx->gpr[4], (void*)(uintptr_t)size_ea);
    size_fix("DataCheck", size_ea, rc); ctx->gpr[3] = (uint32_t)rc;
}
static void hle_trophy_req(ppu_context* ctx)
{
    const uint32_t req_ea = (uint32_t)ctx->gpr[5];
    s32 rc = sceNpTrophyGetRequiredDiskSpace((s32)ctx->gpr[3], (s32)ctx->gpr[4], (u64*)(uintptr_t)req_ea, ctx->gpr[6]);
    const long v = envl("SF_TROPHY_REQ", -1);
    if (v >= 0 && req_ea && rc == 0) w64(req_ea, (uint64_t)v);
    fprintf(stderr, "[sf-knob] TrophyRequiredDiskSpace rc=0x%08X req=%u:%u%s\n", (uint32_t)rc,
            req_ea ? r32(req_ea) : 0, req_ea ? r32(req_ea + 4) : 0, v >= 0 ? " (SF_TROPHY_REQ)" : "");
    ctx->gpr[3] = (uint32_t)rc;
}
} /* namespace sf_knob */
static void sf_register_knob_overrides(void)
{
    ps3_hle_register_ctx(0xF52639EAu, "cellGameBootCheck[sf-knob]", sf_knob::hle_bootcheck);
    ps3_hle_register_ctx(0xDB9819F3u, "cellGameDataCheck[sf-knob]", sf_knob::hle_datacheck);
    ps3_hle_register_ctx(0x370136FEu, "sceNpTrophyGetRequiredDiskSpace[sf-knob]", sf_knob::hle_trophy_req);
}
