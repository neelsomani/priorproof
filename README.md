## PriorProof: A Point-in-Time Measure of Technique Novelty for Formal Proofs

Mathematicians distinguish virtues of proofs — some explain, some are elegant, some are *novel* in technique — but these judgments have resisted operationalization, and novelty in particular has had no mechanical, time-relative definition. We give one for formal proofs. For a Lean theorem proved at time t, we mechanically extract the dependency footprint of its proof and score the surprisal of that footprint under a retrieval-conditioned, hierarchically-smoothed prior built only from the library predating t. Because both the footprint and the temporal corpus are read off Lean's elaborated proof terms and commit history, the measure needs no technique ontology, no annotation, and no language-model judgment of what a proof "does" — the central difficulty that blocks the same measurement for informal proofs is here dissolved by the formal setting, which we use deliberately as a controlled laboratory. We are explicit about scope. The measure captures the surprisal of a proof *as written*, and is meaningful under a directness assumption: the proof carries no gratuitous detours that re-derive already-available results. This assumption holds for curated corpora like Mathlib, whose proofs are written to be reasonably direct; we additionally provide a mechanical redundancy detector that flags the one inflation subcase that is decidable — a sub-derivation that re-proves a lemma already present in the pre-t library. We characterize what the measure does not capture: novelty residing in definitions rather than in the route to a target (Principia's proof of 1+1=2), and novelty of connection between library areas versus novelty of individual premises. Point-in-time scoring handles by construction the case where a result's later simplification would otherwise erase the surprise its original proof carried. We validate with mechanical internal tests (chronological dependency prediction, leakage and paraphrase-stability checks, redundancy detection, and ablations of retrieval and smoothing) and a small two-rater study scoped strictly to footprint nonstandardness rather than to originality. We position the measure against the philosophical literature on proof virtues (explanation, beauty), which it complements rather than replaces, and we describe the continuation — automatic proof-normalization to lift the directness assumption so arbitrary and machine-generated proofs can be scored, a connection-level prior, and carrying these distinctions to informal mathematics where extraction lacks ground truth — as the research program this formal instrument is the controlled study for.

## Methodology

**The object.** For a theorem declaration D proved at time t, novelty is the surprisal of D's proof's technique footprint under a prior representing what the formal library before t would have expected for a theorem of D's kind. One declaration in, one number out, scored at D's own date.

**Footprint, not tactics, not names.** Surface tactics (`simp`, `linarith`) are syntactic and miss technique; named premises break on proofs that introduce new objects the pre-t prior cannot predict, making every such proof spuriously maximal-surprise. So each proof-introduced object is recursively unfolded to the *established machinery* it rests on — premises whose reuse count in the time-t snapshot exceeds a threshold — and the proof is fingerprinted by that frontier, with surviving primitives inverse-frequency weighted. The reuse-count threshold is swept and reported as a diagnostic rather than as independent robustness evidence: in our extraction, the family-backoff is coarse enough that varying the threshold over the practical range leaves the footprint's family-bucket assignment unchanged across declarations, so the score is invariant to the threshold by construction rather than by accident. We log this explicitly via a bucket-identity diagnostic that records, per declaration, whether its family buckets shift across the threshold sweep; in the corpus we score, they do not. The methodologically honest read is that establishment-by-reuse-count is absorbed by the family abstraction once backoff fires, and any future finer-grained sensitivity claim would need a parameter that bites at the family level (e.g., the establishment threshold for families themselves), which we leave to future work. If the buckets are identical, the sweep is reported as inert rather than as evidence of robustness. A deterministic filter drops compiler plumbing (typeclass resolution, coercions, recursors, notation, routine `simp` boilerplate) before scoring; this filter is treated as a first-class object with its own sensitivity study.

**Premise-families.** Raw Lean constants are too granular. A rare raw name would look novel merely for being rare. Each dependency maps to the finest *family* with enough pre-t historical support, backing off raw declaration → namespace/module → library area. This normalizes without a hand-built ontology. A backoff-depth decorrelation check confirms the final score is not merely a proxy for how far the backoff had to climb.

