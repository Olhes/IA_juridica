import assert from "node:assert/strict";
import test from "node:test";

import {
  CORE_SERVICES,
  BACKEND_HEALTH_URL,
  composeUpArgs,
  isServiceReady,
  startFrontendAfterBackend,
  startHostProcesses,
  startPnpmScript,
  waitForBackendHealth,
} from "../../../scripts/dev-full.mjs";

test("development startup targets only PostgreSQL and Redis", () => {
  assert.deepEqual(CORE_SERVICES, ["postgres", "redis"]);
  assert.deepEqual(composeUpArgs(), ["compose", "up", "-d", "postgres", "redis"]);
});

test("host processes require running containers with healthy checks", () => {
  assert.equal(isServiceReady({ status: "running", health: "healthy" }), true);
  assert.equal(isServiceReady({ status: "running", health: "starting" }), false);
  assert.equal(isServiceReady({ status: "exited", health: "unhealthy" }), false);
});

test("Windows launches pnpm concurrently with an argument vector", () => {
  let received;
  const child = {};
  const pnpmExecPath = "C:\\Users\\developer\\AppData\\Local\\pnpm\\pnpm.cjs";

  const result = startHostProcesses({
    platform: "win32",
    nodePath: "C:\\Program Files\\nodejs\\node.exe",
    pnpmExecPath,
    spawnProcess: (...args) => {
      received = args;
      return child;
    },
  });

  assert.equal(result, child);
  assert.deepEqual(received, [
    "C:\\Program Files\\nodejs\\node.exe",
    [
      pnpmExecPath,
      "exec",
      "concurrently",
      "-k",
      "-n",
      "BACKEND,FRONTEND",
      "-c",
      "green,blue",
      "pnpm run backend:dev:safe",
      "node scripts/dev-full.mjs frontend-after-backend",
    ],
    { stdio: "inherit" },
  ]);
});

test("Windows executes standalone pnpm without passing an exe to Node", () => {
  let received;
  startHostProcesses({ platform: "win32", pnpmExecPath: "C:\\pnpm\\pnpm.exe",
    spawnProcess: (...args) => { received = args; return {}; } });
  assert.equal(received[0], "C:\\pnpm\\pnpm.exe");
  assert.equal(received[1][0], "exec");
});

test("Windows nested frontend executes standalone pnpm directly", () => {
  const pnpmExecPath = "C:\\Users\\developer name\\AppData\\Local\\pnpm\\@pnpm\\exe\\pnpm.EXE";
  let received;
  const child = {};
  const result = startPnpmScript("frontend:dev", {
    platform: "win32",
    nodePath: "C:\\Program Files\\nodejs\\node.exe",
    pnpmExecPath,
    spawnProcess: (...args) => { received = args; return child; },
  });
  assert.equal(result, child);
  assert.deepEqual(received, [pnpmExecPath, ["run", "frontend:dev"], { stdio: "inherit" }]);
});

test("Windows nested frontend uses Node for JavaScript pnpm entrypoints", () => {
  const nodePath = "C:\\Program Files\\nodejs\\node.exe";
  const pnpmExecPath = "C:\\Users\\developer name\\pnpm\\pnpm.cjs";
  let received;
  startPnpmScript("frontend:dev", {
    platform: "win32", nodePath, pnpmExecPath,
    spawnProcess: (...args) => { received = args; return {}; },
  });
  assert.deepEqual(received, [nodePath, [pnpmExecPath, "run", "frontend:dev"], { stdio: "inherit" }]);
});

test("Windows nested frontend requires pnpm's entrypoint", () => {
  assert.throws(() => startPnpmScript("frontend:dev", { platform: "win32", pnpmExecPath: "" }), /npm_execpath/);
});

test("Windows requires pnpm's entrypoint", () => {
  assert.throws(
    () => startHostProcesses({ platform: "win32", pnpmExecPath: "" }),
    /npm_execpath/,
  );
});

test("pnpm supplies the Windows launcher entrypoint to package scripts", () => {
  assert.match(process.env.npm_execpath ?? "", /pnpm\.(?:cjs|exe)$/i);
});

test("backend health retries transient failures until it succeeds", async () => {
  const attempts = [];
  const responses = [
    new TypeError("fetch failed"),
    { ok: false, status: 503 },
    { ok: true, status: 200 },
  ];

  await waitForBackendHealth({
    fetchImpl: async (url) => {
      attempts.push(url);
      const response = responses.shift();
      if (response instanceof Error) throw response;
      return response;
    },
    sleepFn: async () => {},
    timeoutMs: 1_000,
  });

  assert.deepEqual(attempts, [BACKEND_HEALTH_URL, BACKEND_HEALTH_URL, BACKEND_HEALTH_URL]);
});

test("frontend is not started until backend health succeeds", async () => {
  let releaseHealth;
  let frontendStarted = false;
  const health = new Promise((resolve) => {
    releaseHealth = resolve;
  });

  const pending = startFrontendAfterBackend({
    waitForHealth: () => health,
    startFrontend: () => {
      frontendStarted = true;
      return { pid: 1234 };
    },
  });

  await Promise.resolve();
  assert.equal(frontendStarted, false);
  releaseHealth();
  const frontend = await pending;
  assert.equal(frontendStarted, true);
  assert.deepEqual(frontend, { pid: 1234 });
});
