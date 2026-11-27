/* ---------------------------------------------------------------------------
 * Strikeforce port override: SPURS LFQueue (PPU -> SPU), port-local, SDK untouched.
 *
 * v0.20.0 has no _cellSpursLFQueuePushBody (NID 0x8A85674D): it is faked as
 * CELL_OK, nothing is pushed, and the game's SPU consumer spins on GETLLAR of
 * the queue line forever. Its _cellSpursLFQueueInitialize writes depth at
 * +0x0C, i.e. into push1.m_h7/m_h8 of the SDK's CellSyncLFQueue layout,
 * which this title's SPU consumer reads as the push-reserve counter.
 *
 * Clean-room from the public CellSyncLFQueue layout (0x00 pop1 h1..h4,
 * 0x08 push1 h5..h8, 0x10 size, 0x14 depth, 0x18 buffer u64, 0x20 bs[4],
 * 0x24 direction, 0x28 v1, 0x2C init, 0x30 push2, 0x50 pop2, 0x70 eaSignal)
 * and Saud's earlier Workbench findings. Single serialized PPU producer:
 * reserve (h8) and complete (h5) advance together. No consumer signal is
 * sent (the observed consumer polls the line). Blocking push waits by
 * yielding. Not a general implementation.
 * -----------------------------------------------------------------------*/
#include <atomic>
#include <mutex>
#include <thread>
#include <chrono>
#include "ppu_context.h"
extern "C" uint8_t* vm_base;
extern "C" void spu_lockline_lock(void);
extern "C" void spu_lockline_unlock(void);
extern "C" void spu_coh_notify_write(uint32_t ea);
extern "C" void ps3_hle_register_ctx(uint32_t nid, const char* name, void (*fn)(ppu_context*));

namespace sf_lfq {
static const uint32_t E_AGAIN = 0x80410901u, E_INVAL = 0x80410902u, E_PERM = 0x80410909u,
                      E_STAT = 0x8041090Fu, E_ALIGN = 0x80410910u, E_NULL = 0x80410911u;
static inline uint8_t* P(uint32_t ea) { return vm_base + ea; }
static inline uint16_t r16(uint32_t ea) { uint8_t* p = P(ea); return (uint16_t)((p[0] << 8) | p[1]); }
static inline uint32_t r32(uint32_t ea) { uint8_t* p = P(ea); return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | p[3]; }
static inline void w16(uint32_t ea, uint16_t v) { uint8_t* p = P(ea); p[0] = (uint8_t)(v >> 8); p[1] = (uint8_t)v; }
static inline void w32(uint32_t ea, uint32_t v) { uint8_t* p = P(ea); p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16); p[2] = (uint8_t)(v >> 8); p[3] = (uint8_t)v; }
static inline void w64(uint32_t ea, uint64_t v) { w32(ea, (uint32_t)(v >> 32)); w32(ea + 4, (uint32_t)v); }
static std::mutex g_push_mu;
static std::atomic<unsigned> g_init_n{0}, g_push_n{0}, g_full_n{0};

