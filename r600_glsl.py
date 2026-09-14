#!/usr/bin/env python3
"""Translate a decoded R600/R700 shader program into GLSL for deko3d.

This is the step that turns the disassembler into something the port can
actually run. The Switch's GPU cannot execute Latte microcode, so every shader
the Wii U binary hands to GX2 has to become a Maxwell shader. deko3d takes
precompiled `.dksh` modules, and devkitPro ships `uam` to build them from
GLSL -- so GLSL is the target, and `uam` is the thing that says whether the
translation is well-formed.

The translation is deliberately literal. Registers become `vec4`s, ALU slots
become assignments, and the hardware's two implicit registers -- PV (the
previous group's vector result) and PS (its scalar result) -- become ordinary
variables. No attempt is made to reconstruct the original high-level shader:
the output reads like what it is, a transliteration, because a transliteration
can be checked against the disassembly line by line and a reconstruction
cannot.

Three hardware rules drive the shape of the output:

* **An instruction group issues at once.** Every slot in a group reads the
  register file and PV as they were *before* the group. So each slot's result
  goes to a temporary, and the writes to GPRs and PV happen together at the
  end of the group. Emitting the writes inline would be wrong exactly when a
  group reads and writes the same register, which the vertex shaders do.
* **PV is per-channel, PS is scalar.** The four vector units each write their
  own channel of PV; the fifth (trans) unit writes PS.
* **Anything not understood is an error.** An unsupported opcode raises rather
  than emitting something plausible. A shader that silently loses an
  instruction is far more expensive than one that refuses to translate.

    r600_glsl.py <program.bin> [--stage vert|frag] [-o out.glsl]
"""

from __future__ import annotations

import argparse
import sys

from r600 import CHAN, SEL, decode_cf, AluSlot, CfInst, Src

#: Export TYPE, CF_ALLOC_EXPORT_WORD0 [14:13].
EXPORT_PIXEL, EXPORT_POS, EXPORT_PARAM = 0, 1, 2

#: Inline constant source selects that are not registers.
INLINE_CONST = {248: "0.0", 249: "1.0", 250: "1.0", 251: "-1.0", 252: "0.5"}


class Unsupported(Exception):
    """An instruction this translator does not handle.

    Raised rather than worked around. The five shaders in the executable use a
    small corner of the ISA; the honest failure mode for the sixth is a name
    and a slot number, not silently wrong pixels.
    """


# ---------------------------------------------------------------------------
# Opcode semantics.
#
# Each entry takes the already-rendered source expressions and returns a GLSL
# expression. Sources the hardware ignores are not passed: the decoder drops
# src1 for unary opcodes, so `a` here is always a real operand.
# ---------------------------------------------------------------------------

