#!/usr/bin/env python3
"""sf_lifecycle.py - SPURS taskset/task lifecycle timeline + stage-transition leak checker (box-only, stdlib only).

Reads a Strikeforce ps3recomp stderr log (read-only) and writes:
  <out>/lifecycle_summary.txt   text summary (stages, alive-at-stage-change, address reuse, per-taskset timeline)
  <out>/lifecycle.html          self-contained timeline (inline SVG, no external libraries)
  <out>/lifecycle.json          everything above as data
Usage:
  python3 sf_lifecycle.py LOG [--out DIR] [--strip-prefix] [--rare-max 16] [--gap-lines 2000] [--stage-at L ...]
  python3 sf_lifecycle.py --selftest
Line numbers are the log's own (1-based). Nothing here changes or talks to the game.

EXTENDING: every input format is one row of RULES below: (name, prefix, regex with named groups, kind).
A new log format drops in as a new row as long as its named groups use the standard field names:
  image args taskset task q ea owner buf size depth dir w0 w1 w2 w3 pc lr name tid path n
and its kind is one of KINDS (see handle()). The proposed log-only build format
  [sf-lc] <event> key=value key=value ...
is parsed generically (any keys) - see README.md for the event names it understands.
"""
import argparse, html, json, os, re, sys
from collections import defaultdict, OrderedDict

HEX = r'0x[0-9A-Fa-f]+'
RULES = [
    # name                prefix              regex                                                                                   kind
    ('dispatch',      '[spu_workload] dispatch', rf'^\[spu_workload\] dispatch HIT \(async\) fp={HEX} args=(?P<args>{HEX}) image=(?P<image>\d+)', 'dispatch'),
    ('built',         '[taskset] built',     rf'^\[taskset\] built SpursTasksetContext image=(?P<image>\d+) taskset=(?P<taskset>{HEX}) task=(?P<task>\d+)', 'bind'),
    ('returned',      '[spu_workload] async', r'^\[spu_workload\] async image=(?P<image>\d+) RETURNED', 'return'),
    ('wait_signal',   '[spu_workload] WAIT_SIGNAL', rf'^\[spu_workload\] WAIT_SIGNAL#(?P<n>\d+) enter task=(?P<task>\d+) taskset=(?P<taskset>{HEX})', 'task_activity'),
    ('sleeping',      '[spu_workload] task',  rf'^\[spu_workload\] task (?P<task>\d+) \(taskset (?P<taskset>{HEX})\) sleeping (?P<n>\d+)s', 'task_activity'),
    ('signal_task',   '[spu_workload] signal', rf'^\[spu_workload\] signal task (?P<task>\d+) \(taskset (?P<taskset>{HEX})\)', 'task_signal'),
    ('spu_spin',      '[spu-spin]',          rf'^\[spu-spin\] img=(?P<image>\d+) pc=(?P<pc>{HEX}) lr=(?P<lr>{HEX}) GETLLAR ea=(?P<ea>{HEX}) \S+; line: (?P<w0>[0-9A-Fa-f]{{8}}) (?P<w1>[0-9A-Fa-f]{{8}}) (?P<w2>[0-9A-Fa-f]{{8}}) (?P<w3>[0-9A-Fa-f]{{8}})', 'spin'),
    ('lfq_init',      '[sf-lfq] init',       rf'^\[sf-lfq\] init owner=(?P<owner>{HEX}) q=(?P<q>{HEX}) buf=(?P<buf>{HEX}) size=(?P<size>\d+) depth=(?P<depth>\d+) dir=(?P<dir>\d+)', 'queue_init'),
    ('lfq_woke',      '[sf-lfq] push',       rf'^\[sf-lfq\] push q=(?P<q>{HEX}) woke SPU consumer task (?P<task>\d+) \(taskset (?P<taskset>{HEX})\)', 'queue_push'),
    ('lfq_size',      '[sf-lfq] size',       rf'^\[sf-lfq\] size q=(?P<q>{HEX})', 'queue_touch'),
    ('lfq2_push',     '[sf-lfq2] push',      rf'^\[sf-lfq2\] push q=(?P<q>{HEX}) .*?h1=(?P<h1>\d+) h4=(?P<h4>\d+) h5=(?P<h5>\d+) h8=(?P<h8>\d+)', 'queue_push'),
    ('lfq_pop',       '[sf-lfq] pop',        rf'^\[sf-lfq\] pop q=(?P<q>{HEX})(?: .*?task=(?P<task>\d+))?(?: .*?taskset=(?P<taskset>{HEX}))?', 'queue_pop'),   # proposed
    ('fs_open',       '[fs] open',           r"^\[fs\] open '(?P<path>[^']+)'", 'fs_open'),
    ('thread',        '[SYS] sys_ppu_thread_create', r'^\[SYS\] sys_ppu_thread_create tid=(?P<tid>\d+) name="(?P<name>[^"]*)"', 'ppu_thread'),
    ('movie',         '[sf-movie] OpenStream', r'^\[sf-movie\] OpenStream (?P<path>\S+)', 'load_hint'),
    ('now_loading',   '',                    r'(?i)now ?loading', 'load_hint'),
    ('atrac_setdata', '[cellAtrac] SetData handle', rf'^\[cellAtrac\] SetData handle=(?P<owner>{HEX}) ch=(?P<n>\d+)', 'load_hint'),
    ('sf_lc',         '[sf-lc]',             r'^\[sf-lc\] (?P<ev>\w+)(?P<kv>.*)$', 'sf_lc'),                                   # proposed generic
]
RULES = [(n, p, re.compile(r), k) for n, p, r, k in RULES]
# [sf-lc] events (proposed log-only build) -> kind
SF_LC = {'taskset_create': 'taskset_create', 'taskset_shutdown': 'taskset_end', 'taskset_join': 'taskset_end',
         'taskset_destroy': 'taskset_end', 'task_create': 'task_create', 'task_exit': 'return', 'task_start': 'task_activity',
         'host_thread_start': 'task_activity', 'host_thread_stop': 'return', 'lfq_init': 'queue_init', 'lfq_push': 'queue_push',
         'lfq_pop': 'queue_pop', 'stage': 'stage_mark'}
