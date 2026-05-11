"""
Unit tests for lobster_claw.solve.

Run:
    python3 -m pytest test_lobster_claw.py -v
or:
    python3 test_lobster_claw.py
"""

from __future__ import annotations
import unittest
from lobster_claw import solve, _tokenize, _clean, _fold_compound


class TestClean(unittest.TestCase):
    def test_strips_punctuation_and_lowercases(self) -> None:
        self.assertEqual(_clean("Five GAINS! seven."), "fivegainsseven")

    def test_keeps_plus_and_star(self) -> None:
        self.assertEqual(_clean("3+4*5"), "+*")  # digits stripped, + and * kept


class TestTokenize(unittest.TestCase):
    def test_simple_addition(self) -> None:
        self.assertEqual(
            _tokenize("fivegainsseven"),
            ["five", "gains", "seven"],
        )

    def test_compound_twenty_one(self) -> None:
        self.assertEqual(
            _tokenize("twentyone"),
            ["twenty", "one"],
        )

    def test_greedy_seventeen_not_seven_teen(self) -> None:
        # "seventeen" must match before "seven" + (no "teen" token).
        self.assertEqual(_tokenize("seventeen"), ["seventeen"])

    def test_skips_unknown_chars(self) -> None:
        # An unknown letter sequence between known tokens is ignored char by char.
        self.assertEqual(
            _tokenize("fivexxxgainsseven"),
            ["five", "gains", "seven"],
        )


class TestFoldCompound(unittest.TestCase):
    def test_single(self) -> None:
        self.assertEqual(_fold_compound(["seven"]), 7)

    def test_twenty_one(self) -> None:
        self.assertEqual(_fold_compound(["twenty", "one"]), 21)

    def test_two_hundred(self) -> None:
        self.assertEqual(_fold_compound(["two", "hundred"]), 200)

    def test_two_hundred_three(self) -> None:
        self.assertEqual(_fold_compound(["two", "hundred", "three"]), 203)

    def test_one_thousand_five_hundred_twenty_one(self) -> None:
        self.assertEqual(
            _fold_compound(["one", "thousand", "five", "hundred", "twenty", "one"]),
            1521,
        )

    def test_hundred_alone(self) -> None:
        # "hundred" with no leading multiplier should still mean 100.
        self.assertEqual(_fold_compound(["hundred"]), 100)


class TestSolve(unittest.TestCase):
    def test_basic_addition(self) -> None:
        self.assertEqual(solve("five gains seven"), "12.00")

    def test_basic_subtraction(self) -> None:
        self.assertEqual(solve("ten loses three"), "7.00")

    def test_molts_is_subtraction(self) -> None:
        self.assertEqual(solve("twenty molts five"), "15.00")

    def test_drops_is_subtraction(self) -> None:
        self.assertEqual(solve("twenty drops five"), "15.00")

    def test_adds_is_addition(self) -> None:
        self.assertEqual(solve("twenty adds five"), "25.00")

    def test_plus_word(self) -> None:
        self.assertEqual(solve("twenty plus five"), "25.00")

    def test_times_is_multiplication(self) -> None:
        self.assertEqual(solve("six times seven"), "42.00")

    def test_multiplied_is_multiplication(self) -> None:
        self.assertEqual(solve("six multiplied seven"), "42.00")

    def test_left_to_right_no_precedence(self) -> None:
        # 10 * 3 + 4  evaluated left-to-right -> 34.
        self.assertEqual(solve("ten times three plus four"), "34.00")
        # 2 + 3 * 4   evaluated left-to-right -> 20 (NOT 14).
        self.assertEqual(solve("two plus three times four"), "20.00")

    def test_compound_numbers(self) -> None:
        self.assertEqual(solve("twenty one gains three"), "24.00")
        self.assertEqual(solve("two hundred loses fifty"), "150.00")
        self.assertEqual(
            solve("one thousand five hundred plus twenty one"),
            "1521.00",
        )

    def test_and_inside_number_is_separator(self) -> None:
        self.assertEqual(solve("two hundred and three"), "203.00")
        self.assertEqual(solve("twenty and one gains seven"), "28.00")

    def test_punctuation_stripped(self) -> None:
        self.assertEqual(solve("Five GAINS! seven."), "12.00")
        self.assertEqual(solve("  twenty,, plus three??? "), "23.00")

    def test_missing_operands_raises(self) -> None:
        with self.assertRaises(ValueError):
            solve("foo bar baz")

    def test_negative_result_formats(self) -> None:
        self.assertEqual(solve("three loses ten"), "-7.00")

    def test_multiple_operations(self) -> None:
        # 100 - 30 - 20 + 5 = 55
        self.assertEqual(
            solve("one hundred loses thirty loses twenty plus five"),
            "55.00",
        )


