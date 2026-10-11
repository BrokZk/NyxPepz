import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from referral_rewards import reward_units,points_from_units,UNITS_PER_POINT


class ReferralMathTests(unittest.TestCase):
    def test_first_and_next_rates(self):
        self.assertEqual(points_from_units(reward_units(10000,True)),10)
        self.assertEqual(points_from_units(reward_units(10000,False)),5)

    def test_small_amounts_keep_exact_fraction_units(self):
        first=reward_units(1005,True)
        second=reward_units(1005,False)
        self.assertEqual(first,2010)
        self.assertEqual(second,1005)
        self.assertEqual(points_from_units(first+second),1.5075)
        self.assertEqual(reward_units(1,False),1)
        self.assertEqual(points_from_units(1),0.0005)

    def test_existing_points_can_be_kept_as_a_base(self):
        old=7*UNITS_PER_POINT
        self.assertEqual(points_from_units(old+reward_units(10000,True)),17)

    def test_invalid_amounts_are_rejected(self):
        for value in (-1,True,10.5,"1000",10000001,None):
            with self.assertRaises(ValueError):
                reward_units(value,True)
        with self.assertRaises(ValueError):
            reward_units(100,"yes")


if __name__=="__main__":unittest.main()