LOADER_NAMES = re.compile(r'Loader|Load|Str', re.I)
TASKSET_SPAN = 0x4000      # an address within this many bytes above a taskset EA belongs to it (queues sit at +0x1900..+0x1A00)


def hx(s):
    return int(s, 16) if isinstance(s, str) else s


def fmt(a):
    return '0x%08X' % a if a is not None else '-'


class Inst:
    """One dispatched run of an SPU task image."""
    __slots__ = ('id', 'image', 'args', 'line', 'taskset', 'task', 'ret', 'ret_how', 'stage', 'events', 'spins', 'queues', 'k')

    def __init__(self, iid, image, args, line, k):
        self.id, self.image, self.args, self.line, self.k = iid, image, args, line, k
        self.taskset = self.task = self.ret = self.ret_how = self.stage = None
        self.events, self.spins, self.queues = [], [], set()

    def label(self):
        return f'{self.image}#{self.k}@{fmt(self.taskset)}/t{self.task}'


class Model:
    def __init__(self):
        self.insts = []
        self.by_image = defaultdict(list)
        self.unbound = defaultdict(list)       # image -> instances waiting for their [taskset] built line
        self.queues = OrderedDict()            # q -> {'inits': [...], 'owner', 'pushes', 'touch', 'pops'}
        self.taskset_act = defaultdict(list)   # taskset -> [(line, kind, task)]
        self.taskset_marks = defaultdict(list)  # explicit create/end lines (sf-lc)
        self.fs = []; self.threads = []; self.hints = []; self.stage_marks = []
        self.sleeps = []           # (line, taskset, task, secs): one line per waiting host thread per second
        self.spins = []; self.unmatched = defaultdict(int); self.nlines = 0

    # ---------------------------------------------------------------- parsing
    def feed(self, ln, line):
        self.nlines = max(self.nlines, ln)
        for name, pre, rx, kind in RULES:
            if pre and not line.startswith(pre):
                continue
            m = rx.search(line)
            if not m:
                continue
            d = {k: v for k, v in m.groupdict().items() if v is not None}
            if kind == 'sf_lc':
                ev = d['ev']; kind = SF_LC.get(ev)
                d = dict(re.findall(r'(\w+)=(\S+)', d.get('kv', '')), ev=ev)
                if 'ts' in d and 'taskset' not in d: d['taskset'] = d['ts']
                if 'img' in d and 'image' not in d: d['image'] = d['img']
                if not kind:
                    self.unmatched['sf-lc ' + ev] += 1; return
            self.handle(kind, name, ln, line, d)
            return

    def handle(self, kind, name, ln, line, d):
        img = d.get('image'); ts = hx(d['taskset']) if 'taskset' in d else None
        task = int(d['task']) if 'task' in d else None
        if kind == 'dispatch':
            i = Inst(len(self.insts), img, hx(d['args']), ln, len(self.by_image[img]) + 1)
            self.insts.append(i); self.by_image[img].append(i); self.unbound[img].append(i)
        elif kind == 'bind':
            if self.unbound[img]:
                i = self.unbound[img].pop(0); i.taskset, i.task = ts, task
            else:
                self.unmatched['built without dispatch'] += 1
        elif kind == 'task_create':          # explicit create (proposed): behaves like dispatch+bind
            i = Inst(len(self.insts), img or '?', hx(d.get('args', '0x0')), ln, len(self.by_image[img]) + 1)
            i.taskset, i.task = ts, task
            self.insts.append(i); self.by_image[img].append(i)
        elif kind == 'return':
            cands = [i for i in self.by_image.get(img, []) if i.ret is None]
            if ts is not None:
                cands = [i for i in cands if i.taskset == ts and (task is None or i.task == task)] or cands
            if cands:
                i = cands[0]; i.ret = ln
                i.ret_how = 'oldest-open (FIFO, ASSUMED)' if len(cands) > 1 else 'only open run'
            else:
                self.unmatched['return without open run'] += 1
        elif kind in ('task_activity', 'task_signal'):
            self.taskset_act[ts].append((ln, name, task))
            if name == 'sleeping': self.sleeps.append((ln, ts, task, int(d['n'])))
            i = self.open_on(ts, task)
            if i: i.events.append((ln, name))
        elif kind == 'spin':
            ea = hx(d['ea']); q = ea & ~0x7F
            w = [hx(d[k]) for k in ('w0', 'w1', 'w2', 'w3')]
            sane = (w[0] >> 16) == (w[1] & 0xFFFF) and (w[2] >> 16) == (w[3] & 0xFFFF)
            sp = {'line': ln, 'image': img, 'pc': d['pc'], 'lr': d['lr'], 'ea': ea, 'q': q, 'words': ' '.join(d[k] for k in ('w0', 'w1', 'w2', 'w3')),
                  'queue_header_sane': sane, 'empty': sane and (w[0] >> 16) == (w[2] >> 16), 'inst': None, 'candidates': []}
            opn = [i for i in self.by_image.get(img, []) if i.ret is None]
            own = [i for i in opn if i.taskset is not None and 0 <= ea - i.taskset < TASKSET_SPAN]
            pick = own if own else opn
            sp['candidates'] = [i.id for i in pick]
            if len(pick) == 1:
                sp['inst'] = pick[0].id; pick[0].spins.append(sp); pick[0].queues.add(q)
            self.spins.append(sp)
            self.q(q)['touch'].append((ln, 'spin img=%s' % img))
        elif kind == 'queue_init':
            Q = self.q(hx(d['q']))
            Q['inits'].append({'line': ln, 'owner': hx(d['owner']), 'buf': hx(d.get('buf', '0')), 'size': d.get('size'),
                               'depth': d.get('depth'), 'dir': d.get('dir')})
        elif kind in ('queue_push', 'queue_pop', 'queue_touch'):
            Q = self.q(hx(d['q']))
            Q[{'queue_push': 'pushes', 'queue_pop': 'pops', 'queue_touch': 'touch'}[kind]].append((ln, name))
            if ts is not None:
                Q['consumers'].add((ts, task))
                i = self.open_on(ts, task)
                if i: i.queues.add(hx(d['q'])); i.events.append((ln, name))
        elif kind == 'fs_open':
            self.fs.append((ln, d['path']))
        elif kind == 'ppu_thread':
            self.threads.append((ln, int(d['tid']), d['name']))
        elif kind == 'load_hint':
            self.hints.append((ln, name, line[:120]))
        elif kind in ('taskset_create', 'taskset_end'):
            self.taskset_marks[ts].append((ln, d.get('ev', kind)))
        elif kind == 'stage_mark':
            self.stage_marks.append((ln, d.get('name', 'sf-lc stage')))

    def q(self, q):
        if q not in self.queues:
            self.queues[q] = {'inits': [], 'pushes': [], 'pops': [], 'touch': [], 'consumers': set()}
        return self.queues[q]

    def open_on(self, ts, task):
        best = None
        for i in self.insts[::-1]:
            if i.taskset == ts and (task is None or i.task == task) and i.ret is None:
                return i
        return best

    # ---------------------------------------------------------------- analysis
    def analyse(self, rare_max=16, gap_lines=2000, stage_at=()):
        N = self.nlines
        rare = {img for img, L in self.by_image.items() if len(L) <= rare_max}
        rd = sorted(i.line for i in self.insts if i.image in rare)
        clusters = []
        for ln in rd:
            if clusters and ln - clusters[-1][-1] <= gap_lines: clusters[-1].append(ln)
            else: clusters.append([ln])
        starts = [(1, ['log start'])]
        for c in clusters[1:]:
            starts.append((c[0], ['rare-image dispatch cluster L%d-L%d (%d dispatches)' % (c[0], c[-1], len(c))]))
        for ln, nm in self.stage_marks:
            starts.append((ln, ['explicit ' + nm]))
        for ln in stage_at:
            starts.append((ln, ['--stage-at']))
        merged = []
        for ln, why in sorted(starts):
            if merged and ln - merged[-1][0] <= gap_lines and merged[-1][0] != 1: merged[-1][1].extend(why)
            else: merged.append([ln, list(why)])
        stages = []
        for k, (ln, why) in enumerate(merged):
            end = merged[k + 1][0] - 1 if k + 1 < len(merged) else N
            stages.append({'no': k, 'name': chr(ord('A') + k - 1) if k else 'boot', 'start': ln, 'end': end, 'why': why})
        def stage_of(ln):
            for s in stages[::-1]:
                if ln >= s['start']: return s['no']
            return 0
        for i in self.insts: i.stage = stage_of(i.line)
        # load evidence before each boundary: the fs-open burst that ends closest before it
        for s in stages[1:]:
            b = s['start']; prev = [f for f in self.fs if f[0] < b]
            burst = []
            for f in prev[::-1]:
                if burst and burst[-1][0] - f[0] > 300: break
                burst.append(f)
            burst = burst[::-1]
            s['load_burst'] = {'first': burst[0][0], 'last': burst[-1][0], 'n': len(burst), 'first_path': burst[0][1]} if burst else None
            win0 = stages[s['no'] - 1]['start']
            s['threads'] = [t for t in self.threads if win0 <= t[0] < b + gap_lines and LOADER_NAMES.search(t[2])][-4:]
            s['hints'] = [h for h in self.hints if b - 5000 <= h[0] < b + gap_lines][-6:]
            ts_seen_before = {i.taskset for i in self.insts if i.line < b and i.taskset is not None}
            s['tasksets_recreated'] = sorted({i.taskset for i in self.insts if i.stage == s['no'] and i.image in rare and i.taskset in ts_seen_before})
            if s['tasksets_recreated']:
                s['why'].append('taskset EA re-created: ' + ', '.join(fmt(t) for t in s['tasksets_recreated']))
        # alive at each stage change
        changes = []
        for s in stages[1:]:
            b = s['start']; alive = []
            for i in self.insts:
                if i.line < b and (i.ret is None or i.ret >= b):
                    after = [e for e in i.events if e[0] >= b] + [(x['line'], 'spu-spin') for x in i.spins if x['line'] >= b]
                    redis = [j for j in self.by_image[i.image] if j.stage == s['no'] and j.line >= b]
                    alive.append({'inst': i.id, 'label': i.label(), 'image': i.image, 'args': fmt(i.args), 'taskset': fmt(i.taskset), 'task': i.task,
                                  'dispatched': i.line, 'origin_stage': stages[i.stage]['name'], 'returned': i.ret,
                                  'evidence_after': sorted(after)[:3], 'last_evidence': max([e[0] for e in after], default=None),
                                  'redispatched_in_new_stage': [(j.line, fmt(j.args), fmt(j.taskset)) for j in redis],
                                  'verdict': ('LEAK: image re-dispatched in the new stage while this run never returned' if redis and i.ret is None
                                              else 'persistent (never re-dispatched)' if i.ret is None and len(self.by_image[i.image]) == 1
                                              else 'returned later at L%d' % i.ret if i.ret else 'open, not re-dispatched yet')})
            tsa = sorted({a['taskset'] for a in alive})
            qs = sorted({fmt(q) for q, Q in self.queues.items() if any(fmt(init['owner']) in tsa for init in Q['inits'])} |
                        {fmt(q) for a in alive for q in self.insts[a['inst']].queues})
            changes.append({'stage': s['name'], 'boundary': b, 'alive_runs': alive, 'alive_tasksets': tsa, 'alive_queues': qs})
        # address reuse while an old user may be live
        reuse = []
        for s in stages[1:]:
            b = s['start']
            for i in self.insts:
                if i.stage != s['no'] or i.image not in rare: continue
                old = [j for j in self.insts if j.line < b and j.ret is None and j.image == i.image]
                for j in old:
                    if j.taskset == i.taskset and i.taskset is not None:
                        reuse.append({'kind': 'taskset_reuse', 'addr': fmt(i.taskset), 'line': i.line, 'new': i.label(), 'old': j.label(),
                                      'old_dispatched': j.line, 'old_stage': stages[j.stage]['name'], 'new_stage': s['name'],
                                      'note': 'same taskset EA re-built while an earlier run on it never RETURNed'})
                    if j.args == i.args:
                        reuse.append({'kind': 'args_reuse', 'addr': fmt(i.args), 'line': i.line, 'new': i.label(), 'old': j.label(),
                                      'old_dispatched': j.line, 'old_stage': stages[j.stage]['name'], 'new_stage': s['name'],
                                      'note': 'same task args block handed to a new run while the old run never RETURNed'})
        for q, Q in self.queues.items():
            for a, bb in zip(Q['inits'], Q['inits'][1:]):
                users = [i for i in self.insts if i.taskset == a['owner'] and i.line <= bb['line'] and (i.ret is None or i.ret > bb['line'])]
                if users:
                    reuse.append({'kind': 'queue_reinit', 'addr': fmt(q), 'line': bb['line'], 'new': 'init owner ' + fmt(bb['owner']),
                                  'old': ', '.join(u.label() for u in users[:3]), 'old_dispatched': users[0].line, 'old_stage': stages[users[0].stage]['name'],
                                  'new_stage': stages[stage_of(bb['line'])]['name'], 'note': 'queue re-initialised while a run of its old owner never returned'})
        for sp in self.spins:
            st = stage_of(sp['line'])
            cur = [c for c in sp['candidates'] if self.insts[c].stage == st]
            for iid in sp['candidates']:
                i = self.insts[iid]
                if i.stage < st and i.taskset is not None and 0 <= sp['ea'] - i.taskset < TASKSET_SPAN:
                    reuse.append({'kind': 'possible_stale_poll' if cur else 'stale_poll', 'addr': fmt(sp['ea']), 'line': sp['line'], 'new': 'stage %s memory' % stages[st]['name'],
                                  'old': i.label(), 'old_dispatched': i.line, 'old_stage': stages[i.stage]['name'], 'new_stage': stages[st]['name'],
                                  'note': ('polls a queue of its old taskset (+0x%X) after its stage ended; line %s %s' %
                                           (sp['ea'] - i.taskset, sp['words'], 'looks like a queue header' if sp['queue_header_sane']
                                            else 'is NOT a queue header (memory likely reused)'))
                                  + ('' if len(sp['candidates']) == 1 else ' [ambiguous: %d candidate runs%s]' % (len(sp['candidates']),
                                     ', incl. current-stage ' + ', '.join(self.insts[c].label() for c in cur) if cur else ''))})
        # the same (taskset, task) printing the same 'sleeping Ns' twice within a few lines = two live host threads for one task
        dup = []; grp = defaultdict(list)
        for ln, ts, task, n in self.sleeps: grp[(ts, task, n)].append(ln)
        for (ts, task, n), lines in grp.items():
            for a, b in zip(lines, lines[1:]):
                if b - a <= 200:
                    runs = [i for i in self.insts if i.taskset == ts and i.task == task and i.line < a and (i.ret is None or i.ret > a)]
                    dup.append({'line': b, 'first': a, 'taskset': fmt(ts), 'task': task, 'secs': n,
                                'open_runs': [i.label() + ' L%d' % i.line for i in runs]})
                    reuse.append({'kind': 'duplicate_live_task', 'addr': fmt(ts), 'line': b, 'new': '%s/t%d' % (fmt(ts), task),
                                  'old': ', '.join(i.label() for i in runs) or '?', 'old_dispatched': runs[0].line if runs else 0,
                                  'old_stage': stages[runs[0].stage]['name'] if runs else '?', 'new_stage': stages[stage_of(b)]['name'],
                                  'note': "'task %d (taskset %s) sleeping %ds' printed at L%d and L%d: two waiters for one task (the two lines are CONFIRMED; one line per waiting host thread is ASSUMED from the format, the print source is not on the box)"
                                          % (task, fmt(ts), n, a, b)})
        reuse.sort(key=lambda r: (r['line'], r['kind']))
        never = [i for i in self.insts if i.ret is None]
        tasksets = defaultdict(lambda: {'runs': 0, 'returned': 0, 'images': set(), 'first': None, 'last': None, 'open': []})
        for i in self.insts:
            T = tasksets[fmt(i.taskset)]
            T['runs'] += 1; T['returned'] += i.ret is not None; T['images'].add(i.image)
            T['first'] = i.line if T['first'] is None else T['first']; T['last'] = i.line
            if i.ret is None: T['open'].append(i.id)
        self.result = {'duplicates': dup, 'lines': N, 'stages': stages, 'changes': changes, 'reuse': reuse, 'never': [i.id for i in never],
                       'rare_images': sorted(rare), 'tasksets': tasksets}
        return self.result


