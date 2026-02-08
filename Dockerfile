FROM python:3.9-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN python -m pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy the script
COPY dredger.py .
COPY sites.json .

# Copy maintenance tools
COPY maintenance/ ./maintenance/

# Run the script
CMD ["python", "dredger.py"]
