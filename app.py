import os
import threading
import webbrowser

import uvicorn

from backend.api import app


HOST = os.getenv("APP_HOST", "127.0.0.1")
PORT = int(os.getenv("APP_PORT", "8000"))
AUTO_OPEN_BROWSER = os.getenv("AUTO_OPEN_BROWSER", "1") == "1"


def main() -> None:
    if AUTO_OPEN_BROWSER:
        threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()
    uvicorn.run(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()
