// BetterGovPH Open Data Visualization - Standalone Application

use actix_files as fs;
use actix_cors::Cors;
use actix_web::{web, App, Error as ActixError, HttpRequest, HttpResponse, HttpServer};
use tera::{Tera, Context};

mod utils;
use utils::*;
use serde::Deserialize;
use std::path::Path;

// Route handlers

// BetterGovPH Homepage
async fn favicon() -> Result<fs::NamedFile, ActixError> {
    fs::NamedFile::open("static/favicon.ico").map_err(|e| actix_web::error::ErrorNotFound(e))
}
async fn robots() -> Result<fs::NamedFile, ActixError> {
    fs::NamedFile::open("static/robots.txt").map_err(|e| actix_web::error::ErrorNotFound(e))
}
async fn home(req: HttpRequest) -> Result<HttpResponse, ActixError> {
    let tera = Tera::new("templates/**/*").map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    let mut context = Context::new();
    
    add_frontend_env_to_context(&mut context);
    
    context.insert("title", "BetterGovPH Data Visualizations");
    context.insert("company_name", "BetterGovPH");
    context.insert("platform", "BetterGovPH");
    context.insert("SITE_NAME", "BetterGovPH Data Visualizations");
    context.insert("SITE_URL", "https://visualizations.bettergov.ph");
    
    let template_name = if is_mobile(&req) {
        "mobile/visualizations_home.html"
    } else {
        "visualizations_home.html"
    };
    
    let rendered = tera.render(template_name, &context).map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    Ok(HttpResponse::Ok().content_type("text/html").body(rendered))
}

// Budget Analysis Page
async fn budget(req: HttpRequest) -> Result<HttpResponse, ActixError> {
    let tera = Tera::new("templates/**/*").map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    let mut context = Context::new();
    
    add_frontend_env_to_context(&mut context);
    
    context.insert("title", "Budget Analysis - BetterGovPH");
    context.insert("company_name", "BetterGovPH");
    context.insert("platform", "BetterGovPH");
    context.insert("SITE_NAME", "BetterGovPH Data Visualizations");
    context.insert("SITE_URL", "https://visualizations.bettergov.ph");
    
    let template_name = if is_mobile(&req) {
        "mobile/budget.html"
    } else {
        "budget.html"
    };
    
    let rendered = tera.render(template_name, &context).map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    Ok(HttpResponse::Ok().content_type("text/html").body(rendered))
}

// Flood Control Projects Page
async fn flood(req: HttpRequest) -> Result<HttpResponse, ActixError> {
    let tera = Tera::new("templates/**/*").map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    let mut context = Context::new();
    
    add_frontend_env_to_context(&mut context);
    
    context.insert("title", "Flood Control Projects - BetterGovPH");
    context.insert("company_name", "BetterGovPH");
    context.insert("platform", "BetterGovPH");
    context.insert("SITE_NAME", "BetterGovPH Data Visualizations");
    context.insert("SITE_URL", "https://visualizations.bettergov.ph");
    
    let template_name = if is_mobile(&req) {
        "mobile/flood.html"
    } else {
        "flood.html"
    };
    
    let rendered = tera.render(template_name, &context).map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    Ok(HttpResponse::Ok().content_type("text/html").body(rendered))
}

// DIME Infrastructure Projects Page
async fn dime(req: HttpRequest) -> Result<HttpResponse, ActixError> {
    let tera = Tera::new("templates/**/*").map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    let mut context = Context::new();
    
    add_frontend_env_to_context(&mut context);
    
    context.insert("title", "DIME Infrastructure Projects - BetterGovPH");
    context.insert("company_name", "BetterGovPH");
    context.insert("platform", "BetterGovPH");
    context.insert("SITE_NAME", "BetterGovPH Data Visualizations");
    context.insert("SITE_URL", "https://visualizations.bettergov.ph");
    
    let template_name = if is_mobile(&req) {
        "mobile/dime.html"
    } else {
        "dime.html"
    };
    
    let rendered = tera.render(template_name, &context).map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    Ok(HttpResponse::Ok().content_type("text/html").body(rendered))
}