# -------------------------------------------------------------------- outputs
def inst_dict(i):
    return {'id': i.id, 'label': i.label(), 'image': i.image, 'k': i.k, 'args': fmt(i.args), 'taskset': fmt(i.taskset), 'task': i.task,
            'dispatched': i.line, 'returned': i.ret, 'ret_how': i.ret_how, 'stage': i.stage,
            'spins': [{k: (fmt(v) if k in ('ea', 'q') else v) for k, v in s.items()} for s in i.spins],
            'queues': [fmt(q) for q in sorted(i.queues)], 'n_events': len(i.events),
            'first_event': i.events[0] if i.events else None, 'last_event': i.events[-1] if i.events else None}


def summary(M, R, path):
    S = R['stages']; L = []
    L.append(f'# SPURS lifecycle summary: {path}  ({R["lines"]} lines)')
    L.append('Stages are INFERRED (rare-image dispatch clusters, taskset re-creation, fs-open bursts); line numbers are the log\'s own.')
    L.append('')
    L.append('## Stages')
    for s in S:
        L.append(f"- {s['name']:5s} L{s['start']}-L{s['end']}: " + '; '.join(s['why']))
        if s.get('load_burst'):
            lb = s['load_burst']; L.append(f"        load before it: {lb['n']} fs opens L{lb['first']}-L{lb['last']} (first {lb['first_path']})")
        for t in s.get('threads', []): L.append(f"        loader-type thread: L{t[0]} tid={t[1]} {t[2]}")
    L.append('')
    L.append('## Runs that never RETURNED (by image)')
    by = defaultdict(list)
    for iid in R['never']: by[M.insts[iid].image].append(M.insts[iid])
    for img, runs in sorted(by.items(), key=lambda x: x[1][0].line):
        tot = len(M.by_image[img]); ret = sum(1 for i in M.by_image[img] if i.ret)
        L.append(f"- image {img}: dispatched {tot}, returned {ret}, open {len(runs)}: " +
                 ', '.join(f"L{i.line} {fmt(i.taskset)}/t{i.task} args {fmt(i.args)} (stage {S[i.stage]['name']})" for i in runs))
    L.append('')
    L.append('## SPU spin lines ([spu-spin] = one host thread re-read one line 4M times)')
    for sp in M.spins:
        who = M.insts[sp['inst']].label() if sp['inst'] is not None else 'ambiguous: ' + ' | '.join(M.insts[c].label() for c in sp['candidates'])
        L.append(f"- L{sp['line']} img {sp['image']} pc {sp['pc']} ea {fmt(sp['ea'])} line {sp['words']} "
                 f"[{'empty queue' if sp['empty'] else 'queue header' if sp['queue_header_sane'] else 'NOT a queue header'}] -> {who}")
    L.append('')
    for c in R['changes']:
        L.append(f"## Stage change -> {c['stage']} at L{c['boundary']}: still alive from older stages")
        for a in c['alive_runs']:
            ev = ', '.join(f"L{e[0]} {e[1]}" for e in a['evidence_after']) or 'no later line attributed'
            L.append(f"- {a['label']} args {a['args']} dispatched L{a['dispatched']} (stage {a['origin_stage']}) "
                     f"{'returned L%d' % a['returned'] if a['returned'] else 'NEVER returned'}; after the change: {ev}")
            L.append(f"      verdict: {a['verdict']}" + (f"; new-stage runs: {a['redispatched_in_new_stage']}" if a['redispatched_in_new_stage'] else ''))
        L.append(f"  tasksets alive: {', '.join(c['alive_tasksets']) or '-'}")
        L.append(f"  queues alive (owned by / touched by those): {', '.join(c['alive_queues']) or '-'}")
        L.append('')
    L.append('## Addresses re-used while an old user may still be live')
    if not R['reuse']: L.append('- none found')
    for r in R['reuse']:
        L.append(f"- L{r['line']} {r['kind']:19s} {r['addr']}: new {r['new']} (stage {r['new_stage']}) vs old {r['old']} "
                 f"(L{r['old_dispatched']}, stage {r['old_stage']}) - {r['note']}")
    L.append('')
    L.append('## Per-taskset timeline')
    for ts, T in sorted(R['tasksets'].items(), key=lambda x: x[1]['first']):
        act = M.taskset_act.get(int(ts, 16) if ts != '-' else None, [])
        L.append(f"- {ts}: images {sorted(T['images'])}, runs {T['runs']} (returned {T['returned']}), dispatches L{T['first']}..L{T['last']}, "
                 f"WAIT/signal lines {len(act)}" + (f" L{act[0][0]}..L{act[-1][0]}" if act else '') +
                 (f", open: {', '.join(M.insts[i].label() + ' L%d' % M.insts[i].line for i in T['open'][:6])}" if T['open'] else ''))
        mk = M.taskset_marks.get(int(ts, 16) if ts != '-' else None)
        if mk: L.append(f"      explicit lifecycle: {mk}")
    L.append('')
    L.append('## Queues')
    for q, Q in M.queues.items():
        ini = '; '.join(f"init L{x['line']} owner {fmt(x['owner'])} depth {x['depth']} dir {x['dir']}" for x in Q['inits']) or 'no init line (capped or before log)'
        L.append(f"- {fmt(q)}: {ini}; pushes {len(Q['pushes'])}" + (f" (last L{Q['pushes'][-1][0]})" if Q['pushes'] else '') +
                 f"; pops {len(Q['pops'])}; other {len(Q['touch'])}" + (f" (last L{Q['touch'][-1][0]})" if Q['touch'] else ''))
    if M.unmatched:
        L.append(''); L.append('## Unmatched: ' + ', '.join(f'{k}: {v}' for k, v in M.unmatched.items()))
    return '\n'.join(L) + '\n'


