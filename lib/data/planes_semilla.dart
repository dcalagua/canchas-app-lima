import '../models/plan_trabajo.dart';

/// Plantillas de PLAN DE TRABAJO que trae Pichangol (editable por el profe).
/// Traemos una plantilla de INICIACIÓN por deporte (tenis, pádel, fútbol,
/// natación, vóley, básquet). El profe la "usa" (se clona con id propio) y la
/// edita a su gusto. Mismo molde: solo cambian habilidades y sesiones.

/// Devuelve la plantilla Pichangol para [deporte] (Deporte.name), o null si aún
/// no tenemos una para ese deporte. Un único punto de entrada para AppState.
PlanTrabajo? plantillaPara(String deporte, String academiaId) {
  switch (deporte) {
    case 'tenis':
      return plantillaTenisPichangol(academiaId);
    case 'padel':
      return plantillaPadelPichangol(academiaId);
    case 'futbol':
      return plantillaFutbolPichangol(academiaId);
    case 'natacion':
      return plantillaNatacionPichangol(academiaId);
    case 'voley':
      return plantillaVoleyPichangol(academiaId);
    case 'basquet':
      return plantillaBasquetPichangol(academiaId);
    default:
      return null;
  }
}

/// Habilidades estándar de tenis que se evalúan por alumno.
const List<String> habilidadesTenis = [
  'Derecha (drive)',
  'Revés',
  'Saque',
  'Volea',
  'Globo y smash',
  'Desplazamiento y postura',
  'Táctica de juego',
  'Actitud y competencia',
];

/// Plantilla Pichangol de tenis: 12 clases progresivas (iniciación → intermedio).
/// Es una PLANTILLA (esPlantilla=true, no se persiste tal cual): el profe la
/// "usa" y ahí se clona con un id propio para poder editarla.
PlanTrabajo plantillaTenisPichangol(String academiaId) => PlanTrabajo(
      id: 'plantilla_tenis',
      academiaId: academiaId,
      deporte: 'tenis',
      nombre: 'Plan de tenis · Iniciación',
      nivel: 'Iniciación e intermedio',
      esPlantilla: true,
      habilidades: habilidadesTenis,
      sesiones: const [
        SesionPlan(
          numero: 1,
          titulo: 'Familiarización con la raqueta',
          objetivo: 'Tomar contacto con la raqueta y la pelota; empuñadura y '
              'equilibrio.',
          contenidos: [
            'Empuñadura este (continental) y agarre correcto',
            'Botes controlados de pelota (arriba y al piso)',
            'Desplazamientos básicos y posición de espera',
          ],
        ),
        SesionPlan(
          numero: 2,
          titulo: 'Derecha: primeros golpes',
          objetivo: 'Introducir el golpe de derecha con swing corto y control.',
          contenidos: [
            'Postura lateral y preparación temprana',
            'Contacto delante del cuerpo, mano firme',
            'Peloteo suave desde media cancha',
          ],
        ),
        SesionPlan(
          numero: 3,
          titulo: 'Revés a dos manos',
          objetivo: 'Introducir el revés y coordinar ambas manos.',
          contenidos: [
            'Empuñadura de revés y giro de hombros',
            'Contacto al frente y terminación arriba',
            'Alternar derecha/revés en el peloteo',
          ],
        ),
        SesionPlan(
          numero: 4,
          titulo: 'Consistencia de fondo',
          objetivo: 'Sostener el peloteo cruzado con dirección.',
          contenidos: [
            'Cruzados de derecha (10 seguidos)',
            'Cruzados de revés',
            'Recuperación al centro después de cada golpe',
          ],
        ),
        SesionPlan(
          numero: 5,
          titulo: 'La volea',
          objetivo: 'Introducir la volea de derecha y de revés en la red.',
          contenidos: [
            'Empuñadura continental y bloqueo firme',
            'Volea de derecha y de revés cerca de la red',
            'Aproximación a la red y split-step',
          ],
        ),
        SesionPlan(
          numero: 6,
          titulo: 'El saque (parte 1)',
          objetivo: 'Mecánica básica del saque: lanzamiento y contacto arriba.',
          contenidos: [
            'Lanzamiento de pelota constante',
            'Posición de saque y agarre continental',
            'Saque a media potencia buscando el cajón',
          ],
        ),
        SesionPlan(
          numero: 7,
          titulo: 'Evaluación intermedia',
          objetivo: 'Medir el avance de golpes básicos y ajustar el plan.',
          contenidos: [
            'Circuito de derecha, revés y volea',
            'Saque: 10 intentos por lado',
            'Registrar nivel por habilidad de cada alumno',
          ],
        ),
        SesionPlan(
          numero: 8,
          titulo: 'Desplazamiento y equilibrio',
          objetivo: 'Mejorar el juego de pies y llegar bien a la pelota.',
          contenidos: [
            'Pasos de ajuste y cruce',
            'Recuperación y posición de base',
            'Peloteo con desplazamiento lateral',
          ],
        ),
        SesionPlan(
          numero: 9,
          titulo: 'Globo y smash',
          objetivo: 'Introducir el globo defensivo y el remate (smash).',
          contenidos: [
            'Globo por encima del rival',
            'Smash con posición lateral',
            'Situación: globo → smash',
          ],
        ),
        SesionPlan(
          numero: 10,
          titulo: 'Saque (parte 2) y devolución',
          objetivo: 'Consolidar el saque y practicar la devolución.',
          contenidos: [
            'Saque con dirección (a la T y abierto)',
            'Devolución bloqueada y en profundidad',
            'Punto empezando con saque',
          ],
        ),
        SesionPlan(
          numero: 11,
          titulo: 'Táctica: puntos y patrones',
          objetivo: 'Jugar puntos con intención (dirección y profundidad).',
          contenidos: [
            'Patrón: cruzado y cambio a paralelo',
            'Construcción del punto desde el fondo',
            'Puntos con conteo (juegos cortos)',
          ],
        ),
        SesionPlan(
          numero: 12,
          titulo: 'Mini-torneo y evaluación final',
          objetivo: 'Competir y cerrar el ciclo evaluando cada habilidad.',
          contenidos: [
            'Mini-torneo interno (sets cortos)',
            'Evaluación final por habilidad',
            'Feedback individual y metas del próximo ciclo',
          ],
        ),
      ],
    );

