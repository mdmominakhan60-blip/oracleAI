# Third-party model notice

## palm_line_student_fp16.onnx

This model is vendored from [samuelwbarber/palm-line-reader](https://github.com/samuelwbarber/palm-line-reader), commit `bc48939`, under the **MIT License**. The original repository and license are preserved as the source of provenance.

SHA-256 for the default fp16 model:

```text
e2c9f826676b3aaf0a715f3087fcd4fc0b4dccd8c53de05fd26696a8399f8dd6
```

The optional int8 variant `palm_line_student_int8.onnx` has SHA-256
`14bcf11d75c790ac0c147f3335b2772d53bc558e8af54aaadc7a148f8cf8db0c`. It is
smaller but the upstream project reports visibly weaker thin-line quality; use
it only after a capture-distribution benchmark.

The model is a 5.55M-parameter U-Net with a fixed `[1, 3, 512, 512]` RGB input and four output classes: background, heart line, head line and life line. The upstream README reports foreground validation Dice `0.8098` on its own held-out data and warns that performance drops on off-distribution framing. OracleAI uses it only as an **auxiliary computer-vision evidence helper**. It does not establish palmistry meaning, health facts, personality, future events or certainty; the multimodal LLM must still inspect the user image and apply the strict Mira evidence/safety contract.

The training source photos and teacher checkpoint are not included in the upstream repository. OracleAI must benchmark this model on its own consented capture distribution before enabling a public-confidence claim. Relationship, children and travel lines are outside this model and remain capture-guided/LLM-only with `needs_photo` when unsupported.
