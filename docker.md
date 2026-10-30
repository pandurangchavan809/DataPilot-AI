# Docker for DataPilot AI (with Interview Prep)

What Docker is, why this project uses it, what every Docker file here does, the commands you'll
actually use, and interview questions with answers.

---

## 1. What Docker is, in one minute

- **Image:** a packaged, read-only snapshot of an app *plus everything it needs*: the OS libraries,
  the Python or Node runtime, dependencies and code. It's built from a `Dockerfile`.
- **Container:** a running instance of an image, isolated from your machine. You can run many
  containers from one image.
- **Dockerfile:** the recipe, a list of steps to build an image.
- **Registry:** a place to store images, such as Docker Hub or GitHub Container Registry.
- **Docker Compose:** runs **several containers together** from one YAML file (`docker-compose.yml`).

> Without Docker: "it works on my machine" (Windows, Python 3.11, my installed packages).
> With Docker: the exact same image runs identically on a laptop, a CI server, Render, AWS or
> Kubernetes.

**Container vs virtual machine:** a VM includes a whole guest operating system (GBs, slow to boot).
A container shares the host's kernel and only packages the app layer (MBs, starts in seconds).

---

## 2. Why this project uses Docker, and where

| Use | How |
|---|---|
| **Run the full production-like stack locally** | `docker compose up --build` starts nginx (frontend), gunicorn (backend) and Redis together, which is what a real deployment looks like |
| **Same environment everywhere** | The backend always runs on `python:3.11-slim`, whatever OS you develop on |
| **Deploy anywhere that runs containers** | Render (Runtime: Docker), Railway, Fly.io, AWS ECS, Google Cloud Run, Azure Container Apps, Kubernetes |
| **Try Redis without installing it** | The `redis:7-alpine` image runs in one line |

**Is Docker required?** No. On Render you can also deploy with plain Python (`pip install` +
`gunicorn`), as `deployment.md` describes, and Vercel builds the frontend itself. Docker is the
*portable* option, and the standard in most companies.

---

## 3. The Docker files in this repo

### 3.1 `Dockerfile` (repo root): the backend image

```dockerfile
FROM python:3.11-slim                      # 1. small official Python base image

ENV PYTHONDONTWRITEBYTECODE=1 \            # 2. no .pyc files
    PYTHONUNBUFFERED=1 \                   #    logs appear immediately (no buffering)
    PIP_NO_CACHE_DIR=1                     #    smaller image

WORKDIR /app                               # 3. all following commands run in /app

COPY requirements.txt .                    # 4. copy ONLY requirements first...
RUN pip install -r requirements.txt        #    ...then install (this layer is cached)

COPY . .                                   # 5. now copy the code (filtered by .dockerignore)
RUN useradd --create-home appuser && mkdir -p data auth && chown -R appuser /app
USER appuser                               # 6. do not run as root (security)

EXPOSE 5000                                # 7. documents the port
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "...urlopen('http://127.0.0.1:5000/api/health')"
CMD ["gunicorn", "-c", "gunicorn.conf.py", "wsgi:app"]   # 8. start command
```

Why each choice matters:

1. **`python:3.11-slim`:** Debian with Python and little else. It's about 5× smaller than the full
   image, which also means less to download and fewer security issues. All dependencies have
   prebuilt wheels, so no compilers are needed.
2. **`PYTHONUNBUFFERED=1`:** without it, `print` and log output can sit in a buffer, so
   `docker logs` looks empty.
3. **`WORKDIR`:** creates the folder if needed and sets the working directory.
4. **Layer caching:** each instruction creates a cached *layer*. Because `requirements.txt` is
   copied *before* the code, changing a `.py` file reuses the cached `pip install` layer, so a
   rebuild takes seconds instead of minutes.
5. **`COPY . .`** copies the project, **minus everything listed in `.dockerignore`**.
6. **A non-root user:** if the app were ever compromised, the attacker isn't root inside the
   container. `data/` and `auth/` are created and owned by this user, so the demo database and the
   user-accounts database (`auth/auth.db`) can be written.
7. **`EXPOSE`** is documentation only. Publishing a port happens with `-p` or Compose's `ports`.
8. **`HEALTHCHECK`:** Docker calls `/api/health` every 30 s and marks the container
   `healthy` or `unhealthy`. Orchestrators use this to restart broken containers.