// NEP Analysis Page
async fn nep(req: HttpRequest) -> Result<HttpResponse, ActixError> {
    let tera = Tera::new("templates/**/*").map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    let mut context = Context::new();

    add_frontend_env_to_context(&mut context);

    context.insert("title", "NEP Analysis - BetterGovPH");
    context.insert("company_name", "BetterGovPH");
    context.insert("platform", "BetterGovPH");
    context.insert("SITE_NAME", "BetterGovPH Data Visualizations");
    context.insert("SITE_URL", "https://visualizations.bettergov.ph");

    let template_name = if is_mobile(&req) {
        "mobile/nep.html"
    } else {
        "nep.html"
    };

    let rendered = tera.render(template_name, &context).map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    Ok(HttpResponse::Ok().content_type("text/html").body(rendered))
}

// Interactive Map Page
async fn map(req: HttpRequest) -> Result<HttpResponse, ActixError> {
    let tera = Tera::new("templates/**/*").map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    let mut context = Context::new();

    add_frontend_env_to_context(&mut context);

    context.insert("title", "Interactive Map - BetterGovPH");
    context.insert("company_name", "BetterGovPH");
    context.insert("platform", "BetterGovPH");
    context.insert("SITE_NAME", "BetterGovPH Data Visualizations");
    context.insert("SITE_URL", "https://visualizations.bettergov.ph");

    let template_name = if is_mobile(&req) {
        "mobile/map.html"
    } else {
        "map.html"
    };

    let rendered = tera.render(template_name, &context).map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    Ok(HttpResponse::Ok().content_type("text/html").body(rendered))
}

// Multi-Purpose Buildings Page
async fn mpb(req: HttpRequest) -> Result<HttpResponse, ActixError> {
    let tera = Tera::new("templates/**/*").map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    let mut context = Context::new();

    add_frontend_env_to_context(&mut context);

    context.insert("title", "Multi-Purpose Buildings - BetterGovPH");
    context.insert("company_name", "BetterGovPH");
    context.insert("platform", "BetterGovPH");
    context.insert("SITE_NAME", "BetterGovPH Data Visualizations");
    context.insert("SITE_URL", "https://visualizations.bettergov.ph");

    let template_name = if is_mobile(&req) {
        "mobile/mpb.html"
    } else {
        "mpb.html"
    };

    let rendered = tera.render(template_name, &context).map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    Ok(HttpResponse::Ok().content_type("text/html").body(rendered))
}


// Budget-NEP Correlation Page
async fn budget_nep_correlation(req: HttpRequest) -> Result<HttpResponse, ActixError> {
    let tera = Tera::new("templates/**/*").map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    let mut context = Context::new();

    add_frontend_env_to_context(&mut context);

    context.insert("title", "Budget-NEP Correlation - BetterGovPH");
    context.insert("company_name", "BetterGovPH");
    context.insert("platform", "BetterGovPH");
    context.insert("SITE_NAME", "BetterGovPH Data Visualizations");
    context.insert("SITE_URL", "https://visualizations.bettergov.ph");

    let template_name = if is_mobile(&req) {
        "mobile/budget_nep_correlation.html"
    } else {
        "budget_nep_correlation.html"
    };

    let rendered = tera.render(template_name, &context).map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    Ok(HttpResponse::Ok().content_type("text/html").body(rendered))
}

// Budget-Flood Correlation Page
async fn budget_flood_correlation(req: HttpRequest) -> Result<HttpResponse, ActixError> {
    let tera = Tera::new("templates/**/*").map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    let mut context = Context::new();

    add_frontend_env_to_context(&mut context);

    context.insert("title", "Budget-Flood Correlation - BetterGovPH");
    context.insert("company_name", "BetterGovPH");
    context.insert("platform", "BetterGovPH");
    context.insert("SITE_NAME", "BetterGovPH Data Visualizations");
    context.insert("SITE_URL", "https://visualizations.bettergov.ph");

    let template_name = if is_mobile(&req) {
        "mobile/budget_flood_correlation.html"
    } else {
        "budget_flood_correlation.html"
    };

    let rendered = tera.render(template_name, &context).map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    Ok(HttpResponse::Ok().content_type("text/html").body(rendered))
}

