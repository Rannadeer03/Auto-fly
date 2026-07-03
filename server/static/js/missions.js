'use strict';

/**
 * DronAI — Mission History module
 *
 * The single web interface for every completed mission: listing, searching,
 * viewing (summary, photo gallery, video, logs, telemetry, metadata, mapping
 * results), downloading as ZIP, and deleting.
 *
 * All mission assets are served straight from the mission folder by the
 * backend (/missions-data/<name>/…); this module never needs anything but
 * HTTP. planning.js delegates to `missionsUI` when the Missions tab opens or
 * a mission session completes.
 */
class MissionsUI {
  constructor() {
    this.missions = [];          // last listing from GET /missions
    this.selected = null;        // currently open mission name
    this.query = '';

    this._searchTimer = null;
    this._detailMap = null;      // Leaflet map inside the detail panel
    this._lightboxPhotos = [];   // [{src, caption}]
    this._lightboxIdx = 0;
    this._galleryShowAll = false;
  }

  init() {
    const search = document.getElementById('mission-search');
    if (search) {
      search.addEventListener('input', () => {
        clearTimeout(this._searchTimer);
        this._searchTimer = setTimeout(() => {
          this.query = search.value;
          this.load();
        }, 250);
      });
    }
    const del = document.getElementById('btn-mission-delete');
    if (del) del.addEventListener('click', () => this.deleteSelected());

    document.addEventListener('keydown', (e) => {
      const lb = document.getElementById('lightbox');
      if (!lb || lb.classList.contains('hidden')) return;
      if (e.key === 'Escape') this.closeLightbox();
      if (e.key === 'ArrowLeft') this.lightboxStep(-1);
      if (e.key === 'ArrowRight') this.lightboxStep(1);
    });
  }

  // ══════════════════════════════════════════ LISTING & SEARCH

  async load() {
    const list = document.getElementById('mission-list');
    try {
      const res = await fetch(`/missions?q=${encodeURIComponent(this.query)}`);
      const data = await res.json();
      this.missions = data.missions || [];
    } catch (_) {
      list.innerHTML = '<p class="text-xs text-red-400">Backend unreachable.</p>';
      return;
    }

    const count = document.getElementById('mission-count');
    if (count) count.textContent = `${this.missions.length} mission${this.missions.length === 1 ? '' : 's'}`;

    if (!this.missions.length) {
      list.innerHTML = `<p class="text-xs text-slate-500">${
        this.query ? 'No missions match your search.' : 'No missions recorded yet.'}</p>`;
      return;
    }

    list.innerHTML = '';
    this.missions.forEach(m => {
      const meta = m.metadata || {};
      const div = document.createElement('div');
      div.className = 'mission-item' + (this.selected === m.name ? ' selected' : '');
      div.innerHTML = `
        <div class="flex items-center justify-between gap-2">
          <span class="text-xs font-bold text-sky-300 truncate">${this._esc(m.name)}</span>
          ${m.active
            ? '<span class="badge badge-bad">● RECORDING</span>'
            : `<span class="text-xs text-slate-500 flex-shrink-0">${m.photo_count} 📷${m.has_video ? ' · 🎥' : ''}</span>`}
        </div>
        <div class="text-xs text-slate-500 mt-1">
          ${this._esc(this._fmtDate(meta.started_at) || '—')} · ${this._esc(meta.end_reason || 'in progress')}
        </div>
        <div class="text-xs text-slate-600 mt-0.5">
          ${this._fmtBytes(m.total_size_bytes)}${m.stats && m.stats.distance_m ? ` · ${this._fmtDistance(m.stats.distance_m)} flown` : ''}
        </div>`;
      div.addEventListener('click', () => this.open(m.name));
      list.appendChild(div);
    });
  }

  // ══════════════════════════════════════════ DETAIL PAGE

  async open(name) {
    this.selected = name;
    this._galleryShowAll = false;
    this.load(); // refresh list highlight (async, fire and forget)

    const panel = document.getElementById('mission-detail');
    panel.innerHTML = '<p class="text-xs text-slate-500">Loading…</p>';
    this._setActions(null);

    let d;
    try {
      const res = await fetch(`/missions/${encodeURIComponent(name)}`);
      if (!res.ok) { panel.innerHTML = '<p class="text-xs text-red-400">Mission not found.</p>'; return; }
      d = await res.json();
    } catch (err) {
      panel.innerHTML = `<p class="text-xs text-red-400">Failed to load mission: ${this._esc(err.message)}</p>`;
      return;
    }

    this._renderDetail(name, d);
    this._setActions(name, d.active);

    // Async enrichments (never block the main render)
    this._renderMap(name, d);
    this._loadLog(name);
  }

