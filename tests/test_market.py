import json
import unittest

from app.market import ASSUMPTIONS, batch, config, firm, run, sensitivity


FACTS = dict(market_size=500_000, arpu=19, cac=40, churn_monthly=0.04, cpm=12.5, sales_cycle_days=90)
SEEDS = list(range(120))


def three(cash=600_000):
    return [firm('cheap', 'Ucuz', 'cheap', cash),
            firm('prem', 'Premium', 'premium', cash),
            firm('b2b', 'Məktəb', 'b2b', cash)]


class ContractTest(unittest.TestCase):
    def test_missing_evidence_blocks_the_simulation(self):
        with self.assertRaises(ValueError) as caught:
            config({k: v for k, v in FACTS.items() if k != 'cac'}, three())
        self.assertIn('cac', str(caught.exception))

    def test_rejects_unusable_setups(self):
        with self.assertRaises(ValueError):
            firm('x', 'X', 'uydurma', 1000)
        with self.assertRaises(ValueError):
            firm('x', 'X', 'cheap', 0)
        with self.assertRaises(ValueError):
            config(FACTS, three(), horizon=3)
        with self.assertRaises(ValueError):
            config(FACTS, three(), crises=[dict(kind='meteor', step=2)])
        with self.assertRaises(ValueError):
            batch(config(FACTS, three()), [])

    def test_strategy_sets_price_and_budget_when_unset(self):
        result = run(config(FACTS, three()), 1)
        self.assertAlmostEqual(result['firms']['cheap']['price'], 19 * 0.6, places=4)
        self.assertGreater(result['firms']['prem']['price'], result['firms']['cheap']['price'])


class ReproducibilityTest(unittest.TestCase):
    def test_same_seed_gives_identical_history(self):
        settings = config(FACTS, three())
        self.assertEqual(json.dumps(run(settings, 7)), json.dumps(run(settings, 7)))

    def test_different_seeds_give_different_histories(self):
        settings = config(FACTS, three())
        self.assertNotEqual(json.dumps(run(settings, 7)), json.dumps(run(settings, 8)))

    def test_no_firm_ordering_advantage(self):
        twins = [firm('a', 'A', 'cheap', 600_000), firm('b', 'B', 'cheap', 600_000)]
        rates = batch(config(FACTS, twins), SEEDS)['firms']
        self.assertAlmostEqual(rates['a']['win_rate'], 0.5, delta=0.15)
        self.assertAlmostEqual(rates['b']['win_rate'], 0.5, delta=0.15)


class MarketBoundsTest(unittest.TestCase):
    def test_nobody_sells_beyond_the_evidenced_market(self):
        result = run(config(FACTS, three()), 5)
        seats = sum(f['customers'] * (ASSUMPTIONS['seats_per_institution'] if f['strategy'] == 'b2b' else 1)
                    for f in result['firms'].values())
        self.assertLessEqual(seats, FACTS['market_size'])

    def test_budget_bounds_acquisition_at_the_evidenced_cost(self):
        small = run(config(FACTS, [firm('a', 'A', 'cheap', 200_000)]), 2)['firms']['a']
        large = run(config(FACTS, [firm('a', 'A', 'cheap', 800_000)]), 2)['firms']['a']
        self.assertGreater(large['acquired'], small['acquired'])
        self.assertGreaterEqual(small['cac_realised'], FACTS['cac'] * 0.25)

    def test_institutional_sales_cycle_delays_first_customers(self):
        slow = dict(FACTS, sales_cycle_days=180)
        result = run(config(slow, [firm('b2b', 'Məktəb', 'b2b', 900_000)]), 4)
        self.assertEqual(result['history'][3]['b2b']['customers'], 0)
        self.assertGreater(result['firms']['b2b']['customers'], 0)

    def test_win_rates_and_no_winner_account_for_every_run(self):
        outcome = batch(config(FACTS, three()), SEEDS[:40])
        total = sum(f['win_rate'] for f in outcome['firms'].values()) + outcome['no_winner_rate']
        self.assertAlmostEqual(total, 1.0, places=6)


class CrisisTest(unittest.TestCase):
    def duel(self, crises=()):
        pair = [firm('ads', 'Reklam', 'cheap', 600_000), firm('dir', 'Birbaşa', 'b2b', 600_000)]
        return batch(config(FACTS, pair, crises=crises), SEEDS[:60])['firms']

    def test_ad_price_shock_hits_the_paid_channel_hardest(self):
        calm = self.duel()
        shocked = self.duel([dict(kind='cpm_shock', step=4, factor=3.0)])
        self.assertGreater(calm['ads']['win_rate'], shocked['ads']['win_rate'])
        self.assertGreater(shocked['dir']['win_rate'], calm['dir']['win_rate'])

    def test_funding_cut_removes_cash(self):
        settings = config(FACTS, three(), crises=[dict(kind='funding_cut', step=2, factor=0.1, firm_id='prem')])
        cut = run(settings, 1)['history'][2]['prem']['cash']
        intact = run(config(FACTS, three()), 1)['history'][2]['prem']['cash']
        self.assertLess(cut, intact)

    def test_entrant_joins_mid_game(self):
        settings = config(FACTS, three(), crises=[dict(kind='entrant', step=10, id='late', strategy='cheap')])
        result = run(settings, 1)
        self.assertNotIn('late', result['history'][9])
        self.assertIn('late', result['firms'])

    def test_broken_unit_economics_bankrupt_everyone(self):
        doomed = dict(FACTS, cac=400, churn_monthly=0.15, sales_cycle_days=30)
        pair = [firm('a', 'A', 'cheap', 200_000), firm('b', 'B', 'premium', 200_000)]
        outcome = batch(config(doomed, pair), SEEDS[:40])
        self.assertEqual(outcome['firms']['a']['survival_rate'], 0.0)
        self.assertGreater(outcome['no_winner_rate'], 0.5)


class SensitivityTest(unittest.TestCase):
    def test_unknown_key_is_refused(self):
        with self.assertRaises(ValueError):
            sensitivity(config(FACTS, three()), SEEDS[:5], 'uydurma_parametr')

    def test_reports_one_point_per_factor(self):
        report = sensitivity(config(FACTS, three()), SEEDS[:15], 'arpu', factors=(0.5, 1.0, 2.0))
        self.assertEqual([p['factor'] for p in report['points']], [0.5, 1.0, 2.0])
        self.assertEqual(report['pool'], 'parameters')
        self.assertAlmostEqual(report['points'][2]['value'], FACTS['arpu'] * 2)

    def test_a_decisive_assumption_shows_a_wide_swing(self):
        report = sensitivity(config(FACTS, three()), SEEDS[:15], 'price_sensitivity', factors=(0.25, 1.0, 3.0))
        self.assertEqual(report['pool'], 'assumptions')
        self.assertGreater(report['worst_swing'], 0.5)

    def test_a_uniform_cost_shift_does_not_decide_the_race(self):
        report = sensitivity(config(FACTS, three()), SEEDS[:15], 'cac', factors=(0.5, 1.0, 2.0))
        self.assertLess(report['worst_swing'], 0.5)


if __name__ == '__main__':
    unittest.main()
