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
| **¿Hiciste el Paso 0?** | **No** — el login JWT ya existía. Emisión del token en `auth-service/src/auth_service/core/security.py:34` (`create_access_token`), ruta de login en `auth-service/src/auth_service/api/routers/auth.py:48`, y validación en el borde con `api-gateway/src/auth/jwt-auth.guard.ts:25`. |

---

## 1. Qué construí

Antes de este cambio, cerrar sesión en Fijazo era una ficción: el cliente borraba el token
y el servidor no se enteraba de nada, así que un token robado seguía abriendo puertas hasta
que expiraba —hasta 24 horas después—. Ahora el sistema puede cerrar una sesión de verdad.

El token que emite auth-service lleva un identificador único de sesión (`jti`). La ruta
nueva `POST /auth/logout` toma el token con el que se la invoca, extrae ese `jti` y lo
apunta en una lista de revocados en Redis, con un tiempo de vida exactamente igual al que
le quedaba al token. El `JwtAuthGuard` del api-gateway —el mismo que ya existía, extendido,
no reemplazado— consulta esa lista en cada petición autenticada y responde 401 si la sesión
fue cerrada, con un mensaje distinto del de "token inválido o expirado" para que el cliente
pueda distinguir los dos casos.

Como el guard es global, la revocación protege **todas** las rutas del sistema sin haber
tocado un solo controller. Y como la revocación se indexa por sesión y no por usuario,
cerrar sesión en un dispositivo no cierra las de los demás.

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

- **Arquitectura por capas de auth-service.** El repo separa `api/` (routers, schemas,
  deps), `application/` (servicios y puertos) y `infrastructure/` (implementaciones). Metí
  cada pieza en su capa: el puerto `RevokedTokenStore` en `application/ports.py`, la
  implementación Redis en `infrastructure/revocation/`, el caso de uso dentro de
  `AuthService` y la factoría en `api/deps.py`. La carpeta `infrastructure/revocation/`
  imita a `infrastructure/events/` y `infrastructure/http/`, que ya existían.
- **Puertos como `Protocol`.** `RevokedTokenStore` está escrito con la misma forma y el
  mismo estilo de docstring que `SecurityEventPublisher`, para que el caso de uso dependa
  de una capacidad y no de Redis.
- **Errores por excepción de dominio, no por respuesta a mano.** El logout lanza
  `InvalidCredentialsError` y deja que el handler central la traduzca a 401. No registré
  handlers nuevos ni devolví `JSONResponse` desde el router.
- **Vocabulario de observabilidad del gateway.** Al reportar el fallo de Redis reutilicé
  los tags `service` / `transport` / `failure_mode` que ya usa `SentryExceptionFilter`,
  con el valor `fail-open`. El repo ya distinguía `fail-open` de `fail-closed` como
  concepto propio y me apoyé en él.
- **Tabla `ROUTE_RULES` como fuente de verdad, no decoradores.** El proxy comodín hizo que
  `@Public()` dejara de bastar; respeté esa decisión y **no** añadí decoradores por método.
- **Docstrings y comentarios en español explicando el *porqué*,** no el qué, que es el
  estilo del resto del repositorio. Donde cambié una afirmación que dejó de ser cierta
  (la cabecera de `security.py` decía "portado sin cambios") la actualicé en vez de dejar
  documentación mintiendo.
- **Commits Conventional** con el mismo formato que los tres avances previos.

**¿Qué NO dupliqué, pudiendo hacerlo?**

- **No creé un guard nuevo.** Extendí `JwtAuthGuard` (`jwt-auth.guard.ts:25`) añadiéndole
  una dependencia y siete líneas. Un `RevokedTokenGuard` aparte habría sido más cómodo de
  escribir y habría dejado el sistema con dos guards que deciden sobre el mismo token.
- **No toqué `ROUTE_RULES`.** `/auth/logout` queda protegida precisamente por **no** estar
  en esa tabla. Añadir una entrada era innecesario: la convención ya resolvía el requisito
  "logout sin token → 401" sin escribir código.
