"""ALU opcode tables, transcribed from reference/r700.txt.

Taken from the ALU_INST field enumerations in the microcode-format chapter
(the "0 OP2_INST_ADD, 1 OP2_INST_MUL, ..." lists), not from the per-instruction
reference pages. The two disagree: the NOP page says "opcode 0 (0x0)", which
is ADD's opcode, while the enumeration puts NOP at 26. The enumeration is the
one the shaders agree with -- in binkPixelShader, opcode 0 is the add of the
YUV bias vector, and an assembler would have no reason to emit a NOP there.

115 OP2 and 22 OP3 opcodes is well past the count where a typo stops being
unlikely, and a wrong entry produces a disassembly that is correct everywhere
except one instruction -- the hardest kind of wrong to notice. Regenerate with
the pipeline in blaster/README.md rather than editing by hand.
"""

OP2_INST = {
    0: 'ADD', 1: 'MUL', 2: 'MUL_IEEE', 3: 'MAX', 4: 'MIN', 5: 'MAX_DX10', 6:
    'MIN_DX10', 7: 'FREXP_64', 8: 'SETE', 9: 'SETGT', 10: 'SETGE', 11:
    'SETNE', 12: 'SETE_DX10', 13: 'SETGT_DX10', 14: 'SETGE_DX10', 15:
    'SETNE_DX10', 16: 'FRACT', 17: 'TRUNC', 18: 'CEIL', 19: 'RNDNE', 20:
    'FLOOR', 21: 'MOVA', 22: 'MOVA_FLOOR', 23: 'ADD_64', 24: 'MOVA_INT', 25:
    'MOV', 26: 'NOP', 27: 'MUL_64', 28: 'FLT64_TO_FLT32', 29:
    'FLT32_TO_FLT64', 30: 'PRED_SETGT_UINT', 31: 'PRED_SETGE_UINT', 32:
    'PRED_SETE', 33: 'PRED_SETGT', 34: 'PRED_SETGE', 35: 'PRED_SETNE', 36:
    'PRED_SET_INV', 37: 'PRED_SET_POP', 38: 'PRED_SET_CLR', 39:
    'PRED_SET_RESTORE', 40: 'PRED_SETE_PUSH', 41: 'PRED_SETGT_PUSH', 42:
    'PRED_SETGE_PUSH', 43: 'PRED_SETNE_PUSH', 44: 'KILLE', 45: 'KILLGT', 46:
    'KILLGE', 47: 'KILLNE', 48: 'AND_INT', 49: 'OR_INT', 50: 'XOR_INT', 51:
    'NOT_INT', 52: 'ADD_INT', 53: 'SUB_INT', 54: 'MAX_INT', 55: 'MIN_INT', 56:
    'MAX_UINT', 57: 'MIN_UINT', 58: 'SETE_INT', 59: 'SETGT_INT', 60:
    'SETGE_INT', 61: 'SETNE_INT', 62: 'SETGT_UINT', 63: 'SETGE_UINT', 64:
    'KILLGT_UINT', 65: 'KILLGE_UINT', 66: 'PRED_SETE_INT', 67:
    'PRED_SETGT_INT', 68: 'PRED_SETGE_INT', 69: 'PRED_SETNE_INT', 70:
    'KILLE_INT', 71: 'KILLGT_INT', 72: 'KILLGE_INT', 73: 'KILLNE_INT', 74:
    'PRED_SETE_PUSH_INT', 75: 'PRED_SETGT_PUSH_INT', 76:
    'PRED_SETGE_PUSH_INT', 77: 'PRED_SETNE_PUSH_INT', 78:
    'PRED_SETLT_PUSH_INT', 79: 'PRED_SETLE_PUSH_INT', 80: 'DOT4', 81:
    'DOT4_IEEE', 82: 'CUBE', 83: 'MAX4', 96: 'MOVA_GPR_INT', 97: 'EXP_IEEE',
    98: 'LOG_CLAMPED', 99: 'LOG_IEEE', 100: 'RECIP_CLAMPED', 101: 'RECIP_FF',
    102: 'RECIP_IEEE', 103: 'RECIPSQRT_CLAMPED', 104: 'RECIPSQRT_FF', 105:
    'RECIPSQRT_IEEE', 106: 'SQRT_IEEE', 107: 'FLT_TO_INT', 108: 'INT_TO_FLT',
    109: 'UINT_TO_FLT', 110: 'SIN', 111: 'COS', 112: 'ASHR_INT', 113:
    'LSHR_INT', 114: 'LSHL_INT', 115: 'MULLO_INT', 116: 'MULHI_INT', 117:
    'MULLO_UINT', 118: 'MULHI_UINT', 119: 'RECIP_INT', 120: 'RECIP_UINT', 121:
    'FLT_TO_UINT', 122: 'LDEXP_64', 123: 'FRACT_64', 124: 'PRED_SETGT_64',
    125: 'PRED_SETE_64', 126: 'PRED_SETGE_64'
}

OP3_INST = {
    8: 'MULADD_64', 9: 'MULADD_64_M2', 10: 'MULADD_64_M4', 11: 'MULADD_64_D2',
    12: 'MUL_LIT', 13: 'MUL_LIT_M2', 14: 'MUL_LIT_M4', 15: 'MUL_LIT_D2', 16:
    'MULADD', 17: 'MULADD_M2', 18: 'MULADD_M4', 19: 'MULADD_D2', 20:
    'MULADD_IEEE', 21: 'MULADD_IEEE_M2', 22: 'MULADD_IEEE_M4', 23:
    'MULADD_IEEE_D2', 24: 'CNDE', 25: 'CNDGT', 26: 'CNDGE', 28: 'CNDE_INT',
    29: 'CMNDGT_INT', 30: 'CNDGE_INT'
}
