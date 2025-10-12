// BetterGovPH Open Data Visualization - Standalone Application

use actix_web::{App, HttpServer, HttpResponse, HttpRequest, Result, error::Error as ActixError, web};
use actix_files as fs;
use actix_cors::Cors;
use tera::{Tera, Context};

mod utils;
use utils::*;

// Route handlers

// BetterGovPH Homepage
async fn home(_req: HttpRequest) -> Result<HttpResponse, ActixError> {
    let tera = Tera::new("templates/**/*").map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    let mut context = Context::new();
    
    add_frontend_env_to_context(&mut context);
    
    context.insert("title", "BetterGovPH Data Visualizations");
    context.insert("company_name", "BetterGovPH");
    context.insert("platform", "BetterGovPH");
    context.insert("SITE_NAME", "BetterGovPH Data Visualizations");
    context.insert("SITE_URL", "https://visualizations.bettergov.ph");
    
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
    context.insert("SITE_URL", "https://visualizations.bettergov.ph");
    
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
    context.insert("SITE_URL", "https://visualizations.bettergov.ph");
    
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
    context.insert("SITE_URL", "https://visualizations.bettergov.ph");
    
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
    context.insert("SITE_URL", "https://visualizations.bettergov.ph");

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
    context.insert("SITE_URL", "https://visualizations.bettergov.ph");

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
    context.insert("SITE_URL", "https://visualizations.bettergov.ph");

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
    context.insert("SITE_URL", "https://visualizations.bettergov.ph");

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
    context.insert("SITE_URL", "https://visualizations.bettergov.ph");

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
    context.insert("SITE_URL", "https://visualizations.bettergov.ph");

    let template_name = "flood_dime_correlation.html";

    let rendered = tera.render(template_name, &context).map_err(|e| actix_web::error::ErrorInternalServerError(e))?;
    Ok(HttpResponse::Ok().content_type("text/html").body(rendered))
}

#[actix_web::main]
async fn main() -> std::io::Result<()> {
    // Initialize logging
    env_logger::init();

    println!("🚀 Starting BetterGovPH Open Data Visualization Server");

    HttpServer::new(|| {
        let cors = Cors::default()
            .allow_any_origin()
            .allow_any_method()
            .allow_any_header();

        App::new()
            .wrap(cors)
            .service(fs::Files::new("/static", "./static/"))
            .service(web::resource("/").to(home))
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
