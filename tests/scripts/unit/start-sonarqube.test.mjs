import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { spawnSync } from 'node:child_process';

const root = new URL('../../../', import.meta.url);
const manifest = JSON.parse(readFileSync(new URL('package.json', root), 'utf8'));

test('sonar:start arranca el servidor sin alterar el comando de análisis', () => {
  assert.match(manifest.scripts['sonar:start'], /scripts\/start-sonarqube\.ps1/);
  assert.equal(manifest.scripts.sonar, 'node scripts/run-tests.mjs sonar');
});

test('sonar:start comprueba rutas locales sin iniciar el servidor', (t) => {
  if (process.platform !== 'win32' ||
      !existsSync('C:\\Herramientas\\jdk-21\\bin\\java.exe') ||
      !existsSync('D:\\Installations\\sonarqube-26.11.0.134175\\bin\\windows-x86-64\\StartSonar.bat')) {
    return t.skip('La instalación local de Windows no está disponible.');
  }
  const result = spawnSync('powershell', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
    'scripts/start-sonarqube.ps1', '-Check'], { cwd: root, encoding: 'utf8', windowsHide: true });
  assert.equal(result.status, 0, result.stderr);
});