def svg_timeline(M, R, lo=1, hi=None):
    N = max(R['lines'], 1); hi = hi or N; W = 1500; X0 = 230; PW = W - X0 - 20
    x = lambda ln: X0 + PW * (min(max(ln, lo), hi) - lo) / max(hi - lo, 1)
    vis = lambda ln: lo <= ln <= hi
    rare = set(R['rare_images']); rows = []
    for i in sorted((i for i in M.insts if i.image in rare), key=lambda i: (i.image, i.line)):
        rows.append(('run', i))
    for img, runs in sorted(M.by_image.items()):
        if img not in rare: rows.append(('rep', img))
    tsrows = sorted({t for t in M.taskset_act if t is not None}, key=lambda t: M.taskset_act[t][0][0])
    RH = 16; top = 70
    H = top + (len(rows) + len(tsrows) + 3) * RH + 40
    e = html.escape; o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" font-family="monospace" font-size="11">']
    cols = ['#f4f4f4', '#e8eef8']
    for s in [s for s in R['stages'] if s['end'] >= lo and s['start'] <= hi]:
        o.append(f'<rect x="{x(s["start"]):.1f}" y="20" width="{max(1, x(s["end"]) - x(s["start"])):.1f}" height="{H - 30}" fill="{cols[s["no"] % 2]}"><title>{e(s["name"])} L{s["start"]}-L{s["end"]}: {e("; ".join(s["why"]))}</title></rect>')
        o.append(f'<text x="{x(s["start"]) + 3:.1f}" y="32" font-weight="bold">{e(s["name"])} L{s["start"]}</text>')
        if s['no']: o.append(f'<line x1="{x(s["start"]):.1f}" y1="20" x2="{x(s["start"]):.1f}" y2="{H - 10}" stroke="#555" stroke-dasharray="4,3"/>')
    y = 44
    o.append(f'<text x="4" y="{y + 10}">fs opens / loaders</text>')
    for ln, p in M.fs:
        if vis(ln): o.append(f'<line x1="{x(ln):.1f}" y1="{y}" x2="{x(ln):.1f}" y2="{y + 8}" stroke="#2a7"><title>L{ln} {e(p)}</title></line>')
    for ln, tid, nm in M.threads:
        if LOADER_NAMES.search(nm) and vis(ln): o.append(f'<circle cx="{x(ln):.1f}" cy="{y + 12}" r="3" fill="#a52"><title>L{ln} thread tid={tid} {e(nm)}</title></circle>')
    y = top
    for kind, it in rows:
        if kind == 'run':
            i = it; end = i.ret or N
            col = '#4a8' if i.ret else '#d33'
            if i.line > hi or end < lo: y += RH; continue
            o.append(f'<text x="4" y="{y + 11}">{e(i.label())[:34]}</text>')
            tip = f'{i.label()} args {fmt(i.args)} dispatched L{i.line} ' + (f'returned L{i.ret}' if i.ret else 'NEVER returned')
            o.append(f'<rect x="{x(i.line):.1f}" y="{y + 3}" width="{max(2, x(end) - x(i.line)):.1f}" height="9" fill="{col}" opacity="0.75"><title>{e(tip)}</title></rect>')
            for sp in [q for q in i.spins if vis(q['line'])]:
                o.append(f'<path d="M{x(sp["line"]):.1f},{y + 1} l5,12 l-10,0 z" fill="#f90" stroke="#000" stroke-width="0.5"><title>L{sp["line"]} spin ea {fmt(sp["ea"])} {sp["words"]}</title></path>')
        else:
            runs = M.by_image[it]; nb = 300; bins = [0] * nb
            for i in runs:
                if vis(i.line): bins[min(nb - 1, int(nb * (i.line - lo) / max(hi - lo, 1)))] += 1
            mx = max(bins) or 1; bw = PW / nb
            o.append(f'<text x="4" y="{y + 11}">{e(it)} x{len(runs)} (repeating)</text>')
            for b, c in enumerate(bins):
                if c: o.append(f'<rect x="{X0 + b * bw:.1f}" y="{y + 13 - 11 * c / mx:.1f}" width="{bw:.1f}" height="{11 * c / mx:.1f}" fill="#68a"/>')
            for i in runs:
                if i.ret is None and i.line <= hi:
                    o.append(f'<rect x="{x(i.line):.1f}" y="{y + 3}" width="{max(3, x(N) - x(i.line)):.1f}" height="9" fill="#d33" opacity="0.75"><title>{e(i.label())} dispatched L{i.line} NEVER returned</title></rect>')
                for sp in [q for q in i.spins if vis(q['line'])]:
                    o.append(f'<path d="M{x(sp["line"]):.1f},{y + 1} l5,12 l-10,0 z" fill="#f90" stroke="#000" stroke-width="0.5"><title>L{sp["line"]} spin ea {fmt(sp["ea"])} {sp["words"]}</title></path>')
        y += RH
    for sp in M.spins:
        if sp['inst'] is None and vis(sp['line']):
            o.append(f'<path d="M{x(sp["line"]):.1f},{y + 1} l5,12 l-10,0 z" fill="#f90" stroke="#000" stroke-width="0.5"><title>L{sp["line"]} spin img {sp["image"]} ea {fmt(sp["ea"])} (ambiguous owner)</title></path>')
    o.append(f'<text x="4" y="{y + 11}">ambiguous spins</text>'); y += RH
    o.append(f'<text x="4" y="{y + 11}" font-weight="bold">taskset WAIT/signal</text>'); y += RH
    for ts in tsrows:
        o.append(f'<text x="4" y="{y + 11}">{fmt(ts)}</text>')
        for ln, nm, task in [a for a in M.taskset_act[ts] if vis(a[0])][:4000]:
            o.append(f'<line x1="{x(ln):.1f}" y1="{y + 2}" x2="{x(ln):.1f}" y2="{y + 13}" stroke="#77c" stroke-width="0.6"/>')
        y += RH
    for r in [r for r in R['reuse'] if vis(r['line'])]:
        o.append(f'<line x1="{x(r["line"]):.1f}" y1="38" x2="{x(r["line"]):.1f}" y2="{H - 10}" stroke="#c0c" stroke-width="1"><title>L{r["line"]} {e(r["kind"])} {e(r["addr"])}: {e(r["note"])}</title></line>')
    o.append(f'<text x="{X0}" y="14">x = log line {lo}..{hi}.  green = run that returned, red = never returned, orange = [spu-spin], magenta = address reuse, dashed = inferred stage start. Hover for details.</text>')
    o.append('</svg>')
    return '\n'.join(o)


