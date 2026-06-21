import * as ImagePicker from 'expo-image-picker';
import * as Location from 'expo-location';
import React, { useCallback, useState } from 'react';
import {
  ActivityIndicator, FlatList, Image, RefreshControl, StyleSheet, Text,
  TextInput, TouchableOpacity, View,
} from 'react-native';

import { api } from '../api';
import { colors } from '../theme';

// Mini-app del verificador: lista de visitas priorizada por demanda, captura de
// fotos GEO del SITIO (no documentos personales), confirma y firma.
export default function VerificadorScreen() {
  const [zona, setZona] = useState('lima_este');
  const [visitas, setVisitas] = useState<any[]>([]);
  const [cargando, setCargando] = useState(false);
  const [sel, setSel] = useState<any | null>(null);
  const [fotos, setFotos] = useState<string[]>([]);
  const [firma, setFirma] = useState('');
  const [msg, setMsg] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setCargando(true);
    setMsg(null);
    try {
      setVisitas(await api.visitas(zona));
    } catch (e: any) {
      setMsg(e.message);
    } finally {
      setCargando(false);
    }
  }, [zona]);

  React.useEffect(() => { cargar(); }, [cargar]);

  async function tomarFoto() {
    const perm = await ImagePicker.requestCameraPermissionsAsync();
    if (!perm.granted) { setMsg('Falta permiso de cámara.'); return; }
    const r = await ImagePicker.launchCameraAsync({ quality: 0.5 });
    if (!r.canceled && r.assets?.[0]) setFotos((f) => [...f, r.assets[0].uri]);
  }

  async function confirmar() {
    if (!sel) return;
    if (fotos.length === 0) { setMsg('Toma al menos una foto del sitio.'); return; }
    if (!firma.trim()) { setMsg('Firma con tu nombre.'); return; }
    setMsg(null);
    try {
      const perm = await Location.requestForegroundPermissionsAsync();
      if (!perm.granted) { setMsg('Falta permiso de ubicación.'); return; }
      const pos = await Location.getCurrentPositionAsync({});
      const r = await api.captura(sel.id, {
        // En producción, subir las fotos a Storage y enviar sus URLs.
        fotos_geo_urls: fotos,
        lat_sitio: pos.coords.latitude,
        lng_sitio: pos.coords.longitude,
        firma_verificador: firma.trim(),
        observaciones: `Verificado en sitio (${fotos.length} fotos).`,
      });
      if (r.ok) {
        setMsg(`✅ ${r.insignia} — coincide (${r.distancia_m ?? '—'} m). ¡Cancha verificada!`);
      } else if (r.estado === 'rechazada') {
        setMsg(`❌ No coincide la ubicación (${r.distancia_m} m). Rechazada.`);
      } else {
        setMsg(`No se pudo: ${r.error}`);
      }
      setSel(null); setFotos([]); setFirma('');
      cargar();
    } catch (e: any) {
      setMsg(e.message);
    }
  }

  if (sel) {
    return (
      <View style={s.cont}>
        <View style={{ padding: 20 }}>
          <TouchableOpacity onPress={() => { setSel(null); setFotos([]); }}>
            <Text style={s.volver}>‹ Volver a la lista</Text>
          </TouchableOpacity>
          <Text style={s.titulo}>Verificar en sitio</Text>
          <Text style={s.sub}>Cancha #{sel.cancha_id} · zona {sel.zona} · demanda {sel.demanda}</Text>

          <TouchableOpacity style={s.boton} onPress={tomarFoto}>
            <Text style={s.botonTxt}>📷 Tomar foto del sitio</Text>
          </TouchableOpacity>
          <FlatList horizontal data={fotos} keyExtractor={(u, i) => u + i}
            style={{ marginTop: 12 }}
            renderItem={({ item }) => <Image source={{ uri: item }} style={s.thumb} />} />

          <Text style={s.label}>Firma (tu nombre)</Text>
          <TextInput style={s.input} value={firma} onChangeText={setFirma}
            placeholder="Nombre del verificador" />

          {msg && <Text style={s.msg}>{msg}</Text>}
          <TouchableOpacity style={[s.boton, { backgroundColor: colors.clay, marginTop: 16 }]}
            onPress={confirmar}>
            <Text style={[s.botonTxt, { color: colors.blanco }]}>Confirmar y firmar</Text>
          </TouchableOpacity>
          <Text style={s.nota}>
            Las fotos son del establecimiento, no documentos personales. No se piden DNI ni recibos.
          </Text>
        </View>
      </View>
    );
  }

  return (
    <View style={s.cont}>
      <View style={{ padding: 20, paddingBottom: 8 }}>
        <Text style={s.titulo}>Visitas del verificador</Text>
        <Text style={s.sub}>Priorizadas por demanda: la cancha más pedida va primero.</Text>
        <Text style={s.label}>Zona</Text>
        <TextInput style={s.input} value={zona} onChangeText={setZona}
          autoCapitalize="none" placeholder="lima_norte | lima_sur | lima_este | lima_moderna | callao" />
        {msg && <Text style={s.msg}>{msg}</Text>}
      </View>
      <FlatList
        data={visitas}
        keyExtractor={(v) => String(v.id)}
        contentContainerStyle={{ padding: 20, paddingTop: 0 }}
        refreshControl={<RefreshControl refreshing={cargando} onRefresh={cargar} />}
        renderItem={({ item }) => (
          <TouchableOpacity style={s.visita} onPress={() => setSel(item)}>
            <View style={{ flex: 1 }}>
              <Text style={s.visitaTit}>Cancha {item.cancha_id}</Text>
              <Text style={s.visitaSub}>{item.estado} · {item.motivo}</Text>
            </View>
            <View style={s.demanda}>
              <Text style={s.demandaNum}>{item.demanda}</Text>
              <Text style={s.demandaLbl}>pedidos</Text>
            </View>
          </TouchableOpacity>
        )}
        ListEmptyComponent={!cargando
          ? <Text style={{ color: colors.tenue }}>No hay visitas pendientes en esta zona.</Text>
          : <ActivityIndicator />}
      />
    </View>
  );
}

