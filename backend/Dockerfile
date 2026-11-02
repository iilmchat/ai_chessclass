FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# DejaVuSans (кириллица) для PDF-отчётов родителям (S-25, порт §20.2)
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Stockfish 17.1 (ubuntu avx2) — официальный релиз; движок для chess_lab (E-04)
RUN python - <<'PYEOF'
import glob
import os
import shutil
import tarfile
import urllib.request

url = "https://github.com/official-stockfish/Stockfish/releases/download/sf_17.1/stockfish-ubuntu-x86-64-avx2.tar"
tar_path = "/tmp/sf.tar"
urllib.request.urlretrieve(url, tar_path)
os.makedirs("/tmp/sf", exist_ok=True)
with tarfile.open(tar_path) as tf:
    tf.extractall("/tmp/sf")
candidates = [
    p for p in glob.glob("/tmp/sf/**/stockfish*", recursive=True)
    if os.path.isfile(p)
]
if not candidates:
    raise SystemExit("stockfish binary not found in archive")
shutil.copy2(candidates[0], "/usr/local/bin/stockfish")
os.chmod("/usr/local/bin/stockfish", 0o755)
print("installed:", candidates[0])
PYEOF

WORKDIR /srv/backend

COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e .

COPY . .

EXPOSE 8020

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8020"]