// Flood-DIME Correlation Page
async fn flood_dime_correlation(req: HttpRequest) -> Result<HttpResponse, ActixError> {
    let tera = Tera::new("templates/**/*").map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    let mut context = Context::new();

    add_frontend_env_to_context(&mut context);

    context.insert("title", "Flood-DIME Correlation - BetterGovPH");
    context.insert("company_name", "BetterGovPH");
    context.insert("platform", "BetterGovPH");
    context.insert("SITE_NAME", "BetterGovPH Data Visualizations");
    context.insert("SITE_URL", "https://visualizations.bettergov.ph");

    let template_name = if is_mobile(&req) {
        "mobile/flood_dime_correlation.html"
    } else {
        "flood_dime_correlation.html"
    };

    let rendered = tera.render(template_name, &context).map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    Ok(HttpResponse::Ok().content_type("text/html").body(rendered))
}

// Contractor-District Correlation Page
async fn contractor_district_correlation(req: HttpRequest) -> Result<HttpResponse, ActixError> {
    let tera = Tera::new("templates/**/*").map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    let mut context = Context::new();

    add_frontend_env_to_context(&mut context);

    context.insert("title", "Contractor-District Correlation Analysis - BetterGovPH");
    context.insert("company_name", "BetterGovPH");
    context.insert("platform", "BetterGovPH");
    context.insert("SITE_NAME", "BetterGovPH Data Visualizations");
    context.insert("SITE_URL", "https://visualizations.bettergov.ph");

    let template_name = if is_mobile(&req) {
        "mobile/contractor_district_correlation.html"
    } else {
        "contractor_district_correlation.html"
    };

    let rendered = tera.render(template_name, &context).map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    Ok(HttpResponse::Ok().content_type("text/html").body(rendered))
}

// Dynasty-Poverty Correlation Page
async fn dynasty_poverty_correlation(_req: HttpRequest) -> Result<HttpResponse, ActixError> {
    let tera = Tera::new("templates/**/*").map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    let mut context = Context::new();

    add_frontend_env_to_context(&mut context);

    context.insert("title", "Dynasty-Poverty Correlation Analysis - BetterGovPH");
    context.insert("company_name", "BetterGovPH");
    context.insert("platform", "BetterGovPH");
    context.insert("SITE_NAME", "BetterGovPH Data Visualizations");
    context.insert("SITE_URL", "https://visualizations.bettergov.ph");

    let template_name = "dynasty_poverty_correlation.html";

    let rendered = tera.render(template_name, &context).map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    Ok(HttpResponse::Ok().content_type("text/html").body(rendered))
}

// Contractors Page
async fn contractors(req: HttpRequest) -> Result<HttpResponse, ActixError> {
    let tera = Tera::new("templates/**/*").map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    let mut context = Context::new();

    add_frontend_env_to_context(&mut context);

    context.insert("title", "SEC Contractors - BetterGovPH");
    context.insert("company_name", "BetterGovPH");
    context.insert("platform", "BetterGovPH");
    context.insert("SITE_NAME", "BetterGovPH Data Visualizations");
    context.insert("SITE_URL", "https://visualizations.bettergov.ph");

    let template_name = if is_mobile(&req) {
        "mobile/philgeps.html"
    } else {
        "philgeps.html"
    };

    let rendered = tera.render(template_name, &context).map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    Ok(HttpResponse::Ok().content_type("text/html").body(rendered))
}



