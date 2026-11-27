# مواصفات التشغيل التالية — لسالم (مسودة)

تاريخ: 2026-11-27 19:19 Asia/Kuwait (UTC+3)  
من: مختبر البيتا  
إلى: سالم (مشغّل الجهاز فقط)  
هذه مسودة للمنسّق؛ المختبر لا يراسل سالم مباشرة ولا يلمس جهاز سعود.

## الأولوية والسلامة

1. **لا تقاطع** عمل 1788_bbits ولا نافذة SFRACE (`1786_sfrace`). بناء 1788 جاهز (exe MD5 `0AA9D0B7F8F213D5E2AA09B300CD70E2`، 19:13) واختبار الحداد/census **لم يبدأ** وفق `/workspace/sf-gfx-runs/BUILD_1788.md`. أكمل ذلك أولاً إن كان ما زال في الانتظار.
2. هذا التشغيل **بعد** خمول 5 دقائق بلا `MyGameRecomp` وبلا نافذة SFRACE، وعلى **نسخة التجربة فقط**: `<TEST_COPY>`.
3. لا تعدّل `PLAY_Strikeforce.bat`. لا تلمس RPCS3 أو Downloads أو ملفات لعب سعود. نافذة واحدة `[TEST-SALEM]`. لا تكتب `sfauto\ringwatch_work\pad.txt`.
4. غش النقل/learn للتشخيص فقط. لا تجميد صحة ما دامت `confirmed_hp` فارغة. لا تخطّي أفلام/مشاهد ولا ضغط أثناءها.

## البناء / النسخة

- **لا تستخدم** `sfauto\exe_copies\1788_bbits\MyGameRecomp.exe` لهذا التشغيل (نسخة إضاءة/census).
- استخدم مشغّل العدّة كما هو: `sfauto\autotester\PLAY_Strikeforce_AUTOTEST.bat`
  - يفضّل `sfauto\exe_copies\1786_autotest\MyGameRecomp.exe` إن وُجد (حتى تاريخ hooks لم يُبنَ).
  - وإلا `sfauto\exe_copies\1786_movie_v5\MyGameRecomp.exe` (MD5 المعروف في المصادر: `E41A5A94725045155439770EE70087C7`).
- الحالة: `sfauto\state_autotest` (ينسخ من `state_movie1786` إن لزم، كما يفعل `tester.ps1`). لا تستخدم حلقة ringwatch الحية.
- البيئة موجودة في الـ bat: `PAD_FILE=sfauto\autotester\pad.txt`, `SF_MOVIE_LOG=1`, `SF_HLE_LRLOG=1` (قد لا يُنتج v5 أسطر `[hle-lr]` — سجّل ذلك في التغطية، لا تُرقّع البناء في هذا التشغيل إلا إذا كان `1786_autotest` جاهزاً مسبقاً).
- انسخ ملفات البوت الجديدة إلى الجهاز إن لم تكن هناك: `sfauto\autotester\lib\npc_bot.py` و `lib\npc_bot.ps1` (من `/workspace/sf-autotester/lib/`).

## المرحلة والمسار

هدف أول تمرين: **القرية + جمع ذاكرة**، لا فرض عبور بوابة Bandit Trap (نقطة تعليق معروفة).

1. إقلاع. **صفر ضغط** حتى نهاية أفلام البداية. استخدم:
   `replay.ps1 -Seq sfauto\autotester\sequences\boot_to_start.padseq -Log play_logs\autotest_*_stderr.log`
2. لقطة PRESS START. إن القائمة مؤكدة: `menu_cross.padseq` فقط. إن شككت أنها مقطع أو ديمو: لا تضغط.
3. عند استقرار قرية Lou Sang (لعب حر، الحارس idle):
   - لقطة `village_spawn`.
   - `lib\tp_tool.ps1 -mode save-as -Name village_spawn` (أملأ Y/Z؛ لا `goto` بنقطة ناقصة).
   - `lib\tp_tool.ps1 -mode read` مرة ثانية للتثبيت. أرسل الأرقام.
4. (اختياري إن وُجد قتال قصير **قبل البوابة**، مثلاً مدخل Bandit Trap فقط): `godmode.ps1 -mode learn -Seconds 30` أثناء ضربة واحدة على الأقل + لقطة لشريط الصحة. لا `-FullHeap` في أول مرة. لا `mode on`. إن لم يتوفر قتال بأمان، أبقِ التعلّم للاحقاً ولا تدخل البوابة.
5. لا تدخل البوابة ولا تنتظر تعليق التحميل في هذا التشغيل. إن ظهر `SPU-HALT` / شاشة تحميل معلقة / شاشة سوداء: صوّر، أوقف الإدخال، أرسل اللوق. لا تتخطّ.

