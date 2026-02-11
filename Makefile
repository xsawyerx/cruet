.PHONY: build dev test clean bench compare

build:
	pip install -e . --no-build-isolation

dev:
	pip install -e ".[dev]" --no-build-isolation

test:
	python -m pytest tests/ -v

clean:
	rm -rf build/ dist/ *.egg-info src/*.egg-info
	find . -name '*.so' -delete
	find . -name '*.pyc' -delete
	find . -name '__pycache__' -type d -exec rm -rf {} +

bench:
	python benchmarks/run_benchmarks.py

compare:
	bash benchmarks/run_wrk.sh
