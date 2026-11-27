# Researcher OSK findings (ps3recomp e85647a vs RPCS3 0ca5eb0) — verify against OUR base d81c393
Likely cause (confirmed in code, NOT confirmed as the crash cause):
- On Windows, ps3recomp uses an old stub that rejects cellOskDialogLoadAsync unless cellOskDialogInit was called first. Init isn't a real PS3 function, so the game never calls it.
- So LoadAsync silently returns 0x8002B301 and no events are sent (LOADED 0x502, FINISHED 0x503, UNLOADED 0x504). The native OSK path that sends them only builds on Linux (PS3RECOMP_NATIVE_OSK_HEADLESS).
- Hypothesis: the game calls LoadAsync right after SetLayoutMode/SetInitialKeyLayout, gets the error or waits for an event, then exits.
How to verify:
- Run with PS3_HLE_ARGS=7FCFC915 and look for a [hle-args] nid=0x7FCFC915 line.
- On a non-zero exit, check the [exit-chain] code=.. lr=.. line; on exit 0, add PS3_EXIT_CHAIN=1.
- In RPCS3, look for "sending CELL_SYSUTIL_OSKDIALOG_LOADED".
Behavior bugs in the stub:
- numCharsResultString is the buffer CAPACITY (read it, never write it).
- GetSize should write u16 1,1 (the stub writes u32 640,240).
- Abort should send FINISHED with ABORT.
- Error codes are 0x8002B501..B504; BUSY is 0x8002B105.
- SetLayoutMode(0x2400) and SetInitialKeyLayout(2) are fine.
Missing functions:
- LoadAsyncExt 0xE64582B3, SetDeviceMask 0xD3790A86, DisableDimmer 0x41F20828, SetKeyLayoutOption 0xB53C54FA, AddSupportLanguage 0x7F21C918.
- The 17 cellOskExtUtility (0x003B) functions; the most important is ExtSendFinishMessage 0x42439DB5.
AudioOut reminders:
- GetDeviceInfo: latency u16 at +6; modes at +8; each SoundMode is 8 bytes with layout u32 at +4; total 136; state=1; latency=13.
- GetState: downMixer at +8, soundMode at +12, size 20.
- VideoOutGetState matches.
Fast fix proposal (auto-confirm OSK; sketch is unbuilt and untested):
- LoadAsync doesn't require Init and broadcasts LOADED.
- FINISHED comes on a later cellSysutilCheckCallback poll via cellSysutil_set_osk_pump.
- UnloadAsync writes result=0 and the text as BE UTF-16 (copy min(len, cap)), then broadcasts UNLOADED.
- Text comes from env OSK_AUTO_TEXT, else the game's init_text, else "Saud".
- Expected event order: 0x502, 0x503, 0x504.
(Full C sketch was in the researcher's agent message; reimplement it from the description above against our stub's helpers: GUEST_EA, vm_read32/vm_write16, cellSysutilQueueEvent, s_result_text.)
