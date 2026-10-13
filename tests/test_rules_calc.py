"""Unit tests for the corpus index, date boundaries and fee arithmetic.

Run: python -m unittest discover -s tests
"""
import unittest
from datetime import date
from decimal import Decimal

from policy_assistant import rules
from policy_assistant.calc import compute_fee, inr
from policy_assistant.corpus import CIRCULAR, FAQ, MASTER, cite, corpus, faq_cite


class CorpusTests(unittest.TestCase):
    def test_master_clauses_parsed(self):
        self.assertEqual(len(corpus()[MASTER]), 17)  # 3 + 4 + 4 + 4 + 2
        self.assertIn("2.4", corpus()[MASTER])

    def test_circular_items_parsed_with_continuation(self):
        items = corpus()[CIRCULAR]
        self.assertEqual(sorted(items), list("ABCDEF"))
        self.assertIn("01 September 2026", items["D"])

    def test_faq_has_five_questions(self):
        self.assertEqual(len(corpus()[FAQ]), 5)
        faq_cite("UPI transaction")

    def test_never_invent_clause(self):
        with self.assertRaises(KeyError):
            cite(MASTER, "6.1")
        with self.assertRaises(KeyError):
            cite(CIRCULAR, "G")


class DateBoundaryTests(unittest.TestCase):
    def test_before_master(self):
        with self.assertRaises(rules.PolicyNotInForce):
            rules.upi_settlement(date(2025, 12, 31))

    def test_circular_issued_but_not_effective(self):
        t = rules.mdr_terms(date(2026, 7, 25), large=False)
        self.assertEqual(t.value["rate"], Decimal("0.003"))
        self.assertEqual(t.value["cap"], Decimal("15"))

    def test_circular_effective_first_day(self):
        t = rules.mdr_terms(date(2026, 8, 1), large=True)
        self.assertEqual(t.value["cap"], Decimal("25"))
        small = rules.mdr_terms(date(2026, 8, 1), large=False)
        self.assertEqual(small.value["rate"], Decimal("0.0025"))

    def test_refund_reversal_switches_on_1_sep(self):
        self.assertTrue(rules.refund_mdr_reversed(date(2026, 8, 31), 3).value)
        self.assertFalse(rules.refund_mdr_reversed(date(2026, 9, 1), 3).value)

    def test_refund_after_24h_not_reversed(self):
        self.assertFalse(rules.refund_mdr_reversed(date(2026, 8, 20), 25).value)
        self.assertTrue(rules.refund_mdr_reversed(date(2026, 8, 20), 24).value)

    def test_band_boundary_exactly_10_lakh_is_small(self):
        self.assertFalse(rules.is_large(Decimal("1000000")))
        self.assertTrue(rules.is_large(Decimal("1000001")))


class FeeTests(unittest.TestCase):
    def test_q2_large_4000_after_aug(self):
        f = compute_fee(4000, Decimal("0.005"), Decimal("25"))
        self.assertEqual((f.mdr, f.gst, f.total), (Decimal("20.00"), Decimal("3.60"), Decimal("23.60")))
        self.assertFalse(f.capped)

    def test_q2_large_4000_before_aug_hits_old_cap(self):
        f = compute_fee(4000, Decimal("0.005"), Decimal("15"))
        self.assertEqual((f.mdr, f.gst), (Decimal("15.00"), Decimal("2.70")))

    def test_q3_large_150000_capped(self):
        f = compute_fee(150000, Decimal("0.005"), Decimal("25"))
        self.assertEqual((f.mdr, f.gst, f.total), (Decimal("25.00"), Decimal("4.50"), Decimal("29.50")))
        self.assertTrue(f.capped)

    def test_rounding_half_up(self):
        f = compute_fee(1001, Decimal("0.0025"), Decimal("15"))  # 2.5025 -> 2.50
        self.assertEqual(f.mdr, Decimal("2.50"))
        self.assertEqual(f.gst, Decimal("0.45"))

    def test_inr_format(self):
        self.assertEqual(inr(Decimal("150000")), "₹1,50,000")
        self.assertEqual(inr(Decimal("23.60")), "₹23.60")
        self.assertEqual(inr(Decimal("10000000")), "₹1,00,00,000")


if __name__ == "__main__":
    unittest.main()
