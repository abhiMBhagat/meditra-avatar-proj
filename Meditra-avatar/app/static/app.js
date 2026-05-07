const form = document.getElementById("form");
const textEl = document.getElementById("text");
const statusEl = document.getElementById("status");
const errorEl = document.getElementById("error");
const btnEl = document.getElementById("btn");
const videoEl = document.getElementById("output");
const pauseLoopEl = document.getElementById("pauseLoop");
const playBtnEl = document.getElementById("playBtn");

function setBusy(isBusy) {
  btnEl.disabled = isBusy;
  textEl.disabled = isBusy;
  statusEl.textContent = isBusy ? "Generating… (this can take a bit)" : "";
}

function setError(msg) {
  errorEl.textContent = msg || "";
}

// Initialize pause loop
function initPauseLoop() {
  pauseLoopEl.src = "/static/visemes/pause.mp4";
  pauseLoopEl.load();
  pauseLoopEl.play().catch(e => {
    console.log("Pause loop autoplay failed:", e);
    console.log("Pause loop element:", pauseLoopEl);
    console.log("Pause loop src:", pauseLoopEl.src);
  });
}

// Handle video playback with overlay
function playGeneratedVideo(videoUrl) {
  videoEl.src = videoUrl + `?t=${Date.now()}`;
  videoEl.load();
  
  // Show play button
  playBtnEl.style.display = "inline-block";
  playBtnEl.onclick = () => {
    // Show generated video overlay
    videoEl.classList.remove("hidden");
    
    // Play generated video with audio
    videoEl.play().then(() => {
      // When generated video ends, hide overlay and resume pause loop
      videoEl.addEventListener("ended", () => {
        videoEl.classList.add("hidden");
        pauseLoopEl.play().catch(e => console.log("Pause loop resume failed:", e));
      }, { once: true });
    }).catch(e => console.log("Generated video play failed:", e));
  };
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  setError("");

  const text = (textEl.value || "").trim();
  if (!text) return;

  setBusy(true);
  try {
    const resp = await fetch("/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });

    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      throw new Error(data?.detail || `Request failed (${resp.status})`);
    }

    const videoUrl = data.video_url;

    // Use overlay playback system
    playGeneratedVideo(videoUrl);
    statusEl.textContent = "Done.";
  } catch (err) {
    setError(String(err?.message || err));
  } finally {
    setBusy(false);
  }
});

// Initialize pause loop when page loads
document.addEventListener("DOMContentLoaded", () => {
  initPauseLoop();
});

