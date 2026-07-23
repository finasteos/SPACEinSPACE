# Blender Autonomous Jobs

Genererar 3D-scener i Blender medans du sover.

## Köstruktur

```
blender-jobs/queue/
  ├── pending/    ← jobb som väntar på godkännande (.md med prompt)
  ├── approved/   ← godkända jobb — de ENDA `run` kör
  ├── active/     ← pågående jobb
  ├── done/       ← klara jobb (+ glTF + screenshot)
  └── failed/     ← misslyckade jobb
blender-jobs/exports/   ← glTF/GLB per klart jobb
```

## Kom igång

Ingen separat socket-addon behövs längre — workern startar den *persistenta*
Blender-ambassadören (B0) själv och kör varje jobb i en session
(scen → glTF-export → render).

```bash
# 1. Lägg till jobb (hamnar i pending/):
python3 blender-jobs/worker.py add "Create a low-poly castle with a dragon"
python3 blender-jobs/worker.py refill          # eller seeda från seed-ideas.md

# 2. Se kön:
python3 blender-jobs/worker.py list

# 3. GODKÄNN vad som får köras (human-in-the-loop):
python3 blender-jobs/worker.py approve castle  # eller: approve all

# 4. Kör godkända jobb:
python3 blender-jobs/worker.py run
```

Bara **godkända** jobb körs. Pending-jobb väntar tills en människa godkänner
dem — även den automatiska launchd-körningen (`run-next.sh`) kör enbart
`approved/`.

## Automatiskt var 30:e minut (macOS)

```bash
# Installera launchd-tjänsten:
cp blender-jobs/com.suparays.blender-worker.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.suparays.blender-worker.plist

# Kolla loggar:
tail -f ~/Library/Logs/blender-worker.log

# Stoppa:
launchctl unload ~/Library/LaunchAgents/com.suparays.blender-worker.plist
```

## Galleri

Färdiga scener hamnar i `blender-jobs/gallery.md` med screenshot + länk till
den exporterade glTF/GLB-filen i `blender-jobs/exports/` (redo för Commons /
Three.js / Godot).

## Seed-ideas

Redigera `blender-jobs/seed-ideas.md` för att påverka vad systemet skapar.
