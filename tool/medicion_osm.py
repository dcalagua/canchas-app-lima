"""Siembra de canchas CON NOMBRE desde OpenStreetMap (oct-2026, director).

Corre en GitHub Actions (el entorno de desarrollo no alcanza Overpass) y deja
en el log, comprimido, [lat, lng, deporte, nombre, ciudad, osm_id] de cada
cancha (`leisure=pitch`) o complejo (`leisure=sports_centre`) que tenga
nombre. Datos © colaboradores de OpenStreetMap (ODbL)."""
import base64, gzip, json, time, urllib.parse, urllib.request

OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
CIUDADES = {  # sur, oeste, norte, este
    "lima": (-12.55, -77.20, -11.70, -76.60), "arequipa": (-16.50, -71.65, -16.30, -71.45),
    "trujillo": (-8.20, -79.10, -8.02, -78.95), "chiclayo": (-6.85, -79.90, -6.70, -79.78),
    "piura": (-5.25, -80.72, -5.13, -80.58), "cusco": (-13.58, -72.02, -13.48, -71.88),
    "quito": (-0.38, -78.60, -0.02, -78.38), "guayaquil": (-2.30, -80.05, -2.03, -79.85),
    "cuenca": (-2.95, -79.08, -2.84, -78.94),
    "la_paz_el_alto": (-16.62, -68.25, -16.40, -68.00), "santa_cruz": (-17.90, -63.30, -17.70, -63.08),
    "cochabamba": (-17.45, -66.25, -17.33, -66.08),
}
FUERA = {"golf", "skateboard", "equestrian", "shooting", "motor", "karting", "athletics", "running", "swimming"}


def consulta(bbox):
    s, w, n, e = bbox
    q = (f'[out:json][timeout:240];(nwr["leisure"="pitch"]["name"]({s},{w},{n},{e});'
         f'nwr["leisure"="sports_centre"]["name"]({s},{w},{n},{e}););out center tags;')
    for url in OVERPASS:
        for _ in range(3):
            try:
                req = urllib.request.Request(url, data=urllib.parse.urlencode({"data": q}).encode(),
                                             headers={"User-Agent": "Pichangol-semilla/1.0"})
                with urllib.request.urlopen(req, timeout=300) as r:
                    return json.load(r)["elements"]
            except Exception as ex:  # noqa: BLE001
                print("reintento", url, ex, flush=True)
                time.sleep(20)
    return None


todo = []
for ciudad, bbox in CIUDADES.items():
    els = consulta(bbox)
    if els is None:
        print(f"### {ciudad}: FALLO", flush=True)
        continue
    n = 0
    for el in els:
        t = el.get("tags", {})
        dep = (t.get("sport") or "").split(";")[0].strip().lower()
        if dep in FUERA:
            continue
        c = el.get("center") or {"lat": el.get("lat"), "lon": el.get("lon")}
        if c.get("lat") is None:
            continue
        todo.append([round(c["lat"], 6), round(c["lon"], 6), dep, t["name"][:80], ciudad, f"{el['type'][0]}{el['id']}",
                     t.get("leisure", "")])
        n += 1
    print(f"### {ciudad}: {n}", flush=True)
    time.sleep(8)
blob = base64.b64encode(gzip.compress(json.dumps(todo, ensure_ascii=False).encode())).decode()
for i in range(0, len(blob), 3000):
    print(f"@@osm@@{i // 3000}@@{blob[i:i + 3000]}", flush=True)
print("### total", len(todo), flush=True)
