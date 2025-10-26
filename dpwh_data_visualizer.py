#!/usr/bin/env python3
"""
Data visualization tools for DPWH archive
Creates interactive visualizations of the downloaded data
"""

import os
import json
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np

def load_data_summary(archive_dir):
    """Load the data summary created by the analysis script"""
    summary_file = Path(archive_dir) / "data_summary.json"
    
    if not summary_file.exists():
        print("Data summary not found. Please run analyze_dpwh_archive.py first.")
        return None
    
    with open(summary_file, 'r') as f:
        return json.load(f)

def create_file_type_visualization(summary):
    """Create visualization of file types distribution"""
    file_types = summary['file_types']
    
    # Filter out empty extensions and get top 15
    filtered_types = {k: v for k, v in file_types.items() if k and v > 0}
    top_types = dict(sorted(filtered_types.items(), key=lambda x: x[1], reverse=True)[:15])
    
    # Create bar chart
    fig = px.bar(
        x=list(top_types.keys()),
        y=list(top_types.values()),
        title="File Types Distribution in DPWH Archive",
        labels={'x': 'File Extension', 'y': 'Number of Files'},
        color=list(top_types.values()),
        color_continuous_scale='viridis'
    )
    
    fig.update_layout(
        xaxis_tickangle=-45,
        height=600,
        showlegend=False
    )
    
    return fig

def create_size_distribution_visualization(summary):
    """Create visualization of file size distribution"""
    file_sizes = summary['extraction_results']['file_sizes']
    
    # Calculate total sizes by extension
    total_sizes = {}
    for ext, sizes in file_sizes.items():
        total_sizes[ext] = sum(sizes) / (1024 * 1024)  # Convert to MB
    
    # Get top 10 by total size
    top_sizes = dict(sorted(total_sizes.items(), key=lambda x: x[1], reverse=True)[:10])
    
    # Create pie chart
    fig = px.pie(
        values=list(top_sizes.values()),
        names=list(top_sizes.keys()),
        title="File Size Distribution by Type (MB)"
    )
    
    return fig

def create_directory_structure_visualization(extract_dir):
    """Create a tree-like visualization of directory structure"""
    extract_path = Path(extract_dir)
    
    # Get directory structure
    dirs = []
    for root, dirnames, filenames in os.walk(extract_path):
        level = root.replace(str(extract_path), '').count(os.sep)
        indent = ' ' * 2 * level
        dirs.append(f"{indent}{os.path.basename(root)}/ ({len(filenames)} files)")
    
    return dirs[:50]  # Limit to first 50 directories

def create_data_overview_dashboard(summary, extract_dir):
    """Create a comprehensive dashboard"""
    # Create subplots
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=('File Types Distribution', 'File Size Distribution', 
                       'Archive Overview', 'Directory Structure'),
        specs=[[{"type": "bar"}, {"type": "pie"}],
               [{"type": "table"}, {"type": "bar"}]]
    )
    
    # File types bar chart
    file_types = summary['file_types']
    filtered_types = {k: v for k, v in file_types.items() if k and v > 0}
    top_types = dict(sorted(filtered_types.items(), key=lambda x: x[1], reverse=True)[:10])
    
    fig.add_trace(
        go.Bar(x=list(top_types.keys()), y=list(top_types.values()), name="File Types"),
        row=1, col=1
    )
    
    # File size pie chart
    file_sizes = summary['extraction_results']['file_sizes']
    total_sizes = {}
    for ext, sizes in file_sizes.items():
        total_sizes[ext] = sum(sizes) / (1024 * 1024)  # Convert to MB
    
    top_sizes = dict(sorted(total_sizes.items(), key=lambda x: x[1], reverse=True)[:8])
    
    fig.add_trace(
        go.Pie(labels=list(top_sizes.keys()), values=list(top_sizes.values()), name="File Sizes"),
        row=1, col=2
    )
    
    # Archive overview table
    overview_data = [
        ['Total Files', summary['total_files']],
        ['Total Directories', summary['total_directories']],
        ['File Types', len(summary['file_types'])],
        ['Archive Size', '~60GB'],
        ['Zip Files', '31']
    ]
    
    fig.add_trace(
        go.Table(
            header=dict(values=['Metric', 'Value']),
            cells=dict(values=list(zip(*overview_data)))
        ),
        row=2, col=1
    )
    
    # Directory structure (simplified)
    extract_path = Path(extract_dir)
    dir_counts = {}
    for root, dirnames, filenames in os.walk(extract_path):
        if len(dirnames) > 0:
            dir_counts[root.split('/')[-1]] = len(filenames)
    
    top_dirs = dict(sorted(dir_counts.items(), key=lambda x: x[1], reverse=True)[:10])
    
    fig.add_trace(
        go.Bar(x=list(top_dirs.keys()), y=list(top_dirs.values()), name="Files per Directory"),
        row=2, col=2
    )
    
    fig.update_layout(height=800, title_text="DPWH Archive Data Overview Dashboard")
    
    return fig

