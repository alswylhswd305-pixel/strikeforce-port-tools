/* Copyright (c) 2026 Saud Hamad Alsuwailih
 * SPDX-License-Identifier: AGPL-3.0-or-later OR LicenseRef-Saud-Commercial
 */

/* Strikeforce port: cellSail movie playback that really plays (picture + sound).
 *
 * Own implementation (dual-licensed AGPL-3.0-or-later OR a commercial licence from Saud). No RPCS3 or GPL code.
 * Spec sources, all paraphrased:
 *  - the game's own use of SAIL, read from its lifted code (ppu_recomp_002.cpp,
 *    0x5C871C audio thread, 0x5C8E7C video fetch, 0x5C91E8 player setup,
 *    0x5C99E4 stream open, 0x5CA2A4 player callback);
 *  - struct layouts (CellSailVideoFormat / AudioFormat / FrameInfo, event and
 *    state numbers) and PAMF header layout as facts from RPCS3 cellSail.h
 *    L586-L633, L766-L826 and cellPamf.h (CellPamfReader 128 bytes, stream
 *    headers 0x30 bytes from 0x88, coding types 0x02/0x1B/0x80/0xDC);
 *  - the adapter protocol notes in project-vekta port/kz1hd/sail.cpp header (MIT).
 * Video decode: Windows Media Foundation MPEG-2 / H.264 decoder MFTs (part of
 * the OS). ATRAC3plus: the at3_standalone decoder already linked for cellAtrac.
 * LPCM: own 24/16-bit big-endian to float.
 *
 * The movie is never skipped: the player reports the stream end only after the
 * last decoded frame has been handed to the game and the sound has drained.
 */
#include <windows.h>
#include <mfapi.h>
#include <mfidl.h>
#include <mftransform.h>
#include <mferror.h>
#include <thread>
#include <mutex>
#include <condition_variable>
#include <deque>
#include <vector>
#include <string>
#include <atomic>
#include <chrono>
#include <map>
#include <cmath>
#pragma comment(lib, "mfplat.lib")
#pragma comment(lib, "mfuuid.lib")
#pragma comment(lib, "ole32.lib")
#include "at3_bridge.h"
#include "ps3emu/guest_call.h"

extern "C" const char* ppu_vfs_root;   /* ppu_fs.cpp:97 */

namespace sf_movie {

/* ---------------------------------------------------------------- constants */
static const uint32_t E_INVALID_ARG   = 0x80610701u;
static const uint32_t E_INVALID_STATE = 0x80610702u;
static const uint32_t E_UNSUPPORTED   = 0x80610703u;
static const uint32_t E_EMPTY         = 0x80610705u;
static const uint32_t E_MEMORY        = 0x806107F0u;
static const uint32_t PAMF_NOT_FOUND  = 0x80610501u;
static const uint32_t PAMF_INVALID    = 0x80610503u;

enum { EV_ERROR = 1, EV_CALL_COMPLETED = 2, EV_STATE_CHANGED = 3, EV_STREAM_OPENED = 4,
       EV_STREAM_CLOSED = 5, EV_SOURCE_EOS = 8 };
enum { CALL_BOOT = 1, CALL_OPEN_STREAM = 2, CALL_CLOSE_STREAM = 3, CALL_START = 10, CALL_STOP = 11 };
enum { ST_BOOT_TRANSITION = 1, ST_CLOSED = 2, ST_OPEN_TRANSITION = 3, ST_OPENED = 4,
       ST_START_TRANSITION = 5, ST_RUNNING = 6, ST_STOP_TRANSITION = 7, ST_CLOSE_TRANSITION = 8 };
static const int AUDIO_BLOCK = 256;           /* the game asks for 256 sample frames */
static const int NUM_GFX_BUFFERS = 4;
static const int NUM_SND_BUFFERS = 16;

static bool s_log = true;
#define MLOG(...) do { if (s_log) { fprintf(stderr, "[sf-movie] " __VA_ARGS__); fflush(stderr); } } while (0)

static inline uint8_t* G(uint32_t ea) { return vm_base + ea; }
/* Own big-endian guest accessors (ppu_memory.h is C with stdatomic.h; the
 * other port .inc files also go through vm_base directly). */
static inline uint8_t  vm_read8(uint32_t ea)  { return vm_base[ea]; }
static inline uint32_t vm_read32(uint32_t ea) { uint32_t v; memcpy(&v, vm_base + ea, 4); return _byteswap_ulong(v); }
static inline void vm_write8(uint32_t ea, uint8_t v)   { vm_base[ea] = v; }
static inline void vm_write16(uint32_t ea, uint16_t v) { v = _byteswap_ushort(v); memcpy(vm_base + ea, &v, 2); }
static inline void vm_write32(uint32_t ea, uint32_t v) { v = _byteswap_ulong(v); memcpy(vm_base + ea, &v, 4); }
static inline void vm_write64(uint32_t ea, uint64_t v) { v = _byteswap_uint64(v); memcpy(vm_base + ea, &v, 8); }
static inline void wbe16(uint32_t ea, uint16_t v) { vm_write16(ea, v); }
static inline void wbe32(uint32_t ea, uint32_t v) { vm_write32(ea, v); }
static inline void wbe64(uint32_t ea, uint64_t v) { vm_write64(ea, v); }

/* g_ps3_guest_caller returns void (guest_call.h), so a callback whose r3
 * result we need goes through the checked code/TOC entry point. */
static bool gcall_ok(uint32_t opd, uint64_t* out, uint64_t a0, uint64_t a1, uint64_t a2, uint64_t a3)
{
    *out = 0;
    if (!opd || (opd & 3)) return false;
    const uint32_t code = vm_read32(opd), toc = vm_read32(opd + 4);
    return ppu_guest_call_ct_checked(code, toc, a0, a1, a2, a3, 0, 0, 0, 0, out) == 1;
}
static uint64_t gcall(uint32_t opd, uint64_t a0, uint64_t a1 = 0, uint64_t a2 = 0, uint64_t a3 = 0)
{
    uint64_t r = 0;
    if (!gcall_ok(opd, &r, a0, a1, a2, a3)) {
        fprintf(stderr, "[sf-movie] guest call 0x%08X not dispatched\n", opd);
        return (uint64_t)-1;
    }
    return r;
}

/* ---------------------------------------------------------------- PAMF info */
struct PamfStream { uint8_t coding, stream_id, private_id, ch, fs_code, bits, frc; };
struct PamfInfo {
    uint32_t data_offset = 0, data_size = 0, header_size = 0;
    uint32_t start_pts = 0, end_pts = 0;
    std::vector<PamfStream> streams;
    std::vector<uint8_t> header;
};

static bool pamf_parse(FILE* f, PamfInfo& pi)
{
    uint8_t h[0x800];
    if (fseek(f, 0, SEEK_SET) || fread(h, 1, sizeof h, f) != sizeof h) return false;
    if (memcmp(h, "PAMF", 4)) return false;
    auto be32 = [&](int o) { return (uint32_t)h[o] << 24 | h[o + 1] << 16 | h[o + 2] << 8 | h[o + 3]; };
    pi.header_size = be32(8) * 0x800;   /* in 2048-byte units */
    pi.data_size   = be32(12) * 0x800;
    pi.data_offset = pi.header_size;
    pi.start_pts   = be32(0x5A);
    pi.end_pts     = be32(0x60);
    const int n = h[0x87];
    if (n <= 0 || 0x88 + n * 0x30 > 0x800) return false;
    for (int i = 0; i < n; i++) {
        const uint8_t* s = h + 0x88 + i * 0x30;
        PamfStream st{};
        st.coding = s[0]; st.stream_id = s[4]; st.private_id = s[5];
        if (st.coding == 0xDC || st.coding == 0x80 || st.coding == 0x81) {
            st.ch = s[0x12]; st.fs_code = s[0x13]; st.bits = s[0x14];
        } else {
            st.frc = s[0x12] & 0x0F;
        }
        pi.streams.push_back(st);
    }
    pi.header.assign(h, h + 0x800);
    return true;
}

/* -------------------------------------------------------------- MF decoder */
static const GUID kCLSID_H264Dec  = {0x62CE7E72, 0x4C71, 0x4d20, {0xB1, 0x5D, 0x45, 0x28, 0x31, 0xA8, 0x7D, 0x9D}};
static const GUID kCLSID_MPEG2Dec = {0x2D709E52, 0x123F, 0x49b5, {0x9C, 0xBC, 0x9A, 0xF5, 0xCD, 0xE2, 0x8F, 0xB9}};
static const GUID kFmt_H264  = {0x34363248, 0x0000, 0x0010, {0x80, 0x00, 0x00, 0xAA, 0x00, 0x38, 0x9B, 0x71}};
static const GUID kFmt_MPEG2 = {0xe06d8026, 0xdb46, 0x11cf, {0xb4, 0xd1, 0x00, 0x80, 0x5f, 0x6c, 0xbb, 0xea}};
static const GUID kFmt_NV12  = {0x3231564E, 0x0000, 0x0010, {0x80, 0x00, 0x00, 0xAA, 0x00, 0x38, 0x9B, 0x71}};

struct VideoDecoder {
    IMFTransform* mft = nullptr;
    bool provides = false;
    UINT32 out_w = 0, out_h = 0; LONG stride = 0;
    DWORD out_cb = 0;
    bool open(bool avc, int w, int h) {
        HRESULT hr = create(avc);
        if (FAILED(hr) || !mft) { MLOG("MF %s decoder create failed hr=0x%08lX\n", avc ? "H.264" : "MPEG-2", hr); return false; }
        IMFMediaType* in = nullptr; MFCreateMediaType(&in);
        in->SetGUID(MF_MT_MAJOR_TYPE, MFMediaType_Video);
        in->SetGUID(MF_MT_SUBTYPE, avc ? kFmt_H264 : kFmt_MPEG2);
        MFSetAttributeSize(in, MF_MT_FRAME_SIZE, w, h);
        hr = mft->SetInputType(0, in, 0); in->Release();
        if (FAILED(hr)) { MLOG("MF SetInputType hr=0x%08lX\n", hr); return false; }
        if (!pick_output()) return false;
        mft->ProcessMessage(MFT_MESSAGE_NOTIFY_BEGIN_STREAMING, 0);
        mft->ProcessMessage(MFT_MESSAGE_NOTIFY_START_OF_STREAM, 0);
        return true;
    }
    /* Decoders are found through MFTEnumEx + IMFActivate: the MPEG-2 decoder on
     * Windows 10/11 ships as the Store "MPEG-2 Video Extension", and creating
     * its CLSID directly fails with a licensing error (0xC004F011). */
    HRESULT create(bool avc) {
        MFT_REGISTER_TYPE_INFO in{MFMediaType_Video, avc ? kFmt_H264 : kFmt_MPEG2};
        const UINT32 base = MFT_ENUM_FLAG_SYNCMFT | MFT_ENUM_FLAG_LOCALMFT | MFT_ENUM_FLAG_SORTANDFILTER;
        const UINT32 tries[2] = {base, base | 0x00000400u /* MFT_ENUM_FLAG_UNTRUSTED_STOREMFT */};
        HRESULT last = E_FAIL;
        for (UINT32 flags : tries) {
            IMFActivate** acts = nullptr; UINT32 n = 0;
            HRESULT hr = MFTEnumEx(MFT_CATEGORY_VIDEO_DECODER, flags, &in, nullptr, &acts, &n);
            MLOG("MFTEnumEx %s flags 0x%X -> hr=0x%08lX, %u decoders\n", avc ? "H.264" : "MPEG-2", flags, hr, n);
            for (UINT32 i = 0; SUCCEEDED(hr) && i < n && !mft; i++) {
                WCHAR* name = nullptr; UINT32 nl = 0;
                acts[i]->GetAllocatedString(MFT_FRIENDLY_NAME_Attribute, &name, &nl);
                HRESULT ha = acts[i]->ActivateObject(IID_PPV_ARGS(&mft));
                MLOG("  decoder %u '%ls' activate hr=0x%08lX\n", i, name ? name : L"?", ha);
                if (name) CoTaskMemFree(name);
                if (FAILED(ha)) { mft = nullptr; last = ha; }
            }
            for (UINT32 i = 0; i < n; i++) acts[i]->Release();
            if (acts) CoTaskMemFree(acts);
            if (mft) return S_OK;
            if (FAILED(hr)) last = hr;
        }
        /* last resort: the in-box CLSID (works for H.264) */
        HRESULT hr = CoCreateInstance(avc ? kCLSID_H264Dec : kCLSID_MPEG2Dec, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&mft));
        MLOG("CoCreateInstance %s hr=0x%08lX\n", avc ? "H.264" : "MPEG-2", hr);
        return FAILED(hr) ? (FAILED(last) ? last : hr) : S_OK;
    }
    bool pick_output() {
        for (DWORD i = 0;; i++) {
            IMFMediaType* t = nullptr;
            if (FAILED(mft->GetOutputAvailableType(0, i, &t))) break;
            GUID sub{}; t->GetGUID(MF_MT_SUBTYPE, &sub);
            if (sub == kFmt_NV12) {
                HRESULT hr = mft->SetOutputType(0, t, 0);
                MFGetAttributeSize(t, MF_MT_FRAME_SIZE, &out_w, &out_h);
                UINT32 s = 0;
                stride = SUCCEEDED(t->GetUINT32(MF_MT_DEFAULT_STRIDE, &s)) ? (LONG)s : (LONG)out_w;
                t->Release();
                MFT_OUTPUT_STREAM_INFO si{}; mft->GetOutputStreamInfo(0, &si);
                provides = (si.dwFlags & (MFT_OUTPUT_STREAM_PROVIDES_SAMPLES | MFT_OUTPUT_STREAM_CAN_PROVIDE_SAMPLES)) != 0;
                out_cb = si.cbSize;
                return SUCCEEDED(hr);
            }
            t->Release();
        }
        MLOG("MF decoder offers no NV12 output\n");
        return false;
    }
    void close() { if (mft) { mft->Release(); mft = nullptr; } }
};

