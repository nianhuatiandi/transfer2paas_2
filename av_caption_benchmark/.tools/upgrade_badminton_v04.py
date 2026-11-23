from pathlib import Path

root = Path(__file__).resolve().parent.parent
base = (root / 'badminton_prompt_v0.3.txt').read_text(encoding='utf-8')
prefix, remainder = base.split('Self-contained badminton vocabulary', 1)
_, template = remainder.split('Output Format\n', 1)
prefix = prefix.replace('Do not force lift, chassé steps, or any other label', 'Do not force lift, chasse step, or any other label')
prefix = prefix.replace('With the requested 10-fps input, normally round visual estimates', 'When only the requested 10-fps sampling is available, normally round visual estimates')
prefix = prefix.replace('Describe and annotate the supplied badminton video', 'Badminton video annotation prompt v0.4\n\nDescribe and annotate the supplied badminton video', 1)

vocabulary = '''Badminton terminology and decision rules v0.4
Canonical labels are the exact English labels below. Chinese names explain the terminology and may be used only in the Chinese term field, original visible text, or original speech. Spell chasse step consistently; chassé steps, chasse steps, shuffle, and 并步 are aliases, not additional output labels. Generic shuffling is not automatically chasse step.

The terminology follows BWF Shuttle Time. The evidence thresholds, fallback hierarchy, event boundaries, and output fields below are operational choices for this annotation task, not quotations from or a certification by BWF.
Reference: BWF Schools Badminton Teachers' Manual, second edition, February 2021: https://badmintonner.nl/pdf/4.-BWF-ST-Teachers-Manual_Inclusivity_ENGLISH.pdf
These definitions are self-contained; do not assume a referenced URL has been opened.

Footwork labels
- split step | 启动步／分腿垫步: A brief preparatory unweighting or small hop with feet reestablishing support before moving off. Require a visible loading/unweighting-to-support sequence; a pause, wide stance, or ordinary walking step is insufficient. A large jump or perfectly simultaneous landing is not required. Interval: visible preparation/unweighting through renewed support. Key moment: support re-established, if observed.
- chasse step | 并步: A lead foot moves in the travel direction and the trailing foot follows/closes the gap, without passing or crossing the lead foot. Require at least one discernible lead-and-follow cycle. The feet need not touch, and travel may be forward, backward, sideways, or diagonal. Group continuous same-direction cycles; report the count only if observable. Crossing feet supports crossover step instead; sideways body displacement with hidden feet supports movement. Interval: first step initiating the cycle through the final follow step or transition into another pattern. Key moments: none required.
- crossover step | 交叉步: During travel one foot visibly passes across the other foot's path in front or behind. Require a discernible crossing sequence rather than a single perspective-overlapped image. State direction and front/behind crossing only if visible. Interval: initiation of the crossing step through establishment of the next support. If crossing is unclear, use movement. Key moments: none required.
- lunge | 弓步／跨步上网: A reaching step with the lead knee flexing and bearing weight as the body or racket hand reaches toward the shuttle area. Require step-and-load evidence; a stationary squat or torso bend is insufficient. Do not require an ideal textbook posture. Interval: reaching step onset through loaded reach, ending when unloading/push-back begins. A stroke may overlap but gets its own supported event. Key moment: maximum loaded reach, only if visible.
- recovery | 回位: Movement or stance reestablishment after a preceding reach/stroke toward an observable ready position. Do not assume that position is the geometric centre of the court. If chasse step or another named pattern describes these same steps, record that pattern once and write purpose=recovery in Detail; do not duplicate its interval as recovery. Use recovery when the purpose is clear but the specific footwork is not. Interval: exit from the preceding action through the established ready stance or a new action. Key moment: ready stance re-established, if visible.
- scissor jump | 剪刀步起跳／剪刀跳: A rear-court jump with visible body rotation and an exchange of the legs' forward/backward positions. A generic hop is insufficient. Interval: takeoff through landing. Key moments: takeoff and initial landing, if observed. The accompanying stroke is a separate overlapping event.

Stroke labels
- lift | 挑球: A low/underarm stroke from the forecourt whose outgoing shuttle path supports an upward, deep return toward the opponent's rear court. Require the forecourt context and a stroke linked to a discriminative outgoing path; do not require the shuttle's eventual landing or exact contact frame to be visible. Both high defensive and flatter attacking lifts are possible. A raised racket alone or a short rising path without depth evidence is insufficient. Use lift when this family is supported but the forehand/backhand side is unclear. Interval: identifiable striking preparation through follow-through. Key moment: racket-shuttle contact, if localizable.
- forehand lift | 正手挑球: All lift evidence above, plus visible forehand-side striking mechanics relative to the racket arm/body. Do not derive forehand from screen right, the actor's assumed handedness, or the transcript alone. Use lift if the stroke side is unresolved. Same interval/key moment as lift.
- backhand lift | 反手挑球: All lift evidence above, plus visible backhand-side striking mechanics relative to the racket arm/body. Screen left alone does not establish backhand. Do not require a detailed grip view if the visible mechanics otherwise establish the side. Use lift if the side is unresolved. Same interval/key moment as lift.
- net shot | 网前球／放网: A forecourt stroke whose shuttle passes close over the tape and descends short toward the opponent's forecourt. Distinguish from lift by the outgoing trajectory, not just low contact or a gentle swing. Landing need not be visible if the near-net short path is established. Do not claim a spinning/tumbling net shot unless shuttle behaviour supports it.
- drive | 平抽球: A comparatively fast, flat return with an outgoing nearly level trajectory, typically through the midcourt. Require path evidence; swing speed, racket height, and a loud hit alone are insufficient.
- clear | 后场高远球: A stroke from the rear court sending the shuttle deep toward the opponent's rear court. Distinguish it from forecourt lift by the observed contact region and striking context; do not call every high return a clear.
- drop shot | 吊球: A rear-court stroke whose outgoing path descends toward the opponent's forecourt. Distinguish from net shot by the rear-court striking context. Neither a soft-looking swing nor a later low shuttle position alone establishes this label.
- smash | 杀球: A stroke from a high contact region with a visibly steep, fast downward outgoing path. A high racket, jump, or impact sound alone is insufficient. Describe an observed jump as an attribute; do not invent a separate jump-smash label.
- backhand serve | 反手发球: A backhand serving motion that visibly initiates play. Require start-of-play context; a low backhand stroke in a continuing exchange is not enough.
- forehand high serve | 正手发高远球: A forehand serving motion that initiates play with a high, deep outgoing trajectory. Require both serving context and the high/deep path; otherwise use an appropriate broader label.
For net shot, drive, clear, drop shot, smash, and serves, annotate identifiable striking preparation through follow-through. Their applicable key moment is racket-shuttle contact; mark it uncertain if it cannot be localized.

Fallback labels (valid annotations, not failures)
- movement | 移动（步法未定）: Body displacement is observable but the foot sequence is not identifiable. State visible travel direction and the missing cue. Do not guess footwork from the movement's destination.
- upward return | 向上回球（球种未定）: A stroke and an outgoing rising shuttle are supported, but forecourt origin or deep trajectory evidence is insufficient for lift. It is more specific than return, but not equivalent to lift.
- return | 回球（球种未定）: Evidence supports striking/redirecting the shuttle but not a more specific stroke label. Exact contact need not occur in a sampled frame: a tracked incoming/outgoing shuttle change linked to the racket motion can support a stroke. Sound alone cannot establish who struck it.
- racket swing | 挥拍（触球未确认）: Racket motion is visible but evidence of shuttle contact/redirection is insufficient. Do not claim an outgoing shot or invent a contact timestamp.

Classification and segmentation checks
- For each visible racket action, decide: identifiable stroke subtype -> canonical stroke label; otherwise supported rising return -> upward return; otherwise supported stroke -> return; otherwise visible swing -> racket swing. A hidden exact contact frame does not by itself force every stroke down to racket swing. Conversely, an instructional voice naming a stroke does not establish that stroke.
- For each visible foot sequence, test split step, chasse step, crossover step, lunge, scissor jump, or recovery against their own cues; otherwise use movement. Never force the example sequence split step -> chasse step -> lunge -> lift -> recovery onto the clip.
- Separate footwork and stroke intervals. A lunge plus a forehand lift can be two overlapping events, not a single lunge event and not one combined Technique label. For one stroke, choose only the most specific supported label: do not emit duplicate lift and forehand lift events.
- Keep movement direction and shuttle direction separate. State forehand/backhand and court location only to the extent supported by the view. If the shuttle disappears, describe the last supported trajectory; its landing point remains unobserved.
- Treat deception/假动作, a hidden preparation, and an attacking/defensive lift as attributes in Detail only when their visible mechanics/path support them. Describe the actual change in racket preparation or trajectory; do not infer intent, opponent deception, spin, or a successful tactical outcome from the video title or narration.
- Good decision example (not a fact about the supplied video): the lead foot moves screen right and the trailing foot closes without crossing -> chasse step, travel=screen right. If those same steps restore readiness, write purpose=recovery in that event.
- Good decision example: forecourt low forehand swing plus a sufficiently supported deep rising outgoing path -> forehand lift even if landing is off-screen; if only a rising return is supported -> upward return; if only the swing is supported -> racket swing.

'''

template = template.replace('Technique: <one exact vocabulary label>\n', 'Technique: <one exact canonical English label>\nChinese term: <the matching Chinese name from the vocabulary>\n')
template = template.replace('duplicated actions, unsupported speech', 'duplicated footwork/recovery or parent/subtype stroke events, misuse of movement/return when a more specific label is supported, unsupported speech')
revised = prefix + vocabulary + 'Output Format\n' + template

current = root / 'badminton_prompt.txt'
backup = root / 'badminton_prompt_v0.2.txt'
old = current.read_bytes()
if not backup.exists():
    backup.write_bytes(old)
snapshot = root / 'badminton_prompt_v0.4.txt'
snapshot.write_text(revised, encoding='utf-8')
current.write_bytes(snapshot.read_bytes())
print('Updated:', current)
print('Version:', snapshot)
print('Previous prompt backup:', backup)
assert current.read_bytes() == snapshot.read_bytes()
assert revised.count('## ') == 4
for term in ['chasse step | 并步', 'forehand lift | 正手挑球', 'backhand lift | 反手挑球', 'upward return | 向上回球', 'Chinese term:']:
    assert term in revised, term
print('Four-section format and terminology checks passed.')