// Circles Page (unpublished - data quality analysis)
async fn circles(_req: HttpRequest) -> Result<HttpResponse, ActixError> {
    let tera = Tera::new("templates/**/*").map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    let mut context = Context::new();

    add_frontend_env_to_context(&mut context);

    context.insert("title", "Coordinate Circles - Data Quality Analysis");
    context.insert("company_name", "BetterGovPH");
    context.insert("platform", "BetterGovPH");
    context.insert("SITE_NAME", "BetterGovPH Data Visualizations");
    context.insert("SITE_URL", "https://visualizations.bettergov.ph");

    let template_name = "circles.html";

    let rendered = tera.render(template_name, &context).map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    Ok(HttpResponse::Ok().content_type("text/html").body(rendered))
}

// EOGO Corruption Risk Analysis Page
async fn eogo(_req: HttpRequest) -> Result<HttpResponse, ActixError> {
    let tera = Tera::new("templates/**/*").map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    let mut context = Context::new();

    add_frontend_env_to_context(&mut context);

    context.insert("title", "EOGO Corruption Risk Analysis - BetterGovPH");
    context.insert("company_name", "BetterGovPH");
    context.insert("platform", "BetterGovPH");
    context.insert("SITE_NAME", "BetterGovPH Data Visualizations");
    context.insert("SITE_URL", "https://visualizations.bettergov.ph");

    let template_name = "eogo.html";

    let rendered = tera.render(template_name, &context).map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    Ok(HttpResponse::Ok().content_type("text/html").body(rendered))
}

// Sources Page
async fn sources(_req: HttpRequest) -> Result<HttpResponse, ActixError> {
    let tera = Tera::new("templates/**/*").map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    let mut context = Context::new();

    add_frontend_env_to_context(&mut context);

    context.insert("title", "Data Sources - BetterGovPH");
    context.insert("company_name", "BetterGovPH");
    context.insert("platform", "BetterGovPH");
    context.insert("SITE_NAME", "BetterGovPH Data Visualizations");
    context.insert("SITE_URL", "https://visualizations.bettergov.ph");

    let template_name = if is_mobile(&_req) {
        "mobile/sources.html"
    } else {
        "sources.html"
    };

    let rendered = tera.render(template_name, &context).map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    Ok(HttpResponse::Ok().content_type("text/html").body(rendered))
}

// Political Dynasties Page
async fn dynasty(req: HttpRequest) -> Result<HttpResponse, ActixError> {
    let tera = Tera::new("templates/**/*").map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    let mut context = Context::new();

    add_frontend_env_to_context(&mut context);

    context.insert("title", "Political Dynasties - BetterGovPH");
    context.insert("company_name", "BetterGovPH");
    context.insert("platform", "BetterGovPH");
    context.insert("SITE_NAME", "BetterGovPH Data Visualizations");
    context.insert("SITE_URL", "https://visualizations.bettergov.ph");

    let template_name = if is_mobile(&req) {
        "mobile/dynasty.html"
    } else {
        "dynasty.html"
    };

    let rendered = tera.render(template_name, &context).map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    Ok(HttpResponse::Ok().content_type("text/html").body(rendered))
}

// Dynasty Projects Page
async fn dynasty_projects(_req: HttpRequest) -> Result<HttpResponse, ActixError> {
    let tera = Tera::new("templates/**/*").map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    let mut context = Context::new();

    add_frontend_env_to_context(&mut context);

    context.insert("title", "Dynasty Projects - BetterGovPH");
    context.insert("company_name", "BetterGovPH");
    context.insert("platform", "BetterGovPH");
    context.insert("SITE_NAME", "BetterGovPH Data Visualizations");
    context.insert("SITE_URL", "https://visualizations.bettergov.ph");

    let template_name = "dynasty-projects.html";

    let rendered = tera.render(template_name, &context).map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    Ok(HttpResponse::Ok().content_type("text/html").body(rendered))
}

// Zaldy DPWH Projects Page
async fn zaldy(_req: HttpRequest) -> Result<HttpResponse, ActixError> {
    let tera = Tera::new("templates/**/*").map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    let mut context = Context::new();

    add_frontend_env_to_context(&mut context);

    context.insert("title", "DPWH Projects Database Tags - BetterGovPH");
    context.insert("company_name", "BetterGovPH");
    context.insert("platform", "BetterGovPH");
    context.insert("SITE_NAME", "BetterGovPH Data Visualizations");
    context.insert("SITE_URL", "https://visualizations.bettergov.ph");

    let template_name = "zaldy.html";

    let rendered = tera.render(template_name, &context).map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    Ok(HttpResponse::Ok().content_type("text/html").body(rendered))
}

