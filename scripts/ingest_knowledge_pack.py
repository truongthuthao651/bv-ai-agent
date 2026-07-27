"""Ingest an offline "knowledge pack" of PUBLIC reference documents.

Why this exists: employees ask questions whose answer is public background
(Luật Kinh doanh bảo hiểm, thông tư/nghị định, public product brochures) rather
than internal policy text. Rather than putting the app on the network — CLAUDE.md
rule 4: no external API calls, must work air-gapped — a human downloads those
public files ONCE, records where each came from in a manifest, and this script
indexes them like any other document. Retrieval and answering stay entirely
offline; the recorded URL is only ever rendered as the citation link, so an
employee can click through to the public original.

The script itself performs NO network access: it reads local files only. If a
manifest entry points at a file that isn't there, it is reported and skipped —
downloading is deliberately a manual step, so nothing in this repo can fetch.

Manifest (``manifest.yaml`` next to the files; see ``manifest.example.yaml``):

    - file: luat_kinh_doanh_bao_hiem_2022.pdf
      title: Luật Kinh doanh bảo hiểm 2022 (Luật 08/2022/QH15)
      url: https://example.gov.vn/van-ban/luat-08-2022-qh15
      doc_type: reference          # optional, defaults to "reference"
      department: Pháp chế         # optional

Usage:

    python scripts/ingest_knowledge_pack.py                 # data/knowledge_pack
    python scripts/ingest_knowledge_pack.py <thư mục khác>
    python scripts/ingest_knowledge_pack.py --dry-run       # kiểm tra manifest

Note (native deployment): embedded Qdrant is single-process — stop the API
before running this.
"""

from __future__ import annotations

import argparse
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

# Import the app package when run as a plain script from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.ingest import _run_pipeline, _validate_source_url  # noqa: E402
from app.config.settings import settings  # noqa: E402
from app.models.schemas import DocType  # noqa: E402

_MANIFEST_NAME = "manifest.yaml"
_DEFAULT_DOC_TYPE = DocType.REFERENCE


@dataclass
class PackEntry:
    """One validated manifest row, resolved against the pack directory."""

    path: Path
    title: str
    url: str
    doc_type: DocType
    department: str | None


def _fail(message: str) -> None:
    print(f"  ✗ {message}", file=sys.stderr)


def parse_manifest(raw: object, pack_dir: Path) -> tuple[list[PackEntry], list[str]]:
    """Validate a loaded manifest into entries + human-readable problems.

    Pure (no I/O beyond ``Path.is_file``) so the manifest contract is
    unit-testable without Qdrant or a model.
    """
    entries: list[PackEntry] = []
    problems: list[str] = []
    if not isinstance(raw, list):
        return [], [f"{_MANIFEST_NAME} phải là một danh sách (list) các tài liệu."]

    for i, item in enumerate(raw, start=1):
        where = f"mục #{i}"
        if not isinstance(item, dict):
            problems.append(f"{where}: không phải một bản ghi (mapping).")
            continue
        filename = str(item.get("file") or "").strip()
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        if not filename or not title or not url:
            problems.append(f"{where}: thiếu 'file', 'title' hoặc 'url'.")
            continue
        # Manifest is authored by hand: keep it inside the pack directory.
        path = (pack_dir / filename).resolve()
        if not str(path).startswith(str(pack_dir.resolve())):
            problems.append(f"{where}: đường dẫn '{filename}' nằm ngoài thư mục pack.")
            continue
        if not path.is_file():
            problems.append(
                f"{where}: chưa có tệp '{filename}' trong {pack_dir} "
                "(hãy tải thủ công từ url rồi chạy lại)."
            )
            continue
        try:
            validated_url = _validate_source_url(url)
        except Exception as exc:  # HTTPException carries the Vietnamese detail
            problems.append(f"{where}: {getattr(exc, 'detail', exc)}")
            continue
        raw_type = str(item.get("doc_type") or "").strip()
        try:
            doc_type = DocType(raw_type) if raw_type else _DEFAULT_DOC_TYPE
        except ValueError:
            problems.append(f"{where}: doc_type không hợp lệ: '{raw_type}'.")
            continue
        department = str(item.get("department") or "").strip() or None
        if department and department not in settings.departments:
            problems.append(
                f"{where}: phòng ban '{department}' không có trong DEPARTMENTS."
            )
            continue
        entries.append(
            PackEntry(
                path=path,
                title=unicodedata.normalize("NFC", title),
                url=validated_url or url,
                doc_type=doc_type,
                department=department,
            )
        )
    return entries, problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "pack_dir",
        nargs="?",
        default=None,
        help="Thư mục chứa manifest.yaml và các tệp (mặc định: data/knowledge_pack)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chỉ kiểm tra manifest, không nạp vào Qdrant.",
    )
    args = parser.parse_args()

    import yaml  # local import: keeps --help working without the dependency

    pack_dir = Path(args.pack_dir or (settings.data_dir / "knowledge_pack"))
    manifest = pack_dir / _MANIFEST_NAME
    if not manifest.is_file():
        _fail(
            f"Không tìm thấy {manifest}. Xem manifest.example.yaml để biết định dạng."
        )
        return 1

    entries, problems = parse_manifest(
        yaml.safe_load(manifest.read_text(encoding="utf-8")), pack_dir
    )
    for problem in problems:
        _fail(problem)
    if not entries:
        _fail("Không có tài liệu nào hợp lệ để nạp.")
        return 1

    print(f"Sẽ nạp {len(entries)} tài liệu tham khảo công khai từ {pack_dir}:")
    for entry in entries:
        print(f"  • {entry.title}  ←  {entry.path.name}  ({entry.url})")
    if args.dry_run:
        print("--dry-run: không nạp gì cả.")
        return 0 if not problems else 1

    failures = 0
    for entry in entries:
        try:
            result = _run_pipeline(
                entry.path,
                entry.doc_type,
                entry.title,
                entry.department,
                entry.url,
            )
        except Exception as exc:
            failures += 1
            _fail(f"{entry.path.name}: {exc}")
            continue
        print(f"  ✓ {result.doc_title} — {result.n_chunks} đoạn")
    return 1 if failures or problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
