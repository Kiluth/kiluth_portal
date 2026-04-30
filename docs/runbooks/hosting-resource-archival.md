# Hosting Resource Archival Runbook

How to retire a hosting droplet whose contract has expired and is **not** being renewed: snapshot for a year, destroy the VM, remove DNS, flip the registry to `Archived`. Tick each box on the Resource form's **Archival Checklist** as you go so future-you can see what's been done.

This is a manual runbook, not automation. The destructive steps require human eyes — DigitalOcean's destroy modal and Cloudflare's bulk-delete confirmation are the safety net.

## Vocabulary

- **Expired** — contract end date passed; cleanup hasn't happened yet (droplet usually still running and billing).
- **Archived** — droplet deleted on DO, snapshot retained.
- **Deleted** — droplet AND snapshot both gone (rare; only when client asked for full data destruction).

## Pre-flight

Before touching anything in DigitalOcean:

1. **Confirm non-renewal** with the project's PM and the customer. If renewal is even possibly on the table, leave the resource as `Expired` and revisit later.
2. **Confirm the IP** in the registry matches the droplet you're about to destroy. The Resource record's `identifier` field holds the IP.
3. **Open the browser tabs** you'll need:
   - DigitalOcean → https://cloud.digitalocean.com/droplets (switch to the team that owns the droplet — most customer hosting lives in **Technology Team 2**)
   - Cloudflare DNS → https://dash.cloudflare.com/35321218724970e16ca5dee8cf7f02d2/kiluth.com/dns/records
   - Coolify (only if the droplet was managed by Coolify) → https://coolify.kiluth.com

## Steps

### 1. Locate droplet

Search the DO Droplets page by IP. Click into the droplet to confirm the project label matches the Resource's `project` field. Note the size (e.g. `4 GB / 50 GB / SGP1`) for sanity-checking the snapshot later.

### 2. Snapshot

Backups & Snapshots tab → **Take a Snapshot** → accept the default name (DO auto-fills `<droplet-name>-<unix-ms>`, which matches the existing fleet's pattern) → **Take Live Snapshot**.

Live snapshot is fine for expired non-prod customer envs. Power-Off-then-Snapshot only matters when the box is serving live writes you can't afford to half-capture.

Wait until the Snapshots row shows a size and a `Created … minute ago` rather than `Taking Snapshot` (typically <2 min for our 4 GB / 50 GB tier; size column reflects used disk, not allocated).

✅ Tick **Snapshot Taken** on the Resource form. Paste the snapshot name into **Snapshot ID**.

### 3. Verify snapshot

Visit https://cloud.digitalocean.com/images/snapshots and confirm the row exists with a real size. Do this **before** the destroy click — once the droplet is gone, a missing snapshot means the data is unrecoverable.

### 4. Clean Coolify (only if the droplet is Coolify-managed)

> ⚠️ **Order matters — do this BEFORE destroying the droplet.** Coolify's cascade-delete tries to SSH the host to gracefully shut down containers; with the host still alive that takes seconds, with the host already destroyed the click silently hangs and nothing gets removed. Get the snapshot first (step 2-3), Coolify second, droplet third.

Skip this step for droplets that weren't registered as Coolify Servers (most pre-2026 customer envs aren't). Quick check: search the customer slug at https://coolify.kiluth.com/servers — if nothing matches, skip to step 5.

If there is a match, you'll typically have:

- A **Server** entry under Servers (the SSH connection to the droplet)
- An **Environment** under the customer's Project (Projects → `PROJ-XXXX - <customer> - <app>` → `dev` / `uat` / etc.) holding the Application + Postgres/MySQL + Redis + any object-store services

Cleanest path: **Server → Danger Zone → Delete** with the **"Delete all resources (N total)"** checkbox checked, then type the server name on the next step → Continue. That cascades through the application + databases + services.

After the Server entry is gone, the now-empty Environment can be deleted via **Project → Environment → Delete Environment** (type the env name to confirm).

