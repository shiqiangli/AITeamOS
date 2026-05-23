import unittest

from src.pure_function import add_i32


class PureFunctionTest(unittest.TestCase):
    def test_preserves_operand_order(self) -> None:
        self.assertEqual(add_i32("lhs", "rhs"), "runtime.add_i32(lhs, rhs)")


if __name__ == "__main__":
    unittest.main()
