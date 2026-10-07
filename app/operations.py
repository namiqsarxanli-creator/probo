"""Local, deterministic planning calculations. Amounts are ordinary USD, not AI-call microdollars."""
import math
from datetime import date


def number(value, label, low=0, high=1_000_000_000):
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f'{label} rəqəm olmalıdır.') from None
    if not math.isfinite(result) or not low <= result <= high:
        raise ValueError(f'{label} {low}–{high} arasında olmalıdır.')
    return result


def plan_input(data):
    plan = dict(starting_cash=number(data.get('starting_cash'), 'İlkin vəsait'),
                monthly_customers=number(data.get('monthly_customers'), 'Aylıq yeni müştəri', 0, 1_000_000),
                price=number(data.get('price'), 'Müştəri üzrə aylıq gəlir'),
                variable_cost=number(data.get('variable_cost'), 'Müştəri üzrə xərc'),
                fixed_cost=number(data.get('fixed_cost'), 'Sabit aylıq xərc'),
                churn=number(data.get('churn'), 'Aylıq itki faizi', 0, 100),
                growth=number(data.get('growth'), 'Yeni müştəri artımı faizi', -90, 500))
    try:
        months = int(data.get('months'))
    except (TypeError, ValueError):
        raise ValueError('Müddət 1–36 ay olmalıdır.') from None
    if not 1 <= months <= 36:
        raise ValueError('Müddət 1–36 ay olmalıdır.')
    plan['months'] = months
    return plan


def scenario_input(data):
    result = dict(name=str(data.get('name', '')).strip(),
                  sales_multiplier=number(data.get('sales_multiplier'), 'Satış əmsalı', 0, 5),
                  cost_multiplier=number(data.get('cost_multiplier'), 'Xərc əmsalı', 0, 5))
    if not 3 <= len(result['name']) <= 100:
        raise ValueError('Ssenari adı 3–100 simvol olmalıdır.')
    try:
        result['delay_months'] = int(data.get('delay_months'))
    except (TypeError, ValueError):
        raise ValueError('Gecikmə 0–24 ay olmalıdır.') from None
    if not 0 <= result['delay_months'] <= 24:
        raise ValueError('Gecikmə 0–24 ay olmalıdır.')
    return result


def project(plan, scenario=None):
    """Existing customers persist subject to churn; all revenue is recurring.

    This is a transparent what-if model, not a market forecast.
    """
    scenario = scenario or dict(sales_multiplier=1, cost_multiplier=1, delay_months=0)
    cash = plan['starting_cash']
    customers = 0.0
    rows = []
    for month in range(1, plan['months'] + 1):
        customers *= 1 - plan['churn'] / 100
        added = (plan['monthly_customers'] * (1 + plan['growth'] / 100) ** (month - 1)
                 * scenario['sales_multiplier'] if month > scenario['delay_months'] else 0)
        customers += added
        revenue = customers * plan['price']
        variable = customers * plan['variable_cost'] * scenario['cost_multiplier']
        fixed = plan['fixed_cost'] * scenario['cost_multiplier']
        net = revenue - variable - fixed
        cash += net
        rows.append(dict(month=month, customers=round(customers, 2), revenue=round(revenue, 2),
                         costs=round(variable + fixed, 2), net=round(net, 2), cash=round(cash, 2)))
    return dict(rows=rows, ending_cash=rows[-1]['cash'], total_revenue=round(sum(r['revenue'] for r in rows), 2),
                total_costs=round(sum(r['costs'] for r in rows), 2),
                first_negative_month=next((r['month'] for r in rows if r['cash'] < 0), None))


def due_date(value):
    try:
        return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError):
        raise ValueError('Son tarix YYYY-MM-DD formatında olmalıdır.') from None
