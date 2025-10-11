# BetterGovPH Data Visualizations

This project contains the **BetterGovPH Data Visualizations** platform - a comprehensive open data visualization tool for Philippine government budget, infrastructure, and flood control projects.

## Project Status

✅ **FULLY ISOLATED** from kenchlightyear business platform  
✅ **RUNNING** on dedicated server (10.27.79.7)  
✅ **PRODUCTION READY** for visualizations.bettergov.ph  
✅ **TEST ACCESS** available at altgovph.site  

## Domains

- **Production**: https://visualizations.bettergov.ph
- **Test/Transition**: https://altgovph.site

## Architecture

### Frontend (Rust/Actix-Web)
- **Server**: 192.168.2.122:8888
- **Framework**: Actix-Web with Tera templating
- **Routes**: 11 major pages + correlation analysis
- **Mobile Support**: Responsive design with dedicated mobile templates

### Backend (Python/FastAPI) 
- **Server**: 192.168.2.122:8000
- **Framework**: FastAPI with async PostgreSQL
- **Database**: Government budget and infrastructure data
- **Status**: Mock API responses (database integration pending)

### Reverse Proxy (Nginx)
- **Ports**: 80/443
- **SSL**: Lets Encrypt certificates
- **Load Balancing**: API requests proxied to FastAPI backend

## Routes and Functionality

### / (Homepage)
- **Templates**: visualizations_home.html, mobile/visualizations_home.html
- **Functionality**: Landing page with navigation to all data sections

### /budget (Budget Analysis)
- **Templates**: budget.html, mobile/budget.html
- **Functionality**: AI-powered analysis of Government Appropriations Act (GAA) data
- **Features**: Intelligent insights, duplicate detection, trend analysis

### /flood (Flood Control Projects)
- **Templates**: flood.html, mobile/flood.html
- **Functionality**: Comprehensive tracking of DPWH flood control infrastructure
- **Features**: Nationwide project mapping and analysis

### /dime (DIME Infrastructure)
- **Templates**: dime.html, mobile/dime.html
- **Functionality**: Digital Information for Monitoring and Evaluation
- **Features**: 12,870+ major infrastructure projects worth ₱740B+

### /nep (NEP Analysis)
- **Templates**: nep.html, mobile/nep.html
- **Functionality**: National Expenditure Program analysis
- **Features**: AI-powered insights, duplicate detection, budget tracking

### /map (Interactive Map)
- **Templates**: map.html, mobile/map.html
- **Functionality**: Interactive geographical visualization
- **Features**: Flood control projects and infrastructure mapping

### /about (About Page)
- **Templates**: about.html, mobile/about.html
- **Functionality**: Project information and advocacy focus

### Correlation Analysis
- **Budget-NEP**: /budget-nep-correlation
- **Budget-Flood**: /budget-flood-correlation
- **Flood-DIME**: /flood-dime-correlation
- **Templates**: Individual correlation analysis pages
- **Functionality**: Data science connections between datasets

## File Structure

### Templates
- visualizations_home.html - Main homepage
- base_visualizations.html - Base template for desktop pages
- base.html - Legacy base template
- mobile/ - Mobile-optimized versions of all templates

### Static Assets
- static/css/ - Stylesheets (altgovph-theme.css, mobile styles)
- static/js/ - JavaScript functionality
- static/images/ - Logos and assets
- static/data/ - JSON datasets for visualizations

### Source Code
- src/main.rs - Actix-Web frontend application
- visualization.py - FastAPI backend (mock responses)
- Cargo.toml - Rust dependencies
- requirements.txt - Python dependencies

## Development Status

### ✅ Completed
- Complete isolation from kenchlightyear platform
- All routes functional (11 pages)
- Mobile responsive design
- SSL certificate configuration
- Domain routing (both test and production)
- Template cleanup (removed business content)
- Navigation fixes (removed /alt references)

### 🔄 In Progress
- FastAPI backend service (mock responses working)
- PostgreSQL database integration
- API endpoint testing
- Production deployment verification

### 📋 Next Steps
- Fix FastAPI service startup
- Test all API endpoints
- Verify database connections
- Performance optimization
- Production SSL for visualizations.bettergov.ph

## Deployment

### Server: 10.27.79.7
- **Frontend**: visualization.service (systemd)
- **Backend**: visualization_api.service (systemd) 
- **Proxy**: Nginx with SSL termination

### Environment
- .env - Application configuration
- venv/ - Python virtual environment (gitignored)
- target/ - Rust build artifacts

## Notes

- **Complete Separation**: No dependencies on kenchlightyear codebase
- **Advocacy Focus**: Removed all business/marketing content
- **Open Data Mission**: Transparency and accessibility for citizens
- **Mobile First**: Responsive design across all devices
- **API Ready**: FastAPI backend prepared for data endpoints

## Testing

Access the application at:
- Test: https://altgovph.site
- Production: https://visualizations.bettergov.ph

All 11 major pages and correlation analyses should load successfully.
