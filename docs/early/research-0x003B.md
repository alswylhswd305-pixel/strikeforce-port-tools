# Research note: sysmodule 0x003B and the NULL call at 0x7190

_Read-only research by the research agent (sources: RPCS3 commit 7ad67aa, ps3recomp commit e85647a). The NULL-object hypothesis was later confirmed; the actual cause was the cellVideoOutGetDeviceInfo layout (see fix-log.md)._

Researcher findings (read-only research, verify yourself):
- sysmodule 0x003B = CELL_SYSMODULE_SYSUTIL_OSK_EXT (libsysutil_oskdialog_ext.sprx, lib cellOskExtUtility, 17 funcs cellOskDialogExt*). NIDs: InputDeviceUnlock 0x09565B21, RegisterKeyboardEventHookCallback 0x1E1B4C97, ...Ex 0xBDCF8383, AddJapaneseOptionDictionary 0x23A2EDE6, EnableClipboard 0x40187C25, SendFinishMessage 0x42439DB5, AddOptionDictionary 0x4FE14D09, SetInitialScale 0x75370397, InputDeviceLock 0x7C95FEB8, SetBaseColor 0x7EB292CD, RegisterConfirmWordFilterCallback 0x8692FCD2, UpdateInputText 0x8B60C469, DisableHalfByteKana 0x9CB12C89, SetPointerEnable 0xC5447A90, UpdatePointerDisplayPos 0xD3EA496B, EnableHalfByteKana 0xE6C43C58, RegisterForceFinishCallback 0xE800F586. ps3recomp has no handlers for these. None return pointers -> probably not the direct NULL source.
- NID = first 4 bytes LE of SHA-1(name + suffix 6759659904250490566427499489741A) (RPCS3 PPUModule.cpp). ps3recomp docs/NID_SYSTEM.md is outdated.
- ps3recomp cellSysmoduleLoadModule only marks loaded; doesn't load PRX or patch imports. Unresolved NIDs default fake CELL_OK without writing outputs -> handles stay NULL (docs/DIAGNOSTICS.md#L1415).
- 0x7190 < 0x10000 so likely NOT a real OPD: probably lwz rX,0x7190(rBase) with rBase=0 (unfilled object). Check whether 0x7190 is in any segment of EBOOT.loader.json/image.json; disasm around 0x0007CD38 (tools/show_func.py 0x0007C008 --asm --max 0 or tools/ppu_disasm.py EBOOT.ELF --va 0x0007CC80 --length 0x100), trace origin of rN.
- Run with PS3_HLE_TRACE=400 PS3_CALLTRACE=200 PPU_VCALL_BT=1, collect UNRESOLVED NID lines before crash, lookup with tools/nid_database.py --lookup. PS3_HLE_UNRESOLVED=fail to find the import that matters; PS3_HLE_ARGS=<nid> prints r3-r10.
- Possible: game loads its own USRDIR/*.sprx that wasn't lifted -> empty pointers. Check PS3_GAME/USRDIR/*.sprx.
- v0.20.0 has lwmutex/SPURS/Windows-lock regression fixed in commit 316be1d (PR #847); consider building from master e85647a+.
- Quick paths: PPU_NOOP_BAD_VCALL=1 (diagnostic band-aid), stubs for the 17 OSK funcs (Register* store callbacks), return real errors instead of fake CELL_OK so game takes fallback path, regenerate NID table with gen_hle_nids.py --all.
- RPCS3 side: Log Level=All, grep cellSysmoduleLoadModule/cellOskDialogExt/sys_prx_load_module/.sprx; tools/rpcs3_probe with GDB server 127.0.0.1:2345, break at 0x7CD38 (may need PPU interpreter).
