# Deployment handoff

The current authorized release stays local. No hosting account, API key or paid service is needed to run it with Ollama. Public deployment has not been performed.

## Prepared deployment

Dockerfile builds the React frontend, installs the Python service and runs as a non-root user. `deploy/render.yaml` is an example Render Blueprint; copy it to the repository root as `render.yaml` when deploying this project as its own repository. A persistent disk is specified because workspaces/history are file-backed. Select and review the hosting plan before creating resources; no paid resources have been created here.

Required hosting settings:

- Exact `QUERYCRAFT_ALLOWED_HOSTS` hostname and `QUERYCRAFT_ALLOWED_ORIGINS` HTTPS origin.
- `QUERYCRAFT_ACCESS_USER` and a long unique `QUERYCRAFT_ACCESS_PASSWORD`, supplied through the host's secret manager.
- `QUERYCRAFT_SECURE_COOKIE=1`; terminate HTTPS at the host.
- `QUERYCRAFT_DATA=/app/data` on a persistent volume.
- One application worker. Multiple workers require external database/file coordination.
- `QUERYCRAFT_PROVIDER=openai`, an explicitly selected compatible `OPENAI_MODEL`, and server-only `OPENAI_API_KEY` for the prepared Responses API adapter; or an authenticated reachable self-hosted Ollama server that supports structured outputs. The user's localhost Ollama is not reachable from the hosting container.

`/api/live` is the unauthenticated liveness endpoint. All application routes require Basic authentication when a password is set; a non-local hostname without configured authentication is rejected. This is a private demonstration gate, not a multi-user identity system. Workspaces remain separate, high-entropy cookie identities.

## Verification status

- Local production frontend build: verified.
- Local API and workflow checks: verified; see evidence/VERIFICATION.md.
- Provider adapter request/refusal/configuration checks: verified with mocked HTTP responses.
- Real OpenAI inference: **not tested**; no key supplied and no API expenditure incurred.
- Docker image: build definition prepared; **not built locally** because no Docker daemon is installed.
- Render deployment: **not attempted**; no account configured, and the user requested local mode for this release.

## After hosting is configured

Build the image, start it with the chosen configuration, check /api/live, verify unauthenticated application requests get 401, authenticate and run a simple query, import a synthetic CSV, restart the service and verify persistence. Run the entire benchmark on the deployed model; local-model figures do not transfer. Then test host/origin restrictions and the selected upload/workspace limits before sharing the demo link.

Official references: [Render FastAPI deployment](https://render.com/docs/deploy-fastapi), [persistent disks](https://render.com/docs/disks), [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses). Ollama's own cloud currently lacks structured outputs, so do not assume its cloud endpoint is a drop-in replacement for this schema-constrained local API.