- **No abrí una segunda conexión a Redis en auth-service.** Reutilicé `app.state.redis`
  del `lifespan` (`main.py:62`) a través de `get_redis`.
- **No escribí una segunda decodificación del JWT.** El logout usa `decode_access_token`,
  el mismo que ya existía, para que secreto y algoritmo no puedan divergir.
- **No creé un servicio de aplicación nuevo.** `logout` es un método más de `AuthService`,
  junto a `register` y `login`.
- **No dupliqué la política de fail-open.** Vive en un solo sitio,
  `RevokedTokenStore.isRevoked`. El guard confía en ese contrato en lugar de repetir el
  `try/catch`, y hay un test que documenta esa frontera.
- **No añadí un servicio Redis al `docker-compose`.** Ya estaba, para el stream
  `security-events`.
- **No creé una fixture de test paralela.** Extendí `test_redis`, la que ya había.

---

## 3. Decisiones técnicas

### Decisión 1
- **Qué decidí:** implementar `POST /auth/logout` **en auth-service**, no en el api-gateway. auth-service es el dueño del token: es donde se firma (`security.py:34`) y donde vive la información de las credenciales y los permisos que se emiten para el gateway. El gateway ya reenvía el header `Authorization` intacto (`proxy/proxy.controller.ts:47-50`), así que el servicio puede decodificar el token y extraer `jti` y `exp` con el `decode_access_token` que ya existe.
- **Alternativa que descarté:** un controller de logout propio dentro del api-gateway, registrado antes del catch-all `@All('*path')` del proxy (`proxy/proxy.controller.ts:31`), que escribiera directamente en Redis.
- **Por qué:** habría partido el dominio de autenticación entre dos repositorios — el token se firma en un servicio y se revoca en otro — y habría duplicado el manejo del token en el gateway. Además `SERVICE_MAP` (`proxy/service-map.ts:6`) ya declara que todo `/auth/*` pertenece a auth-service; meter ahí una excepción contradecía una convención explícita del repo. El coste de la alternativa era bajo (un submódulo menos que tocar), pero el precio arquitectónico no compensaba.

### Decisión 2
- **Qué decidí:** ante un Redis **caído o inaccesible**, el guard **falla abierto**: si no puede consultar la lista de revocados, registra el error y deja pasar el token siempre que la firma y la expiración sean válidas.
- **Alternativa que descarté:** fallar cerrado, es decir, rechazar con 401 cualquier petición mientras no se pueda verificar la lista.
- **Por qué:** el repositorio **ya tenía tomada esta misma decisión** en un caso equivalente: `RedisSecurityEventPublisher` (`infrastructure/events/redis_stream_publisher.py:30`) documenta explícitamente que "un Redis caído no debe tumbar el login", y el proyecto ya maneja `failure_mode="fail-open"` / `"fail-closed"` como vocabulario propio en `capture_error`. Ser coherente con esa decisión pesa más que mi preferencia personal. Fallar cerrado habría convertido a Redis en un punto único de fallo capaz de dejar sin servicio **todo** el tráfico autenticado del sistema, no solo el revocado. **Riesgo que acepto:** durante una caída de Redis, un token revocado vuelve a ser válido hasta que expire. Es una ventana acotada por el TTL del token y se prefiere frente a una caída total de la API.

---

## 4. Las 3 preguntas de mi actividad

**Pregunta 1: ¿Por qué el TTL de la entrada de revocación debe coincidir con la expiración del token, en vez de guardarla para siempre?**

