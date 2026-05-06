# NEXA — look-at-me + backend autostart — quickstart

## Co ta zmiana robi

Naprawia trzy konkretne rzeczy:

1. **Komenda „look at me" / „popatrz na mnie"** — przedtem próbowała odpalić
   nieistniejący skrypt `scripts/control_vision_look_at_me_runtime.py` jako
   subprocess i konkurowała z głównym `CameraService` o kamerę
   (`Device or resource busy`). Teraz cały tracking idzie w jednym procesie,
   dzieli kamerę z resztą NEXA, i startuje w czasie poniżej 100 ms.

2. **Komenda „stop looking at me" / „przestań na mnie patrzeć"** — przedtem
   nie zatrzymywała trackingu (bo tracking nigdy nie startował). Teraz woła
   `LookAtMeSession.stop()`, czeka na zakończenie wątku i centruje pan/tilt.

3. **Auto-start Hailo-Ollama** — przedtem trzeba było ręcznie odpalić serwer
   LLM przed startem NEXA. Teraz NEXA sama go startuje na boot, jeśli nie
   wykryje go już działającego.

Wake/komenda loop wraca do normalnego działania, ponieważ usunęliśmy
`subprocess.run(timeout=8.0)` w środku flow komendy oraz `vision.close()`
który zabijał `CameraService`.

---

## Instalacja

Wszystko poniżej wykonujesz **na Pi**, w katalogu głównym repo NEXA
(tam gdzie jest `main.py`).

### 1. Wgranie patcha

Skopiuj na Pi:
- `apply_nexa_patch.py`
- folder `patch_files/` (musi leżeć obok `apply_nexa_patch.py`)

A potem:

```bash
cd ~/nexa             # lub gdzie masz repo
python3 apply_nexa_patch.py
```

Patcher zrobi:
- Sanity check, że jesteś w repo root.
- Skopiuje nowe moduły (`modules/devices/vision/look_at_me/`,
  `modules/runtime/backend_autostart/`, `modules/runtime/builder/look_at_me_mixin.py`).
- Załata istniejące pliki (literalnym dopasowaniem stringów, nie regexem) —
  każdy plik dostaje `.bak` przed zmianą.
- Zaktualizuje `config/settings.json`:
  - włączy `llm.autostart`
  - **odblokuje pan/tilt motion gates**:
    - `hardware_enabled: true`
    - `motion_enabled: true`
    - `dry_run: false`
    - `allow_uncalibrated_motion: true` (opcjonalna ścieżka bez kalibracji)
  - doda sekcję `look_at_me` z parametrami **automatycznie dopasowanymi do
    Twoich `pan_tilt.safe_limits`** — skanowanie nigdy nie wyjdzie poza
    bezpieczny obszar.
- Sprawdzi że nowe moduły dają się zaimportować.

Patcher jest **idempotentny** — możesz go odpalić wielokrotnie i nie
podwoi zmian.

### 2. Weryfikacja zmian (opcjonalna, ale zalecana)

```bash
git diff config/settings.json
```

Sprawdź czy zmiany w pan_tilt to to czego oczekujesz. Jeśli coś się
nie zgadza:

```bash
# rollback całego configu:
mv config/settings.json.bak config/settings.json

# rollback konkretnego pliku Pythona (przykład):
mv modules/core/flows/action_flow/visual_shell_actions_mixin.py.bak \
   modules/core/flows/action_flow/visual_shell_actions_mixin.py
```

### 3. Testy bez sprzętu

```bash
# unit testy planera (pure logic, bez hardware)
python3 -m unittest tests.vision.unit.look_at_me.test_planners -v

# smoke test pełnego lifecycle z fake camera + fake pan/tilt
python3 -m unittest tests.vision.unit.look_at_me.test_session_smoke -v
```

Powinno przejść 12 testów w mniej niż 1 sekundzie. Jeśli któryś
nie przechodzi, **nie startuj NEXA** — daj znać co wyszło.

### 4. Uruchomienie NEXA

```bash
python3 main.py
```

W logu powinieneś zobaczyć:

```
LLM backend autostart: attempted=True, already_running=..., launched=..., ready=True, detail=...
Vision backend started.
Assistant booted.
```