## إعدادات البوت (Ollama + reflex)

قبل إطلاق اللعبة أو معها على نفس الجهاز:

- تأكد أن Ollama يستمع: `http://127.0.0.1:11434`. أولاً شغّل **`ollama list`** (أو `curl http://127.0.0.1:11434/api/tags`) وأرسل الجدول كاملاً. سعود قال إن نموذج Hermes (Nous Research) مثبّت؛ **الوسم الدقيق VERIFY من هذا الجدول — لا تُخمّنه**.
- الافتراضي لأول تمرين قصير: **`qwen3:14b`**. إن فشل التحميل أو ضاق الـ VRAM: **`qwen3.5:4b`** (ثم `qwen3.5:2b` / `qwen2.5-coder:7b` عند الحاجة). النموذج يُمرَّر بـ **`-Model`** (الخيار موجود في `npc_bot.ps1`).
- بعد استقرار القرية والحارس idle، شغّل (عدّل المسارات حسب نسخ العدّة على الجهاز):

```
powershell -NoProfile -ExecutionPolicy Bypass -File sfauto\autotester\lib\npc_bot.ps1 -LogFile play_logs\<run>_stderr.log -Seconds 120 -Model qwen3:14b -Fallback qwen3.5:4b
```

- البوابة الصلبة داخل البوت: لا ضغط إن فيلم نشط أو الحالة Unsure. إن ارتفع عدّاد القتلى بلا تقدّم في الموضع/المنطقة لـ N ثانية، يوقف القتال وينتقل (كاشف stuck-in-respawn؛ KO ما زال بلا عنوان ذاكرة). في المنطقة الثلجية قرب S (لقطة `/workspace/sf-rec/race_now_1921.png`، 339 Defeated) لا تترك السكربت يقاتل إلى ما لا نهاية — انظر bug_review B-08 (VERIFY: قد يكون تصميم المهمة).
- المدة المقترحة لأول جمع ذاكرة: **120 ثانية** تجوّل في القرية (move/wait). لا تتوقع قتال NPC كاملاً: HP والأعداء غير مؤكدين؛ العصا أمامية/تكتيكية بلا yaw عالمي بعد.
- أثناء عمل اللعبة + Ollama: لقطة `nvidia-smi` (VRAM المستخدمة، وهل النموذج بقي محملاً). هذا بند **VERIFY** على RTX 5080 16GB. إن هبطت اللعبة بقوة بعد تحميل 14b، أوقف البوت وأعد 60 ث بـ `-Model qwen3.5:4b`.

### تشغيل M1 (قرية → بوابة الثلج، وقف قبل الدخول)

بعد خمول الجهاز ونسخة التجربة (`1786_movie_v5` أو `1786_autotest`)، انسخ `/workspace/sf-beta/missions.json` إلى `sfauto\autotester\data\missions.json` إن لم يكن هناك، ونفّذ الإقلاع والقائمة كما فوق حتى تستقر القرية (`save-as village_spawn`). ثم:

```
powershell -NoProfile -ExecutionPolicy Bypass -File sfauto\autotester\lib\npc_bot.ps1 -LogFile play_logs\<run>_stderr.log -Mission M1 -MissionsFile sfauto\autotester\data\missions.json -Model qwen3:14b -Fallback qwen3.5:4b
```

(المهلة من المهمة 480 ث ما لم تمرّر `-Seconds` صراحة.) الهدف: يوصل بوابة فخ قطاع الطرق **ويقف قبل الدخول**. لا يُترك يزرع في منطقة إعادة الظهور قرب S (B-08).

عند التوقف:

- إن ظهر في اللوق `BLUS30471/5443` أو `5444`: هذا شرط تقريبي **VERIFY** (ملفات كاش، انظر PLAN §2.8). لا تكمل المشي. اطلب/التقط لقطة فوراً، و`tp_tool.ps1 -mode save-as -Name bandit_trap_gate_approach` واقرأ XYZ (`0x008D3800`).
- إن ظهر `SPU-HALT` / `0x31C20` / `EventFlagWait BLOCKED`: هذا **فشل/تعليق** لا هدف. لقطة + اللوق، لا تتخطّ.
- إن كتب البوت `SCREENSHOT REQUESTED` أو `goal_met` / `failed` في `npc_bot.jsonl`: نفّذ اللقطة (`shot.ps1`) وأرسل الحدث (المهمة، الوقت Kuwait، السبب).
- حرّر الأزرار (السكربت يفرّغ pad.txt). لا تدخل البوابة في هذا التشغيل.

