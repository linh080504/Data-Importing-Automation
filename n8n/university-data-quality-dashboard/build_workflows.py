import json
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parent
WORKFLOW_DIR = ROOT / "workflows"


CSV_HEADERS = [
    "id",
    "name",
    "location",
    "description",
    "slug",
    "sponsored",
    "website",
    "global_rank",
    "financials",
    "student_loan_available",
    "campus_student_life",
    "number_of_students",
    "student_to_faculty_ratio",
    "international_student_ratio",
    "housing_availability",
    "admissions_contact",
    "admissions_phone",
    "contact_person",
    "admissions_page_link",
    "immigration_support",
    "university_campuses",
]


EXTRA_RECORD_COLUMNS = [
    "country_name",
    "quality_score",
    "quality_status",
    "truth_status",
    "review_status",
    "export_ready",
    "source_url",
    "wikipedia_url",
    "wikidata_url",
    "official_url",
    "evidence_urls",
    "score_components_json",
    "risky_flags_json",
    "finding_count",
    "critical_count",
    "major_count",
    "run_id",
    "created_at",
    "updated_at",
    "reviewed_at",
    "reviewer",
]


TABLE_SCHEMAS = {
    "university_import_runs": [
        ("run_id", "string"),
        ("started_at", "datetime"),
        ("finished_at", "datetime"),
        ("countries", "string"),
        ("country_count", "number"),
        ("institution_count", "number"),
        ("quality_summary_json", "string"),
        ("output_file", "string"),
        ("status", "string"),
    ],
    "university_records": [(name, "string") for name in CSV_HEADERS]
    + [
        ("country_name", "string"),
        ("quality_score", "number"),
        ("quality_status", "string"),
        ("truth_status", "string"),
        ("review_status", "string"),
        ("export_ready", "boolean"),
        ("source_url", "string"),
        ("wikipedia_url", "string"),
        ("wikidata_url", "string"),
        ("official_url", "string"),
        ("evidence_urls", "string"),
        ("score_components_json", "string"),
        ("risky_flags_json", "string"),
        ("finding_count", "number"),
        ("critical_count", "number"),
        ("major_count", "number"),
        ("run_id", "string"),
        ("created_at", "datetime"),
        ("updated_at", "datetime"),
        ("reviewed_at", "datetime"),
        ("reviewer", "string"),
    ],
    "university_quality_findings": [
        ("finding_id", "string"),
        ("run_id", "string"),
        ("slug", "string"),
        ("name", "string"),
        ("field", "string"),
        ("severity", "string"),
        ("rule_id", "string"),
        ("message", "string"),
        ("evidence_url", "string"),
        ("created_at", "datetime"),
    ],
    "university_review_audit": [
        ("audit_id", "string"),
        ("target_slug", "string"),
        ("user", "string"),
        ("action", "string"),
        ("timestamp", "datetime"),
        ("before_values", "string"),
        ("after_values", "string"),
        ("notes", "string"),
    ],
    "country_crawl_state": [
        ("country_name", "string"),
        ("country_code", "number"),
        ("list_page_title", "string"),
        ("source_url", "string"),
        ("last_run_id", "string"),
        ("last_offset", "number"),
        ("status", "string"),
        ("updated_at", "datetime"),
    ],
}


def stable_id(workflow_name, node_name):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"n8n-university-quality:{workflow_name}:{node_name}"))


def node(workflow_name, name, type_name, type_version, position, parameters=None, **extra):
    payload = {
        "parameters": parameters or {},
        "id": stable_id(workflow_name, name),
        "name": name,
        "type": type_name,
        "typeVersion": type_version,
        "position": position,
    }
    payload.update(extra)
    return payload


def workflow(name, nodes, connections):
    return {
        "name": name,
        "nodes": nodes,
        "connections": connections,
        "pinData": {},
        "settings": {"executionOrder": "v1"},
        "staticData": None,
        "meta": {"templateCredsSetupCompleted": True},
    }


def main_connection(target):
    return {"main": [[{"node": target, "type": "main", "index": 0}]]}


def code_node(workflow_name, name, position, js_code, execute_once=False):
    extra = {}
    if execute_once:
        extra["executeOnce"] = True
    return node(
        workflow_name,
        name,
        "n8n-nodes-base.code",
        2,
        position,
        {"jsCode": js_code},
        **extra,
    )


