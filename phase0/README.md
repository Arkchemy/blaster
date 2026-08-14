# Phase 0: Dumping & Decryption

Turns a legally-owned physical or digital copy of *Skylanders: Spyro's
Adventure* (Wii U) into a decrypted `.rpx` + `.rpl` set the recompiler can
actually work with. Per the project's standing "reuse before rebuilding"
principle, none of this is reimplemented here — it's existing, actively
used homebrew-scene tooling, documented so the workflow is reproducible.

## 1. Dump the game (needs real Wii U hardware)

Can't be automated from a dev sandbox or a script — needs the actual
console. Two tools, pick one depending on whether a raw disc image or an
already-installable dump is wanted:

- **[disc2app](https://www.gamebrew.org/wiki/Disc2app_Wii_U)** — dumps
  straight to installable `.app`/`.h3`/`.tmd`/`.cert`/`.tik` files (skips
  needing a separate "convert raw dump to installable" step). Faster than a
  full disc dump since it only reads what's needed. Needs ~23GB free space
  on the destination SD/USB.
- **WUDD** — dumps a full raw `.wud`/`.wux` disc image instead, if that's
  preferred (e.g. for archival). Needs converting to installable format
  afterward.

Either way, this step happens entirely on-console via the Homebrew
Launcher — see [ConsoleMods: Creating Game Backups](https://consolemods.org/wiki/WiiU:Creating_Game_Backups)
for the current, actively-maintained step-by-step guide (this changes with
Wii U CFW versions faster than it's worth duplicating here).

## 2. Get the Wii U common key

`wiiu_decrypt.py` (below) needs the Wii U common key to decrypt titles —
this is the same key every Wii U uses, publicly documented across the Wii U
homebrew scene for years now (search "Wii U common key" — deliberately not
reproduced in this repo; find it from a scene source, same as the project
plan already assumed). Once you have it, save it as a plain-text hex string
(no `0x` prefix, spaces are fine and get stripped) to:

```
~/.wiiu/common-key
```

`wiiu_decrypt.py` checks its SHA1 hash before doing anything and refuses to
run against a wrong key, so there's no risk of silently decrypting with
garbage.

## 3. Decrypt and extract

[ihaveamac/wiiu-things](https://github.com/ihaveamac/wiiu-things) (MIT
licensed) — run `tools/phase0_setup.sh` once to clone it to
`~/devtools/wiiu-things` and check its one real dependency (the
`cryptography` Python package).

```sh
# From the folder containing your dumped title.tmd, title.tik/cetk, and
# the .app/.h3 content files:
python3 ~/devtools/wiiu-things/wiiu_decrypt.py
python3 ~/devtools/wiiu-things/wiiu_extract.py
```

`wiiu_extract.py` walks the title's FST (file system table) and pulls out
the actual files — this is where the `.rpx` main executable and `.rpl`
shared library dependencies (Phase 1's actual input) end up, alongside the
asset archives (textures/models/audio/GX2 shaders) Phase 4 repackages
untouched.

Useful `wiiu_extract.py` flags: `--dump-info` (print more detail without
extracting), `--full-paths`, `--no-extract` (inspect only).

## What's still manual

Everything above is real, working tooling — but it's still a human running
commands on real hardware and a real terminal, not an automated pipeline.
That automation is explicitly Phase 4's job (the injector/packaging
pipeline), once Phases 1–3 are proven against this specific game — see the
main project plan.
