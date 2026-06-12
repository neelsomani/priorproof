## PriorProof: A Point-in-Time Measure of Technique Novelty for Formal Proofs

Mathematicians distinguish virtues of proofs — some explain, some are elegant, some are *novel* in technique — but these judgments have resisted operationalization, and novelty in particular has had no mechanical, time-relative definition. We give one for formal proofs. For a Lean theorem proved at time t, we mechanically extract the dependency footprint of its proof and score the surprisal of that footprint under a retrieval-conditioned, hierarchically-smoothed prior built only from the library predating t. Because both the footprint and the temporal corpus are read off Lean's elaborated proof terms and commit history, the measure needs no technique ontology, no annotation, and no language-model judgment of what a proof "does" — the central difficulty that blocks the same measurement for informal proofs is here dissolved by the formal setting, which we use deliberately as a controlled laboratory. We are explicit about scope. The measure captures the surprisal of a proof *as written*, and is meaningful under a directness assumption: the proof carries no gratuitous detours that re-derive already-available results. This assumption holds for curated corpora like Mathlib, whose proofs are written to be reasonably direct; we additionally provide a mechanical redundancy detector that flags the one inflation subcase that is decidable — a sub-derivation that re-proves a lemma already present in the pre-t library. We characterize what the measure does not capture: novelty residing in definitions rather than in the route to a target (Principia's proof of 1+1=2), and novelty of connection between library areas versus novelty of individual premises. Point-in-time scoring handles by construction the case where a result's later simplification would otherwise erase the surprise its original proof carried. We validate with mechanical internal tests (chronological dependency prediction, leakage and paraphrase-stability checks, redundancy detection, and ablations of retrieval and smoothing) and a small two-rater study scoped strictly to footprint nonstandardness rather than to originality. We position the measure against the philosophical literature on proof virtues (explanation, beauty), which it complements rather than replaces, and we describe the continuation — automatic proof-normalization to lift the directness assumption so arbitrary and machine-generated proofs can be scored, a connection-level prior, and carrying these distinctions to informal mathematics where extraction lacks ground truth — as the research program this formal instrument is the controlled study for.

## Methodology

**The object.** For a theorem declaration D proved at time t, novelty is the surprisal of D's proof's technique footprint under a prior representing what the formal library before t would have expected for a theorem of D's kind. One declaration in, one number out, scored at D's own date.

**Footprint, not tactics, not names.** Surface tactics (`simp`, `linarith`) are syntactic and miss technique; named premises break on proofs that introduce new objects the pre-t prior cannot predict, making every such proof spuriously maximal-surprise. So each proof-introduced object is recursively unfolded to the *established machinery* it rests on — premises whose reuse count in the time-t snapshot exceeds a threshold — and the proof is fingerprinted by that frontier, with surviving primitives inverse-frequency weighted. The threshold is swept, never hand-set, and central results must hold across the sweep. A deterministic filter drops compiler plumbing (typeclass resolution, coercions, recursors, notation, routine `simp` boilerplate) before scoring; this filter is treated as a first-class object with its own sensitivity study.

**Premise-families.** Raw Lean constants are too granular. A rare raw name would look novel merely for being rare. Each dependency maps to the finest *family* with enough pre-t historical support, backing off raw declaration → namespace/module → library area. This normalizes without a hand-built ontology. A backoff-depth decorrelation check confirms the final score is not merely a proxy for how far the backoff had to climb.

**The prior.** A retrieval-conditioned empirical distribution over established premise-families: retrieve the nearest pre-t theorems to D by an embedding of D's *statement only* (never its proof) and weight the premise-families their proofs used. Sparse contexts back off hierarchically (retrieved-neighbor → namespace → module → global), which keeps the "conditioned on this kind of theorem" claim alive where exact neighbors are few. The few statistical parameters (time decay, context-kernel and smoothing weights, mixture weights) are fit by chronological log-likelihood: hide each proof, build the prior from declarations before its date, predict the premise-families it actually used.

