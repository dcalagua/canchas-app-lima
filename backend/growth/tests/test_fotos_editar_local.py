"""Editar local → "Fotos del local": subir propias y quitar las de Google
(pedido del director, 2-oct-2026: "¿dónde se suben nuevas fotos y se
eliminan las de Google?")."""
from web import anfitrion

SB = "https://proy.supabase.co/storage/v1/object/public/canchas"


def _c(cid, fotos):
    return {"id": cid, "foto_url": fotos[0] if fotos else None, "fotos": fotos}


def test_repartir_fotos_del_local(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://proy.supabase.co")
    g1, g2 = "https://lh3.googleusercontent.com/a", "https://lh3.googleusercontent.com/b"
    p_a = f"{SB}/u100_futbol/web_1.jpg"
    nueva = f"{SB}/u100_futbol/web_2.jpg"
    ajena = f"{SB}/u999/web_9.jpg"
    a = _c("u100_futbol", [g1, p_a])
    b = _c("u100_tenis", [g2])
    gal = anfitrion._galeria_local(a, [a, b])
    assert [x["propia"] for x in gal] == [False, True, False]
    # sin galería en el cuerpo (cliente viejo) no toca fotos
    assert anfitrion._repartir_fotos_local(a, [a, b], None) == (None, [])
    # quita las de Google, sube una nueva (la deja de portada) y una ajena se ignora
    por, quitadas = anfitrion._repartir_fotos_local(a, [a, b], [nueva, p_a, ajena])
    assert por == {"u100_futbol": [nueva, p_a], "u100_tenis": []}
    assert quitadas == []  # las de Google nunca se borran del bucket (no son nuestras)
    # quitar una propia la borra del bucket
    a2 = _c("u100_futbol", [nueva, p_a])
    por, quitadas = anfitrion._repartir_fotos_local(a2, [a2], [nueva])
    assert por == {"u100_futbol": [nueva]} and quitadas == [p_a]