**The prior.** A retrieval-conditioned empirical distribution over established premise-families: retrieve the nearest pre-t theorems to D by an embedding of D's *statement only* (never its proof) and weight the premise-families their proofs used. Sparse contexts back off hierarchically (retrieved-neighbor → namespace → module → global), which keeps the "conditioned on this kind of theorem" claim alive where exact neighbors are few. The few statistical parameters (time decay, context-kernel and smoothing weights, mixture weights) are fit by chronological log-likelihood: hide each proof, build the prior from declarations before its date, predict the premise-families it actually used.

**Leakage discipline.** The governing requirement is that the prior reflect only knowledge available before t. Almost all of this is enforced by a single mechanical act: build the prior from the Mathlib snapshot checked out at the start of the time-bin containing D. That one slice automatically excludes D itself, every proof that depends on D (its descendants necessarily postdate it), the retrieval corpus, the candidate premise support, the reuse counts that drive the threshold and weights, and the neighbor set — all of them, because none of those declarations exist in a pre-t snapshot. There is no separate "exclude the target" rule to maintain; it is a consequence of the cutoff, and because every proof is scored only at its own date, no scenario arises in which the prior's cutoff is later than the proof.

The slice cannot reach two channels, and these are where the actual care goes. First, the **frozen base model's parametric memory**: any pretrained model used in the prior or encoder has seen future mathematics in its training text regardless of the corpus cutoff. This is not eliminated but measured, via a counterfactual-retrieval probe — swap the retrieved pre-t context for unrelated context, and if predictions do not change, the model is relying on parametric memory rather than the sliced corpus, and that case is flagged. The distribution of this sensitivity is reported overall and conditional on retrieval being non-empty, so empty-retrieval rows cannot dilute the headline. Second, the **statement encoder**: its contrastive training uses proof-derived positives, so an encoder trained on post-t proofs could absorb future dependency patterns into its similarity geometry. This is handled by training on the earliest slice and validating that its neighbor sets match per-bin encoders on a cross-bin sample, excluding bins whose encoder path is identical to the frozen reference, and falling back to per-bin training if stability fails. We use ≈3-month bins (~12–16 snapshots across Mathlib's Lean 4 history), each frozen at the bin's start.

The one residual that no mechanism closes is *diffuse* human-mediated influence: a proof whose technique was learned from D but which carries no formal dependency edge to D enters the prior looking like independent corroboration. The descendant-exclusion handled by slicing removes only logically-traceable influence, not this. Its effect is one-directional — diffuse self-influence makes a proof look slightly *less* novel than it was — so the metric is conservative about novelty, never inflationary, which we state as a characterized bias rather than an open hole.

**The directness assumption and its backstop.** The measure scores the footprint of the proof *as written*, and is meaningful under the assumption that the proof is reasonably direct — that it carries no eliminable detour re-deriving an already-available result the long way around. The canonical violation is an Euler/exponential re-derivation of cos²+sin²=1, whose surprising machinery is spent re-establishing a lemma the library already contains; scored naively, such a proof is over-credited. Two things make the assumption acceptable. First, it is *true of the evaluation data*: Mathlib proofs are written to be reasonably direct, so the violation does not arise in the corpus we score, rather than being an idealization. Second, the redundancy detector implements two paths against the pre-t library: a top-level path that flags whole proofs whose dependency reduces to a single prior theorem ("by exact prior_theorem" wrappers), and a nested path that flags sub-derivations whose conclusion matches a prior statement up to trivial equivalence. The nested path requires the extractor to emit proof subterms; the top-level path requires only the proof's direct dependency set. The detection logic is verified end-to-end on a constructed Euler-style re-derivation fixture in which both paths fire. On the live Mathlib corpus, our current proof-term backend emits only top-level dependencies, so only the top-level path activates in practice; the nested path is dormant pending extraction-side uplift rather than for detector reasons. We report this distinction explicitly when summarizing real-corpus redundancy counts, and treat the constructed-fixture pass as the validating evidence for the nested path until the extraction backend exposes subterms. We are explicit that this detector catches only *redundancy with the existing library*; baroqueness that re-derives a genuinely fresh intermediate the hard way is not detectable from the footprint and remains out of scope. Critically, the directness assumption removes only gratuitously-inflated proofs; it does not affect comparison among direct proofs (an elementary versus an analytic proof of the same theorem), which is where the metric does its real work.

