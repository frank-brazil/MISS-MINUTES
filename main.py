from app.api.app import app, create_app
from app.config.settings import load_config
from app.runtime.runtime import MissMinutesRuntime

if __name__ == "__main__":
    import uvicorn

    config = load_config()
    runtime = MissMinutesRuntime(config)
    app_instance = create_app(runtime=runtime)
    uvicorn.run(app_instance, host="127.0.0.1", port=8000)
