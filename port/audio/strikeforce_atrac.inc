/* Strikeforce port: register the cellAtrac streaming functions that v0.20
 * left unregistered (faked CELL_OK, out-params untouched). The
 * implementations live in the patched libs/codec/cellAtrac.c.
 *
 *   0x2BFFF084  cellAtracGetStreamDataInfo
 *   0x46CFC013  cellAtracAddStreamData
 *   0x06DDB53E  cellAtracSetSecondBuffer
 *   0x99EFE171  cellAtracIsSecondBufferNeeded
 *   0x99FB73D1  cellAtracGetBufferInfoForResetting
 *   0xBE07F05E  cellAtracGetSecondBufferInfo
 *   0xC9A95FCB  cellAtracGetVacantSize
 *
 * Apply the cellAtrac.c / .h patch first, then include this after the other
 * strikeforce_*.inc files and call sf_register_atrac_overrides() from
 * ps3_load_prx_modules() in port/stubs.cpp. This is a safety net if
 * gen_hle_nids is not regenerated on the test-folder rebuild. */
extern "C" s32 cellAtracGetStreamDataInfo(u32, u32, u32, u32);
extern "C" s32 cellAtracAddStreamData(u32, u32);
extern "C" s32 cellAtracSetSecondBuffer(u32, u32, u32);
extern "C" s32 cellAtracIsSecondBufferNeeded(u32);
extern "C" s32 cellAtracGetBufferInfoForResetting(u32, u32, u32);
extern "C" s32 cellAtracGetSecondBufferInfo(u32, u32, u32);
extern "C" s32 cellAtracGetVacantSize(u32, u32);
extern "C" void ps3_hle_register(unsigned int nid, const char* name, void* handler);
static void sf_register_atrac_overrides(void)
{
    ps3_hle_register(0x2BFFF084u, "cellAtracGetStreamDataInfo[sf]", (void*)cellAtracGetStreamDataInfo);
    ps3_hle_register(0x46CFC013u, "cellAtracAddStreamData[sf]", (void*)cellAtracAddStreamData);
    ps3_hle_register(0x06DDB53Eu, "cellAtracSetSecondBuffer[sf]", (void*)cellAtracSetSecondBuffer);
    ps3_hle_register(0x99EFE171u, "cellAtracIsSecondBufferNeeded[sf]", (void*)cellAtracIsSecondBufferNeeded);
    ps3_hle_register(0x99FB73D1u, "cellAtracGetBufferInfoForResetting[sf]", (void*)cellAtracGetBufferInfoForResetting);
    ps3_hle_register(0xBE07F05Eu, "cellAtracGetSecondBufferInfo[sf]", (void*)cellAtracGetSecondBufferInfo);
    ps3_hle_register(0xC9A95FCBu, "cellAtracGetVacantSize[sf]", (void*)cellAtracGetVacantSize);
}
