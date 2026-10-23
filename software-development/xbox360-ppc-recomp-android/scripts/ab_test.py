#!/usr/bin/env python3
"""A/B honesto: ¿este guion de pulsaciones hace avanzar el juego?

Construye las condiciones del A/B bien, que es donde fallan casi todos:

- El CONTROL tiene el pad **instalado pero sin pulsar nunca** (un gesto
  programado mas alla del final de la corrida). Un control "sin
  pulsaciones" a secas no tiene pad, si el driver solo se instala cuando
  hay guion: ese A/B mide dos variables a la vez.
- Cada condicion corre en un estado limpio (user y cache borrados) y con
  la MISMA duracion, porque el tiempo de ejecucion cambia el resultado.
- Se comprueba el CODIGO DE SALIDA: 137 = OOM killer = la medicion no
  vale; 124 = llego al final.
- Se lee el log COMPLETO (todos los stems, por marca de tiempo), porque
  el sink rotatorio cambia de stem a mitad de corrida.
- Se reporta el RECUENTO, no un punto: el juego no es determinista y el
  conteo absoluto es ruidoso.

Uso:
    ab_test.py --binario out/pc/mcla --juego-root ~/mi-juego \\
               --guion "3:0x1000,6:0x1000,9:0x0010" --repeticiones 3

    # con el driver de video offscreen (obligatorio si no hay X server)
    ab_test.py --binario out/pc/mcla --juego-root ~/mi-juego \\
               --guion "3:0x1000,6:0x1000" --control "9999:0x1000"
"""

import argparse
import glob
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

LOG_RE = re.compile(r"^mcla_(\d+)(\.\d+)?\.log$")


def logs_de_la_corrida(log_dir, desde):
    """{stem: {indice: ruta}} de los logs escritos despues de `desde`."""
    stems = {}
    for nombre in os.listdir(log_dir):
        m = LOG_RE.match(nombre)
        if not m:
            continue
        ruta = Path(log_dir) / nombre
        try:
            if ruta.stat().st_mtime <= desde:
                continue
        except OSError:
            continue
        indice = int(m.group(2)[1:]) if m.group(2) else 0
        stems.setdefault(m.group(1), {})[indice] = ruta
    return stems


def leer_texto(log_dir, desde):
    """Todo el log de la corrida, en orden cronologico."""
    stems = logs_de_la_corrida(log_dir, desde)
    textos = []
    for stem in sorted(stems, key=int):
        for indice in sorted(stems[stem]):
            try:
                textos.append(stems[stem][indice].read_text(
                    encoding="utf-8", errors="replace"))
            except OSError:
                pass
    return "\n".join(textos)


def limpiar_estado(root, user, cache):
    for d in (user, cache):
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True, exist_ok=True)
    # La arena del invitado va en tmpfs: sin limpiarla, varias ejecuciones
    # seguidas agotan /dev/shm y el fallo aparece como SIGBUS.
    for f in glob.glob("/dev/shm/xenia_memory_*"):
        try:
            os.unlink(f)
        except OSError:
            pass


def correr(binario, root, user, cache, guion, duracion, extra):
    limpiar_estado(root, user, cache)
    log_dir = Path(root) / "out/pc/logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    cmd = [str(binario),
           f"--game_data_root={root}",
           f"--user_data_root={user}",
           f"--cache_root={cache}",
           f"--metadata_root={root}/out/runtime/metadata",
           "--log_level=info", "--headless=true", "--mnk_mode=true",
           "--user_language=1", "--video_driver=offscreen"] + list(extra)

    env = dict(os.environ)
    if guion:
        env["MCLA_PAD_PRESS"] = guion

    desde = time.time()
    try:
        proc = subprocess.run(cmd, cwd=root, env=env, timeout=duracion,
                              capture_output=True, text=True)
        codigo = proc.returncode
    except subprocess.TimeoutExpired:
        codigo = 124          # timeout: llego al final de la ventana
    except FileNotFoundError:
        return None

    texto = leer_texto(log_dir, desde)
    if not texto:
        return None
    return {
        "codigo": codigo,
        "pipelines": texto.count("Creating graphics pipeline"),
        "fatales": texto.count("invalid or unregistered function"),
        "guardado": "mc4.sav" in texto,
        "pulsaciones": texto.count("scripted gamepad buttons"),
        "shaders": len(set(re.findall(
            r"Creating graphics pipeline state with VS ([0-9A-F]+)", texto))),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--binario", required=True)
    ap.add_argument("--juego-root", required=True)
    ap.add_argument("--guion", required=True, help="guion del tratamiento")
    ap.add_argument("--control", default="9999:0x1000",
                    help="guion del control: pad presente, sin pulsar "
                         "(por defecto un gesto fuera de la corrida)")
    ap.add_argument("--repeticiones", type=int, default=3)
    ap.add_argument("--duracion", type=int, default=180)
    ap.add_argument("--extra", nargs=argparse.REMAINDER, default=[],
                    help="argumentos extra para el juego")
    args = ap.parse_args()

    root = Path(args.juego_root).resolve()
    binario = Path(args.binario)
    if not binario.is_absolute():
        binario = root / binario
    if not binario.exists():
        print(f"ERROR: no existe {binario}", file=sys.stderr)
        return 1
    user = root / "out/runtime/user"
    cache = root / "out/runtime/cache"

    condiciones = [("control", args.control), ("tratamiento", args.guion)]
    resultados = {nombre: [] for nombre, _ in condiciones}

    for rep in range(1, args.repeticiones + 1):
        print(f"--- repeticion {rep}/{args.repeticiones} ---", flush=True)
        for nombre, guion in condiciones:
            r = correr(binario, root, user, cache, guion,
                       args.duracion, args.extra)
            if r is None:
                print(f"  {nombre:12s} SIN LOG (la corrida no arranco?)", flush=True)
                continue
            resultados[nombre].append(r)
            marca = ""
            if r["codigo"] == 137:
                marca = "  <-- OOM: medicion NO VALE"
            print(f"  {nombre:12s} pipes={r['pipelines']:5d} shaders={r['shaders']:4d} "
                  f"guardado={'si' if r['guardado'] else 'no':3s} "
                  f"exit={r['codigo']}{marca}", flush=True)

    print()
    print("=== resumen ===")
    for nombre, _ in condiciones:
        rs = [r for r in resultados[nombre] if r["codigo"] != 137]
        if not rs:
            print(f"  {nombre:12s} (sin corridas validas)")
            continue
        pipes = [r["pipelines"] for r in rs]
        llegaron = sum(1 for r in rs if r["guardado"])
        print(f"  {nombre:12s} pipes min={min(pipes)} max={max(pipes)} "
              f"llego={llegaron}/{len(rs)}")

    validos = [r for r in resultados["control"] if r["codigo"] != 137]
    trat = [r for r in resultados["tratamiento"] if r["codigo"] != 137]
    if not validos or not trat:
        print("\n  sin datos validos: revisa el codigo de salida (137 = OOM)")
        return 1
    media_control = sum(r["pipelines"] for r in validos) / len(validos)
    media_trat = sum(r["pipelines"] for r in trat) / len(trat)
    print()
    print(f"  diferencia media de pipelines: {media_trat - media_control:+.0f}")
    print("  Compara condiciones, no contra numeros guardados de otra sesion:")
    print("  el conteo absoluto es ruidoso.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
