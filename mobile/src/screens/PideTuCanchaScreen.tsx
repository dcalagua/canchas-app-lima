import React, { useState } from 'react';
import {
  ActivityIndicator, ScrollView, StyleSheet, Text, TextInput,
  TouchableOpacity, View,
} from 'react-native';

import { api } from '../api';
import { USER_ID, colors } from '../theme';

export default function PideTuCanchaScreen() {
  const [nombre, setNombre] = useState('');
  const [direccion, setDireccion] = useState('');
  const [distrito, setDistrito] = useState('');
  const [cargando, setCargando] = useState(false);
  const [resultado, setResultado] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  async function enviar() {
    if (!nombre.trim() || !direccion.trim()) {
      setError('Pon el nombre de la cancha y su dirección.');
      return;
    }
    setError(null);
    setCargando(true);
    setResultado(null);
    try {
      const r = await api.pedirCancha(
        {
          usuario_id: USER_ID,
          nombre_cancha_libre: nombre.trim(),
          direccion_texto: direccion.trim(),
          distrito: distrito.trim() || undefined,
        },
        `pide-${Date.now()}`,
      );
      setResultado(r);
      setNombre('');
      setDireccion('');
      setDistrito('');
    } catch (e: any) {
      setError(e.message ?? 'No se pudo enviar.');
    } finally {
      setCargando(false);
    }
  }

  return (
    <ScrollView style={s.cont} contentContainerStyle={{ padding: 20 }}>
      <Text style={s.titulo}>Pide tu cancha</Text>
      <Text style={s.sub}>
        ¿No encuentras tu cancha? Pídela y ganas puntos. Si la traemos a
        Pichangol, tu premio se libera.
      </Text>

      <Text style={s.label}>Nombre de la cancha</Text>
      <TextInput style={s.input} value={nombre} onChangeText={setNombre}
        placeholder="Ej.: Complejo Los Pinos" />

      <Text style={s.label}>Dirección</Text>
      <TextInput style={s.input} value={direccion} onChangeText={setDireccion}
        placeholder="Av. y número, referencia" />

      <Text style={s.label}>Distrito</Text>
      <TextInput style={s.input} value={distrito} onChangeText={setDistrito}
        placeholder="Ej.: Ate, Los Olivos, Surco…" />

      {error && <Text style={s.error}>{error}</Text>}

      <TouchableOpacity style={s.boton} onPress={enviar} disabled={cargando}>
        {cargando
          ? <ActivityIndicator color={colors.lima} />
          : <Text style={s.botonTxt}>Pedir cancha</Text>}
      </TouchableOpacity>

      {resultado && (
        <View style={s.card}>
          <Text style={s.cardTit}>¡Solicitud registrada! 🎉</Text>
          <Text style={s.cardLn}>Zona: {resultado.solicitud?.zona}</Text>
          <Text style={s.cardLn}>
            Puntos {resultado.puntos_acreditados ? 'pendientes' : 'no acreditados (tope del mes)'}:{' '}
            <Text style={{ fontWeight: '800' }}>{resultado.puntos_pendientes}</Text>
          </Text>
          <Text style={s.cardLn}>
            Esta cancha ya la pidieron {resultado.demanda_en_grupo} vez(ces).
          </Text>
          <Text style={s.cardNota}>
            Tus puntos se liberan cuando la cancha se registre y verifique.
          </Text>
        </View>
      )}
    </ScrollView>
  );
}

const s = StyleSheet.create({
  cont: { flex: 1, backgroundColor: colors.papel },
  titulo: { fontSize: 26, fontWeight: '800', color: colors.tinta },
  sub: { color: colors.tenue, marginTop: 6, marginBottom: 16, lineHeight: 20 },
  label: { fontWeight: '700', color: colors.tinta, marginTop: 12, marginBottom: 6 },
  input: {
    backgroundColor: colors.blanco, borderWidth: 1, borderColor: colors.trazo,
    borderRadius: 12, paddingHorizontal: 14, paddingVertical: 12, fontSize: 15,
  },
  error: { color: colors.clay, marginTop: 12, fontWeight: '600' },
  boton: {
    backgroundColor: colors.pino, borderRadius: 14, paddingVertical: 16,
    alignItems: 'center', marginTop: 20,
  },
  botonTxt: { color: colors.lima, fontWeight: '800', fontSize: 16 },
  card: {
    backgroundColor: colors.blanco, borderRadius: 16, borderWidth: 1,
    borderColor: colors.trazo, padding: 16, marginTop: 20,
  },
  cardTit: { fontWeight: '800', fontSize: 16, color: colors.tinta, marginBottom: 8 },
  cardLn: { color: colors.tinta, marginBottom: 4 },
  cardNota: { color: colors.tenue, marginTop: 8, fontStyle: 'italic' },
});
