"""
Payslip Checker

Reads payslip JSON files and reports overpayment, underpayment, or correct pay.
Can check a single file or scan the whole payslips/ folder.

Usage:
    python payslips/checker.py                          # check all payslips
    python payslips/checker.py --file PS-2024-002.json  # check one payslip
    python payslips/checker.py --summary                # summary table only
"""

import sys
import json
import argparse
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PAYSLIP_DIR = Path(__file__).parent

STATUS_ICON = {
    "correct":   "OK",
    "underpaid": "UNDERPAID",
    "overpaid":  "OVERPAID",
}

# ---------------------------------------------------------------------------
# Checker
# ---------------------------------------------------------------------------

def check_payslip(ps: dict, verbose: bool = True) -> dict:
    audit  = ps["audit"]
    emp    = ps["employee"]
    period = ps["pay_period"]
    paid   = ps["paid"]

    status   = audit["status"]
    variance = audit["variance"]
    issues   = audit["issues"]

    result = {
        "payslip_id":  ps["payslip_id"],
        "employee":    emp["name"],
        "period":      f"{period['start']} → {period['end']}",
        "calculated":  audit["calculated_gross"],
        "paid":        audit["paid_gross"],
        "variance":    variance,
        "variance_pct":audit["variance_pct"],
        "status":      status,
        "issues":      issues,
    }

    if not verbose:
        return result

    icon  = STATUS_ICON[status]
    sign  = "+" if variance > 0 else ""

    print(f"\n  Payslip  : {ps['payslip_id']}")
    print(f"  Employee : {emp['name']}  ({emp['employment_type'].replace('_', '-')})")
    print(f"  Period   : {period['start']} to {period['end']}")
    print(f"  Award    : {ps['award']['name']}")
    print(f"  Shifts   : {len(ps['shifts'])}")
    print(f"  ─────────────────────────────────────────")
    print(f"  Calculated (correct) : ${audit['calculated_gross']:.2f}")
    print(f"  Actually paid        : ${audit['paid_gross']:.2f}")
    print(f"  Variance             : {sign}${abs(variance):.2f}  ({sign}{audit['variance_pct']:.2f}%)")
    print(f"  Status               : {icon}")

    if issues:
        print(f"  ─────────────────────────────────────────")
        print(f"  Issues found:")
        for issue in issues:
            print(f"    - {issue}")

    if paid.get("notes"):
        print(f"  ─────────────────────────────────────────")
        print(f"  Pay note : {paid['notes']}")

    return result


def check_all(folder: Path, summary_only: bool = False) -> list[dict]:
    files = sorted(folder.glob("PS-*.json"))
    if not files:
        print("  No payslip files found.")
        return []

    results = []
    for f in files:
        with open(f, encoding="utf-8") as fh:
            ps = json.load(fh)
        results.append(check_payslip(ps, verbose=not summary_only))

    # Summary table
    print(f"\n  {'='*65}")
    print(f"  {'PAYSLIP AUDIT SUMMARY':^63}")
    print(f"  {'='*65}")
    print(f"  {'ID':<16} {'Employee':<16} {'Period':<26} {'Variance':>10}  Status")
    print(f"  {'-'*65}")
    for r in results:
        sign = "+" if r["variance"] > 0 else ""
        icon = STATUS_ICON[r["status"]]
        print(f"  {r['payslip_id']:<16} {r['employee']:<16} {r['period']:<26} "
              f"{sign}${abs(r['variance']):.2f}{'':>3}  {icon}")

    correct   = sum(1 for r in results if r["status"] == "correct")
    underpaid = sum(1 for r in results if r["status"] == "underpaid")
    overpaid  = sum(1 for r in results if r["status"] == "overpaid")
    total_variance = sum(r["variance"] for r in results)

    print(f"  {'-'*65}")
    print(f"  Total: {len(results)}  |  Correct: {correct}  |  "
          f"Underpaid: {underpaid}  |  Overpaid: {overpaid}")
    sign = "+" if total_variance > 0 else ""
    print(f"  Net variance across all payslips: {sign}${total_variance:.2f}")
    print(f"  {'='*65}\n")

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check payslips for overpay/underpay")
    parser.add_argument("--file",    help="Check a single payslip file by name (e.g. PS-2024-002.json)")
    parser.add_argument("--summary", action="store_true", help="Print summary table only")
    args = parser.parse_args()

    print("\n" + "="*50)
    print("  Payslip Checker")
    print("="*50)

    if args.file:
        path = PAYSLIP_DIR / args.file
        with open(path, encoding="utf-8") as f:
            ps = json.load(f)
        check_payslip(ps, verbose=True)
        print()
    else:
        check_all(PAYSLIP_DIR, summary_only=args.summary)
