# Open Data Visualization - AltGovPH Frontend

This directory contains the frontend components copied from the AltGovPH section of the kenchlightyear_web project.

## Routes and Functionality

### /alt (AltGovPH Homepage)
- **Templates**: `altgovph_home.html`, `mobile/altgovph_home.html`
- **Functionality**: Landing page with navigation to all data sections

### /budget (Budget Analysis)
- **Templates**: `budget.html`, `mobile/budget.html`
- **Functionality**: AI-powered analysis of Government Appropriations Act (GAA) data with intelligent insights, duplicate detection, and trend analysis

### /flood (Flood Control Projects)
- **Templates**: `flood.html`, `mobile/flood.html`
- **Functionality**: Comprehensive tracking and analysis of DPWH flood control infrastructure projects across the Philippines

### /dime (DIME Infrastructure)
- **Templates**: `dime.html`, `mobile/dime.html`
- **Functionality**: Digital Information for Monitoring and Evaluation - Track 12,870+ major infrastructure projects worth ₱740B+ nationwide

### Correlation Analysis
- **Templates**: `budget_flood_correlation.html`, `flood_dime_correlation.html`
- **Functionality**: Data science analysis connecting different datasets for transparency

## Files Copied:

### Templates
- `templates/altgovph_home.html` - Main AltGovPH homepage template
- `templates/mobile/altgovph_home.html` - Mobile version of the AltGovPH homepage
- `templates/base_altgovph.html` - Base template for AltGovPH desktop pages
- `templates/mobile/base_altgovph.html` - Base template for AltGovPH mobile pages
- `templates/base.html` - Main base template that AltGovPH templates extend
- `templates/budget.html` - Budget analysis page template
- `templates/mobile/budget.html` - Mobile budget analysis page
- `templates/flood.html` - Flood control projects page template
- `templates/mobile/flood.html` - Mobile flood control projects page
- `templates/dime.html` - DIME infrastructure projects page template
- `templates/mobile/dime.html` - Mobile DIME infrastructure projects page
- `templates/budget_flood_correlation.html` - Budget-flood correlation analysis
- `templates/flood_dime_correlation.html` - Flood-DIME correlation analysis

### CSS Stylesheets
- `static/css/altgovph-theme.css` - AltGovPH desktop theme styles
- `static/css/altgovph-mobile.css` - Mobile-specific AltGovPH styles
- `static/css/altgovph-shared.css` - Shared AltGovPH styles
- `static/css/style.css` - Main site styles (referenced by base.html)
- `static/css/mobile-fixes.css` - Mobile fixes (referenced by base.html)
- `static/css/mobile-budget.css` - Mobile budget-specific styles
- `static/css/mobile.css` - General mobile styles

### JavaScript Files
- `static/js/main.js` - Main JavaScript functionality
- `static/js/mobile.js` - Mobile-specific JavaScript
- `static/js/auth-unified.js` - Authentication JavaScript
- `static/js/oauth-config.js` - OAuth configuration
- `static/js/error-handling.js` - Error handling JavaScript

### Static Data Files
- `static/data/` - Directory containing all JSON data files used by templates
  - Budget trends analysis data
  - Contractor statistics cache
  - Correlation datasets for all years (2020-2025)
  - Flood control project data
  - DIME project data
  - Philippines regions mapping
  - Various analysis datasets

### Images
- `static/images/kl.png` - KenchLightyear logo (referenced in base templates)

### Rust Route Definitions
- `altgovph_routes.rs` - Complete route handlers extracted from main.rs
  - Contains route functions for all AltGovPH pages
  - Includes helper functions for mobile redirects and domain blocking
  - Example route registration code included as comments

## Notes:
- All API endpoints and backend functionality were excluded as requested
- The templates use Jinja2 templating syntax for dynamic content
- External CDNs are used for fonts (Inter), icons (Font Awesome), Chart.js, D3.js, and Leaflet maps
- The `gov_logo.png` referenced in templates doesn't exist in the original project
- Templates include comprehensive data visualizations using Chart.js and D3.js
- Mobile templates provide responsive design for all data views

## Usage:
To integrate these routes into your Actix-web application, reference the `altgovph_routes.rs` file and register the routes as shown in the comments at the bottom of that file.
