FROM node:22-bookworm-slim AS frontend
WORKDIR /app/web
COPY web/package.json web/pnpm-lock.yaml ./
RUN corepack enable && corepack prepare pnpm@11.25.0 --activate && pnpm install --frozen-lockfile --ignore-scripts
COPY web/ ./
RUN pnpm build

FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home app
COPY *.py ./
COPY evidence/ ./evidence/
COPY --from=frontend /app/web/dist ./web/dist
RUN mkdir /app/data && chown -R app:app /app
USER app
ENV QUERYCRAFT_DATA=/app/data
EXPOSE 8040
CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8040"]
