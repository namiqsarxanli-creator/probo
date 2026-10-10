"""One call per worker, on that worker's own model, provider and price.

Groq's connection settings come from the project's existing `.env` through
`app.provider.Provider` (AI_BASE_URL, AI_API_KEY / GROQ_API_KEY); every other
provider needs only its key in the same file (GEMINI_API_KEY,
OPENROUTER_API_KEY). A provider without a key simply supplies no candidates.
Strict schemas are requested everywhere; when a provider refuses the schema
itself, the call is retried once without it and the reply records that
enforcement was lost — the guard checks the result either way.
"""
import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.provider import InvalidGeneration, Provider
from agency.workforce import MODELS, PROVIDERS


class Models:
    def __init__(self, provider: Provider):
        self.provider = provider
        self._available, self._checked = None, 0.0

    def credentials(self, name):
        """(base URL, key) for a provider, or None when this project has no key for it."""
        cfg = self.provider.config()
        if name == 'groq':
            if not cfg.get('AI_BASE_URL') or not cfg.get('AI_API_KEY'):
                return None
            return cfg['AI_BASE_URL'].rstrip('/'), cfg['AI_API_KEY']
        key = cfg.get(PROVIDERS[name]['key'])
        return (PROVIDERS[name]['base'], key) if key else None

    def ready(self):
        return self.provider.status()['ready'] or any(self.credentials(name) for name in PROVIDERS if name != 'groq')

    def available(self, max_age=600):
        """Worker model ids some configured provider will serve, or None when no list can be read."""
        if self._available is not None and time.time() - self._checked < max_age:
            return self._available
        found, answered = set(), False
        for name in PROVIDERS:
            creds = self.credentials(name)
            if not creds:
                continue
            request = Request(creds[0] + '/models', headers={'Authorization': 'Bearer ' + creds[1],
                                                             'User-Agent': 'SubutAgentliyi/1.0'})
            try:
                with urlopen(request, timeout=20) as response:
                    listed = {str(item.get('id')).removeprefix('models/')
                              for item in json.loads(response.read(3_000_000)).get('data', [])}
            except (HTTPError, URLError, TimeoutError, OSError, ValueError):
                continue
            answered = True
            found |= {key for key, spec in MODELS.items()
                      if spec.get('provider', 'groq') == name and spec.get('api', key) in listed}
        if not answered:
            return None
        self._available, self._checked = found, time.time()
        return found

    def call(self, model, messages, schema, name, max_tokens=3000):
        if model not in MODELS:
            raise ValueError('Naməlum model.')
        spec = MODELS[model]
        provider = spec.get('provider', 'groq')
        creds = self.credentials(provider)
        if not creds:
            raise RuntimeError(f"{PROVIDERS[provider]['label']} üçün açar yoxdur.")
        payload = dict(model=spec.get('api', model), messages=messages, temperature=0.1, max_tokens=max_tokens,
                       response_format={'type': 'json_schema',
                                        'json_schema': {'name': name, 'strict': True, 'schema': schema}})
        if spec['effort']:
            payload['reasoning_effort'] = spec['effort']
            if provider == 'groq':
                payload['include_reasoning'] = False  # Groq-only parameter; others reject it
        input_bound = len(json.dumps(messages, ensure_ascii=False).encode()) + 1024
        call = dict(payload=payload, endpoint=creds[0] + '/chat/completions', key=creds[1],
                    input_rate=spec['input'], output_rate=spec['output'],
                    reserve=max(1, int(input_bound * spec['input'] + max_tokens * spec['output'])))
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
                          cost=int(input_bound / 3 * spec['input'] + produced * spec['output']))
        result['duration_ms'] = max(1, round((time.perf_counter() - started) * 1000))
        result['model'] = model
        return result
