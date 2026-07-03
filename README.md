# cfn-express-agent-demo

A minimal Bedrock tool-use agent that designs, deploys, and self-heals an AWS
CloudFormation stack using [CloudFormation Express mode](https://aws.amazon.com/blogs/aws/accelerate-your-infrastructure-deployments-by-up-to-4x-with-aws-cloudformation-express-mode/)
(launched June 30, 2026), plus a controlled STANDARD vs EXPRESS benchmark on the
resulting template.

Write-up: see `BLOG_POST.md` for the full story, real timings, and a gotcha
around `OnFailure` + Express mode.

## What's here

- `deployer.py` — create/update/delete a CloudFormation stack via boto3, polling
  every second and returning terminal status + failure reasons (no `aws cloudformation
  wait`, which polls too slowly to measure Express mode accurately).
- `agent_loop.py` — a Bedrock Converse tool-use loop. The model gets one tool,
  `deploy_stack(template_yaml)`, and a goal in plain English. It writes the
  CloudFormation template itself, deploys with `DeploymentConfig={"Mode": "EXPRESS"}`,
  and — if the stack fails — gets the real `DescribeStackEvents` failure reasons
  back as the tool result so it can fix the template and redeploy.
- `benchmark.py` — takes a known-good template and runs N create+delete cycles in
  STANDARD mode and N in EXPRESS mode, back to back, to isolate the actual
  deployment-mode speed difference (not model latency or template quality).
- `final_template.yaml` — the template the agent produced (least-privilege IAM
  role, explicit log group, HTTP API + Lambda proxy integration, `GET /health`).

## Requirements

- AWS credentials with permission to create/delete `AWS::Lambda::Function`,
  `AWS::ApiGatewayV2::*`, `AWS::IAM::Role`, `AWS::Logs::LogGroup` (`CAPABILITY_NAMED_IAM`).
- `aws-cli` >= 2.35 (the `DeploymentConfig` parameter is not present in older
  builds — this is what actually gates Express mode support, not boto3 version).
- Bedrock model access to `us.anthropic.claude-sonnet-4-6` (or swap `MODEL_ID` in
  `agent_loop.py` for whatever Claude model your account has access to).

## Run it

```bash
python3 -m venv venv && source venv/bin/activate
pip install boto3 "botocore[crt]"

python3 agent_loop.py      # design + deploy + self-heal loop
python3 benchmark.py final_template.yaml   # STANDARD vs EXPRESS, 3 runs each
```

Both scripts create real stacks in `ap-northeast-1` (edit `CFN_REGION` in
`deployer.py` to change) and will leave the stack running until you delete it —
`benchmark.py` cleans up after itself, `agent_loop.py` does not.

## License

MIT
