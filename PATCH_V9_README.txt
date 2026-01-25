PATCH V9 — Build fix (Windows/Docker)
------------------------------------
This patch fixes the Docker build error:
  COPY outputs /app/outputs  -> fails when outputs/ doesn't exist or is ignored.

Changes:
1) Dockerfile: replaced 'COPY outputs /app/outputs' with 'RUN mkdir -p /app/outputs'
2) docker-compose.yml: removed obsolete 'version:' key (Compose v2 warns but still runs)
3) Added outputs/.gitkeep to ensure host directory exists (optional)

How to apply:
- Extract this zip to the ROOT of your repo folder (overwrite Dockerfile and docker-compose.yml).
- Ensure your repo root is the folder that contains apps/, config/, scripts/, Dockerfile, docker-compose.yml.

Then run:
  docker compose down
  docker compose up --build

If port 8000 is in use, stop the process or change the port mapping in docker-compose.yml.

