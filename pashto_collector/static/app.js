const stateUrl = "/api/state";
const foldersUrl = "/api/folders?limit=300";

const els = {
  projectRoot: document.querySelector("#projectRoot"),
  linkStatus: document.querySelector("#linkStatus"),
  downloadStatus: document.querySelector("#downloadStatus"),
  linkCurrent: document.querySelector("#linkCurrent"),
  downloadCurrent: document.querySelector("#downloadCurrent"),
  enabledSources: document.querySelector("#enabledSources"),
  scannedFolders: document.querySelector("#scannedFolders"),
  totalLinks: document.querySelector("#totalLinks"),
  pendingDownloads: document.querySelector("#pendingDownloads"),
  downloadedLinks: document.querySelector("#downloadedLinks"),
  metadataLinks: document.querySelector("#metadataLinks"),
  failedLinks: document.querySelector("#failedLinks"),
  totalFiles: document.querySelector("#totalFiles"),
  totalSizeMetric: document.querySelector("#totalSizeMetric"),
  updatedAt: document.querySelector("#updatedAt"),
  sourceCount: document.querySelector("#sourceCount"),
  totalSize: document.querySelector("#totalSize"),
  lastError: document.querySelector("#lastError"),
  linkStatusBars: document.querySelector("#linkStatusBars"),
  sourceBars: document.querySelector("#sourceBars"),
  linkTypeBars: document.querySelector("#linkTypeBars"),
  fileTypeBars: document.querySelector("#fileTypeBars"),
  domainBars: document.querySelector("#domainBars"),
  folderStatsBody: document.querySelector("#folderStatsBody"),
  linksBody: document.querySelector("#linksBody"),
  downloadQueueBody: document.querySelector("#downloadQueueBody"),
  completedDownloadsBody: document.querySelector("#completedDownloadsBody"),
  failedDownloadsBody: document.querySelector("#failedDownloadsBody"),
  foldersBody: document.querySelector("#foldersBody"),
  domainsBody: document.querySelector("#domainsBody"),
  eventsBody: document.querySelector("#eventsBody"),
  linkSearch: document.querySelector("#linkSearch"),
  statusFilter: document.querySelector("#statusFilter"),
  sourceFilter: document.querySelector("#sourceFilter"),
  domainStatusFilter: document.querySelector("#domainStatusFilter"),
  domainCount: document.querySelector("#domainCount"),
  startLinksBtn: document.querySelector("#startLinksBtn"),
  stopLinksBtn: document.querySelector("#stopLinksBtn"),
  startDownloadsBtn: document.querySelector("#startDownloadsBtn"),
  stopDownloadsBtn: document.querySelector("#stopDownloadsBtn"),
  refreshFoldersBtn: document.querySelector("#refreshFoldersBtn"),
  folderLimit: document.querySelector("#folderLimit"),
  resultsPerFolder: document.querySelector("#resultsPerFolder"),
  downloadBatchSize: document.querySelector("#downloadBatchSize"),
  continuousDownloads: document.querySelector("#continuousDownloads"),
};

let latestLinks = [];
let latestQueue = [];
let latestCompleted = [];
let latestFailed = [];
let latestDomains = [];
let latestEvents = [];
let latestSources = [];

function fmtNumber(value) {
  return new Intl.NumberFormat().format(value || 0);
}

function fmtBytes(value) {
  if (!value) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = value;
  let idx = 0;
  while (size >= 1024 && idx < units.length - 1) {
    size /= 1024;
    idx += 1;
  }
  return `${size.toFixed(idx === 0 ? 0 : 1)} ${units[idx]}`;
}

function progressLabel(link) {
  const downloaded = link.downloaded_bytes || link.bytes || 0;
  const total = link.total_bytes || 0;
  if (total > 0) {
    return `${fmtBytes(downloaded)} / ${fmtBytes(total)}`;
  }
  if (downloaded > 0) {
    return `${fmtBytes(downloaded)} downloaded`;
  }
  return "Waiting";
}

function progressPercent(link) {
  const downloaded = link.downloaded_bytes || link.bytes || 0;
  const total = link.total_bytes || 0;
  if (!total) return 0;
  return Math.max(0, Math.min(100, Math.round((downloaded / total) * 100)));
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function postJson(url, payload = {}) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  return response.json();
}

function renderBars(container, items) {
  const visible = items.filter((item) => item.value > 0);
  if (!visible.length) {
    container.innerHTML = `<p class="empty">No data yet.</p>`;
    return;
  }
  const max = Math.max(...visible.map((item) => item.value), 1);
  container.innerHTML = visible
    .map((item) => {
      const width = Math.max(2, Math.round((item.value / max) * 100));
      return `
        <div class="barRow">
          <span>${escapeHtml(item.label)}</span>
          <div class="track"><div class="fill" style="width:${width}%"></div></div>
          <strong>${fmtNumber(item.value)}</strong>
        </div>
      `;
    })
    .join("");
}