**Leakage discipline.** The governing requirement is that the prior reflect only knowledge available before t. Almost all of this is enforced by a single mechanical act: build the prior from the Mathlib snapshot checked out at the start of the time-bin containing D. That one slice automatically excludes D itself, every proof that depends on D (its descendants necessarily postdate it), the retrieval corpus, the candidate premise support, the reuse counts that drive the threshold and weights, and the neighbor set — all of them, because none of those declarations exist in a pre-t snapshot. There is no separate "exclude the target" rule to maintain; it is a consequence of the cutoff, and because every proof is scored only at its own date, no scenario arises in which the prior's cutoff is later than the proof.

The slice cannot reach two channels, and these are where the actual care goes. First, the **frozen base model's parametric memory**: any pretrained model used in the prior or encoder has seen future mathematics in its training text regardless of the corpus cutoff. This is not eliminated but measured, via a counterfactual-retrieval probe — swap the retrieved pre-t context for unrelated context, and if predictions do not change, the model is relying on parametric memory rather than the sliced corpus, and that case is flagged. The distribution of this sensitivity is reported. Second, the **statement encoder**: its contrastive training uses proof-derived positives, so an encoder trained on post-t proofs could absorb future dependency patterns into its similarity geometry. This is handled by training on the earliest slice and validating that its neighbor sets match per-bin encoders on a sample, falling back to per-bin training if stability fails. We use ≈3-month bins (~12–16 snapshots across Mathlib's Lean 4 history), each frozen at the bin's start.

The one residual that no mechanism closes is *diffuse* human-mediated influence: a proof whose technique was learned from D but which carries no formal dependency edge to D enters the prior looking like independent corroboration. The descendant-exclusion handled by slicing removes only logically-traceable influence, not this. Its effect is one-directional — diffuse self-influence makes a proof look slightly *less* novel than it was — so the metric is conservative about novelty, never inflationary, which we state as a characterized bias rather than an open hole.

**The directness assumption and its backstop.** The measure scores the footprint of the proof *as written*, and is meaningful under the assumption that the proof is reasonably direct — that it carries no eliminable detour re-deriving an already-available result the long way around. The canonical violation is an Euler/exponential re-derivation of cos²+sin²=1, whose surprising machinery is spent re-establishing a lemma the library already contains; scored naively, such a proof is over-credited. Two things make the assumption acceptable. First, it is *true of the evaluation data*: Mathlib proofs are written to be reasonably direct, so the violation does not arise in the corpus we score, rather than being an idealization. Second, the one inflation subcase that is mechanically decidable — a sub-derivation whose conclusion matches a statement already present in the pre-t library, up to trivial equivalence — is caught by a **redundancy detector** that flags it and excludes its machinery from the novelty signal. We are explicit that this detector catches only *redundancy with the existing library*; baroqueness that re-derives a genuinely fresh intermediate the hard way is not detectable from the footprint and remains out of scope. Critically, the directness assumption removes only gratuitously-inflated proofs; it does not affect comparison among direct proofs (an elementary versus an analytic proof of the same theorem), which is where the metric does its real work.

**What it does not measure.** Footprint surprisal diverges from felt novelty in characterizable ways, each illustrated by a canonical case. *Definitional novelty:* the achievement in Principia's proof of 1+1=2 lives in the construction of number from logic, upstream of any proof term; the metric correctly scores the *proof* of that statement as un-novel and is openly blind to the foundational work, because that novelty resides in definitions, not in the route to the target. *Connection versus node:* the metric scores the surprisal of the premises a proof uses, not of the connections it draws between library areas; some novelty (the analytic proof of infinitude of primes deriving its force from a number-theory↔analysis bridge) is better described as connection-novelty, which we treat as future work rather than claim the node-level metric captures. *Elegance and explanation* are distinct proof virtues studied in the philosophy literature and are not targeted here. Point-in-time scoring handles a fourth case by construction: a result's later simplification does not retroactively lower the surprise its original proof carried, because each proof is scored only against the library predating it.

