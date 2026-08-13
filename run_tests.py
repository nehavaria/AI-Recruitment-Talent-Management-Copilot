"""
run_tests.py — Test runner for the AI Recruitment & Talent Management Copilot.

Usage:
    python run_tests.py                  # run all tests
    python run_tests.py --module 1       # run only Module 1 (MySQL connection)
    python run_tests.py --module 5       # run only Module 5 (hiring score)
    python run_tests.py --fast           # skip slow STT tests
    python run_tests.py --unit           # run only pure unit tests (no DB)
    python run_tests.py --integration    # run only DB integration tests
    python run_tests.py --workflow       # run only the end-to-end workflow test
    python run_tests.py --coverage       # run with HTML coverage report
"""

import sys
import subprocess
import argparse

MODULE_MAP = {
    1:  "tests/test_01_mysql_connection.py",
    2:  "tests/test_02_candidate_retrieval.py",
    3:  "tests/test_03_job_retrieval.py",
    4:  "tests/test_04_candidate_status_updates.py",
    5:  "tests/test_05_hiring_score.py",
    6:  "tests/test_06_dashboard_metrics.py",
    7:  "tests/test_07_08_09_search_filter_sort.py",
    8:  "tests/test_07_08_09_search_filter_sort.py",
    9:  "tests/test_07_08_09_search_filter_sort.py",
    10: "tests/test_10_candidate_profile.py",
    11: "tests/test_11_interview_report.py",
    12: "tests/test_12_15_voice_and_evaluation.py",
    13: "tests/test_12_15_voice_and_evaluation.py",
    14: "tests/test_12_15_voice_and_evaluation.py",
    15: "tests/test_12_15_voice_and_evaluation.py",
    16: "tests/test_16_complete_workflow.py",
}

MODULE_NAMES = {
    1:  "MySQL Connection",
    2:  "Candidate Retrieval",
    3:  "Job Retrieval",
    4:  "Candidate Status Updates",
    5:  "Hiring Score Calculation",
    6:  "Dashboard Metrics",
    7:  "Search",
    8:  "Filtering",
    9:  "Sorting",
    10: "Candidate Profile",
    11: "Interview Report",
    12: "Voice Recording",
    13: "Speech-to-Text",
    14: "Voice Answer Storage",
    15: "Interview Evaluation",
    16: "Complete Recruitment Workflow",
}


def main():
    parser = argparse.ArgumentParser(description="AI Recruitment Copilot Test Runner")
    parser.add_argument("--module",      type=int, help="Run a specific module (1-16)")
    parser.add_argument("--fast",        action="store_true", help="Skip slow tests")
    parser.add_argument("--unit",        action="store_true", help="Unit tests only (no DB)")
    parser.add_argument("--integration", action="store_true", help="Integration tests only")
    parser.add_argument("--workflow",    action="store_true", help="End-to-end workflow only")
    parser.add_argument("--coverage",    action="store_true", help="Generate HTML coverage report")
    args = parser.parse_args()

    cmd = [sys.executable, "-m", "pytest"]

    if args.coverage:
        cmd += ["--cov=.", "--cov-report=html:htmlcov", "--cov-report=term-missing"]

    if args.module:
        path = MODULE_MAP.get(args.module)
        if not path:
            print(f"Unknown module: {args.module}. Valid range: 1-16")
            sys.exit(1)
        name = MODULE_NAMES[args.module]
        print(f"\n{'='*60}")
        print(f"  Running Module {args.module}: {name}")
        print(f"{'='*60}\n")
        cmd.append(path)
    elif args.unit:
        cmd += ["-m", "unit"]
    elif args.integration:
        cmd += ["-m", "integration"]
    elif args.workflow:
        cmd.append("tests/test_16_complete_workflow.py")
    elif args.fast:
        cmd += ["-m", "not slow"]
    else:
        print("\n" + "="*60)
        print("  Running ALL 16 Test Modules")
        print("="*60)
        print("\nModules:")
        for num, name in MODULE_NAMES.items():
            print(f"  {num:2d}. {name}")
        print()
        cmd.append("tests/")

    result = subprocess.run(cmd)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