/* ------------------------------------------------------------------ player */
struct Frame { std::vector<uint8_t> argb; double t; };

struct Movie {
    std::string path;
    PamfInfo pi;
    int vidx = -1, aidx = -1;
    double fps = 29.97;
    int width = 1280, height = 720;
    int ch = 2;                      /* channels handed to the game */
    std::mutex m;
    std::condition_variable cv;
    std::deque<Frame> frames;
    std::deque<float> pcm;           /* interleaved, ch per frame, 48 kHz */
    bool demux_eof = false, video_eof = false, audio_eof = false, quit = false;
    std::atomic<bool> video_failed{false};
    uint64_t start_off = 0, end_off = ~0ull;   /* file byte range to play */
    std::thread th;
    /* stats */
    uint64_t frames_decoded = 0, frames_shown = 0, au_video = 0, au_audio = 0, samples_out = 0;
    double rms_sum[8] = {}; uint64_t rms_n = 0;
    float peak = 0;
};

struct Desc {
    uint32_t ea = 0;
    std::string uri, host;
    int type = 0;
    bool opened = false;
    PamfInfo pi;
    uint32_t header_ea = 0;          /* guest copy of the PAMF header, for the reader */
    int sel_video = -1, sel_audio = -1;
};

struct Player {
    uint32_t self = 0, cb = 0, cb_arg = 0;
    uint32_t alloc_opd = 0, free_opd = 0, alloc_arg = 0;
    uint32_t snd = 0, gfx = 0;
    uint32_t snd_funcs[3] = {}, snd_arg = 0;
    uint32_t gfx_funcs[5] = {}, gfx_arg = 0;
    uint32_t cur_desc = 0;
    Movie* mv = nullptr;
    bool running = false, paused = false, ended = false, eos_sent = false;
    std::chrono::steady_clock::time_point t0; double paused_at = 0;
    bool clock_started = false;
    uint32_t gbuf[NUM_GFX_BUFFERS] = {}; int ngbuf = 0, next_g = 0;
    uint32_t cur_frame_buf = 0; uint64_t cur_frame_pts = 0; uint32_t cur_tag = 0;
    uint32_t sbuf[NUM_SND_BUFFERS] = {}; int next_s = 0;
    uint32_t snd_tag = 0;
    uint64_t snd_served = 0;
    uint32_t session = 0;
    uint32_t scratch = 0;            /* guest scratch (alloc out-array) */
    double clock() const {
        if (!clock_started) return 0;
        if (paused) return paused_at;
        return std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    }
};

static Player g;
static std::map<uint32_t, Desc> s_desc;
static uint32_t s_session_counter = 0;

static void notify(uint32_t major, uint32_t minor, uint64_t a0, uint64_t a1 = 0)
{
    MLOG("event major=%u minor=%u arg0=0x%llX arg1=0x%llX\n", major, minor,
         (unsigned long long)a0, (unsigned long long)a1);
    if (g.cb) gcall(g.cb, g.cb_arg, ((uint64_t)major << 32) | minor, a0, a1);
}
static void call_done(uint32_t call, uint32_t via, uint32_t to, uint64_t user)
{
    notify(EV_STATE_CHANGED, 0, via);
    notify(EV_CALL_COMPLETED, call, 0, user);
    notify(EV_STATE_CHANGED, 0, to);
}

static uint32_t galloc(uint32_t size, uint32_t align = 128)
{
    if (!g.alloc_opd) return 0;
    uint64_t r = 0;
    if (!gcall_ok(g.alloc_opd, &r, g.alloc_arg, align, size, 0)) return 0;
    return (uint32_t)r;
}
static void gfree(uint32_t p, uint32_t align = 128)
{
    if (p && g.free_opd) gcall(g.free_opd, g.alloc_arg, align, p);
}

static std::string guest_str(uint32_t ea)
{
    std::string s;
    for (uint32_t i = 0; ea && i < 1024; i++) { char c = (char)vm_read8(ea + i); if (!c) break; s += c; }
    return s;
}

/* x-cell-fs:///dev_bdvd/PS3_GAME/... -> <vfs>/dev_bdvd/PS3_GAME/...; the VFS root
 * is the dev_bdvd directory itself in this port (see derive_vfs_root). */