> Porque pasada la expiración la entrada ya no protege de nada: **el token queda rechazado por otro motivo, más barato y anterior**. En mi guard, el `verify` de `jsonwebtoken` (`jwt-auth.guard.ts:57`) comprueba el `exp` y lanza antes de que se llegue siquiera a consultar la lista de revocados (`:71`). Conservar el `jti` un segundo después de su `exp` es guardar una defensa para un ataque que ya es imposible.
>
> Y no es solo desperdicio: es desperdicio que **crece sin techo**. Cada login que termina en logout dejaría una clave eterna, así que el consumo de memoria de Redis sería proporcional al número histórico de sesiones cerradas del sistema, no al número de sesiones vivas. Con TTL, el tamaño de la lista está acotado por las sesiones que hay abiertas ahora mismo. Como los tokens de Fijazo duran 24 h (`access_token_expire_minutes = 60 * 24`), la lista nunca guarda más de un día de logouts. En la evidencia se ve el TTL real justo tras revocar: **86399 segundos**.
>
> Además, delegar el borrado en el TTL de Redis me ahorra escribir —y mantener— un proceso de limpieza periódico que podría fallar en silencio. `seconds_until_expiry` (`security.py:57`) hace ese cálculo y devuelve 0 para tokens ya expirados, caso en el que ni siquiera se escribe la clave.

**Pregunta 2: Si el almacén de revocados (Redis) está caído cuando llega una petición: ¿tu guard falla abierto (deja pasar) o falla cerrado (rechaza)? ¿Cuál elegiste y qué riesgo aceptas con esa decisión?**

> **Falla abierto.** Si Redis no responde, `RevokedTokenStore.isRevoked` captura el error, lo reporta a Sentry con el tag `failure_mode: 'fail-open'`, lo escribe en el log y devuelve `false`; el token pasa siempre que su firma y su expiración sean válidas (`revoked-token.store.ts:80`). Está demostrado en `evidencia-fail-open-redis-caido.txt`: con Redis parado, la ruta protegida sigue respondiendo 200 y el gateway registra el fallo.
>
> **Por qué esta y no la otra.** Fallar cerrado convierte a Redis en un punto único de fallo capaz de tumbar *todo* el tráfico autenticado del sistema: sin Redis, nadie podría consultar sus apuestas, ni ver el ranking, ni nada. El daño de esa decisión es total e inmediato; el de la contraria es parcial y acotado. Pesó también que **el repositorio ya había tomado esta misma decisión** en un caso análogo: `RedisSecurityEventPublisher` documenta que "un Redis caído no debe tumbar el login" (`redis_stream_publisher.py:30`). Ser coherente con el criterio que ya tenía el sistema vale más que imponer mi preferencia.
>
> **El riesgo que acepto, dicho claro:** durante la caída de Redis, un token revocado vuelve a ser válido. Si alguien roba un token, la víctima cierra sesión y Redis se cae en esa ventana, el atacante recupera el acceso hasta que Redis vuelva o el token expire. Lo asumo porque es una conjunción de tres cosas poco probable, con impacto acotado a una cuenta, frente a una caída general garantizada de todo el sistema cada vez que Redis se reinicie.
>
> **Lo que hice para reducirlo:** el fallo no es silencioso —va a Sentry con `transport: 'redis'` y `failure_mode: 'fail-open'`, así que una caída se ve—, y configuré el cliente con `enableOfflineQueue: false` y `maxRetriesPerRequest: 1` para que la ventana sea lo más corta posible. Sin eso, ioredis encolaría los comandos y cada petición se quedaría colgada hasta el timeout: tendría la inseguridad del fail-open **y** la indisponibilidad del fail-closed a la vez.
>
> **Dónde cambiaría de opinión:** si Fijazo manejara dinero real o datos sensibles, invertiría la decisión, o pondría Redis en alta disponibilidad para no tener que elegir.

**Pregunta 3: ¿En qué se diferencia esto de simplemente borrar el token en el navegador del cliente?**

> En quién decide, que es lo único que importa en seguridad. Borrar el token en el navegador es **una petición amable al cliente**, y el cliente es precisamente la parte que no controlo. Funciona solo si quien tiene el token coopera — y si alguien te lo robó, no coopera.
>
> Concretamente, borrar el token en el cliente no hace nada contra el caso que motiva esta actividad: si el token viajó a otra parte —una extensión maliciosa, un log, un `curl` copiado de las DevTools, el portapapeles— esa copia **sigue siendo válida**, porque un JWT es autocontenido y el servidor lo aceptaba sin consultar nada. El borrado en el cliente limpia una copia y no toca las demás; la revocación invalida la **sesión**, y con ella todas sus copias a la vez.
>
> La diferencia se ve en mis dos capturas: `despues-ruta-protegida-401.png` es exactamente la misma petición que `antes-ruta-protegida-200.png`, con el mismo token, enviada desde Postman — un cliente que nunca "borró" nada y que ni siquiera se enteró del logout. Con solo borrado en el cliente, esa segunda captura habría seguido dando 200. Lo que cambió no está en el cliente, está en el servidor.
>
> Dicho eso, **no son alternativas, son complementarias**: el frontend debe seguir borrando el token al cerrar sesión, para no dejarlo en `localStorage` de un ordenador compartido. Lo que ya no hace falta es *confiar* en que lo haga.

