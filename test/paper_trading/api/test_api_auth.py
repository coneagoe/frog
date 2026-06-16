from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from paper_trading.api.app import create_app
from paper_trading.api.deps import get_session
from storage.model.base import Base


def test_api_requires_bearer_token(monkeypatch, tmp_path):
    monkeypatch.setenv("PAPER_TRADING_API_TOKEN", "secret")
    engine = create_engine(f"sqlite:///{tmp_path / 'auth.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    client = TestClient(app)

    unauthorized = client.get("/paper/accounts")
    authorized = client.get(
        "/paper/accounts", headers={"Authorization": "Bearer secret"}
    )

    assert unauthorized.status_code == 401
    assert authorized.status_code != 401
    session.close()
    engine.dispose()
