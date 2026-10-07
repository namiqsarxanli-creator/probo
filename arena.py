"""Run the market engine from the command line: python arena.py

The studio UI does not reach this engine yet. This entry point exists so the
simulation can be inspected and argued with before it is wired in.

The figures below carry no evidence. They are typed in here to make the demo
runnable, and the report marks them as such — which is exactly what the app
will do with any parameter no source could support.
"""
import sys

from app.market import ASSUMPTIONS, batch, config, firm, sensitivity
from app.parameters import PARAMETERS


DEMO_FACTS = dict(market_size=500_000, arpu=19, cac=40, churn_monthly=0.04, cpm=12.5, sales_cycle_days=90)
SEEDS = list(range(200))


def money(value):
    return f'{value:>14,.0f}'


def show_inputs():
    print('SÜBUT VƏZİYYƏTİ')
    for key, (label, _, unit) in PARAMETERS.items():
        print(f'  [SÜBUTSUZ] {label:<32} {DEMO_FACTS[key]:>12,.4g}  {unit:<18} əl ilə daxil edilib')
    print('\n  Heç bir parametr mənbə ilə təsdiqlənməyib, ona görə aşağıdakı nəticə')
    print('  bazar haqqında deyil, yalnız bu rəqəmlərin nəticəsi haqqındadır.\n')


def show_race(outcome, horizon, note):
    print(f'ARENA — {outcome["runs"]} təkrar, {horizon} ay, {note}')
    order = sorted(outcome['firms'].items(), key=lambda item: -item[1]['win_rate'])
    print(f'  {"Şirkət":<16}{"qalibiyyət":>12}{"sağqalma":>12}{"mənfəət p10":>16}{"median":>16}{"p90":>16}')
    for _, company in order:
        profit = company['profit']
        print(f'  {company["name"]:<16}{company["win_rate"]:>11.1%}{company["survival_rate"]:>12.1%}'
              f'{money(profit["p10"])}{money(profit["median"])}{money(profit["p90"])}')
    print(f'  Qalibsiz qaçışlar: {outcome["no_winner_rate"]:.1%}\n')


def show_sensitivity(settings):
    print('HƏSSASLIQ — nəticə hansı girişdən asılıdır?')
    keys = ['price_sensitivity', 'arpu', 'cac', 'churn_monthly', 'market_size']
    report = sorted((sensitivity(settings, SEEDS[:40], key) for key in keys),
                    key=lambda item: -item['worst_swing'])
    for item in report:
        origin = 'sübut' if item['pool'] == 'parameters' else 'fərziyyə'
        print(f'  {item["key"]:<20}{item["worst_swing"]:>7.0%} çevrilmə   ({origin})')
    worst = report[0]
    print(f'\n  Ən kövrək nöqtə: {worst["key"]}. Yarıdan ikiqata qədər dəyişəndə qalib '
          f'{worst["worst_swing"]:.0%} çevrilir.')
    print('  Növbəti simulyasiyadan əvvəl ölçülməli olan budur.\n')


def main():
    # The Windows console still defaults to cp1252, which cannot print Azerbaijani.
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    teams = [firm('cheap', 'Ucuz qiymət', 'cheap', 600_000),
             firm('prem', 'Premium', 'premium', 600_000),
             firm('b2b', 'Məktəb B2B', 'b2b', 600_000)]
    print('\nFƏRZİYYƏ ARENASI — bazar mühərriki\n' + '=' * 78 + '\n')
    show_inputs()
    calm = config(DEMO_FACTS, teams, horizon=36)
    show_race(batch(calm, SEEDS), 36, 'böhransız')
    shocked = config(DEMO_FACTS, teams, horizon=36,
                     crises=[dict(kind='cpm_shock', step=8, factor=2.5)])
    show_race(batch(shocked, SEEDS), 36, 'reklam qiyməti 8-ci ayda 2.5x')
    show_sensitivity(calm)
    print('MODEL FƏRZİYYƏLƏRİ (sübut deyil, mübahisə üçün açıqdır)')
    for key, value in ASSUMPTIONS.items():
        print(f'  {key:<28}{value}')
    print('\nEyni seed hər dəfə eyni nəticəni verir. Nəticə proqnoz deyil:')
    print('fərziyyələr səhv çıxsa nəticənin nə qədər dəyişdiyini göstərir.\n')


if __name__ == '__main__':
    main()