---

## 5. Uso de Inteligencia Artificial — **obligatorio**

**¿Usaste IA en este examen?**  ☑ Sí  ☐ No

Herramienta: **Claude (Claude Code)**, integrado en VS Code con acceso de lectura al repositorio.

| # | Qué le pedí | Qué me devolvió | Qué corregí, adapté o descarté — y por qué |
|:--:|---|---|---|
| 1 | Que analizara el repositorio del grupo y determinara qué exige la Actividad A antes de escribir nada, sin proponer código todavía. | Un mapa de la arquitectura con `archivo:línea`: el guard global en `jwt-auth.guard.ts:25`, su registro como `APP_GUARD` en `auth.module.ts:13`, y tres hallazgos — (a) el token **no** lleva `jti`, (b) las rutas públicas se deciden por la tabla `ROUTE_RULES` y no por el decorador `@Public()`, (c) Redis ya está en el `docker-compose`. Dejó tres decisiones abiertas en vez de resolverlas solo. | Acepté el análisis tras verificar yo mismo cada `archivo:línea` que citó. **No** le dejé decidir la ubicación del logout ni el modo de fallo: eran decisiones de arquitectura de *mi* sistema y las tomé yo (ver sección 3). Le exigí explícitamente que no tocara `route-rules.ts`. |
| 2 | La información para la tarjeta del Kanban, en el formato de tabla que ya usa el tablero del grupo. | Tarjeta **T-039** con título, responsable, descripción, alcance por submódulo, anclaje, criterios de aceptación y definición de hecho. Dedujo el ID mirando el máximo del historial (`T-038`). | Verifiqué que `T-039` fuera realmente el siguiente ID libre antes de crear la tarjeta. Descarté su propuesta alternativa de partirla en cuatro subtarjetas (T-039a…d) y la creé como una sola, para no desentonar con el resto del tablero, que usa una tarjeta por entregable. |
| 3 | Un plan de implementación dividido en 4 commits como mínimo, con la rama creada y la bitácora rellenándose a medida que avanzo. | Plan de 6 commits semánticos, con las ramas `exam/gomiiDev` en el superproyecto y los dos submódulos afectados, y el orden de push de submódulos antes que superproyecto. | Le quité el control de git: los commits los ejecuto yo, para revisar cada diff antes de que entre al historial. También decidí yo qué hacer con los tokens ya emitidos sin `jti` (dejarlos pasar hasta que expiren, en vez de invalidar todas las sesiones vivas al desplegar). |
| 4 | Que implementara el guard y las pruebas de revocación. | El guard extendido y una batería de tests. Entre ellos, uno llamado *"falla abierto: si el almacén de revocados no responde, el token pasa"* que en realidad afirmaba `rejects.toThrow()` — lo contrario de lo que dice su nombre — y que **pasaba en verde**. | Ver el apartado siguiente. Es el error más grave de la sesión y el que más me hizo revisar lo que estaba aceptando. |
| 5 | Que levantara el stack y generara la evidencia del recorrido antes/después. | El stack completo construido y corriendo, y los recorridos verificados por consola con los códigos y el TTL real de Redis. Detectó que `/users/me` devolvía 404 y buscó una ruta protegida que sí respondiera 200. | Las **capturas las hice yo desde Postman**, no por consola: se ven mucho más claras para el tribunal y demuestran que la petición del "después" es literalmente la misma del "antes". Los `.txt` de consola quedan como evidencia complementaria y reproducible. |
| 6 | Que redactara la bitácora con las capturas y cerrara las secciones pendientes. | Las secciones 1, 2, 4, 6 y 8 redactadas, más la sección del README. Al citar `archivo:línea` se equivocó **cuatro veces** con números que se habían desplazado por sus propias ediciones. | Le exigí verificar cada `archivo:línea` con `grep` antes de darlo por bueno, porque el enunciado avisa de que se comprueban. Aparecieron cuatro referencias desfasadas (`security.py`, `deps.py`, `main.py`, `conftest.py`) y se corrigieron. Es el motivo por el que no doy por buena ninguna cita sin comprobarla. |

