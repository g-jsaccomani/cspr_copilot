#!/usr/bin/env python3
"""
CSPR Native Google Workspace Cloner & Automated Checklist Populator
--------------------------------------------------------------------
1. Populates any native Google Sheet Review Checklist (.gsheet, e.g.
   1r7-DA8FZtJ1TDzDLAA_7TiQnXxlj7GxiZIyUeUi8iYc) directly from BigQuery /
   local_tests/cspr_findings_<project>.json in <2 seconds via Google Sheets API
   (spreadsheets.values.batchUpdate), preserving 100% of original formatting,
   dropdowns, formulas, colors, and Apps Script.
2. Clones the official Google Cloud CSPR Templates (.gdoc, .gsheet, .gslides)
   from [DASA] - CSPR / PSO Library into My Drive/Nubank/CSPR/01 - [Internal]
   as NATIVE Google Workspace documents (no .docx/.xlsx/.pptx conversion!) and
   replaces customer metadata via Docs/Slides replaceAllText API.
"""

import os
import sys
import json
import urllib.request
import urllib.parse
import urllib.error
import subprocess

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_FINDINGS_JSON = os.path.join(BASE_DIR, "local_tests/cspr_findings_nu-cspr-assessment.json")
DEFAULT_SPREADSHEET_ID = "1r7-DA8FZtJ1TDzDLAA_7TiQnXxlj7GxiZIyUeUi8iYc"

REQUIRED_SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/presentations",
]

# Official Google Workspace Template Doc IDs from [DASA] - CSPR / PSO Library
NATIVE_TEMPLATES = [
    # (Subfolder in 01 - [Internal], Target Native Filename, Source Template doc_id, mimeType)
    ("01 - Kick-off", "[Nubank - CSPR] - Kick-off - final", "1hYlw-1bE_LFiFFYgCKX46Niq8kU603idHeFSt14Yg3k", "application/vnd.google-apps.presentation"),
    ("02. Prerequisite", "YAML Nubank", "1HIRs8EY7ckd9Fl5ic-4kqdj2wh9zNdPT6h0ml9kWzGQ", "application/vnd.google-apps.document"),
    ("02. Prerequisite", "[Nubank] CSPR - Technical Questionnaire", "1KSE4CPPLj93xqEuKZCNkY0-1Swhsa6GzW0kF3Otzuzw", "application/vnd.google-apps.document"),
    ("02. Prerequisite", "[Nubank] CSPR - Toolkit Prerequisite Customer Guide", "1RAqofcyPVwaoeBt0oHFwlRjeDSth8HgqAmZqiMGKaII", "application/vnd.google-apps.document"),
    ("03. Discovery Sessions", "01 - [ CSPR - Nubank ] - Cloud Identity & IAM", "1IQfibfw33qVp_UN7vmScJANSxV4ldOuHc_F8ZegpyZo", "application/vnd.google-apps.presentation"),
    ("03. Discovery Sessions", "02 - [ CSPR - Nubank ] - Resource Management & Organizational Policies", "1WVn8nTT4bFdkbWRi0JbO9_WobfjVCbTayXu26wVDsDE", "application/vnd.google-apps.presentation"),
    ("03. Discovery Sessions", "03 - [ CSPR - Nubank ] - Network Security", "1sVT0JfGQMTew72ET41raoIIUco5Xgahn2--oQOqKnbo", "application/vnd.google-apps.presentation"),
    ("03. Discovery Sessions", "04 - [ CSPR - Nubank ] - VM Security", "1wrNc1Ml9dxCIrUO922Jt5YC0X1ld3wlB1PcMnaQr5AA", "application/vnd.google-apps.presentation"),
    ("03. Discovery Sessions", "05 - [ CSPR - Nubank ] - GKE Security & Kubernetes Security", "1Jl8pPU3KWDJuOfRftM9oFm7ULOmmP7iAGn9JiJQqMxs", "application/vnd.google-apps.presentation"),
    ("03. Discovery Sessions", "06 - [ CSPR - Nubank ] - Security Operations", "19dAgHenuGO0rNwX0RJwwzp45jCodaFYINw7qzGjs8to", "application/vnd.google-apps.presentation"),
    ("03. Discovery Sessions", "07 - [ CSPR - Nubank ] - Data Security", "1QgJs983qLyXtxGqaGWI0RpnWpBQXYCuQIUqXYrR34xc", "application/vnd.google-apps.presentation"),
    ("03. Discovery Sessions", "CSPR - Discovery Sessions TEMPLATE [Stable]", "1d9kjnzo9IfJBgHnW3HTbA8zX8ywnhGK8C-vgha_wZx0", "application/vnd.google-apps.presentation"),
    ("04. Findings", "[Nubank] Review Checklist - Cloud Security Posture Review", "1r7-DA8FZtJ1TDzDLAA_7TiQnXxlj7GxiZIyUeUi8iYc", "application/vnd.google-apps.spreadsheet"),
    ("05. Executive Summary", "CSPR - CSPR Dashboard [Stable]", "19GUBpRSCzvcPQvOCV_HQnMHprrwYb-YsJtsFP2HdMvo", "application/vnd.google-apps.document"),
    ("05. Executive Summary", "CSPR - Executive Summary Template [Stable]", "1pDXfmWy_U8dbYMU2OS43FaA8Y9Af2uB3VyttswEO0S8", "application/vnd.google-apps.presentation"),
    ("05. Executive Summary", "[ Nubank - CSPR ] - Close-out - v.1 - final", "1Z6QHJpF9-6Q69jhHX7ZAwxnCPElcMDVOOqkPnJ-arbE", "application/vnd.google-apps.presentation"),
    ("05. Executive Summary", "[ Nubank - CSPR ] - Executive Summary v.1 - final", "1kpxTMHKulAxYgrKsj4eLzbqZDBmuSrYIVskpzbTULfU", "application/vnd.google-apps.presentation"),
    ("05. Executive Summary", "[Nubank-CSPR] - Recommendations Report - v.1.0 - final", "1cJfTevWc5FKHB4APzSMdxfMvH52LtU7cjFNaKAQHF5c", "application/vnd.google-apps.document"),
    ("06. Recommendations", "Recommendations Report Template - Cloud Security Posture Review [Stable][Security & Trust]", "1KF_LBExemw-C9V0arM00AhYlOnXQrGWwxFPOLpGPxeE", "application/vnd.google-apps.document"),
    ("06. Recommendations", "Review Checklist Template - Cloud Security Posture Review [Stable]", "1CyLW0JSDONm91DJHuy4-ZVkWpHXB1SEgopmP6rHN6Yg", "application/vnd.google-apps.spreadsheet"),
    ("06. Recommendations", "[Nubank] Cloud Security Recommendations Report", "1ikT1kWQCJb38TvMtQ-Y9Grc_CGPqOUvoqcQ3V741w8M", "application/vnd.google-apps.document"),
    ("[Int] User Guide", "CSPR Toolkit - User Guide [Stable]", "1EnOfV5iSUbOrK29doQdBmCOOspeGioSd7LwlU2SSc3E", "application/vnd.google-apps.document"),
]