const s = StyleSheet.create({
  cont: { flex: 1, backgroundColor: colors.papel },
  titulo: { fontSize: 24, fontWeight: '800', color: colors.tinta },
  sub: { color: colors.tenue, marginTop: 4, marginBottom: 8 },
  volver: { color: colors.pino, fontWeight: '700', marginBottom: 8 },
  label: { fontWeight: '700', color: colors.tinta, marginTop: 14, marginBottom: 6 },
  input: {
    backgroundColor: colors.blanco, borderWidth: 1, borderColor: colors.trazo,
    borderRadius: 12, paddingHorizontal: 14, paddingVertical: 12, fontSize: 14,
  },
  boton: {
    backgroundColor: colors.pino, borderRadius: 12, paddingVertical: 14,
    alignItems: 'center', marginTop: 14,
  },
  botonTxt: { color: colors.lima, fontWeight: '800' },
  thumb: { width: 80, height: 80, borderRadius: 10, marginRight: 8 },
  msg: { marginTop: 12, color: colors.tinta, fontWeight: '600' },
  nota: { color: colors.tenue, fontSize: 12, marginTop: 14, fontStyle: 'italic' },
  visita: {
    flexDirection: 'row', alignItems: 'center', backgroundColor: colors.blanco,
    borderRadius: 14, borderWidth: 1, borderColor: colors.trazo, padding: 16,
    marginBottom: 10,
  },
  visitaTit: { fontWeight: '800', color: colors.tinta, fontSize: 15 },
  visitaSub: { color: colors.tenue, marginTop: 2, fontSize: 12 },
  demanda: { alignItems: 'center', backgroundColor: '#EAF6C2', borderRadius: 10, padding: 8, minWidth: 60 },
  demandaNum: { fontWeight: '900', color: colors.pino, fontSize: 18 },
  demandaLbl: { color: colors.pino, fontSize: 10 },
});
