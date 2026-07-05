FROM python:3.12-slim
WORKDIR /app
# webhook.py is dependency-free (stdlib only). It imports payment.py from scripts/.
COPY scripts/ ./scripts/
COPY data/ ./data/
ENV PORT=8787
EXPOSE 8787
# Render/Railway/Fly inject PORT; webhook.py binds 0.0.0.0:$PORT.
CMD ["python", "scripts/webhook.py"]
