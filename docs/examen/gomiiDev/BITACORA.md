# Bitácora — Examen Final

---

## 0. Identificación

| | |
|---|---|
| **Nombre** | Carlos Hernández |
| **Usuario GitHub** | @gomiiDev |
| **Grupo / Proyecto** | Saint-Roche-Microsystems — Fijazo API |
| **Actividad asignada** | **A — Revocación de sesión JWT (logout real)** |
| **Rama** | `exam/gomiiDev` |
| **Tag** | `examen-gomiiDev` |
| **Pull Request** | *(pendiente — se enlaza al cierre)* |
| **Tarjeta Kanban** | T-039 — Revocación de sesión JWT (logout real) *(enlace pendiente)* |
| **¿Hiciste el Paso 0?** | **No** — el login JWT ya existía. Emisión del token en `auth-service/src/auth_service/core/security.py:29` (`create_access_token`), ruta de login en `auth-service/src/auth_service/api/routers/auth.py:42`, y validación en el borde con `api-gateway/src/auth/jwt-auth.guard.ts:20`. |

---

## 1. Qué construí

*(pendiente — se redacta al terminar la implementación)*

---

## 2. Anclaje con el repositorio de mi grupo — **obligatorio (C2)**

| Código preexistente | Archivo:línea | Cómo me conecto con él |
|---|---|---|
| `JwtAuthGuard` — guard global que valida firma y expiración del JWT | `api-gateway/src/auth/jwt-auth.guard.ts:25` (consulta en `:71`) | **Extendí este guard, no creé otro.** Le añadí una tercera dependencia por constructor (`RevokedTokenStore`) y la consulta de revocación después del `verify` existente. Su `canActivate` pasó de `boolean` a `Promise<boolean>`. |
| Registro del guard como `APP_GUARD` | `api-gateway/src/auth/auth.module.ts:13` | Intacto. Al seguir siendo el mismo guard global, la revocación se aplica automáticamente a **todas** las rutas protegidas del sistema, sin tocar ni un controller. |
| `SentryExceptionFilter` — tags `service`/`transport`/`failure_mode` | `api-gateway/src/common/sentry-exception.filter.ts:25-27` | Reutilicé ese mismo vocabulario de tags al reportar el fallo de Redis, con `failure_mode: 'fail-open'`. Los errores del store aparecen en Sentry con el mismo esquema que el resto del gateway. |
| Bloque `api-gateway` del compose | `docker-compose.yml:176` | Le añadí `REDIS_URI`, `REVOKED_TOKENS_KEY_PREFIX` y `redis` en `depends_on`, junto a las variables que ya tenía. No creé un compose aparte. |
| `create_access_token` — único punto de emisión del JWT | `auth-service/src/auth_service/core/security.py:34` | Le añadí el claim `jti` (UUID4) al payload existente `sub`/`role`/`exp`. No creé una función paralela de emisión: modifiqué la única que ya había, así que **todo** token del sistema queda revocable sin tocar ningún llamador. |
| `decode_access_token` — decodificación y validación del JWT | `auth-service/src/auth_service/core/security.py:50` | Lo reutilizo tal cual en el logout para recuperar `jti` y `exp` del token presentado. No escribí una segunda decodificación con `jwt.decode`: si el secreto o el algoritmo cambian, ambos caminos siguen coincidiendo. |
| Tabla `ROUTE_RULES` — fuente de verdad de qué rutas son públicas | `api-gateway/src/auth/route-rules.ts:14` | *(pendiente)* |
| `app.state.redis` — cliente Redis del ciclo de vida de la app | `auth-service/src/auth_service/main.py:62` | La lista de revocados reutiliza **esta misma conexión**. No abrí un cliente Redis nuevo ni añadí nada al `lifespan`: la conexión ya se crea al arrancar y se cierra en el `finally`. |
| `get_redis` / `get_security_event_publisher` — factorías de inyección | `auth-service/src/auth_service/api/deps.py:41` y `:47` | Añadí `get_revoked_token_store` calcado de `get_security_event_publisher` (mismos parámetros `redis` + `settings`, mismo retorno tipado por el puerto) y lo enchufé a `get_auth_service`. |
| `AuthService` — servicio de aplicación con `register` y `login` | `auth-service/src/auth_service/application/services/auth_service.py:33` | Le añadí el método `logout` **dentro de la misma clase**, no un servicio nuevo. Recibe el store como sexta dependencia opcional, igual que las cinco que ya tenía. |
| `SecurityEventPublisher` — puerto `Protocol` de la capa de aplicación | `auth-service/src/auth_service/application/ports.py:45` | Modelé `RevokedTokenStore` como un `Protocol` hermano, con el mismo estilo de docstring, para que el caso de uso dependa de la capacidad y no de Redis. |
| `RedisSecurityEventPublisher` — precedente de fail-open ante Redis caído | `auth-service/src/auth_service/infrastructure/events/redis_stream_publisher.py:30` | De aquí saqué la decisión de modo de fallo del guard (ver Decisión 2). El store de escritura hace lo contrario **a propósito**, y el porqué queda documentado en el propio código. |
| Excepciones de dominio → HTTP en el handler central | `auth-service/src/auth_service/main.py:154` | El logout lanza `InvalidCredentialsError` y el handler ya la traduce a 401 con `WWW-Authenticate: Bearer`. No registré ningún handler ni devolví `JSONResponse` a mano. |
| Fixture `test_redis` de la suite | `auth-service/tests/conftest.py:72` | La extendí para que limpie también las claves de revocación entre tests, en vez de crear una fixture paralela. |
| Servicio `redis` del stack | `docker-compose.yml:57` | Es el almacén de la lista de revocados. Ya estaba levantado para el stream `security-events`; no añadí ningún servicio nuevo al compose. |

