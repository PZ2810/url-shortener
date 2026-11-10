import http from 'k6/http';
import { check, sleep } from 'k6';

// 50 concurrent virtual users sustained for 30 seconds
export const options = {
  vus: 50,
  duration: '30s',
  thresholds: {
    http_req_duration: ['p(95)<10'], // 95% of requests must complete below 10ms for cache hits
    http_req_failed: ['rate<0.01'],   // Error rate below 1%
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:5000';

export default function () {
  // Test redirect endpoint (redirects: 0 prevents following the 302 to measure app latency only)
  const res = http.get(`${BASE_URL}/1`, { redirects: 0 });
  
  check(res, {
    'status is 302': (r) => r.status === 302,
  });

  sleep(0.01);
}

