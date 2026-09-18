from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .common import norm, utc_now

# ---------------------------------------------------------------------------
# WHY THIS EXISTS HERE, NOT IN A CONSUMER REPO
# ---------------------------------------------------------------------------
# Loading a whole directive to answer a question about one guideline puts
# twelve other guidelines in front of a model. Splitting on section
# boundaries means the text of an unrelated guideline is never in the
# context window at all, which is a physical guarantee rather than an
# instruction.
#
# This split writes into the governed library, so it must go through this
# repo's build-candidate -> validate -> evaluate -> approve -> publish gate
# like every other derived artifact (chunks, indexes). A consumer repo
# (e.g. adverse-information-assistant) reads the published result; it must
# never regenerate it directly against the library, because that bypasses
# the audit trail, the rollback snapshot, and the reassembly proof being
# reviewed as part of a release rather than trusted on say-so.
#
# The relative output paths below are a cross-repo contract: a consumer
# reading the split locates it by these same paths (or, more robustly, by
# the document_id -> robot_text_path lookup in documents.jsonl, which is
# how this module finds the source text too). Changing a path here without
# a coordinated change on the read side breaks that consumer silently.

SEAD_TEXT_DIR = ("ROBOT_READABLE_DIRECTORY/TEXT/PERSONNEL_VETTING/"
                  "SECURITY_EXECUTIVE_AGENT_DIRECTIVES_SEAD")
SEAD4_DIR = f"{SEAD_TEXT_DIR}/SEAD-4_Adjudicative-Guidelines"
SEAD3_DIR = f"{SEAD_TEXT_DIR}/SEAD-3_Reporting-Requirements"

ISL_DIR = ("ROBOT_READABLE_DIRECTORY/TEXT/INDUSTRIAL_SECURITY/"
           "INDUSTRIAL_SECURITY_LETTERS_ISL/CURRENT")
ISL_SPLIT_DIR = f"{ISL_DIR}/2021-02_SEAD-3_rev-2024"

SPLIT_FOLDERS = {"SEAD-3": SEAD3_DIR, "SEAD-4": SEAD4_DIR, "ISL-2021-02": ISL_SPLIT_DIR}

# document_id, per documents.jsonl — the durable key. Resolving the source
# text through it (rather than a literal path) survives a library rename;
# see the release history around 2026-09-08 for the incident that motivated
# this in the consumer repo.
DIRECTIVE_DOC_IDS = {
    "SEAD-3": "dcsa-sead-sead-3-reporting-requirements",
    "SEAD-4": "dcsa-sead-sead-4-adjudicative-guidelines",
    "ISL-2021-02": "dcsa-isl_current-2021-02-sead-3-rev-2024",
}

FURNITURE = re.compile(
    r"^\s*(?:=+\s*PAGE\s+\d+\s*=+|UNCLASSIFIED|Page\s+\d+|\d{1,3})\s*$", re.I)

SEAD3 = [
    (r"^A\.\s+AUTHORITY", "01_Overview_Policy_and_General_Requirements.md",
     "Overview, Policy and General Requirements",
     "Authority, purpose, applicability, definitions and policy."),
    (r"^F\.\s+REPORTABLE ACTIVITIES FOR ALL COVERED INDIVIDUALS",
     "02_All_Covered_Individuals.md", "All Covered Individuals",
     "Reportable activities that apply to every covered individual."),
    (r"^G\.\s+REPORTABLE ACTIVITIES FOR INDIVIDUALS WITH ACCESS TO SECRET",
     "03_Secret_Confidential_L_Noncritical.md",
     "Secret, Confidential, L Access, and Non-Critical Sensitive Positions",
     "Additional reporting requirements at the Secret/Confidential/L level, "
     "in addition to those in Section F."),
    (r"^H\.\s+REPORTABLE ACTIVITIES FOR INDIVIDUALS WITH ACCESS TO TOP SECRET",
     "04_Top_Secret_Q_Critical_Special.md",
     "Top Secret, Q Access, and Critical or Special Sensitive Positions",
     "Additional reporting requirements at the Top Secret/Q level, in addition "
     "to those in Section F."),
    (r"^I\.\s+RESPONSIBILITIES", "05_Responsibilities_and_Effective_Date.md",
     "Responsibilities and Effective Date",
     "Agency responsibilities and the effective date of the Directive."),
    (r"^APPENDIX A", "06_Appendix_A_Required_Data_Elements.md",
     "Appendix A — Required Data Elements for Reporting",
     "The information a report must contain, by reportable activity."),
]

