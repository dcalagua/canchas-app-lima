import '../config/pais.dart';

/// Símbolo de moneda actual, según el país detectado por GPS. OJO: es
/// **display-only** — NO convierte montos (S/100 no se vuelve Bs100), solo
/// cambia el símbolo para que el multi-país se vea correcto. La conversión y los
/// precios reales por país son parte del módulo multi-país (fase aparte).
///
/// La fuente de verdad del país (moneda + pasarela) vive en `config/pais.dart`;
/// aquí solo se cachea el símbolo para que la UI lo interpole barato
/// (`'$monedaSimbolo ${monto}'`).
String monedaSimbolo = 'S/';

/// Ajusta la moneda según el código ISO de país (de reverse-geocode). Delega en
/// la config de país, que además fija la pasarela y persiste la elección.
void setMonedaPorPais(String? iso) {
  setPaisPorIso(iso); // fire-and-forget: actualiza país + símbolo + persiste
}

/// Formatea un monto con el símbolo actual: "S/ 30.00" / "Bs 30.00" / "$ 30.00".
String precio(num monto, {int dec = 2}) =>
    '$monedaSimbolo ${monto.toStringAsFixed(dec)}';

/// Formatea SOLO el número de un monto de dinero: 2 decimales, pero sin el
/// ".00" sobrante en montos enteros. "90" → "90", "25.5" → "25.50",
/// "9.99" → "9.99". Úsalo con el símbolo por país al lado
/// (`'$simbolo ${montoTxt(m)}'`). Correcto para S/, Bs y $ (los 3 usan 2
/// decimales). NO antepone símbolo (la moneda la pone quien llama, según la
/// entidad/país, no el GPS del dispositivo).
String montoTxt(num monto) {
  final s = monto.toStringAsFixed(2);
  return s.endsWith('.00') ? s.substring(0, s.length - 3) : s;
}