static std::string resolve(std::string uri)
{
    if (uri.rfind("x-cell-fs://", 0) == 0) uri = uri.substr(12);
    std::string root = ppu_vfs_root ? ppu_vfs_root : ".";
    std::string cand[3];
    cand[0] = root + uri;
    if (uri.rfind("/dev_bdvd", 0) == 0) cand[1] = root + uri.substr(9);
    cand[2] = root + "/.." + uri;
    for (auto& c : cand) {
        if (c.empty()) continue;
        FILE* f = fopen(c.c_str(), "rb");
        if (f) { fclose(f); return c; }
    }
    return {};
}

/* -------------------------------------------------------- colour conversion */
static void nv12_to_argb(const uint8_t* y, const uint8_t* uv, int ys, int w, int h, uint8_t* out)
{
    /* BT.709 limited range -> full-range RGB, byte order A R G B (guest ARGB). */
    for (int j = 0; j < h; j++) {
        const uint8_t* yr = y + (size_t)j * ys;
        const uint8_t* cr = uv + (size_t)(j >> 1) * ys;
        uint8_t* o = out + (size_t)j * w * 4;
        for (int i = 0; i < w; i++) {
            int Y = (yr[i] - 16) * 298;
            int U = cr[i & ~1] - 128, V = cr[(i & ~1) + 1] - 128;
            int R = (Y + 459 * V + 128) >> 8;
            int Gc = (Y - 55 * U - 136 * V + 128) >> 8;
            int B = (Y + 541 * U + 128) >> 8;
            o[0] = 0xFF;
            o[1] = (uint8_t)(R < 0 ? 0 : R > 255 ? 255 : R);
            o[2] = (uint8_t)(Gc < 0 ? 0 : Gc > 255 ? 255 : Gc);
            o[3] = (uint8_t)(B < 0 ? 0 : B > 255 ? 255 : B);
            o += 4;
        }
    }
}

/* ----------------------------------------------------------- decode thread */
static void push_frame(Movie* mv, IMFSample* s, VideoDecoder& vd)
{
    IMFMediaBuffer* b = nullptr;
    if (FAILED(s->ConvertToContiguousBuffer(&b))) return;
    BYTE* p = nullptr; DWORD len = 0;
    if (SUCCEEDED(b->Lock(&p, nullptr, &len))) {
        int w = (int)vd.out_w, h = (int)vd.out_h;
        int ys = vd.stride > 0 ? (int)vd.stride : w;
        /* NV12 height in the buffer may be padded to 16 (720 -> 720/736). */
        int hpad = (int)(len / (DWORD)ys * 2 / 3);
        if (hpad < h) hpad = h;
        Frame f;
        int ow = mv->width, oh = mv->height;
        if (ow > w) ow = w;
        if (oh > h) oh = h;
        f.argb.resize((size_t)mv->width * mv->height * 4, 0);
        std::vector<uint8_t> tmp((size_t)ow * oh * 4);
        nv12_to_argb(p, p + (size_t)ys * hpad, ys, ow, oh, tmp.data());
        for (int j = 0; j < oh; j++)
            memcpy(&f.argb[(size_t)j * mv->width * 4], &tmp[(size_t)j * ow * 4], (size_t)ow * 4);
        f.t = (double)mv->frames_decoded / mv->fps;
        b->Unlock();
        if (mv->frames_decoded % 150 == 0) {
            uint64_t sum = 0; size_t np = (size_t)ow * oh;
            for (size_t k = 0; k < np; k += 7) { const uint8_t* q = &tmp[k * 4]; sum += (q[1] * 2 + q[2] * 5 + q[3]) >> 3; }
            const uint8_t* y0 = p;
            uint64_t ys_sum = 0; for (int k = 0; k < w * 16; k += 3) ys_sum += y0[(size_t)(h / 2) * ys + (k % w)];
            MLOG("frame %llu: mean RGB-luma %.1f, mid-row Y %.1f (decoder %ux%u stride %d hpad %d len %lu)\n",
                 (unsigned long long)mv->frames_decoded, (double)sum / (double)((np + 6) / 7),
                 (double)ys_sum / (double)((w * 16 + 2) / 3), vd.out_w, vd.out_h, ys, hpad, (unsigned long)len);
            const char* dd = getenv("SF_MOVIE_DUMP");
            if (dd && *dd) {
                char fn[600]; snprintf(fn, sizeof fn, "%s\\%s_f%05llu.bmp", dd,
                    mv->path.substr(mv->path.find_last_of("/\\") + 1).c_str(), (unsigned long long)mv->frames_decoded);
                FILE* o = fopen(fn, "wb");
                if (o) {
                    const int W = mv->width, H = mv->height; const uint32_t sz = 54 + (uint32_t)W * H * 4;
                    uint8_t hd[54] = {'B','M'}; memcpy(hd + 2, &sz, 4); hd[10] = 54; hd[14] = 40;
                    memcpy(hd + 18, &W, 4); int nh = -H; memcpy(hd + 22, &nh, 4); hd[26] = 1; hd[28] = 32;
                    fwrite(hd, 1, 54, o);
                    std::vector<uint8_t> row((size_t)W * 4);
                    for (int j = 0; j < H; j++) { const uint8_t* a = &f.argb[(size_t)j * W * 4];
                        for (int i2 = 0; i2 < W; i2++) { row[i2*4] = a[i2*4+3]; row[i2*4+1] = a[i2*4+2]; row[i2*4+2] = a[i2*4+1]; row[i2*4+3] = 255; }
                        fwrite(row.data(), 1, row.size(), o); }
                    fclose(o);
                }
            }
        }
        std::unique_lock<std::mutex> l(mv->m);
        mv->frames.push_back(std::move(f));
        mv->frames_decoded++;
    }
    b->Release();
}

static bool drain_output(Movie* mv, VideoDecoder& vd)
{
    for (;;) {
        MFT_OUTPUT_DATA_BUFFER ob{}; DWORD status = 0;
        IMFSample* own = nullptr;
        if (!vd.provides) {
            MFCreateSample(&own);
            IMFMediaBuffer* mb = nullptr;
            DWORD cb = vd.out_cb ? vd.out_cb : (DWORD)(vd.out_w * vd.out_h * 3 / 2 + 4096);
            MFCreateMemoryBuffer(cb, &mb); own->AddBuffer(mb); mb->Release();
            ob.pSample = own;
        }
        HRESULT hr = vd.mft->ProcessOutput(0, 1, &ob, &status);
        if (hr == MF_E_TRANSFORM_NEED_MORE_INPUT) { if (own) own->Release(); if (ob.pEvents) ob.pEvents->Release(); return true; }
        if (hr == MF_E_TRANSFORM_STREAM_CHANGE) {
            if (own) own->Release();
            if (ob.pEvents) ob.pEvents->Release();
            if (!vd.pick_output()) return false;
            MLOG("video output %ux%u stride %ld\n", vd.out_w, vd.out_h, (long)vd.stride);
            continue;
        }
        if (FAILED(hr)) { if (own) own->Release(); if (ob.pEvents) ob.pEvents->Release(); MLOG("ProcessOutput hr=0x%08lX\n", hr); return false; }
        if (ob.pSample) push_frame(mv, ob.pSample, vd);
        if (ob.pSample && ob.pSample != own) ob.pSample->Release();
        if (own) own->Release();
        if (ob.pEvents) ob.pEvents->Release();
    }
}

static void feed_video(Movie* mv, VideoDecoder& vd, const uint8_t* au, size_t n)
{
    IMFSample* s = nullptr; MFCreateSample(&s);
    IMFMediaBuffer* mb = nullptr; MFCreateMemoryBuffer((DWORD)n, &mb);
    BYTE* p = nullptr; mb->Lock(&p, nullptr, nullptr); memcpy(p, au, n); mb->Unlock();
    mb->SetCurrentLength((DWORD)n); s->AddBuffer(mb); mb->Release();
    LONGLONG t = (LONGLONG)(mv->au_video * 10000000.0 / mv->fps);
    s->SetSampleTime(t); s->SetSampleDuration((LONGLONG)(10000000.0 / mv->fps));
    mv->au_video++;
    for (int tries = 0; tries < 4; tries++) {
        HRESULT hr = vd.mft->ProcessInput(0, s, 0);
        if (hr == MF_E_NOTACCEPTING) { drain_output(mv, vd); continue; }
        break;
    }
    s->Release();
    drain_output(mv, vd);
}

/* Split an elementary stream into access units. MPEG-2: a unit starts at a
 * sequence header / GOP / picture start code once the unit already holds a
 * picture. H.264: a unit starts at each access unit delimiter (NAL 9). */
struct AuSplitter {
    bool avc;
    std::vector<uint8_t> buf;
    template <class F> void push(const uint8_t* d, size_t n, F&& emit, bool flush = false) {
        buf.insert(buf.end(), d, d + n);
        size_t start = 0; bool have_pic = false;
        size_t i = 0;
        for (; i + 4 <= buf.size(); i++) {
            if (buf[i] || buf[i + 1] || buf[i + 2] != 1) continue;
            uint8_t c = buf[i + 3];
            bool boundary;
            if (avc) {
                boundary = (c & 0x1F) == 9;
                if (boundary && i > start) { size_t b = (i > 0 && buf[i - 1] == 0) ? i - 1 : i; if (b > start) { emit(&buf[start], b - start); start = b; } }
            } else {
                boundary = c == 0xB3 || c == 0xB8 || c == 0x00;
                if (boundary && have_pic) { emit(&buf[start], i - start); start = i; have_pic = false; }
                if (c == 0x00) have_pic = true;
            }
            i += 3;
        }
        if (flush) { if (buf.size() > start) emit(&buf[start], buf.size() - start); buf.clear(); }
        else buf.erase(buf.begin(), buf.begin() + start);
    }
};

