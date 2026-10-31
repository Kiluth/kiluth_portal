"""Tell AWS a task needs checking.

The queue holds each message for DELAY_SECONDS, and the checker collects what
arrives in the next minute (kiluth-infra modules/task-check). So a run of saves
on one task costs one run: each run reads the latest state, and text the model
has already judged comes from the verdict cache.

Sends with the Portal's EC2 role (`frappe-instance`, kiluth-infra modules/frappe),
which boto3 picks up from the instance metadata, so there are no keys to store.
The role may send to this one queue and nothing else on it.

A failed send leaves the task "not checked" (handlers.py) for the daily run.
"""

import json

import frappe

REGION = "ap-southeast-1"
DELAY_SECONDS = 90


def send(task):
	url = frappe.conf.get("task_check_queue_url")
	if not url:
		return
	import boto3

	boto3.client("sqs", region_name=REGION).send_message(
		QueueUrl=url, MessageBody=json.dumps({"task": task}), DelaySeconds=DELAY_SECONDS
	)