**Validation.** Mechanical, primarily: (1) chronological prediction — the prior assigns higher likelihood to actually-used premise-families than to random ones; (2) retrieval and smoothing ablations — removing each worsens prediction; (3) parametric-leakage probe — the counterfactual-retrieval test, with its sensitivity distribution reported; (4) paraphrase/proof-edit stability — equivalent minor proof changes do not move the score; (5) redundancy detection — `by exact prior_theorem` and library-re-derivation sub-proofs are flagged, not scored as novel; (6) backoff-depth decorrelation. Then one human check, scoped narrowly: two raters working in the chosen domain compare proof *pairs* on "which uses a more nonstandard dependency footprint relative to nearby formal proofs" — never "which is more original." Inter-rater agreement is both the construct check and the ceiling; the metric is reported against that ceiling, alongside a naive-LLM-judge baseline given the identical prompt.

**Domain.** One corpus-dense Mathlib area where reuse meaningfully tracks establishment and comparison classes are large enough for stable percentiles, chosen empirically by density.

## Roadmap

**Extraction and corpus.** Stand up Lean/Mathlib with ntp-toolkit and LeanDojo; reproduce premise extraction on a recent and an older commit. Build the quarterly snapshots, normalize extracted declarations into `data/declarations.jsonl`, and compute per-snapshot reuse counts.

**Gate checks.** Once extracted declarations exist, run the two empirical checks before scaling up. *Density:* confirm at least one Mathlib area has enough proofs per quarterly snapshot to populate retrieval-conditioned priors without backing off to global. *Redundancy-detector feasibility:* confirm the statement-equivalence check is mechanically implementable on real proof terms. If density fails, change domain; if the equivalence check is intractable, drop the detector to a weaker `by exact`-only form and narrow the claim.

**Metric.** Implement deterministic dependency filtering, recursive unfolding to the established-machinery frontier, inverse-frequency weighting, family backoff, and the surprisal score. First scores on hand-picked high/low examples act as smoke tests, including the Euler-re-derivation construction as a redundancy-detector unit test.

**Prior and encoder.** Mine proof-derived contrastive pairs, fine-tune a transformer statement encoder, build the multi-stage retriever over Lean statements, and fit the hierarchical-smoothed retrieval-conditioned prior by chronological log-likelihood. Resolve encoder time-slicing via the neighbor-stability check; run the parametric-leakage probe.

**Validation.** Run all six mechanical tests. Run the threshold sweep and confirm results hold across it. Run the canonical-case suite as documented qualitative behavior. Recruit two domain raters; collect 50–100 pairwise comparisons on footprint-nonstandardness; report agreement, ceiling, metric-vs-consensus, and the naive-LLM baseline.

## Quickstart Guide

Install the package in editable mode before running commands:

```bash
python3 -m pip install -e ".[dev]"
```

Editable install means changes under `src/priorproof/` are picked up immediately. Reinstall only when `pyproject.toml` dependencies or console entrypoints change.

The install exposes the `priorproof-*` commands used below.

Before running gate checks, metric construction, scoring, or validation, you need a normalized declaration corpus:

```text
data/declarations.jsonl
```

Create it with the extraction commands in the Corpus And Extraction section. If you already have extractor output, `priorproof-extract-declarations` can normalize it; see `docs/extraction.md` and `docs/data_schema.md`.

### Corpus And Extraction

Freeze Mathlib snapshots, run a Lean/LeanDojo/ntp-toolkit extractor, normalize extractor output into declaration JSONL, and build corpus artifacts.

Relevant files:

