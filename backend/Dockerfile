FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# DejaVuSans (кириллица) для PDF-отчётов родителям (S-25, порт §20.2)
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Stockfish 17.1 (ubuntu avx2) — официальный релиз; движок для chess_lab (E-04).
# S-62 (supply chain, A08): SHA256 архива зафиксирован; несовпадение ломает
# build (обновление версии — только вместе с новым hash после проверки).
ARG STOCKFISH_SHA256=09e953222dbe80aaea5c33dab265413b295cb8376418445c877708c61e31987d
RUN python - <<'PYEOF'
import glob
import hashlib
import os
import shutil
import sys
import tarfile
import urllib.request

url = "https://github.com/official-stockfish/Stockfish/releases/download/sf_17.1/stockfish-ubuntu-x86-64-avx2.tar"
expected = os.environ["STOCKFISH_SHA256"].strip()
tar_path = "/tmp/sf.tar"
urllib.request.urlretrieve(url, tar_path)
digest = hashlib.sha256(open(tar_path, "rb").read()).hexdigest()
if digest != expected:
    # S-62: hash-mismatch = build падает (архив подменён/перезалит).
    sys.exit(f"stockfish archive hash mismatch: {digest} != {expected}")
os.makedirs("/tmp/sf", exist_ok=True)
with tarfile.open(tar_path) as tf:
    tf.extractall("/tmp/sf")
candidates = [
    p for p in glob.glob("/tmp/sf/**/stockfish*", recursive=True)
    if os.path.isfile(p)
]
if not candidates:
    raise SystemExit("stockfish binary not found in archive")
result = shutil.copy2(candidates[0], "/usr/local/bin/stockfish")
os.chmod("/usr/local/bin/stockfish", 0o755)
print("installed:", result, "sha256 OK")
PYEOF

WORKDIR /srv/backend

# S-62: зависимости — ТОЛЬКО из hash-locked requirements.lock (сгенерирован
# `pip-compile --generate-hashes` от pyproject.toml; обновления — через
# перегенерацию lock, RULES §6); сам проект — поверх `--no-deps`, иначе pip
# снова резолвит из PyPI. Требование lock без hash ломает этот build.
COPY requirements.lock pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --require-hashes -r requirements.lock \
    && pip install --no-cache-dir --no-deps -e .

COPY . .

# S-93: worker/api не работают от root. Каталоги volume'ов создаются заранее,
# чтобы Docker унаследовал owner при первом монтировании named volume.
RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /srv/reports /srv/archive /srv/voice_cache /srv/jwt \
    && chown -R appuser:appuser /srv/reports /srv/archive /srv/voice_cache /srv/jwt
ENV PATH="/home/appuser/.local/bin:${PATH}"
USER appuser

EXPOSE 8020

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8020"]
