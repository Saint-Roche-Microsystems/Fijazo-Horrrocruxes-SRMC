# Bitácora — Examen Final

---

## 0. Identificación

| | |
|---|---|
| **Nombre** | Antonio Adrian Revilla Anchapaxi |
| **Usuario GitHub** | @RevillaA |
| **Grupo / Proyecto** | Grupo 1 — Fijazo · `Saint-Roche-Microsystems/Fijazo-Horrrocruxes-SRMC` |
| **Actividad asignada** | C — Consumidor asíncrono idempotente |
| **Rama** | `exam/RevillaA` (repo principal **y** submódulo `progression-service`) |
| **Tag** | `examen-RevillaA` |
| **Pull Request** | Repo principal: https://github.com/Saint-Roche-Microsystems/Fijazo-Horrrocruxes-SRMC/pull/59 · Progression-Service: *(enlace a completar tras abrirla)* |
| **Tarjeta Kanban** | *(enlace a completar)* |
| **¿Hiciste el Paso 0?** | No aplica — la Actividad C no tiene Paso 0 (solo A y D lo requieren). |

---

## 1. Qué construí

Extendí `ProgressionRecalcConsumer` (el consumer que ya escuchaba `bets.events` en
`progression-service`) para que ignore un evento que ya procesó. Antes, si RabbitMQ
reentregaba el mismo mensaje —algo que la entrega "al menos una vez" garantiza que va a
pasar tarde o temprano—, el consumer repetía la llamada HTTP a bets-service y el upsert en
Mongo sin darse cuenta de que ya lo había hecho. Ahora calcula una clave a partir de
`event_type`+`bet_id`+`occurred_at`, la busca en una colección nueva
(`processed_bet_events`) antes de recalcular, y si ya existe descarta el mensaje con un log
distinguible en vez de volver a golpear bets-service. Lo comprobé en vivo con
`docker compose`: publicando el mismo evento dos veces contra el código original obtuve dos
recálculos; contra el código con el cambio, uno solo.

---

## 2. Anclaje con el repositorio de mi grupo — **obligatorio (C2)**

| Código preexistente | Archivo:línea | Cómo me conecto con él |
|---|---|---|
| `RabbitMqBetEventPublisher.publish` | `bets-service/src/bets_service/infrastructure/events/rabbitmq_publisher.py:24-33` | Es el evento que endurezco: no lo toco, solo consumo lo que ya publica en `bets.events`. |
| `ProgressionRecalcConsumer.handle` (ya existía) | `progression-service/src/progression_service/infrastructure/events/rabbitmq_consumer.py:86` | Extendí el método existente con un chequeo antes de `recalculate()` (línea 110) y un `mark_processed` después (línea 146). No creé un consumer paralelo. |
| `ProgressionRepository` / `BetRepository` (puertos existentes) | `progression-service/src/progression_service/domain/repositories/progression_repository.py` | Copié su mismo patrón (ABC + métodos async) para `ProcessedEventRepository`. |
| `MongoProgressionRepository` (implementación existente) | `progression-service/src/progression_service/infrastructure/repositories/mongo_progression_repository.py:32-47` | Mismo patrón para `MongoProcessedEventRepository`: una clase por colección, inyectada con `AsyncDatabase`. |
| Construcción del consumer en el lifespan | `progression-service/src/progression_service/main.py:96-99` | Añadí una línea (`MongoProcessedEventRepository(db)`) al mismo lugar donde ya se armaba `ProgressionRecalcConsumer`, no un cableado nuevo. |

**¿Qué convención del repositorio seguí para que mi código no desentone?**
La arquitectura hexagonal que ya usa progression-service: puerto abstracto en
`domain/repositories/`, implementación concreta en `infrastructure/repositories/`, inyectado
donde ya se construían los demás repositorios (`api/deps.py` para HTTP, `main.py` para el
consumer). También seguí su convención de logging estructurado (`logger.info(..., extra={...})`)
y su política de ack/nack ya documentada en el docstring del módulo.

**¿Qué NO dupliqué, pudiendo hacerlo?**
No creé un segundo consumer de `bets.events`, ni una cola nueva, ni un microservicio nuevo
(fue mi primer instinto y lo descarté, ver sección 5). Extendí el `ProgressionRecalcConsumer`
que ya existía en `infrastructure/events/rabbitmq_consumer.py:54`, y reutilicé el mismo
`db` de Mongo que ya usan `MongoProgressionRepository` y `MongoStatisticsRepository` en vez
de levantar una base de datos aparte.

---

## 3. Decisiones técnicas

### Decisión 1
- **Qué decidí:** derivar la clave de idempotencia de campos que el evento ya trae
  (`event_type`+`bet_id`+`occurred_at`) en vez de añadir un `event_id` nuevo al contrato de
  `BetEvent`.
