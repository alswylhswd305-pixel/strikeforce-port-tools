# Salem progress 13:35 (UTC+3)
- RPCS3 0.0.41 reference captures done: sfauto\ref_rpcs3\ref_*.png (title 12:56:06, mainmenu, selectforce, selectchar, movie 13:01:59, instage_start 13:05:01, instage_notut 13:05:12, midstage 13:06:35); box copies /workspace/sf-shots/rpcs3/.
- listing_before/after/diff.tsv in ref_rpcs3. RPCS3 wrote: cache\BLUS30471 (139 PPU objs), dev_hdd1 caches (144), dev_hdd0 savedata BLUS30471-SAVEDATA (3) + trophy NPWR01068_00 (35), $locks, games.yml (BLUS30471 path), GuiConfigs\CurrentSettings.ini (+[GSFrame] visibility=Windowed from Alt+Enter), persistent_settings.dat (playtime), log\RPCS3.log(.gz), TTY.log, RPCS3.buf.
- libsre copied read-only: test copy firmware-local\libsre.sprx SHA1 E8C84FC5298F3B05DF45EA19ED82E97417F9E8C8, fw 04.9300. Decrypt NOT yet run.
- ROOT CAUSE found for missing village/white ground: scene RT 0x0B530000 has zeta offset 0 -> rec_zeta treated as "no depth" -> shared DSV, cleared at each batch start/target switch -> after the VB flush the sky dome overwrote the village. Fix: has_zeta flag + off_ds_find_z (backup .bak_zeta0). Testing play79.
- Diagnostics added (env-gated only): SF_RTLIFE, SF_SAVERT_FLUSH, SF_SWLOG.
