#!/usr/bin/env python3
"""Lee el log COMPLETO de una corrida del port (todos los stems, todas las partes).

Resuelve la trampa del sink rotatorio del SDK, que rompe de tres maneras
distintas a cualquier script que lea logs:

1. Al llegar a 5 MB renombra el log actual a `<nombre>.1.log`, cuyo
   contenido es ANTERIOR: leer solo `<nombre>.log` pierde el principio de
   la corrida.
2. Si ese `.1.log` ya existe lo renombra a `.2.log`: el numero total de
   ficheros NO crece, asi que "hay un log mas que antes" no prueba que la
   corrida actual escribio nada.
3. Al rotar abre un log NUEVO con otro numero: el "stem" cambia a mitad
   de corrida, asi que leer solo el ultimo stem pierde lo anterior.

Por eso el filtro es por MARCA DE TIEMPO (no por conteo de ficheros) y se
leen todos los stems.

Uso:
    leer_log_corrida.py <directorio-de-logs> [--desde-segundos N] [--stem NNN]

    # la corrida mas reciente
    leer_log_corrida.py out/pc/logs

    # una corrida concreta
    leer_log_corrida.py out/pc/logs --stem 128

    # lo escrito en los ultimos 600 s
    leer_log_corrida.py out/pc/logs --desde-segundos 600

Con --resumen imprime en vez del texto: los numeros que se usan para
medir, y si la corrida llego (guardado escrito) o no.
"""

import argparse
import os
import re
import sys
import time

LOG_RE = re.compile(r"^mcla_(\d+)(\.\d+)?\.log$")


def stems_modificados(log_dir, desde):
    """{stem: {indice: ruta}} de los logs escritos despues de `desde`."""
    stems = {}
    for nombre in os.listdir(log_dir):
        m = LOG_RE.match(nombre)
        if not m:
            continue
        ruta = os.path.join(log_dir, nombre)
        try:
            if os.path.getmtime(ruta) <= desde:
                continue
        except OSError:
            continue
        # El grupo 2 viene como ".1", con el punto: hay que quitarlo.
        indice = int(m.group(2)[1:]) if m.group(2) else 0
        stems.setdefault(m.group(1), {})[indice] = ruta
    return stems


def leer(log_dir, desde=0.0, stem_filtrado=None):
    """El texto de la corrida, en orden cronologico.

    Dentro de un stem, de la parte mas antigua a la actual. Entre stems, del
    numero mas bajo al mas alto (el numero crece con cada corrida).
    """
    stems = stems_modificados(log_dir, desde)
    if stem_filtrado is not None:
        stems = {k: v for k, v in stems.items() if k == stem_filtrado}
    if not stems:
        return ""
    textos = []
    for stem in sorted(stems, key=int):
        for indice in sorted(stems[stem]):
            try:
                with open(stems[stem][indice], encoding="utf-8", errors="replace") as fh:
                    textos.append(fh.read())
            except OSError:
                pass
    return "\n".join(textos)


def resumen(texto):
    guardado = "mc4.sav" in texto
    return {
        "pipelines": texto.count("Creating graphics pipeline"),
        "fatales": texto.count("invalid or unregistered function"),
        "triggers": texto.count("trigger fired"),
        "pulsaciones": texto.count("scripted gamepad buttons"),
        "guardado": guardado,
        "ficheros_leidos": sorted(set(re.findall(
            r"leer \d+ bytes de '([^']+\.rpf)'", texto))),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("log_dir")
    ap.add_argument("--desde-segundos", type=float, default=0.0,
                    help="ignorar logs no modificados en los ultimos N s")
    ap.add_argument("--stem", default=None,
                    help="leer solo ese stem (numero de corrida)")
    ap.add_argument("--resumen", action="store_true",
                    help="imprimir los numeros de medicion en vez del texto")
    args = ap.parse_args()

    desde = time.time() - args.desde_segundos if args.desde_segundos else 0.0
    texto = leer(args.log_dir, desde, args.stem)
    if not texto:
        print("no hay log en esa ventana", file=sys.stderr)
        return 1

    if args.resumen:
        r = resumen(texto)
        for clave, valor in r.items():
            if clave == "ficheros_leidos":
                print(f"  {clave:16s} {valor}")
            else:
                print(f"  {clave:16s} {valor}")
        print()
        print("  'guardado: si' = el juego entro en una partida de verdad.")
        print("  'guardado: no' = la corrida NO llego: no concluyas nada de ella.")
    else:
        sys.stdout.write(texto)
    return 0


if __name__ == "__main__":
    sys.exit(main())
