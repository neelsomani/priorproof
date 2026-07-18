# Third-Party Software Licenses

PriorProof depends on the following third-party software components. This document records their licenses as verified from their respective repositories.

## Core Dependencies

### Lean 4
- **Purpose**: Formal proof verification and elaborated proof term extraction
- **Version**: v4.2.0-rc1 (2023Q4), v4.5.0-rc1 (2024Q1), v4.7.0-rc2 (2024Q2)
- **License**: Apache-2.0
- **Repository**: https://github.com/leanprover/lean4
- **License URL**: https://github.com/leanprover/lean4/blob/master/LICENSE

### Mathlib4
- **Purpose**: Mathematical library providing formal theorem corpus
- **Commits**:
  - 2023Q4: `aef04106feb057e57456331886e5f38e392dea9f`
  - 2024Q1: `2a17457d3236d97eec6687377c01a74fe2961ab7`
  - 2024Q2: `d8d7e696a4c05914b5f2dbff8768541fe1dd4b39`
- **License**: Apache-2.0
- **Repository**: https://github.com/leanprover-community/mathlib4
- **License URL**: https://github.com/leanprover-community/mathlib4/blob/master/LICENSE

## Python Dependencies

### sentence-transformers
- **Purpose**: Neural statement encoder for contrastive learning and retrieval
- **Version**: ≥3.0
- **License**: Apache-2.0
- **Repository**: https://github.com/UKPLab/sentence-transformers
- **License URL**: https://github.com/UKPLab/sentence-transformers/blob/master/LICENSE

### all-MiniLM-L6-v2 (Model Weights)
- **Purpose**: Pre-trained transformer model for statement encoding
- **Model**: sentence-transformers/all-MiniLM-L6-v2
- **License**: Apache-2.0
- **Model Card**: https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2

### PyTorch
- **Purpose**: Deep learning framework for encoder training
- **Version**: ≥2.2
- **License**: BSD 3-Clause
- **Repository**: https://github.com/pytorch/pytorch
- **License URL**: https://github.com/pytorch/pytorch/blob/main/LICENSE

### Hugging Face datasets
- **Purpose**: Data loading and processing utilities
- **Version**: ≥2.19
- **License**: Apache-2.0
- **Repository**: https://github.com/huggingface/datasets
- **License URL**: https://github.com/huggingface/datasets/blob/main/LICENSE

### Hugging Face accelerate
- **Purpose**: Distributed training utilities
- **Version**: ≥1.1
- **License**: Apache-2.0
- **Repository**: https://github.com/huggingface/accelerate
- **License URL**: https://github.com/huggingface/accelerate/blob/main/LICENSE

### OpenAI Python Client
- **Purpose**: LLM baseline and proof narrative generation
- **Version**: ≥1.0
- **License**: Apache-2.0
- **Repository**: https://github.com/openai/openai-python
- **License URL**: https://github.com/openai/openai-python/blob/main/LICENSE

### pytest
- **Purpose**: Testing framework
- **Version**: ≥8
- **License**: MIT
- **Repository**: https://github.com/pytest-dev/pytest
- **License URL**: https://github.com/pytest-dev/pytest/blob/main/LICENSE

## Optional Extraction Adapters

PriorProof supports (but does not require) normalization of extraction output from the following third-party tools:

### LeanDojo
- **Purpose**: Lean proof extraction (optional adapter support)
- **License**: MIT
- **Repository**: https://github.com/lean-dojo/LeanDojo
- **License URL**: https://github.com/lean-dojo/LeanDojo/blob/main/LICENSE
- **Note**: PriorProof provides a `--adapter leandojo` normalization mode but does not depend on LeanDojo as a runtime requirement. The reported study uses the built-in `proof-term` backend.

### NTP Toolkit
- **Purpose**: Neural theorem proving toolkit (optional adapter support)
- **License**: MIT (based on related ntptutorial repository)
- **Repository**: https://github.com/wellecks/ntptutorial
- **Note**: PriorProof provides a `--adapter ntp` normalization mode for ntp-toolkit-style output but does not depend on it as a runtime requirement. The reported study uses the built-in `proof-term` backend.

## License Summary

| Software | License | Commercial Use | Attribution Required |
|----------|---------|----------------|---------------------|
| Lean 4 | Apache-2.0 | ✓ | ✓ |
| Mathlib4 | Apache-2.0 | ✓ | ✓ |
| sentence-transformers | Apache-2.0 | ✓ | ✓ |
| all-MiniLM-L6-v2 | Apache-2.0 | ✓ | ✓ |
| PyTorch | BSD 3-Clause | ✓ | ✓ |
| HuggingFace datasets | Apache-2.0 | ✓ | ✓ |
| HuggingFace accelerate | Apache-2.0 | ✓ | ✓ |
| OpenAI Python | Apache-2.0 | ✓ | ✓ |
| pytest | MIT | ✓ | ✓ |
| LeanDojo (optional) | MIT | ✓ | ✓ |
| NTP Toolkit (optional) | MIT | ✓ | ✓ |

## Verification

All licenses were verified from the respective repository LICENSE files on 2026-07-18. Users should consult the original repositories for the most current license terms.

## Compliance

PriorProof itself is licensed under the MIT License (see LICENSE file). All third-party dependencies are compatible with this license choice.

For Apache-2.0 licensed dependencies, this document serves as the required NOTICE of third-party code usage. All copyright notices and license terms from the original projects are preserved in their respective packages.
