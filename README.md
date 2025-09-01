# MelodySearch — melody-based music search

A web app that lets users search for songs by humming or playing a short melody into a microphone.

**Tech stack**: Frontend — HTML, CSS, JavaScript. Backend — Flask (Python). Database — PostgreSQL.

**Main features**

* Search by melody recorded from the microphone (singing, guitar, etc.).
* Matches based on melodic interval patterns (intervals between consecutive notes measured in whole-tone units — "cung"), so searches work across different keys and timbres.
* Example data in the database are synthetic samples created for demonstration.

**How it works (brief)**

1. Record a short melody from the mic in the browser.
2. Backend extracts pitch and converts it to a sequence of intervals between consecutive notes measured in whole-tone units.

   * Example: C D E F → semitone diffs `2, 2, 1` → cung `{1, 1, 0.5}`.
3. Backend queries the PostgreSQL database for songs whose stored interval patterns match the recorded pattern and returns candidates.

**Run**

* Install the required Python libraries, create a PostgreSQL database like the example data, then run:

```bash
python app.py
```

**Demo video**

https://github.com/user-attachments/assets/3ae51e3b-8890-4783-973c-7495ac413010

---