static void audio_out(Movie* mv, float** planes, int nsamp, int srcch)
{
    /* Hand the game the stream's own channels. Order for 6 ch: L R C LFE Ls Rs
     * (cellAudio's 8-channel order minus the back pair); see map_6ch(). */
    std::vector<float> o((size_t)nsamp * mv->ch);
    for (int s = 0; s < nsamp; s++)
        for (int c = 0; c < mv->ch; c++) {
            float v = c < srcch ? planes[c][s] : 0.f;
            o[(size_t)s * mv->ch + c] = v;
            mv->rms_sum[c] += (double)v * v;
            float a = fabsf(v); if (a > mv->peak) mv->peak = a;
        }
    mv->rms_n += nsamp;
    std::unique_lock<std::mutex> l(mv->m);
    mv->pcm.insert(mv->pcm.end(), o.begin(), o.end());
}

/* ATRAC3plus decoder planes come out in channel-unit order (atrac3plusdec.cpp
 * atrac3p_decode_frame copies unit by unit; set_channel_params case 6 is
 * STEREO, MONO, STEREO, MONO): L R | C | Ls Rs | LFE. cellAudio 6 ch wants
 * L R C LFE Ls Rs, so output c takes plane kAt3Map6[c]. Checked in the test log
 * by per-channel RMS (LFE lowest, dialogue in C). */
static const int kAt3Map6[6] = {0, 1, 2, 5, 3, 4};
/* PAMF LPCM 6 ch sample order: L C R Ls Rs LFE (the Blu-ray LPCM order) is the
 * assumption to verify; remapped to L R C LFE Ls Rs. Checked in the test log by
 * per-channel RMS (LFE lowest, dialogue in C). */
/* Measured on movie002 (v3 run 17:46): source ch0 0.272, ch1 0.266, ch2 0.047,
 * ch3 0.046, ch4 0.045, ch5 0.035 RMS -> the pair is ch0/ch1 (L R), so the
 * {0,2,1,...} Blu-ray guess was wrong. Taken as cellAudio order L R C LFE Ls Rs;
 * which of ch3/ch5 is LFE is not confirmed. */
static const int kLpcmMap6[6] = {0, 1, 2, 3, 4, 5};

static void decode_thread(Movie* mv)
{
    CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    MFStartup(MF_VERSION, MFSTARTUP_NOSOCKET);
    FILE* f = fopen(mv->path.c_str(), "rb");
    const PamfStream& vs = mv->pi.streams[mv->vidx];
    const bool avc = vs.coding == 0x1B;
    VideoDecoder vd;
    bool vok = f && vd.open(avc, mv->width, mv->height);
    if (!vok) { mv->video_failed = true; MLOG("VIDEO DECODER FAILED: picture will be missing for %s\n", mv->path.c_str()); }
    MLOG("decode %s: video %s (%s), audio %s, %.3f fps\n", mv->path.c_str(), avc ? "H.264" : "MPEG-2",
         vok ? "MF ok" : "MF FAILED",
         mv->aidx < 0 ? "none" : mv->pi.streams[mv->aidx].coding == 0xDC ? "ATRAC3plus" :
         mv->pi.streams[mv->aidx].coding == 0x80 ? "LPCM" : "other", mv->fps);
    const PamfStream* as = mv->aidx >= 0 ? &mv->pi.streams[mv->aidx] : nullptr;
    void* at3 = nullptr; int at3_frame = 0, at3_ch = 0;
    std::vector<uint8_t> abuf;
    AuSplitter sp{avc, {}};
    auto emit_video = [&](const uint8_t* d, size_t n) { if (vok) feed_video(mv, vd, d, n); };
    if (f) fseek(f, (long)(mv->start_off ? mv->start_off : mv->pi.data_offset), SEEK_SET);
    std::vector<uint8_t> pack(0x800);
    uint64_t packs = 0;
    while (f && !mv->quit) {
        {   /* stay a few frames / about a second of sound ahead */
            std::unique_lock<std::mutex> l(mv->m);
            mv->cv.wait(l, [&] { return mv->quit ||
                ((mv->frames.size() < 6 || mv->pcm.size() < (size_t)48000 * mv->ch) && mv->frames.size() < 12); });
            if (mv->quit) break;
        }
        if ((uint64_t)ftell(f) >= mv->end_off) break;            /* terminus byte position */
        if (fread(pack.data(), 1, 0x800, f) != 0x800) break;
        packs++;
        const uint8_t* p = pack.data();
        if (p[0] || p[1] || p[2] != 1 || p[3] != 0xBA) continue;
        size_t i = 14 + (p[13] & 7);
        while (i + 6 <= 0x800) {
            if (p[i] || p[i + 1] || p[i + 2] != 1) break;
            uint8_t sid = p[i + 3];
            size_t len = (size_t)p[i + 4] << 8 | p[i + 5];
            const uint8_t* pkt = p + i + 6;
            if (i + 6 + len > 0x800) break;
            if (sid == 0xE0 || sid == 0xBD) {
                size_t hl = pkt[2];
                const uint8_t* pay = pkt + 3 + hl;
                size_t pn = len - 3 - hl;
                if (sid == vs.stream_id && sid == 0xE0) sp.push(pay, pn, emit_video);
                else if (sid == 0xBD && as && pn > 4 && pay[0] == as->private_id) abuf.insert(abuf.end(), pay + 4, pay + pn);
            }
            i += 6 + len;
        }
        /* audio: decode whatever whole frames are buffered */
        if (as && as->coding == 0xDC) {
            size_t o = 0;
            while (o + 8 <= abuf.size()) {
                if (abuf[o] != 0x0F || abuf[o + 1] != 0xD0) { o++; continue; }
                unsigned cfg = (unsigned)abuf[o + 2] << 8 | abuf[o + 3];
                int fsz = (int)(((cfg & 0x3FF) + 1) * 8);
                int chc = (cfg >> 10) & 7;
                static const int chmap[8] = {0, 1, 2, 3, 4, 6, 7, 8};
                if (o + 8 + fsz > abuf.size()) break;
                if (!at3) { at3_ch = chmap[chc]; at3_frame = fsz; int ba = fsz; at3 = at3p_open(at3_ch, &ba);
                            MLOG("ATRAC3plus %d ch, frame %d bytes, decoder %s\n", at3_ch, fsz, at3 ? "ok" : "FAILED"); }
                if (at3) {
                    static float pl[8][2048]; float* planes[8]; for (int c = 0; c < 8; c++) planes[c] = pl[c];
                    int ns = 0;
                    if (at3p_decode(at3, planes, &ns, &abuf[o + 8], fsz) >= 0 && ns > 0) {
                        if (at3_ch == 6) { float* r[6]; for (int c = 0; c < 6; c++) r[c] = planes[kAt3Map6[c]]; audio_out(mv, r, ns, 6); }
                        else audio_out(mv, planes, ns, at3_ch);
                    }
                    mv->au_audio++;
                }
                o += 8 + fsz;
            }
            abuf.erase(abuf.begin(), abuf.begin() + o);
        } else if (as && as->coding == 0x80) {
            const int bps = as->bits == 0xC0 ? 3 : 2;   /* 0xC0 = 24-bit in this title */
            const int sch = as->ch ? as->ch : 2;
            const size_t fb = (size_t)bps * sch;
            size_t nfr = abuf.size() / fb;
            if (nfr) {
                std::vector<float> pl((size_t)sch * nfr);
                for (size_t s = 0; s < nfr; s++)
                    for (int c = 0; c < sch; c++) {
                        const uint8_t* q = &abuf[s * fb + (size_t)c * bps];
                        int32_t v = bps == 3 ? (int32_t)((uint32_t)q[0] << 24 | q[1] << 16 | q[2] << 8) : (int32_t)((uint32_t)q[0] << 24 | q[1] << 16);
                        pl[(size_t)c * nfr + s] = (float)v / 2147483648.0f;
                    }
                float* planes[8];
                for (int c = 0; c < sch && c < 8; c++) planes[c] = &pl[(size_t)(sch == 6 ? kLpcmMap6[c] : c) * nfr];
                audio_out(mv, planes, (int)nfr, sch);
                mv->au_audio += nfr;
                abuf.erase(abuf.begin(), abuf.begin() + nfr * fb);
            }
        }
    }
    /* end of data: flush the last unit and drain the decoder */
    sp.push(nullptr, 0, emit_video, true);
    if (vok) {
        vd.mft->ProcessMessage(MFT_MESSAGE_NOTIFY_END_OF_STREAM, 0);
        vd.mft->ProcessMessage(MFT_MESSAGE_COMMAND_DRAIN, 0);
        drain_output(mv, vd);
    }
    vd.close();
    if (at3) at3p_close(at3);
    if (f) fclose(f);
    {
        std::unique_lock<std::mutex> l(mv->m);
        mv->demux_eof = true;
    }
    MLOG("decode done %s: %llu packs, %llu video AUs, %llu frames decoded, audio units %llu\n", mv->path.c_str(),
         (unsigned long long)packs, (unsigned long long)mv->au_video, (unsigned long long)mv->frames_decoded,
         (unsigned long long)mv->au_audio);
    MFShutdown();
    CoUninitialize();
}

