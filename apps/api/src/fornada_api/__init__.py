def main() -> None:
    """Serve the API without auto-reload (`fastapi dev` is for development)."""
    import uvicorn

    uvicorn.run("fornada_api.main:app")
