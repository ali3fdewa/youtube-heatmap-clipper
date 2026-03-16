/**
 * app.js — AI Viral YouTube Heatmap Clipper Frontend Logic
 *
 * Handles all API interactions, dynamic UI rendering,
 * heatmap chart, segment table, and job polling.
 */

// ==========================================================================
// State
// ==========================================================================
const state = {
  metadata: null,
  heatmap: [],
  segments: [],
  selectedSegments: new Set(),
  currentJobId: null,
  clips: [],
  settings: {
    aspectRatio: '9:16',
    cropMode: 'center',
    threshold: 0.40,
    speed: false, // Fast processing turbo mode
    tts: {
        enabled: false,
        voice: ''
    },
    subtitles: {
      enabled: true,
      model: 'base',
      language: '',
      preset: 'viral',
    },
    telegram: { botToken: '', chatId: '' },
  },
};

// ==========================================================================
// Toast Notifications
// ==========================================================================
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 3500);
}

// ==========================================================================
// Helpers
// ==========================================================================
function formatTime(seconds) {
  if (!seconds && seconds !== 0) return '--:--';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  return h > 0
    ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
    : `${m}:${String(s).padStart(2, '0')}`;
}

function parseTime(str) {
  const parts = str.split(':').map(Number);
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
  if (parts.length === 2) return parts[0] * 60 + parts[1];
  return Number(str) || 0;
}

async function apiCall(url, body = null) {
  const opts = body
    ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
    : { method: 'GET' };
  const resp = await fetch(url, opts);
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.error || 'API error');
  return data;
}

// ==========================================================================
// Scan Video
// ==========================================================================
async function scanVideo() {
  const urlInput = document.getElementById('youtube-url');
  const url = urlInput.value.trim();
  if (!url) { showToast('Please paste a YouTube URL', 'error'); return; }

  const scanBtn = document.getElementById('btn-scan');
  scanBtn.disabled = true;
  scanBtn.innerHTML = '<span class="animate-spin inline-block mr-2">⏳</span> Scanning…';

  try {
    const data = await apiCall('/api/scan', {
      url,
      threshold: state.settings.threshold,
      pre_pad: 3,
      post_pad: 5,
    });

    state.metadata = data.metadata;
    state.heatmap = data.heatmap || [];
    state.segments = data.segments || [];
    state.selectedSegments.clear();

    console.log(`[Heatmap] Got ${state.heatmap.length} points, ${state.segments.length} segments`);

    renderMetadata();
    renderHeatmap();
    renderSegments();

    // Show sections
    document.getElementById('section-metadata').classList.remove('hidden');
    document.getElementById('section-heatmap').classList.remove('hidden');
    document.getElementById('section-segments').classList.remove('hidden');

    showToast('Video scanned successfully!', 'success');
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    scanBtn.disabled = false;
    scanBtn.innerHTML = '🔍 Scan Video';
  }
}

// ==========================================================================
// Render Metadata
// ==========================================================================
function renderMetadata() {
  const m = state.metadata;
  if (!m) return;

  document.getElementById('meta-thumbnail').src = m.thumbnail || '';
  document.getElementById('meta-title').textContent = m.title || 'Untitled';
  document.getElementById('meta-channel').textContent = m.channel || 'Unknown';
  document.getElementById('meta-duration').textContent = formatTime(m.duration);
  document.getElementById('meta-video-id').textContent = m.video_id || '';
}

