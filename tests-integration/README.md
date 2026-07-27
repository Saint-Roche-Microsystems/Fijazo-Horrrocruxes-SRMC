# Integration tests

Validan, contra los servicios reales y sin stubs, los dos caminos que atraviesan varios
procesos.

## Cadena síncrona A→B→C (`test_chain_abc.py`, T-018)

```
bets-service --TCP--> users-service --HTTP--> auth-service
```

Un registro real en auth-service crea la credencial y propaga el perfil a
users-service (`POST /internal/users`); bets-service valida al usuario contra
users-service (`users.validate`, TCP), que a su vez consulta el estado de bloqueo en
auth-service (`GET /internal/lock-status`, HTTP). Se verifica que `active`, `tier` y
`locked` llegan correctamente combinados hasta bets-service.

## Circuito asíncrono (`test_async_progression.py`, T-026/T-027)

```
bets-service --publish--> RabbitMQ (bets.events → progression.recalc) --> progression-service
```

Crear una apuesta acaba actualizando las estadísticas del usuario sin que nadie llame a
`POST /internal/recalculate`.

El test materializa la proyección con una primera lectura antes de provocar el segundo
cambio. Es deliberado: `GET /statistics/{user_id}` usa `get_or_recalculate`, que calcula
por su cuenta cuando no hay nada almacenado, así que una consulta en frío daría verde
aunque el consumer no existiera.

## Uso

```bash
docker compose -f tests-integration/docker-compose.yml up -d --build
poetry run pytest tests-integration/ -q
docker compose -f tests-integration/docker-compose.yml down -v
```

El compose levanta los cuatro servicios, sus Mongo y RabbitMQ (con la misma topología de
producción: monta `../rabbitmq/definitions.json`, para no probar contra una copia
divergente).

Este directorio queda fuera de `testpaths` (`pyproject.toml` sólo incluye `tests/`), así
que `poetry run pytest` normal no lo ejecuta ni requiere los contenedores.