// ── PÁDEL ────────────────────────────────────────────────────────────────────
const List<String> habilidadesPadel = [
  'Derecha y revés de fondo',
  'Volea',
  'Bandeja',
  'Saque y resto',
  'Salida de pared (fondo)',
  'Globo',
  'Posición y juego en pareja',
  'Actitud y competencia',
];

PlanTrabajo plantillaPadelPichangol(String academiaId) => PlanTrabajo(
      id: 'plantilla_padel',
      academiaId: academiaId,
      deporte: 'padel',
      nombre: 'Plan de pádel · Iniciación',
      nivel: 'Iniciación e intermedio',
      esPlantilla: true,
      habilidades: habilidadesPadel,
      sesiones: const [
        SesionPlan(
          numero: 1,
          titulo: 'La pala y la posición',
          objetivo: 'Empuñadura continental, posición de espera y contacto.',
          contenidos: [
            'Empuñadura continental y equilibrio',
            'Posición de espera en el centro de la pista',
            'Peloteo suave de fondo controlando la pala',
          ],
        ),
        SesionPlan(
          numero: 2,
          titulo: 'Golpes de fondo',
          objetivo: 'Derecha y revés planos con control y dirección.',
          contenidos: [
            'Preparación temprana y contacto delante',
            'Cruzados de derecha y de revés',
            'Recuperación al centro tras el golpe',
          ],
        ),
        SesionPlan(
          numero: 3,
          titulo: 'La volea',
          objetivo: 'Volea de derecha y de revés firme en la red.',
          contenidos: [
            'Bloqueo firme, sin swing largo',
            'Volea cruzada y paralela',
            'Subida a la red con split-step',
          ],
        ),
        SesionPlan(
          numero: 4,
          titulo: 'Saque y resto',
          objetivo: 'Saque reglamentario (bajo, cruzado) y devolución.',
          contenidos: [
            'Saque por debajo de la cintura al cuadro cruzado',
            'Resto profundo y subida',
            'Punto empezando con saque',
          ],
        ),
        SesionPlan(
          numero: 5,
          titulo: 'Uso de la pared (defensa)',
          objetivo: 'Leer el bote y sacar la pelota de la pared de fondo.',
          contenidos: [
            'Lectura del rebote en pared de fondo',
            'Salida de pared con paciencia',
            'Defender y volver a colocar la pelota',
          ],
        ),
        SesionPlan(
          numero: 6,
          titulo: 'El globo',
          objetivo: 'Globo defensivo para recuperar la red.',
          contenidos: [
            'Globo profundo por encima del rival',
            'Globo tras defensa de pared',
            'Recuperar la red después del globo',
          ],
        ),
        SesionPlan(
          numero: 7,
          titulo: 'Evaluación intermedia',
          objetivo: 'Medir golpes básicos y ajustar el plan.',
          contenidos: [
            'Circuito: fondo, volea y bandeja',
            'Saque y resto: 10 por lado',
            'Registrar nivel por habilidad de cada alumno',
          ],
        ),
        SesionPlan(
          numero: 8,
          titulo: 'La bandeja',
          objetivo: 'Bandeja para mantener la red sin rematar.',
          contenidos: [
            'Contacto arriba y a la derecha, pala abierta',
            'Bandeja cruzada con control',
            'Situación: globo del rival → bandeja',
          ],
        ),
        SesionPlan(
          numero: 9,
          titulo: 'Juego en pareja',
          objetivo: 'Moverse coordinados y cubrir el centro.',
          contenidos: [
            'Movimientos en espejo con la pareja',
            'Quién va al centro y cambios',
            'Comunicación básica en el punto',
          ],
        ),
        SesionPlan(
          numero: 10,
          titulo: 'Mini-torneo y evaluación final',
          objetivo: 'Competir en parejas y cerrar evaluando cada habilidad.',
          contenidos: [
            'Mini-torneo de dobles (juegos cortos)',
            'Evaluación final por habilidad',
            'Feedback individual y metas del próximo ciclo',
          ],
        ),
      ],
    );

