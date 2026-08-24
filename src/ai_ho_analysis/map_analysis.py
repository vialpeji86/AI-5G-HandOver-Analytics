from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import html
import json
import zipfile
from typing import Dict

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class MapProfile:
    name: str
    top_n: int
    metric: str
    long_only: bool = False
    min_attempts: int = 0


MAP_PROFILES: Dict[str, MapProfile] = {
    "Top 10 Long HO Attempts": MapProfile("Top 10 Long HO Attempts", top_n=10, metric="Attempts", long_only=True),
    "Top 10 HO Fails": MapProfile("Top 10 HO Fails", top_n=10, metric="Failures"),
    "Top 5 HO Fails": MapProfile("Top 5 HO Fails", top_n=5, metric="Failures"),
    "Top 10 Longest Distance": MapProfile("Top 10 Longest Distance", top_n=10, metric="Distance_km"),
    "Top 15 HO Attempts": MapProfile("Top 15 HO Attempts", top_n=15, metric="Attempts"),
    "Top 10 Fail Rate (min 20 att)": MapProfile(
        "Top 10 Fail Rate (min 20 att)", top_n=10, metric="Fail_Rate", min_attempts=20
    ),
}


def _apply_profile(df: pd.DataFrame, profile_name: str) -> pd.DataFrame:
    if profile_name not in MAP_PROFILES:
        raise ValueError(f"Unknown map profile: {profile_name}")
    p = MAP_PROFILES[profile_name]
    out = df.copy()
    out = out[out["src_lat"].notna() & out["src_lon"].notna() & out["tgt_lat"].notna() & out["tgt_lon"].notna()]
    if p.long_only:
        out = out[out["Distance_km"] >= 5]
    if p.min_attempts > 0 and "Attempts" in out.columns:
        out = out[pd.to_numeric(out["Attempts"], errors="coerce").fillna(0) >= p.min_attempts]
    out = out.sort_values(p.metric, ascending=False, na_position="last").head(p.top_n).copy()
    out["Rank"] = np.arange(1, len(out) + 1)
    return out


def _kml_escape(v: object) -> str:
    return html.escape("" if v is None else str(v))


def _build_kml(df: pd.DataFrame, profile_name: str) -> str:
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<kml xmlns="http://www.opengis.net/kml/2.2">',
        "<Document>",
        f"<name>{_kml_escape(profile_name)}</name>",
    ]
    for _, r in df.iterrows():
        src_name = _kml_escape(r.get("Source_Site", r.get("Source_DU", "Source")))
        tgt_name = _kml_escape(r.get("Target_Site", r.get("Target_DU", "Target")))
        att = _kml_escape(r.get("Attempts", ""))
        fai = _kml_escape(r.get("Failures", ""))
        dist = _kml_escape(f"{float(r.get('Distance_km', np.nan)):.2f} km" if pd.notna(r.get("Distance_km", np.nan)) else "")
        src_lat = float(r["src_lat"])
        src_lon = float(r["src_lon"])
        tgt_lat = float(r["tgt_lat"])
        tgt_lon = float(r["tgt_lon"])
        desc = f"Attempts: {att} | Failures: {fai} | Distance: {dist}"

        parts.extend(
            [
                "<Placemark>",
                f"<name>{src_name}</name>",
                f"<description>{_kml_escape(desc)}</description>",
                f"<Point><coordinates>{src_lon},{src_lat},0</coordinates></Point>",
                "</Placemark>",
                "<Placemark>",
                f"<name>{tgt_name}</name>",
                f"<description>{_kml_escape(desc)}</description>",
                f"<Point><coordinates>{tgt_lon},{tgt_lat},0</coordinates></Point>",
                "</Placemark>",
                "<Placemark>",
                f"<name>{src_name} -> {tgt_name}</name>",
                f"<description>{_kml_escape(desc)}</description>",
                "<LineString>",
                "<tessellate>1</tessellate>",
                f"<coordinates>{src_lon},{src_lat},0 {tgt_lon},{tgt_lat},0</coordinates>",
                "</LineString>",
                "</Placemark>",
            ]
        )
    parts.extend(["</Document>", "</kml>"])
    return "\n".join(parts)


