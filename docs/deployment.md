# Deployment

Operational detail for the Docker image, the Compose services and the target VPS. Stable design and data model: `docs/architecture.md`. Current commands and environment variables: `README.md`. The folder `deploy/` holds only the configuration files; this document explains them.

The deployment path is locked as Path A: Cloudflare at the edge, Python at the origin (see `docs/roadmap.md`). A single Debian host (EU provider chosen by the user; not yet provisioned) runs Docker Compose: `offerte-mcp` is long-running, `offerte-etl` is a one-shot batch job launched by an external systemd timer, and `cloudflared` is the only public ingress. The MCP service is intentionally unauthenticated; Cloudflare provides the public edge and per-IP rate limiting. Agents have no shell, filesystem, database or CLI access: MCP is the only agent-facing interface. Kubernetes, MySQL/PostgreSQL, Parquet, Redis and message queues are intentionally deferred. Cloudflare Workers/D1/Durable Objects/R2 are not used as runtime or database (see `docs/architecture.md` §11).

Two ingress phases: **debugging** (Objectives 1–2 in the roadmap) uses a temporary Tunnel with the Cloudflare default URL (`*.trycloudflare.com`) — no own domain is configured yet, and the endpoint is for debugging only, never for third-party traffic. **Production** (Objective 3) adds an own domain, a named Tunnel and edge rate limiting.

## Runtime layout

```text
/var/lib/offerte/db/offerte.db
/var/lib/offerte/db/offerte.db.new
/var/lib/offerte/db/offerte.db.prev
/var/lib/offerte/raw/YYYY-MM-DD/
/var/lib/offerte/db/etl.lock
```

`offerte.db`, `.new` and `.prev` stay in the same directory and on the same volume: the ETL completes validation and then uses the atomic rename. The database and the raw files are separate directories. The ETL service mounts both read-write; the MCP service mounts only the database read-only and does not mount the raw directory. There is no auth volume: the deployment uses no application credentials or sessions.

Paths and the HTTP bind are configurable without code changes; the environment variables are listed in `README.md`. A command-line option takes precedence over its environment variable. The `offerte-etl` user owns the database and raw directories; `offerte-mcp` belongs to the shared read group of the database. The effective protection of the MCP read-only mount is the responsibility of the Docker/systemd configuration, in addition to `mode=ro` and `PRAGMA query_only=ON` in the code. No credentials file is planned for MCP.

## Docker image

`Dockerfile` builds one multi-stage image: the build stage creates the Python environment from `uv.lock` (`--locked --no-dev`), while the runtime stage contains only the virtual environment, the `etl` and `offerte` packages, and the runtime directories. Base Python and uv images are pinned by digest; the image includes no tests, raw files, local databases or development tools, and starts as the non-root `offerte-mcp` user.

The entrypoint is `python` with default `-m offerte.mcp`; the batch job selects the same artifact with `-m etl scarica`, and the Docker configuration selects `offerte-etl` without duplicating the image. Read-only filesystem, `no-new-privileges`, dropped capabilities and the `tmpfs` for `/tmp` are applied by the Docker services, not implicitly by the application process. Build from the repository root:

```bash
docker build --tag offerte:local .
```

The same image selects the ETL module by replacing the command and, for a batch run, the user:

```bash
docker run --rm \
  --read-only --tmpfs /tmp \
  --security-opt no-new-privileges --cap-drop ALL \
  --user offerte-mcp \
  -e OFFERTE_DB=/var/lib/offerte/db/offerte.db \
  -v "$PWD/build:/var/lib/offerte/db:ro" \
  offerte:local -m offerte.mcp

docker run --rm --user offerte-etl \
  --security-opt no-new-privileges --cap-drop ALL \
  -v offerte-db:/var/lib/offerte/db \
  -v offerte-raw:/var/lib/offerte/raw \
  -v "$PWD/docs:/var/lib/offerte/parametri:ro" \
  offerte:local -m etl scarica \
  --db /var/lib/offerte/db/offerte.db \
  --raw-dir /var/lib/offerte/raw \
  --parametri /var/lib/offerte/parametri/PO_Parametri_Mercato_Libero_E_20261014.csv
```

The MCP container must keep its database mount read-only and must not be given a raw mount.

## Docker Compose services

`compose.yml` runs both processes from that image:

- `offerte-mcp` is long-running, runs as the non-root `offerte-mcp` user, mounts the database read-only, has a read-only root filesystem with a `tmpfs` for `/tmp`, drops all capabilities, and publishes the MCP port only on the host loopback (`127.0.0.1:${OFFERTE_MCP_PORT:-8000}:8000`). It does not mount the raw directory. Inside the container it listens on `0.0.0.0`, because only then does the published port reach the process: the non-loopback bind is made explicit by `OFFERTE_MCP_CONSENTI_NON_LOOPBACK`, never implicit. A healthcheck runs `python -m offerte.mcp --verifica`.
- `offerte-etl` is a batch job under the `etl` profile, runs as `offerte-etl`, mounts the database and the dated raw directory read-write, uses `restart: "no"` and exits when the ETL finishes. It is never started by `docker compose up` and is not started by MCP.

The database volume holds `offerte.db`, its `.new` and `.prev` snapshots, and the `etl.lock` file. The parameter CSV is mounted (not baked into the image): for v1 the current snapshot (`OFFERTE_PARAMETRI_NOME`, default `PO_Parametri_Mercato_Libero_E_20261014.csv`) is updated **manually** by replacing the file on the host. Its filename must keep the `PO_Parametri_..._AAAAMMGG.csv` form because the date is read from it. Automatic parameter download replaces the manual step in the production objective; until then, a stale snapshot is a known, documented limitation, not a silent failure.

Copy `.env.example` to `.env` to override the port and the parameter CSV location, then build and start MCP (the database volume must already contain a database produced by the ETL):

```bash
cp .env.example .env
docker compose build
docker compose up -d offerte-mcp
```

Run the ETL manually:

```bash
docker compose --profile etl run --rm offerte-etl
```

## ETL lock and readiness

Two overlapping ETLs must never read and replace the same database. The lock is an `etl.lock` file in the database directory (exclusive non-blocking `flock`), acquired before reading and before the swap: it lives on the same persistent volume, is shared between containers and is released even on error or termination. If it is already held, the ETL exits with code 3 and a structured `etl_in_corso` error, without touching the database.

MCP readiness is `python -m offerte.mcp --verifica`: exit 0 if the database is readable read-only, 1 if missing, 2 if unreadable. It never creates an empty database: an uninitialized volume stays a controlled error, not a silently empty database.

## Target host and Cloudflare

- A Linux VM (stable Debian) in an EU provider chosen by the user. Automatic security updates, key-based SSH. Kubernetes and other orchestrators are not part of the first phase. The host is not yet provisioned; Objective 2 in `docs/roadmap.md` covers its bootstrap.
- **Cloudflare in front as a proxy**: DDoS, WAF and per-IP rate limiting. The origin must not be directly reachable (otherwise the protection is bypassed). **Cloudflare Tunnel only** (`cloudflared`): the host opens outbound connections only, no public port, and the MCP server listens on `127.0.0.1` in plain HTTP. No local reverse proxy (Caddy) and no public 443.
  - Note: MCP calls (dynamic JSON-RPC POSTs) need no caching; Cloudflare's value is in DDoS and abuse mitigation.
- **Debugging phase (no own domain yet):** a temporary Tunnel (`cloudflared tunnel --url http://127.0.0.1:8000`) with the auto-generated `*.trycloudflare.com` URL. Public and unauthenticated: debugging only, closed when not in use, never for third-party traffic. No `cloudflared` Compose service is needed in this phase; it is run ad hoc on the host.
- **Production phase (own domain):** a named Tunnel, preferably as a Compose service, with a DNS record (`mcp.<domain>`) and per-IP rate limiting on `/mcp` at the edge. This is Objective 3 in the roadmap; do not add it before the debugging deployment works.
- Separate system users: `offerte-etl` (writes in `/var/lib/offerte`) and `offerte-mcp` (reads the DB). systemd units with hardening: `NoNewPrivileges`, `ProtectSystem=strict`, `ProtectHome`, `PrivateTmp`, minimal `ReadWritePaths`, `MemoryMax`.
- VPS persistence: prefer explicit host directories (`/var/lib/offerte/db`, `/var/lib/offerte/raw`) over opaque Docker volumes, to simplify backup and restore. In both cases the active DB, `.new`, `.prev` and the lock must stay on the same filesystem.
- Backup: the DB is rebuildable; save at least the configuration and the active/previous database. Raw files are not kept as a functional requirement.
- `/healthz` is an HTTP route with no authentication and no application data: it returns 200 only when the DB is readable, otherwise 503; it serves Docker, systemd and future managed providers.

## Local / debugging trial with an LLM