class TestPostfixNouns(unittest.TestCase):
    """
    "what is the <product|sum|...> of A and B" was returning A+B (or weirder)
    before 2026-04-26. The real failing case was a Moltbook challenge whose
    only number tokens were "fourteen ... twenty six" with "product" appearing
    after both operands; the infix parser folded everything into one number
    via the no-op "and" joiner and gave 40.00 instead of 364.00.
    """

    def test_real_moltbook_product_challenge_2026_04_26(self) -> None:
        """The exact challenge that broke production — must return 364.00."""
        challenge = (
            "A] lO.oB sT-ErRr SwImS^ aT] fOuRtEeN mE-tErS pEr/ sEcOnD, "
            "aNd] iTs ClAw ExErTs~ tWeNtY sIx nEwToNs, "
            "wHaT iS tHe PrOdUcT< oF tHeSe?"
        )
        self.assertEqual(solve(challenge), "364.00")

    def test_product_of_two_simple_numbers(self) -> None:
        self.assertEqual(solve("what is the product of three and four"), "12.00")

    def test_sum_of_two_numbers(self) -> None:
        self.assertEqual(solve("what is the sum of fourteen and twenty six"), "40.00")

    def test_total_is_sum(self) -> None:
        self.assertEqual(solve("the total of seven and eight"), "15.00")

    def test_difference_of_two_numbers(self) -> None:
        self.assertEqual(
            solve("what is the difference between twenty and seven"),
            "13.00",
        )

    def test_quotient_of_two_numbers(self) -> None:
        self.assertEqual(solve("what is the quotient of twenty and four"), "5.00")

    def test_quotient_div_zero_falls_back_to_infix(self) -> None:
        # Postfix solver bails on /0 (returns None) and we fall through to
        # infix. Infix silently drops the unknown "quotient" token and folds
        # ["ten", "and", "zero"] -> 10. Documented here so future readers
        # don't mistake the behaviour for a bug: the verify endpoint will
        # simply reject the wrong answer; the verify-fail retry path in the
        # MCP then deletes the orphan post. Acceptable failure mode for a
        # non-sensical challenge ("divide by zero" should never be generated
        # by Moltbook's challenge generator in practice).
        self.assertEqual(solve("the quotient of ten and zero"), "10.00")

    def test_postfix_preserves_compound_after_magnitude(self) -> None:
        # "and" after "hundred" is still a compound joiner: 203 + 4 = 207.
        self.assertEqual(
            solve("the sum of two hundred and three and four"),
            "207.00",
        )

    def test_postfix_three_operands_product(self) -> None:
        self.assertEqual(
            solve("the product of two and three and four"),
            "24.00",
        )

    def test_postfix_three_operands_sum(self) -> None:
        self.assertEqual(
            solve("the sum of one and two and three"),
            "6.00",
        )

    def test_postfix_op_before_operands(self) -> None:
        # Operator-prefix phrasing should also work.
        self.assertEqual(solve("product: fourteen and twenty six"), "364.00")

    def test_postfix_with_one_operand_falls_back(self) -> None:
        # "the product of seven" — only one operand, postfix bails to infix.
        # Infix sees just "seven" → returns 7.00.
        self.assertEqual(solve("the product of seven"), "7.00")

    def test_ambiguous_two_distinct_postfix_ops_falls_back(self) -> None:
        # If "product" AND "sum" both appear, defer to infix (which here
        # finds no verbs and just returns the folded number).
        # "five and seven" with infix: "and" no-op, fold [5,7] = 12.
        self.assertEqual(
            solve("the product or sum of five and seven"),
            "12.00",
        )

    def test_existing_compound_unchanged(self) -> None:
        # Sanity: postfix code path must not alter pre-existing behaviour
        # when no postfix noun is present.
        self.assertEqual(solve("two hundred and three"), "203.00")
        self.assertEqual(solve("twenty and one gains seven"), "28.00")

    # --- trailing-verb override (added 2026-05-10) ---
    # Captured from co-founder review publish failure 2026-05-11 02:01 UTC:
    # postfix "total" gave 35+2=37 instead of the intended 35*2=70.
    # The trailing "please multiply" is the actual instruction.
    def test_trailing_multiply_overrides_total_noun(self) -> None:
        self.assertEqual(
            solve("first claw force is thirty five newtons and other claw "
                  "is two, what is the total force, please multiply?"),
            "70.00",
        )

    def test_trailing_subtract_overrides_total_noun(self) -> None:
        # Defensive: SUB verb at end should also override total→+.
        self.assertEqual(
            solve("lobster a has sixty newtons and lobster b has twenty, "
                  "what is the difference please subtract?"),
            "40.00",
        )

    def test_midsequence_multiplies_bypasses_postfix(self) -> None:
        # Captured from successful publish 2026-05-11 02:01 UTC after
        # persistent-script fix. The verb "multiplies" is NOT trailing —
        # it has an operand ("four") after it, so infix should compute
        # 32 * 4 = 128, NOT postfix("total"→"+") = 32+4 = 36.
        self.assertEqual(
            solve("claw force is thirty two newtons and during dominance "
                  "fight it multiplies by four, what's total force?"),
            "128.00",
        )

    # --- false-positive substring tests ---
    # The greedy tokenizer matches "sum" inside "summons", "summer", "consumed",
    # and "total" inside "totally". Without the whole-word filter these would
    # falsely trigger the postfix path and silently rewrite the operator.
    # All five challenges below MUST go through the infix path.

    def test_summons_does_not_trigger_postfix(self) -> None:
        # "summons" contains "sum". Infix sees number tokens only:
        # twenty + ten = 30 (and is no-op compound joiner).
        self.assertEqual(
            solve("the lobster summons twenty crabs and consumes ten"),
            "30.00",
        )

    def test_summer_does_not_trigger_postfix(self) -> None:
        # "summer" contains "sum". Infix: ten (molts is subtract but has no
        # second operand) -> just 10.
        self.assertEqual(solve("the lobster of summer molts ten"), "10.00")

    def test_totally_does_not_trigger_postfix(self) -> None:
        # "totally" contains "total". Infix should give 5 + 2 evaluated as
        # gains then loses: 5 - 2 = 3 (NOT postfix sum 7).
        self.assertEqual(
            solve("the lobster totally gains five and loses two"),
            "3.00",
        )

    def test_consumed_does_not_trigger_postfix(self) -> None:
        # "consumed" contains "sum". Infix: twenty + three = 23 ("ate" is not
        # a verb, "and" is no-op compound joiner) -> 23.
        self.assertEqual(
            solve("she consumed twenty fish and ate three"),
            "23.00",
        )

    def test_production_does_not_trigger_postfix(self) -> None:
        # "production" greedy-matches "product". Infix should give the
        # arithmetic without a phantom multiply.
        self.assertEqual(
            solve("the production line gains five and loses two"),
            "3.00",
        )


    def test_space_obfuscated_product_postfix(self) -> None:
        # "P]rO dUcT" has a SPACE inside the obfuscated token. Raw \b check fails
        # because the letters are split. Compact-clean ends with "product" →
        # compact-end fallback accepts it → postfix multiply applies.
        self.assertEqual(
            solve(
                "A] lO b-StEr S^wImS[ aT/ tW eN tY tHrEe MeTeR sPeR SeCoNd]"
                " aNd| iTs ClA w ExE rTs^ SeV eN N{eU}toNs, WhAt Is ThE P]rO dUcT?"
            ),
            "161.00",  # 23 * 7
        )


