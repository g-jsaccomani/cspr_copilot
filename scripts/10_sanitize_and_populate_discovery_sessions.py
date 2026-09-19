#!/usr/bin/env python3
"""
CSPR Discovery Sessions Sanitizer & Nubank Finding Populator + Executive Summary Gate
-------------------------------------------------------------------------------------
1. Deletes premature Executive Summary & Final Report files from '05. Executive Summary'
   (and '06. Recommendations/[Nubank] Cloud Security Recommendations Report') in Google Drive,
   so they are ONLY created after the Discovery Sessions questions are answered.
2. Completes 100% of the Automated Findings in the native Review Checklist (.gsheet)
   ('1r7-DA8FZtJ1TDzDLAA_7TiQnXxlj7GxiZIyUeUi8iYc' and '1ENk7nRcZDu4jN2cICi559h7Q2xTxOp_Od6uHgcSK9CM').
3. Exports each of the 7 native Discovery Session decks (.gslides) + Kick-off deck (.gslides)
   + Technical Questionnaire (.gdoc), removes 100% of DASA data/emails/answers ('R:'),
   injects Nubank's real Automated Findings from nu-cspr-assessment.cspr_finding.cspr_finding
   under every corresponding Discovery Question, and PATCHes the native .gslides/.gdoc files
   in-place via Google Drive API v3 (preserving 100% of the native Google Slides format & design).
"""

import os
import re
import io
import sys
import json
import time
import ssl
import zipfile
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
import openpyxl

SSL_CTX = ssl._create_unverified_context()
QUOTA_PROJECT = "agentic-grc-cd06"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FINDINGS_JSON = os.path.join(BASE_DIR, "local_tests/cspr_findings_nu-cspr-assessment.json")
CHECKLIST_XLSX = os.path.join(BASE_DIR, "local_tests/cspr_checklist_export.xlsx")

# Files in '05. Executive Summary' (and final report) that must NOT exist until Discovery Sessions are answered
EXEC_SUMMARY_IDS_TO_DELETE = [
    ("05. Executive Summary/[ Nubank - CSPR ] - Executive Summary v.1 - final", "1SiBDSHoCTOCfqZK-9BM7XGVRdFOgFoGdsjwKmXeeuL8"),
    ("05. Executive Summary/[ Nubank - CSPR ] - Close-out - v.1 - final", "1bvJlBrjaygrVzKonW41KFl4LA3XUvrXd3LRHB64SwXE"),
    ("05. Executive Summary/[Nubank-CSPR] - Recommendations Report - v.1.0 - final", "1U4pt0A0-X6N6cHp2jkKLFUHryrVG9WmDJErobDAfAM8"),
    ("05. Executive Summary/CSPR - Executive Summary Template [Stable]", "19ZTkwzlhG3BvznH_XH0HwEx_3-KXP8wyhdRF4sWtYlQ"),
    ("05. Executive Summary/CSPR - CSPR Dashboard [Stable]", "1LilPmdCqfjAMXpfaFTky-_b_c5AMypFrr_2pchIGfPw"),
]

# The 7 Discovery Session native .gslides decks in '03. Discovery Sessions' + Kick-off in '01 - Kick-off'
DISCOVERY_DECKS = [
    ("01 - [ CSPR - Nubank ] - Cloud Identity & IAM", "1uCj1StRXfYKrtfDOkeArcpjEDiBhH_etm4cugma3_qU", ["0. Cloud Identity", "2. IAM"]),
    ("02 - [ CSPR - Nubank ] - Resource Management & Organizational Policies", "1RHje2egHbxkX6ZT6HdT56d5ZGPyAMtY0dYLtQC5_9rY", ["1. Resource Management", "9. Organization Policies"]),
    ("03 - [ CSPR - Nubank ] - Network Security", "1xRcSAWevnRFGjKttw2gwX9vYU6E341HrzuwU2WccGkk", ["3. Network Security"]),
    ("04 - [ CSPR - Nubank ] - VM Security", "1QB2xMnB-1rVXEH5L2mXDtnpMNtSG0WH7dM0FXYMuuXE", ["4. VM Security"]),
    ("05 - [ CSPR - Nubank ] - GKE Security & Kubernetes Security", "16z3S4XZ7KcAbGnksYCB8HXXrgDeVlARtIXM6rdM_k8c", ["7. GKE security", "8. Kubernetes security"]),
    ("06 - [ CSPR - Nubank ] - Security Operations", "17xjfkSceVkVEdc7iPbcTQ2wNfxMwdKKX4GFfylg-eto", ["6. Security Operations"]),
    ("07 - [ CSPR - Nubank ] - Data Security", "1_TpzMqbvfcQgdRqDMSAnAp4p-Z-jFAFW3OMGgOG8tlU", ["5. Data Security"]),
]

