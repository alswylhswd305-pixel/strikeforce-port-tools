# voicefreeze tools (stdlib Python 3, no deps)

## voice_freeze_analyzer.py
Parses SF-DIAG 1786 stderr logs: `[sfww]` store watch, `[vi]` voice arrays, `[vm]/[vm-cnt]/[vm-rec]/[vm-sum]`, `[hle-lr]/[hle-lrc]`, SPU unlifted/halt/LS dumps, `EventFlagWait BLOCKED`, `[fs] open` / Now Loading markers.
```
python3 voice_freeze_analyzer.py LOG [LOG...] [--stubs stub_missing_called.json] [--out DIR] [--cap 128] [--win 100] [--freer-tid 7] [--starter-tid 17]
python3 voice_freeze_analyzer.py --selftest     # needs /workspace/sf-shared/testloop/reports/voicediag1786_*
```
Writes DIR/report.md + DIR/report.json. The report covers:
- the per-thread timeline;
- starts and frees per window;
- the live-voice (union) curve and the moment it hits the cap;
- tid 7 activity during bursts;
- stubs/missing NIDs called near bursts;
- loading transitions;
- the last line per thread, with its wait object;
- ranked candidates C1-C5 with file:line evidence. Points are evidence counts, not probabilities.

To add a log format, add an entry to `PATTERNS` (name -> compiled regex) and handle the name in `Analyzer.feed`.
Example run on the voicediag1786 data: `python3 voice_freeze_analyzer.py ../testloop/reports/voicediag1786_diag_lines.txt --stubs ../testloop/reports/voicediag1786_stub_missing_called.json --out out_voicediag1786`

## race_check.py
Reads the SF_RACE log (race_run_spec.md) and reports, per mixer pass, these checks:
- V: visits per pass (> 176 is an overflow, >= 201 reaches the table);
- M: a voice in snapshot group g while its mask lacks bit g;
- L: a record changed between the GET and the PUT;
- W: tid17 stores inside the pass;
- E: flag set vs the pass end.
```
python3 race_check.py sfrace_<pid>.log [stderr.log] [--tid 17] [--json out.json]
python3 race_check.py --selftest
```

## spu_mini_decode.py
Own SPU decoder (common RRR/RI18/RI10/RI16/RI7/RR forms, halts annotated). `python3 spu_mini_decode.py 31C20 7F003200 1200089A ...`
