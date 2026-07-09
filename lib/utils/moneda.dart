/// Símbolo de moneda actual, según el país detectado por GPS. OJO: es
/// **display-only** — NO convierte montos (S/100 no se vuelve Bs100), solo
/// cambia el símbolo para que el demo multi-país se vea correcto. La conversión
/// y los precios reales por país son parte del módulo multi-país (Fase aparte).
String monedaSimbolo = 'S/';

/// Ajusta el símbolo según el código ISO de país (de reverse-geocode).
void setMonedaPorPais(String? iso) {
  switch ((iso ?? '').toUpperCase()) {
    case 'EC': // Ecuador usa dólar
      monedaSimbolo = '\$';
      break;
    case 'BO': // Bolivia
      monedaSimbolo = 'Bs';
      break;
    case 'PE':
    default:
      monedaSimbolo = 'S/';
  }
}

/// Formatea un monto con el símbolo actual: "S/ 30.00" / "Bs 30.00" / "$ 30.00".
String precio(num monto, {int dec = 2}) =>
    '$monedaSimbolo ${monto.toStringAsFixed(dec)}';
