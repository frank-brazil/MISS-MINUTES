from app.api.app import app, create_app
from app.core.ai import AIModel
from app.providers.openai_provider import OpenAIProvider

if __name__ == "__main__":
    import uvicorn

    configured: AIModel = OpenAIProvider()
    uvicorn.run(create_app(ai_model=configured), host="127.0.0.1", port=8000)