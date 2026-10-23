import test from 'node:test';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { loadSonarToken, runPlan, testPlan } from '../../../scripts/run-tests.mjs';

function capturedOutput() {
  return { errors: [], logs: [], error(message) { this.errors.push(message); },
    log(message) { this.logs.push(message); } };
}

test('offline incluye Python y Node sin activar modelos reales', () => {
  const plan = testPlan('offline');
  assert.equal(plan.length, 3);
  assert.ok(!plan[0].args.includes('--run-model-evals'));
});

test('todos los modos Python usan configuración raíz y las suites Node viven en tests', () => {
  for (const mode of ['python', 'backend', 'scripts', 'offline', 'coverage', 'sonar', 'all', 'quality', 'quality-offline']) {
    const plan = testPlan(mode, mode === 'quality' ? ['--run-model-evals'] : []);
    const index = plan[0].args.indexOf('-c');
    assert.notEqual(index, -1);
    assert.equal(plan[0].args[index + 1], 'pytest.ini');
    assert.ok(!plan[0].args.includes('--run-model-evals') || ['all', 'quality'].includes(mode));
    const nodeTask = plan.find(task => task.command === process.execPath);
    if (nodeTask) {
      assert.deepEqual(nodeTask.args, ['--test', 'tests/scripts/unit/*.test.mjs']);
    }
  }
  assert.equal(testPlan('python').length, 1);
  assert.equal(testPlan('backend').length, 1);
  assert.ok(testPlan('backend')[0].args.includes('tests/backend'));
  assert.ok(testPlan('scripts')[0].args.includes('tests/scripts/unit'));
});

test('all incluye evaluación real y continúa con Node', () => {
  const plan = testPlan('all', ['--run-model-evals']);
  assert.equal(plan.length, 3);
  assert.ok(plan[0].args.includes('--run-model-evals'));
});

test('coverage produce Cobertura y xUnit compatible sin activar modelos reales', () => {
  const plan = testPlan('coverage');
  assert.equal(plan.length, 3);
  assert.ok(plan[2].args.includes('--coverage'));
  assert.ok(plan[0].args.includes('--cov'));
  assert.ok(plan[0].args.includes('--cov-report=xml:coverage.xml'));
  assert.ok(plan[0].args.includes('--junitxml=temp/sonar-reports/pytest.xml'));
  assert.ok(plan[0].args.includes('junit_family=legacy'));
  assert.ok(!plan[0].args.includes('--run-model-evals'));
  assert.ok(testPlan('coverage', ['--run-model-evals'])[0].args.includes('--run-model-evals'));
});

test('quality selecciona solo las pruebas del modelo y reenvía opciones', () => {
  const plan = testPlan('quality', ['--run-model-evals', '--model-eval-timeout', '60']);
  assert.equal(plan.length, 1);
  assert.deepEqual(plan[0].args.slice(-2), ['--model-eval-timeout', '60']);
  assert.ok(plan[0].args.includes('model_quality'));
});

test('harness es offline y harness-real exige --run-model-evals con EVAL_MODE=1', () => {
  const offline = testPlan('harness');
  assert.equal(offline.length, 1);
  assert.ok(offline[0].args.includes('tests/backend/harness'));
  assert.ok(!offline[0].args.includes('--run-model-evals'));
  assert.throws(() => testPlan('harness-real'), /--run-model-evals/);
  const real = testPlan('harness-real', ['--run-model-evals']);
  assert.deepEqual(real.map(task => task.args[task.args.indexOf('evaluation.harness.runner') + 1]),
    ['legal_qa', 'retrieval', 'translation', 'stream']);
  for (const task of real) {
    assert.equal(task.env.EVAL_MODE, '1');
    assert.ok(task.args.includes('--run-model-evals'));
    assert.ok(task.args.includes('ragas==0.4.3'), 'RAGAS solo en la capa temporal de la corrida real');
  }
  assert.ok(real[0].args.includes('--judge') && real[0].args.includes('deepeval'));
});

test('harness-compare pasa --base y --head al comparador sin activar modelos reales', () => {
  const plan = testPlan('harness-compare', ['--base', 'v8', '--head', 'HEAD', '--run-missing']);
  assert.equal(plan.length, 1);
  assert.ok(plan[0].args.includes('evaluation.harness.compare'));
  assert.deepEqual(plan[0].args.slice(-5), ['--base', 'v8', '--head', 'HEAD', '--run-missing']);
  assert.ok(!plan[0].args.includes('--run-model-evals'));
  assert.ok(!plan[0].args.includes('ragas==0.4.3'));
});

test('quality-offline y modos inválidos no activan facturación', () => {
  assert.ok(!testPlan('quality-offline')[0].args.includes('--run-model-evals'));
  assert.throws(() => testPlan('invalid'), /Modo desconocido/);
});

test('fallos de una suite no ocultan las restantes y mantienen exit code', () => {
  const calls = [];
  const output = capturedOutput();
  const result = runPlan(testPlan('all'), (command, args, options) => {
    calls.push({ command, options });
    return { status: calls.length === 1 ? 1 : 0 };
  }, output);
  assert.equal(calls.length, 3);
  assert.equal(result, 1);
  assert.equal(output.errors.length, 1);
  assert.match(output.errors[0], /falló \(1\)/);
  assert.equal(calls[0].options.windowsHide, true);
  assert.equal(calls[0].options.env.DEEPEVAL_TELEMETRY_OPT_OUT, 'YES');
});

