from hiagent2llm import config
from hiagent2llm.app import app

__all__ = ["app"]


def main() -> None:
    import uvicorn

    uvicorn.run(
        "hiagent2llm.app:app",
        host=config.GATEWAY_HOST,
        port=config.GATEWAY_PORT,
    )


if __name__ == "__main__":
    main()
