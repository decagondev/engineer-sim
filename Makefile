.PHONY: install setup doctor test smoke regression run
install:
	pip install -r requirements.txt

setup:
	./setup.sh

doctor:
	python doctor.py
test:
	pytest
smoke:
	pytest tests/smoke
regression:
	pytest tests/regression
run:
	LLM_PROVIDER=$${LLM_PROVIDER:-fake} uvicorn sim.app.main:app --reload
