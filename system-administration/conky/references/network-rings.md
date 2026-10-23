# Network circular graphs (Cairo-based)

## When to Use

Replace the linear `${downspeedgraph}` / `${upspeedgraph}` with circular rings.

## Rules (always on)

- **Cairo is required.** Install `libcairo2-dev` and, on Manjaro, `sudo pacman -S cairo`. Conky may not load if `cairo` is missing.
- **Cairo rings are drawn by a `conky_main()` function in `.conky_helper.lua`.** They run automatically during each draw cycle and require `cairo_xlib_surface_create` to render on the Conky window.
- **History buffer prevents "0" spikes.** The rings store a circular buffer (default size 30) of recent speed values and compute a max for scaling, so idle intervals do not shrink the rings to nothing.
- **The ring positions must match the expected text position** where the linear graphs previously appeared in the `NETWORK` section. Current working positions for a 380×400 panel:
   - download ring: `x=180, y=250`
   - upload ring: `x=260, y=250`
   - radius=25, thickness=4
- **Colors follow the same theme as the rest of the panel.** Colors can be overridden in the Lua helper via `NET_CONFIG.color_down/up` and `NET_CONFIG.bg_color`.

## Procedure

1. **Update the helper.** Add a `conky_main()` function in `~/.conky_helper.lua` that:
   - Creates a Cairo context with `cairo_xlib_surface_create()`
   - Draws rings with `draw_ring(cr, x, y, radius, thickness, value, max_value, color_hex)`
   - Cleans up with `cairo_destroy()` and `cairo_surface_destroy()`
   - Applies `cairo_set_line_cap()` and `cairo_set_line_join()` for smooth edges

2. **Modify the Conky config.** Replace `${downspeedgraph ...}` and `${upspeedgraph ...}` lines in `conky.text` with comments (or remove them) and ensure `lua_load = '/home/jhon/.conky_helper.lua'`.

3. **Place the rings.** The default positions are tuned for the existing "Down: X  Up: Y" text in the NETWORK section. If the rings appear too high, too low, or misaligned, adjust `NET_CONFIG.ring_down_x/y` and `NET_CONFIG.ring_up_x/y` (these are measured from the top-left of the Conky window).

4. **Test with a background Conky** (`conky -c ~/.conkyrc -d`) and watch the output for any `lua: ... error` messages. Common pitfalls:
   - No Cairo library → ring drawing fails silently; display as text if you cannot install Cairo
   - Variable needs interface → use `${downspeed wlp2s0}` (not `${downspeed}`)
   - Update interval is too short → history buffer never fills; use `update_interval = 1.0` or larger in `NET_CONFIG`

5. **Fine-tune after seeing results.** Once the rings appear but not where you want them, use screen-space coordinates: add a small `echo` script that reports the window X/Y for a pixel, or temporarily set ring positions to extreme values and observe the effect.

## Pitfalls

- **Cairo missing → silent failure.** The `conky_main()` function exists but draws nothing. Verify the install with `ldd $(which conky)` (show shared libs) or `conky -c ~/.conkyrc -d 2>&1 | grep "cairo"`. If missing, fall back to native Conky graph variables `${downspeedgraph}`/`${upspeedgraph}` (linear) and document the limitation.
- **Interface mismatch.** Use the correct interface name (e.g., `wlp2s0`). If all network variables are `0`, `iwconfig <iface>` will show the actual link quality.
- **Update interval too aggressive.** If the history buffer never gets a sample (`max_up/down` stay at 1.0), increase the network refresh rate (e.g., `${downspeed wlp2s0}` updates every second). Use `conky_main()` to enforce a custom `update_interval` for the Cairo drawing.
- **Overflow in history buffer.** If you have high throughput (> 1024 KiB/s), the history max calculation may need to accommodate larger numbers. Ensure `max_down/up` is computed as the maximum of all history samples plus a small margin (`+1.0`).
- **Thread-safety with Conky's built-in Lua.** Conky may spawn Lua multiple times. To avoid duplicate draws, use a simple `lock` mechanism (e.g., `if net_state.last_draw then return end`), or guard with a timestamp check: only allow a draw if enough time has elapsed.
- **Colors not matching the theme.** The color hex values (e.g., `0x88c0d0` for blue) must be in the same palette as the rest of Conky. If the ring color looks odd, compare with the `color1`, `color2` etc. in Conky config.