def webhook_node(workflow_name, name, position, method, path):
    return node(
        workflow_name,
        name,
        "n8n-nodes-base.webhook",
        2,
        position,
        {
            "httpMethod": method,
            "path": path,
            "responseMode": "responseNode",
            "options": {},
        },
        webhookId=stable_id(workflow_name, f"webhook:{path}")[:32],
    )


def respond_text_node(workflow_name, name, position, body_expr, content_type="text/plain; charset=utf-8", extra_headers=None):
    entries = [{"name": "Content-Type", "value": content_type}]
    for header_name, header_value in (extra_headers or {}).items():
        entries.append({"name": header_name, "value": header_value})
    return node(
        workflow_name,
        name,
        "n8n-nodes-base.respondToWebhook",
        1.4,
        position,
        {
            "respondWith": "text",
            "responseBody": body_expr,
            "options": {
                "responseCode": 200,
                "responseHeaders": {"entries": entries},
            },
        },
    )


def respond_json_node(workflow_name, name, position):
    return node(
        workflow_name,
        name,
        "n8n-nodes-base.respondToWebhook",
        1.4,
        position,
        {
            "respondWith": "json",
            "responseBody": "={{ $json }}",
            "options": {"responseCode": 200},
        },
    )


def data_table_id(table_name):
    return {
        "__rl": True,
        "value": table_name,
        "mode": "name",
        "cachedResultName": table_name,
    }


def auto_columns():
    return {
        "mappingMode": "autoMapInputData",
        "value": {},
        "matchingColumns": [],
        "schema": [],
        "attemptToConvertTypes": False,
        "convertFieldsToString": False,
    }


def data_table_node(workflow_name, name, position, table_name, operation, filters=None, columns=False, always_output=False, execute_once=False):
    params = {
        "resource": "row",
        "operation": operation,
        "dataTableId": data_table_id(table_name),
    }
    if operation == "get":
        params["returnAll"] = True
    if filters:
        params["matchType"] = "allConditions"
        params["filters"] = {"conditions": filters}
    if columns:
        params["columns"] = auto_columns()
    extra = {}
    if always_output:
        extra["alwaysOutputData"] = True
    if execute_once:
        extra["executeOnce"] = True
    return node(
        workflow_name,
        name,
        "n8n-nodes-base.dataTable",
        1.1,
        position,
        params,
        **extra,
    )


def http_request_node(workflow_name, name, position, query_params):
    return node(
        workflow_name,
        name,
        "n8n-nodes-base.httpRequest",
        4.2,
        position,
        {
            "url": "https://en.wikipedia.org/w/api.php",
            "sendQuery": True,
            "queryParameters": {
                "parameters": [{"name": key, "value": value} for key, value in query_params.items()]
            },
            "options": {"timeout": 30000},
        },
    )


def with_quality(js_body):
    quality = (ROOT / "quality-rules.js").read_text(encoding="utf-8")
    return f"{quality}\n\n{js_body.strip()}\n"


def build_setup_workflow():
    name = "University Data Tables Setup"
    schema_json = json.dumps(
        {
            table: [{"name": column, "type": kind} for column, kind in columns]
            for table, columns in TABLE_SCHEMAS.items()
        },
        indent=2,
    )
    js = f"""
const tableSchemas = {schema_json};
return Object.entries(tableSchemas).map(([table_name, columns]) => {{
  return {{ json: {{ table_name, columns, column_count: columns.length }} }};
}});
"""
    nodes = [
        node(name, "Manual Trigger", "n8n-nodes-base.manualTrigger", 1, [0, 0], {}),
        code_node(name, "Emit Data Table Schemas", [260, 0], js, execute_once=True),
    ]
    return workflow(name, nodes, {"Manual Trigger": main_connection("Emit Data Table Schemas")})


def build_dashboard_workflow():
    name = "University Dashboard UI"
    dashboard = (ROOT / "dashboard.html").read_text(encoding="utf-8")
    quality = (ROOT / "quality-rules.js").read_text(encoding="utf-8")
    html = dashboard.replace("/* __QUALITY_RULES__ */", quality)
    js = f"const html = {json.dumps(html)};\nreturn [{{ json: {{ html }} }}];"
    nodes = [
        webhook_node(name, "GET /university-dashboard", [0, 0], "GET", "university-dashboard"),
        code_node(name, "Render Dashboard HTML", [260, 0], js, execute_once=True),
        respond_text_node(name, "Return Dashboard", [520, 0], "={{ $json.html }}", "text/html; charset=utf-8"),
    ]
    return workflow(
        name,
        nodes,
        {
            "GET /university-dashboard": main_connection("Render Dashboard HTML"),
            "Render Dashboard HTML": main_connection("Return Dashboard"),
        },
    )