**¿En qué se equivocó respecto a mi repositorio?**

**Caso 1 — un test que decía una cosa y comprobaba la contraria, en verde.** Al escribir las pruebas del guard, generó un caso titulado *"falla abierto: si el almacén de revocados no responde, el token pasa"* cuya aserción era `await expect(guard.canActivate(context)).rejects.toThrow()`. Es decir: el nombre prometía que la petición **pasa** y el código exigía que **falle**. Y salió en verde, que es lo que lo hacía peligroso.

*Cómo lo detecté:* me chocó que un test de "fail-open" esperara una excepción, y al mirarlo entendí la causa de fondo: el test inyectaba un `RevokedTokenStore` falso que lanzaba, pero **la política de fail-open no vive en el guard, vive dentro de `RevokedTokenStore.isRevoked`**, que captura el error y devuelve `false` (`api-gateway/src/auth/revoked-token.store.ts:80`). Al sustituir el store por un doble, el test saltaba por encima justo de la capa que implementaba lo que decía estar probando. No probaba nada, y encima dejaba documentado en el repo lo contrario de cómo se comporta el sistema.

*Qué hice:* lo sustituí por dos pruebas en el sitio correcto. En `revoked-token.store.spec.ts` apunto el store a un puerto cerrado (`redis://127.0.0.1:1`) y compruebo que `isRevoked` devuelve `false` en vez de lanzar — el fail-open real, contra un Redis realmente inaccesible. Y en el guard dejé un test que documenta el contrato: el guard confía en que el store nunca lanza, y la política no se duplica en dos capas.

**Caso 2 — un bug de producción que salió gracias a arreglar el caso 1.** Al ejecutar la prueba nueva contra el Redis inaccesible, falló, pero no donde yo esperaba: `onModuleDestroy` llamaba a `client.quit()`, y con `enableOfflineQueue: false` ese comando **lanza** si la conexión ya está caída. Es decir, apagar el gateway habría reventado el ciclo de apagado de Nest cada vez que Redis no estuviera disponible. Lo arreglé cayendo a `disconnect()` cuando `quit()` falla (`revoked-token.store.ts:94`). El error no lo detectó nadie leyendo el código: lo detectó la prueba que casi no llego a escribir.

**Conclusión que me llevo:** la IA acertó en el mapa del repositorio —las rutas y los `archivo:línea` que citó eran correctos y los verifiqué uno a uno— pero un test suyo en verde no es garantía de nada. Aquí el verde ocultaba que la aserción contradecía su propio nombre.

---

## 6. Evidencia

Capturas tomadas desde Postman contra el stack completo del `docker-compose`, no contra un
servicio suelto: el token entra por el api-gateway (`localhost:3000`) y este proxea a
auth-service y users-service, así que lo que se ve es el sistema entero funcionando.

