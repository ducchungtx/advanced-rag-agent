FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install uv
RUN uv pip install --system langchain langchain-google-genai chromadb pypdf fastapi uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
