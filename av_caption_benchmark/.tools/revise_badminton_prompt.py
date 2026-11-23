from pathlib import Path

root = Path(__file__).resolve().parent.parent
original = (root / 'badminton_prompt.txt').read_text(encoding='utf-8-sig')
vocabulary = original.split('- split step —', 1)[1].split('Output Format:', 1)[0].strip()
vocabulary = '- split step —' + vocabulary

intro = '''Describe and annotate the supplied badminton video using only evidence in its frames and audio. Return exactly the four sections in the Output Format, in that order. Write descriptions in English; preserve visible text and spoken words in their original language. Do not use bold formatting.

Input metadata for this test (update these values for another clip):
- Clip duration: 00:08.000.
- Requested video sampling rate: 10 frames/second. This is a request setting, not a guarantee of the frames actually made available by the service.

Priority order: evidence accuracy; full-clip coverage; consistent people and event identities; useful detail. Include all observable events, but omit unsupported embellishment. Never fill an uncertain field with a plausible story.

Observation and coverage rules
- Inspect the beginning, middle, and final available frames and audio. Establish shot boundaries before assigning action intervals. Include every observed camera cut, including a short final shot. Do not carry a pose, person, or event across a cut without checking the new shot.
- Storyline must cover the full verified clip duration. A quiet interval still needs a brief description. If an interval is unavailable or cannot be assessed, explicitly mark that interval as unobserved; do not invent its content to achieve coverage. Other sections contain only the intervals where their text, speech, or actions occur.
- Assign shots S01, S02, etc. Within each shot, assign people stable IDs such as S01-P01 and S01-P02, anchored to clothing and location. Reuse an ID while tracking that person in the shot. At a cut, use new shot-scoped IDs unless identity continuity is demonstrable; describe any supported identity link without assuming it from similar clothing.
- Describe the setting, camera viewpoint, people, clothing, visible equipment, spatial relations, camera changes, and important sounds. Describe static background details once per shot, then describe changes. Include readable text in Visible Text; put non-text artwork in Storyline.
- Do not infer age, identity, intent, coaching role, feeding role, handedness, or speaking identity from context alone. Use neutral visible descriptions where evidence is insufficient. Do not turn a brief lack of movement into a claim that someone remains still for the entire shot.

Timing and modality rules
- Use elapsed clip time in MM:SS.mmm notation. Formatting with three decimals does not mean millisecond accuracy. Use only precision supported by the observations. With the requested 10-fps input, normally round visual estimates to 0.100 s and explicitly mark estimated boundaries. Do not claim frame-exact contact from a frame-sampling request alone.
- All intervals must satisfy 0 <= start < end <= verified duration. A known contact or other key moment must lie inside its event interval. Mark an unobserved boundary or moment uncertain; do not assign it a guessed point timestamp. If only a bracket is supported, report an estimated interval.
- Visual events and audio events have independent timing. Identify a sound as racket-shuttle contact, shoe squeak, or a footfall only when the source is supported; otherwise describe the audible sound without assigning its cause.
- Transcribe only audible words. Do not reconstruct speech from captions, actions, the video topic, or expected coaching phrases. Use [inaudible] for an unclear span, and do not complete words or sentences beyond the clip boundary. Split on speaker changes and clear pauses.
- Give each distinguishable voice an ID V01, V02, etc. Link a voice to a visible person only when audiovisual evidence supports it; otherwise mark the speaker as off-screen or unidentified for that interval. Audible instructions do not establish which action happened visually.
- Quote only readable text, using [illegible] for unreadable spans. Do not complete a logo, banner, or watermark from brand familiarity. Give each text element its own observed interval; do not extend it across a cut without verifying it remains visible.

Action annotation rules
- Use the exact vocabulary below. Describe observable mechanics first, then choose the most specific label whose required evidence is present. There is no target label distribution or target action count.
- Track each person's movement, racket swing, contact evidence, and outgoing shuttle separately. Inspect active racket sequences as well as footwork. Use racket swing when the swing is visible but contact is unconfirmed; use return when a stroke is supported but its subtype is not. Do not hide an observable swing or return inside a lunge entry merely because its exact subtype is uncertain.
- Give distinct footwork, strokes, and recovery their own intervals when supported; these intervals may overlap. A sound alone does not create a stroke event. A lunge alone does not establish a return. Assign each repetition its own action ID, and do not duplicate the same footwork under two labels. If named footwork serves recovery, record the footwork once and describe that purpose in Detail.
- For each formal label, state the relevant visible mechanics in Visual evidence. If a required cue is unavailable, use an appropriate fallback and identify the missing cue. Do not force lift, chassé steps, or any other label because it is expected in this type of video.
- Keep screen directions explicit. Treat player movement direction, racket direction, and shuttle direction as separate observations. Do not infer shuttle destination from racket movement. Use forehand/backhand or court zones only when visible evidence supports them.
- Order actions by start time and use A01, A02, etc. Cross-section references must use the same shot, person, voice, and action IDs. In Related actions, give one supported relationship per linked action: instruction, description, retrospective comment, or temporal overlap only. Co-occurrence alone establishes only temporal overlap; otherwise write none.

Self-contained badminton vocabulary
The definitions below are the annotation rules for this task. Citation names and page numbers document their origin; external documents are not additional evidence about this clip. Do not claim to have opened a linked manual.

'''

