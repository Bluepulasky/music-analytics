FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py index.html requirements.txt logo_copia.png logo_copia_apple.png ./

EXPOSE 8087

CMD ["python", "app.py"]