# The Coach backend brain — container image.
#
# Runs the FastAPI app from source (not as an installed package) so the
# vendored data file backend/data/exercises.json resolves via its
# Path(__file__)-relative loader. `pip install -e .` pulls every dependency
# from pyproject.toml and puts backend/ on sys.path, keeping the source tree
# (and its data files) in place.
#
# State lives in Supabase (set SUPABASE_DB_URL), so the container is stateless
# and safe to scale to zero. Binds $PORT (Fly/Render/Cloud Run all set it).

FROM python:3.13-slim

WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip

# Copy the metadata + source needed for the editable install. Dependencies are
# resolved from pyproject.toml — no duplicated dep list to drift.
COPY pyproject.toml ./
COPY backend ./backend
RUN pip install --no-cache-dir -e .

ENV PYTHONUNBUFFERED=1 \
    PORT=8080

EXPOSE 8080

# /healthz is the unauthenticated probe (see _auth_gate). Everything else needs
# COACH_API_TOKEN, set as a platform secret — never baked into the image.
CMD ["sh", "-c", "uvicorn api.app:app --host 0.0.0.0 --port ${PORT}"]
