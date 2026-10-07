import { spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../', import.meta.url));
const path = fileURLToPath(new URL('../requirements.txt', import.meta.url));
const header = '# Generado desde pyproject.toml + uv.lock. No editar manualmente.\n# Regenerar: pnpm deps:export\n';
const result = spawnSync('uv', ['export', '--frozen', '--no-dev', '--no-emit-project',
  '--no-hashes', '--no-annotate', '--no-header', '--quiet'],
{ cwd: root, encoding: 'utf8', windowsHide: true, shell: false });
if (result.error || result.status !== 0) {
  console.error(result.stderr || result.error?.message || 'uv export failed');
  process.exit(1);
}
const expected = header + result.stdout.replace(/\r\n/g, '\n');
if (process.argv.includes('--check')) {
  if (readFileSync(path, 'utf8').replace(/\r\n/g, '\n') !== expected) {
    console.error('requirements.txt está desactualizado. Ejecuta pnpm deps:export.');
    process.exit(1);
  }
  console.log('requirements.txt coincide con uv.lock (runtime, sin extras/grupos dev/sonar).');
} else {
  writeFileSync(path, expected);
  console.log('requirements.txt regenerado desde uv.lock.');
}
