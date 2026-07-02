'use strict';

/**
 * DronAI — Planning & Mapping UI
 *
 * Owns the tab navigation, the Leaflet survey-planning map (polygon drawing,
 * grid generation, live drone marker), the mission history browser, and the
 * automatic mission-results display after a mission completes.
 *
 * The flight-control logic stays in app.js (class MissionPlanner, global
 * `app`); this module only reads app.lastTelemetry for the drone marker.
 */
class PlanningUI {
  constructor() {
    this.map = null;
    this.drawing = false;
    this.polygonPoints = [];      // [[lat, lon], ...]
    this.polygonLayer = null;
    this.vertexLayers = [];
    this.gridLayer = null;
    this.droneMarker = null;
    this.mapInitialised = false;

    this.selectedMission = null;
    this._lastSessionActive = false;
    this._lastCompletedSeen = null;
  }

  init() {
    this._bindButtons();
    this._loadDefaults();
    setInterval(() => this._updateDroneMarker(), 1000);
    setInterval(() => this._watchSession(), 3000);
  }

  // ══════════════════════════════════════════ TABS

  showTab(name) {
    for (const t of ['flight', 'planning', 'missions']) {
      document.getElementById(`tab-${t}`).classList.toggle('hidden', t !== name);
      document.getElementById(`tabbtn-${t}`).classList.toggle('active', t === name);
    }
    if (name === 'planning') this._ensureMap();
    if (name === 'missions') this.loadMissions();
  }

  // ══════════════════════════════════════════ MAP

