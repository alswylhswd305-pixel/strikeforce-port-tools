#!/usr/bin/env python3
"""voice_freeze_analyzer.py - Strikeforce (BLUS30471) voice-burst / gate-freeze log analyzer.

Stdlib only. Written for the SF-DIAG 1786 log lines ([sfww], [vi], [vm], [vm-cnt],
[vm-rec], [vm-sum], [hle-lr], [hle-lrc]) plus the runtime's own stderr lines
([cellSpurs] EventFlagWait, [WAIT] ..., [spu] ... unlifted, [SPU-HALT], [SPU-TRACE],
[spu_workload] ... RETURNED, [fs] open, [cellAtrac], [SYS] sys_ppu_thread_create,
[watchea], [mfc] REJECTED ...). Unknown lines are counted by shape, never fatal.
Add a format: append a (name, regex) pair to PATTERNS and, if it needs logic,
a branch in Analyzer.feed().

Usage:
  python3 voice_freeze_analyzer.py LOG [LOG ...] [--stubs stub_missing_called.json]
          [--out DIR] [--cap 128] [--win 100] [--freezer-tid 7] [--starter-tid 17]
  python3 voice_freeze_analyzer.py --selftest
Outputs DIR/report.md and DIR/report.json (default DIR = ./vf_out).
"""
import argparse, collections, hashlib, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA = os.path.normpath(os.path.join(HERE, '..', 'testloop', 'reports'))

# ---------------------------------------------------------------- known addresses
# (from SF-DIAG 1786 source: sf_voice_mon_loop arrays and SF_WW_RANGES)
ARRAY_NAMES = {0x1119E080: 'st7650', 0x1119E580: 'st7640', 0x111AA880: 'st7664',
               0x111EED80: 'gen7644', 0x111A1780: 'vtable'}
VOICE_REC_BASE, VOICE_REC_SIZE = 0x11136A80, 0x930
MIXER_IMG = '391227015'
MIXER_FLAG = 0x00DBA900
MIXER_TRAP_PC = 0x31C20

# ---------------------------------------------------------------- NID names
# NID = first 4 bytes (little-endian u32) of SHA1(name + fixed 16-byte suffix): public scheme.
_NID_SUFFIX = bytes.fromhex('6759659904250490566427499489741A')
_NID_CANDIDATES = """sys_lwmutex_create sys_lwmutex_destroy sys_lwmutex_lock sys_lwmutex_trylock
sys_lwmutex_unlock sys_lwcond_create sys_lwcond_destroy sys_lwcond_wait sys_lwcond_signal
sys_lwcond_signal_all sys_lwcond_signal_to sys_time_get_system_time sys_ppu_thread_get_id
sys_ppu_thread_exit sys_ppu_thread_create sys_ppu_thread_once sys_initialize_tls
sys_process_exit _sys_process_atexitspawn _sys_process_at_Exitspawn sys_prx_exitspawn_with_level
cellSpursEventFlagWait cellSpursEventFlagSet cellSpursEventFlagClear cellSpursEventFlagTryWait
cellSpursEventFlagInitialize cellSpursEventFlagAttachLv2EventQueue cellSpursCreateTask
cellSpursCreateTaskset cellSpursSendSignal cellSpursAttributeInitialize cellSpursInitialize
cellSyncLFQueuePush cellSyncLFQueuePop cellSyncLFQueueTryPush cellSyncLFQueueTryPop
cellSyncLFQueueInitialize cellSyncLFQueueSize cellSyncMutexLock cellSyncMutexUnlock
cellSyncBarrierNotify cellSyncBarrierWait cellAudioInit cellAudioPortOpen cellAudioPortStart
cellAudioPortStop cellAudioGetPortConfig cellAudioCreateNotifyEventQueue cellAudioSetNotifyEventQueue
cellAtracCreateDecoder cellAtracDecode cellAtracGetStreamDataInfo cellAtracAddStreamData
cellAtracGetRemainFrame cellAtracSetDataAndGetMemSize cellAtracGetSoundInfo cellAtracDeleteDecoder
cellFsOpen cellFsRead cellFsClose cellFsLseek cellFsStat cellFsFstat cellFsReadWithOffset
cellPadGetData cellPadGetInfo2 cellVideoOutGetState cellGcmSetFlipCommand cellSysutilCheckCallback
sys_event_queue_receive sys_semaphore_wait sys_semaphore_post sys_mutex_lock sys_mutex_unlock
sys_cond_wait sys_cond_signal sys_event_flag_wait sys_event_flag_set _sys_memset _sys_memcpy
_sys_strlen _sys_sprintf _sys_printf _sys_malloc _sys_free sys_timer_usleep sys_timer_sleep
cellSailSoundAdapterGetFrame cellSailDescriptorSetEs cellSailDescriptorOpen
cellSailSoundAdapterGetFormat cellSailSoundAdapterUpdateAvSync cellSailGraphicsAdapterSetPreferredFormat
cellAudioOutSetCopyControl sys_net_initialize_network_ex sceNpBasicRegisterContextSensitiveHandler
sceNpBasicGetCustomInvitationEntryCount""".split()


def nid_of(name):
    d = hashlib.sha1(name.encode() + _NID_SUFFIX).digest()[:4]
    return int.from_bytes(d, 'little')


NID_NAMES = {nid_of(n): n for n in _NID_CANDIDATES}
SYNC_NIDS = {nid_of(n): n for n in ('sys_lwmutex_lock', 'sys_lwmutex_trylock', 'sys_lwcond_wait',
                                     'cellSpursEventFlagWait', 'sys_event_queue_receive',
                                     'sys_semaphore_wait', 'sys_mutex_lock', 'sys_cond_wait',
                                     'sys_event_flag_wait', 'cellSyncLFQueuePush', 'cellSyncLFQueuePop')}

