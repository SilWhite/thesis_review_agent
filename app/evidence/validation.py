from app.schemas import Assessment, Finding
from typing import List


def validate_evidence(assessment: Assessment, blocks: list) -> List[Finding]:
    lookup = {b["id"]: b for b in blocks}

    for finding in assessment.findings:
        if finding.locations and all(loc.verified for loc in finding.locations):
            continue
        # 1. If block_id is already valid
        if finding.block_id and finding.block_id in lookup:
            continue

        matched_id = None
        # 2. Try matching quote in block texts
        quote_snippet = (finding.quote or "").strip()
        if len(quote_snippet) >= 4:
            search_key = quote_snippet[:40]
            for b in blocks:
                if search_key in b.get("text", ""):
                    matched_id = b["id"]
                    break

        # 3. Try matching page from locations
        if not matched_id and finding.locations:
            for loc in finding.locations:
                if loc.block_id and loc.block_id in lookup:
                    matched_id = loc.block_id
                    break
                if matched_id:
                    break

        if matched_id:
            finding.block_id = matched_id
        else:
            # If quote exists but cannot be verified in extracted blocks, mark pending_verification
            if finding.quote and len(finding.quote.strip()) > 0:
                finding.status = "pending_verification"
            # Do NOT falsely assign to the first paragraph/block
            finding.block_id = ""

    return assessment.findings
