"""Server-only, explicit configuration for a Chat Completions compatible API."""
import json
import math
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class SchemaRejected(Exception):
    """The provider refused a strict json_schema request; no tokens were billed."""


class InvalidGeneration(RuntimeError):
    """The model did produce output, but it failed the requested JSON schema.

    Groq validates strict schemas after generation for some models and answers
    400 `json_validate_failed`. Tokens were generated, so this is the worker's
    mistake, not a refused request, and it is not free.
    """

    def __init__(self, generation=''):
        super().__init__('Model sxemə uyğun olmayan JSON yaratdı.')
        self.generation = generation


class RateLimitError(RuntimeError):
    """A rejected request that may be retried after the provider's cooldown."""

    def __init__(self, retry_after=None):
        super().__init__('AI provayderinin sorğu və ya token limiti doldu.')
        self.retry_after = retry_after


class Provider:
    def __init__(self, root):
        self.root = Path(root)

    def config(self):
        values = {}
        file = self.root / '.env'
        if file.exists():
            for line in file.read_text(encoding='utf-8-sig').splitlines():
                if '=' in line and not line.lstrip().startswith('#'):
                    key, value = line.split('=', 1)
                    values[key.strip()] = value.strip().strip('\"').strip("'")
        for key in ('AI_BASE_URL', 'AI_API_KEY', 'GROQ_API_KEY', 'AI_MODEL', 'AI_INPUT_USD_PER_MILLION', 'AI_OUTPUT_USD_PER_MILLION'):
            if key in os.environ:
                values[key] = os.environ[key]
        # Accept Groq's conventional environment variable and use current
        # production defaults only when the configured endpoint is Groq.
        if not values.get('AI_API_KEY') and values.get('GROQ_API_KEY'):
            values['AI_API_KEY'] = values['GROQ_API_KEY']
        try:
            is_groq = urlsplit(values.get('AI_BASE_URL', '')).hostname == 'api.groq.com'
        except ValueError:
            is_groq = False
        if is_groq:
            if not values.get('AI_MODEL'):
                values['AI_MODEL'] = 'openai/gpt-oss-120b'
            if not values.get('AI_INPUT_USD_PER_MILLION'):
                values['AI_INPUT_USD_PER_MILLION'] = '0.15'
            if not values.get('AI_OUTPUT_USD_PER_MILLION'):
                values['AI_OUTPUT_USD_PER_MILLION'] = '0.60'
        return values

    def status(self):
        cfg = self.config()
        missing = [k for k in ('AI_BASE_URL', 'AI_API_KEY', 'AI_MODEL', 'AI_INPUT_USD_PER_MILLION', 'AI_OUTPUT_USD_PER_MILLION') if not cfg.get(k)]
        problem = ''
        try:
            if not missing:
                url = urlsplit(cfg['AI_BASE_URL'])
                if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment:
                    raise ValueError('API ünvanı HTTPS olmalıdır, istifadəçi adı və sorğu parametri olmamalıdır.')
                for key in ('AI_INPUT_USD_PER_MILLION', 'AI_OUTPUT_USD_PER_MILLION'):
                    rate = float(cfg[key])
                    if not math.isfinite(rate) or not 0 <= rate <= 10000:
                        raise ValueError('Token tarifləri 0–10000 arasında olmalıdır.')
        except ValueError as exc:
            problem = str(exc)
        try:
            public_endpoint = urlsplit(cfg.get('AI_BASE_URL', ''))
            safe_endpoint = f'{public_endpoint.scheme}://{public_endpoint.hostname}{public_endpoint.path}' if public_endpoint.hostname else ''
        except ValueError:
            safe_endpoint = ''
        return dict(ready=not missing and not problem, model=cfg.get('AI_MODEL', ''),
                    endpoint=safe_endpoint, missing=missing, problem=problem,
                    key_present=bool(cfg.get('AI_API_KEY')))

    def prepare(self, messages, schema=None, schema_name='response'):
        """Build a call. With `schema`, ask for constrained decoding so required
        fields — including evidence fields — cannot be omitted by the model."""
        if not self.status()['ready']:
            raise ValueError('AI bağlantısı hazır deyil. Bağlantı bölməsində çatışmayan parametrlərə baxın.')
        cfg = self.config()
        response_format = {'type': 'json_object'}
        if schema is not None:
            response_format = {'type': 'json_schema',
                               'json_schema': {'name': schema_name, 'strict': True, 'schema': schema}}
        payload = dict(model=cfg['AI_MODEL'], messages=messages, temperature=0.2,
                       max_tokens=1800, response_format=response_format)
        # UTF-8 bytes plus overhead is a conservative token reservation, not billing truth.
        input_bound = len(json.dumps(messages, ensure_ascii=False).encode()) + 1024
        reserve = math.ceil(input_bound * float(cfg['AI_INPUT_USD_PER_MILLION']) +
                            1800 * float(cfg['AI_OUTPUT_USD_PER_MILLION']))
        return dict(payload=payload, reserve=max(1, reserve), input_bound=input_bound,
                    input_rate=float(cfg['AI_INPUT_USD_PER_MILLION']), output_rate=float(cfg['AI_OUTPUT_USD_PER_MILLION']),
                    endpoint=cfg['AI_BASE_URL'].rstrip('/') + '/chat/completions', key=cfg['AI_API_KEY'])

    def execute(self, call):
        payload = call['payload']
        try:
            return self.send(call, payload)
        except SchemaRejected:
            # The provider refused the schema itself (not the model's output),
            # so retry once without it. The caller is told enforcement was lost;
            # verification still runs on whatever comes back.
            result = self.send(call, dict(payload, response_format={'type': 'json_object'}))
            result['schema_enforced'] = False
            return result

    def send(self, call, payload):
        strict = payload.get('response_format', {}).get('type') == 'json_schema'
        request = Request(call['endpoint'], data=json.dumps(payload).encode(),
                          headers={'Authorization': 'Bearer ' + call['key'], 'Content-Type': 'application/json',
                                   'User-Agent': 'AutonomousInc-Research/0.2'}, method='POST')
        try:
            with build_opener(NoRedirect()).open(request, timeout=60) as response:
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise ValueError('AI cavabı ölçü limitini aşdı.')
                result = json.loads(raw)
            content = result['choices'][0]['message']['content']
            usage = result.get('usage', {})
            tokens_in, tokens_out = usage.get('prompt_tokens'), usage.get('completion_tokens')
            known = all(isinstance(t, int) and not isinstance(t, bool) and t >= 0 for t in (tokens_in, tokens_out))
            cost = math.ceil(tokens_in * call['input_rate'] + tokens_out * call['output_rate']) if known else call['reserve']
            return dict(content=content, cost=cost, usage=usage, estimated=not known, schema_enforced=strict)
        except HTTPError as exc:
            if strict and exc.code == 400:
                try:
                    error = json.loads(exc.read(200_000)).get('error', {})
                except (ValueError, OSError, AttributeError):
                    error = {}
                if error.get('code') == 'json_validate_failed':
                    raise InvalidGeneration(str(error.get('failed_generation') or '')[:20000]) from None
                raise SchemaRejected() from None
            if exc.code == 429:
                try:
                    retry_after = float(exc.headers.get('retry-after', ''))
                    if not math.isfinite(retry_after) or retry_after <= 0:
                        retry_after = None
                except (TypeError, ValueError):
                    retry_after = None
                raise RateLimitError(retry_after) from None
            raise RuntimeError(f'AI provayderi HTTP {exc.code} qaytardı. Bağlantı və kvotanı yoxlayın.') from None
        except (URLError, TimeoutError, OSError):
            raise RuntimeError('AI bağlantısı tamamlanmadı. Təkrar ödəniş riskinə görə avtomatik təkrar edilmir.') from None
        except (KeyError, IndexError, TypeError, json.JSONDecodeError):
            raise RuntimeError('AI provayderinin cavab formatı uyğun deyil.') from None
