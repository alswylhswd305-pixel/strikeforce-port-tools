# Strikeforce PC: bugs Saud found while playing (updated 2026-11-26 16:34, Kuwait time)

## Critical / blocking
1. CRITICAL: every time a new animation triggers, the game freezes completely (Saud, 16:34). Possibly the same root cause as #2 (a job slot whose "done" mark is never written). NOT verified.
2. Freeze in the first battle (snow map), about 1 minute in. Being diagnosed now.

## Graphics / drawing
3. A giant wide shape over the character: it's a character's scarf/cloth stretched huge, covering the screen.
4. The village guard's face isn't seated on his head (flat or detached).
   - Live play 18:24 (build 1650_ovl1): Saud showed the Lou Sang Village guard (arms crossed, silver armor, blue plume). The face area renders as a black hole with only the chin showing; Saud describes the face texture/numbers as sitting outside the body mesh instead of inside it. He wants the face mapped fully inside the head/body. Evidence: freeze-1555/live_1822/guard_crop.jpg, guard_1824_full.jpg, guard_1825_full.jpg. Fix later, needs Saud's approval before any edit. Likely area to check with RenderDoc: the face draw's vertex skinning/bone matrix or its UV/texture binding. Cause NOT verified.
5. Other people's faces don't show.
6. The second weapon looks wrong/glitched when it appears.

7. The ground in Lou Sang Village renders plain white instead of the green grass of the original game (live play 18:24-18:26; evidence guard_1824_full.jpg, look_1826_full.jpg). Saud wants the green ground restored as in the original. Fix later with his approval. Cause not verified.
8. The player's own character's face has the same problem as the guard (live 18:26, build 1650_ovl1): the face shows flat skin with a white patch over the nose and mouth and no eyes; Saud says the face texture sits outside the body mesh instead of inside it. Evidence: live_1822/player_face_1826.jpg, look_1826_full.jpg. Probably the same root cause as #4/#5. Fix later with his approval. Cause not verified.
9. Saud reports faces also have a blue tint / blue 'sad' look (18:25). Not clearly visible in the 18:26 capture (the light-blue next to the face there is the scarf). Needs a closer capture. Fix later with his approval.
10. The blue scarf on Saud's character does not sway or move with physics; it sits stiff on the shoulder (live 18:25-18:26, player_face_1826.jpg). Possibly related to #3 (stretched cloth). Research in progress; no code changes without approval.
11. No character voices or sound effects, only faint ambient audio (Saud, live 18:26, build 1650_ovl1). Evidence: freeze-1555/live_1822/audio_1827_full.jpg; play_logs\fix1650_stderr.log has 231 [cellAtrac] decoder errors so far (162x "Frame data doesn't match channel configuration! ch_block N >= num_channel_blocks N", 41x "Invalid start bit!", 5x "Missing atrac3p feature: Channel unit extension"). Lead (UNVERIFIED): the ATRAC3/ATRAC3+ decode in our cellAtrac HLE fails for voice/SFX streams (wrong channel-block config or wrong data offset), so they come out silent. It may also relate to the mixer job (image 391227015) halt. Saud wants voices and sounds restored. Fix later with his approval.
12. Freeze on the "Now Loading" screen after the village (Saud, live 18:27, build 1650_ovl1, pid 26188). Evidence: freeze-1555/live_1822/freeze_1827_full.jpg. The window still responds and one thread (tid 29112) spins at full CPU, while tid 38884 is BLOCKED in cellSpursEventFlagWait on flag 0x00DBA900. This is the same signature as the mixer-halt freeze (gH/gI/gJ): the audio mixer job, image 391227015, stops at LS 0x31C20 (stderr line 87882), so the flag is never set. It is NOT the main-thread slot freeze (gG/gK). New lead (UNVERIFIED): stderr lines 1185 and 1187 show '[mfc] REJECTED malformed transfer: img=391227015 pc=0x3134C ... size=0'; a rejected DMA could leave the ring-size block at zero. Also possibly linked to #11 (no voices). Fix later with Saud's approval.

## Fixed today
- Black screen after picking a mission (fix1545).
