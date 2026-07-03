<!--
Suggested title: I Let an AI Agent Design, Deploy, and Fix Its Own AWS Stack with CloudFormation Express Mode
Suggested DEV.to tags: aws, cloudformation, ai, serverless
Suggested cover: a screenshot of the terminal output below (agent_loop_stdout.log) or the curl proof.
Canonical: post this same body to DEV.to and AWS Builder Center; set DEV.to's "canonical_url" to whichever you publish first if you want to avoid duplicate-content concerns.
-->

# I Let an AI Agent Design, Deploy, and Fix Its Own AWS Stack with CloudFormation Express Mode

On June 30, 2026, AWS announced [CloudFormation Express mode](https://aws.amazon.com/blogs/aws/accelerate-your-infrastructure-deployments-by-up-to-4x-with-aws-cloudformation-express-mode/): a new deployment mode that returns control as soon as CloudFormation has *applied* your resource configuration, instead of waiting for every resource to fully *stabilize*. AWS's own example shows an SQS queue + DLQ going from 64 seconds (Standard) to 10 seconds (Express).

The launch post specifically calls out a use case I couldn't resist: **AI agents building infrastructure**. If an agent is iterating on a CloudFormation template — deploy, read the error, fix, redeploy — every second of stabilization wait is a second the agent (and you) spend staring at a spinner. So I built the smallest possible version of that idea and pointed it at a real AWS account to see what actually happens, not what the launch post promises.

## The setup

A ~150-line Python harness, no agent framework:

- **Model**: Claude Sonnet 4.6 on Amazon Bedrock (`us.anthropic.claude-sonnet-4-6`), called through the Converse API with a single tool.
- **The only tool the model gets**: `deploy_stack(template_yaml)`. It creates-or-updates a real CloudFormation stack in `ap-northeast-1` using `DeploymentConfig={"Mode": "EXPRESS", "DisableRollback": true}`, polls `DescribeStacks` every second, and — if the stack lands in a failed state — pulls the failed `DescribeStackEvents` reasons back into the tool result.
- **The loop**: give the model a goal in plain English, let it call `deploy_stack` as many times as it needs, feed the failure reasons back as the tool result, and stop when the stack reaches `CREATE_COMPLETE` or `UPDATE_COMPLETE`.

```python
result = deployer.deploy(
    STACK_NAME, template_yaml, mode="EXPRESS", disable_rollback=True
)
# -> {"status": "CREATE_COMPLETE", "elapsed_s": 25.58, "action": "create", "failures": []}
```

No scaffolding, no pre-written template. The model has to write valid CloudFormation from a spec and live with the consequences of its own YAML.

## The brief I gave it

I didn't ask for a bare "hello world" Lambda — that's too easy to be interesting. The brief asked for a small but *opinionated* serverless API:

- A Lambda function (Python 3.13) behind an API Gateway HTTP API, `GET /health` → `{"status": "ok"}`.
- A **dedicated IAM role**, explicitly forbidding the `AWSLambdaBasicExecutionRole` managed policy — inline least-privilege permissions only, scoped to the function's own log group.
- An explicit `AWS::Logs::LogGroup` with 7-day retention, created before the function.
- Proper `AWS_PROXY` integration, a `$default` stage with auto-deploy, and a resource-scoped `Lambda::Permission` for API Gateway.
- Output the invoke URL.

That IAM constraint matters: CloudWatch Logs permissions need the log group ARN for `CreateLogStream`, but a `:log-stream:*` suffix for `PutLogEvents`/`CreateLogStream` at the stream level — a detail people (including me) get wrong constantly.

## What happened

The agent wrote a complete template and called `deploy_stack` **once**. CloudFormation Express mode reported `CREATE_COMPLETE` in **25.6 seconds**, and it got the IAM ARN scoping exactly right on the first try:

```yaml
Resource:
  - !GetAtt LambdaLogGroup.Arn
  - !Sub '${LambdaLogGroup.Arn}:log-stream:*'
```

More importantly, Express mode's "configuration applied" completion wasn't a lie — the API was already serving traffic:

```
$ curl -s -w "\nHTTP_STATUS:%{http_code} TIME:%{time_total}s\n" \
    https://8p7jv0cjt7.execute-api.ap-northeast-1.amazonaws.com/health
{"status": "ok"}
HTTP_STATUS:200 TIME:0.402073s
```

One-shot success is a flatter story than I'd hoped for — I wanted to show off a failure-fix-redeploy cycle. In the interest of not staging a fake failure for drama, I'll say plainly: this run didn't need one. The harness's `deploy_stack` tool is built to hand failure reasons straight back to the model (that's the whole point of the design), it just didn't get exercised this time. If you give Sonnet 4.6 a spec with real IAM subtlety in it, don't be surprised if it nails it.

## Isolating the actual speedup

A single agent run mixes model latency, template quality, and CloudFormation time, so it's not a clean measurement of Express mode itself. To get real numbers, I took the agent's own template and ran it through a controlled loop: create the stack, delete it, repeat — 3 times in Standard mode, 3 times in Express mode, same account, same region, back to back.

| Mode | Runs | Avg deploy time | Individual runs |
|---|---|---|---|
| STANDARD | 3 | 51.91s | 52.03s, 51.78s, 51.93s |
| EXPRESS  | 3 | 25.44s | 25.58s, 25.24s, 25.51s |

That's **2.04x faster**, consistently, for a Lambda + API Gateway HTTP API + IAM role + Log Group stack. It's not AWS's 4x-on-SQS headline number — different resources stabilize differently — but the variance across runs was under half a second in both modes, so the gap is real and repeatable, not noise. For an agent doing dozens of iterate-and-fix cycles while building something more complex, halving every round-trip adds up fast.

## A gotcha worth saving you the debugging time

My first attempt at the harness failed instantly, 8 times in a row, with:

```
ValidationError: OnFailure cannot be specified with EXPRESS deployment mode.
```

I was passing `OnFailure="DO_NOTHING"` alongside `DeploymentConfig` out of habit (old muscle memory for "don't roll back my dev stack"). Express mode wants rollback behavior controlled through `DeploymentConfig.DisableRollback` only — mixing in the classic `OnFailure` parameter is rejected outright, and the error message says so clearly once you know to look for it. If you're porting an existing deploy script to Express mode, grep for `OnFailure` first.

## Takeaways

- Express mode's promise for AI-agent workflows is legitimate, not just marketing: on a real multi-resource stack, the create-to-confirmation loop was about half as long, measured with back-to-back runs on the same template.
- "Configuration applied" isn't "not ready" — the API was live and answering before I'd finished typing the `curl` command.
- Giving the model a *slightly* opinionated, security-conscious spec (no managed execution role, exact ARN scoping) is a better test of an agent's IaC skill than a hello-world Lambda — and Sonnet 4.6 handled the ARN-scoping subtlety correctly without being told the trick.
- If you're building an agent loop against CloudFormation, feed the actual `StackEvents` failure reasons back to the model as the tool result, not just "it failed" — that's what turns a retry loop into an actual fix loop.

All the code — the deploy/poll helper, the Bedrock tool-use loop, and the benchmark script — is about 250 lines total and up on GitHub: [yama3133/cfn-express-agent-demo](https://github.com/yama3133/cfn-express-agent-demo).
