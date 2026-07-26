#!/usr/bin/env node

import { spawnSync } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { createInterface } from 'node:readline/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const SHARED_ENV_EXAMPLE = join(ROOT, 'scripts', 'shared.env.example');
const SHARED_ENV = join(ROOT, 'scripts', '.env.shared');
const SENTRY_DSN_PLACEHOLDER = 'use-your-sentry-project-dsn';

/** Servicios a preparar: dónde vive su .env.example y qué nombre debe tener su .env. */
const SERVICES = [
  { dir: 'auth-service', example: '.env.example', target: '.env' },
  { dir: 'users-service', example: '.env.example', target: '.env' },
  { dir: 'bets-service', example: '.env.example', target: '.env' },
  { dir: 'progression-service', example: '.env.example', target: '.env' },
  { dir: 'api-gateway', example: '.env.example', target: '.env' },
];

/** Gestor de paquetes por servicio, para instalar dependencias tras generar los .env. */
const INSTALL_STEPS = [
  { dir: 'auth-service', cmd: 'poetry', args: ['install'] },
  { dir: 'users-service', cmd: 'npm', args: ['install'] },
  { dir: 'bets-service', cmd: 'poetry', args: ['install'] },
  { dir: 'progression-service', cmd: 'poetry', args: ['install'] },
  { dir: 'api-gateway', cmd: 'npm', args: ['install'] },
];

function run(cmd, args) {
  return spawnSync(cmd, args, { shell: true, encoding: 'utf8' });
}

function checkNode() {
  const res = run('node', ['-v']);
  return res.status === 0 ? res.stdout.trim() : null;
}

function checkNpm() {
  const res = run('npm', ['-v']);
  return res.status === 0 ? res.stdout.trim() : null;
}

function checkPoetry() {
  const res = run('poetry', ['--version']);
  return res.status === 0 ? res.stdout.trim() : null;
}

function checkDependencies() {
  console.log('Verificando herramientas locales...\n');

  const nodeVersion = checkNode();
  const npmVersion = checkNpm();
  const poetryVersion = checkPoetry();

  const missing = [];
  if (!nodeVersion) missing.push('Node.js (https://nodejs.org)');
  if (!npmVersion) missing.push('npm (viene con Node.js)');
  if (!poetryVersion) missing.push('Poetry (https://python-poetry.org/docs/#installation)');

  console.log(`  node    ${nodeVersion ?? 'NO ENCONTRADO'}`);
  console.log(`  npm     ${npmVersion ?? 'NO ENCONTRADO'}`);
  console.log(`  poetry  ${poetryVersion ?? 'NO ENCONTRADO'}\n`);

  if (missing.length > 0) {
    console.error('Faltan herramientas antes de continuar:\n');
    for (const item of missing) console.error(`  - ${item}`);
    console.error('\nInstálalas y vuelve a correr este script.');
    process.exit(1);
  }
}

/** `git submodule status` marca con "-" los submódulos que nunca se inicializaron. */
function checkSubmodules() {
  console.log('Verificando submódulos...\n');
  const status = run('git', ['submodule', 'status']);
  if (status.status !== 0) {
    console.error('No se pudo leer el estado de los submódulos:', status.stderr);
    process.exit(1);
  }

  const lines = status.stdout.split('\n').filter((line) => line.trim() !== '');
  const uninitialized = lines.filter((line) => line.startsWith('-'));

  for (const line of lines) {
    const name = line.trim().split(' ')[1] ?? line.trim();
    console.log(`  ${line.startsWith('-') ? '✗ sin inicializar' : '✓ ok'}  ${name}`);
  }

  if (uninitialized.length > 0) {
    console.log('\nInicializando submódulos pendientes...');
    const update = run('git', ['submodule', 'update', '--init', '--recursive']);
    if (update.status !== 0) {
      console.error('Falló git submodule update --init --recursive:', update.stderr);
      process.exit(1);
    }
    console.log('Submódulos listos.\n');
  } else {
    console.log('\nTodos los submódulos ya están inicializados.\n');
  }
}

async function ask(rl, question, defaultValue) {
  const answer = await rl.question(`${question} [${defaultValue}]: `);
  return answer.trim() === '' ? defaultValue : answer.trim();
}

async function askPorts(rl) {
  console.log('Puertos para correr cada servicio en local (Enter = valor por defecto).\n');

  return {
    mongoAuthPort: await ask(rl, 'Mongo de auth-service', '27019'),
    mongoUsersPort: await ask(rl, 'Mongo de users-service', '27021'),
    mongoBetsPort: await ask(rl, 'Mongo de bets-service', '27020'),
    mongoProgressionPort: await ask(rl, 'Mongo de progression-service', '27022'),
    redisPort: await ask(rl, 'Redis', '6379'),
    rabbitmqAmqpPort: await ask(rl, 'RabbitMQ (AMQP)', '5672'),
    rabbitmqUiPort: await ask(rl, 'RabbitMQ (UI de management)', '15672'),
    authPort: await ask(rl, 'auth-service (HTTP)', '8001'),
    usersHttpPort: await ask(rl, 'users-service (HTTP)', '3001'),
    usersTcpPort: await ask(rl, 'users-service (TCP, users.validate)', '3011'),
    betsPort: await ask(rl, 'bets-service (HTTP)', '8002'),
    progressionPort: await ask(rl, 'progression-service (HTTP)', '8003'),
    gatewayPort: await ask(rl, 'api-gateway (HTTP)', '3000'),
  };
}