function renderFolderStats(rows) {
  if (!rows.length) {
    els.folderStatsBody.innerHTML = `<tr><td colspan="8">No downloaded files yet.</td></tr>`;
    return;
  }
  els.folderStatsBody.innerHTML = rows
    .map(
      (row) => `
        <tr>
          <td>${escapeHtml(row.folder)}</td>
          <td>${fmtNumber(row.total)}</td>
          <td>${fmtNumber(row.text)}</td>
          <td>${fmtNumber(row.pdf)}</td>
          <td>${fmtNumber(row.video)}</td>
          <td>${fmtNumber(row.audio)}</td>
          <td>${fmtNumber(row.image)}</td>
          <td>${fmtBytes(row.bytes)}</td>
        </tr>
      `,
    )
    .join("");
}

function renderLinks(rows) {
  const search = els.linkSearch.value.trim().toLowerCase();
  const status = els.statusFilter.value;
  const source = els.sourceFilter.value;
  rows = rows.filter((link) => {
    if (status && link.status !== status) return false;
    if (source && link.source !== source) return false;
    if (!search) return true;
    const haystack = `${link.title} ${link.folder} ${link.source} ${link.kind} ${link.reason}`.toLowerCase();
    return haystack.includes(search);
  });
  if (!rows.length) {
    els.linksBody.innerHTML = `<tr><td colspan="6">No links have been collected yet.</td></tr>`;
    return;
  }
  els.linksBody.innerHTML = rows
    .map((link) => {
      const detail = link.reason || link.download_url || "";
      const title = link.page_url
        ? `<a href="${escapeHtml(link.page_url)}" target="_blank" rel="noreferrer">${escapeHtml(link.title)}</a>`
        : escapeHtml(link.title);
      return `
        <tr>
          <td><span class="pill ${escapeHtml(link.status)}">${escapeHtml(link.status)}</span></td>
          <td>${escapeHtml(link.source)}</td>
          <td>${escapeHtml(link.kind)}</td>
          <td>${title}</td>
          <td>${escapeHtml(link.folder)}</td>
          <td>${escapeHtml(link.download_url || link.page_url || detail)}</td>
        </tr>
      `;
    })
    .join("");
}

function linkTitle(link) {
  return link.page_url
    ? `<a href="${escapeHtml(link.page_url)}" target="_blank" rel="noreferrer">${escapeHtml(link.title)}</a>`
    : escapeHtml(link.title);
}

function renderDownloadQueue(rows) {
  if (!rows.length) {
    els.downloadQueueBody.innerHTML = `<tr><td colspan="6">No pending downloads.</td></tr>`;
    return;
  }
  els.downloadQueueBody.innerHTML = rows
    .map((link) => {
      const percent = progressPercent(link);
      return `
        <tr>
          <td><span class="pill ${escapeHtml(link.status)}">${escapeHtml(link.status)}</span></td>
          <td>${escapeHtml(link.source)}</td>
          <td>${linkTitle(link)}</td>
          <td>${escapeHtml(link.folder)}</td>
          <td>
            <div class="progressCell">
              <div class="progressTrack"><div class="progressFill" style="width:${percent}%"></div></div>
              <span>${escapeHtml(progressLabel(link))}${percent ? ` (${percent}%)` : ""}</span>
            </div>
          </td>
          <td>${escapeHtml(link.download_url || link.page_url || link.reason || "")}</td>
        </tr>
      `;
    })
    .join("");
}

function renderCompletedDownloads(rows) {
  if (!rows.length) {
    els.completedDownloadsBody.innerHTML = `<tr><td colspan="6">No completed downloads yet.</td></tr>`;
    return;
  }
  els.completedDownloadsBody.innerHTML = rows
    .map(
      (link) => `
        <tr>
          <td><span class="pill ${escapeHtml(link.status)}">${escapeHtml(link.status)}</span></td>
          <td>${escapeHtml(link.source)}</td>
          <td>${escapeHtml(link.kind)}</td>
          <td>${linkTitle(link)}</td>
          <td>${escapeHtml(link.saved_path || link.reason || "")}</td>
          <td>${fmtBytes(link.bytes)}</td>
        </tr>
      `,
    )
    .join("");
}

function renderFailedDownloads(rows) {
  if (!rows.length) {
    els.failedDownloadsBody.innerHTML = `<tr><td colspan="5">No failed downloads.</td></tr>`;
    return;
  }
  els.failedDownloadsBody.innerHTML = rows
    .map(
      (link) => `
        <tr>
          <td><span class="pill ${escapeHtml(link.status)}">${escapeHtml(link.status)}</span></td>
          <td>${escapeHtml(link.source)}</td>
          <td>${linkTitle(link)}</td>
          <td>${escapeHtml(link.folder)}</td>
          <td>${escapeHtml(link.error || link.reason || "")}</td>
        </tr>
      `,
    )
    .join("");
}

