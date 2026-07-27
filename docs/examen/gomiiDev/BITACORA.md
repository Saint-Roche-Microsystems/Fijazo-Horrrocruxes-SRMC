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
| `JwtAuthGuard` — guard global que valida firma y expiración del JWT | `api-gateway/src/auth/jwt-auth.guard.ts:20` | *(pendiente)* |
| Registro del guard como `APP_GUARD` | `api-gateway/src/auth/auth.module.ts:10` | *(pendiente)* |
| `create_access_token` — único punto de emisión del JWT | `auth-service/src/auth_service/core/security.py:34` | Le añadí el claim `jti` (UUID4) al payload existente `sub`/`role`/`exp`. No creé una función paralela de emisión: modifiqué la única que ya había, así que **todo** token del sistema queda revocable sin tocar ningún llamador. |
| `decode_access_token` — decodificación y validación del JWT | `auth-service/src/auth_service/core/security.py:50` | Lo reutilizo tal cual en el logout para recuperar `jti` y `exp` del token presentado. No escribí una segunda decodificación con `jwt.decode`: si el secreto o el algoritmo cambian, ambos caminos siguen coincidiendo. |
| Tabla `ROUTE_RULES` — fuente de verdad de qué rutas son públicas | `api-gateway/src/auth/route-rules.ts:14` | *(pendiente)* |
| `app.state.redis` — cliente Redis del ciclo de vida de la app | `auth-service/src/auth_service/main.py:62` | *(pendiente)* |
| `get_redis` / `get_security_event_publisher` — factorías de inyección | `auth-service/src/auth_service/api/deps.py:34` y `:40` | *(pendiente)* |
| `SecurityEventPublisher` — puerto `Protocol` de la capa de aplicación | `auth-service/src/auth_service/application/ports.py:45` | *(pendiente)* |
| `RedisSecurityEventPublisher` — precedente de fail-open ante Redis caído | `auth-service/src/auth_service/infrastructure/events/redis_stream_publisher.py:30` | *(pendiente)* |
| Servicio `redis` del stack | `docker-compose.yml:57` | *(pendiente)* |

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
| 3 | Un plan de implementación dividido en 4 commits como mínimo, con la rama creada y la bitácora rellenándose a medida que avanzo. | Plan de 6 commits semánticos, con las ramas `exam/gomiiDev` en el superproyecto y los dos submódulos afectados, y el orden de push de submódulos antes que superproyecto. | *(entrada abierta — se completa al ejecutar el plan)* |

**¿En qué se equivocó respecto a mi repositorio?**

*(pendiente — se documenta el caso concreto cuando ocurra, con cómo lo detecté)*

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
| **Archivo de la prueba** | *(pendiente)* |
| **Comando para ejecutarla** | *(pendiente)* |
| **Qué verifica** | *(pendiente)* |
| **¿Falla sin mi cambio?** | *(pendiente)* |

---

## 8. Estado final — honesto

*(pendiente — se cierra al final)*

---

## 9. Declaración

> Declaro que este trabajo es individual, que corresponde a la actividad que me fue asignada, y que la sección 5 refleja de forma completa y veraz el uso que hice de herramientas de Inteligencia Artificial durante el examen.

**Nombre:** Carlos Hernández
**Fecha:** 2026-07-27