  _setActions(name, active = false) {
    const box = document.getElementById('mission-actions');
    if (!box) return;
    if (!name) {
      box.classList.add('hidden');
      box.classList.remove('flex');
      return;
    }
    box.classList.remove('hidden');
    box.classList.add('flex');
    const dl = document.getElementById('btn-mission-download');
    if (dl) {
      dl.href = `/missions/${encodeURIComponent(name)}/download`;
      dl.classList.toggle('opacity-40', !!active);
      dl.title = active ? 'Available after the mission completes' : `Download ${name}.zip`;
    }
    const del = document.getElementById('btn-mission-delete');
    if (del) del.disabled = !!active;
  }

  _renderDetail(name, d) {
    if (this._detailMap) { this._detailMap.remove(); this._detailMap = null; }
    const panel = document.getElementById('mission-detail');
    const meta = d.metadata || {};
    const stats = d.stats || {};
    const photos = d.photos || [];
    const base = `/missions-data/${encodeURIComponent(name)}`;
    this._lightboxPhotos = photos.map(p => ({
      src: `${base}/${p.file}`,
      caption: `${p.file} — ${p.latitude.toFixed(6)}, ${p.longitude.toFixed(6)} @ ${p.altitude_rel.toFixed(1)} m`,
    }));

    let html = `<div class="space-y-5">`;

    // ── Summary ──
    html += `
      <div>
        <p class="text-sm font-bold text-sky-300 mb-2">${this._esc(name)}
          ${d.active ? '<span class="badge badge-bad ml-2">● RECORDING</span>' : ''}</p>
        <div class="grid grid-cols-2 md:grid-cols-3 gap-x-6">
          ${this._row('Mission', meta.mission_name || '—')}
          ${this._row('Started', this._fmtDate(meta.started_at) || '—')}
          ${this._row('Ended', this._fmtDate(meta.ended_at) || '—')}
          ${this._row('Duration', this._fmtDuration(meta.started_at, meta.ended_at))}
          ${this._row('End Reason', meta.end_reason || '—')}
          ${this._row('Waypoints', meta.waypoints_total ?? '—')}
          ${this._row('Photos', meta.photos_captured ?? d.photo_count)}
          ${this._row('Capture Mode', meta.capture_mode || '—')}
          ${this._row('Total Size', this._fmtBytes(d.total_size_bytes))}
        </div>
      </div>`;

    // ── Mapping results ──
    html += `
      <div>
        <p class="text-xs font-bold text-slate-500 uppercase tracking-widest mb-2">
          Mapping Results ${photos.length ? `(${photos.length} geotagged photos)` : ''}
        </p>
        ${photos.length
          ? '<div id="mission-map"></div><p class="text-xs text-slate-600 mt-1">Flight path from telemetry · dots are photo capture points (click to view).</p>'
          : '<p class="text-xs text-slate-500">No geotagged photos recorded for this mission.</p>'}
        ${d.has_mapping_index
          ? `<a class="text-xs text-sky-400 hover:underline" href="${base}/mapping/photos.json" target="_blank">mapping/photos.json (geotag index)</a>`
          : ''}
      </div>`;

    // ── Video ──
    if (d.has_video) {
      html += `
        <div>
          <p class="text-xs font-bold text-slate-500 uppercase tracking-widest mb-2">Video</p>
          <video controls preload="metadata" class="w-full rounded-lg border border-slate-700" style="max-height:340px;">
            <source src="${base}/video.mp4" type="video/mp4">
          </video>
        </div>`;
    }

    // ── Photo gallery ──
    if (photos.length) {
      const limit = this._galleryShowAll ? photos.length : 24;
      const thumbs = photos.slice(0, limit).map((p, i) => `
        <img class="photo-thumb" loading="lazy" src="${base}/${this._esc(p.file)}"
             title="${p.latitude.toFixed(6)}, ${p.longitude.toFixed(6)} @ ${p.altitude_rel.toFixed(1)} m"
             onclick="missionsUI.openLightbox(${i})">`).join('');
      html += `
        <div>
          <p class="text-xs font-bold text-slate-500 uppercase tracking-widest mb-2">
            Photo Gallery (${photos.length})
          </p>
          <div class="grid grid-cols-3 md:grid-cols-4 gap-2">${thumbs}</div>
          ${photos.length > 24 && !this._galleryShowAll
            ? `<button class="btn btn-ghost w-full mt-2" onclick="missionsUI.showAllPhotos()">Show all ${photos.length} photos</button>`
            : ''}
        </div>`;
    }

    // ── Telemetry ──
    html += `
      <div>
        <p class="text-xs font-bold text-slate-500 uppercase tracking-widest mb-2">Telemetry</p>
        ${Object.keys(stats).length ? `
        <div class="grid grid-cols-2 md:grid-cols-3 gap-x-6">
          ${this._row('Samples', stats.samples ?? '—')}
          ${this._row('Distance Flown', this._fmtDistance(stats.distance_m))}
          ${this._row('Max Altitude', stats.max_altitude_rel_m != null ? `${stats.max_altitude_rel_m} m` : '—')}
          ${this._row('Max Speed', stats.max_ground_speed_ms != null ? `${stats.max_ground_speed_ms} m/s` : '—')}
          ${this._row('Battery Start', stats.battery_voltage_start != null ? `${stats.battery_voltage_start.toFixed(2)} V` : '—')}
          ${this._row('Battery End', stats.battery_voltage_end != null ? `${stats.battery_voltage_end.toFixed(2)} V` : '—')}
        </div>` : '<p class="text-xs text-slate-500">No telemetry recorded.</p>'}
        <a class="text-xs text-sky-400 hover:underline" href="${base}/telemetry.json" target="_blank">telemetry.json (raw samples)</a>
      </div>`;

    // ── Mission logs ──
    html += `
      <div>
        <p class="text-xs font-bold text-slate-500 uppercase tracking-widest mb-2">Mission Logs</p>
        <div id="mission-log" class="mission-log-panel font-mono">
          ${d.has_log ? '<span class="text-slate-500">Loading log…</span>'
                      : '<span class="text-slate-500">No mission log recorded.</span>'}
        </div>
      </div>`;

    // ── Metadata & files ──
    const files = d.files || [];
    html += `
      <details class="mission-section">
        <summary class="text-xs font-bold text-slate-500 uppercase tracking-widest mb-2">
          Metadata &amp; Files (${files.length})
        </summary>
        <div class="grid grid-cols-2 md:grid-cols-3 gap-x-6 mb-3 mt-2">
          ${Object.entries(meta).map(([k, v]) => this._row(k.replace(/_/g, ' '), v ?? '—')).join('')}
        </div>
        <div>
          ${files.map(f => `
            <div class="file-row">
              <a href="${base}/${this._esc(f.path)}" target="_blank">${this._esc(f.path)}</a>
              <span class="text-slate-500 flex-shrink-0">${this._fmtBytes(f.size)}</span>
            </div>`).join('')}
        </div>
      </details>`;

    html += `</div>`;
    panel.innerHTML = html;
  }