// Zarah Companies Investigation Page
async fn zarah(_req: HttpRequest) -> Result<HttpResponse, ActixError> {
    let tera = Tera::new("templates/**/*").map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    let mut context = Context::new();

    add_frontend_env_to_context(&mut context);

    context.insert("title", "Zarah Companies Investigation - BetterGovPH");
    context.insert("company_name", "BetterGovPH");
    context.insert("platform", "BetterGovPH");
    context.insert("SITE_NAME", "BetterGovPH Data Visualizations");
    context.insert("SITE_URL", "https://visualizations.bettergov.ph");

    let template_name = "zarah.html";

    let rendered = tera.render(template_name, &context).map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    Ok(HttpResponse::Ok().content_type("text/html").body(rendered))
}

// Integrated Projects Page
async fn integrated(req: HttpRequest) -> Result<HttpResponse, ActixError> {
    let tera = Tera::new("templates/**/*").map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    let mut context = Context::new();

    add_frontend_env_to_context(&mut context);

    context.insert("title", "Integrated Projects - BetterGovPH");
    context.insert("company_name", "BetterGovPH");
    context.insert("platform", "BetterGovPH");
    context.insert("SITE_NAME", "BetterGovPH Data Visualizations");
    context.insert("SITE_URL", "https://visualizations.bettergov.ph");

    let template_name = if is_mobile(&req) {
        "mobile/integrated.html"
    } else {
        "integrated.html"
    };

    let rendered = tera.render(template_name, &context).map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    Ok(HttpResponse::Ok().content_type("text/html").body(rendered))
}

// Family Details Page
async fn family(req: HttpRequest) -> Result<HttpResponse, ActixError> {
    let tera = Tera::new("templates/**/*").map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    let mut context = Context::new();

    add_frontend_env_to_context(&mut context);

    // Get surname and province parameters from query string
    let query = web::Query::<std::collections::HashMap<String, String>>::from_query(req.query_string());
    let surname = query.as_ref().ok().and_then(|q| q.get("surname").cloned()).unwrap_or_else(|| "Unknown".to_string());
    let province = query.as_ref().ok().and_then(|q| q.get("province").cloned()).unwrap_or_else(|| "".to_string());

    context.insert("title", &format!("Family Details: {} - BetterGovPH", surname));
    context.insert("surname", &surname);
    context.insert("province", &province);
    context.insert("company_name", "BetterGovPH");
    context.insert("platform", "BetterGovPH");
    context.insert("SITE_NAME", "BetterGovPH Data Visualizations");
    context.insert("SITE_URL", "https://visualizations.bettergov.ph");

    let template_name = "family.html";

    let rendered = tera.render(template_name, &context).map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    Ok(HttpResponse::Ok().content_type("text/html").body(rendered))
}

// Hours Tracking Page (Secret)
async fn hours(_req: HttpRequest) -> Result<HttpResponse, ActixError> {
    let tera = Tera::new("templates/**/*").map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    let mut context = Context::new();

    add_frontend_env_to_context(&mut context);

    context.insert("title", "Hours Tracking - BetterGovPH");
    context.insert("company_name", "BetterGovPH");
    context.insert("platform", "BetterGovPH");
    context.insert("SITE_NAME", "BetterGovPH Data Visualizations");
    context.insert("SITE_URL", "https://visualizations.bettergov.ph");

    let template_name = "hours.html";

    let rendered = tera.render(template_name, &context).map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    Ok(HttpResponse::Ok().content_type("text/html").body(rendered))
}

