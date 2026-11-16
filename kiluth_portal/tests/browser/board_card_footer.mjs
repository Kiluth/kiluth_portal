// Browser test: the board card footer keeps the assignee avatar round (TASK board, Poom 2026-11-16).
//
// Bug: with a long name + date + "Late · 14 Nov" + "Needs fixing" + comment count in the footer, the avatar
// (a flex child that could shrink) was squashed into a tall narrow oval. It must stay a 20 x 20 circle and
// the name must give way (ellipsis).
//
// This test takes the REAL card CSS out of public/js/task_board.js and the card footer markup the same file builds,
// puts them in a page with the footer rules Frappe's own avatar uses, and measures in Chromium at the narrowest
// column width. Nothing here touches a Portal.
//
//   node kiluth_portal/tests/browser/board_card_footer.mjs [--shot before.png]
//
// Needs `playwright` or `playwright-core` (the copy in kiluth-swarm/composer/node_modules works) and Chrome (CHROME_PATH to change it).
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const src = readFileSync(join(here, "../../public/js/task_board.js"), "utf8");
const css = src.match(/<style id="kiluth-board-css">([\s\S]*?)<\/style>/)?.[1];
if (!css) throw new Error("could not find the board CSS in task_board.js");

// Frappe core's avatar rules (frappe/public/scss/common/avatar.scss, v15): the size classes set width and height,
// the frame fills the span. Nothing there sets flex, which is why the avatar shrank inside .kb-person.
const frappeAvatar = `
  .avatar { display: inline-block; position: relative; vertical-align: middle; border-radius: 50%; }
  .avatar-small { width: 20px; height: 20px; }
  .avatar-frame { width: 100%; height: 100%; border-radius: 50%; display: flex; align-items: center; justify-content: center;
    font-size: 11px; background: #ecd9ff; color: #6b21a8; }
  :root { --gray-300:#d1d8dd; --gray-700:#4b5563; --red-600:#e03636; --red-50:#fff5f5; --orange-700:#b45309; --orange-50:#fffbeb;
    --text-muted:#6b7280; --text-color:#1f272e; --kanban-card-bg:#fff; --control-bg:#f3f3f3; }
  body { font-family: system-ui, sans-serif; margin: 0; }`;

const person = (name) =>
  `<span class="kb-person"><span class="avatar avatar-small"><div class="avatar-frame">P</div></span><span class="kb-name">${name}</span></span>`;
const comments = `<span class="kb-note"><svg width="14" height="14"></svg>12</span>`;
// The footer exactly as card_html builds it (task_board.js, `kb-foot`), on a touch screen the status button is shown.
const foot = (name, due, failing, withComments, withMove) =>
  `<div class="kb-card" data-priority="High"><div class="kb-foot">${person(name)}${due}${failing}${withComments ? comments : ""}` +
  `${withMove ? '<button type="button" class="kb-move">Pending Review</button>' : ""}</div></div>`;
const LONG = "Poompeng Charoenpornthawee Suriyawongsakul";
const late = `<span class="kb-due late">Late · 14 Nov</span>`;
const bad = `<span class="kb-note bad">Needs fixing</span>`;

const cases = {
  "short footer": foot("Poom", `<span class="kb-due">14 Nov</span>`, "", false, false),
  "long name + date": foot(LONG, `<span class="kb-due">14 Nov</span>`, "", false, false),
  "long name + late + needs fixing + comments": foot(LONG, late, bad, true, false),
  "same on a touch screen (status button shown)": foot(LONG, late, bad, true, true),
};

const { chromium } = await import("playwright").catch(() => import("playwright-core")).catch(() => import(join(here, "../../../../../kiluth-swarm/composer/node_modules/playwright-core/index.mjs")));
const CHROME = process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"; // used when Playwright has no browser of its own
const shotIdx = process.argv.indexOf("--shot");
const shot = shotIdx > 0 ? process.argv[shotIdx + 1] : null;
const WIDTH = 230; // the narrowest card content: a 270 px board column less its padding and the card's own 12 px padding

const browser = await chromium.launch(process.env.CHROME_PATH === "none" ? {} : { executablePath: CHROME });
const page = await browser.newPage({ viewport: { width: 320, height: 600 } });
await page.setContent(
  `<style>${frappeAvatar}${css}</style>` +
    Object.entries(cases).map(([k, html]) => `<div class="case" data-case="${k}" style="width:${WIDTH}px;margin:8px;border:1px dashed #ccc">${html}</div>`).join(""),
);
const rows = await page.$$eval(".case", (els) =>
  els.map((el) => {
    const r = (e) => e.getBoundingClientRect();
    const av = el.querySelector(".avatar"), nm = el.querySelector(".kb-name"), ft = el.querySelector(".kb-foot");
    return {
      name: el.dataset.case, avW: r(av).width, avH: r(av).height, nameClipped: nm.scrollWidth > nm.clientWidth,
      nameOverflow: getComputedStyle(nm).textOverflow, footOverflows: ft.scrollWidth > ft.clientWidth + 1,
    };
  }),
);
if (shot) await page.screenshot({ path: shot });
await browser.close();

let failed = 0;
for (const r of rows) {
  const problems = [];
  if (Math.abs(r.avW - 20) > 0.5 || Math.abs(r.avH - 20) > 0.5) problems.push(`avatar is ${r.avW.toFixed(1)} x ${r.avH.toFixed(1)}, want 20 x 20`);
  if (r.nameOverflow !== "ellipsis") problems.push("name does not ellipsize");
  if (r.footOverflows) problems.push("footer overflows the card");
  console.log(`${problems.length ? "FAIL" : "PASS"}  ${r.name}${problems.length ? ": " + problems.join("; ") : ""}`);
  failed += problems.length ? 1 : 0;
}
process.exit(failed ? 1 : 0);
