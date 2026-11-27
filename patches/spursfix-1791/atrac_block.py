# ---------- cellAtrac.c  (SF_ATRAC_LOG=1, field list of sf-shared/atrac-validator/README.md)
s=load('cellAtrac.c')
s=rep(s,'static AtracSlot s_slots[ATRAC_MAX_SLOTS];','''

/* [sf-blackhang] LOG-ONLY: SF_ATRAC_LOG=1 -> one "[sf-atrac] fn=... key=value" line per
 * streaming call (atrac-validator/README.md field list). It only reads state and
 * hashes bytes; nothing feeds back into decoding or the guest. */
#ifdef _WIN32
__declspec(dllimport) unsigned long __stdcall GetCurrentThreadId(void);
#define SFA_TID() ((unsigned long)GetCurrentThreadId())
#else
#define SFA_TID() 0ul
#endif
static int sfa_on(void) { static int v = -1; if (v < 0) { const char* e = getenv("SF_ATRAC_LOG"); v = e ? atoi(e) : 0; if (v) fprintf(stderr, "[sf-atrac] fn=Armed SF_ATRAC_LOG=%d\\n", v); } return v; }
static u32 sfa_fnv(const u8* p, u32 n) { u32 h = 0x811C9DC5u; for (u32 i = 0; i < n; i++) { h ^= p[i]; h *= 0x01000193u; } return h; }
typedef struct { u32 given; u32 ra_wea, ra_len, ra_off; int ra_pending; } SfaSlot;
static SfaSlot s_sfa[ATRAC_MAX_SLOTS];
#define SFA_X(s) (&s_sfa[(int)((s) - s_slots)])
#define SFA(s, fn, fmt, ...) do { if (sfa_on() && (s)) fprintf(stderr, "[sf-atrac] fn=%s tid=%lu h=0x%08X " fmt "\\n", fn, SFA_TID(), (s)->handle_ea, ##__VA_ARGS__); } while (0)
/* AddRecheck: re-hash the ring bytes of the previous add at the next call on this handle. */
static void sfa_recheck(AtracSlot* s)
{
    if (!sfa_on() || !s) return;
    SfaSlot* x = SFA_X(s);
    if (!x->ra_pending) return;
    x->ra_pending = 0;
    SFA(s, "AddRecheck", "off=%u len=%u wea=0x%08X fnv=0x%08X", x->ra_off, x->ra_len, x->ra_wea, sfa_fnv(vm_base + x->ra_wea, x->ra_len));
}''',where='at1')
# DecodeFrame / DecodeError in decode_frame (same decoder call, rc kept for the log)
s=sub(s,'''        if (at3p_decode(s->dec, planes, &n, s->file + at,\r
                        (int)s->t.block_align) < 0 || n != AT3P_SAMPLES) {\r
''','''        const int sfa_rc = at3p_decode(s->dec, planes, &n, s->file + at, (int)s->t.block_align);   /* [sf-blackhang] same call; rc kept for the log */\r
        if (sfa_on()) {\r
            const u8* b = s->file + at; const u32 ba = s->t.block_align;\r
            if (sfa_rc < 0 || n != AT3P_SAMPLES)\r
                SFA(s, "DecodeError", "k=%d off=%u len=%u fnv=0x%08X first16=%02X%02X%02X%02X%02X%02X%02X%02X%02X%02X%02X%02X%02X%02X%02X%02X msg=\\"rc=%d n=%d\\"",\r
                    s->next_frame, at, ba, sfa_fnv(b, ba), b[0],b[1],b[2],b[3],b[4],b[5],b[6],b[7],b[8],b[9],b[10],b[11],b[12],b[13],b[14],b[15], sfa_rc, n);\r
            else if (s->t.channels == 6)\r
                SFA(s, "DecodeFrame", "k=%d off=%u len=%u fnv=0x%08X b0=0x%02X rc=%d", s->next_frame, at, ba, sfa_fnv(b, ba), b[0], sfa_rc);\r
        }\r
        if (sfa_rc < 0 || n != AT3P_SAMPLES) {\r
''','at2')
s=sub(s,'''    if (decode_frame(s, k) < 0) {\r
''','''    sfa_recheck(s);   /* [sf-blackhang] log-only */\r
    if (decode_frame(s, k) < 0) {\r
        SFA(s, "DecodeNoData", "k=%d next_frame=%d fed=%u", k, s->next_frame, s->file_fed);   /* [sf-blackhang] log-only */\r
''','at3')
# GetStreamDataInfo
s=sub(s,'''    ring_release_consumed(s);\r
    if (s->all_on_mem || (s->file_total && s->file_fed >= s->file_total))\r
        return (s32)CELL_ATRAC_ERROR_ALLDATA_IS_ONMEMORY;\r
    u32 wea = 0;\r
    const u32 wr = ring_writable(s, &wea);\r
    if (ppucWritePointer) vm_write32(ppucWritePointer, wea);\r
    if (puiWritableByte) vm_write32(puiWritableByte, wr);\r
    if (puiReadPosition) vm_write32(puiReadPosition, s->file_fed);\r
    return CELL_OK;\r
''','''    sfa_recheck(s);   /* [sf-blackhang] log-only */\r
    ring_release_consumed(s);\r
    if (s->all_on_mem || (s->file_total && s->file_fed >= s->file_total)) {\r
        SFA(s, "GetStreamDataInfo", "wea_given=0x0 writable=0 readpos=%u voff=%u vbytes=%u fed=%u rc=0x%08X", s->file_fed, s->valid_off, s->valid_bytes, s->file_fed, (u32)CELL_ATRAC_ERROR_ALLDATA_IS_ONMEMORY);\r
        return (s32)CELL_ATRAC_ERROR_ALLDATA_IS_ONMEMORY;\r
    }\r
    u32 wea = 0;\r
    const u32 wr = ring_writable(s, &wea);\r
    if (ppucWritePointer) vm_write32(ppucWritePointer, wea);\r
    if (puiWritableByte) vm_write32(puiWritableByte, wr);\r
    if (puiReadPosition) vm_write32(puiReadPosition, s->file_fed);\r
    SFA_X(s)->given = wea;   /* [sf-blackhang] log-only */\r
    SFA(s, "GetStreamDataInfo", "wea_given=0x%08X writable=%u readpos=%u voff=%u vbytes=%u fed=%u rc=0x0", wea, wr, s->file_fed, s->valid_off, s->valid_bytes, s->file_fed);\r
    return CELL_OK;\r
''','at4')
# AddStreamData
s=sub(s,'''    if (s->all_on_mem || uiAddByte == 0) return CELL_OK;\r
    u32 wea = 0;\r
    const u32 wr = ring_writable(s, &wea);\r
    if (uiAddByte > wr) return (s32)CELL_ATRAC_ERROR_ADD_DATA_IS_TOO_BIG;\r
    if (s->host) {\r
        if (s->file_fed + uiAddByte > s->host_cap)\r
            return (s32)CELL_ATRAC_ERROR_ADD_DATA_IS_TOO_BIG;\r
        memcpy(s->host + s->file_fed, vm_base + wea, uiAddByte);\r
    }\r
    s->file_fed += uiAddByte;\r
    s->valid_bytes += uiAddByte;\r
    if (s->file_total && s->file_fed >= s->file_total) s->all_on_mem = 1;\r
    return CELL_OK;\r
''','''    sfa_recheck(s);   /* [sf-blackhang] log-only */\r
    const u32 sfa_off = s->file_fed;\r
    if (s->all_on_mem || uiAddByte == 0) { SFA(s, "AddStreamData", "add=%u off=%u wea_given=0x%08X wea_used=0x0 voff=%u vbytes=%u fed_after=%u rc=0x0 fnv=0x0 note=%s", uiAddByte, sfa_off, SFA_X(s)->given, s->valid_off, s->valid_bytes, s->file_fed, s->all_on_mem ? "all_on_mem" : "zero_add"); return CELL_OK; }\r
    u32 wea = 0;\r
    const u32 wr = ring_writable(s, &wea);\r
    if (uiAddByte > wr) { SFA(s, "AddStreamData", "add=%u off=%u wea_given=0x%08X wea_used=0x%08X voff=%u vbytes=%u fed_after=%u rc=0x%08X fnv=0x0 writable=%u", uiAddByte, sfa_off, SFA_X(s)->given, wea, s->valid_off, s->valid_bytes, s->file_fed, (u32)CELL_ATRAC_ERROR_ADD_DATA_IS_TOO_BIG, wr); return (s32)CELL_ATRAC_ERROR_ADD_DATA_IS_TOO_BIG; }\r
    if (s->host) {\r
        if (s->file_fed + uiAddByte > s->host_cap) {\r
            SFA(s, "AddStreamData", "add=%u off=%u wea_given=0x%08X wea_used=0x%08X voff=%u vbytes=%u fed_after=%u rc=0x%08X fnv=0x0 note=host_cap", uiAddByte, sfa_off, SFA_X(s)->given, wea, s->valid_off, s->valid_bytes, s->file_fed, (u32)CELL_ATRAC_ERROR_ADD_DATA_IS_TOO_BIG);\r
            return (s32)CELL_ATRAC_ERROR_ADD_DATA_IS_TOO_BIG;\r
        }\r
        memcpy(s->host + s->file_fed, vm_base + wea, uiAddByte);\r
    }\r
    s->file_fed += uiAddByte;\r
    s->valid_bytes += uiAddByte;\r
    if (s->file_total && s->file_fed >= s->file_total) s->all_on_mem = 1;\r
    if (sfa_on()) {   /* [sf-blackhang] log-only */\r
        SFA(s, "AddStreamData", "add=%u off=%u wea_given=0x%08X wea_used=0x%08X voff=%u vbytes=%u fed_after=%u rc=0x0 fnv=0x%08X", uiAddByte, sfa_off, SFA_X(s)->given, wea, s->valid_off, s->valid_bytes, s->file_fed, sfa_fnv(vm_base + wea, uiAddByte));\r
        SfaSlot* x = SFA_X(s); x->ra_wea = wea; x->ra_len = uiAddByte; x->ra_off = sfa_off; x->ra_pending = 1;\r
    }\r
    return CELL_OK;\r
''','at5')
# ResetPlayPosition
s=sub(s,'''    if (p >= s->t.end) return (s32)CELL_ATRAC_ERROR_ILLEGAL_SAMPLE;\r
    if (!s->all_on_mem && uiWriteByte) {\r
''','''    if (p >= s->t.end) return (s32)CELL_ATRAC_ERROR_ILLEGAL_SAMPLE;\r
    sfa_recheck(s);   /* [sf-blackhang] log-only */\r
    const u32 sfa_fed0 = s->file_fed; const s32 sfa_nf0 = s->next_frame;\r
    const u32 sfa_roff = s->t.data_off + (u32)(p / AT3P_SAMPLES) * s->t.block_align;\r
    if (!s->all_on_mem && uiWriteByte) {\r
''','at6')
s=sub(s,'''    }\r
    s->pos = p;\r
    return CELL_OK;\r
}\r
\r
s32 cellAtracGetStreamDataInfo''','''    }\r
    s->pos = p;\r
    SFA(s, "ResetPlayPosition", "sample=%u wb=%u roff=%u fed_before=%u fed_after=%u next_frame_before=%d flushed=0 rc=0x0", uiSample, uiWriteByte, sfa_roff, sfa_fed0, s->file_fed, sfa_nf0);   /* [sf-blackhang] log-only */\r
    return CELL_OK;\r
}\r
\r
s32 cellAtracGetStreamDataInfo''','at6b')
# GetBufferInfoForResetting
s=sub(s,'''    vm_write32(pBufferInfo + 12, roff);\r
    return CELL_OK;\r
''','''    vm_write32(pBufferInfo + 12, roff);\r
    SFA(s, "GetBufferInfoForResetting", "sample=%u info_wea=0x%08X info_bytes=%u info_min=%u info_readpos=%u rc=0x0", uiSample, s->buf_ea, s->buf_size, s->t.block_align, roff);   /* [sf-blackhang] log-only */\r
    return CELL_OK;\r
''','at8')
# SetData
s=sub(s,'''    if (puiWorkMemByte) vm_write32(puiWorkMemByte, 0x1000);\r
''','''    if (puiWorkMemByte) vm_write32(puiWorkMemByte, 0x1000);\r
    memset(SFA_X(s), 0, sizeof(SfaSlot));   /* [sf-blackhang] log-only */\r
    SFA(s, "SetData", "ch=%u ba=%u doff=%u first=%d end=%d ls=%d le=%d buf=0x%08X bufsz=%u read=%u total=%u rc=0x0", t.channels, t.block_align, t.data_off, t.first, t.end, t.loop_start, t.loop_end, pucBufferAddr, s->buf_size, uiReadByte, total);\r
''','at7')
save('cellAtrac.c',s)