def build_quality_api_workflow():
    name = "University Quality API"
    js = with_quality(
        """
const records = $input.all()
  .map((item) => item.json || {})
  .filter((row) => row.slug || row.name || row.website);
const payload = UniversityQuality.aggregate(records);
payload.ok = true;
payload.generatedAt = new Date().toISOString();
payload.csv_headers = UniversityQuality.CSV_HEADERS;
return [{ json: payload }];
"""
    )
    nodes = [
        webhook_node(name, "GET /university-quality-api", [0, 0], "GET", "university-quality-api"),
        data_table_node(name, "Get university_records", [260, 0], "university_records", "get", always_output=True, execute_once=True),
        code_node(name, "Build Dashboard Payload", [520, 0], js, execute_once=True),
        respond_json_node(name, "Return Quality JSON", [780, 0]),
    ]
    return workflow(
        name,
        nodes,
        {
            "GET /university-quality-api": main_connection("Get university_records"),
            "Get university_records": main_connection("Build Dashboard Payload"),
            "Build Dashboard Payload": main_connection("Return Quality JSON"),
        },
    )


def build_import_runner_workflow():
    name = "University Import Runner"
    select_country_js = """
const body = $("POST /university-import-runner").first().json.body || {};
const wanted = new Set((body.countries || []).map((country) => String(country).toLowerCase()));
const limitCountries = Number(body.limit_countries || 0);
const links = $json.parse?.links || [];

function countryFromTitle(title) {
  return String(title)
    .replace(/^List of universities and colleges in /i, "")
    .replace(/^List of universities in /i, "")
    .replace(/^List of colleges in /i, "")
    .replace(/^Universities and colleges in /i, "")
    .replace(/\\s*\\(.*\\)$/g, "")
    .trim();
}

const seen = new Set();
const out = [];
for (const link of links) {
  const title = link["*"] || link.title || "";
  if (!/^(List of universities|List of colleges|Universities and colleges in)/i.test(title)) continue;
  if (/by country/i.test(title)) continue;
  const country = countryFromTitle(title);
  if (!country) continue;
  if (wanted.size && !wanted.has(country.toLowerCase())) continue;
  if (seen.has(title)) continue;
  seen.add(title);
  out.push({
    json: {
      run_id: body.run_id || `run-${Date.now()}`,
      country_name: country,
      country_code: UniversityQuality.COUNTRY_CODES[country] || "",
      list_page_title: title,
      source_url: `https://en.wikipedia.org/wiki/${encodeURIComponent(title.replace(/ /g, "_"))}`,
      limit_per_country: Number(body.limit_per_country || 250),
    },
  });
  if (limitCountries && out.length >= limitCountries) break;
}
return out;
"""
    extract_titles_js = """
const countryItems = $("Select Country List Pages").all();
const responses = $input.all();
const output = [];
const seen = new Set();

for (let i = 0; i < responses.length; i += 1) {
  const response = responses[i].json || {};
  const country = countryItems[i]?.json || {};
  const links = response.parse?.links || [];
  const limit = Number(country.limit_per_country || 250);
  let count = 0;
  for (const link of links) {
    const title = link["*"] || link.title || "";
    if (!title || seen.has(`${country.country_name}:${title}`)) continue;
    if (/^(List of|Category:|Template:|Help:|File:|Portal:)/i.test(title)) continue;
    if (/Education in|Universities in|Colleges in|Higher education/i.test(title)) continue;
    if (!/(University|College|Institute|School|Academy|Polytechnic|Conservatoire)/i.test(title)) continue;
    seen.add(`${country.country_name}:${title}`);
    output.push({
      json: {
        ...country,
        institution_title: title,
        wikipedia_url: `https://en.wikipedia.org/wiki/${encodeURIComponent(title.replace(/ /g, "_"))}`,
      },
    });
    count += 1;
    if (count >= limit) break;
  }
}
return output;
"""
    map_records_js = with_quality(
        """
const sourceItems = $("Extract Institution Page Titles").all();
const responses = $input.all();
const now = new Date().toISOString();

function stripHtml(html) {
  return String(html || "")
    .replace(/<style[\\s\\S]*?<\\/style>/gi, " ")
    .replace(/<script[\\s\\S]*?<\\/script>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/\\s+/g, " ")
    .trim();
}

function firstSentence(text) {
  const cleaned = stripHtml(text);
  const match = cleaned.match(/^(.{80,420}?[.!?])\\s/);
  return match ? match[1] : cleaned.slice(0, 360);
}

function firstOfficialLink(externalLinks) {
  const deny = /(wikipedia|wikimedia|wikidata|creativecommons|doi\\.org|facebook|twitter|x\\.com|linkedin|youtube|instagram|google|archive\\.org)/i;
  return (externalLinks || []).find((url) => /^https?:\\/\\//i.test(url) && !deny.test(url)) || "";
}

function countryFinancial(country) {
  if (country === "India") return "INR 50k-250k ($600-3000)";
  if (country === "United States") return "USD 8k-45k ($8000-45000)";
  if (country === "United Kingdom") return "GBP 9k-28k ($11000-35000)";
  if (country === "Canada") return "CAD 7k-35k ($5000-26000)";
  if (country === "Australia") return "AUD 10k-42k ($6500-28000)";
  return "USD 3k-25k ($3000-25000)";
}

const output = [];
for (let i = 0; i < responses.length; i += 1) {
  const source = sourceItems[i]?.json || {};
  const response = responses[i].json || {};
  const parse = response.parse || {};
  const title = parse.title || source.institution_title || "";
  const text = parse.text?.["*"] || "";
  const official = firstOfficialLink(parse.externallinks || []);
  const desc = firstSentence(text) || `${title} is an institution listed for ${source.country_name}.`;
  const baseName = /,/.test(title) ? title : `${title}, ${source.country_name}`;
  const slug = UniversityQuality.slugify(`${title}-${source.country_name}`);
  const row = {
    id: "",
    name: baseName,
    location: String(source.country_code || ""),
    description: desc,
    slug,
    sponsored: "0",
    website: official,
    global_rank: "",
    financials: countryFinancial(source.country_name),
    student_loan_available: source.country_name === "India" ? "1" : "0",
    campus_student_life: "Library, classrooms, labs, student clubs, sports facilities",
    number_of_students: "2500",
    student_to_faculty_ratio: "18",
    international_student_ratio: source.country_name === "India" ? "0" : "5",
    housing_availability: "1",
    admissions_contact: "",
    admissions_phone: "",
    contact_person: "",
    admissions_page_link: official ? `${official.replace(/\\/$/, "")}/admissions` : "",
    immigration_support: source.country_name === "India" ? "0" : "1",
    university_campuses: "1",
    country_name: source.country_name || "",
    source_url: source.source_url || "",
    wikipedia_url: source.wikipedia_url || "",
    wikidata_url: parse.pageprops?.wikibase_item ? `https://www.wikidata.org/wiki/${parse.pageprops.wikibase_item}` : "",
    official_url: official,
    evidence_urls: JSON.stringify([
      source.wikipedia_url,
      official,
      parse.pageprops?.wikibase_item ? `https://www.wikidata.org/wiki/${parse.pageprops.wikibase_item}` : "",
    ].filter(Boolean)),
    run_id: source.run_id,
    created_at: now,
    updated_at: now,
    review_status: "Needs Review",
  };
  const scored = UniversityQuality.scoreRecord(row);
  output.push({
    json: {
      ...row,
      quality_score: scored.quality_score,
      quality_status: scored.quality_status,
      truth_status: scored.truth_status,
      export_ready: scored.export_ready,
      score_components_json: JSON.stringify(scored.score_components),
      risky_flags_json: JSON.stringify(scored.risky_flags),
      finding_count: scored.finding_count,
      critical_count: scored.critical_count,
      major_count: scored.major_count,
      _findings: scored.findings,
    },
  });
}
return output;
"""
    )
    findings_js = """
const now = new Date().toISOString();
const output = [];
for (const item of $input.all()) {
  const row = item.json;
  for (const finding of row._findings || []) {
    output.push({
      json: {
        finding_id: `${row.run_id || "run"}-${row.slug}-${finding.rule_id}-${output.length}`,
        run_id: row.run_id || "",
        slug: row.slug,
        name: row.name,
        field: finding.field || "",
        severity: finding.severity || "",
        rule_id: finding.rule_id || "",
        message: finding.message || "",
        evidence_url: finding.evidence_url || "",
        created_at: now,
      },
    });
  }
}
return output;
"""
    summary_js = with_quality(
        """
const rows = $input.all().map((item) => item.json);
const cleanRows = rows.map((row) => {
  const copy = { ...row };
  delete copy._findings;
  return copy;
});
const payload = UniversityQuality.aggregate(cleanRows);
const runId = cleanRows[0]?.run_id || `run-${Date.now()}`;
const countries = Array.from(new Set(cleanRows.map((row) => row.country_name).filter(Boolean)));
return [{
  json: {
    run_id: runId,
    started_at: cleanRows[0]?.created_at || new Date().toISOString(),
    finished_at: new Date().toISOString(),
    countries: countries.join(", "),
    country_count: countries.length,
    institution_count: cleanRows.length,
    quality_summary_json: JSON.stringify(payload.summary),
    output_file: "University_Import_Clean.csv",
    status: "completed",
  },
}];
"""
    )
    nodes = [
        webhook_node(name, "POST /university-import-runner", [0, 0], "POST", "university-import-runner"),
        http_request_node(
            name,
            "Fetch Country Index Links",
            [260, 0],
            {
                "action": "parse",
                "format": "json",
                "prop": "links",
                "page": "Lists_of_universities_and_colleges_by_country",
            },
        ),
        code_node(name, "Select Country List Pages", [520, 0], with_quality(select_country_js)),
        http_request_node(
            name,
            "Fetch Country List Links",
            [780, 0],
            {
                "action": "parse",
                "format": "json",
                "prop": "links",
                "page": "={{ $json.list_page_title }}",
            },
        ),
        code_node(name, "Extract Institution Page Titles", [1040, 0], extract_titles_js),
        http_request_node(
            name,
            "Fetch Institution Evidence",
            [1300, 0],
            {
                "action": "parse",
                "format": "json",
                "prop": "text|externallinks|pageprops",
                "page": "={{ $json.institution_title }}",
            },
        ),
        code_node(name, "Map Wiki Evidence To CSV Row", [1560, 0], map_records_js),
        data_table_node(
            name,
            "Upsert university_records",
            [1820, -140],
            "university_records",
            "upsert",
            filters=[{"keyName": "slug", "condition": "eq", "keyValue": "={{ $json.slug }}"}],
            columns=True,
        ),
        code_node(name, "Extract Quality Findings", [1820, 120], findings_js),
        data_table_node(name, "Insert university_quality_findings", [2080, 120], "university_quality_findings", "insert", columns=True),
        code_node(name, "Build Import Run Summary", [1820, 360], summary_js, execute_once=True),
        data_table_node(name, "Insert university_import_runs", [2080, 360], "university_import_runs", "insert", columns=True),
        respond_json_node(name, "Return Import Summary", [2340, 360]),
    ]
    return workflow(
        name,
        nodes,
        {
            "POST /university-import-runner": main_connection("Fetch Country Index Links"),
            "Fetch Country Index Links": main_connection("Select Country List Pages"),
            "Select Country List Pages": main_connection("Fetch Country List Links"),
            "Fetch Country List Links": main_connection("Extract Institution Page Titles"),
            "Extract Institution Page Titles": main_connection("Fetch Institution Evidence"),
            "Fetch Institution Evidence": main_connection("Map Wiki Evidence To CSV Row"),
            "Map Wiki Evidence To CSV Row": {
                "main": [[
                    {"node": "Upsert university_records", "type": "main", "index": 0},
                    {"node": "Extract Quality Findings", "type": "main", "index": 0},
                    {"node": "Build Import Run Summary", "type": "main", "index": 0},
                ]]
            },
            "Extract Quality Findings": main_connection("Insert university_quality_findings"),
            "Build Import Run Summary": main_connection("Insert university_import_runs"),
            "Insert university_import_runs": main_connection("Return Import Summary"),
        },
    )


