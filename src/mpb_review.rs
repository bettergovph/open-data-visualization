//! Hash-gated manual annotations for scanned MPB program-of-work rows.
use actix_web::{web, HttpResponse};
use serde::Deserialize;
use serde_json::{json, Map, Value};
use std::fs;
use std::path::{Component, Path, PathBuf};
use std::sync::Mutex;

const AUTH_MARKERS: &str = ".connectivity-admin-hashes";
const ANNOTATIONS: &str = ".mpb-review-annotations.json";
const PROJECT_PREFIX: &str = "2027DPWH-Proposal-";
static ANNOTATION_LOCK: Mutex<()> = Mutex::new(());

#[derive(Deserialize)]
struct AuthQuery {
    hash: String,
}

#[derive(Deserialize)]
struct SaveAnnotation {
    project_code: String,
    row_id: String,
    key_values: std::collections::HashMap<String, String>,
}

fn cache_root() -> PathBuf {
    std::env::var_os("DPWH_DOCUMENT_CACHE")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("analysis/data_sources/dpwh_project_documents/on_demand"))
}

fn authorized(hash: &str) -> bool {
    if hash.len() != 64 || !hash.bytes().all(|b| b.is_ascii_hexdigit()) {
        return false;
    }
    Path::new(AUTH_MARKERS)
        .join(hash.to_ascii_lowercase())
        .is_file()
}

fn denied() -> HttpResponse {
    HttpResponse::Forbidden().json(json!({"error": "Access denied"}))
}

fn read_json(path: &Path) -> Option<Value> {
    fs::read(path)
        .ok()
        .and_then(|bytes| serde_json::from_slice(&bytes).ok())
}

fn is_mpb(metadata: &Value) -> bool {
    ["projectName", "pap1", "pap2", "pap3"]
        .iter()
        .filter_map(|key| metadata.get(key).and_then(Value::as_str))
        .map(str::to_ascii_lowercase)
        .any(|text| {
            text.contains("multi-purpose building")
                || text.contains("multipurpose building")
                || text.contains("multi purpose building")
                || text.contains("multi-purpose buildings")
                || text.contains("multipurpose buildings")
                || text
                    .split(|c: char| !c.is_ascii_alphanumeric())
                    .any(|word| word == "mpb")
        })
}

fn valid_project_code(code: &str) -> bool {
    code.len() == PROJECT_PREFIX.len() + 5
        && code.starts_with(PROJECT_PREFIX)
        && code[PROJECT_PREFIX.len()..]
            .bytes()
            .all(|b| b.is_ascii_digit())
}

fn safe_asset_path(project_dir: &Path, asset: &str) -> Option<PathBuf> {
    let relative = Path::new(asset);
    if relative
        .components()
        .any(|c| !matches!(c, Component::Normal(_)))
    {
        return None;
    }
    let assets = project_dir.join("assets").canonicalize().ok()?;
    let candidate = assets.join(relative).canonicalize().ok()?;
    candidate.starts_with(&assets).then_some(candidate)
}

fn cell_string(value: &Value) -> Option<String> {
    match value {
        Value::String(text) => Some(text.clone()),
        Value::Number(number) => Some(number.to_string()),
        Value::Bool(boolean) => Some(boolean.to_string()),
        _ => None,
    }
}

fn allocation_pesos(metadata: &Value) -> Option<f64> {
    fn number(value: &Value) -> Option<f64> {
        value.as_f64().or_else(|| {
            value
                .as_str()
                .and_then(|text| text.replace(',', "").parse().ok())
        })
    }
    metadata
        .get("nepAllocationPesos")
        .or_else(|| metadata.get("allocationPesos"))
        .and_then(number)
        .or_else(|| metadata.get("amount").and_then(number).map(|amount| amount * 1000.0))
}

fn annotations() -> Result<Value, HttpResponse> {
    let path = Path::new(ANNOTATIONS);
    let Some(value) = read_json(path) else {
        if path.exists() {
            return Err(HttpResponse::InternalServerError()
                .json(json!({"error": "MPB review database is unreadable"})));
        }
        return Ok(json!({"schemaVersion": 1, "annotations": {}}));
    };
    if value
        .get("annotations")
        .and_then(Value::as_object)
        .is_some()
    {
        Ok(value)
    } else {
        Err(HttpResponse::InternalServerError()
            .json(json!({"error": "MPB review database has an invalid structure"})))
    }
}