- **Alternativa que descarté:** ampliar `bets_service.domain.entities.bet_event.BetEvent`
  con un campo `event_id` (UUID) explícito.
- **Por qué:** un `event_id` nuevo es más literal con el enunciado, pero obliga a modificar
  `bets-service` —un servicio que no es mío en esta actividad— para un beneficio marginal:
  RabbitMQ reentrega el mensaje con los mismos bytes, así que `event_type`+`bet_id`+`occurred_at`
  ya identifican la entrega de origen sin tocar un contrato ajeno. Mantiene mi cambio dentro
  de un solo servicio y un solo PR.

### Decisión 2
- **Qué decidí:** marcar la clave como procesada **después** de `recalculate()` y **antes**
  del `ack`.
- **Alternativa que descarté:** marcarla **antes** de llamar a `recalculate()`.
- **Por qué:** si el proceso muere justo entre marcar y recalcular, marcar-antes deja el
  evento como "procesado" sin haberse aplicado nunca — se pierde para siempre. Marcar-después
  tiene una ventana peor en apariencia (un fallo ahí sí puede recalcular de más), pero
  `recalculate()` ya es idempotente en Mongo (hace `upsert` recomputando desde bets-service),
  así que esa ventana cuesta trabajo repetido, no datos incorrectos. Es la respuesta a la
  pregunta 2 de mi actividad.

### Decisión 3
- **Qué decidí:** usar `_id` de Mongo como la propia clave del evento en
  `processed_bet_events`, en vez de un campo `event_key` con un índice único aparte.
- **Alternativa que descarté:** un campo `event_key: str` normal + `create_index("event_key",
  unique=True)`, como hace `ensure_indexes()` con `user_id` en `user_progression`.
- **Por qué:** Mongo ya garantiza unicidad de `_id` sin crear ningún índice adicional; es
  menos código para la misma garantía. Lo dejé anotado porque, si alguien lee
  `MongoProcessedEventRepository` sin este contexto, `_id` como clave de negocio no es obvio.

---

## 4. Las 3 preguntas de mi actividad

**Pregunta 1: ¿Por qué la garantía "al menos una vez" obliga a que la idempotencia viva en el consumidor y no en el publisher?**

> El publisher (`RabbitMqBetEventPublisher.publish`, bets-service) no tiene forma de saber si
> el mensaje que acaba de mandar ya llegó antes: desde su lado, cada llamada a `publish()` es
> un evento nuevo y legítimo. La duplicación no ocurre al publicar, ocurre en el transporte —
> un `nack`, una reconexión del canal, una redelivery de RabbitMQ— que está completamente
> fuera del control del publisher. El único punto del sistema que *ve* la entrega repetida
> (dos mensajes con el mismo contenido llegando por la misma cola) es el consumidor, así que
> es el único lugar donde detectarla es siquiera posible.

**Pregunta 2: ¿Dónde guardas la clave procesada, y qué ocurre si el proceso muere entre aplicar el efecto y guardar la clave? ¿Qué harías para cerrar esa ventana?**

> La guardo en Mongo, en la colección `processed_bet_events` de progression-service
> (`MongoProcessedEventRepository`, misma base que usa el resto del servicio). Marco la clave
> **después** de `recalculate()` y antes del `ack` (Decisión 2). Si el proceso muere en esa
> ventana, el mensaje nunca se confirma: RabbitMQ lo reentrega, y como la clave no llegó a
> guardarse, se recalcula una vez más. No es gratis, pero tampoco es incorrecto:
> `recalculate()` es idempotente en el estado final (hace `upsert` recomputando desde
> bets-service), así que el peor caso es trabajo repetido, no una progresión inconsistente.
> Para cerrar la ventana del todo haría falta una transacción que cubra el upsert de
> progresión y el marcado de la clave en la misma operación atómica —Mongo lo permite con
> transacciones multi-documento sobre un mismo cluster—, pero para el alcance de esta
> actividad el costo (trabajo repetido, no datos malos) me pareció aceptable frente a la
> complejidad de coordinar dos escrituras atómicamente.

**Pregunta 3: ¿Qué diferencia hay entre reintentar un mensaje y mandarlo a una cola de mensajes muertos (DLQ)? ¿Cuándo conviene cada uno?**

