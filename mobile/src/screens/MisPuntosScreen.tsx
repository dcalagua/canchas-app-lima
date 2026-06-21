import React, { useCallback, useState } from 'react';
import {
  ActivityIndicator, FlatList, RefreshControl, StyleSheet, Text, TextInput,
  TouchableOpacity, View,
} from 'react-native';

import { api } from '../api';
import { USER_ID, colors } from '../theme';

export default function MisPuntosScreen() {
  const [saldo, setSaldo] = useState<{ disponible: number; pendiente: number } | null>(null);
  const [movs, setMovs] = useState<any[]>([]);
  const [puntos, setPuntos] = useState('200');
  const [cargando, setCargando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setCargando(true);
    try {
      setSaldo(await api.saldo(USER_ID));
      setMovs(await api.movimientos(USER_ID));
    } catch (e: any) {
      setMsg(e.message);
    } finally {
      setCargando(false);
    }
  }, []);

  React.useEffect(() => { cargar(); }, [cargar]);

  async function canjear(fuente: 'pichangol' | 'dueno') {
    setMsg(null);
    try {
      const r = await api.canjear({
        usuario_id: USER_ID, puntos_usados: Number(puntos) || 0,
        tipo_premio: 'descuento_reserva', fuente_financiamiento: fuente,
      }, `canje-${Date.now()}`);
      if (r.ok) setMsg(`✅ Vale ${r.vale_id} por S/ ${r.valor_soles} (${r.fuente_financiamiento}).`);
      else if (r.bloqueado) setMsg('⚠️ Pichangol llegó al tope del mes. Prueba "cofinanciado por el dueño".');
      else setMsg(`No se pudo: ${r.error}`);
      cargar();
    } catch (e: any) {
      setMsg(e.message);
    }
  }

  return (
    <View style={s.cont}>
      <View style={s.header}>
        <Text style={s.titulo}>Mis puntos</Text>
        <View style={s.saldoRow}>
          <View style={s.saldoBox}>
            <Text style={s.saldoNum}>{saldo?.disponible ?? '—'}</Text>
            <Text style={s.saldoLbl}>disponibles</Text>
          </View>
          <View style={[s.saldoBox, { backgroundColor: '#2A5C4E' }]}>
            <Text style={s.saldoNum}>{saldo?.pendiente ?? '—'}</Text>
            <Text style={s.saldoLbl}>pendientes</Text>
          </View>
        </View>

        <Text style={s.label}>Canjear puntos por un vale de descuento</Text>
        <TextInput style={s.input} value={puntos} onChangeText={setPuntos}
          keyboardType="number-pad" />
        <View style={{ flexDirection: 'row', gap: 10, marginTop: 10 }}>
          <TouchableOpacity style={[s.boton, { flex: 1 }]} onPress={() => canjear('pichangol')}>
            <Text style={s.botonTxt}>Canjear</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[s.botonAlt, { flex: 1 }]} onPress={() => canjear('dueno')}>
            <Text style={s.botonAltTxt}>Cofinanciado dueño</Text>
          </TouchableOpacity>
        </View>
        {msg && <Text style={s.msg}>{msg}</Text>}
        <Text style={s.histTit}>Movimientos</Text>
      </View>

      <FlatList
        data={movs}
        keyExtractor={(m) => String(m.id)}
        contentContainerStyle={{ padding: 20, paddingTop: 0 }}
        refreshControl={<RefreshControl refreshing={cargando} onRefresh={cargar} />}
        renderItem={({ item }) => (
          <View style={s.mov}>
            <View style={{ flex: 1 }}>
              <Text style={s.movAccion}>{item.accion}</Text>
              <Text style={s.movEstado}>{item.estado}</Text>
            </View>
            <Text style={[s.movPts,
              item.estado === 'liberado' ? { color: colors.pino } : { color: colors.tenue }]}>
              +{item.puntos}
            </Text>
          </View>
        )}
        ListEmptyComponent={!cargando
          ? <Text style={{ color: colors.tenue }}>Aún no tienes movimientos.</Text>
          : <ActivityIndicator />}
      />
    </View>
  );
}

const s = StyleSheet.create({
  cont: { flex: 1, backgroundColor: colors.papel },
  header: { padding: 20, paddingBottom: 8 },
  titulo: { fontSize: 26, fontWeight: '800', color: colors.tinta },
  saldoRow: { flexDirection: 'row', gap: 12, marginTop: 14 },
  saldoBox: { flex: 1, backgroundColor: colors.pino, borderRadius: 16, padding: 16 },
  saldoNum: { color: colors.lima, fontSize: 30, fontWeight: '900' },
  saldoLbl: { color: colors.blanco, opacity: 0.85, marginTop: 2 },
  label: { fontWeight: '700', color: colors.tinta, marginTop: 18, marginBottom: 6 },
  input: {
    backgroundColor: colors.blanco, borderWidth: 1, borderColor: colors.trazo,
    borderRadius: 12, paddingHorizontal: 14, paddingVertical: 12, fontSize: 15,
  },
  boton: { backgroundColor: colors.pino, borderRadius: 12, paddingVertical: 14, alignItems: 'center' },
  botonTxt: { color: colors.lima, fontWeight: '800' },
  botonAlt: {
    backgroundColor: colors.blanco, borderRadius: 12, paddingVertical: 14,
    alignItems: 'center', borderWidth: 1.5, borderColor: colors.pino,
  },
  botonAltTxt: { color: colors.pino, fontWeight: '800' },
  msg: { marginTop: 12, color: colors.tinta, fontWeight: '600' },
  histTit: { fontWeight: '800', fontSize: 16, color: colors.tinta, marginTop: 20, marginBottom: 8 },
  mov: {
    flexDirection: 'row', alignItems: 'center', backgroundColor: colors.blanco,
    borderRadius: 12, borderWidth: 1, borderColor: colors.trazo, padding: 14,
    marginBottom: 10,
  },
  movAccion: { fontWeight: '700', color: colors.tinta },
  movEstado: { color: colors.tenue, fontSize: 12, marginTop: 2 },
  movPts: { fontWeight: '900', fontSize: 16 },
});
