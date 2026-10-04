FROM python:3.12-slim
RUN pip install --no-cache-dir numpy scipy && useradd -m sandbox
USER sandbox
WORKDIR /home/sandbox
