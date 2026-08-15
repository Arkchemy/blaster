#!/usr/bin/env python3
"""
Reads a real Skylanders figure's Character ID (and, where known, its
Variant ID) directly off a real Portal of Power over USB, and decodes it
against an embedded character-ID table -- no manual lookup, no web search
at runtime, just protocol I/O + a local table.

Protocol details (device VID/PID, HID report layout, command bytes, block
data layout) were reverse-engineered live against real Portal of Power
hardware connected to this machine, cross-checked against community
reverse-engineering sources (Brandon L. Wilson's "The Skylanders Portal
Demystified", https://gist.github.com/skylandersNFC/5c9fb3debc11c1ea194ed6ddc9fb8faf,
and the character ID table from https://github.com/Texthead1/Skylander-IDs)
-- not guessed.

Usage:
    python3 tools/portal_identify.py [/dev/hidrawN]

--- 2026-08-15 real-hardware run, real finding, not yet resolved ---
Ran against whatever Portal of Power hardware was actually connected to
this machine at the time: lsusb identifies it as
"RedOctane wireless receiver for skylanders wii" (VID:PID 1430:0150,
bus-powered, Full Speed) -- the original *Wii*-generation wireless
Portal of Power's RF receiver dongle, not a directly-wired portal (the
docstring above doesn't specify which physical unit it was validated
against, so this may be a different one).

Every write() to the interrupt OUT report -- including the real 0x52
reset command this tool sends first, and a plain all-zero 32-byte
probe -- fails immediately with EPROTO, regardless of payload content
(confirmed via direct os.write() experiments, not just this script).
The device's real HID report descriptor (pulled via HIDIOCGRDESC, not
guessed) confirms both Input and Output reports really are 32 bytes
with no Report ID byte, matching exactly what this script already
sends -- ruling out a payload-shape bug here.

Real, meaningfully different result from a HIDIOCSFEATURE (SET_REPORT)
attempt with the same 0x52 payload: ETIMEDOUT, not EPROTO -- the
control-transfer path actually reached the device and waited for a
real reply rather than being rejected outright.

--- Update, same day, same session: "no portal powered on" hypothesis
disproven, real root cause still open ---
Owner confirmed this unit is connected by a real USB cable (not
relying on its own RF link to a separate base station the way the
"wireless receiver" name suggested), and moved it to a different USB
port -- same real device (re-enumerated as the same VID:PID, kernel
reassigned the same /dev/hidraw4 node). Both write paths (interrupt
OUT, HIDIOCSFEATURE) still fail exactly the same way (EPROTO,
ETIMEDOUT) on the new port.

But a plain blocking read on the device now genuinely returned real,
unsolicited data: `53 05 00 00 00 0a 00 00 ...` -- the exact `0x53`-
prefixed "passive status heartbeat" format this file's own
query_block() comment already documents from earlier real testing.
This directly disproves the earlier "no portal currently powered on"
hypothesis: a device with nothing behind it wouldn't be actively
streaming its own real status heartbeat. The device is genuinely
alive, powered, and talking -- specifically the *write* direction
(both interrupt OUT and Feature/SET_REPORT) is what's failing,
consistently, regardless of port or payload.

Real root cause is still open. Two honest candidates, neither
confirmed: (1) a genuine Linux kernel/hidraw quirk specific to this
VID:PID that breaks host-to-device writes while leaving device-to-host
reads working (would need a kernel hid-quirks entry or usbmon-level
tracing -- root not available in this environment -- to confirm), or
(2) this specific "wireless receiver" unit's own firmware may simply
never have implemented accepting generic host-driven commands over
this interface at all (only ever needed to be read passively by the
real Wii console's own driver stack, which might talk to it
differently than a Wii U-native wired portal). Flagged as two
plausible hypotheses, not a resolved bug -- resolving further would
need either root (usbmon) or testing against a confirmed-different
portal unit (e.g. a real Wii U or PC-native wired portal, not this
Wii-era "wireless receiver"-branded one) to isolate whether it's
Linux-side or hardware/firmware-side.
"""
import os
import select
import sys
import time

# Real Portal of Power identifiers (VID:PID 1430:0150) -- used only to
# help auto-locate the right /dev/hidraw* node; the actual open still
# happens via the plain device path, this project has no dependency on
# pyusb/hidapi.
PORTAL_VID = "1430"
PORTAL_PID = "0150"