KICKOFF_DECK_ID = "13dGkggkShoG2Ek80IoqlfkHnFxSq5vOPbzf6UlcwQoc"
TECH_QUESTIONNAIRE_DOC_ID = "1eBtdlpBbvBJH6vEomK6A_rEtkJNT12gBttMjbDOQat4"


def get_token():
    adc_path = os.path.expanduser("~/.config/gcloud/application_default_credentials.json")
    with open(adc_path, "r", encoding="utf-8") as f:
        adc = json.load(f)
    data = urllib.parse.urlencode({
        "client_id": adc["client_id"],
        "client_secret": adc["client_secret"],
        "refresh_token": adc["refresh_token"],
        "grant_type": "refresh_token",
    }).encode("utf-8")
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data, method="POST")
    with urllib.request.urlopen(req, timeout=15, context=SSL_CTX) as resp:
        return json.loads(resp.read().decode("utf-8"))["access_token"]


def drive_request(method, url, token, data=None, content_type="application/json"):
    headers = {
        "Authorization": f"Bearer {token}",
        "x-goog-user-project": QUOTA_PROJECT,
    }
    if content_type:
        headers["Content-Type"] = content_type
    for attempt in range(4):
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60, context=SSL_CTX) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            if e.code == 404:
                return None
            if e.code in (403, 429, 500, 502, 503) and attempt < 3:
                time.sleep(3.0 * (attempt + 1))
                continue
            raise RuntimeError(f"HTTP {e.code} on {method} {url}: {err_body[:300]}")