static void movie_stop(Movie* mv)
{
    if (!mv) return;
    { std::unique_lock<std::mutex> l(mv->m); mv->quit = true; }
    mv->cv.notify_all();
    if (mv->th.joinable()) mv->th.join();
}
static void movie_report(Movie* mv, const char* why)
{
    if (!mv) return;
    char rms[200]; int k = 0;
    for (int c = 0; c < mv->ch && c < 8; c++)
        k += snprintf(rms + k, sizeof rms - k, "%s%.4f", c ? "," : "", mv->rms_n ? sqrt(mv->rms_sum[c] / mv->rms_n) : 0.0);
    MLOG("REPORT %s (%s): frames decoded %llu shown %llu, sound %d ch samples handed %llu (%.2f s), rms[%s] peak %.3f, clock %.2f s\n",
         mv->path.c_str(), why, (unsigned long long)mv->frames_decoded, (unsigned long long)mv->frames_shown, mv->ch,
         (unsigned long long)mv->samples_out, mv->samples_out / 48000.0, rms, mv->peak, g.clock());
}

/* ------------------------------------------------------------ HLE handlers */
#define A(n) ((uint32_t)ctx->gpr[3 + (n)])
#define A64(n) (ctx->gpr[3 + (n)])
#define RET(v) (ctx->gpr[3] = (uint64_t)(int64_t)(int32_t)(uint32_t)(v))

static void h_mem_allocator_init(ppu_context* ctx)
{
    /* (pSelf, pCallbacks, pArg): keep both callback OPDs and the argument in
     * the 12-byte record by value -- the callbacks live on the caller's stack. */
    const uint32_t rec = A(0), funcs = A(1);
    if (!rec || !funcs || (rec & 3) || (funcs & 3)) { RET(E_INVALID_ARG); return; }
    const uint32_t a = vm_read32(funcs), f = vm_read32(funcs + 4);
    wbe32(rec, a); wbe32(rec + 4, f); wbe32(rec + 8, A(2));
    RET(0);
}

static void h_player_init2(ppu_context* ctx)
{
    /* (pSelf, pAllocator, pCallback, pCallbackArg, pAttribute, pResource) */
    if (!A(0) || !A(1)) { RET(E_INVALID_ARG); return; }
    if (g.mv) { movie_stop(g.mv); delete g.mv; }
    g = Player{};
    g.self = A(0); g.cb = A(2); g.cb_arg = A(3);
    g.alloc_opd = vm_read32(A(1)); g.free_opd = vm_read32(A(1) + 4); g.alloc_arg = vm_read32(A(1) + 8);
    MLOG("PlayerInitialize2 self=0x%08X cb=0x%08X arg=0x%08X alloc=0x%08X free=0x%08X\n",
         g.self, g.cb, g.cb_arg, g.alloc_opd, g.free_opd);
    RET(0);
}

extern "C" void rsx_d3d12_cpu_texture(uint32_t ea, uint32_t bytes, int add);

static void free_buffers()
{
    if (g.ngbuf && g.gfx_funcs[4] && g.scratch) {
        for (int i = 0; i < g.ngbuf; i++) wbe32(g.scratch + 4 * i, g.gbuf[i]);
        gcall(g.gfx_funcs[4], g.gfx_arg, (uint64_t)g.ngbuf, g.scratch);
    }
    for (int i = 0; i < g.ngbuf; i++) rsx_d3d12_cpu_texture(g.gbuf[i], 0, 0);
    g.ngbuf = 0;
    for (int i = 0; i < NUM_SND_BUFFERS; i++) { gfree(g.sbuf[i]); g.sbuf[i] = 0; }
}

static void close_movie(const char* why)
{
    if (g.mv) { movie_report(g.mv, why); movie_stop(g.mv); delete g.mv; g.mv = nullptr; }
    free_buffers();
    g.running = false;
}

static void h_player_finalize(ppu_context* ctx)
{
    MLOG("PlayerFinalize self=0x%08X\n", A(0));
    close_movie("finalize");
    if (g.gfx_funcs[1]) gcall(g.gfx_funcs[1], g.gfx_arg);   /* adapter Cleanup */
    if (g.snd_funcs[1]) gcall(g.snd_funcs[1], g.snd_arg);
    gfree(g.scratch); g.scratch = 0;
    g.self = 0;
    RET(0);
}

static void h_set_sound_adapter(ppu_context* ctx) { g.snd = A(2); RET(0); }
static void h_set_graphics_adapter(ppu_context* ctx) { g.gfx = A(2); RET(0); }

static void h_snd_init(ppu_context* ctx)
{
    if (!A(0)) { RET(E_INVALID_ARG); return; }
    memset(G(A(0)), 0, 0x100);
    for (int i = 0; i < 3; i++) g.snd_funcs[i] = A(1) ? vm_read32(A(1) + 4 * i) : 0;
    g.snd_arg = A(2);
    RET(0);
}
static void h_gfx_init(ppu_context* ctx)
{
    if (!A(0)) { RET(E_INVALID_ARG); return; }
    memset(G(A(0)), 0, 0x100);
    for (int i = 0; i < 5; i++) g.gfx_funcs[i] = A(1) ? vm_read32(A(1) + 4 * i) : 0;
    g.gfx_arg = A(2);
    MLOG("GraphicsAdapterInitialize funcs makeup=0x%08X cleanup=0x%08X fmtchg=0x%08X alloc=0x%08X free=0x%08X arg=0x%08X\n",
         g.gfx_funcs[0], g.gfx_funcs[1], g.gfx_funcs[2], g.gfx_funcs[3], g.gfx_funcs[4], g.gfx_arg);
    RET(0);
}
static void h_finalize_ok(ppu_context* ctx) { RET(0); }
static void h_gfx_set_pref(ppu_context* ctx)
{
    if (!A(0) || !A(1)) { RET(E_INVALID_ARG); return; }
    MLOG("GraphicsAdapterSetPreferredFormat coding=%d\n", (int)(int8_t)vm_read8(A(1)));
    RET(0);
}

static void h_player_boot(ppu_context* ctx)
{
    if (A(0) != g.self) { RET(E_INVALID_ARG); return; }
    if (!g.scratch) g.scratch = galloc(64);
    /* The adapters are made up when the player boots. */
    if (g.snd_funcs[0]) gcall(g.snd_funcs[0], g.snd_arg);
    if (g.gfx_funcs[0]) gcall(g.gfx_funcs[0], g.gfx_arg);
    call_done(CALL_BOOT, ST_BOOT_TRANSITION, ST_CLOSED, A64(1));
    RET(0);
}

static void h_create_descriptor(ppu_context* ctx)
{
    /* (pSelf, streamType, pMediaInfo, pUri, ppDesc) */
    if (A(0) != g.self || !A(4)) { RET(E_INVALID_ARG); return; }
    const int type = (int)A(1);
    std::string uri = guest_str(A(3));
    if (type != 0) { MLOG("CreateDescriptor type %d not PAMF: %s\n", type, uri.c_str()); RET(E_UNSUPPORTED); return; }
    uint32_t ea = galloc(0x100);
    if (!ea) { RET(E_MEMORY); return; }
    memset(G(ea), 0, 0x100);
    vm_write8(ea + 1, 1);                       /* registered */
    wbe32(ea + 4, (uint32_t)type);
    Desc d; d.ea = ea; d.uri = uri; d.type = type; d.host = resolve(uri);
    MLOG("CreateDescriptor %s -> %s (desc 0x%08X)\n", uri.c_str(), d.host.empty() ? "(missing)" : d.host.c_str(), ea);
    s_desc[ea] = d;
    wbe32(A(4), ea);
    RET(0);
}
static void h_destroy_descriptor(ppu_context* ctx)
{
    auto it = s_desc.find(A(1));
    if (it == s_desc.end()) { RET(E_INVALID_ARG); return; }
    if (it->second.header_ea) gfree(it->second.header_ea);
    if (g.cur_desc == A(1)) g.cur_desc = 0;
    s_desc.erase(it);
    gfree(A(1));
    RET(0);
}
static void h_set_auto_selection(ppu_context* ctx)
{
    if (!s_desc.count(A(0))) { RET(E_INVALID_ARG); return; }
    vm_write8(A(0), (uint8_t)(A(1) != 0));
    RET(0);
}
static void h_desc_open(ppu_context* ctx)
{
    auto it = s_desc.find(A(0));
    if (it == s_desc.end()) { RET(E_INVALID_ARG); return; }
    Desc& d = it->second;
    FILE* f = d.host.empty() ? nullptr : fopen(d.host.c_str(), "rb");
    if (!f) { MLOG("DescriptorOpen: cannot open %s\n", d.uri.c_str()); RET(E_UNSUPPORTED); return; }
    PamfInfo pi; bool ok = pamf_parse(f, pi); fclose(f);
    if (!ok) { MLOG("DescriptorOpen: not PAMF %s\n", d.host.c_str()); RET(E_UNSUPPORTED); return; }
    d.pi = pi; d.opened = true;
    if (!d.header_ea) d.header_ea = galloc(0x800);
    if (d.header_ea) memcpy(G(d.header_ea), pi.header.data(), 0x800);
    for (size_t i = 0; i < pi.streams.size(); i++)
        MLOG("  stream %zu: coding 0x%02X id 0x%02X priv 0x%02X ch %u frc %u\n", i, pi.streams[i].coding,
             pi.streams[i].stream_id, pi.streams[i].private_id, pi.streams[i].ch, pi.streams[i].frc);
    RET(0);
}
static void h_desc_close(ppu_context* ctx)
{
    auto it = s_desc.find(A(0));
    if (it == s_desc.end()) { RET(E_INVALID_ARG); return; }
    it->second.opened = false;
    RET(0);
}
static int nth_stream(const PamfInfo& pi, int type, int index)
{
    int k = 0;
    for (size_t i = 0; i < pi.streams.size(); i++) {
        uint8_t c = pi.streams[i].coding;
        bool video = c == 0x1B || c == 0x02, audio = c == 0xDC || c == 0x80 || c == 0x81;
        bool match = type == 20 ? video : type == 21 ? audio :
                     type == 0 ? c == 0x1B : type == 1 ? c == 0x02 : type == 2 ? c == 0xDC :
                     type == 3 ? c == 0x80 : type == 4 ? c == 0x81 : type == 5 ? c == 0xDD : false;
        if (match && k++ == index) return (int)i;
    }
    return -1;
}
/* cellSailDescriptorSetEs(pSelf, esType, esIndex, enable, pSpecifier).
 * esType 1 = video, 0 = audio. For PAMF the specifier, when given, is the
 * CellPamfReader the game pointed at one stream with SetStreamWithTypeAndIndex. */
