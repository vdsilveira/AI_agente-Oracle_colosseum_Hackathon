FROM python:3.11-slim

# Instala dependências de sistema (ffmpeg para yt-dlp, etc)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copia requirements primeiro (cache)
COPY requirements.txt .

# Instala dependências
RUN pip install --no-cache-dir -r requirements.txt

# Copia código fonte
COPY src/ ./src/
COPY *.md ./
COPY scripts/ ./scripts/

# Cria diretório para chaves (opcional)
RUN mkdir -p keys

# CMD padrão - pode ser sobrescrito
CMD ["python", "-m", "src.main"]