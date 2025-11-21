// BetterGovPH Open Data Visualization - Utility Functions

use std::collections::HashMap;

// Function: load_frontend_env
pub fn load_frontend_env() -> HashMap<String, String> {
    let mut env_vars = HashMap::new();

    // Default values for BetterGovPH
    env_vars.insert("SITE_NAME".to_string(), "BetterGovPH Data Visualizations".to_string());
    env_vars.insert("SITE_URL".to_string(), "https://visualizations.bettergov.ph".to_string());

    // Add other environment variables as needed
    env_vars.insert("GOOGLE_CLIENT_ID".to_string(), std::env::var("GOOGLE_CLIENT_ID").unwrap_or_default());
    env_vars.insert("FACEBOOK_APP_ID".to_string(), std::env::var("FACEBOOK_APP_ID").unwrap_or_default());

    env_vars
}



// Function: add_frontend_env_to_context
pub fn add_frontend_env_to_context(context: &mut tera::Context) {
    let env_vars = load_frontend_env();
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