# ---------------------------------------------------------------- regex table
H = r'(?:0x)?[0-9A-Fa-f]+'
PATTERNS = [
    ('sfww_armed', re.compile(r'^\[sfww\] armed range (\d+) 0x([0-9A-F]+)\.\.0x([0-9A-F]+)')),
    ('sfww', re.compile(r'^\[sfww\] r(\d+) 0x([0-9A-F]+) ([0-9A-F]+)->([0-9A-F]+) w(\d) fn=0x([0-9A-F]+) '
                        r'lr=0x([0-9A-F]+) tid=(\d+) t=(\d+)(?: q=\d+)? ch:(.*)$')),
    ('sfww_cap', re.compile(r'^\[sfww\] --- cap')),
    ('vi', re.compile(r'^\[vi\] t=(\d+) (\w+)((?: \d+:[0-9A-F]+>[0-9A-F]+)*)')),
    ('vm_on', re.compile(r'^\[vm\] voice monitor on')),
    ('vm', re.compile(r'^\[vm\] t=(\d+) g=(\d+) n=(\d+) set:([\d ]*) clr:([\d ]*)$')),
    ('vm_cnt', re.compile(r'^\[vm-cnt\] t=(\d+) \+0x([0-9A-F]+) (\d+)->(\d+)')),
    ('vm_rec', re.compile(r'^\[vm-rec\] t=(\d+) g=(\d+) v=(\d+) head:([0-9A-F ]+) samp:(.*?) k800:([0-9A-F ]+)')),
    ('vm_sum', re.compile(r'^\[vm-sum\] t=(\d+) union=(\d+) groups:((?: g\d+=\d+)*) st7650_nonzero=(\d+)')),
    ('vm_g2', re.compile(r'^\[vm-g2-first\] t=(\d+) (.*)')),
    ('hle_new', re.compile(r'^\[hle-lr\] new nid=0x([0-9A-F]+) lr=0x([0-9A-F]+) tid=(\d+) r3=0x([0-9A-F]+) '
                           r'r4=0x([0-9A-F]+) r5=0x([0-9A-F]+) r6=0x([0-9A-F]+) ret=0x([0-9A-F]+) t=(\d+)')),
    ('hle_dump', re.compile(r'^\[hle-lrc\] dump=(\d+) t=(\d+) pairs=(\d+)')),
    ('hle_cnt', re.compile(r'^\[hle-lrc\] (\d+) 0x([0-9A-F]+) 0x([0-9A-F]+) (\d+) ret=0x([0-9A-F]+) tid=(\d+)')),
    ('ef_blocked', re.compile(r'\[cellSpurs\] EventFlagWait BLOCKED tid=(\d+) (\d+)s on pattern 0x([0-9A-F]+) '
                              r'\(mode=(\w+), bits=0x([0-9A-F]+)\) flagEA=0x([0-9A-F]+)')),
    ('ef_wake', re.compile(r'\[cellSpurs\] EventFlagWait WAKE tid=(\d+) flagEA=0x([0-9A-F]+) pattern=0x([0-9A-F]+) got=0x([0-9A-F]+)')),
    ('ef_set', re.compile(r'\[cellSpurs\] EventFlagSet#?(\d*) ?flagEA=0x([0-9A-F]+) bits=0x([0-9A-F]+)')),
    ('ef_stats', re.compile(r'\[ef-stats\] flag=0x([0-9A-F]+) waits=([\d.]+)/s mean=(\d+)us max=(\d+)us')),
    ('ef_init', re.compile(r'\[cellSpurs\] EventFlagInitialize\(clearMode=(\d+), direction=(\d+)\) flagEA=0x([0-9A-F]+)')),
    ('wait', re.compile(r'^\[WAIT\] (\w+)\(([^)]*)\)(?: tid=(\d+))?(?: cia=0x([0-9A-F]+))?(?: lr=0x([0-9A-F]+))?')),
    ('spu_unlifted', re.compile(r'\[spu\] img=(\d+) branched into unlifted LS 0x([0-9A-F]+) \(lr=0x([0-9A-F]+)\)')),
    ('spu_interp', re.compile(r'\[spu\] img=(\d+) interpreting unlifted LS 0x([0-9A-F]+)')),
    ('spu_lsdump', re.compile(r'^\s*LS\[0x([0-9A-F]+)\]:((?: [0-9A-F]{8})+)')),
    ('spu_lastpcs', re.compile(r'last dispatched PCs \(oldest first\):((?: 0x[0-9A-F]+)+)')),
    ('spu_halt', re.compile(r'\[SPU-HALT\] img=(\d+) pc=0x([0-9A-F]+)(.*)$')),
    ('spu_halt_ls', re.compile(r'\[SPU-HALT\]\s+ls\[0x([0-9A-F]+)\]:((?: [0-9A-F]{8})+)')),
    ('spu_trace_halt', re.compile(r'\[SPU-TRACE\] halt at LS 0x([0-9A-F]+)')),
    ('spu_returned', re.compile(r'\[spu_workload\] async image=(\d+) RETURNED rc=(-?\d+)')),
    ('spu_dispatch', re.compile(r'\[spu_workload\] dispatch HIT .* image=(\d+)')),
    ('wait_signal', re.compile(r'\[spu_workload\] (?:WAIT_SIGNAL#(\d+) enter task=(\d+) taskset=0x([0-9A-F]+)|task (\d+) \(taskset 0x([0-9A-F]+)\) sleeping)')),
    ('fs_open', re.compile(r"\[fs\] open '([^']+)' -> fd (-?\d+)")),
    ('atrac', re.compile(r'\[cellAtrac\] (.*)')),
    ('thread_create', re.compile(r'\[SYS\] sys_ppu_thread_create tid=(\d+) name="([^"]*)"')),
    ('watchea', re.compile(r'\[watchea\] n=\d+ spu(\d+) cmd=0x([0-9A-F]+) ea=0x([0-9A-F]+) size=(\d+)(?: lsa=0x([0-9A-F]+))?')),
    ('put_watch', re.compile(r'\[spu-put-watch\](.*)')),
    ('mfc_rej', re.compile(r'\[mfc\] REJECTED (.*)')),
    ('unresolved', re.compile(r'UNRESOLVED NID[^0-9A-Fx]*(0x[0-9A-Fa-f]+)?')),
    ('lfq', re.compile(r'\[sf-lfq2?\] (.*)')),
    ('gstack', re.compile(r'\[GSTACK:(\w+)[^\]]*\].*?tid=(\d+)')),
    ('pcsample', re.compile(r'\[pcsample\] slot=(\d+) img=(\d+) .*?pc=0x([0-9A-F]+)')),
    ('now_loading', re.compile(r'(?i)now ?loading')),
]
TID_ANY = re.compile(r'\btid=(\d+)')
T_ANY = re.compile(r'\bt=(\d{6,})')


def shape(line):
    s = re.sub(r'0x[0-9A-Fa-f]+', 'H', line[:60])
    return re.sub(r'\d+', 'N', s)


class Ev:
    __slots__ = ('kind', 't', 'tid', 'src', 'ln', 'raw', 'f')

    def __init__(self, kind, t, tid, src, ln, raw, f):
        self.kind, self.t, self.tid, self.src, self.ln, self.raw, self.f = kind, t, tid, src, ln, raw, f

    def ref(self):
        return f"{os.path.basename(self.src)}:{self.ln}"


