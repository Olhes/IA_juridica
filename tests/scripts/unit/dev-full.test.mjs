import assert from "node:assert/strict";
import test from "node:test";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

import {
  CORE_SERVICES,
  BACKEND_HEALTH_URL,
  composeUpArgs,
  developmentProfile,
  ensureSatCorpus,
  profileEnvironment,
  isServiceReady,
  startFrontendAfterBackend,
  startHostProcesses,
  startPnpmScript,
  waitForBackendHealth,
} from "../../../scripts/dev-full.mjs";

test("both retrieval engines use the same local ports", () => {
  assert.deepEqual(developmentProfile([]), developmentProfile(["--sat"]));
  assert.deepEqual(developmentProfile([]), {
    RAG_ENGINE: "sat", DEV_BACKEND_PORT: "8000", DEV_FRONTEND_PORT: "3000",
  });
  assert.deepEqual(developmentProfile(["--lightrag"]), {
    RAG_ENGINE: "lightrag", DEV_BACKEND_PORT: "8000", DEV_FRONTEND_PORT: "3000",
  });
  assert.deepEqual(developmentProfile(["--", "--sat"]), developmentProfile(["--sat"]));
  assert.throws(() => developmentProfile(["--sat", "--lightrag"]));
  assert.throws(() => developmentProfile(["--unknown"]));
});

test("both retrieval engines retain the existing Google OAuth callback", () => {
  for (const args of [[], ["--lightrag"]]) {
    const env = profileEnvironment(developmentProfile(args));
    assert.equal(env.GOOGLE_REDIRECT_URI, "http://localhost:8000/auth/google/callback");
    assert.equal(env.GOOGLE_FRONTEND_CALLBACK_URI, "http://localhost:3000/auth/callback");
    assert.equal(env.NEXT_PUBLIC_API_URL, "http://localhost:8000");
  }
});

test("readiness checks the selected backend rather than the default", async () => {
  const url = BACKEND_HEALTH_URL;
  const engines = ["lightrag", "sat"];
  await waitForBackendHealth({
    url, engine: "sat", sleepFn: async () => {}, fetchImpl: async (actual) => {
      assert.equal(actual, url);
      const rag_engine = engines.shift();
      return { ok: true, json: async () => ({ rag_engine }) };
    },
    timeoutMs: 1_000,
  });
  assert.deepEqual(engines, []);
});

test("development startup brings up the database the backend defaults to", () => {
  assert.deepEqual(CORE_SERVICES, ["surreal", "redis"]);
  assert.deepEqual(composeUpArgs(), ["compose", "up", "-d", "surreal", "redis"]);
});

test("Docker Compose excludes legacy PostgreSQL by default", (t) => {
  const cwd = fileURLToPath(new URL("../../../", import.meta.url));
  const config = (...args) => spawnSync("docker", ["compose", ...args, "config", "--services"], {
    cwd, encoding: "utf8",
  });
  const defaults = config();
  if (defaults.error?.code === "ENOENT") return t.skip("Docker CLI is not installed");
  assert.equal(defaults.status, 0, defaults.stderr);
  assert.deepEqual(defaults.stdout.trim().split(/\r?\n/).sort(), ["redis", "surreal"]);
  const legacy = config("--profile", "legacy-postgres");
  assert.equal(legacy.status, 0, legacy.stderr);
  assert.deepEqual(legacy.stdout.trim().split(/\r?\n/).sort(), ["postgres", "redis", "surreal"]);
});

test("SAT uses the SurrealDB corpus initializer", async () => {
  const calls = [];
  const recorder = (code, stdout = "", stderr = "") => async (...args) => {
    calls.push(args);
    return { code, stdout, stderr };
  };

  assert.equal(await ensureSatCorpus({
    RAG_ENGINE: "lightrag", runProcess: recorder(0),
  }), "skipped");
  assert.deepEqual(calls, []);

  for (const status of ["present", "restored"]) {
    assert.equal(await ensureSatCorpus({
      RAG_ENGINE: "sat", runProcess: recorder(0, status + "\n"),
    }), status);
  }
  assert.deepEqual(calls, Array.from({ length: 2 }, () => [
    "uv", ["run", "python", "-m", "scripts.bootstrap_sat_corpus"], { cwd: "backend" },
  ]));
  await assert.rejects(ensureSatCorpus({
    RAG_ENGINE: "sat", runProcess: recorder(1, "", "connection failed"),
  }), /SurrealDB: connection failed/);
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

test("readiness names a non-JSON body instead of swallowing the parse error", async () => {
  await assert.rejects(
    waitForBackendHealth({
      engine: "sat",
      fetchImpl: async () => ({
        ok: true,
        status: 200,
        json: async () => {
          throw new SyntaxError("Unexpected end of JSON input");
        },
      }),
      sleepFn: () => new Promise((resolve) => setTimeout(resolve, 10)),
      timeoutMs: 5,
    }),
    /without a JSON body — another service may own/,
  );
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