> Reintentar (mi `nack(requeue=True)` en el caso `BetSourceUnavailableError`, ya existente en
> `rabbitmq_consumer.py`) asume que el fallo es transitorio: bets-service está caído *ahora*
> pero va a volver, así que vale la pena que el mensaje espere en la cola y se reintente. Una
> DLQ asume lo contrario: el mensaje en sí es el problema (payload corrupto, un bug que lo
> hace fallar siempre) y reintentarlo indefinidamente no lo va a arreglar, solo quema CPU en
> un bucle cerrado — por eso el propio módulo, en el caso "cualquier otro error", lo descarta
> sin requeue en vez de reintentarlo para siempre. Mi consumidor de bets.events no tiene DLQ
> configurada (no la declaré, no es parte de la topología existente en
> `rabbitmq/definitions.json`), así que ese caso hoy se resuelve descartando y confiando en
> Sentry + el siguiente evento del usuario para reparar la proyección — lo mismo que ya hacía
> el consumer antes de mi cambio. Añadir una DLQ de verdad sería el siguiente paso si este
> descarte silencioso resultara insuficiente en producción.

---

## 5. Uso de Inteligencia Artificial — **obligatorio**

**¿Usaste IA en este examen?** ☒ Sí ☐ No

| # | Qué le pedí | Qué me devolvió | Qué corregí, adapté o descarté — y por qué |
|:--:|---|---|---|
| 1 | Analizar la actividad C y proponer cómo implementarla sobre mi repo. | Un plan para modificar directamente `progression-service` (el consumer que ya existía), citando `rabbitmq_consumer.py`. | Lo acepté en líneas generales, pero le pedí que revisara si el "bug" de duplicado realmente existía: `ProgressionService.recalculate` ya hace `upsert` recalculando desde la fuente de verdad, así que el estado final en Mongo nunca queda duplicado — el problema real es el trabajo repetido (HTTP + upsert de más), no un documento duplicado. Reformulé el enfoque a partir de esa corrección. |
| 2 | Le pedí construir la idempotencia. | Primero propuso (y yo aprobé sin pensarlo bien) crear un **microservicio nuevo** (`bet-audit-service`) para no tocar `bets-service` ni `progression-service`, con su propio Mongo, Dockerfile, etc. | Lo descarté a medio construir: era sobre-ingeniería para lo que pide la actividad (~70 min de código) y, más importante, la consigna real permite modificar los microservicios existentes mientras el cambio quede en mi rama — crear un servicio aparte era más trabajo y menos "integración real" (C2) que extender el consumer que ya hace exactamente este trabajo. Volví al plan original. |
| 3 | Le pedí la clave de idempotencia siguiendo el enunciado ("el evento viaja con un identificador único"). | Primero sugirió derivar la clave de campos existentes sin más explicación. | Le exigí que no asumiera nada y revisara el enunciado literal antes de decidir; la IA confirmó que `event_type`+`bet_id`+`occurred_at` cumplen "identificador único" sin ampliar el contrato de `BetEvent`, y lo dejé así, mejor documentado en la bitácora (Decisión 1). |
| 4 | Le pedí escribir los comentarios/docstrings del código nuevo. | Docstrings de 4-6 líneas explicando el razonamiento completo de cada decisión. | Le pedí que los recortara: eran más largos de lo necesario para lo que aportaban. Los reduje a 1-2 líneas por comentario, y tuve que corregir manualmente dos archivos donde el recorte se aplicó solo en memoria y no se había commiteado (ver más abajo). |

**¿En qué se equivocó respecto a mi repositorio?**
El error más costoso fue el del punto 2: propuso construir `bet-audit-service` como
microservicio nuevo — llegó a crear `pyproject.toml`, `Dockerfile`, estructura de carpetas y
parte del dominio — antes de que yo cayera en cuenta de que la actividad sí permite tocar
`bets-service`/`progression-service` si es necesario, y que ese camino era mucho más eficiente.
Ese trabajo nunca se llegó a commitear (lo verifiqué con `git status` antes de descartarlo),
así que no quedó rastro en el historial, pero costó tiempo real dentro del bloque. También, al
gestionar el submódulo `progression-service`, en un punto dejó dos archivos con docstrings
recortados sin commitear después de haber commiteado la versión larga — lo detecté con
`git status` mostrando `modified` en archivos que yo creía ya cerrados, y lo corregí con un
commit `style(progression): recortar docstrings largos` antes de hacer push.

---

## 6. Evidencia

