# starts the real API with a deterministic drift check for isolated bench runs

def create_app():
    # replaces only the external model call inside the bench-owned server process
    from GitHub_Connector import analysis

    if hasattr(analysis, "llm"):
        analysis.llm.check = lambda *args, **kwargs: []

    from GitHub_Connector.api import app

    return app
