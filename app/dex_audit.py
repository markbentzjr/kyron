import sys, struct, zipfile

FRAMEWORK = ("Landroid/", "Ljava/", "Ljavax/", "Ldalvik/", "Lsun/",
             "Lorg/xml/", "Lorg/w3c/", "Lorg/json/", "Llibcore/")

def read_dex(buf):
    def u32(off): return struct.unpack_from("<I", buf, off)[0]
    str_size, str_off = u32(0x38), u32(0x3C)
    type_size, type_off = u32(0x40), u32(0x44)
    class_size, class_off = u32(0x60), u32(0x64)
    strings = []
    for i in range(str_size):
        off = u32(str_off + i * 4)
        # uleb128 length, then MUTF-8 bytes terminated by 0x00
        p = off
        while buf[p] & 0x80: p += 1
        p += 1
        end = buf.index(b"\x00", p)
        strings.append(buf[p:end].decode("utf-8", "replace"))
    types = [strings[u32(type_off + i * 4)] for i in range(type_size)]
    defined = set()
    for i in range(class_size):
        class_idx = u32(class_off + i * 32)
        defined.add(types[class_idx])
    return defined, set(types)

def audit(path):
    defined, referenced = set(), set()
    with zipfile.ZipFile(path) as z:
        dexs = [n for n in z.namelist() if n.startswith("classes") and n.endswith(".dex")]
        for name in sorted(dexs):
            d, r = read_dex(z.read(name))
            defined |= d; referenced |= r
    missing = [t for t in sorted(referenced)
               if not t.startswith("[") and len(t) >= 3
               and t not in defined and not t.startswith(FRAMEWORK)]
    print(path)
    print(f"  dex files: {len(dexs)}  defined classes: {len(defined)}  referenced types: {len(referenced)}")
    print(f"  MISSING (referenced, not defined, non-framework): {len(missing)}")
    for m in missing[:40]:
        print("   ", m)
    rcount = sum(1 for t in defined if "R$" in t or t.endswith("/R;") or "/R;" in t)
    print(f"  R classes present: {rcount}")

for p in sys.argv[1:]:
    audit(p)