**What it does not measure.** Footprint surprisal diverges from felt novelty in characterizable ways, each illustrated by a canonical case. *Definitional novelty:* the achievement in Principia's proof of 1+1=2 lives in the construction of number from logic, upstream of any proof term; the metric correctly scores the *proof* of that statement as un-novel and is openly blind to the foundational work, because that novelty resides in definitions, not in the route to the target. *Connection versus node:* the metric scores the surprisal of the premises a proof uses, not of the connections it draws between library areas; some novelty (the analytic proof of infinitude of primes deriving its force from a number-theory↔analysis bridge) is better described as connection-novelty, which we treat as future work rather than claim the node-level metric captures. *Elegance and explanation* are distinct proof virtues studied in the philosophy literature and are not targeted here. Point-in-time scoring handles a fourth case by construction: a result's later simplification does not retroactively lower the surprise its original proof carried, because each proof is scored only against the library predating it.

**Validation.** Mechanical, primarily: (1) chronological prediction — the prior assigns higher likelihood to actually-used premise-families than to random ones; (2) retrieval and smoothing ablations — removing each worsens prediction; (3) parametric-leakage probe — the counterfactual-retrieval test, with sensitivity reported overall and on the retrieval-nonempty subset; (4) paraphrase/proof-edit stability — equivalent minor proof changes do not move the score; (5) redundancy detection — `by exact prior_theorem` and library-re-derivation sub-proofs are flagged, not scored as novel; (6) backoff-depth decorrelation. Then one human check, scoped narrowly: two raters working in the chosen domain compare proof *pairs* on which proof uses the less standard mathematical route to its result — never "which is more original." Inter-rater agreement is both the construct check and the ceiling; the metric is reported against that ceiling, alongside a naive-LLM-judge baseline given the identical prompt.

**Domain.** One corpus-dense Mathlib area where reuse meaningfully tracks establishment and comparison classes are large enough for stable percentiles, chosen empirically by density.

## Roadmap

**Extraction and corpus.** Stand up Lean/Mathlib with ntp-toolkit and LeanDojo; reproduce premise extraction on a recent and an older commit. Build the quarterly snapshots, normalize extracted declarations into `data/declarations.jsonl`, and compute per-snapshot reuse counts.

**Gate checks.** Once extracted declarations exist, run the two empirical checks before scaling up. *Density:* confirm at least one Mathlib area has enough proofs per quarterly snapshot to populate retrieval-conditioned priors without backing off to global. *Redundancy-detector feasibility:* confirm the statement-equivalence check is mechanically implementable on real proof terms. If density fails, change domain; if the equivalence check is intractable, drop the detector to a weaker `by exact`-only form and narrow the claim.

**Metric.** Implement deterministic dependency filtering, recursive unfolding to the established-machinery frontier, inverse-frequency weighting, family backoff, and the surprisal score. First scores on hand-picked high/low examples act as smoke tests, including the Euler-re-derivation construction as a redundancy-detector unit test.

**Prior and encoder.** Mine proof-derived contrastive pairs, fine-tune a transformer statement encoder, build the multi-stage retriever over Lean statements, and fit the hierarchical-smoothed retrieval-conditioned prior by chronological log-likelihood. Resolve encoder time-slicing via the neighbor-stability check; run the parametric-leakage probe.

**Validation.** Run all six mechanical tests. Run the threshold sweep with the footprint-bucket diagnostic; only treat it as a sensitivity result when at least some declarations change family buckets across thresholds. Run the canonical-case suite as documented qualitative behavior. Recruit two domain raters; collect 50–100 pairwise comparisons on which proof uses the less standard mathematical route; report agreement, ceiling, metric-vs-consensus, and the naive-LLM baseline.

## Quickstart Guide

Install the package in editable mode before running commands:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Reinstall only when `pyproject.toml` dependencies or console entrypoints change. The install exposes the `priorproof-*` commands used below.

### Corpus And Extraction

Freeze Mathlib snapshots, run Lean over each snapshot, extract declaration records from elaborated theorem values, normalize the output into declaration JSONL, and build corpus artifacts.

Relevant files:

- `src/priorproof/extraction/snapshots.py`: snapshot manifest handling, Mathlib worktree orchestration, extractor-output normalization.
- `src/priorproof/extraction/proof_term.py`: Lean-backed proof-term extractor that reads theorem values and their used constants.
- `src/priorproof/extraction/source_scan.py`: source scanner retained only for plumbing smoke checks.
- `src/priorproof/cli/make_snapshot_manifest.py`: builds an extraction manifest from commit pins.
- `src/priorproof/cli/extract_declarations.py`: prepares worktrees, runs the selected extractor backend, normalizes raw output, and merges declarations.
- `src/priorproof/cli/proof_term_extract.py`: direct proof-term extractor command for one Mathlib checkout.
- `src/priorproof/data/models.py`: declaration, dependency, snapshot, footprint, and score records.
- `docs/extraction.md`: detailed extraction manifest, command-template, and adapter notes.
- `docs/data_schema.md`: normalized JSONL schema expected by the rest of the pipeline.
- `configs/snapshot_commits.example.json`: example commit manifest input.

Run:

```bash
priorproof-make-snapshot-manifest \
  --commits configs/snapshot_commits.example.json \
  --mathlib-repo external/mathlib4 \
  --out artifacts/extraction/manifest.json

# The proof-term extractor expects Lean/Lake from Mathlib's lean-toolchain on PATH.
# If `lake --version` fails, install elan before running extraction.

# Create a local mathlib repo if the checkout is not already present
mkdir -p external
test -d external/mathlib4 || git clone https://github.com/leanprover-community/mathlib4 external/mathlib4

priorproof-extract-declarations \
  --manifest artifacts/extraction/manifest.json \
  --mathlib-repo external/mathlib4 \
  --worktrees-dir artifacts/extraction/worktrees \
  --raw-dir artifacts/extraction/raw \
  --normalized-dir artifacts/extraction/normalized \
  --out-declarations data/declarations.jsonl \
  --out-snapshots artifacts/corpus/snapshots.json \
  --report artifacts/extraction/report.json \
  --backend proof-term \
  --adapter priorproof \
  --execute \
  --strict-raw
```

Test/check:

```bash
python3 -m pytest tests/test_extraction.py
```

### Gate Checks

After `data/declarations.jsonl` exists, decide whether the selected Mathlib area is dense enough. The Mathlib gate report also counts redundancy hits, but a zero count is interpretable only after the constructed redundancy fixture below passes: if the fixture passes and Mathlib still has zero hits, that is evidence that this corpus contains no library-redundancy of the form the detector can see.

Relevant files:

- `src/priorproof/cli/gate_checks.py`: CLI command.
- `src/priorproof/cli/check_redundancy_fixture.py`: focused redundancy-detector wiring check.
- `src/priorproof/corpus/snapshots.py`: density summaries and reuse counts.
- `src/priorproof/corpus/pipeline.py`: builds footprints used by the redundancy check.
- `src/priorproof/metric/redundancy.py`: statement-key and `by exact` redundancy detection.

Run:

```bash
priorproof-gate-checks \
  --declarations data/declarations.jsonl \
  --out artifacts/gate_checks.json

priorproof-check-redundancy-fixture \
  --declarations tests/fixtures/rederive_redundancy.jsonl \
  --out artifacts/checks/rederive_redundancy_report.json \
  --threshold 1 \
  --expect-hit
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
4. Write one footprint file per reuse threshold, then verify whether the thresholds actually change dependency family buckets. `footprints_t5.jsonl` means "stop unfolding when a dependency has at least 5 prior uses," but a proof-term extraction with no dependency subgraph can make all thresholds produce identical buckets.

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

For a domain-scoped study, first filter the broad extraction into a corpus plus a target list. The corpus keeps support declarations that may inform the prior; the target list says which declarations should be fit/scored/reported.

```bash
priorproof-apply-scope \
  --declarations data/declarations.jsonl \
  --scope configs/topology_scope.json \
  --out-declarations data/topology/declarations.jsonl \
  --out-targets data/topology/targets.json \
  --report artifacts/topology/scope_report.json

priorproof-build-corpus \
  --declarations data/topology/declarations.jsonl \
  --out-dir artifacts/topology/corpus \
  --thresholds 3,5,8,13
