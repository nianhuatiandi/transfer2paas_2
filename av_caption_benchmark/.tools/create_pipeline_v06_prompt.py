from pathlib import Path

root = Path(__file__).resolve().parent.parent
v04 = (root / 'badminton_prompt_v0.4.txt').read_text(encoding='utf-8')
terms = v04.split('Footwork labels\n', 1)[1].split('Classification and segmentation checks\n', 1)[0]
common = '''Badminton annotation prompt v0.6 — staged pipeline

Goal: describe the complete supplied clip, readable text, audible speech, and atomic sports actions. Write descriptions in English and preserve original-language speech/text. Use evidence accuracy before completeness of labels or richness of prose. Missing evidence remains uncertain, not a guessed positive or negative event.

Pipeline contract:
1. Local preprocessing reads source duration/fps, detects candidate scene cuts and extracts actual timestamped frames at approximately 10 fps, including the first and last frame of every shot. Cut detections are segmentation aids, not semantic labels.
2. Analyse each shot independently using its frames. The visual-stage JSON task is supplied separately. Track shot-scoped person IDs and every person's changes. A new shot does not establish a new camera end or identity continuity.
3. Transcribe full-clip audio separately, without visual descriptions or sport-specific vocabulary that could bias recognition. The audio-stage task is supplied separately.
4. The program merges chronological observations, assigns action IDs after sorting by start time, checks shot bounds, actor references and labels, and renders these exact headings: Storyline; Visible Text; Speakers and Transcript; Atomic Sports Actions. Per-stage responses are JSON, not the final report.

Evidence rules for the visual stage:
- Frame timestamps are actual source-frame times. Their spacing bounds temporal certainty. Describe observed transitions; mark an onset/offset cropped if absent. Never invent intermediate poses or outgoing shuttle paths.
- Name a technique when its distinguishing evidence is visible; use fallback labels when it is not. Do not require an eventual landing or a perfectly captured contact frame if the visible sequence otherwise supports the stroke. Conversely, a raised racket or sound alone does not establish a stroke subtype.
- Footwork, racket movement and shuttle travel are independent observations. A lunge can overlap a lift. Record repeated attempts separately. Named recovery footwork is one event with recovery stated as its purpose, not a duplicate recovery event.
- Use the exact canonical English label below. The Chinese names are explanatory mappings. No target action count or required technique is prescribed. Example sequences and titles must not create events.
- Recognize forehand/backhand from the actor's visible striking mechanics, never from screen-left/right alone. Describe body travel and shuttle trajectory using distinct screen directions.
- Speech cannot be inferred from captions or mouth movement. Text must be readable; do not complete logos or captions from familiarity. Conversational racket gestures stay in storyline, not Atomic Sports Actions.
- Deception, attacking/defensive intent, spin, and opponent response require their own evidence. Describe an observed preparation change without guessing intent or success.

Canonical vocabulary (terminology informed by BWF Shuttle Time; annotation thresholds are task-specific):
Footwork labels
'''
text = common + terms + '''
Decision sequence:
- Stroke subtype supported -> use the most specific subtype once. Only rising return supported -> upward return. Stroke supported but subtype unknown -> return. Only racket motion supported -> racket swing.
- Foot sequence supported -> split step, chasse step, crossover step, lunge, scissor jump, or recovery as defined above. Foot sequence unavailable -> movement only if displacement is observed.
- The final report preserves visual evidence and uncertainties. Audio/person identity and sound/action correspondence remain unverified unless a separate alignment stage establishes them; do not silently assign them during merging.
'''
(root / 'badminton_prompt_v0.6.txt').write_text(text, encoding='utf-8')
(root / 'badminton_prompt.txt').write_text(text, encoding='utf-8')
print('Saved pipeline prompt v0.6')
