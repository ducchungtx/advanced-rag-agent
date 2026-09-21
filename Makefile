# Advanced RAG Agent
# Usage: make help | make run | make ingest

HOST ?= 127.0.0.1
PORT ?= 8000

ifeq ($(OS),Windows_NT)
  ifneq ($(wildcard rag_env/Scripts/python.exe),)
    PYTHON ?= rag_env/Scripts/python.exe
  else ifneq ($(wildcard .venv/Scripts/python.exe),)
    PYTHON ?= .venv/Scripts/python.exe
  else
    PYTHON ?= python
  endif
else
  ifneq ($(wildcard .venv/bin/python),)
    PYTHON ?= .venv/bin/python
  else ifneq ($(wildcard rag_env/bin/python),)
    PYTHON ?= rag_env/bin/python
  else
    PYTHON ?= python3
  endif
endif

.DEFAULT_GOAL := help

.PHONY: help run ingest install docker-up docker-down

help:
	@echo.
	@echo   make run       - Chay FastAPI (uvicorn --reload)
	@echo   make ingest    - Luu vector: ingest PDF/DOCX/DOC vao Chroma
	@echo   make install   - Cai deps bang uv (sync + extra dev)
	@echo   make docker-up - docker compose up --build
	@echo   make docker-down - docker compose down
	@echo.
	@echo   Bien tuy chon: HOST=$(HOST) PORT=$(PORT) PYTHON=$(PYTHON)
	@echo.

run:
	$(PYTHON) -m uvicorn app.main:app --reload --host $(HOST) --port $(PORT)

ingest:
	$(PYTHON) -u scripts/run_ingest.py

install:
	uv sync --extra dev

docker-up:
	docker compose up --build

docker-down:
	docker compose down
