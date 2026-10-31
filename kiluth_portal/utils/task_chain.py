"""Lay a project's tasks out by what blocks what. No dates needed, and no Frappe,
so it can be tested on its own (python3 kiluth_portal/tests/test_task_chain.py).

A link (a, b) means a blocks b: b lists a under Dependent Tasks. `level` is how
many tasks must finish first along the longest route, which is what puts a task
further to the right in the waterfall.
"""

from __future__ import annotations

from collections import defaultdict


def through_hidden(shown: list[str], links: list[tuple[str, str]]) -> list[tuple[str, str]]:
	"""The links between `shown` tasks, keeping a chain joined across tasks left out."""
	keep = set(shown)
	blocks = defaultdict(set)
	for a, b in links:
		blocks[a].add(b)
	out = set()
	for start in shown:
		seen, stack = {start}, list(blocks[start])
		while stack:
			t = stack.pop()
			if t in seen:
				continue
			seen.add(t)
			if t in keep:
				out.add((start, t))
			else:
				stack.extend(blocks[t])
	return sorted(out)


def levels(tasks: list[str], links: list[tuple[str, str]]) -> dict[str, int]:
	"""Longest route to each task. A loop, which should not exist, gets a level
	one past everything else rather than stopping the page."""
	waits = {t: 0 for t in tasks}
	blocks = defaultdict(list)
	for a, b in links:
		waits[b] += 1
		blocks[a].append(b)
	ready = [t for t in tasks if not waits[t]]
	level = {t: 0 for t in ready}
	while ready:
		t = ready.pop()
		for n in blocks[t]:
			level[n] = max(level.get(n, 0), level[t] + 1)
			waits[n] -= 1
			if not waits[n]:
				ready.append(n)
	top = max(level.values(), default=-1)
	return {t: level.get(t, top + 1) if waits[t] <= 0 else top + 1 for t in tasks}


def layout(tasks: list[str], links: list[tuple[str, str]]) -> dict:
	"""Rows and columns for one project.

	Returns {"chain": [{"task", "level", "row"}], "links": [...], "loose": [...],
	"ends": [...]}. Linked tasks are placed so each follows the one it comes
	after; `loose` tasks are in no chain; `ends` are chain tasks that block nothing.
	"""
	linked = {t for pair in links for t in pair}
	chain = [t for t in tasks if t in linked]
	level = levels(chain, links)
	after = defaultdict(list)
	before = defaultdict(list)
	for a, b in links:
		after[a].append(b)
		before[b].append(a)

	reach = {}

	def depth(t, path=()):
		if t in path:
			return 0
		if t not in reach:
			reach[t] = 1 + max((depth(n, (*path, t)) for n in after[t]), default=0)
		return reach[t]

	rows, placed = {}, set()

	def place(t):
		if t in placed:
			return
		placed.add(t)
		rows[t] = len(rows)
		for n in sorted(after[t], key=lambda x: (-depth(x), level[x], x)):
			place(n)

	for t in sorted((t for t in chain if not before[t]), key=lambda x: (-depth(x), x)):
		place(t)
	for t in sorted(chain):  # only a loop has no start
		place(t)

	return {
		"chain": [{"task": t, "level": level[t], "row": rows[t]} for t in sorted(chain, key=rows.get)],
		"links": sorted(links),
		"loose": [t for t in tasks if t not in linked],
		"ends": sorted(t for t in chain if not after[t]),
	}
