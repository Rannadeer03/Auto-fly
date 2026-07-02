'use strict';

/**
 * Mission Planner — Frontend Application
 *
 * Single-class architecture. All state is owned here.
 * Communicates exclusively with the FastAPI backend via REST.
 * Polls /telemetry at 1 Hz and /logs at 0.5 Hz.
 */
class MissionPlanner {
  constructor() {
    // ── Runtime state ──────────────────────────────────────────────────────
    this.connected      = false;
    this.armed          = false;
    this.missionUploaded = false;
    this.flightMode     = 'UNKNOWN';
    this.selectedFile   = null;
    this.missionInfo    = null;
    this.lastTelemetry  = null;

    // ── Polling handles ───────────────────────────────────────────────────
    this._telemetryTimer = null;
    this._logTimer       = null;

    // ── Log tracking ─────────────────────────────────────────────────────
    this._knownLogCount  = 0;
  }

  // ══════════════════════════════════════════════════════════════════════════
  // INIT
  // ══════════════════════════════════════════════════════════════════════════

  init() {
    this._bindButtons();
    this._bindFileInput();
    this._clockLoop();
    this._updateButtons();
    this._addLogLine('Mission Planner initialised.', 'INFO');
  }

  // ══════════════════════════════════════════════════════════════════════════
  // EVENT BINDING
  // ══════════════════════════════════════════════════════════════════════════

  _bindButtons() {
    const bind = (id, fn) => {
      const el = document.getElementById(id);
      if (el) el.addEventListener('click', () => fn.call(this));
    };
    bind('btn-connect',    this.connect);
    bind('btn-disconnect', this.disconnect);
    bind('btn-upload',     this.uploadMission);
    bind('btn-clear',      this.clearMission);
    bind('btn-arm',        this.arm);
    bind('btn-disarm',     this.disarm);
    bind('btn-start',      this.startMission);
    bind('btn-pause',      this.pause);
    bind('btn-resume',     this.resume);
    bind('btn-rtl',        this.rtl);
    bind('btn-land',       this.land);
    bind('btn-emergency',  this.emergencyStop);
  }

  _bindFileInput() {
    const input    = document.getElementById('file-input');
    const dropzone = document.getElementById('dropzone');

    input.addEventListener('change', (e) => {
      if (e.target.files[0]) this._handleFileSelect(e.target.files[0]);
    });

    dropzone.addEventListener('dragover', (e) => {
      e.preventDefault();
      dropzone.classList.add('drag-over');
    });
    dropzone.addEventListener('dragleave', () => dropzone.classList.remove('drag-over'));
    dropzone.addEventListener('drop', (e) => {
      e.preventDefault();
      dropzone.classList.remove('drag-over');
      if (e.dataTransfer.files[0]) this._handleFileSelect(e.dataTransfer.files[0]);
    });
  }

  // ══════════════════════════════════════════════════════════════════════════
  // FILE SELECTION
  // ══════════════════════════════════════════════════════════════════════════

  _handleFileSelect(file) {
    const name = file.name.toLowerCase();
    if (!name.endsWith('.waypoints') && !name.endsWith('.plan')) {
      this.showToast('Only .waypoints and .plan files are accepted.', 'error');
      return;
    }
    this.selectedFile = file;
    this._el('file-name').textContent = file.name;
    this._el('file-size').textContent = this._fmtBytes(file.size);
    this._show('file-info');
    this._hide('validation-box');
    this._hide('mission-info-panel');
    this._hide('upload-progress');
    this._updateButtons();
  }

  // ══════════════════════════════════════════════════════════════════════════
  // DRONE OPERATIONS
  // ══════════════════════════════════════════════════════════════════════════

  async connect() {
    this._setLoading('btn-connect', true, 'Connecting…');
    const res = await this._api('/connect', 'POST');
    this._setLoading('btn-connect', false, 'Connect');
    if (res && res.success) {
      this.showToast('Connected to Pixhawk.', 'success');
      this._addLogLine('Connected to Pixhawk.', 'INFO');
      this._startPolling();
    } else {
      this.showToast(res ? res.message : 'Connection failed.', 'error');
    }
  }

