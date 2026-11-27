/*
 * cellAtrac streaming ring bookkeeping (no real .at3 needed).
 *
 * Builds a minimal ATRAC3plus RIFF, hands SetData only a prefix, then checks:
 *   * GetStreamDataInfo writes a write pointer / writable / file offset
 *     (the unregistered path used to return CELL_OK and leave these untouched);
 *   * AddStreamData copies the rest and then GetStreamDataInfo returns
 *     ALLDATA_IS_ONMEMORY;
 *   * Decode returns NODATA_IN_BUFFER until the next frame is fed, and
 *     GetRemainFrame is not stuck at -1 while the file is still incomplete.
 *
 * Build (from the repo root):
 *   cc -std=gnu11 -Iinclude -I runtime/ppu -o /tmp/test_cellAtrac_stream \
 *      libs/codec/tests/test_cellAtrac_stream.c
 *   /tmp/test_cellAtrac_stream
 */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>

uint8_t* vm_base;
#include "../cellAtrac.c"

int g_resv_store_active;
uint32_t g_ww_lo, g_ww_hi;
void ppu_resv_break_store(uint64_t ea) { (void)ea; }
void ps3_ww_report_inline(uint32_t a, uint64_t v, int w) { (void)a; (void)v; (void)w; }
int spu_coh_is_reserved(uint32_t a) { (void)a; return 0; }
void spu_lockline_lock(void) {}
void spu_lockline_unlock(void) {}
void spu_coh_notify_write(uint32_t a) { (void)a; }

/* Stub the ATRAC decoder: this test only cares about ring / remain / NODATA. */
void* at3p_open(int channels, int* block_align) { (void)channels; (void)block_align; return (void*)1; }
void  at3p_close(void* dec) { (void)dec; }
void  at3p_flush(void* dec) { (void)dec; }
int   at3p_decode(void* dec, float** planes, int* samples,
                  const uint8_t* frame, int frame_bytes)
{
    (void)dec; (void)frame;
    if (planes) {
        for (int c = 0; c < 8; c++)
            if (planes[c]) memset(planes[c], 0, 2048 * sizeof(float));
    }
    if (samples) *samples = 2048;
    return frame_bytes;
}

enum { MEM = 8u << 20, H = 0x100, WORK = 0x200, OUT = 0x10000, ARGS = 0x20,
       FILE_EA = 0x100000, RING_EA = 0x200000 };

static void wr_le32(u8* p, u32 v) { p[0]=(u8)v; p[1]=(u8)(v>>8); p[2]=(u8)(v>>16); p[3]=(u8)(v>>24); }
static void wr_le16(u8* p, u16 v) { p[0]=(u8)v; p[1]=(u8)(v>>8); }

/* Minimal AT3P RIFF: fmt + fact + data of nframes * ba bytes. */
static u32 build_riff(u8* f, u32 ba, u32 nframes)
{
    const u32 data_bytes = nframes * ba;
    const u8 guid[16] = { 0xBF,0xAA,0x23,0xE9,0x58,0xCB,0x71,0x44,
                          0xA1,0x19,0xFF,0xFA,0x01,0xE4,0xCE,0x62 };
    u32 o = 0;
    memcpy(f + o, "RIFF", 4); wr_le32(f + 4, 0); memcpy(f + 8, "WAVE", 4); o = 12;
    memcpy(f + o, "fmt ", 4); wr_le32(f + o + 4, 40);
    wr_le16(f + o + 8, 0xFFFE);
    wr_le16(f + o + 10, 2);                 /* channels */
    wr_le32(f + o + 12, 48000);
    wr_le16(f + o + 20, (u16)ba);
    memcpy(f + o + 8 + 24, guid, 16);
    o += 8 + 40;
    memcpy(f + o, "fact", 4); wr_le32(f + o + 4, 8);
    wr_le32(f + o + 8, nframes * 2048);     /* audible samples */
    wr_le32(f + o + 12, 0);                 /* off1 */
    o += 8 + 8;
    memcpy(f + o, "data", 4); wr_le32(f + o + 4, data_bytes);
    o += 8;
    for (u32 i = 0; i < data_bytes; i++) f[o + i] = (u8)(0xA0 + (i % 17));
    o += data_bytes;
    wr_le32(f + 4, o - 8);
    return o;
}

static u32 rd32(u32 ea) { return vm_read32(ea); }

