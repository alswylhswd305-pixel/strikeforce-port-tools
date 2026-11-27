# Copy to env.local.ps1 (git-ignored), edit the paths, then dot-source it:  . .\scripts\env.local.ps1
# Every path points at files YOU own and keep locally. None of them belong in the repo.
$env:SF_ROOT        = "D:\sf-work"                                  # work folder created by setup-work.ps1
$env:SF_ELF         = "D:\sf-private\EBOOT.elf"                     # your decrypted EBOOT (from your own disc, via RPCS3)
$env:SF_DEV_FLASH   = "D:\RPCS3\dev_flash"                          # dev_flash of your RPCS3 with official firmware installed
$env:SF_DISC_SOURCE = "E:\"                                         # your disc dump root (folder with PS3_GAME) or a mounted ISO drive
$env:SF_RPCS3_CACHE = ""                                            # optional: <rpcs3>\cache\BLUS30471\ppu-...-EBOOT.BIN (for sfauto harvest)

# Toolchain (Windows): VS 2022 Build Tools (MSVC), clang-cl (LLVM), CMake, Ninja, Python 3.12.
$env:SF_VCVARS      = "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
$env:SF_TOOL_PATHS  = ""                                            # extra PATH entries (e.g. portable LLVM\bin;cmake\bin;ninja), ';'-separated