- `src/priorproof/extraction/snapshots.py`: snapshot manifest handling, Mathlib worktree orchestration, extractor-output normalization.
- `src/priorproof/cli/make_snapshot_manifest.py`: builds an extraction manifest from commit pins.
- `src/priorproof/cli/extract_declarations.py`: prepares worktrees, runs the extractor command template, normalizes raw output, and merges declarations.
- `src/priorproof/data/models.py`: declaration, dependency, snapshot, footprint, and score records.
- `docs/extraction.md`: detailed extraction manifest, command-template, and adapter notes.
- `docs/data_schema.md`: normalized JSONL schema expected by the rest of the pipeline.
- `configs/snapshot_commits.example.json`: example commit manifest input.

Run:

```bash
priorproof-make-snapshot-manifest \
  --commits configs/snapshot_commits.example.json \
  --out artifacts/extraction/manifest.json

priorproof-extract-declarations \
  --manifest artifacts/extraction/manifest.json \
  --mathlib-repo /path/to/mathlib4 \
  --worktrees-dir artifacts/extraction/worktrees \
  --raw-dir artifacts/extraction/raw \
  --normalized-dir artifacts/extraction/normalized \
  --out-declarations data/declarations.jsonl \
  --out-snapshots artifacts/corpus/snapshots.json \
  --report artifacts/extraction/report.json \
  --adapter auto \
  --extractor-command "python3 /path/to/extractor.py --repo {worktree} --out {raw_path}" \
  --execute \
  --strict-raw
```

Test/check:

```bash
python3 -m pytest tests/test_extraction.py
```

### Gate Checks

After `data/declarations.jsonl` exists, decide whether the selected Mathlib area is dense enough and whether redundancy detection is viable on extracted subterms.

Relevant files:

- `src/priorproof/cli/gate_checks.py`: CLI command.
- `src/priorproof/corpus/snapshots.py`: density summaries and reuse counts.
- `src/priorproof/corpus/pipeline.py`: builds footprints used by the redundancy check.
- `src/priorproof/metric/redundancy.py`: statement-key and `by exact` redundancy detection.

Run:

```bash
priorproof-gate-checks \
  --declarations data/declarations.jsonl \
  --out artifacts/gate_checks.json
```

Test/check:

```bash
python3 -m pytest tests/test_metric_core.py
```

### Metric And Footprints

Turn a theorem's raw extracted proof dependencies into the object that gets scored for novelty: a small weighted set of technique dependencies called a footprint.

This step does four things:

1. Drop dependencies that are usually Lean implementation noise rather than proof technique. Examples include generated recursors, coercions, typeclass instances, notation helpers, and routine tactic boilerplate.
2. Replace proof-local helper objects with the older library machinery they depend on. If a proof introduces a fresh local lemma `h`, and `h` is proved using older lemmas `A` and `B`, the footprint should contain `A` and `B`, not the fresh name `h`. The recursion stops when a dependency is already established in the pre-time corpus, meaning its reuse count is at least the selected threshold.
3. Convert overly specific raw declaration names into supported family names when the exact declaration has too little history. For example, a raw dependency can back off from `decl:Mathlib.Foo.bar` to `namespace:Mathlib.Foo`, then `module:Mathlib.Foo.Basic`, then `area:Mathlib`, then `global`.
4. Write one footprint file per reuse threshold, because the threshold is a sensitivity parameter. `footprints_t5.jsonl` means "stop unfolding when a dependency has at least 5 prior uses."

Concrete shape:

```text
raw proof dependencies
  [fresh_helper_h, Eq.mp, instFoo, Mathlib.Analysis.SpecialLemma]

after filtering
  [fresh_helper_h, Mathlib.Analysis.SpecialLemma]

after unfolding fresh_helper_h
  [Mathlib.Topology.Compact.isClosed, Mathlib.MeasureTheory.integral_mono, Mathlib.Analysis.SpecialLemma]

after family backoff and weighting
  [
    {family: "namespace:Mathlib.Topology.Compact", weight: ...},
    {family: "module:Mathlib.MeasureTheory.Integral", weight: ...},
    {family: "area:Mathlib.Analysis", weight: ...}
  ]
```

