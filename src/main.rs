// BetterGovPH Open Data Visualization - Standalone Application

use actix_web::{App, HttpServer, HttpResponse, HttpRequest, Result, error::Error as ActixError, web};
use actix_files as fs;
use tera::{Tera, Context};
use std::collections::HashMap;

// Helper functions

// Function: add_frontend_env_to_context
fn add_frontend_env_to_context(context: &mut tera::Context) {
    let mut env_vars = HashMap::new();
    env_vars.insert("SITE_URL".to_string(), "https://altgovph.site".to_string());
    env_vars.insert("SITE_NAME".to_string(), "BetterGovPH Data Visualizations".to_string());
    
    for (key, value) in env_vars {
        context.insert(&key, &value);
    }
}

// Function: should_use_mobile_template
fn should_use_mobile_template(_req: &HttpRequest) -> bool {
    false  // Disabled for this standalone app
}

// Function: check_mobile_redirect_enhanced
fn check_mobile_redirect_enhanced(_req: &HttpRequest) -> Option<actix_web::HttpResponse> {
    None  // Disabled for this standalone app
}

// Function: check_production_domain_block
fn check_production_domain_block(_req: &HttpRequest) -> Option<actix_web::HttpResponse> {
    None  // Disabled for this standalone app
}

// Route handlers

// BetterGovPH Homepage
async fn altgovph_home(_req: HttpRequest) -> Result<HttpResponse, ActixError> {
    let tera = Tera::new("templates/**/*").map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    let mut context = Context::new();
    
    add_frontend_env_to_context(&mut context);
    
    context.insert("title", "BetterGovPH Data Visualizations");
    context.insert("company_name", "BetterGovPH");
    context.insert("platform", "BetterGovPH");
    context.insert("SITE_NAME", "BetterGovPH Data Visualizations");
    context.insert("SITE_URL", "https://altgovph.site");
    
    let template_name = "visualizations_home.html";
    
    let rendered = tera.render(template_name, &context).map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    Ok(HttpResponse::Ok().content_type("text/html").body(rendered))
}

// Budget Analysis Page
async fn budget(_req: HttpRequest) -> Result<HttpResponse, ActixError> {
    let tera = Tera::new("templates/**/*").map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    let mut context = Context::new();
    
    add_frontend_env_to_context(&mut context);
    
    context.insert("title", "Budget Analysis - BetterGovPH");
    context.insert("company_name", "BetterGovPH");
    context.insert("platform", "BetterGovPH");
    context.insert("SITE_NAME", "BetterGovPH Data Visualizations");
    context.insert("SITE_URL", "https://altgovph.site");
    
    let template_name = "budget.html";
    
    let rendered = tera.render(template_name, &context).map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    Ok(HttpResponse::Ok().content_type("text/html").body(rendered))
}

// Flood Control Projects Page
async fn flood(_req: HttpRequest) -> Result<HttpResponse, ActixError> {
    let tera = Tera::new("templates/**/*").map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    let mut context = Context::new();
    
    add_frontend_env_to_context(&mut context);
    
    context.insert("title", "Flood Control Projects - BetterGovPH");
    context.insert("company_name", "BetterGovPH");
    context.insert("platform", "BetterGovPH");
    context.insert("SITE_NAME", "BetterGovPH Data Visualizations");
    context.insert("SITE_URL", "https://altgovph.site");
    
    let template_name = "flood.html";
    
    let rendered = tera.render(template_name, &context).map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    Ok(HttpResponse::Ok().content_type("text/html").body(rendered))
}

// DIME Infrastructure Projects Page
async fn dime(_req: HttpRequest) -> Result<HttpResponse, ActixError> {
    let tera = Tera::new("templates/**/*").map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    let mut context = Context::new();
    
    add_frontend_env_to_context(&mut context);
    
    context.insert("title", "DIME Infrastructure Projects - BetterGovPH");
    context.insert("company_name", "BetterGovPH");
    context.insert("platform", "BetterGovPH");
    context.insert("SITE_NAME", "BetterGovPH Data Visualizations");
    context.insert("SITE_URL", "https://altgovph.site");
    
    let template_name = "dime.html";
    
    let rendered = tera.render(template_name, &context).map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    Ok(HttpResponse::Ok().content_type("text/html").body(rendered))
}

// NEP Analysis Page
async fn nep(_req: HttpRequest) -> Result<HttpResponse, ActixError> {
    let tera = Tera::new("templates/**/*").map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    let mut context = Context::new();

    add_frontend_env_to_context(&mut context);

    context.insert("title", "NEP Analysis - BetterGovPH");
    context.insert("company_name", "BetterGovPH");
    context.insert("platform", "BetterGovPH");
    context.insert("SITE_NAME", "BetterGovPH Data Visualizations");
    context.insert("SITE_URL", "https://altgovph.site");

    let template_name = "nep.html";

    let rendered = tera.render(template_name, &context).map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    Ok(HttpResponse::Ok().content_type("text/html").body(rendered))
}