def write_html(M, R, path, out, txt):
    e = html.escape
    zlo = max(1, (R['stages'][-1]['start'] if len(R['stages']) > 1 else 1) - 500)
    rows = ''.join(f"<tr><td>L{r['line']}</td><td>{e(r['kind'])}</td><td>{e(r['addr'])}</td><td>{e(r['new'])} ({e(r['new_stage'])})</td>"
                   f"<td>{e(r['old'])} L{r['old_dispatched']} ({e(r['old_stage'])})</td><td>{e(r['note'])}</td></tr>" for r in R['reuse'])
    doc = f"""<!doctype html><html><head><meta charset="utf-8"><title>SPURS lifecycle - {e(os.path.basename(path))}</title>
<style>body{{font-family:sans-serif;margin:12px}} table{{border-collapse:collapse;font-size:12px}} td,th{{border:1px solid #ccc;padding:2px 6px}}
pre{{font-size:12px;background:#fafafa;padding:8px;white-space:pre-wrap}} .wrap{{overflow-x:auto;border:1px solid #ddd}}</style></head><body>
<h2>SPURS taskset/task lifecycle: {e(path)}</h2>
<div class="wrap">{svg_timeline(M, R)}</div>
<h3>Zoom: last stage change L{zlo}..L{R['lines']}</h3>
<div class="wrap">{svg_timeline(M, R, zlo, R['lines'])}</div>
<h3>Addresses re-used while an old user may still be live</h3>
<table><tr><th>line</th><th>kind</th><th>address</th><th>new user</th><th>old user</th><th>note</th></tr>{rows or '<tr><td colspan=6>none</td></tr>'}</table>
<h3>Text summary</h3><pre>{e(txt)}</pre></body></html>"""
    open(os.path.join(out, 'lifecycle.html'), 'w', encoding='utf-8').write(doc)