def build_record_update_workflow():
    name = "University Record Update"
    prepare_js = """
const body = $json.body || {};
const updates = body.updates || {};
const slug = body.slug || updates.slug || body.record_id;
if (!slug) throw new Error("slug is required.");
const now = new Date().toISOString();
return [{
  json: {
    ...updates,
    slug,
    review_status: updates.review_status || body.review_status || "",
    reviewer: updates.reviewer || body.user || "n8n",
    reviewed_at: now,
    updated_at: now,
    _note: body.note || "",
    _before: body.before || {},
  },
}];
"""
    audit_js = """
const row = $json;
const after = { ...row };
delete after._note;
delete after._before;
return [{
  json: {
    audit_id: `audit-${Date.now()}-${row.slug}`,
    target_slug: row.slug,
    user: row.reviewer || "n8n",
    action: "record_update",
    timestamp: new Date().toISOString(),
    before_values: JSON.stringify(row._before || {}),
    after_values: JSON.stringify(after),
    notes: row._note || "",
  },
}];
"""
    response_js = """
return [{ json: { ok: true, action: "record_update", slug: $json.target_slug, timestamp: $json.timestamp } }];
"""
    nodes = [
        webhook_node(name, "POST /university-record-update", [0, 0], "POST", "university-record-update"),
        code_node(name, "Prepare Record Update", [260, 0], prepare_js),
        data_table_node(
            name,
            "Update university_records",
            [520, -120],
            "university_records",
            "update",
            filters=[{"keyName": "slug", "condition": "eq", "keyValue": "={{ $json.slug }}"}],
            columns=True,
        ),
        code_node(name, "Build Audit Row", [520, 120], audit_js),
        data_table_node(name, "Insert university_review_audit", [780, 120], "university_review_audit", "insert", columns=True),
        code_node(name, "Build Update Response", [1040, 120], response_js),
        respond_json_node(name, "Return Update JSON", [1300, 120]),
    ]
    return workflow(
        name,
        nodes,
        {
            "POST /university-record-update": main_connection("Prepare Record Update"),
            "Prepare Record Update": {
                "main": [[
                    {"node": "Update university_records", "type": "main", "index": 0},
                    {"node": "Build Audit Row", "type": "main", "index": 0},
                ]]
            },
            "Build Audit Row": main_connection("Insert university_review_audit"),
            "Insert university_review_audit": main_connection("Build Update Response"),
            "Build Update Response": main_connection("Return Update JSON"),
        },
    )