9. **`CMD`:** gunicorn reads `gunicorn.conf.py` (threaded workers, `$PORT`, 180 s timeout) and
   serves `wsgi:app`.

### 3.2 `.dockerignore` (repo root)

Files that are **never** copied into the backend image:

```
.env  .env.*  !.env.example     ← secrets never baked into an image
data/                            ← demo.db is recreated at startup
auth/                            ← local user accounts must never end up in an image
.venv/ venv/ __pycache__/ ...    ← local environments and caches
tests/ frontend/ .git/ *.md      ← not needed at runtime; keeps the image small
```

**Why it's critical:** an image is often pushed to a registry. If `.env` were copied in, anyone
who could pull the image could read your API keys. Secrets are passed **at runtime** instead
(`--env-file` or `env_file:`).

### 3.3 `frontend/Dockerfile`: a multi-stage build

```dockerfile
# Stage 1: build (needs Node)
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund           # exact versions from the lockfile
COPY . .
ARG VITE_API_BASE_URL=                    # build-time value (empty = same-origin /api)
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build                         # outputs static files to /app/dist

# Stage 2: serve (no Node at all)
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
```

- **Multi-stage:** Node and `node_modules` (hundreds of MB) exist only in stage 1. The final image
  is just nginx plus the built HTML, CSS and JS (about 50 MB).
- **`npm ci`:** installs exactly what `package-lock.json` says. It's reproducible and faster than
  `npm install` in CI.
- **`ARG` vs `ENV`:** `ARG` exists only during the build. Vite reads `VITE_*` variables **at build
  time** and bakes them into the JavaScript, so the backend URL must be known when the image is
  built.
- `frontend/.dockerignore` excludes `node_modules`, `dist` and `.env*`.

### 3.4 `frontend/nginx.conf`

- Serves the React build from `/usr/share/nginx/html`, with gzip compression.
- **`location /api/` → `proxy_pass http://backend:5000`:** the browser calls the *same origin*
  (`:8080/api/...`) and nginx forwards the request to the backend container. Same origin means no
  CORS is needed in this setup. `backend` is the **Compose service name**, which Docker's internal
  DNS resolves.
- **`proxy_buffering off`:** essential for streaming (SSE). Otherwise nginx collects the whole
  answer before sending it.
- `/assets/` gets a 1-year cache, which is safe because Vite adds a content hash to each filename.
- `try_files $uri /index.html`: the single-page-app fallback.

> This nginx config is for the Compose setup. On Vercel, the frontend calls Render directly through
> `VITE_API_BASE_URL`, and no nginx is involved.

### 3.5 `docker-compose.yml` (repo root)

```yaml
services:
  backend:
    build: .                     # root Dockerfile
    env_file: .env               # secrets injected at runtime, not baked in
    environment:                 # these override .env for the container setup
      APP_ENV: production
      SESSION_BACKEND: redis
      REDIS_URL: redis://redis:6379/0           # "redis" = the service name below
      RATE_LIMIT_STORAGE_URI: redis://redis:6379/1
      PROXY_FIX_HOPS: "1"                       # behind nginx
      CORS_ORIGINS: http://localhost:8080
    depends_on: [redis]
    restart: unless-stopped
  frontend:
    build: ./frontend
    ports: ["8080:80"]           # host:container → open http://localhost:8080
    depends_on: [backend]
    restart: unless-stopped
  redis:
    image: redis:7-alpine
    command: ["redis-server", "--save", "", "--appendonly", "no"]   # in-memory only
    restart: unless-stopped
```

- Compose creates a **private network**. Containers reach each other by service name
  (`backend`, `redis`).
- **Only the frontend publishes a port** (8080). The backend and Redis aren't reachable from
  outside, which is a smaller attack surface.