def run(path, out=None, strip_prefix=False, rare_max=16, gap_lines=2000, stage_at=(), quiet=False):
    M = Model()
    with open(path, 'rb') as fh:
        for n, b in enumerate(fh, 1):
            line = b.replace(b'\x00', b'').decode('utf-8', 'replace').rstrip('\r\n')
            if strip_prefix:
                m = re.match(r'^(\d+):(.*)$', line)
                if m: n, line = int(m.group(1)), m.group(2)
            M.feed(n, line)
    R = M.analyse(rare_max, gap_lines, stage_at)
    txt = summary(M, R, path)
    if out:
        os.makedirs(out, exist_ok=True)
        open(os.path.join(out, 'lifecycle_summary.txt'), 'w', encoding='utf-8').write(txt)
        write_html(M, R, path, out, txt)
        J = dict(R, tasksets={k: dict(v, images=sorted(v['images'])) for k, v in R['tasksets'].items()},
                 runs=[inst_dict(i) for i in M.insts if i.image in R['rare_images'] or i.ret is None or i.spins],
                 spins=[{k: (fmt(v) if k in ('ea', 'q') else v) for k, v in s.items()} for s in M.spins],
                 queues={fmt(q): {'inits': [dict(x, owner=fmt(x['owner']), buf=fmt(x['buf'])) for x in Q['inits']], 'pushes': len(Q['pushes']),
                                  'pops': len(Q['pops']), 'touch': Q['touch'][-5:], 'consumers': [[fmt(a), b] for a, b in Q['consumers']]}
                         for q, Q in M.queues.items()})
        json.dump(J, open(os.path.join(out, 'lifecycle.json'), 'w'), indent=1, default=str)
    if not quiet: sys.stdout.write(txt)
    return M, R