Następnie powiedz:

> Nexa, look at me

albo:

> Nexa, popatrz na mnie

NEXA powinna w ciągu **~2 sekund** od końca wypowiedzi:
1. Zaakceptować komendę przez Vosk fast lane (LLM omijany).
2. Wystartować `LookAtMeSession` (in-process, własny wątek).
3. Powiedzieć: „Okay, I will look at you now. Where are you?" /
   „Dobrze, będę teraz na ciebie patrzeć. Gdzie jesteś?".
4. Zacząć ruszać pan/tiltem — najpierw skanowanie X (lewo↔prawo),
   potem na każdym poziomie tilt (3 poziomy: 0°, ~3.85°, ~7°).
5. Gdy znajdzie twarz — przejść w tryb tracking, podążać za twarzą
   z hold zone 2% (twarz nie musi być idealnie w centrum żeby NEXA
   przestała się ruszać).

Aby zatrzymać:

> Nexa, stop looking at me

albo:

> Nexa, przestań na mnie patrzeć

NEXA powie: „Okay, I stopped looking at you." / „Dobrze, przestałam
na ciebie patrzeć.", po czym pan/tilt wróci do center (0°, 0°).

---

## Co możesz tunować

Wszystkie parametry w `config/settings.json` w sekcji `look_at_me`:

```jsonc
{
  "look_at_me": {
    "enabled": true,
    "target_fps": 25.0,                 // ile FPS chodzi worker thread
    "scan_after_no_face_frames": 6,     // po ilu pustych klatkach zacząć skanować
    "scan_interval_seconds": 0.16,      // jak często przesuwać podczas skanu
    "return_to_center_on_stop": true,
    "max_runtime_seconds": 600.0,       // hard limit — gdyby stop nigdy nie przyszedł
    "tracking": {
      "pan_gain_degrees": 22.0,         // jak agresywnie ścigać po X
      "tilt_gain_degrees": 24.0,        // jak agresywnie ścigać po Y
      "hold_zone_x": 0.020,             // 2% — dead zone, żeby nie drgało
      "hold_zone_y": 0.025,
      "max_step_degrees": 1.4,          // max ruch na klatkę (i tak clamp przez safe_limits)
      "fast_offset_threshold": 0.045,   // przy większym offset → boost
      "fast_gain_boost": 1.35,
      "invert_tilt": false              // przerzuć na true jeśli góra↔dół jest odwrócone
    },
    "scan": {
      "pan_limit_degrees": 14.0,        // ←→ skan się mieści w ±14°
      "pan_step_degrees": 2.33,         // krok skanu
      "tilt_levels_degrees": [0.0, 3.85, 7.0]  // 3 poziomy góra
    }
  }
}
```

### Jeśli chcesz większy zasięg skanu

Zwiększ `pan_tilt.safe_limits.pan_max_degrees` / `pan_min_degrees`
oraz `tilt_max_degrees` w `config/settings.json`. Na przykład dla
pełnego zakresu pan-tilt z zestawu Waveshare dla Pi:

```json
"safe_limits": {
  "pan_min_degrees": -45.0,
  "pan_center_degrees": 0.0,
  "pan_max_degrees": 45.0,
  "tilt_min_degrees": -20.0,
  "tilt_center_degrees": 0.0,
  "tilt_max_degrees": 20.0
}
```

Po zmianie zaktualizuj też `look_at_me.scan` — patcher nie zmienia
tej sekcji jeśli już istnieje. Albo usuń całą sekcję `look_at_me`
i odpal patcher ponownie — wygeneruje świeże defaulty pasujące do
nowych safe_limits.

### Jeśli chcesz produkcyjną kalibrację (zalecane długoterminowo)

Zamiast `allow_uncalibrated_motion: true`, użyj prawdziwej kalibracji:

```bash
# 1. Wykalibruj fizyczne limity:
python3 scripts/waveshare_pan_tilt_safe_limit_calibrator.py

# 2. W config/settings.json zmień:
#    "allow_uncalibrated_motion": false
```

Plik kalibracji `var/data/pan_tilt_limit_calibration.json` zostanie
utworzony przez powyższy skrypt z prawdziwymi twardymi limitami
twojego konkretnego sprzętu.

---

