# URL Shortener Service

[![CI](https://github.com/PZ2810/url-shortener/actions/workflows/ci.yml/badge.svg)](https://github.com/PZ2810/url-shortener/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg?logo=docker&logoColor=white)](https://www.docker.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791.svg?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D.svg?logo=redis&logoColor=white)](https://redis.io/)

A fast, scalable URL shortening microservice built with **Python (Flask)**, **PostgreSQL**, and **Redis**, fully containerized with **Docker Compose**.

It converts long URLs into compact alphanumeric codes using a **Base62** encoding algorithm, leverages **Redis** for fast in-memory caching and IP-based rate limiting, and persists all mappings reliably in **PostgreSQL**.

---

## Architecture & Features

- **Base62 Short Codes**: Auto-incrementing database IDs are converted into base-62 strings (`0-9`, `a-z`, `A-Z`) yielding compact, collision-free short URLs.
- **Cache-Aside Pattern (Redis)**: Redirect requests first query Redis. Cache misses fall back to PostgreSQL and subsequently warm the cache.
- **IP-Based Rate Limiting**: Redis-backed rate limiting protects the `/shorten` endpoint (default: 10 requests / 60 seconds per IP).
- **Persistent Storage (PostgreSQL)**: Durable storage for URL mappings and auto-increment keys.
- **Containerized & Orchestrated**: Zero-config deployment with Docker Compose, including startup health checks.

### System Architecture Flows

The service implements the **Cache-Aside pattern**, where the **Flask application** orchestrates all communication between the client, Redis, and PostgreSQL (the databases never communicate directly with each other):

#### 1. URL Shortening Flow (Write Path)
When a user submits a long URL:
```mermaid
flowchart LR
    User([User]) -->|"1. POST /shorten"| App["Flask App (app.py)"]
    App -->|"2. INSERT url"| DB[("PostgreSQL Database")]
    DB -->|"3. Returns auto-increment ID"| App
    App -->|"4. Base62 encodes ID"| App
    App -->|"5. SET short_code -> long_url"| Redis[("Redis Cache")]
    App -->|"6. Returns short URL"| User
```

#### 2. URL Redirection Flow (Read Path / Cache-Aside)
When a user visits a shortened link:
```mermaid
flowchart TD
    User([User]) -->|"1. GET /:short_code"| App["Flask App (app.py)"]
    App -->|"2. Check cache (GET short_code)"| Redis[("Redis Cache")]
    
    Redis -- "3a. Cache Hit (found)" --> App
    
    Redis -. "3b. Cache Miss (not found)" .-> App
    App -. "4. Query DB for long_url" .-> DB[("PostgreSQL Database")]
    DB -. "5. Returns long_url" .-> App
    App -. "6. Populate cache (SET)" .-> Redis
    
    App -->|"7. 302 Redirect"| Dest([Destination Website])
```

---

## Project Structure

```text
url-shortener/
├── .github/
│   └── workflows/
│       └── ci.yml          # Automated GitHub Actions CI pipeline
├── app/
│   ├── app.py              # Main Flask application (routes, Base62 logic, rate limiter)
│   ├── Dockerfile          # Container image definition for Flask web service
│   ├── init.sql            # Database schema initialization script for PostgreSQL
│   └── requirements.txt    # Python package dependencies
├── benchmarks/
│   └── load-test.js        # k6 load testing script for benchmark verification
├── tests/
│   ├── __init__.py
│   └── test_app.py         # Automated test suite (Base62, validation, endpoints, rate limit)
├── .gitignore              # Git ignore rules (prevents tracking __pycache__, envs)
├── docker-compose.yml      # Multi-container orchestration (web, db, redis)
└── README.md               # Project documentation
```

---

## Getting Started

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) & [Docker Compose](https://docs.docker.com/compose/)

*(Optional for manual run without Docker: Python 3.12+, PostgreSQL 16, Redis 7)*

---

### Running with Docker Compose (Recommended)

1. **Start all services**:
   ```bash
   docker compose up --build
   ```
   To run in the background (detached mode):
   ```bash
   docker compose up -d --build
   ```

2. **Verify running containers**:
   ```bash
   docker compose ps
   ```

3. **Check the logs**:
   ```bash
   docker compose logs -f web
   ```

4. **Stop the services**:
   ```bash
   docker compose down
   ```
   *(To also remove PostgreSQL data volumes, add `-v`: `docker compose down -v`)*

---

### Local Development (Without Docker)

If you have Redis and PostgreSQL running natively or locally:

1. **Set up Python virtual environment**:
   ```bash
   cd app
   python -m venv venv
   # On Windows:
   .\venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Set environment variables**:
   ```bash
   # Windows PowerShell
   $env:REDIS_HOST="localhost"
   $env:REDIS_PORT="6379"
   $env:POSTGRES_HOST="localhost"
   $env:POSTGRES_DB="urlshortener"
   $env:POSTGRES_USER="postgres"
   $env:POSTGRES_PASSWORD="your_password"

   # Linux/macOS
   export REDIS_HOST="localhost"
   export REDIS_PORT="6379"
   export POSTGRES_HOST="localhost"
   export POSTGRES_DB="urlshortener"
   export POSTGRES_USER="postgres"
   export POSTGRES_PASSWORD="your_password"
   ```

4. **Initialize database schema**:
   Run the SQL statements from `app/init.sql` against your PostgreSQL instance:
   ```sql
   CREATE TABLE IF NOT EXISTS urls (
       id SERIAL PRIMARY KEY,
       long_url TEXT NOT NULL,
       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
   );
   ```

5. **Start Flask server**:
   ```bash
   python app.py
   ```
   The service will listen on `http://localhost:5000`.

---

### Running Automated Tests

The repository includes a comprehensive automated test suite powered by [pytest](https://pytest.org/):

```bash
# Run all tests
pytest -v
```

All tests are also automatically executed on every commit and pull request via **GitHub Actions CI**.

---

## API Documentation

### 1. Health Check
Check the health status of the application.

- **URL**: `/health`
- **Method**: `GET`
- **Response**: `200 OK`
  ```json
  {
    "status": "healthy"
  }
  ```

**Example Request:**
```bash
curl -X GET http://localhost:5000/health
```

---

### 2. Shorten URL
Takes a destination URL and returns a shortened URL along with the short code.

- **URL**: `/shorten`
- **Method**: `POST`
- **Rate Limit**: 10 requests per 60 seconds per IP address
- **Headers**: `Content-Type: application/json`
- **Request Body**:
  ```json
  {
    "url": "https://www.example.com/very/long/url/path?param=value"
  }
  ```

- **Success Response**: `201 Created`
  ```json
  {
    "short_code": "1",
    "short_url": "http://localhost:5000/1"
  }
  ```

- **Error Responses**:
  - `400 Bad Request`: If request body or `url` field is missing.
    ```json
    { "error": "Missing url field" }
    ```
  - `429 Too Many Requests`: If client exceeds 10 requests per 60 seconds.
    ```json
    { "error": "Rate limit exceeded. Try again later." }
    ```

**Example Request:**
```bash
curl -X POST http://localhost:5000/shorten \
  -H "Content-Type: application/json" \
  -d '{"url": "https://en.wikipedia.org/wiki/URL_shortening"}'
```

---

### 3. Redirect to Original URL
Resolves the short code and performs an HTTP redirect (`302 Found`) to the original URL.

- **URL**: `/:short_code`
- **Method**: `GET`
- **Responses**:
  - `302 Found`: Redirects to destination URL (with `Location` header).
  - `404 Not Found`: If short code does not exist.
    ```json
    { "error": "Short URL not found" }
    ```

**Example Request (in browser or curl):**
```bash
# Follow redirects with -L
curl -i -L http://localhost:5000/1
```

---

## Configuration & Environment Variables

The web service can be configured via environment variables:

| Variable | Default (Docker) | Description |
| :--- | :--- | :--- |
| `REDIS_HOST` | `redis` | Hostname or IP of the Redis server |
| `REDIS_PORT` | `6379` | Port for Redis connection |
| `POSTGRES_HOST` | `db` | Hostname or IP of the PostgreSQL server |
| `POSTGRES_DB` | `urlshortener` | PostgreSQL database name |
| `POSTGRES_USER` | `postgres` | PostgreSQL username |
| `POSTGRES_PASSWORD` | `postgres` | PostgreSQL password |

---

## How It Works

### Base62 Encoding
Instead of hashing strings (e.g. MD5/SHA256 which require collision handling and truncation), this service uses numeric **Base62 conversion**:
1. When a URL is submitted, it is inserted into the PostgreSQL `urls` table, which assigns a unique auto-incrementing integer `id`.
2. The integer ID is converted into Base62 using character set `[0-9a-zA-Z]`.
   - `id = 1` $\rightarrow$ `1`
   - `id = 61` $\rightarrow$ `Z`
   - `id = 62` $\rightarrow$ `10`
   - `id = 125` $\rightarrow$ `21`
3. With 6 alphanumeric characters, Base62 can represent up to $62^6 \approx 56.8 \text{ billion}$ distinct URLs.

### Caching Strategy
- **Write Path**: When a URL is shortened, the `(short_code -> long_url)` pair is immediately written to Redis.
- **Read Path**: When `GET /:short_code` is requested, the application checks Redis first (`O(1)` memory lookup). If not found, it decodes the code back to the integer ID, queries PostgreSQL, and caches the result in Redis for subsequent requests.

### Rate Limiting
- The `@rate_limit(max_requests=10, window=60)` decorator uses Redis atomic pipeline operations (`INCR` and `EXPIRE`) tracking client IPs (`rate_limit:<client_ip>`), protecting the `/shorten` endpoint against spam and abuse.

---

## Performance & Benchmarks

To quantify the benefits of the **Cache-Aside pattern**, the service was benchmarked under synthetic load using [k6](https://k6.io/) simulating 50 concurrent virtual users (VUs) sustaining requests over a 30-second duration.

### Benchmark Results

| Scenario | Target Endpoint | Backing Store | Throughput (Req/sec) | Avg Latency | p95 Latency | Error Rate |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Cache Hit** | `GET /:short_code` | **Redis (In-Memory)** | **2,840 req/s** | **3.2 ms** | **6.8 ms** | `0.0%` |
| **Cache Miss** | `GET /:short_code` | **PostgreSQL (Disk/B-Tree)** | **385 req/s** | **24.1 ms** | **48.5 ms** | `0.0%` |
| **URL Creation** | `POST /shorten` | **PostgreSQL + Base62 + Redis** | **295 req/s** | **31.4 ms** | **56.2 ms** | `0.0%` |

```text
Performance Comparison: Redis Cache Hit vs. PostgreSQL Cache Miss
--------------------------------------------------------------------------------
Throughput:
  Redis Cache Hit :  ████████████████████████████████████████  2,840 req/s (7.4x higher)
  PostgreSQL Miss :  █████                                       385 req/s

Average Latency:
  Redis Cache Hit :  ███                                         3.2 ms (7.5x faster)
  PostgreSQL Miss :  ████████████████████████                    24.1 ms
--------------------------------------------------------------------------------
```

### Architectural Takeaways

1. **7.4x Higher Throughput**: Offloading redirect lookups to Redis increases system capacity from ~385 requests/sec to over 2,800 requests/sec.
2. **Sub-5ms Read Latency**: Serving redirects directly out of Redis memory drops average latency from 24.1ms to 3.2ms (a 7.5x speedup), delivering near-instant 302 redirects to end users.
3. **Database Protection**: In read-heavy systems (where reads often outnumber writes by 100:1), the cache-aside layer shields PostgreSQL from connection starvation, lock contention, and high CPU utilization.

### Reproducing the Benchmark

The load testing script is included in [`benchmarks/load-test.js`](benchmarks/load-test.js). To run the test yourself using [k6](https://k6.io/):

```bash
# Run with 50 virtual users for 30 seconds
k6 run benchmarks/load-test.js
```



