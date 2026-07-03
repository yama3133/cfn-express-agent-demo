"""CloudFormation deploy/poll helpers shared by the agent loop and the benchmark."""
import time
import uuid
import boto3
import botocore

CFN_REGION = "ap-northeast-1"

TERMINAL_OK = {"CREATE_COMPLETE", "UPDATE_COMPLETE"}
TERMINAL_BAD = {
    "CREATE_FAILED", "ROLLBACK_COMPLETE", "ROLLBACK_FAILED",
    "UPDATE_ROLLBACK_COMPLETE", "UPDATE_ROLLBACK_FAILED",
    "UPDATE_FAILED", "DELETE_FAILED",
}


def _client():
    return boto3.client("cloudformation", region_name=CFN_REGION)


def stack_status(cfn, stack_name: str):
    try:
        resp = cfn.describe_stacks(StackName=stack_name)
        return resp["Stacks"][0]["StackStatus"]
    except botocore.exceptions.ClientError as e:
        if "does not exist" in str(e):
            return None
        raise


def failure_events(cfn, stack_name: str):
    reasons = []
    try:
        paginator = cfn.get_paginator("describe_stack_events")
        for page in paginator.paginate(StackName=stack_name):
            for ev in page["StackEvents"]:
                if ev["ResourceStatus"].endswith("FAILED"):
                    reasons.append(
                        f"{ev['ResourceType']} {ev['LogicalResourceId']}: "
                        f"{ev.get('ResourceStatusReason', '')}"
                    )
    except Exception:
        pass
    # events are newest-first; cap to the most relevant ones
    return reasons[:15]


def deploy(stack_name: str, template_body: str, mode: str, disable_rollback: bool, poll_interval: float = 1.0, timeout_s: float = 300):
    """Create-or-update a stack and poll every poll_interval seconds until terminal.

    Returns dict: status, elapsed_s, failures(list[str]), action("create"|"update"|"delete+create")
    """
    cfn = _client()
    current = stack_status(cfn, stack_name)

    action = "create"
    if current in TERMINAL_BAD:
        # Failed/rollback-complete stacks in this state generally cannot be updated further; start clean.
        t0 = time.time()
        cfn.delete_stack(StackName=stack_name)
        while True:
            s = stack_status(cfn, stack_name)
            if s is None:
                break
            time.sleep(poll_interval)
        action = "delete+create"
        current = None

    deployment_config = {"Mode": mode, "DisableRollback": disable_rollback}
    token = str(uuid.uuid4())

    t_start = time.time()
    try:
        if current is None:
            cfn.create_stack(
                StackName=stack_name,
                TemplateBody=template_body,
                Capabilities=["CAPABILITY_NAMED_IAM"],
                DeploymentConfig=deployment_config,
                ClientRequestToken=token,
            )
        else:
            action = "update"
            cfn.update_stack(
                StackName=stack_name,
                TemplateBody=template_body,
                Capabilities=["CAPABILITY_NAMED_IAM"],
                DeploymentConfig=deployment_config,
                ClientRequestToken=token,
            )
    except botocore.exceptions.ClientError as e:
        elapsed = time.time() - t_start
        if "No updates are to be performed" in str(e):
            return {"status": "NO_CHANGES", "elapsed_s": elapsed, "failures": [], "action": action}
        return {"status": "API_ERROR", "elapsed_s": elapsed, "failures": [str(e)], "action": action}

    deadline = time.time() + timeout_s
    status = None
    while time.time() < deadline:
        status = stack_status(cfn, stack_name)
        if status in TERMINAL_OK or status in TERMINAL_BAD:
            break
        time.sleep(poll_interval)
    elapsed = time.time() - t_start

    failures = []
    if status in TERMINAL_BAD:
        failures = failure_events(cfn, stack_name)

    return {"status": status or "TIMEOUT", "elapsed_s": elapsed, "failures": failures, "action": action}


def delete(stack_name: str, poll_interval: float = 1.0, timeout_s: float = 300):
    cfn = _client()
    if stack_status(cfn, stack_name) is None:
        return {"status": "ALREADY_GONE", "elapsed_s": 0.0}
    t0 = time.time()
    cfn.delete_stack(StackName=stack_name)
    deadline = time.time() + timeout_s
    status = "DELETE_IN_PROGRESS"
    while time.time() < deadline:
        status = stack_status(cfn, stack_name)
        if status is None:
            status = "DELETE_COMPLETE"
            break
        if status == "DELETE_FAILED":
            break
        time.sleep(poll_interval)
    return {"status": status, "elapsed_s": time.time() - t0}
