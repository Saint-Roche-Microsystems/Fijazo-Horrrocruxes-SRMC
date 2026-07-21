# Guía de la API — fijazo-api (para el frontend)

Backend de apuestas deportivas: autenticación, gestión de apuestas (simples y parlay), importación
masiva por Excel, estadísticas, ranking global y gamificación (rangos + logros).

- **Base URL local**: `http://localhost:8000`
- **Documentación interactiva**: `http://localhost:8000/docs` (Swagger) — siempre la fuente de
  verdad más actualizada; este documento es una guía de referencia rápida.
- **Formato**: JSON en todo (excepto `GET /bets/template`, que devuelve un binario `.xlsx`, y
  `POST /bets/import`, que recibe `multipart/form-data`).

---

## 1. Autenticación

### Flujo
1. `POST /auth/register` — crea el usuario (rol `USER` por defecto).
2. `POST /auth/login` — devuelve un JWT.
3. En cada request protegido, enviar el header:
   ```
   Authorization: Bearer <token>
   ```
4. El token expira (`ACCESS_TOKEN_EXPIRE_MINUTES`, 24h por defecto en `.env`). No hay refresh
   token en esta versión: al expirar, el usuario debe volver a loguear.

### `POST /auth/register`
Público. Crea un usuario.

**Request**
```json
{ "username": "carlos", "email": "carlos@mail.com", "password": "password123" }
```
Validaciones: `username` 3–15 caracteres, `password` 8–64 caracteres, `email` formato válido.
Email y username deben ser únicos → `409 Conflict` si ya existen.

**Response `201`** → `UserResponse` (ver sección 8).

### `POST /auth/login`
Público.

**Request**
```json
{ "email": "carlos@mail.com", "password": "password123" }
```

**Response `200`**
```json
{ "access_token": "eyJhbGciOi...", "token_type": "bearer" }
```

**Errores**: `401` credenciales inválidas · `403` cuenta desactivada por un admin.

### `GET /users/me`
Requiere token. Devuelve el perfil del usuario autenticado (`UserResponse`).

---

## 2. Convenciones globales

### Formato de error
Todas las respuestas de error de negocio devuelven:
```json
{ "detail": "mensaje legible" }
```
Los errores de **validación** de Pydantic (422) usan el formato estándar de FastAPI:
```json
{ "detail": [ { "loc": ["body", "odds"], "msg": "Input should be greater than 1", "type": "..." } ] }
```

### Mapeo de códigos HTTP
| Código | Cuándo |
|---|---|
| `400` | Regla de negocio violada (archivo de import inválido, apuesta simple/parlay inconsistente) |
| `401` | Sin token / token inválido o expirado / credenciales incorrectas |
| `403` | Sin permisos (no-admin en endpoints admin) o cuenta desactivada |
| `404` | Recurso no encontrado o no pertenece al usuario (nunca filtra existencia de recursos ajenos) |
| `409` | Conflicto de unicidad (email/username duplicado) |
| `422` | Body/query inválido según el schema (Pydantic) |

### Paginación
Todos los listados paginados comparten esta forma:
```json
{ "items": [...], "total": 123, "page": 1, "page_size": 20 }
```
Query params: `page` (≥1, default 1), `page_size` (1–100, default 20).

### Enums
| Enum | Valores |
|---|---|
| `Role` | `USER`, `ADMIN` |
| `BetType` | `SIMPLE`, `PARLAY` |
| `BetStatus` | `PENDING`, `WON`, `LOST`, `VOID` |
| `AchievementCategory` | `STREAKS`, `EXPERIENCE`, `PROFITABILITY`, `PRECISION`, `ACTIVITY`, `BOOKMAKERS`, `SPORTS` |

---

## 3. Apuestas (`/bets`) — requieren token

Una apuesta puede ser **simple** (una selección) o **parlay** (varias selecciones combinadas). El
modelo es retrocompatible: los campos raíz (`sport`, `odds`, `selection`, …) son siempre la
**selección principal**; un parlay añade selecciones extra en `legs`.

### Reglas de negocio (validadas en el backend, útiles para validar también en el form)
- `odds > 1`, `stake > 0`, todos los campos obligatorios no vacíos.
- `bet_type = SIMPLE` ⇒ `legs` debe ir **vacío**.
- `bet_type = PARLAY` ⇒ `legs` debe tener **al menos 1** elemento (selección principal + legs ≥ 2
  selecciones totales). Cada leg también exige `odds > 1`.
- Una apuesta pertenece únicamente a su usuario (nunca se puede ver/editar la de otro).