def export_profile_kmz(relation_detail: pd.DataFrame, profile_name: str, out_kmz: str | Path) -> Path:
    selected = _apply_profile(relation_detail, profile_name)
    if selected.empty:
        raise ValueError("No rows available for this map profile.")
    out = Path(out_kmz)
    out.parent.mkdir(parents=True, exist_ok=True)
    kml = _build_kml(selected, profile_name)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("doc.kml", kml)
    return out


def build_profile_map_html(
    relation_detail: pd.DataFrame,
    profile_name: str,
    out_html: str | Path,
) -> Path:
    selected = _apply_profile(relation_detail, profile_name)
    if selected.empty:
        raise ValueError("No rows available for this map profile.")

    source_group = selected.groupby(["Source_DU", "src_lat", "src_lon"], as_index=False)["Attempts"].sum()
    src_row = source_group.sort_values("Attempts", ascending=False).iloc[0]
    center_lat = float(src_row["src_lat"])
    center_lon = float(src_row["src_lon"])
    source_du_center = str(int(src_row["Source_DU"])) if pd.notna(src_row["Source_DU"]) else "N/A"

    features = []
    for _, r in selected.iterrows():
        src = {
            "du": str(r.get("Source_DU", "")),
            "gnb": str(r.get("Source_GNB", "")),
            "site": str(r.get("Source_Site", "")),
            "lat": float(r["src_lat"]),
            "lon": float(r["src_lon"]),
        }
        tgt = {
            "du": str(r.get("Target_DU", "")),
            "gnb": str(r.get("Target_GNB", "")),
            "site": str(r.get("Target_Site", "")),
            "lat": float(r["tgt_lat"]),
            "lon": float(r["tgt_lon"]),
        }
        features.append(
            {
                "rank": int(r.get("Rank", 0)),
                "src": src,
                "tgt": tgt,
                "attempts": float(r.get("Attempts", 0)),
                "failures": float(r.get("Failures", 0)),
                "distance_km": float(r.get("Distance_km", 0)),
            }
        )

    data_json = json.dumps(features)
    profile_theme = {
        "Top 10 Long HO Attempts": {"line": "#0B5ED7", "source": "#0A3F9E", "target": "#16A34A"},
        "Top 10 HO Fails": {"line": "#C62828", "source": "#0A3F9E", "target": "#16A34A"},
        "Top 5 HO Fails": {"line": "#E53935", "source": "#0A3F9E", "target": "#16A34A"},
        "Top 10 Longest Distance": {"line": "#7E57C2", "source": "#0A3F9E", "target": "#16A34A"},
        "Top 15 HO Attempts": {"line": "#0277BD", "source": "#0A3F9E", "target": "#16A34A"},
        "Top 10 Fail Rate (min 20 att)": {"line": "#EF6C00", "source": "#0A3F9E", "target": "#16A34A"},
    }.get(profile_name, {"line": "#1B6FE3", "source": "#0A3F9E", "target": "#16A34A"})
    theme_json = json.dumps(profile_theme)
    title = html.escape(profile_name)
    html_doc = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <style>
    body {{ margin: 0; font-family: "Segoe UI", Arial, sans-serif; background: #eef3fb; color: #0b2a5b; }}
    .top {{ padding: 12px 14px; background: linear-gradient(90deg, #063a94, #0b5ed7); color: #fff; }}
    .subtitle {{ font-size: 12px; opacity: .9; }}
    #map {{ height: calc(100vh - 74px); width: 100%; }}
    .legend {{ background: white; padding: 10px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,.15); }}
    .chip {{ display: inline-block; padding: 3px 8px; border-radius: 999px; font-size: 11px; margin-right: 6px; }}
    .rel-panel {{ background: rgba(255,255,255,.94); padding: 8px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,.15); width: 240px; }}
    .rel-head {{ font-size: 12px; font-weight: 700; margin-bottom: 6px; color: #1b3569; }}
    .rel-row {{ font-size: 11px; display: flex; align-items: center; gap: 6px; margin: 3px 0; }}
    .sw {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; }}
    .rel-actions button {{ border: 1px solid #d3dff0; background: #f5f8ff; color: #1f3e78; font-size: 10px; border-radius: 6px; padding: 2px 6px; margin-right: 4px; cursor: pointer; }}
    .leaflet-control-layers {{ display:none; }}
    #relRows {{ max-height: 190px; overflow-y: scroll; overflow-x: hidden; padding-right: 2px; }}
    #relRows::-webkit-scrollbar {{ width: 8px; }}
    #relRows::-webkit-scrollbar-track {{ background: #edf2fb; border-radius: 8px; }}
    #relRows::-webkit-scrollbar-thumb {{ background: #9eb6dd; border-radius: 8px; }}
    #relRows::-webkit-scrollbar-thumb:hover {{ background: #7f9ccc; }}
  </style>
</head>
<body>
  <div class="top">
    <div><strong>{title}</strong></div>
    <div class="subtitle">Source DU center: {source_du_center} | OSM base map | Professional HO relation view</div>
  </div>
  <div id="map"></div>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    const rel = {data_json};
    const theme = {theme_json};
    const map = L.map('map').setView([{center_lat}, {center_lon}], 11);
    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors'
    }}).addTo(map);

    const srcIcon = L.circleMarker([{center_lat}, {center_lon}], {{
      radius: 10, color: '#063a94', fillColor: theme.source, fillOpacity: 1, weight: 2
    }}).addTo(map).bindPopup('<b>Center Source DU</b><br>{source_du_center}');

    const bounds = [];
    const maxAttempts = Math.max(...rel.map(x => x.attempts || 0), 1);
    const widthForAttempts = (att) => {{
      const r = Math.max(0, (att || 0) / maxAttempts);
      return 2 + (r * 7); // 2..9
    }};
    const pairCount = {{}};
    for (const r of rel) {{
      const k = `${{r.src.lat.toFixed(6)}},${{r.src.lon.toFixed(6)}}|${{r.tgt.lat.toFixed(6)}},${{r.tgt.lon.toFixed(6)}}`;
      pairCount[k] = (pairCount[k] || 0) + 1;
    }}
    const pairSeen = {{}};

    const relationLayers = [];
    const linePalette = ['#0B5ED7','#C62828','#7E57C2','#EF6C00','#00897B','#5D4037','#3949AB','#AD1457','#2E7D32','#546E7A','#6D4C41','#1E88E5'];
    const relationColor = (idx) => linePalette[idx % linePalette.length];

    const offsetPath = (s, t, idx, total) => {{
      // Build a subtle 3-point path with bounded perpendicular offset midpoint.
      // This keeps all duplicate relations visible without creating exaggerated polygons.
      const lat1 = s.lat, lon1 = s.lon, lat2 = t.lat, lon2 = t.lon;
      const dLat = lat2 - lat1;
      const dLon = lon2 - lon1;
      const dist = Math.sqrt(dLat*dLat + dLon*dLon) || 0.000001;
      const nLat = -dLon / dist;
      const nLon = dLat / dist;
      const spread = (idx - (total - 1) / 2); // symmetric around center
      const denom = Math.max(1, (total - 1) / 2);
      // Compress spacing so parallel lines stay visually close.
      const spreadNorm = (spread / denom) * 0.42; // tighter than previous

      // Offset scales with segment length and is strictly bounded.
      // For short segments, keep very subtle bending to avoid odd loops.
      // Smaller amplitude for smoother, less separated bends.
      const baseAmp = Math.min(0.0012, Math.max(0.00003, dist * 0.055));
      const midLat = (lat1 + lat2) / 2 + (nLat * baseAmp * spreadNorm);
      const midLon = (lon1 + lon2) / 2 + (nLon * baseAmp * spreadNorm);
      return [[lat1, lon1], [midLat, midLon], [lat2, lon2]];
    }};

    for (const r of rel) {{
      const s = r.src;
      const t = r.tgt;
      bounds.push([s.lat, s.lon], [t.lat, t.lon]);
      const k = `${{s.lat.toFixed(6)}},${{s.lon.toFixed(6)}}|${{t.lat.toFixed(6)}},${{t.lon.toFixed(6)}}`;
      const totalDup = pairCount[k] || 1;
      const dupIdx = pairSeen[k] || 0;
      pairSeen[k] = dupIdx + 1;
      const path = totalDup > 1 ? offsetPath(s, t, dupIdx, totalDup) : [[s.lat, s.lon], [t.lat, t.lon]];
      const lineColor = relationColor((r.rank || 1) - 1);
      const line = L.polyline(path, {{
        color: lineColor, weight: widthForAttempts(r.attempts), opacity: 0.78
      }}).addTo(map);
      line.bindPopup(
        `<b>Rank #${{r.rank}}</b><br>` +
        `Source: ${{s.gnb}}-${{s.du}} (${{s.site}})<br>` +
        `Target: ${{t.gnb}}-${{t.du}} (${{t.site}})<br>` +
        `Attempts: ${{r.attempts.toLocaleString()}} | Fails: ${{r.failures.toLocaleString()}}<br>` +
        `Distance: ${{r.distance_km.toFixed(2)}} km` +
        `<br>Parallel lines on same path: ${{totalDup}}`
      );

      L.circleMarker([s.lat, s.lon], {{
        radius: 6, color: '#0a3f9e', fillColor: theme.source, fillOpacity: 0.95, weight: 1
      }}).addTo(map);
      L.circleMarker([t.lat, t.lon], {{
        radius: 6, color: '#0c7a43', fillColor: theme.target, fillOpacity: 0.95, weight: 1
      }}).addTo(map);
      relationLayers.push({{
        id: `R${{r.rank}}`,
        color: lineColor,
        line: line,
        text: `R${{r.rank}} | Att:${{Math.round(r.attempts)}} F:${{Math.round(r.failures)}} D:${{r.distance_km.toFixed(2)}}km`
      }});
    }}
    if (bounds.length) map.fitBounds(bounds, {{ padding: [40, 40] }});

    const legend = L.control({{position: 'bottomleft'}});
    legend.onAdd = function() {{
      const div = L.DomUtil.create('div', 'legend');
      div.innerHTML =
        '<div><span class="chip" style="background:' + theme.source + ';color:#fff;">Source DU</span>' +
        '<span class="chip" style="background:' + theme.target + ';color:#fff;">Target DU</span>' +
        '<span class="chip" style="background:' + theme.line + ';color:#fff;">Relation Line</span></div>' +
        '<div style="margin-top:6px;font-size:12px;">Rows shown: ' + rel.length + '</div>' +
        '<div style="margin-top:4px;font-size:12px;">Line width = Attempts intensity (min thin, max thick)</div>';
      return div;
    }};
    legend.addTo(map);

    // Discreet thematic panel: toggle each relation line on/off.
    const relPanel = L.control({{position: 'topright'}});
    relPanel.onAdd = function() {{
      const div = L.DomUtil.create('div', 'rel-panel');
      const rows = relationLayers.map((x, i) =>
        `<label class="rel-row"><input type="checkbox" data-idx="${{i}}" checked />` +
        `<span class="sw" style="background:${{x.color}}"></span><span>${{x.text}}</span></label>`
      ).join('');
      div.innerHTML =
        '<div class="rel-head">Relations (thematic)</div>' +
        '<div class="rel-actions"><button id="relOn">All On</button><button id="relOff">All Off</button></div>' +
        '<div id="relRows" style="margin-top:4px;">' + rows + '</div>';
      L.DomEvent.disableClickPropagation(div);
      return div;
    }};
    relPanel.addTo(map);

    setTimeout(() => {{
      const relRows = document.getElementById('relRows');
      const relOn = document.getElementById('relOn');
      const relOff = document.getElementById('relOff');
      if (relRows) {{
        relRows.addEventListener('change', (ev) => {{
          const t = ev.target;
          if (!t || !t.matches('input[type="checkbox"]')) return;
          const idx = parseInt(t.getAttribute('data-idx') || '-1', 10);
          if (idx < 0 || idx >= relationLayers.length) return;
          const layer = relationLayers[idx].line;
          if (t.checked) {{
            layer.addTo(map);
          }} else {{
            map.removeLayer(layer);
          }}
        }});
      }}
      if (relOn) relOn.addEventListener('click', () => {{
        relationLayers.forEach((x, idx) => {{
          x.line.addTo(map);
          const cb = relRows?.querySelector(`input[data-idx="${{idx}}"]`);
          if (cb) cb.checked = true;
        }});
      }});
      if (relOff) relOff.addEventListener('click', () => {{
        relationLayers.forEach((x, idx) => {{
          map.removeLayer(x.line);
          const cb = relRows?.querySelector(`input[data-idx="${{idx}}"]`);
          if (cb) cb.checked = false;
        }});
      }});
    }}, 0);
  </script>
</body>
</html>"""

    out = Path(out_html)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_doc, encoding="utf-8")
    return out
