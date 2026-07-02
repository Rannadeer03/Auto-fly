// DronAI live-feed client.
//
// No build step, no framework: this runs as-is on whatever browser a phone
// or laptop ships with on the local network. It owns one RTCPeerConnection
// at a time, negotiates it against POST /offer, and rebuilds the connection
// with backoff whenever it drops — the operator should never need to
// refresh the page mid-flight.

(() => {
  const RECONNECT_DELAYS_MS = [1000, 2000, 5000, 5000, 10000];
  const STATUS_POLL_INTERVAL_MS = 1000;

  const videoEl = document.getElementById("video");
  const connectionStateEl = document.getElementById("connectionState");
  const iceStateEl = document.getElementById("iceState");
  const resolutionEl = document.getElementById("resolution");
  const clientFpsEl = document.getElementById("clientFps");
  const cameraHealthyEl = document.getElementById("cameraHealthy");
  const serverFpsEl = document.getElementById("serverFps");
  const peerCountEl = document.getElementById("peerCount");

  let pc = null;
  let reconnectAttempt = 0;
  let reconnectTimer = null;
  let frameCount = 0;
  let fpsWindowStart = performance.now();
  let videoFrameCallbackHandle = null;

  function setBadge(el, state) {
    el.textContent = state;
    el.className = `badge ${state}`;
  }

  function scheduleReconnect() {
    if (reconnectTimer !== null) return;
    const delay =
      RECONNECT_DELAYS_MS[Math.min(reconnectAttempt, RECONNECT_DELAYS_MS.length - 1)];
    reconnectAttempt += 1;
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      connect();
    }, delay);
  }

  function teardownPeerConnection() {
    if (pc !== null) {
      pc.onconnectionstatechange = null;
      pc.oniceconnectionstatechange = null;
      pc.ontrack = null;
      pc.close();
      pc = null;
    }
    if (videoFrameCallbackHandle !== null && videoEl.cancelVideoFrameCallback) {
      videoEl.cancelVideoFrameCallback(videoFrameCallbackHandle);
      videoFrameCallbackHandle = null;
    }
  }

  async function connect() {
    teardownPeerConnection();

    // No STUN/TURN: the Pi and the browser are expected to be on the same
    // local network, so host candidates alone are sufficient.
    pc = new RTCPeerConnection({ iceServers: [] });
    pc.addTransceiver("video", { direction: "recvonly" });

    pc.ontrack = (event) => {
      if (videoEl.srcObject !== event.streams[0]) {
        videoEl.srcObject = event.streams[0];
      }
      startFpsCounter();
    };

    pc.onconnectionstatechange = () => {
      setBadge(connectionStateEl, pc.connectionState);
      if (pc.connectionState === "connected") {
        reconnectAttempt = 0;
      } else if (["failed", "disconnected", "closed"].includes(pc.connectionState)) {
        scheduleReconnect();
      }
    };

    pc.oniceconnectionstatechange = () => {
      setBadge(iceStateEl, pc.iceConnectionState);
      if (pc.iceConnectionState === "failed") {
        scheduleReconnect();
      }
    };

    try {
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);

      const response = await fetch("/offer", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sdp: offer.sdp, type: offer.type }),
      });

      if (!response.ok) {
        throw new Error(`/offer returned ${response.status}`);
      }

      const answer = await response.json();
      await pc.setRemoteDescription(answer);
    } catch (err) {
      console.error("WebRTC negotiation failed, will retry:", err);
      scheduleReconnect();
    }
  }

  function startFpsCounter() {
    frameCount = 0;
    fpsWindowStart = performance.now();

    if (videoEl.requestVideoFrameCallback) {
      const onFrame = () => {
        frameCount += 1;
        const elapsed = performance.now() - fpsWindowStart;
        if (elapsed >= 1000) {
          clientFpsEl.textContent = ((frameCount / elapsed) * 1000).toFixed(1);
          frameCount = 0;
          fpsWindowStart = performance.now();
        }
        if (videoEl.videoWidth && videoEl.videoHeight) {
          resolutionEl.textContent = `${videoEl.videoWidth}x${videoEl.videoHeight}`;
        }
        videoFrameCallbackHandle = videoEl.requestVideoFrameCallback(onFrame);
      };
      videoFrameCallbackHandle = videoEl.requestVideoFrameCallback(onFrame);
    } else {
      // Fallback for browsers without requestVideoFrameCallback (e.g. some
      // mobile WebViews): approximate fps from decoded-frame deltas.
      let lastFrames = 0;
      let lastTime = performance.now();
      setInterval(() => {
        if (!videoEl.getVideoPlaybackQuality) return;
        const quality = videoEl.getVideoPlaybackQuality();
        const now = performance.now();
        const deltaFrames = quality.totalVideoFrames - lastFrames;
        const deltaTime = now - lastTime;
        if (deltaTime > 0) {
          clientFpsEl.textContent = ((deltaFrames / deltaTime) * 1000).toFixed(1);
        }
        lastFrames = quality.totalVideoFrames;
        lastTime = now;
        if (videoEl.videoWidth && videoEl.videoHeight) {
          resolutionEl.textContent = `${videoEl.videoWidth}x${videoEl.videoHeight}`;
        }
      }, 1000);
    }
  }

  async function pollServerStatus() {
    try {
      const response = await fetch("/api/status");
      if (!response.ok) return;
      const data = await response.json();
      cameraHealthyEl.textContent = data.camera.healthy ? "yes" : "no";
      serverFpsEl.textContent = data.camera.measured_fps.toFixed
        ? data.camera.measured_fps.toFixed(1)
        : data.camera.measured_fps;
      peerCountEl.textContent = data.webrtc.peer_count;
    } catch (err) {
      // Status polling is best-effort; the video pipeline doesn't depend on it.
    }
  }

  setInterval(pollServerStatus, STATUS_POLL_INTERVAL_MS);
  pollServerStatus();
  connect();
})();