GUIDELINES = [
    ("A", "Allegiance_to_the_United_States", "Allegiance to the United States"),
    ("B", "Foreign_Influence", "Foreign Influence"),
    ("C", "Foreign_Preference", "Foreign Preference"),
    ("D", "Sexual_Behavior", "Sexual Behavior"),
    ("E", "Personal_Conduct", "Personal Conduct"),
    ("F", "Financial_Considerations", "Financial Considerations"),
    ("G", "Alcohol_Consumption", "Alcohol Consumption"),
    ("H", "Drug_Involvement_and_Substance_Misuse",
     "Drug Involvement and Substance Misuse"),
    ("I", "Psychological_Conditions", "Psychological Conditions"),
    ("J", "Criminal_Conduct", "Criminal Conduct"),
    ("K", "Handling_Protected_Information", "Handling Protected Information"),
    ("L", "Outside_Activities", "Outside Activities"),
    ("M", "Use_of_Information_Technology", "Use of Information Technology"),
]

SEAD4 = [
    (r"^A\.\s+AUTHORITY", "01_Directive_Overview_and_Policy.md",
     "Directive Overview and Policy",
     "Authority, purpose, applicability, definitions, policy and effective date."),
    (r"^APPENDIX A\b", "02_Appendix_A_Introduction_and_Adjudicative_Process.md",
     "Appendix A — Introduction and the Adjudicative Process",
     "The introduction and the adjudicative process, including the whole-person "
     "concept. APPLIES TO EVERY GUIDELINE — load this alongside any guideline."),
]
for _i, (_ltr, _slug, _title) in enumerate(GUIDELINES, start=3):
    SEAD4.append((rf"^GUIDELINE {_ltr}:", f"{_i:02d}_Guideline_{_ltr}_{_slug}.md",
                  f"Guideline {_ltr} — {_title}",
                  f"The concern, disqualifying conditions and mitigating "
                  f"conditions for Guideline {_ltr}."))
SEAD4 += [
    (r"^APPENDIX B\b", "16_Appendix_B_Bond_Amendment_Guidance.md",
     "Appendix B — Bond Amendment Guidance",
     "Statutory restrictions on granting eligibility."),
    (r"^APPENDIX C\b", "17_Appendix_C_Exceptions.md",
     "Appendix C — Exceptions",
     "Waiver, condition and deviation — definitions and when each applies."),
]

PROVENANCE = (
    "> Section-level extract of the machine-readable text of *{full}*. Cut at "
    "section headings by the DCSA Archivist's directive-split build step; the "
    "parts are verified to reassemble into the source before this release could "
    "be validated. Page and classification furniture is removed. OCR artifacts "
    "in the source are reproduced unchanged — this file is faithful to the text "
    "it was made from, not corrected."
)

ISL = [
    (r"^\s*CLARIFICATION AND GUIDANCE ON REPORTABLE ACTIVITIES",
     "01_Overview_and_Adverse_Information_Guidance.md",
     "Overview and Adverse Information Guidance",
     "Scope, who counts as a covered individual, and the narrative guidance on "
     "adverse information reporting that precedes the tables.", None),
    (r"^\s*TABLE 1:", "02_Table_1_Adverse_Information.md",
     "Table 1 — Adverse Information Reporting Requirements",
     "Adverse information items reportable for all covered individuals.",
     "corpus/reporting/tables/adverse-information.yaml"),
    (r"^\s*TABLE 2:", "03_Table_2_All_Covered_Individuals.md",
     "Table 2 — Reporting Requirements for All Covered Individuals",
     "Reportable activities that apply to every covered individual.",
     "corpus/reporting/tables/all-covered-individuals.yaml"),
    (r"^\s*TABLE 3:", "04_Table_3_Top_Secret_Q.md",
     "Table 3 — Top Secret and “Q” Access",
     "Additional reporting requirements specific to Top Secret or Q access.",
     "corpus/reporting/tables/top-secret-q.yaml"),
    (r"^\s*TABLE 4:", "05_Table_4_Foreign_Travel.md",
     "Table 4 — Foreign Travel Reporting",
     "Foreign travel reporting, pre-approval, and the aggregation rule.",
     "corpus/reporting/tables/all-covered-individuals.yaml"),
]

