#!/usr/bin/env python3
"""Refresh the public trivia bank around HGAB 3rd-reading evidence."""
import json
from pathlib import Path

ROOT = Path(__file__).parent
BANK = ROOT / "static/nep-preview/budget-trivia-2027.json"
NEP = Path("/Users/joebertj/nep")

KEEP = {
    "hgab3-project-row-count", "hgab3-unmatched-count", "hgab3-inspected-missing-docs",
    "hgab3-most-missing-type", "hgab3-documents-listed-count", "hgab3-linked-rows",
    "hgab3-linked-share", "hgab3-missing-photos", "hgab3-missing-pow", "hgab3-missing-docs-share",
    "flag-repeat-amount", "flag-historical-title", "flag-chainage-overlap", "flag-high-rate-threshold",
    "flag-short-range-threshold", "flag-rehab-good-fair", "flag-unmatched-meaning", "flag-no-docs-distinction",
    "flag-most-common-count", "flag-two-points-count", "hgab-3rd-highest-bridge-stated-meter-allocation",
    "medium-burol-rate-math", "medium-high-rate-both-checks", "medium-short-range-signal",
    "medium-repeat-allocation-scenario", "medium-missing-rdc-scenario", "medium-unmatched-and-no-docs",
    "medium-goodfair-rehab-scenario", "medium-recent-surfacing-scenario", "medium-missing-pow-scenario",
    "medium-missing-photos-scenario", "easy-summary-rcs-same-package", "medium-summary-mpb-match",
    "medium-summary-repeat-scope", "medium-summary-inspire-ledger", "medium-summary-missing-length",
    "medium-summary-high-rate-followup", "medium-flag-specific-camayse-peer-rate",
    "medium-flag-specific-tutuloy-overlap", "medium-flag-specific-repeated-allocation",
    "medium-flag-specific-abacan-attachments", "medium-flag-specific-good-fair-year",
    "medium-deo-villa-socorro-rate", "medium-deo-chainage-overlap-count",
}

def read_json(path):
    return json.loads(path.read_text())

