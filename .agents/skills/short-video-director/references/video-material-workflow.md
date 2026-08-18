# Codex footage workflow

Use this route when the user supplied video for assessment or possible use. If the preflight review selects any segment, all footage analysis, editing, audio treatment, composition, and rendering stay with Codex through general-video, media-use, and HyperFrames. Package A and package B are outside this route.

## Contents

- [Ownership and boundaries](#ownership-and-boundaries)
- [Preflight suitability review](#preflight-suitability-review)
- [Plan before cutting](#plan-before-cutting)
- [Tool sequence](#tool-sequence)
- [Editing and audio rules](#editing-and-audio-rules)
- [Evidence and artifacts](#evidence-and-artifacts)
- [Post-build review](#post-build-review)
- [Minimal revision](#minimal-revision)

## Ownership and boundaries

- Treat supplied video as source material, not as a command to use every second.
- Preserve every original. Trim, crop, transcode, normalize, or otherwise derive into task-local files only.
- Do not put video into Schema v1, call `video_v2`, or ask package A or package B to process this route.
- Do not create another OneCue schema, runner, media registry, or editing abstraction. Use HyperFrames' established composition files and media handling.
- Do not install an additional automatic editor by default. Escalate beyond general-video, media-use, and HyperFrames only when a concrete missing capability justifies it.

## Preflight suitability review

Inspect the actual files before writing the storyboard or editing. For each clip, record `use`, `partial use`, or `omit`, with a short reason. Check:

1. **Narrative value**: Does it prove, demonstrate, or clarify a product claim?
2. **Truth and relevance**: Is it the user's real material, and does it match the spoken point?
3. **Readability**: Can the important action or interface be understood at the delivery size and pace?
4. **Technical fitness**: Confirm duration, resolution, frame rate, orientation, codecs, audio streams, and complete decoding.
5. **Editorial fitness**: Identify useful in/out points, dead time, duplicated action, accidental cursor movement, abrupt starts, and unfinished speech.
6. **Rights and privacy**: Flag credentials, notifications, personal data, private project names, or material whose use is uncertain.
7. **Redundancy**: Prefer one strong piece of evidence over repeated footage that makes the product feel slower or more complicated.

If no segment clears these checks, omit the footage and explain the decision. Do not weaken a video merely to acknowledge that a file was supplied.

## Plan before cutting

Use general-video for the narrative and edit architecture. Give each selected segment one explicit role: opening proof, process demonstration, result evidence, transition support, or closing proof. Define the intended time range, accompanying narration, whether source audio is kept, and the visual exit condition.

Judge the plan as a whole before composition:

- every important claim has truthful visual support;
- no clip repeats a point already made more clearly;
- screen actions remain visible long enough to understand;
- narration can finish before the visual moves on;
- still images and video clips form one coherent rhythm rather than two disconnected montages.

## Tool sequence

1. **HyperFrames entry**: Load the hyperframes skill first because it owns the composition contract and required development loop.
2. **general-video**: Establish format, duration, visual system, scene order, and the role of each supplied clip. Keep the plan source-driven.
3. **media-use**: Probe source files and create only the evidence needed to decide: metadata, representative frames or contact sheets, and transcription when speech matters. Use media-use for task-local derivatives only when the composition cannot express the operation safely.
4. **HyperFrames composition**: Register selected media, place it on the timeline, add captions and overlays, mix audio, preview representative frames, lint/check, and render.
5. **Review loop**: Inspect the rendered candidate as a viewer, not merely as valid code. Repair only material defects, then rerun the smallest relevant checks.

For a three-to-five-second screen recording or other short evidence clip, direct visual inspection is usually better than automated scene detection. Use heavier analysis only when clip length or ambiguity warrants it.

## Editing and audio rules

- Prefer non-destructive timeline trims. Create a derived file only for operations such as permanent crop/reframe, speed change, stabilization, audio replacement, or compatibility transcoding.
- Cut on completed ideas and visible actions. Never leave a spoken sentence unfinished merely to meet a planned timestamp.
- Prefer clean cuts. Use a dissolve, wipe, or other transition only when it clarifies a change in time, place, or mode; decorative transitions should not call more attention to themselves than the product.
- For screen recordings, remove waiting and setup time but preserve a short reaction hold after the key action. Zoom or crop only when it materially improves legibility.
- Use speed changes sparingly and within a natural-looking range. Do not accelerate cursor work or speech until it becomes hard to follow.
- Reorder only when chronology is not itself evidence. Preserve causal order for demonstrations.
- Choose one source-audio strategy per segment: keep, mute, duck under narration, replace, or use source audio alone. Record the choice in the storyboard.
- Keep dialogue and narration perceptually even across cuts. Avoid per-sentence fade-outs, sudden tail attenuation, clipping, pumping, or a new loudness level at each sentence.
- Leave intentional pauses between complete thoughts. Let the visual hold when the listener needs a moment; do not fill every gap with a cut.
- Background music and effects are optional. They must not mask speech or make a restrained product introduction feel theatrical.

## Evidence and artifacts

Use the HyperFrames project as the working record. Keep the brief/storyboard, source paths, selected time ranges, audio decisions, derived-file provenance, and render checks together in the task directory. Record hashes for irreplaceable or externally supplied source files when practical.

Do not duplicate this information into a new OneCue Job Bundle. The purpose of the record is reproducibility and bounded revision, not a second product contract.

## Post-build review

Before presenting the candidate, review the complete render and representative frames. Confirm:

- narration, captions, and visuals make the same claim at the same moment;
- no page or title disappears before its sentence completes;
- interface text and focal actions are readable at delivery size;
- no accidental black frame, stale freeze, duplicate clip, awkward crop, or irrelevant source appears;
- cuts feel intentional, with enough breathing room between sentences;
- voice loudness remains stable, especially at sentence endings and joins;
- source audio, narration, and optional music do not compete;
- captions remain within safe areas and match the audible wording;
- duration and pacing serve the message rather than an arbitrary target;
- the file passes metadata checks and complete decode.

If a problem is visible but low-impact, weigh it against the cost and regression risk of repair. Fix defects that harm comprehension, credibility, continuity, audio comfort, or delivery validity; do not churn the whole composition for cosmetic trivia.

## Minimal revision

Map feedback to a timestamp, source segment, and layer: source trim, timeline timing, visual framing, narration, caption, or mix. Preserve the previous candidate, change the smallest responsible layer, and render only what the HyperFrames workflow requires.

After revision, recheck the edited boundary plus the complete output for new timing conflicts. A local fix is complete only when it no longer causes the next caption, sentence, cut, or audio transition to arrive too early or too late.