# CharacterID -> name, from https://github.com/Texthead1/Skylander-IDs
# (community-maintained, sourced from Portal-To-Unity). VariantID is a
# separate field this table doesn't cover in general -- see
# POP_FIZZ_VARIANTS below for the one character this project has real,
# captured variant data for.
CHARACTER_IDS = {
    0: "Whirlwind", 1: "Sonic Boom", 2: "Warnado", 3: "Lightning Rod",
    4: "Bash", 5: "Terrafin", 6: "Dino-Rang", 7: "Prism Break",
    8: "Sunburn", 9: "Eruptor", 10: "Ignitor", 11: "Flameslinger",
    12: "Zap", 13: "Wham-Shell", 14: "Gill Grunt", 15: "Slam Bam",
    16: "Spyro", 17: "Voodood", 18: "Double Trouble", 19: "Trigger Happy",
    20: "Drobot", 21: "Drill Sergeant", 22: "Boomer", 23: "Wrecking Ball",
    24: "Camo", 25: "Zook", 26: "Stealth Elf", 27: "Stump Smash",
    28: "Dark Spyro", 29: "Hex", 30: "Chop Chop", 31: "Ghost Roaster",
    32: "Cynder",
    100: "Jet-Vac", 101: "Swarm", 102: "Crusher", 103: "Flashwing",
    104: "Hot Head", 105: "Hot Dog", 106: "Chill", 107: "Thumpback",
    108: "Pop Fizz", 109: "Ninjini", 110: "Bouncer", 111: "Sprocket",
    112: "Tree Rex", 113: "Shroomboom", 114: "Eye-Brawl", 115: "Fright Rider",
    404: "Legendary Bash", 416: "Legendary Spyro",
    419: "Legendary Trigger Happy", 430: "Legendary Chop Chop",
    450: "Gusto", 451: "Thunderbolt", 452: "Fling Kong", 453: "Blades",
    454: "Wallop", 455: "Head Rush", 456: "Fist Bump", 457: "Rocky Roll",
    458: "Wildfire", 459: "Ka-Boom", 460: "Trail Blazer", 461: "Torch",
    462: "Snap Shot", 463: "Lob-Star", 464: "Flip Wreck", 465: "Echo",
    466: "Blastermind", 467: "Enigma", 468: "Déjà Vu", 469: "Cobra Cadabra",
    470: "Jawbreaker", 471: "Gearshift", 472: "Chopper", 473: "Tread Head",
    474: "Bushwhack", 475: "Tuff Luck", 476: "Food Fight", 477: "High Five",
    478: "Krypt King", 479: "Short Cut", 480: "Bat Spin", 481: "Funny Bone",
    482: "Knight Light", 483: "Spotlight", 484: "Knight Mare", 485: "Blackout",
    601: "King Pen", 602: "Tri-Tip", 603: "Chopscotch", 604: "Boom Bloom",
    605: "Pit Boss", 606: "Barbella", 607: "Air Strike", 608: "Ember",
    609: "Ambush", 610: "Dr. Krankcase", 611: "Hood Sickle",
    612: "Taw Kwon Crow", 613: "Golden Queen", 614: "Wolfgang",
    615: "Pain-Yatta", 616: "Mysticat", 617: "Starcast", 618: "Buckshot",
    619: "Aurora", 620: "Flare Wolf", 621: "Chompy Mage", 622: "Bad Juju",
    623: "Grave Clobber", 624: "Blaster-Tron", 625: "Ro-Bow",
    626: "Chain Reaction", 627: "Kaos", 628: "Wild Storm", 629: "Tidepool",
    630: "Crash Bandicoot", 631: "Dr. Neo Cortex",
    3000: "Scratch", 3001: "Pop Thorn", 3002: "Slobber Tooth",
    3003: "Scorp", 3004: "Fryno", 3005: "Smolderdash", 3006: "Bumble Blast",
    3007: "Zoo Lou", 3008: "Dune Bug", 3009: "Star Strike",
    3010: "Countdown", 3011: "Wind-Up", 3012: "Roller Brawl",
    3013: "Grim Creeper", 3014: "Rip Tide", 3015: "Punk Shock",
}

