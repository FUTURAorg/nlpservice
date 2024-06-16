from python:3.10

WORKDIR /app

COPY requirements.txt .

RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cu118

COPY model.py model.py
COPY server.py server.py
COPY server.py server.py
