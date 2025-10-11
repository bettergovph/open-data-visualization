# BetterGovPH Data Visualizations

This project contains the **BetterGovPH Data Visualizations** platform - a comprehensive open data visualization tool for Philippine government budget, infrastructure, and flood control projects.

## Project Status

✅ **FULLY ISOLATED** from kenchlightyear business platform  
✅ **RUNNING** on dedicated server (10.27.79.7)  
✅ **PRODUCTION READY** for   
✅ **TEST ACCESS** available at   

## Domains

- **Production**: 
- **Test/Transition**: 

## Architecture

### Frontend (Rust/Actix-Web)
- **Server**: 192.168.2.122:8888
- **Framework**: Actix-Web with Tera templating
- **Routes**: 11 major pages + correlation analysis
- **Mobile Support**: Responsive design with dedicated mobile templates

### Backend (Python/FastAPI) 
- **Server**: 192.168.2.122:8000 (currently being fixed)
- **Framework**: FastAPI with async PostgreSQL
- **Database**: Government budget and infrastructure data
- **Status**: Syntax errors resolved, database connection in progress

### Reverse Proxy (Nginx)
- **Ports**: 80/443
- **SSL**: Let's Encrypt certificates
- **Load Balancing**: API requests proxied to FastAPI backend

## Routes and Functionality

### / (Homepage)
- **Templates**: , 
- **Functionality**: Landing page with navigation to all data sections

### /budget (Budget Analysis)
- **Templates**: , 
- **Functionality**: AI-powered analysis of Government Appropriations Act (GAA) data
- **Features**: Intelligent insights, duplicate detection, trend analysis

### /flood (Flood Control Projects)
- **Templates**: , 
- **Functionality**: Comprehensive tracking of DPWH flood control infrastructure
- **Features**: Nationwide project mapping and analysis

### /dime (DIME Infrastructure)
- **Templates**: , 
- **Functionality**: Digital Information for Monitoring and Evaluation
- **Features**: 12,870+ major infrastructure projects worth ₱740B+

### /nep (NEP Analysis)
- **Templates**: , 
- **Functionality**: National Expenditure Program analysis
- **Features**: AI-powered insights, duplicate detection, budget tracking

### /map (Interactive Map)
- **Templates**: , 
- **Functionality**: Interactive geographical visualization
- **Features**: Flood control projects and infrastructure mapping

### /about (About Page)
- **Templates**: , 
- **Functionality**: Project information and advocacy focus

### Correlation Analysis
- **Budget-NEP**: 
- **Budget-Flood**: 
- **Flood-DIME**: 
- **Templates**: Individual correlation analysis pages
- **Functionality**: Data science connections between datasets

## File Structure

### Templates
-  - Main homepage
-  - Base template for desktop pages
-  - Legacy base template
-  - Mobile-optimized versions of all templates

### Static Assets
-  - Stylesheets (altgovph-theme.css, mobile styles)
-  - JavaScript functionality
-  - Logos and assets
-  - JSON datasets for visualizations

### Source Code
-  - Actix-Web frontend application
-  - FastAPI backend (under development)
-  - Rust dependencies
-  - Python dependencies

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
- FastAPI backend service (syntax errors resolved)
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
- **Frontend**:  (systemd)
- **Backend**:  (systemd) 
- **Proxy**: Nginx with SSL termination

### Environment
-  - Application configuration
-  - Python virtual environment
-  - Rust build artifacts

## Notes

- **Complete Separation**: No dependencies on kenchlightyear codebase
- **Advocacy Focus**: Removed all business/marketing content
- **Open Data Mission**: Transparency and accessibility for citizens
- **Mobile First**: Responsive design across all devices
- **API Ready**: FastAPI backend prepared for data endpoints

## Testing

Access the application at:
- Test: 
- Production: 

All 11 major pages and correlation analyses should load successfully.
