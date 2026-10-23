#!/bin/bash
# Mide la memoria de un proceso Android. Es la cifra que hay que comparar
# cuando un cambio dice "ahorra memoria": el mismo dispositivo, el mismo
# modelo, unicamente el modo alterno.
#
#   ./measure-app-memory.sh <paquete> [etiqueta]
#
# Salida: PSS (RAM resident), RSS y SWAP PSS (paginas empujadas a swap).
# PSS es la cifra comparable: RSS infla por paginas compartidas entre
# procesos, y SWAP dice si el sistema esta moviendo la app a swap.
set -u

PKG=${1:?uso: measure-app-memory.sh <paquete> [etiqueta]}
LABEL=${2:-}

PID=$(adb shell pidof "$PKG" 2>/dev/null | tr -d '\r' | awk '{print $1}')
if [ -z "$PID" ]; then
    echo "$PKG no esta corriendo - no hay memoria que medir"
    exit 1
fi

echo "---------------------------------------------------------------"
echo "  ${LABEL:+$LABEL - }$PKG  (pid $PID)"
echo "---------------------------------------------------------------"
adb shell dumpsys meminfo "$PKG" 2>/dev/null | grep -E \
    "TOTAL PSS|TOTAL RSS|TOTAL SWAP PSS|Native Heap|EGL mtrack|GL mtrack" \
  | sed 's/^/  /'
echo
echo "  Para comparar, repite la medicion con el otro modo y el mismo modelo."
echo "  Un modo que no mueve estas cifras no esta haciendo nada."
