// Changing a task's status on a phone: tap the status, pick from a sheet, Undo for a
// few seconds. Two deliberate taps, because drag is off on touch screens. Used by
// the Task Board and the Task page.
frappe.provide("kiluth.tasks");

(() => {
	if (kiluth.tasks.pick_status) return;

	const CHOICES = ["Open", "Working", "Pending Review", "Completed", "Cancelled"];
	const UNDO_MS = 6000;

	function add_styles() {
		if (document.getElementById("kiluth-sheet-css")) return;
		$(`<style id="kiluth-sheet-css">
			.kt-backdrop { position: fixed; inset: 0; z-index: 1050; background: rgba(0, 0, 0, 0.5); }
			.kt-sheet { position: fixed; z-index: 1051; left: 0; right: 0; bottom: 0; max-width: 480px; margin: 0 auto;
				padding: 16px 16px calc(16px + env(safe-area-inset-bottom, 0px)); border-radius: 16px 16px 0 0;
				background: var(--card-bg, var(--fg-color)); color: var(--text-color); box-shadow: 0 -4px 24px rgba(0, 0, 0, 0.3); }
			.kt-sheet-title { font-size: 12px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
			.kt-sheet-head { font-size: 16px; font-weight: 600; margin: 2px 0 10px; }
			.kt-sheet button.kt-choice { display: flex; width: 100%; align-items: center; justify-content: space-between; gap: 12px;
				min-height: 48px; padding: 0 12px; border: 0; border-radius: 10px; background: transparent; color: var(--text-color);
				font-size: 16px; text-align: left; }
			.kt-sheet button.kt-choice:hover, .kt-sheet button.kt-choice:focus-visible { background: var(--control-bg); outline: none; }
			.kt-sheet button.kt-choice[aria-current="true"] { font-weight: 600; background: var(--control-bg); }
			.kt-sheet .kt-hint { font-size: 12px; color: var(--text-muted); font-weight: 400; }
			.kt-sheet button.kt-cancel { width: 100%; min-height: 44px; margin-top: 8px; border: 0; border-radius: 10px;
				background: transparent; color: var(--text-muted); font-size: 15px; }
			.kt-undo { position: fixed; z-index: 1052; left: 16px; right: 16px; bottom: calc(16px + env(safe-area-inset-bottom, 0px));
				max-width: 420px; margin: 0 auto; display: flex; align-items: center; justify-content: space-between; gap: 12px;
				padding: 12px 16px; border-radius: 10px; font-size: 14px; background: var(--gray-900); color: #fff;
				box-shadow: 0 4px 16px rgba(0, 0, 0, 0.35); }
			[data-theme="dark"] .kt-undo { background: var(--gray-100); color: var(--gray-900); }
			.kt-undo button { border: 0; background: transparent; color: inherit; font-weight: 600; text-decoration: underline; min-height: 28px; }
		</style>`).appendTo("head");
	}

	function close_sheet() {
		$(".kt-backdrop, .kt-sheet").remove();
		$(document).off("keydown.ktsheet");
	}

	/** Ask for a new status. `task`: {name, subject, status, owner}. Calls `done(status)`. */
	kiluth.tasks.pick_status = function (task, done) {
		add_styles();
		close_sheet();
		const backdrop = $(`<div class="kt-backdrop"></div>`).appendTo("body").on("click", close_sheet);
		const sheet = $(`<div class="kt-sheet" role="dialog" aria-modal="true" aria-label="${__("Move task")}">
			<div class="kt-sheet-title"></div>
			<div class="kt-sheet-head">${__("Move to")}</div>
		</div>`).appendTo("body");
		sheet.find(".kt-sheet-title").text(task.subject || task.name);
		const not_requester = task.owner && task.owner !== frappe.session.user;
		for (const status of CHOICES) {
			const here = status === task.status;
			const hint = status === "Completed" && not_requester ? `<span class="kt-hint">${__("The requester completes a task")}</span>` : "";
			$(`<button type="button" class="kt-choice" aria-current="${here}"><span>${__(status)}</span>${here ? "✓" : hint}</button>`)
				.appendTo(sheet)
				.on("click", () => {
					close_sheet();
					if (!here) done(status);
				});
		}
		$(`<button type="button" class="kt-cancel">${__("Cancel")}</button>`).appendTo(sheet).on("click", close_sheet);
		$(document).on("keydown.ktsheet", (e) => e.key === "Escape" && close_sheet());
		sheet.find(".kt-choice").first().trigger("focus");
		return backdrop;
	};

	/** Show "Moved to X · Undo". `undo` runs if the person taps it. */
	kiluth.tasks.undo_bar = function (text, undo) {
		add_styles();
		$(".kt-undo").remove();
		const bar = $(`<div class="kt-undo" role="status"><span></span><button type="button">${__("Undo")}</button></div>`).appendTo("body");
		bar.find("span").text(text);
		const timer = setTimeout(() => bar.remove(), UNDO_MS);
		bar.find("button").on("click", () => {
			clearTimeout(timer);
			bar.remove();
			undo();
		});
	};

	/** Set a task's status from outside its form, then offer Undo. */
	kiluth.tasks.move = async function (task, status, after) {
		const set = (value) => frappe.xcall("frappe.client.set_value", {
			doctype: "Task", name: task.name, fieldname: "status", value,
		});
		await set(status);
		after();
		kiluth.tasks.undo_bar(__("Moved to {0}", [__(status)]), async () => {
			await set(task.status);
			after();
		});
	};
})();
