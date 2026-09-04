"""Benchmark deterministic palm CV components on public and repository fixtures.

This intentionally measures capture preflight and auxiliary evidence only. It does
not claim ground-truth palmistry accuracy without an annotated evaluation set.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core import palm_full_scope, palm_landmarks, palm_lines, palm_vision  # noqa: E402


IMAGE_PATHS = [
    ROOT / "tests/fixtures/palm/palm_hand.jpg",
    Path("/home/ubuntu/palmistry-candidate/code/input/hand1.jpg"),
    Path("/home/ubuntu/palmistry-candidate/code/input/hand48.jpg"),
    Path("/home/ubuntu/palmistry-candidate/code/input/hand6.jpg"),
    Path("/home/ubuntu/palmistry-candidate/code/input/hand70.jpg"),
    Path("/home/ubuntu/palmistry-candidate/detect/inputs/hand1_1.jpg"),
    Path("/home/ubuntu/palmistry-candidate/detect/inputs/hand1_2.jpg"),
    Path("/home/ubuntu/palm-line-reader/docs/example1_input.png"),
    Path("/home/ubuntu/palm-line-reader/docs/example2_input.png"),
    Path("/home/ubuntu/palm-line-reader/docs/example3_input.png"),
    Path("/home/ubuntu/palm-line-reader/docs/example4_input.png"),
    Path("/home/ubuntu/palmistry-candidate/data/IMG_0364.jpg"),
    Path("/home/ubuntu/palmistry-candidate/data/IMG_0367.jpg"),
    Path("/home/ubuntu/palmistry-candidate/data/IMG_0370.jpg"),
    Path("/home/ubuntu/palmistry-candidate/data/IMG_0382.HEIC"),
]


def main() -> None:
    rows = []
    for path in IMAGE_PATHS:
        item = {"file": str(path), "exists": path.is_file()}
        if not path.is_file():
            item["error"] = "missing"
            rows.append(item)
            continue
        image = path.read_bytes()
        item["bytes"] = len(image)
        item["precheck"] = palm_vision.analyze(image)
        item["line_segmentation_fp16"] = palm_lines.analyze(image)
        item["line_segmentation_int8"] = palm_lines.analyze(
            image, model_path=str(ROOT / "models" / "palm_line_student_int8.onnx")
        )
        item["line_segmentation_ensemble"] = palm_lines.analyze_ensemble(image)
        # Backward-compatible alias used by earlier benchmark reports.
        item["line_segmentation"] = item["line_segmentation_fp16"]
        item["hand_geometry"] = palm_landmarks.analyze(image)
        item["full_scope"] = palm_full_scope.analyze(
            image, hand_geometry=item["hand_geometry"]
        )
        rows.append(item)
    print(json.dumps({"count": len(rows), "results": rows}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