static void h_desc_set_es(ppu_context* ctx)
{
    auto it = s_desc.find(A(0));
    if (it == s_desc.end() || !it->second.opened) { RET(E_INVALID_STATE); return; }
    Desc& d = it->second;
    const int es = (int)A(1), idx = (int)A(2); const bool en = A(3) != 0; const uint32_t spec = A(4);
    int s = -1;
    if (spec) s = (int)(int32_t)vm_read32(spec + 0x1C);        /* reader.currentStreamIndex */
    else s = nth_stream(d.pi, es == 1 ? 20 : 21, idx);
    if (s < 0) { RET(E_INVALID_ARG); return; }
    if (es == 1) d.sel_video = en ? s : -1; else if (es == 0) d.sel_audio = en ? s : -1;
    MLOG("DescriptorSetEs es=%d index=%d enable=%d spec=0x%08X -> stream %d\n", es, idx, en, spec, s);
    RET(0);
}
/* The PAMF database is a CellPamfReader over the guest copy of the header. */
static void h_create_database(ppu_context* ctx)
{
    auto it = s_desc.find(A(0));
    if (it == s_desc.end() || !it->second.opened || !A(1) || A(2) < 0x80) { RET(E_INVALID_ARG); return; }
    Desc& d = it->second; const uint32_t r = A(1);
    memset(G(r), 0, 0x80);
    wbe64(r + 0x00, d.pi.header_size);
    wbe64(r + 0x08, d.pi.data_size);
    wbe32(r + 0x10, 0);                 /* attribute */
    wbe16(r + 0x14, 0);                 /* isPsmf */
    wbe16(r + 0x16, (uint16_t)((d.pi.header[6] - '0') * 10 + (d.pi.header[7] - '0')));
    wbe32(r + 0x18, 0); wbe32(r + 0x1C, (uint32_t)-1);      /* group period, (group|stream) */
    /* The reader's own layout: indices then header pointers (header, sequence
     * info, grouping period, group, current stream). */
    wbe32(r + 0x20, d.header_ea);
    wbe32(r + 0x24, d.header_ea + 0x50);
    wbe32(r + 0x28, d.header_ea + 0x7C);
    wbe32(r + 0x2C, d.header_ea + 0x84);
    wbe32(r + 0x30, 0);
    RET(0);
}
static void h_destroy_database(ppu_context* ctx) { if (A(1)) memset(G(A(1)), 0, 0x80); RET(0); }

static void h_pamf_set_stream_type_index(ppu_context* ctx)
{
    /* (pSelf reader, streamType, streamIndex) -> stream index or error */
    const uint32_t r = A(0);
    uint32_t hdr = r ? vm_read32(r + 0x20) : 0;
    Desc* d = nullptr;
    for (auto& kv : s_desc) if (kv.second.header_ea == hdr && hdr) d = &kv.second;
    if (!d) { RET(PAMF_INVALID); return; }
    int s = nth_stream(d->pi, (int)(uint8_t)A(1), (int)(uint8_t)A(2));
    MLOG("PamfReaderSetStreamWithTypeAndIndex type=%u index=%u -> %d\n", (unsigned)(uint8_t)A(1), (unsigned)(uint8_t)A(2), s);
    if (s < 0) { RET(PAMF_NOT_FOUND); return; }
    wbe32(r + 0x1C, (uint32_t)s);
    wbe32(r + 0x30, hdr + 0x88 + 0x30 * s);
    RET(s);
}
static void h_avi_get_stream(ppu_context* ctx) { RET(E_UNSUPPORTED); }

static void h_add_descriptor(ppu_context* ctx)
{
    if (A(0) != g.self || !s_desc.count(A(1))) { RET(E_INVALID_ARG); return; }
    g.cur_desc = A(1);
    RET(0);
}

static double frc_to_fps(int c)
{
    switch (c) { case 1: return 24000.0 / 1001; case 2: return 24; case 3: return 25; case 4: return 30000.0 / 1001;
                 case 5: return 30; case 6: return 50; case 7: return 60000.0 / 1001; case 8: return 60; }
    return 30000.0 / 1001;
}

static void h_open_stream(ppu_context* ctx)
{
    if (A(0) != g.self) { RET(E_INVALID_ARG); return; }
    auto it = s_desc.find(g.cur_desc);
    if (it == s_desc.end() || !it->second.opened) { RET(E_INVALID_STATE); return; }
    Desc& d = it->second;
    close_movie("reopen");
    Movie* mv = new Movie;
    mv->path = d.host; mv->pi = d.pi;
    mv->vidx = d.sel_video >= 0 ? d.sel_video : nth_stream(d.pi, 20, 0);
    mv->aidx = d.sel_audio;
    if (mv->vidx < 0) { delete mv; RET(E_UNSUPPORTED); return; }
    const uint8_t* vh = d.pi.header.data() + 0x88 + 0x30 * mv->vidx;
    mv->width = vh[0x19] * 16 ? vh[0x19] * 16 : 1280;            /* M2V/AVC: size / 16 */
    mv->height = vh[0x1B] * 16 ? vh[0x1B] * 16 : 720;
    if (mv->width < 16 || mv->width > 1920) mv->width = 1280;
    if (mv->height < 16 || mv->height > 1088) mv->height = 720;
    mv->fps = frc_to_fps(d.pi.streams[mv->vidx].frc);
    mv->ch = mv->aidx >= 0 ? (d.pi.streams[mv->aidx].ch == 6 ? 6 : d.pi.streams[mv->aidx].ch == 8 ? 8 : 2) : 2;
    g.mv = mv;
    g.session = ++s_session_counter;
    g.running = false; g.ended = false; g.eos_sent = false; g.clock_started = false;
    g.cur_frame_buf = 0; g.snd_served = 0; g.snd_tag = 0; g.cur_tag = 0;
    /* frame buffers come from the game's graphics adapter (they live where its
     * texture expects them); sound buffers from the player's allocator. */
    if (g.gfx_funcs[3] && g.scratch) {
        int64_t n = (int64_t)(int32_t)(uint32_t)gcall(g.gfx_funcs[3], g.gfx_arg, (uint64_t)mv->width * mv->height * 4,
                                                      NUM_GFX_BUFFERS, g.scratch);
        g.ngbuf = 0;
        for (int i = 0; i < NUM_GFX_BUFFERS; i++) { uint32_t b = vm_read32(g.scratch + 4 * i); if (b) g.gbuf[g.ngbuf++] = b; }
        for (int i = 0; i < g.ngbuf; i++) rsx_d3d12_cpu_texture(g.gbuf[i], (uint32_t)(mv->width * mv->height * 4), 1);
        MLOG("graphics Alloc(size %d, %d) -> %lld, %d buffers first 0x%08X\n", mv->width * mv->height * 4,
             NUM_GFX_BUFFERS, (long long)n, g.ngbuf, g.ngbuf ? g.gbuf[0] : 0);
    }
    for (int i = 0; i < NUM_SND_BUFFERS; i++) if (!g.sbuf[i]) g.sbuf[i] = galloc(AUDIO_BLOCK * 8 * 4);
    mv->th = std::thread(decode_thread, mv);
    MLOG("OpenStream %s %dx%d %.3f fps video stream %d audio stream %d (%d ch)\n", mv->path.c_str(), mv->width,
         mv->height, mv->fps, mv->vidx, mv->aidx, mv->ch);
    call_done(CALL_OPEN_STREAM, ST_OPEN_TRANSITION, ST_OPENED, A64(1));
    RET(0);
}

