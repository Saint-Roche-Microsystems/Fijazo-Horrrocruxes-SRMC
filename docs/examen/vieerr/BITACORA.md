# Bitácora — Examen Final

---

## 0. Identificación

| | |
|---|---|
| **Nombre** | Olivier Paspuel |
| **Usuario GitHub** | @vieerr |
| **Grupo / Proyecto** | Grupo 1 — Fijazo · `Saint-Roche-Microsystems/Fijazo-Horrrocruxes-SRMC` |
| **Actividad asignada** | **B — Nuevo salto síncrono con contrato** |
| **Rama** | `exam/vieerr` (repo maestro y submódulos `users-service` y `progression-service`) |
| **Tag** | `examen-vieerr` |
| **Pull Request** | https://github.com/Saint-Roche-Microsystems/Fijazo-Horrrocruxes-SRMC/pull/56 · submódulos: [Users-Service#3](https://github.com/Saint-Roche-Microsystems/Users-Service/pull/3) · [Progression-Service#2](https://github.com/Saint-Roche-Microsystems/Progression-Service/pull/2) |
| **Tarjeta Kanban** | `T-041` en el Project [Fijazo-To-Do](https://github.com/orgs/Saint-Roche-Microsystems/projects), issue [#57](https://github.com/Saint-Roche-Microsystems/Fijazo-Horrrocruxes-SRMC/issues/57), en **Done** y enlazada al PR #56 (captura: `kanban.png`) |
| **¿Hiciste el Paso 0?** | No — la actividad B no lo tiene. El transporte síncrono con contrato ya existía: `users-service/src/users/users.messages.controller.ts:29` (`@MessagePattern('users.validate')`) y su cliente en `bets-service/src/bets_service/infrastructure/tcp/users_validator.py:36`. |

---

## 1. Qué construí

El contrato TCP entre servicios tiene un método nuevo, `users.profile`, que devuelve el
perfil de identidad de un usuario (`id`, `username`, `tier`, `role`, `active`,
`created_at`), y **progression-service lo consume**. Hasta ahora ese servicio pintaba el
`username` del ranking y calculaba la antigüedad de la cuenta leyendo la colección `users`
de su propia Mongo — un resto del monolito que en el despliegue real está vacía, porque los
usuarios viven en la base de users-service. El resultado era un ranking con los nombres en
blanco, antigüedad 0 para todo el mundo y un `200` con una fila vacía cuando se pedían las
estadísticas de un usuario que no existe.

Ahora el dato lo sirve quien es dueño de él, por el mismo transporte con contrato que ya
usaba bets-service, y los errores viajan tipados: `NOT_FOUND` e `INVALID_ARGUMENT` se
traducen a **404** y **400** en la API, y una caída de users-service a **503** en un tiempo
acotado, en vez de a un 500 o a una espera indefinida.

---

## 2. Anclaje con el repositorio de mi grupo — **obligatorio (C2)**

| Código preexistente | Archivo:línea | Cómo me conecto con él |
|---|---|---|
| Controlador de mensajes TCP (`@MessagePattern('users.validate')`) | `users-service/src/users/users.messages.controller.ts:29` | Añado `users.profile` **en ese mismo controlador**, no en uno nuevo: es el contrato que ya existía y el que `main.ts` conecta al transporte TCP. |
| `UsersService` (dueño de la colección `users`) | `users-service/src/users/users.service.ts:43` | Añado `getProfile()` junto a `validate()`, con el mismo `userModel` y el mismo `isValidObjectId` que usa `findOrFail()`. |
| Filtro global RPC del microservicio | `users-service/src/common/sentry-rpc-exception.filter.ts:7`, registrado en `users-service/src/main.ts:26` | Es el filtro por el que pasa mi error tipado. Lo extiendo (que devuelva la carga del `RpcException`) en lugar de registrar un segundo filtro. |
| Cliente TCP del framing de Nest | `bets-service/src/bets_service/infrastructure/tcp/users_validator.py:36` | Mi `TcpUserProfileClient` replica su framing `<longitud>#<json>`, su manejo de errores (`asyncio.TimeoutError, OSError, ValueError` → error de disponibilidad) y su estilo de documentación. |
| Cableado de puertos y fallback de desarrollo | `progression-service/src/progression_service/api/deps.py:80` (`get_bet_repository`) y `bets-service/.../users_validator.py:21` (`AlwaysValidUserValidator`) | Mi proveedor de perfil se cablea igual (factoría en `deps.py`, `Annotated[..., Depends(...)]`) y conserva un modo de desarrollo local, como el resto del repo. |
| Filtro de excepciones de dominio → HTTP | `progression-service/src/progression_service/main.py:203` (`status_map`) | Mis dos excepciones nuevas se registran **en ese mapa**; no añado handlers propios ni devuelvo `HTTPException` desde el router. |
| Proxy del gateway | `api-gateway/src/proxy/proxy.controller.ts:100` (`validateStatus: () => true` y `res.status(response.status)`) | Es lo que hace que el 404/400/503 de progression-service llegue al cliente tal cual: no hay que tocar el gateway para que el código correcto salga. |
| Consumidor de `progression.recalc` | `progression-service/src/progression_service/api/deps.py:145` (`build_progression_service`) | El consumer de RabbitMQ no pasa por `Depends`, así que también le paso el proveedor nuevo: el camino asíncrono usa el mismo grafo de objetos que el HTTP. |

**¿Qué convención del repositorio seguí para que mi código no desentone?**

Arquitectura hexagonal por capas, como el resto de los servicios FastAPI del grupo: entidad
de dominio pura (`domain/entities/user_profile.py`), puerto abstracto
(`domain/repositories/user_profile_provider.py`), adaptador de infraestructura
(`infrastructure/tcp/users_profile_client.py`) y cableado en `api/deps.py`. Los errores son
subclases de `DomainError` traducidas en un único sitio (`main.py`), nunca `HTTPException`
en el router. Los nombres de configuración copian los que bets-service ya usa para el mismo
servicio destino (`USERS_SERVICE_TCP_HOST`, `USERS_SERVICE_TCP_PORT`,
`USERS_SERVICE_TIMEOUT_SECONDS`), y el `.env.example` documenta qué pasa con el valor vacío,
igual que las demás secciones. En users-service, TypeScript con Nest: el patrón nuevo va en
el controlador de mensajes existente y el tipo de la respuesta se exporta desde
`users.service.ts` junto a `ValidateResult`. Commits en Conventional Commits, como en los
tres avances.

**¿Qué NO dupliqué, pudiendo hacerlo?**

- No creé un segundo controlador TCP: extendí `users.messages.controller.ts:29`.
- No registré un segundo filtro RPC en users-service ni un segundo handler de excepciones en
  progression-service: usé `sentry-rpc-exception.filter.ts` y el `status_map` de
  `main.py:203`.
- No copié a mano el cliente TCP de bets-service en otro punto del árbol: el adaptador vive
  en la capa de infraestructura de progression-service, que es quien hace la llamada.
- No borré ni reescribí `MongoUserRepository` (código de mis compañeros): lo dejé donde
  estaba y lo **envolví** con `MongoUserProfileProvider` para el modo de desarrollo.
- No añadí un endpoint HTTP nuevo en users-service para esta consulta, pudiendo hacerlo: el
  salto tenía que ser síncrono **con contrato**, y el contrato ya existía.

---

## 3. Decisiones técnicas

### Decisión 1 — Método nuevo (`users.profile`) en vez de ampliar `users.validate`
- **Qué decidí:** añadir un patrón nuevo al contrato en lugar de meter `username` y
  `created_at` en la respuesta de `users.validate`.
- **Alternativa que descarté:** ampliar `validate`, que ya viaja en cada creación de apuesta
  y "casi" traía lo que necesitaba.
- **Por qué:** `validate` responde una pregunta de autorización, y por eso trata al usuario
  inexistente como "no activo" (`users.service.ts:156`), sin error. Mi consulta es de lectura
  de identidad y necesita justo lo contrario: distinguir *no existe* (404) de *existe y está
  desactivado* (200 con `active: false`). Mezclarlas habría obligado a romper la semántica de
  `validate` para bets-service, que es su único consumidor y no pidió nada. Además `validate`
  hace un salto extra a auth-service (`users.service.ts:167`) que mi caso no necesita:
  reutilizarlo habría añadido latencia y un punto de fallo ajeno.

### Decisión 2 — Corregir el filtro RPC en vez de parsear el error envuelto
- **Qué decidí:** arreglar `sentry-rpc-exception.filter.ts` para que devuelva
  `exception.getError()`, la carga del `RpcException`, como hace el `BaseRpcExceptionFilter`
  de Nest.
- **Alternativa que descarté:** dejar el filtro como estaba y hacer que mi cliente Python
  leyera `err.error.code`.
- **Por qué:** el filtro, al reenviar la instancia entera, cambiaba la forma de **todos** los
  errores RPC del servicio, no sólo los míos; adaptarme habría dejado el contrato documentado
  de una forma y emitido de otra, y el siguiente consumidor habría vuelto a tropezar. Lo
  comprobé sobre el propio Nest antes de decidir (un `node -e` que serializa
  `new RpcException({code:'NOT_FOUND'})` devuelve `{"err":{"error":{…},"message":…}}`). Aun
  así, **el cliente acepta las dos formas**: no por indecisión, sino porque en un despliegue
  escalonado puede quedar un users-service viejo en el aire, y prefiero que en ese hueco un
  404 siga siendo un 404 y no un 503. Hay un test que fija ese caso.

### Decisión 3 — El usuario inexistente sube como 404 en vez de degradarse a fila vacía
- **Qué decidí:** que `StatisticsService.recalculate()` propague `NotFoundError`, y que sea
  el backfill (`recalculate_all`) el que omita con log a los usuarios sin perfil.
- **Alternativa que descarté:** mantener el `username = user.username if user else ""`
  original y no fallar nunca.
- **Por qué:** ese `else ""` es exactamente lo que ocultó el problema durante tres avances:
  la API respondía 200 y el ranking mostraba filas sin nombre, así que nadie lo veía.
  Recalcular la proyección de un usuario que no existe sólo puede materializar una fila
  fantasma en el ranking (hay un test que comprueba que no se hace `upsert`). En el backfill
  sí tolero la ausencia, porque ahí no hay ningún cliente a quien devolverle un 404 y un
  usuario borrado no puede impedir que se recalculen los demás.

### Decisión 4 — Leer la longitud del frame como unidades UTF-16, no como bytes
- **Qué decidí:** que el lector de frames cuente unidades UTF-16 para saber dónde termina
  el JSON, en vez de fiarse del número como si fueran bytes.
- **Alternativa que descarté:** dejar el lector como estaba y escribir los mensajes de
  error del contrato en ASCII, sin tildes.
- **Por qué:** esto no salió de los tests, salió de levantar el sistema en Docker: el caso
  del `user_id` mal formado devolvía **503** en vez de 400, con
  `Expecting ',' delimiter`. Nest calcula el prefijo con `messageData.length`
  (`@nestjs/microservices/helpers/json-socket.js:61`), que en JavaScript son unidades
  UTF-16; "inválido" ocupa un byte más que caracteres, así que el JSON llegaba cortado a
  media palabra. Escribir los mensajes sin tildes lo habría tapado dejando la trampa
  puesta para el siguiente campo con texto real — un `username` con acento habría vuelto a
  romperlo, y ahí ya no es un mensaje de error, es el dato. Es exactamente el mismo bug
  latente que tiene hoy `TcpUserValidator` en bets-service; lo dejo señalado abajo porque
  ese cliente no es de mi actividad.

### Decisión 5 — Puerto nuevo de un método en vez de reutilizar `UserRepository`
- **Qué decidí:** crear `UserProfileProvider` con un solo método.
- **Alternativa que descarté:** implementar el `UserRepository` existente sobre TCP.
- **Por qué:** **segregación de interfaces (ISP)**. `UserRepository`
  (`progression-service/src/progression_service/domain/repositories/user_repository.py:9`)
  tiene ocho métodos, casi todos de escritura (`create`, `set_active`,
  `record_login_failure`, `reset_login_failures`…), heredados de cuando el monolito era dueño
  de los usuarios. Implementarlo por TCP habría obligado a dejar seis métodos lanzando
  `NotImplementedError` — y a insinuar que este servicio puede escribir usuarios, que es justo
  lo que la separación de dominios prohíbe.

---

## 4. Las 3 preguntas de mi actividad

**Pregunta 1: ¿Por qué el contrato debe vivir en un lugar compartido y no duplicado dentro de cada servicio?**

> Porque un contrato duplicado deja de ser un contrato en cuanto una de las dos copias
> cambia, y nadie se entera hasta que falla en ejecución. En mi caso el contrato vive en un
> único sitio, el controlador de mensajes de su dueño
> (`users-service/src/users/users.messages.controller.ts`): allí se declaran el patrón, la
> forma de la respuesta y los códigos de error, y allí mismo está el test que fija el frame
> exacto. Mi cliente Python no puede "acordar" nada por su cuenta. Este repositorio es además
> un caso incómodo: cada microservicio es un submódulo git independiente, así que no hay un
> `libs/contracts` físico que ambos importen — la única defensa es que la declaración viva en
> el dueño y que cada extremo tenga su test de contrato, para que un desajuste salga en CI y
> no en producción. La consecuencia práctica la tuve delante: el `created_at` que emite Nest
> es un ISO-8601 con sufijo `Z` y `datetime.fromisoformat` no lo digiere en cualquier
> versión, así que el adaptador lo normaliza en un único punto
> (`users_profile_client.py`, `_parse_datetime`) en vez de que cada llamador lo adivine.

**Pregunta 2: ¿Qué código de error del transporte elegiste para "no encontrado" y a qué código HTTP lo mapeas? ¿Por qué no es correcto devolver 500?**

> Elegí `NOT_FOUND` como código del contrato (y `INVALID_ARGUMENT` para el argumento
> inválido), con los nombres de gRPC porque es la convención de transporte síncrono con
> contrato del curso y porque el transporte real aquí —TCP de Nest— no trae códigos propios:
> el `err` del frame es lo que uno meta dentro del `RpcException`. La cadena completa es:
> `users.messages.controller.ts` lanza `RpcException({code:'NOT_FOUND'})` → el cliente lo
> traduce a `NotFoundError` (`users_profile_client.py`, `_raise_from_err`) → el `status_map`
> de `progression-service/src/progression_service/main.py:203` lo convierte en **404** → el
> gateway hace proxy conservando el status (`proxy.controller.ts:99`). `INVALID_ARGUMENT` →
> `InvalidArgumentError` → **400**; users-service caído → **503**.
>
> Devolver 500 sería mentir sobre de quién es el problema. Un 500 significa "fallé yo, y
> repetir la misma petición no depende de ti"; un usuario que no existe es una pregunta
> legítimamente respondida. En concreto: con 500 el frontend no puede decidir si pintar
> "usuario no encontrado" o reintentar, un reintento automático insistiría eternamente sobre
> algo que nunca va a cambiar, y las alertas de Sentry se llenarían de eventos que no son
> incidentes. Por eso el 503 sí lo reservo para la caída real de users-service: ahí el
> reintento sí tiene sentido y el estado es genuinamente "no lo sé todavía".

**Pregunta 3: Si mañana añades un campo nuevo al contrato, ¿siguen funcionando los clientes que no lo conocen? ¿Por qué?**

> Sí, y es una propiedad del diseño, no una casualidad. La respuesta viaja como un objeto
> JSON y mi cliente lee **campo a campo por nombre**, con valor por defecto
> (`response.get("tier") or "standard"`, `response.get("created_at")` → `None` si falta), sin
> exigir que no sobre nada ni depender del orden. Un campo nuevo lo ignora; un campo que
> falte no lo rompe. Lo mismo hace el `TcpUserValidator` de bets-service con `users.validate`,
> así que la convención ya estaba en el repo. Lo que **no** es compatible hacia atrás es
> quitar o renombrar un campo, cambiar su tipo, o añadir un código de error nuevo esperando
> que el consumidor lo entienda: mi cliente traduce los códigos que conoce y manda el resto a
> `UserProfileUnavailableError` (503), que es un fallo seguro pero no el código correcto. Por
> eso los cambios compatibles son *añadir*, y el resto exige un patrón nuevo — que es
> exactamente lo que hice aquí en vez de tocar `users.validate`.

---

## 5. Uso de Inteligencia Artificial — **obligatorio**

**¿Usaste IA en este examen?**  ☑ Sí  ☐ No

| # | Qué le pedí | Qué me devolvió | Qué corregí, adapté o descarté — y por qué |
|:--:|---|---|---|
| 1 | Cómo serializa Nest un `RpcException` cuando el microservicio tiene registrado un filtro global propio, para saber qué recibe exactamente un cliente que no es de Nest. | La explicación de que el `BaseRpcExceptionFilter` devuelve `exception.getError()`, y de que un filtro propio que reenvíe la instancia cambia esa forma. | La explicación era correcta pero no me fiaba, porque de ese detalle dependía todo el manejo de errores: lo verifiqué a mano contra el `node_modules` del propio repo (`rpc-exception.js`, `server.js`) y con un `node -e` que serializa el objeto. Salió `{"err":{"error":{…},"message":…}}`, que confirmó el envoltorio. Sin esa comprobación habría escrito el cliente contra la forma equivocada. |
| 2 | Un borrador de docstring en español para el puerto y la entidad nuevos, en el tono del resto del repo. | Docstrings correctos pero genéricos ("Repositorio de usuarios", "Devuelve el usuario"). | Los reescribí casi enteros: en este repositorio los docstrings explican **por qué** existe la pieza, no qué hace la línea siguiente. Les puse la razón real (por qué el puerto está separado del `UserRepository` heredado, por qué la colección `users` local está vacía), que es lo que un compañero necesita para no volver a leerla mal. |
| 3 | Ayuda con la documentación: pasar mis notas sueltas a la estructura de la bitácora y redactar la descripción del PR a partir del `git diff`. | Un borrador ordenado de las secciones y un resumen del diff por servicio. | Rehice las partes que hablaban del sistema: el borrador describía *qué* cambia cada archivo, no *por qué* —que es lo que se evalúa— y daba por buena la explicación del problema sin comprobarla. Reescribí el diagnóstico (la colección `users` vacía, las bases separadas) y verifiqué uno por uno los `archivo:línea` de la sección 2, que estaban desplazados porque mis propios cambios habían movido las líneas. |
| 4 | Ideas de nombre para el código de error del argumento inválido y para el caso de timeout. | Sugirió `BAD_REQUEST` / `VALIDATION_ERROR`, y una excepción de timeout propia. | Descarté las dos. `BAD_REQUEST` es vocabulario HTTP y este contrato no es HTTP: usé `INVALID_ARGUMENT`, el vocabulario de transporte con contrato que sigue el curso. Y no hice una excepción de timeout aparte: el repo ya trata timeout y socket caído como lo mismo (`UserValidationUnavailableError` en bets-service), porque al llamador le da igual la causa — lo que necesita saber es que no hay respuesta. Mantener esa simetría vale más que un nombre más preciso. |

**¿En qué se equivocó respecto a mi repositorio?**

En dos cosas concretas, las dos porque no conoce el estado real del código:

1. Dio por hecho que el error tipado llegaría al cliente como `err.code`, que es lo que
   documenta Nest. Aquí no era cierto, porque `SentryRpcExceptionFilter` sustituye al filtro
   por defecto y reenvía la instancia entera. Lo detecté antes de escribir el cliente porque
   desconfié justo del punto del que dependía todo el mapeo de errores: fui al `node_modules`
   a leer `rpc-exception.js` y `server.js`, y lo reproduje con un `node -e`. Acabó siendo el
   hallazgo más útil del examen — era un fallo real del sistema que ningún consumidor había
   notado, porque hasta ahora ningún error RPC del contrato era tipado.
2. Propuso que progression-service pidiera el perfil por HTTP a `GET /users/{id}` de
   users-service, "que seguro existe". Existe, pero es la superficie pública que el gateway
   expone al frontend y devuelve el `UserResponseDto` **con el email**; además la actividad
   pide un salto síncrono **con contrato**, y el contrato de este sistema es el transporte
   TCP. Lo vi al abrir `users.controller.ts` y `user-response.dto.ts` para comprobar qué
   devuelven de verdad.

---

## 6. Evidencia

| Archivo | Qué demuestra |
|---|---|
| `antes-sin-metodo.txt` | Que la consulta no existía: el contrato TCP sólo tenía `users.validate`, y progression-service resolvía el perfil contra su propia Mongo (base distinta a la de users-service). |
| `antes-username-vacio.txt` | Comportamiento previo en ejecución real: `GET /statistics/{id}` de un usuario **existente** devuelve 200 con `"username": ""`, y un id **inexistente** devuelve 200 igualmente. |
| `despues-caso-ok.txt` | La misma petición con el cambio: 200 con el `username` real, resuelto por `users.profile`. |
| `despues-caso-error.txt` | Casos de error con el código HTTP correcto: usuario inexistente → **404**, id mal formado → **400**, users-service caído → **503**. |
| `despues-tests.txt` | Salida de las suites automatizadas de los dos servicios. |
| `kanban.png` | Tarjeta del examen movida a *Hecho* y enlazada al PR. |

**Cómo reproducir mi cambio desde cero:**

```bash
git clone --recurse-submodules https://github.com/Saint-Roche-Microsystems/Fijazo-Horrrocruxes-SRMC.git
cd Fijazo-Horrrocruxes-SRMC
git checkout exam/vieerr && git submodule update --init --recursive
node scripts/bootstrap.mjs
docker compose up --build -d

# 1. Registro + login (el gateway es el único puerto público)
curl -s -X POST localhost:3000/auth/register -H 'content-type: application/json' \
  -d '{"username":"olivier","email":"olivier@fijazo.com","password":"secret123"}'
TOKEN=$(curl -s -X POST localhost:3000/auth/login -H 'content-type: application/json' \
  -d '{"email":"olivier@fijazo.com","password":"secret123"}' \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
USER_ID=$(python3 -c 'import base64,json,sys;p=sys.argv[1].split(".")[1];print(json.loads(base64.urlsafe_b64decode(p+"=="))["sub"])' "$TOKEN")

# 2. Caso principal: el username sale del contrato users.profile
curl -i -s localhost:3000/statistics/$USER_ID -H "Authorization: Bearer $TOKEN"

# 3. Casos borde
curl -i -s localhost:3000/statistics/000000000000000000000000 -H "Authorization: Bearer $TOKEN"  # 404
curl -i -s localhost:3000/statistics/no-es-un-objectid        -H "Authorization: Bearer $TOKEN"  # 400
docker compose stop users-service
curl -i -s localhost:3000/statistics/$USER_ID -H "Authorization: Bearer $TOKEN"                  # 503
```

---

## 7. Prueba automatizada

| | |
|---|---|
| **Archivo de la prueba** | `progression-service/tests/test_tcp_user_profile_client.py` y `progression-service/tests/test_statistics_user_profile_errors.py` (consumidor); `users-service/src/users/tcp-user-profile.e2e.spec.ts` (contrato, extremo del dueño) |
| **Comando para ejecutarla** | `cd progression-service && poetry run pytest -q` · `cd users-service && npx jest tcp-user-profile` |
| **Qué verifica** | Que el cliente traduce el contrato a dominio y **sólo** a dominio: `NOT_FOUND` → 404, `INVALID_ARGUMENT` → 400, y timeout / conexión rechazada / error no tipado → 503, sin propagar ninguna excepción de socket; que `GET /statistics/{id}` devuelve esos códigos de punta a punta y **no materializa** estadísticas cuando el perfil no se pudo resolver; y, del lado de users-service, la forma exacta del frame TCP —incluidos los errores tipados— y que la respuesta no lleva email ni hash de contraseña. |
| **¿Falla sin mi cambio?** | Sí, comprobado de dos formas. (1) Dejando los tests y revirtiendo la implementación, la suite de progression-service ni siquiera importa: `ModuleNotFoundError: progression_service.infrastructure.tcp.users_profile_client` — el contrato y su cliente *son* el cambio. (2) La verificación que no depende de que exista mi código: la aserción central de `test_unknown_user_is_404_not_an_empty_row` es que un usuario inexistente devuelve 404, y contra el sistema anterior levantado en Docker esa misma petición devolvía **200** con `"username": ""` (ver `antes-username-vacio.txt`). |

*Salida de las pruebas pasando:* `despues-tests.txt` (64 en progression-service, 5 en users-service).

---

## 8. Estado final — honesto

**Funciona:**
- `users.profile` en el contrato TCP, con validación de entrada y errores tipados.
- progression-service resuelve el perfil por TCP: `username` real en estadísticas y ranking,
  y antigüedad de cuenta real en el cálculo de rango y logros.
- Traducción completa a HTTP: 200 / 404 / 400 / 503, conservada por el proxy del gateway.
- Destino caído: el consumidor responde en un tiempo acotado
  (`USERS_SERVICE_TIMEOUT_SECONDS`, 5 s por defecto) en vez de colgarse.
- 13 pruebas nuevas en progression-service (64 en total, todas en verde) y 5 en
  users-service.
- Verificado en ejecución real, con el sistema levantado en Docker: ver
  `antes-username-vacio.txt` y `despues-caso-ok.txt` / `despues-caso-error.txt`.

**Matiz honesto sobre el 503:** sólo se llega al contrato cuando hay que **recalcular**.
Un usuario cuyas estadísticas ya están materializadas se sirve de la proyección y responde
200 aunque users-service esté caído — no es un fallo, es la proyección haciendo su trabajo,
pero conviene decirlo porque el 503 de la evidencia se captura con un usuario sin
estadísticas previas.

**No funciona / quedó incompleto:**
- El camino de progresión (`/ranks`, `/achievements`) resuelve el perfil **dos veces** por
  recálculo: una en `StatisticsService.recalculate()` y otra en
  `ProgressionService._evaluate()`. Es correcto, pero son dos round-trips TCP donde bastaría
  uno.
- El filtro RPC de users-service manda a Sentry también mis errores de cliente (`NOT_FOUND`,
  `INVALID_ARGUMENT`), que no son incidentes. No lo cambié porque la observabilidad es la
  actividad de otro compañero y no quise pisar ese trabajo, pero lo dejo señalado.
- La prueba de users-service necesita Redis levantado, porque `UsersModule` arrastra el
  consumer de `security-events`. Es una condición previa del módulo, no de mi test.
- `bets-service` tiene el mismo bug de longitud UTF-16 en su `TcpUserValidator`
  (`_read_frame`), latente porque `users.validate` hoy sólo devuelve booleanos y
  `tier`. No lo toqué: ese cliente pertenece a otro salto y a otra actividad, pero está
  a una línea de romperse el día que su contrato devuelva texto.
- El `poetry.lock` de progression-service está desactualizado respecto a su `pyproject.toml`
  (le falta `sentry-sdk`), así que `poetry install` no basta para correr la suite en limpio.
  Es anterior a mi rama y no lo regeneré: habría metido en mi diff un archivo que mi
  actividad no necesita.

**Cuál era mi siguiente paso:**

Pasar el perfil ya resuelto desde `StatisticsService` a `ProgressionService._evaluate()`
para eliminar el segundo round-trip, y añadir a `tests-integration/` un caso que hable con
el users-service real en vez de con el servidor asyncio simulado: es lo único que hoy
garantizaría que las dos mitades del contrato siguen de acuerdo.

---

## 9. Declaración

> Declaro que este trabajo es individual, que corresponde a la actividad que me fue
> asignada, y que la sección 5 refleja de forma completa y veraz el uso que hice de
> herramientas de Inteligencia Artificial durante el examen.

**Nombre:** Olivier Paspuel
**Fecha:** 27 de julio de 2026
