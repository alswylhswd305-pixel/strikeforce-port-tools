# تصميم بوت NPC — ذاكرة + Ollama محلي + reflex + pad.txt

تاريخ: 2026-11-27 19:19 Asia/Kuwait (UTC+3)، تحديث 19:28 ثم 19:46  
مرتبط من: [PLAN.md](PLAN.md) §1–§2  
الكود: `/workspace/sf-autotester/lib/npc_bot.py`, `lib/npc_bot.ps1` (ملفات جديدة؛ لم تُعدَّل `tester.ps1` / `pad_driver.ps1` / التسلسلات).

## الغرض

تحويل المختبر من ضغطات مكتوبة سلفاً إلى بوت يقرأ موضع اللاعب (ومع الوقت الصحة والأعداء) ويقرر.move/attack/dodge/wait. العقل التكتيكي: **Ollama على جهاز سعود** (`http://127.0.0.1:11434`)، النموذج الأقوى `qwen3:14b`. طبقة reflex سريعة لكل نقرة لأن زمن الـ LLM لا يكفي لحركة الإطار. بوابة الأفلام قاعدة صلبة خارج الـ LLM.

غش النقل/تجميد الصحة للتشخيص فقط. البوت في اللعب العادي يكتب `pad.txt` فقط، ولا يستدعي `goto` إلا في مسار تشخيص منفصل بموافقة التشغيل.

## ما هو معروف (مع الاستشهاد) مقابل المفقود

### معروف — CONFIRMED

| قيمة | أين | دليل |
|---|---|---|
| X/Y/Z للاعب عند `0x008D3800` | `lib/tp_tool.ps1:22`, `data/checkpoints.json:2,13` | اختبار 17:25–17:26: X=6499.8→6799.8، ثبت، الخريطة تغيّرت |
| Y+5 عند التنفيذ | `tp_tool.ps1:85` | نفس `TELEPORT_GO.bat` |
| مرايا موضع اللاعب | `checkpoints.json:4-12` | تتبع اللاعب، ليست قائمة أعداء |
| اكتشاف قاعدة الضيف | `SFAT_VM.cs:51-59` | `R32(0x8487B0)==0xB4` و `R32(0xDB8710)==0x11103500` |
| كشف فيلم PAM | `movie_guard.ps1:48-72` | `[sf-movie] PlayerStart` / `PlayerStop` / `PlayerFinalize`؛ Unsure → لا ضغط |
| صيغة pad.txt | `pad_driver.ps1:142-151` | `0xMASK HOLD [lx ly]` في `sfauto\autotester\pad.txt` |
| أزرار | `lib/buttons.json` + `combat_step.padseq` | SQUARE `0x8000`, TRIANGLE `0x1000`, عصا `0x10000`, START `0x0008`, CROSS `0x4000`؛ أمام `lx=128 ly=0` |

### غير مؤكد / مفقود — لا يُختلق

| قيمة | الحالة | خطة الإيجاد |
|---|---|---|
| صحة اللاعب | `confirmed_hp: []` (`godmode_addrs.json:20`). `hp_hunt` 7814 تناقصاً بلا إثبات. مرشح ضعيف `0x101F0754` (`godmode_addrs.json:13-17`) | `godmode.ps1 -mode learn` أثناء ضربات على نافذة الاختبار؛ تأكيد مرتين مع لقطة الشريط. انظر PLAN §1.2 |
| وقوع / knockdown | `confirmed_knockdown: []` | نفس التعلّم وقت الوقوع (لقطة 23:59 يوم 26) |
| قائمة الأعداء (موضع+HP) | لا ذكر لهيكل في الملفات | مسح قراءة فقط لثلاثيات float تتحرك مع عدو ظاهر. PLAN §1.3 |
| اتجاه اللاعب / الكاميرا | غير موجود | دوران معروف بالعصا + قراءة قرب `0x008D3800`. حتى التأكيد: عصا نسبية فقط |
| علم قائمة / تحميل في الذاكرة | غير موجود | اللوق + اللقطة + عنوان النافذة. VERIFY علامة لاحقاً |
| زر التجنّب | غير مسمّى في العدّة | VERIFY في قتال اختبار (أي زر يُنتج dodge) |
| Y/Z لنقطة القرية | X فقط 6499.8 | `save-as village_spawn` |
| عدّاد القتلى (KO / Defeated) | غير موجود في الذاكرة. ظاهر على الشاشة: «339 Defeated» في `/workspace/sf-rec/race_now_1921.png` | مسح كلمة تزيد مع القتل وتطابق الشاشة (قراءة فقط). PLAN §2.4.1 و§5 |
| اسم/معرّف المنطقة والهدف | غير موجود. اللوق يعطي `Story: Shu Chapter 1` فقط (`saud_blackhang_1817_stderr.log:9613`) ولا يكتب اسم المهمة (`progress.md`) | مسح نصوص + أسطر التحميل + مقارنة عبر النقل. PLAN §5 |

