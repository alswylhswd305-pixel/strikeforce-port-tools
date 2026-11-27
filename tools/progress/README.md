# مقياس تقدّم سترايك فورس (BLUS30471)

يعيد هذا المجلد حساب أرقام المقياس من مصادر معدودة. لا يخترع نسبة واحدة لـ«كم خلصت اللعبة».

## التحديث بعد كل تجربة

```bash
python3 /workspace/sf-progress/gather_progress.py
```

أو مع لوق جديد ومجلد الأفلام إن توفر:

```bash
python3 /workspace/sf-progress/gather_progress.py \
  --log /workspace/sf-shared/testloop/saud_blackhang_1817_stderr.log \
  --movie-dir "/path/to/PS3_GAME/USRDIR/movie"
```

يكتب:

- `progress.json` — كل الأرقام مع مصادرها
- `progress.md` — ملخص عربي قصير

المصادر الثابتة (قائمة المهام، الأفلام المتحقق منها) في `sources.json`.
عدّ الدوال من `/workspace/sf-shared/progress-src/out/EBOOT.functions.json`.
تصنيف دوال النظام من `/workspace/sf-shared/nid-autolink/pc-results/` (يقرأ v2 إن وجد، ولا يستبدل أرقام التصنيف إلا إذا ظهر `report.csv` جديد داخل v2).

بعد التوليد، تُحدَّث صفحة المقياس يدوياً من `progress.json` (الصفحة لا تتحدث وحدها).
