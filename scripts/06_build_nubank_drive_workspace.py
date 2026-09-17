#!/usr/bin/env python3
"""
Google Cloud Security Posture Review (CSPR) - Nubank Drive Workspace & Deliverables Builder
Populates the complete sanitized CSPR folder structure (mirroring [DASA] - CSPR / 01 - [Internal])
for Nubank (Organization ID: 802070535070 | Project: nu-cspr-assessment) with real telemetry & findings.
"""

import os
import sys
import json
import shutil
from datetime import datetime
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
import pptx
from pptx.util import Inches as PptInches, Pt as PptPt
from pptx.dml.color import RGBColor as PptRGBColor
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FINDINGS_JSON_PATH = os.path.join(BASE_DIR, "local_tests/cspr_findings_nu-cspr-assessment.json")
FINDINGS_RAW_SRC = os.path.join(BASE_DIR, "local_tests/Findings_raw_Nubank")

_ALL_TARGETS = [
    os.path.join(BASE_DIR, "deliverables/Nubank_CSPR_Drive/01 - [Internal]"),
    "/Users/jsaccomani/Library/CloudStorage/GoogleDrive-jsaccomani@google.com/Shared drives/Nu Pagamentos S A - INSTITUICAO DE PAGAMENTO GenAI CON X 600 [CR]/[EXT] Nubank/CSPR/01 - [Internal]",
    "/Users/jsaccomani/Library/CloudStorage/GoogleDrive-jsaccomani@google.com/My Drive/Nubank/CSPR/01 - [Internal]",
]
TARGETS = [
    t for idx, t in enumerate(_ALL_TARGETS)
    if idx == 0 or os.path.exists(os.path.dirname(os.path.dirname(t)))
]

NUBANK_META = {
    "customer": "Nubank (Nu Pagamentos S.A.)",
    "short_name": "Nubank",
    "org_id": "802070535070",
    "domain": "nubank.com.br",
    "project_id": "nu-cspr-assessment",
    "project_number": "164301515297",
    "location": "us-east1",
    "reviewer": "Joabson Saccomani (jsaccomani@google.com)",
    "date": "September 2026",
    "cai_tables": 235,
    "cai_rows": "10,140,678",
    "cai_size_gb": "10.61 GB",
    "projects_total": "343,869 (453 GCP Projects + 343,413 Apps Script Projects)",
    "folders_total": "194 Folders (401 Folder-level IAM Bindings)",
    "iam_policies": "360,227",
    "gke_resources": "29,874 (25 GKE Clusters | 94 Node Pools | 3,904 Pods)",
    "org_policy_evals": "2,622",
    "unused_sa_keys": "269 unused (>90d) out of 665 analyzed user-managed keys",
    "rec_rows": "466,675 (450,707 Insights + 15,968 Recommendations)",
    "total_checks": 326,
}

DOMAIN_MAP = {
    "cloudid": "01 - Cloud Identity & IAM",
    "iam": "01 - Cloud Identity & IAM",
    "iamrec": "01 - Cloud Identity & IAM",
    "policyanalyzer": "01 - Cloud Identity & IAM",
    "pltmi": "01 - Cloud Identity & IAM",
    "resource": "02 - Resource Management & Organizational Policies",
    "orgpol": "02 - Resource Management & Organizational Policies",
    "network": "03 - Network Security",
    "vm": "04 - VM Security",
    "gke": "05 - GKE Security & Kubernetes Security",
    "k8s": "05 - GKE Security & Kubernetes Security",
    "secops": "06 - Security Operations",
    "data": "07 - Data Security",
}