  async disconnect() {
    this._setLoading('btn-disconnect', true, 'Disconnecting…');
    const res = await this._api('/disconnect', 'POST');
    this._setLoading('btn-disconnect', false, 'Disconnect');
    this._stopPolling();
    this._applyTelemetry(null);
    this.missionUploaded = false;
    if (res && res.success) {
      this.showToast('Disconnected from Pixhawk.', 'info');
      this._addLogLine('Disconnected from Pixhawk.', 'INFO');
    }
  }

  async uploadMission() {
    if (!this.selectedFile) { this.showToast('No file selected.', 'error'); return; }

    const formData = new FormData();
    formData.append('file', this.selectedFile);

    this._setLoading('btn-upload', true, 'Uploading…');
    this._show('upload-progress');
    this._setUploadProgress(10);

    try {
      const res = await this._uploadWithProgress('/upload', formData, (pct) => {
        this._setUploadProgress(Math.round(pct * 0.7)); // file tx = 0-70%
      });

      this._setUploadProgress(100);

      if (res.success) {
        this._setValidation(res.message, 'success');
        this._showMissionInfo(res.mission_info);
        this.missionInfo = res.mission_info;
        if (res.uploaded_to_drone) {
          this.missionUploaded = true;
          this._addLogLine(`Mission uploaded: ${res.mission_info.waypoint_count} waypoints, ${res.mission_info.total_distance_km} km.`, 'INFO');
          this.showToast(`Mission uploaded — ${res.mission_info.waypoint_count} waypoints.`, 'success');
        } else {
          this._addLogLine('Mission parsed. Connect drone to upload to vehicle.', 'INFO');
          this.showToast('Mission parsed. Connect drone to upload.', 'warning');
        }
      } else {
        this._setValidation(res.detail || res.message || 'Upload failed.', 'error');
        this.showToast('Upload failed — see validation panel.', 'error');
      }
    } catch (err) {
      this._setValidation('Upload error: ' + err.message, 'error');
      this.showToast('Upload error.', 'error');
    } finally {
      this._setLoading('btn-upload', false, 'Upload Mission to Drone');
      this._updateButtons();
      setTimeout(() => this._hide('upload-progress'), 1500);
    }
  }

  async clearMission() {
    const res = await this._api('/clear', 'POST');
    if (res && res.success) {
      this.missionUploaded = false;
      this.missionInfo = null;
      this._hide('mission-info-panel');
      this._hide('validation-box');
      this._hide('file-info');
      this.selectedFile = null;
      const input = document.getElementById('file-input');
      if (input) input.value = '';
      this.showToast('Mission cleared.', 'info');
      this._addLogLine('Mission cleared.', 'INFO');
      this._updateButtons();
    } else {
      this.showToast(res ? res.message : 'Clear failed.', 'error');
    }
  }

  async arm() {
    const res = await this._api('/arm', 'POST');
    this._showCmdStatus(res);
    if (res && res.success) {
      this.showToast('Drone armed.', 'success');
      this._addLogLine('ARM command accepted.', 'INFO');
    } else {
      this.showToast(res ? res.message : 'ARM failed.', 'error');
      this._addLogLine('ARM rejected: ' + (res ? res.message : 'unknown error'), 'WARNING');
    }
  }

  async disarm() {
    const res = await this._api('/disarm', 'POST');
    this._showCmdStatus(res);
    if (res && res.success) {
      this.showToast('Drone disarmed.', 'info');
      this._addLogLine('DISARM command accepted.', 'INFO');
    } else {
      this.showToast(res ? res.message : 'DISARM failed.', 'error');
    }
  }

  async startMission() {
    const res = await this._api('/start', 'POST');
    this._showCmdStatus(res);
    if (res && res.success) {
      this.showToast('Mission started — AUTO mode.', 'success');
      this._addLogLine('Mission started in AUTO mode.', 'INFO');
    } else {
      this.showToast(res ? res.message : 'Start failed.', 'error');
      this._addLogLine('START rejected: ' + (res ? res.message : 'unknown'), 'WARNING');
    }
  }

  async pause() {
    const res = await this._api('/pause', 'POST');
    this._showCmdStatus(res);
    if (res && res.success) this.showToast('Mission paused (LOITER).', 'warning');
  }

  async resume() {
    const res = await this._api('/resume', 'POST');
    this._showCmdStatus(res);
    if (res && res.success) this.showToast('Mission resumed (AUTO).', 'success');
  }