**¿Qué convención del repositorio seguí para que mi código no desentone?**

*(pendiente)*

**¿Qué NO dupliqué, pudiendo hacerlo?**

*(pendiente)*

---

## 3. Decisiones técnicas

### Decisión 1
- **Qué decidí:** implementar `POST /auth/logout` **en auth-service**, no en el api-gateway. auth-service es el dueño del token: es donde se firma (`security.py:29`) y donde vive la información de las credenciales y los permisos que se emiten para el gateway. El gateway ya reenvía el header `Authorization` intacto (`proxy/proxy.controller.ts:47-50`), así que el servicio puede decodificar el token y extraer `jti` y `exp` con el `decode_access_token` que ya existe.
- **Alternativa que descarté:** un controller de logout propio dentro del api-gateway, registrado antes del catch-all `@All('*path')` del proxy (`proxy/proxy.controller.ts:31`), que escribiera directamente en Redis.
- **Por qué:** habría partido el dominio de autenticación entre dos repositorios — el token se firma en un servicio y se revoca en otro — y habría duplicado el manejo del token en el gateway. Además `SERVICE_MAP` (`proxy/service-map.ts:6`) ya declara que todo `/auth/*` pertenece a auth-service; meter ahí una excepción contradecía una convención explícita del repo. El coste de la alternativa era bajo (un submódulo menos que tocar), pero el precio arquitectónico no compensaba.

### Decisión 2
- **Qué decidí:** ante un Redis **caído o inaccesible**, el guard **falla abierto**: si no puede consultar la lista de revocados, registra el error y deja pasar el token siempre que la firma y la expiración sean válidas.
- **Alternativa que descarté:** fallar cerrado, es decir, rechazar con 401 cualquier petición mientras no se pueda verificar la lista.
- **Por qué:** el repositorio **ya tenía tomada esta misma decisión** en un caso equivalente: `RedisSecurityEventPublisher` (`infrastructure/events/redis_stream_publisher.py:30`) documenta explícitamente que "un Redis caído no debe tumbar el login", y el proyecto ya maneja `failure_mode="fail-open"` / `"fail-closed"` como vocabulario propio en `capture_error`. Ser coherente con esa decisión pesa más que mi preferencia personal. Fallar cerrado habría convertido a Redis en un punto único de fallo capaz de dejar sin servicio **todo** el tráfico autenticado del sistema, no solo el revocado. **Riesgo que acepto:** durante una caída de Redis, un token revocado vuelve a ser válido hasta que expire. Es una ventana acotada por el TTL del token y se prefiere frente a una caída total de la API.

---

## 4. Las 3 preguntas de mi actividad

**Pregunta 1: ¿Por qué el TTL de la entrada de revocación debe coincidir con la expiración del token, en vez de guardarla para siempre?**

> *(pendiente)*

**Pregunta 2: Si el almacén de revocados (Redis) está caído cuando llega una petición: ¿tu guard falla abierto (deja pasar) o falla cerrado (rechaza)? ¿Cuál elegiste y qué riesgo aceptas con esa decisión?**

> *(pendiente — ver Decisión 2)*

**Pregunta 3: ¿En qué se diferencia esto de simplemente borrar el token en el navegador del cliente?**

> *(pendiente)*

---

