"""Talks to the agent: locally (fast while developing) or on AgentCore Runtime
(when agent_runtime_arn is set in agent/settings.json)."""
import base64
import json

import boto3

import config


def ask(prompt: str, session_id: str, image_bytes: bytes | None = None, image_format: str = "jpeg") -> str:
    payload = {"prompt": prompt}
    if image_bytes:
        payload["image_b64"] = base64.b64encode(image_bytes).decode()
        payload["image_format"] = image_format

    if not config.AGENT_RUNTIME_ARN:
        from yorisoi_agent import handle_request  # local mode
        return handle_request(payload, session_id)["reply"]

    client = boto3.client("bedrock-agentcore", region_name=config.AWS_REGION)
    resp = client.invoke_agent_runtime(
        agentRuntimeArn=config.AGENT_RUNTIME_ARN,
        runtimeSessionId=session_id,  # must be 33+ chars (uuid4 is 36)
        payload=json.dumps(payload).encode(),
        qualifier=config.AGENT_QUALIFIER,
    )
    body = b"".join(resp["response"]).decode("utf-8")
    data = json.loads(body)
    return data.get("reply", str(data)) if isinstance(data, dict) else str(data)
