# sf_lifecycle.py: SPURS taskset/task lifecycle timeline and stage-transition leak checker (box-only)

Stdlib-only Python 3. It reads a saved stderr log (read-only) and never touches the game, the PC or GitHub.
It was built for the village black hang (`../blackhang_1817.md`).

## Run
```
python3 sf_lifecycle.py LOG                         # writes results/<log name>/ next to this script, prints the summary
python3 sf_lifecycle.py LOG --out DIR --quiet
python3 sf_lifecycle.py EXTRACT.txt --strip-prefix  # input lines look like "66154:[spu-spin] ..."
python3 sf_lifecycle.py LOG --stage-at 106822 ...   # add stage starts by hand
python3 sf_lifecycle.py --selftest
```
Options:
- `--rare-max 16`: an image with at most this many dispatches counts as a stage-level task. Per-frame jobs such as 437063289 are "repeating".
- `--gap-lines 2000`: rare dispatches closer together than this form one stage-start cluster.

## Outputs (`results/<log>/`)
- **`lifecycle_summary.txt`:**
  - stages (with the reasons they were inferred, the fs-open burst before each, and loader-type threads);
  - runs that never RETURNED;
  - `[spu-spin]` lines, with the run they belong to and whether the polled line is an empty queue, a queue header, or not a queue header;
  - per stage change: the runs, tasksets and queues still alive from older stages, the evidence after the change, and a verdict;
  - addresses reused while an old user may be live;
  - a per-taskset timeline and a per-queue list.
- **`lifecycle.html`:** a self-contained page with two inline-SVG timelines (whole log, and a zoom on the last stage change), the reuse table and the text summary. Hover any mark for details.
  - Green bar: a run that returned. Red bar: a run that never returned.
  - Orange triangle: `[spu-spin]`. Magenta line: address reuse. Dashed line: inferred stage start.
  - Ticks: fs opens, loader threads, taskset WAIT/sleeping/signal lines. Repeating jobs are drawn as a density strip plus their open run.
- **`lifecycle.json`:** the same data.

## How it decides (all INFERRED from log lines; check the line numbers)
- **Run** = one `dispatch HIT (async)`, bound to its taskset and task by the next `[taskset] built` line for that image (FIFO).
  - A `RETURNED` line closes the oldest open run of its image. When several are open, this is marked `oldest-open (FIFO, ASSUMED)`.
- **Stage start** = a cluster of dispatches of rare images, or an explicit `[sf-lc] stage`, or `--stage-at`. It is annotated with the fs-open burst just before it and with any taskset EA re-created in it.
- **Alive at a stage change** = dispatched before the boundary and not RETURNED before it. Lines after the boundary are attributed to the run:
  - WAIT_SIGNAL / sleeping / signal lines go to the newest open run on that taskset and task;
  - a spin goes to the open run of that image whose taskset lies within 0x4000 below the EA, or to the only open run.
- **Verdicts:**
  - `LEAK` = the same image was dispatched again in the new stage while this run never returned;
  - `persistent` = dispatched once only (for example the mixer);
  - `returned later`.
- **Reuse kinds:**
  - `taskset_reuse`: the same taskset EA is re-built while an older run on it never returned;
  - `args_reuse`: the same image and args block is handed to a new run in that situation;
  - `queue_reinit`: a second `[sf-lfq] init` of a queue while a run of its old owner is open;
  - `stale_poll`: a `[spu-spin]` by a run from an older stage on an address inside its old taskset. It says whether the line still looks like an LFQueue header (h1==h4 and h5==h8).
  - `possible_stale_poll`: the same, but a current-stage run is also a candidate.
  - `duplicate_live_task`: the same `task N (taskset X) sleeping Ns` printed twice within 200 lines. The two lines are a fact; reading them as two waiting host threads is ASSUMED from the format, because the print source is not on the box.

## Extending (new log-only build formats)
Each input format is one row of `RULES` at the top of the script: `(name, prefix, regex with named groups, kind)`.
- Use the standard group names: `image args taskset task q ea owner buf size depth dir w0..w3 pc lr name tid path n`.
- Pick one of these kinds: `dispatch bind return task_create task_activity task_signal spin queue_init queue_push queue_pop queue_touch fs_open ppu_thread load_hint taskset_create taskset_end stage_mark`.
- `[sf-lfq] pop q=...` is already in the table, for the proposed SPU-side pop line.

The proposed lifecycle hook needs **no new code**. If it prints `[sf-lc] <event> key=value ...`, every key is parsed. Events mapped so far (`SF_LC` dict):

| event | kind | keys used |
|---|---|---|
| `taskset_create` / `taskset_shutdown` / `taskset_join` / `taskset_destroy` | taskset_create / taskset_end | `ts=` (or `taskset=`) |
| `task_create` | task_create (dispatch+bind in one) | `ts= task= image=`/`img= args=` |
| `task_exit`, `host_thread_stop` | return | `image= ts= task=` |
| `task_start`, `host_thread_start` | task_activity | `ts= task=` |
| `lfq_init` / `lfq_push` / `lfq_pop` | queue_* | `q= owner= depth= dir= ts= task=` |
| `stage` | stage_mark | `name=` |

Example line: `[sf-lc] taskset_shutdown ts=0x16C52680 rc=0 hosttid=1234`.
The uncapped `[sf-lfq]` / `[sf-lfq2]` lines from `SF_LFQ_LOG_MAX=0` use the existing rows unchanged.

## Verified on the box (2026-11-27 18:40, Asia/Kuwait)
`--selftest` OK. Both real logs run in about 2 s each. Results: `results/saud_blackhang_1817_stderr/`, `results/voicediag1786_saud_20261127-172741_stderr/`.
- **18:17 black hang:**
  - stages: boot; A from L34751; B from L47344; C from L106822. C re-creates 0x16FA2000.
  - 361927206 and 433674278: 3 dispatched, 0 returned. 9000: 0 of 3 returned. 437063289: one open run from L107973.
  - `taskset_reuse` / `args_reuse` for 0x16FA2000 at L106846/L106847 (old runs from L34787/L34788); for 0x14C02A80 (image 9000) at L47344 and L106822.
  - `stale_poll` 0x16C53F80 at L107252: the stage-B run 361927206#2, at offset +0x1900 of its old taskset; the line is not a queue header.
  - `possible_stale_poll` 0x16FA3980 at L108353: 433674278, stage A or C.
- **17:27 log:**
  - stages: boot; A from L12233; B from L40515.
  - 9000, 361927206 and 433674278: the stage-A runs never returned and the images were re-dispatched in B (LEAK).
  - After the stage change, the stage-A tasks of 0x16FA2000 still print `sleeping` at L76789/L76790.
  - `duplicate_live_task` 0x14C02A80 t0 at L76791 + L76795.
  - `taskset_reuse` / `args_reuse` for 0x14C02A80 at L40515. No reuse of 0x16FA2000: B used 0x16C52680.

sha256 `sf_lifecycle.py` = ced42e1cc8d36fd5987039ac05d4400d1ba839bd242c72d64e4548cc4efb79ba