أرجع: jsonl، ملخص الأحداث، XYZ المحفوظ، اللقطة، مقتطف اللوق (أسطر الكاش/التعليق).

### مقارنة النماذج (bake-off): qwen3:14b مقابل Hermes

بعد `ollama list` وتحديد وسم Hermes الفعلي، كرّر **نفس** سيناريو 120 ثانية مرتين (نفس exe، نفس `state_autotest`، نفس المسار، لا تشغّل النموذجين معاً إن ضاق الـ VRAM):

```
powershell ...\npc_bot.ps1 -LogFile play_logs\<run>_qwen_stderr.log -Seconds 120 -Model qwen3:14b -Fallback qwen3.5:4b
powershell ...\npc_bot.ps1 -LogFile play_logs\<run>_hermes_stderr.log -Seconds 120 -Model <HERMES_TAG_FROM_LIST> -Fallback qwen3.5:4b
```

لكل تشغيل:

```
python sfauto\autotester\lib\npc_bot.py --summarize-events sfauto\autotester\reports\npc_<id>\npc_bot.jsonl
```

أرسل: وسم النموذج، عدد طلبات Ollama، عدد الردود ذات JSON الصالح، النسبة (صالح/الكل)، زمن كل قرار بالمللي ثانية (أو الوسيط/الأقصى إن كثرت)، ونتيجة اللعب (تغيّر XYZ عند `0x008D3800`، هل بُوّبت أفلام، هل أطلق كاشف إعادة الظهور، أين توقف، أي خطأ VRAM). المقارنة الأولى بنفس `format: json` الحالي حتى تكون عادلة. نماذج Hermes (Nous) قد تدعم tool-call بصيغة تختلف حسب الوسم؛ لا نفترضها. إن كانت نسبة JSON على Hermes ضعيفة، أعد الـ 120 ث بـ `--prompt-style hermes` (يوصّله `-PromptStyle hermes` إن وُجد، أو غِير الاستدعاء) — نفس التخطيط، مع طلب JSON خام بلا XML أدوات. اختر الفائز: أعلى نسبة JSON صالح، ثم زمن قرار لا يعطّل الـ reflex، ثم النتيجة داخل اللعبة. إن تعادلا صرّح بالتعادل. لا تكتب نسبة قبل العدّ.

إن Ollama غير جاهز: نفّذ الخطوات 1–4 فقط وأرسل اللوقات، وقل إن البوت لم يُشغَّل.

## ماذا يُلتقط ويُرسل (أرقام ومسارات + لقطات؛ لا تفرّغ القرص كله)

أرجع إلى `/workspace/sf-shared/` (أو ملخص أرقام + مقتطفات إن كانت الملفات ضخمة):

- مسار exe الفعلي وMD5 و`play_logs\autotest_<ts>_stderr.log` + stdout (أو مقتطف: كل أسطر `[sf-movie]`، آخر 80 سطراً، أي `SPU-HALT` / `EventFlagWait`).
- خرج `tp_tool` save-as + read (X/Y/Z).
- إن رُفع learn: ملف `godmode_learn_*.txt` + لقطة الشريط وقت الضربة. لا تملأ `confirmed_hp` إلا إذا تأكدت أنت مع الشريط.
- لقطات PrintWindow (client إن وُجد): `title_start`, `main_menu`, `village_spawn`, وأي فيلم/شاشة سوداء/تعليق، و`movie013` إن ظهر (frames=0 سابقاً).
- `pad_events.jsonl` و`npc_bot.jsonl` وآخر سطر كُتب في `pad.txt`.
- `nvidia-smi` (نص) أثناء اللعبة+Ollama، واسم النموذج الذي اشتغل فعلاً.
- خرج `ollama list` كاملاً، وملخص `--summarize-events` لكل من Qwen وHermes (زمن القرار، JSON الصالح، النتيجة داخل اللعبة)، والفائز أو التعادل.
- إن وُجدت تغطية: `coverage.txt` (حتى لو بلا `[hle-lr]` على v5).
- وقت البداية/النهاية Asia/Kuwait، وpid نافذة الاختبار فقط.

لا تغلق نوافذ لم تبدأها هذه الجلسة.
