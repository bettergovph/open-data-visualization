// AltGovPH Routes - Extracted from main.rs
// Contains only the route handlers for AltGovPH data visualization pages

use actix_web::{HttpResponse, HttpRequest, Result, error::Error as ActixError, web};
use tera::{Tera, Context};
use std::collections::HashMap;

// Helper functions from utils module

// Function: add_frontend_env_to_context
pub fn add_frontend_env_to_context(context: &mut tera::Context) {
    // This would load environment variables for the frontend
    // Simplified version for this extraction
    let mut env_vars = HashMap::new();
    env_vars.insert("SITE_URL".to_string(), "https://altgovph.site".to_string());
    env_vars.insert("SITE_NAME".to_string(), "AltGovPH".to_string());

    for (key, value) in env_vars {
        context.insert(key, &value);
    }
}

// Function: should_use_mobile_template
pub fn should_use_mobile_template(req: &HttpRequest) -> bool {
    // Check if the request is coming from a mobile domain
    if let Some(host) = req.headers().get("host") {
        if let Ok(host_str) = host.to_str() {
            return host_str.contains("m.kenchlightyear.com") ||
                   host_str.contains("mobile.kenchlightyear.com");
        }
    }
    false
}

// Function: check_mobile_redirect_enhanced
pub fn check_mobile_redirect_enhanced(req: &HttpRequest) -> Option<actix_web::HttpResponse> {
    // Check if the request is coming from a mobile domain
    if let Some(host) = req.headers().get("host") {
        if let Ok(host_str) = host.to_str() {
            if host_str.contains("m.kenchlightyear.com") ||
               host_str.contains("mobile.kenchlightyear.com") {
                return None; // Already on mobile domain
            }
        }
    }
    None
}

// Function: check_production_domain_block
pub fn check_production_domain_block(req: &HttpRequest) -> Option<actix_web::HttpResponse> {
    // Check if the request is coming from production kenchlightyear.com domain
    if let Some(host) = req.headers().get("host") {
        if let Ok(host_str) = host.to_str() {
            // Redirect from production kenchlightyear.com to altgovph.site (not staging)
            if host_str == "kenchlightyear.com" || host_str == "www.kenchlightyear.com" {
                let path = req.uri().path();
                if path == "/budget" || path == "/flood" || path == "/alt" || path == "/dime" || path == "/budget-flood-correlation" || path == "/flood-dime-correlation" {
                    println!("🔄 Redirecting {} from production kenchlightyear.com to altgovph.site", path);

                    // Preserve query parameters
                    let query_string = if let Some(query) = req.uri().query() {
                        format!("?{}", query)
                    } else {
                        String::new()
                    };

                    let redirect_url = format!("https://altgovph.site{}{}", path, query_string);
                    return Some(HttpResponse::PermanentRedirect()
                        .append_header(("Location", redirect_url))
                        .finish());
                }
            }
        }
    }
    None
}

// Route handlers

async fn altgovph_home(_req: HttpRequest) -> Result<HttpResponse, ActixError> {
    // Check for mobile redirect
    if let Some(redirect) = check_mobile_redirect_enhanced(&_req) {
        return Ok(redirect);
    }

    // Use AltGovPH home template
    let tera = Tera::new("templates/**/*").map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    let mut context = Context::new();

    // Add frontend environment variables first
    add_frontend_env_to_context(&mut context);

    // AltGovPH theme for home page
    context.insert("title", "AltGovPH - Alternative Government Philippines");
    context.insert("company_name", "AltGovPH");
    context.insert("platform", "AltGovPH");
    context.insert("SITE_NAME", "AltGovPH");
    context.insert("SITE_URL", "https://altgovph.site");

    // Override Open Graph and Twitter metadata for AltGovPH
    context.insert("og_title", "AltGovPH - Alternative Government Philippines");
    context.insert("og_description", "Promoting Data Transparency and Open Government in the Philippines");
    context.insert("og_url", "https://altgovph.site/");
    context.insert("og_image", "/static/images/gov_logo.png");

    // Choose template based on host
    let template_name = if should_use_mobile_template(&_req) {
        "mobile/altgovph_home.html"
    } else {
        "altgovph_home.html"
    };

    let rendered = tera.render(template_name, &context).map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    Ok(HttpResponse::Ok().content_type("text/html").body(rendered))
}