- `depends_on` controls start order (it doesn't wait for readiness).
- `restart: unless-stopped` brings containers back after a crash or reboot.
- Redis persistence is off, because sessions are short-lived by design.

---

## 4. How to use it (step by step)

**Install:** Docker Desktop for Windows (it uses WSL 2). Check that it works:

```bash
docker --version
docker compose version
```

**Run the whole stack:**

```bash
cp .env.example .env              # once; fill in API keys and SECRET_KEY
docker compose up --build         # build the images and start everything
# open http://localhost:8080
```

**Run in the background, watch logs, stop:**

```bash
docker compose up -d --build      # -d = detached (background)
docker compose ps                 # what's running, and health status
docker compose logs -f backend    # follow backend logs (Ctrl+C stops following)
docker compose down               # stop and remove the containers and network
```

**Backend only, without Compose:**

```bash
docker build -t datapilot-api .                         # build the image, tag it datapilot-api
docker run --rm -p 5000:5000 --env-file .env datapilot-api
# http://localhost:5000/api/health
```

**After changing code:** `docker compose up -d --build` rebuilds only what changed.

---

## 5. Command cheat sheet

### Images

| Command | What it does |
|---|---|
| `docker build -t name:tag .` | Build an image from the Dockerfile in `.` |
| `docker build --no-cache -t name .` | Rebuild without the layer cache |
| `docker build --build-arg VITE_API_BASE_URL=https://api.x.com -t web ./frontend` | Pass a build-time `ARG` |
| `docker images` | List local images |
| `docker rmi name` | Delete an image |
| `docker pull redis:7-alpine` | Download an image |
| `docker tag name user/name:1.0` + `docker push user/name:1.0` | Publish to a registry |
| `docker history name` | Show the image's layers and their sizes |

### Containers

| Command | What it does |
|---|---|
| `docker run -d --name api -p 5000:5000 --env-file .env datapilot-api` | Start a container in the background |
| `docker run --rm -it python:3.11-slim bash` | A throwaway interactive container |
| `docker ps` / `docker ps -a` | Running containers / all, including stopped |
| `docker logs -f api` | Follow a container's logs |
| `docker exec -it api sh` | Open a shell inside a running container |
| `docker stop api` / `docker start api` / `docker restart api` | Lifecycle |
| `docker rm api` (`-f` forces it) | Delete a container |
| `docker inspect api` | Full details: IP, environment, mounts, health |
| `docker stats` | Live CPU and memory per container |
| `docker cp api:/app/data/demo.db .` | Copy a file out of a container |

### Compose

| Command | What it does |
|---|---|
| `docker compose up --build` | Build and start everything (shows logs) |
| `docker compose up -d` | Start in the background |
| `docker compose ps` | Service status |
| `docker compose logs -f backend` | One service's logs |
| `docker compose exec backend sh` | Shell into a service |
| `docker compose exec redis redis-cli keys '*'` | Look at the session keys in Redis |
| `docker compose restart backend` | Restart one service |
| `docker compose down` | Stop and remove (`-v` also removes volumes) |
| `docker compose config` | Show the final merged config (good for debugging) |

### Clean up

| Command | What it does |
|---|---|
| `docker system df` | Disk used by Docker |
| `docker image prune` | Remove dangling images |
| `docker system prune -a` | Remove **everything** unused (careful) |

**Flags to remember:**
- `-d` runs detached (in the background).
- `-p host:container` publishes a port.
- `--env-file` passes environment variables.
- `--rm` deletes the container when it exits.
- `-it` gives an interactive terminal.
- `-t` tags the image when building.
- `-f` follows logs, or forces removal.

---

## 6. Troubleshooting

| Problem | Cause / fix |
|---|---|
| `port is already allocated` | Something else uses 8080 or 5000. Stop it, or change `ports: ["8081:80"]`. |
| Backend `unhealthy` | `docker compose logs backend`. Usually a missing API key or `SECRET_KEY` in `.env`. |
| Frontend shows "unavailable" | Backend not up yet or crashed. Run `docker compose ps` and check the logs. |
| Code change not visible | You didn't rebuild. Run `docker compose up -d --build`. |
| Answers arrive all at once | A proxy is buffering. Check that `proxy_buffering off` is in the nginx config. |
| `.env` change ignored | Run `docker compose up -d` again. It recreates containers whose environment changed. |
| Docker Desktop won't start on Windows | Enable WSL 2 and virtualization in the BIOS |

---

> **User accounts in Docker:** `auth/auth.db` lives inside the container, so `docker compose down`
> followed by a rebuild loses the accounts (the demo user is recreated on start). To keep them, mount a
> volume, e.g. `volumes: ["auth-data:/app/auth"]` on the backend service.

## 7. Interview questions and answers

**Q1. What is Docker and why did you use it?**
> Docker packages an application with its runtime and dependencies into an image that runs the
> same everywhere. I used it so the backend always runs on the same Python 3.11 environment, and
> so the full stack (nginx, Flask with gunicorn, and Redis) starts with one command, the same way it
> would in production.

**Q2. Image vs container?**
> An image is the read-only template, like a class. A container is a running instance of it, like
> an object. One image can run many containers.

**Q3. Docker vs virtual machine?**
> A VM virtualizes the hardware and runs a full guest OS. Containers share the host kernel and
> isolate processes, so they're far lighter: MBs instead of GBs, and they start in seconds.

**Q4. Explain your backend Dockerfile.**
> It starts from `python:3.11-slim` and copies `requirements.txt` first so the dependency layer is
> cached, then copies the code. It runs as a non-root user, defines a health check on
> `/api/health`, and starts gunicorn with threaded workers, which suit the long-lived streaming
> responses.

**Q5. Why copy `requirements.txt` before the rest of the code?**
> Layer caching. Docker reuses a layer if its inputs haven't changed. Dependencies change rarely
> and code changes often, so this order means most rebuilds skip `pip install`.

**Q6. What is a multi-stage build? Where did you use it?**
> Several `FROM` stages in one Dockerfile. Later stages copy only what they need from earlier ones.
> My frontend builds with Node in stage 1 and copies only the static `dist/` output into an nginx
> image, so the final image has no Node and no `node_modules`.

**Q7. How do you handle secrets with Docker?**
> Never in the image. `.env` is in `.dockerignore`, and secrets are injected at runtime with
> `env_file` / `--env-file` or the platform's secret manager. Anything baked into an image can be
> read by whoever pulls it.

**Q8. `CMD` vs `ENTRYPOINT`? `RUN` vs `CMD`?**
> `RUN` executes at **build** time and creates a layer (e.g. `pip install`). `CMD` is the default
> command at **run** time, and arguments to `docker run` can override it. `ENTRYPOINT` fixes the
> executable, and `CMD` then supplies default arguments to it.

**Q9. `ARG` vs `ENV`?**
> `ARG` exists only during the build. `ENV` is set in the image and present at runtime. I use
> `ARG VITE_API_BASE_URL` because Vite bakes it into the JavaScript at build time.

**Q10. `EXPOSE` vs `-p`?**
> `EXPOSE` only documents the port. `-p 8080:80` (or Compose `ports`) actually publishes a
> container port on the host.

**Q11. How do containers talk to each other in Compose?**
> Compose creates a network with built-in DNS, so services reach each other by service name. My
> nginx proxies to `http://backend:5000`, and the backend uses `redis://redis:6379`.

**Q12. Why is only the frontend port published?**
> The browser only needs nginx. The backend and Redis stay on the private network, so they can't be
> reached directly from outside. That's a smaller attack surface.

**Q13. Why Redis in the Compose setup?**
> gunicorn runs several worker processes, and in-memory state isn't shared between them. Redis
> stores the encrypted session data and rate-limit counters, so any worker can serve any request.

**Q14. Why gunicorn and not `python wsgi.py` in the container?**
> Flask's built-in server is for development: one process, not hardened. gunicorn is a production
> WSGI server with multiple workers, timeouts and graceful restarts.

**Q15. Why run as a non-root user?**
> Least privilege. If the app is compromised, the attacker doesn't get root inside the container,
> which limits the damage.

**Q16. What does `HEALTHCHECK` do?**
> Docker runs the command periodically and marks the container healthy or unhealthy. Orchestrators
> and load balancers use that to restart containers or stop routing to them.

**Q17. Why `python:3.11-slim` and not `alpine` for Python?**
> Alpine uses musl instead of glibc, so many Python wheels aren't prebuilt for it and must be
> compiled. That gives slower builds and sometimes subtle bugs. `slim` stays small and stays
> compatible.

**Q18. How would you deploy these images to production?**
> Build the images in CI, push them to a registry with a version tag, then deploy to a container
> platform (Render, ECS, Cloud Run or Kubernetes) with a managed Redis and secrets from the
> platform's secret store. Then scale backend replicas horizontally.

**Q19. What is `.dockerignore` for?**
> It keeps files out of the build context: secrets (`.env`), virtual environments, `.git`, tests and
> local data. Builds are faster, images smaller, and nothing sensitive leaks into an image.

**Q20. Volumes: did you need one?**
> Not here. The demo database is regenerated at startup, user databases are external, and Redis is
> intentionally non-persistent. If I needed persistent data, for example uploaded CSVs in v2, I'd
> mount a named volume or use object storage.
