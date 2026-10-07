"""One call per worker, on that worker's own model and at that model's price.

Connection settings (endpoint, key) come from the project's existing `.env`
through `app.provider.Provider`; the model and the price come from the
worker. Strict schemas use constrained decoding; when a model refuses a
strict schema the provider retries once without it, and the reply records
that enforcement was lost.
"""
import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.provider import InvalidGeneration, Provider
from agency.workforce import MODELS


class Models:
    def __init__(self, provider: Provider):
        self.provider = provider
        self._available, self._checked = None, 0.0

    def ready(self):
        return self.provider.status()['ready']

    def available(self, max_age=600):
        """Model ids this key may use, or None when the list cannot be read."""
        if self._available is not None and time.time() - self._checked < max_age:
            return self._available
        cfg = self.provider.config()
        if not cfg.get('AI_BASE_URL') or not cfg.get('AI_API_KEY'):
            return None
        request = Request(cfg['AI_BASE_URL'].rstrip('/') + '/models',
                          headers={'Authorization': 'Bearer ' + cfg['AI_API_KEY'],
                                   'User-Agent': 'SubutAgentliyi/1.0'})
        try:
            with urlopen(request, timeout=20) as response:
                listed = {item.get('id') for item in json.loads(response.read(1_000_000)).get('data', [])}
        except (HTTPError, URLError, TimeoutError, OSError, ValueError):
            return None
        self._available, self._checked = {m for m in MODELS if m in listed}, time.time()
        return self._available

    def call(self, model, messages, schema, name, max_tokens=3000):
        if model not in MODELS:
            raise ValueError('Naməlum model.')
        cfg = self.provider.config()
        price = MODELS[model]
        payload = dict(model=model, messages=messages, temperature=0.1, max_tokens=max_tokens,
                       response_format={'type': 'json_schema',
                                        'json_schema': {'name': name, 'strict': True, 'schema': schema}})
        if price['effort']:
            payload.update(reasoning_effort=price['effort'], include_reasoning=False)
        input_bound = len(json.dumps(messages, ensure_ascii=False).encode()) + 1024
        call = dict(payload=payload, endpoint=cfg['AI_BASE_URL'].rstrip('/') + '/chat/completions',
                    key=cfg['AI_API_KEY'], input_rate=price['input'], output_rate=price['output'],
                    reserve=max(1, int(input_bound * price['input'] + max_tokens * price['output'])))
        started = time.perf_counter()
        try:
            result = self.provider.execute(call)
        except InvalidGeneration as exc:
            # The worker answered in the wrong shape. Hand the text to the guard,
            # which will block it as a format violation, and charge an estimate:
            # the provider generated tokens but reported no usage.
            produced = len(exc.generation) // 3 + 1
            result = dict(content=exc.generation, usage={}, estimated=True, schema_enforced=True,
                          invalid_generation=True,
                          cost=int(input_bound / 3 * price['input'] + produced * price['output']))
        result['duration_ms'] = max(1, round((time.perf_counter() - started) * 1000))
        result['model'] = model
        return result
