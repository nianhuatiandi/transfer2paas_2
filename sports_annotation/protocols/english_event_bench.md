# English audiovisual event benchmark protocol

## Run and read a clip

From the repository root, run `python -m sports_annotation bench input.mp4 --out runs/my_clip`. The command reads `QWEN_API_KEY` or prompts for it without saving it. For a sport with a local lexicon, add `--lexicon sports_annotation/lexicons/badminton_bwf_v01.json`. For independent word times, install Vosk and pass a language-appropriate local model using `--vosk-model PATH`. Generic clips need no sports terminology. Vision uses a muted 10 fps video and timestamped stills. Clips without an audio stream produce an empty audio track.

- **reference.json** contains English descriptions and scored intervals, with the original utterance alongside each English rendering. It is immediately usable as a machine-reviewed silver reference.
- **review.html** plays the source, events, phases and scored temporal overlaps. **events.txt** is the readable list. **annotations.json** includes withheld candidates. **review_queue.json** records unresolved spans and unmatched transcript candidates.
- **release_protocol.json** records the model, source hash, prompts, implementation hashes and window settings. Per-stage directories retain requests, raw replies and usage. An unchanged rerun reuses completed stages. Choose a new output directory for a different source or initial protocol.

## Event units

| Level or track | Unit | Inclusion rule |
| --- | --- | --- |
| Activity | Broader activity of a person | Stored on each visual event so instances can be interpreted in context. |
| Visual event | One observable operation, gesture, visible speaking bout or held state | Record actor, source-clock onset and end, brief sentence and concrete details. Concurrent actions may overlap. A completed and restarted execution may form another event. |
| Phase | An observable stage of a parent event | Give it a parent-specific ID and interval. Score phase overlaps separately. |
| Audio event | Audible speech clause, sound, music, or ambience | Speech retains original words, English rendering and time evidence. Sound descriptions specify audible characteristics. |

A person who stands or sits almost motionless and speaks has a **visible_speech** event when successive frames establish articulatory movement. A concurrent hand gesture may receive its own row. Posture is an attribute, with a separate check of body support. A cropped talking head can have clear visible speech and unclear posture. When the image cuts to a demonstration or an object, narration can continue on the audio track. Resuming visible speech can start another visual event. The metric can count locomotion or sport actions by selecting `kind=motion` and can evaluate communication separately.

## Annotation and verification

1. Establish conservative person IDs from source-time appearance samples. Use event-local actors for visible hands or bodies whose cross-shot identity cannot be established.
2. Propose visual events from muted 15-second windows with up to three seconds of context on either side. Transcribe and identify sounds independently from the audio. Review the visual table with the original sound.
3. Use scene changes to propose inspection intervals, splitting extended shots into shorter spans. Inspect faces on mute and then review all local operations, gestures, states and speaking bouts against the clip. Carry core-clock boundaries across shared context. Keep unresolved cross-window identities visible for adjudication.
4. Check event and phase claims against muted source frames. Observable movement, fine technical labels, details and posture can have different support. If elaboration fails, recheck the minimal core claim and replace its description only when the core can be observed. Recheck non-speech sounds by listening again.
5. Re-listen to original-language clause candidates and produce English renderings. Attach independent word times when a local acoustic match supports the phrase. Keep unlocatable quotes in the review queue.
6. On the common source clock, intersect every eligible visual interval with every eligible audio interval. An edge asserts co-occurrence. It carries no automatic speaker identity, causal or semantic claim. Half-open intervals that only touch produce no edge. The silver export scores intersections with at least 0.20 seconds of robust overlap. Small ambiguous handoffs between distinct adjacent clauses of the same voice retain boundary ranges; longer conflicts remain for review. Absence of an edge in a withheld or unreviewed interval provides no negative answer by itself.

## Adjudicated test references

To publish a human-reviewed test reference, a reviewer can accept, edit, drop or add events after viewing the source. Supply a decisions JSON with `reviewer`, `annotations_sha256`, an `events` object keyed by each original event ID and an optional `add` array of complete event rows. Existing rows take `{"decision":"accept"}`, `{"decision":"drop"}`, or `{"decision":"edit","changes":{...}}`. A phase has its own review flags. Approving a previously uncertain phase requires editing the parent's phases. To correct the scope of an action, a reviewer can drop it and add the revised instances. Run `python -m sports_annotation bench-adjudicate annotations.json decisions.json --out reviewed_reference.json`. The exporter validates the rows and recomputes relations from the revised intervals.

The internal checks and the sample pilot measure different things. Replay links, interval arithmetic, ID consistency and English fields can be checked exhaustively. A speaking-presence spot check does not establish a population accuracy estimate for detailed motion, transcription or timing.