fn load_project(code: &str) -> Result<Option<Value>, HttpResponse> {
    if !valid_project_code(code) {
        return Ok(None);
    }
    let project_dir = cache_root().join(code);
    let Some(metadata) = read_json(&project_dir.join("metadata.json")) else {
        return Ok(None);
    };
    if !is_mpb(&metadata) {
        return Ok(None);
    }
    let Some(result) = read_json(&project_dir.join("result.json")) else {
        return Ok(None);
    };
    let Some(pow_document) =
        result
            .get("documents")
            .and_then(Value::as_array)
            .and_then(|documents| {
                documents
                    .iter()
                    .find(|doc| doc.get("kind").and_then(Value::as_str) == Some("pow"))
            })
    else {
        return Ok(None);
    };
    let Some(pow) = pow_document.get("pow") else {
        return Ok(None);
    };
    let sha = pow
        .get("pdfSha256")
        .and_then(Value::as_str)
        .unwrap_or("unknown");
    let asset = pow_document
        .get("pdfAsset")
        .and_then(Value::as_str)
        .unwrap_or("");
    let Some(pdf_path) = safe_asset_path(&project_dir, asset) else {
        return Ok(None);
    };
    let Some(parent) = pdf_path.parent() else {
        return Ok(None);
    };
    let Some(tables) = read_json(&parent.join("pow-native-tables.json")) else {
        return Ok(None);
    };

    let saved = annotations()?;
    let saved_rows = saved.get("annotations").and_then(Value::as_object).unwrap();
    let mut rows = Vec::new();
    if let Some(tables) = tables.as_array() {
        for (table_index, table) in tables.iter().enumerate() {
            let page = table.get("page").and_then(Value::as_u64).unwrap_or(0);
            let Some(table_rows) = table.get("cells").and_then(Value::as_array) else {
                continue;
            };
            for (row_index, cells) in table_rows.iter().enumerate() {
                let values = cells
                    .as_array()
                    .map(|cells| cells.iter().filter_map(cell_string).collect::<Vec<_>>())
                    .unwrap_or_default();
                let raw_text = values
                    .iter()
                    .map(|cell| cell.trim())
                    .filter(|cell| !cell.is_empty())
                    .collect::<Vec<_>>()
                    .join(" | ");
                if raw_text.is_empty() {
                    continue;
                }
                let row_id = format!("{code}:{sha}:{page}:{table_index}:{row_index}");
                let saved_entry = saved_rows.get(&row_id);
                let key_values = saved_entry
                    .and_then(|entry| entry.get("keyValues"))
                    .cloned()
                    .or_else(|| saved_entry.and_then(|entry| entry.get("note")).and_then(Value::as_str).map(|note| json!({"note": note})))
                    .unwrap_or_else(|| json!({}));
                rows.push(json!({
                    "rowId": row_id,
                    "page": page,
                    "table": table_index + 1,
                    "row": row_index + 1,
                    "rawText": raw_text,
                    "keyValues": key_values,
                }));
            }
        }
    }
    let document = pow_document.get("metadata").unwrap_or(&Value::Null);
    let project = json!({
        "code": code,
        "name": metadata.get("projectName").and_then(Value::as_str).unwrap_or(""),
        "allocationPesos": allocation_pesos(&metadata),
        "office": metadata.get("office").and_then(Value::as_str).unwrap_or(""),
        "region": metadata.get("region").and_then(Value::as_str).unwrap_or(""),
        "pap3": metadata.get("pap3").and_then(Value::as_str).unwrap_or(""),
        "powUrl": document.get("url").and_then(Value::as_str).unwrap_or(""),
        "powStatus": pow.get("status").and_then(Value::as_str).unwrap_or("unknown"),
        "pageCount": pow.get("pageCount").and_then(Value::as_u64).unwrap_or(0),
        "rows": rows,
    });
    Ok(Some(project))
}

async fn list_projects(query: web::Query<AuthQuery>) -> HttpResponse {
    if !authorized(&query.hash) {
        return denied();
    }
    let root = cache_root();
    let entries = match fs::read_dir(&root) {
        Ok(entries) => entries,
        Err(_) => {
            return HttpResponse::ServiceUnavailable()
                .json(json!({"error": "POW document cache is unavailable"}))
        }
    };
    let mut projects = Vec::new();
    for entry in entries.flatten() {
        let code = entry.file_name().to_string_lossy().to_string();
        if !valid_project_code(&code) {
            continue;
        }
        match load_project(&code) {
            Ok(Some(project)) => {
                let rows = project
                    .get("rows")
                    .and_then(Value::as_array)
                    .map(Vec::len)
                    .unwrap_or(0);
                projects.push(json!({
                    "code": code,
                    "name": project.get("name"),
                    "allocationPesos": project.get("allocationPesos"),
                    "office": project.get("office"),
                    "region": project.get("region"),
                    "pageCount": project.get("pageCount"),
                    "rowCount": rows,
                    "powStatus": project.get("powStatus"),
                }));
            }
            Ok(None) => {}
            Err(error) => return error,
        }
    }
    projects.sort_by(|a, b| {
        b.get("allocationPesos")
            .and_then(Value::as_f64)
            .partial_cmp(&a.get("allocationPesos").and_then(Value::as_f64))
            .unwrap_or(std::cmp::Ordering::Equal)
            .then_with(|| {
                a.get("code")
                    .and_then(Value::as_str)
                    .cmp(&b.get("code").and_then(Value::as_str))
            })
    });
    HttpResponse::Ok()
        .insert_header(("Cache-Control", "no-store"))
        .json(json!({"projects": projects}))
}

