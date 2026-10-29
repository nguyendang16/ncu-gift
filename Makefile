.PHONY: setup api web dev test types samples reset

setup:            ## install backend (venv) and frontend dependencies
	cd backend && python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
	cd frontend && npm install

api:              ## FastAPI on http://127.0.0.1:8000  (seeds the synthetic dataset on first start)
	cd backend && ./.venv/bin/python -m app

web:              ## React on http://localhost:5173  (proxies /api to the backend)
	cd frontend && npm run dev

dev:              ## both servers; Ctrl-C stops both
	@trap 'kill 0' INT TERM; (cd backend && NCU_GIFT_RELOAD=1 ./.venv/bin/python -m app) & (cd frontend && npm run dev) & wait

test:             ## backend tests + frontend type-check
	cd backend && ./.venv/bin/python -m pytest -q tests
	cd frontend && npm run typecheck

types:            ## regenerate the TypeScript API types after changing backend/app/schemas.py
	cd backend && ./.venv/bin/python scripts/export_openapi.py
	cd frontend && npm run gen:api

samples:          ## rewrite sample_data/*.xlsx
	cd backend && ./.venv/bin/python scripts/export_samples.py

reset:            ## delete the database and uploads (the synthetic dataset is recreated on next start)
	rm -f data/ncu_gift.db* data/uploads/*.xlsx data/uploads/*.csv
