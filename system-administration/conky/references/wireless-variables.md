# Native Conky Wireless Variables

All native Conky Wi-Fi variables **require the interface name** as a literal argument. They do not auto-detect.

| Variable | Description | Example |
|---|---|---|
| `${wireless_essid <iface>}` | SSID of the connected network | `${wireless_essid wlp2s0}` → `MyWiFi` |
| `${wireless_bitrate <iface>}` | Current link bitrate | `${wireless_bitrate wlp2s0}` → `325 Mb/s` |
| `${wireless_link_qual <iface>}` | Raw link quality (numerator/denominator) | `${wireless_link_qual wlp2s0}` → `45/70` |
| `${wireless_link_qual_perc <iface>}` | Link quality as percentage (0–100) | `${wireless_link_qual_perc wlp2s0}%` → `64%` |
| `${wireless_link_bar <iface> <h>,<w>}` | Progress-bar visual for signal | `${wireless_link_bar wlp2s0 10,100}` |
| `${downspeed <iface>}` | Current download speed | `${downspeed wlp2s0}` → `1.2 MiB/s` |
| `${upspeed <iface>}` | Current upload speed | `${upspeed wlp2s0}` → `0.3 MiB/s` |
| `${downspeedf <iface>}` | Download speed as float (KiB/s) | `${downspeedf wlp2s0}` → `1250.0` |
| `${upspeedf <iface>}` | Upload speed as float (KiB/s) | `${upspeedf wlp2s0}` → `300.0` |
| `${totaldown <iface>}` | Cumulative downloaded since boot | `${totaldown wlp2s0}` → `1.2 GiB` |
| `${totalup <iface>}` | Cumulative uploaded since boot | `${totalup wlp2s0}` → `300 MiB` |
| `${downspeedgraph <iface> <h>,<w> <in> <out> -t}` | Download graph | `${downspeedgraph wlp2s0 20,100 88c0d0 81a1c1 -t}` |
| `${upspeedgraph <iface> <h>,<w> <in> <out> -t}` | Upload graph | `${upspeedgraph wlp2s0 20,100 a3be8c b48ead -t}` |

## libiw fallback

If native variables return empty/blank but `iwconfig` shows data, Conky was built without `libiw`. Use `execi` with `iwconfig` instead:

```lua
${execi 5 iwconfig wlp2s0 | grep 'Bit Rate' | awk '{print $2}' | tr -d 'Mb/s'}
${execi 5 iwconfig wlp2s0 | grep 'Signal level' | awk '{print $4}' | sed 's/dBm//'}
${execi 5 iwgetid -r}
```

## Verification commands

```bash
ip link | grep -E '^[0-9]+: (w|wl)'          # detect wireless interface
iwconfig wlp2s0                               # check signal/bitrate/ESSID
conky -c /dev/stdin <<'EOF'
conky.config = {}
conky.text = [[${wireless_link_qual_perc wlp2s0}%]]
EOF 2>&1 | head -5
```