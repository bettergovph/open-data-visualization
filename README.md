# 🇵🇭 DPWH Archive Data Visualization

This project downloads, analyzes, and visualizes data from the Philippines Department of Public Works and Highways (DPWH) archive hosted on Internet Archive.

## 📋 Overview

The DPWH archive contains approximately 60GB of data across 31 zip files, representing a comprehensive dataset of public works and infrastructure information from the Philippines government.

## 🚀 Quick Start

### Prerequisites

- Python 3.7+
- Internet connection for downloading
- Sufficient disk space (~60GB for full download)

### Installation

1. Clone or download this repository
2. Install dependencies:
```bash
pip install -r requirements.txt
```

### Running the Pipeline

Execute the complete data pipeline:
```bash
python dpwh_pipeline_runner.py
```

This will:
1. Download all 31 zip files (~60GB)
2. Extract and analyze the data structure
3. Generate interactive visualizations
4. Create an HTML report

## 📁 Project Structure

```
open-data-visualization/
├── dpwh_archive_downloader.py  # Downloads all archive files
├── dpwh_archive_analyzer.py    # Extracts and analyzes data
├── dpwh_data_visualizer.py     # Creates visualizations
├── dpwh_pipeline_runner.py     # Main orchestration script
├── requirements.txt            # Python dependencies
└── README.md                   # This file
```

## 🔧 Individual Scripts

### Download Script
```bash
python dpwh_archive_downloader.py
```
- Downloads all 31 zip files from Internet Archive
- Creates `dpwh_archive/` directory
- Shows progress for each download
- Handles resume for interrupted downloads

### Analysis Script
```bash
python dpwh_archive_analyzer.py
```
- Extracts all zip files to `dpwh_archive/extracted/`
- Analyzes file structure and types
- Examines metadata files (XML, SQLite)
- Samples data files for content analysis
- Generates `data_summary.json`

### Visualization Script
```bash
python dpwh_data_visualizer.py
```
- Creates interactive charts and graphs
- Generates comprehensive HTML report
- Shows file type distributions
- Displays directory structure analysis

## 📊 Output Files

After running the pipeline, you'll find:

- `dpwh_archive/` - Downloaded zip files
- `dpwh_archive/extracted/` - Extracted data files
- `dpwh_archive/data_summary.json` - Analysis results
- `dpwh_analysis_report.html` - Interactive visualization report

## 🎯 Features

- **Comprehensive Download**: All 31 archive files with progress tracking
- **Smart Extraction**: Automatic zip file extraction with error handling
- **Data Analysis**: File type analysis, size distribution, metadata examination
- **Interactive Visualizations**: Plotly-based charts and graphs
- **HTML Report**: Self-contained report with embedded visualizations
- **Resume Capability**: Skip already downloaded files
- **Error Handling**: Robust error handling throughout the pipeline

## 📈 Visualizations

The generated report includes:

- File type distribution charts
- File size analysis by extension
- Directory structure overview
- Archive metadata summary
- Interactive data exploration tools

## 🔍 Data Insights

The DPWH archive contains various file types including:
- CSV files with infrastructure data
- PDF documents and reports
- Excel spreadsheets
- XML metadata files
- Database files (SQLite)
- Text documents

## 🛠️ Customization

You can modify the scripts to:
- Change download directory
- Adjust visualization parameters
- Add custom data analysis
- Modify report styling
- Add new file type handlers

## 📝 Notes

- The download process may take several hours depending on your internet connection
- Ensure you have sufficient disk space (60GB+ recommended)
- The analysis process may take time for large datasets
- All scripts include progress indicators and error handling

## 🤝 Contributing

Feel free to submit issues, feature requests, or pull requests to improve this data visualization pipeline.

## 📄 License

This project is for educational and research purposes. Please respect the Internet Archive's terms of service and the DPWH's data usage policies.

---

**Last Updated**: October 2025