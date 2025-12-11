import unittest
import sys
import os


def run_tests():
    """
    Runs the full test suite with verbose output (verbosity=2).
    Ensures 'tests_output' directory exists.
    """
    # 1. Ensure Output Directory
    output_dir = os.path.abspath("tests_output")
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created output directory: {output_dir}")

    # 2. Discover Tests
    loader = unittest.TestLoader()
    start_dir = os.path.abspath("tests")
    suite = loader.discover(start_dir)

    # 3. Run with Verbosity
    print("\n🚀 Running WebScraperToolkit Evaluation Suite...\n")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # 4. Exit Code
    if result.wasSuccessful():
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    run_tests()
