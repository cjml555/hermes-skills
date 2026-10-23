#!/usr/bin/env python3
"""Identidad de un ejecutable XEX2 de Xbox 360.

Uso: python3 xex_info.py <ruta/default.xex>

Imprime tamaño, sha256 y los campos de ExecutionInfo (Title ID, Media ID, versión,
disco) de los que depende un proyecto recompilado: el launcher y los ganchos están
atados a las direcciones de una copia concreta, así que el Title ID decide si el
análisis aplica.

Sale 1 si el archivo no es un XEX2 o si falta ExecutionInfo, para poder usarlo como
puerta dentro de un pipeline.
"""
import hashlib
import struct
import sys

EXECUTION_INFO = 0x00040006


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip())
        return 2

    with open(argv[1], "rb") as handle:
        data = handle.read()

    print(f"archivo: {argv[1]}")
    print(f"tamano : {len(data):,} bytes")
    print(f"sha256 : {hashlib.sha256(data).hexdigest()}")

    if data[:4] != b"XEX2":
        print(f"magic  : {data[:4]!r} -> NO es un XEX2")
        return 1
    print("magic  : b'XEX2' -> XEX2 valido")

    header_count = struct.unpack_from(">I", data, 20)[0]
    headers = {}
    for index in range(header_count):
        key, value = struct.unpack_from(">II", data, 24 + index * 8)
        headers[key] = value

    info = headers.get(EXECUTION_INFO)
    if info is None:
        print("ExecutionInfo: ausente -> no se puede leer la identidad")
        return 1

    media_id, version, base_version, title_id, _platform, _exe_type, disc, disc_count = \
        struct.unpack_from(">4IBBBB", data, info)

    print()
    print("=== ExecutionInfo ===")
    print(f"  Title ID     : {title_id:08X}")
    print(f"  Media ID     : {media_id:08X}")
    print(f"  Version      : {version >> 24}.{version >> 8 & 0xFF}."
          f"{version >> 4 & 0xF}.{version & 0xF}")
    print(f"  Base version : 0x{base_version:08X}")
    print(f"  Disc         : {disc} de {disc_count}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
