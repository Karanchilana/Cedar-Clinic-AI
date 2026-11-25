const $ = (id) => document.getElementById(id);

let doctors = [];
let appointments = [];
let selectedDay = null;

let socket = null;
let micStream = null;
let micNode = null;
let audioCtx = null;
let speaker = null;
let playHead = 0;
let playing = [];
let stopRing = null;
let timer = null;
let startedAt = 0;
let cardTimeout = null;
const analysers = { agent: null, user: null };

const phone = $("phone");

function formatDay(iso) {
  return new Date(iso + "T00:00:00").toLocaleDateString("en-IN", { weekday: "short", day: "numeric" });
}

function formatTime(time) {
  const [h, m] = time.split(":").map(Number);
  const suffix = h >= 12 ? "PM" : "AM";
  return `${h % 12 || 12}:${String(m).padStart(2, "0")} ${suffix}`;
}

function formatPhone(phone) {
  return phone.length === 10 ? `${phone.slice(0, 5)} ${phone.slice(5)}` : phone;
}

function initials(name) {
  return name.replace("Dr. ", "").split(" ").map((part) => part[0]).join("");
}

async function loadDoctors() {
  doctors = await fetch("/api/doctors").then((res) => res.json());
  if (!selectedDay) selectedDay = Object.keys(doctors[0].slots)[0];
  renderDays();
  renderDoctors();
  renderStats();
}

async function loadAppointments(highlightId) {
  appointments = await fetch("/api/appointments").then((res) => res.json());
  renderAppointments(highlightId);
  renderStats();
}

function renderDays() {
  const days = Object.keys(doctors[0].slots);
  $("days").innerHTML = days
    .map((day) => `<button data-day="${day}" class="${day === selectedDay ? "active" : ""}">${formatDay(day)}</button>`)
    .join("");
}

function renderDoctors(highlightId) {
  $("doctors").innerHTML = doctors
    .map((doctor) => {
      const free = doctor.slots[selectedDay];
      const slots = doctor.times
        .map((time) => `<span class="slot ${free.includes(time) ? "" : "taken"}">${formatTime(time)}</span>`)
        .join("");
      return `
        <li class="doctor ${doctor.id === highlightId ? "flash" : ""}">
          <div class="initials">${initials(doctor.name)}</div>
          <div>
            <h3>${doctor.name}</h3>
            <p>${doctor.specialty}</p>
          </div>
          <span class="open-count">${free.length} open</span>
          <div class="slots">${slots}</div>
        </li>`;
    })
    .join("");
}

function renderAppointments(highlightId) {
  const active = appointments.filter((a) => a.status === "booked").length;
  $("apptCount").textContent = `${active} upcoming`;

  $("appointments").innerHTML = appointments
    .map(
      (a) => `
        <li class="appt ${a.status} ${a.id === highlightId ? "flash" : ""}">
          <div class="when">${formatDay(a.date)}<span>${formatTime(a.time)}</span></div>
          <div class="who">
            <strong>${a.patient}</strong>
            <span>${a.doctor} · ${a.specialty}</span>
          </div>
          <div class="meta">
            <span class="phone-no">${formatPhone(a.phone)}</span>
            <span class="pill">${a.status === "booked" ? "Booked" : "Cancelled"}</span>
          </div>
        </li>`
    )
    .join("");
}

function renderStats() {
  const open = doctors.reduce(
    (sum, doctor) => sum + Object.values(doctor.slots).reduce((n, slots) => n + slots.length, 0),
    0
  );
  $("statDoctors").textContent = doctors.length;
  $("statOpen").textContent = open;
  $("statBooked").textContent = appointments.filter((a) => a.status === "booked").length;
}

function addLine(role, text) {
  for (const box of [$("transcript"), $("phoneTranscript")]) {
    const line = document.createElement("div");
    line.className = `line ${role}`;
    line.innerHTML = `<b>${role === "agent" ? "Maya" : "Caller"}</b><p></p>`;
    line.querySelector("p").textContent = text;
    box.querySelector(".empty")?.remove();
    box.append(line);
    box.scrollTop = box.scrollHeight;
  }
}

