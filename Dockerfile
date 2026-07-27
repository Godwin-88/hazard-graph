FROM python:3.11-slim

WORKDIR /app

# System deps for rasterio + numpy + PyTorch CPU
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ gdal-bin libgdal-dev libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# GDAL env for rasterio
ENV CPLUS_INCLUDE_PATH=/usr/include/gdal
ENV C_INCLUDE_PATH=/usr/include/gdal

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create model storage directory
RUN mkdir -p models/saved

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]