// ── FÚTBOL ───────────────────────────────────────────────────────────────────
const List<String> habilidadesFutbol = [
  'Control y recepción',
  'Pase y precisión',
  'Conducción y regate',
  'Tiro a puerta',
  'Juego aéreo (cabeceo)',
  'Defensa y marca',
  'Táctica y posición',
  'Actitud y trabajo en equipo',
];

PlanTrabajo plantillaFutbolPichangol(String academiaId) => PlanTrabajo(
      id: 'plantilla_futbol',
      academiaId: academiaId,
      deporte: 'futbol',
      nombre: 'Plan de fútbol · Iniciación',
      nivel: 'Iniciación e intermedio',
      esPlantilla: true,
      habilidades: habilidadesFutbol,
      sesiones: const [
        SesionPlan(
          numero: 1,
          titulo: 'Familiarización con el balón',
          objetivo: 'Contacto con el balón, superficies y coordinación.',
          contenidos: [
            'Toques con planta, interior y exterior',
            'Conducción libre por el espacio',
            'Juegos de calentamiento con balón',
          ],
        ),
        SesionPlan(
          numero: 2,
          titulo: 'Control y recepción',
          objetivo: 'Recibir y controlar el balón orientándolo.',
          contenidos: [
            'Control con interior y con planta',
            'Recepción orientada hacia el espacio libre',
            'Rondos en grupos pequeños',
          ],
        ),
        SesionPlan(
          numero: 3,
          titulo: 'El pase',
          objetivo: 'Pase preciso a corta y media distancia.',
          contenidos: [
            'Pase con interior, firme y al pie',
            'Pared (dar y va) en parejas',
            'Circuito de pases en movimiento',
          ],
        ),
        SesionPlan(
          numero: 4,
          titulo: 'Conducción y regate',
          objetivo: 'Conducir con cambios de dirección y superar rival.',
          contenidos: [
            'Conducción entre conos con ambos pies',
            'Fintas básicas (cambio de ritmo y dirección)',
            '1v1 en espacio reducido',
          ],
        ),
        SesionPlan(
          numero: 5,
          titulo: 'Tiro a puerta',
          objetivo: 'Golpeo con precisión y potencia.',
          contenidos: [
            'Golpeo con empeine e interior',
            'Definición dentro del área',
            'Finalización tras pase o conducción',
          ],
        ),
        SesionPlan(
          numero: 6,
          titulo: 'Evaluación intermedia',
          objetivo: 'Medir técnica básica y ajustar el plan.',
          contenidos: [
            'Circuito técnico: control, pase, conducción, tiro',
            'Partido reducido observando lo trabajado',
            'Registrar nivel por habilidad de cada alumno',
          ],
        ),
        SesionPlan(
          numero: 7,
          titulo: 'Juego aéreo y defensa',
          objetivo: 'Cabecear y defender la marca individual.',
          contenidos: [
            'Cabeceo de despeje y de remate',
            'Posición defensiva y temporización',
            'Marca al hombre en zona reducida',
          ],
        ),
        SesionPlan(
          numero: 8,
          titulo: 'Táctica: posición y espacios',
          objetivo: 'Ocupar espacios y jugar en equipo.',
          contenidos: [
            'Desmarque y apoyo al compañero',
            'Amplitud y profundidad en ataque',
            'Transición defensa-ataque',
          ],
        ),
        SesionPlan(
          numero: 9,
          titulo: 'Situaciones de juego',
          objetivo: 'Aplicar lo aprendido en superioridades.',
          contenidos: [
            'Juegos 2v1 y 3v2',
            'Finalización con pocos toques',
            'Toma de decisiones bajo presión',
          ],
        ),
        SesionPlan(
          numero: 10,
          titulo: 'Partido y evaluación final',
          objetivo: 'Competir y cerrar evaluando cada habilidad.',
          contenidos: [
            'Partido formal aplicando lo trabajado',
            'Evaluación final por habilidad',
            'Feedback individual y metas del próximo ciclo',
          ],
        ),
      ],
    );

