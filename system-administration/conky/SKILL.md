---
name: conky
description: Configure the Conky desktop widget and system-monitor panel.
---

# Conky — desktop widget configuration

Build and maintain a Conky monitor panel. The goal is a working panel on first try, with values that actually update.

## When to Use

- The user wants a desktop system monitor (Conky) showing CPU, RAM, disk, network, and/or GPU.
- Existing Conky output is empty, wrong, or showing `0` where data should be.
- The user reports a specific field not displaying.

## Rules (always on)

- **Prefer native Conky variables over Lua for data fields.** Variables like `${downspeed wlp2s0}`, `${fs_used /}`, `${mem}`, `${swap}` render immediately and update every interval. Lua is only for formatting/labels that Conky cannot produce (e.g., uptime in human form).
- **Every Conky variable that tracks an interface or mount takes the target as a literal argument.** Network fields use the interface name (`downspeed wlp2s0`, `wireless_essid wlp2s0`, `wireless_bitrate wlp2s0`); disk fields take the path (`fs_used /`, `fs_used /home`).
- **Lua function calls have NO parentheses and NO underscore-prefixed name** — write `${lua format_uptime}`, not `${lua format_uptime()}` and not `${lua conky_format_uptime}`. Conky auto-attaches the `conky_` prefix.
- **Always validate a variable in isolation** before adding it to the panel: copy just that line into a tiny `test.conf` with `default_color = '#ffffff'` and `background = false`, then run `conky -c test.conf 2>&1 | grep -iE 'warn|error|nil|failed'`.
- **Answer in Spanish (neutral Latin American, no voseo)** when the user communicates in Spanish.
- **Give the fix, not the process.** State which line changed, show the corrected line, and a one-line reason.

## The minimal working panel

```lua
conky.config = {
    alignment = 'top_right',
    gap_x = 20, gap_y = 20,
    minimum_width = 380, minimum_height = 400,
    own_window = true, own_window_type = 'desktop',
    own_window_colour = '#00000000',
    own_window_hints = 'undecorated,below,sticky,skip_taskbar,skip_pager',
    background = false, border_width = 0,
    default_color = '#ffffff', use_xft = true,
    font = 'JetBrains Mono:size=9', xftalpha = 0.9,
    update_interval = 1.0, double_buffer = true,
};

conky.text = [[
${color1}${font JetBrains Mono:bold:size=14}SYSTEM${font}${color}
${hr 1}
${color7}Host:${color0} $nodename
${color7}Kernel:${color0} $kernel
${color7}Uptime:${color0} ${lua format_uptime}
${color7}Arch:${color0} ${execi 3600 uname -m}

${color1}${font JetBrains Mono:bold:size=14}CPU${font}${color}
${hr 1}
${color7}Model:${color0} ${execi 3600 lscpu | awk '/^Model name:/ {sub(/^Model name:[ ]*/, ""); print}'}
${color7}Cores:${color0} ${nproc}
${color7}Load:${color0} ${loadavg}

${color1}${font JetBrains Mono:bold:size=14}MEMORY${font}${color}
${hr 1}
${color7}RAM:${color0} ${mem} / ${memmax} ${membar 6,180}
${color7}Swap:${color0} ${swap} / ${swapmax} ${swapbar 6,180}

${color1}${font JetBrains Mono:bold:size=14}DISK${font}${color}
${hr 1}
${color7}Root:${color0} ${fs_used /} / ${fs_size /} ${fs_bar 6,180 /}
${color7}Home:${color0} ${fs_used /home} / ${fs_size /home} ${fs_bar 6,180 /home}
${color7}Disk I/O:${color0} ${diskio_read} / ${diskio_write}

${color1}${font JetBrains Mono:bold:size=14}NETWORK${font}${color}
${hr 1}
${color7}Interface:${color0} ${execi 5 ip route get 8.8.8.8 | awk '/dev/ {print $5}'}
${color7}ESSID:${color0} ${wireless_essid wlp2s0}
${color7}Signal:${color0} ${wireless_link_qual_perc wlp2s0}%
${color7}Speed:${color0} ${wireless_bitrate wlp2s0}
${color7}Down:${color0} ${downspeed wlp2s0}  ${color7}Up:${color0} ${upspeed wlp2s0}
${downspeedgraph wlp2s0 20,100 88c0d0 81a1c1 -t} ${upspeedgraph wlp2s0 20,100 a3be8c b48ead -t}
${color7}Total: ${color0} ${totaldown wlp2s0}  ${color7}|  ${color0} ${totalup wlp2s0}

${color1}${font JetBrains Mono:bold:size=14}GPU${font}${color}
${hr 1}
${color7}GPU:${color0} ${execi 3600 lspci -nn | grep -i "VGA compatible controller" | cut -d ':' -f3- | sed 's/^ *//' | head -1 || echo "Unknown GPU"}
${color7}Temp:${color0} ${lua conky_format_gpu_temp}°C
]]
```