def check_token_has_drive_scopes(token):
    if not token:
        return False
    try:
        url = f"https://www.googleapis.com/oauth2/v1/tokeninfo?access_token={token}"
        with urllib.request.urlopen(url, timeout=5) as resp:
            info = json.loads(resp.read().decode("utf-8"))
            scopes = info.get("scope", "")
            return "https://www.googleapis.com/auth/drive" in scopes
    except Exception:
        return False


def get_workspace_access_token(auto_prompt=True):
    """Obtains an OAuth token with Google Drive, Sheets, Docs, and Slides scopes."""
    for cmd in (
        ["gcloud", "auth", "application-default", "print-access-token"],
        ["gcloud", "auth", "print-access-token"],
    ):
        try:
            tok = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode("utf-8").strip()
            if check_token_has_drive_scopes(tok):
                return tok
        except Exception:
            pass

    if not auto_prompt:
        raise RuntimeError(
            "Token OAuth atual não possui escopos do Google Drive/Sheets/Docs/Slides. "
            "Execute: gcloud auth application-default login --scopes=" + ",".join(REQUIRED_SCOPES)
        )

    print("\n[!] Solicitando autorização OAuth para Google Drive / Sheets / Docs / Slides no navegador...")
    subprocess.run(
        [
            "gcloud", "auth", "application-default", "login",
            f"--scopes={','.join(REQUIRED_SCOPES)}",
        ],
        check=True,
    )
    tok = subprocess.check_output(
        ["gcloud", "auth", "application-default", "print-access-token"]
    ).decode("utf-8").strip()
    return tok


def api_request(method, url, token, body=None):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} on {method} {url}: {err_body[:400]}")


def col_idx_to_letter(idx0):
    """Converts 0-based column index to Excel/Sheets column letter (0 -> A, 15 -> P)."""
    result = ""
    n = idx0 + 1
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result