Relevant files:

- `src/priorproof/cli/build_corpus.py`: corpus and footprint artifact CLI command.
- `src/priorproof/corpus/pipeline.py`: coordinates filtering, redundancy exclusion, and frontier construction.
- `src/priorproof/metric/filtering.py`: deterministic dependency filter and sensitivity variants.
- `src/priorproof/metric/frontier.py`: recursive established-frontier construction.
- `src/priorproof/metric/families.py`: declaration/namespace/module/area/global family backoff.
- `src/priorproof/metric/scoring.py`: footprint surprisal scoring primitive.

Run:

```bash
priorproof-build-corpus \
  --declarations data/declarations.jsonl \
  --out-dir artifacts/corpus \
  --thresholds 3,5,8,13
```

Test/check:

```bash
python3 -m pytest tests/test_metric_core.py
```

### Prior And Encoder

Estimate what dependencies would have been expected for a theorem before its proof existed, then score how surprising the actual footprint is under that expectation.

This step does four things:

1. Mine contrastive training examples from the pre-time corpus. Positives come from shared proof families, shared downstream users, major dependency links, and same-namespace symbol overlap. Hard negatives come from statements that look similar but have no dependency-family overlap or a different theorem shape.
2. Fine-tune a transformer statement encoder. It reads theorem statements, not proofs, and turns them into vectors so similar statements can be compared. This requires the optional ML dependencies and a modest GPU.
3. Retrieve pre-time neighbors. For a target theorem `D`, the retriever looks only inside the snapshot that predates `D` and finds the older theorem statements closest to `D`'s statement.
4. Build the prior distribution over dependency families. The prior is a probability distribution over families like `namespace:Mathlib.Topology.Compact` or `module:Mathlib.MeasureTheory.Integral`. It mixes evidence from retrieved neighbors, declarations in the same namespace, declarations in the same module, and the whole pre-time corpus. If retrieval is sparse, namespace/module/global smoothing keeps plausible families from getting zero probability.
5. Score novelty. The scorer takes the actual footprint from the metric step and sums `-log(probability)` for each footprint family, weighted by the dependency weights. A high score means the proof used families that the pre-time prior assigned low probability.

Concrete shape:

```text
target theorem statement
  "Every compact set in a Hausdorff space is closed"

retrieved pre-time neighbors, using statements only
  [old_compact_image theorem, old_closed_embedding theorem, old_t2_separation theorem]

prior over dependency families
  {
    "namespace:Mathlib.Topology.Compact": 0.31,
    "namespace:Mathlib.Topology.Separation": 0.22,
    "module:Mathlib.Topology.Basic": 0.11,
    "area:Mathlib.MeasureTheory": 0.01
  }

actual footprint from the proof
  [
    {family: "namespace:Mathlib.Topology.Compact", weight: 0.6},
    {family: "area:Mathlib.MeasureTheory", weight: 0.4}
  ]

novelty score
  low contribution from Topology.Compact, high contribution from MeasureTheory
```

Relevant files:

- `src/priorproof/modeling/contrastive.py`: proof-derived positive pair and hard-negative mining.
- `src/priorproof/modeling/neural_encoder.py`: optional transformer fine-tuning and neural statement encoder.
- `src/priorproof/modeling/retriever.py`: statement-neighbor retrieval.
- `src/priorproof/modeling/prior.py`: retrieval/namespace/module/global smoothed prior.
- `src/priorproof/corpus/pipeline.py`: `score_with_retrieval_prior` orchestration.
- `src/priorproof/cli/build_contrastive_data.py`: contrastive data mining command.
- `src/priorproof/cli/train_neural_encoder.py`: neural encoder fine-tuning command.
- `src/priorproof/cli/fit_prior.py`: prior grid search by chronological likelihood.
- `src/priorproof/cli/score_novelty.py`: novelty scoring command.
- `docs/encoder.md`: learned encoder training and time-slicing details.