static void h_close_stream(ppu_context* ctx)
{
    if (A(0) != g.self) { RET(E_INVALID_ARG); return; }
    close_movie("close");
    call_done(CALL_CLOSE_STREAM, ST_CLOSE_TRANSITION, ST_CLOSED, A64(1));
    notify(EV_STREAM_CLOSED, 0, 0);
    RET(0);
}

/* Restart the decode thread on a new byte range (Start with a seek). */
static void movie_restart(Movie* mv, uint64_t so, uint64_t eo)
{
    movie_stop(mv);
    {
        std::unique_lock<std::mutex> l(mv->m);
        mv->frames.clear(); mv->pcm.clear();
        mv->demux_eof = mv->video_eof = mv->audio_eof = mv->quit = false;
        mv->frames_decoded = mv->frames_shown = mv->au_video = mv->au_audio = mv->samples_out = 0;
        for (double& r : mv->rms_sum) r = 0;
        mv->rms_n = 0; mv->peak = 0;
        mv->start_off = so; mv->end_off = eo;
    }
    mv->th = std::thread(decode_thread, mv);
}

static uint64_t rd64(uint32_t ea) { return (uint64_t)vm_read32(ea) << 32 | vm_read32(ea + 4); }

static void h_start(ppu_context* ctx)
{
    /* (pSelf, pCommand, userParam): the game (0x5C9980) passes a
     * CellSailStartCommand {startType, seekType, terminusType, flags, startArg,
     * reserved, u64 seekArg, u64 terminusArg} at r4 and 0 in r5. */
    if (A(0) != g.self || !g.mv) { RET(E_INVALID_STATE); return; }
    const uint32_t cmd = A(1);
    uint32_t st = 0, sk = 0, tt = 0, fl = 0; uint64_t sa = 0, ta = 0;
    if (cmd) { st = vm_read32(cmd); sk = vm_read32(cmd + 4); tt = vm_read32(cmd + 8); fl = vm_read32(cmd + 0xC);
               sa = rd64(cmd + 0x18); ta = rd64(cmd + 0x20); }
    Movie* mv = g.mv;
    const uint64_t d0 = mv->pi.data_offset;
    /* ABSOLUTE_BYTE_POSITION (seek 1, terminus 2). Whether the position counts
     * from the file start or the data start is not confirmed; a value below
     * the data start is taken as data-relative. Logged both ways. */
    auto to_file = [&](uint64_t v) { return (v >= d0 ? v : d0 + v) & ~0x7FFull; };
    uint64_t so = sk == 1 ? to_file(sa) : d0;
    uint64_t eo = tt == 2 ? to_file(ta + 0x7FF) : ~0ull;
    MLOG("PlayerStart cmd start=%u seek=%u terminus=%u flags=0x%X seekArg=0x%llX terminusArg=0x%llX -> file 0x%llX..0x%llX (data 0x%llX)\n",
         st, sk, tt, fl, (unsigned long long)sa, (unsigned long long)ta, (unsigned long long)so,
         (unsigned long long)eo, (unsigned long long)d0);
    if (so != (mv->start_off ? mv->start_off : d0) || eo != mv->end_off) movie_restart(mv, so, eo);
    g.running = true; g.paused = false; g.ended = false; g.eos_sent = false;
    /* the clock starts when the first frame is ready (GetFrame) */
    g.clock_started = false;
    call_done(CALL_START, ST_START_TRANSITION, ST_RUNNING, A64(2));
    RET(0);
}
static void h_stop(ppu_context* ctx)
{
    if (A(0) != g.self) { RET(E_INVALID_ARG); return; }
    MLOG("PlayerStop at clock %.2f\n", g.clock());
    g.running = false;
    if (g.mv) movie_report(g.mv, "stop");
    call_done(CALL_STOP, ST_STOP_TRANSITION, ST_OPENED, A64(1));
    RET(0);
}
static void h_set_paused(ppu_context* ctx)
{
    bool p = A(1) != 0;
    if (p && !g.paused) { g.paused_at = g.clock(); g.paused = true; }
    else if (!p && g.paused) {
        g.paused = false;
        g.t0 = std::chrono::steady_clock::now() - std::chrono::duration_cast<std::chrono::steady_clock::duration>(
                   std::chrono::duration<double>(g.paused_at));
    }
    RET(0);
}

/* End of stream, on the game's own thread: once every decoded frame has been
 * shown and the sound has been handed out, the player goes back to OPENED. */
static void check_end()
{
    Movie* mv = g.mv;
    if (!mv || g.eos_sent || !g.running) return;
    bool done;
    {
        std::unique_lock<std::mutex> l(mv->m);
        done = mv->demux_eof && mv->frames.empty() && mv->pcm.size() < (size_t)AUDIO_BLOCK * mv->ch;
    }
    if (!done) return;
    g.eos_sent = true; g.ended = true;
    movie_report(mv, "end of stream");
    notify(EV_SOURCE_EOS, 0, 0);
    notify(EV_STATE_CHANGED, 0, ST_STOP_TRANSITION);
    notify(EV_STATE_CHANGED, 0, ST_OPENED);
}

static void h_gfx_get_format(ppu_context* ctx)
{
    const uint32_t f = A(1);
    if (!f) { RET(E_INVALID_ARG); return; }
    Movie* mv = g.mv;
    memset(G(f), 0, 0x20);
    vm_write8(f + 0, 0);                         /* ARGB interleaved, as the game asked */
    vm_write8(f + 1, 0);                         /* progressive */
    vm_write8(f + 2, 8);                         /* bits per colour */
    int frc = -1;
    if (mv) { double fps = mv->fps; frc = fps < 24 ? 0 : fps < 24.5 ? 1 : fps < 26 ? 2 : fps < 29.99 ? 3 : fps < 31 ? 4 : fps < 51 ? 5 : fps < 59.99 ? 6 : 7; }
    vm_write8(f + 3, (uint8_t)frc);
    wbe16(f + 4, (uint16_t)(mv ? mv->width : 1280));
    wbe16(f + 6, (uint16_t)(mv ? mv->height : 720));
    wbe32(f + 8, (uint32_t)(mv ? mv->width : 1280) * 4);
    wbe32(f + 0xC, 0xFF);                        /* alpha */
    vm_write8(f + 0x10, 1);                      /* BT.709 */
    vm_write8(f + 0x11, 1);                      /* 1:1 */
    vm_write8(f + 0x12, 0);                      /* full range out */
    vm_write8(f + 0x13, 0xFF);
    wbe32(f + 0x14, 0xFFFFFFFFu); wbe32(f + 0x18, 0xFFFFFFFFu);
    RET(0);
}

static void h_gfx_get_frame(ppu_context* ctx)
{
    /* (pSelf, pInfo) -> info {+0 buffer, +4 session, +8 tag, +0xC status, +0x10 pts} */
    const uint32_t info = A(1);
    if (!info) { RET(E_INVALID_ARG); return; }
    Movie* mv = g.mv;
    memset(G(info), 0, 0x18);
    if (!mv || !g.running || !g.ngbuf) { RET(E_EMPTY); return; }
    bool have = false; Frame fr;
    {
        std::unique_lock<std::mutex> l(mv->m);
        if (!g.clock_started && mv->frames.empty() && mv->video_failed) {
            /* no picture can come: run the clock from now so the sound plays
             * and the stream still reaches its end (logged as a failure above) */
            g.t0 = std::chrono::steady_clock::now(); g.clock_started = true;
        }
        if (!g.clock_started && !mv->frames.empty()) {
            g.t0 = std::chrono::steady_clock::now() - std::chrono::duration_cast<std::chrono::steady_clock::duration>(
                       std::chrono::duration<double>(mv->frames.front().t));
            g.clock_started = true;
        }
        double now = g.clock();
        /* the decoder is behind: hold the clock instead of skipping ahead */
        if (g.clock_started && mv->frames.empty() && !mv->demux_eof && !g.paused) {
            double next = (double)mv->frames_decoded / mv->fps;
            if (now > next + 0.05)
                g.t0 = std::chrono::steady_clock::now() - std::chrono::duration_cast<std::chrono::steady_clock::duration>(
                           std::chrono::duration<double>(next));
        }
        while (mv->frames.size() > 1 && mv->frames[1].t <= now) { mv->frames.pop_front(); mv->frames_shown++; }
        if (!mv->frames.empty() && mv->frames.front().t <= now) {
            fr = std::move(mv->frames.front()); mv->frames.pop_front(); have = true;
        }
    }
    mv->cv.notify_all();
    uint32_t status;
    if (have) {
        uint32_t b = g.gbuf[g.next_g++ % g.ngbuf];
        memcpy(G(b), fr.argb.data(), fr.argb.size());
        if (mv->frames_shown % 300 == 0) {
            const uint8_t* q = G(b) + ((size_t)360 * mv->width + 640) * 4;
            MLOG("guest buf 0x%08X centre pixel A%02X R%02X G%02X B%02X\n", b, q[0], q[1], q[2], q[3]);
        }
        g.cur_frame_buf = b;
        g.cur_frame_pts = (uint64_t)mv->pi.start_pts + (uint64_t)(fr.t * 90000.0);
        g.cur_tag++;
        mv->frames_shown++;
        status = 0x200 | 0x4;                    /* NEXT, on time */
        if (mv->frames_shown == 1 || mv->frames_shown % 300 == 0)
            MLOG("video frame %llu pts %.2f s clock %.2f s queue %zu\n", (unsigned long long)mv->frames_shown,
                 fr.t, g.clock(), mv->frames.size());
    } else {
        check_end();
        if (!g.cur_frame_buf) { RET(E_EMPTY); return; }
        status = 0x100 | 0x4;                    /* the current frame again */
    }
    wbe32(info + 0x0, g.cur_frame_buf);
    wbe32(info + 0x4, g.session);
    wbe32(info + 0x8, g.cur_tag);
    wbe32(info + 0xC, status);
    wbe64(info + 0x10, g.cur_frame_pts);
    RET(status);
}