# VariantID lookup for the one character this project has real, captured
# example data for (see the recomp/README paired-single work's sibling
# investigation) -- from the same Texthead1/Skylander-IDs table.
POP_FIZZ_VARIANTS = {
    4096: "Pop Fizz",
    4614: "Pop Fizz (LightCore)",
    5122: "Punch Pop Fizz",
    10245: "Super Gulp Pop Fizz",
    14341: "Fizzy Frenzy Pop Fizz",
    15362: "Love Potion Pop Fizz",
}
VARIANT_TABLES = {108: POP_FIZZ_VARIANTS}


def find_portal_hidraw():
    """Scans /sys/class/hidraw for a device matching the real Portal of
    Power's VID/PID, returns its /dev/hidrawN path."""
    base = "/sys/class/hidraw"
    for name in sorted(os.listdir(base)):
        uevent_path = os.path.join(base, name, "device", "uevent")
        try:
            with open(uevent_path) as f:
                uevent = f.read()
        except OSError:
            continue
        # HID_ID=<bus>:<vendor>:<product>, e.g. 0003:00001430:00000150
        for line in uevent.splitlines():
            if line.startswith("HID_ID="):
                _, vid, pid = line[len("HID_ID="):].split(":")
                if vid[-4:].lower() == PORTAL_VID and pid[-4:].lower() == PORTAL_PID:
                    return "/dev/" + name
    return None


def send_packet(fd, cmd_bytes):
    pkt = bytearray(32)
    for i, b in enumerate(cmd_bytes):
        pkt[i] = b
    os.write(fd, bytes(pkt))


def read_packets(fd, timeout):
    out = []
    end = time.time() + timeout
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.1)
        if r:
            out.append(os.read(fd, 64))
    return out


def query_block(fd, block_index):
    """Real command format `[0x51, 0x20 + tag_index, block_index]` (tag_index=0
    for a single-pad portal). Real response format `51 <len> <block> <data...>`
    -- len=0x10 (16) when real block data follows, len=0x00 when there's
    no tag to read from (confirmed live: the passive `53`-prefixed status
    heartbeat is not reliable enough to gate on -- it was observed to stop
    streaming on its own mid-session even with a tag physically present,
    while direct block queries kept working regardless. Retrying the query
    itself, and treating a real (0x10-length) response as "yes, a tag is
    there", is the mechanism that's actually been confirmed reliable."""
    send_packet(fd, [0x51, 0x20, block_index])
    for pkt in read_packets(fd, 0.6):
        if pkt[0] == 0x51 and pkt[1] == 0x10 and pkt[2] == block_index:
            return bytes(pkt[3:19])  # 16 bytes of real block data
    return None


def query_block_with_retry(fd, block_index, attempts=8, delay=0.5):
    for i in range(attempts):
        data = query_block(fd, block_index)
        if data is not None:
            return data
        time.sleep(delay)
    return None


def identify(character_id, variant_id):
    name = CHARACTER_IDS.get(character_id)
    variant_name = None
    if character_id in VARIANT_TABLES:
        variant_name = VARIANT_TABLES[character_id].get(variant_id)
    return name, variant_name