### Campos calculados (el frontend no los envía, solo los muestra)
Con `combined_odds = odds × ∏(leg.odds)` (para simples, `combined_odds == odds`):
- `potential_return = stake × combined_odds`
- `potential_profit = stake × (combined_odds − 1)`
- `implied_probability = 1 / combined_odds`

### `BetCreate` (body de `POST /bets`)
```json
{
  "sport": "Fútbol",
  "league": "LaLiga",
  "event": "Real Madrid vs Barcelona",
  "bet_type": "PARLAY",
  "market": "1X2",
  "selection": "Real Madrid",
  "odds": 2.0,
  "stake": 10.0,
  "bookmaker": "Bet365",
  "event_datetime": "2026-08-01T20:00:00Z",
  "status": "PENDING",
  "notes": "opcional",
  "reference_id": "opcional",
  "legs": [
    { "sport": "Tenis", "league": "ATP", "event": "X vs Y", "market": "Ganador", "selection": "X", "odds": 3.0 }
  ]
}
```
`legs: []` (u omitido) para una apuesta simple.

### `BetUpdate` (body de `PUT /bets/{id}`)
Igual que `BetCreate` pero **todos los campos opcionales**; solo se actualizan los enviados
(`exclude_unset`). Si se cambia `bet_type` sin ajustar `legs` acordemente, se revalida la invariante
y puede devolver `400`.

### `BetResponse`
```json
{
  "id": "664f...",
  "sport": "Fútbol", "league": "LaLiga", "event": "Real Madrid vs Barcelona",
  "bet_type": "PARLAY", "market": "1X2", "selection": "Real Madrid",
  "odds": 2.0, "stake": 10.0, "bookmaker": "Bet365",
  "event_datetime": "2026-08-01T20:00:00Z", "status": "PENDING",
  "notes": null, "reference_id": null,
  "legs": [
    { "sport": "Tenis", "league": "ATP", "event": "X vs Y", "market": "Ganador", "selection": "X", "odds": 3.0 }
  ],
  "combined_odds": 6.0,
  "potential_return": 60.0, "potential_profit": 50.0, "implied_probability": 0.1667,
  "created_at": "2026-07-11T10:00:00Z", "updated_at": "2026-07-11T10:00:00Z"
}
```

### Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/bets` | Crear apuesta (simple o parlay) → `201` |
| `GET` | `/bets` | Listar apuestas propias, paginado + filtros |
| `GET` | `/bets/{id}` | Detalle de una apuesta propia |
| `PUT` | `/bets/{id}` | Editar (parcial) |
| `DELETE` | `/bets/{id}` | Eliminar → `204` |
| `GET` | `/bets/template` | Descargar plantilla `.xlsx` |
| `POST` | `/bets/import` | Importar apuestas desde `.xlsx` |

`GET /bets` — query params: `page`, `page_size`, `status` (`BetStatus`), `sport` (texto exacto),
`bet_type` (`BetType`). Response: `PaginatedBets` (`items: BetResponse[]`).

> **Nota de rutas**: `/bets/template` y `/bets/import` están registrados antes de `/bets/{id}` —
> el frontend no necesita hacer nada especial, pero si algún día se añaden más subrutas de `/bets`,
> deben declararse igual de "literal antes que param" en el backend.

### Descargar plantilla — `GET /bets/template`
Devuelve un binario. Content-Type `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`,
con `Content-Disposition: attachment; filename="plantilla_apuestas.xlsx"`. En el frontend, tratar
como descarga de archivo (`blob` + link `download`), no como JSON.

Columnas de la plantilla (fila 1, con dropdowns en *Tipo de apuesta* y *Estado*):
`Deporte, Liga, Evento, Tipo de apuesta, Mercado, Selección, Cuota, Stake, Casa de apuestas,
Fecha y hora del evento, Estado, Notas, ID de referencia, Ticket`.

- **Ticket** es la columna clave para **parlays por Excel**: las filas que comparten el mismo valor
  de `Ticket` se combinan en **una sola apuesta parlay** (la 1ª fila aporta los datos generales +
  selección principal; las siguientes filas de ese ticket son las `legs`). Dejar `Ticket` vacío =
  apuesta simple normal.

### Importar — `POST /bets/import`
`multipart/form-data` con un campo `file` (`.xlsx`, si no → `400`).