def populate_native_gsheet(spreadsheet_id, findings_by_id, token, project_id="nu-cspr-assessment"):
    """
    Populates a native Google Sheet Review Checklist (.gsheet) in <2 seconds via
    spreadsheets.values.batchUpdate without modifying any formatting, colors, or formulas.
    """
    print(f"\n>>> Lendo abas da planilha nativa Google Sheets: {spreadsheet_id} ...")
    meta = api_request(
        "GET",
        f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}?includeGridData=false",
        token,
    )
    sheets = [s["properties"]["title"] for s in meta.get("sheets", [])]
    print(f"    Abas encontradas ({len(sheets)}): {', '.join(sheets)}")

    batch_updates = []
    matched_rules_count = 0

    for sheet_title in sheets:
        encoded_range = urllib.parse.quote(f"'{sheet_title}'!A1:Z500")
        val_resp = api_request(
            "GET",
            f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{encoded_range}",
            token,
        )
        rows = val_resp.get("values", [])
        if not rows:
            continue

        # Update Instruction tab Project ID / Dataset ID / Location if applicable
        if "instruction" in sheet_title.lower():
            for r_idx, row in enumerate(rows):
                for c_idx, cell_val in enumerate(row):
                    if str(cell_val).strip() == "is-cspr":
                        col_let = col_idx_to_letter(c_idx)
                        batch_updates.append({
                            "range": f"'{sheet_title}'!{col_let}{r_idx + 1}",
                            "values": [[project_id]],
                        })

        # Locate header row containing 'Row ID(N)' and 'Automated Findings(N)'
        header_row_idx = None
        col_rowid = None
        col_autofind = None
        col_query = None

        for r_idx, row in enumerate(rows[:15]):
            normalized = [str(c).strip().lower() for c in row]
            if any("row id" in c for c in normalized) and any("automated finding" in c for c in normalized):
                header_row_idx = r_idx
                for c_idx, h_text in enumerate(normalized):
                    if "row id" in h_text:
                        col_rowid = c_idx
                    elif "automated finding" in h_text:
                        col_autofind = c_idx
                    elif "finding query" in h_text:
                        col_query = c_idx
                break

        if header_row_idx is None or col_rowid is None or col_autofind is None:
            continue

        col_autofind_letter = col_idx_to_letter(col_autofind)
        col_query_letter = col_idx_to_letter(col_query) if col_query is not None else None

        sheet_matches = 0
        for r_idx in range(header_row_idx + 1, len(rows)):
            row = rows[r_idx]
            if col_rowid >= len(row):
                continue
            rid = str(row[col_rowid]).strip()
            if rid in findings_by_id:
                f_obj = findings_by_id[rid]
                finding_text = f_obj.get("finding", "")
                sql_text = f_obj.get("sql_script", "")
                row_num_1based = r_idx + 1

                batch_updates.append({
                    "range": f"'{sheet_title}'!{col_autofind_letter}{row_num_1based}",
                    "values": [[finding_text]],
                })
                if col_query_letter and sql_text:
                    batch_updates.append({
                        "range": f"'{sheet_title}'!{col_query_letter}{row_num_1based}",
                        "values": [[sql_text]],
                    })
                sheet_matches += 1
                matched_rules_count += 1

        if sheet_matches > 0:
            print(f"    ✔ Aba [{sheet_title}]: {sheet_matches} regras mapeadas para preenchimento.")

    if batch_updates:
        print(f">>> Enviando batchUpdate com {len(batch_updates)} células para o Google Sheets ({matched_rules_count} regras)...")
        api_request(
            "POST",
            f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values:batchUpdate",
            token,
            body={
                "valueInputOption": "RAW",
                "data": batch_updates,
            },
        )
        print(f"[✔] Planilha nativa ({spreadsheet_id}) 100% populada mantendo toda a formatação original!")
    else:
        print("[i] Nenhuma célula pendente encontrada para atualização.")