function renderDomains(rows) {
  const status = els.domainStatusFilter.value;
  rows = status ? rows.filter((domain) => domain.status === status) : rows;
  els.domainCount.textContent = `${fmtNumber(rows.length)} domains`;
  if (!rows.length) {
    els.domainsBody.innerHTML = `<tr><td colspan="5">No new websites discovered yet.</td></tr>`;
    return;
  }
  els.domainsBody.innerHTML = rows
    .map((domain) => {
      const approveDisabled = domain.status === "approved" ? "disabled" : "";
      const rejectDisabled = domain.status === "rejected" ? "disabled" : "";
      const sample = domain.sample_url
        ? `<a href="${escapeHtml(domain.sample_url)}" target="_blank" rel="noreferrer">${escapeHtml(domain.sample_title || domain.sample_url)}</a>`
        : "";
      return `
        <tr>
          <td>${escapeHtml(domain.domain)}</td>
          <td><span class="pill ${escapeHtml(domain.status)}">${escapeHtml(domain.status)}</span></td>
          <td>${fmtNumber(domain.link_count)}</td>
          <td>${sample}</td>
          <td class="actionCell">
            <button class="tiny approveDomain" data-domain="${escapeHtml(domain.domain)}" ${approveDisabled}>Approve</button>
            <button class="tiny secondary rejectDomain" data-domain="${escapeHtml(domain.domain)}" ${rejectDisabled}>Reject</button>
          </td>
        </tr>
      `;
    })
    .join("");
}

function renderEvents(rows) {
  if (!rows.length) {
    els.eventsBody.innerHTML = `<tr><td colspan="5">No events yet.</td></tr>`;
    return;
  }
  els.eventsBody.innerHTML = rows
    .map(
      (event) => `
        <tr>
          <td>${event.created_at ? new Date(event.created_at).toLocaleTimeString() : ""}</td>
          <td>${escapeHtml(event.phase)}</td>
          <td><span class="pill ${escapeHtml(event.level)}">${escapeHtml(event.level)}</span></td>
          <td>${escapeHtml(event.message)}</td>
          <td>${escapeHtml(event.folder || "")}</td>
        </tr>
      `,
    )
    .join("");
}

function renderSourceChips(sources) {
  latestSources = sources || [];
  if (!latestSources.length) {
    els.enabledSources.textContent = "None";
    return;
  }
  els.enabledSources.innerHTML = latestSources.map((source) => `<span class="sourceChip">${escapeHtml(source)}</span>`).join("");
  const current = els.sourceFilter.value;
  els.sourceFilter.innerHTML = `<option value="">All sources</option>${latestSources
    .map((source) => `<option value="${escapeHtml(source)}">${escapeHtml(source)}</option>`)
    .join("")}`;
  if (latestSources.includes(current)) {
    els.sourceFilter.value = current;
  }
}

function applyPreset(preset) {
  const presets = {
    slow: { folders: 5, results: 1, batch: 1, continuous: false },
    normal: { folders: 25, results: 2, batch: 5, continuous: true },
    deep: { folders: 100, results: 3, batch: 10, continuous: true },
  };
  const values = presets[preset];
  if (!values) return;
  els.folderLimit.value = values.folders;
  els.resultsPerFolder.value = values.results;
  els.downloadBatchSize.value = values.batch;
  els.continuousDownloads.checked = values.continuous;
}

async function updateDomain(domain, action) {
  await postJson(`/api/domain/${action}`, { domain });
  await loadState();
}

async function loadFolders() {
  const response = await fetch(foldersUrl);
  const data = await response.json();
  els.foldersBody.innerHTML = data.folders
    .map(
      (folder) => `
        <tr>
          <td>${escapeHtml(folder.kind)}</td>
          <td>${escapeHtml(folder.path)}</td>
          <td>${escapeHtml(folder.query)}</td>
        </tr>
      `,
    )
    .join("");
}

async function rescanFolders() {
  await postJson("/api/rescan", { limit: 300 });
  await loadFolders();
  await loadState();
}

