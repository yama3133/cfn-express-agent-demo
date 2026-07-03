"""Part A: let a Bedrock agent write, deploy, and self-heal a CloudFormation stack
using Express mode for the fast iterate-fail-fix-redeploy loop.
"""
import json
import time
import boto3

import deployer

BEDROCK_REGION = "us-east-1"
MODEL_ID = "us.anthropic.claude-sonnet-4-6"
STACK_NAME = "cfn-express-agent-demo"
MAX_ITERATIONS = 8

GOAL = """\
Design and deploy a single AWS CloudFormation template (YAML) for a small serverless API:

- An AWS::Lambda::Function (Python 3.13 runtime) whose handler returns a 200 response
  with JSON body {"status": "ok"} for any request.
- A dedicated AWS::IAM::Role for the function that follows least privilege: do NOT use
  the AWSLambdaBasicExecutionRole managed policy. Instead attach an inline policy that
  grants exactly the CloudWatch Logs permissions the function needs, scoped to its own
  log group ARN.
- An explicit AWS::Logs::LogGroup for the function's log group with a 7-day retention
  period, created before the function depends on it.
- An Amazon API Gateway HTTP API (AWS::ApiGatewayV2::Api, ProtocolType=HTTP) with a
  GET /health route wired to the Lambda function via an AWS_PROXY integration, an
  explicit $default stage with AutoDeploy enabled, and an AWS::Lambda::Permission that
  allows this specific API to invoke the function.
- Output the invoke URL for the /health endpoint.

Use the deploy_stack tool to deploy this template. If the deployment fails, read the
failure reasons carefully, fix the template, and call deploy_stack again with the
corrected full template. Keep iterating until the tool reports status CREATE_COMPLETE
or UPDATE_COMPLETE. Then stop and summarize what happened, including how many attempts
it took and what each failure was caused by.
"""

TOOL_CONFIG = {
    "tools": [
        {
            "toolSpec": {
                "name": "deploy_stack",
                "description": (
                    "Create or update the CloudFormation stack from the given template "
                    "body using Express mode, and poll until it reaches a terminal "
                    "status. Returns status, elapsed seconds, and failure reasons if any."
                ),
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "template_yaml": {
                                "type": "string",
                                "description": "The complete CloudFormation template body, in YAML.",
                            }
                        },
                        "required": ["template_yaml"],
                    }
                },
            }
        }
    ]
}


def log_event(f, obj):
    f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    f.flush()


def main():
    bedrock = boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)
    messages = [{"role": "user", "content": [{"text": GOAL}]}]

    with open("run_log.jsonl", "w") as logf, open("templates_history.md", "w") as tplf:
        iteration = 0
        t_wall_start = time.time()
        final_status = None

        while iteration < MAX_ITERATIONS:
            resp = bedrock.converse(
                modelId=MODEL_ID,
                messages=messages,
                toolConfig=TOOL_CONFIG,
                inferenceConfig={"maxTokens": 4096, "temperature": 0.3},
            )
            output_message = resp["output"]["message"]
            messages.append(output_message)
            stop_reason = resp["stopReason"]

            text_parts = [b["text"] for b in output_message["content"] if "text" in b]
            if text_parts:
                print("\n--- assistant ---\n" + "\n".join(text_parts))

            if stop_reason != "tool_use":
                final_status = "agent_stopped"
                break

            tool_results = []
            for block in output_message["content"]:
                if "toolUse" not in block:
                    continue
                tool_use = block["toolUse"]
                if tool_use["name"] != "deploy_stack":
                    continue

                iteration += 1
                template_yaml = tool_use["input"]["template_yaml"]
                print(f"\n=== iteration {iteration}: deploying (EXPRESS) ===")

                tplf.write(f"\n\n## Iteration {iteration}\n\n```yaml\n{template_yaml}\n```\n")

                t0 = time.time()
                result = deployer.deploy(
                    STACK_NAME, template_yaml, mode="EXPRESS", disable_rollback=True
                )
                result["iteration"] = iteration
                result["wall_time_s"] = time.time() - t0
                print(json.dumps({k: v for k, v in result.items() if k != "failures"}, indent=2))
                if result["failures"]:
                    print("failures:")
                    for f in result["failures"]:
                        print(" -", f)

                log_event(logf, {
                    "iteration": iteration,
                    "mode": "EXPRESS",
                    "status": result["status"],
                    "elapsed_s": round(result["elapsed_s"], 2),
                    "action": result["action"],
                    "failures": result["failures"],
                    "template_chars": len(template_yaml),
                })

                tool_result_text = json.dumps({
                    "status": result["status"],
                    "elapsed_s": round(result["elapsed_s"], 2),
                    "action": result["action"],
                    "failures": result["failures"],
                })
                tool_results.append({
                    "toolResult": {
                        "toolUseId": tool_use["toolUseId"],
                        "content": [{"text": tool_result_text}],
                        "status": "error" if result["status"] not in deployer.TERMINAL_OK else "success",
                    }
                })

                if result["status"] in deployer.TERMINAL_OK:
                    final_status = result["status"]

            messages.append({"role": "user", "content": tool_results})

            if final_status in deployer.TERMINAL_OK:
                # let the model produce its final summary, then stop after next turn
                resp = bedrock.converse(
                    modelId=MODEL_ID,
                    messages=messages,
                    toolConfig=TOOL_CONFIG,
                    inferenceConfig={"maxTokens": 4096, "temperature": 0.3},
                )
                summary_msg = resp["output"]["message"]
                for b in summary_msg["content"]:
                    if "text" in b:
                        print("\n--- final summary ---\n" + b["text"])
                messages.append(summary_msg)
                break

        total_wall = time.time() - t_wall_start
        print(f"\n=== done: {iteration} iteration(s), total wall time {total_wall:.1f}s, final_status={final_status} ===")

        log_event(logf, {
            "summary": True,
            "iterations": iteration,
            "total_wall_s": round(total_wall, 2),
            "final_status": final_status,
        })

    with open("final_conversation.json", "w") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2, default=str)


if __name__ == "__main__":
    main()