// ── NATACIÓN ─────────────────────────────────────────────────────────────────
const List<String> habilidadesNatacion = [
  'Flotación y respiración',
  'Crol (libre)',
  'Espalda',
  'Pecho (braza)',
  'Mariposa',
  'Salidas y viradas',
  'Resistencia',
  'Técnica y coordinación',
];

PlanTrabajo plantillaNatacionPichangol(String academiaId) => PlanTrabajo(
      id: 'plantilla_natacion',
      academiaId: academiaId,
      deporte: 'natacion',
      nombre: 'Plan de natación · Iniciación',
      nivel: 'Iniciación e intermedio',
      esPlantilla: true,
      habilidades: habilidadesNatacion,
      sesiones: const [
        SesionPlan(
          numero: 1,
          titulo: 'Adaptación al medio',
          objetivo: 'Perder el miedo, flotar y controlar la respiración.',
          contenidos: [
            'Entradas al agua y desplazamiento en la pared',
            'Flotación ventral y dorsal',
            'Burbujas: exhalar por la boca dentro del agua',
          ],
        ),
        SesionPlan(
          numero: 2,
          titulo: 'Respiración y patada',
          objetivo: 'Coordinar respiración con patada de crol.',
          contenidos: [
            'Patada de crol con tabla',
            'Respiración lateral rítmica',
            'Deslizamientos con impulso de pared',
          ],
        ),
        SesionPlan(
          numero: 3,
          titulo: 'Crol: brazada',
          objetivo: 'Técnica de brazada de crol coordinada.',
          contenidos: [
            'Brazada con recobro alto',
            'Coordinación brazo-respiración',
            'Nado de crol en tramos cortos',
          ],
        ),
        SesionPlan(
          numero: 4,
          titulo: 'Espalda',
          objetivo: 'Nadar de espalda con posición horizontal.',
          contenidos: [
            'Flotación y patada de espalda con tabla',
            'Brazada alterna de espalda',
            'Nado de espalda en tramos cortos',
          ],
        ),
        SesionPlan(
          numero: 5,
          titulo: 'Evaluación intermedia',
          objetivo: 'Medir crol y espalda; ajustar el plan.',
          contenidos: [
            'Crol y espalda en distancia corta',
            'Control de respiración y flotación',
            'Registrar nivel por habilidad de cada alumno',
          ],
        ),
        SesionPlan(
          numero: 6,
          titulo: 'Pecho (braza)',
          objetivo: 'Técnica de patada y brazada de pecho.',
          contenidos: [
            'Patada de rana con tabla',
            'Brazada de pecho y tiempo de deslizamiento',
            'Coordinación patada-brazada-respiración',
          ],
        ),
        SesionPlan(
          numero: 7,
          titulo: 'Introducción a mariposa',
          objetivo: 'Ondulación y patada de delfín.',
          contenidos: [
            'Ondulación de cuerpo y patada de delfín',
            'Brazada de mariposa con ayuda',
            'Tramos cortos de mariposa',
          ],
        ),
        SesionPlan(
          numero: 8,
          titulo: 'Salidas y viradas',
          objetivo: 'Salir del poyete y voltear en la pared.',
          contenidos: [
            'Salida desde el borde',
            'Virada sencilla de crol y espalda',
            'Encadenar nado con virada',
          ],
        ),
        SesionPlan(
          numero: 9,
          titulo: 'Resistencia',
          objetivo: 'Sostener el nado en distancias mayores.',
          contenidos: [
            'Series de crol con descanso',
            'Nado continuo suave',
            'Control del ritmo y respiración',
          ],
        ),
        SesionPlan(
          numero: 10,
          titulo: 'Prueba final y evaluación',
          objetivo: 'Nadar los estilos y cerrar evaluando cada habilidad.',
          contenidos: [
            'Prueba de crol, espalda y pecho',
            'Evaluación final por habilidad',
            'Feedback individual y metas del próximo ciclo',
          ],
        ),
      ],
    );

