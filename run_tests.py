import os
import sys
import unittest


def run_tests():
    """
    Runs all tests in the 'tests' directory with the correct PYTHONPATH.
    """
    # ensure 'src' is in python path
    project_root = os.path.dirname(os.path.abspath(__file__))
    src_path = os.path.join(project_root, "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

    # Discover and run tests
    loader = unittest.TestLoader()
    start_dir = os.path.join(project_root, "tests")
    suite = loader.discover(start_dir, pattern="test_*.py")

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    if not result.wasSuccessful():
        sys.exit(1)


if __name__ == "__main__":
    run_tests()
