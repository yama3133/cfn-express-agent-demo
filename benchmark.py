"""Part B: controlled STANDARD vs EXPRESS benchmark using one known-good template,
repeated create+delete cycles, to isolate the pure deployment-mode speed difference.
"""
import json
import sys
import time

import deployer

STACK_NAME = "cfn-express-benchmark"
RUNS_PER_MODE = 3


def run(template_path: str, runs_per_mode: int = RUNS_PER_MODE):
    with open(template_path) as f:
        template = f.read()

    results = []
    for mode in ["STANDARD", "EXPRESS"]:
        for i in range(runs_per_mode):
            print(f"\n=== {mode} run {i + 1}/{runs_per_mode} ===")
            deploy_res = deployer.deploy(
                STACK_NAME, template, mode=mode, disable_rollback=(mode == "EXPRESS")
            )
            print(json.dumps({k: v for k, v in deploy_res.items() if k != "failures"}, indent=2))
            if deploy_res["failures"]:
                for fmsg in deploy_res["failures"]:
                    print(" -", fmsg)

            delete_res = deployer.delete(STACK_NAME)
            print("delete:", json.dumps(delete_res, indent=2))

            results.append({
                "mode": mode,
                "run": i + 1,
                "deploy_status": deploy_res["status"],
                "deploy_elapsed_s": round(deploy_res["elapsed_s"], 2),
                "delete_status": delete_res["status"],
                "delete_elapsed_s": round(delete_res["elapsed_s"], 2),
            })

    with open("benchmark_results.json", "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print("\n=== summary ===")
    for mode in ["STANDARD", "EXPRESS"]:
        deploys = [r["deploy_elapsed_s"] for r in results if r["mode"] == mode and r["deploy_status"] in deployer.TERMINAL_OK]
        if deploys:
            print(f"{mode}: n={len(deploys)} avg_deploy_s={sum(deploys)/len(deploys):.2f} runs={deploys}")
        else:
            print(f"{mode}: no successful runs -> {[r['deploy_status'] for r in results if r['mode']==mode]}")

    return results


if __name__ == "__main__":
    tpl = sys.argv[1] if len(sys.argv) > 1 else "final_template.yaml"
    run(tpl)