## 5. Uso de Inteligencia Artificial — **obligatorio**

**¿Usaste IA en este examen?**  ☑ Sí  ☐ No

Herramienta: **Claude (Claude Code)**, integrado en VS Code con acceso de lectura al repositorio.

| # | Qué le pedí | Qué me devolvió | Qué corregí, adapté o descarté — y por qué |
|:--:|---|---|---|
| 1 | Que analizara el repositorio del grupo y determinara qué exige la Actividad A antes de escribir nada, sin proponer código todavía. | Un mapa de la arquitectura con `archivo:línea`: el guard global en `jwt-auth.guard.ts:20`, su registro como `APP_GUARD` en `auth.module.ts:10`, y tres hallazgos — (a) el token **no** lleva `jti`, (b) las rutas públicas se deciden por la tabla `ROUTE_RULES` y no por el decorador `@Public()`, (c) Redis ya está en el `docker-compose`. Dejó tres decisiones abiertas en vez de resolverlas solo. | Acepté el análisis tras verificar yo mismo cada `archivo:línea` que citó. **No** le dejé decidir la ubicación del logout ni el modo de fallo: eran decisiones de arquitectura de *mi* sistema y las tomé yo (ver sección 3). Le exigí explícitamente que no tocara `route-rules.ts`. |
| 2 | La información para la tarjeta del Kanban, en el formato de tabla que ya usa el tablero del grupo. | Tarjeta **T-039** con título, responsable, descripción, alcance por submódulo, anclaje, criterios de aceptación y definición de hecho. Dedujo el ID mirando el máximo del historial (`T-038`). | Verifiqué que `T-039` fuera realmente el siguiente ID libre antes de crear la tarjeta. Descarté su propuesta alternativa de partirla en cuatro subtarjetas (T-039a…d) y la creé como una sola, para no desentonar con el resto del tablero, que usa una tarjeta por entregable. |
| 3 | Un plan de implementación dividido en 4 commits como mínimo, con la rama creada y la bitácora rellenándose a medida que avanzo. | Plan de 6 commits semánticos, con las ramas `exam/gomiiDev` en el superproyecto y los dos submódulos afectados, y el orden de push de submódulos antes que superproyecto. | Le quité el control de git: los commits los ejecuto yo, para revisar cada diff antes de que entre al historial. También decidí yo qué hacer con los tokens ya emitidos sin `jti` (dejarlos pasar hasta que expiren, en vez de invalidar todas las sesiones vivas al desplegar). |
| 4 | Que implementara el guard y las pruebas de revocación. | El guard extendido y una batería de tests. Entre ellos, uno llamado *"falla abierto: si el almacén de revocados no responde, el token pasa"* que en realidad afirmaba `rejects.toThrow()` — lo contrario de lo que dice su nombre — y que **pasaba en verde**. | Ver el apartado siguiente. Es el error más grave de la sesión y el que más me hizo revisar lo que estaba aceptando. |

**¿En qué se equivocó respecto a mi repositorio?**

**Caso 1 — un test que decía una cosa y comprobaba la contraria, en verde.** Al escribir las pruebas del guard, generó un caso titulado *"falla abierto: si el almacén de revocados no responde, el token pasa"* cuya aserción era `await expect(guard.canActivate(context)).rejects.toThrow()`. Es decir: el nombre prometía que la petición **pasa** y el código exigía que **falle**. Y salió en verde, que es lo que lo hacía peligroso.

*Cómo lo detecté:* me chocó que un test de "fail-open" esperara una excepción, y al mirarlo entendí la causa de fondo: el test inyectaba un `RevokedTokenStore` falso que lanzaba, pero **la política de fail-open no vive en el guard, vive dentro de `RevokedTokenStore.isRevoked`**, que captura el error y devuelve `false` (`api-gateway/src/auth/revoked-token.store.ts:80`). Al sustituir el store por un doble, el test saltaba por encima justo de la capa que implementaba lo que decía estar probando. No probaba nada, y encima dejaba documentado en el repo lo contrario de cómo se comporta el sistema.

*Qué hice:* lo sustituí por dos pruebas en el sitio correcto. En `revoked-token.store.spec.ts` apunto el store a un puerto cerrado (`redis://127.0.0.1:1`) y compruebo que `isRevoked` devuelve `false` en vez de lanzar — el fail-open real, contra un Redis realmente inaccesible. Y en el guard dejé un test que documenta el contrato: el guard confía en que el store nunca lanza, y la política no se duplica en dos capas.

