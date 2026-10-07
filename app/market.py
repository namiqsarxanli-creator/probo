"""Deterministic market simulation the language model is not allowed to touch.

The model is stated, not improvised, so a reader can argue with it:

* category adoption follows the Bass diffusion model (Bass, 1969), with new
  adopters drawn from the untapped market at rate p + q * installed_share;
* adopters and switchers pick a firm by multinomial logit choice
  (McFadden, 1974) over price, perceived quality and advertising reach,
  against an outside option of not buying at all;
* a firm can only absorb as many of them as its budget buys at the evidenced
  acquisition cost, so demand it cannot pay to serve returns to the market;
* retention is geometric, with churn rising as price moves above the
  evidenced ARPU;
* firms that run out of cash leave, and their customers rejoin the pool.

Every draw comes from a seeded `random.Random`, so a run is reproducible from
its seed alone. Following Mesa's batch_run convention, replications are driven
by an explicit list of seeds rather than a hidden iteration count.

Market facts (market_size, arpu, cac, churn_monthly, cpm, sales_cycle_days)
must arrive verified from `app.parameters`. Everything defined here is a
modelling assumption, exposed in `ASSUMPTIONS` so it can be swept and argued
with — never presented as evidence.
"""
import math
import random
from collections import deque


STRATEGIES = {
    'cheap': dict(label='Ucuz qiymət', price_factor=0.6, quality=0.85, ad_share=0.55, segment='consumer'),
    'premium': dict(label='Premium məhsul', price_factor=1.8, quality=1.35, ad_share=0.30, segment='consumer'),
    # Institutions pay less per seat and make it up in volume.
    'b2b': dict(label='Məktəblərlə B2B', price_factor=0.75, quality=1.15, ad_share=0.10, segment='institution'),
}

# Modelling assumptions. Not evidence: sweep them before trusting any verdict.
ASSUMPTIONS = dict(
    innovation=0.012,          # Bass p: adoption without word of mouth
    imitation=0.38,            # Bass q: word-of-mouth pull
    price_sensitivity=1.6,     # logit weight on price relative to ARPU
    awareness_weight=0.22,     # logit weight on log reach
    outside_option=1.0,        # utility of buying nothing
    churn_elasticity=0.45,     # how fast churn grows with price
    acquisition_elasticity=0.6,  # how much harder a weakly preferred offer is to sell
    institution_share=0.12,    # share of the market bought through institutions
    seats_per_institution=60,  # paying seats behind one institutional customer
    institution_cac_efficiency=0.35,  # bulk deals cost less per seat to win
    fixed_cost_share=0.35,     # monthly fixed cost as a share of ad budget
    budget_months=12,          # runway a default monthly ad budget is spread over
)
CRISES = ('cpm_shock', 'entrant', 'funding_cut')
FACTS = ('market_size', 'arpu', 'cac', 'churn_monthly', 'cpm', 'sales_cycle_days')
SWEPT = ('price_sensitivity', 'arpu', 'cac', 'churn_monthly', 'market_size', 'cpm')


def _binomial(rng, n, p):
    n, p = int(max(0, n)), min(1.0, max(0.0, p))
    if n == 0 or p == 0.0:
        return 0
    if p == 1.0:
        return n
    if n <= 256:
        return sum(1 for _ in range(n) if rng.random() < p)
    # Normal approximation stays well inside its validity range at this size.
    return min(n, max(0, round(rng.gauss(n * p, math.sqrt(n * p * (1 - p))))))


def _multinomial(rng, count, weights):
    """Exact multinomial split via sequential conditional binomials."""
    shares, remaining, rest = [0] * len(weights), int(count), sum(weights)
    for index, weight in enumerate(weights):
        if remaining <= 0 or rest <= 0:
            break
        if index == len(weights) - 1:
            shares[index] = remaining
            break
        drawn = _binomial(rng, remaining, weight / rest)
        shares[index] = drawn
        remaining -= drawn
        rest -= weight
    return shares


def firm(identifier, name, strategy, cash, ad_budget=None, price=None):
    """One competitor. Leaving budget or price unset applies the strategy's stance."""
    if strategy not in STRATEGIES:
        raise ValueError('Naməlum strategiya.')
    if float(cash) <= 0:
        raise ValueError('Başlanğıc kapital müsbət olmalıdır.')
    return dict(id=identifier, name=name, strategy=strategy, cash=float(cash),
                ad_budget=None if ad_budget is None else float(ad_budget), price=price)


