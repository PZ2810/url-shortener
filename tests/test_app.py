import os
import sys
from unittest.mock import MagicMock

# Add app directory to sys.path so app modules can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app")))

import pytest
from app import app, base62_encode, base62_decode, is_valid_url


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture(autouse=True)
def mock_redis_default(monkeypatch):
    """Mock Redis cache methods by default so tests run fast without live Redis."""
    monkeypatch.setattr("app.cache.get", lambda key: None)
    monkeypatch.setattr("app.cache.set", MagicMock())
    
    mock_pipe = MagicMock()
    monkeypatch.setattr("app.cache.pipeline", lambda: mock_pipe)


# ==========================================
# 1. Base62 Algorithm Tests
# ==========================================
def test_base62_encode_decode():
    """Verify that encoding then decoding returns the original ID."""
    test_ids = [0, 1, 61, 62, 125, 9999, 123456789]
    for num in test_ids:
        encoded = base62_encode(num)
        assert isinstance(encoded, str)
        assert len(encoded) > 0
        decoded = base62_decode(encoded)
        assert decoded == num


def test_base62_zero():
    """Verify 0 maps to '0'."""
    assert base62_encode(0) == "0"
    assert base62_decode("0") == 0


def test_base62_collision_free():
    """Verify different IDs yield different short codes."""
    codes = {base62_encode(i) for i in range(1, 1000)}
    assert len(codes) == 999


# ==========================================
# 2. Input Validation Tests
# ==========================================
def test_is_valid_url_success():
    """Valid URLs should return True."""
    valid_urls = [
        "https://www.google.com",
        "http://github.com/user/repo",
        "https://sub.domain.co.uk/path?query=1&var=abc#section",
        "http://localhost:5000/test",
    ]
    for url in valid_urls:
        assert is_valid_url(url) is True


def test_is_valid_url_rejections():
    """Invalid URLs should return False."""
    invalid_urls = [
        "not-a-url",
        "hello world",
        "javascript:alert(1)",
        "ftp://files.example.com",
        "",
        "   ",
        None,
        12345,
        "https://" + "a" * 2050,  # Exceeds 2048 chars
    ]
    for url in invalid_urls:
        assert is_valid_url(url) is False


# ==========================================
# 3. API Endpoint Tests
# ==========================================
def test_health_check(client):
    """GET /health should return 200 and healthy status."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "healthy"}


def test_shorten_missing_data(client):
    """POST /shorten without body or 'url' key returns 400."""
    res1 = client.post("/shorten", json={})
    assert res1.status_code == 400

    res2 = client.post("/shorten", json={"wrong_key": "https://google.com"})
    assert res2.status_code == 400


def test_shorten_invalid_url(client):
    """POST /shorten with an invalid URL returns 400."""
    response = client.post("/shorten", json={"url": "not-a-valid-url"})
    assert response.status_code == 400
    assert "Invalid URL" in response.get_json()["error"]


def test_shorten_success(client, monkeypatch):
    """POST /shorten with valid URL inserts into DB and returns short URL."""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = [42]
    mock_conn.cursor.return_value = mock_cur

    monkeypatch.setattr("app.get_db", lambda: mock_conn)
    monkeypatch.setattr("app.cache.set", MagicMock())
    monkeypatch.setattr("app.cache.get", lambda key: None)

    mock_pipe = MagicMock()
    monkeypatch.setattr("app.cache.pipeline", lambda: mock_pipe)

    response = client.post("/shorten", json={"url": "https://www.example.com"})
    assert response.status_code == 201
    data = response.get_json()
    assert "short_code" in data
    assert "short_url" in data
    assert data["short_code"] == base62_encode(42)


def test_redirect_cache_hit(client, monkeypatch):
    """GET /:short_code when cached in Redis directly returns 302."""
    monkeypatch.setattr("app.cache.get", lambda code: "https://cached-target.com")

    response = client.get("/abc")
    assert response.status_code == 302
    assert response.headers["Location"] == "https://cached-target.com"


def test_redirect_cache_miss_db_hit(client, monkeypatch):
    """GET /:short_code on cache miss queries DB, caches result, and redirects."""
    monkeypatch.setattr("app.cache.get", lambda code: None)
    mock_cache_set = MagicMock()
    monkeypatch.setattr("app.cache.set", mock_cache_set)

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = ["https://db-target.com"]
    mock_conn.cursor.return_value = mock_cur
    monkeypatch.setattr("app.get_db", lambda: mock_conn)

    response = client.get("/1")
    assert response.status_code == 302
    assert response.headers["Location"] == "https://db-target.com"
    mock_cache_set.assert_called_once_with("1", "https://db-target.com")


def test_redirect_not_found(client, monkeypatch):
    """GET /:short_code returns 404 when code does not exist in Redis or DB."""
    monkeypatch.setattr("app.cache.get", lambda code: None)

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = None
    mock_conn.cursor.return_value = mock_cur
    monkeypatch.setattr("app.get_db", lambda: mock_conn)

    response = client.get("/nonexistent")
    assert response.status_code == 404
    assert response.get_json() == {"error": "Short URL not found"}


def test_rate_limit_exceeded(client, monkeypatch):
    """POST /shorten returns 429 when IP exceeds rate limit."""
    monkeypatch.setattr("app.cache.get", lambda key: "10")

    response = client.post("/shorten", json={"url": "https://example.com"})
    assert response.status_code == 429
    assert "Rate limit exceeded" in response.get_json()["error"]