function showCard(type, appt) {
  const card = $("card");
  card.className = `card ${type === "cancelled" ? "cancel" : ""}`;
  card.innerHTML = `
    <small>${type === "booked" ? "Appointment booked" : "Appointment cancelled"}</small>
    <strong>${appt.doctor}</strong>
    <span>${formatDay(appt.date)} · ${formatTime(appt.time)} · ${appt.id}</span>`;
  requestAnimationFrame(() => card.classList.add("show"));
  clearTimeout(cardTimeout);
  cardTimeout = setTimeout(() => card.classList.remove("show"), 6000);
}

async function onAppointmentChange(type, appt) {
  selectedDay = appt.date;
  await loadDoctors();
  renderDoctors(appt.doctor_id);
  await loadAppointments(appt.id);
  showCard(type, appt);
}

function listen() {
  const source = new EventSource("/api/events");
  source.onmessage = (message) => {
    const event = JSON.parse(message.data);
    if (event.type === "transcript") addLine(event.role, event.text);
    if (event.type === "booked" || event.type === "cancelled") onAppointmentChange(event.type, event.appointment);
    if (event.type === "call" && event.state === "ended" && socket) endCall();
  };
}

function getAudioCtx() {
  if (!audioCtx) audioCtx = new AudioContext({ sampleRate: 16000 });
  if (audioCtx.state === "suspended") audioCtx.resume();
  return audioCtx;
}

function playRing() {
  const ctx = getAudioCtx();
  const gain = ctx.createGain();
  gain.gain.value = 0;
  gain.connect(ctx.destination);

  const oscillators = [440, 480].map((freq) => {
    const osc = ctx.createOscillator();
    osc.frequency.value = freq;
    osc.connect(gain);
    osc.start();
    return osc;
  });

  const now = ctx.currentTime;
  for (let i = 0; i < 10; i++) {
    const start = now + i * 3;
    gain.gain.setValueAtTime(0.06, start);
    gain.gain.setValueAtTime(0, start + 1.6);
  }

  return () => {
    gain.gain.cancelScheduledValues(ctx.currentTime);
    gain.gain.setValueAtTime(0, ctx.currentTime);
    oscillators.forEach((osc) => osc.stop());
  };
}

function playHangup() {
  const ctx = getAudioCtx();
  [0, 0.25, 0.5].forEach((delay) => {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.frequency.value = 620 - delay * 300;
    gain.gain.value = 0.07;
    osc.connect(gain).connect(ctx.destination);
    osc.start(ctx.currentTime + delay);
    osc.stop(ctx.currentTime + delay + 0.16);
  });
}

function makeAnalyser(node) {
  const analyser = getAudioCtx().createAnalyser();
  analyser.fftSize = 64;
  analyser.smoothingTimeConstant = 0.75;
  node.connect(analyser);
  return analyser;
}

function playAudio(bytes) {
  const ctx = getAudioCtx();
  const pcm = new Int16Array(bytes);
  const buffer = ctx.createBuffer(1, pcm.length, 24000);
  const channel = buffer.getChannelData(0);
  pcm.forEach((sample, i) => (channel[i] = sample / 0x8000));

  const source = ctx.createBufferSource();
  source.buffer = buffer;
  source.connect(speaker);
  playHead = Math.max(playHead, ctx.currentTime + 0.05);
  source.start(playHead);
  playHead += buffer.duration;

  playing.push(source);
  source.onended = () => (playing = playing.filter((s) => s !== source));
}

function stopAudio() {
  playing.forEach((source) => source.stop());
  playing = [];
  playHead = 0;
}

function drawWave() {
  const canvas = $("wave");
  const ctx = canvas.getContext("2d");
  const bars = 28;
  const agent = new Uint8Array(32);
  const user = new Uint8Array(32);

  const frame = () => {
    if (!phone.classList.contains("open")) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    if (analysers.agent) analysers.agent.getByteFrequencyData(agent);
    if (analysers.user) analysers.user.getByteFrequencyData(user);

    const agentLoud = agent.reduce((a, b) => a + b, 0);
    const userLoud = user.reduce((a, b) => a + b, 0);
    const data = agentLoud >= userLoud ? agent : user;
    ctx.fillStyle = agentLoud >= userLoud ? "#9fd3b4" : "#f1efe8";

    const gap = canvas.width / bars;
    for (let i = 0; i < bars; i++) {
      const value = data[Math.abs(i - bars / 2) + 1] / 255;
      const height = Math.max(6, value * canvas.height);
      const x = i * gap + gap / 4;
      ctx.beginPath();
      ctx.roundRect(x, (canvas.height - height) / 2, gap / 2, height, 4);
      ctx.fill();
    }
    requestAnimationFrame(frame);
  };
  frame();
}

