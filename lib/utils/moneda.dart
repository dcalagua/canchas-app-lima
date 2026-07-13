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