def generate_html_report(summary, extract_dir, output_file="dpwh_analysis_report.html"):
    """Generate a comprehensive HTML report"""
    
    # Create visualizations
    file_type_fig = create_file_type_visualization(summary)
    size_fig = create_size_distribution_visualization(summary)
    dashboard_fig = create_data_overview_dashboard(summary, extract_dir)
    
    # Generate HTML
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>DPWH Archive Analysis Report</title>
        <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            .header {{ background-color: #f0f0f0; padding: 20px; border-radius: 5px; }}
            .section {{ margin: 20px 0; }}
            .metric {{ display: inline-block; margin: 10px; padding: 10px; background-color: #e8f4f8; border-radius: 5px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🇵🇭 DPWH Archive Analysis Report</h1>
            <p>Department of Public Works and Highways - Philippines</p>
            <p>Archive Date: {summary['archive_info']['archive_date']}</p>
        </div>
        
        <div class="section">
            <h2>📊 Archive Overview</h2>
            <div class="metric">Total Files: {summary['total_files']:,}</div>
            <div class="metric">Total Directories: {summary['total_directories']:,}</div>
            <div class="metric">File Types: {len(summary['file_types'])}</div>
            <div class="metric">Archive Size: {summary['archive_info']['total_size_gb']}</div>
        </div>
        
        <div class="section">
            <h2>📈 Data Visualizations</h2>
            <div id="dashboard"></div>
            <div id="filetypes"></div>
            <div id="sizes"></div>
        </div>
        
        <div class="section">
            <h2>📁 File Types Found</h2>
            <ul>
    """
    
    # Add file types list
    for ext, count in sorted(summary['file_types'].items(), key=lambda x: x[1], reverse=True)[:20]:
        html_content += f"<li>{ext or '(no extension)'}: {count:,} files</li>\n"
    
    html_content += """
            </ul>
        </div>
        
        <script>
    """
    
    # Add Plotly visualizations
    html_content += f"""
            Plotly.newPlot('dashboard', {dashboard_fig.to_json()['data']}, {dashboard_fig.to_json()['layout']});
            Plotly.newPlot('filetypes', {file_type_fig.to_json()['data']}, {file_type_fig.to_json()['layout']});
            Plotly.newPlot('sizes', {size_fig.to_json()['data']}, {size_fig.to_json()['layout']});
        </script>
    </body>
    </html>
    """
    
    # Save HTML file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"HTML report generated: {output_file}")
    return output_file

def main():
    archive_dir = "dpwh_archive"
    extract_dir = Path(archive_dir) / "extracted"
    
    # Load data summary
    summary = load_data_summary(archive_dir)
    if not summary:
        return
    
    print("Creating visualizations...")
    
    # Generate HTML report
    report_file = generate_html_report(summary, extract_dir)
    
    print(f"\n{'='*50}")
    print("Visualization Complete!")
    print(f"📊 Report generated: {report_file}")
    print(f"📁 Data location: {extract_dir}")
    print(f"📈 Total files visualized: {summary['total_files']:,}")

if __name__ == "__main__":
    main()
