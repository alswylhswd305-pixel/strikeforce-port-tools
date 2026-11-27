/* Test-copy diagnostic cheat only. Env-gated god mode (SF_GODMODE=1).
 * Include this in a translation unit that already has vm_base and vm_oob
 * (same place as the 1786 voice-monitor / HLE-log hook).
 * Host thread periodically writes confirmed player HP / knockdown words
 * listed in SF_GODMODE_ADDRS (text: "0xEA u32 0xVALUE" or "0xEA f32 123.0").
 * If the file is missing or empty, the thread logs once and writes nothing.
 * Do not compile this into the exe used by PLAY_Strikeforce.bat. Install a
 * build only under sfauto\exe_copies\<tag>\ (e.g. 1786_autotest). Never
 * overwrite 1786_movie_v5 while Saud is using it. See BUILD_NOTES.md.
 */
#pragma once
#include <thread>
#include <vector>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <atomic>
#include <chrono>

struct SfGodEntry { uint32_t ea; int is_f32; uint32_t u; float f; };

static std::atomic<int> s_sf_god{0};

static void sf_god_store_be(uint32_t ea, uint32_t host_u) {
    if (vm_oob(ea, 4)) return;
    uint8_t* p = (uint8_t*)vm_base + ea;
    p[0] = (uint8_t)(host_u >> 24);
    p[1] = (uint8_t)(host_u >> 16);
    p[2] = (uint8_t)(host_u >> 8);
    p[3] = (uint8_t)host_u;
}

static int sf_god_load(const char* path, std::vector<SfGodEntry>& out) {
    out.clear();
    if (!path || !path[0]) return 0;
    FILE* f = fopen(path, "rb");
    if (!f) return 0;
    char line[256];
    while (fgets(line, sizeof line, f)) {
        if (line[0] == '#' || line[0] == '\n' || line[0] == '\r') continue;
        char kind[8] = {0};
        unsigned long ea = 0;
        if (sscanf(line, "0x%lx %7s", &ea, kind) < 2) continue;
        SfGodEntry e{};
        e.ea = (uint32_t)ea;
        e.is_f32 = (strcmp(kind, "f32") == 0);
        if (e.is_f32) {
            float v = 0;
            sscanf(line, "%*s %*s %f", &v);
            e.f = v;
        } else {
            unsigned long v = 0;
            if (sscanf(line, "%*s %*s 0x%lx", &v) != 1)
                sscanf(line, "%*s %*s %lu", &v);
            e.u = (uint32_t)v;
        }
        if (e.ea) out.push_back(e);
    }
    fclose(f);
    return (int)out.size();
}

static void sf_god_loop(void) {
    const char* path = getenv("SF_GODMODE_ADDRS");
    int ms = 100;
    if (const char* e = getenv("SF_GODMODE_MS")) { ms = atoi(e); if (ms < 16) ms = 16; }
    std::vector<SfGodEntry> ents;
    int n = sf_god_load(path, ents);
    fprintf(stderr, "[sf-god] start addrs=%d file=%s every %d ms\n", n, path ? path : "(none)", ms);
    fflush(stderr);
    if (n <= 0) return;
    for (;;) {
        if (!s_sf_god.load()) break;
        for (size_t i = 0; i < ents.size(); i++) {
            if (ents[i].is_f32) {
                union { float f; uint32_t u; } c;
                c.f = ents[i].f;
                sf_god_store_be(ents[i].ea, c.u);
            } else {
                sf_god_store_be(ents[i].ea, ents[i].u);
            }
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(ms));
    }
    fprintf(stderr, "[sf-god] stopped\n");
}

extern "C" void sf_godmode_start(void) {
    const char* e = getenv("SF_GODMODE");
    if (!e || e[0] != '1') return;
    s_sf_god.store(1);
    std::thread(sf_god_loop).detach();
}