وضع التعلّم موجود في `godmode.ps1` فرع `learn` (قرب xyz افتراضياً؛ `-FullHeap` اختياري). `mode on` يرفض عناوين غير مؤكدة. خطاف `SF_GODMODE` لم يُترجم في هذه الجولة (`hooks/BUILD_NOTES.md`).

## الحلقة (ملخص)

1. المضيف `npc_bot.ps1` (الجهاز فقط): يفتح `[TEST-SALEM]`، يرفض `Saud plays`، يجد القاعدة، يقرأ XYZ (وHP إن تأكدت)، يقرأ ذيل stderr للحارس وأعلام التحميل/الـ halt، يبني state JSON.
2. `npc_bot.py --tick`: إن `movie.active` أو `movie.unsure` → لا ضغط (اكتب pad فارغ) وتوقف عن Ollama لهذا التيك.
3. كل `NPC_TACTIC_SEC` (افتراضي 2.5ث): `POST http://127.0.0.1:11434/api/chat` بالنموذج `qwen3:14b` (أو `OLLAMA_MODEL`)، الحالة المضغوطة، رد JSON `{action,lx,ly,buttons,hold,goal,reason}`. مهلة قصيرة؛ عند الفشل أبقِ آخر تكتيك. إن فشل 14b/VRAM: `OLLAMA_FALLBACK=qwen3.5:4b`.
4. كل تيك (~50–100ms): reflex ينفّذ التكتيك إلى سطر pad. لا حساب عصا من إحداثيات عالمية قبل تأكيد yaw.
5. كاشف **stuck-in-respawn** (خارج الـ LLM): إذا ارتفع عدّاد القتلى ولم يتغيّر الموضع (عند `0x008D3800`) ولا معرّف المنطقة/الهدف لمدة N ثانية، يُلغى `attack`/`dodge` ويُستبدل بـ `move`، ثم الانتقال لخطوة الفحص التالية. `goto` تشخيصي فقط. إن كان KO أو حسّاس التقدّم غير مؤكد، الكاشف لا يطلق. التفاصيل: PLAN §2.4.1.
6. سجّل القرار في `npc_bot.jsonl` (مع زمن قرار Ollama وصلاحية JSON إن وُجد طلب). لا تكتب `ringwatch_work\pad.txt`.

النموذج عبر `-Model` / `--model` (موجود). مقارنة 120ث بين `qwen3:14b` ووسم Hermes بعد `ollama list`: PLAN §2.7 و[run_spec_for_salem.md](run_spec_for_salem.md). أول مقارنة تستخدم `format: json` الحالي؛ صيغة tool-call الخاصة بـ Hermes تُجرَّب فقط إن انخفضت نسبة JSON (`--prompt-style hermes`).

VRAM 16GB مشتركة مع اللعبة: **VERIFY** بـ `nvidia-smi` أثناء التشغيل. انظر PLAN §2.3.

## قيادة بالمهام

`--mission <id>` / `-Mission` يحمّل `/workspace/sf-beta/missions.json`. الهدف يُمرَّر للـ LLM؛ كل تيك يفحص الشرط/الفشل. عند الهدف أو الفشل: pad فارغ، `stop=true`، طلب لقطة، وحدَث عطل إن فشل. بوابة الأفلام وكاشف إعادة الظهور باقيان. الاستخدام بدون `--mission` لم يتغيّر.

M1: القرية → بوابة Bandit Trap، وقف قبل الدخول. XYZ البوابة VERIFY. `BLUS30471/5443-5444` ملفات كاش (route_mission1.json:66؛ اللوقات 17:27 و18:17) — توقف تقريبي VERIFY. التفاصيل في PLAN §2.8.

## ماذا نُفّذ وما اختُبر

- نُفّذ إصدار أول: `lib/npc_bot.py` + `lib/npc_bot.ps1`، مع كاشف stuck-in-respawn و`--summarize-events` و`--prompt-style`.
- اختُبر: `python3 lib/npc_bot.py --selftest` على الصندوق (بوابة، reflex، pad، عميل وهمي، كاشف التعليق، تحميل M1، تحقق هدف/مهلة/فشل). **لم يُختبر على اللعبة ولا على Ollama الحقيقي** (لا نسخة تشغيل ولا جهاز سعود من هنا). سالم يشغّله على نسخة التجربة وفق [run_spec_for_salem.md](run_spec_for_salem.md).
