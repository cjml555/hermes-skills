#!/usr/bin/env python3
"""Declara los destinos de rama huerfanos que reporta `rexglue codegen` y reintenta
hasta que el analisis pase la validacion.

Uso:
    python3 scripts/fix_orphan_branches.py <raiz-del-proyecto> [manifest.toml]

Por que itera: declarar una direccion en el analysis TOML cambia el descubrimiento de
limites de las funciones vecinas, asi que la ronda siguiente reporta destinos nuevos
(tipicamente a pocos bytes del anterior). Cada ronda cuesta ~60 s en un xex de ~9 MB;
converge en pocas rondas.

Las direcciones se normalizan a '0x' + hex en minuscula: el parser del SDK acepta
`"0X822C9948"` igual que `"0x822C9948"`, pero si el TOML ya trae una clave con el
prefijo en mayuscula y el helper no lo reconoce, la misma direccion se vuelve a
declarar en cada ronda y cada ronda gasta un ciclo de codegen de ~60 s.

Escribe:
    <raiz>/<juego>_analysis.toml   lo crea con las flags de registros y lo amplia
    <raiz>/codegen.log             salida completa de la ultima ronda

Sale 0 cuando el codegen supera la validacion, 1 si no hay nada nuevo que declarar
y 2 si agota las rondas. Requiere `rexglue` en el PATH.
"""
import pathlib
import re
import subprocess
import sys

# Un destino sin dueno aparece asi en la salida del validador:
#   0x822C9948 from 0x822C9E14: b 0x822C9948 from 0x822C9E14 - target not in any function
ORPHAN = re.compile(r"^\s+(0[xX][0-9A-Fa-f]{8}) from (0[xX][0-9A-Fa-f]{8})", re.M)
DECLARED = re.compile(r'"0[xX]([0-9A-Fa-f]{8})"\s*=\s*\{\s*\}')
INCLUDES = re.compile(r"includes\s*=\s*\[([^\]]*)\]")

HEADER = """# Destinos de rama sin dueno que reporto el validador del analisis.
# Declararlos hace que el descubrimiento les encuentre limites. Las flags de
# registros se dejan en el contexto PPC compartido durante el arranque.
cr_as_local = false
xer_as_local = false
ctr_as_local = false
non_volatile_as_local = false

[functions]
"""


def norm(addr: str) -> str:
    """Normaliza una direccion a '0x' + hex en minuscula."""
    body = addr[2:] if addr[:2].lower() == "0x" else addr
    return "0x" + body.lower()


def pick_paths(root: pathlib.Path, argv: list) -> tuple:
    if len(argv) > 2:
        manifest = root / argv[2] if not pathlib.Path(argv[2]).is_absolute() else pathlib.Path(argv[2])
    else:
        found = sorted(root.glob("*_manifest.toml"))
        if not found:
            sys.exit(f"no encontre ningun *_manifest.toml en {root}; pasalo como segundo argumento")
        manifest = found[0]

    # El analysis que corresponde al manifest manda; solo si no existe se cae al
    # primero que aparezca, para no mezclar dos juegos en el mismo directorio.
    name = manifest.name
    stem = name[: -len("_manifest.toml")] if name.endswith("_manifest.toml") else manifest.stem
    preferred = root / f"{stem}_analysis.toml"
    if preferred.exists():
        analysis = preferred
    else:
        existing = sorted(root.glob("*_analysis.toml"))
        analysis = existing[0] if existing else preferred
    return manifest, analysis


def ensure_included(manifest: pathlib.Path, analysis: pathlib.Path) -> None:
    """El manifest solo aplica el analysis TOML si lo lista en `includes`."""
    text = manifest.read_text()
    if analysis.name in text:
        return
    replacement = f'includes = ["{analysis.name}"]'
    new, count = INCLUDES.subn(replacement, text, count=1)
    if count == 0:
        # Sin clave `includes`: el final del archivo pertenece a [entrypoint], que
        # es donde la clave vive, asi que anadirla ahi es correcto.
        new = text.rstrip("\n") + f"\n{replacement}\n"
    manifest.write_text(new)
    print(f"  manifest: {analysis.name} anadido a includes")


def declared(analysis: pathlib.Path) -> set:
    return {norm("0x" + hexpart) for hexpart in DECLARED.findall(analysis.read_text())}


def append(analysis: pathlib.Path, pending: dict) -> None:
    lines = []
    for target in sorted(pending):
        lines.append(f"# b {target} at {pending[target]}.")
        lines.append(f'"{target}" = {{ }}')
    with analysis.open("a") as fh:
        fh.write("\n".join(lines) + "\n")


def main() -> int:
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".").expanduser().resolve()
    manifest, analysis = pick_paths(root, sys.argv)
    if not analysis.exists():
        analysis.write_text(HEADER)
        print(f"  creado {analysis.name}")
    ensure_included(manifest, analysis)

    max_rounds = int(sys.argv[3]) if len(sys.argv) > 3 else 15
    log = root / "codegen.log"

    for rnd in range(1, max_rounds + 1):
        print(f"\n{'=' * 20} ronda {rnd}/{max_rounds} {'=' * 20}", flush=True)
        proc = subprocess.run(
            ["rexglue", "codegen", manifest.name],
            cwd=root, capture_output=True, text=True,
        )
        out = proc.stdout + proc.stderr
        log.write_text(out)

        if "Validation failed" not in out:
            print("\n>>> VALIDACION SUPERADA", flush=True)
            print("\n".join(out.splitlines()[-30:]), flush=True)
            return 0

        known = declared(analysis)
        pending = {}
        for target, source in ORPHAN.findall(out):
            key = norm(target)
            if key not in known:
                pending[key] = source
        print(f"  huerfanos: {len(set(norm(t) for t, _ in ORPHAN.findall(out)))} "
              f"| declarados: {len(known)} | nuevos: {len(pending)}")
        for target, src in sorted(pending.items()):
            print(f"    + {target}  (b desde {src})")

        if not pending:
            print("\n>>> la validacion fallo pero no hay destinos nuevos que declarar;"
                  f" revisa {log}", flush=True)
            print("\n".join(out.splitlines()[-30:]), flush=True)
            return 1
        append(analysis, pending)

    print(f"\n>>> sin converger en {max_rounds} rondas", flush=True)
    return 2


if __name__ == "__main__":
    sys.exit(main())