async fn get_project(path: web::Path<String>, query: web::Query<AuthQuery>) -> HttpResponse {
    if !authorized(&query.hash) {
        return denied();
    }
    match load_project(&path.into_inner()) {
        Ok(Some(project)) => HttpResponse::Ok()
            .insert_header(("Cache-Control", "no-store"))
            .json(project),
        Ok(None) => HttpResponse::NotFound().json(json!({"error": "Scanned MPB POW not found"})),
        Err(error) => error,
    }
}

async fn save_annotation(
    query: web::Query<AuthQuery>,
    input: web::Json<SaveAnnotation>,
) -> HttpResponse {
    if !authorized(&query.hash) {
        return denied();
    }
    if input.key_values.len() > 100
        || input.row_id.len() > 300
        || !valid_project_code(&input.project_code)
        || input.key_values.iter().any(|(key, value)| {
            key.trim().is_empty() || key.len() > 200 || value.len() > 20_000
        })
    {
        return HttpResponse::BadRequest().json(json!({"error": "Invalid annotation fields"}));
    }
    let project = match load_project(&input.project_code) {
        Ok(Some(project)) => project,
        Ok(None) => {
            return HttpResponse::NotFound().json(json!({"error": "Scanned MPB POW not found"}))
        }
        Err(error) => return error,
    };
    let row_exists = project
        .get("rows")
        .and_then(Value::as_array)
        .is_some_and(|rows| {
            rows.iter()
                .any(|row| row.get("rowId").and_then(Value::as_str) == Some(&input.row_id))
        });
    if !row_exists {
        return HttpResponse::NotFound().json(json!({"error": "Scanned row not found"}));
    }

    let _guard = match ANNOTATION_LOCK.lock() {
        Ok(guard) => guard,
        Err(_) => return HttpResponse::InternalServerError().finish(),
    };
    let mut database = match annotations() {
        Ok(data) => data,
        Err(error) => return error,
    };
    let annotations = database
        .get_mut("annotations")
        .and_then(Value::as_object_mut)
        .unwrap();
    if input.key_values.is_empty() {
        annotations.remove(&input.row_id);
    } else {
        let mut entry = Map::new();
        entry.insert("projectCode".to_string(), json!(input.project_code));
        entry.insert(
            "rawText".to_string(),
            json!(project["rows"]
                .as_array()
                .unwrap()
                .iter()
                .find(|row| row["rowId"] == input.row_id)
                .and_then(|row| row["rawText"].as_str())
                .unwrap_or("")),
        );
        let key_values = input.key_values.iter()
            .map(|(key, value)| (key.trim().to_string(), Value::String(value.trim().to_string())))
            .collect::<Map<String, Value>>();
        entry.insert("keyValues".to_string(), Value::Object(key_values));
        entry.insert(
            "updatedAtEpochSeconds".to_string(),
            json!(current_epoch_seconds()),
        );
        annotations.insert(input.row_id.clone(), Value::Object(entry));
    }
    let temp = Path::new(ANNOTATIONS).with_extension("json.tmp");
    let bytes = match serde_json::to_vec_pretty(&database) {
        Ok(bytes) => bytes,
        Err(_) => {
            return HttpResponse::InternalServerError()
                .json(json!({"error": "Could not serialize MPB review database"}))
        }
    };
    if fs::write(&temp, bytes).is_err() {
        return HttpResponse::InternalServerError()
            .json(json!({"error": "Could not write MPB review database"}));
    }
    if fs::rename(&temp, ANNOTATIONS).is_err() {
        return HttpResponse::InternalServerError()
            .json(json!({"error": "Could not replace MPB review database"}));
    }
    HttpResponse::Ok()
        .insert_header(("Cache-Control", "no-store"))
        .json(json!({"saved": true, "rowId": input.row_id}))
}

fn current_epoch_seconds() -> u64 {
    // The repository avoids an extra time dependency; SystemTime yields a UTC epoch marker.
    use std::time::{SystemTime, UNIX_EPOCH};
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

pub fn configure(config: &mut web::ServiceConfig) {
    config
        .service(web::resource("/projects").route(web::get().to(list_projects)))
        .service(web::resource("/projects/{code}").route(web::get().to(get_project)))
        .service(web::resource("/annotations").route(web::post().to(save_annotation)));
}