ALU_GLSL = {
    "ADD":            lambda a, b: f"{a} + {b}",
    "MUL":            lambda a, b: f"{a} * {b}",
    "MUL_IEEE":       lambda a, b: f"{a} * {b}",
    "MAX":            lambda a, b: f"max({a}, {b})",
    "MIN":            lambda a, b: f"min({a}, {b})",
    "MAX_DX10":       lambda a, b: f"max({a}, {b})",
    "MIN_DX10":       lambda a, b: f"min({a}, {b})",
    "MOV":            lambda a: a,
    "FRACT":          lambda a: f"fract({a})",
    "FLOOR":          lambda a: f"floor({a})",
    "TRUNC":          lambda a: f"trunc({a})",
    "CEIL":           lambda a: f"ceil({a})",
    "RNDNE":          lambda a: f"roundEven({a})",
    "RECIP_IEEE":     lambda a: f"(1.0 / {a})",
    "RECIP_CLAMPED":  lambda a: f"(1.0 / {a})",
    "RECIP_FF":       lambda a: f"(1.0 / {a})",
    "RECIPSQRT_IEEE": lambda a: f"inversesqrt({a})",
    "RECIPSQRT_CLAMPED": lambda a: f"inversesqrt({a})",
    "RECIPSQRT_FF":   lambda a: f"inversesqrt({a})",
    "SQRT_IEEE":      lambda a: f"sqrt({a})",
    "EXP_IEEE":       lambda a: f"exp2({a})",
    "LOG_IEEE":       lambda a: f"log2({a})",
    "LOG_CLAMPED":    lambda a: f"log2({a})",
    "SETE":           lambda a, b: f"(({a} == {b}) ? 1.0 : 0.0)",
    "SETNE":          lambda a, b: f"(({a} != {b}) ? 1.0 : 0.0)",
    "SETGT":          lambda a, b: f"(({a} > {b}) ? 1.0 : 0.0)",
    "SETGE":          lambda a, b: f"(({a} >= {b}) ? 1.0 : 0.0)",
    "SETE_DX10":      lambda a, b: f"(({a} == {b}) ? 1.0 : 0.0)",
    "SETNE_DX10":     lambda a, b: f"(({a} != {b}) ? 1.0 : 0.0)",
    "SETGT_DX10":     lambda a, b: f"(({a} > {b}) ? 1.0 : 0.0)",
    "SETGE_DX10":     lambda a, b: f"(({a} >= {b}) ? 1.0 : 0.0)",
    # OP3. The conditional moves all test src0 against zero and pick src1 or
    # src2; the _INT forms test the bit pattern as an integer. The M2/M4/D2
    # suffixes are an output modifier baked into the opcode, because OP3 has
    # no OMOD field -- there are no spare bits for one.
    "MULADD":         lambda a, b, c: f"{a} * {b} + {c}",
    "MULADD_IEEE":    lambda a, b, c: f"{a} * {b} + {c}",
    "MULADD_M2":      lambda a, b, c: f"({a} * {b} + {c}) * 2.0",
    "MULADD_M4":      lambda a, b, c: f"({a} * {b} + {c}) * 4.0",
    "MULADD_D2":      lambda a, b, c: f"({a} * {b} + {c}) * 0.5",
    "MULADD_IEEE_M2": lambda a, b, c: f"({a} * {b} + {c}) * 2.0",
    "MULADD_IEEE_M4": lambda a, b, c: f"({a} * {b} + {c}) * 4.0",
    "MULADD_IEEE_D2": lambda a, b, c: f"({a} * {b} + {c}) * 0.5",
    "CNDE":           lambda a, b, c: f"(({a} == 0.0) ? {b} : {c})",
    "CNDGT":          lambda a, b, c: f"(({a} > 0.0) ? {b} : {c})",
    "CNDGE":          lambda a, b, c: f"(({a} >= 0.0) ? {b} : {c})",
    "CNDE_INT":       lambda a, b, c: f"((floatBitsToInt({a}) == 0) ? {b} : {c})",
    "CNDGT_INT":      lambda a, b, c: f"((floatBitsToInt({a}) > 0) ? {b} : {c})",
    # The R700 enumeration spells this one CMNDGT_INT. It is a typo in the
    # document -- there is no such operation -- but the table is generated
    # from the document, so the name is carried rather than quietly fixed.
    "CMNDGT_INT":     lambda a, b, c: f"((floatBitsToInt({a}) > 0) ? {b} : {c})",
    "CNDGE_INT":      lambda a, b, c: f"((floatBitsToInt({a}) >= 0) ? {b} : {c})",
}

#: Reduction opcodes: one result from four slots, not four results.
DOT4 = {"DOT4", "DOT4_IEEE"}

#: Opcodes that legitimately produce nothing.
ALU_NOP = {"NOP"}

#: Predicate-setting opcodes, as GLSL conditions. These do not write a
#: register -- they set the predicate that the following JUMP tests, which is
#: how a compiler spells an `if` on this hardware. The _INT forms compare the
#: raw bit patterns, so they go through floatBitsToInt rather than comparing
#: as floats: a shader that tests a flag packed into a constant register is
#: asking about bits, not about magnitude.
PRED_GLSL = {
    "PRED_SETE":      lambda a, b: f"({a} == {b})",
    "PRED_SETNE":     lambda a, b: f"({a} != {b})",
    "PRED_SETGT":     lambda a, b: f"({a} > {b})",
    "PRED_SETGE":     lambda a, b: f"({a} >= {b})",
    "PRED_SETE_INT":  lambda a, b: f"(floatBitsToInt({a}) == floatBitsToInt({b}))",
    "PRED_SETNE_INT": lambda a, b: f"(floatBitsToInt({a}) != floatBitsToInt({b}))",
    "PRED_SETGT_INT": lambda a, b: f"(floatBitsToInt({a}) > floatBitsToInt({b}))",
    "PRED_SETGE_INT": lambda a, b: f"(floatBitsToInt({a}) >= floatBitsToInt({b}))",
}


