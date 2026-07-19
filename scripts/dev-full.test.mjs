import assert from "node:assert/strict";
import test from "node:test";

import {
  CORE_SERVICES,
  BACKEND_HEALTH_URL,
  composeUpArgs,
  isServiceReady,
  startFrontendAfterBackend,
  startHostProcesses,
  waitForBackendHealth,
} from "./dev-full.mjs";

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

test("Windows requires pnpm's JavaScript entrypoint", () => {
  assert.throws(
    () => startHostProcesses({ platform: "win32", pnpmExecPath: "" }),
    /npm_execpath/,
  );
});

test("pnpm supplies the Windows launcher entrypoint to package scripts", () => {
  assert.match(process.env.npm_execpath ?? "", /pnpm\.cjs$/i);
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