```

Test/check:

```bash
python3 -m pytest tests/test_metric_core.py
```

### Prior And Encoder

Estimate what dependencies would have been expected for a theorem before its proof existed, then score how surprising the actual footprint is under that expectation.

This step does five things:

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
- `src/priorproof/cli/build_contrastive_data.py`: contrastive data mining command with a pre-bin slice selector.
- `src/priorproof/cli/train_neural_encoder.py`: neural encoder fine-tuning command.
- `src/priorproof/cli/check_encoder_stability.py`: frozen-early versus per-bin neighbor-stability check.
- `src/priorproof/cli/fit_prior.py`: prior grid search by chronological likelihood.
- `src/priorproof/cli/score_novelty.py`: novelty scoring command.
- `docs/encoder.md`: learned encoder training and time-slicing details.

Run:

```bash
python3 -m pip install -e ".[ml]"

priorproof-build-contrastive-data \
  --declarations data/declarations.jsonl \
  --footprints artifacts/corpus/footprints_t5.jsonl \
  --snapshots artifacts/corpus/snapshots.json \
  --train-before-snapshot 2024Q1 \
  --out-examples artifacts/encoder/contrastive_examples_t5_2024Q1.jsonl \
  --out-report artifacts/encoder/contrastive_report_t5_2024Q1.json

priorproof-train-neural-encoder \
  --declarations data/declarations.jsonl \
  --examples artifacts/encoder/contrastive_examples_t5_2024Q1.jsonl \
  --base-model sentence-transformers/all-MiniLM-L6-v2 \
  --out-dir artifacts/encoder/neural_t5_2024Q1 \
  --epochs 1 \
  --batch-size 64

priorproof-build-contrastive-data \
  --declarations data/declarations.jsonl \
  --footprints artifacts/corpus/footprints_t5.jsonl \
  --snapshots artifacts/corpus/snapshots.json \
  --train-before-snapshot 2024Q2 \
  --out-examples artifacts/encoder/contrastive_examples_t5_2024Q2.jsonl \
  --out-report artifacts/encoder/contrastive_report_t5_2024Q2.json

priorproof-train-neural-encoder \
  --declarations data/declarations.jsonl \
  --examples artifacts/encoder/contrastive_examples_t5_2024Q2.jsonl \
  --base-model sentence-transformers/all-MiniLM-L6-v2 \
  --out-dir artifacts/encoder/neural_t5_2024Q2 \
  --epochs 1 \
  --batch-size 64

python3 - <<'PY'
import json
from pathlib import Path

Path("artifacts/encoder").mkdir(parents=True, exist_ok=True)
Path("artifacts/encoder/encoder_map_t5.json").write_text(json.dumps({
    "2024Q1": "artifacts/encoder/neural_t5_2024Q1",
    "2024Q2": "artifacts/encoder/neural_t5_2024Q2",
}, indent=2) + "\n")
PY

priorproof-fit-prior \
  --declarations data/declarations.jsonl \
  --footprints artifacts/corpus/footprints_t5.jsonl \
  --snapshots artifacts/corpus/snapshots.json \
  --encoder-map artifacts/encoder/encoder_map_t5.json \
  --out artifacts/prior_grid_t5.json

priorproof-score \
  --declarations data/declarations.jsonl \
  --footprints artifacts/corpus/footprints_t5.jsonl \
  --snapshots artifacts/corpus/snapshots.json \
  --encoder-map artifacts/encoder/encoder_map_t5.json \
  --prior-grid artifacts/prior_grid_t5.json \
  --out-scores artifacts/scores_t5.jsonl \
  --out-priors artifacts/priors_t5.jsonl
```

Omit `--target-declarations` for full-corpus runs. For scoped studies, use the scoped declarations/footprints/snapshots paths and add `--target-declarations data/topology/targets.json` so the support corpus contributes to retrieval and smoothing without becoming part of the reported target set.

The first snapshot in this example (`2023Q4`) has no earlier mathlib declarations in the manifest, so prior fitting and scoring skip it. The encoder map only needs entries for scoreable snapshots with a non-empty pre-time corpus.

The cheaper frozen-early shortcut is allowed only after it has a stability artifact. Train the earliest-slice encoder and the per-bin comparison encoders, then run:

```bash
priorproof-check-encoder-stability \
  --declarations data/declarations.jsonl \
  --footprints artifacts/corpus/footprints_t5.jsonl \
  --snapshots artifacts/corpus/snapshots.json \
  --reference-encoder artifacts/encoder/neural_t5_2024Q1 \
  --encoder-map artifacts/encoder/encoder_map_t5.json \
  --out artifacts/encoder/stability_t5.json
