import { spawn } from "node:child_process";
import { createServer } from "node:net";
import { pathToFileURL } from "node:url";

export const CORE_SERVICES = ["postgres", "redis"];
export const BACKEND_HEALTH_URL = "http://localhost:8000/ready";
const READINESS_TIMEOUT_MS = 120_000;
const READINESS_POLL_MS = 1_000;

export function developmentProfile(args) {
  // pnpm may forward the option separator literally; npm consumes it.
  if (args[0] === "--") args = args.slice(1);
  const sat = args.includes("--sat");
  if (args.some((arg) => arg !== "--sat" && arg !== "--lightrag") ||
      (sat && args.includes("--lightrag"))) {
    throw new Error("Use dev:full [--sat | --lightrag].");
  }
  return {
    RAG_ENGINE: sat ? "sat" : "lightrag",
    DEV_BACKEND_PORT: "8000",
    DEV_FRONTEND_PORT: "3000",
  };
}

export function profileEnvironment(profile) {
  const api = `http://localhost:${profile.DEV_BACKEND_PORT}`;
  const frontend = `http://localhost:${profile.DEV_FRONTEND_PORT}`;
  return {
    ...profile,
    PYTHONIOENCODING: "utf-8",
    NEXT_PUBLIC_API_URL: api,
    BACKEND_URL: api,
    GOOGLE_REDIRECT_URI: `${api}/auth/google/callback`,
    GOOGLE_FRONTEND_CALLBACK_URI: `${frontend}/auth/callback`,
  };
}

function ensurePortFree(port, host) {
  return new Promise((resolve, reject) => {
    const server = createServer();
    server.once("error", (error) => reject(new Error(
      `Cannot start: ${host ?? "localhost"}:${port} (${error.code}). Stop the old instance of this profile first.`,
    )));
    server.listen({ port: Number(port), host }, () => server.close(resolve));
  });
}

export function composeUpArgs() {
  return ["compose", "up", "-d", ...CORE_SERVICES];
}

export function isServiceReady(state) {
  return state.status === "running" && state.health === "healthy";
}

function run(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, options);
    let stdout = "";
    let stderr = "";

    child.stdout?.on("data", (chunk) => {
      stdout += chunk;
    });
    child.stderr?.on("data", (chunk) => {
      stderr += chunk;
    });
    child.once("error", reject);
    child.once("close", (code) => resolve({ code, stdout, stderr }));
  });
}

async function serviceState(service) {
  const container = await run("docker", ["compose", "ps", "-q", service]);
  const containerId = container.stdout.trim();

  if (container.code !== 0 || !containerId) {
    return { service, status: "not-created", health: "unknown" };
  }

  const inspection = await run("docker", [
    "inspect",
    "--format",
    "{{.State.Status}}/{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}",
    containerId,
  ]);

  if (inspection.code !== 0) {
    return { service, status: "unknown", health: "unknown" };
  }

  const [status, health] = inspection.stdout.trim().split("/");
  return { service, status, health };
}

