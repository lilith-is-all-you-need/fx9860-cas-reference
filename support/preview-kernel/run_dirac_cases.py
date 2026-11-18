"""Small public-C-ABI regression, using an existing real SH CLI in fresh processes."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess

CASES = [
    ("unit", "integrate(diff(Heaviside(x),x),x,-1,1)", "1"),
    ("positive_slope", "integrate(diff(Heaviside(2*x),x),x,-1,1)", "1"),
    ("negative_slope", "integrate(diff(Heaviside(-2*x),x),x,-1,1)", "-1"),
    ("shift_and_amplitude", "integrate(3*diff(Heaviside(2*x-1),x),x,-1,1)", "3"),
    ("polynomial_weight", "integrate((x+1)*diff(Heaviside(2*x-1),x),x,-1,1)", "3/2"),
    ("negative_polynomial_weight", "integrate((x+1)*diff(Heaviside(-2*x+1),x),x,-1,1)", "-3/2"),
    ("reverse", "integrate(diff(Heaviside(2*x),x),x,1,-1)", "-1"),
    ("outside", "integrate(diff(Heaviside(2*x-4),x),x,-1,1)", "0"),
    ("lower_endpoint_full_mass", "integrate(diff(Heaviside(2*x+2),x),x,-1,1)", "1"),
    ("upper_endpoint_full_mass", "integrate(diff(Heaviside(2*x-2),x),x,-1,1)", "1"),
    ("first_distribution_derivative", "integrate(x*diff(Heaviside(2*x),x,2),x,-1,1)", "-1"),
    ("negative_first_distribution_derivative", "integrate(x*diff(Heaviside(-2*x),x,2),x,-1,1)", "1"),
    ("shifted_distribution_derivative", "integrate((x^2+1)*diff(Heaviside(2*x-1),x,2),x,-1,1)", "-1"),
    ("second_distribution_derivative", "integrate(x^2*diff(Heaviside(2*x),x,3),x,-1,1)", "2"),
    ("negative_second_distribution_derivative", "integrate(x^2*diff(Heaviside(-2*x),x,3),x,-1,1)", "-2"),
    ("unscaled_distribution_derivative", "integrate(x*diff(Heaviside(x),x,2),x,-1,1)", "-1"),
    ("constant_polynomial_derivative", "integrate(diff(Heaviside(2*x),x,2),x,-1,1)", "0"),
    ("rational_slope", "integrate(diff(Heaviside(x/2-1/4),x),x,-1,1)", "1"),
    ("zero_slope", "integrate(diff(Heaviside(0*x+1),x),x,-1,1)", "0"),
    ("ordinary_integral", "integrate(3*x^2+2*x+1,x,-1,2)", "15"),
    ("recovery_arithmetic", "7*8+1", "57"),
    ("unknown_slope", "integrate(diff(Heaviside(a*x),x),x,-1,1)", "symbolic"),
    ("unknown_support", "integrate(diff(Heaviside(2*x-a),x),x,-1,1)", "symbolic"),
    ("derivative_endpoint_refusal", "integrate(x*diff(Heaviside(x+1),x,2),x,-1,1)", "symbolic"),
    ("nonsmooth_derivative_refusal", "integrate(abs(x)*diff(Heaviside(x),x,2),x,-1,1)", "symbolic"),
    ("pole_weight_refusal", "integrate(diff(Heaviside(x),x)/x,x,-1,1)", "symbolic"),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--elf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--qemu", default="qemu-sh4eb")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    rows = []
    env = dict(os.environ, LD_LIBRARY_PATH="/opt/khicas-host/lib/x86_64-linux-gnu")
    for name, expression, expected in CASES:
        input_line = ("normal(" + expression + ")\n")
        command = [args.qemu, str(args.elf)]
        result = subprocess.run(command, input=input_line, capture_output=True,
                                text=True, timeout=40, env=env)
        actual = None
        try:
            actual = json.loads(result.stdout.strip())
        except (ValueError, TypeError):
            pass
        passed = result.returncode == 0 and actual is not None and actual["status"] == 0
        if passed:
            passed = ("integrate(" in actual["result"] if expected == "symbolic"
                      else actual["result"] == expected)
        rows.append(dict(name=name, input=input_line.strip(), expected=expected,
                         passed=passed, exit_code=result.returncode,
                         actual=actual, stdout=result.stdout, stderr=result.stderr))
    report = dict(label=args.label, command=[args.qemu, str(args.elf)],
                  elf_sha256=hashlib.sha256(args.elf.read_bytes()).hexdigest(),
                  physical_arena_bytes=32768, tracked_limit_bytes=24576,
                  evidence="Real accepted SH C ABI with CPU emulation; no hardware claim",
                  passed=sum(row["passed"] for row in rows), total=len(rows), cases=rows)
    (args.output / (args.label + ".json")).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"label":args.label,"passed":report["passed"],"total":report["total"],
                      "failures":[dict(name=r["name"],actual=r["actual"],expected=r["expected"])
                                  for r in rows if not r["passed"]]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
