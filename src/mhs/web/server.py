"""Entry point: `uv run mhs` serves the app on http://127.0.0.1:3062."""

import uvicorn

from mhs.config import HOST, PORT


def main() -> None:
    uvicorn.run("mhs.web.app:create_app", factory=True, host=HOST, port=PORT)


if __name__ == "__main__":
    main()
