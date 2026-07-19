FROM python:3.12-slim

# ffmpeg renders; fonts-dejavu-core gives drawtext a font for burned-in captions
# (the slim image ships none, so captions would silently skip without it).
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# server.py imports x402/provenance/tokengate at load — copy all runtime modules
# or the container crashes on startup with ModuleNotFoundError.
COPY pipeline.py server.py x402.py provenance.py tokengate.py ./

# Host sets PORT -> server.py runs the HTTP MCP transport on 0.0.0.0:$PORT.
ENV PORT=8000
EXPOSE 8000
CMD ["python", "server.py"]