ending = '''
Output Format
Return only these four sections. Repeat the entry templates as needed; do not output placeholders.

## Storyline

<MM:SS.mmm> - <MM:SS.mmm>
Shot: <S01>
<A concise but specific paragraph integrating the observed visual changes and audio in this interval. Introduce people with shot-scoped IDs and distinguishing attributes. Mark a cut, estimated boundary, or unavailable interval explicitly.>

## Visible Text

<MM:SS.mmm> - <MM:SS.mmm>
Shot: <S01>
"<verbatim readable text, with [illegible] for unclear spans>": <position, appearance, and any timing uncertainty>

<If empty, write No visible text.>

## Speakers and Transcript

Speaker profiles:
<V01> - <audible voice characteristics; supported visual person link, or unidentified>

<MM:SS.mmm> - <MM:SS.mmm>
Speaker: <voice ID; visible person ID if supported, or off-screen/unidentified>
State: <audible delivery and emotion; use uncertain where needed>
Content: "<verbatim audible speech>"
Related actions: <action ID: relationship; repeat for each supported link, or none>

<If empty, write No intelligible speech.>

## Atomic Sports Actions

<MM:SS.mmm> - <MM:SS.mmm>
Action ID: <A01>
Shot: <S01>
Actor: <person ID>
Technique: <one exact vocabulary label>
Visual evidence: <specific visible cues supporting this label; identify missing cues for a fallback>
Detail: <this occurrence's body mechanics, equipment, screen directions, and any estimated or cropped boundaries>
Key moments: <supported anchor and timestamp or estimated interval; uncertain for an unsupported applicable anchor; none if not applicable>
Aligned sounds: <observed sound, its independent timestamp, and supported relation to this action; otherwise uncertain or none>

<If empty, write No discernible sports actions.>

Before returning, check the final answer for omitted shots or tail intervals, unjustified stillness claims, inconsistent actor/voice IDs, missing visible racket events, duplicated actions, unsupported speech or text completion, and out-of-range times. Correct inconsistencies using available evidence. If evidence is unavailable, preserve uncertainty instead of guessing. Return the annotations only, without a reasoning trace.
'''

target = root / 'badminton_prompt_v0.3.txt'
target.write_text(intro + vocabulary + '\n\n' + ending, encoding='utf-8')
print(target)
print('Original bytes:', len(original.encode('utf-8')))
print('Revised bytes:', target.stat().st_size)
assert target.read_text(encoding='utf-8').count('## ') == 4
assert (root / 'badminton_prompt.txt').read_text(encoding='utf-8-sig') == original