static void hle_init(ppu_context* ctx)
{
    const uint32_t owner = (uint32_t)ctx->gpr[3], q = (uint32_t)ctx->gpr[4], buf = (uint32_t)ctx->gpr[5];
    const uint32_t size = (uint32_t)ctx->gpr[6], depth = (uint32_t)ctx->gpr[7], dir = (uint32_t)ctx->gpr[8];
    uint32_t rc = 0;
    if (!q || (size && !buf)) rc = E_NULL;
    else if ((size && (size > 0x4000 || (size & 15))) || !depth || depth > 0x7fff || dir > 3) rc = E_INVAL;
    else if ((q & 127) || (buf & 15)) rc = E_ALIGN;
    else {
        spu_lockline_lock();
        const uint32_t init = r32(q + 0x2C);
        if (init == 2) {
            if (r32(q + 0x10) != size || r32(q + 0x14) != depth || r32(q + 0x1C) != buf) rc = E_INVAL;
        } else if (init != 0) {
            rc = E_STAT;
        } else {
            memset(P(q), 0, 128);
            w32(q + 0x10, size);
            w32(q + 0x14, depth);
            w64(q + 0x18, (uint64_t)buf | (dir == 3 ? 1u : 0u));
            w32(q + 0x20, 0xFFFFFFFFu);              /* bs[4] = -1 */
            w32(q + 0x24, dir);
            w32(q + 0x28, dir == 3 ? 0xFFFFFFFFu : 0u); /* v1 */
            if (dir == 3) { w16(q + 0x30, 0xFFFF); w16(q + 0x50, 0xFFFF); }
            w64(q + 0x70, (uint64_t)owner);          /* eaSignal = taskset */
        }
        spu_lockline_unlock();
        spu_coh_notify_write(q);
    }
    if (g_init_n++ < 16)
        fprintf(stderr, "[sf-lfq] init owner=0x%08X q=0x%08X buf=0x%08X size=%u depth=%u dir=%u -> 0x%08X\n",
                owner, q, buf, size, depth, dir, rc);
    ctx->gpr[3] = rc;
}

static void hle_push(ppu_context* ctx)
{
    const uint32_t q = (uint32_t)ctx->gpr[3], src = (uint32_t)ctx->gpr[4], blocking = (uint32_t)ctx->gpr[5];
    uint32_t rc = 0, slot = 0, dest = 0, h1 = 0, h8 = 0;
    if (!q || !src) { ctx->gpr[3] = E_NULL; return; }
    if (q & 127) { ctx->gpr[3] = E_ALIGN; return; }
    for (unsigned spins = 0;; spins++) {
        {
            std::lock_guard<std::mutex> g(g_push_mu);
            spu_lockline_lock();
            const uint32_t dir = r32(q + 0x24), size = r32(q + 0x10), depth = r32(q + 0x14);
            const uint32_t buf = r32(q + 0x1C) & ~1u, ring = 2 * depth;
            if (dir != 2) rc = E_PERM;
            else if (!depth || !size) rc = E_STAT;
            else {
                h1 = r16(q + 0x00); h8 = r16(q + 0x0E);
                uint32_t used = (h8 + ring - h1) % ring;
                if (used >= depth) rc = E_AGAIN;
                else {
                    slot = h8;
                    dest = buf + size * (slot >= depth ? slot - depth : slot);
                    memcpy(P(dest), P(src), size);
                    std::atomic_thread_fence(std::memory_order_seq_cst);
                    const uint16_t next = (uint16_t)(slot + 1 >= ring ? 0 : slot + 1);
                    w16(q + 0x0E, next);   /* push1.m_h8: reserved */
                    w16(q + 0x08, next);   /* push1.m_h5: completed */
                    rc = 0;
                }
            }
            spu_lockline_unlock();
            if (rc == 0) { spu_coh_notify_write(dest); spu_coh_notify_write(q); }
        }
        if (rc == E_AGAIN && blocking) {
            if (g_full_n++ < 4) fprintf(stderr, "[sf-lfq] push q=0x%08X full, blocking wait\n", q);
            std::this_thread::sleep_for(std::chrono::microseconds(spins < 64 ? 0 : 200));
            continue;
        }
        break;
    }
    if (g_push_n++ < 24)
        fprintf(stderr, "[sf-lfq] push#%u q=0x%08X src=0x%08X blk=%u h1=%u slot=%u dest=0x%08X -> 0x%08X\n",
                (unsigned)g_push_n.load(), q, src, blocking, h1, slot, dest, rc);
    ctx->gpr[3] = rc;
}
} /* namespace sf_lfq */

static void sf_register_lfqueue_overrides(void)
{
    ps3_hle_register_ctx(0x011EE38Bu, "_cellSpursLFQueueInitialize[sf-port]", sf_lfq::hle_init);
    ps3_hle_register_ctx(0x8A85674Du, "_cellSpursLFQueuePushBody[sf-port]", sf_lfq::hle_push);
    fprintf(stderr, "[sf-lfq] port overrides registered (init 0x011EE38B, push 0x8A85674D)\n");
}
