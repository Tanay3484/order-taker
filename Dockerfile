# One container for the Hugging Face Space: Ollama + the Order Taker app.

# Ollama, pinned to the version the app was tested with
FROM ollama/ollama:0.35.1 AS ollama

# Python base instead of plain Ubuntu (matches CI's 3.11)
FROM python:3.11-slim

# Hugging Face runs the container as uid 1000, so create that user (as root)
RUN useradd -m -u 1000 user

# Copy the Ollama binary and its libraries from the official image
COPY --from=ollama /usr/bin/ollama /usr/bin/ollama
COPY --from=ollama /usr/lib/ollama /usr/lib/ollama

# Python deps first, so code changes don't reinstall everything
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Switch to the HF user only after the root-only steps are done
USER user
ENV HOME=/home/user \
    OLLAMA_MODELS=/home/user/.ollama/models \
    OLLAMA_HOST=127.0.0.1:11434 \
    OLLAMA_NUM_PARALLEL=1 \
    ORDER_DB=/home/user/data/order_taker.db \
    ORDER_PORT=7860 \
    ORDER_MODEL=qwen2.5:3b \
    ORDER_SORTER_MODEL=qwen2.5:3b \
    OLLAMA_URL=http://127.0.0.1:11434 \
    ORDER_PARALLEL=1 \
    PYTHONUNBUFFERED=1

# Bake the model into the image so restarts don't download 2 GB.
# Wait until Ollama actually answers instead of guessing with sleep.
RUN mkdir -p /home/user/data \
    && (ollama serve > /tmp/ollama.log 2>&1 &) \
    && for i in $(seq 1 60); do ollama list > /dev/null 2>&1 && break; sleep 1; done \
    && ollama pull qwen2.5:3b

# App code last: it changes most often, so it shouldn't invalidate the layers above
WORKDIR /home/user/app
COPY --chown=user:user . .

EXPOSE 7860

# Start Ollama in the background, then the app in the foreground.
# The app copes with Ollama still loading (it shows "AI helper isn't running" until ready).
CMD ["sh", "-c", "ollama serve & exec python app.py"]