class Analyzer:
    def __init__(self, cap=128, win=100, freer_tid=7, starter_tid=17, stubs=None):
        self.cap, self.win, self.freer, self.starter = cap, win, freer_tid, starter_tid
        self.ranges = {}            # range idx -> (lo, hi, name)
        self.ev = []                # selected events
        self.unknown = collections.Counter()
        self.kinds = collections.Counter()
        self.last_by_tid = {}       # tid -> Ev (any line with tid)
        self.last_wait_by_tid = {}  # tid -> Ev
        self.last_t = None
        self.hle_dump_t = {}
        self.hle_counts = collections.defaultdict(dict)  # dump -> (nid,lr,tid)->count
        self.hle_first = {}         # nid -> Ev
        self.stub_nids = {}
        for row in (stubs or []):
            try:
                self.stub_nids[int(row[1], 16)] = (row[0], row[2])
            except Exception:
                pass
        self.lines_total = 0
        self.pending_ls = None      # attach LS dump lines to the preceding unlifted/halt event

    # ------------------------------------------------------------ parsing
    def feed_file(self, path):
        with open(path, 'rb') as fh:
            for ln, b in enumerate(fh, 1):
                if b'\x00' in b:
                    b = b.replace(b'\x00', b'')
                line = b.decode('utf-8', 'replace').rstrip('\r\n')
                if line.startswith(('    ', '\t')) and 'LS[' not in line and 'last dispatched' not in line:
                    continue
                self.lines_total += 1
                self.feed(line, path, ln)

    def feed(self, line, src, ln):
        for name, rx in PATTERNS:
            m = rx.search(line)
            if m:
                self.kinds[name] += 1
                self.handle(name, m, line, src, ln)
                break
        else:
            if line.strip():
                self.unknown[shape(line)] += 1
                mt = T_ANY.search(line)
                if mt:
                    self.last_t = int(mt.group(1))
        mt = TID_ANY.search(line)
        if mt:
            tid = int(mt.group(1))
            self.last_by_tid[tid] = Ev('line', self.last_t, tid, src, ln, line, {})

    def add(self, kind, t, tid, src, ln, raw, **f):
        e = Ev(kind, t, tid, src, ln, raw, f)
        self.ev.append(e)
        return e

    def handle(self, name, m, line, src, ln):
        g = m.groups()
        if name == 'sfww_armed':
            lo, hi = int(g[1], 16), int(g[2], 16)
            self.ranges[int(g[0])] = (lo, hi, ARRAY_NAMES.get(lo, f'range{g[0]}'))
            return
        if name == 'sfww':
            r, addr, old, new = int(g[0]), int(g[1], 16), int(g[2], 16), int(g[3], 16)
            t, tid = int(g[8]), int(g[7])
            self.last_t = t
            lo, hi, arr = self.ranges.get(r, (None, None, f'range{r}'))
            idx = addr - lo if lo is not None else None
            self.add('ww', t, tid, src, ln, line, r=r, arr=arr, addr=addr, idx=idx, old=old, new=new,
                     w=int(g[4]), fn=int(g[5], 16), lr=int(g[6], 16), ch=g[9].strip())
            return
        if name == 'vi':
            t = int(g[0]); self.last_t = t
            ch = [(int(a), int(b, 16), int(c, 16)) for a, b, c in re.findall(r'(\d+):([0-9A-F]+)>([0-9A-F]+)', g[2])]
            self.add('vi', t, None, src, ln, line, arr=g[1], ch=ch)
            return
        if name == 'vm':
            t = int(g[0]); self.last_t = t
            self.add('vm', t, None, src, ln, line, g=int(g[1]), n=int(g[2]),
                     set=[int(x) for x in g[3].split()], clr=[int(x) for x in g[4].split()])
            return
        if name == 'vm_cnt':
            t = int(g[0]); self.last_t = t
            self.add('vmcnt', t, None, src, ln, line, off=int(g[1], 16), old=int(g[2]), new=int(g[3]))
            return
        if name == 'vm_rec':
            t = int(g[0]); self.last_t = t
            k = [int(x, 16) for x in g[5].split()]
            self.add('vmrec', t, None, src, ln, line, g=int(g[1]), v=int(g[2]), k800=k)
            return
        if name == 'vm_sum':
            t = int(g[0]); self.last_t = t
            groups = {int(a): int(b) for a, b in re.findall(r'g(\d+)=(\d+)', g[2])}
            self.add('sum', t, None, src, ln, line, union=int(g[1]), groups=groups, st=int(g[3]))
            return
        if name == 'hle_new':
            nid, t, tid = int(g[0], 16), int(g[8]), int(g[2])
            self.last_t = t
            e = self.add('hle', t, tid, src, ln, line, nid=nid, lr=int(g[1], 16), r3=int(g[3], 16), ret=int(g[7], 16))
            self.hle_first.setdefault(nid, e)
            if nid in SYNC_NIDS:
                self.last_wait_by_tid[tid] = e
            return
        if name == 'hle_dump':
            self.cur_dump = int(g[0]); self.hle_dump_t[self.cur_dump] = (int(g[1]), src, ln)
            self.last_t = int(g[1])
            return
        if name == 'hle_cnt':
            d = int(g[0])
            self.hle_counts[d][(int(g[1], 16), int(g[2], 16), int(g[5]))] = (int(g[3]), int(g[4], 16), src, ln)
            return
        t = self.last_t
        if name == 'ef_blocked':
            tid = int(g[0])
            e = self.add('ef_blocked', t, tid, src, ln, line, secs=int(g[1]), pattern=int(g[2], 16), bits=int(g[4], 16), flag=int(g[5], 16))
            self.last_wait_by_tid[tid] = e
        elif name == 'ef_wake':
            self.add('ef_wake', t, int(g[0]), src, ln, line, flag=int(g[1], 16))
        elif name == 'ef_set':
            self.add('ef_set', t, None, src, ln, line, flag=int(g[1], 16), bits=int(g[2], 16))
        elif name == 'ef_stats':
            self.add('ef_stats', t, None, src, ln, line, flag=int(g[0], 16), rate=float(g[1]), mean=int(g[2]), mx=int(g[3]))
        elif name == 'ef_init':
            self.add('ef_init', t, None, src, ln, line, clear=int(g[0]), dir=int(g[1]), flag=int(g[2], 16))
        elif name == 'wait':
            tid = int(g[2]) if g[2] else None
            e = self.add('wait', t, tid, src, ln, line, what=g[0], args=g[1])
            if tid is not None:
                self.last_wait_by_tid[tid] = e
        elif name == 'spu_unlifted':
            e = self.add('spu_unlifted', t, None, src, ln, line, img=g[0], ls=int(g[1], 16), lr=int(g[2], 16), lsdump={})
            self.pending_ls = e
        elif name == 'spu_lsdump' and self.pending_ls is not None:
            self.pending_ls.f.setdefault('lsdump', {})[int(g[0], 16)] = [int(x, 16) for x in g[1].split()]
        elif name == 'spu_lastpcs' and self.pending_ls is not None:
            self.pending_ls.f['lastpcs'] = g[0].split()
        elif name == 'spu_halt':
            regs = dict((k, v) for k, v in re.findall(r'(r\d+)=([0-9A-F]+)', g[2]))
            e = self.add('spu_halt', t, None, src, ln, line, img=g[0], pc=int(g[1], 16), regs=regs, lsdump={})
            self.pending_ls = e
        elif name == 'spu_halt_ls' and self.pending_ls is not None:
            self.pending_ls.f.setdefault('lsdump', {})[int(g[0], 16)] = [int(x, 16) for x in g[1].split()]
        elif name == 'spu_trace_halt':
            self.add('spu_trace_halt', t, None, src, ln, line, ls=int(g[0], 16))
        elif name == 'spu_returned':
            self.add('spu_returned', t, None, src, ln, line, img=g[0], rc=int(g[1]))
        elif name == 'fs_open':
            self.add('fs_open', t, None, src, ln, line, path=g[0], fd=int(g[1]))
        elif name == 'atrac':
            self.add('atrac', t, None, src, ln, line, msg=g[0])
        elif name == 'thread_create':
            self.add('thread_create', t, int(g[0]), src, ln, line, name=g[1])
        elif name == 'watchea':
            self.add('watchea', t, None, src, ln, line, cmd=int(g[1], 16), ea=int(g[2], 16), size=int(g[3]))
        elif name in ('mfc_rej', 'unresolved', 'put_watch', 'now_loading', 'gstack', 'pcsample', 'lfq', 'wait_signal', 'spu_dispatch', 'vm_g2', 'spu_interp'):
            self.add(name, t, None, src, ln, line)

    # ------------------------------------------------------------ analysis helpers
    def of(self, *kinds):
        ks = set(kinds)
        return [e for e in self.ev if e.kind in ks]

    def analyze(self):
        R = {'lines': self.lines_total, 'kinds': dict(self.kinds),
             'unknown_shapes_top': self.unknown.most_common(15), 'ranges': {k: [hex(v[0]), hex(v[1]), v[2]] for k, v in self.ranges.items()}}
        ww = self.of('ww')
        st = [e for e in ww if e.f['arr'] == 'st7650']
        starts = [e for e in st if e.f['old'] == 0 and e.f['new'] != 0]
        stops = [e for e in st if e.f['old'] == 2 and e.f['new'] == 1]
        frees = [e for e in st if e.f['old'] != 0 and e.f['new'] == 0]
        vt = [e for e in ww if e.f['arr'] == 'vtable']
        bit_set = [e for e in vt if e.f['w'] == 1 and (e.f['new'] & ~e.f['old'])]
        bit_clr = [e for e in vt if e.f['w'] == 1 and (e.f['old'] & ~e.f['new'])]
        sums = self.of('sum')

        def writers(evs):
            c = collections.Counter((f"fn=0x{e.f['fn']:X}", f"lr=0x{e.f['lr']:X}", f"tid={e.tid}") for e in evs)
            return [[*k, n] for k, n in c.most_common(10)]
        R['starts'] = {'n': len(starts), 'writers': writers(starts)}
        R['stops_2to1'] = {'n': len(stops), 'writers': writers(stops)}
        R['frees_to0'] = {'n': len(frees), 'writers': writers(frees)}
        R['group_bit_set'] = {'n': len(bit_set), 'writers': writers(bit_set)}
        R['group_bit_clear'] = {'n': len(bit_clr), 'writers': writers(bit_clr)}
        R['all_ww_writers'] = writers(ww)[:25]

        # ---- live curve / cap
        curve = [(e.t, e.f['union'], e.f['groups'], e.ref()) for e in sums]
        R['union_max'] = max((c[1] for c in curve), default=None)
        R['union_max_at'] = next(([c[0], c[3]] for c in curve if c[1] == R['union_max']), None)
        capev = next((c for c in curve if c[1] >= self.cap), None)
        R['cap'] = self.cap
        R['cap_first_hit'] = [capev[0], capev[3], capev[1]] if capev else None

        # ---- bursts: union rising >= 40 within 3 s
        bursts = []
        for i, c in enumerate(curve):
            j = i
            while j + 1 < len(curve) and curve[j + 1][0] - c[0] <= 3000:
                j += 1
            best = max(curve[i:j + 1], key=lambda x: x[1])
            if best[1] - c[1] >= 40 and (not bursts or c[0] > bursts[-1]['t_peak']):
                k = i
                while k + 1 <= j and curve[k + 1][1] >= curve[k][1]:
                    k += 1
                bursts.append({'t0': c[0], 'u0': c[1], 'ref0': c[3], 't_peak': curve[k][0], 'u_peak': curve[k][1],
                               'ref_peak': curve[k][3], 'dur_ms': curve[k][0] - c[0]})
        # hold time at/near peak
        for b in bursts:
            hold_end = b['t_peak']
            for c in curve:
                if c[0] > b['t_peak']:
                    if c[1] >= b['u_peak'] - 3:
                        hold_end = c[0]
                    else:
                        break
            b['hold_ms'] = hold_end - b['t_peak']
        R['bursts'] = bursts

        # ---- windows
        W = self.win
        tl = [e.t for e in ww] + [c[0] for c in curve]
        if tl:
            t0 = min(tl)
            wins = collections.OrderedDict()

            def w(t):
                k = (t - t0) // W
                if k not in wins:
                    wins[k] = {'t': t0 + k * W, 'starts': 0, 'stops': 0, 'frees': 0, 'bset': 0, 'bclr': 0, 'freer_ev': 0, 'union': None}
                return wins[k]
            for e in starts: w(e.t)['starts'] += 1
            for e in stops: w(e.t)['stops'] += 1
            for e in frees: w(e.t)['frees'] += 1
            for e in bit_set: w(e.t)['bset'] += 1
            for e in bit_clr: w(e.t)['bclr'] += 1
            for e in ww:
                if e.tid == self.freer: w(e.t)['freer_ev'] += 1
            for c in curve: w(c[0])['union'] = c[1]
            wl = [wins[k] for k in sorted(wins)]
            R['windows_total'] = len(wl)
            hot = [x for x in wl if x['starts'] - x['frees'] >= 3]
            R['windows_starts_outpace_frees'] = hot[:60]
        # ---- freer (tid 7) tick cadence: most common (fn,lr) of freer is its tick marker
        fe = [e for e in ww if e.tid == self.freer]
        tick = None
        if fe:
            (fn, lr), _ = collections.Counter((e.f['fn'], e.f['lr']) for e in fe if e.f['old'] == 0).most_common(1)[0]
            tick = [e for e in fe if e.f['fn'] == fn and e.f['lr'] == lr and e.f['old'] == 0]
            gaps = [(b.t - a.t, a, b) for a, b in zip(tick, tick[1:])]
            gl = sorted(g[0] for g in gaps)
            med = gl[len(gl) // 2] if gl else None
            big = sorted(gaps, key=lambda g: -g[0])[:8]
            R['freer'] = {'tid': self.freer, 'tick_marker': f'fn=0x{fn:X} lr=0x{lr:X}', 'ticks': len(tick), 'median_gap_ms': med,
                          'largest_gaps': [[g[0], g[1].ref(), g[2].ref()] for g in big],
                          'last_event': [fe[-1].t, fe[-1].ref(), fe[-1].raw[:160]]}
            # tick cadence inside bursts vs outside
            for b in bursts:
                inside = [g for g in gaps if b['t0'] <= g[1].t <= b['t_peak'] + b['hold_ms']]
                b['freer_ticks'] = len(inside)
                b['freer_max_gap_ms'] = max((g[0] for g in inside), default=None)
                b['starts'] = sum(1 for e in starts if b['t0'] <= e.t <= b['t_peak'])
                b['frees'] = sum(1 for e in frees if b['t0'] <= e.t <= b['t_peak'])
                b['distinct_voices_started'] = len({e.f['idx'] for e in starts if b['t0'] <= e.t <= b['t_peak']})
        # ---- mass operations: >= 50 writes by one (tid, fn, lr) inside 300 ms, excluding the steady tick
        mass = []
        byk = collections.defaultdict(list)
        for e in vt:
            byk[(e.tid, e.f['fn'], e.f['lr'])].append(e)
        for k, L in byk.items():
            i = 0
            for j in range(len(L)):
                while L[j].t - L[i].t > 300:
                    i += 1
                if j - i + 1 >= 50:
                    mass.append({'tid': k[0], 'fn': f'0x{k[1]:X}', 'lr': f'0x{k[2]:X}', 't0': L[i].t, 't1': L[j].t,
                                 'n_in_300ms': j - i + 1, 'ref0': L[i].ref(), 'ref1': L[j].ref()})
                    break
        R['mass_ops'] = sorted(mass, key=lambda x: x['t0'])
        # ---- count jumps with no PPU writer nearby
        jumps = []
        vtw = [e for e in vt if e.f['w'] == 4]
        for e in self.of('vmcnt'):
            d = e.f['new'] - e.f['old']
            if abs(d) >= 8:
                ea = 0x111A1780 + e.f['off']
                near = [x for x in vtw if x.f['addr'] == ea and abs(x.t - e.t) <= 5]
                jumps.append({'t': e.t, 'ref': e.ref(), 'off': hex(e.f['off']), 'old': e.f['old'], 'new': e.f['new'],
                              'ppu_writes_within_5ms': len(near)})
        R['count_jumps'] = jumps[:40]
        # ---- voice record index word (+0x848 = k800 word 18) at allocation time
        recs = self.of('vmrec')
        idxw = collections.Counter()
        for e in recs:
            k = e.f['k800']
            if len(k) > 18:
                idxw[k[18]] += 1
        R['rec_0x848_at_alloc_top'] = [[hex(a), n] for a, n in idxw.most_common(8)]
        R['max_voice_id'] = max((e.f['v'] for e in recs), default=None)
        # ---- SPU / halt / flag
        un = self.of('spu_unlifted')
        halts = self.of('spu_halt')
        trace = self.of('spu_trace_halt')
        rets = [e for e in self.of('spu_returned') if e.f['img'] == MIXER_IMG]
        efb = [e for e in self.of('ef_blocked') if e.f['flag'] == MIXER_FLAG]
        trap = [e for e in un if e.f['img'] == MIXER_IMG]
        R['mixer_unlifted'] = [{'ref': e.ref(), 't': e.t, 'ls': hex(e.f['ls']), 'lr': hex(e.f['lr']),
                                'lsdump': {hex(k): ' '.join(f'{x:08X}' for x in v) for k, v in e.f.get('lsdump', {}).items()},
                                'lastpcs': e.f.get('lastpcs')} for e in trap][:12]
        R['spu_halts'] = [{'ref': e.ref(), 'img': e.f['img'], 'pc': hex(e.f['pc']), 'regs': e.f['regs'],
                           'ls_all_zero': all(x == 0 for v in e.f.get('lsdump', {}).values() for x in v) if e.f.get('lsdump') else None}
                          for e in halts][:6]
        R['spu_trace_halts'] = [e.ref() for e in trace][:6]
        R['mixer_returned'] = [e.ref() for e in rets][:12]
        R['ef_blocked_mixer_flag'] = {'n': len(efb), 'first': efb[0].ref() if efb else None,
                                      'max_secs': max((e.f['secs'] for e in efb), default=None), 'tids': sorted({e.tid for e in efb})}
        R['ef_init'] = [[hex(e.f['flag']), e.f['clear'], e.f['dir'], e.ref()] for e in self.of('ef_init')][:20]
        # ---- loading markers
        fs = self.of('fs_open')
        load = [e for e in fs if '/dev_hdd1/cache/' in e.f['path'] or 'Voice.bin' in e.f['path'] or 'Sound' in e.f['path']]
        R['loading_markers'] = [[e.t, e.ref(), e.f['path']] for e in load][:40] + \
            [[e.t, e.ref(), 'thread ' + e.f['name']] for e in self.of('thread_create') if 'Str' in e.f['name']][:10] + \
            [[e.t, e.ref(), 'now-loading text'] for e in self.of('now_loading')][:10]
        R['atrac_errors'] = collections.Counter(re.sub(r'\d+', 'N', e.f['msg'])[:90] for e in self.of('atrac')).most_common(8)
        # ---- stubs near bursts
        near = []
        if self.stub_nids:
            for nid, (kind, nm) in self.stub_nids.items():
                e = self.hle_first.get(nid)
                if e:
                    near.append({'nid': f'0x{nid:08X}', 'name': nm, 'kind': kind, 'first_call_t': e.t, 'ref': e.ref(),
                                 'ms_from_nearest_burst': min((abs(e.t - b['t0']) for b in bursts), default=None)})
        # per-dump deltas around bursts
        dumps = sorted(self.hle_counts)
        deltas = []
        for a, b in zip(dumps, dumps[1:]):
            if a not in self.hle_dump_t or b not in self.hle_dump_t:
                continue                      # partial dump in a log tail: no header, no time
            ta, tb = self.hle_dump_t[a][0], self.hle_dump_t[b][0]
            hit = [x for x in bursts if ta <= x['t0'] <= tb or ta <= x['t_peak'] <= tb]
            if not hit:
                continue
            ca, cb = self.hle_counts[a], self.hle_counts[b]
            for k, v in cb.items():
                d = v[0] - ca.get(k, (0,))[0]
                if d and (k[0] in self.stub_nids or k[0] in SYNC_NIDS or k[2] in (self.freer, self.starter)):
                    deltas.append({'dumps': f'{a}->{b}', 'nid': f'0x{k[0]:08X}', 'name': NID_NAMES.get(k[0], self.stub_nids.get(k[0], ('', '?'))[1]),
                                   'lr': f'0x{k[1]:X}', 'tid': k[2], 'delta': d, 'ret': f'0x{v[1]:X}', 'ref': f'{os.path.basename(v[2])}:{v[3]}'})
        R['stubs_called'] = near
        R['hle_deltas_in_burst_dump_window'] = sorted(deltas, key=lambda x: -x['delta'])[:30]
        # ---- per-thread timeline
        per = collections.defaultdict(lambda: {'n': 0, 't0': None, 't1': None, 'fnlr': collections.Counter()})
        for e in ww + self.of('hle'):
            p = per[e.tid]
            p['n'] += 1
            p['t0'] = e.t if p['t0'] is None else min(p['t0'], e.t)
            p['t1'] = e.t if p['t1'] is None else max(p['t1'], e.t)
            key = f"fn=0x{e.f['fn']:X}/lr=0x{e.f['lr']:X}" if e.kind == 'ww' else f"hle {NID_NAMES.get(e.f['nid'], hex(e.f['nid']))}@0x{e.f['lr']:X}"
            p['fnlr'][key] += 1
        R['threads'] = {str(t): {'events': p['n'], 't_first': p['t0'], 't_last': p['t1'], 'top': p['fnlr'].most_common(5),
                                 'last_line': self.last_by_tid[t].ref() + ' ' + self.last_by_tid[t].raw[:140] if t in self.last_by_tid else None,
                                 'last_wait': (self.last_wait_by_tid[t].ref() + ' ' + self.last_wait_by_tid[t].raw[:160]) if t in self.last_wait_by_tid else None}
                        for t, p in sorted(per.items(), key=lambda kv: (kv[0] is None, kv[0] or 0))}
        R['waits_last_per_tid'] = {str(t): e.ref() + ' ' + e.raw[:180] for t, e in self.last_wait_by_tid.items()}
        # ---- freeze point
        tend = max((e.t for e in self.ev if e.t), default=None)
        R['t_end'] = tend
        self.R = R
        R['candidates'] = self.rank(R, starts, frees, bursts, trap, halts, efb, rets)
        return R

    # ------------------------------------------------------------ ranking (heuristic order, not probabilities)
    def rank(self, R, starts, frees, bursts, trap, halts, efb, rets):
        C = []

        def cand(cid, title, pts, ev, missing):
            C.append({'id': cid, 'title': title, 'points': pts, 'evidence': ev, 'missing_to_confirm': missing})
        # C1 mixer trap / divisor zero
        ev, p = [], 0
        for t in trap[:2]:
            ev.append(f"{t.ref()} mixer img {MIXER_IMG} enters LS 0x{t.f['ls']:X} (lr 0x{t.f['lr']:X})"); p += 3
            d = t.f.get('lsdump', {}).get(MIXER_TRAP_PC)
            if d and d[0] == 0x7F003200:
                ev.append(f"{t.ref()} LS[0x31C20]=7F003200 = heqi r100,0 (decoded by spu_mini_decode.py)"); p += 2
        for h in halts[:1]:
            ev.append(f"{h.ref()} SPU-HALT regs {h.f['regs']}"); p += 3
        for r in rets[-1:]:
            ev.append(f"{r.ref()} mixer job RETURNED (job ended; nobody sets 0x{MIXER_FLAG:08X} afterwards)"); p += 1
        if efb:
            ev.append(f"{efb[0].ref()} EventFlagWait BLOCKED on 0x{MIXER_FLAG:08X} x{len(efb)} (max {max(e.f['secs'] for e in efb)} s)"); p += 2
        if p:
            cand('C1', 'Mixer SPU job hits its divide-by-zero trap (heqi r100,0 at LS 0x31C20) because its 288-byte table '
                 '(EA r93+0x13CE0) is zero; the job ends, event flag 0xDBA900 is never set again, tid 7 waits forever',
                 p, ev, 'r100/r89/r93 + LS at r89 at the trap; the writer that zeroed EA 0x11387860 in THIS run (PUT watch)')
        # C2 ring index overflow (needs putinputs/watchea lines)
        we = [e for e in self.of('watchea') if e.f['size'] == 4096 and 0x11357580 <= e.f['ea'] < 0x11400000]
        ev = [f"{e.ref()} 4KB mixer PUT at EA 0x{e.f['ea']:X} (past ring end 0x11357580)" for e in we[:3]]
        p = 4 * min(len(we), 1)
        if bursts:
            b = max(bursts, key=lambda x: x['u_peak'])
            ev.append(f"{b['ref_peak']} union {b['u_peak']} voices (cap {self.cap}); pages/pass = 7 + 2 x visits, ring = 360 pages, "
                      f"table page 408 needs >= 201 visits in one pass")
            p += 1
        cand('C2', 'Mixer ring write index runs past the 360-page ring in one pass (visits > 176) and its 4KB PUT lands on '
             'page 408 = EA 0x11387580, zeroing the table (seen in run B 2026-11-26); needs a pass that visits ~2x the live voices',
             p, ev, 'SPU_PUTINPUTS / PS3RECOMP_SPU_PUT_WATCH=11387860 in the same run as the voice monitor')
        # C3 mass stop/restore near the trap
        ev, p = [], 0
        tt = trap[0].t if trap else None
        for m in R['mass_ops']:
            if m['tid'] == self.starter and (tt is None or (m['t0'] and abs(m['t0'] - tt) <= 3000)):
                ev.append(f"{m['ref0']}..{m['ref1']} tid {m['tid']} fn {m['fn']} lr {m['lr']} x{m['n_in_300ms']} in 300 ms"); p += 1
        for j in R['count_jumps'][:4]:
            if j['ppu_writes_within_5ms'] == 0:
                ev.append(f"{j['ref']} count +{j['off']} {j['old']}->{j['new']} with no PPU store watched within 5 ms"); p += 1
        if ev:
            cand('C3', 'Scene-change stop-all / restore by tid 17 (lr 0x59590 / 0x59724) at Now Loading overlaps a mixer pass: '
                 'torn view between the live voice masks (param+0x358, read per pass) and the per-tick snapshot 0x111A2000/2800, so the mixer '
                 'allocates a voice once per mismatched group (path 1, no de-dup) and the pass walks the voices 2-3 times', p, ev,
                 'SF_RACE run (race_run_spec.md): race_check.py checks M (mask vs snapshot), V (visits per pass), L (lost update), E (flag order)')
        # C4 voice leak / freer stall
        ev, p = [], 0
        for b in bursts:
            ev.append(f"{b['ref0']}->{b['ref_peak']} union {b['u0']}->{b['u_peak']} in {b['dur_ms']} ms, held {b['hold_ms']} ms; "
                      f"starts {b.get('starts')} frees {b.get('frees')} freer ticks {b.get('freer_ticks')} max gap {b.get('freer_max_gap_ms')} ms")
            if b['hold_ms'] > 5000: p += 1
        fr = R.get('freer', {})
        if fr.get('largest_gaps') and fr.get('median_gap_ms') and fr['largest_gaps'][0][0] > 20 * fr['median_gap_ms']:
            ev.append(f"freer tid {self.freer} tick gap {fr['largest_gaps'][0][0]} ms at {fr['largest_gaps'][0][1]} (median {fr['median_gap_ms']} ms)"); p += 1
        cand('C4', 'Voices are started faster than tid 7 frees them (or tid 7 stalls), so the live set stays near the pool size', p, ev,
             'RPCS3 popcount of 0x111A1780 bitmap at the same game moment (is 130 live voices normal?)')
        # C5 stub/missing HLE near the burst
        ev = [f"{s['ref']} {s['kind']} {s['name']} first call {s['ms_from_nearest_burst']} ms from a burst" for s in R['stubs_called']
              if s['ms_from_nearest_burst'] is not None and s['ms_from_nearest_burst'] < 5000]
        cand('C5', 'A stubbed/missing HLE import (cellSail*) returns 0 near the burst and changes the game\'s sound requests',
             len(ev), ev, 'call order of cellSail* vs first start in the burst; RPCS3 return values')
        C.sort(key=lambda c: -c['points'])
        return C


# ---------------------------------------------------------------- report
def write_report(R, out, inputs):
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, 'report.json'), 'w') as fh:
        json.dump(R, fh, indent=1, default=str)
    L = [f"# voice_freeze_analyzer report", f"Inputs: {', '.join(inputs)}", f"Lines parsed: {R['lines']}", ""]
    L += ["## Ranked root-cause candidates (points = heuristic evidence count, not a probability)"]
    for c in R['candidates']:
        L.append(f"### {c['id']} ({c['points']} pts) {c['title']}")
        L += [f"- {x}" for x in c['evidence']] or ['- (no evidence lines in these logs)']
        L.append(f"- to confirm: {c['missing_to_confirm']}")
    L += ["", "## Voice starts / stops / frees (st7650 writes)",
          f"- starts 0->2: {R['starts']['n']} {R['starts']['writers']}", f"- stops 2->1: {R['stops_2to1']['n']} {R['stops_2to1']['writers']}",
          f"- frees ->0: {R['frees_to0']['n']} {R['frees_to0']['writers']}",
          f"- group bit set: {R['group_bit_set']['n']} {R['group_bit_set']['writers'][:4]}",
          f"- group bit clear: {R['group_bit_clear']['n']} {R['group_bit_clear']['writers'][:4]}",
          f"- max voice id seen in [vm-rec]: {R['max_voice_id']}; rec+0x848 at alloc: {R['rec_0x848_at_alloc_top']}",
          "", "## Live-voice curve", f"- max union {R['union_max']} at {R['union_max_at']}; first >= cap {R['cap']}: {R['cap_first_hit']}"]
    for b in R['bursts']:
        L.append(f"- burst {b['ref0']} -> {b['ref_peak']}: {b['u0']}->{b['u_peak']} in {b['dur_ms']} ms, held {b['hold_ms']} ms, "
                 f"starts {b.get('starts')}, frees {b.get('frees')}, distinct voices {b.get('distinct_voices_started')}, "
                 f"freer ticks {b.get('freer_ticks')}, freer max gap {b.get('freer_max_gap_ms')} ms")
    L += ["", f"## Windows ({len(R.get('windows_starts_outpace_frees', []))} of {R.get('windows_total')} windows with starts - frees >= 3)"]
    L += ["| t | starts | stops | frees | bit set | bit clr | freer ev | union |", "|---|---|---|---|---|---|---|---|"]
    for w in R.get('windows_starts_outpace_frees', [])[:40]:
        L.append(f"| {w['t']} | {w['starts']} | {w['stops']} | {w['frees']} | {w['bset']} | {w['bclr']} | {w['freer_ev']} | {w['union']} |")
    L += ["", "## Freer thread", f"- {R.get('freer')}", "", "## Mass operations (>=50 table writes by one fn/lr in 300 ms)"]
    L += [f"- {m}" for m in R['mass_ops']] or ['- none']
    L += ["", "## Count jumps (|delta|>=8)"] + ([f"- {j}" for j in R['count_jumps'][:20]] or ['- none'])
    L += ["", "## Mixer SPU / flag"] + [f"- unlifted entry: {x}" for x in R['mixer_unlifted']] + [f"- halt: {x}" for x in R['spu_halts']]
    L += [f"- SPU-TRACE halts: {R['spu_trace_halts']}", f"- mixer RETURNED: {R['mixer_returned']}", f"- EF 0xDBA900 blocked: {R['ef_blocked_mixer_flag']}",
          f"- EF init: {R['ef_init']}"]
    L += ["", "## Loading markers"] + ([f"- {x}" for x in R['loading_markers']] or ['- none in these logs (diag extract has no [fs] lines)'])
    L += ["", "## Stub/missing imports called"] + ([f"- {x}" for x in R['stubs_called']] or ['- none'])
    L += ["", "## HLE count deltas in the dump interval that contains a burst (sync/stub/tid7/tid17)"] + \
        ([f"- {x}" for x in R['hle_deltas_in_burst_dump_window']] or ['- none'])
    L += ["", "## Per-thread timeline"]
    for t, p in R['threads'].items():
        L.append(f"- tid {t}: {p['events']} ev, t {p['t_first']}..{p['t_last']}, top {p['top'][:3]}")
        if p['last_wait']:
            L.append(f"  - last wait-like: {p['last_wait']}")
    L += ["", "## Last wait line per tid"] + [f"- tid {t}: {v}" for t, v in R['waits_last_per_tid'].items()]
    L += ["", "## Unknown line shapes (extend PATTERNS)"] + [f"- {n} x `{s}`" for s, n in R['unknown_shapes_top']]
    with open(os.path.join(out, 'report.md'), 'w') as fh:
        fh.write('\n'.join(L) + '\n')
    return os.path.join(out, 'report.md')