class TestSubstringFalsePositives(unittest.TestCase):
    """Regression for two production bugs fixed 2026-05-11.

    Bug 1 (antenna/ten): _tokenize greedily matched "ten" inside "antenna"
    (a-n-t-e-n-n-a) giving 35+22=57 instead of 35+12=47.
    Fix: _valid_numbers() pre-filter — only NUMBER_WORDS that appear as whole
    words in the original challenge are accepted by _tokenize().

    Bug 2 (doubled consonants: fIiVvE / tWwO): _clean() only collapsed
    repeated vowels (a/i/o/u), leaving "fivve" and "twwo" unrecognised.
    Fix: _clean() now collapses all non-'e' repeated chars so "fIiVvE" → "five"
    and "tWwO" → "two" before tokenisation.
    """

    def test_ten_inside_antenna_ignored(self) -> None:
        # "antenna" contains "ten" as a substring. Without the word-boundary
        # filter _tokenize extracts [thirty, five, +, ten, twelve, total] and
        # returns 35+10+12=57. Correct answer: 35+12=47.
        self.assertEqual(
            solve(
                "ThIrTy FiVe NoOtOnS] + An TeNnA ExErTs/ TwElVe NeWtOnS~ HoW{ MaNy }ToTaL?"
            ),
            "47.00",
        )

    def test_doubled_consonants_thirty_five_plus_twenty_two(self) -> None:
        # Heavy obfuscation: "fIiVvE" (doubled v) and "tWwO" (doubled w).
        # Before fix: _clean collapsed only vowels → "fivve"/"twwo" not found →
        # postfix path on partial tokens gave 30+20=50. Correct answer: 35+22=57.
        self.assertEqual(
            solve(
                "tHiRtY fIiVvE ~ nOoOtOnS, uMm } lOoOobSsStEr\\ cLaW| fOrCe~ "
                "iS tWeNtY tWwO < wHaT } iS~ tHe| ToTaL- FoRcE?"
            ),
            "57.00",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