test('error de arranque falla la ejecución y éxito retorna cero', () => {
  const output = capturedOutput();
  assert.equal(runPlan(testPlan('quality', ['--run-model-evals']), () => ({ error: new Error('not found'), status: null }), output), 1);
  assert.match(output.errors[0], /no pudo iniciarse/);
  assert.equal(runPlan(testPlan('quality-offline'), () => ({ status: 0 }), output), 0);
});

test('sonar lee SONAR_TOKEN de backend/.env con BOM, comillas y CRLF sin cargar otras claves', () => {
  const env = {};
  const token = loadSonarToken(env, (path, encoding) => {
    assert.equal(path, fileURLToPath(new URL('../../../backend/.env', import.meta.url)));
    assert.equal(encoding, 'utf8');
    return '\uFEFF# secreto local\r\nSONAR_TOKEN=" PRIVATE " # scanner\r\nOTHER_SECRET=other\r\n';
  });
  assert.equal(token, 'PRIVATE');
  assert.deepEqual(env, {});
});

test('sonar permite SONAR_TOKEN del entorno para CI sin leer archivos', () => {
  assert.equal(loadSonarToken({ SONAR_TOKEN: ' PRIVATE ' }, () => assert.fail('no leer archivo')), 'PRIVATE');
  assert.equal(loadSonarToken({ SONAR_TOKEN: ' ' }, () => 'SONAR_TOKEN=FILE'), 'FILE');
});

test('sonar diagnostica archivo ausente, vacío, token MCP y multilínea sin revelar secretos', () => {
  const missing = () => { throw Object.assign(new Error('PRIVATE'), { code: 'ENOENT' }); };
  assert.throws(() => loadSonarToken({}, missing), /Falta SONAR_TOKEN/);
  for (const content of ['', 'SONAR_TOKEN= ', 'SONARQUBE_TOKEN=PRIVATE', 'SONAR_TOKEN="PRIVATE\nPRIVATE"']) {
    assert.throws(() => loadSonarToken({ SONARQUBE_TOKEN: 'PRIVATE' }, () => content), error => {
      assert.match(error.message, /Falta SONAR_TOKEN/);
      assert.ok(!error.message.includes('PRIVATE'));
      return true;
    });
  }
  assert.throws(() => loadSonarToken({}, () => { throw new Error('PRIVATE'); }), error => {
    assert.match(error.message, /No se pudo leer/);
    assert.ok(!error.message.includes('PRIVATE'));
    return true;
  });
});

test('sonar entrega el token del archivo solo al scanner, no a tests ni argumentos', () => {
  const plan = testPlan('sonar');
  const calls = [];
  plan.at(-1).env = { SONAR_TOKEN: loadSonarToken({}, () => 'SONAR_TOKEN=PRIVATE\nOTHER_SECRET=other') };
  assert.equal(runPlan(plan, (command, args, options) => {
    calls.push({ args, options });
    return { status: 0 };
  }, capturedOutput()), 0);
  assert.equal(calls[0].options.env.SONAR_TOKEN, process.env.SONAR_TOKEN);
  assert.equal(calls[1].options.env.SONAR_TOKEN, process.env.SONAR_TOKEN);
  assert.equal(calls[2].options.env.SONAR_TOKEN, process.env.SONAR_TOKEN);
  assert.equal(calls[3].options.env.SONAR_TOKEN, 'PRIVATE');
  assert.equal(calls[3].options.env.OTHER_SECRET, process.env.OTHER_SECRET);
  assert.ok(!calls.some(call => call.args.some(arg => arg.includes('PRIVATE'))));
});

test('sonar ejecuta scanner solo después de todas las suites exitosas', () => {
  const plan = testPlan('sonar');
  const calls = [];
  const output = capturedOutput();
  assert.equal(runPlan(plan, (command, args) => {
    calls.push(args);
    return { status: calls.length === 1 ? 1 : 0 };
  }, output), 1);
  assert.equal(calls.length, 3);
  assert.ok(!calls.some(args => args.includes('pysonar')));
  assert.equal(runPlan(plan, () => ({ status: 0 }), output), 0);
  assert.equal(plan[3].args.at(-1), 'pysonar');
  assert.equal(plan[3].requiresSuccess, true);
});

test('modelos reales requieren flag explícito y frontend offline nunca lo hereda', () => {
  assert.throws(() => testPlan('quality'), /--run-model-evals/);
  assert.throws(() => testPlan('e2e-real'), /--run-model-evals/);
  assert.ok(!testPlan('all')[0].args.includes('--run-model-evals'));
  const real = testPlan('e2e-real', ['--run-model-evals']);
  assert.equal(real[0].env.RUN_MODEL_EVALS, '1');
  assert.ok(real[0].args.includes('tests/frontend/e2e/playwright.real.config.mjs'));
  assert.equal(testPlan('e2e')[0].env.RUN_MODEL_EVALS, '0');
  assert.equal(testPlan('frontend', ['--run-model-evals'])[0].env.RUN_MODEL_EVALS, '0');
  assert.ok(!testPlan('frontend', ['--run-model-evals'])[0].args.includes('--run-model-evals'));
});

test('coverage frontend usa LCOV separado y conserva opciones Vitest', () => {
  const plan = testPlan('frontend-coverage', ['--reporter=verbose']);
  assert.ok(plan[0].args.includes('--coverage'));
  assert.equal(plan[0].args.at(-1), '--reporter=verbose');
  assert.equal(testPlan('frontend')[0].args.includes('--coverage'), false);
});
