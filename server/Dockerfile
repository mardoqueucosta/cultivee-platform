FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p data
EXPOSE ${PORT:-5002}
CMD gunicorn -b 0.0.0.0:${PORT:-5002} -w 2 --threads 4 app:app
