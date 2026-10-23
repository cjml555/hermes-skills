#!/usr/bin/env python3
"""Triagea los huecos de codigo de un port ReXGlue y declara los que de verdad faltan.

Que huecos son problema
----------------------
`scripts/huecos.py` (en el proyecto) mide el C++ GENERADO y lista todo lo que
queda entre el fin de una funcion y el inicio de la siguiente. Ese informe
tiene falsos positivos:

  - Un hueco listado puede tener YA su funcion: el Discover reclamo la
    direccion con un tamano menor que el hueco, asi que la funcion existe y
    esta registrada, pero el hueco sigue en la lista.
  - Un hueco puede ser la TABLA DE IMPORTS del kernel, no codigo. Declararla
    cada 8 bytes destroza los imports y el enlace falla con N
    "undefined reference to sub_XXXXXXXX".

El juez son las dos tablas del fichero de inicializacion que genera el
codegen (`<proyecto>_init.cpp`): las funciones de juego (`sub_`) y los
imports del kernel (`__imp__`).

Como declarar
--------------
Por tramos de 8 bytes, no solo el inicio: un hueco puede contener varias
funciones seguidas, y declarar solo el inicio deja las demas entradas
inalcanzables (el crash se mueve a +8, +24, +64... dentro del mismo hueco).

Y de a poco: piloto de 5 huecos, backup del analysis, y vuelta atras si el
codegen se rompe. Un hueco declarado de mas no rompe el arranque: rompe el
avance del juego, asi que el criterio de aceptacion no es "compila" sino
"el juego arranca igual y sigue llegando al mismo sitio".

Uso:
    python3 scripts/triage_huecos.py <proyecto> --informe
    python3 scripts/triage_huecos.py <proyecto> --agrupar
    python3 scripts/triage_huecos.py <proyecto> --bytes 0x8260BACC
    python3 scripts/triage_huecos.py <proyecto> --piloto
    python3 scripts/triage_huecos.py <proyecto> [--min 8] [--timeout 120]

Opciones:
    --informe    solo informa: quantos huecos son reales, y por que se descartan
    --agrupar    agrupa por (tamano, separacion): una tabla de datos repite patron
    --bytes ADDR desensambla esa direccion con el volcado de memoria
    --piloto     declara solo 5 huecos y prueba el ciclo completo
    --min N      tamano minimo del hueco (8 = codigo real; 4 = padding)
    --timeout N  segundos de la prueba de juego
    --no-probar  no corre el juego al final

Requiere: el volcado de memoria en <proyecto>/out/runtime/cache/*.bin para
--bytes (ver references/triage-de-huecos.md seccion 3), y capstone en el
user site de python3 para desensamblar.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

IMAGEN_BASE = 0x82000000


# ---------------------------------------------------------------- project ----

def localizar(proyecto: Path):
    """Los ficheros que hay que leer del proyecto."""
    p = dict(
        root=proyecto,
        init=None,
        informe=None,
        analysis=None,
        gen=None,
    )
    for cand in sorted(proyecto.glob("generated/default/*_init.cpp")):
        p["init"] = cand
        break
    if p["init"] is None:
        sys.exit(f"no encontre generated/default/*_init.cpp en {proyecto}")
    p["gen"] = p["init"].parent
    for cand in sorted(proyecto.glob("out/huecos_now.txt")):
        p["informe"] = cand
        break
    if p["informe"] is None:
        p["informe"] = proyecto / "out/huecos_now.txt"
    stem = p["init"].name[: -len("_init.cpp")]
    p["analysis"] = proyecto / f"{stem}_analysis.toml"
    if not p["analysis"].exists():
        found = sorted(proyecto.glob("*_analysis.toml"))
        if found:
            p["analysis"] = found[0]
    return p


# ------------------------------------------------------------------ tablas ---

FUNC_RE = re.compile(r"\{\s*(0x[0-9A-Fa-f]+)\s*,\s*sub_")
IMPORT_RE = re.compile(r"\{\s*(0x[0-9A-Fa-f]+)\s*,\s*__imp__\w+")


def funciones(cand: Path) -> set:
    texto = cand.read_text(encoding="utf-8", errors="replace")
    return {int(m, 16) for m in FUNC_RE.findall(texto)}


def imports(cand: Path) -> set:
    texto = cand.read_text(encoding="utf-8", errors="replace")
    return {int(m, 16) for m in IMPORT_RE.findall(texto)}


# ----------------------------------------------------------------- huecos ----

HUECO_RE = re.compile(
    r"^\s+(0x[0-9A-F]+)\s+(\d+) bytes\s+\(tras (0x[0-9A-F]+), antes de (0x[0-9A-F]+)\)", re.M)


def huecos(informe: Path, minimo: int):
    """[(inicio, tamano, tras, antes)] del bloque final del informe."""
    if not informe.exists():
        sys.exit(f"falta el informe {informe}; regeneralo con scripts/huecos.py")
    texto = informe.read_text(encoding="utf-8", errors="replace")
    if "TODOS los huecos" not in texto:
        # Sin ese bloque, el informe solo trae los 60 primeros huecos, y
        # declararlos a partir de ahi seria declarar una fraccion sin
        # saberlo. Mejor fallar que declarar a medias.
        sys.exit(f"el informe {informe} no tiene el bloque 'TODOS los huecos';\n"
                 f"  regeneralo con scripts/huecos.py")
    bloque = texto.split("TODOS los huecos")[-1]
    return [(int(a, 16), int(s), int(i, 16), int(d, 16))
            for a, s, i, d in HUECO_RE.findall(bloque) if int(s) >= minimo]


def es_import(hueco, tabla_imports):
    """El hueco contiene alguna direccion de la tabla de imports."""
    inicio, tam = hueco[0], hueco[1]
    return any(inicio <= i < inicio + tam for i in tabla_imports)


# ------------------------------------------------------------------ informe --

def cmd_informe(proj, args):
    h = huecos(proj["informe"], args.min)
    funcs = funciones(proj["init"])
    imports_tabla = imports(proj["init"])
    print(f"huecos >= {args.min} bytes: {len(h)}")
    print(f"funciones registradas: {len(funcs)}   imports del kernel: {len(imports_tabla)}")
    con_funcion = [x for x in h if x[0] in funcs]
    con_import = [x for x in h if es_import(x, imports_tabla)]
    reales = [x for x in h if x[0] not in funcs and not es_import(x, imports_tabla)]
    print(f"  ya tienen funcion (no son problema): {len(con_funcion)}")
    print(f"  tocan la tabla de imports (datos):    {len(con_import)}")
    print(f"  REALES sin dueno:                     {len(reales)}")
    print()
    print("los reales (primeros 20):")
    for inicio, tam, tras, antes in reales[:20]:
        print(f"  0x{inicio:08X}  {tam:5d} bytes   (tras 0x{tras:08X}, antes 0x{antes:08X})")
    return 0


def cmd_agrupar(proj, args):
    """Agrupa por (tamano, separacion): una tabla de datos repite el patron."""
    h = huecos(proj["informe"], args.min)
    funcs = funciones(proj["init"])
    reales = [x for x in h if x[0] not in funcs]
    print("agrupacion por (tamano, separacion con el siguiente):")
    pares = Counter()
    for i, (a, s, _, d) in enumerate(reales):
        sig = reales[i + 1][0] if i + 1 < len(reales) else None
        pares[(s, (sig - d) if sig is not None else 0)] += 1
    for (tam, sep), n in pares.most_common(12):
        marca = "  <- patron repetido: probable tabla de datos" if n >= 3 else ""
        print(f"  {n:3d} huecos de {tam:4d} bytes, separados por {sep:#x}{marca}")
    return 0


def cmd_bytes(proj, args):
    """Desensambla una direccion con el volcado de memoria."""
    imagen = None
    for cand in sorted((proj["root"] / "out/runtime/cache").glob("*.bin")):
        imagen = cand
        break
    if imagen is None:
        sys.exit("no hay volcado de memoria en out/runtime/cache/*.bin;\n"
                 "  corre el juego con --<juego>_dump_image=true (ver la referencia)")
    try:
        from capstone import CS_ARCH_PPC, CS_MODE_32, CS_MODE_BIG_ENDIAN, Cs
    except ImportError:
        sys.exit(f"falta capstone; instalalo en el user site:\n"
                 f"  uv pip install --target \"$(python3 -m site --user-site)\" capstone==5.0.7")
    datos = imagen.read_bytes()
    addr = int(args.bytes, 0)
    off = addr - IMAGEN_BASE
    if off < 0 or off + 64 > len(datos):
        sys.exit(f"0x{addr:08X} fuera de la imagen ({imagen.name})")
    print(f"{imagen}  ({len(datos)} bytes, base 0x{IMAGEN_BASE:08X})")
    dis = Cs(CS_ARCH_PPC, CS_MODE_32 | CS_MODE_BIG_ENDIAN)
    for i in dis.disasm(datos[off:off + 64], addr):
        print(f"  {i.address:08X}  {i.bytes.hex()}  {i.mnemonic:8} {i.op_str}")
    return 0


# --------------------------------------------------------------- declaracion --

def declaradas(analysis: Path) -> set:
    if not analysis.exists():
        return set()
    texto = analysis.read_text(encoding="utf-8")
    return {int(m, 16) for m in re.findall(r'"0x([0-9A-Fa-f]+)"\s*=', texto)}


def escribir(analysis: Path, entradas, comentario):
    texto = analysis.read_text(encoding="utf-8")
    ya = declaradas(analysis)
    nuevas = [e for e in entradas if e not in ya]
    if not nuevas:
        return 0
    if not texto.rstrip().endswith("}"):
        texto = texto.rstrip() + "\n"
    bloque = [f"\n# --- {comentario} ---\n"]
    bloque += [f'"0x{e:08X}" = {{ }}\n' for e in nuevas]
    analysis.write_text(texto + "".join(bloque), encoding="utf-8")
    return len(nuevas)


def codegen(proj, args):
    target = f"{proj['analysis'].stem.split('_')[0]}_codegen"
    cmd = ["cmake", "--build", str(proj["root"] / "out/pc"), "--target", target,
           "--parallel", "4"]
    print("  regenerando codegen...", flush=True)
    try:
        r = subprocess.run(cmd, cwd=proj["root"], capture_output=True, text=True,
                           timeout=2400)
    except subprocess.TimeoutExpired:
        print("  el codegen se paso del tiempo")
        return False, ""
    return r.returncode == 0, (r.stdout + r.stderr)[-3000:]


def probar(proj, args):
    """Corre el juego y dice como fue: pipelines y fatales."""
    for f in Path("/dev/shm").glob("xenia_memory_*"):
        try:
            f.unlink()
        except OSError:
            pass
    juego = proj["root"] / "out/pc" / proj["init"].name[: -len("_init.cpp")]
    if not juego.exists():
        cand = sorted((proj["root"] / "out/pc").glob("mcla*"))
        cand = [c for c in cand if c.is_file() and c.stat().st_mode & 0o111]
        if not cand:
            print("  no encuentro el ejecutable del juego en out/pc/")
            return None
        juego = cand[0]
    cmd = [str(juego),
           "--headless=true", "--mnk_mode=true", "--user_language=1",
           "--video_driver=offscreen", "--log_level=info"]
    try:
        subprocess.run(cmd, cwd=proj["root"], capture_output=True, text=True,
                       timeout=args.timeout * 60)
    except subprocess.TimeoutExpired:
        pass
    logs = sorted((proj["root"] / "out/pc/logs").glob("*.log"),
                  key=lambda p: p.stat().st_mtime)
    if not logs:
        return None
    texto = logs[-1].read_text(errors="replace")
    return {"log": logs[-1].name,
            "pipelines": texto.count("Creating graphics pipeline"),
            "fatales": texto.count("invalid or unregistered")}


def cmd_declarar(proj, args):
    h = huecos(proj["informe"], args.min)
    funcs = funciones(proj["init"])
    imports_tabla = imports(proj["init"])

    print(f"huecos >= {args.min} bytes: {len(h)}")
    antes = len(h)
    h = [x for x in h if x[0] not in funcs]
    print(f"  sin funcion registrada: {len(h)}   (los otros {antes - len(h)} ya son funciones)")
    antes = len(h)
    h = [x for x in h if not es_import(x, imports_tabla)]
    print(f"  que no tocan la tabla de imports: {len(h)}   (los otros {antes - len(h)} eran imports)")

    if args.piloto:
        h = h[:5]
        print("  piloto: 5 huecos")

    entradas = []
    for inicio, tam, _, _ in h:
        for off in range(0, tam, 8):
            entradas.append(inicio + off)
    print(f"entradas a declarar: {len(entradas)}")

    backup = proj["root"] / "out" / f"{proj['analysis'].name}.bak"
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(proj["analysis"], backup)
    print(f"backup en {backup}")

    n = escribir(proj["analysis"], entradas,
                 f"Auto: huecos >= {args.min} bytes, en tramos de 8")
    print(f"declaradas: {n}")

    ok, salida = codegen(proj, args)
    if not ok:
        print("\nCODEGEN ROTO: se restaura el analysis")
        print(salida[-2000:])
        shutil.copy2(backup, proj["analysis"])
        return 2
    print("codegen OK")

    # El judge final: las direcciones declaradas tienen que ser funciones.
    regs = funciones(proj["init"])
    decl = declaradas(proj["analysis"])
    sin_funcion = [d for d in decl if d not in regs]
    print(f"entradas declaradas: {len(decl)}   de las que no son funcion: {len(sin_funcion)}")

    if not args.no_probar:
        r = probar(proj, args)
        if r:
            print(f"juego: {r['log']}  pipelines={r['pipelines']}  fatales={r['fatales']}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("proyecto", help="raiz del proyecto ReXGlue")
    ap.add_argument("--informe", action="store_true", help="solo informa")
    ap.add_argument("--agrupar", action="store_true", help="agrupa por patron")
    ap.add_argument("--bytes", help="desensambla esta direccion")
    ap.add_argument("--piloto", action="store_true", help="declara 5 huecos y prueba")
    ap.add_argument("--min", type=int, default=8, help="tamano minimo del hueco")
    ap.add_argument("--timeout", type=int, default=120, help="segundos de la prueba")
    ap.add_argument("--no-probar", action="store_true")
    args = ap.parse_args()

    root = Path(args.proyecto).expanduser().resolve()
    if not root.is_dir():
        sys.exit(f"no existe el directorio {root}")
    proj = localizar(root)

    if args.bytes:
        return cmd_bytes(proj, args)
    if args.agrupar:
        return cmd_agrupar(proj, args)
    if args.informe:
        return cmd_informe(proj, args)
    return cmd_declarar(proj, args)


if __name__ == "__main__":
    sys.exit(main())