def config(parameters, firms, horizon=36, crises=(), assumptions=None):
    """Bind verified market facts to firm decisions and modelling assumptions."""
    missing = [key for key in FACTS if key not in parameters]
    if missing:
        raise ValueError('Simulyasiya üçün çatışmayan parametrlər: ' + ', '.join(missing))
    if not 1 <= len(firms) <= 6:
        raise ValueError('1–6 şirkət arasında olmalıdır.')
    if not 6 <= horizon <= 120:
        raise ValueError('Üfüq 6–120 ay arasında olmalıdır.')
    for crisis in crises:
        if crisis.get('kind') not in CRISES:
            raise ValueError('Naməlum böhran növü.')
    return dict(parameters=dict(parameters), firms=[dict(f) for f in firms], horizon=int(horizon),
                crises=[dict(c) for c in crises], assumptions=dict(ASSUMPTIONS, **(assumptions or {})))


class _Firm:
    def __init__(self, spec, facts, rules):
        preset = STRATEGIES[spec['strategy']]
        self.id, self.name, self.strategy = spec['id'], spec['name'], spec['strategy']
        self.segment, self.quality = preset['segment'], preset['quality']
        self.price = float(spec['price']) if spec.get('price') else facts['arpu'] * preset['price_factor']
        self.cash = float(spec['cash'])
        # How much of the war chest goes to winning customers, and how exposed
        # that makes the firm when ad prices move.
        self.paid_dependence = preset['ad_share']
        self.ad_budget = (float(spec['ad_budget']) if spec.get('ad_budget') is not None
                          else self.cash * preset['ad_share'] / rules['budget_months'])
        self.customers = 0
        self.acquired = 0
        self.revenue = 0.0
        self.profit = 0.0
        self.ad_spent = 0.0
        self.alive = True
        self.pipeline = deque()
        self.lag = max(0, round(facts['sales_cycle_days'] / 30) - 1) if self.segment == 'institution' else 0
        self.rules = rules
        self.base_cpm = facts['cpm']

    def seats(self, facts):
        return self.rules['seats_per_institution'] if self.segment == 'institution' else 1

    def capacity(self, facts, cpm, share, reference):
        """Customers this month's budget can actually pay to acquire.

        Two forces move the evidenced CAC. An ad price shock bites in
        proportion to how much of a firm's go-to-market runs through paid
        media, so a direct-sales outfit shrugs off what guts a performance
        marketer. And an offer few people prefer costs more to sell: demand
        and acquisition cost are the same fact seen from two sides.
        """
        shock = (cpm / self.base_cpm - 1) if self.base_cpm else 0.0
        unit = facts['cac'] * max(0.05, 1 + self.paid_dependence * shock)
        pull = (reference / share) ** self.rules['acquisition_elasticity'] if share > 0 else 8.0
        unit *= min(8.0, max(0.25, pull))
        if self.segment == 'institution':
            unit *= self.seats(facts) * self.rules['institution_cac_efficiency']
        return int(self.ad_budget / unit) if unit > 0 else 0

    def utility(self, facts, cpm):
        reach = self.ad_budget / cpm * 1000 if cpm > 0 else 0.0
        return (self.quality
                - self.rules['price_sensitivity'] * (self.price / facts['arpu'])
                + self.rules['awareness_weight'] * math.log1p(reach))

    def churn_rate(self, facts):
        ratio = max(self.price / facts['arpu'], 0.01)
        return min(0.9, facts['churn_monthly'] * ratio ** self.rules['churn_elasticity'])


