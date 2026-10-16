import 'package:flutter/services.dart';

/// Formatea el número de tarjeta en grupos de 4: "4111 1111 1111 1111".
/// Guarda solo dígitos internamente; el consumidor debe quitar los espacios.
class TarjetaNumeroFormatter extends TextInputFormatter {
  @override
  TextEditingValue formatEditUpdate(
      TextEditingValue oldValue, TextEditingValue newValue) {
    var digitos = newValue.text.replaceAll(RegExp(r'\D'), '');
    if (digitos.length > 19) digitos = digitos.substring(0, 19);
    final buf = StringBuffer();
    for (var i = 0; i < digitos.length; i++) {
      if (i != 0 && i % 4 == 0) buf.write(' ');
      buf.write(digitos[i]);
    }
    final texto = buf.toString();
    return TextEditingValue(
      text: texto,
      selection: TextSelection.collapsed(offset: texto.length),
    );
  }
}

/// Formatea el vencimiento como "MM/AA" insertando el "/" automáticamente.
class VencimientoFormatter extends TextInputFormatter {
  @override
  TextEditingValue formatEditUpdate(
      TextEditingValue oldValue, TextEditingValue newValue) {
    var d = newValue.text.replaceAll(RegExp(r'\D'), '');
    if (d.length > 4) d = d.substring(0, 4);
    final texto = d.length >= 3 ? '${d.substring(0, 2)}/${d.substring(2)}' : d;
    return TextEditingValue(
      text: texto,
      selection: TextSelection.collapsed(offset: texto.length),
    );
  }
}