**Response `200`** → `ImportSummaryResponse`:
```json
{
  "total_rows": 6,
  "imported": 3,
  "rejected": 3,
  "errors": [
    { "row": 5, "field": "odds", "error": "Input should be greater than 1" },
    { "row": 6, "field": "evento", "error": "Apuesta duplicada dentro del archivo." },
    { "row": 7, "field": "reference_id", "error": "ID de referencia duplicado en el archivo." }
  ]
}
```
Notas para la UI:
- `total_rows` cuenta **filas físicas** del Excel; `imported`/`rejected` cuentan **apuestas**
  (un parlay de 3 filas cuenta como 1 apuesta, no 3).
- Una fila con error **no detiene** el procesamiento del resto — mostrar el resumen completo con
  la tabla de errores (fila + campo + motivo), no solo un mensaje genérico.
- Las apuestas importadas ya quedan reflejadas en estadísticas/ranking/logros automáticamente.

---

## 4. Estadísticas (`/statistics`) — requieren token

Se calculan a partir del historial de apuestas del usuario; nunca se editan a mano. Se recalculan
automáticamente al crear, editar, eliminar o importar apuestas.

### `GET /statistics/me` → `StatisticsResponse`
```json
{
  "user_id": "664f...", "username": "carlos",
  "total_bets": 42, "won": 20, "lost": 15, "void": 2, "pending": 5,
  "win_rate": 57.14,
  "total_stake": 420.0, "total_return": 510.0, "net_profit": 90.0, "roi": 21.43,
  "avg_odds": 2.1, "avg_stake": 10.0,
  "biggest_win": 45.0, "biggest_loss": -20.0,
  "current_streak": 3, "best_streak": 6, "consistency": 62.5,
  "distinct_sports": 4, "distinct_bookmakers": 2, "max_consecutive_days": 9,
  "last_activity_at": "2026-07-10T18:00:00Z",
  "last_bet_at": "2026-08-01T20:00:00Z",
  "ranking_score": 34.8,
  "updated_at": "2026-07-11T10:00:00Z"
}
```

**Definiciones clave para tooltips en la UI**:
- `win_rate` = ganadas / (ganadas+perdidas) × 100 — **VOID no cuenta** (es un empate/devolución).
- `roi` = beneficio neto / stake total × 100.
- `current_streak`: positivo = racha de victorias, negativo = racha de derrotas (saltando VOID).
- `consistency` (0–100): más alto = resultados más estables a lo largo del tiempo.
- `combined_odds` de los parlays ya está incorporada en `avg_odds`, `net_profit`, etc.

---

## 5. Ranking global (`/ranking`) — requieren token

Ordenado por `ranking_score` (0–100), con penalización si el usuario tiene pocas apuestas
(<30 finalizadas), para que no escale posiciones con una muestra pequeña.

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/ranking` | Página del ranking global |
| `GET` | `/ranking/top` | Top N (query `limit`, default 10) |
| `GET` | `/ranking/me` | Posición del usuario autenticado |

`GET /ranking` — query: `page`, `page_size` → `RankingPage`:
```json
{
  "items": [
    { "position": 1, "username": "carlos", "ranking_score": 78.4, "win_rate": 65.0,
      "roi": 34.2, "net_profit": 320.5, "total_bets": 55, "current_streak": 4 }
  ],
  "total": 12, "page": 1, "page_size": 20
}
```

`GET /ranking/top?limit=10` → `RankingEntry[]` directamente (sin envoltorio de paginación).

`GET /ranking/me` → `RankingPosition`:
```json
{ "position": 3, "entry": { "position": 3, "username": "carlos", "...": "..." } }
```
`position`/`entry` pueden ser `null` solo si el usuario todavía no tiene estadísticas materializadas
(caso raro: se materializan automáticamente en el primer `GET /statistics/me` o `/ranks/me`).

---

## 6. Rangos (`/ranks`) — requieren token

Gamificación tipo "nivel de jugador" (Novato → Leyenda), calculada con una puntuación 0–100 que
combina rendimiento, consistencia, racha, volumen y antigüedad en la plataforma.

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/ranks` | Catálogo de los 9 rangos |
| `GET` | `/ranks/me` | Rango actual + progreso al siguiente |

`GET /ranks` → `RankResponse[]` (orden fijo, útil para pintar una barra de progreso con 9 escalones):
```json
[
  { "level": 1, "name": "Novato", "icon": "🐣", "min_score": 0.0 },
  { "level": 2, "name": "Principiante", "icon": "🌱", "min_score": 10.0 },
  { "level": 3, "name": "Amateur", "icon": "🎯", "min_score": 20.0 },
  { "level": 4, "name": "Experimentado", "icon": "📈", "min_score": 30.0 },
  { "level": 5, "name": "Profesional", "icon": "💼", "min_score": 42.0 },
  { "level": 6, "name": "Experto", "icon": "🧠", "min_score": 55.0 },
  { "level": 7, "name": "Maestro", "icon": "🏆", "min_score": 68.0 },
  { "level": 8, "name": "Elite", "icon": "👑", "min_score": 80.0 },
  { "level": 9, "name": "Leyenda", "icon": "🔥", "min_score": 92.0 }
]
```