## Step-by-step procedure

1. **Detect the wireless interface.** `ip link | grep -E '^[0-9]+: (w|wl)'`. Use that name everywhere; `conky` cannot guess it for you.
2. **Write `conkyrc` to `~/.conkyrc`** and `conky -c ~/.conkyrc -d`, then watch for `[warn]` in output.
3. **If a field shows `0` or blank**, determine why: it may be genuinely idle, or the variable needs an argument.
4. **Rebuild Conky after any Lua change** — clear the cache and restart, because Conky does not hot-reload Lua.
5. **Use `-d` for background daemon mode** or run `conky -c ~/.conkyrc` in foreground to read diagnostics.

## Pitfalls

- **The Disk I/O line shows `0 / 0` on an idle system** — `${diskio_read}` and `${diskio_write}` measure bytes transferred *between updates*, not throughput. On a quiet desktop this is normal and healthy. To test it, generate I/O (`dd if=/dev/zero of=/tmp/bench bs=1M count=100`) and watch the line move.
- **`loadavg` can read `0.00 0.00 0.00` and still be correct** — it is a *waiting-process* counter, not CPU utilization. Zero means the run queue is empty. Do not treat it as a broken field.
- **`${execi N}` runs the shell command once every N seconds** instead of every update. Use `execi 5` for network/disk info and `execi 3600` for static facts (model, arch), or Conky re-spawns `lscpu`/`nvidia-smi` every second and the panel jitter-wobbles.
- **A `conky: cannot open /home/jhon/.conkyrc` error means the shell never expanded `~`.** Always use the absolute path `~/.conkyrc` when passing it, or write the config to `$HOME/conkyrc` and reference `$HOME/...`.
- **`own_window_transparent` is deprecated** in modern Conky; use `own_window_colour = '#00000000'` with an alpha of `00`.
- **`invalid CPU number '(null)', falling back to CPU 1`** comes from `${cpugraph}` / `${freq_g}` on newer Conky builds. Drop the graph and frequency fields; use plain `${cpu cpu0}%` if you need per-core numbers.
- **Wireless fields need libiw.** On distros that dropped libiw, `${wireless_essid /wireless_bitrate /wireless_link_qual_perc}` silently resolve to empty. If all three are blank but `iwconfig` shows data, Conky cannot read the interface — fall back to `execi 5 iwconfig <iface> | grep 'Bit Rate\|Signal level\|ESSID'`.
- **GPU section must use `lspci` + `sensors` for Intel integrated graphics, not `nvidia-smi`.** When there is no NVIDIA GPU, the `nvidia-smi` commands fail silently. Replace with `execi 3600 lspci -nn | grep -i 'VGA compatible controller' | cut -d ':' -f3- | sed 's/^ *//' | head -1` for the model and `sensors | grep -A1 'temp1:' | tail -1 | awk '{print $2}' | tr -d '+°C'` for temperature. The Intel GPU temp path `/sys/class/drm/card0/device/hwmon/*/temp1_input` is not always present.

## Troubleshooting decision tree

| Symptom | Check | Fix |
|---|---|---|
| `loadavg` is `0.00` | `uptime` shows load | Correct display; nothing wrong |
| Disk I/O is `0 / 0` | `iostat -d 1` shows activity | Expected when idle; test with `dd` |
| Speed/signal show `0` | `ip -s link show <iface>` shows packets | Wait one interval; if still 0, libiw missing |
| Wireless fields blank | `iwconfig` has values | libiw missing → use `execi 5 iwconfig` |
| Lua function `nil` | wrong name or `()` in text | Call as `${lua format_name}` |
| Field renders as `0` | variable needs target | Add interface/path argument |

## Support files

- `references/wireless-variables.md` — full native Conky Wi-Fi variable table and the libiw fallback.
- `scripts/test_conf.sh` — quick validator: writes a minimal config, runs Conky, and reports warnings/errors.
- `references/network-rings.md` — Cairo-based circular network graphs with history buffer, positions, and scaling.
