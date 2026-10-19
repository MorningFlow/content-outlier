const fs = require('fs');
const path = require('path');

function loadEnv() {
  const envPath = path.join(__dirname, '.env');
  if (!fs.existsSync(envPath)) return {};
  const lines = fs.readFileSync(envPath, 'utf8').split('\n');
  const env = {};
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const idx = trimmed.indexOf('=');
    if (idx === -1) continue;
    let key = trimmed.slice(0, idx).trim();
    let val = trimmed.slice(idx + 1).trim();
    if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
      val = val.slice(1, -1);
    }
    env[key] = val;
  }
  return env;
}

const baseEnv = loadEnv();

module.exports = {
  apps: [
    {
      name: "contentoutlier-web",
      cwd: "/home/ubuntu/apps/contentoutlier/frontend",
      script: ".next/standalone/server.js",
      env: {
        NODE_ENV: "production",
        PORT: 3003,
        HOSTNAME: "0.0.0.0",
        INTERNAL_API_URL: "http://127.0.0.1:8000",
      },
      autorestart: true,
      max_memory_restart: "500M",
      restart_delay: 2000,
    },
    {
      name: "contentoutlier-api",
      cwd: "/home/ubuntu/apps/contentoutlier",
      script: "/home/ubuntu/apps/contentoutlier/.venv/bin/uvicorn",
      args: "app.api.main:app --host 127.0.0.1 --port 8000",
      interpreter: "none",
      env: {
        APP_ENV: "production",
        ...baseEnv,
      },
      autorestart: true,
      max_memory_restart: "400M",
      restart_delay: 2000,
    },
    {
      name: "contentoutlier-worker",
      cwd: "/home/ubuntu/apps/contentoutlier",
      script: "/home/ubuntu/apps/contentoutlier/.venv/bin/python",
      args: "-m app.worker.runner",
      interpreter: "none",
      env: {
        APP_ENV: "production",
        ...baseEnv,
      },
      autorestart: true,
      max_memory_restart: "500M",
      restart_delay: 2000,
    },
  ],
};