// Interactive Map Page
async fn map(_req: HttpRequest) -> Result<HttpResponse, ActixError> {
    let tera = Tera::new("templates/**/*").map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    let mut context = Context::new();

    add_frontend_env_to_context(&mut context);

    context.insert("title", "Interactive Map - BetterGovPH");
    context.insert("company_name", "BetterGovPH");
    context.insert("platform", "BetterGovPH");
    context.insert("SITE_NAME", "BetterGovPH Data Visualizations");
    context.insert("SITE_URL", "https://altgovph.site");

    let template_name = "map.html";

    let rendered = tera.render(template_name, &context).map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    Ok(HttpResponse::Ok().content_type("text/html").body(rendered))
}

// About Page
async fn about(_req: HttpRequest) -> Result<HttpResponse, ActixError> {
    let tera = Tera::new("templates/**/*").map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    let mut context = Context::new();

    add_frontend_env_to_context(&mut context);

    context.insert("title", "About - BetterGovPH");
    context.insert("company_name", "BetterGovPH");
    context.insert("platform", "BetterGovPH");
    context.insert("SITE_NAME", "BetterGovPH Data Visualizations");
    context.insert("SITE_URL", "https://altgovph.site");

    let template_name = "about.html";

    let rendered = tera.render(template_name, &context).map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    Ok(HttpResponse::Ok().content_type("text/html").body(rendered))
}

// Budget-NEP Correlation Page
async fn budget_nep_correlation(_req: HttpRequest) -> Result<HttpResponse, ActixError> {
    let tera = Tera::new("templates/**/*").map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    let mut context = Context::new();

    add_frontend_env_to_context(&mut context);

    context.insert("title", "Budget-NEP Correlation - BetterGovPH");
    context.insert("company_name", "BetterGovPH");
    context.insert("platform", "BetterGovPH");
    context.insert("SITE_NAME", "BetterGovPH Data Visualizations");
    context.insert("SITE_URL", "https://altgovph.site");

    let template_name = "budget_nep_correlation.html";

    let rendered = tera.render(template_name, &context).map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    Ok(HttpResponse::Ok().content_type("text/html").body(rendered))
}

// Budget-Flood Correlation Page
async fn budget_flood_correlation(_req: HttpRequest) -> Result<HttpResponse, ActixError> {
    let tera = Tera::new("templates/**/*").map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    let mut context = Context::new();

    add_frontend_env_to_context(&mut context);

    context.insert("title", "Budget-Flood Correlation - BetterGovPH");
    context.insert("company_name", "BetterGovPH");
    context.insert("platform", "BetterGovPH");
    context.insert("SITE_NAME", "BetterGovPH Data Visualizations");
    context.insert("SITE_URL", "https://altgovph.site");

    let template_name = "budget_flood_correlation.html";

    let rendered = tera.render(template_name, &context).map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    Ok(HttpResponse::Ok().content_type("text/html").body(rendered))
}

// Flood-DIME Correlation Page
async fn flood_dime_correlation(_req: HttpRequest) -> Result<HttpResponse, ActixError> {
    let tera = Tera::new("templates/**/*").map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    let mut context = Context::new();

    add_frontend_env_to_context(&mut context);

    context.insert("title", "Flood-DIME Correlation - BetterGovPH");
    context.insert("company_name", "BetterGovPH");
    context.insert("platform", "BetterGovPH");
    context.insert("SITE_NAME", "BetterGovPH Data Visualizations");
    context.insert("SITE_URL", "https://altgovph.site");

    let template_name = "flood_dime_correlation.html";

    let rendered = tera.render(template_name, &context).map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    Ok(HttpResponse::Ok().content_type("text/html").body(rendered))
}

#[actix_web::main]
async fn main() -> std::io::Result<()> {
    println!("🚀 Starting BetterGovPH Open Data Visualization Server");
    
    HttpServer::new(|| {
        App::new()
            .service(fs::Files::new("/static", "./static/"))
            .service(web::resource("/").to(altgovph_home))
            .service(web::resource("/budget").to(budget))
            .service(web::resource("/flood").to(flood))
            .service(web::resource("/dime").to(dime))
            .service(web::resource("/nep").to(nep))
            .service(web::resource("/map").to(map))
            .service(web::resource("/about").to(about))
            .service(web::resource("/budget-nep-correlation").to(budget_nep_correlation))
            .service(web::resource("/budget-flood-correlation").to(budget_flood_correlation))
            .service(web::resource("/flood-dime-correlation").to(flood_dime_correlation))
    })
    .bind("127.0.0.1:8888")?
    .run()
    .await
}