def run(paths, stubs_path, out, cap, win, freer, starter):
    stubs = json.load(open(stubs_path)) if stubs_path and os.path.exists(stubs_path) else []
    A = Analyzer(cap=cap, win=win, freer_tid=freer, starter_tid=starter, stubs=stubs)
    for p in paths:
        A.feed_file(p)
    R = A.analyze()
    return R, write_report(R, out, paths)


SYNTH = """[sfww] armed range 0 0x1119E080..0x1119E134
[sfww] armed range 4 0x111A1780..0x111A2000
[vm-sum] t=1000 union=2 groups: g1=2 g3=2 st7650_nonzero=2
[spu] img=391227015 branched into unlifted LS 0x31C20 (lr=0x31A84) -- ending the job
      last dispatched PCs (oldest first): 0x0CD08 0x07600
      LS[0x31C20]: 7F003200 1200089A 0C003289 0C00320A 4CFFF28B 4CFFF20C 8139448B 8159050C
[SPU-HALT] img=391227015 pc=0x31C20 r7=0001F760 r89=0001F760 r92=00000200 r93=11373B80 1415E806 r100=00000000
[SPU-HALT]  ls[0x1F760]: 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000
[spu_workload] async image=391227015 RETURNED rc=0 (job ran to completion, did not loop)
[cellSpurs] EventFlagWait BLOCKED tid=35024 1s on pattern 0x0001 (mode=AND, bits=0x0000) flagEA=0x00DBA900 -- waiting
[cellSpurs] EventFlagWait BLOCKED tid=35024 2s on pattern 0x0001 (mode=AND, bits=0x0000) flagEA=0x00DBA900 -- waiting
[WAIT] event_queue_receive(q=1 timeout=9000000) tid=10 cia=0x0080FC68 lr=0x0004D510
[fs] open '/dev_hdd1/cache/BLUS30471/5444' -> fd 6
some totally new line format 0x1234 t=1234567
"""