  async rtl() {
    const res = await this._api('/rtl', 'POST');
    this._showCmdStatus(res);
    if (res && res.success) {
      this.showToast('Return to Launch initiated.', 'warning');
      this._addLogLine('RTL initiated.', 'WARNING');
    }
  }

  async land() {
    const res = await this._api('/land', 'POST');
    this._showCmdStatus(res);
    if (res && res.success) {
      this.showToast('Landing initiated.', 'warning');
      this._addLogLine('LAND initiated.', 'INFO');
    }
  }

  async emergencyStop() {
    const confirmed = confirm(
      '⚠ EMERGENCY STOP\n\nThis will force-disarm the drone immediately.\nThe drone will fall if airborne.\n\nProceed?'
    );
    if (!confirmed) return;
    const res = await this._api('/emergency_stop', 'POST');
    this._showCmdStatus(res);
    this.showToast('EMERGENCY STOP executed.', 'error');
    this._addLogLine('EMERGENCY STOP executed.', 'CRITICAL');
  }

  clearLogs() {
    const panel = document.getElementById('log-panel');
    panel.innerHTML = '';
    this._addLogLine('Logs cleared.', 'INFO');
    this._api('/logs', 'DELETE').catch(() => {});
  }

  // ══════════════════════════════════════════════════════════════════════════
  // POLLING
  // ══════════════════════════════════════════════════════════════════════════

  _startPolling() {
    this._stopPolling();
    this._pollTelemetry(); // immediate first call
    this._telemetryTimer = setInterval(() => this._pollTelemetry(), 1000);
    this._logTimer = setInterval(() => this._pollLogs(), 2000);
  }

  _stopPolling() {
    clearInterval(this._telemetryTimer);
    clearInterval(this._logTimer);
    this._telemetryTimer = null;
    this._logTimer = null;
  }

  async _pollTelemetry() {
    try {
      const data = await this._api('/telemetry', 'GET');
      if (data) this._applyTelemetry(data);
    } catch (_) { /* silent — connection may have dropped */ }
  }

  async _pollLogs() {
    try {
      const res = await this._api('/logs?count=100', 'GET');
      if (res && res.logs) {
        const fresh = res.logs.slice(this._knownLogCount);
        fresh.forEach(e => this._addLogLine(`[${e.logger}] ${e.msg}`, e.level));
        this._knownLogCount = res.logs.length;
      }
    } catch (_) {}
  }

  // ══════════════════════════════════════════════════════════════════════════
  // TELEMETRY APPLICATION
  // ══════════════════════════════════════════════════════════════════════════

  _applyTelemetry(d) {
    if (!d) {
      // Reset to disconnected state
      this.connected = false;
      this.armed = false;
      this.flightMode = 'UNKNOWN';
      this.missionUploaded = false;
      this._updateConnectionUI(false);
      this._updateButtons();
      return;
    }

    this.connected       = d.connected;
    this.armed           = d.armed;
    this.flightMode      = d.flight_mode || 'UNKNOWN';
    this.missionUploaded = d.mission_uploaded;
    this.lastTelemetry   = d;

    this._updateConnectionUI(d.connected);
    this._updateStatusCard(d);
    this._updateTelemetryPanel(d);
    this._updateHealthBadges(d.health);
    this._updateButtons();

    // Animate telemetry dot
    const dot = document.getElementById('tele-dot');
    if (dot) {
      dot.className = d.connected ? 'dot dot-green' : 'dot dot-gray';
    }
  }

  _updateConnectionUI(connected) {
    const dot    = document.getElementById('hdr-dot');
    const status = document.getElementById('hdr-status');
    const stDot  = document.getElementById('st-dot');
    const stConn = document.getElementById('st-conn');

    if (dot)    dot.className    = connected ? 'dot dot-green' : 'dot dot-red';
    if (status) status.textContent = connected ? 'Connected' : 'Disconnected';
    if (stDot)  stDot.className  = connected ? 'dot dot-green' : 'dot dot-gray';
    if (stConn) stConn.textContent = connected ? 'Connected' : 'Disconnected';
  }

