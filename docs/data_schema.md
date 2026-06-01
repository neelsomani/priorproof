# Data Schema

PriorProof expects Lean extraction output as JSONL declaration records. The Lean-facing extractor can be replaced as long as it emits this schema.

`priorproof-extract-declarations` can also normalize flexible LeanDojo-like, ntp-toolkit-like, or generic raw extractor output into this schema.

## Declaration Record

Required fields:

- `name`: Fully-qualified Lean declaration name.
- `statement`: Pretty-printed or normalized theorem statement. The encoder uses only this field for retrieval.
- `proof_date`: ISO date for the declaration's commit date.
- `module`: Lean module path.
- `namespace`: Lean namespace.
- `commit`: Mathlib commit containing the declaration.
- `dependencies`: List of dependency records used by the elaborated proof term.

Optional fields:

- `dependency_edges`: Pairs `[parent, child]` used for recursive unfolding of proof-introduced objects.
- `subterms`: Extractor-provided sub-derivations for redundancy detection. Each item may include `id`, `conclusion`, `normalized_conclusion`, `dependencies`, and `exact`.
- `metadata`: Free-form extractor metadata.

## Dependency Record

- `name`: Fully-qualified constant name.
- `kind`: One of `const`, `typeclass`, `coercion`, `recursor`, `simpGenerated`, or extractor-specific tags.
- `module`: Module where the dependency lives.
- `namespace`: Namespace where the dependency lives.
- `digest`: Optional stable declaration hash.
- `source`: Optional source span or extractor provenance.

## Produced Artifacts

- `snapshots.json`: Quarterly point-in-time slices.
- `density.json`: Per-snapshot module and namespace density summaries.
- `footprints_t{threshold}.jsonl`: Established-frontier proof footprints.
- `encoder.json`: Fitted statement-only encoder.
- `priors_t{threshold}.jsonl`: Retrieval hits and family distributions per declaration.
- `scores_t{threshold}.jsonl`: Novelty scores per declaration.
- `validation_report.json`: Mechanical validation summaries.