**Caso 2 — un bug de producción que salió gracias a arreglar el caso 1.** Al ejecutar la prueba nueva contra el Redis inaccesible, falló, pero no donde yo esperaba: `onModuleDestroy` llamaba a `client.quit()`, y con `enableOfflineQueue: false` ese comando **lanza** si la conexión ya está caída. Es decir, apagar el gateway habría reventado el ciclo de apagado de Nest cada vez que Redis no estuviera disponible. Lo arreglé cayendo a `disconnect()` cuando `quit()` falla (`revoked-token.store.ts:94`). El error no lo detectó nadie leyendo el código: lo detectó la prueba que casi no llego a escribir.

**Conclusión que me llevo:** la IA acertó en el mapa del repositorio —las rutas y los `archivo:línea` que citó eran correctos y los verifiqué uno a uno— pero un test suyo en verde no es garantía de nada. Aquí el verde ocultaba que la aserción contradecía su propio nombre.

---

## 6. Evidencia

| Archivo | Qué demuestra |
|---|---|
| `antes-ruta-protegida-200.png` | *(pendiente)* |
| `despues-logout-200.png` | *(pendiente)* |
| `despues-ruta-protegida-401.png` | *(pendiente)* |

**Cómo reproducir mi cambio desde cero:**

```bash
# (pendiente)
```

---

## 7. Prueba automatizada

| | |
|---|---|
| **Archivo de la prueba** | `api-gateway/src/auth/jwt-auth.guard.spec.ts` (unitaria, la que pide la actividad), `api-gateway/test/token-revocation.e2e-spec.ts` (e2e por HTTP), `api-gateway/src/auth/revoked-token.store.spec.ts` (fail-open) y `auth-service/tests/test_auth.py` (logout). |
| **Comando para ejecutarla** | `cd api-gateway && npx jest jwt-auth.guard` y `npx jest --config ./test/jest-e2e.json` |
| **Qué verifica** | Lo que exige el enunciado: **el guard rechaza un token cuyo `jti` está en la lista de revocados y acepta uno que no lo está.** Además: que el 401 por revocación es distinguible del de token inválido, que revocar una sesión no afecta a la de otro usuario, que un token sin `jti` sigue pasando, y que no se consulta Redis si la firma es inválida. El e2e prueba el mínimo viable completo — **la misma petición con el mismo token pasa de 200 a 401**. |
| **¿Falla sin mi cambio?** | **Sí.** Lo comprobé quitando *solo* la consulta de revocación de `jwt-auth.guard.ts` y dejando todo lo demás igual: 3 tests unitarios y los 3 e2e fallan. Salida completa en `prueba-falla-sin-el-cambio.txt`; la misma ejecución con el cambio, en `prueba-pasa-con-el-cambio.txt`. |

**Sin mi cambio** (`prueba-falla-sin-el-cambio.txt`):

```
● JwtAuthGuard › lista de sesiones revocadas › rechaza un token cuyo jti está en la lista de revocados
● JwtAuthGuard › lista de sesiones revocadas › distingue el 401 por revocación del 401 por token inválido
● JwtAuthGuard › lista de sesiones revocadas › confía en el contrato del store: la política de fallo no vive aquí
Tests:       3 failed, 10 passed, 13 total

● Revocación de sesión (e2e) › la MISMA petición con el MISMO token pasa de 200 a 401 tras revocarlo
● Revocación de sesión (e2e) › el 401 por revocación se distingue del 401 por token inválido
● Revocación de sesión (e2e) › revocar la sesión de un usuario no afecta al token vigente de otro
Tests:       3 failed, 3 total
```

**Con mi cambio** (`prueba-pasa-con-el-cambio.txt`):

```
--- npx jest (unitarios) ---
Test Suites: 4 passed, 4 total
Tests:       29 passed, 29 total

--- npx jest --config ./test/jest-e2e.json (e2e) ---
Test Suites: 6 passed, 6 total
Tests:       26 passed, 26 total
```

**auth-service** (44 tests, requiere Mongo y Redis levantados):

```
$ TEST_MONGO_URI="mongodb://localhost:27019" poetry run pytest tests/ -q
............................................                             [100%]
44 passed in 38.24s
```

---

## 8. Estado final — honesto

*(pendiente — se cierra al final)*

---

## 9. Declaración

> Declaro que este trabajo es individual, que corresponde a la actividad que me fue asignada, y que la sección 5 refleja de forma completa y veraz el uso que hice de herramientas de Inteligencia Artificial durante el examen.

**Nombre:** Carlos Hernández
**Fecha:** 2026-07-27