After loading a valid DB, start the service with the local Compose override (locally, or on the target host for Objective 2):

```bash
docker compose -f compose.yml -f deploy/compose.local.yml run --build --rm offerte-etl
docker compose -f compose.yml -f deploy/compose.local.yml up --build -d offerte-mcp
curl -fsS http://127.0.0.1:8000/healthz
```

For a remote LLM, use a temporary Tunnel only for the trial:

```bash
cloudflared tunnel --url http://127.0.0.1:8000
```

Configure the MCP client with the URL returned by `cloudflared` plus the `/mcp` suffix, for example `https://<temporary-name>.trycloudflare.com/mcp`. Do not publish the MCP port directly on the Internet and do not set the application's non-loopback bind for this trial. The temporary Tunnel is public and unauthenticated: close it at the end of the trial and do not use it for third-party traffic.

The `compose.local.yml` override bind-mounts `build/`, needs no network downloads, runs as the host UID/GID (set `OFFERTE_LOCAL_UID` and `OFFERTE_LOCAL_GID` if yours differ from `1000`) and adds `:z` to the bind mounts for SELinux hosts.

## Future Manufact Cloud compatibility

Manufact is not the initial deployment (Path A is locked; see the roadmap). This section is retained only as a portability note. The repository remains suitable for a future migration because the provider can use the committed `Dockerfile` or the Python runtime and configure the start command, port and per-environment variables. There, too, the service stays public and without application authentication; rate limiting is configured at the provider gateway.

The future configuration must start HTTP, not stdio:

```text
python -m offerte.mcp --trasporto http
OFFERTE_MCP_HOST=0.0.0.0
OFFERTE_MCP_PORT=3000
OFFERTE_MCP_CONSENTI_NON_LOOPBACK=1
```

A Manufact deployment cannot assume that `/var/lib/offerte/db` or `/raw` are persistent. Before using it, an adapter is needed that publishes a validated SQLite artifact to shared storage and downloads it into the MCP server's temporary filesystem. Previews must use data and secrets separate from production. The code boundaries that keep this migration possible:

- the application logic (`offerte.ricerca`, future `calc`) receives a SQLite connection and knows nothing about filesystem, Docker, Cloudflare or the provider;
- `offerte.mcp` stays a thin MCP adapter; the HTTP endpoint is `/mcp`, while unauthenticated `/healthz` exposes readiness only;
- the HTTP process listens on `0.0.0.0` only when the deployment requires it and uses `OFFERTE_MCP_PORT`, falling back to the conventional `PORT` variable;
- no important data is kept in the local filesystem of the MCP process: on a platform without persistent storage the future DB will be an immutable SQLite artifact in Object Storage, downloaded to `/tmp` and opened read-only;
- the DB source is isolated behind a future boundary (`local path` on the VPS, `object artifact` in serverless) without duplicating queries or calculations;
- per-IP rate limiting must stay at the gateway; local application state cannot be used as a global limit if there are multiple instances;
- the process must shut down cleanly on `SIGINT`: MCP clients must be able to reconnect if a platform replaces a deployment.

Manufact Cloud documents GitHub deployment with the Python runtime or a custom `Dockerfile`, start command, port and per-environment variables; the current `Dockerfile` is therefore a compatible base, but production configuration will have to select the HTTP transport explicitly. The `stdio` mode stays the default for local clients and does not need to be replaced. Manufact previews must use a non-production DB; variables and secrets are configured on the platform, never committed to the repository. Automatic deploys are subordinate to `just check` and an MCP smoke test. Before migrating, the Streamable HTTP transport with MCP sessions and a possible controlled interruption of streams during a deploy must also be validated; the Manufact documentation indicates a 300-second maximum shutdown window and requires clients to reconnect.

Official sources consulted:

- [Manufact Cloud quickstart](https://docs.manufact.com/dashboard/quickstart)
- [Manufact build and deployment](https://docs.manufact.com/dashboard/deployments)
- [Manufact environment variables](https://docs.manufact.com/dashboard/environment-variables)
- [Manufact server settings](https://docs.manufact.com/dashboard/settings)
- [MCP Python SDK: deploy and scale](https://py.sdk.modelcontextprotocol.io/run/deploy/)
- [MCP Python SDK: custom health route](https://py.sdk.modelcontextprotocol.io/run/asgi/)

This compatibility is a future design constraint, not an active Manufact deployment. The Object Storage adapter and any shared key management will be separate tasks when the migration is actually useful.
