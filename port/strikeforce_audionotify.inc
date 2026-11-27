/* Strikeforce port: cellAudioSetNotifyEventQueue (NID 0x377E0CD9).
 *
 * play16 (20261126-083638-39c869) was 100% silent: the mix thread ran at
 * 187.5 blocks/s with peak=0, no underruns, port 0 ring empty. Cause:
 *   * _cellsurMixerMain created evq id=1 key=0x8000CAFE02460300 (depth 2)
 *     and blocked on sys_event_queue_receive (9s timeout; 22 wakes in a
 *     long run = timeouts only).
 *   * The game called cellAudioSetNotifyEventQueue(0). Firmware and RPCS3
 *     remap 0 to the _mxr000 key 0x8000CAFE02460300. This runtime's
 *     sys_event_find_queue_by_key(0) returns 0, so no mix events were posted.
 *
 * This wrapper remaps 0 to that key, then calls the SDK HLE. Include after
 * strikeforce_lfqueue.inc and register from ps3_load_prx_modules(). */
extern "C" s32 cellAudioSetNotifyEventQueue(u64 key);
namespace sf_an {
static const uint64_t MXR000 = 0x8000CAFE02460300ull;
static void hle_set_notify(ppu_context* ctx)
{
    uint64_t key = ctx->gpr[3];
    if (key == 0) {
        fprintf(stderr, "[sf-an] SetNotifyEventQueue(0) remapped to 0x8000CAFE02460300 (_mxr000 / libmixer)\n");
        key = MXR000;
    }
    ctx->gpr[3] = (uint32_t)cellAudioSetNotifyEventQueue(key);
}
} /* namespace sf_an */
static void sf_register_audionotify_overrides(void)
{
    ps3_hle_register_ctx(0x377E0CD9u, "cellAudioSetNotifyEventQueue[sf-an]", sf_an::hle_set_notify);
}