## Co dalej dla pozostałych komend

Architektura fast-lane vs LLM którą masz teraz pokrywa:
- `look at me` / `popatrz na mnie` → fast lane
- `stop looking at me` / `przestań na mnie patrzeć` → fast lane
- `show desktop`, `show face`, `show eyes`, `show battery`, `show temperature`,
  `show date`, `show time` → fast lane (już działały)
- `what time is it`, `who are you` → fast lane (już działały)
- `set focus mode`, `start break`, `remember this`, `where is my X` → fast lane
- **wszystko inne** (np. „what is a black hole", „what do you think about X")
  → LLM przez Hailo-Ollama

Ta lista jest w `voice_engine.runtime_candidate_intent_allowlist`
w `config/settings.json` plus w `runtime_candidate_executor.py`
`_TRANSCRIPT_INTENT_OVERRIDES`. Żeby dodać nową fast-lane komendę,
edytujesz oba miejsca i dorzucasz handler w
`modules/core/flows/action_flow/`.

---

## Co zostało **świadomie** nietknięte

- `voice_input.engine: faster_whisper` — twoja konfiguracja Whisper
  zostaje, fast lane Vosk używa tego samego transcript pipeline.
- `wake_engine: openwakeword`, `wake_model_path: models/wake/nexa.onnx` —
  wakeword bez zmian.
- `pan_tilt.safe_limits` — nie ruszam, bo to są twoje fizyczne limity.
- Stara metoda `_run_voice_engine_v2_vision_look_at_me_control` w
  `interaction_mixin.py` zostaje w pliku jako martwy kod (już nikt
  jej nie woła). Możesz ją usunąć ręcznie kiedyś, ale nie była
  wymagana do naprawy bugu.
- Skrypty `scripts/run_vision_*.py` — działały zawsze niezależnie,
  zostawiamy do diagnostyki / regresji.

---

## Rollback

Każdy plik dotknięty patchem ma backup z sufiksem `.bak`. Żeby
cofnąć całość:

```bash
cd ~/nexa
find . -name "*.bak" -not -path "./var/backups/*" | while read bak; do
  orig="${bak%.bak}"
  echo "restore: $orig"
  cp "$bak" "$orig"
done

# oraz usuń nowe moduły:
rm -rf modules/devices/vision/look_at_me
rm -rf modules/runtime/backend_autostart
rm -f  modules/runtime/builder/look_at_me_mixin.py
rm -rf tests/vision/unit/look_at_me
```

---

## Architektura w jednym diagramie

```
┌──────────────────────────────────────────────────────────────────────┐
│  CoreAssistant (jeden proces)                                        │
│                                                                      │
│  ┌────────────────────────────┐                                      │
│  │ BackendAutostartService    │  start_llm_backend()                 │
│  │  (boot only, before warmup)│  → http://127.0.0.1:8000             │
│  └────────────────────────────┘     (Hailo-Ollama)                   │
│                                                                      │
│  ┌────────────────────────────┐                                      │
│  │ CameraService              │  continuous_capture_worker @ 10fps   │
│  │  (jeden właściciel kamery) │  latest_observation() →              │
│  └────────────┬───────────────┘  VisionObservation z faces           │
│               │                                                      │
│               ▼                                                      │
│  ┌────────────────────────────┐                                      │
│  │ LookAtMeSession (NOWE)     │  worker thread @ 25fps               │
│  │   start(language=...)      │   - jeśli twarz: TrackingPlanner     │
│  │   stop()                   │   - jeśli brak: ScanPlanner (X+Y)    │
│  │   status()                 │   - move_delta() na pan-tilcie       │
│  └────────────┬───────────────┘                                      │
│               │                                                      │
│               ▼                                                      │
│  ┌────────────────────────────┐                                      │
│  │ PanTiltService             │  WaveshareSerialPanTiltBackend       │
│  │  (waveshare_serial)        │  z safe_limits, max_step_degrees     │
│  └────────────────────────────┘                                      │
└──────────────────────────────────────────────────────────────────────┘
```

Zero subprocesów. Zero handoff'ów kamery. Jeden właściciel kamery,
jeden właściciel pan-tilta. Wszystko start/stop w czasie poniżej 100 ms.