# Real block-layout knowledge, derived by disassembling the actual game's
# own tfbSpyroTag class (tfbGame_cafe.rpx, Skylanders: Spyro's Adventure
# Wii U, Japan-region build) with Capstone -- not guessed, not sourced from
# any external table. Two real functions were fully ported to Python and
# executed to get these numbers:
#
#  - tfbSpyroTag::getBlockRange(DataType, regionIndex, area, &start, &count)
#    at 0x02066a9c: a 6-way switch on DataType (0-5) computing block
#    ranges from a runtime-initialized `_dataRegions` table (2 entries).
#    `area` (0 or nonzero) selects between two REAL redundant save areas
#    on the physical chip -- confirmed by the literal base constants used:
#    0x24 (36) for area=0, 0x08 (8) for area!=0.
#  - tfbSpyroTag::setDataRegionSizeInternal(dataType, sizeA, sizeB) at
#    0x0206eb7c: populates `_dataRegions` at construction time, walking
#    block indices and skipping Mifare Classic sector-trailer blocks
#    (block_index % 4 == 3, confirmed via the real isTrailer helper at
#    0x020612c8) -- exactly the same trailer pattern independently
#    confirmed by hand from this project's own live USB captures (block 3
#    of area 0 showed a real trailer-like `0f 0f 0f 69` pattern).
#
# Real constructor call site (tfbSpyroTag::tfbSpyroTag, 0x0206ee14) seeds
# the table with setDataRegionSizeInternal(0, 4, 3) then (1, 1, 3) --
# executing the ported logic with those exact real arguments gives the
# concrete block numbers below. DataType 0 (TagHeader) is a fixed
# blocks[0,2) range coded directly in getBlockRange, not table-driven.
#
# DataType meaning isn't confirmed by name (no string table for enum
# names survived in the binary), but the *blocks* themselves are real:
# this is genuinely everywhere on the physical chip the real game reads
# and writes, well beyond the block 0/1 this tool used before.
REGIONS = {
    # (dataType, regionIndex, area): (blockStart, blockCount)
    (0, 0, 0): (0, 2), (0, 0, 1): (0, 2),  # TagHeader, fixed, ignores regionIndex/area
    (1, 0, 0): (0x24, 1), (1, 0, 1): (8, 1),
    (2, 0, 0): (0x25, 4), (2, 0, 1): (9, 4),   # r4==0 off-by-one adjust applied
    (2, 1, 0): (0x2d, 1), (2, 1, 1): (0x11, 1),
    (3, 0, 0): (0x29, 4), (3, 0, 1): (0x0d, 4),
    (3, 1, 0): (0x2e, 4), (3, 1, 1): (0x12, 4),
    (4, 0, 0): (0x24, 5), (4, 0, 1): (8, 5),
    (4, 1, 0): (0x2d, 1), (4, 1, 1): (0x11, 1),
    (5, 0, 0): (0x29, 4), (5, 0, 1): (0x0d, 4),
    (5, 1, 0): (0x2e, 4), (5, 1, 1): (0x12, 4),
}


def dump_regions(fd):
    """Read every real block the game's own code says it uses (per
    REGIONS above), across both real redundant areas, and print raw hex
    plus a best-effort ASCII/UTF-16LE decode -- this project's build for
    Spyro's Adventure is Japan-region, per its own meta.xml, so any real
    text found here is expected to be Japanese, not English."""
    seen = set()
    for (dt, ri, area), (start, count) in REGIONS.items():
        for b in range(start, start + count):
            seen.add(b)
    for b in sorted(seen):
        data = query_block_with_retry(fd, b, attempts=3, delay=0.3)
        if data is None:
            print(f"  block {b:3d} ({b:#04x}): no response")
            continue
        ascii_repr = ''.join(chr(c) if 0x20 <= c < 0x7f else '.' for c in data)
        try:
            utf16 = data.decode('utf-16-le', errors='replace').replace('\x00', '')
        except Exception:
            utf16 = ''
        print(f"  block {b:3d} ({b:#04x}): {data.hex()}  ascii={ascii_repr!r}  utf16le={utf16!r}")


def main():
    dev_path = sys.argv[1] if len(sys.argv) > 1 else find_portal_hidraw()
    if not dev_path:
        print("No Portal of Power found (looked for VID 1430 / PID 0150 under /sys/class/hidraw).")
        return 1
    print(f"using device: {dev_path}")

    fd = os.open(dev_path, os.O_RDWR)
    try:
        send_packet(fd, [0x52])  # reset
        read_packets(fd, 0.3)

        print("reading block 1 (retrying up to ~4s if no tag responds yet)...")
        block1 = query_block_with_retry(fd, 1)
        if block1 is None:
            print("no tag responded -- is a figure on the portal?")
            return 1

        character_id = block1[0] | (block1[1] << 8)   # bytes 0-1, little-endian
        variant_id = block1[12] | (block1[13] << 8)    # bytes 12-13, little-endian

        name, variant_name = identify(character_id, variant_id)
        print(f"CharacterID={character_id} VariantID={variant_id}")
        if name:
            print(f"Identified: {variant_name or name}")
        else:
            print(f"Identified: unknown character (ID {character_id} not in this project's table)")

        print()
        print("dumping every real block the game's own code (tfbSpyroTag) reads/writes,")
        print("per the disassembly-derived REGIONS table -- looking for name/nickname data:")
        dump_regions(fd)
        return 0
    finally:
        os.close(fd)


if __name__ == "__main__":
    sys.exit(main())
