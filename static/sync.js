(() => {
  "use strict";
  const panel = document.getElementById("sync-progress");
  if (!panel) return;
  const statusUrl = panel.dataset.statusUrl;
  let status = panel.dataset.initialStatus || "idle";
  let observedRunning = ["queued", "running"].includes(status);
  let tries = 0;
  const terminal = new Set(["completed", "partial", "failed", "cancelled"]);
  const byId = (id) => document.getElementById(id);

  function render(job) {
    status = job.status || status;
    if (["queued", "running"].includes(status)) observedRunning = true;
    byId("sync-status-label").textContent = status.replaceAll("_", " ").replace(/\b\w/g, (ch) => ch.toUpperCase());
    byId("sync-message").textContent = job.message || "Checking document source…";
    byId("sync-processed").textContent = String(job.processed || 0);
    byId("sync-total").textContent = String(job.total || 0);
    byId("sync-fetched").textContent = String(job.fetched || 0);
    byId("sync-skipped").textContent = String(job.skipped || 0);
    byId("sync-failed").textContent = String(job.failed || 0);
    const percent = Math.max(0, Math.min(100, Number(job.progress_percent || 0)));
    byId("sync-progress-bar").style.width = `${percent}%`;
    panel.querySelector('[role="progressbar"]').setAttribute("aria-valuenow", String(percent));
  }

  async function poll() {
    if (!statusUrl || terminal.has(status) || tries > 1800) return;
    tries += 1;
    try {
      const response = await fetch(statusUrl, { credentials: "same-origin", cache: "no-store", headers: { "Accept": "application/json" } });
      if (response.redirected || !(response.headers.get("content-type") || "").includes("application/json")) {
        byId("sync-message").textContent = "Your sign-in may have expired. Sign in again to view sync progress.";
        return;
      }
      if (!response.ok) throw new Error("status unavailable");
      const job = await response.json();
      render(job);
      if (terminal.has(job.status)) {
        if (observedRunning) window.setTimeout(() => window.location.reload(), 900);
        return;
      }
    } catch (_error) {
      byId("sync-message").textContent = "Progress could not be refreshed right now. This page will keep trying.";
    }
    window.setTimeout(poll, 1800);
  }

  if (["queued", "running"].includes(status)) window.setTimeout(poll, 500);
})();
