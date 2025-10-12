// BetterGovPH Open Data Visualization - Utility Functions

use std::collections::HashMap;

// Function: load_frontend_env
pub fn load_frontend_env() -> HashMap<String, String> {
    let mut env_vars = HashMap::new();

    // Default values for BetterGovPH
    env_vars.insert("SITE_NAME".to_string(), "BetterGovPH Data Visualizations".to_string());
    env_vars.insert("SITE_URL".to_string(), "https://altgovph.site".to_string());

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

