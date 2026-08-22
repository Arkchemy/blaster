# blaster

Python tools and host-testable C regression tests for the Arkchemy Skylanders
recompiler project. Field-schema extraction, save-format tooling, the Wii→Wii U
audio transplant pipeline, and `verify.sh` — the actual recompiler-correctness
test suite.

## Running `verify.sh`

`verify.sh` predates the org's split into separate repos and still uses paths
that assume it's sitting inside the original monorepo (`recomp/`, `tools/`,
`testdata/` all as siblings under one root). To run it, clone this repo
(`blaster`) and [`conquertron`](https://github.com/Arkchemy/conquertron)
(the recompiler core) as siblings, then symlink or copy `conquertron`'s
contents in as `recomp/` and this repo's own contents in as `tools/`:

```bash
mkdir arkchemy-verify && cd arkchemy-verify
git clone https://github.com/Arkchemy/conquertron recomp
git clone https://github.com/Arkchemy/blaster tools
cp -r tools/testdata .
export ZIG=/path/to/zig
export QEMU_AARCH64=/path/to/qemu-aarch64-static
sh tools/verify.sh
```

`testdata/` needs to sit at the root alongside `recomp/` and `tools/`, not
inside either — it's a real, git-tracked directory in this repo
(`blaster/testdata/`), just referenced by `verify.sh` via a monorepo-relative
path rather than `tools/testdata/`.