def load_findings():
    with open(FINDINGS_JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def style_slide_header(slide, title_text, subtitle_text=None):
    # Add Google Cloud header bar
    shape = slide.shapes.add_shape(
        1, PptInches(0), PptInches(0), PptInches(13.333), PptInches(1.15)
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = PptRGBColor(26, 115, 232)  # Google Blue
    shape.line.fill.background()

    txBox = slide.shapes.add_textbox(PptInches(0.5), PptInches(0.18), PptInches(12.3), PptInches(0.8))
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = title_text
    p.font.size = PptPt(24)
    p.font.bold = True
    p.font.color.rgb = PptRGBColor(255, 255, 255)

    if subtitle_text:
        p2 = tf.add_paragraph()
        p2.text = subtitle_text
        p2.font.size = PptPt(13)
        p2.font.color.rgb = PptRGBColor(232, 240, 254)


def add_bullet_slide(prs, title, subtitle, bullets):
    blank_layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank_layout)
    style_slide_header(slide, title, subtitle)

    txBox = slide.shapes.add_textbox(PptInches(0.6), PptInches(1.4), PptInches(12.1), PptInches(5.6))
    tf = txBox.text_frame
    tf.word_wrap = True
    for idx, b in enumerate(bullets):
        p = tf.paragraphs[0] if idx == 0 else tf.add_paragraph()
        p.text = f"• {b}"
        p.font.size = PptPt(14)
        p.space_after = PptPt(8)
        p.font.color.rgb = PptRGBColor(32, 33, 36)
    return slide


def build_presentation(filepath, deck_title, deck_subtitle, sections):
    prs = pptx.Presentation()
    prs.slide_width = PptInches(13.333)
    prs.slide_height = PptInches(7.5)

    # Cover slide
    cover = prs.slides.add_slide(prs.slide_layouts[6])
    bg = cover.shapes.add_shape(1, PptInches(0), PptInches(0), PptInches(13.333), PptInches(7.5))
    bg.fill.solid()
    bg.fill.fore_color.rgb = PptRGBColor(13, 45, 82)
    bg.line.fill.background()

    tb = cover.shapes.add_textbox(PptInches(0.8), PptInches(1.8), PptInches(11.5), PptInches(4.5))
    tf = tb.text_frame
    tf.word_wrap = True
    p0 = tf.paragraphs[0]
    p0.text = "Google Cloud Professional Services (PSO) — Security & Trust"
    p0.font.size = PptPt(16)
    p0.font.color.rgb = PptRGBColor(138, 180, 248)

    p1 = tf.add_paragraph()
    p1.text = deck_title
    p1.font.size = PptPt(34)
    p1.font.bold = True
    p1.font.color.rgb = PptRGBColor(255, 255, 255)

    p2 = tf.add_paragraph()
    p2.text = deck_subtitle
    p2.font.size = PptPt(18)
    p2.font.color.rgb = PptRGBColor(232, 240, 254)

    p3 = tf.add_paragraph()
    p3.text = (
        f"\nCustomer: {NUBANK_META['customer']} | Org ID: {NUBANK_META['org_id']}\n"
        f"Assessment Project: {NUBANK_META['project_id']} ({NUBANK_META['location']})\n"
        f"Lead Reviewer: {NUBANK_META['reviewer']} | Date: {NUBANK_META['date']}"
    )
    p3.font.size = PptPt(14)
    p3.font.color.rgb = PptRGBColor(189, 193, 198)

    for sec in sections:
        add_bullet_slide(prs, sec["title"], sec.get("subtitle", ""), sec["bullets"])

    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    prs.save(filepath)


def build_discovery_deck(filepath, session_num, domain_name, dom_prefixes, findings):
    dom_findings = [f for f in findings if f["row_id"].split("-")[0] in dom_prefixes]
    non_zero = [
        f for f in dom_findings
        if f.get("finding") and not f["finding"].strip().startswith("0 out of") and not f["finding"].strip().startswith("No ")
    ]
    sample_checks = (non_zero + dom_findings)[:18]

    sections = [
        {
            "title": f"{domain_name} — Scope & Telemetry Baseline (Nubank)",
            "subtitle": f"Organization ID: {NUBANK_META['org_id']} | Project: {NUBANK_META['project_id']}",
            "bullets": [
                f"Domain Evaluated: {domain_name} ({len(dom_findings)} automated CSPR controls executed).",
                f"Cloud Asset Inventory Baseline: {NUBANK_META['cai_tables']} tables | {NUBANK_META['cai_rows']} records ({NUBANK_META['cai_size_gb']}).",
                f"Resource Scope: {NUBANK_META['projects_total']} across {NUBANK_META['folders_total']}.",
                f"IAM & Policy Baseline: {NUBANK_META['iam_policies']} IAM bindings, {NUBANK_META['org_policy_evals']} Org Policy evaluations, {NUBANK_META['rec_rows']} Recommender insights.",
                "Objective: Validate architecture, identify high-priority posture gaps, and align on remediation roadmap.",
            ],
        }
    ]

    # Chunk findings into slides of 6 bullets each
    for i in range(0, len(sample_checks), 6):
        chunk = sample_checks[i : i + 6]
        bullets = []
        for c in chunk:
            txt = " | ".join([line.strip() for line in (c.get("finding") or "").splitlines() if line.strip()])
            if len(txt) > 180:
                txt = txt[:177] + "..."
            bullets.append(f"[{c['row_id']}] {c.get('section')} — {c.get('topic')}: {txt}")
        sections.append(
            {
                "title": f"{domain_name} — Automated Scanner Findings (Part {i//6 + 1})",
                "subtitle": f"Live telemetry extracted from {NUBANK_META['project_id']}.cspr_finding",
                "bullets": bullets,
            }
        )

    sections.append(
        {
            "title": f"{domain_name} — Discovery Discussion Questions & Next Steps",
            "subtitle": "Interactive Architecture Validation with Nubank Security & Platform Teams",
            "bullets": [
                "Validate exceptions and business justification for non-default configurations identified by the scanner.",
                "Confirm CI/CD & Terraform/IaC guardrails enforcing policy compliance across all 194 folders and 453 GCP projects.",
                "Review operational ownership and SLAs for P1/P2 remediation items in this security domain.",
                "Align on Quick Wins (0-30 days), Medium-Term Architecture Changes (30-90 days), and Long-Term Transformation (90+ days).",
            ],
        }
    )

    build_presentation(
        filepath,
        f"CSPR Discovery Session {session_num}: {domain_name}",
        f"Google Cloud Security Posture Review — {NUBANK_META['customer']}",
        sections,
    )


def build_word_doc(filepath, doc_title, doc_subtitle, sections_dict):
    doc = docx.Document()
    title_p = doc.add_heading(doc_title, level=0)
    sub_p = doc.add_paragraph(doc_subtitle)
    sub_p.runs[0].italic = True

    meta_table = doc.add_table(rows=5, cols=2)
    meta_table.style = "Table Grid"
    rows_data = [
        ("Customer / Organization", f"{NUBANK_META['customer']} (Org ID: {NUBANK_META['org_id']})"),
        ("Primary Domain", NUBANK_META["domain"]),
        ("Assessment Project & Region", f"{NUBANK_META['project_id']} (#{NUBANK_META['project_number']}) | {NUBANK_META['location']}"),
        ("Telemetry Datasets Ingested", f"cspr_cai ({NUBANK_META['cai_rows']} rows), cspr_policy (3,287 rows), cspr_rec ({NUBANK_META['rec_rows']})"),
        ("Lead PSO Security Reviewer", f"{NUBANK_META['reviewer']} — {NUBANK_META['date']}"),
    ]
    for idx, (k, v) in enumerate(rows_data):
        meta_table.rows[idx].cells[0].text = k
        meta_table.rows[idx].cells[1].text = v

    doc.add_paragraph()
    for sec_title, paragraphs in sections_dict.items():
        doc.add_heading(sec_title, level=1)
        for p_text in paragraphs:
            if p_text.startswith("• "):
                doc.add_paragraph(p_text[2:], style="List Bullet")
            else:
                doc.add_paragraph(p_text)

    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    doc.save(filepath)


def build_checklist_xlsx(filepath, findings):
    wb = openpyxl.Workbook()
    ws_sum = wb.active
    ws_sum.title = "Executive Summary"

    header_fill = PatternFill(start_color="1A73E8", end_color="1A73E8", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True, size=11)

    ws_sum.append(["Google Cloud Security Posture Review (CSPR) — Nubank Review Checklist"])
    ws_sum["A1"].font = Font(bold=True, size=14, color="1A73E8")
    ws_sum.append(["Customer", NUBANK_META["customer"]])
    ws_sum.append(["Organization ID", NUBANK_META["org_id"]])
    ws_sum.append(["Assessment Project", NUBANK_META["project_id"]])
    ws_sum.append(["Total Automated Checks Executed", len(findings)])
    ws_sum.append([])

    ws_sum.append(["Domain Prefix", "Security Domain", "Automated Checks Executed", "Findings With Affected Resources"])
    for cell in ws_sum[7]:
        cell.fill = header_fill
        cell.font = header_font

    by_dom = {}
    for r in findings:
        dom = r["row_id"].split("-")[0]
        by_dom.setdefault(dom, []).append(r)

    for dom, items in sorted(by_dom.items()):
        with_items = sum(1 for x in items if x.get("items"))
        ws_sum.append([dom.upper(), DOMAIN_MAP.get(dom, dom), len(items), with_items])

    ws_all = wb.create_sheet(title="All 326 CSPR Findings")
    headers = ["Row ID", "Domain", "Security Pillar", "Section", "Topic", "Automated Scanner Finding (Nubank)", "Affected Groups Count", "Sample Affected Resources"]
    ws_all.append(headers)
    for cell in ws_all[1]:
        cell.fill = header_fill
        cell.font = header_font

    for r in findings:
        rid = r["row_id"]
        dom = rid.split("-")[0]
        items = r.get("items") or []
        samples = []
        for grp in items[:3]:
            names = grp.get("names") or []
            samples.append(f"{grp.get('remark')}: {', '.join(names[:5])}")
        ws_all.append([
            rid,
            dom.upper(),
            DOMAIN_MAP.get(dom, dom),
            r.get("section", ""),
            r.get("topic", ""),
            r.get("finding", ""),
            len(items),
            " | ".join(samples)[:1000],
        ])

    for ws in [ws_sum, ws_all]:
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = 28

    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    wb.save(filepath)


def populate_workspace(root_dir, findings):
    print(f"\n>>> Populating Nubank CSPR Workspace at: {root_dir}")
    os.makedirs(root_dir, exist_ok=True)

    # 1. 01 - Kick-off
    kickoff_dir = os.path.join(root_dir, "01 - Kick-off")
    build_presentation(
        os.path.join(kickoff_dir, "[Nubank - CSPR] - Kick-off - final.pptx"),
        "[Nubank - CSPR] — Cloud Security Posture Review Kick-off",
        "Scope, Telemetry Architecture, Discovery Schedule & Deliverables",
        [
            {
                "title": "Engagement Overview & Objectives",
                "subtitle": "Google Cloud Professional Services (PSO) Security & Trust",
                "bullets": [
                    f"Target Environment: {NUBANK_META['customer']} (Organization ID: {NUBANK_META['org_id']}).",
                    f"Dedicated Assessment Project: {NUBANK_META['project_id']} ({NUBANK_META['location']}).",
                    "Comprehensive review across 7 core security domains and 326 automated posture rules.",
                    "Combines automated BigQuery telemetry analysis (CAI, Policy Analyzer, Recommenders) with 7 interactive architectural Discovery Sessions.",
                ],
            },
            {
                "title": "Telemetry Collection Summary (100% Completed)",
                "subtitle": "Validated BigQuery Datasets in nu-cspr-assessment",
                "bullets": [
                    f"Cloud Asset Inventory (cspr_cai): {NUBANK_META['cai_tables']} tables | {NUBANK_META['cai_rows']} rows | {NUBANK_META['cai_size_gb']}.",
                    f"Resource Hierarchy: {NUBANK_META['projects_total']} across {NUBANK_META['folders_total']}.",
                    f"Organization Policy & Key Analyzer (cspr_policy): {NUBANK_META['org_policy_evals']} Org Policy records + 665 SA Key analyses.",
                    f"Security & IAM Recommenders (cspr_rec): {NUBANK_META['rec_rows']}.",
                    f"CSPR Automated Findings (cspr_finding): 326 controls evaluated across 13 technical modules.",
                ],
            },
        ],
    )

    # 2. 02. Prerequisite
    prereq_dir = os.path.join(root_dir, "02. Prerequisite")
    with open(os.path.join(BASE_DIR, "local_tests/cloudrun-findings-processed-nu-cspr-assessment.yaml"), "r") as yf:
        yaml_content = yf.read()
    build_word_doc(
        os.path.join(prereq_dir, "YAML Nubank.docx"),
        "CSPR Cloud Run Job & Prerequisite Configuration YAML — Nubank",
        f"Sanitized Execution Manifests for {NUBANK_META['project_id']} (Org: {NUBANK_META['org_id']})",
        {
            "1. Cloud Run Jobs Configuration (nu-cspr-assessment)": [
                f"• Service Account: cspr-prereq-cloudrun-sa@{NUBANK_META['project_id']}.iam.gserviceaccount.com",
                f"• Artifact Registry: {NUBANK_META['location']}-docker.pkg.dev/{NUBANK_META['project_id']}/customer-cspr-toolkit",
                yaml_content,
            ]
        },
    )
    build_word_doc(
        os.path.join(prereq_dir, "[Nubank] CSPR - Technical Questionnaire.docx"),
        "[Nubank] CSPR — Technical Discovery Questionnaire",
        "Architectural & Operational Questionnaire Across All 7 CSPR Security Domains",
        {
            "Domain 01: Cloud Identity & IAM": [
                "• How are Super Admin and Organization Admin roles governed (`group:cloudsec@nubank.com.br`, `serviceAccount:nu-cloud-security@...`)?",
                "• What is the lifecycle process for the 665 user-managed Service Account keys (of which 269 have not been used in >90 days)?",
                "• How are external domain IAM bindings (`1,237 bindings` across partner domains) reviewed and recertified?",
            ],
            "Domain 02: Resource Management & Organization Policies": [
                "• How are the 194 folders and 343,869 projects (453 GCP + 343,413 Apps Script) provisioned and governed via Terraform/IaC?",
                "• What is the strategy for enforcing baseline Organization Policies (`constraints/compute.vmExternalIpAccess`, `constraints/storage.uniformBucketLevelAccess`, `constraints/iam.disableServiceAccountKeyCreation`) at the Organization root?",
            ],
            "Domain 03: Network Security": [
                "• How is the Shared VPC host project (`nu-ai-core-tooling`) segmented from standalone VPCs?",
                "• How are the 48 firewall rules allowing `0.0.0.0/0` ingress and the 148 VMs with external IPs monitored and restricted?",
                "• What is the policy for enabling Firewall Logging (`1,233 out of 1,241 firewall rules currently have logging disabled`)?",
            ],
            "Domain 04: VM & Compute Security": [
                "• How are OS patches applied across the 908 non-GKE VMs (`907 currently without OS Config Patch Deployments`)?",
                "• What is the migration plan for the 15 VMs utilizing the default Compute Engine Service Account (14 with Editor permissions)?",
            ],
            "Domain 05: GKE & Kubernetes Security": [
                "• What is the roadmap for enabling Application-Layer Secrets Encryption (`databaseEncryptionEnabled`) across the 25 GKE clusters?",
                "• How are container image retention policies managed in Artifact Registry (`81,097 of 184,380 images are >1 year old`)?",
            ],
            "Domain 06: Security Operations (SecOps)": [
                "• What third-party CSPM/SIEM platform ingests the 3 Organization-level Log Sinks since Security Command Center is currently disabled?",
                "• How are Data Access Audit Logs selectively enabled for critical production datasets and buckets?",
            ],
            "Domain 07: Data Security": [
                "• What is the remediation timeline for enabling Uniform Bucket-Level Access (UBLA) on the 203 Cloud Storage buckets currently using legacy ACLs?",
                "• How are CMEK keys in Cloud KMS (`cicd-delivery`, etc.) rotated and enforced across Cloud SQL, BigQuery, and Cloud Storage?",
            ],
        },
    )
    build_word_doc(
        os.path.join(prereq_dir, "[Nubank] CSPR - Toolkit Prerequisite Customer Guide.docx"),
        "[Nubank] CSPR — Toolkit Prerequisite & Telemetry Verification Guide",
        f"Completed Setup & Validation Record for {NUBANK_META['project_id']}",
        {
            "1. Telemetry Verification Summary": [
                f"• Cloud Asset Inventory (cspr_cai): {NUBANK_META['cai_tables']} tables | {NUBANK_META['cai_rows']} rows ({NUBANK_META['cai_size_gb']})",
                f"• Organization Policy & Key Analyzer (cspr_policy): 2 tables | 3,287 rows",
                f"• Recommender & Insights Export (cspr_rec): 2 tables | {NUBANK_META['rec_rows']}",
                f"• Automated Findings Dataset (cspr_finding): 88 normalized views + 326 evaluated controls",
            ]
        },
    )

    # 3. 03. Discovery Sessions
    disc_dir = os.path.join(root_dir, "03. Discovery Sessions")
    discovery_sessions = [
        ("01", "01 - [ CSPR - Nubank ] - Cloud Identity & IAM.pptx", "Cloud Identity & IAM", ["cloudid", "iam", "iamrec", "policyanalyzer", "pltmi"]),
        ("02", "02 - [ CSPR - Nubank ] - Resource Management & Organizational Policies.pptx", "Resource Management & Organizational Policies", ["resource", "orgpol"]),
        ("03", "03 - [ CSPR - Nubank ] - Network Security.pptx", "Network Security", ["network"]),
        ("04", "04 - [ CSPR - Nubank ] - VM Security.pptx", "VM Security", ["vm"]),
        ("05", "05 - [ CSPR - Nubank ] - GKE Security & Kubernetes Security.pptx", "GKE Security & Kubernetes Security", ["gke", "k8s"]),
        ("06", "06 - [ CSPR - Nubank ] - Security Operations.pptx", "Security Operations", ["secops"]),
        ("07", "07 - [ CSPR - Nubank ] - Data Security.pptx", "Data Security", ["data"]),
    ]
    for s_num, fname, d_title, prefixes in discovery_sessions:
        build_discovery_deck(os.path.join(disc_dir, fname), s_num, d_title, prefixes, findings)

    build_presentation(
        os.path.join(disc_dir, "CSPR - Discovery Sessions TEMPLATE [Stable].pptx"),
        "CSPR — Discovery Session Template [Stable]",
        f"Sanitized Standard Deck for {NUBANK_META['customer']}",
        [{"title": "Discovery Session Template", "subtitle": "Standard PSO Structure", "bullets": ["Domain Scope", "Key Findings", "Architectural Validation"]}],
    )

    # 4. 04. Findings
    findings_dir = os.path.join(root_dir, "04. Findings")
    raw_dst = os.path.join(findings_dir, "Findings_raw")
    if os.path.exists(raw_dst):
        shutil.rmtree(raw_dst)
    shutil.copytree(FINDINGS_RAW_SRC, raw_dst)
    build_checklist_xlsx(os.path.join(findings_dir, "[Nubank] Review Checklist - Cloud Security Posture Review.xlsx"), findings)

    # 5. 05. Executive Summary
    exec_dir = os.path.join(root_dir, "05. Executive Summary")
    exec_sections = [
        {
            "title": "Executive Summary — Nubank GCP Security Posture",
            "subtitle": f"Organization ID: {NUBANK_META['org_id']} | 343,869 Total Projects (453 GCP + 343,413 Apps Script)",
            "bullets": [
                "Full organization telemetry collected and analyzed across 10.61 GB of Cloud Asset Inventory data, 2,622 Org Policy states, 665 SA keys, and 466,675 Recommender insights.",
                "326 automated security controls evaluated across 7 security pillars (Identity/IAM, Resource/OrgPolicy, Network, Compute/VM, GKE/K8s, Data, SecOps).",
                "Strong foundational practices observed in GKE node image standardization (100% COS containerd across 94 node pools), GKE logging/monitoring (25/25 clusters enabled), and centralized Org Log Sinks (3 recursive sinks).",
                "Priority improvement areas identified in Service Account Key hygiene (269 unused keys >90d), excessive IAM privileges (1,439 IAM Recommender actions), Organization Policy enforcement at root, and Firewall Logging coverage.",
            ],
        },
        {
            "title": "Top Priority Findings & Strategic Recommendations",
            "subtitle": "Prioritized Remediation Roadmap for Nubank",
            "bullets": [
                "[P0 - IAM & Key Hygiene] Revoke/rotate 269 unused Service Account keys (>90 days inactive) and enforce constraints/iam.disableServiceAccountKeyCreation.",
                "[P0 - Excessive Permissions] Remediate 1 P1 and 1,438 P2 IAM Recommender findings, and reduce the 343,804 Owner/Editor bindings granted to Service Accounts.",
                "[P1 - Org Policy Guardrails] Enforce constraints/compute.vmExternalIpAccess, constraints/storage.uniformBucketLevelAccess, and constraints/compute.trustedImageProjects at Org/Folder levels.",
                "[P1 - GKE & K8s Hardening] Enable Application-layer Secrets Encryption (KMS) across all 25 GKE clusters and implement Artifact Registry cleanup policies (81,097 images >1 year old).",
                "[P1 - Network & VM Security] Review 48 0.0.0.0/0 ingress firewall rules, enable Firewall Logging on critical rules, and enroll 907 non-GKE VMs in OS Config Patch Management.",
                "[P2 - Data & SecOps] Enable Uniform Bucket-Level Access on the remaining 203 Cloud Storage buckets and configure Essential Contacts at Organization root.",
            ],
        },
    ]
    build_presentation(
        os.path.join(exec_dir, "[ Nubank - CSPR ] - Executive Summary v.1 - final.pptx"),
        "[ Nubank - CSPR ] — Executive Summary",
        f"Cloud Security Posture Review Findings & Strategic Roadmap — {NUBANK_META['customer']}",
        exec_sections,
    )
    build_presentation(
        os.path.join(exec_dir, "[ Nubank - CSPR ] - Close-out - v.1 - final.pptx"),
        "[ Nubank - CSPR ] — Engagement Close-Out Presentation",
        f"Consolidated Findings Across All 7 Security Domains — {NUBANK_META['customer']}",
        exec_sections,
    )
    build_presentation(
        os.path.join(exec_dir, "CSPR - Executive Summary Template [Stable].pptx"),
        "CSPR — Executive Summary Template [Stable]",
        "Google Cloud Professional Services (PSO) Security Practice",
        exec_sections[:1],
    )

    report_sections = {
        "1. Executive Summary & Scope": [
            f"Google Cloud Professional Services (PSO) conducted an organization-wide Cloud Security Posture Review (CSPR) for {NUBANK_META['customer']} (Organization ID: {NUBANK_META['org_id']}).",
            f"• Total Projects Assessed: {NUBANK_META['projects_total']} across {NUBANK_META['folders_total']}.",
            f"• Cloud Asset Inventory (cspr_cai): {NUBANK_META['cai_tables']} tables | {NUBANK_META['cai_rows']} rows ({NUBANK_META['cai_size_gb']}).",
            f"• Policy Analyzer & Recommenders: {NUBANK_META['org_policy_evals']} Org Policy records, 665 Service Account keys analyzed, and {NUBANK_META['rec_rows']}.",
            f"• Total Automated CSPR Controls Evaluated: {NUBANK_META['total_checks']} controls across 13 scanner modules.",
        ],
        "2. Key Findings & Recommendations — Cloud Identity & IAM": [
            "• [iam-09eb] Organization Admins: 2 principals hold roles/resourcemanager.organizationAdmin at the Org root (group:cloudsec@nubank.com.br and serviceAccount:nu-cloud-security@...).",
            "• [iam-122d] Primitive Roles on Service Accounts: 343,804 resources have IAM bindings granting Owner or Editor roles to Service Accounts.",
            "• [policyanalyzer-zi2u] Unused Service Account Keys: 269 out of 665 user-managed service account keys have not been used in the last 90 days.",
            "• [iamrec-w92s / iamrec-34qx] IAM Recommender: 1 P1 action and 1,438 P2 actions identified to revoke unused or excessive permissions.",
            "• [iam-2eus / iam-3fj5] External Identities: 1,237 IAM bindings to external users/groups and 35 Owner bindings outside nubank.com.br.",
            "• [pltmi-w34f2] Lateral Movement Insights: 105 lateral movement risk insights identified across service account impersonation chains.",
        ],
        "3. Key Findings & Recommendations — Resource Management & Organization Policies": [
            "• [resource-2b70 / resource-1036] Hierarchy: 1 Organization (802070535070), 194 Folders (401 folder IAM bindings), 453 GCP projects, and 343,413 Apps Script projects.",
            "• [resource-0umx] Essential Contacts: 0 principals are assigned Essential Contacts Viewer or Admin roles.",
            "• [orgpol-*] Organization Policies: Key constraints including constraints/compute.vmExternalIpAccess, constraints/compute.trustedImageProjects, constraints/storage.uniformBucketLevelAccess, and constraints/cloudfunctions.allowedIngressSettings are not enforced at the Organization root.",
        ],
        "4. Key Findings & Recommendations — Network Security": [
            "• [network-20f4 / network-03ce] Shared VPC: 1 Shared VPC host project (nu-ai-core-tooling) with 5 principals holding access to all subnets.",
            "• [network-12fc] Public Exposure: 148 out of 1,009 VMs have external IP addresses (including 4 GKE nodes), and 48 firewall rules allow ingress from 0.0.0.0/0.",
            "• [network-1fd7] Firewall Logging: 1,233 out of 1,241 active VPC firewall rules (and 10 out of 18 firewall policy rules) have logging disabled.",
        ],
        "5. Key Findings & Recommendations — VM & Compute Security": [
            "• [vm-3ox7] Instance Management: 890 out of 1,009 VMs are standalone instances (not managed in MIGs); 693 are currently running.",
            "• [vm-45wt] Patch Management: 907 out of 908 non-GKE VMs do not have an active OS Config VM Manager patch deployment.",
            "• [vm-2f10] Default Service Accounts: 15 VM instances use the default Compute Engine service account (14 with project Editor role).",
        ],
        "6. Key Findings & Recommendations — GKE & Kubernetes Security": [
            "• [gke-01uo] Secrets Encryption: 25 out of 25 GKE clusters do not have Application-Layer Secrets Encryption (KMS databaseEncryption) enabled.",
            "• [gke-035c / gke-08e4] Positive Controls: 100% of the 94 node pools use Container-Optimized OS with containerd, and 25/25 clusters have Cloud Logging and Monitoring enabled.",
            "• [k8s-0juz] Pod Security: 15 out of 1,949 customer containers use hostPort bindings.",
            "• [k8s-0x3r] Container Image Lifecycle: 81,097 out of 184,380 Docker image versions in Artifact Registry are older than 1 year (oldest from 2022-08-08).",
        ],
        "7. Key Findings & Recommendations — Data Security & SecOps": [
            "• [data-052d / data-23od] Cloud Storage: 203 out of 944 buckets do not have Uniform Bucket-Level Access (UBLA) enabled; 371 buckets lack lifecycle policies.",
            "• [secops-zhmk] Centralized Logging: 3 Organization-level aggregated log sinks are active with includeChildren=true.",
            "• [secops-c6eh] Security Command Center: Native SCC standard/premium notifications are disabled at the Organization level (verify external CSPM integration coverage).",
        ],
    }

    build_word_doc(
        os.path.join(exec_dir, "[Nubank-CSPR] - Recommendations Report - v.1.0 - final.docx"),
        "[Nubank-CSPR] — Cloud Security Recommendations Report (v1.0 Final)",
        f"Comprehensive Posture Assessment & Remediation Roadmap for {NUBANK_META['customer']}",
        report_sections,
    )
    build_word_doc(
        os.path.join(exec_dir, "CSPR - CSPR Dashboard [Stable].docx"),
        "CSPR — Looker Studio & BigQuery Dashboard Guide [Stable]",
        f"Connected to {NUBANK_META['project_id']}.cspr_finding",
        report_sections,
    )

    # 6. 06. Recommendations
    rec_dir = os.path.join(root_dir, "06. Recommendations")
    build_word_doc(
        os.path.join(rec_dir, "[Nubank] Cloud Security Recommendations Report.docx"),
        "[Nubank] Cloud Security Recommendations Report",
        f"Google Cloud PSO Security & Trust Deliverable — {NUBANK_META['customer']}",
        report_sections,
    )
    build_word_doc(
        os.path.join(rec_dir, "Recommendations Report Template - Cloud Security Posture Review [Stable][Security & Trust].docx"),
        "Recommendations Report Template — Cloud Security Posture Review [Stable]",
        "Sanitized Google Cloud PSO Template",
        report_sections,
    )
    build_checklist_xlsx(
        os.path.join(rec_dir, "Review Checklist Template - Cloud Security Posture Review [Stable].xlsx"),
        findings,
    )

    # 7. [Int] User Guide
    ug_dir = os.path.join(root_dir, "[Int] User Guide")
    build_word_doc(
        os.path.join(ug_dir, "CSPR Toolkit - User Guide [Stable].docx"),
        "CSPR Toolkit — Internal Reviewer User Guide [Stable]",
        f"Sanitized Edition for {NUBANK_META['customer']} Assessment ({NUBANK_META['project_id']})",
        report_sections,
    )


def main():
    findings = load_findings()
    for t in TARGETS:
        try:
            populate_workspace(t, findings)
            print(f"[✔] Successfully built workspace: {t}")
        except Exception as e:
            print(f"[!] Warning populating {t}: {e}")


if __name__ == "__main__":
    main()