/** Lee scripts/.env.shared si ya existe (para reutilizar secretos y DSNs previos). */
function readSharedEnvValues() {
  if (!existsSync(SHARED_ENV)) return {};
  const content = readFileSync(SHARED_ENV, 'utf8');
  const values = {};
  for (const line of content.split('\n')) {
    const match = line.match(/^([A-Z0-9_]+)=(.*)$/);
    if (match) values[match[1]] = match[2];
  }
  return values;
}

/** Genera (o reutiliza) los secretos de servicio a servicio. A diferencia de los DSN de
 * Sentry, estos NO se vuelven a pedir en cada corrida: rotarlos invalidaría sesiones/JWTs
 * ya emitidos, así que solo se generan la primera vez. */
function ensureSharedSecrets(existingValues) {
  if (existingValues.JWT_SECRET && existingValues.INTERNAL_API_KEY) {
    console.log('\nReutilizando secretos existentes en scripts/.env.shared.\n');
    return {
      JWT_SECRET: existingValues.JWT_SECRET,
      JWT_ALGORITHM: existingValues.JWT_ALGORITHM ?? 'HS256',
      INTERNAL_API_KEY: existingValues.INTERNAL_API_KEY,
    };
  }

  console.log('Generando scripts/.env.shared con secretos nuevos...\n');
  return {
    JWT_SECRET: randomBytes(32).toString('hex'),
    JWT_ALGORITHM: 'HS256',
    INTERNAL_API_KEY: randomBytes(32).toString('hex'),
  };
}

/** Los DSN de Sentry sí se preguntan en cada corrida (como los puertos):
 *  dejar el campo en blanco es una opción válida y deshabilita
 * el SDK en los servicios de ese stack, sin romper el arranque local. */
async function askSentryDsns(rl, existingValues) {
  console.log(
    'DSN de los proyectos de Sentry (Enter para dejarlo vacío y deshabilitar el SDK en esos servicios).\n',
  );

  const previousFastapiDsn =
    existingValues.SENTRY_FASTAPI_DSN && existingValues.SENTRY_FASTAPI_DSN !== SENTRY_DSN_PLACEHOLDER
      ? existingValues.SENTRY_FASTAPI_DSN
      : '';
  const previousNestjsDsn =
    existingValues.SENTRY_NESTJS_DSN && existingValues.SENTRY_NESTJS_DSN !== SENTRY_DSN_PLACEHOLDER
      ? existingValues.SENTRY_NESTJS_DSN
      : '';

  const fastapiDsn = await ask(
    rl,
    'DSN del proyecto FastAPI (auth-service, bets-service, progression-service)',
    previousFastapiDsn,
  );
  const nestjsDsn = await ask(
    rl,
    'DSN del proyecto NestJS (users-service, api-gateway)',
    previousNestjsDsn,
  );

  return { SENTRY_FASTAPI_DSN: fastapiDsn, SENTRY_NESTJS_DSN: nestjsDsn };
}

/** Reemplaza `KEY=valor` línea a línea; conserva comentarios y claves sin override. */
function applyOverrides(envContent, overrides) {
  return envContent
    .split('\n')
    .map((line) => {
      const match = line.match(/^([A-Z0-9_]+)=/);
      if (match && Object.prototype.hasOwnProperty.call(overrides, match[1])) {
        return `${match[1]}=${overrides[match[1]]}`;
      }
      return line;
    })
    .join('\n');
}