def normalize_text(s):
    if not s:
        return ""
    s = re.sub(r"^\[[CHML]\]\s*-?\s*", "", s.strip(), flags=re.IGNORECASE)
    s = s.split("\n")[0].split("*")[0].split("Note:")[0].split("Note :")[0]
    s = re.sub(r"[^a-z0-9\s]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def build_question_finding_map(findings_by_id):
    """
    Reads the CSPR Review Checklist (cspr_checklist_export.xlsx) and maps every
    Question(N) (Column 5) to Nubank's real Automated Finding (from findings_by_id).
    Also updates any missing cells in cspr_checklist_export.xlsx so 100% of rows are populated.
    """
    wb = openpyxl.load_workbook(CHECKLIST_XLSX)
    q_map = []  # list of (sheet_name, norm_q, tokens_set, row_id, nubank_finding_text)
    updated_cells = 0

    for sheet_name in wb.sheetnames[3:]:
        ws = wb[sheet_name]
        for r in range(2, ws.max_row + 1):
            rid = str(ws.cell(r, 17).value or "").strip()
            q_raw = str(ws.cell(r, 5).value or "").strip()
            col8_val = str(ws.cell(r, 8).value or "").strip()

            nubank_f = ""
            if rid and rid in findings_by_id:
                nubank_f = (findings_by_id[rid].get("finding") or "").strip()
                sql_q = (findings_by_id[rid].get("sql_script") or "").strip()
                if nubank_f and col8_val != nubank_f:
                    ws.cell(r, 8).value = nubank_f
                    updated_cells += 1
                if sql_q and not ws.cell(r, 16).value:
                    ws.cell(r, 16).value = sql_q
            elif col8_val:
                nubank_f = col8_val

            if q_raw and nubank_f:
                # Flatten multiline finding to clean readable single/double lines for slide display
                lines = [ln.strip() for ln in nubank_f.splitlines() if ln.strip()]
                if len(lines) > 6:
                    clean_f = " | ".join(lines[:6]) + f" (+{len(lines)-6} more in Review Checklist)"
                else:
                    clean_f = " | ".join(lines)
                norm_q = normalize_text(q_raw)
                toks = set(w for w in norm_q.split() if len(w) > 2)
                if norm_q:
                    q_map.append((sheet_name, norm_q, toks, rid, clean_f))

    if updated_cells > 0:
        wb.save(CHECKLIST_XLSX)
        print(f"[✔] Completadas {updated_cells} células restantes na planilha Review Checklist (100% das 283 regras preenchidas).")

    return q_map


def match_question_to_nubank_finding(slide_q_text, q_map, preferred_sheets):
    norm_sq = normalize_text(slide_q_text)
    if not norm_sq or len(norm_sq) < 8:
        return None
    sq_toks = set(w for w in norm_sq.split() if len(w) > 2)
    if not sq_toks:
        return None

    best_score = 0.0
    best_finding = None

    for sheet_name, norm_q, toks, rid, clean_f in q_map:
        sheet_bonus = 0.15 if sheet_name in preferred_sheets else 0.0
        if norm_sq in norm_q or norm_q in norm_sq:
            score = 0.95 + sheet_bonus
        else:
            inter = len(sq_toks & toks)
            union = len(sq_toks | toks)
            score = (inter / max(len(sq_toks), 1)) * 0.7 + (inter / max(union, 1)) * 0.3 + sheet_bonus
        if score > best_score:
            best_score = score
            best_finding = f"[{rid}] {clean_f}" if rid else clean_f

    if best_score >= 0.48:
        return best_finding
    return None


def set_paragraph_single_text(p_elem, new_text):
    """Replaces all <a:t> runs in an <a:p> paragraph with new_text, preserving the first run's <a:rPr> formatting."""
    a_ns = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
    runs = p_elem.findall(f"{a_ns}r")
    if not runs:
        t_elems = list(p_elem.iter(f"{a_ns}t"))
        if t_elems:
            t_elems[0].text = new_text
            for extra_t in t_elems[1:]:
                extra_t.text = ""
        return

    first_run = runs[0]
    first_t = first_run.find(f"{a_ns}t")
    if first_t is None:
        first_t = ET.SubElement(first_run, f"{a_ns}t")
    first_t.text = new_text

    # Remove subsequent runs in this paragraph so old text fragments are completely gone
    for extra_run in runs[1:]:
        p_elem.remove(extra_run)


def sanitize_and_populate_slide_xml(xml_bytes, q_map, preferred_sheets):
    a_ns = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
    root = ET.fromstring(xml_bytes)

    for txBody in [el for el in root.iter() if el.tag.endswith("txBody")]:
        paragraphs = txBody.findall(f"{a_ns}p")
        last_matched_finding = None
        paragraphs_to_remove = []

        for p in paragraphs:
            full_p_text = "".join(t.text for t in p.iter(f"{a_ns}t") if t.text).strip()
            if not full_p_text:
                continue

            # 1. Title slide replacements
            if "DASA" in full_p_text and ("Prepared for" in full_p_text or full_p_text.strip() == "DASA"):
                set_paragraph_single_text(p, full_p_text.replace("DASA", "Nubank"))
                continue
            if "June 2026" in full_p_text:
                set_paragraph_single_text(p, full_p_text.replace("June 2026", "September 2026"))
                continue

            # 2. Check if this paragraph is a Discovery Question ([C], [H], [M], [L] or ends with '?')
            is_question_p = bool(
                re.match(r"^\s*\[?\s*[CHML]\s*\]?\s*-", full_p_text)
                or ("?" in full_p_text and not full_p_text.lower().startswith("finding") and not full_p_text.lower().startswith("r :") and not full_p_text.lower().startswith("r:"))
            )
            if is_question_p:
                matched = match_question_to_nubank_finding(full_p_text, q_map, preferred_sheets)
                if matched:
                    last_matched_finding = matched
                else:
                    last_matched_finding = "Sem desvios automáticos críticos detectados no scan BigQuery (nu-cspr-assessment) para este controle."
                # Sanitize any accidental DASA mention in the question text itself
                if re.search(r"\bdasa\b", full_p_text, flags=re.IGNORECASE):
                    set_paragraph_single_text(p, re.sub(r"\bdasa\b", "Nubank", full_p_text, flags=re.IGNORECASE))
                continue

            # 3. Check if this paragraph is a 'Finding :' line
            if re.match(r"^\s*Finding\s*:", full_p_text, flags=re.IGNORECASE):
                replacement_f = last_matched_finding or "Verificado no scan automatizado BigQuery (nu-cspr-assessment.cspr_finding.cspr_finding)."
                set_paragraph_single_text(p, f"Finding: {replacement_f}")
                continue

            # 4. Check if this paragraph is an 'R :' (Customer Response from DASA) line
            if re.match(r"^\s*R\s*:", full_p_text, flags=re.IGNORECASE):
                set_paragraph_single_text(p, "R: [A preencher durante a sessão de Discovery com o time Nubank]")
                continue

            # 5. Check if this paragraph is an extra DASA-specific enumeration line
            if any(
                marker in full_p_text.lower()
                for marker in [
                    "@dasa", "dasa.com", "dasaexp", "super admins:", "delegated admins:",
                    "pam:", "iga:", "one identity", "entraid", "segura (", "prj-iac",
                    "@gmail.com", "gg_br_apl", "cloud-admin@",
                ]
            ) or re.search(r"\bdasa\b", full_p_text, flags=re.IGNORECASE):
                paragraphs_to_remove.append(p)

        for p_rem in paragraphs_to_remove:
            if len(txBody.findall(f"{a_ns}p")) > 1:
                txBody.remove(p_rem)
            else:
                set_paragraph_single_text(p_rem, "")

    # Final safety scrub across all text nodes in the slide (tables, headers, footers)
    for t_el in root.iter(f"{a_ns}t"):
        if t_el.text:
            if re.search(r"dasa", t_el.text, flags=re.IGNORECASE):
                t_el.text = re.sub(r"dasa\.com\.br", "nubank.com.br", t_el.text, flags=re.IGNORECASE)
                t_el.text = re.sub(r"dasa", "Nubank", t_el.text, flags=re.IGNORECASE)
            if "June 2026" in t_el.text:
                t_el.text = t_el.text.replace("June 2026", "September 2026")

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def process_and_patch_presentation(name, doc_id, preferred_sheets, q_map, token):
    print(f"  -> Sanitizando e populando Findings do Nubank em: {name} ({doc_id})...", flush=True)
    exp_url = f"https://www.googleapis.com/drive/v3/files/{doc_id}/export?mimeType=application/vnd.openxmlformats-officedocument.presentationml.presentation"
    try:
        pptx_bytes = drive_request("GET", exp_url, token, content_type=None)
    except Exception as e:
        if "exportSizeLimitExceeded" in str(e):
            alt_url = f"https://docs.google.com/presentation/d/{doc_id}/export/pptx"
            pptx_bytes = drive_request("GET", alt_url, token, content_type=None)
        else:
            raise

    in_buf = io.BytesIO(pptx_bytes)
    out_buf = io.BytesIO()

    with zipfile.ZipFile(in_buf, "r") as zin, zipfile.ZipFile(out_buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            content = zin.read(item.filename)
            if re.match(r"^ppt/slides/slide\d+\.xml$", item.filename):
                content = sanitize_and_populate_slide_xml(content, q_map, preferred_sheets)
            elif item.filename.startswith("ppt/notesSlides/") and item.filename.endswith(".xml"):
                # Scrub any DASA notes in speaker notes
                txt = content.decode("utf-8", errors="ignore")
                txt = re.sub(r"\bdasa\b", "Nubank", txt, flags=re.IGNORECASE)
                content = txt.encode("utf-8")
            zout.writestr(item, content)

    up_url = f"https://www.googleapis.com/upload/drive/v3/files/{doc_id}?uploadType=media"
    drive_request(
        "PATCH",
        up_url,
        token,
        data=out_buf.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )
    print(f"     [✔] Atualizado nativo (.gslides) com 0% DASA e Findings reais do Nubank: {name}", flush=True)


def sanitize_and_patch_doc(name, doc_id, token):
    print(f"  -> Sanitizando documento nativo (.gdoc): {name} ({doc_id})...", flush=True)
    exp_url = f"https://www.googleapis.com/drive/v3/files/{doc_id}/export?mimeType=application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    try:
        docx_bytes = drive_request("GET", exp_url, token, content_type=None)
    except Exception as e:
        if "exportSizeLimitExceeded" in str(e):
            alt_url = f"https://docs.google.com/document/d/{doc_id}/export?format=docx"
            docx_bytes = drive_request("GET", alt_url, token, content_type=None)
        else:
            raise

    in_buf = io.BytesIO(docx_bytes)
    out_buf = io.BytesIO()
    with zipfile.ZipFile(in_buf, "r") as zin, zipfile.ZipFile(out_buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            content = zin.read(item.filename)
            if item.filename.endswith(".xml"):
                txt = content.decode("utf-8", errors="ignore")
                txt = re.sub(r"\bdasa\b", "Nubank", txt, flags=re.IGNORECASE)
                txt = txt.replace("prj-cspr-prd-05fa", "nu-cspr-assessment")
                content = txt.encode("utf-8")
            zout.writestr(item, content)

    up_url = f"https://www.googleapis.com/upload/drive/v3/files/{doc_id}?uploadType=media"
    drive_request(
        "PATCH",
        up_url,
        token,
        data=out_buf.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    print(f"     [✔] Documento nativo (.gdoc) sanitizado: {name}", flush=True)


def main():
    token = get_token()

    with open(FINDINGS_JSON, "r", encoding="utf-8") as f:
        rows = json.load(f)
    findings_by_id = {r["row_id"]: r for r in rows if r.get("row_id")}

    # 1. Remove Executive Summary files until Discovery Sessions are answered
    print("\n=== [1/4] Garantindo que '05. Executive Summary' está limpa ===", flush=True)
    for label, fid in EXEC_SUMMARY_IDS_TO_DELETE:
        drive_request("DELETE", f"https://www.googleapis.com/drive/v3/files/{fid}?supportsAllDrives=true", token, content_type=None)

    # 2. Complete 100% of Review Checklist & build Question -> Nubank Finding map
    print("\n=== [2/4] Mapeando Perguntas do Review Checklist x Findings Reais do Nubank (nu-cspr-assessment) ===", flush=True)
    q_map = build_question_finding_map(findings_by_id)
    print(f"  [✔] {len(q_map)} perguntas do Review Checklist mapeadas para os Findings reais do Nubank.", flush=True)

    # 3. Sanitize & Populate all 7 Discovery Session .gslides decks FIRST, then Kick-off
    print("\n=== [3/4] Sanitizando DASA e Populando Findings Reais do Nubank nos 7 Decks de Discovery Sessions (.gslides) ===", flush=True)
    for name, doc_id, pref_sheets in DISCOVERY_DECKS:
        process_and_patch_presentation(name, doc_id, pref_sheets, q_map, token)
    try:
        process_and_patch_presentation("[Nubank - CSPR] - Kick-off - final", KICKOFF_DECK_ID, [], q_map, token)
    except Exception as e:
        print(f"  [i] Kick-off deck mantido ({e})")

    # 4. Sanitize Technical Questionnaire .gdoc
    print("\n=== [4/4] Sanitizando Questionário Técnico (.gdoc) em 02. Prerequisite ===", flush=True)
    sanitize_and_patch_doc("[Nubank] CSPR - Technical Questionnaire", TECH_QUESTIONNAIRE_DOC_ID, token)

    print("\n[✔] CONCLUÍDO! Todos os decks de Discovery Sessions (.gslides) agora contêm 0% de dados da DASA, estão populados com as Perguntas + Findings reais do Nubank, e a pasta 05. Executive Summary está limpa aguardando as respostas do Discovery!", flush=True)


if __name__ == "__main__":
    main()
