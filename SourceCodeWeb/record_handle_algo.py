import numpy as np
import sounddevice as sd
from scipy.signal import butter, lfilter, medfilt
import math

# --- CẤU HÌNH CHUNG ---
SR = 44100           # Sample rate (Hz)
DURATION = 5         # Thời gian ghi âm (giây)
BUFFER_SIZE = 4096   # Kích thước khung xử lý (frame size, samples)
HOP_SIZE = 2048      # Bước nhảy giữa các khung (hop size, samples)
CLARITY_TH = 0.7     # Ngưỡng clarity (0–1) lọc frame không rõ pitch
ENERGY_TH_FRAC = 0.01  # Tỉ lệ ngưỡng năng lượng để loại noise
MIN_FRAMES = 3       # Số frame tối thiểu để coi là một note (≈140 ms)
MAX_MIDI = 64        # Lọc bỏ các nốt có MIDI > 57
MIN_MIDI = 47

# --- 1) GHI ÂM TỪ MIC ---
print("Đang ghi âm...")
audio = sd.rec(int(DURATION * SR), samplerate=SR, channels=1)
sd.wait()
print("Kết thúc ghi âm")
y = audio.flatten()

# --- 2) BAND-PASS FILTER 80–1200 Hz ---
def bandpass(x, sr=SR, low=80, high=1200, order=4):
    nyq = sr / 2.0
    b, a = butter(order, [low/nyq, high/nyq], btype='band')
    return lfilter(b, a, x)

y_bp = bandpass(y)

# --- 3) CHIA FRAMES VÀ TÍNH NĂNG LƯỢNG ---
frames = []
energies = []
for start in range(0, len(y_bp) - BUFFER_SIZE + 1, HOP_SIZE):
    frame = y_bp[start:start + BUFFER_SIZE]
    frames.append(frame)
    energies.append(np.sum(frame ** 2))
max_energy = max(energies) if energies else 0
energy_th = ENERGY_TH_FRAC * max_energy

# --- 4) ĐỊNH NGHĨA HÀM NSDF VÀ PITCH DETECTION ---
def nsdf(frame):
    N = len(frame)
    w = frame * np.hanning(N)
    # Autocorrelation via FFT
    acf = np.fft.irfft(np.abs(np.fft.rfft(w, n=2*N))**2)[:N]
    # Normalized square difference
    sum_sq = np.cumsum(w*w)
    denom = sum_sq[N-1] + sum_sq[:N] - sum_sq
    denom[denom == 0] = np.finfo(float).eps
    return 2 * acf / denom

def detect_pitch(frame, sr=SR):
    if np.sum(frame**2) < energy_th:
        return np.nan, 0.0
    curve = nsdf(frame)
    min_lag = int(sr / 1200)
    max_lag = min(int(sr / 80), len(curve) - 1)
    idx = np.argmax(curve[min_lag:max_lag]) + min_lag
    clarity = curve[idx]
    if clarity < CLARITY_TH:
        return np.nan, clarity
    # Parabolic interpolation
    if 1 <= idx < len(curve) - 1:
        y0, y1, y2 = curve[idx-1], curve[idx], curve[idx+1]
        d = (y0 - 2*y1 + y2)
        if d != 0:
            idx = idx + (y0 - y2) / (2 * d)
    freq = sr / idx
    return freq, clarity

# --- 5) LẤY PITCH MỖI FRAME ---
midi_real = []
for frame in frames:
    f0, cl = detect_pitch(frame)
    if not math.isnan(f0) and f0 > 0:
        midi_real.append(69 + 12 * math.log2(f0 / 440.0))
    else:
        midi_real.append(np.nan)

# --- 6) SMOOTHING VỚI MEDIAN FILTER ---
midi_smooth = medfilt(np.array(midi_real), kernel_size=5)

# --- 7) CHUYỂN SANG INTEGER SEMITONE ---
midi_int = np.full(len(midi_smooth), -1, dtype=int)
valid_mask = ~np.isnan(midi_smooth)
midi_int[valid_mask] = np.round(midi_smooth[valid_mask]).astype(int)

# --- 8) SEGMENT THÀNH CÁC NỐT ---
notes = []
start = 0
current = midi_int[0]
for i in range(1, len(midi_int)):
    if midi_int[i] != current:
        length = i - start
        if current >= 0 and length >= MIN_FRAMES:
            notes.append(current)
        current = midi_int[i]
        start = i
# Cuối cùng
length = len(midi_int) - start
if current >= 0 and length >= MIN_FRAMES:
    notes.append(current)

notes = [n for n in notes if n <= MAX_MIDI and n >= MIN_MIDI]

# --- 9) TÍNH KHOẢNG CÁCH SEMITONE GIỮA CÁC NỐT ---
if len(notes) < 2:
    print("Không tìm đủ nốt hợp lệ để tính khoảng cách.")
else:
    intervals = np.diff(notes)
    print("Nốt (MIDI semitone):", notes)
    print("Khoảng cách semitone giữa các nốt:", intervals)