```

If `artifacts/encoder/stability_t5.json` reports `"passed": true`, `priorproof-fit-prior`, `priorproof-score`, `priorproof-ablate`, and `priorproof-counterfactual-priors` may use `--encoder artifacts/encoder/neural_t5_2024Q1 --allow-shared-encoder`. The stability check samples only cross-bin comparisons: snapshots whose mapped encoder path is identical to the frozen reference are excluded and counted in `excluded_self_comparison_snapshot_ids`. Without `--allow-shared-encoder`, scoring commands refuse to use one encoder across multiple snapshots.

Test/check:

```bash
python3 -m pytest tests/test_encoder_prior_validation.py
```

### Validation

Finally, we run mechanical validation summaries, ablations, counterfactual retrieval leakage checks, threshold sweeps, canonical-case assembly, rater packet generation, and LLM-baseline request generation. The validation report includes `threshold_sweep.footprint_bucket_diagnostic`, which logs one sample declaration's dependency-family buckets at each threshold and reports the corpus-wide rate of identical buckets.

Relevant files:

- `src/priorproof/evaluation/reports.py`: chronological prediction, ablations, leakage probe, threshold sweep, redundancy summary, rater agreement.
- `src/priorproof/cli/ablate.py`: retrieval/smoothing ablation artifact generation.
- `src/priorproof/cli/counterfactual_priors.py`: unrelated-context priors for leakage probes.
- `src/priorproof/cli/validate.py`: validation report aggregation.
- `src/priorproof/cli/make_canonical_cases.py`: hand-picked topology contrast cases with actual scores.
- `src/priorproof/cli/make_study_packet.py`: combined canonical plus stratified rater/LLM packet.
- `src/priorproof/cli/make_rater_ui.py`: static blinded rater UI.
- `src/priorproof/cli/generate_proof_narratives.py`: optional LLM pass that fills missing proof narratives from only the blinded packet.
- `src/priorproof/cli/run_llm_baseline.py`: LLM baseline request generation and optional execution.
- `src/priorproof/cli/evaluate_llm_baseline.py`: LLM baseline response scoring against the packet answer key.
- `tools/make_release.py`: build the small commit-ready blinded rater release from ignored artifacts.

Run:

```bash
priorproof-ablate \
  --declarations data/declarations.jsonl \
  --footprints artifacts/corpus/footprints_t5.jsonl \
  --snapshots artifacts/corpus/snapshots.json \
  --encoder-map artifacts/encoder/encoder_map_t5.json \
  --out-dir artifacts/ablations

priorproof-counterfactual-priors \
  --declarations data/declarations.jsonl \
  --footprints artifacts/corpus/footprints_t5.jsonl \
  --snapshots artifacts/corpus/snapshots.json \
  --encoder-map artifacts/encoder/encoder_map_t5.json \
  --out-scores artifacts/counterfactual_scores_t5.jsonl \
  --out-priors artifacts/counterfactual_priors_t5.jsonl

for threshold in 3 8 13; do
  priorproof-score \
    --declarations data/declarations.jsonl \
    --footprints artifacts/corpus/footprints_t${threshold}.jsonl \
    --snapshots artifacts/corpus/snapshots.json \
    --encoder-map artifacts/encoder/encoder_map_t5.json \
    --prior-grid artifacts/prior_grid_t5.json \
    --out-scores artifacts/scores_t${threshold}.jsonl \
    --out-priors artifacts/priors_t${threshold}.jsonl
done

priorproof-validate \
  --footprints artifacts/corpus/footprints_t3.jsonl artifacts/corpus/footprints_t5.jsonl artifacts/corpus/footprints_t8.jsonl artifacts/corpus/footprints_t13.jsonl \
  --priors artifacts/priors_t5.jsonl \
  --scores artifacts/scores_t3.jsonl artifacts/scores_t5.jsonl artifacts/scores_t8.jsonl artifacts/scores_t13.jsonl \
  --ablated-scores artifacts/ablations/global_only_scores.jsonl artifacts/ablations/no_module_scores.jsonl artifacts/ablations/no_namespace_scores.jsonl artifacts/ablations/no_retrieval_scores.jsonl \
  --counterfactual-priors artifacts/counterfactual_priors_t5.jsonl \
  --out artifacts/validation_report.json

