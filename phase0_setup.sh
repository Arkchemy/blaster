#!/bin/sh
# Idempotent setup for Phase 0 (dumping/decryption) tooling. Matches
# tools/setup_toolchain.sh's pattern: fetch and build real, existing tools
# rather than reimplement them (see the project's "reuse before
# rebuilding" principle). Installs under ~/devtools/wiiu-things.
#
# This only sets up the *decrypt/extract* step. Dumping a disc to
# .app/.h3/.tmd/.cert/.tik (or a raw .wud/.wux) has to happen on real Wii U
# hardware via disc2app/WUDD -- see tools/phase0/README.md.
set -e

DEVTOOLS="${DEVTOOLS:-$HOME/devtools}"
mkdir -p "$DEVTOOLS"
cd "$DEVTOOLS"

if [ ! -d wiiu-things ]; then
    echo "== Cloning ihaveamac/wiiu-things (MIT licensed) =="
    git clone --depth 1 https://github.com/ihaveamac/wiiu-things.git
else
    echo "== wiiu-things already cloned =="
fi

echo "== Checking for the 'cryptography' Python package (wiiu_decrypt.py's only real dependency) =="
if python3 -c "import cryptography" 2>/dev/null; then
    echo "   found."
else
    echo "   not found -- install with: pip3 install --user cryptography"
fi

echo "== Checking for the Wii U common key file =="
if [ -f "$HOME/.wiiu/common-key" ]; then
    echo "   found at ~/.wiiu/common-key"
else
    echo "   NOT FOUND. wiiu_decrypt.py requires this at ~/.wiiu/common-key"
    echo "   (a plain-text hex string) before it will run -- see"
    echo "   tools/phase0/README.md for what it is and why this script"
    echo "   deliberately does not supply it for you."
fi

echo "== Done. See tools/phase0/README.md for the full dump -> decrypt -> extract workflow. =="