// Integrated Matrix 2026 Dashboard
async fn integ2026(_req: HttpRequest) -> Result<HttpResponse, ActixError> {
    let tera = Tera::new("templates/**/*").map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    let mut context = Context::new();

    add_frontend_env_to_context(&mut context);

    context.insert("title", "Integrated Matrix 2026 - BetterGovPH");
    context.insert("company_name", "BetterGovPH");
    context.insert("platform", "BetterGovPH");
    context.insert("SITE_NAME", "BetterGovPH Data Visualizations");
    context.insert("SITE_URL", "https://visualizations.bettergov.ph");

    let template_name = "integrated_matrix.html";

    let rendered = tera.render(template_name, &context).map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    Ok(HttpResponse::Ok().content_type("text/html").body(rendered))
}

// API: Integrated Matrix JSON
async fn api_integrated_matrix() -> Result<fs::NamedFile, ActixError> {
    fs::NamedFile::open("static/data/integrated_matrix.json").map_err(|e| actix_web::error::ErrorNotFound(e))
}

#[derive(Deserialize)]
struct CongressmanQuery {
    name: String,
}

#[derive(Deserialize)]
struct IntegratedProjectQuery {
    page: Option<usize>,
    limit: Option<usize>,
    project_name: Option<String>,
    contractor: Option<String>,
}

async fn api_integrated_projects(query: web::Query<IntegratedProjectQuery>) -> Result<HttpResponse, ActixError> {
    let client = reqwest::Client::new();
    let mut params = Vec::new();

    if let Some(page) = query.page {
        params.push(("page", page.to_string()));
    }
    if let Some(limit) = query.limit {
        params.push(("limit", limit.to_string()));
    }
    if let Some(ref name) = query.project_name {
        params.push(("project_name", name.clone()));
    }
    if let Some(ref contractor) = query.contractor {
        params.push(("contractor", contractor.clone()));
    }

    // Proxy to Python service using env var or default
    let base_url = std::env::var("PYTHON_API_URL").unwrap_or_else(|_| "http://127.0.0.1:8000".to_string());
    
    // Ensure base_url doesn't end with slash to avoid double slashes
    let base_url = base_url.trim_end_matches('/');
    let url = format!("{}/api/integrated/projects", base_url);
    
    match client.get(&url).query(&params).send().await {
        Ok(resp) => {
            let status = actix_web::http::StatusCode::from_u16(resp.status().as_u16())
                .unwrap_or(actix_web::http::StatusCode::INTERNAL_SERVER_ERROR);
            
            match resp.json::<serde_json::Value>().await {
                Ok(json) => Ok(HttpResponse::build(status).json(json)),
                Err(e) => Ok(HttpResponse::InternalServerError().json(serde_json::json!({
                    "success": false,
                    "error": format!("Failed to parse upstream response: {}", e)
                })))
            }
        },
        Err(e) => Ok(HttpResponse::BadGateway().json(serde_json::json!({
            "success": false,
            "error": format!("Failed to connect to upstream service '{}': {}", url, e)
        })))
    }
}

fn slugify(s: &str) -> String {
    let mut result = String::new();
    let mut last_was_dash = false;
    for c in s.to_lowercase().chars() {
        if c.is_alphanumeric() {
             result.push(c);
             last_was_dash = false;
        } else {
             if !last_was_dash {
                 result.push('-');
                 last_was_dash = true;
             }
        }
    }
    result.trim_matches('-').to_string()
}

async fn api_dynasty_congressman(query: web::Query<CongressmanQuery>) -> Result<fs::NamedFile, ActixError> {
    let name = &query.name;
    let slug = slugify(name);
    let path_str = format!("static/data/congressman-projects-{}/all-projects-cache.json", slug);
    let path = Path::new(&path_str);
    
    if path.exists() {
         fs::NamedFile::open(path).map_err(|e| actix_web::error::ErrorNotFound(e))
    } else {
        Err(actix_web::error::ErrorNotFound(format!("Cache not found for {}", name)))
    }
}

