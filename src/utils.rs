// BetterGovPH Open Data Visualization - Utility Functions

use std::collections::HashMap;

// Function: get_site_branding
pub fn get_site_branding(req: &actix_web::HttpRequest) -> (String, String) {
    let host = req.headers().get("host")
        .and_then(|h| h.to_str().ok())
        .unwrap_or("visualizations.bettergov.ph");

    if host.contains("research.bettergov.ph") {
        ("BetterGovPH Research".to_string(), "https://research.bettergov.ph".to_string())
    } else {
        ("BetterGovPH Data Visualizations".to_string(), "https://visualizations.bettergov.ph".to_string())
    }
}

// Function: load_frontend_env
pub fn load_frontend_env(req: &actix_web::HttpRequest) -> HashMap<String, String> {
    let mut env_vars = HashMap::new();

    let (site_name, site_url) = get_site_branding(req);

    // Dynamic values based on host
    env_vars.insert("SITE_NAME".to_string(), site_name);
    env_vars.insert("SITE_URL".to_string(), site_url);

    // Add other environment variables as needed
    env_vars.insert("GOOGLE_CLIENT_ID".to_string(), std::env::var("GOOGLE_CLIENT_ID").unwrap_or_default());
    env_vars.insert("FACEBOOK_APP_ID".to_string(), std::env::var("FACEBOOK_APP_ID").unwrap_or_default());

    env_vars
}

// Function: add_frontend_env_to_context
pub fn add_frontend_env_to_context(context: &mut tera::Context, req: &actix_web::HttpRequest) {
    let env_vars = load_frontend_env(req);
    for (key, value) in env_vars {
        context.insert(key, &value);
    }
}

// Function: is_mobile
// Detects if the request is from a mobile device based on User-Agent
pub fn is_mobile(req: &actix_web::HttpRequest) -> bool {
    if let Some(user_agent) = req.headers().get(actix_web::http::header::USER_AGENT) {
        if let Ok(ua_str) = user_agent.to_str() {
            let ua = ua_str.to_lowercase();
            // Check for common mobile user agents
            return ua.contains("mobile") || 
                   ua.contains("android") || 
                   ua.contains("iphone") || 
                   ua.contains("ipod") ||
                   ua.contains("blackberry") ||
                   ua.contains("windows phone");
        }
    }
    false
}