  _updateStatusCard(d) {
    const hb = d.last_heartbeat_ago_s < 99 ? `${d.last_heartbeat_ago_s.toFixed(1)}s ago` : '—';
    this._setText('st-hb',      hb);
    this._setText('st-sys',     d.system_status || '—');
    this._setText('st-mode',    d.flight_mode   || '—');
    this._setText('st-gpsfix',  d.gps.fix_type_str);
    this._setText('st-sats',    String(d.gps.satellites_visible));
    this._setText('st-volt',    `${d.battery.voltage.toFixed(2)} V`);
    this._setText('st-alt',     `${d.position.altitude_rel.toFixed(1)} m`);
    this._setText('st-gs',      `${d.position.ground_speed.toFixed(1)} m/s`);
    this._setText('st-hdg',     `${d.position.heading}°`);
    this._setText('st-mup',     d.mission_uploaded ? 'Yes' : 'No');
    this._setText('st-wpts',    d.mission.total_waypoints > 0 ? String(d.mission.total_waypoints) : '—');
    this._setText('st-cwp',     d.mission.total_waypoints > 0
                                  ? `${d.mission.current_waypoint} / ${d.mission.total_waypoints}`
                                  : '—');

    // Arm status
    const armEl = document.getElementById('st-arm');
    if (armEl) {
      armEl.textContent  = d.armed ? 'ARMED' : 'DISARMED';
      armEl.className    = `tele-value ${d.armed ? 'text-red-400' : 'text-green-400'}`;
    }

    // Battery with colour
    const battEl = document.getElementById('st-batt');
    const pct = d.battery.remaining_percent;
    if (battEl) {
      battEl.textContent = pct >= 0 ? `${pct}%` : '—';
      battEl.className = `tele-value ${pct < 20 ? 'text-red-400' : pct < 40 ? 'text-yellow-400' : 'text-green-400'}`;
    }

    // Header updates
    this._setText('hdr-mode',  d.flight_mode || '—');
    this._setText('hdr-gps',   d.gps.fix_type_str);
    this._setText('hdr-sats',  `${d.gps.satellites_visible} sats`);
    this._setText('hdr-batt',  pct >= 0 ? `${pct}%` : '—');
    const hdrArm = document.getElementById('hdr-arm');
    if (hdrArm) {
      hdrArm.textContent = d.armed ? 'ARMED' : 'DISARMED';
      hdrArm.className = `text-xs font-bold uppercase tracking-widest ${d.armed ? 'text-red-400' : 'text-slate-500'}`;
    }

    // Mission progress bars (status card)
    const mpct = d.mission.progress_percent;
    this._setText('st-prog-pct', `${mpct}%`);
    this._setWidth('st-prog-bar', `${mpct}%`);

    // Link quality
    const lq = d.link_quality_percent;
    this._setText('st-link-pct', `${lq}%`);
    this._setWidth('st-link-bar', `${lq}%`);
  }

  _updateTelemetryPanel(d) {
    const p = d.position;
    const g = d.gps;
    const a = d.attitude;
    const b = d.battery;
    const m = d.mission;

    this._setText('t-lat',   `${p.latitude.toFixed(6)}°`);
    this._setText('t-lon',   `${p.longitude.toFixed(6)}°`);
    this._setText('t-altm',  `${p.altitude_msl.toFixed(1)} m`);
    this._setText('t-altr',  `${p.altitude_rel.toFixed(1)} m`);
    this._setText('t-hdg',   `${p.heading}°`);
    this._setText('t-gs',    `${p.ground_speed.toFixed(2)} m/s`);
    this._setText('t-as',    `${p.air_speed.toFixed(2)} m/s`);
    this._setText('t-cr',    `${p.climb_rate >= 0 ? '+' : ''}${p.climb_rate.toFixed(2)} m/s`);
    this._setText('t-roll',  `${a.roll_deg.toFixed(1)}°`);
    this._setText('t-pitch', `${a.pitch_deg.toFixed(1)}°`);
    this._setText('t-yaw',   `${a.yaw_deg.toFixed(1)}°`);
    this._setText('t-volt',  `${b.voltage.toFixed(2)} V`);
    this._setText('t-curr',  `${b.current.toFixed(2)} A`);
    this._setText('t-brem',  b.remaining_percent >= 0 ? `${b.remaining_percent}%` : '—');
    this._setText('t-bmah',  `${b.consumed_mah.toFixed(0)} mAh`);
    this._setText('t-fix',   g.fix_type_str);
    this._setText('t-sats',  String(g.satellites_visible));
    this._setText('t-hdop',  g.hdop.toFixed(2));
    this._setText('t-vdop',  g.vdop.toFixed(2));
    this._setText('t-cwp',   m.total_waypoints > 0 ? `${m.current_waypoint} / ${m.total_waypoints}` : '—');
    this._setText('t-dwp',   m.total_waypoints > 0 ? `${m.distance_to_waypoint_m.toFixed(0)} m` : '—');

    const prog = m.progress_percent;
    this._setText('t-prog-pct', `${prog}%`);
    this._setWidth('t-prog-bar', `${prog}%`);

    const lq = d.link_quality_percent;
    this._setText('t-link', `${lq}%`);
    this._setWidth('t-link-bar', `${lq}%`);
  }

