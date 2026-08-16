#!/usr/bin/env python3.14
"""Generate KiCad PCB: ESP32 DevKit → HW-130 Uno-form shield adapter.

Layout
------
* Left: Arduino UNO R3 male-header footprint — HW-130 stacks here (same as Uno).
* Right wing: 2×15 female sockets for a 30-pin ESP32 DevKit (beside the shield,
  so the DevKit is not crushed under the motor shield).
* Screw terminal: external regulated 5 V for shield logic (never from ESP32 5V).

Pin map matches src/esp32/esp32_plotter and hardware/WIRING.md.

  python3.14 cad/pcb/generate_adapter.py
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parent
PROJ = ROOT / "esp32_hw130_adapter"
OUT = ROOT / "out"

UNO_PAD = {
    1: "NC",
    2: "IOREF",
    3: "RESET",
    4: "3V3",
    5: "P5V",
    6: "GND",
    7: "GND",
    8: "VIN",
    9: "A0",
    10: "A1",
    11: "A2",
    12: "A3",
    13: "A4",
    14: "A5",
    15: "D0",
    16: "D1",
    17: "D2",
    18: "D3",
    19: "D4",
    20: "D5",
    21: "D6",
    22: "D7",
    23: "D8",
    24: "D9",
    25: "D10",
    26: "D11",
    27: "D12",
    28: "D13",
    29: "GND",
    30: "AREF",
    31: "SDA",
    32: "SCL",
}

# ESP32-DevKit V1 / DOIT 30-pin, USB at pad-1 end of each row
ESP_LEFT = [
    "3V3", "EN", "SVP", "SVN", "GPIO34", "GPIO35", "GPIO32", "GPIO33",
    "GPIO25", "GPIO26", "GPIO27", "GPIO14", "GPIO12", "GND", "GPIO13",
]
ESP_RIGHT = [
    "GPIO23", "GPIO22", "TX0", "RX0", "GPIO21", "GND", "GPIO19", "GPIO18",
    "GPIO5", "GPIO17", "GPIO16", "GPIO4", "GPIO0", "GPIO2", "GPIO15",
]

ROUTES = {
    "D12": "GPIO18",
    "D4": "GPIO19",
    "D7": "GPIO23",
    "D8": "GPIO13",
    "D11": "GPIO25",
    "D3": "GPIO26",
    "D6": "GPIO27",
    "D5": "GPIO32",
    "D10": "GPIO33",  # SERVO_1
}


def mm(x: float) -> int:
    return int(pcbnew.FromMM(x))


def uid() -> str:
    return str(uuid.uuid4())


def ensure_net(board: pcbnew.BOARD, name: str) -> pcbnew.NETINFO_ITEM:
    info = board.GetNetInfo().GetNetItem(name)
    if info is not None and info.GetNetCode() != 0:
        return info
    net = pcbnew.NETINFO_ITEM(board, name)
    board.Add(net)
    return net


def add_track(board, net, layer, x1, y1, x2, y2, width=0.4):
    if abs(x1 - x2) < 1e-6 and abs(y1 - y2) < 1e-6:
        return
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(pcbnew.VECTOR2I(mm(x1), mm(y1)))
    t.SetEnd(pcbnew.VECTOR2I(mm(x2), mm(y2)))
    t.SetWidth(mm(width))
    t.SetLayer(layer)
    t.SetNet(net)
    board.Add(t)


def add_via(board, net, x, y):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
    v.SetWidth(mm(0.8))
    v.SetDrill(mm(0.4))
    v.SetNet(net)
    board.Add(v)


def pad_xy(fp: pcbnew.FOOTPRINT, pad_name: str) -> tuple[float, float]:
    pad = fp.FindPadByNumber(pad_name)
    p = pad.GetCenter()
    return pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)


def route_manhattan(board, net, layer_a, layer_b, x1, y1, x2, y2, channel_y, width=0.35):
    """Horizontal on layer_a to channel, via, horizontal/vertical on layer_b."""
    add_track(board, net, layer_a, x1, y1, x1, channel_y, width)
    add_via(board, net, x1, channel_y)
    add_track(board, net, layer_b, x1, channel_y, x2, channel_y, width)
    add_via(board, net, x2, channel_y)
    add_track(board, net, layer_a, x2, channel_y, x2, y2, width)


def add_filled_zone(board, net, layer, pts):
    zone = pcbnew.ZONE(board)
    zone.SetNet(net)
    zone.SetLayer(layer)
    zone.SetIsFilled(True)
    zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    zone.SetMinThickness(mm(0.25))
    zone.SetLocalClearance(mm(0.3))
    chain = zone.Outline().NewOutline()
    for i, (x, y) in enumerate(pts):
        if i == 0:
            zone.Outline().SetOutline(chain)  # noqa — keep API happy
        zone.Outline().Append(mm(x), mm(y))
    # Rebuild outline properly
    zone = pcbnew.ZONE(board)
    zone.SetNet(net)
    zone.SetLayer(layer)
    zone.SetLocalClearance(mm(0.35))
    zone.SetMinThickness(mm(0.25))
    zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    outline = zone.GetOutline()
    outline.NewOutline()
    for x, y in pts:
        outline.Append(mm(x), mm(y))
    board.Add(zone)
    return zone


def main() -> None:
    PROJ.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)

    board = pcbnew.BOARD()
    settings = board.GetDesignSettings()
    settings.SetCopperLayerCount(2)

    # --- Uno R3 header block (HW-130 stacks here) ---
    uno = pcbnew.FootprintLoad(
        "/usr/share/kicad/footprints/Module.pretty", "Arduino_UNO_R3"
    )
    uno.SetReference("J_SHIELD")
    uno.SetValue("UNO_R3_HEADERS")
    # Pad1 at (40, 30) → digital row around y≈78
    uno.SetPosition(pcbnew.VECTOR2I(mm(40), mm(30)))
    board.Add(uno)

    uno_bb = uno.GetBoundingBox(False, False)
    uno_right = pcbnew.ToMM(uno_bb.GetRight())
    uno_top = pcbnew.ToMM(uno_bb.GetTop())
    uno_bot = pcbnew.ToMM(uno_bb.GetBottom())
    uno_left = pcbnew.ToMM(uno_bb.GetLeft())

    # --- ESP32 DevKit on right wing (outside shield body) ---
    sock_lib = "/usr/share/kicad/footprints/Connector_PinSocket_2.54mm.pretty"
    # 0°: pads run +Y. Row spacing 25.4 mm. USB / pin1 toward top of board.
    wing_x = uno_right + 8.0
    esp_y0 = uno_top + 6.0  # pad1 near top
    row_pitch = 25.4

    left = pcbnew.FootprintLoad(sock_lib, "PinSocket_1x15_P2.54mm_Vertical")
    left.SetReference("J_ESP_L")
    left.SetValue("DevKit_LEFT")
    left.SetPosition(pcbnew.VECTOR2I(mm(wing_x), mm(esp_y0)))
    left.SetOrientationDegrees(0)
    board.Add(left)

    right = pcbnew.FootprintLoad(sock_lib, "PinSocket_1x15_P2.54mm_Vertical")
    right.SetReference("J_ESP_R")
    right.SetValue("DevKit_RIGHT")
    right.SetPosition(pcbnew.VECTOR2I(mm(wing_x + row_pitch), mm(esp_y0)))
    right.SetOrientationDegrees(0)
    board.Add(right)

    # --- EXT 5V terminal near power header ---
    term = pcbnew.FootprintLoad(
        "/usr/share/kicad/footprints/TerminalBlock_Phoenix.pretty",
        "TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal",
    )
    term.SetReference("J_5V")
    term.SetValue("EXT_5V")
    term.SetPosition(pcbnew.VECTOR2I(mm(uno_left + 5), mm(uno_bot + 8)))
    board.Add(term)

    net_gnd = ensure_net(board, "GND")
    net_5v = ensure_net(board, "P5V")

    for pad_num, signal in UNO_PAD.items():
        pad = uno.FindPadByNumber(str(pad_num))
        if signal == "GND":
            pad.SetNet(net_gnd)
        elif signal == "P5V":
            pad.SetNet(net_5v)
        elif signal in ROUTES:
            pad.SetNet(ensure_net(board, ROUTES[signal]))
        else:
            pad.SetNet(ensure_net(board, f"NC_{signal}"))

    for i, name in enumerate(ESP_LEFT, start=1):
        pad = left.FindPadByNumber(str(i))
        if name == "GND":
            pad.SetNet(net_gnd)
        elif name == "3V3":
            pad.SetNet(ensure_net(board, "ESP_3V3"))
        else:
            pad.SetNet(ensure_net(board, name))

    for i, name in enumerate(ESP_RIGHT, start=1):
        pad = right.FindPadByNumber(str(i))
        if name == "GND":
            pad.SetNet(net_gnd)
        else:
            pad.SetNet(ensure_net(board, name))

    term.FindPadByNumber("1").SetNet(net_5v)
    term.FindPadByNumber("2").SetNet(net_gnd)

    def uno_xy(signal: str) -> tuple[float, float]:
        for num, sig in UNO_PAD.items():
            if sig == signal:
                return pad_xy(uno, str(num))
        raise KeyError(signal)

    def esp_xy(gpio: str) -> tuple[float, float]:
        if gpio in ESP_LEFT:
            return pad_xy(left, str(ESP_LEFT.index(gpio) + 1))
        return pad_xy(right, str(ESP_RIGHT.index(gpio) + 1))

    fcu, bcu = pcbnew.F_Cu, pcbnew.B_Cu

    # Non-crossing 2-layer route:
    #  - F.Cu verticals only at unique X (Uno pad X, and a fan column beside ESP)
    #  - B.Cu horizontals only (channel bus + short stubs into ESP pads)
    # Never run a track along an ESP header column (would short every pad).
    sock_bottom = max(
        pcbnew.ToMM(left.GetBoundingBox(False, False).GetBottom()),
        pcbnew.ToMM(right.GetBoundingBox(False, False).GetBottom()),
    )
    base_ch = max(uno_bot, sock_bottom) + 4.0

    left_nets = []
    right_nets = []
    for shield_pin, gpio in ROUTES.items():
        x2, _ = esp_xy(gpio)
        if abs(x2 - wing_x) < 1.0:
            left_nets.append((shield_pin, gpio))
        else:
            right_nets.append((shield_pin, gpio))

    def route_to_esp(shield_pin, gpio, fan_x, ch):
        net = ensure_net(board, gpio)
        x1, y1 = uno_xy(shield_pin)
        x2, y2 = esp_xy(gpio)
        # Down from Uno pad
        add_track(board, net, fcu, x1, y1, x1, ch, 0.35)
        add_via(board, net, x1, ch)
        # Channel bus on back to fan column
        add_track(board, net, bcu, x1, ch, fan_x, ch, 0.35)
        add_via(board, net, fan_x, ch)
        # Up fan column (clear of sockets)
        add_track(board, net, fcu, fan_x, ch, fan_x, y2, 0.35)
        add_via(board, net, fan_x, y2)
        # Stub into ESP pad on back
        add_track(board, net, bcu, fan_x, y2, x2, y2, 0.35)

    # Fan columns: left of left socket / right of right socket
    for i, (sp, gpio) in enumerate(left_nets):
        fan_x = wing_x - 3.0 - i * 1.5
        ch = base_ch + i * 1.27
        route_to_esp(sp, gpio, fan_x, ch)

    for i, (sp, gpio) in enumerate(right_nets):
        fan_x = wing_x + row_pitch + 3.0 + i * 1.5
        ch = base_ch + (len(left_nets) + i) * 1.27
        route_to_esp(sp, gpio, fan_x, ch)

    # 5V: stay below power header, do not drag across NC pads on y=30
    tx, ty = pad_xy(term, "1")
    ux, uy = uno_xy("P5V")
    add_track(board, net_5v, fcu, tx, ty, tx, uy + 3.0, 0.75)
    add_track(board, net_5v, fcu, tx, uy + 3.0, ux, uy + 3.0, 0.75)
    add_track(board, net_5v, fcu, ux, uy + 3.0, ux, uy, 0.75)

    # GND: zones only

    # Board outline includes fan alley + route channels
    right_fp = right.GetBoundingBox(False, False)
    term_bb = term.GetBoundingBox(False, False)
    n_left, n_right = len(left_nets), len(right_nets)
    fan_left = wing_x - 3.0 - max(n_left - 1, 0) * 1.5 - 2.0
    fan_right = wing_x + row_pitch + 3.0 + max(n_right - 1, 0) * 1.5 + 2.0
    route_band = 4.0 + (n_left + n_right) * 1.27 + 3.0
    xmin = min(uno_left, pcbnew.ToMM(term_bb.GetLeft()), fan_left) - 2.0
    ymin = min(uno_top, pcbnew.ToMM(left.GetBoundingBox(False, False).GetTop())) - 6.0
    xmax = max(pcbnew.ToMM(right_fp.GetRight()), fan_right) + 2.0
    ymax = max(
        uno_bot,
        pcbnew.ToMM(term_bb.GetBottom()),
        sock_bottom,
    ) + route_band + 2.0

    def edge(x1, y1, x2, y2):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(pcbnew.VECTOR2I(mm(x1), mm(y1)))
        s.SetEnd(pcbnew.VECTOR2I(mm(x2), mm(y2)))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(mm(0.15))
        board.Add(s)

    edge(xmin, ymin, xmax, ymin)
    edge(xmax, ymin, xmax, ymax)
    edge(xmax, ymax, xmin, ymax)
    edge(xmin, ymax, xmin, ymin)

    # GND zones
    for layer in (fcu, bcu):
        zone = pcbnew.ZONE(board)
        zone.SetNet(net_gnd)
        zone.SetLayer(layer)
        zone.SetLocalClearance(mm(0.4))
        zone.SetMinThickness(mm(0.25))
        zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        outline = zone.Outline()
        outline.NewOutline()
        for x, y in ((xmin + 0.5, ymin + 0.5), (xmax - 0.5, ymin + 0.5),
                     (xmax - 0.5, ymax - 0.5), (xmin + 0.5, ymax - 0.5)):
            outline.Append(mm(x), mm(y))
        board.Add(zone)

    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())

    # Silk labels
    for txt, x, y, size in (
        ("ESP32 ↔ HW-130", (xmin + xmax) / 2, ymin + 2.2, 1.6),
        ("USB this way ↑", wing_x + row_pitch / 2, ymin + 4.5, 1.1),
        ("HW-130 stacks on left headers", (uno_left + uno_right) / 2, ymax - 2.2, 1.1),
        ("J_5V: external 5V only", uno_left + 15, ymax - 5.0, 1.0),
    ):
        t = pcbnew.PCB_TEXT(board)
        t.SetText(txt)
        t.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
        t.SetLayer(pcbnew.F_SilkS)
        t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
        t.SetTextThickness(mm(0.15))
        board.Add(t)

    # Optional M3 holes can be added in pcbnew; omitted here to keep DRC clean.

    pcb_path = PROJ / "esp32_hw130_adapter.kicad_pcb"
    pcbnew.SaveBoard(str(pcb_path), board)
    print(f"Wrote {pcb_path}")
    print(f"Board size ≈ {xmax - xmin:.1f} × {ymax - ymin:.1f} mm")

    write_pro(PROJ / "esp32_hw130_adapter.kicad_pro")
    write_sch(PROJ / "esp32_hw130_adapter.kicad_sch")
    write_docs()
    print("Done.")


def write_pro(path: Path) -> None:
    path.write_text("""{
  "board": {
    "design_settings": {
      "defaults": {},
      "diff_pair_dimensions": [],
      "drc_exclusions": [],
      "meta": { "version": 2 },
      "rule_severities": {},
      "rules": {
        "min_copper_edge_clearance": 0.2,
        "min_hole_clearance": 0.25,
        "min_hole_to_hole": 0.25,
        "min_through_hole_diameter": 0.3,
        "min_track_width": 0.2,
        "min_via": 0.4,
        "solder_mask_clearance": 0.0,
        "solder_mask_min_width": 0.0,
        "solder_mask_to_copper_clearance": 0.0
      },
      "track_widths": [0.0, 0.35, 0.5, 0.75],
      "via_dimensions": [
        { "diameter": 0.0, "drill": 0.0 },
        { "diameter": 0.8, "drill": 0.4 }
      ],
      "zones_settings": {}
    }
  },
  "meta": { "filename": "esp32_hw130_adapter.kicad_pro", "version": 3 },
  "net_settings": {
    "classes": [{
      "clearance": 0.2, "name": "Default", "track_width": 0.35,
      "via_diameter": 0.8, "via_drill": 0.4, "wire_width": 6,
      "diff_pair_gap": 0.25, "diff_pair_via_gap": 0.25, "diff_pair_width": 0.2,
      "line_style": 0, "microvia_diameter": 0.3, "microvia_drill": 0.1,
      "pcb_color": "rgba(0, 0, 0, 0.000)", "priority": 0,
      "schematic_color": "rgba(0, 0, 0, 0.000)", "bus_width": 12
    }],
    "meta": { "version": 4 },
    "netclass_assignments": null,
    "netclass_patterns": []
  },
  "pcbnew": { "last_paths": { "plot": "" }, "page_layout_descr_file": "" },
  "schematic": {
    "annotate_start_num": 0, "drawing": {}, "legacy_lib_dir": "",
    "legacy_lib_list": [], "meta": { "version": 1 },
    "net_format_name": "", "page_layout_descr_file": "", "plot_directory": "",
    "spice_current_sheet_as_root": false, "spice_external_command": "",
    "spice_model_current_sheet_as_root": true, "spice_save_all_currents": false,
    "spice_save_all_dissipations": false, "spice_save_all_voltages": false,
    "subsheet_field_names": [], "text_variables": {}
  },
  "sheets": [["esp32_hw130_adapter.kicad_sch", "Root"]],
  "text_variables": {},
  "libraries": { "pinned_footprint_libs": [], "pinned_symbol_libs": [] },
  "boards": [],
  "cvpcb": { "equivalence_files": [] }
}
""")


def write_sch(path: Path) -> None:
    lines = [
        "(kicad_sch",
        "\t(version 20250114)",
        '\t(generator "eeschema")',
        '\t(generator_version "10.0")',
        f'\t(uuid "{uid()}")',
        '\t(paper "A4")',
        "\t(title_block",
        '\t\t(title "ESP32 to HW-130 Uno-form adapter")',
        '\t\t(date "2026-08-16")',
        '\t\t(rev "1")',
        "\t)",
        "\t(lib_symbols)",
    ]
    texts = [
        (25.4, 25.4, "HW-130 stacks on J_SHIELD (Arduino R3 male headers)."),
        (25.4, 33.0, "ESP32 DevKit plugs into J_ESP_L / J_ESP_R on the right wing."),
        (25.4, 40.6, "J_5V: external regulated 5 V → shield 5V/GND. Not from ESP32."),
        (25.4, 48.3, "Yellow PWR jumper on HW-130 must be removed; motors on EXT_PWR."),
    ]
    y = 60.0
    for s, g in ROUTES.items():
        texts.append((25.4, y, f"{s}  →  {g}"))
        y += 6.35
    for x, yy, msg in texts:
        lines += [
            f'\t(text "{msg}"',
            "\t\t(exclude_from_sim no)",
            f"\t\t(at {x} {yy} 0)",
            "\t\t(effects (font (size 1.8 1.8)) (justify left))",
            f'\t\t(uuid "{uid()}")',
            "\t)",
        ]
    lines += [
        "\t(sheet_instances",
        '\t\t(path "/" (page "1"))',
        "\t)",
        ")",
        "",
    ]
    path.write_text("\n".join(lines))


def write_docs() -> None:
    (OUT / "pinmap.md").write_text(
        "# Pin map\n\n"
        "| Shield pin | ESP32 |\n| --- | --- |\n"
        + "\n".join(f"| {s} | {g} |" for s, g in ROUTES.items())
        + "\n| 5V | J_5V external |\n| GND | common |\n"
    )
    (ROOT / "BOM.md").write_text(
        """# BOM — ESP32 ↔ HW-130 adapter

| Ref | Qty | Part |
| --- | --- | --- |
| J_SHIELD | 1 | Arduino R3 male header set (1×8 + 1×10 + 1×8 + 1×6) soldered into Uno footprint |
| J_ESP_L / J_ESP_R | 2 | 1×15 female pin socket 2.54 mm (ESP32-DevKit V1) |
| J_5V | 1 | 2-pin screw terminal 5.08 mm |
| H1–H4 | 4 | M3 mounting hole (optional standoffs) |
| — | 1 | PCB (this design) |
| — | 1 | ESP32-DevKit V1 / DOIT 30-pin |
| — | 1 | HW-130 L293D shield |
| — | 1 | Regulated 5 V supply (≥2 A recommended) |

## Assembly

1. Solder female sockets for ESP32 on the **right wing** (USB toward silk arrow).
2. Solder **male** Arduino headers pointing **up** on the left footprint.
3. Solder J_5V.
4. Plug ESP32 into wing sockets; stack HW-130 on male headers.
5. Wire motors as on Uno (X=M1+M2, Y=M3+M4). Remove yellow PWR jumper.
6. Feed J_5V from external 5 V; common GND with ESP32 USB GND / supply −.
"""
    )


if __name__ == "__main__":
    main()