// ==========================================================================
// Render Heatmap Chart (Canvas)
// ==========================================================================
function renderHeatmap() {
  const canvas = document.getElementById('heatmap-canvas');
  if (!canvas) return;

  // Show a message if no heatmap data
  if (!state.heatmap.length) {
    const ctx = canvas.getContext('2d');
    const width = canvas.parentElement.clientWidth || 600;
    canvas.width = width;
    canvas.height = 48;
    ctx.fillStyle = 'rgba(15, 23, 42, 0.8)';
    ctx.fillRect(0, 0, width, 48);
    ctx.fillStyle = '#94a3b8';
    ctx.font = '13px Inter, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('No heatmap data available for this video (Most Replayed not enabled)', width / 2, 28);
    return;
  }

  const ctx = canvas.getContext('2d');
  const container = canvas.parentElement;
  const width = container.clientWidth || 600;
  const height = container.clientHeight || 48;
  canvas.width = width;
  canvas.height = height;

  ctx.clearRect(0, 0, width, height);

  const data = state.heatmap;
  const maxTime = data[data.length - 1]?.start || 1;

  // Background
  ctx.fillStyle = 'rgba(15, 23, 42, 0.8)';
  ctx.fillRect(0, 0, width, height);

  // Draw bars
  const barWidth = Math.max(2, width / data.length);
  data.forEach((point, i) => {
    const x = (point.start / maxTime) * width;
    const intensity = point.intensity || 0;
    const barHeight = intensity * (height - 4);

    // Color gradient based on intensity
    const hue = 260 - intensity * 200; // purple → red for hot
    const saturation = 60 + intensity * 40;
    const lightness = 40 + intensity * 25;
    ctx.fillStyle = `hsl(${hue}, ${saturation}%, ${lightness}%)`;

    ctx.fillRect(x, height - barHeight - 2, barWidth - 1, barHeight);
  });

  // Draw segment markers
  state.segments.forEach((seg) => {
    const x1 = (seg.start / maxTime) * width;
    const x2 = (seg.end / maxTime) * width;
    ctx.fillStyle = 'rgba(250, 204, 21, 0.2)';
    ctx.fillRect(x1, 0, x2 - x1, height);

    ctx.strokeStyle = '#facc15';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(x1, 0); ctx.lineTo(x1, height);
    ctx.stroke();
  });
}

// ==========================================================================
// Render Segments Table
// ==========================================================================
function renderSegments() {
  const tbody = document.getElementById('segments-tbody');
  if (!tbody) return;
  tbody.innerHTML = '';

  if (!state.segments.length) {
    tbody.innerHTML = `
      <tr><td colspan="6" class="text-center py-8 text-slate-500">
        No heatmap segments found. Try lowering the detection threshold.
      </td></tr>`;
    return;
  }

  state.segments.forEach((seg, i) => {
    const tr = document.createElement('tr');
    tr.className = 'border-b border-slate-700/30';
    tr.innerHTML = `
      <td class="p-3 text-center">
        <input type="checkbox" class="custom-checkbox" data-index="${i}"
               ${state.selectedSegments.has(i) ? 'checked' : ''}
               onchange="toggleSegment(${i}, this.checked)">
      </td>
      <td class="p-3 text-center font-mono text-sm">${formatTime(seg.start)}</td>
      <td class="p-3 text-center font-mono text-sm">${formatTime(seg.end)}</td>
      <td class="p-3 text-center">
        <span class="inline-block px-2 py-0.5 rounded-full text-xs font-semibold
          ${seg.score >= 0.8 ? 'bg-red-500/20 text-red-400' :
            seg.score >= 0.6 ? 'bg-amber-500/20 text-amber-400' :
            'bg-blue-500/20 text-blue-400'}">
          ${(seg.score * 100).toFixed(0)}%
        </span>
      </td>
      <td class="p-3 text-center">
        <span class="inline-block px-2 py-0.5 rounded-full text-xs font-semibold
          ${seg.viral_score >= 0.8 ? 'bg-fuchsia-500/20 text-fuchsia-400' :
            seg.viral_score >= 0.6 ? 'bg-purple-500/20 text-purple-400' :
            'bg-indigo-500/20 text-indigo-400'}">
          🔥 ${((seg.viral_score || seg.score) * 100).toFixed(0)}%
        </span>
      </td>
      <td class="p-3 text-center">
        <button onclick="previewSegment(${i})"
                class="text-xs px-3 py-1.5 rounded-lg bg-indigo-500/20 text-indigo-400
                       hover:bg-indigo-500/40 transition-all duration-200">
          ▶ Preview
        </button>
      </td>
    `;
    tbody.appendChild(tr);
  });

  updateSelectionCount();
}

function toggleSegment(index, checked) {
  if (checked) state.selectedSegments.add(index);
  else state.selectedSegments.delete(index);
  updateSelectionCount();
}