def selftest():
    import tempfile
    ok = True

    def check(c, msg):
        nonlocal ok
        print(('PASS ' if c else 'FAIL ') + msg)
        ok = ok and c
    # NID scheme sanity (public value: sys_initialize_tls = 0x744680A2, seen in the diag log)
    check(nid_of('sys_initialize_tls') == 0x744680A2, 'NID hash scheme')
    sys.path.insert(0, HERE)
    import spu_mini_decode as D
    check(D.decode(0x7F003200).startswith('heqi r100, 0'), 'decode 7F003200 = heqi r100,0')
    check(D.decode(0x0C00320A) == 'sfi r10, r100, 0', 'decode 0C00320A = sfi r10,r100,0')
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, 'synth.log'); open(p, 'w').write(SYNTH)
        R, _ = run([p], None, os.path.join(td, 'o'), 128, 100, 7, 17)
        check(R['spu_halts'] and R['spu_halts'][0]['regs'].get('r100') == '00000000', 'synthetic: SPU-HALT r100 parsed')
        check(R['spu_halts'][0]['ls_all_zero'] is True, 'synthetic: halt LS all zero')
        check(R['mixer_unlifted'][0]['lsdump'].get('0x31c20', '').startswith('7F003200'), 'synthetic: LS dump attached')
        check(R['ef_blocked_mixer_flag']['n'] == 2, 'synthetic: EF blocked x2')
        check(R['candidates'][0]['id'] == 'C1', 'synthetic: C1 ranked first')
        check(R['loading_markers'] and '5444' in R['loading_markers'][0][2], 'synthetic: loading marker')
        check(sum(R['kinds'].values()) >= 10 and R['unknown_shapes_top'], 'synthetic: unknown line counted, not fatal')
    real = os.path.join(DEFAULT_DATA, 'voicediag1786_diag_lines.txt')
    stubs = os.path.join(DEFAULT_DATA, 'voicediag1786_stub_missing_called.json')
    if os.path.exists(real):
        with tempfile.TemporaryDirectory() as td:
            R, _ = run([real], stubs, td, 128, 100, 7, 17)
        check(R['starts']['n'] == 1311, f"voicediag1786: 1311 voice starts (got {R['starts']['n']})")
        top = R['starts']['writers'][0]
        check(top[:3] == ['fn=0x5A750', 'lr=0x5A91C', 'tid=17'], f'voicediag1786: top start writer {top}')
        check(R['union_max'] == 127, f"voicediag1786: max union 127 (got {R['union_max']})")
        b = max(R['bursts'], key=lambda x: x['u_peak']) if R['bursts'] else None
        check(b is not None and 87030000 <= b['t0'] <= 87036000 and b['u_peak'] == 127, f'voicediag1786: burst near t=87033363 ({b and b["t0"]})')
        check(not R['mixer_unlifted'] and not R['ef_blocked_mixer_flag']['n'], 'voicediag1786: no mixer trap/EF block (no freeze in that run)')
        check(any(w[:3] == ['fn=0x58974', 'lr=0x58A54', 'tid=7'] for w in R['group_bit_clear']['writers']), 'voicediag1786: frees by tid 7 fn 0x58974')
    else:
        print('SKIP voicediag1786 data not found at', real)
    print('SELFTEST', 'OK' if ok else 'FAILED')
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('logs', nargs='*')
    ap.add_argument('--stubs', default=os.path.join(DEFAULT_DATA, 'voicediag1786_stub_missing_called.json'))
    ap.add_argument('--out', default='vf_out')
    ap.add_argument('--cap', type=int, default=128)
    ap.add_argument('--win', type=int, default=100)
    ap.add_argument('--freer-tid', type=int, default=7)
    ap.add_argument('--starter-tid', type=int, default=17)
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    if not a.logs:
        ap.error('give at least one log')
    R, rep = run(a.logs, a.stubs, a.out, a.cap, a.win, a.freer_tid, a.starter_tid)
    print('report:', rep)
    for c in R['candidates']:
        print(f"{c['id']} {c['points']}pts {c['title'][:110]}")


if __name__ == '__main__':
    main()
