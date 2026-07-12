FROM python:3.12-slim

# ffmpeg is the one non-pip dependency the render pipeline needs.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY pipeline.py server.py ./

# Host sets PORT -> server.py runs the HTTP MCP transport on 0.0.0.0:$PORT.
ENV PORT=8000
EXPOSE 8000
CMD ["python", "server.py"]
