# Structural signature dumper for pyc files. Runs on Python 2.x and 3.x.
# Prints one repr-tuple per line: code object headers and instruction
# (opname, argrepr) pairs with addresses/line info normalized away.
#
# Usage: <interp> sig_dump.py <file.pyc>
import marshal
import sys
import types

PY2 = sys.version_info[0] == 2


def header_size(data):
    magic = ord(data[0]) + ord(data[1]) * 256 if PY2 else data[0] + data[1] * 256
    if magic < 4000:
        # 3.x series
        if magic >= 3390:
            return 16
        if magic >= 3200:
            return 12
        return 8
    return 8  # 1.x / 2.x


def byte_at(s, i):
    return ord(s[i]) if isinstance(s, str) else s[i]


def describe2(code, op, arg, label):
    import opcode
    if op in opcode.hasconst:
        try:
            c = code.co_consts[arg]
            if isinstance(c, types.CodeType):
                # the raw repr carries a memory address and the build
                # path - normalize like sig3 does so an original pyc and
                # a recompiled pyc compare equal (the nested code's own
                # instructions are dumped recursively below anyway)
                return "<code %s>" % c.co_name
            return repr(c)[:60]
        except Exception:
            return "<const>"
    if op in opcode.hasname:
        return str(code.co_names[arg])
    if op in opcode.haslocal:
        return str(code.co_varnames[arg])
    if op in opcode.hasfree:
        names = code.co_cellvars + code.co_freevars
        return str(names[arg])
    if op in opcode.hasjrel or op in opcode.hasjabs:
        return label
    return str(arg)


def sig2(code, out):
    import opcode
    out.append((code.co_name, code.co_argcount))
    bc = code.co_code
    n = len(bc)
    # first pass: instruction boundaries
    bounds = []
    i = 0
    while i < n:
        op = byte_at(bc, i)
        start = i
        i += 1
        if op >= opcode.HAVE_ARGUMENT:
            i += 2
        bounds.append((start, i, op))
    off2idx = dict((b[0], k) for k, b in enumerate(bounds))
    # second pass: emit with jump labels = target instruction index
    for k, (start, end, op) in enumerate(bounds):
        name = opcode.opname[op]
        if op >= opcode.HAVE_ARGUMENT:
            arg = byte_at(bc, start + 1) + byte_at(bc, start + 2) * 256
            if op in opcode.hasjrel:
                tgt = end + arg
            elif op in opcode.hasjabs:
                tgt = arg
            else:
                tgt = None
            label = "#%s" % off2idx.get(tgt, "?") if tgt is not None else str(arg)
            r = describe2(code, op, arg, label)
            # py2 quirk: None/True/False are real names in Python 2 and the
            # compiler's LOAD_CONST folding for them is line-number dependent
            # (a statement >254 lines past the previous line event compiles
            # to LOAD_NAME None instead of LOAD_CONST None -- lnotab delta
            # limit).  Restored sources never reproduce the original blank
            # line/comment layout, so this pair is systematic sig noise;
            # semantically LOAD_NAME None == LOAD_CONST None.
            if name == "LOAD_NAME" and r in ("None", "True", "False"):
                name = "LOAD_CONST"
            out.append((name, r))
        else:
            out.append((name, ""))
    for c in code.co_consts:
        if isinstance(c, types.CodeType):
            sig2(c, out)


def sig3_manual(code, out):
    # Python 3.0-3.3: no dis.get_instructions; walk co_code by hand
    import opcode
    out.append((code.co_name, code.co_argcount))
    bc = code.co_code
    n = len(bc)
    bounds = []
    i = 0
    while i < n:
        op = bc[i] if not isinstance(bc, str) else ord(bc[i])
        start = i
        i += 1
        if op >= opcode.HAVE_ARGUMENT:
            i += 2
        bounds.append((start, i, op))
    off2idx = dict((b[0], k) for k, b in enumerate(bounds))
    for k, (start, end, op) in enumerate(bounds):
        name = opcode.opname[op]
        if op >= opcode.HAVE_ARGUMENT:
            arg = (bc[start + 1] if not isinstance(bc, str) else ord(bc[start + 1])) +                   (bc[start + 2] if not isinstance(bc, str) else ord(bc[start + 2])) * 256
            if op in opcode.hasjrel:
                tgt = end + arg
                r = "#%s" % off2idx.get(tgt, "?")
            elif op in opcode.hasjabs:
                r = "#%s" % off2idx.get(arg, "?")
            elif op in opcode.hasconst:
                try:
                    c = code.co_consts[arg]
                    if isinstance(c, types.CodeType):
                        # normalize away address/path noise (see describe2)
                        r = "<code %s>" % c.co_name
                    else:
                        r = repr(c)[:60]
                except Exception:
                    r = "<const>"
            elif op in opcode.hasname:
                r = str(code.co_names[arg])
            elif op in opcode.haslocal:
                r = str(code.co_varnames[arg])
            elif op in opcode.hasfree:
                r = str((code.co_cellvars + code.co_freevars)[arg])
            else:
                r = str(arg)
            # 3.0-3.3 LOAD_CONST-folding quirk (see sig3): LOAD_NAME
            # None/True/False is the line-layout-dependent spelling of
            # the keyword constant -- normalize
            if name == "LOAD_NAME" and r in ("None", "True", "False"):
                name = "LOAD_CONST"
            out.append((name, r))
        else:
            out.append((name, ""))
    for c in code.co_consts:
        if isinstance(c, types.CodeType):
            sig3_manual(c, out)


