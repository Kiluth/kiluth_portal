"""Replay past certificates through Kiluth's check and compare with what was decided.

Read-only on the Portal (REST, Kiluth Swarm's key); calls Bedrock with your
AWS SSO session. Nothing is signed or voided.

	set -a; . <workspace>/departments/technology/artifacts/.erpnext-swarm.env; set +a
	AWS_PROFILE=kiluth python kiluth_portal/tests/bench_certify.py [CERT-00021 ...] \
		[--model global.anthropic.claude-sonnet-4-6] [--out /tmp/certbench/run.json]

Needs requests and boto3. Each certificate is judged with the earlier
attempts that existed when it was taken, against today's docs.
"""

import argparse
import importlib.util
import json
import os
import sys
import time

import requests

here = os.path.dirname(os.path.abspath(__file__))


def _load(name, rel):
	spec = importlib.util.spec_from_file_location(name, os.path.join(here, "..", rel))
	m = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(m)
	return m


cf = _load("certify", "kiluth_hr/certify.py")
bedrock = _load("bedrock", "utils/bedrock.py")


def main():
	ap = argparse.ArgumentParser()
	ap.add_argument("names", nargs="*")
	ap.add_argument("--model", default=cf.DEFAULT_MODEL)
	ap.add_argument("--out", default="/tmp/certbench/run.json")
	a = ap.parse_args()
	base = os.environ["SWARM_BASE_URL"].rstrip("/")
	h = {"Authorization": f"token {os.environ['SWARM_API_KEY']}:{os.environ['SWARM_API_SECRET']}"}

	def get(path, **params):
		r = requests.get(base + path, params={k: json.dumps(v) if not isinstance(v, (str, int)) else v
			for k, v in params.items()}, headers=h, timeout=60)
		r.raise_for_status()
		return r.json()["data"]

	docs = get("/api/resource/Document", filters=[["document_type", "=", "Certificate"]],
		fields=["name", "title", "status", "creation"], order_by="creation asc", limit_page_length=1000)
	for d in docs:
		files = get("/api/resource/File", filters=[["attached_to_doctype", "=", "Document"],
			["attached_to_name", "=", d["name"]], ["file_name", "like", "%.md"]],
			fields=["file_url"], order_by="creation asc")
		d["record"] = ""
		if files:
			r = requests.get(base + files[0]["file_url"], headers=h, timeout=60)
			r.raise_for_status()
			d["record"] = r.content.decode("utf-8")

	cache = {}

	def fetch(slug):
		if slug not in cache:
			r = requests.get(f"{cf.DOCS}/{slug}", timeout=30)
			r.raise_for_status()
			cache[slug] = r.text
		return cache[slug]

	def ask(system, user):
		return bedrock.ask_with_tool(system, user, cf.VERDICT_TOOL, a.model)

	results = []
	for i, d in enumerate(docs):
		if a.names and d["name"] not in a.names:
			continue
		earlier = [(e["name"], e["status"], e["record"]) for e in docs[:i] if e["title"] == d["title"]]
		t0 = time.time()
		try:
			out = cf.evaluate(d["name"], d["title"], d["record"], earlier, fetch("hr/certification"), fetch, ask)
		except Exception as e:
			out = {"verdict": "error", "by": "error", "reason": repr(e), "notes": [], "usage": {}}
		want = {"Signed": "sign", "Void": "void"}.get(d["status"], d["status"])
		agree = out["verdict"] == want
		u = out.get("usage") or {}
		results.append({"name": d["name"], "title": d["title"], "was": d["status"], "now": out["verdict"],
			"by": out["by"], "agree": agree, "reason": out["reason"], "notes": out["notes"],
			"answer": out.get("answer"), "in": u.get("inputTokens", 0), "out": u.get("outputTokens", 0),
			"secs": round(time.time() - t0, 1)})
		print(f"{d['name']}  was {d['status']:<8} now {out['verdict']:<5} by {out['by']:<5} "
			f"{'agree' if agree else 'DISAGREE'}  {u.get('inputTokens', 0)}/{u.get('outputTokens', 0)} tok", flush=True)
	os.makedirs(os.path.dirname(a.out), exist_ok=True)
	with open(a.out, "w") as f:
		json.dump({"model": a.model, "results": results}, f, indent=1, ensure_ascii=False)
	tin, tout = sum(r["in"] for r in results), sum(r["out"] for r in results)
	print(f"\n{sum(r['agree'] for r in results)}/{len(results)} agree. Tokens {tin} in / {tout} out. Written to {a.out}")


if __name__ == "__main__":
	sys.exit(main())
