#!/usr/bin/env python3
"""
Generate static PNG flag files for each dynasty
"""

import json
import os
import hashlib
from datetime import datetime
from PIL import Image, ImageDraw
import io

def create_flag_svg(flag_params, dynasty_id, surname):
    """Create SVG flag from parameters"""
    
    slices = flag_params['slices']
    orientation = flag_params['orientation']
    shape_sequence = flag_params['shape_sequence']
    color_scheme = flag_params['color_scheme']
    symbol = flag_params.get('symbol')
    variation = flag_params['variation']
    is_czech_style = flag_params['is_czech_style']
    
    # Create SVG
    svg_content = f'''<svg width="100" height="60" viewBox="0 0 100 60" xmlns="http://www.w3.org/2000/svg">
    <defs>
        <style>
            .flag-slice {{ stroke: #333; stroke-width: 0.5; }}
            .flag-symbol {{ fill: #000; stroke: #fff; stroke-width: 0.5; }}
        </style>
    </defs>
'''
    
    # Create flag slices
    slice_width = 100 / slices
    slice_height = 60
    
    for i in range(slices):
        x = i * slice_width
        y = 0
        width = slice_width
        height = slice_height
        
        # Get shape and color
        shape = shape_sequence[i] if i < len(shape_sequence) else 'rectangle'
        color = color_scheme[i] if i < len(color_scheme) else '#FF6B6B'
        
        # Create slice based on shape
        if shape == 'triangle' or is_czech_style:
            # Triangle slice
            points = f"{x},{y} {x+width},{y} {x+width/2},{y+height}"
            svg_content += f'    <polygon points="{points}" fill="{color}" class="flag-slice"/>\n'
        elif shape == 'horizontal-rectangle':
            # Horizontal rectangle
            svg_content += f'    <rect x="{x}" y="{y}" width="{width}" height="{height}" fill="{color}" class="flag-slice"/>\n'
        else:
            # Default rectangle
            svg_content += f'    <rect x="{x}" y="{y}" width="{width}" height="{height}" fill="{color}" class="flag-slice"/>\n'
    
    # Add symbol if present
    if symbol and symbol != 'None':
        symbol_x = 50
        symbol_y = 30
        symbol_size = 15
        
        if symbol == 'circle':
            svg_content += f'    <circle cx="{symbol_x}" cy="{symbol_y}" r="{symbol_size}" class="flag-symbol"/>\n'
        elif symbol == 'cross':
            svg_content += f'    <g class="flag-symbol">\n'
            svg_content += f'        <line x1="{symbol_x-symbol_size}" y1="{symbol_y}" x2="{symbol_x+symbol_size}" y2="{symbol_y}"/>\n'
            svg_content += f'        <line x1="{symbol_x}" y1="{symbol_y-symbol_size}" x2="{symbol_x}" y2="{symbol_y+symbol_size}"/>\n'
            svg_content += f'    </g>\n'
        elif symbol == 'star':
            # Simple 5-pointed star
            star_points = f"{symbol_x},{symbol_y-symbol_size} {symbol_x+4},{symbol_y-4} {symbol_x+symbol_size},{symbol_y} {symbol_x+4},{symbol_y+4} {symbol_x},{symbol_y+symbol_size} {symbol_x-4},{symbol_y+4} {symbol_x-symbol_size},{symbol_y} {symbol_x-4},{symbol_y-4}"
            svg_content += f'    <polygon points="{star_points}" class="flag-symbol"/>\n'
        elif symbol == 'diamond':
            diamond_points = f"{symbol_x},{symbol_y-symbol_size} {symbol_x+symbol_size},{symbol_y} {symbol_x},{symbol_y+symbol_size} {symbol_x-symbol_size},{symbol_y}"
            svg_content += f'    <polygon points="{diamond_points}" class="flag-symbol"/>\n'
        elif symbol == 'triangle':
            triangle_points = f"{symbol_x},{symbol_y-symbol_size} {symbol_x+symbol_size},{symbol_y+symbol_size} {symbol_x-symbol_size},{symbol_y+symbol_size}"
            svg_content += f'    <polygon points="{triangle_points}" class="flag-symbol"/>\n'
        elif symbol == 'square':
            svg_content += f'    <rect x="{symbol_x-symbol_size/2}" y="{symbol_y-symbol_size/2}" width="{symbol_size}" height="{symbol_size}" class="flag-symbol"/>\n'
        elif symbol == 'hexagon':
            hex_points = f"{symbol_x},{symbol_y-symbol_size} {symbol_x+symbol_size*0.866},{symbol_y-symbol_size/2} {symbol_x+symbol_size*0.866},{symbol_y+symbol_size/2} {symbol_x},{symbol_y+symbol_size} {symbol_x-symbol_size*0.866},{symbol_y+symbol_size/2} {symbol_x-symbol_size*0.866},{symbol_y-symbol_size/2}"
            svg_content += f'    <polygon points="{hex_points}" class="flag-symbol"/>\n'
        elif symbol == 'arrow':
            arrow_points = f"{symbol_x-symbol_size},{symbol_y} {symbol_x+symbol_size},{symbol_y} {symbol_x+symbol_size/2},{symbol_y-symbol_size/2} {symbol_x+symbol_size},{symbol_y} {symbol_x+symbol_size/2},{symbol_y+symbol_size/2}"
            svg_content += f'    <polygon points="{arrow_points}" class="flag-symbol"/>\n'
        elif symbol == 'heart':
            # Simple heart shape
            heart_path = f"M{symbol_x},{symbol_y+symbol_size/2} C{symbol_x-symbol_size/2},{symbol_y} {symbol_x-symbol_size},{symbol_y+symbol_size/4} {symbol_x-symbol_size},{symbol_y+symbol_size/2} C{symbol_x-symbol_size},{symbol_y+symbol_size*0.75} {symbol_x-symbol_size/2},{symbol_y+symbol_size} {symbol_x},{symbol_y+symbol_size} C{symbol_x+symbol_size/2},{symbol_y+symbol_size} {symbol_x+symbol_size},{symbol_y+symbol_size*0.75} {symbol_x+symbol_size},{symbol_y+symbol_size/2} C{symbol_x+symbol_size},{symbol_y+symbol_size/4} {symbol_x+symbol_size/2},{symbol_y} {symbol_x},{symbol_y+symbol_size/2} Z"
            svg_content += f'    <path d="{heart_path}" class="flag-symbol"/>\n'
        elif symbol == 'crescent':
            # Crescent moon
            svg_content += f'    <path d="M{symbol_x-symbol_size/2},{symbol_y} A{symbol_size/2},{symbol_size/2} 0 0,1 {symbol_x+symbol_size/2},{symbol_y} A{symbol_size/3},{symbol_size/3} 0 0,0 {symbol_x-symbol_size/2},{symbol_y} Z" class="flag-symbol"/>\n'
    
    svg_content += '</svg>'
    return svg_content

