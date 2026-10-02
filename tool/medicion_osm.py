"""Medición de canchas en OpenStreetMap (oct-2026, pedido del director).

Cuenta las canchas (`leisure=pitch`) por ciudad y vuelca, comprimidas en el
log, las de las zonas que se comparan contra lo que ya devolvió Google. Corre
en GitHub Actions (el entorno de desarrollo no alcanza Overpass)."""
import base64, gzip, json, time, urllib.parse, urllib.request
from collections import Counter

OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
CIUDADES = {  # sur, oeste, norte, este
    "lima_metropolitana": (-12.40, -77.20, -11.75, -76.60),
    "quito": (-0.40, -78.62, 0.05, -78.35),
    "guayaquil": (-2.30, -80.05, -2.03, -79.85),
    "la_paz_el_alto": (-16.62, -68.25, -16.40, -68.00),
    "santa_cruz": (-17.90, -63.30, -17.70, -63.08),
    "cochabamba": (-17.45, -66.25, -17.33, -66.08),
}
COMPARAR = {"lima_cmp": (-12.20, -77.13, -11.88, -76.65), "quito_cmp": (-0.30, -78.58, -0.05, -78.40)}


def consulta(bbox):
    s, w, n, e = bbox
    q = f'[out:json][timeout:180];(nwr["leisure"="pitch"]({s},{w},{n},{e});nwr["leisure"="sports_centre"]({s},{w},{n},{e}););out center tags;'
    for url in OVERPASS:
        for intento in range(3):
            try:
                req = urllib.request.Request(url, data=urllib.parse.urlencode({"data": q}).encode(),
                                             headers={"User-Agent": "Pichangol-medicion/1.0"})
                with urllib.request.urlopen(req, timeout=240) as r:
                    return json.load(r)["elements"]
            except Exception as ex:  # noqa: BLE001
                print("reintento", url, ex, flush=True)
                time.sleep(15)
    return []


def compacto(el):
    c = el.get("center") or {"lat": el.get("lat"), "lon": el.get("lon")}
    t = el.get("tags", {})
    return [round(c["lat"], 5), round(c["lon"], 5), t.get("leisure", ""), t.get("sport", ""), t.get("name", "")[:40],
            t.get("access", "")]


for nombre, bbox in {**CIUDADES, **COMPARAR}.items():
    els = consulta(bbox)
    pitch = [x for x in els if x.get("tags", {}).get("leisure") == "pitch"]
    centros = [x for x in els if x.get("tags", {}).get("leisure") == "sports_centre"]
    deportes = Counter((x.get("tags", {}).get("sport") or "sin_deporte").split(";")[0] for x in pitch)
    con_nombre = sum(1 for x in pitch + centros if x.get("tags", {}).get("name"))
    print(f"### {nombre}: canchas={len(pitch)} centros={len(centros)} con_nombre={con_nombre} deportes={deportes.most_common(8)}", flush=True)
    if nombre in COMPARAR:
        blob = base64.b64encode(gzip.compress(json.dumps([compacto(x) for x in els]).encode())).decode()
        for i in range(0, len(blob), 3000):
            print(f"@@{nombre}@@{i // 3000}@@{blob[i:i + 3000]}", flush=True)
    time.sleep(10)