function buildOverridesPerService(shared, ports) {
  const rabbitmqUrl = `amqp://fijazo:fijazo@localhost:${ports.rabbitmqAmqpPort}/`;
  const redisUri = `redis://localhost:${ports.redisPort}/0`;

  return {
    'auth-service': {
      MONGO_URI: `mongodb://localhost:${ports.mongoAuthPort}`,
      JWT_SECRET: shared.JWT_SECRET,
      JWT_ALGORITHM: shared.JWT_ALGORITHM,
      INTERNAL_API_KEY: shared.INTERNAL_API_KEY,
      USERS_SERVICE_URL: `http://localhost:${ports.usersHttpPort}`,
      REDIS_URI: redisUri,
      SENTRY_DSN: shared.SENTRY_FASTAPI_DSN,
    },
    'users-service': {
      HTTP_PORT: ports.usersHttpPort,
      TCP_PORT: ports.usersTcpPort,
      MONGO_URI: `mongodb://localhost:${ports.mongoUsersPort}`,
      INTERNAL_API_KEY: shared.INTERNAL_API_KEY,
      AUTH_SERVICE_URL: `http://localhost:${ports.authPort}`,
      REDIS_URI: redisUri,
      SENTRY_DSN: shared.SENTRY_NESTJS_DSN,
    },
    'bets-service': {
      MONGO_URI: `mongodb://localhost:${ports.mongoBetsPort}`,
      INTERNAL_API_KEY: shared.INTERNAL_API_KEY,
      USERS_SERVICE_TCP_HOST: 'localhost',
      USERS_SERVICE_TCP_PORT: ports.usersTcpPort,
      RABBITMQ_URL: rabbitmqUrl,
      SENTRY_DSN: shared.SENTRY_FASTAPI_DSN,
    },
    'progression-service': {
      MONGO_URI: `mongodb://localhost:${ports.mongoProgressionPort}`,
      INTERNAL_API_KEY: shared.INTERNAL_API_KEY,
      SENTRY_DSN: shared.SENTRY_FASTAPI_DSN,
    },
    'api-gateway': {
      PORT: ports.gatewayPort,
      JWT_SECRET: shared.JWT_SECRET,
      JWT_ALGORITHM: shared.JWT_ALGORITHM,
      INTERNAL_API_KEY: shared.INTERNAL_API_KEY,
      AUTH_SERVICE_URL: `http://localhost:${ports.authPort}`,
      USERS_SERVICE_URL: `http://localhost:${ports.usersHttpPort}`,
      BETS_SERVICE_URL: `http://localhost:${ports.betsPort}`,
      PROGRESSION_SERVICE_URL: `http://localhost:${ports.progressionPort}`,
      SENTRY_DSN: shared.SENTRY_NESTJS_DSN,
    },
  };
}

function generateEnvFiles(overridesPerService) {
  const existing = SERVICES.filter((service) =>
    existsSync(join(ROOT, service.dir, service.target)),
  );
  if (existing.length > 0) {
    console.log('ADVERTENCIA: se sobrescribirán los siguientes archivos ya existentes:');
    for (const service of existing) console.log(`  - ${service.dir}/${service.target}`);
    console.log();
  }

  console.log('Generando archivos .env por servicio...\n');

  for (const service of SERVICES) {
    const serviceDir = join(ROOT, service.dir);
    const examplePath = join(serviceDir, service.example);
    const targetPath = join(serviceDir, service.target);

    if (!existsSync(examplePath)) {
      console.log(`  ! ${service.dir}: no se encontró ${service.example}, se omite`);
      continue;
    }

    const template = readFileSync(examplePath, 'utf8');
    const generated = applyOverrides(template, overridesPerService[service.dir] ?? {});
    writeFileSync(targetPath, generated);
    console.log(`  ✓ ${service.dir}/${service.target} generado`);
  }
}

/** Corre `poetry install` / `npm install` en cada servicio. */
function installDependencies() {
  console.log('Instalando dependencias de cada microservicio...\n');

  const failures = [];
  for (const step of INSTALL_STEPS) {
    const cwd = join(ROOT, step.dir);
    process.stdout.write(`  ${step.dir} (${step.cmd} ${step.args.join(' ')})... `);
    const res = spawnSync(step.cmd, step.args, { cwd, shell: true, encoding: 'utf8' });
    if (res.status === 0) {
      console.log('OK');
    } else {
      console.log('ERROR');
      failures.push({ dir: step.dir, output: (res.stderr || res.stdout || '').trim() });
    }
  }

  if (failures.length > 0) {
    console.log('\nDetalle de los errores:');
    for (const failure of failures) {
      console.log(`\n--- ${failure.dir} ---`);
      console.log(failure.output.split('\n').slice(-20).join('\n'));
    }
  }

  return failures;
}

async function main() {
  checkDependencies();
  checkSubmodules();

  const existingSharedValues = readSharedEnvValues();

  const rl = createInterface({ input: process.stdin, output: process.stdout });
  let ports;
  let secrets;
  let sentryDsns;
  try {
    ports = await askPorts(rl);
    secrets = ensureSharedSecrets(existingSharedValues);
    sentryDsns = await askSentryDsns(rl, existingSharedValues);
  } finally {
    rl.close();
  }

  const shared = { ...secrets, ...sentryDsns };
  const template = readFileSync(SHARED_ENV_EXAMPLE, 'utf8');
  writeFileSync(SHARED_ENV, applyOverrides(template, shared));

  const overridesPerService = buildOverridesPerService(shared, ports);
  console.log();
  generateEnvFiles(overridesPerService);

  console.log();
  const failures = installDependencies();

  console.log();
  if (failures.length > 0) {
    console.log(
      `Instalación completada con errores en: ${failures.map((f) => f.dir).join(', ')}.`,
    );
    console.log('Revisa el detalle de arriba y corrígelo antes de correr esos servicios.');
  } else {
    console.log('Todas las dependencias se instalaron correctamente.');
  }
  console.log('\nPara ejecutar cada microservicio por separado, ejecutar: node scripts/local_run.mjs');
}

main();
