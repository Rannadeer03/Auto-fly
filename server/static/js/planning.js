'use strict';

/**
 * DronAI — Planning & Mapping UI
 *
 * Owns the tab navigation, the Leaflet survey-planning map (polygon drawing,
 * grid generation, live drone marker), and the automatic switch to the
 * Missions tab after a mission completes.
 *
 * The flight-control logic stays in app.js (class MissionPlanner, global
 * `app`); the mission history browser lives in missions.js (global
 * `missionsUI`). This module only reads app.lastTelemetry for the drone
 * marker and delegates to missionsUI for history.
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
    if (name === 'missions') missionsUI.load();
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
        missionsUI.open(s.last_completed);
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