  _ensureMap() {
    if (this.mapInitialised) {
      setTimeout(() => this.map.invalidateSize(), 50);
      return;
    }
    if (typeof L === 'undefined') {
      document.getElementById('map').innerHTML =
        '<p class="text-xs text-red-400 p-4">Leaflet failed to load (no internet?). ' +
        'Planning map unavailable, but file-based mission upload still works.</p>';
      return;
    }
    this.mapInitialised = true;

    this.map = L.map('map', { zoomControl: true }).setView([12.8268, 80.0515], 17);

    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap',
    }).addTo(this.map);
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
      maxZoom: 19, opacity: 0.85,
    }).addTo(this.map);

    this.map.on('click', (e) => this._onMapClick(e));

    // Centre on the drone if we already have a GPS fix
    const t = window.app && app.lastTelemetry;
    if (t && (t.position.latitude || t.position.longitude)) {
      this.map.setView([t.position.latitude, t.position.longitude], 18);
    }
  }

  _bindButtons() {
    const bind = (id, fn) => {
      const el = document.getElementById(id);
      if (el) el.addEventListener('click', () => fn.call(this));
    };
    bind('btn-draw', this.startDrawing);
    bind('btn-finish-poly', this.finishPolygon);
    bind('btn-clear-poly', this.clearPolygon);
    bind('btn-generate', this.generateGrid);
  }

  async _loadDefaults() {
    try {
      const res = await fetch('/config');
      const cfg = await res.json();
      this._setVal('p-alt', cfg.altitude_m);
      this._setVal('p-speed', cfg.speed_ms);
      this._setVal('p-side', cfg.side_overlap_pct);
      this._setVal('p-front', cfg.front_overlap_pct);
      this._setVal('p-angle', cfg.grid_angle_deg);
    } catch (_) { /* defaults in the HTML remain */ }
  }

  // ── Polygon drawing ─────────────────────────────────────────────

  startDrawing() {
    if (!this.mapInitialised) return;
    this.clearPolygon();
    this.drawing = true;
    document.getElementById('btn-finish-poly').classList.remove('hidden');
    document.getElementById('map-hint').textContent =
      'Click the map to add vertices. At least 3 needed, then press “Finish”.';
    this.map.getContainer().style.cursor = 'crosshair';
  }

  _onMapClick(e) {
    if (!this.drawing) return;
    this.polygonPoints.push([e.latlng.lat, e.latlng.lng]);
    const v = L.circleMarker(e.latlng, {
      radius: 5, color: '#38bdf8', fillColor: '#38bdf8', fillOpacity: 0.9,
    }).addTo(this.map);
    this.vertexLayers.push(v);
    this._redrawPolygon(true);
  }

  finishPolygon() {
    if (this.polygonPoints.length < 3) {
      app.showToast('Need at least 3 vertices for a survey area.', 'warning');
      return;
    }
    this.drawing = false;
    this.map.getContainer().style.cursor = '';
    document.getElementById('btn-finish-poly').classList.add('hidden');
    document.getElementById('map-hint').textContent =
      'Area defined. Set parameters and press “Generate Grid & Upload”.';
    this._redrawPolygon(false);
    document.getElementById('btn-generate').disabled = false;
  }

  clearPolygon() {
    this.drawing = false;
    this.polygonPoints = [];
    if (this.polygonLayer) { this.polygonLayer.remove(); this.polygonLayer = null; }
    if (this.gridLayer) { this.gridLayer.remove(); this.gridLayer = null; }
    this.vertexLayers.forEach(v => v.remove());
    this.vertexLayers = [];
    const gen = document.getElementById('btn-generate');
    if (gen) gen.disabled = true;
    const fin = document.getElementById('btn-finish-poly');
    if (fin) fin.classList.add('hidden');
    const pr = document.getElementById('plan-result');
    if (pr) pr.classList.add('hidden');
    if (this.map) this.map.getContainer().style.cursor = '';
  }

  _redrawPolygon(open) {
    if (this.polygonLayer) this.polygonLayer.remove();
    if (this.polygonPoints.length < 2) return;
    this.polygonLayer = open
      ? L.polyline(this.polygonPoints, { color: '#38bdf8', weight: 2, dashArray: '5,5' })
      : L.polygon(this.polygonPoints, {
          color: '#38bdf8', weight: 2, fillColor: '#38bdf8', fillOpacity: 0.08,
        });
    this.polygonLayer.addTo(this.map);
  }

  // ── Grid generation ─────────────────────────────────────────────

  async generateGrid() {
    if (this.polygonPoints.length < 3) return;
    const btn = document.getElementById('btn-generate');
    btn.disabled = true;
    btn.textContent = 'Generating…';

    const body = {
      polygon: this.polygonPoints,
      altitude_m: parseFloat(this._val('p-alt')) || 30,
      speed_ms: parseFloat(this._val('p-speed')) || 5,
      side_overlap_pct: parseFloat(this._val('p-side')) || 65,
      front_overlap_pct: parseFloat(this._val('p-front')) || 75,
      angle_deg: parseFloat(this._val('p-angle')) || 0,
      upload: true,
    };
    const photoDist = parseFloat(this._val('p-photodist'));
    if (photoDist > 0) body.photo_distance_m = photoDist;

    try {
      const res = await fetch('/mission/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) {
        app.showToast(data.detail || 'Grid generation failed.', 'error');
        return;
      }

      this._drawGrid(data.mission_info);
      this._showPlanResult(data);
      app.showToast(data.message, data.uploaded_to_drone ? 'success' : 'warning');
      if (data.uploaded_to_drone) app.missionUploaded = true;
    } catch (err) {
      app.showToast('Grid generation error: ' + err.message, 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = 'Generate Grid & Upload';
    }
  }

  _drawGrid(mission) {
    if (this.gridLayer) this.gridLayer.remove();
    if (!mission || !mission.waypoints) return;
    const pts = mission.waypoints
      .filter(w => w.command === 16 && !w.current && (w.latitude || w.longitude))
      .map(w => [w.latitude, w.longitude]);
    if (!pts.length) return;
    this.gridLayer = L.layerGroup();
    L.polyline(pts, { color: '#22c55e', weight: 2 }).addTo(this.gridLayer);
    pts.forEach((p, i) => {
      L.circleMarker(p, {
        radius: 3, color: '#22c55e', fillColor: '#0f172a', fillOpacity: 1, weight: 1.5,
      }).bindTooltip(`WP ${i + 1}`).addTo(this.gridLayer);
    });
    this.gridLayer.addTo(this.map);
  }

  _showPlanResult(data) {
    const m = data.mission_info, p = data.plan_info || {};
    document.getElementById('plan-result').classList.remove('hidden');
    this._setText('pr-wpts', m.waypoint_count);
    this._setText('pr-lines', p.line_count ?? '—');
    this._setText('pr-spacing', p.line_spacing_m != null ? `${p.line_spacing_m} m` : '—');
    this._setText('pr-photo', p.photo_spacing_m != null ? `${p.photo_spacing_m} m` : '—');
    this._setText('pr-dist', `${m.total_distance_km} km`);
    this._setText('pr-dur', `${m.estimated_duration_minutes} min`);
    this._setText('pr-photos', p.estimated_photos ?? '—');
    this._setText('pr-uploaded', data.uploaded_to_drone
      ? (data.verified ? 'Yes ✓ verified' : 'Yes (unverified)')
      : 'No — drone offline');
  }

  // ── Live drone marker ───────────────────────────────────────────

  _updateDroneMarker() {
    if (!this.mapInitialised) return;
    const t = window.app && app.lastTelemetry;
    if (!t || !t.connected) return;
    const { latitude, longitude, heading } = t.position;
    if (!latitude && !longitude) return;

    if (!this.droneMarker) {
      this.droneMarker = L.marker([latitude, longitude], {
        icon: L.divIcon({
          className: '',
          html: '<div id="drone-icon" style="font-size:22px; transform-origin:center;">🛩️</div>',
          iconSize: [24, 24], iconAnchor: [12, 12],
        }),
      }).addTo(this.map).bindTooltip('Drone');
    } else {
      this.droneMarker.setLatLng([latitude, longitude]);
    }
    const icon = document.getElementById('drone-icon');
    if (icon) icon.style.transform = `rotate(${heading}deg)`;
  }

  // ══════════════════════════════════════════ MISSION HISTORY & RESULTS

  async loadMissions() {
    try {
      const res = await fetch('/missions');
      const data = await res.json();
      const list = document.getElementById('mission-list');
      if (!data.missions.length) {
        list.innerHTML = '<p class="text-xs text-slate-500">No missions recorded yet.</p>';
        return;
      }
      list.innerHTML = '';
      data.missions.forEach(m => {
        const meta = m.metadata || {};
        const div = document.createElement('div');
        div.className = 'mission-item' + (this.selectedMission === m.name ? ' selected' : '');
        div.innerHTML = `
          <div class="flex items-center justify-between">
            <span class="text-xs font-bold text-sky-300">${this._esc(m.name)}</span>
            <span class="text-xs text-slate-500">${m.photo_count} 📷${m.has_video ? ' · 🎥' : ''}</span>
          </div>
          <div class="text-xs text-slate-500 mt-1">
            ${this._esc(meta.started_at || '')} — ${this._esc(meta.end_reason || 'in progress')}
          </div>`;
        div.addEventListener('click', () => this.showMissionDetail(m.name));
        list.appendChild(div);
      });
    } catch (_) { /* backend unreachable */ }
  }

  async showMissionDetail(name) {
    this.selectedMission = name;
    this.loadMissions(); // refresh selection highlight
    const panel = document.getElementById('mission-detail');
    panel.innerHTML = '<p class="text-xs text-slate-500">Loading…</p>';
    try {
      const res = await fetch(`/missions/${encodeURIComponent(name)}`);
      if (!res.ok) { panel.innerHTML = '<p class="text-xs text-red-400">Mission not found.</p>'; return; }
      const d = await res.json();
      const meta = d.metadata || {};
      const photos = d.photos || [];
      const base = `/missions-data/${encodeURIComponent(name)}`;

      let html = `
        <div class="space-y-4">
          <div>
            <p class="text-sm font-bold text-sky-300 mb-2">${this._esc(name)}</p>
            <div class="grid grid-cols-2 md:grid-cols-3 gap-x-6">
              ${this._metaRow('Mission', meta.mission_name || '—')}
              ${this._metaRow('Started', meta.started_at || '—')}
              ${this._metaRow('Ended', meta.ended_at || '—')}
              ${this._metaRow('End Reason', meta.end_reason || '—')}
              ${this._metaRow('Photos', meta.photos_captured ?? d.photo_count)}
              ${this._metaRow('Capture Mode', meta.capture_mode || '—')}
            </div>
          </div>`;

      if (d.has_video) {
        html += `
          <div>
            <p class="text-xs font-bold text-slate-500 uppercase tracking-widest mb-2">Video</p>
            <video controls preload="metadata" class="w-full rounded-lg border border-slate-700" style="max-height:300px;">
              <source src="${base}/video.mp4" type="video/mp4">
            </video>
          </div>`;
      }

      if (photos.length) {
        const thumbs = photos.slice(0, 24).map(p => `
          <a href="${base}/${p.file}" target="_blank" title="${p.latitude.toFixed(6)}, ${p.longitude.toFixed(6)} @ ${p.altitude_rel.toFixed(1)}m">
            <img class="photo-thumb" loading="lazy" src="${base}/${p.file}">
          </a>`).join('');
        html += `
          <div>
            <p class="text-xs font-bold text-slate-500 uppercase tracking-widest mb-2">
              Mapping Photos (${photos.length} geotagged${photos.length > 24 ? ', showing 24' : ''})
            </p>
            <div class="grid grid-cols-3 md:grid-cols-4 gap-2">${thumbs}</div>
          </div>`;
      }

      html += `
        <div class="flex gap-3 pt-1">
          <a class="text-xs text-sky-400 hover:underline" href="${base}/telemetry.json" target="_blank">telemetry.json</a>
          <a class="text-xs text-sky-400 hover:underline" href="${base}/mission.json" target="_blank">mission.json</a>
          <a class="text-xs text-sky-400 hover:underline" href="${base}/metadata.json" target="_blank">metadata.json</a>
          <a class="text-xs text-sky-400 hover:underline" href="${base}/mapping/photos.json" target="_blank">mapping/photos.json</a>
        </div>
      </div>`;
      panel.innerHTML = html;
    } catch (err) {
      panel.innerHTML = `<p class="text-xs text-red-400">Failed to load mission: ${this._esc(err.message)}</p>`;
    }
  }

  _metaRow(label, value) {
    return `<div class="tele-row"><span class="tele-label">${label}</span>
            <span class="tele-value">${this._esc(String(value))}</span></div>`;
  }

  // ── Auto-display results when a mission finishes ────────────────

  async _watchSession() {
    try {
      const res = await fetch('/mission/session');
      const s = await res.json();
      const finished = this._lastSessionActive && !s.active;
      const newCompletion = s.last_completed && s.last_completed !== this._lastCompletedSeen;
      this._lastSessionActive = s.active;

      if (finished && newCompletion) {
        this._lastCompletedSeen = s.last_completed;
        app.showToast(`Mission complete — ${s.last_completed}`, 'success');
        this.showTab('missions');
        await this.loadMissions();
        this.showMissionDetail(s.last_completed);
      } else if (s.last_completed) {
        // Remember completions we didn't witness so we don't replay them later.
        if (this._lastCompletedSeen === null) this._lastCompletedSeen = s.last_completed;
      }
    } catch (_) { /* backend unreachable */ }
  }

  // ── utils ───────────────────────────────────────────────────────

  _val(id) { const e = document.getElementById(id); return e ? e.value : ''; }
  _setVal(id, v) { const e = document.getElementById(id); if (e && v != null) e.value = v; }
  _setText(id, v) { const e = document.getElementById(id); if (e) e.textContent = v; }
  _esc(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
}

const ui = new PlanningUI();
document.addEventListener('DOMContentLoaded', () => ui.init());
