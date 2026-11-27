/* Strikeforce port: cellVideoOutGetDeviceInfo (NID 0x1E930EEF) with the SDK
 * struct layout. The v0.20 SDK HLE omits the 0x14-byte colorInfo block, so its
 * mode table lands at +0x0C instead of +0x20 and every mode has refreshRates=0.
 * PSGL's mode picker (guest 0x52CD60) reads modes at info+0x20 and requires
 * (refreshRates & wanted) != 0, so it found no 1280x720 mode, device setup
 * (0x4C9E54) failed, the heap setup (0x4CA260) was skipped and the first
 * allocation from the game heap returned NULL (the opd 0x7190 null bctr).
 * Layout (big-endian guest memory):
 *   +0x00 portType u8   +0x01 colorSpace u8  +0x02 latency u16
 *   +0x04 availableModeCount u8  +0x05 state u8  +0x06 rgbOutputRange u8
 *   +0x0C colorInfo (8 x u16 + u32 gamma)    +0x20 availableModes[32] x 8
 *   +0x120 ksvList                           total 0x1C8
 * Mode set = one 720p progressive 16:9 mode at 59.94/60 Hz (the same
 * thing an emulator reports when configured for 720p). SF_VIDEO_MODES=1080
 * adds 1080p as well. */
namespace sf_vo {
using sf_lfq::P; using sf_lfq::w16; using sf_lfq::w32;
static void hle_get_device_info(ppu_context* ctx)
{
    const uint32_t videoOut = (uint32_t)ctx->gpr[3], idx = (uint32_t)ctx->gpr[4], info = (uint32_t)ctx->gpr[5];
    if (!info) { ctx->gpr[3] = 0x8002B222u; return; }           /* ILLEGAL_PARAMETER */
    if (videoOut != 0 || idx != 0) { ctx->gpr[3] = 0x8002B224u; return; } /* DEVICE_NOT_FOUND */
    uint8_t* p = P(info);
    memset(p, 0, 0x1C8);
    p[0] = 0x01;            /* HDMI */
    p[1] = 0x01;            /* RGB */
    w16(info + 2, 100);     /* latency */
    p[5] = 0x01;            /* DEVICE_STATE_AVAILABLE */
    p[6] = 0x01;            /* rgbOutputRange full */
    for (int i = 0; i < 8; i++) w16(info + 0x0C + 2 * i, 0xFFFF);
    w32(info + 0x1C, 100);  /* gamma */
    int n = 0;
    auto add = [&](uint8_t res, uint8_t scan, uint8_t conv, uint8_t aspect) {
        const uint32_t m = info + 0x20 + 8 * n++;
        P(m)[0] = res; P(m)[1] = scan; P(m)[2] = conv; P(m)[3] = aspect;
        w16(m + 6, 0x0001 | 0x0004);   /* 59.94 Hz | 60 Hz */
    };
    add(2 /*720*/, 1 /*progressive*/, 0, 2 /*16:9*/);
    const char* e = getenv("SF_VIDEO_MODES");
    if (e && strstr(e, "1080")) add(1 /*1080*/, 1, 0, 2);
    p[4] = (uint8_t)n;
    fprintf(stderr, "[sf-vo] GetDeviceInfo(out=%u, dev=%u) -> %d mode(s), first 720p prog 16:9 rr=0x0005\n", videoOut, idx, n);
    ctx->gpr[3] = 0;
}
} /* namespace sf_vo */
static void sf_register_videoout_overrides(void)
{
    ps3_hle_register_ctx(0x1E930EEFu, "cellVideoOutGetDeviceInfo[sf-vo]", sf_vo::hle_get_device_info);
}