// ── VÓLEY ────────────────────────────────────────────────────────────────────
const List<String> habilidadesVoley = [
  'Antebrazo (recepción)',
  'Voleo (colocación)',
  'Saque',
  'Remate',
  'Bloqueo',
  'Desplazamientos y defensa',
  'Táctica y rotación',
  'Actitud y trabajo en equipo',
];

PlanTrabajo plantillaVoleyPichangol(String academiaId) => PlanTrabajo(
      id: 'plantilla_voley',
      academiaId: academiaId,
      deporte: 'voley',
      nombre: 'Plan de vóley · Iniciación',
      nivel: 'Iniciación e intermedio',
      esPlantilla: true,
      habilidades: habilidadesVoley,
      sesiones: const [
        SesionPlan(
          numero: 1,
          titulo: 'Postura y desplazamientos',
          objetivo: 'Posición base y moverse para llegar al balón.',
          contenidos: [
            'Posición de espera y equilibrio',
            'Desplazamientos laterales y frontales',
            'Familiarización con el balón',
          ],
        ),
        SesionPlan(
          numero: 2,
          titulo: 'Antebrazo (recepción)',
          objetivo: 'Golpe de antebrazo controlado.',
          contenidos: [
            'Plataforma de brazos firme',
            'Recepción a media altura en parejas',
            'Dirigir el balón hacia el colocador',
          ],
        ),
        SesionPlan(
          numero: 3,
          titulo: 'Voleo (colocación)',
          objetivo: 'Golpe de dedos para colocar.',
          contenidos: [
            'Forma de manos y contacto sobre la frente',
            'Voleo hacia arriba en el sitio',
            'Colocación al compañero',
          ],
        ),
        SesionPlan(
          numero: 4,
          titulo: 'El saque',
          objetivo: 'Saque de abajo y de arriba al campo contrario.',
          contenidos: [
            'Saque bajo por seguridad',
            'Introducción al saque tenis',
            'Saque buscando zonas',
          ],
        ),
        SesionPlan(
          numero: 5,
          titulo: 'Evaluación intermedia',
          objetivo: 'Medir recepción, voleo y saque.',
          contenidos: [
            'Circuito: recepción-colocación-saque',
            'Juego cooperativo 3 toques',
            'Registrar nivel por habilidad de cada alumno',
          ],
        ),
        SesionPlan(
          numero: 6,
          titulo: 'El remate',
          objetivo: 'Aproximación, salto y golpe de ataque.',
          contenidos: [
            'Paso de aproximación y salto',
            'Golpe de ataque sobre balón sostenido',
            'Remate tras colocación',
          ],
        ),
        SesionPlan(
          numero: 7,
          titulo: 'Bloqueo y defensa',
          objetivo: 'Bloquear en la red y defender atrás.',
          contenidos: [
            'Salto de bloqueo y manos sobre la red',
            'Defensa baja tras el bloqueo',
            'Coordinación bloqueo-defensa',
          ],
        ),
        SesionPlan(
          numero: 8,
          titulo: 'Táctica: los 3 toques y rotación',
          objetivo: 'Jugar recepción-colocación-ataque y rotar.',
          contenidos: [
            'Sistema de 3 toques',
            'Rotaciones y posiciones',
            'Partido reducido y evaluación final por habilidad',
          ],
        ),
      ],
    );

