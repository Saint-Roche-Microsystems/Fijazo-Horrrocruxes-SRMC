#!/usr/bin/env node
/**
 * Muestra, servicio por servicio, los comandos para levantar la plataforma en local sin
 * Docker consolidado: cada microservicio corre con poetry/npm en el host, y solo su Mongo
 * propio (más Redis/RabbitMQ compartidos) corre en contenedor.
 */

import { existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));

const SERVICE_DIRS = [
  'auth-service',
  'users-service',
  'bets-service',
  'progression-service',
  'api-gateway',
];

const DEFAULT_PORTS = { auth: '8001', bets: '8002', progression: '8003' };

function readEnvFile(path) {
  if (!existsSync(path)) return {};
  const values = {};
  for (const line of readFileSync(path, 'utf8').split('\n')) {
    const match = line.match(/^([A-Z0-9_]+)=(.*)$/);
    if (match) values[match[1]] = match[2].trim();
  }
  return values;
}

function extractPort(url, fallback) {
  const match = typeof url === 'string' ? url.match(/:(\d+)(?:\/|$)/) : null;
  return match ? match[1] : fallback;
}

function resolvePorts() {
  const gatewayEnv = readEnvFile(join(ROOT, 'api-gateway', '.env'));
  return {
    auth: extractPort(gatewayEnv.AUTH_SERVICE_URL, DEFAULT_PORTS.auth),
    bets: extractPort(gatewayEnv.BETS_SERVICE_URL, DEFAULT_PORTS.bets),
    progression: extractPort(gatewayEnv.PROGRESSION_SERVICE_URL, DEFAULT_PORTS.progression),
  };
}

function buildServices(ports) {
  return [
    {
      dir: 'auth-service',
      runCmd: `poetry run uvicorn auth_service.main:app --reload --port ${ports.auth}`,
    },
    { dir: 'users-service', runCmd: 'npm run start:dev' },
    {
      dir: 'bets-service',
      runCmd: `poetry run uvicorn bets_service.main:app --reload --port ${ports.bets}`,
    },
    {
      dir: 'progression-service',
      runCmd: `poetry run uvicorn progression_service.main:app --reload --port ${ports.progression}`,
    },
    { dir: 'api-gateway', runCmd: 'npm run start:dev' },
  ];
}

/** Todos los servicios necesitan su .env ya generado (por bootstrap.mjs) antes de esto. */
function checkEnvFiles() {
  const missing = SERVICE_DIRS.filter((dir) => !existsSync(join(ROOT, dir, '.env')));

  if (missing.length > 0) {
    console.error('Faltan archivos .env en los siguientes microservicios:\n');
    for (const dir of missing) console.error(`  - ${dir}/.env`);
    console.error('\nCorre primero: node scripts/bootstrap.mjs');
    process.exit(1);
  }
}

function printInstructions(services) {
  console.log('Todos los microservicios tienen su .env. Secuencia para levantar todo en local:\n');

  console.log('0. Infraestructura compartida (Redis + RabbitMQ), desde la raíz del proyecto:');
  console.log('   docker compose up -d redis rabbitmq\n');

  for (const service of services) {
    console.log(`--- ${service.dir} ---`);
    console.log(`1. cd ${service.dir}`);
    if (service.dir === 'api-gateway') {
      console.log(`2. ${service.runCmd}`);
    } else {
      console.log('2. docker compose up -d mongo');
      console.log(`3. ${service.runCmd}`);
    }
    console.log();
  }
}

checkEnvFiles();
printInstructions(buildServices(resolvePorts()));