def main():
    bank = read_json(BANK)
    questions = [q for q in bank["questions"] if q.get("id") in KEEP]
    by_id = {q["id"]: q for q in questions}

    # Coverage figures are tied to the latest available Transparency metadata snapshot.
    coverage = read_json(NEP / "analysis_output/dpwh-in-depth-data.json")["hgabCoverage"]
    review = read_json(NEP / "analysis_output/line_item_review_queue.json")["summary"]
    mpb = read_json(NEP / "analysis_output/mpb_analysis.json")
    cost = read_json(NEP / "analysis_output/cost_per_km.json")
    location = read_json(NEP / "analysis_output/congress_arcgis_bridge_audit.json")["summary"]

    def replace(qid, question=None, answer=None, explanation=None, choices=None):
        q = by_id[qid]
        if question is not None: q["question"] = question
        if explanation is not None: q["explanation"] = explanation
        if answer is not None:
            q["answer"] = answer
            if choices is None:
                choices = [answer] + [c for c in q["choices"] if c != answer][:3]
            q["choices"] = choices

    # Refresh changing figures/labels to the current HGAB 3rd evidence exports.
    replace("hgab3-project-row-count", answer=f"{coverage['projectRows']:,}", explanation=f"The HGAB 3rd-reading set contains {coverage['projectRows']:,} DPWH project rows. Document figures below use the Transparency metadata snapshot retrieved 18 October 2026.")
    replace("hgab3-unmatched-count", answer=f"{coverage['noSelectedNepRows']:,}", explanation=f"{coverage['noSelectedNepRows']:,} HGAB rows had no selected NEP counterpart in the current matching screen; this is a review lead, not proof of a new project.")
    replace("hgab3-inspected-missing-docs", answer=f"{coverage['missingAnyTypeRows']:,}", explanation=f"Among {coverage['inspectedRows']:,} inspected rows with listed documents, {coverage['missingAnyTypeRows']:,} lacked at least one tracked type in the 18 October 2026 metadata snapshot.")
    replace("hgab3-most-missing-type", answer="RDC endorsement", explanation="RDC endorsements were missing in 501 of the 751 inspected rows in the 18 October 2026 metadata snapshot.")
    replace("hgab3-documents-listed-count", answer=f"{coverage['listedAnyRows']:,}", explanation=f"{coverage['listedAnyRows']:,} HGAB rows had at least one Transparency document listing in the 18 October 2026 metadata snapshot.")
    replace("hgab3-linked-rows", answer=f"{coverage['linkedRows']:,}", explanation=f"{coverage['linkedRows']:,} of {coverage['projectRows']:,} HGAB rows were linked in the 18 October 2026 snapshot.")
    replace("hgab3-linked-share", answer=f"{coverage['linkedPct']:.1f}%", explanation=f"The linked share was {coverage['linkedPct']:.1f}% ({coverage['linkedRows']:,} of {coverage['projectRows']:,}) in the 18 October 2026 snapshot.")
    replace("hgab3-missing-photos", answer=f"{coverage['missingTypes']['photos']['count']:,}", explanation=f"{coverage['missingTypes']['photos']['count']:,} of {coverage['inspectedRows']:,} inspected rows lacked geotagged photos in the 18 October 2026 snapshot.")
    replace("hgab3-missing-pow", answer=f"{coverage['missingTypes']['pow']['count']:,}", explanation=f"{coverage['missingTypes']['pow']['count']:,} of {coverage['inspectedRows']:,} inspected rows lacked a POW in the 18 October 2026 snapshot.")
    replace("hgab3-missing-docs-share", answer=f"{coverage['missingAnyTypePct']:.1f}%", explanation=f"{coverage['missingAnyTypePct']:.1f}% of inspected rows with listed documents lacked at least one tracked type in the 18 October 2026 snapshot.")
    replace("flag-most-common-count", answer=f"{review['flagTypes']['missing_documents']:,} missing-document flags", explanation=f"Missing-document flags lead the queue with {review['flagTypes']['missing_documents']:,} occurrences; a flag signals a follow-up, not a finding of wrongdoing.")
    replace("flag-two-points-count", answer=f"{review['flagCountDistribution']['2']:,}", explanation=f"{review['flagCountDistribution']['2']:,} source occurrences carry exactly two review flags.")
    replace("medium-summary-mpb-match", question="An HGAB 3rd-reading multi-purpose building has no selected NEP counterpart. What should a reviewer compare before calling it new?", explanation="The counterpart review considers title, office, location, and scope; an unmatched row alone does not establish a new project.")
    replace("medium-summary-repeat-scope", question="An HGAB 3rd-reading project title recurs in an older GAA. What should be compared before calling the work a duplicate?", explanation="Compare location, scope, quantities, and chainage against the historical entry. A repeated title is a lead for review, not proof of duplicate work.")
    replace("easy-summary-rcs-same-package", question="How many district-office Rainwater Collector System lines remained unchanged in the HGAB 3rd-reading trace?", answer="199", explanation="The stage trace found 199 district-office RCS lines unchanged in HGAB 3rd reading. Each retained a ₱4.2 million allocation; the comparison describes budget stages, not expenditure.", choices=["199", "587", "2,835", "5,765"])
    by_id["easy-summary-rcs-same-package"]["sources"] = [{"label":"HGAB 3rd · RCS stage trace","url":"rcs.html"}]
    replace("medium-unmatched-and-no-docs", question="An HGAB 3rd-reading project has no selected counterpart in the matching screen and no listed documents. Which two review leads apply?", answer="No selected counterpart and missing documentation", explanation="The row merits both a counterpart review and a document-listing check. Neither condition alone establishes a new project or missing work.")

    # Keep evidence links focused on the HGAB 3rd-reading site and its analyses.
    for q in questions:
        q["stage"] = "HGAB 3rd reading"
        for source in q.get("sources", []):
            label = source.get("label", "")
            if "NEP" in label and "HGAB" not in label:
                source["label"] = label.replace("NEP", "HGAB 3rd")
        if q["id"].startswith("hgab3-"):
            q["explanation"] += " Figures are a dated metadata snapshot and can change as document listings are refreshed."

    # Add current analysis questions not represented in the legacy curated set.
    additions = [
        {"id":"hgab3-review-queue-size","question":"How many HGAB 3rd-reading source occurrences are flagged for follow-up in the current review queue?","answer":f"{review['flaggedOccurrences']:,}","choices":[f"{review['flaggedOccurrences']:,}",f"{review['sourceOccurrences']:,}",f"{review['flagTypes']['insertion']:,}",f"{review['flagTypes']['amount_group']:,}"],"explanation":f"The queue contains {review['flaggedOccurrences']:,} flagged source occurrences out of {review['sourceOccurrences']:,}. A flag prioritizes checking; it is not a conclusion of irregularity.","difficulty":"medium","topic":"review-queue","pool":"hgab-review-queue","sources":[{"label":"HGAB 3rd · line-item review queue","url":"dpwh.html#review-queue"}]},
        {"id":"hgab3-mpb-lines","question":"How many HGAB 3rd-reading multi-purpose building lines are in the current MPB analysis?","answer":f"{mpb['summary']['hgabLines']:,}","choices":[f"{mpb['summary']['hgabLines']:,}",f"{mpb['summary']['insertionCandidates']:,}",f"{mpb['summary']['ambiguousLines']:,}",f"{mpb['summary']['repeatPairs']:,}"],"explanation":f"The MPB analysis covers {mpb['summary']['hgabLines']:,} HGAB lines. Match candidates and repeated scopes are review groups, not confirmed additions or duplicates.","difficulty":"medium","topic":"matching","pool":"hgab-mpb-lines","sources":[{"label":"HGAB 3rd · multi-purpose building analysis","url":"mpb.html"}]},
        {"id":"hgab3-mpb-amount","question":"What total allocation do the HGAB 3rd-reading MPB lines carry in the current analysis?","answer":f"₱{mpb['summary']['hgabPesos']:,}","choices":[f"₱{mpb['summary']['hgabPesos']:,}","₱58,707,566,100","₱8,370,655,100","₱837,065,510"],"explanation":"This is the total of HGAB 3rd-reading MPB lines in the current analysis, not a reported expenditure total.","difficulty":"hard","topic":"allocation","pool":"hgab-mpb-amount","sources":[{"label":"HGAB 3rd · multi-purpose building analysis","url":"mpb.html"}]},
        {"id":"hgab3-rate-candidates","question":"How many HGAB 3rd-reading projects are currently flagged as high allocation per stated meter?","answer":f"{cost['highRateScreen']['candidates']:,}","choices":[f"{cost['highRateScreen']['candidates']:,}",f"{cost['highRateScreen']['graphExtremeRecords']:,}","109","501"],"explanation":"This is a screening count based on stated lengths and peer comparisons. It is not a finding that any project is overpriced.","difficulty":"medium","topic":"cost-per-meter","pool":"hgab-rate-candidates","sources":[{"label":"HGAB 3rd · allocation per stated length","url":"cost-per-km.html"}]},
        {"id":"hgab3-location-attribution","question":"How many HGAB 3rd-reading lines were uniquely assigned in the latest geographic attribution audit?","answer":f"{location['uniquelyAssignedLines']:,}","choices":[f"{location['uniquelyAssignedLines']:,}",f"{location['candidateLineItems']:,}","9,035","7,501"],"explanation":"The audit uniquely assigned these lines using qualified location consensus. Geographic attribution provides context and does not establish legislative sponsorship.","difficulty":"hard","topic":"geography","pool":"hgab-location-attribution","sources":[{"label":"HGAB 3rd · geographic attribution audit","url":"congress-geographic-attribution.html"}]},
    ]
    questions.extend(additions)
    # Stable pool identity prevents duplicate variants of the same question in one round.
    for q in questions:
        q["pool"] = q["id"]
        q["stage"] = "HGAB 3rd reading"
        if q["id"] == "hgab-3rd-highest-bridge-stated-meter-allocation":
            q["finalChallenge"] = True
        elif q.get("finalChallenge"):
            q.pop("finalChallenge", None)
    bank["questions"] = questions
    bank["generatedFrom"] = "HGAB 3rd-reading evidence; refreshed 2026-10-26"
    bank.pop("congressional_representatives", None)
    BANK.write_text(json.dumps(bank, ensure_ascii=False, indent=2) + "\n")
    print(f"Wrote {len(questions)} HGAB 3rd-reading questions")

if __name__ == "__main__":
    main()
