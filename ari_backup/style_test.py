import os
import unittest


REPO_PATH = os.path.dirname(os.path.join(os.path.dirname(__file__), '..'))


class StyleTest(unittest.TestCase):
    """
    This test class contains code style enforcement tests.

    If this test fails, please make sure you are in compliance with PEP-8[0].
    The test should have printed the problems to the screen when you ran
    "python setup.py test", but you can also manually invoke this test by
    running "flake8 ." at the root of this repository.

    [0] https://www.python.org/dev/peps/pep-0008/
    """
    def test_pep8(self):
        """This test makes sure the code is PEP-8 compliant."""
        self.assertEqual(os.system('flake8 {}'.format(REPO_PATH)), 0)


if __name__ == '__main__':
    unittest.main()
