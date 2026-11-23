import json
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding='utf-8')
headings = ['## Storyline', '## Visible Text', '## Speakers and Transcript', '## Atomic Sports Actions']
positions = [text.find(h) for h in headings]
sections = {h: text.split(h, 1)[1].split('\n## ', 1)[0] for h in headings if h in text}
time_pattern = r'(\d{2}):(\d{2})\.(\d{3})'
interval_pattern = re.compile(r'^' + time_pattern + r'\s*[-–]\s*' + time_pattern, re.M)

def seconds(parts):
    return int(parts[0]) * 60 + int(parts[1]) + int(parts[2]) / 1000

def intervals(s):
    return [(seconds(m.groups()[:3]), seconds(m.groups()[3:])) for m in interval_pattern.finditer(s)]

story = intervals(sections.get(headings[0], ''))
cursor = 0
gaps = []
for start, end in sorted(story):
    if start > cursor + 0.001:
        gaps.append([round(cursor, 3), start])
    cursor = max(cursor, end)
if cursor < 8:
    gaps.append([round(cursor, 3), 8])
actions = sections.get(headings[3], '')
action_entries = []
markers = list(interval_pattern.finditer(actions))
for index, marker in enumerate(markers):
    block = actions[marker.start():markers[index + 1].start() if index + 1 < len(markers) else len(actions)]
    identity = re.search(r'^Action ID:\s*(A\d+)', block, re.M)
    if identity:
        action_entries.append({'id': identity.group(1), 'start': seconds(marker.groups()[:3]), 'end': seconds(marker.groups()[3:])})
ids = re.findall(r'^Action ID:\s*(A\d+)', actions, re.M)
labels = re.findall(r'^Technique:\s*(.+)', actions, re.M)
allowed = {'split step', 'chasse step', 'crossover step', 'lunge', 'recovery', 'scissor jump', 'lift', 'forehand lift', 'backhand lift', 'net shot', 'drive', 'clear', 'drop shot', 'smash', 'backhand serve', 'forehand high serve', 'movement', 'upward return', 'return', 'racket swing', 'hand feed', 'racket feed'}
all_intervals = intervals(text)
result = {
    'response': str(path),
    'four_sections_in_order': all(p >= 0 for p in positions) and positions == sorted(positions),
    'storyline_intervals': story,
    'storyline_gaps_seconds': gaps,
    'invalid_intervals': [[s, e] for s, e in all_intervals if not (0 <= s < e <= 8)],
    'action_count': len(ids),
    'duplicate_action_ids': sorted({i for i in ids if ids.count(i) > 1}),
    'action_ids_sequential': ids == ['A' + str(i + 1).zfill(2) for i in range(len(ids))],
    'actions_in_start_time_order': [e['start'] for e in action_entries] == sorted(e['start'] for e in action_entries),
    'technique_counts': {label: labels.count(label) for label in sorted(set(labels))},
    'unknown_techniques': sorted(set(labels) - allowed),
    'visual_evidence_fields': len(re.findall(r'^Visual evidence:', actions, re.M)),
    'observed_shot_ids': sorted(set(re.findall(r'^Shot:\s*(S\d+)', text, re.M))),
    'limitations': 'Structural checks only. Shot content, identity, terminology correctness, audio transcription, and event boundaries require independent review.',
}
path.with_name('review_checks.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=True, indent=2))