def find_or_create_drive_folder(parent_id, folder_name, token):
    q = (
        f"'{parent_id}' in parents and "
        f"name = '{folder_name.replace(chr(39), chr(92)+chr(39))}' and "
        f"mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    )
    url = f"https://www.googleapis.com/drive/v3/files?q={urllib.parse.quote(q)}&fields=files(id,name)&supportsAllDrives=true&includeItemsFromAllDrives=true"
    res = api_request("GET", url, token)
    files = res.get("files", [])
    if files:
        return files[0]["id"]

    create_res = api_request(
        "POST",
        "https://www.googleapis.com/drive/v3/files?supportsAllDrives=true",
        token,
        body={
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        },
    )
    return create_res["id"]


def replace_text_in_native_doc_or_slides(doc_id, mime_type, token):
    """Uses Google Docs / Slides batchUpdate replaceAllText so zero formatting is lost."""
    replacements = [
        ("DASA", "Nubank"),
        ("dasa.com.br", "nubank.com.br"),
        ("prj-cspr-prd-05fa", "nu-cspr-assessment"),
        ("Interseguro", "Nubank"),
        ("is-cspr", "nu-cspr-assessment"),
    ]
    if mime_type == "application/vnd.google-apps.document":
        reqs = [
            {
                "replaceAllText": {
                    "containsText": {"text": old, "matchCase": False},
                    "replaceText": new,
                }
            }
            for old, new in replacements
        ]
        try:
            api_request(
                "POST",
                f"https://docs.googleapis.com/v1/documents/{doc_id}:batchUpdate",
                token,
                body={"requests": reqs},
            )
        except Exception:
            pass
    elif mime_type == "application/vnd.google-apps.presentation":
        reqs = [
            {
                "replaceAllText": {
                    "containsText": {"text": old, "matchCase": False},
                    "replaceText": new,
                }
            }
            for old, new in replacements
        ]
        try:
            api_request(
                "POST",
                f"https://slides.googleapis.com/v1/presentations/{doc_id}:batchUpdate",
                token,
                body={"requests": reqs},
            )
        except Exception:
            pass


def clone_official_templates_to_my_drive(token, findings_by_id):
    """
    Finds or creates 'My Drive > Nubank > CSPR > 01 - [Internal]' and copies all
    official Google Docs/Sheets/Slides templates as native Google Workspace documents.
    """
    print("\n>>> Localizando estrutura 'Meu Drive > Nubank > CSPR > 01 - [Internal]' no Google Drive...")
    nubank_id = find_or_create_drive_folder("root", "Nubank", token)
    cspr_id = find_or_create_drive_folder(nubank_id, "CSPR", token)
    internal_id = find_or_create_drive_folder(cspr_id, "01 - [Internal]", token)

    subfolders = {}
    for sub_name, target_name, src_doc_id, mime_type in NATIVE_TEMPLATES:
        if sub_name not in subfolders:
            subfolders[sub_name] = find_or_create_drive_folder(internal_id, sub_name, token)
        parent_folder_id = subfolders[sub_name]

        # Check if native file already exists in subfolder
        q = (
            f"'{parent_folder_id}' in parents and "
            f"name = '{target_name.replace(chr(39), chr(92)+chr(39))}' and trashed = false"
        )
        existing = api_request(
            "GET",
            f"https://www.googleapis.com/drive/v3/files?q={urllib.parse.quote(q)}&fields=files(id,name,mimeType)&supportsAllDrives=true&includeItemsFromAllDrives=true",
            token,
        ).get("files", [])

        if existing:
            new_id = existing[0]["id"]
            print(f"    [=] Já existe nativo: {sub_name}/{target_name} ({new_id})")
        else:
            copy_res = api_request(
                "POST",
                f"https://www.googleapis.com/drive/v3/files/{src_doc_id}/copy?supportsAllDrives=true",
                token,
                body={
                    "name": target_name,
                    "parents": [parent_folder_id],
                },
            )
            new_id = copy_res["id"]
            print(f"    [+] Clonado nativo ({mime_type.split('.')[-1]}): {sub_name}/{target_name} -> {new_id}")
            replace_text_in_native_doc_or_slides(new_id, mime_type, token)

        if mime_type == "application/vnd.google-apps.spreadsheet" and "Nubank" in target_name:
            populate_native_gsheet(new_id, findings_by_id, token)


def main():
    spreadsheet_id = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SPREADSHEET_ID
    findings_json = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_FINDINGS_JSON

    with open(findings_json, "r", encoding="utf-8") as f:
        rows = json.load(f)
    findings_by_id = {r["row_id"]: r for r in rows if r.get("row_id")}
    print(f"[✔] Carregadas {len(findings_by_id)} regras CSPR de {findings_json}")

    token = get_workspace_access_token(auto_prompt=True)

    # 1. Populate the user's active Google Sheet (1r7-DA8FZtJ1TDzDLAA_7TiQnXxlj7GxiZIyUeUi8iYc)
    if spreadsheet_id:
        populate_native_gsheet(spreadsheet_id, findings_by_id, token)

    # 2. Clone all official templates (.gdoc, .gsheet, .gslides) into My Drive/Nubank/CSPR/01 - [Internal]
    clone_official_templates_to_my_drive(token, findings_by_id)


if __name__ == "__main__":
    main()