int main(void)
{
    vm_base = calloc(1, MEM);
    assert(vm_base);

    const u32 ba = 192, nframes = 8;
    u8* file = vm_base + FILE_EA;
    const u32 total = build_riff(file, ba, nframes);
    AtracTrackInfo t;
    assert(atrac_parse_riff(file, total, &t) == 0);
    assert(t.block_align == ba);
    assert(t.channels == 2);
    const u32 header_and_one = t.data_off + ba;     /* header + first frame only */
    assert(header_and_one < total);

    const u32 ring_size = 1024;
    memcpy(vm_base + RING_EA, file, header_and_one);
    assert(cellAtracSetDataAndGetMemSize(H, RING_EA, header_and_one, ring_size, ARGS) == CELL_OK);
    assert(rd32(ARGS) == 0x1000);

    /* Incomplete file must not claim "all data is on memory". */
    assert(cellAtracGetRemainFrame(H, ARGS) == CELL_OK);
    const s32 rem0 = (s32)rd32(ARGS);
    assert(rem0 != (s32)CELL_ATRAC_ALLDATA_IS_ON_MEMORY);
    assert(rem0 >= 0);

    /* Unwritten out-params were the old fake; these must be filled in. */
    vm_write32(ARGS, 0xDEADBEEF);
    vm_write32(ARGS + 4, 0xDEADBEEF);
    vm_write32(ARGS + 8, 0xDEADBEEF);
    assert(cellAtracGetStreamDataInfo(H, ARGS, ARGS + 4, ARGS + 8) == CELL_OK);
    const u32 wptr = rd32(ARGS), wbytes = rd32(ARGS + 4), rpos = rd32(ARGS + 8);
    assert(wptr == RING_EA + header_and_one);
    assert(wbytes > 0);
    assert(rpos == header_and_one);

    assert(cellAtracGetVacantSize(H, ARGS) == CELL_OK);
    assert(rd32(ARGS) == wbytes);
    assert(cellAtracIsSecondBufferNeeded(H) == 0);
    assert(cellAtracGetSecondBufferInfo(H, ARGS, ARGS + 4) == (s32)CELL_ATRAC_ERROR_NONEED_SECOND_BUFFER);
    assert(rd32(ARGS) == 0 && rd32(ARGS + 4) == 0);

    /* Header only: no complete frame fed -> Decode returns NODATA. */
    assert(cellAtracDeleteDecoder(H) == CELL_OK);
    memcpy(vm_base + RING_EA, file, t.data_off);
    assert(cellAtracSetDataAndGetMemSize(H, RING_EA, t.data_off, ring_size, ARGS) == CELL_OK);
    assert(cellAtracCreateDecoder(H, WORK, 0, 0) == CELL_OK);
    assert(cellAtracDecode(H, OUT, ARGS, ARGS + 4, ARGS + 8)
           == (s32)CELL_ATRAC_ERROR_NODATA_IN_BUFFER);
    assert(rd32(ARGS) == 0); /* samples */

    /* Restart with header + first frame, then interleave Add/Decode until the
     * file is fully fed (the ring is smaller than the file, so Decode must
     * free space before the rest can be added). */
    assert(cellAtracDeleteDecoder(H) == CELL_OK);
    memcpy(vm_base + RING_EA, file, header_and_one);
    assert(cellAtracSetDataAndGetMemSize(H, RING_EA, header_and_one, ring_size, ARGS) == CELL_OK);
    assert(cellAtracCreateDecoder(H, WORK, 0, 0) == CELL_OK);

    u32 fed = header_and_one;
    int decoded = 0, loops = 0;
    while (fed < total) {
        s32 gi = cellAtracGetStreamDataInfo(H, ARGS, ARGS + 4, ARGS + 8);
        if (gi == (s32)CELL_ATRAC_ERROR_ALLDATA_IS_ONMEMORY) break;
        assert(gi == CELL_OK);
        u32 wp = rd32(ARGS), n = rd32(ARGS + 4), rp = rd32(ARGS + 8);
        assert(rp == fed);
        if (n == 0) {
            /* Ring full: consume a frame to free space. */
            s32 rc = cellAtracDecode(H, OUT, ARGS, ARGS + 4, ARGS + 8);
            assert(rc == CELL_OK || rc == (s32)CELL_ATRAC_ERROR_NODATA_IN_BUFFER);
            if (rc == CELL_OK) decoded++;
            else {
                /* Should not happen while bytes remain to be fed and the first
                 * frame was already present. */
                assert(0 && "NODATA with empty writable but file not finished");
            }
        } else {
            if (n > total - fed) n = total - fed;
            memcpy(vm_base + wp, file + fed, n);
            assert(cellAtracAddStreamData(H, n) == CELL_OK);
            fed += n;
        }
        assert(++loops < 1000);
    }
    assert(fed == total);
    assert(cellAtracGetStreamDataInfo(H, ARGS, ARGS + 4, ARGS + 8)
           == (s32)CELL_ATRAC_ERROR_ALLDATA_IS_ONMEMORY);
    assert(cellAtracGetRemainFrame(H, ARGS) == CELL_OK);
    assert((s32)rd32(ARGS) == (s32)CELL_ATRAC_ALLDATA_IS_ON_MEMORY);

    assert(cellAtracGetBufferInfoForResetting(H, 0, ARGS) == CELL_OK);
    assert(rd32(ARGS + 4) == 0); /* writable=0 when all on memory */

    /* All-on-memory SetData still reports -1 and rejects stream info. */
    assert(cellAtracDeleteDecoder(H) == CELL_OK);
    memcpy(vm_base + RING_EA, file, total);
    assert(cellAtracSetDataAndGetMemSize(H, RING_EA, total, total, ARGS) == CELL_OK);
    assert(cellAtracGetRemainFrame(H, ARGS) == CELL_OK);
    assert((s32)rd32(ARGS) == (s32)CELL_ATRAC_ALLDATA_IS_ON_MEMORY);
    assert(cellAtracGetStreamDataInfo(H, ARGS, ARGS + 4, ARGS + 8)
           == (s32)CELL_ATRAC_ERROR_ALLDATA_IS_ONMEMORY);

    /* Strikeforce BGM is 6ch AT3P; the old ch<=2 cap returned ILLEGAL_DATA. */
    {
        u8* f6 = vm_base + 0x300000;
        /* Rebuild the stereo fixture's header and poke channels=6 into fmt. */
        memset(f6, 0, 4096);
        const u32 tot6 = build_riff(f6, 1712, 2);
        f6[12+8+2] = 6; f6[12+8+3] = 0; /* le16 channels at fmt+2 */
        AtracTrackInfo t6;
        assert(atrac_parse_riff(f6, tot6, &t6) == 0);
        assert(t6.channels == 6);
        assert(t6.block_align == 1712);
    }

    puts("cellAtrac stream: prefix, GetStreamDataInfo, AddStreamData, remain, all-on-mem passed");
    return 0;
}
