import '../models/plan_trabajo.dart';

/// Plantillas de PLAN DE TRABAJO que trae Pichangol (editable por el profe).
/// Fase 1: TENIS (iniciación e intermedio). Después se replican fútbol/pádel/
/// natación con el mismo molde (solo cambian habilidades y sesiones).

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
