#!/usr/bin/env node
/**
 * Compara la latencia del camino síncrono (TCP `users.validate`, bets-service -> users-service)
 * contra el camino asíncrono (Redis Streams `XADD`, auth-service -> security-events) mediante
 * N iteraciones secuenciales de cada uno, midiendo el round-trip de cada operación.
 *
 * Uso:
 *   node scripts/latency.mjs [--iterations 200] [--warmup 20]
 *
 * Variables de entorno (con default apuntando al setup local):
 *   USERS_TCP_HOST=localhost   USERS_TCP_PORT=3011
 *   REDIS_HOST=localhost       REDIS_PORT=6379
 *   BENCH_USER_ID=<id de un usuario real ya creado en users-service>
 */

import { connect } from 'node:net';

const args = process.argv.slice(2);
const flag = (name, def) => {
  const i = args.indexOf(`--${name}`);
  return i !== -1 && args[i + 1] !== undefined ? Number(args[i + 1]) : def;
};

const ITERATIONS = flag('iterations', 200);
const WARMUP = flag('warmup', 20);

const USERS_TCP_HOST = process.env.USERS_TCP_HOST ?? 'localhost';
const USERS_TCP_PORT = Number(process.env.USERS_TCP_PORT ?? 3011);
const REDIS_HOST = process.env.REDIS_HOST ?? 'localhost';
const REDIS_PORT = Number(process.env.REDIS_PORT ?? 6379);
const BENCH_USER_ID = process.env.BENCH_USER_ID ?? '000000000000000000000000';
const BENCH_STREAM = process.env.BENCH_STREAM ?? 'latency-bench';

/** Framing `<longitud>#<json>` de `Transport.TCP` de Nest. */
function encodeTcpFrame(payload) {
  const body = Buffer.from(JSON.stringify(payload), 'utf8');
  return Buffer.concat([Buffer.from(`${body.length}#`, 'utf8'), body]);
}

/** Una llamada `users.validate` completa: abre socket, escribe, espera respuesta, cierra. */
function tcpValidateOnce() {
  return new Promise((resolve, reject) => {
    const start = process.hrtime.bigint();
    const socket = connect(USERS_TCP_PORT, USERS_TCP_HOST, () => {
      const payload = {
        pattern: 'users.validate',
        id: '1',
        data: { user_id: BENCH_USER_ID, request_id: `latency-bench-${Date.now()}` },
      };
      socket.write(encodeTcpFrame(payload));
    });

    let buffer = Buffer.alloc(0);
    socket.on('data', (chunk) => {
      buffer = Buffer.concat([buffer, chunk]);
      const sep = buffer.indexOf('#');
      if (sep === -1) return;
      const length = Number(buffer.subarray(0, sep).toString('utf8'));
      if (buffer.length - sep - 1 < length) return; // frame incompleto, sigue leyendo
      const elapsedMs = Number(process.hrtime.bigint() - start) / 1e6;
      socket.end();
      resolve(elapsedMs);
    });
    socket.on('error', reject);
  });
}

/** Codifica un comando en protocolo RESP (Array de Bulk Strings), como hace cualquier cliente Redis. */
function encodeResp(...args) {
  const parts = [`*${args.length}\r\n`];
  for (const arg of args) {
    const s = String(arg);
    parts.push(`$${Buffer.byteLength(s)}\r\n${s}\r\n`);
  }
  return Buffer.from(parts.join(''), 'utf8');
}

/** Una llamada `XADD` completa contra Redis: abre socket, escribe, espera respuesta (+id), cierra. */
function redisXaddOnce(seq) {
  return new Promise((resolve, reject) => {
    const start = process.hrtime.bigint();
    const socket = connect(REDIS_PORT, REDIS_HOST, () => {
      socket.write(
        encodeResp('XADD', BENCH_STREAM, '*', 'seq', String(seq), 'ts', String(Date.now())),
      );
    });

    let buffer = '';
    socket.on('data', (chunk) => {
      buffer += chunk.toString('utf8');
      if (!buffer.endsWith('\r\n')) return; // respuesta RESP incompleta, sigue leyendo
      const elapsedMs = Number(process.hrtime.bigint() - start) / 1e6;
      socket.end();
      resolve(elapsedMs);
    });
    socket.on('error', reject);
  });
}

function stats(samples) {
  const sorted = [...samples].sort((a, b) => a - b);
  const sum = sorted.reduce((acc, v) => acc + v, 0);
  const p95Index = Math.ceil(0.95 * sorted.length) - 1;
  return {
    avg: sum / sorted.length,
    p95: sorted[Math.max(0, p95Index)],
    max: sorted[sorted.length - 1],
  };
}

async function runSeries(label, warmupFn, iterFn) {
  console.log(`\n-- ${label}: ${WARMUP} warmup + ${ITERATIONS} mediciones --`);
  for (let i = 0; i < WARMUP; i++) await warmupFn(i);

  const samples = [];
  for (let i = 0; i < ITERATIONS; i++) {
    samples.push(await iterFn(i));
  }
  return stats(samples);
}

function fmt(ms) {
  return `${ms.toFixed(2)} ms`;
}

async function main() {
  console.log('Comparativa de latencia: TCP síncrono (users.validate) vs Redis asíncrono (XADD)');
  console.log(`Iteraciones: ${ITERATIONS} (+ ${WARMUP} de calentamiento) por camino`);

  const tcpStats = await runSeries('Síncrono (TCP users.validate)', tcpValidateOnce, tcpValidateOnce);
  const redisStats = await runSeries(
    'Asíncrono (Redis XADD)',
    (i) => redisXaddOnce(`warmup-${i}`),
    (i) => redisXaddOnce(i),
  );

  console.log('\n| Camino | Promedio | p95 | Máximo |');
  console.log('|---|---|---|---|');
  console.log(`| Síncrono (TCP) | ${fmt(tcpStats.avg)} | ${fmt(tcpStats.p95)} | ${fmt(tcpStats.max)} |`);
  console.log(`| Asíncrono (Redis) | ${fmt(redisStats.avg)} | ${fmt(redisStats.p95)} | ${fmt(redisStats.max)} |`);

  console.log(
    '\nNota: ambas mediciones son round-trip del transporte (el cliente espera la respuesta/ack en ' +
      'los dos casos), para comparar el costo puro de cada protocolo. La diferencia de fondo entre ' +
      'los caminos no es esta latencia individual sino el acoplamiento temporal (Avance 1): el ' +
      'síncrono bloquea la petición HTTP del usuario si el vecino cae, el asíncrono no.',
  );
}

main().catch((err) => {
  console.error('Error ejecutando el benchmark de latencia:', err);
  process.exitCode = 1;
});
