import os

import uvicorn

if __name__ == "__main__":
    # `make dev` sets NCU_GIFT_RELOAD=1 so the API restarts by itself when the code changes (a server left running on old code
    # looks like missing features in the new interface).
    reload = os.environ.get("NCU_GIFT_RELOAD") == "1"
    uvicorn.run("app.main:app", host="127.0.0.1", port=int(os.environ.get("PORT", 8000)), reload=reload, reload_dirs=["app"] if reload else None)