function sleep(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

export async function waitForBackendHealth({
  url = BACKEND_HEALTH_URL,
  engine,
  fetchImpl = globalThis.fetch,
  sleepFn = sleep,
  timeoutMs = READINESS_TIMEOUT_MS,
  pollMs = READINESS_POLL_MS,
} = {}) {
  const deadline = Date.now() + timeoutMs;
  let lastFailure = "no response";

  while (Date.now() < deadline) {
    try {
      const response = await fetchImpl(url);
      if (response.ok) {
        if (!engine || (await response.json()).rag_engine === engine) return;
        lastFailure = `expected retrieval engine ${engine}`;
      } else {
        lastFailure = `HTTP ${response.status}`;
      }
    } catch (error) {
      lastFailure = error instanceof Error ? error.message : String(error);
    }

    await sleepFn(pollMs);
  }

  throw new Error(`Timed out waiting for ${url}: ${lastFailure}.`);
}

async function waitForInfrastructure() {
  const deadline = Date.now() + READINESS_TIMEOUT_MS;

  while (Date.now() < deadline) {
    const states = await Promise.all(CORE_SERVICES.map(serviceState));
    if (states.every(isServiceReady)) {
      return;
    }

    const failed = states.find((state) => ["exited", "dead"].includes(state.status));
    if (failed) {
      throw new Error(`${failed.service} stopped before becoming healthy.`);
    }

    await sleep(READINESS_POLL_MS);
  }

  const states = await Promise.all(CORE_SERVICES.map(serviceState));
  const details = states.map(({ service, status, health }) => `${service}=${status}/${health}`).join(", ");
  throw new Error(`Timed out waiting for Docker infrastructure: ${details}.`);
}

async function startInfrastructure() {
  console.log("Starting PostgreSQL and Redis...");
  const result = await run("docker", composeUpArgs(), { stdio: "inherit" });
  if (result.code !== 0) {
    throw new Error("Docker Compose could not start PostgreSQL and Redis.");
  }

  console.log("Waiting for PostgreSQL and Redis health checks...");
  await waitForInfrastructure();
  console.log("PostgreSQL and Redis are healthy. Starting backend...");
}

function startPnpm(args, {
  platform = process.platform,
  nodePath = process.execPath,
  pnpmExecPath = process.env.npm_execpath,
  spawnProcess = spawn,
} = {}) {
  if (platform === "win32") {
    if (!pnpmExecPath) {
      throw new Error("pnpm did not provide npm_execpath for the Windows development launcher.");
    }
    // El entrypoint puede cambiar a standalone también en procesos anidados.
    return /\.exe$/i.test(pnpmExecPath)
      ? spawnProcess(pnpmExecPath, args, { stdio: "inherit" })
      : spawnProcess(nodePath, [pnpmExecPath, ...args], { stdio: "inherit" });
  }

  return spawnProcess("pnpm", args, { stdio: "inherit" });
}

export function startPnpmScript(script, options = {}) {
  return startPnpm(["run", script], options);
}

export async function startFrontendAfterBackend({
  waitForHealth = waitForBackendHealth,
  startFrontend = () => startPnpmScript("frontend:dev"),
} = {}) {
  await waitForHealth();
  return startFrontend();
}

export function startHostProcesses(options = {}) {
  const concurrentlyArgs = [
    "exec",
    "concurrently",
    "-k",
    "-n",
    "BACKEND,FRONTEND",
    "-c",
    "green,blue",
    "pnpm run backend:dev:safe",
    "node scripts/dev-full.mjs frontend-after-backend",
  ];

  return startPnpm(concurrentlyArgs, options);
}

async function runFrontendGate() {
  const port = process.env.DEV_FRONTEND_PORT ?? "3000";
  const backend = `http://localhost:${process.env.DEV_BACKEND_PORT ?? "8000"}`;
  const url = `${backend}/ready`;
  console.log(`Waiting for ${process.env.RAG_ENGINE} backend at ${url}...`);
  const frontend = await startFrontendAfterBackend({
    waitForHealth: () => waitForBackendHealth({ url, engine: process.env.RAG_ENGINE }),
    startFrontend: () => startPnpm(["--dir", "frontend", "exec", "next", "dev", "--port", port, "--hostname", "localhost"]),
  });
  console.log(`Frontend http://localhost:${port} → ${backend} (${process.env.RAG_ENGINE})`);

  for (const signal of ["SIGINT", "SIGTERM"]) {
    process.once(signal, () => frontend.kill(signal));
  }

  return new Promise((resolve, reject) => {
    frontend.once("error", reject);
    frontend.once("close", (code) => resolve(code ?? 1));
  });
}

async function main() {
  const profile = developmentProfile(process.argv.slice(2));
  Object.assign(process.env, profileEnvironment(profile));
  if (profile.RAG_ENGINE === "sat") console.log("SAT-Graph — recuperador experimental");
  await Promise.all([
    ensurePortFree(profile.DEV_BACKEND_PORT, "127.0.0.1"),
    ensurePortFree(profile.DEV_FRONTEND_PORT),
  ]);
  await startInfrastructure();

  const hosts = startHostProcesses();
  for (const signal of ["SIGINT", "SIGTERM"]) {
    process.once(signal, () => {
      hosts.kill(signal);
    });
  }

  const exitCode = await new Promise((resolve, reject) => {
    hosts.once("error", reject);
    hosts.once("close", (code) => resolve(code ?? 1));
  });
  process.exitCode = exitCode;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const entrypoint = process.argv[2] === "frontend-after-backend" ? runFrontendGate : main;
  entrypoint().then((exitCode) => {
    if (typeof exitCode === "number") {
      process.exitCode = exitCode;
    }
  }).catch((error) => {
    console.error(`Development startup failed: ${error.message}`);
    process.exitCode = 1;
  });
}