static void h_snd_get_format(ppu_context* ctx)
{
    const uint32_t f = A(1);
    if (!f) { RET(E_INVALID_ARG); return; }
    Movie* mv = g.mv;
    const int ch = mv ? mv->ch : 2;
    memset(G(f), 0, 0x18);
    vm_write8(f + 0, 1);                          /* LPCM float32 */
    vm_write8(f + 1, (uint8_t)ch);
    wbe16(f + 2, AUDIO_BLOCK);
    wbe32(f + 4, 48000);
    wbe32(f + 8, ch == 6 ? 8u : ch == 8 ? 11u : 2u);   /* 6CH_LCRlrE / 8CH / 2CH_LR */
    wbe32(f + 0xC, 0xFFFFFFFFu); wbe32(f + 0x10, 0xFFFFFFFFu); wbe32(f + 0x14, 0xFFFFFFFFu);
    RET(0);
}

static void h_snd_get_frame(ppu_context* ctx)
{
    /* (pSelf, samples, pInfo) */
    const uint32_t info = A(2);
    const int n = (int)A(1) > 0 && (int)A(1) <= 2048 ? (int)A(1) : AUDIO_BLOCK;
    if (!info) { RET(E_INVALID_ARG); return; }
    Movie* mv = g.mv;
    memset(G(info), 0, 0x18);
    if (!mv || !g.running || g.paused || !g.clock_started) { RET(E_EMPTY); return; }
    /* pace by the player clock: one block per block of movie time, a few ahead */
    if (g.snd_served * (uint64_t)n >= (uint64_t)(g.clock() * 48000.0) + 4 * (uint64_t)n) { RET(E_EMPTY); return; }
    const uint32_t buf = g.sbuf[g.next_s++ % NUM_SND_BUFFERS];
    if (!buf) { RET(E_MEMORY); return; }
    {
        std::unique_lock<std::mutex> l(mv->m);
        const size_t need = (size_t)n * mv->ch;
        if (mv->pcm.size() < need) { RET(E_EMPTY); return; }
        uint32_t* o = (uint32_t*)G(buf);
        for (size_t i = 0; i < need; i++) {
            float v = mv->pcm.front(); mv->pcm.pop_front();
            uint32_t w; memcpy(&w, &v, 4);
            o[i] = _byteswap_ulong(w);
        }
    }
    mv->cv.notify_all();
    g.snd_served++;
    mv->samples_out += n;
    if (g.snd_served == 1 || g.snd_served % 2000 == 0)
        MLOG("sound block %llu (%d ch) clock %.2f s\n", (unsigned long long)g.snd_served, mv->ch, g.clock());
    wbe32(info + 0x0, buf);
    wbe32(info + 0x4, g.session);
    wbe32(info + 0x8, ++g.snd_tag);
    wbe32(info + 0xC, 0x204);
    wbe64(info + 0x10, (uint64_t)mv->pi.start_pts + (uint64_t)((g.snd_served - 1) * (uint64_t)n * 90000ull / 48000ull));
    RET(0x204);
}

/* PtsToTimePosition(pSelf, pts, pTimePosition): time from the stream start in
 * 90 kHz units (the game converts only pts > 89999 = the PAMF start of 90000). */
static void h_pts_to_time(ppu_context* ctx)
{
    if (!A(2)) { RET(E_INVALID_ARG); return; }
    const uint64_t start = g.mv ? g.mv->pi.start_pts : 90000;
    const uint64_t pts = A64(1);
    wbe64(A(2), pts > start ? pts - start : 0);
    RET(0);
}
static void h_update_avsync(ppu_context* ctx) { RET(0); }

#undef A
#undef A64
#undef RET

} // namespace sf_movie

static void sf_register_movie_overrides(void)
{
    using namespace sf_movie;
    const char* e = getenv("SF_MOVIE_LOG");
    s_log = !(e && *e == '0');
    struct { uint32_t nid; const char* name; void (*fn)(ppu_context*); } t[] = {
        {0x346EBBA3u, "cellSailMemAllocatorInitialize[sfm]", h_mem_allocator_init},
        {0x23654375u, "cellSailPlayerInitialize2[sfm]", h_player_init2},
        {0x18B4629Du, "cellSailPlayerFinalize[sfm]", h_player_finalize},
        {0x1139A206u, "cellSailPlayerSetSoundAdapter[sfm]", h_set_sound_adapter},
        {0x18BCD21Bu, "cellSailPlayerSetGraphicsAdapter[sfm]", h_set_graphics_adapter},
        {0xBDF21B0Fu, "cellSailPlayerBoot[sfm]", h_player_boot},
        {0xD7938B8Du, "cellSailPlayerCreateDescriptor[sfm]", h_create_descriptor},
        {0xFC839BD4u, "cellSailPlayerDestroyDescriptor[sfm]", h_destroy_descriptor},
        {0x7C8DFF3Bu, "cellSailPlayerAddDescriptor[sfm]", h_add_descriptor},
        {0x34ECC1B9u, "cellSailPlayerOpenStream[sfm]", h_open_stream},
        {0x85BEFFCCu, "cellSailPlayerCloseStream[sfm]", h_close_stream},
        {0xE535B0D3u, "cellSailPlayerStart[sfm]", h_start},
        {0xEBA8D4ECu, "cellSailPlayerStop[sfm]", h_stop},
        {0xD1D55A90u, "cellSailPlayerSetPaused[sfm]", h_set_paused},
        {0x76B1A425u, "cellSailDescriptorSetAutoSelection[sfm]", h_set_auto_selection},
        {0xC044FAB1u, "cellSailDescriptorOpen[sfm]", h_desc_open},
        {0x15FD6A2Au, "cellSailDescriptorClose[sfm]", h_desc_close},
        {0x0D0C2F0Cu, "cellSailDescriptorSetEs[sfm]", h_desc_set_es},
        {0x0ABB318Bu, "cellSailDescriptorCreateDatabase[sfm]", h_create_database},
        {0x28336E89u, "cellSailDescriptorDestroyDatabase[sfm]", h_destroy_database},
        {0xDDEBD2A5u, "cellSailAviMovieGetStreamByTypeAndIndex[sfm]", h_avi_get_stream},
        {0x28B4E2C1u, "cellPamfReaderSetStreamWithTypeAndIndex[sfm]", h_pamf_set_stream_type_index},
        {0x3D0D3B72u, "cellSailSoundAdapterInitialize[sfm]", h_snd_init},
        {0xD1462438u, "cellSailSoundAdapterFinalize[sfm]", h_finalize_ok},
        {0xF25F197Du, "cellSailSoundAdapterGetFormat[sfm]", h_snd_get_format},
        {0x7EB8D6B5u, "cellSailSoundAdapterGetFrame[sfm]", h_snd_get_frame},
        {0x4AE979DFu, "cellSailSoundAdapterPtsToTimePosition[sfm]", h_pts_to_time},
        {0xEEC22809u, "cellSailSoundAdapterUpdateAvSync[sfm]", h_update_avsync},
        {0x1C983864u, "cellSailGraphicsAdapterInitialize[sfm]", h_gfx_init},
        {0x76488BB1u, "cellSailGraphicsAdapterFinalize[sfm]", h_finalize_ok},
        {0x2E3CCB5Eu, "cellSailGraphicsAdapterSetPreferredFormat[sfm]", h_gfx_set_pref},
        {0xFFD58AA4u, "cellSailGraphicsAdapterGetFormat[sfm]", h_gfx_get_format},
        {0x0247C69Eu, "cellSailGraphicsAdapterGetFrame[sfm]", h_gfx_get_frame},
        {0x1872331Bu, "cellSailGraphicsAdapterPtsToTimePosition[sfm]", h_pts_to_time},
        {0x44A20E79u, "cellSailGraphicsAdapterUpdateAvSync[sfm]", h_update_avsync},
    };
    for (auto& x : t) ps3_hle_register_ctx(x.nid, x.name, x.fn);
    fprintf(stderr, "[sf-movie] cellSail/cellPamf movie player registered (%zu functions)\n", sizeof t / sizeof t[0]);
}
