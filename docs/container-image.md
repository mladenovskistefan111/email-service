# Container image

Multi-stage [`Dockerfile`](https://github.com/platform-boutique/app-email-service/tree/main/Dockerfile):

| Stage | Base | What happens |
|---|---|---|
| builder | `python:3.12-alpine` | installs `g++`/`linux-headers`, `pip install -r requirements.in`, **compiles the protos** with `grpc_tools.protoc` into `generated/` and patches the relative import in `email_pb2_grpc.py` |
| runtime | `python:3.12-alpine` | copies site-packages, generated stubs (`/app/src/generated`), `src/`, `templates/`; runs as non-root |

- **Entrypoint:** `python src/server.py` (working dir `/app`; `src/` is on `sys.path`, so `from generated import …` resolves).
- **User:** `appuser` — UID `100`, GID `101` (verified). Set `runAsUser: 100` for `runAsNonRoot`.
- **EXPOSE:** `8080` only.
- **Docker `HEALTHCHECK`:** Python `grpc.channel_ready_future` against `localhost:${PORT:-8080}` (honours the default).
- **Image size:** ~41 MB.
- **Reproducibility:** the image installs from `requirements.in` (direct dependencies pinned, transitive ones floating), **not** from the fully pinned `requirements.txt`. Builds on different days can pull different transitive versions. Switch to `requirements.txt` if you need byte-for-byte repeatability.
- The generated stubs are **not** in git; they only exist after the Docker build (see local dev below).