def run(settings, seed):
    """One reproducible market history. Same seed, same numbers, always."""
    rng = random.Random(seed)
    facts, rules = settings['parameters'], settings['assumptions']
    cpm = facts['cpm']
    firms = [_Firm(spec, facts, rules) for spec in settings['firms']]
    crises = {}
    for crisis in settings['crises']:
        crises.setdefault(int(crisis.get('step', 0)), []).append(crisis)

    potential = {'consumer': facts['market_size'] * (1 - rules['institution_share']),
                 'institution': facts['market_size'] * rules['institution_share'] / max(1, rules['seats_per_institution'])}
    adopted = {'consumer': 0, 'institution': 0}
    switchers = {'consumer': 0, 'institution': 0}
    history = []

    for step in range(settings['horizon']):
        for crisis in crises.get(step, []):
            if crisis['kind'] == 'cpm_shock':
                cpm *= float(crisis.get('factor', 2.0))
            elif crisis['kind'] == 'funding_cut':
                for target in firms:
                    if crisis.get('firm_id') in (None, target.id):
                        target.cash *= float(crisis.get('factor', 0.4))
            elif crisis['kind'] == 'entrant':
                spec = firm(crisis.get('id', f'entrant-{step}'), crisis.get('name', 'Yeni rəqib'),
                            crisis.get('strategy', 'cheap'), crisis.get('cash', facts['cac'] * 6000),
                            crisis.get('ad_budget'))
                firms.append(_Firm(spec, facts, rules))

        for segment in ('consumer', 'institution'):
            competing = [f for f in firms if f.alive and f.segment == segment]
            # Sequential conditional draws favour whoever is asked first, so
            # the order is reshuffled rather than inherited from the config.
            rng.shuffle(competing)
            remaining = max(0.0, potential[segment] - adopted[segment])
            rate = rules['innovation'] + rules['imitation'] * (adopted[segment] / potential[segment] if potential[segment] else 0)
            fresh = _binomial(rng, remaining, min(1.0, max(0.0, rate)))
            adopted[segment] += fresh
            pool = fresh + switchers[segment]
            switchers[segment] = 0
            if not competing or pool <= 0:
                continue
            utilities = [f.utility(facts, cpm) for f in competing] + [rules['outside_option']]
            top = max(utilities)
            weights = [math.exp(u - top) for u in utilities]
            total = sum(weights)
            reference = 1 / len(weights)
            capacities = [f.capacity(facts, cpm, weights[i] / total, reference) for i, f in enumerate(competing)]
            unserved = 0
            for winner, chosen, room in zip(competing, _multinomial(rng, pool, weights), capacities):
                won = min(chosen, room)
                unserved += chosen - won
                if not won:
                    continue
                if winner.lag:
                    winner.pipeline.append((step + winner.lag, won))
                else:
                    winner.customers += won
                    winner.acquired += won
            # Demand a firm could not fund stays in the market and tries again.
            switchers[segment] += unserved

        for company in firms:
            if not company.alive:
                continue
            while company.pipeline and company.pipeline[0][0] <= step:
                _, won = company.pipeline.popleft()
                company.customers += won
                company.acquired += won
            lost = _binomial(rng, company.customers, company.churn_rate(facts))
            company.customers -= lost
            switchers[company.segment] += lost
            revenue = company.customers * company.price * company.seats(facts)
            spend = company.ad_budget * (1 + rules['fixed_cost_share'])
            company.revenue += revenue
            company.ad_spent += company.ad_budget
            company.profit += revenue - spend
            company.cash += revenue - spend
            if company.cash < 0:
                company.alive = False
                switchers[company.segment] += company.customers
                company.customers = 0
        history.append({f.id: dict(customers=f.customers, cash=round(f.cash, 2)) for f in firms})

    results = {f.id: dict(name=f.name, strategy=f.strategy, price=round(f.price, 4),
                          customers=f.customers, acquired=f.acquired, revenue=round(f.revenue, 2),
                          profit=round(f.profit, 2), cash=round(f.cash, 2), survived=f.alive,
                          cac_realised=round(f.ad_spent / f.acquired, 2) if f.acquired else None)
               for f in firms}
    alive = [f for f in firms if f.alive]
    winner = max(alive, key=lambda f: f.profit).id if alive else None
    return dict(seed=seed, winner=winner, firms=results, history=history)


def _percentiles(values):
    if not values:
        return {}
    ordered = sorted(values)
    pick = lambda q: ordered[min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))]
    return dict(p10=pick(.10), median=pick(.50), p90=pick(.90))


def batch(settings, seeds):
    """Replications over explicit seeds, reported as a distribution."""
    seeds = list(seeds)
    if not 1 <= len(seeds) <= 2000:
        raise ValueError('1–2000 təkrar arasında olmalıdır.')
    runs = [run(settings, seed) for seed in seeds]
    identifiers = list(runs[-1]['firms'])
    wins = {identifier: 0 for identifier in identifiers}
    wins[None] = 0
    for result in runs:
        wins[result['winner']] = wins.get(result['winner'], 0) + 1
    summary = {}
    for identifier in identifiers:
        profits = [r['firms'][identifier]['profit'] for r in runs if identifier in r['firms']]
        summary[identifier] = dict(
            name=runs[-1]['firms'][identifier]['name'],
            wins=wins.get(identifier, 0),
            win_rate=round(wins.get(identifier, 0) / len(runs), 4),
            survival_rate=round(sum(1 for r in runs if r['firms'].get(identifier, {}).get('survived')) / len(runs), 4),
            profit=_percentiles(profits))
    return dict(runs=len(runs), seeds=seeds, firms=summary,
                no_winner_rate=round(wins.get(None, 0) / len(runs), 4))