  showAllPhotos() {
    this._galleryShowAll = true;
    if (this.selected) this.open(this.selected);
  }

  // ══════════════════════════════════════════ MAPPING MINI-MAP

  async _renderMap(name, d) {
    const el = document.getElementById('mission-map');
    if (!el || typeof L === 'undefined') return;
    const photos = d.photos || [];
    if (!photos.length) return;

    const map = L.map('mission-map', { zoomControl: true });
    this._detailMap = map;
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19, attribution: '&copy; OpenStreetMap',
    }).addTo(map);
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
      maxZoom: 19, opacity: 0.85,
    }).addTo(map);

    // Photo capture points
    const pts = [];
    photos.forEach((p, i) => {
      if (!p.latitude && !p.longitude) return;
      pts.push([p.latitude, p.longitude]);
      L.circleMarker([p.latitude, p.longitude], {
        radius: 4, color: '#38bdf8', fillColor: '#0f172a', fillOpacity: 1, weight: 1.5,
      }).bindTooltip(`${p.file} @ ${p.altitude_rel.toFixed(1)} m`)
        .on('click', () => this.openLightbox(i))
        .addTo(map);
    });
    if (pts.length) map.fitBounds(L.latLngBounds(pts).pad(0.15));

    // Flight path from telemetry (may be large — fetched separately)
    try {
      const res = await fetch(`/missions-data/${encodeURIComponent(name)}/telemetry.json`);
      if (res.ok && this._detailMap === map) {
        const samples = await res.json();
        const path = samples
          .filter(s => s.latitude || s.longitude)
          .map(s => [s.latitude, s.longitude]);
        if (path.length > 1) {
          L.polyline(path, { color: '#22c55e', weight: 2, opacity: 0.8 }).addTo(map);
          if (!pts.length) map.fitBounds(L.latLngBounds(path).pad(0.15));
        }
      }
    } catch (_) { /* path is optional */ }
  }

  // ══════════════════════════════════════════ MISSION LOG

  async _loadLog(name) {
    const el = document.getElementById('mission-log');
    if (!el) return;
    try {
      const res = await fetch(`/missions/${encodeURIComponent(name)}/log`);
      const data = await res.json();
      if (!data.lines || !data.lines.length) {
        el.innerHTML = '<span class="text-slate-500">No mission log recorded.</span>';
        return;
      }
      el.innerHTML = data.lines.map(line => {
        const level = (line.match(/\[(DEBUG|INFO|WARNING|ERROR|CRITICAL)\]/) || [])[1] || 'INFO';
        return `<div class="log-${level}">${this._esc(line)}</div>`;
      }).join('');
      if (data.total_lines > data.lines.length) {
        el.innerHTML = `<div class="text-slate-600">… showing last ${data.lines.length} of ${data.total_lines} lines</div>` + el.innerHTML;
      }
      el.scrollTop = el.scrollHeight;
    } catch (_) {
      el.innerHTML = '<span class="text-red-400">Failed to load mission log.</span>';
    }
  }

  // ══════════════════════════════════════════ DELETE

  async deleteSelected() {
    const name = this.selected;
    if (!name) return;
    if (!confirm(`Delete mission "${name}"?\n\nAll photos, video, logs and telemetry for this mission will be permanently removed.`)) return;
    try {
      const res = await fetch(`/missions/${encodeURIComponent(name)}`, { method: 'DELETE' });
      const data = await res.json();
      if (res.ok && data.success) {
        app.showToast(`Mission ${name} deleted.`, 'info');
        this.selected = null;
        this._setActions(null);
        document.getElementById('mission-detail').innerHTML =
          '<p class="text-xs text-slate-500">Select a mission to view its results.</p>';
        if (this._detailMap) { this._detailMap.remove(); this._detailMap = null; }
        this.load();
      } else {
        app.showToast(data.detail || 'Delete failed.', 'error');
      }
    } catch (err) {
      app.showToast('Delete failed: ' + err.message, 'error');
    }
  }

  // ══════════════════════════════════════════ LIGHTBOX

  openLightbox(idx) {
    if (!this._lightboxPhotos.length) return;
    this._lightboxIdx = Math.max(0, Math.min(idx, this._lightboxPhotos.length - 1));
    document.getElementById('lightbox').classList.remove('hidden');
    this._applyLightbox();
  }

  lightboxStep(delta) {
    const n = this._lightboxPhotos.length;
    if (!n) return;
    this._lightboxIdx = (this._lightboxIdx + delta + n) % n;
    this._applyLightbox();
  }

  _applyLightbox() {
    const p = this._lightboxPhotos[this._lightboxIdx];
    document.getElementById('lightbox-img').src = p.src;
    document.getElementById('lightbox-open').href = p.src;
    document.getElementById('lightbox-caption').textContent =
      `${this._lightboxIdx + 1} / ${this._lightboxPhotos.length} — ${p.caption}`;
  }

  closeLightbox(event) {
    // Only close on backdrop click, ✕ button, or Escape — not on the image.
    if (event && event.target && event.target.id === 'lightbox-img') return;
    document.getElementById('lightbox').classList.add('hidden');
  }

  // ══════════════════════════════════════════ UTILS

  _row(label, value) {
    return `<div class="tele-row"><span class="tele-label">${this._esc(String(label))}</span>
            <span class="tele-value">${this._esc(String(value))}</span></div>`;
  }

  _fmtDate(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    if (isNaN(d)) return iso;
    return d.toLocaleString(undefined, {
      year: 'numeric', month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  }

  _fmtDuration(startIso, endIso) {
    if (!startIso || !endIso) return '—';
    const s = new Date(startIso), e = new Date(endIso);
    if (isNaN(s) || isNaN(e)) return '—';
    let secs = Math.max(0, Math.round((e - s) / 1000));
    const m = Math.floor(secs / 60);
    secs %= 60;
    return m ? `${m}m ${secs}s` : `${secs}s`;
  }

  _fmtDistance(m) {
    if (m == null) return '—';
    return m >= 1000 ? `${(m / 1000).toFixed(2)} km` : `${Math.round(m)} m`;
  }

  _fmtBytes(n) {
    if (!n) return '0 B';
    if (n < 1024) return `${n} B`;
    if (n < 1048576) return `${(n / 1024).toFixed(1)} KB`;
    if (n < 1073741824) return `${(n / 1048576).toFixed(1)} MB`;
    return `${(n / 1073741824).toFixed(2)} GB`;
  }

  _esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
}

const missionsUI = new MissionsUI();
document.addEventListener('DOMContentLoaded', () => missionsUI.init());