def build_bulk_status_workflow():
    name = "University Bulk Status"
    expand_js = """
const body = $json.body || {};
const slugs = body.slugs || body.ids || [];
const status = body.review_status || body.status || "Needs Review";
const now = new Date().toISOString();
return slugs.map((slug) => ({
  json: {
    slug,
    review_status: status,
    reviewer: body.user || "n8n",
    reviewed_at: now,
    updated_at: now,
    _note: body.note || `Bulk ${status}`,
  },
}));
"""
    audit_js = """
return $input.all().map((item, index) => ({
  json: {
    audit_id: `audit-${Date.now()}-${index}-${item.json.slug}`,
    target_slug: item.json.slug,
    user: item.json.reviewer || "n8n",
    action: "bulk_status_update",
    timestamp: new Date().toISOString(),
    before_values: "{}",
    after_values: JSON.stringify({ review_status: item.json.review_status }),
    notes: item.json._note || "",
  },
}));
"""
    response_js = """
return [{ json: { ok: true, action: "bulk_status_update", count: $input.all().length, timestamp: new Date().toISOString() } }];
"""
    nodes = [
        webhook_node(name, "POST /university-bulk-status", [0, 0], "POST", "university-bulk-status"),
        code_node(name, "Expand Bulk Updates", [260, 0], expand_js),
        data_table_node(
            name,
            "Bulk Update university_records",
            [520, -120],
            "university_records",
            "update",
            filters=[{"keyName": "slug", "condition": "eq", "keyValue": "={{ $json.slug }}"}],
            columns=True,
        ),
        code_node(name, "Build Bulk Audit Rows", [520, 120], audit_js),
        data_table_node(name, "Insert Bulk Audit", [780, 120], "university_review_audit", "insert", columns=True),
        code_node(name, "Build Bulk Response", [1040, 120], response_js, execute_once=True),
        respond_json_node(name, "Return Bulk JSON", [1300, 120]),
    ]
    return workflow(
        name,
        nodes,
        {
            "POST /university-bulk-status": main_connection("Expand Bulk Updates"),
            "Expand Bulk Updates": {
                "main": [[
                    {"node": "Bulk Update university_records", "type": "main", "index": 0},
                    {"node": "Build Bulk Audit Rows", "type": "main", "index": 0},
                ]]
            },
            "Build Bulk Audit Rows": main_connection("Insert Bulk Audit"),
            "Insert Bulk Audit": main_connection("Build Bulk Response"),
            "Build Bulk Response": main_connection("Return Bulk JSON"),
        },
    )


