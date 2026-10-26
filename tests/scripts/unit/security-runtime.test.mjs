import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { brotliCompressSync, brotliDecompressSync, constants } from 'node:zlib';

const root = new URL('../../../', import.meta.url);
const read = (path) => readFileSync(new URL(path, root), 'utf8');
const manifest = (path) => JSON.parse(read(path));

test('el runtime ejecutado contiene el parche y mantiene Brotli funcional', () => {
  const [major, minor, patch] = process.versions.node.split('.').map(Number);
  assert.ok(major === 24 && (minor > 22 || (minor === 22 && patch >= 1)),
    `Node ${process.versions.node} no satisface >=24.22.1 <25`);
  assert.ok(Number.isInteger(constants.BROTLI_DECODER_ERROR_FORMAT_BLOCK_SWITCH));
  const input = Buffer.from('Comprobación de compresión segura: español y quechua.');
  assert.deepEqual(brotliDecompressSync(brotliCompressSync(input)), input);
});

test('ambos proyectos exigen Node 24 con el parche de Brotli', () => {
  for (const path of ['package.json', 'frontend/package.json']) {
    assert.equal(manifest(path).engines.node, '>=24.22.1 <25');
  }
  assert.equal(read('.nvmrc').trim(), '24.22.1');
  assert.equal(read('.node-version').trim(), '24.22.1');
  assert.match(read('.npmrc'), /^engine-strict=true$/m);
  assert.match(read('frontend/.npmrc'), /^engine-strict=true$/m);
});

test('ambas etapas Docker usan una base Node parcheada', () => {
  const stages = read('frontend/Dockerfile').match(/^FROM .+$/gm);
  assert.deepEqual(stages, [
    'FROM node:24.22.1-alpine AS builder',
    'FROM node:24.22.1-alpine AS runtime',
  ]);
});

test('Next y las transitivas de desarrollo conservan sus parches de seguridad', () => {
  assert.equal(manifest('frontend/package.json').dependencies.next, '16.4.3');
  const overrides = manifest('package.json').pnpm.overrides;
  assert.equal(overrides['shell-quote@<1.11.0'], '1.11.0');
  assert.equal(overrides['undici@>=7.0.0 <7.30.1'], '7.30.1');
});
