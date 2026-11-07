// touch_taps.bundle.js with fake events, no browser: node --test kiluth_portal/tests/
// What it can't show is iPhone itself sending a click to a stopped scroller; that
// is checked on the phone.
import { test, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const SOURCE = readFileSync(new URL("../public/js/touch_taps.bundle.js", import.meta.url), "utf8");

let clock, handlers, head;

function load() {
	clock = 0;
	handlers = {};
	head = [];
	globalThis.performance = { now: () => clock };
	globalThis.document = {
		addEventListener: (type, fn) => (handlers[type] ||= []).push(fn),
		getElementById: (id) => head.find((el) => el.id === id) || null,
		createElement: () => ({}),
		head: { appendChild: (el) => head.push(el) },
	};
	new Function(SOURCE)();
}

function fire(type, init = {}) {
	const e = { type, touches: [{}], prevented: false, stopped: false, ...init };
	e.preventDefault = () => (e.prevented = true);
	e.stopImmediatePropagation = () => (e.stopped = true);
	for (const fn of handlers[type] || []) fn(e);
	return e;
}

// One tap: finger down, then the click iPhone sends about 100 ms later.
function tap() {
	fire("touchstart");
	clock += 100;
	return fire("click");
}

beforeEach(load);

test("a tap on a still list clicks", () => {
	clock = 5000;
	const click = tap();
	assert.equal(click.prevented, false);
	assert.equal(click.stopped, false);
});

test("a tap on a moving list only stops it", () => {
	clock = 5000;
	fire("scroll");
	clock += 16;
	const click = tap();
	assert.equal(click.prevented, true);
	assert.equal(click.stopped, true);
});

test("the next tap after stopping the list clicks", () => {
	clock = 5000;
	fire("scroll");
	clock += 16;
	tap();
	clock += 400;
	assert.equal(tap().prevented, false);
});

test("a tap once the list has come to rest clicks", () => {
	clock = 5000;
	fire("scroll");
	clock += 300;
	assert.equal(tap().prevented, false);
});

test("a stopping touch that sends no click doesn't eat a later one", () => {
	clock = 5000;
	fire("scroll");
	clock += 16;
	fire("touchstart");
	clock += 2000;
	assert.equal(fire("click").prevented, false);
});

test("a mouse click never touches, so a scroll never eats it", () => {
	clock = 5000;
	fire("scroll");
	clock += 16;
	assert.equal(fire("click").prevented, false);
});

test("two fingers on a moving list aren't a tap to stop", () => {
	clock = 5000;
	fire("scroll");
	clock += 16;
	fire("touchstart", { touches: [{}, {}] });
	clock += 100;
	assert.equal(fire("click").prevented, false);
});

test("the sidebar's hover-only button stays hidden on a screen with no hover", () => {
	const style = head.find((el) => el.id === "kiluth-touch-css");
	assert.ok(style);
	assert.match(style.textContent, /@media \(hover: none\)/);
	assert.match(style.textContent, /\.body-sidebar:hover \.sidebar-toggle-btn \{ opacity: 0; visibility: hidden; \}/);
});
