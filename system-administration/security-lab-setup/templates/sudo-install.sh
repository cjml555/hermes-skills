#!/usr/bin/env bash
# <LAB>/scripts/sudo-install.sh — TODO lo que necesita sudo, en un bloque.
#
#   sudo <LAB>/scripts/sudo-install.sh
#
# Idempotente: se puede volver a correr sin romper nada. Tarda ~10-20 min
# (paquetes de pacman + imagenes Docker). Todo lo que se puede hacer sin sudo
# (workspace, binarios release, compose, scripts, notas) debe estar HECHO antes
# de entregar esto; este script es el ultimo paso, no el plan.
#
# Structure: log -> pacman tools -> docker + group -> setcap -> verify.

set -uo pipefail          # NOT set -e: one failing step must not abort the rest

# Resolve the REAL user, not root: under sudo $USER is root and $HOME is /root,
# so a path built from them lands in the wrong tree.
TARGET_USER="${SUDO_USER:-<USER>}"
LAB="/home/$TARGET_USER/<LAB_DIR>"
STAMP="$(date +%Y%m%d-%H%M%S)"
LOG="$LAB/evidence/sudo-install-$STAMP.log"
mkdir -p "$LAB/evidence"
export HOME="/home/$TARGET_USER"

step() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
fail() { printf '\033[1;31mFALLO: %s\033[0m\n' "$*"; exit 1; }

# tee so the user sees progress AND keeps a record for the next session.
exec > >(tee -a "$LOG") 2>&1
step "Log completo en $LOG"

# ---------------------------------------------------------------- 1. PACMAN TOOLS
step "1/4  Herramientas nativas de Arch/Manjaro"
PACMAN_PKGS="nmap wireshark-cli radare2 john hashcat sqlmap hydra gobuster \
nikto openbsd-netcat socat jq metasploit masscan exploitdb jdk-openjdk"

sudo pacman -S --needed --noconfirm $PACMAN_PKGS \
  || fail "pacman devolvio error — revisa el log; quizas falta -Sy primero"

# A stale/absent package list makes the whole batch above fail on a missing
# member. Refresh once and retry rather than leaving the host half-tooled.
step "Refrescando bases de pacman por si falta algun paquete"
sudo pacman -Sy --noconfirm >/dev/null 2>&1
sudo pacman -S --needed --noconfirm $PACMAN_PKGS \
  || echo "AVISO: la segunda pasada tambien fallo; revisa $LOG"

# ---------------------------------------------------------------- 2. DOCKER
step "2/4  Docker + plugin compose"

if ! command -v docker >/dev/null; then
  sudo pacman -S --needed --noconfirm docker docker-compose \
    || fail "no se pudo instalar docker"
else
  echo "docker ya presente: $(docker --version 2>/dev/null || echo version ilegible)"
fi

# The daemon may refuse to start inside a container/chroot; that is NOT fatal.
if sudo systemctl enable --now docker 2>/dev/null; then
  echo "systemd: docker habilitado y arrancado"
elif sudo systemctl start docker 2>/dev/null; then
  echo "docker arrancado (sin enable)"
else
  echo "AVISO: systemctl no arranco docker. Revisa: systemctl status docker"
fi

if sudo usermod -aG docker "$TARGET_USER"; then
  echo "$TARGET_USER agregado al grupo docker"
  echo ">> remember: cierra la sesion y vuelve a entrar (o: newgrp docker)"
fi

# ---------------------------------------------------------------- 3. SETCAP
step "3/4  Permisos de captura para nmap/tshark (sin sudo en cada uso)"

for bin in tshark nmap dumpcap; do
  path="$(command -v "$bin" 2>/dev/null || true)"
  [[ -z "$path" ]] && { echo "- $bin no instalado, se omite"; continue; }
  real="$(readlink -f "$path")"
  if sudo setcap cap_net_raw,cap_net_admin+eip "$real" 2>/dev/null; then
    echo "- $bin -> OK ($real)"
  else
    echo "- $bin -> setcap fallo; usalo con sudo"
  fi
done

# ---------------------------------------------------------------- 4. VERIFY
step "4/4  Verificacion"

missing=()
for t in nmap tshark radare2 r2 john hashcat sqlmap hydra gobuster nikto nc \
         socat jq masscan metasploit-msfconsole docker; do
  if command -v "$t" >/dev/null; then
    printf '  %-22s %s\n' "$t" "$(command -v "$t")"
  else
    missing+=("$t")
  fi
done

if command -v docker >/dev/null; then
  docker compose version >/dev/null 2>&1 \
    && echo "  docker compose         OK" \
    || echo "  AVISO: falta el plugin 'docker compose'"
  sudo docker run --rm hello-world >/dev/null 2>&1 \
    && echo "  docker run             OK (daemon responde)" \
    || echo "  AVISO: el daemon no responde; revisa 'systemctl status docker'"
fi

echo
if [[ ${#missing[@]} -eq 0 ]]; then
  echo "TODAS las herramientas presentes."
else
  echo "SIGUEN FALTANDO: ${missing[*]}"
  echo "Revisa $LOG para el motivo (normalmente un paquete con otro nombre)."
fi

cat <<EOF

========================================================================
SIGUIENTE PASO (manual: el grupo nuevo solo aplica a sesiones nuevas):

  1) newgrp docker          # o cierra sesion y vuelve a entrar
  2) cd $LAB
  3) scripts/up.sh -d web   # el grupo mas barato en imagenes
  4) scripts/scan.sh        # estado + cabeceras HTTP

DESPUES, bajo demanda (imagenes pesadas, RAM justa):
  scripts/up.sh -d net      # vulnerable host multi-servicio
  scripts/up.sh -d bench    # banco de fuzzing para ffuf
  scripts/<toolbox>.sh      # toolbox Kali (build largo)

Puertos publicados (todos atados a 127.0.0.1). Rellena esta lista al
elegirlos y despues de cualquier renumeracion — el README la repite:
  :1xxxx  <first target>
  :8xxx   <second target>
  :8xxx   <toolbox / proxy>
========================================================================
EOF
