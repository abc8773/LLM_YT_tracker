const channelFilter = document.getElementById("channel-filter");
const themeFilter = document.getElementById("theme-filter");
const searchInput = document.getElementById("search-input");
const tableBody = document.getElementById("video-table-body");
const statChannels = document.getElementById("stat-channels");
const statVideos = document.getElementById("stat-videos");
const statAnalysis = document.getElementById("stat-analysis");
const dataSourceLabel = document.getElementById("data-source");
const lastUpdatedLabel = document.getElementById("last-updated");

let dataset = [];

function stripEmojis(value) {
  if (!value) return value;
  return String(value)
    .replace(/[\uFE0E\uFE0F]/g, "")
    .replace(/[\u2600-\u26FF\u2700-\u27BF\u{1F1E6}-\u{1F1FF}\u{1F300}-\u{1F5FF}\u{1F600}-\u{1F64F}\u{1F680}-\u{1F6FF}\u{1F700}-\u{1F77F}\u{1F780}-\u{1F7FF}\u{1F800}-\u{1F8FF}\u{1F900}-\u{1F9FF}\u{1FA70}-\u{1FAFF}]/gu, "")
    .replace(/\s{2,}/g, " ")
    .trim();
}

function asDateLabel(value) {
  if (!value) return "n/a";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function createChips(values) {
  if (!values || values.length === 0) return '<span class="muted">n/a</span>';
  return `<div class="chip-list">${values
    .map((value) => `<span class="chip">${stripEmojis(value)}</span>`)
    .join("")}</div>`;
}

function renderRows(rows) {
  if (!rows.length) {
    tableBody.innerHTML = '<tr><td colspan="7">No videos match the current filters.</td></tr>';
    return;
  }

  tableBody.innerHTML = rows
    .map(
      (video) => `
        <tr>
          <td>${asDateLabel(video.published_at)}</td>
          <td>
            <strong>${stripEmojis(video.channel)}</strong><br />
            <span class="muted">${stripEmojis(video.transcript_source || "pending transcript")}</span>
          </td>
          <td>
            <a class="video-link" href="${video.url}" target="_blank" rel="noreferrer">${stripEmojis(video.title)}</a>
          </td>
          <td>${createChips(video.speakers)}</td>
          <td>${createChips(video.topics)}</td>
          <td>${createChips(video.themes)}</td>
          <td class="summary">${video.summary ? stripEmojis(video.summary) : '<span class="muted">Summary pending</span>'}</td>
        </tr>
      `
    )
    .join("");
}

function applyFilters() {
  const channel = channelFilter.value.trim().toLowerCase();
  const theme = themeFilter.value.trim().toLowerCase();
  const query = searchInput.value.trim().toLowerCase();

  const filtered = dataset.filter((video) => {
    const matchesChannel = !channel || video.channel.toLowerCase() === channel;
    const matchesTheme = !theme || (video.themes || []).some((item) => item.toLowerCase() === theme);
    const haystack = [
      video.title,
      video.channel,
      ...(video.topics || []),
      ...(video.keywords || []),
      video.summary || "",
    ]
      .join(" ")
      .toLowerCase();
    const matchesQuery = !query || haystack.includes(query);
    return matchesChannel && matchesTheme && matchesQuery;
  });

  renderRows(filtered);
}

function populateFilters(videos) {
  const channels = [...new Set(videos.map((video) => video.channel).filter(Boolean))].sort();
  const themes = [...new Set(videos.flatMap((video) => video.themes || []).filter(Boolean))].sort();

  for (const channel of channels) {
    const option = document.createElement("option");
    option.value = stripEmojis(channel);
    option.textContent = stripEmojis(channel);
    channelFilter.appendChild(option);
  }

  for (const theme of themes) {
    const option = document.createElement("option");
    option.value = stripEmojis(theme);
    option.textContent = stripEmojis(theme);
    themeFilter.appendChild(option);
  }
}

async function loadData() {
  const sources = [
    { url: "/dashboard-data", label: "Live API" },
    { url: "./data/latest.json", label: "Static snapshot" },
  ];

  for (const source of sources) {
    try {
      const response = await fetch(source.url, { cache: "no-store" });
      if (!response.ok) {
        continue;
      }
      const payload = await response.json();
      dataset = payload.videos || [];
      populateFilters(dataset);
      renderRows(dataset);
      statChannels.textContent = String(payload.stats?.channels || 0);
      statVideos.textContent = String(payload.stats?.videos || dataset.length);
      statAnalysis.textContent = String(payload.stats?.analysis || 0);
      dataSourceLabel.textContent = `Data source: ${source.label}`;
      lastUpdatedLabel.textContent = `Last updated: ${asDateLabel(payload.generated_at || payload.stats?.last_video_update)}`;
      return;
    } catch (_error) {
      // Try the next source.
    }
  }

  tableBody.innerHTML = '<tr><td colspan="7">Unable to load tracker data.</td></tr>';
  dataSourceLabel.textContent = "Data source: unavailable";
}

channelFilter.addEventListener("change", applyFilters);
themeFilter.addEventListener("change", applyFilters);
searchInput.addEventListener("input", applyFilters);

loadData();
