"""Run the API with the host and port configured in .env."""
from .config import api_binding


def main():
    import uvicorn
    host, port = api_binding()
    uvicorn.run('app.platform.application:app', host=host, port=port)


if __name__ == '__main__':
    main()