async function loadState() {
  const response = await fetch(stateUrl);
  const data = await response.json();
  const linksByStatus = data.linksByStatus || {};
  const linksByType = data.linksByType || {};
  const linksBySource = data.linksBySource || {};
  const linksByDomain = data.linksByDomain || [];
  const filesByType = data.filesByType || {};

  els.projectRoot.textContent = data.projectRoot;
  els.linkStatus.textContent = data.linkRunning ? "Links running" : "Links idle";
  els.downloadStatus.textContent = data.downloadRunning ? "Downloads running" : "Downloads idle";
  els.linkStatus.classList.toggle("running", data.linkRunning);
  els.downloadStatus.classList.toggle("running", data.downloadRunning);
  els.linkCurrent.textContent = data.linkCurrent || "Idle";
  els.downloadCurrent.textContent = data.downloadCurrent || "Idle";
  renderSourceChips(data.enabledSources || []);
  els.scannedFolders.textContent = fmtNumber(data.lastScanCount);
  els.totalLinks.textContent = fmtNumber(data.totalLinks);
  els.pendingDownloads.textContent = fmtNumber(data.pendingDownloads);
  els.downloadedLinks.textContent = fmtNumber(linksByStatus.downloaded);
  els.metadataLinks.textContent = fmtNumber(linksByStatus.metadata_saved);
  els.failedLinks.textContent = fmtNumber(linksByStatus.download_failed);
  els.totalFiles.textContent = fmtNumber(data.totalFiles);
  els.totalSizeMetric.textContent = fmtBytes(data.totalBytes);
  els.updatedAt.textContent = data.updatedAt ? new Date(data.updatedAt).toLocaleTimeString() : "";
  els.totalSize.textContent = fmtBytes(data.totalBytes);
  els.lastError.textContent = data.lastError || "";
  els.sourceCount.textContent = `${fmtNumber(Object.keys(linksBySource).length)} active`;

  els.startLinksBtn.disabled = data.linkRunning;
  els.stopLinksBtn.disabled = !data.linkRunning;
  els.startDownloadsBtn.disabled = data.downloadRunning;
  els.stopDownloadsBtn.disabled = !data.downloadRunning;

  renderBars(
    els.linkStatusBars,
    ["link_found", "downloading", "downloaded", "metadata_saved", "download_failed"].map((label) => ({
      label,
      value: linksByStatus[label] || 0,
    })),
  );
  renderBars(
    els.sourceBars,
    Object.entries(linksBySource).map(([label, value]) => ({ label, value })),
  );
  renderBars(
    els.linkTypeBars,
    Object.entries(linksByType).map(([label, value]) => ({ label, value })),
  );
  renderBars(
    els.fileTypeBars,
    Object.entries(filesByType).map(([label, value]) => ({ label, value })),
  );
  renderBars(
    els.domainBars,
    linksByDomain.map((item) => ({ label: item.domain, value: item.count })),
  );
  latestLinks = data.collectedLinks || data.recentLinks || [];
  latestQueue = [...(data.activeDownloads || []), ...(data.collectedLinks || [])];
  latestCompleted = data.completedDownloads || [];
  latestFailed = data.failedDownloads || [];
  latestDomains = data.candidateDomains || [];
  latestEvents = data.recentEvents || [];
  renderFolderStats(data.folderStats || []);
  renderLinks(latestLinks);
  renderDownloadQueue(latestQueue);
  renderCompletedDownloads(latestCompleted);
  renderFailedDownloads(latestFailed);
  renderDomains(latestDomains);
  renderEvents(latestEvents);
}

els.startLinksBtn.addEventListener("click", async () => {
  els.startLinksBtn.disabled = true;
  await postJson("/api/start-links", {
    folderLimit: Number(els.folderLimit.value || 25),
    resultsPerFolder: Number(els.resultsPerFolder.value || 1),
  });
  await loadState();
});

els.stopLinksBtn.addEventListener("click", async () => {
  await postJson("/api/stop-links");
  await loadState();
});

els.startDownloadsBtn.addEventListener("click", async () => {
  els.startDownloadsBtn.disabled = true;
  await postJson("/api/start-downloads", {
    batchSize: Number(els.downloadBatchSize.value || 5),
    continuous: els.continuousDownloads.checked,
  });
  await loadState();
});

els.stopDownloadsBtn.addEventListener("click", async () => {
  await postJson("/api/stop-downloads");
  await loadState();
});

els.refreshFoldersBtn.addEventListener("click", rescanFolders);

document.querySelectorAll(".presetBtn").forEach((button) => {
  button.addEventListener("click", () => applyPreset(button.dataset.preset));
});

els.linkSearch.addEventListener("input", () => renderLinks(latestLinks));
els.statusFilter.addEventListener("change", () => renderLinks(latestLinks));
els.sourceFilter.addEventListener("change", () => renderLinks(latestLinks));
els.domainStatusFilter.addEventListener("change", () => renderDomains(latestDomains));

els.domainsBody.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-domain]");
  if (!button) return;
  const domain = button.dataset.domain;
  if (button.classList.contains("approveDomain")) {
    await updateDomain(domain, "approve");
  } else if (button.classList.contains("rejectDomain")) {
    await updateDomain(domain, "reject");
  }
});

loadState();
loadFolders();
setInterval(loadState, 2500);