def sig3(code, out):
    import dis
    if not hasattr(dis, "get_instructions"):
        return sig3_manual(code, out)
    out.append((code.co_name, code.co_argcount))
    insts = list(dis.get_instructions(code))
    off2idx = {}
    for k, inst in enumerate(insts):
        off2idx[inst.offset] = k
    skip = set()
    for i, inst in enumerate(insts):
        if inst.opname == "STORE_NAME" and inst.argrepr in (
            "__firstlineno__",
            "__static_attributes__",
        ):
            skip.add(i)
            if i > 0 and insts[i - 1].opname in ("LOAD_CONST", "LOAD_SMALL_INT"):
                skip.add(i - 1)
    for i, inst in enumerate(insts):
        if i in skip:
            continue
        r = inst.argrepr
        if r.startswith("<code object"):
            r = "<code %s>" % r.split()[2]
        if inst.opname in dis.hasjrel or inst.opname in dis.hasjabs:
            tgt = inst.argval
            if isinstance(tgt, int):
                r = "#%s" % off2idx.get(tgt, "?")
        name = inst.opname
        # 3.12+/3.14 load specializations (LOAD_FAST_CHECK /
        # LOAD_FAST_BORROW) are semantically identical to LOAD_FAST; the
        # compiler's choice varies with surrounding context, so an
        # original pyc and a recompilation of equivalent source can
        # legitimately differ -- systematic sig noise (bz2 3.14 decompress
        # near-pass blocked on exactly this pair)
        if name in ("LOAD_FAST_BORROW", "LOAD_FAST_CHECK"):
            name = "LOAD_FAST"
        # 3.3 quirk (same family as the py2 lnotab case in sig2): the
        # LOAD_CONST folding for None/True/False is line-layout
        # dependent -- module-level defaults far from the previous line
        # event compile to LOAD_NAME None. Restored sources never
        # reproduce the original blank-line layout; in 3.x these are
        # keywords so LOAD_NAME None can ONLY be this quirk and is
        # semantically LOAD_CONST None (asyncore 3.3 poll/loop defaults)
        if name == "LOAD_NAME" and r in ("None", "True", "False"):
            name = "LOAD_CONST"
        # 3.13+ fused pairs (STORE_FAST_LOAD_FAST / LOAD_FAST_LOAD_FAST)
        # are a scheduling artifact whose emission depends on SOURCE
        # LINE LAYOUT (a line-number boundary between the two ops
        # suppresses the fusion -- multiline vs one-line list
        # comprehensions compile differently). Restored sources never
        # reproduce the original wrapping, so normalize the fusion back
        # into its two component ops (_sitebuiltins 3.13/3.14 blocked on
        # exactly this pair)
        if name in ("STORE_FAST_LOAD_FAST", "LOAD_FAST_LOAD_FAST",
                    "STORE_FAST_STORE_FAST"):
            parts = [p.strip() for p in r.split(",")]
            if len(parts) == 2:
                if name == "STORE_FAST_STORE_FAST":
                    out.append(("STORE_FAST", parts[0]))
                    out.append(("STORE_FAST", parts[1]))
                else:
                    first = "STORE_FAST" if name == "STORE_FAST_LOAD_FAST" else "LOAD_FAST"
                    second = "LOAD_FAST" if name == "STORE_FAST_LOAD_FAST" else "LOAD_FAST"
                    out.append((first, parts[0]))
                    out.append((second, parts[1]))
                continue
        out.append((name, r))
    for c in code.co_consts:
        if isinstance(c, types.CodeType):
            sig3(c, out)


def main():
    data = open(sys.argv[1], "rb").read()
    code = marshal.loads(data[header_size(data):])
    out = []
    if PY2:
        sig2(code, out)
    else:
        sig3(code, out)
    for item in out:
        sys.stdout.write(repr(item) + "\n")


main()
