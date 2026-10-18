//! Proxy to the optional on-demand document worker; no scraping in Actix.
use actix_web::{web, HttpRequest, HttpResponse};
use std::time::Duration;

async fn proxy(req: HttpRequest) -> HttpResponse {
    let code = req.match_info().get("code").unwrap_or("");
    let prefix = "2027DPWH-Proposal-";
    if !code.starts_with(prefix) || code.len() != prefix.len() + 5
        || !code[prefix.len()..].bytes().all(|c| c.is_ascii_digit()) {
        return HttpResponse::BadRequest().json(serde_json::json!({"error":"Invalid project code"}));
    }
    let tail = req.match_info().get("tail").unwrap_or("");
    if tail.split('/').any(|p| p == ".." || p == ".") || tail.contains('\\') {
        return HttpResponse::BadRequest().finish();
    }
    let suffix = if tail.is_empty() { String::new() } else { format!("/{}", tail) };
    let base = std::env::var("DOCUMENT_SERVICE_URL").unwrap_or_else(|_| "http://127.0.0.1:8879".to_string());
    let url = format!("{}/projects/{}{}", base.trim_end_matches('/'), code, suffix);
    let client = match reqwest::Client::builder().timeout(Duration::from_secs(60)).build() {
        Ok(c) => c, Err(_) => return HttpResponse::ServiceUnavailable().finish(),
    };
    let response = if req.method() == actix_web::http::Method::POST {
        client.post(url).send().await
    } else { client.get(url).send().await };
    match response {
        Ok(response) => {
            let status = actix_web::http::StatusCode::from_u16(response.status().as_u16())
                .unwrap_or(actix_web::http::StatusCode::BAD_GATEWAY);
            let content_type = response.headers().get("content-type").and_then(|v| v.to_str().ok()).unwrap_or("application/json").to_string();
            match response.bytes().await {
                Ok(bytes) => HttpResponse::build(status).content_type(content_type).body(bytes),
                Err(_) => HttpResponse::BadGateway().json(serde_json::json!({"error":"Document response interrupted"})),
            }
        },
        Err(_) => HttpResponse::ServiceUnavailable().json(serde_json::json!({"error":"Document processing worker unavailable; original BetterGov source links remain available"})),
    }
}
pub fn configure(config: &mut web::ServiceConfig) {
    config.service(web::resource("/api/nep-documents/{code}").route(web::get().to(proxy)))
        .service(web::resource("/api/nep-documents/{code}/{tail:.*}")
            .route(web::get().to(proxy)).route(web::post().to(proxy)));
}