`GET /ranks/me` → `RankMeResponse`:
```json
{
  "rank_score": 15.0,
  "current": { "level": 2, "name": "Principiante", "icon": "🌱", "min_score": 10.0 },
  "next": { "level": 3, "name": "Amateur", "icon": "🎯", "min_score": 20.0 },
  "progress": 50.0,
  "rank_updated_at": "2026-07-11T10:00:00Z"
}
```
`progress` es el % (0–100) avanzado entre el rango actual y el siguiente — ideal para una barra de
progreso. `next` es `null` en el rango máximo (Leyenda), y ahí `progress` siempre es `100`.

---

## 7. Logros / Achievements (`/achievements`) — requieren token

23 logros repartidos en 7 categorías. Son **monótonos**: una vez desbloqueados, quedan fijos con
su fecha (nunca se "pierden" ni se duplican).

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/achievements` | Catálogo completo (para pantalla "todos los logros") |
| `GET` | `/achievements/me` | Logros del usuario: desbloqueados + pendientes |

`GET /achievements` → `AchievementResponse[]`:
```json
[
  { "id": "streak_3", "name": "En racha", "description": "Gana 3 apuestas consecutivas.",
    "category": "STREAKS", "icon": "🔥" }
]
```

`GET /achievements/me` → `AchievementsMeResponse`:
```json
{
  "unlocked_count": 7,
  "total": 23,
  "achievements": [
    { "id": "exp_first", "name": "Primera apuesta", "description": "...", "category": "EXPERIENCE",
      "icon": "🎫", "unlocked": true, "obtained_at": "2026-07-01T12:00:00Z" },
    { "id": "streak_10", "name": "Racha legendaria", "description": "...", "category": "STREAKS",
      "icon": "⚡", "unlocked": false, "obtained_at": null }
  ]
}
```
Ideal para agrupar por `category` en la UI (grid con icono, nombre, descripción, y un estado
bloqueado/desbloqueado + fecha).

### Catálogo completo (id → nombre) por categoría
| Categoría | Logros |
|---|---|
| **STREAKS** | `streak_3` En racha · `streak_5` Imparable · `streak_10` Racha legendaria · `streak_20` Invencible |
| **EXPERIENCE** | `exp_first` Primera apuesta · `exp_10` Aprendiz · `exp_50` Habitual · `exp_100` Veterano · `exp_500` Centurión |
| **PROFITABILITY** | `profit_first` Primer beneficio · `roi_positive` En verde · `roi_20` Rentable · `profit_target` Gran ganador (net_profit ≥ 500) |
| **PRECISION** | `winrate_60` Certero (≥10 decididas) · `winrate_70` Preciso (≥15) · `winrate_80` Francotirador (≥20) |
| **ACTIVITY** | `activity_7` Constante · `activity_30` Disciplinado · `activity_monthly` Activo (actividad últimos 30 días) |
| **BOOKMAKERS** | `bookmakers_3` Explorador · `bookmakers_5` Trotamundos |
| **SPORTS** | `sports_3` Polivalente · `sports_5` Todoterreno |

---

## 8. Usuarios y administración (`/users`)

### `UserResponse`
```json
{ "id": "664f...", "username": "carlos", "email": "carlos@mail.com", "role": "USER",
  "active": true, "created_at": "2026-07-01T12:00:00Z" }
```
`GET /users/me` — cualquier usuario autenticado ve su propio perfil (incluye `active`; si un admin
lo desactivó, el usuario ya no puede loguear, así que en la práctica siempre verá `active: true`
mientras tenga sesión).

### Endpoints solo-ADMIN (requieren `role: "ADMIN"`, si no → `403`)

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/users` | Listado paginado (`PaginatedUsers`) |
| `GET` | `/users/{id}` | Detalle de un usuario |
| `PATCH` | `/users/{id}/active` | Activar/desactivar |

`PATCH /users/{id}/active` — body `{ "active": false }` → `UserResponse` actualizado.
- Un usuario **desactivado** no puede loguear (`403`) y su token existente deja de funcionar
  (`403` en cualquier endpoint protegido) — útil para forzar logout inmediato en el frontend si se
  recibe `403` con este mensaje.