function toggleAllSegments(checked) {
  state.segments.forEach((_, i) => {
    if (checked) state.selectedSegments.add(i);
    else state.selectedSegments.delete(i);
  });
  renderSegments();
}

function updateSelectionCount() {
  const countEl = document.getElementById('selection-count');
  if (countEl) countEl.textContent = `${state.selectedSegments.size} selected`;
}

function previewSegment(index) {
  const seg = state.segments[index];
  if (!seg || !state.metadata) return;
  // Open YouTube at the timestamp
  const url = `https://www.youtube.com/watch?v=${state.metadata.video_id}&t=${Math.floor(seg.start)}`;
  window.open(url, '_blank');
}

// ==========================================================================
// Create Clips
// ==========================================================================
async function createClips() {
  if (!state.selectedSegments.size) {
    showToast('Select at least one segment', 'error');
    return;
  }
  if (!state.metadata) {
    showToast('Scan a video first', 'error');
    return;
  }

  const btn = document.getElementById('btn-create-clips');
  btn.disabled = true;
  btn.innerHTML = '<span class="animate-spin inline-block mr-2">⏳</span> Starting…';

  const segments = [...state.selectedSegments].map(i => state.segments[i]);

  try {
    const data = await apiCall('/api/clips', {
      url: state.metadata.url,
      video_id: state.metadata.video_id,
      segments,
      aspect_ratio: state.settings.aspectRatio,
      crop_mode: state.settings.cropMode,
      subtitles: state.settings.subtitles,
      tts: state.settings.tts,
      speed: state.settings.speed,
    });

    state.currentJobId = data.job_id;
    document.getElementById('section-output').classList.remove('hidden');
    pollJobStatus();
    showToast('Clip generation started!', 'info');
  } catch (err) {
    showToast(err.message, 'error');
    btn.disabled = false;
    btn.innerHTML = '🎬 Create Selected Clips';
  }
}

