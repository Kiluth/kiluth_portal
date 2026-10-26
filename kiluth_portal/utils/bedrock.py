"""Amazon Bedrock, for the few Portal jobs that need a model.

The Portal's EC2 role (`frappe-instance`, kiluth-infra `modules/frappe`) may
call `bedrock:InvokeModel` on the Claude models it is scoped to. boto3 picks
the role up from the instance metadata, so there are no keys to store.

Current Claude models in ap-southeast-1 are reachable only through the global
cross-region profiles (`global.anthropic.<model>`), so a request may be served
in any AWS commercial region. Model invocation logging stays off.

No Frappe import: the certificate bench (tests/bench_certify.py) calls this
from a laptop with an SSO profile.
"""

from __future__ import annotations

REGION = "ap-southeast-1"


def ask_with_tool(system, user, tool, model_id, max_tokens=8000, region=REGION, client=None):
	"""One Converse call that must answer by calling `tool`.

	tool: {"name", "description", "schema"} with a JSON schema for the answer.
	Returns (tool input dict, usage dict). Raises ValueError when the model
	answers without the tool, so a caller never mistakes prose for a verdict.
	"""
	import boto3
	from botocore.config import Config

	client = client or boto3.client("bedrock-runtime", region_name=region,
		config=Config(retries={"mode": "standard", "max_attempts": 3}, read_timeout=300))
	resp = client.converse(
		modelId=model_id,
		system=[{"text": system}],
		messages=[{"role": "user", "content": [{"text": user}]}],
		inferenceConfig={"maxTokens": int(max_tokens), "temperature": 0},
		toolConfig={
			"tools": [{"toolSpec": {"name": tool["name"], "description": tool["description"],
				"inputSchema": {"json": tool["schema"]}}}],
			"toolChoice": {"tool": {"name": tool["name"]}},
		},
	)
	usage = resp.get("usage", {})
	if resp.get("stopReason") == "max_tokens":
		raise ValueError(f"The model ran out of tokens ({max_tokens}) before answering")
	for block in resp["output"]["message"]["content"]:
		use = block.get("toolUse")
		if use and use.get("name") == tool["name"]:
			return use.get("input") or {}, usage
	raise ValueError("The model answered without calling " + tool["name"])