  _updateHealthBadges(h) {
    const set = (id, ok) => {
      const el = document.getElementById(id);
      if (!el) return;
      el.className = ok ? 'badge badge-ok' : 'badge badge-bad';
    };
    set('h-ekf',     h.ekf_ok);
    set('h-gps',     h.gps_ok);
    set('h-gyro',    h.gyro_ok);
    set('h-accel',   h.accelerometer_ok);
    set('h-baro',    h.barometer_ok);
    set('h-compass', h.compass_ok);
    set('h-batt',    h.battery_ok);
  }

  // ══════════════════════════════════════════════════════════════════════════
  // BUTTON STATE MACHINE
  // ══════════════════════════════════════════════════════════════════════════

  _updateButtons() {
    const c  = this.connected;
    const a  = this.armed;
    const m  = this.missionUploaded;
    const f  = !!this.selectedFile;
    const mode = (this.flightMode || '').toUpperCase();
    const inAuto   = mode === 'AUTO';
    const inLoiter = mode === 'LOITER' || mode === 'BRAKE' || mode === 'POSHOLD';

    this._setBtn('btn-connect',    !c);
    this._setBtn('btn-disconnect', c);
    this._setBtn('btn-upload',     f);
    this._setBtn('btn-clear',      c && m && !inAuto);
    this._setBtn('btn-arm',        c && !a && m);
    this._setBtn('btn-disarm',     c && a  && !inAuto);
    this._setBtn('btn-start',      c && a  && m && !inAuto);
    this._setBtn('btn-pause',      c && a  && inAuto);
    this._setBtn('btn-resume',     c && a  && inLoiter && m);
    this._setBtn('btn-rtl',        c && a);
    this._setBtn('btn-land',       c && a);
    this._setBtn('btn-emergency',  c);
  }

  _setBtn(id, enabled) {
    const el = document.getElementById(id);
    if (!el) return;
    el.disabled = !enabled;
  }

  // ══════════════════════════════════════════════════════════════════════════
  // UI HELPERS
  // ══════════════════════════════════════════════════════════════════════════

  _showMissionInfo(info) {
    if (!info) return;
    this._show('mission-info-panel');
    this._setText('mi-fmt',    info.source_format === 'plan' ? 'QGC .plan (JSON)' : 'QGC .waypoints');
    this._setText('mi-wpts',   String(info.waypoint_count));
    this._setText('mi-nav',    String(info.nav_waypoints));
    this._setText('mi-dist',   `${info.total_distance_km.toFixed(3)} km (${info.total_distance_m.toFixed(0)} m)`);
    this._setText('mi-dur',    `${info.estimated_duration_minutes} min`);
    this._setText('mi-batt',   `~${info.estimated_battery_percent}%`);
    this._setText('mi-altmin', `${info.min_altitude_m.toFixed(1)} m`);
    this._setText('mi-altmax', `${info.max_altitude_m.toFixed(1)} m`);
  }

  _setValidation(msg, type) {
    const box = document.getElementById('validation-box');
    const status = document.getElementById('validation-status');
    if (!box || !status) return;
    this._show('validation-box');
    const styles = {
      success: 'bg-green-900/40 text-green-300 border-green-700/50',
      error:   'bg-red-900/40   text-red-300   border-red-700/50',
      warning: 'bg-yellow-900/40 text-yellow-300 border-yellow-700/50',
    };
    status.className  = `text-xs rounded-lg p-2.5 border ${styles[type] || styles.warning}`;
    status.textContent = msg;
  }

