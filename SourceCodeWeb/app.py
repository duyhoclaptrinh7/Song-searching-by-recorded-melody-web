from flask import Flask, render_template, jsonify
import numpy as np
import sounddevice as sd
from scipy.signal import butter, lfilter, medfilt
import math
import psycopg2

app = Flask(__name__)

# --- CẤU HÌNH CHUNG ---
SR = 44100           # Sample rate (Hz)
DURATION = 5         # Thời gian ghi âm (giây)
BUFFER_SIZE = 4096   # Kích thước khung xử lý (frame size, samples)
HOP_SIZE = 2048      # Bước nhảy giữa các khung (hop size, samples)
CLARITY_TH = 0.7     # Ngưỡng clarity (0–1) lọc frame không rõ pitch
ENERGY_TH_FRAC = 0.01  # Tỉ lệ ngưỡng năng lượng để loại noise
MIN_FRAMES = 3       # Số frame tối thiểu để coi là một note (≈140 ms)
MAX_MIDI = 64        # Lọc bỏ các nốt có MIDI > 57
MIN_MIDI = 47        # Lọc bỏ các nốt có MIDI < 47

# --- Kết nối cơ sở dữ liệu ---
conn = psycopg2.connect(
    dbname="SearchByMelody",
    user="app_user",
    password="userpassword",
    host="localhost",
    port="5432"
)
cursor = conn.cursor()

# --- Hàm hỗ trợ xử lý âm thanh ---
def bandpass(x, sr=SR, low=80, high=1200, order=4):
    nyq = sr / 2.0
    b, a = butter(order, [low / nyq, high / nyq], btype='band')
    return lfilter(b, a, x)

def nsdf(frame):
    N = len(frame)
    w = frame * np.hanning(N)
    acf = np.fft.irfft(np.abs(np.fft.rfft(w, n=2 * N)) ** 2)[:N]
    sum_sq = np.cumsum(w * w)
    denom = sum_sq[N - 1] + sum_sq[:N] - sum_sq
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
    if 1 <= idx < len(curve) - 1:
        y0, y1, y2 = curve[idx-1], curve[idx], curve[idx+1]
        d = (y0 - 2*y1 + y2)
        if d != 0:
            idx += (y0 - y2) / (2 * d)
    return sr / idx, clarity

# --- Route trang chủ ---
@app.route("/")
def index():
    return render_template("index.html")

# --- Route ghi âm và xử lý ---
@app.route("/process-audio", methods=["POST"])
def process_audio():
    try:
        # --- Ghi âm từ mic ---
        print("Đang ghi âm...")
        y = sd.rec(int(DURATION * SR), samplerate=SR, channels=1)
        sd.wait()
        print("Kết thúc ghi âm")
        y = y.flatten()

        # --- Band-pass filter ---
        y_bp = bandpass(y)

        # --- Chia frames và tính năng lượng ---
        frames = []
        energies = []
        for start in range(0, len(y_bp) - BUFFER_SIZE + 1, HOP_SIZE):
            frame = y_bp[start:start + BUFFER_SIZE]
            frames.append(frame)
            energies.append(np.sum(frame ** 2))
        max_energy = max(energies) if energies else 0
        global energy_th
        energy_th = ENERGY_TH_FRAC * max_energy

        # --- Lấy pitch mỗi frame ---
        midi_real = []
        for frame in frames:
            f0, cl = detect_pitch(frame)
            if not math.isnan(f0) and f0 > 0:
                midi_real.append(69 + 12 * math.log2(f0 / 440.0))
            else:
                midi_real.append(np.nan)

        # --- Smoothing với median filter ---
        midi_smooth = medfilt(np.array(midi_real), kernel_size=5)

        # --- Chuyển sang integer semitone ---
        midi_int = np.full(len(midi_smooth), -1, dtype=int)
        valid_mask = ~np.isnan(midi_smooth)
        midi_int[valid_mask] = np.round(midi_smooth[valid_mask]).astype(int)

        # --- Segment thành các nốt ---
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
        length = len(midi_int) - start
        if current >= 0 and length >= MIN_FRAMES:
            notes.append(current)

        # --- Lọc bỏ các nốt MIDI không hợp lệ ---
        notes = [n for n in notes if MIN_MIDI <= n <= MAX_MIDI]

        # --- Tính khoảng cách tone ---
        if len(notes) < 2:
            return jsonify({"success": True, "message": "Không tìm đủ nốt hợp lệ để tính khoảng cách.", "tone_intervals": []})

        intervals = np.diff(notes)
        tone_intervals = intervals / 2.0

        # --- Truy vấn cơ sở dữ liệu ---
        tone_intervals_str = ",".join(
            f"{int(x)}" if x.is_integer() else f"{x:.1f}" 
            for x in tone_intervals
        )
        query = f"""
            SELECT * FROM songs
            WHERE melody_signature_str LIKE '%,{tone_intervals_str},%' 
            OR melody_signature_str LIKE '{tone_intervals_str},%' 
            OR melody_signature_str LIKE '%,{tone_intervals_str}' 
            OR melody_signature_str = '{tone_intervals_str}'
        """
        cursor.execute(query)
        results = cursor.fetchall()

        # Xử lý kết quả từ cơ sở dữ liệu
        songs = [{"song_id": row[0], "title": row[1], "audio_url": row[3]} for row in results]

        # Trả kết quả về frontend
        return jsonify({"success": True, "tone_intervals": tone_intervals.tolist(), "songs": songs})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

if __name__ == "__main__":
    app.run(debug=True)