| Archivo | Qué demuestra |
|---|---|
| `antes-ruta-protegida-200.png` | **El punto de partida.** `GET http://localhost:3000/users` con el token del usuario A en *Bearer Token* → **200 OK** (20 ms, 1.4 KB) y el JSON con la lista de usuarios. La sesión está abierta y el guard deja pasar. |
| `despues-logout-200.png` | **El cierre de sesión.** `POST http://localhost:3000/auth/logout` con **ese mismo token** → **200 OK** (21 ms) y `{"detail": "Sesión cerrada."}`. En este instante auth-service ha escrito `revoked_jti:<jti>` en Redis con el TTL de la vida restante del token. |
| `despues-ruta-protegida-401.png` | **La prueba de que la revocación es real.** Es **la misma petición** que la primera captura —mismo método `GET`, misma URL `localhost:3000/users`, mismo token— y ahora responde **401 Unauthorized** (7 ms) con `"Sesión cerrada: el token fue revocado. Vuelve a iniciar sesión."`. El token no ha expirado ni ha cambiado: lo único distinto es que su `jti` está en la lista de revocados. Comparar esta captura con la primera es el examen entero en dos imágenes. |
| `borde-logout-dos-veces.png` | **Caso borde: logout repetido.** Segundo `POST /auth/logout` con el token ya revocado → **401**, con el mismo mensaje de sesión cerrada. **No revienta**: no hay 500 ni excepción, el sistema responde de forma coherente. Ver la nota de abajo sobre por qué es 401 y no 200. |

**Nota sobre el doble logout — divergencia consciente respecto al enunciado.**
El enunciado pide que el segundo logout "no reviente". No revienta, pero devuelve **401 en
lugar de 200**, y conviene explicar por qué: `/auth/logout` es una ruta protegida, así que
el `JwtAuthGuard` ve que el token ya está revocado y lo rechaza **antes** de que la petición
llegue a auth-service. La idempotencia **sí está implementada** en la capa de servicio —
`RedisRevokedTokenStore.revoke` solo reescribe la misma clave, y el test
`test_logout_twice_does_not_break` lo comprueba llamando a auth-service directamente, donde
ambas llamadas dan 200. A través del gateway, el 401 me parece la respuesta más correcta:
si la sesión ya está cerrada, ese token no autoriza nada, tampoco a volver a cerrarse.
Exceptuar `/auth/logout` de la comprobación de revocación habría abierto un agujero — una
ruta protegida que acepta tokens revocados — a cambio de un código de estado más bonito.

**Evidencia complementaria en texto** (reproducible, con los valores reales):

| Archivo | Qué demuestra |
|---|---|
| `evidencia-recorrido-completo.txt` | El recorrido entero por consola, incluidos los `jti` de ambos usuarios, el **TTL real en Redis: 86399 s** (exactamente las 24 h que le quedaban al token, ver pregunta 1) y la comprobación de que el `jti` del usuario B **no** está en la lista tras el logout de A. |
| `evidencia-fail-open-redis-caido.txt` | La respuesta a la pregunta 2 **demostrada, no solo argumentada**: se para Redis con `docker compose stop redis`, la ruta protegida **sigue respondiendo 200**, y el log del gateway registra `No se pudo consultar la lista de revocados; se deja pasar el token (fail-open)`. |
| `prueba-falla-sin-el-cambio.txt` | Los 3 tests unitarios y los 3 e2e fallando al quitar únicamente la consulta de revocación del guard. |
| `prueba-pasa-con-el-cambio.txt` | Las mismas pruebas en verde con el cambio: 29 unitarios y 26 e2e. |

**Cómo reproducir mi cambio desde cero:**

```bash
git clone --recurse-submodules <repo> && cd Fijazo-Horrrocruxes-SRMC
git checkout exam/gomiiDev
git submodule update --init --recursive

docker compose up -d --build

# 1. Crear un usuario y obtener su token
curl -s -X POST localhost:3000/auth/register -H 'content-type: application/json' \
  -d '{"username":"examen","email":"examen@test.com","password":"password123"}'

TOKEN=$(curl -s -X POST localhost:3000/auth/login -H 'content-type: application/json' \
  -d '{"email":"examen@test.com","password":"password123"}' \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

# 2. ANTES: la ruta protegida responde
curl -i localhost:3000/users -H "Authorization: Bearer $TOKEN"          # 200

# 3. Cerrar sesión
curl -i -X POST localhost:3000/auth/logout -H "Authorization: Bearer $TOKEN"   # 200

# 4. DESPUES: la MISMA peticion con el MISMO token
curl -i localhost:3000/users -H "Authorization: Bearer $TOKEN"          # 401 revocado

# 5. Casos borde
curl -i -X POST localhost:3000/auth/logout                              # 401 sin token
curl -i -X POST localhost:3000/auth/logout -H "Authorization: Bearer $TOKEN"  # 401, no revienta

# 6. Fail-open: con Redis caido el trafico autenticado sigue pasando
docker compose stop redis
curl -i localhost:3000/users -H "Authorization: Bearer <token de otro usuario>"  # 200
docker compose start redis
```