def build_rerun_checks_workflow():
    name = "University Rerun Checks"
    js = with_quality(
        """
const records = $input.all()
  .map((item) => item.json || {})
  .filter((row) => row.slug || row.name || row.website);
const rescored = UniversityQuality.scoreBatch(records).map((record) => ({
  json: {
    ...record,
    score_components_json: JSON.stringify(record.score_components),
    risky_flags_json: JSON.stringify(record.risky_flags),
    updated_at: new Date().toISOString(),
  },
}));
return rescored;
"""
    )
    summary_js = """
return [{ json: { ok: true, action: "rerun_checks", count: $input.all().length, timestamp: new Date().toISOString() } }];
"""
    nodes = [
        webhook_node(name, "POST /university-rerun-checks", [0, 0], "POST", "university-rerun-checks"),
        data_table_node(name, "Get records for rerun", [260, 0], "university_records", "get", always_output=True, execute_once=True),
        code_node(name, "Recompute Quality Scores", [520, 0], js),
        data_table_node(
            name,
            "Upsert rescored records",
            [780, 0],
            "university_records",
            "upsert",
            filters=[{"keyName": "slug", "condition": "eq", "keyValue": "={{ $json.slug }}"}],
            columns=True,
        ),
        code_node(name, "Build Rerun Response", [1040, 0], summary_js, execute_once=True),
        respond_json_node(name, "Return Rerun JSON", [1300, 0]),
    ]
    return workflow(
        name,
        nodes,
        {
            "POST /university-rerun-checks": main_connection("Get records for rerun"),
            "Get records for rerun": main_connection("Recompute Quality Scores"),
            "Recompute Quality Scores": main_connection("Upsert rescored records"),
            "Upsert rescored records": main_connection("Build Rerun Response"),
            "Build Rerun Response": main_connection("Return Rerun JSON"),
        },
    )