def generate_static_flags():
    """Generate static SVG files for all dynasty flags"""
    
    # Load flag cache
    cache_file = "static/data/dynasty_flags_cache.json"
    if not os.path.exists(cache_file):
        print("❌ Flag cache not found. Please run generate_dynasty_flags.py first.")
        return
    
    with open(cache_file, 'r', encoding='utf-8') as f:
        flag_data = json.load(f)
    
    # Create flags directory
    flags_dir = "static/flags"
    os.makedirs(flags_dir, exist_ok=True)
    
    print("🏴 Generating static flag SVG files...")
    print(f"📊 Total dynasties: {flag_data['summary']['total_dynasties']}")
    
    generated_count = 0
    error_count = 0
    
    for location_key, dynasty in flag_data['dynasties'].items():
        try:
            if 'flag_parameters' in dynasty:
                # Generate SVG content
                svg_content = create_flag_svg(
                    dynasty['flag_parameters'],
                    dynasty['dynasty_id'],
                    dynasty['surname']
                )
                
                # Save SVG file
                flag_filename = f"flag_{dynasty['dynasty_id']}.svg"
                flag_path = os.path.join(flags_dir, flag_filename)
                
                with open(flag_path, 'w', encoding='utf-8') as f:
                    f.write(svg_content)
                
                generated_count += 1
                
                if generated_count % 1000 == 0:
                    print(f"✅ Generated {generated_count} flags...")
                    
            else:
                print(f"⚠️ No flag parameters for {dynasty['surname']} ({location_key})")
                error_count += 1
                
        except Exception as e:
            print(f"❌ Error generating flag for {dynasty['surname']}: {e}")
            error_count += 1
    
    # Create index file
    index_data = {
        "summary": {
            "total_flags": generated_count,
            "errors": error_count,
            "last_generated": datetime.now().isoformat(),
            "version": "1.0"
        },
        "flags": {}
    }
    
    # Add flag mappings
    for location_key, dynasty in flag_data['dynasties'].items():
        if 'flag_parameters' in dynasty:
            index_data["flags"][dynasty['dynasty_id']] = {
                "filename": f"flag_{dynasty['dynasty_id']}.svg",
                "surname": dynasty['surname'],
                "location": dynasty['location_display'],
                "location_key": location_key
            }
    
    # Save index
    index_path = os.path.join(flags_dir, "index.json")
    with open(index_path, 'w', encoding='utf-8') as f:
        json.dump(index_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Flag generation complete!")
    print(f"📊 Generated: {generated_count} flags")
    print(f"❌ Errors: {error_count}")
    print(f"📁 Flags directory: {flags_dir}")
    print(f"📄 Index file: {index_path}")

if __name__ == "__main__":
    generate_static_flags()
