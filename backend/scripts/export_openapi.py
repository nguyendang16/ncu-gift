"""Write the API contract to frontend/openapi.json; `npm run gen:api` turns it into TypeScript types."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import app  # noqa: E402

out = Path(__file__).resolve().parents[2] / "frontend" / "openapi.json"
out.write_text(json.dumps(app.openapi(), indent=2))
print("wrote", out)