priorproof-canonical-cases \
  --case-spec configs/topology_canonical_cases.json \
  --declarations data/topology/declarations.jsonl \
  --scores artifacts/topology/scores_t5.jsonl \
  --footprints artifacts/topology/corpus/footprints_t5.jsonl \
  --mathlib-repo external/mathlib4 \
  --out artifacts/topology/canonical_cases.json

priorproof-study-packet \
  --declarations data/topology/declarations.jsonl \
  --scores artifacts/topology/scores_t5.jsonl \
  --footprints artifacts/topology/corpus/footprints_t5.jsonl \
  --canonical-cases artifacts/topology/canonical_cases.json \
  --mathlib-repo external/mathlib4 \
  --stratified-count 64 \
  --canonical-repeats 3 \
  --out-dir artifacts/topology/study_packet

priorproof-generate-proof-narratives \
  --packet artifacts/topology/study_packet/study_packet.json \
  --out-packet artifacts/topology/study_packet/study_packet_with_narratives.json \
  --out-dir artifacts/topology/proof_narratives \
  --model gpt-5-mini \
  --execute

priorproof-rater-ui \
  --packet artifacts/topology/study_packet/study_packet_with_narratives.json \
  --out artifacts/topology/study_packet/rater_ui.html

python3 tools/make_release.py --force

priorproof-llm-baseline \
  --packet artifacts/topology/study_packet/study_packet_with_narratives.json \
  --out-dir artifacts/topology/llm_baseline \
  --model gpt-5 \
  --model gpt-5-mini

priorproof-evaluate-llm-baseline \
  --responses artifacts/topology/llm_baseline/responses.jsonl \
  --requests artifacts/topology/llm_baseline/requests.jsonl \
  --answer-key artifacts/topology/study_packet/answer_key.json \
  --out artifacts/topology/llm_baseline/report.json
```

For scoped validation runs, pass the same `--target-declarations` file to `priorproof-ablate`, `priorproof-counterfactual-priors`, and every `priorproof-score` invocation used to produce validation inputs.

`artifacts/` is intentionally ignored because it contains large generated corpora, model checkpoints, answer keys, metric scores, and private analysis files. Generate `release/study_packet/` when you need a small rater-facing folder that is safe to commit or send to raters. The release command reads the cleaned study packet, strips canonical/stratified labels and metric fields, writes `study_packet_blinded.json`, renders a matching `rater_ui.html`, and records file hashes in `MANIFEST.json`. Commit the generated `release/study_packet/` folder, not `artifacts/topology/study_packet/answer_key.json` or the full `artifacts/` tree.

The public study packet and rater UI intentionally exclude scores, prior probabilities, dependency buckets, and metric-derived explanations. Those fields are kept only in `answer_key.json` and canonical analysis artifacts so human and LLM judgments remain independent. The proof-narrative command reads only the blinded packet. Without `--execute`, it writes narrative requests only; it does not copy the packet forward or invent placeholder prose. `priorproof-rater-ui` and `priorproof-llm-baseline` hard-error unless every side already has a non-empty proof narrative. The LLM baseline command above writes `requests.jsonl` for two models and both prompt strictness levels. Add `--execute` only when `OPENAI_API_KEY` is set and the optional `openai` package is installed; otherwise the artifact is a dry-run request set over the exact blinded rater packet. Run the evaluator after `responses.jsonl` exists; it reports accuracy and invalid/missing-response rates overall, by model, by prompt strictness, and by canonical versus stratified source.

If narratives are generated outside the command, merge them with:

```bash
priorproof-generate-proof-narratives \
  --packet artifacts/topology/study_packet/study_packet.json \
  --responses artifacts/topology/proof_narratives/narrative_responses.jsonl \
  --out-packet artifacts/topology/study_packet/study_packet_with_narratives.json \
  --out-dir artifacts/topology/proof_narratives \
  --model gpt-5-mini
```

Test/check:

```bash
python3 -m pytest tests/test_encoder_prior_validation.py
```