async fn budget(_req: HttpRequest) -> Result<HttpResponse, ActixError> {
    // Check for mobile redirect
    if let Some(redirect) = check_mobile_redirect_enhanced(&_req) {
        return Ok(redirect);
    }

    // Check for production domain blocking (block /budget and /flood on kenchlightyear.com)
    if let Some(block_response) = check_production_domain_block(&_req) {
        return Ok(block_response);
    }

    // Use standalone budget template (no KenchLightyear branding)
    let tera = Tera::new("templates/**/*").map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    let mut context = Context::new();

    // Add frontend environment variables first
    add_frontend_env_to_context(&mut context);

    // AltGovPH theme for budget frontend separation (override after env vars)
    context.insert("title", "Budget Analysis - AltGovPH");
    context.insert("company_name", "AltGovPH");
    context.insert("platform", "AltGovPH");
    context.insert("SITE_NAME", "AltGovPH");
    context.insert("SITE_URL", "https://altgovph.site");

    // Override Open Graph and Twitter metadata for AltGovPH
    context.insert("og_title", "Budget Analysis - AltGovPH");
    context.insert("og_description", "Government Data Analysis Platform for Budget and Flood Control Projects");
    context.insert("og_url", "https://altgovph.site/");
    context.insert("og_image", "/static/images/gov_logo.png");

    // Choose template based on host
    let template_name = if should_use_mobile_template(&_req) {
        "mobile/budget.html"
    } else {
        "budget.html"
    };

    let rendered = tera.render(template_name, &context).map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    Ok(HttpResponse::Ok().content_type("text/html").body(rendered))
}

async fn flood(_req: HttpRequest) -> Result<HttpResponse, ActixError> {
    // Check for mobile redirect
    if let Some(redirect) = check_mobile_redirect_enhanced(&_req) {
        return Ok(redirect);
    }

    // Check for production domain blocking (block /budget and /flood on kenchlightyear.com)
    if let Some(block_response) = check_production_domain_block(&_req) {
        return Ok(block_response);
    }

    // Use standalone flood template (no KenchLightyear branding)
    let tera = Tera::new("templates/**/*").map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    let mut context = Context::new();

    // Add frontend environment variables first
    add_frontend_env_to_context(&mut context);

    // AltGovPH theme for flood frontend separation (override after env vars)
    context.insert("title", "Flood Control Projects - AltGovPH");
    context.insert("company_name", "AltGovPH");
    context.insert("platform", "AltGovPH");
    context.insert("SITE_NAME", "AltGovPH");
    context.insert("SITE_URL", "https://altgovph.site");

    // Override Open Graph and Twitter metadata for AltGovPH
    context.insert("og_title", "Flood Control Projects - AltGovPH");
    context.insert("og_description", "Government Data Analysis Platform for Flood Control Infrastructure Projects");
    context.insert("og_url", "https://altgovph.site/");
    context.insert("og_image", "/static/images/gov_logo.png");

    // Choose template based on host
    let template_name = if should_use_mobile_template(&_req) {
        "mobile/flood.html"
    } else {
        "flood.html"
    };

    let rendered = tera.render(template_name, &context).map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    Ok(HttpResponse::Ok().content_type("text/html").body(rendered))
}

