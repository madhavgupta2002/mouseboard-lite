import {Motion, textEdit} from "./motion.mjs";

const $ = id => document.getElementById(id);
const motion = new Motion();
const token = location.hash.slice(1);
history.replaceState(null, "", location.pathname); // Keep the pairing code out of copied URLs.
let socket, paused = false, sensors = false, composing = false, previous = "";
let pendingX = 0, pendingY = 0, lastSensor = 0, heartbeat, wakeLock;
const held = new Map();
const connected = () => socket?.readyState === WebSocket.OPEN;
const status = text => { $("status").textContent = text; };
const send = message => {
  if (!connected()) return;
  // Never silently discard a button release or a keystroke on a slow connection.
  if (socket.bufferedAmount > 8192) { socket.close(); return; }
  socket.send(JSON.stringify(message));
};
const resetMotion = () => { motion.reset(); pendingX = pendingY = 0; };

function release() {
  held.clear();
  document.querySelectorAll(".pressed").forEach(element => element.classList.remove("pressed"));
  send({type: "release"});
  resetMotion();
}

function setControls(enabled) {
  document.querySelectorAll("main button, textarea").forEach(element => { element.disabled = !enabled; });
}

async function connect() {
  if (connected()) {
    release(); socket.close(); return;
  }
  if (!isSecureContext) return status("Open the HTTPS pairing link after installing the certificate.");
  if (!token) return status("Scan the pairing QR shown on the computer.");
  $("connect").disabled = true;
  try {
    if (!window.DeviceOrientationEvent) throw new Error("This browser has no motion sensor API.");
    if (typeof DeviceOrientationEvent.requestPermission === "function") {
      const permission = await DeviceOrientationEvent.requestPermission();
      if (permission !== "granted") throw new Error("Motion permission was denied.");
    }
    socket = new WebSocket(`wss://${location.host}/ws`, `mouseboard.${token}`);
    status("Connecting…");
    socket.onopen = async () => {
      paused = false; sensors = false; lastSensor = performance.now(); resetMotion();
      previous = ""; $("typing").value = ""; $("pause").textContent = "Pause";
      $("connect").textContent = "Disconnect"; $("connect").disabled = false;
      setControls(true); status("Connected · waiting for motion");
      heartbeat = setInterval(() => {
        send({type: "ping"});
        if (!sensors && performance.now() - lastSensor > 3000)
          status("Connected · allow motion sensors in browser site settings");
      }, 1000);
      try { wakeLock = await navigator.wakeLock?.request("screen"); } catch { /* Manual screen timeout still works. */ }
    };
    socket.onmessage = event => {
      const message = JSON.parse(event.data);
      if (message.type === "error") status(message.message);
    };
    socket.onerror = () => status("Connection failed. Check Wi-Fi, certificate, and the current pairing QR.");
    socket.onclose = () => {
      clearInterval(heartbeat); release(); setControls(false);
      wakeLock?.release(); wakeLock = null;
      $("connect").textContent = "Connect"; $("connect").disabled = false;
      status("Disconnected · keep the phone page visible and tap Connect");
    };
  } catch (error) {
    status(error.message); $("connect").disabled = false;
  }
}

window.addEventListener("deviceorientation", event => {
  if (!connected() || paused) return;
  if (![event.alpha, event.beta, event.gamma].every(Number.isFinite)) return;
  if (!sensors) { sensors = true; status("Connected · motion ready"); }
  lastSensor = performance.now();
  if (document.activeElement === $("typing")) { resetMotion(); return; }
  const [x, y] = motion.update(event.alpha, event.beta, event.gamma, lastSensor / 1000, +$("speed").value);
  pendingX += x; pendingY += y;
});

function frame() {
  if (connected() && !paused && socket.bufferedAmount < 8192) {
    const x = Math.trunc(pendingX), y = Math.trunc(pendingY);
    if (x || y) {
      send({type: "move", x, y});
      pendingX -= x; pendingY -= y;
    }
  } else pendingX = pendingY = 0;
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
$("connect").addEventListener("click", connect);
$("center").addEventListener("click", () => { release(); send({type: "center"}); });
$("pause").addEventListener("click", () => {
  paused = !paused; release();
  $("pause").textContent = paused ? "Resume" : "Pause";
  status(paused ? "Motion paused · clicks and keyboard still work" : "Connected · motion ready");
});

for (const button of ["left", "right"]) {
  const pad = $(button);
  pad.addEventListener("contextmenu", event => event.preventDefault());
  pad.addEventListener("pointerdown", event => {
    event.preventDefault();
    if (!connected() || held.has(button)) return;
    pad.setPointerCapture(event.pointerId); held.set(button, event.pointerId);
    pad.classList.add("pressed"); send({type: "button", button, down: true});
  });
  const up = event => {
    if (held.get(button) !== event.pointerId) return;
    held.delete(button); pad.classList.remove("pressed");
    send({type: "button", button, down: false});
  };
  ["pointerup", "pointercancel", "lostpointercapture"].forEach(name => pad.addEventListener(name, up));
}

let scrollPointer = null, scrollY = 0, scrollRemainder = 0;
$("scroll").addEventListener("pointerdown", event => {
  if (!connected() || scrollPointer !== null) return;
  $("scroll").setPointerCapture(event.pointerId);
  scrollPointer = event.pointerId; scrollY = event.clientY; scrollRemainder = 0;
});
$("scroll").addEventListener("pointermove", event => {
  if (event.pointerId !== scrollPointer) return;
  scrollRemainder += event.clientY - scrollY; scrollY = event.clientY;
  const steps = Math.trunc(scrollRemainder / 18);
  if (steps) { send({type: "scroll", y: steps}); scrollRemainder -= steps * 18; }
});
["pointerup", "pointercancel", "lostpointercapture"].forEach(name =>
  $("scroll").addEventListener(name, () => { scrollPointer = null; }));

function type() {
  if (composing) return;
  const current = $("typing").value.replace(/\n/g, "");
  const edit = textEdit(previous, current);
  if (edit.remove > 256 || edit.text.length > 256 || /[^\x20-\x7e]/.test(current)) {
    $("typing").value = previous; return status("Use English text, up to 256 changed characters at once.");
  }
  send(edit); previous = current; $("typing").value = current;
  $("typing").setSelectionRange(current.length, current.length);
}
$("typing").addEventListener("compositionstart", () => { composing = true; });
$("typing").addEventListener("compositionend", () => { composing = false; type(); });
$("typing").addEventListener("input", type);
$("typing").addEventListener("beforeinput", event => {
  if (event.inputType === "insertLineBreak" || event.inputType === "insertParagraph") {
    event.preventDefault(); send({type: "key", key: "enter"});
    previous = ""; $("typing").value = "";
  }
});
$("typing").addEventListener("blur", () => { previous = ""; $("typing").value = ""; });
document.querySelectorAll("[data-key]").forEach(button => {
  button.addEventListener("pointerdown", event => event.preventDefault());
  button.addEventListener("click", () => {
    send({type: "key", key: button.dataset.key});
    previous = ""; $("typing").value = "";
  });
});
document.addEventListener("visibilitychange", () => {
  if (document.hidden) { release(); socket?.close(); }
});
window.addEventListener("pagehide", () => { release(); socket?.close(); });