Run:

```bash
python3 -m pip install -e ".[ml]"

priorproof-build-contrastive-data \
  --declarations data/declarations.jsonl \
  --footprints artifacts/corpus/footprints_t5.jsonl \
  --out-examples artifacts/encoder/contrastive_examples_t5.jsonl \
  --out-report artifacts/encoder/contrastive_report_t5.json

priorproof-train-neural-encoder \
  --declarations data/declarations.jsonl \
  --examples artifacts/encoder/contrastive_examples_t5.jsonl \
  --base-model sentence-transformers/all-MiniLM-L6-v2 \
  --out-dir artifacts/encoder/neural_t5 \
  --epochs 1 \
  --batch-size 64

priorproof-fit-prior \
  --declarations data/declarations.jsonl \
  --footprints artifacts/corpus/footprints_t5.jsonl \
  --snapshots artifacts/corpus/snapshots.json \
  --encoder artifacts/encoder/neural_t5 \
  --out artifacts/prior_grid_t5.json

priorproof-score \
  --declarations data/declarations.jsonl \
  --footprints artifacts/corpus/footprints_t5.jsonl \
  --snapshots artifacts/corpus/snapshots.json \
  --encoder artifacts/encoder/neural_t5 \
  --out-scores artifacts/scores_t5.jsonl \
  --out-priors artifacts/priors_t5.jsonl
```

Test/check:

```bash
python3 -m pytest tests/test_encoder_prior_validation.py
```

### Validation

Finally, we run mechanical validation summaries, ablations, counterfactual retrieval leakage checks, threshold sweeps, and rater packet generation.

Relevant files:

- `src/priorproof/evaluation/reports.py`: chronological prediction, ablations, leakage probe, threshold sweep, redundancy summary, rater agreement.
- `src/priorproof/cli/ablate.py`: retrieval/smoothing ablation artifact generation.
- `src/priorproof/cli/counterfactual_priors.py`: unrelated-context priors for leakage probes.
- `src/priorproof/cli/validate.py`: validation report aggregation.
- `src/priorproof/cli/make_rater_packet.py`: blinded pairwise rater packets.

Run:

```bash
priorproof-ablate \
  --declarations data/declarations.jsonl \
  --footprints artifacts/corpus/footprints_t5.jsonl \
  --snapshots artifacts/corpus/snapshots.json \
  --encoder artifacts/encoder.json \
  --out-dir artifacts/ablations

priorproof-counterfactual-priors \
  --declarations data/declarations.jsonl \
  --footprints artifacts/corpus/footprints_t5.jsonl \
  --snapshots artifacts/corpus/snapshots.json \
  --encoder artifacts/encoder.json \
  --out-scores artifacts/counterfactual_scores_t5.jsonl \
  --out-priors artifacts/counterfactual_priors_t5.jsonl

priorproof-validate \
  --footprints artifacts/corpus/footprints_t3.jsonl artifacts/corpus/footprints_t5.jsonl artifacts/corpus/footprints_t8.jsonl artifacts/corpus/footprints_t13.jsonl \
  --priors artifacts/priors_t5.jsonl \
  --scores artifacts/scores_t3.jsonl artifacts/scores_t5.jsonl artifacts/scores_t8.jsonl artifacts/scores_t13.jsonl \
  --counterfactual-priors artifacts/counterfactual_priors_t5.jsonl \
  --out artifacts/validation_report.json

priorproof-rater-packet \
  --declarations data/declarations.jsonl \
  --scores artifacts/scores_t5.jsonl \
  --out-dir artifacts/raters \
  --n 100
```

Test/check:

```bash
python3 -m pytest tests/test_encoder_prior_validation.py
```