## Example Lua snippet (minimal)

```lua
local NET_CONFIG = {
    update_interval = 1.0, history_size = 30,
    ring_down_x = 180, ring_down_y = 250,
    ring_up_x   = 260, ring_up_y   = 250,
    ring_radius = 25, ring_thickness = 4,
    color_down = 0x88c0d0, color_up = 0xa3be8c,
    bg_color = 0x2e3440, bg_alpha = 0.3, fg_alpha = 0.8,
}

local net_state = { history_down = {}, history_up = {}, history_ptr = 0, max_down = 0.1, max_up = 0.1 }
for i = 0, NET_CONFIG.history_size - 1 do net_state.history_down[i] = 0.1; net_state.history_up[i] = 0.1 end

local function update_history()
    local down = tonumber(conky_parse('${downspeed wlp2s0}')) or 0
    local up   = tonumber(conky_parse('${upspeed wlp2s0}'))   or 0
    net_state.history_ptr = (net_state.history_ptr + 1) % NET_CONFIG.history_size
    net_state.history_down[net_state.history_ptr] = down
    net_state.history_up[net_state.history_ptr]   = up
    -- compute max with a small margin
    local max_down, max_up = 0.1, 0.1
    for i = 0, NET_CONFIG.history_size - 1 do
        if net_state.history_down[i] > max_down then max_down = net_state.history_down[i] end
        if net_state.history_up[i]   > max_up   then max_up   = net_state.history_up[i]   end
    end
    net_state.max_down, net_state.max_up = math.max(max_down, 1.0), math.max(max_up, 1.0)
end

function conky_main()
    if conky_window == nil then return end
    update_history()
    local cs = cairo_xlib_surface_create(conky_window.display, conky_window.drawable, conky_window.visual, conky_window.width, conky_window.height)
    if cs == nil then return end
    local cr = cairo_create(cs)
    if cr == nil then cairo_surface_destroy(cs); return end
    cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND); cairo_set_line_join(cr, CAIRO_LINE_JOIN_ROUND)
    -- helper function draw_ring omitted for brevity
    draw_ring(cr, NET_CONFIG.ring_down_x, NET_CONFIG.ring_down_y, NET_CONFIG.ring_radius, NET_CONFIG.ring_thickness, net_state.history_down[net_state.history_ptr], net_state.max_down, NET_CONFIG.color_down)
    draw_ring(cr, NET_CONFIG.ring_up_x, NET_CONFIG.ring_up_y, NET_CONFIG.ring_radius, NET_CONFIG.ring_thickness, net_state.history_up[net_state.history_ptr], net_state.max_up, NET_CONFIG.color_up)
    cairo_destroy(cr); cairo_surface_destroy(cs)
end
```

## Known working configuration

For the user’s current panel (1366×768, `top_right`, 380×400, `JetBrains Mono:size=9`, Nord colors):

```lua
local NET_CONFIG = {
    ring_down_x = 180, ring_down_y = 250,
    ring_up_x   = 260, ring_up_y   = 250,
    ring_radius = 25, ring_thickness = 4,
}
```

Place the rings where the linear graphs were, and the network section will display both text and circular speed bars simultaneously.

## References

- Conky Lua API documentation (Cairo bindings).
- The Mimod theme (`/home/jhon/Downloads/Mimod/scripts/rings.lua`) for initial Cairo ring drawing inspiration.
- Conky error logs (`[warn] [src/lua/...]`) for missing functions like `cairo_xlib_surface_create`.