// MPB Top Buildings proxy to Python service
async fn api_mpb_top_buildings_proxy() -> Result<HttpResponse, ActixError> {
    let client = reqwest::Client::new();

    // Proxy to Python service using env var or default
    let base_url = std::env::var("PYTHON_API_URL").unwrap_or_else(|_| "http://127.0.0.1:8000".to_string());
    let base_url = base_url.trim_end_matches('/');
    let url = format!("{}/api/mpb/top-buildings", base_url);

    match client.get(&url).send().await {
        Ok(resp) => {
            let status = actix_web::http::StatusCode::from_u16(resp.status().as_u16())
                .unwrap_or(actix_web::http::StatusCode::INTERNAL_SERVER_ERROR);

            match resp.json::<serde_json::Value>().await {
                Ok(json) => Ok(HttpResponse::build(status).json(json)),
                Err(e) => Ok(HttpResponse::InternalServerError().json(serde_json::json!({
                    "success": false,
                    "error": format!("Failed to parse upstream response: {}", e)
                })))
            }
        },
        Err(e) => Ok(HttpResponse::BadGateway().json(serde_json::json!({
            "success": false,
            "error": format!("Failed to connect to upstream service '{}': {}", url, e)
        })))
    }
}

#[actix_web::main]
async fn main() -> std::io::Result<()> {
    // Load environment variables from .env file
    dotenv::dotenv().ok();
    
    // Initialize logging
    env_logger::init();

    // Read server configuration from environment
    let host = std::env::var("SERVER_HOST").unwrap_or_else(|_| "127.0.0.1".to_string());
    let port = std::env::var("SERVER_PORT")
        .unwrap_or_else(|_| "8889".to_string())
        .parse::<u16>()
        .unwrap_or(8889);
    
    let bind_address = format!("{}:{}", host, port);

    println!("🚀 Starting BetterGovPH Open Data Visualization Server");
    println!("📡 Listening on {}", bind_address);

    HttpServer::new(|| {
        let cors = Cors::default()
            .allow_any_origin()
            .allow_any_method()
            .allow_any_header();

        App::new()
            .wrap(cors)
            .service(fs::Files::new("/static", "./static/"))
            .service(web::resource("/favicon.ico").route(web::get().to(favicon)))
            .service(web::resource("/robots.txt").route(web::get().to(robots)))
            .service(web::resource("/").to(home))
            .service(web::resource("/budget").to(budget))
            .service(web::resource("/flood").to(flood))
            .service(web::resource("/dime").to(dime))
            .service(web::resource("/nep").to(nep))
            .service(web::resource("/map").to(map))
            .service(web::resource("/mpb").to(mpb))
        .service(web::resource("/philgeps").to(contractors))
        .service(web::resource("/dynasty").to(dynasty))
        .service(web::resource("/dynasty-projects").to(dynasty_projects))
        .service(web::resource("/integrated").to(integrated))
        .service(web::resource("/family").to(family))
        .service(web::resource("/zaldy").to(zaldy))
        .service(web::resource("/zarah").to(zarah))
            .service(web::resource("/budget-nep-correlation").to(budget_nep_correlation))
            .service(web::resource("/budget-flood-correlation").to(budget_flood_correlation))
            .service(web::resource("/flood-dime-correlation").to(flood_dime_correlation))
            .service(web::resource("/contractor-district-correlation").to(contractor_district_correlation))
            .service(web::resource("/dynasty-poverty-correlation").to(dynasty_poverty_correlation))
            .service(web::resource("/eogo").to(eogo))
            .service(web::resource("/sources").to(sources))
            .service(web::resource("/circles").to(circles))
            .service(web::resource("/hours").to(hours))
            .service(web::resource("/integ2026").to(integ2026))
            .service(web::resource("/api/integrated/matrix").route(web::get().to(api_integrated_matrix)))
            .service(web::resource("/api/integrated/projects").route(web::get().to(api_integrated_projects)))
            .service(web::resource("/api/mpb/top-buildings").route(web::get().to(api_mpb_top_buildings_proxy)))
            .service(web::resource("/api/dynasty-projects/congressman").route(web::get().to(api_dynasty_congressman)))
    })
    .bind(&bind_address)?
    .run()
    .await
}
