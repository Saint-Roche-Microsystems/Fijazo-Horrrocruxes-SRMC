# Integration tests: cadena síncrona A→B→C

Valida la cadena completa entre los tres servicios reales, sin stubs:

```
bets-service --TCP--> users-service --HTTP--> auth-service
```

Un registro real en auth-service crea la credencial y propaga el perfil a
users-service (`POST /internal/users`); bets-service valida al usuario contra
users-service (`users.validate`, TCP), que a su vez consulta el estado de bloqueo en
auth-service (`GET /internal/lock-status`, HTTP). Se verifica que `active`, `tier` y
`locked` llegan correctamente combinados hasta bets-service.

## Uso

```bash
docker compose -f tests-integration/docker-compose.yml up -d --build
poetry run pytest tests-integration/test_chain_abc.py -q
docker compose -f tests-integration/docker-compose.yml down -v
```

No requiere RabbitMQ: esta cadena es enteramente síncrona (TCP + HTTP).

Este directorio queda fuera de `testpaths` (`pyproject.toml` sólo incluye `tests/`), así
que `poetry run pytest` normal no lo ejecuta ni requiere los tres contenedores.