def selftest():
    import tempfile
    L = ["[sf-lfq] init owner=0x16FA2000 q=0x16FA3900 buf=0x16FA1EB0 size=16 depth=8 dir=2 -> 0x00000000",
         "[spu_workload] dispatch HIT (async) fp=0x1 args=0x16FA3A80 image=361927206 -> spawning thread",
         "[taskset] built SpursTasksetContext image=361927206 taskset=0x16FA2000 task=0"]
    L += ["[fs] open '/dev_hdd1/cache/BLUS30471/%d' -> fd 6" % k for k in range(5)]
    L += ["[spu_workload] dispatch HIT (async) fp=0x1 args=0x11058B00 image=437063289 -> spawning thread",
          "[taskset] built SpursTasksetContext image=437063289 taskset=0x11057180 task=0",
          "[spu_workload] async image=437063289 RETURNED rc=0 (job ran to completion, did not loop)"] * 30
    L += ["[spu_workload] dispatch HIT (async) fp=0x1 args=0x16C54100 image=361927206 -> spawning thread",
          "[taskset] built SpursTasksetContext image=361927206 taskset=0x16C52680 task=0"]
    L += ["x"] * 50
    L += ["[spu_workload] dispatch HIT (async) fp=0x1 args=0x16FA3A80 image=361927206 -> spawning thread",
          "[taskset] built SpursTasksetContext image=361927206 taskset=0x16FA2000 task=0",
          "[spu-spin] img=361927206 pc=0x0B42C lr=0x0B420 GETLLAR ea=0x16C53F80 x4M; line: 00000000 CDCDCDCD FFFFFFFF 006B42C0",
          "[sf-lc] taskset_shutdown ts=0x16C52680",
          "[spu_workload] task 0 (taskset 0x16FA2000) sleeping 1s in WAIT_SIGNAL",
          "[spu_workload] task 0 (taskset 0x16FA2000) sleeping 1s in WAIT_SIGNAL"]
    fd, p = tempfile.mkstemp(); os.write(fd, ('\n'.join(L) + '\n').encode()); os.close(fd)
    M, R = run(p, None, gap_lines=20, quiet=True); os.unlink(p)
    kinds = {(r['kind'], r['addr']) for r in R['reuse']}
    ok = len(R['stages']) == 3 and ('taskset_reuse', '0x16FA2000') in kinds and ('args_reuse', '0x16FA3A80') in kinds
    ok &= ('stale_poll', '0x16C53F80') in kinds and any('LEAK' in a['verdict'] for a in R['changes'][1]['alive_runs'])
    ok &= ('duplicate_live_task', '0x16FA2000') in kinds
    ok &= len(R['never']) == 3 and M.taskset_marks[0x16C52680] and M.spins[0]['inst'] is not None
    print('SELFTEST', 'OK' if ok else 'FAIL', sorted(kinds), [s['start'] for s in R['stages']])
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('log', nargs='?'); ap.add_argument('--out'); ap.add_argument('--strip-prefix', action='store_true')
    ap.add_argument('--rare-max', type=int, default=16, help='an image with <= this many dispatches is a stage-level task (default 16)')
    ap.add_argument('--gap-lines', type=int, default=2000, help='rare dispatches closer than this form one stage-start cluster')
    ap.add_argument('--stage-at', type=int, nargs='*', default=[], help='add stage starts by hand (line numbers)')
    ap.add_argument('--quiet', action='store_true'); ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest: return selftest()
    if not a.log: ap.error('give a LOG or --selftest')
    out = a.out or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results', os.path.splitext(os.path.basename(a.log))[0])
    run(a.log, out, a.strip_prefix, a.rare_max, a.gap_lines, a.stage_at, a.quiet)
    print('-> ' + out); return 0


if __name__ == '__main__':
    sys.exit(main())
