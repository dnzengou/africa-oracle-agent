# Deploy Guide — Africa Oracle Agent v0.2.0

## Status
- ✅ Dockerfile: multi-arch (linux/amd64 + linux/arm64), healthcheck baked in
- ✅ `fly.toml`: ARM64 shared-cpu, jnb region, healthcheck on `/health`
- ✅ `vercel.json`: Python ASGI, 60s max
- ✅ `.github/workflows/ci.yml`: tests + multi-arch GHCR publish on push to main
- ⚠ Local verification skipped: Docker daemon offline at deploy time
- ⚠ No `git remote` configured: `git push` is a no-op until you add one

## Path A — GHCR via GitHub Actions (recommended, zero local setup)

```sh
# 1. Create GitHub repo + add remote
gh repo create africa-oracle-agent --public --source=. --remote=origin --push
#   (or manually: gh auth login; git remote add origin git@github.com:<you>/africa-oracle-agent.git; git push -u origin main)

# 2. Workflow runs automatically on push to main:
#    - pytest tests/ -v   (14 tests)
#    - buildx → linux/amd64,linux/arm64 → push ghcr.io/<you>/africa-oracle-agent:latest

# 3. Verify
gh run list --limit 3
docker pull ghcr.io/<you>/africa-oracle-agent:latest
docker run --rm -p 8000:8000 ghcr.io/<you>/africa-oracle-agent:latest &
curl http://localhost:8000/health
# {"status":"ok","version":"0.2.0","providers":4}
```

## Path B — Fly.io (ARM64 native, primary)

```sh
# 1. Install Fly CLI (one-time)
#    Windows:  iwr https://fly.io/install.ps1 -useb | iex
#    Linux/Mac: curl -L https://fly.io/install.sh | sh

# 2. Authenticate + launch (one-time)
fly auth login
fly launch --no-deploy --copy-config --name africa-oracle-agent
#   accept fly.toml (jnb region, shared-cpu-1x, 512mb)

# 3. Deploy
fly deploy

# 4. Verify
fly status
curl https://africa-oracle-agent.fly.dev/health
curl -X POST https://africa-oracle-agent.fly.dev/hunt \
  -H 'Content-Type: application/json' \
  -d '{"provider":"safaricom","country":"KE"}'
```

## Path C — Vercel (serverless Python ASGI)

```sh
# Either via dashboard:
#   vercel.com/import → GitHub → select africa-oracle-agent → Deploy
# Or via CLI:
npm i -g vercel
vercel --prod

# Verify
curl https://<project>.vercel.app/health
```

## Path D — Local Docker (verify Dockerfile before pushing)

```sh
# Start Docker Desktop, then:
docker build -t africa-oracle:dev .
docker run --rm -p 8000:8000 africa-oracle:dev &
curl http://localhost:8000/health

# Multi-arch verification (requires buildx + QEMU for cross-platform):
docker buildx create --use --name multi || true
docker buildx build --platform linux/amd64,linux/arm64 -t africa-oracle:v0.2.0 .
```

## Post-deploy smoke tests

```sh
URL="https://<your-deploy-url>"
curl -s "$URL/health" | jq .
curl -s "$URL/providers" | jq 'keys'
curl -s -X POST "$URL/hunt" \
  -H 'Content-Type: application/json' \
  -d '{"provider":"mtn","country":"GH"}' | jq .
curl -s -X POST "$URL/feeds/all" -H 'Content-Type: application/json' -d '{}' \
  | jq '.currencies, .agents_reporting'
```

## Rollback

- **Fly.io:** `fly releases` → `fly deploy --image registry.fly.io/africa-oracle-agent:<sha>`
- **GHCR:** `docker pull ghcr.io/<you>/africa-oracle-agent:<short-sha>` (every commit is tagged)
- **Vercel:** Promote previous deployment from the dashboard

## What's NOT deployed yet
- AFRI Jetton (`afri-token.fc`): contract scaffold has FunC syntax issues (see `EVAL_REPORT.md` P1-5/6/7) — needs rewrite against TIP-74 stdlib before `afri-deploy.sh` can compile a BoC.
- Real provider API calls: `oracle_agent._real_fetch` raises `NotImplementedError`. Needs provider API keys + KYC.