def sensitivity(settings, seeds, key, factors=(0.5, 0.75, 1.0, 1.5, 2.0)):
    """How far the verdict moves when one assumed or evidenced input moves.

    The point is not the win rate at any single factor but the spread: a wide
    swing means the answer is an artefact of that input, so measuring it beats
    simulating anything else.
    """
    pool = 'parameters' if key in settings['parameters'] else 'assumptions'
    if key not in settings[pool]:
        raise ValueError('Bu ad nə parametrlərdə, nə də fərziyyələrdə var.')
    base, points = settings[pool][key], []
    for factor in factors:
        variant = dict(settings, **{pool: dict(settings[pool], **{key: base * factor})})
        outcome = batch(variant, seeds)
        points.append(dict(factor=factor, value=base * factor,
                           win_rate={i: f['win_rate'] for i, f in outcome['firms'].items()},
                           no_winner_rate=outcome['no_winner_rate']))
    leaders = {i: [p['win_rate'].get(i, 0) for p in points] for i in points[0]['win_rate']}
    swing = {i: round(max(rates) - min(rates), 4) for i, rates in leaders.items()}
    return dict(key=key, pool=pool, base=base, points=points, swing=swing,
                worst_swing=max(swing.values()) if swing else 0.0)


def _number(value, low, high, label):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f'{label} ədəd olmalıdır.') from None
    if not math.isfinite(number) or not low <= number <= high:
        raise ValueError(f'{label} {low:g}–{high:g} arasında olmalıdır.')
    return number


def _label(value, limit, label):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= limit:
        raise ValueError(f'{label} 1–{limit} simvol arasında olmalıdır.')
    return value.strip()


def plan(request):
    """Validate an untrusted request and return the full verdict.

    This is the boundary the HTTP layer calls: everything arriving here is
    treated as hostile input, and every figure is stated back in the reply so
    a reader can see exactly what was simulated.
    """
    if not isinstance(request, dict):
        raise ValueError('Sorğu obyekt olmalıdır.')
    given = request.get('parameters')
    if not isinstance(given, dict):
        raise ValueError('Bazar parametrləri göndərilməyib.')
    bounds = dict(market_size=(1, 1e13), arpu=(.01, 1e5), cac=(.01, 1e6),
                  churn_monthly=(.0001, .9), cpm=(.01, 1e4), sales_cycle_days=(1, 1095))
    facts = {key: _number(given.get(key), *bounds[key], key) for key in FACTS}

    entries = request.get('firms')
    if not isinstance(entries, list) or not 1 <= len(entries) <= 6:
        raise ValueError('1–6 şirkət göndərilməlidir.')
    teams, seen = [], set()
    for index, entry in enumerate(entries, 1):
        if not isinstance(entry, dict):
            raise ValueError('Şirkət formatı uyğun deyil.')
        identifier = _label(entry.get('id') or f'firm{index}', 24, 'Şirkət kodu')
        if identifier in seen:
            raise ValueError('Şirkət kodları təkrarlana bilməz.')
        seen.add(identifier)
        teams.append(firm(identifier, _label(entry.get('name'), 40, 'Şirkət adı'),
                          entry.get('strategy'), _number(entry.get('cash'), 1000, 1e9, 'Kapital'),
                          None if entry.get('ad_budget') in (None, '') else _number(entry['ad_budget'], 1, 1e8, 'Reklam büdcəsi'),
                          None if entry.get('price') in (None, '') else _number(entry['price'], .01, 1e5, 'Qiymət')))

    horizon = int(_number(request.get('horizon', 36), 6, 120, 'Üfüq'))
    replications = int(_number(request.get('replications', 200), 20, 400, 'Təkrar sayı'))
    crises = request.get('crises') or []
    if not isinstance(crises, list) or len(crises) > 4:
        raise ValueError('Ən çox 4 böhran əlavə edilə bilər.')
    for crisis in crises:
        if not isinstance(crisis, dict) or crisis.get('kind') not in CRISES:
            raise ValueError('Naməlum böhran növü.')
        crisis['step'] = int(_number(crisis.get('step', 0), 0, horizon - 1, 'Böhran ayı'))

    settings = config(facts, teams, horizon, crises)
    seeds = list(range(replications))
    keys = request.get('sensitivity') or SWEPT
    if not isinstance(keys, (list, tuple)) or len(keys) > 8:
        raise ValueError('Ən çox 8 həssaslıq açarı seçilə bilər.')
    sweep = sorted((sensitivity(settings, seeds[:min(40, replications)], key) for key in keys),
                   key=lambda report: -report['worst_swing'])
    return dict(race=batch(settings, seeds), sensitivity=sweep, parameters=facts,
                assumptions=settings['assumptions'], horizon=horizon, crises=crises,
                replications=replications, seed_range=[seeds[0], seeds[-1]])
