#!/usr/bin/env bash
# status_monitor.sh — envoie l'état des sections et du PC par Telegram.
# Appelée toutes les 15 min par le cronjob hermes.

set -u
export HERMES_HOME="/home/jhon/.hermes"
HERMES="/home/jhon/.hermes/hermes-agent/.hermes/bin/hermes"

# --- 1. Statut du PC ---
load=$(cut -d' ' -f1-3 /proc/loadavg)
uptime=$(uptime -p | sed 's/up //')
mem_total=$(free -m | awk '/Mem:/ {print $2}')
mem_used=$(free -m | awk '/Mem:/ {print $3}')
mem_free=$(free -m | awk '/Mem:/ {print $4}')
disk=$(df -h / | awk 'NR==2 {print $5}')
cpu_raw=$(cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null || echo "N/A")
if [[ "$cpu_raw" =~ ^[0-9]+$ ]]; then
  cpu_temp=$(( cpu_raw / 1000 ))
else
  cpu_temp="$cpu_raw"
fi
cpu_temp="${cpu_temp}°C"
net_ifs=$(ip -br -o addr show | awk '$2 ~ /UP/ {print $1": "$3}' | tr '\n' ' ' | sed 's/ $//')
swap=$(free -m | awk '/Swap:/ {print $2" / "$3}')

# --- 2. Statut des sections ---
kanban=$(HERMES="$HERMES" "$HERMES" kanban list 2>/dev/null | tail -n +2 | wc -l)
kanban_names=$(HERMES="$HERMES" "$HERMES" kanban list 2>/dev/null | tail -n +2 | awk '{print $3}' | sort -u | tr '\n' ' ' | sed 's/ $//')
cron_jobs=$(HERMES="$HERMES" "$HERMES" cron list 2>/dev/null | tail -n +2 | wc -l)

# --- 3. Message (sortie standard, délivrée par le cronjob à Telegram) ---
cat <<EOF
★ STATUS — $(date '+%H:%M')
──────
🖥️  PC :
  • Charge (1/5/15) : ${load}
  • Uptime        : ${uptime}
  • Mémoire       : ${mem_used}/${mem_total} MB utilisés (free ${mem_free})
  • Swap          : ${swap}
  • Disque        : ${disk}
  • Température   : ${cpu_temp}
  • Interfaces    : ${net_ifs:-aucune}

📋 Sections :
  • Kanban  : ${kanban} tâches (${kanban_names:-aucune})
  • Cron    : ${cron_jobs} crontab
EOF