> 🩹 **Recovery — if you already destroyed the droplet and Coolify entries are stuck**: the UI cascade-delete will silently fail. Two escape hatches:
>
> 1. **Coolify API**: `DELETE /api/v1/servers/{uuid}?delete_associated_volumes=true` with the `COOLIFY_TOKEN` from the frappe_docker GitHub repo secrets (same token the auto-deploy workflow uses). Get the server UUID from the URL on its Danger Zone page.
> 2. **Direct SQL** on Coolify's Postgres: `DELETE` the orphan rows from `servers`, `applications`, `standalone_postgresqls`, `standalone_redis`, `services` referencing the dead server.
>
> Don't try to manually click each resource's "Delete" — same SSH-to-dead-host hang.

### 5. Destroy droplet

Droplet → **Settings** → scroll to **Destroy** → click Destroy.

In the **Droplet Danger Zone** modal:

- Under **Associated Resources → Snapshots**, leave the snapshot **unchecked** (this is the default; the modal's headline says "destroy the Droplet and all backups" but snapshots are opt-in for deletion here).
- Type the droplet name into the confirm field.
- Click **Destroy**.

Toast should read "Droplet deleted successfully" and the droplet leaves the list.

✅ Tick **Droplet Destroyed**.

### 6. Clean Cloudflare DNS

On the Cloudflare DNS records page, type the customer-app slug (e.g. `pharmdelo`, `handyman`, `pimtooklaedee`) into **Search DNS Records** and click **Search**.

The result should be a small set of A records — typically the apex `<customer-app>.<env>` and the wildcard `*.<customer-app>.<env>` for each environment that just got destroyed. **Sanity check the IP** in the Content column matches the one you just destroyed.

Use the header checkbox (Select all) → **Delete N records** (red) → type `DELETE` → confirm.

✅ Tick **DNS Records Cleaned**.

### 7. Flip status to Archived

On the Resource form, change **Status** from `Expired` → `Archived` and save. The doctype's [`_auto_set_status`](../../kiluth_portal/kiluth_hosting/doctype/resource/resource.py) early-returns on terminal states (`Archived`, `Deleted`), so the value sticks even though `before_save` runs. The daily scheduler is idempotent on terminal states for the same reason.

If you prefer a one-liner from the browser console on the Resource page:

```js
fetch('/api/method/frappe.client.set_value', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/x-www-form-urlencoded',
    'X-Frappe-CSRF-Token': frappe.csrf_token,
  },
  body: new URLSearchParams({
    doctype: 'Resource',
    name: 'RESOURCE-XXXXX',
    fieldname: 'status',
    value: 'Archived',
  }),
}).then(r => r.json()).then(console.log);
```

## Verification

You should be able to assert all of the following:

- Droplet IP no longer appears on DO Droplets page (any team).
- Snapshot row exists on https://cloud.digitalocean.com/images/snapshots with the expected size.
- `pharmdelo` (or whatever slug) returns zero rows on the Cloudflare DNS search.
- If Coolify-managed: the Server entry no longer appears at https://coolify.kiluth.com/servers (or is flagged as a known-blocked cleanup per step 4's recovery callout).
- Resource record's status is `Archived` and the three checklist boxes are ticked. The Snapshot ID field has the snapshot name.

## Rollback (customer comes back)

DO retains the snapshot indefinitely (≈ used-disk × $0.06/mo). To revive:

1. Snapshots page → click the snapshot → **Create Droplet** (pick same size and region).
2. Re-create the Cloudflare A records (apex + wildcard) pointing at the new droplet IP.
3. Create a fresh Resource record (don't reuse the old one — that one is the historical archive); link it to the same Project and Customer.

## Examples in the registry

These have all been through this runbook end to end:

- RESOURCE-00007 / RESOURCE-00009 — Pharmdelo PKMS dev + uat (the case this runbook was written from)
- RESOURCE-00012 — Pimpasai Chinese Vocab (Team 2)
- RESOURCE-00014 — PimTookLaeDee (Team 1)
- RESOURCE-00002 — HandyMan (Team 1)
- RESOURCE-00016 — Thitinun PHR (Team 1)

Search the existing `Archived` records to see real Snapshot ID values for naming reference.
