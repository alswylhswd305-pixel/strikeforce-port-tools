# أدوات تغطية الرسم ودوال النظام

تعاد بعد كل بناء. **ما تشغّل اللعبة وما تقفلها.** تقرأ المصدر والسجلات فقط، وتكتب ملفات جديدة تحت `tools/coverage_tools/out/`.

القياسات تستخدم نفس قواعد العد السابقة:

- أوامر الرسم: `tools/rsx_census/gen_coverage.py` (2026-11-27) — 376/798 كان الرقم المنشور (مدعوم / أوامر لها اسم أو معالج).
- دوال النظام: `nid-coverage.md` (2026-11-26 21:29 توقيت الكويت) — 267/346 منفَّذة من مستوردات `out/EBOOT.imports.json`.

التصنيف آلي (**غير مؤكد** / ASSUMED) إلا إذا وُسم KNOWN.

## التشغيل (من جذر نسخة التجربة)

```text
cd <your-test-copy-root>   # or set SF_TEST_ROOT

python tools\coverage_tools\rsx_coverage.py
python tools\coverage_tools\syscall_coverage.py
```

أو بمسار صريح:

```text
python tools\coverage_tools\rsx_coverage.py --root . --out sfauto\coverage_tools\out
python tools\coverage_tools\syscall_coverage.py --root . --out sfauto\coverage_tools\out
```

خيارات مفيدة:

- `--src` و `--backend` لأوامر الرسم إذا تبي تحدد شجرة بناء غير الأحدث.
- `--max-log-mb 120` حد حجم السجل (الافتراضي 120). الملفات الأكبر تُتخطى وتُذكر في JSON.
- `--rpcs3` لمسار سجل RPCS3 (مرجع سلوك فقط، مو مصدر كود).

## المخرجات

تحت `sfauto\coverage_tools\out\`:

- `rsx_coverage.json` / `.md` / `.png`
- `syscall_coverage.json` / `.md` / `.png`

الصورة ملخص عربي، والصفوف العشرة الأهم مظللة بالأحمر.

المصدر الأحدث يُختار تلقائياً من `sfauto\*\src` (أحدث `rsx_commands.c` وأحدث `rsx_d3d12_backend.c`)، والملفات الناقصة تُكمَّل من `ps3recomp\libs\video`.

These tools are dual-licensed: AGPL-3.0-or-later, or a commercial licence from Saud Hamad Alsuwailih.