DIRECTIVES = {
    "SEAD-3": {
        "full": "Security Executive Agent Directive 3: Reporting Requirements "
                "for Personnel with Access to Classified Information or Who "
                "Hold a Sensitive Position",
        "anchors": SEAD3,
    },
    "SEAD-4": {
        "full": "Security Executive Agent Directive 4: National Security "
                "Adjudicative Guidelines",
        "anchors": SEAD4,
    },
    "ISL-2021-02": {
        "full": "DCSA Industrial Security Letter 2021-02, SEAD 3 "
                "implementation for cleared industry (revised 2024)",
        "anchors": ISL,
    },
}


def _strip_furniture(lines: list[str]) -> list[str]:
    return [l for l in lines if not FURNITURE.match(l)]


def _sig(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _source_paths(records: list[dict[str, Any]]) -> dict[str, str]:
    """document_id -> robot_text_path, for the directives we split."""
    wanted = set(DIRECTIVE_DOC_IDS.values())
    found: dict[str, str] = {}
    for record in records:
        did = record.get("document_id")
        if did in wanted:
            found[did] = record.get("robot_text_path")
    return found


def build_directive_splits(root: Path, records: list[dict[str, Any]], producer: str = "dcsa-archivist build-candidate"
                            ) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """Split SEAD-3, SEAD-4 and ISL 2021-02 into per-section files.

    Returns (files, problems, skipped). `files` is a list of
    {"relative_path": <posix path under root>, "content": <str>} ready to be
    written under a release's production tree — the generic publish step in
    release.py copies everything under production/ to the library root, so no
    directive-split-specific publish logic is needed.

    `skipped` covers a directive that is simply absent from THIS library (no
    matching document_id, or its source text is not on disk) — not every
    library this pipeline runs against carries the SEAD/ISL directives, and
    that is not a defect. It is informational only and never blocks
    publication.

    `problems` covers a directive that IS present but whose split could not
    be verified (anchor mismatch, reassembly failure, a missing guideline
    file) — that is this repo's job breaking, so it blocks publication. A
    directive whose reassembly cannot be proven contributes no files and is
    reported here instead — partial, unverified output is worse than none,
    so nothing is written for that directive at all. This mirrors the
    all-or-nothing behaviour the original standalone script enforced.
    """
    source_paths = _source_paths(records)
    files: list[dict[str, Any]] = []
    problems: list[str] = []
    skipped: list[str] = []
    ineligible = {r.get('document_id') for r in records
                  if r.get('document_id') in DIRECTIVE_DOC_IDS.values()
                  and (r.get('current_status') != 'current'
                       or r.get('answer_eligibility', 'answer_eligible') != 'answer_eligible')}

    for name, spec in DIRECTIVES.items():
        doc_id = DIRECTIVE_DOC_IDS[name]
        if doc_id in ineligible:
            problems.append(f'{name}: directive source is not current and answer-eligible; reviewed successor or explicit split retirement required')
            continue
        rel = source_paths.get(doc_id)
        if not rel:
            skipped.append(f"{name}: document_id {doc_id!r} not found in the "
                            f"enriched manifest — not carried by this library")
            continue
        src = root / norm(rel)
        if not src.is_file():
            skipped.append(f"{name}: manifest names {rel} but it is not on disk")
            continue

        raw = src.read_text(encoding="utf-8", errors="replace")
        lines = raw.splitlines()

        cuts: list[tuple[int, tuple]] = []
        ok = True
        for anchor in spec["anchors"]:
            pat = re.compile(anchor[0])
            hits = [i for i, l in enumerate(lines) if pat.match(l)]
            if len(hits) != 1:
                problems.append(f"{name}: anchor {anchor[0]!r} matched "
                                 f"{len(hits)} times; expected exactly 1")
                ok = False
                break
            cuts.append((hits[0], anchor))
        if not ok:
            continue
        cuts.sort(key=lambda c: c[0])
        if [c[1][1] for c in cuts] != [a[1] for a in spec["anchors"]]:
            problems.append(f"{name}: sections are not in the expected order")
            continue

        pieces = []
        for n, (start, anchor) in enumerate(cuts):
            end = cuts[n + 1][0] if n + 1 < len(cuts) else len(lines)
            body = lines[0:end] if n == 0 else lines[start:end]
            pieces.append((anchor, _strip_furniture(body)))

        want = _sig("\n".join(_strip_furniture(lines)))
        got = _sig("\n".join("\n".join(b) for _, b in pieces))
        if want != got:
            i = next((k for k in range(min(len(want), len(got))) if want[k] != got[k]),
                      min(len(want), len(got)))
            problems.append(
                f"{name}: REASSEMBLY FAILED — the parts do not reproduce the "
                f"source (first divergence near char {i} of {len(want)}). "
                f"Nothing written for this directive.")
            continue

        bad_start = False
        for anchor, body in pieces:
            first = next((l for l in body if l.strip()), "")
            if anchor is cuts[0][1]:
                continue
            if not re.match(anchor[0], first):
                problems.append(f"{name}: {anchor[1]} does not start at its "
                                 f"heading (starts {first[:60]!r})")
                bad_start = True
        if bad_start:
            continue

        if name == "SEAD-4":
            letters = {re.search(r"Guideline_([A-M])_", a[1]).group(1)
                       for a, _ in pieces if "_Guideline_" in a[1]}
            missing = sorted(set("ABCDEFGHIJKLM") - letters)
            if missing:
                problems.append(f"SEAD-4: missing guideline file(s) for {missing}")
                continue

        out_dir = SPLIT_FOLDERS[name]
        manifest = {"directive": name, "source_file": src.name,
                    "source_sha256": hashlib.sha256(raw.encode()).hexdigest(),
                    "generated_by": producer,
                    "generated_utc": utc_now(),
                    "cut_method": "section headings, reassembly-verified",
                    "sections": []}
        for anchor, body in pieces:
            pat, fname, title, scope = anchor[:4]
            verifies = anchor[4] if len(anchor) > 4 else None
            text = "\n".join(body).strip("\n")
            doc = (f"# {name} — {title}\n\n**Scope:** {scope}\n\n"
                   f"{PROVENANCE.format(full=spec['full'])}\n\n---\n\n{text}\n")
            files.append({"relative_path": f"{out_dir}/{fname}", "content": doc})
            entry = {"file": fname, "title": title,
                      "body_sha256": hashlib.sha256(text.encode()).hexdigest(),
                      "lines": len(body)}
            m = re.search(r"Guideline_([A-M])_", fname)
            if m:
                entry["guideline"] = m.group(1)
            if verifies:
                entry["verifies"] = verifies
            manifest["sections"].append(entry)
        files.append({"relative_path": f"{out_dir}/manifest.json",
                      "content": json.dumps(manifest, indent=2) + "\n"})

        index = "\n".join(f"| `{s['file']}` | {s['title']} |"
                          for s in manifest["sections"])
        readme = (
            f"# {name} — section-level text\n\n"
            f"Machine-readable text of *{spec['full']}*, split so a reader loads "
            f"only the section it needs.\n\n"
            f"Cut at section headings and verified to reassemble into "
            f"`../{src.name}` with no loss, as part of a gated evidence release. "
            f"`manifest.json` carries the section index and a SHA-256 for each "
            f"body.\n\n"
            + ("**Load `02_Appendix_A_Introduction_and_Adjudicative_Process.md` "
               "alongside any guideline file.** It carries the adjudicative "
               "process and the whole-person concept, which qualify every "
               "guideline.\n\n"
               if name == "SEAD-4" else
               "**Sections G and H are additive.** They list requirements *in "
               "addition to* Section F, so a reader at either level needs "
               "`02_All_Covered_Individuals.md` as well.\n\n"
               if name == "SEAD-3" else
               "Each table file records, in `manifest.json`, the corpus "
               "reporting table it is the source of record for — so verifying "
               "a corpus table is a file-to-file comparison rather than a hunt "
               "through the letter.\n\n")
            + f"| File | Contents |\n|---|---|\n{index}\n\n"
            f"Generated by `{producer}` — never edit "
            f"these files directly; edit `directive_splits.py` and cut a new "
            f"release.\n")
        files.append({"relative_path": f"{out_dir}/README.md", "content": readme})

    return files, problems, skipped