**Pruebas automatizadas:**

```bash
cd api-gateway && npx jest && npx jest --config ./test/jest-e2e.json
cd auth-service && TEST_MONGO_URI="mongodb://localhost:27019" poetry run pytest tests/ -q
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

**Funciona** (verificado contra el stack completo del `docker-compose`, no solo en tests):

- El token del login lleva `jti` único; dos logins del mismo usuario dan `jti` distintos.
- `POST /auth/logout` responde 200 y registra la sesión en Redis con TTL = vida restante
  del token (medido: 86399 s).
- La misma ruta protegida, con el mismo token, **pasa de 200 a 401** tras el logout. Es el
  mínimo viable de la actividad y está en las capturas 1 y 3.
- El 401 por revocación es distinguible del de token inválido o expirado.
- Caso borde: logout sin token → 401.
- Caso borde: logout dos veces → no revienta (401, ver la nota de la sección 6).
- Caso borde: el token vigente de otro usuario sigue funcionando tras el logout del primero.
- Dos sesiones del **mismo** usuario se revocan por separado: cerrar en un dispositivo no
  cierra el otro.
- Fail-open comprobado parando Redis de verdad: el tráfico autenticado sigue pasando y el
  gateway lo registra.
- Pruebas: 29 unitarios + 26 e2e en api-gateway, 44 en auth-service. Verificado que las
  pruebas de revocación **fallan** si se quita la consulta del guard.

**No funciona / quedó incompleto — y lo digo con precisión:**

- **Los tokens emitidos antes de este cambio no se pueden revocar.** No llevan `jti`, así
  que el guard los deja pasar hasta que expiren (máximo 24 h tras el despliegue). Fue una
  decisión consciente: la alternativa era invalidar de golpe todas las sesiones vivas.
  Está aislada en una condición explícita del guard y cubierta por un test.
- **El logout no invalida la sesión en otros servicios que validen el JWT por su cuenta.**
  Hoy no ocurre —solo el gateway valida tokens de cliente, el resto confía en las cabeceras
  `X-User-Id`/`X-User-Role` que él inyecta—, pero si algún servicio empezara a validar el
  JWT directamente, tendría que consultar la misma lista. No hay nada que lo impida ni que
  lo recuerde más allá del comentario en `config.py`.
- **No hay revocación masiva por usuario.** No existe un "cerrar todas mis sesiones" ni una
  forma de expulsar a un usuario comprometido de todos sus dispositivos a la vez. La lista
  se indexa por `jti`, no por `sub`, que era lo que pedía la actividad.
- **El fail-open es una decisión, no una limitación**, pero conviene repetirla aquí: con
  Redis caído, un token revocado vuelve a pasar. Está argumentado en la pregunta 2.
- **La suite de auth-service necesita Mongo y Redis levantados.** No hay dobles; sigue el
  patrón de integración que ya tenía el repo, pero significa que no corre en frío.

**Cuál era mi siguiente paso:**

Añadir revocación por usuario además de por sesión: guardar en Redis una marca
`revoked_user:<sub>` con el instante del corte, y que el guard rechace cualquier token de
ese usuario emitido antes de esa marca. Resuelve el caso "me robaron la cuenta, échame a
todos" sin tener que enumerar los `jti` de sus sesiones abiertas, que el sistema no conoce.
Después, exponerlo como `POST /auth/logout-all`.

---

## 9. Declaración

> Declaro que este trabajo es individual, que corresponde a la actividad que me fue asignada, y que la sección 5 refleja de forma completa y veraz el uso que hice de herramientas de Inteligencia Artificial durante el examen.

**Nombre:** Carlos Hernández
**Fecha:** 2026-07-27
