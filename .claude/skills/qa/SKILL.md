---
name: qa
description: Corre el QA completo de Pichangol como si un tester humano probara el app — suite de viajes de usuario del backend, salud estática del APK y exploración adversarial — y entrega un informe en español con veredicto. Usar antes de un release, tras cambios de plata/flujos, o cuando el director pida "pruebas de usuario" o "QA".
---

Lanza el agente **qa-pichangol** (Agent tool, subagent_type `qa-pichangol`)
con este encargo, y pásale como contexto los argumentos que dio el usuario
(si nombró un flujo o pantalla, el foco adversarial va ahí):

> Ejecuta el QA completo de Pichangol según tu definición: (1) suite pytest
> completa del backend (viajes de usuario incluidos), (2) salud estática del
> APK (balances vs baselines, venenos de Flutter 3.24.5, reglas de la casa),
> (3) exploración adversarial del diff reciente. Entrega el informe con
> veredicto 🟢/🟡/🔴.

Cuando el agente devuelva el informe, preséntalo al usuario TAL CUAL (en
español) y agrega al final una línea con los flujos del guión manual
(`docs/qa/guion_pruebas_usuario.md`) que conviene ejecutar en teléfono real
según lo que cambió.