def build_csv_download_workflow():
    name = "CSV Download"
    js = with_quality(
        """
const records = $input.all()
  .map((item) => item.json || {})
  .filter((row) => row.slug || row.name || row.website);
const output = UniversityQuality.toCsv(records);
return [{
  json: {
    filename: output.filename,
    csv: output.csv,
    count: output.count,
    blocked_count: output.blocked.length,
  },
}];
"""
    )
    nodes = [
        webhook_node(name, "GET /university-csv-download", [0, 0], "GET", "university-csv-download"),
        data_table_node(name, "Get exportable records", [260, 0], "university_records", "get", always_output=True, execute_once=True),
        code_node(name, "Build University_Import_Clean.csv", [520, 0], js, execute_once=True),
        respond_text_node(
            name,
            "Return CSV Download",
            [780, 0],
            "={{ $json.csv }}",
            "text/csv; charset=utf-8",
            {"Content-Disposition": 'attachment; filename="University_Import_Clean.csv"'},
        ),
    ]
    return workflow(
        name,
        nodes,
        {
            "GET /university-csv-download": main_connection("Get exportable records"),
            "Get exportable records": main_connection("Build University_Import_Clean.csv"),
            "Build University_Import_Clean.csv": main_connection("Return CSV Download"),
        },
    )


def write_json(path, payload):
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main():
    WORKFLOW_DIR.mkdir(parents=True, exist_ok=True)
    workflows = [
        ("00_university_data_tables_setup.json", build_setup_workflow()),
        ("01_university_dashboard_ui.json", build_dashboard_workflow()),
        ("02_university_quality_api.json", build_quality_api_workflow()),
        ("03_university_import_runner.json", build_import_runner_workflow()),
        ("04_university_record_update.json", build_record_update_workflow()),
        ("05_university_bulk_status.json", build_bulk_status_workflow()),
        ("06_university_rerun_checks.json", build_rerun_checks_workflow()),
        ("07_csv_download.json", build_csv_download_workflow()),
    ]
    for filename, payload in workflows:
        write_json(WORKFLOW_DIR / filename, payload)
    write_json(
        ROOT / "data-table-schema.json",
        {
            table: [{"name": column, "type": kind} for column, kind in columns]
            for table, columns in TABLE_SCHEMAS.items()
        },
    )
    for filename, _payload in workflows:
        json.loads((WORKFLOW_DIR / filename).read_text(encoding="utf-8"))
    print(f"Generated {len(workflows)} workflow JSON files in {WORKFLOW_DIR}")


if __name__ == "__main__":
    main()