class Translator:
    def __init__(self, blob: bytes, name: str = "shader"):
        self.blob = blob
        self.name = name
        self.cf = decode_cf(blob)
        self.gprs: set[int] = set()
        self.consts = -1            # highest constant-file index seen
        self.samplers: set[int] = set()
        self.params: set[int] = set()
        self.stage = self._stage()
        self.inputs = self._inputs()
        # Slot indices restart at zero in every ALU clause, so a temporary
        # named after one is only unique within its clause. Shaders with more
        # than one clause -- every branching shader has at least three --
        # would redeclare it.
        self.clause_id = 0

    # -- stage -------------------------------------------------------------
    def _stage(self) -> str:
        """A program's exports say what it is: positions make it a vertex
        shader, pixels make it a fragment shader. Nothing else needs asking."""
        types = {c.export_type for c in self.cf if c.kind == "export"}
        if EXPORT_POS in types:
            return "vert"
        if EXPORT_PIXEL in types:
            return "frag"
        raise Unsupported(f"{self.name}: no position or pixel export, "
                          "so the stage cannot be determined")

    # -- inputs ------------------------------------------------------------
    def _inputs(self) -> set[int]:
        """Registers the program reads before it writes them.

        Those, and only those, are shader inputs -- attributes for a vertex
        shader, interpolated parameters for a fragment one. Every other
        register the program touches is a scratch it fills itself, which
        matters because compilers here use R123 as a dummy destination for
        results that are only wanted via PV. Declaring that as an input would
        claim a varying at location 123 that nothing ever writes.

        Reads are collected a whole group at a time, because every slot in a
        group reads the register file as it stood before the group ran.
        """
        inputs: set[int] = set()
        written: set[int] = set()

        def read(regs):
            inputs.update(r for r in regs if r not in written)

        for cf in self.cf:
            if cf.kind == "alu":
                group: list[AluSlot] = []
                for sl in cf.alu:
                    group.append(sl)
                    if not sl.last:
                        continue
                    read({s.sel for g in group for s in g.srcs if s.sel < 128})
                    written.update(g.dst_gpr for g in group if g.write)
                    group = []
            elif cf.kind == "clause" and cf.name == "TEX":
                for t in cf.tex:
                    read({t.src_gpr})
                    if any(sel != 7 for sel in t.dst_sel):
                        written.add(t.dst_gpr)
            elif cf.kind == "export":
                read({cf.rw_gpr})
        return inputs

    # -- operands ----------------------------------------------------------
    def src(self, s: Src, literals: tuple) -> str:
        if s.sel < 128:
            self.gprs.add(s.sel)
            expr = f"R{s.sel}.{CHAN[s.chan]}"
        elif s.sel in INLINE_CONST:
            expr = INLINE_CONST[s.sel]
        elif s.sel == 253:
            if s.chan >= len(literals):
                raise Unsupported(f"{self.name}: literal channel "
                                  f"{CHAN[s.chan]} past the group's literals")
            expr = float_literal(literals[s.chan])
        elif s.sel == 254:
            expr = f"PV.{CHAN[s.chan]}"
        elif s.sel == 255:
            expr = "PS"
        elif s.sel >= 256:
            idx = s.sel - 256
            self.consts = max(self.consts, idx)
            expr = f"uf[{idx}].{CHAN[s.chan]}"
        else:
            # 128-159 is the kcache, i.e. uniform *blocks*. Every shader this
            # game binds reports mode 0, which is uniform registers, so seeing
            # one means the assumption broke and the constants would silently
            # come from the wrong place.
            raise Unsupported(f"{self.name}: kcache source {s.sel}; this "
                              "shader uses uniform blocks, not registers")
        if s.abs:
            expr = f"abs({expr})"
        if s.neg:
            expr = f"-({expr})"
        return expr

    # -- ALU ---------------------------------------------------------------
    def alu_clause(self, slots: list[AluSlot], out: list[str]) -> None:
        self.clause_id += 1
        group: list[AluSlot] = []
        for sl in slots:
            group.append(sl)
            if sl.last:
                self.alu_group(group, out)
                group = []
        if group:
            raise Unsupported(f"{self.name}: ALU clause ends mid-group")

    def alu_group(self, group: list[AluSlot], out: list[str]) -> None:
        literals = next((s.literals for s in group if s.literals), ())
        writes: list[str] = []
        out.append(f"    // group {group[0].group}")
        group = self.reduction(group, literals, out, writes)
        for sl in group:
            if sl.name in ALU_NOP:
                continue
            if sl.pred:
                raise Unsupported(f"{self.name}: predicated slot {sl.index} "
                                  f"({sl.name}); no predicate stack is modelled")
            fn = ALU_GLSL.get(sl.name)
            if fn is None:
                raise Unsupported(f"{self.name}: ALU opcode {sl.name} at slot "
                                  f"{sl.index}")
            expr = fn(*[self.src(s, literals) for s in sl.srcs])
            expr = {0: "{}", 1: "({}) * 2.0", 2: "({}) * 4.0",
                    3: "({}) * 0.5"}[sl.omod].format(expr)
            if sl.clamp:
                expr = f"clamp({expr}, 0.0, 1.0)"
            tmp = f"t{self.clause_id}_{sl.index}"
            out.append(f"    float {tmp} = {expr};")
            # The write-back half: PV/PS always, the GPR only if WRITE_MASK.
            writes.append(f"PS = {tmp};" if sl.trans
                          else f"PV.{CHAN[sl.dst_chan]} = {tmp};")
            if sl.write:
                self.gprs.add(sl.dst_gpr)
                writes.append(f"R{sl.dst_gpr}.{CHAN[sl.dst_chan]} = {tmp};")
        if writes:
            out.append("    " + " ".join(writes))

    def reduction(self, group: list[AluSlot], literals: tuple,
                  out: list[str], writes: list[str]) -> list[AluSlot]:
        """Fold a DOT4 group into one expression, returning the other slots.

        A dot product is not four instructions that each produce a value: it
        is one reduction spread across the four vector units, each slot
        carrying one pair of components. The doc is explicit that only PV.x
        holds the result. Treating the slots as independent multiplies would
        produce four unrelated numbers and a shader that renders nothing
        recognisable -- which is why this is folded before the ordinary
        per-slot path runs.
        """
        dots = [sl for sl in group if sl.name in DOT4]
        if not dots:
            return group
        if len(dots) != 4:
            raise Unsupported(f"{self.name}: DOT4 across {len(dots)} slots, "
                              "not 4; the reduction must cover all elements")
        a = ", ".join(self.src(sl.srcs[0], literals) for sl in dots)
        b = ", ".join(self.src(sl.srcs[1], literals) for sl in dots)
        expr = f"dot(vec4({a}), vec4({b}))"
        # OMOD and CLAMP are required to be identical across the four slots,
        # so either is the group's.
        expr = {0: "{}", 1: "({}) * 2.0", 2: "({}) * 4.0",
                3: "({}) * 0.5"}[dots[0].omod].format(expr)
        if dots[0].clamp:
            expr = f"clamp({expr}, 0.0, 1.0)"
        tmp = f"d{self.clause_id}_{dots[0].index}"
        out.append(f"    float {tmp} = {expr};")
        writes.append(f"PV.x = {tmp};")
        for sl in dots:
            if sl.write:
                self.gprs.add(sl.dst_gpr)
                writes.append(f"R{sl.dst_gpr}.{CHAN[sl.dst_chan]} = {tmp};")
        return [sl for sl in group if sl.name not in DOT4]

    # -- TEX ---------------------------------------------------------------
    def tex_clause(self, insts, out: list[str]) -> None:
        self.clause_id += 1
        for t in insts:
            if not t.name.startswith("SAMPLE"):
                raise Unsupported(f"{self.name}: texture op {t.name}")
            if t.name not in ("SAMPLE", "SAMPLE_LZ"):
                raise Unsupported(f"{self.name}: texture op {t.name} needs an "
                                  "explicit LOD or gradient argument")
            self.samplers.add(t.resource)
            self.gprs.add(t.src_gpr)
            self.gprs.add(t.dst_gpr)
            coord = ", ".join(self.coord(t.src_gpr, c) for c in t.src_sel[:2])
            fetch = "texture" if t.name == "SAMPLE" else "textureLod"
            tail = ", 0.0" if fetch == "textureLod" else ""
            sample = f"s{self.clause_id}_{t.index}"
            out.append(f"    vec4 {sample} = {fetch}(tex{t.resource}, "
                       f"vec2({coord}){tail});")
            for i, sel in enumerate(t.dst_sel):
                if sel == 7:            # SEL_MASK: this channel is not written
                    continue
                src = {4: "0.0", 5: "1.0"}.get(sel, f"{sample}.{SEL.get(sel)}")
                out.append(f"    R{t.dst_gpr}.{CHAN[i]} = {src};")

    def coord(self, gpr: int, sel: int) -> str:
        if sel in (4, 5):
            return "0.0" if sel == 4 else "1.0"
        if sel == 7:
            raise Unsupported(f"{self.name}: masked texture coordinate")
        return f"R{gpr}.{SEL[sel]}"

    # -- exports -----------------------------------------------------------
    def export(self, cf: CfInst, out: list[str]) -> None:
        self.gprs.add(cf.rw_gpr)
        parts = []
        for sel in cf.swiz:
            if sel in (4, 5):
                parts.append("0.0" if sel == 4 else "1.0")
            elif sel == 7:
                parts.append("0.0")     # masked: nothing drives it
            else:
                parts.append(f"R{cf.rw_gpr}.{SEL[sel]}")
        value = f"vec4({', '.join(parts)})"

        if cf.export_type == EXPORT_POS:
            # ARRAY_BASE 60 is position 0; 61-63 are the clip-distance and
            # point-size slots, which nothing here uses.
            if cf.array_base != 60:
                raise Unsupported(f"{self.name}: position export to array "
                                  f"base {cf.array_base}")
            out.append(f"    gl_Position = {value};")
        elif cf.export_type == EXPORT_PARAM:
            self.params.add(cf.array_base)
            out.append(f"    param{cf.array_base} = {value};")
        elif cf.export_type == EXPORT_PIXEL:
            if cf.array_base != 0:
                raise Unsupported(f"{self.name}: pixel export to render "
                                  f"target {cf.array_base}")
            out.append(f"    color0 = {value};")
        else:
            raise Unsupported(f"{self.name}: export type {cf.export_type}")

    # -- control flow ------------------------------------------------------
    def predicate(self, cf: CfInst) -> str:
        """The condition an ALU_PUSH_BEFORE clause leaves on the stack."""
        sets = [sl for sl in cf.alu if sl.name in PRED_GLSL]
        if len(sets) != 1 or len(cf.alu) != len(sets):
            raise Unsupported(f"{self.name}: CF {cf.index} pushes a predicate "
                              "from a clause that is not a single PRED_SET")
        sl = sets[0]
        return PRED_GLSL[sl.name](*[self.src(s, sl.literals) for s in sl.srcs])

    def emit(self, lo: int, hi: int, out: list[str], depth: int = 1) -> None:
        """Emit CF instructions [lo, hi), rebuilding branches as if/else.

        The hardware has no if: a compiler spells one as PUSH a predicate,
        JUMP past the taken side, ELSE, POP. Only that exact shape is
        reconstructed. Loops, breaks and nested pushes raise instead, because
        an if/else is verifiable by eye against the disassembly and a general
        structurizer guessing at the stack is not.
        """
        pad = "    " * depth
        i = lo
        while i < hi:
            cf = self.cf[i]
            if cf.name == "ALU_PUSH_BEFORE":
                jump = self.cf[i + 1] if i + 1 < hi else None
                if jump is None or jump.name != "JUMP":
                    raise Unsupported(f"{self.name}: CF {cf.index} pushes a "
                                      "predicate that no JUMP consumes")
                cond = self.predicate(cf)
                target = jump.addr // 8          # ADDR counts CF slots
                els = self.cf[target] if target < len(self.cf) else None
                out.append(f"{pad}if {cond} {{")
                if els is not None and els.name == "ELSE":
                    self.emit(i + 2, target, out, depth + 1)
                    out.append(f"{pad}}} else {{")
                    end = els.addr // 8
                    self.emit(target + 1, end, out, depth + 1)
                    out.append(f"{pad}}}")
                    i = end
                else:
                    self.emit(i + 2, target, out, depth + 1)
                    out.append(f"{pad}}}")
                    i = target
                continue
            self.emit_one(cf, out, pad)
            i += 1

    def emit_one(self, cf: CfInst, out: list[str], pad: str) -> None:
        body: list[str] = []
        if cf.kind == "alu":
            self.alu_clause(cf.alu, body)
        elif cf.kind == "clause" and cf.name == "TEX":
            self.tex_clause(cf.tex, body)
        elif cf.kind == "export":
            self.export(cf, body)
        elif cf.name in ("CALL_FS", "NOP", "POP"):
            # CALL_FS runs the fetch shader, which on deko3d is declarative
            # vertex-attribute state rather than code -- the attributes are
            # already in the input registers by the time main() starts. POP
            # only unwinds the stack that emit() has already structured away.
            return
        else:
            raise Unsupported(f"{self.name}: control flow {cf.name} at "
                              f"CF {cf.index}")
        out.extend(pad[4:] + line for line in body)

    # -- whole program -----------------------------------------------------
    def translate(self) -> str:
        body: list[str] = []
        self.emit(0, len(self.cf), body)
        return self.assemble(body)

    def assemble(self, body: list[str]) -> str:
        out = ["#version 460", ""]
        out.append(f"// Translated from {self.name} by blaster/r600_glsl.py.")
        out.append("// Transliterated from Latte microcode -- see r600.py"
                   " --cf for the source.")
        out.append("")

        if self.stage == "vert":
            # The fetch shader loads attribute N into GPR N+1; GPR 0 holds the
            # vertex index. That is the layout every vertex shader in this
            # game's executable reads, and it is the one thing here taken from
            # the shape of the code rather than from a field: the attribute
            # streams handed to GX2InitFetchShaderEx are the real authority,
            # and this has to be re-checked against them per shader.
            for r in sorted(self.inputs):
                if r == 0:
                    raise Unsupported(f"{self.name}: vertex shader reads R0, "
                                      "which holds the vertex index, not an "
                                      "attribute")
                out.append(f"layout (location = {r - 1}) in vec4 attr{r - 1};")
            for p in sorted(self.params):
                out.append(f"layout (location = {p}) out vec4 param{p};")
        else:
            for r in sorted(self.inputs):
                out.append(f"layout (location = {r}) in vec4 param{r};")
            out.append("layout (location = 0) out vec4 color0;")
        out.append("")

        if self.consts >= 0:
            out.append("// GX2SetVertexUniformReg / GX2SetPixelUniformReg write")
            out.append("// the constant file; every shader this game binds")
            out.append("// reports mode 0, so these are registers, not blocks.")
            out.append("layout (std140, binding = 0) uniform Constants {")
            out.append(f"    vec4 uf[{self.consts + 1}];")
            out.append("};")
            out.append("")
        for s in sorted(self.samplers):
            out.append(f"layout (binding = {s}) uniform sampler2D tex{s};")
        if self.samplers:
            out.append("")

        out.append("void main()")
        out.append("{")
        for r in sorted(self.gprs):
            if r not in self.inputs:
                init = "vec4(0.0)"
            elif self.stage == "vert":
                init = f"attr{r - 1}"
            else:
                init = f"param{r}"
            out.append(f"    vec4 R{r} = {init};")
        out.append("    vec4 PV = vec4(0.0);")
        out.append("    float PS = 0.0;")
        out.append("")
        out.extend(body)
        out.append("}")
        return "\n".join(out) + "\n"


def float_literal(word: int) -> str:
    import struct
    f = struct.unpack("<f", struct.pack("<I", word))[0]
    return repr(f)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("program")
    ap.add_argument("-o", "--out", help="write GLSL here instead of stdout")
    ap.add_argument("--print-stage", action="store_true",
                    help="print only the pipeline stage uam should be given")
    args = ap.parse_args()

    import os
    blob = open(args.program, "rb").read()
    t = Translator(blob, os.path.basename(args.program).split(".")[0])
    if args.print_stage:
        print(t.stage)
        return 0
    try:
        glsl = t.translate()
    except Unsupported as e:
        print(f"cannot translate: {e}", file=sys.stderr)
        return 1
    if args.out:
        open(args.out, "w").write(glsl)
        print(f"{t.stage}\t{args.out}")
    else:
        sys.stdout.write(glsl)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
