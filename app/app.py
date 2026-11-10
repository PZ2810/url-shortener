import os
import string
from functools import wraps
from urllib.parse import urlparse

from flask import Flask, request, redirect, jsonify, render_template
import redis
import psycopg2

app = Flask(__name__)

# Define the 62 characters used for short codes (0-9, a-z, A-Z)
ALPHABET = string.digits + string.ascii_lowercase + string.ascii_uppercase

# Connect to Redis for fast lookups
cache = redis.Redis(
    host=os.environ.get("REDIS_HOST", "redis"),
    port=int(os.environ.get("REDIS_PORT", 6379)),
    decode_responses=True,
)


def get_db():
    """Connect to PostgreSQL for permanent storage."""
    return psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "db"),
        database=os.environ.get("POSTGRES_DB", "urlshortener"),
        user=os.environ.get("POSTGRES_USER", "postgres"),
        password=os.environ.get("POSTGRES_PASSWORD", "postgres"),
    )


def is_valid_url(url):
    """Validate that the URL is a string, within 2048 chars, and has a valid http/https scheme with a domain."""
    if not isinstance(url, str):
        return False
    url = url.strip()
    if not url or len(url) > 2048:
        return False
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def rate_limit(max_requests=10, window=60):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Get the client's IP address
            client_ip = request.remote_addr
            # Create a unique Redis key for this IP
            key = f"rate_limit:{client_ip}"
            # Check current request count
            current = cache.get(key)
            if current and int(current) >= max_requests:
                return jsonify({"error": "Rate limit exceeded. Try again later."}), 429
            # Increment counter and set expiration atomically
            pipe = cache.pipeline()
            pipe.incr(key)
            pipe.expire(key, window)
            pipe.execute()
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def base62_encode(num):
    """Convert a database ID into a short alphanumeric string."""
    if num == 0:
        return ALPHABET[0]
    result = []
    while num > 0:
        num, remainder = divmod(num, 62)
        result.append(ALPHABET[remainder])
    return "".join(reversed(result))


def base62_decode(code):
    """Convert a short code back into the original database ID."""
    num = 0
    for char in code:
        num = num * 62 + ALPHABET.index(char)
    return num


@app.route("/shorten", methods=["POST"])
@rate_limit(max_requests=10, window=60)
def shorten_url():
    # Grab the long URL from the request body
    data = request.get_json()
    if not data or "url" not in data:
        return jsonify({"error": "Missing url field"}), 400

    long_url = data["url"]

    # Validate URL format and length
    if not is_valid_url(long_url):
        return jsonify({"error": "Invalid URL. Must start with http:// or https:// and be under 2048 characters."}), 400

    long_url = long_url.strip()

    # Save to PostgreSQL - the database assigns an auto-incrementing ID
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO urls (long_url) VALUES (%s) RETURNING id", (long_url,))
    url_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()

    # Encode the database ID into a short code
    short_code = base62_encode(url_id)

    # Cache the mapping for fast redirects later
    cache.set(short_code, long_url)

    base_url = os.environ.get("BASE_URL", request.host_url.rstrip("/"))
    return jsonify({"short_url": f"{base_url}/{short_code}", "short_code": short_code}), 201


@app.route("/")
def index():
    return render_template("index.html")



@app.route("/<short_code>")
def redirect_url(short_code):
    # Check the fast cache first
    long_url = cache.get(short_code)

    if long_url:
        print("CACHE HIT", flush=True)
        return redirect(long_url, code=302)

    # Cache miss - fall back to the database
    print("CACHE MISS - querying database", flush=True)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT long_url FROM urls WHERE id = %s", (base62_decode(short_code),))
    result = cur.fetchone()
    cur.close()
    conn.close()

    if not result:
        return jsonify({"error": "Short URL not found"}), 404

    # Found it in the database - cache it for next time
    long_url = result[0]
    cache.set(short_code, long_url)

    return redirect(long_url, code=302)


@app.route("/health")
def health():
    return jsonify({"status": "healthy"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