async fn dime(_req: HttpRequest) -> Result<HttpResponse, ActixError> {
    // Check for mobile redirect
    if let Some(redirect) = check_mobile_redirect_enhanced(&_req) {
        return Ok(redirect);
    }

    // Check for production domain blocking (block /dime on kenchlightyear.com)
    if let Some(block_response) = check_production_domain_block(&_req) {
        return Ok(block_response);
    }

    // Use standalone DIME template (no KenchLightyear branding)
    let tera = Tera::new("templates/**/*").map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    let mut context = Context::new();

    // Add frontend environment variables first
    add_frontend_env_to_context(&mut context);

    // AltGovPH theme for DIME frontend separation (override after env vars)
    context.insert("title", "DIME Infrastructure Projects - AltGovPH");
    context.insert("company_name", "AltGovPH");
    context.insert("platform", "AltGovPH");
    context.insert("SITE_NAME", "AltGovPH");
    context.insert("SITE_URL", "https://altgovph.site");

    // Override Open Graph and Twitter metadata for AltGovPH
    context.insert("og_title", "DIME Infrastructure Projects - AltGovPH");
    context.insert("og_description", "Department of Infrastructure and Mega-Projects Execution - Infrastructure Projects Tracker");
    context.insert("og_url", "https://altgovph.site/");
    context.insert("og_image", "/static/images/gov_logo.png");

    // Choose template based on host
    let template_name = if should_use_mobile_template(&_req) {
        "mobile/dime.html"
    } else {
        "dime.html"
    };

    let rendered = tera.render(template_name, &context).map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    Ok(HttpResponse::Ok().content_type("text/html").body(rendered))
}

async fn budget_flood_correlation(_req: HttpRequest) -> Result<HttpResponse, ActixError> {
    // Check for mobile redirect
    if let Some(redirect) = check_mobile_redirect_enhanced(&_req) {
        return Ok(redirect);
    }

    // Check for production domain blocking (block on kenchlightyear.com)
    if let Some(block_response) = check_production_domain_block(&_req) {
        return Ok(block_response);
    }

    // Use budget-flood correlation template
    let tera = Tera::new("templates/**/*").map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    let mut context = Context::new();

    // Add frontend environment variables first
    add_frontend_env_to_context(&mut context);

    // AltGovPH theme for budget-flood correlation page
    context.insert("company_name", "AltGovPH");
    context.insert("platform", "AltGovPH");
    context.insert("SITE_NAME", "AltGovPH");
    context.insert("SITE_URL", "https://altgovph.site");
    context.insert("og_url", "https://altgovph.site/budget-flood-correlation");
    context.insert("og_image", "/static/images/gov_logo.png");

    let rendered = tera.render("budget_flood_correlation.html", &context).map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    Ok(HttpResponse::Ok().content_type("text/html").body(rendered))
}

async fn flood_dime_correlation(_req: HttpRequest) -> Result<HttpResponse, ActixError> {
    // Check for mobile redirect
    if let Some(redirect) = check_mobile_redirect_enhanced(&_req) {
        return Ok(redirect);
    }

    // Check for production domain blocking (block on kenchlightyear.com)
    if let Some(block_response) = check_production_domain_block(&_req) {
        return Ok(block_response);
    }

    // Use flood-dime correlation template
    let tera = Tera::new("templates/**/*").map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    let mut context = Context::new();

    // Add frontend environment variables first
    add_frontend_env_to_context(&mut context);

    // AltGovPH theme for flood-dime correlation page
    context.insert("title", "Flood-DIME Correlation Analysis - AltGovPH");
    context.insert("company_name", "AltGovPH");
    context.insert("platform", "AltGovPH");
    context.insert("SITE_NAME", "AltGovPH");
    context.insert("SITE_URL", "https://altgovph.site");

    // Override Open Graph and Twitter metadata for AltGovPH
    context.insert("og_url", "https://altgovph.site/flood-dime-correlation");
    context.insert("og_image", "/static/images/gov_logo.png");

    let rendered = tera.render("flood_dime_correlation.html", &context).map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    Ok(HttpResponse::Ok().content_type("text/html").body(rendered))
}

// Route registration example (for reference)
/*
In your main.rs, you would register these routes like:

App::new()
    .service(web::resource("/alt").to(altgovph_home))
    .service(web::resource("/budget").to(budget))
    .service(web::resource("/flood").to(flood))
    .service(web::resource("/dime").to(dime))
    .service(web::resource("/budget-flood-correlation").to(budget_flood_correlation))
    .service(web::resource("/flood-dime-correlation").to(flood_dime_correlation))
*/