// ── BÁSQUET ──────────────────────────────────────────────────────────────────
const List<String> habilidadesBasquet = [
  'Bote y manejo',
  'Pase y recepción',
  'Entrada a canasta (bandeja)',
  'Tiro (media y libre)',
  'Defensa individual',
  'Rebote',
  'Táctica y espacios',
  'Actitud y trabajo en equipo',
];

PlanTrabajo plantillaBasquetPichangol(String academiaId) => PlanTrabajo(
      id: 'plantilla_basquet',
      academiaId: academiaId,
      deporte: 'basquet',
      nombre: 'Plan de básquet · Iniciación',
      nivel: 'Iniciación e intermedio',
      esPlantilla: true,
      habilidades: habilidadesBasquet,
      sesiones: const [
        SesionPlan(
          numero: 1,
          titulo: 'Manejo de balón',
          objetivo: 'Bote con ambas manos y control.',
          contenidos: [
            'Bote en el sitio con derecha e izquierda',
            'Bote en desplazamiento',
            'Bote con cambios de mano',
          ],
        ),
        SesionPlan(
          numero: 2,
          titulo: 'El pase',
          objetivo: 'Pase de pecho y de pique preciso.',
          contenidos: [
            'Pase de pecho en parejas',
            'Pase de pique',
            'Pases en movimiento',
          ],
        ),
        SesionPlan(
          numero: 3,
          titulo: 'Entrada a canasta',
          objetivo: 'Bandeja coordinando pasos y balón.',
          contenidos: [
            'Ritmo de dos pasos',
            'Bandeja por derecha e izquierda',
            'Entrada tras bote',
          ],
        ),
        SesionPlan(
          numero: 4,
          titulo: 'El tiro',
          objetivo: 'Mecánica de tiro a media distancia y libre.',
          contenidos: [
            'Mecánica: pies, codo y muñeca',
            'Tiro cercano y tiro libre',
            'Tiro tras recepción',
          ],
        ),
        SesionPlan(
          numero: 5,
          titulo: 'Evaluación intermedia',
          objetivo: 'Medir bote, pase, bandeja y tiro.',
          contenidos: [
            'Circuito técnico completo',
            'Juego reducido 3v3',
            'Registrar nivel por habilidad de cada alumno',
          ],
        ),
        SesionPlan(
          numero: 6,
          titulo: 'Defensa y rebote',
          objetivo: 'Defensa individual y ganar el rebote.',
          contenidos: [
            'Posición defensiva y desplazamientos',
            'Bloqueo de rebote (box out)',
            'Rebote ofensivo y defensivo',
          ],
        ),
        SesionPlan(
          numero: 7,
          titulo: 'Táctica: espacios y superioridades',
          objetivo: 'Jugar sin balón y aprovechar 2v1/3v2.',
          contenidos: [
            'Desmarque y pasar-cortar',
            'Contraataque 2v1',
            'Espaciado en media cancha',
          ],
        ),
        SesionPlan(
          numero: 8,
          titulo: 'Partido y evaluación final',
          objetivo: 'Competir y cerrar evaluando cada habilidad.',
          contenidos: [
            'Partido 5v5 aplicando lo trabajado',
            'Evaluación final por habilidad',
            'Feedback individual y metas del próximo ciclo',
          ],
        ),
      ],
    );