| Archivo | Qué demuestra |
|---|---|
| `antes-test-sin-idempotencia.txt` | Los 15 tests de `test_rabbitmq_consumer.py` (incluidos los de deduplicación) corridos contra el consumer **antes** de mi cambio (commit `bb62405`, vía `git worktree`): fallan porque el constructor no acepta `processed_events`. |
| `despues-test-con-idempotencia.txt` | Suite completa de `progression-service` con mi cambio aplicado: **55/55** en verde. |
| `antes-evento-duplicado.txt` | Logs reales de `progression-service` corriendo el código previo (`bb62405`) en un contenedor Docker separado, en la misma red: publiqué el mismo `bet.created` dos veces y las dos veces logueó `"Progresión recalculada por evento."` — el efecto se duplicó. |
| `despues-evento-duplicado.txt` | Mismo experimento, mismo evento, contra el código con mi cambio: una `"Progresión recalculada por evento."` y un `"Evento descartado: ya se había procesado."` con el `event_key`. |
| `despues-mongo-processed-events.txt` | Consulta directa a Mongo (`processed_bet_events` y `user_progression`) confirmando una sola clave procesada y un solo documento de progresión para el usuario de prueba. |

**Cómo reproducir mi cambio desde cero:**

```bash
# 1. Levantar la infraestructura y los servicios relevantes
docker compose up -d --build mongo-auth mongo-users mongo-bets mongo-progression \
  redis rabbitmq auth-service users-service bets-service progression-service

# 2. Publicar el mismo evento dos veces directo al exchange bets.events
#    (script en docs/examen/RevillaA/publish_duplicate.py, requiere aio_pika)
cd progression-service && poetry run python ../docs/examen/RevillaA/publish_duplicate.py

# 3. Ver el resultado en los logs
docker compose logs progression-service | grep -i "recalculada\|descartado"

# 4. Verificar en Mongo que solo hay una clave procesada
docker exec fijazo-horrrocruxes-srmc-mongo-progression-1 mongosh progression_service \
  --eval "db.processed_bet_events.find().pretty()"

# 5. Tests automatizados
cd progression-service && poetry run pytest tests/test_rabbitmq_consumer.py -v
```

---

## 7. Prueba automatizada

| | |
|---|---|
| **Archivo de la prueba** | `progression-service/tests/test_rabbitmq_consumer.py` (funciones `test_duplicate_event_recalculates_only_once`, `test_two_distinct_events_recalculate_twice`, `test_message_without_bet_id_is_acked_and_never_recalculates`, `test_message_without_occurred_at_is_acked_and_never_recalculates`) |
| **Comando para ejecutarla** | `poetry run pytest tests/test_rabbitmq_consumer.py -v` (dentro de `progression-service/`) |
| **Qué verifica** | Que procesar el mismo evento dos veces deje un solo recálculo, que dos eventos distintos recalculen dos veces, y que un evento con `bet_id`/`occurred_at` inválidos se descarte sin romper el consumer. |
| **¿Falla sin mi cambio?** | Sí — lo comprobé con `git worktree` contra el commit previo a mis cambios (`bb62405`): los 15 tests del archivo fallan (`TypeError: got an unexpected keyword argument 'processed_events'`). Salida completa en `antes-test-sin-idempotencia.txt`. |

*Salida de la prueba pasando (suite completa, 55/55):*

```
tests/test_rabbitmq_consumer.py::test_duplicate_event_recalculates_only_once PASSED
tests/test_rabbitmq_consumer.py::test_two_distinct_events_recalculate_twice PASSED
tests/test_rabbitmq_consumer.py::test_message_without_bet_id_is_acked_and_never_recalculates PASSED
tests/test_rabbitmq_consumer.py::test_message_without_occurred_at_is_acked_and_never_recalculates PASSED
...
============================= 55 passed in 11.17s ==============================
```

---

## 8. Estado final — honesto

**Funciona:**
- Deduplicación de `bet.created`/`bet.updated`/`bet.deleted` en `ProgressionRecalcConsumer`, verificada con tests y con ejecución real en Docker (antes/después).
- Casos borde: evento repetido (1 solo efecto), eventos distintos (2 efectos), payload inválido (se descarta sin tumbar el consumer), suite completa sin regresiones (55/55).

**No funciona / quedó incompleto:**
- No abrí una cola de mensajes muertos (DLQ) para los errores no transitorios; siguen descartándose con log, igual que antes de mi cambio (ver Pregunta 3).
- No até la tarjeta Kanban ni el PR del submódulo `Progression-Service` en el momento de escribir esto — quedan como acción manual mía fuera de este documento (ver sección 0).

**Cuál era mi siguiente paso:**
Abrir formalmente el PR de `Progression-Service` (el enlace de creación ya lo tengo), referenciarlo desde la PR #59 del repo principal, mover la tarjeta Kanban a Hecho, y empujar el tag `examen-RevillaA`.

---

## 9. Declaración

> Declaro que este trabajo es individual, que corresponde a la actividad que me fue asignada, y que la sección 5 refleja de forma completa y veraz el uso que hice de herramientas de Inteligencia Artificial durante el examen.

**Nombre:** Antonio Adrian Revilla Anchapaxi
**Fecha:** 2026-07-27