  _showCmdStatus(res) {
    const el = document.getElementById('cmd-status');
    if (!el) return;
    el.classList.remove('hidden');
    el.className = `mt-2 text-xs rounded p-2.5 border ${res && res.success
      ? 'bg-green-900/40 text-green-300 border-green-700/50'
      : 'bg-red-900/40   text-red-300   border-red-700/50'}`;
    el.textContent = res ? res.message : 'No response from server.';
    clearTimeout(this._cmdStatusTimer);
    this._cmdStatusTimer = setTimeout(() => el.classList.add('hidden'), 5000);
  }

  _setLoading(id, loading, text) {
    const el = document.getElementById(id);
    if (!el) return;
    el.disabled = loading;
    if (text) el.textContent = text;
  }

  _setUploadProgress(pct) {
    const bar = document.getElementById('upload-bar');
    const txt = document.getElementById('upload-pct');
    if (bar) bar.style.width = `${pct}%`;
    if (txt) txt.textContent = `${pct}%`;
  }

  _addLogLine(msg, level = 'INFO') {
    const panel = document.getElementById('log-panel');
    if (!panel) return;

    const ts = new Date().toISOString().substr(11, 8);
    const line = document.createElement('div');
    line.className = `log-entry log-${level}`;
    line.innerHTML = `<span class="text-slate-600 mr-2 select-none">${ts}</span><span>${this._escHtml(msg)}</span>`;
    panel.appendChild(line);

    // Trim to 500 entries
    while (panel.children.length > 500) {
      panel.removeChild(panel.firstChild);
    }

    const autoScroll = document.getElementById('log-autoscroll');
    if (!autoScroll || autoScroll.checked) {
      panel.scrollTop = panel.scrollHeight;
    }
  }

  showToast(message, type = 'info') {
    const colours = {
      success: 'bg-green-900/90 text-green-100 border border-green-700/60',
      error:   'bg-red-900/90   text-red-100   border border-red-700/60',
      warning: 'bg-yellow-900/90 text-yellow-100 border border-yellow-700/60',
      info:    'bg-slate-800/95  text-slate-100  border border-slate-600/60',
    };
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast pointer-events-auto ${colours[type] || colours.info}`;
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateX(20px)';
      setTimeout(() => toast.remove(), 350);
    }, 3500);
  }

  // ══════════════════════════════════════════════════════════════════════════
  // API
  // ══════════════════════════════════════════════════════════════════════════

  async _api(url, method = 'GET', body = null) {
    try {
      const opts = {
        method,
        headers: { 'Accept': 'application/json' },
      };
      if (body && method !== 'GET') {
        opts.headers['Content-Type'] = 'application/json';
        opts.body = JSON.stringify(body);
      }
      const res = await fetch(url, opts);
      return await res.json();
    } catch (err) {
      console.error(`API error [${method} ${url}]:`, err);
      return null;
    }
  }

  async _uploadWithProgress(url, formData, onProgress) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', url);
      xhr.setRequestHeader('Accept', 'application/json');

      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total);
      };

      xhr.onload = () => {
        try { resolve(JSON.parse(xhr.responseText)); }
        catch (e) { reject(new Error('Invalid JSON response.')); }
      };
      xhr.onerror = () => reject(new Error('Network error.'));
      xhr.send(formData);
    });
  }

  // ══════════════════════════════════════════════════════════════════════════
  // DOM UTILITIES
  // ══════════════════════════════════════════════════════════════════════════

  _el(id)                { return document.getElementById(id); }
  _show(id)              { const e = this._el(id); if (e) e.classList.remove('hidden'); }
  _hide(id)              { const e = this._el(id); if (e) e.classList.add('hidden'); }
  _setText(id, val)      { const e = this._el(id); if (e) e.textContent = val; }
  _setWidth(id, w)       { const e = this._el(id); if (e) e.style.width = w; }
  _escHtml(s)            { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

  _fmtBytes(n) {
    if (n < 1024) return `${n} B`;
    if (n < 1048576) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / 1048576).toFixed(2)} MB`;
  }

  _clockLoop() {
    const update = () => {
      const el = document.getElementById('clock');
      if (el) el.textContent = new Date().toUTCString().slice(17, 25) + ' UTC';
    };
    update();
    setInterval(update, 1000);
  }
}

// ── Bootstrap ──────────────────────────────────────────────────────────────

const app = new MissionPlanner();
document.addEventListener('DOMContentLoaded', () => app.init());
