import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseEnv } from 'node:util';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');

export function testPlan(mode, extra = []) {
  const real = extra.includes('--run-model-evals');
  if (['quality', 'e2e-real', 'harness-real'].includes(mode) && !real) {
    throw new Error('Confirma red/coste con --run-model-evals. No se inició ninguna prueba real.');
  }
  if (['frontend', 'frontend-coverage', 'e2e', 'e2e-real'].includes(mode)) {
    if (mode.startsWith('e2e')) {
      return [{ name: mode === 'e2e-real' ? 'Navegador / real (red/coste)' : 'Navegador / API simulada', command: process.execPath,
        args: [resolve(root, 'node_modules/@playwright/test/cli.js'), 'test', '--config',
          mode === 'e2e-real' ? 'tests/frontend/e2e/playwright.real.config.mjs' : 'tests/frontend/e2e/playwright.config.mjs',
          ...extra.filter(arg => arg !== '--run-model-evals')],
        env: { RUN_MODEL_EVALS: mode === 'e2e-real' ? '1' : '0' } }];
    }
    return [{ name: 'Frontend / React offline', command: process.execPath,
      args: [resolve(root, 'node_modules/vitest/vitest.mjs'), 'run', '--config', 'tests/frontend/vitest.config.mts',
        ...(mode === 'frontend-coverage' ? ['--coverage'] : []), ...extra.filter(arg => arg !== '--run-model-evals')],
      env: { RUN_MODEL_EVALS: '0' } }];
  }
  if (mode === 'harness-real') {
    // Evaluación real del harness: temperatura 0, sin caché de respuestas y N=3 muestras (EVAL_MODE=1).
    return [{ name: 'Harness / evaluación real (red/coste)', command: process.platform === 'win32' ? 'uv.exe' : 'uv',
      args: ['run', '--frozen', '--extra', 'dev', '--inexact', 'python', '-m', 'evaluation.harness.runner', 'legal_qa', ...extra],
      env: { EVAL_MODE: '1', PYTHONPATH: 'backend' } }];
  }
  if (mode === 'harness-compare') {
    // Compara los resultados del harness de dos commits (`--base <ref> --head <ref>`); offline salvo --run-model-evals.
    return [{ name: 'Harness / comparación entre commits', command: process.platform === 'win32' ? 'uv.exe' : 'uv',
      args: ['run', '--frozen', '--extra', 'dev', '--inexact', 'python', '-m', 'evaluation.harness.compare', ...extra],
      env: { PYTHONPATH: 'backend' } }];
  }
  const flags = {
    python: [],
    backend: ['tests/backend'],
    scripts: ['tests/scripts/unit'],
    offline: [],
    coverage: ['--cov', '--cov-report=term-missing', '--cov-report=xml:coverage.xml',
      '--junitxml=temp/sonar-reports/pytest.xml', '-o', 'junit_family=legacy'],
    all: [],
    harness: ['tests/backend/harness'],
    quality: ['tests/backend/quality', '-m', 'model_quality', '--run-model-evals'],
    'quality-offline': ['tests/backend/quality', '-m', 'quality'],
  };
  if (mode === 'sonar') flags.sonar = flags.coverage;
  if (!Object.hasOwn(flags, mode)) throw new Error(`Modo desconocido: ${mode}`);
  const tasks = [{
    name: 'Python / evaluaciones',
    command: process.platform === 'win32' ? 'uv.exe' : 'uv',
    args: ['run', '--frozen', '--extra', 'dev', '--inexact', 'pytest', '-c', 'pytest.ini', '-q', ...flags[mode], ...extra],
  }];
  if (mode === 'offline' || mode === 'all' || mode === 'coverage' || mode === 'sonar' || mode === 'scripts') {
    tasks.push({ name: 'Node / scripts', command: process.execPath,
      args: ['--test', 'tests/scripts/unit/*.test.mjs'] });
    if (mode !== 'scripts') tasks.push(...testPlan(mode === 'coverage' || mode === 'sonar' ? 'frontend-coverage' : 'frontend'));
  }
  if (mode === 'sonar') {
    tasks.push({ name: 'SonarQube / análisis', command: process.platform === 'win32' ? 'uv.exe' : 'uv',
      args: ['run', '--frozen', '--group', 'sonar', '--inexact', 'pysonar'], requiresSuccess: true });
  }
  return tasks;
}

export function loadSonarToken(env = process.env, read = readFileSync) {
  let token = env.SONAR_TOKEN?.trim();
  if (!token) {
    let config;
    try {
      config = parseEnv(read(resolve(root, 'backend', '.env'), 'utf8').replace(/^\uFEFF/, ''));
    } catch (error) {
      if (error.code !== 'ENOENT') {
        throw new Error('No se pudo leer backend/.env. Comprueba formato y permisos; consulta docs/SONARQUBE.md.');
      }
    }
    token = config?.SONAR_TOKEN?.trim();
  }
  if (!token || /[\r\n]/.test(token)) {
    throw new Error('Falta SONAR_TOKEN válido. Guárdalo en backend/.env; consulta docs/SONARQUBE.md.');
  }
  return token;
}

export function runPlan(tasks, run = spawnSync, output = console) {
  let failed = false;
  for (const task of tasks) {
    if (task.requiresSuccess && failed) {
      output.error(`${task.name}: omitido porque una suite de tests falló.`);
      continue;
    }
    output.log(`\n=== ${task.name} ===`);
    const result = run(task.command, task.args, {
      cwd: root, stdio: 'inherit', shell: false, windowsHide: true,
      env: { ...process.env, ...task.env, DEEPEVAL_TELEMETRY_OPT_OUT: 'YES' },
    });
    if (result.error || result.status !== 0) {
      failed = true;
      output.error(`${task.name}: falló (${result.status ?? 'no pudo iniciarse'}).`);
    }
  }
  return failed ? 1 : 0;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const mode = process.argv[2] ?? 'offline';
    const plan = testPlan(mode, process.argv.slice(3));
    if (mode === 'sonar') plan.at(-1).env = { SONAR_TOKEN: loadSonarToken() };
    process.exitCode = runPlan(plan);
  } catch (error) {
    console.error(error.message);
    process.exitCode = 2;
  }
}
