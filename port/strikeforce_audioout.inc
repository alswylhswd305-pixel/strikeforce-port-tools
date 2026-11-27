/* Strikeforce port: cellAudioOutGetDeviceInfo (NID 0x7663E368) and
 * cellAudioOutGetState (NID 0xF4E3CAA0) with the SDK struct layout.
 *
 * The v0.20 SDK HLE uses a packed 4-byte SoundMode (no layout u32) and omits
 * the u16 latency, so DeviceInfo modes land at +6 instead of +8 and the
 * struct is 70 bytes instead of 136. GetState writes downMixer at +4 and
 * soundMode at +8 instead of +8 / +12 (size 20). It also stores device
 * state=2, which is not AVAILABLE (1).
 *
 * A title reading the official layout therefore sees fs=0 / channel=0 at
 * soundMode (+12) and an invalid device state — a source of silence.
 *
 * Layout (big-endian guest memory), same as the public Cell SDK / RPCS3:
 *   CellAudioOutSoundMode (8): +0 type, +1 channel, +2 fs, +3 reserved, +4 layout u32
 *   CellAudioOutDeviceInfo (136):
 *     +0 portType u8, +1 availableModeCount u8, +2 state u8, +3 reserved[3],
 *     +6 latency u16, +8 availableModes[16]
 *   CellAudioOutState (20):
 *     +0 state u8, +1 encoder u8, +2 reserved[6], +8 downMixer u32, +12 soundMode
 * Device state AVAILABLE=1, output state ENABLED=0, latency=13, 48 kHz LPCM. */
namespace sf_ao {
using sf_lfq::P; using sf_lfq::w16; using sf_lfq::w32;
enum { SZ_DEV = 136, SZ_STATE = 20 };
static const uint32_t E_ILLEGAL = 0x8002B242u, E_NOTFOUND = 0x8002B244u;
static void write_mode(uint32_t ea, uint8_t type, uint8_t ch, uint8_t fs, uint32_t layout)
{
    uint8_t* p = P(ea);
    p[0] = type; p[1] = ch; p[2] = fs; p[3] = 0;
    w32(ea + 4, layout);
}
static void hle_get_device_info(ppu_context* ctx)
{
    const uint32_t audioOut = (uint32_t)ctx->gpr[3], idx = (uint32_t)ctx->gpr[4], info = (uint32_t)ctx->gpr[5];
    if (!info) { ctx->gpr[3] = E_ILLEGAL; return; }
    if (audioOut != 0 || idx != 0) { ctx->gpr[3] = E_NOTFOUND; return; }
    memset(P(info), 0, SZ_DEV);
    P(info)[0] = 0;             /* HDMI */
    P(info)[1] = 3;             /* 2ch / 5.1 / 7.1 LPCM */
    P(info)[2] = 1;             /* DEVICE_STATE_AVAILABLE */
    w16(info + 6, 13);          /* latency */
    write_mode(info + 8,  0, 2, 0x04, 0x00000001u); /* LPCM 2ch 48k  LAYOUT_2CH */
    write_mode(info + 16, 0, 6, 0x04, 0x00010000u); /* LPCM 5.1      LAYOUT_6CH */
    write_mode(info + 24, 0, 8, 0x04, 0x40000000u); /* LPCM 7.1      LAYOUT_8CH */
    fprintf(stderr, "[sf-ao] GetDeviceInfo(out=%u, dev=%u) -> 3 LPCM modes, state=AVAILABLE, latency=13\n",
            audioOut, idx);
    ctx->gpr[3] = 0;
}
static void hle_get_state(ppu_context* ctx)
{
    const uint32_t audioOut = (uint32_t)ctx->gpr[3], idx = (uint32_t)ctx->gpr[4], st = (uint32_t)ctx->gpr[5];
    if (!st) { ctx->gpr[3] = E_ILLEGAL; return; }
    if (audioOut != 0 || idx != 0) { ctx->gpr[3] = E_NOTFOUND; return; }
    memset(P(st), 0, SZ_STATE);
    P(st)[0] = 0;               /* OUTPUT_STATE_ENABLED */
    P(st)[1] = 0;               /* LPCM */
    w32(st + 8, 0);             /* downMixer NONE */
    write_mode(st + 12, 0, 2, 0x04, 0x00000001u);
    fprintf(stderr, "[sf-ao] GetState(out=%u, dev=%u) -> ENABLED LPCM 2ch 48k, downMixer=0\n",
            audioOut, idx);
    ctx->gpr[3] = 0;
}
} /* namespace sf_ao */
static void sf_register_audioout_overrides(void)
{
    ps3_hle_register_ctx(0x7663E368u, "cellAudioOutGetDeviceInfo[sf-ao]", sf_ao::hle_get_device_info);
    ps3_hle_register_ctx(0xF4E3CAA0u, "cellAudioOutGetState[sf-ao]", sf_ao::hle_get_state);
}