// ==========================================================================
// Manual Clip
// ==========================================================================
async function createManualClip() {
  const startInput = document.getElementById('manual-start').value;
  const endInput = document.getElementById('manual-end').value;
  const urlInput = document.getElementById('youtube-url').value.trim();

  if (!urlInput) { showToast('Paste a YouTube URL first', 'error'); return; }
  if (!startInput || !endInput) { showToast('Enter start and end time', 'error'); return; }

  const start = parseTime(startInput);
  const end = parseTime(endInput);
  if (end <= start) { showToast('End time must be after start time', 'error'); return; }

  try {
    const data = await apiCall('/api/manual-clip', {
      url: urlInput,
      start, end,
      aspect_ratio: state.settings.aspectRatio,
      crop_mode: state.settings.cropMode,
      subtitles: state.settings.subtitles,
      tts: state.settings.tts,
      speed: state.settings.speed,
    });

    state.currentJobId = data.job_id;
    document.getElementById('section-output').classList.remove('hidden');
    pollJobStatus();
    showToast('Manual clip generation started!', 'info');
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// ==========================================================================
// Batch Processing
// ==========================================================================
async function scanBatch() {
  const url = document.getElementById('batch-url').value.trim();
  if (!url) { showToast('Paste a playlist or channel URL', 'error'); return; }

  const btn = document.getElementById('btn-batch');
  btn.disabled = true;
  btn.innerHTML = '<span class="animate-spin inline-block mr-2">⏳</span> Scanning…';

  try {
    const data = await apiCall('/api/batch', { url });
    showToast(`Found ${data.count} videos in playlist`, 'success');

    const listEl = document.getElementById('batch-video-list');
    if (listEl) {
      listEl.innerHTML = data.videos.map((v, i) =>
        `<div class="flex items-center gap-3 py-2 border-b border-slate-700/30">
          <span class="text-slate-500 text-sm w-8">${i + 1}.</span>
          <span class="flex-1 text-sm text-slate-300 truncate">${v.title}</span>
          <span class="text-xs text-slate-500">${formatTime(v.duration)}</span>
        </div>`
      ).join('');
      listEl.classList.remove('hidden');
    }
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '📂 Scan Playlist';
  }
}

// ==========================================================================
// Job Polling
// ==========================================================================
let _shownErrors = new Set();

async function pollJobStatus() {
  if (!state.currentJobId) return;

  try {
    const data = await apiCall(`/api/status/${state.currentJobId}`);

    // Update progress
    const progressEl = document.getElementById('job-progress');
    const statusEl = document.getElementById('job-status');
    const progressBar = document.getElementById('progress-bar');

    if (progressEl) {
      const pct = data.total > 0 ? Math.round((data.progress / data.total) * 100) : 0;
      progressEl.textContent = `${data.progress}/${data.total} clips`;
      if (progressBar) progressBar.style.width = `${pct}%`;
    }
    if (statusEl) {
      const statusMap = {
        downloading: '⬇️ Downloading video…',
        processing: `🎞️ Generating clips… (${data.progress || 0}/${data.total || 0})`,
        completed: '✅ Completed!',
        error: '❌ Error',
      };
      statusEl.textContent = statusMap[data.status] || data.status;
    }

    // Render clips (progressively as they become available)
    if (data.clips && data.clips.length) {
      renderClips(data.clips);
    }

    // Show NEW errors only (avoid spamming on every poll)
    if (data.errors && data.errors.length) {
      data.errors.forEach(err => {
        if (!_shownErrors.has(err)) {
          _shownErrors.add(err);
          showToast(err, 'error');
        }
      });
    }

    // Continue polling if not done
    if (data.status === 'downloading' || data.status === 'processing') {
      setTimeout(pollJobStatus, 2000);
    } else {
      // Job finished (completed or error) — reset button
      const btn = document.getElementById('btn-create-clips');
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '🎬 Create Selected Clips';
      }
      if (data.status === 'completed') {
        const clipCount = data.clips ? data.clips.length : 0;
        const errCount = data.errors ? data.errors.length : 0;
        if (errCount > 0) {
          showToast(`${clipCount} clip(s) generated, ${errCount} failed`, 'warning');
        } else {
          showToast(`${clipCount} clip(s) generated successfully!`, 'success');
        }
      }
      // Reset error tracking for next job
      _shownErrors.clear();
    }
  } catch (err) {
    console.error('Poll error:', err);
    setTimeout(pollJobStatus, 3000);
  }
}

// ==========================================================================
// Render Clips Output
// ==========================================================================
function renderClips(clips) {
  state.clips = clips;
  const grid = document.getElementById('clips-grid');
  if (!grid) return;

  grid.innerHTML = clips.map(clip => `
    <div class="glass-light rounded-2xl p-4 anim-pop-in hover:-translate-y-1 hover:shadow-2xl hover:shadow-indigo-500/10 transition-all duration-300">
      <div class="relative group rounded-xl overflow-hidden mb-4 bg-slate-900 border border-slate-700/50">
        <video controls playsinline preload="metadata" class="w-full aspect-[9/16] object-contain">
          <source src="${clip.url}" type="video/mp4">
        </video>
        <!-- Overlay Badges -->
        <div class="absolute top-3 left-3 flex gap-2">
            <span class="px-2 py-1 rounded-lg bg-black/60 backdrop-blur-md text-[10px] font-bold text-white uppercase tracking-wider border border-white/10">
                ⭐ Viral
            </span>
        </div>
      </div>
      
      <div class="flex items-center gap-2 mb-4 px-1">
        <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
        <span class="text-xs text-slate-300 font-mono">${formatTime(clip.start)} → ${formatTime(clip.end)} (${clip.filename.split('_')[1] || 'clip'})</span>
      </div>
      
      <div class="grid grid-cols-2 gap-2">
        <a href="${clip.url}" download
           class="flex items-center justify-center gap-2 py-2.5 px-3 rounded-xl bg-gradient-to-br from-indigo-500/20 to-purple-500/20 
                  border border-indigo-500/30 text-indigo-300 hover:bg-indigo-500/30 hover:text-white hover:border-indigo-400 
                  transition-all text-sm font-semibold shadow-lg shadow-indigo-500/10 hover:shadow-indigo-500/20">
          <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
          Download
        </a>
        <button onclick="sendToTelegram('${clip.filename}')"
                class="flex items-center justify-center gap-2 py-2.5 px-3 rounded-xl bg-gradient-to-br from-sky-500/20 to-blue-500/20 
                       border border-sky-500/30 text-sky-300 hover:bg-sky-500/30 hover:text-white hover:border-sky-400 
                       transition-all text-sm font-semibold shadow-lg shadow-sky-500/10 hover:shadow-sky-500/20">
          <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"></path></svg>
          Telegram
        </button>
      </div>
    </div>
  `).join('');
}

// ==========================================================================
// Telegram Send
// ==========================================================================
async function sendToTelegram(filename) {
  const token = state.settings.telegram.botToken;
  const chatId = state.settings.telegram.chatId;

  if (!token || !chatId) {
    showToast('Configure Telegram settings first', 'error');
    // Open settings
    document.getElementById('settings-panel').classList.remove('hidden');
    return;
  }

  try {
    await apiCall('/api/telegram/send', {
      bot_token: token,
      chat_id: chatId,
      filename,
      caption: `🎬 ${state.metadata?.title || 'Clip'} | AI Heatmap Clipper`,
    });
    showToast('Clip sent to Telegram!', 'success');
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// ==========================================================================
// Threshold Control
// ==========================================================================
function updateThreshold(value) {
  const threshold = parseInt(value, 10) / 100;
  state.settings.threshold = threshold;
  const display = document.getElementById('threshold-value');
  if (display) display.textContent = threshold.toFixed(2);
}

async function rescanWithThreshold() {
  const url = document.getElementById('youtube-url').value.trim();
  if (!url) { showToast('Paste a YouTube URL first', 'error'); return; }
  showToast(`Re-scanning with threshold ${state.settings.threshold.toFixed(2)}…`, 'info');
  await scanVideo();
}

// ==========================================================================
// Settings
// ==========================================================================
function updateSetting(key, value) {
  const keys = key.split('.');
  let obj = state.settings;
  for (let i = 0; i < keys.length - 1; i++) obj = obj[keys[i]];
  obj[keys[keys.length - 1]] = value;
}

function toggleSettings() {
  document.getElementById('settings-panel').classList.toggle('hidden');
}

function updateFontSize(value) {
  const size = parseInt(value, 10);
  state.settings.subtitles.font_size = size;
  const display = document.getElementById('font-size-value');
  if (display) display.textContent = size;
}

// ==========================================================================
// System Check
// ==========================================================================
async function checkSystem() {
  try {
    const data = await apiCall('/api/system-check');
    const el = document.getElementById('system-status');
    if (!el) return;

    let html = '';
    for (const [name, info] of Object.entries(data)) {
      const icon = info.ok ? '✅' : '❌';
      html += `<span class="text-xs ${info.ok ? 'text-green-400' : 'text-red-400'}">${icon} ${name}</span>`;
    }
    el.innerHTML = html;
  } catch (err) {
    console.error('System check failed:', err);
  }
}

async function fetchVoices() {
  try {
    const data = await apiCall('/api/tts/voices');
    const select = document.getElementById('tts-voice-select');
    if (!select) return;
    
    select.innerHTML = data.voices.map(v => 
      `<option value="${v.id}">${v.name}</option>`
    ).join('');
    
    select.disabled = false;
    
    // Set default in state
    if (data.voices.length) {
       state.settings.tts.voice = data.voices[0].id;
    }
  } catch(e) {
    console.warn("Failed to load TTS voices", e);
  }
}

// ==========================================================================
// Init
// ==========================================================================
document.addEventListener('DOMContentLoaded', () => {
  checkSystem();
  fetchVoices();

  // URL paste handling
  const urlInput = document.getElementById('youtube-url');
  if (urlInput) {
    urlInput.addEventListener('paste', () => {
      setTimeout(() => {
        if (urlInput.value.trim()) scanVideo();
      }, 100);
    });

    urlInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') scanVideo();
    });
  }

  // Resize heatmap on window resize
  window.addEventListener('resize', () => {
    if (state.heatmap.length) renderHeatmap();
  });
});