- Un admin **no puede desactivarse a sí mismo** → `403`.

**Sugerencia de UI admin**: tabla de usuarios con toggle activo/inactivo, columna de rol, buscador
por email/username (el filtro de búsqueda no está implementado en backend todavía — solo
paginación simple).

---

## 9. Interfaces TypeScript sugeridas

```typescript
type Role = "USER" | "ADMIN";
type BetType = "SIMPLE" | "PARLAY";
type BetStatus = "PENDING" | "WON" | "LOST" | "VOID";
type AchievementCategory =
  | "STREAKS" | "EXPERIENCE" | "PROFITABILITY" | "PRECISION"
  | "ACTIVITY" | "BOOKMAKERS" | "SPORTS";

interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

interface User {
  id: string;
  username: string;
  email: string;
  role: Role;
  active: boolean;
  created_at: string; // ISO datetime
}

interface Leg {
  sport: string;
  league: string;
  event: string;
  market: string;
  selection: string;
  odds: number;
}

interface Bet {
  id: string;
  sport: string;
  league: string;
  event: string;
  bet_type: BetType;
  market: string;
  selection: string;
  odds: number;
  stake: number;
  bookmaker: string;
  event_datetime: string;
  status: BetStatus;
  notes: string | null;
  reference_id: string | null;
  legs: Leg[];
  combined_odds: number;
  potential_return: number;
  potential_profit: number;
  implied_probability: number;
  created_at: string;
  updated_at: string;
}

interface Statistics {
  user_id: string;
  username: string;
  total_bets: number;
  won: number;
  lost: number;
  void: number;
  pending: number;
  win_rate: number;
  total_stake: number;
  total_return: number;
  net_profit: number;
  roi: number;
  avg_odds: number;
  avg_stake: number;
  biggest_win: number;
  biggest_loss: number;
  current_streak: number;
  best_streak: number;
  consistency: number;
  distinct_sports: number;
  distinct_bookmakers: number;
  max_consecutive_days: number;
  last_activity_at: string | null;
  last_bet_at: string | null;
  ranking_score: number;
  updated_at: string;
}

interface RankingEntry {
  position: number;
  username: string;
  ranking_score: number;
  win_rate: number;
  roi: number;
  net_profit: number;
  total_bets: number;
  current_streak: number;
}

interface Rank {
  level: number;
  name: string;
  icon: string;
  min_score: number;
}

interface RankMe {
  rank_score: number;
  current: Rank;
  next: Rank | null;
  progress: number; // 0-100
  rank_updated_at: string | null;
}

interface Achievement {
  id: string;
  name: string;
  description: string;
  category: AchievementCategory;
  icon: string;
}

interface UserAchievement extends Achievement {
  unlocked: boolean;
  obtained_at: string | null;
}

interface ImportSummary {
  total_rows: number;
  imported: number;
  rejected: number;
  errors: { row: number; field: string; error: string }[];
}
```

---

## 10. Pantallas sugeridas (mapa funcional)

| Pantalla | Endpoints principales |
|---|---|
| Login / Registro | `POST /auth/login`, `POST /auth/register` |
| Perfil | `GET /users/me` |
| Nueva apuesta (form simple/parlay) | `POST /bets` (toggle Simple/Parlay muestra/oculta el bloque de `legs`) |
| Historial de apuestas (tabla + filtros) | `GET /bets`, `GET /bets/{id}`, `PUT /bets/{id}`, `DELETE /bets/{id}` |
| Importar Excel (descargar plantilla → subir → ver resumen) | `GET /bets/template`, `POST /bets/import` |
| Dashboard de estadísticas | `GET /statistics/me` |
| Ranking global / Top 10 | `GET /ranking`, `GET /ranking/top`, `GET /ranking/me` |
| Mi rango / progreso | `GET /ranks`, `GET /ranks/me` |
| Mis logros (grid por categoría) | `GET /achievements`, `GET /achievements/me` |
| Panel admin: usuarios | `GET /users`, `PATCH /users/{id}/active` |

### Efectos secundarios a tener en cuenta en la UI
- Crear/editar/eliminar/importar apuestas **recalcula automáticamente** estadísticas, ranking y
  logros. Tras cualquiera de esas acciones, si la pantalla de estadísticas/ranking/logros está
  visible, conviene refrescarla (no hay WebSocket/push; es *pull* bajo demanda).
- Desactivar un usuario (admin) invalida su sesión de inmediato (`403` en la siguiente request):
  el frontend debe capturar `403` en llamadas autenticadas y redirigir a login si el mensaje indica
  cuenta desactivada.