function setCallState(state, text) {
  phone.dataset.state = state;
  $("callStatus").textContent = text;
  $("agent").classList.toggle("busy", state !== "idle");
  $("agentText").textContent = state === "idle" ? "Maya is available" : "Maya is on a call";
  $("liveTag").classList.toggle("on", state === "connected");
  $("tryCall").disabled = state !== "idle";
}

function startTimer() {
  startedAt = Date.now();
  timer = setInterval(() => {
    const seconds = Math.floor((Date.now() - startedAt) / 1000);
    const mm = String(Math.floor(seconds / 60)).padStart(2, "0");
    const ss = String(seconds % 60).padStart(2, "0");
    $("callStatus").textContent = `${mm}:${ss}`;
  }, 1000);
}

async function startCall() {
  $("transcript").innerHTML = "";
  $("phoneTranscript").innerHTML = "";
  $("muteBtn").classList.remove("on");
  $("muteBtn").querySelector("span").textContent = "Mute";
  phone.classList.add("open");
  setCallState("ringing", "Calling…");
  stopRing = playRing();
  drawWave();

  try {
    const ctx = getAudioCtx();
    const [stream] = await Promise.all([
      navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } }),
      ctx.audioWorklet.addModule("mic-worklet.js"),
      new Promise((resolve) => setTimeout(resolve, 1800)),
    ]);
    if (phone.dataset.state !== "ringing") {
      stream.getTracks().forEach((track) => track.stop());
      return;
    }
    micStream = stream;

    const mic = ctx.createMediaStreamSource(stream);
    micNode = new AudioWorkletNode(ctx, "mic-processor");
    mic.connect(micNode);
    micNode.connect(ctx.destination);
    analysers.user = makeAnalyser(mic);

    speaker = ctx.createGain();
    speaker.connect(ctx.destination);
    analysers.agent = makeAnalyser(speaker);

    const protocol = location.protocol === "https:" ? "wss" : "ws";
    socket = new WebSocket(`${protocol}://${location.host}/ws`);
    socket.binaryType = "arraybuffer";

    socket.onopen = () => {
      stopRing?.();
      stopRing = null;
      setCallState("connected", "00:00");
      startTimer();
      micNode.port.onmessage = (event) => {
        if (socket?.readyState === WebSocket.OPEN) socket.send(event.data);
      };
    };

    socket.onmessage = (event) => {
      if (typeof event.data === "string") {
        if (JSON.parse(event.data).type === "clear") stopAudio();
      } else {
        playAudio(event.data);
      }
    };

    socket.onclose = () => endCall();
  } catch (err) {
    console.error(err);
    endCall("Call failed");
  }
}

function endCall(reason = "Call ended") {
  if (phone.dataset.state === "ended" || phone.dataset.state === "idle") return;

  stopRing?.();
  stopRing = null;
  clearInterval(timer);
  socket?.close();
  socket = null;
  micNode?.disconnect();
  micNode = null;
  micStream?.getTracks().forEach((track) => track.stop());
  micStream = null;
  stopAudio();
  analysers.agent = null;
  analysers.user = null;

  playHangup();
  setCallState("ended", reason);

  setTimeout(() => {
    phone.classList.remove("open");
    $("card").classList.remove("show");
    setCallState("idle", "");
  }, 2200);
}

function toggleMute() {
  const track = micStream?.getAudioTracks()[0];
  if (!track) return;
  track.enabled = !track.enabled;
  $("muteBtn").classList.toggle("on", !track.enabled);
  $("muteBtn").querySelector("span").textContent = track.enabled ? "Mute" : "Unmute";
}

function tickClock() {
  $("clock").textContent = new Date().toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit", hour12: false });
}

$("days").addEventListener("click", (event) => {
  const day = event.target.dataset.day;
  if (!day) return;
  selectedDay = day;
  renderDays();
  renderDoctors();
});

$("tryCall").addEventListener("click", startCall);
$("endBtn").addEventListener("click", () => endCall());
$("muteBtn").addEventListener("click", toggleMute);

$("today").innerHTML = `<em>${new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" })}</em>`;
tickClock();
setInterval(tickClock, 10000);
setCallState("idle", "");
loadDoctors();
loadAppointments();
listen();
