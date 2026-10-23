#!/usr/bin/env python3
"""Compara dos corridas del port (logs de PC) para responder: "el juego llego
mas lejos con esta entrada que sin ella".

Resuelve las dos trampas de comparar logs a mano:

1. El log rota: `<nombre>.log` es la parte NUEVA y `<nombre>.1.log` la ANTIGUA.
   Leer solo una de las dos pierde el principio de la corrida y produce
   conclusiones falsas. Aqui se concatenan y se ordenan por timestamp.
2. La textura de swap alterna entre dos direcciones (doble buffer), con lo que
   no dice que pantalla se muestra. Lo que distingue una pantalla de otra es
   el CONJUNTO de hashes de vertex shader que se crean.

Uso:
    comparar_corridas.py <log-a> [<log-b>] [--presion MARCADOR]

    <log-a> puede ser la ruta del `.log` o su base sin extension (se buscan
    ambos y se concatenan).

    --presion MARCADOR: texto que identifica la pulsacion en el log (por
    defecto "scripted gamepad pressing"). Con el, se imprime el histograma de
    pipelines por segundo alrededor de la pulsacion, que es donde se ve si el
    juego cargo una pantalla nueva.

Criterio: la corrida con pulsacion debe cargar un conjunto de shaders que el
control NO carga. Un pipeline count mas alto no prueba nada: el titulo tambien
crea pipelines mientras carga.
"""

import argparse
import datetime
import os
import re
import sys

TS = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\.")
PIPE = re.compile(r"Creating graphics pipeline state with VS ([0-9A-F]+)")
DEFAULT_PRESS_MARKER = "scripted gamepad pressing"


def resolve(base):
    """Devuelve el texto del log concatenando la parte antigua y la nueva."""
    if base.endswith(".log"):
        base = base[: -len(".log")]
    old = base + ".1.log"
    new = base + ".log"
    parts = []
    for path in (old, new):
        if os.path.exists(path):
            with open(path, encoding="utf-8", errors="replace") as fh:
                parts.append(fh.read())
    if not parts:
        raise SystemExit(f"no hay log para {base} (buscaba {old} y {new})")
    return "\n".join(parts)


def parse(base):
    """[(timestamp, linea)] ordenado cronologicamente."""
    events = []
    for line in resolve(base).splitlines():
        match = TS.match(line)
        if not match:
            continue
        stamp = datetime.datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
        events.append((stamp, line))
    events.sort(key=lambda item: item[0])
    if not events:
        raise SystemExit(f"{base}: sin lineas con timestamp")
    return events


def summarize(events):
    shaders, pipes, presents, fatals, textures = set(), 0, 0, 0, 0
    for _, line in events:
        match = PIPE.search(line)
        if match:
            shaders.add(match.group(1))
            pipes += 1
        elif "PRESENT: swap_texture" in line:
            presents += 1
        elif "Loaded tiled" in line:
            textures += 1
        if "FATAL" in line or "invalid or unregistered function" in line:
            fatals += 1
    return {
        "shaders": shaders,
        "pipes": pipes,
        "presents": presents,
        "fatals": fatals,
        "textures": textures,
    }


def press_moment(events, marker):
    for stamp, line in events:
        if marker in line:
            return stamp
    return None


def histogram(events, origin, window=20):
    """Pipelines por segundo, relativo a origin."""
    buckets = {}
    for stamp, line in events:
        if PIPE.search(line):
            rel = int((stamp - origin).total_seconds())
            buckets[rel] = buckets.get(rel, 0) + 1
    return dict(sorted(buckets.items()))


def report(label, events, marker):
    stats = summarize(events)
    t0 = events[0][0]
    duration = events[-1][0] - t0
    print(f"--- {label} ---")
    print(f"  duracion:        {duration}")
    print(f"  pipelines:       {stats['pipes']}")
    print(f"  presents:        {stats['presents']}")
    print(f"  texturas:        {stats['textures']}")
    print(f"  shaders unicos:  {len(stats['shaders'])}")
    print(f"  errores fatales: {stats['fatals']}")

    moment = press_moment(events, marker)
    if moment is not None:
        print(f"  pulsacion en:    t+{int((moment - t0).total_seconds())}s")
        buckets = histogram(events, t0)
        for rel in sorted(buckets):
            if -5 <= rel <= 90 and buckets[rel]:
                print(f"      t+{rel:3d}s  pipelines={buckets[rel]}")
    else:
        print(f"  pulsacion:       no encontrada (marcador {marker!r})")
    return stats


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("log_a")
    parser.add_argument("log_b", nargs="?")
    parser.add_argument("--presion", default=DEFAULT_PRESS_MARKER,
                        help="texto que marca la pulsacion en el log")
    args = parser.parse_args()

    events_a = parse(args.log_a)
    stats_a = report(args.log_a, events_a, args.presion)

    if not args.log_b:
        return 0

    events_b = parse(args.log_b)
    stats_b = report(args.log_b, events_b, args.presion)

    print()
    only_a = stats_a["shaders"] - stats_b["shaders"]
    only_b = stats_b["shaders"] - stats_a["shaders"]
    print("=== diferencia de shaders ===")
    print(f"  solo en A: {len(only_a)}")
    for shader in sorted(only_a)[:12]:
        print(f"      {shader}")
    print(f"  solo en B: {len(only_b)}")
    for shader in sorted(only_b)[:12]:
        print(f"      {shader}")

    print()
    if only_a and not only_b:
        print("VEREDICTO: A carga una pantalla que B nunca carga.")
    elif stats_a["fatals"] and not stats_b["fatals"]:
        print("VEREDICTO: A fallo donde B no. Revisa la direccion del crash.")
    else:
        print("VEREDICTO: sin diferencia concluyente. Comprueba duraciones y niveles de log.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
