/**
 * Dynasty Heatmap with Flag Integration
 * Combines the heatmap visualization with unique dynasty flags
 */

class DynastyHeatmapWithFlags {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.flagGenerator = new DynastyFlagGenerator();
        this.dynasties = [];
        this.flags = [];
        this.map = null;
        this.heatmapLayer = null;
        this.flagLayer = null;
    }

    /**
     * Initialize the heatmap with flags
     */
    async initialize() {
        await this.loadDynastyData();
        this.generateFlags();
        this.createMap();
        this.createHeatmap();
        this.createFlagLayer();
        this.createLegend();
    }

    /**
     * Load dynasty data from API
     */
    async loadDynastyData() {
        try {
            const response = await fetch('/api/dynasties');
            this.dynasties = await response.json();
            console.log(`Loaded ${this.dynasties.length} dynasties`);
        } catch (error) {
            console.error('Error loading dynasty data:', error);
            this.dynasties = [];
        }
    }

    /**
     * Generate flags for all dynasties
     */
    generateFlags() {
        this.flags = this.flagGenerator.generateAllFlags(this.dynasties);
        console.log(`Generated ${this.flags.length} unique flags`);
    }

    /**
     * Create Leaflet map
     */
    createMap() {
        this.map = L.map(this.container).setView([12.8797, 121.7740], 6);
        
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap contributors'
        }).addTo(this.map);
    }

    /**
     * Create heatmap layer
     */
    createHeatmap() {
        const heatmapData = this.dynasties.map(dynasty => ({
            lat: dynasty.latitude,
            lng: dynasty.longitude,
            intensity: dynasty.influence_score || 1
        }));

        this.heatmapLayer = L.heatLayer(heatmapData, {
            radius: 25,
            blur: 15,
            maxZoom: 17,
            max: 1.0,
            gradient: {
                0.4: 'blue',
                0.6: 'cyan',
                0.7: 'lime',
                0.8: 'yellow',
                1.0: 'red'
            }
        }).addTo(this.map);
    }

    /**
     * Create flag layer with custom markers
     */
    createFlagLayer() {
        this.flagLayer = L.layerGroup();
        
        this.dynasties.forEach((dynasty, index) => {
            const flag = this.flags[index];
            const marker = this.createFlagMarker(dynasty, flag);
            this.flagLayer.addLayer(marker);
        });
        
        this.flagLayer.addTo(this.map);
    }

    /**
     * Create custom flag marker
     */
    createFlagMarker(dynasty, flag) {
        const marker = L.marker([dynasty.latitude, dynasty.longitude], {
            icon: L.divIcon({
                html: `
                    <div class="dynasty-flag-marker" data-dynasty-id="${dynasty.id}">
                        ${flag.svg}
                    </div>
                `,
                className: 'custom-flag-marker',
                iconSize: [40, 40],
                iconAnchor: [20, 20]
            })
        });

        // Add popup with dynasty information
        const popupContent = `
            <div class="dynasty-popup">
                <h3>${dynasty.name}</h3>
                <div class="flag-preview">${flag.svg}</div>
                <p><strong>Province:</strong> ${dynasty.province}</p>
                <p><strong>Influence Score:</strong> ${dynasty.influence_score || 'N/A'}</p>
                <p><strong>Flag:</strong> ${flag.slices} slices, ${flag.shape}</p>
                <p><strong>Members:</strong> ${dynasty.member_count || 0}</p>
            </div>
        `;
        
        marker.bindPopup(popupContent);
        return marker;
    }

    /**
     * Create legend with flags
     */
    createLegend() {
        const legend = this.flagGenerator.createFlagLegend(this.flags);
        legend.style.position = 'absolute';
        legend.style.top = '10px';
        legend.style.right = '10px';
        legend.style.zIndex = '1000';
        
        this.container.appendChild(legend);
    }

    /**
     * Toggle heatmap visibility
     */
    toggleHeatmap() {
        if (this.map.hasLayer(this.heatmapLayer)) {
            this.map.removeLayer(this.heatmapLayer);
        } else {
            this.map.addLayer(this.heatmapLayer);
        }
    }

    /**
     * Toggle flag visibility
     */
    toggleFlags() {
        if (this.map.hasLayer(this.flagLayer)) {
            this.map.removeLayer(this.flagLayer);
        } else {
            this.map.addLayer(this.flagLayer);
        }
    }

    /**
     * Filter dynasties by province
     */
    filterByProvince(province) {
        this.flagLayer.clearLayers();
        
        const filteredDynasties = this.dynasties.filter(d => d.province === province);
        
        filteredDynasties.forEach((dynasty, index) => {
            const flag = this.flags.find(f => f.id === dynasty.id);
            if (flag) {
                const marker = this.createFlagMarker(dynasty, flag);
                this.flagLayer.addLayer(marker);
            }
        });
    }

    /**
     * Get flag statistics
     */
    getFlagStatistics() {
        const stats = {
            totalFlags: this.flags.length,
            shapes: {},
            sliceDistribution: {},
            colorUsage: {}
        };

        this.flags.forEach(flag => {
            // Count shapes
            stats.shapes[flag.shape] = (stats.shapes[flag.shape] || 0) + 1;
            
            // Count slices
            stats.sliceDistribution[flag.slices] = (stats.sliceDistribution[flag.slices] || 0) + 1;
            
            // Count colors
            flag.colors.forEach(color => {
                stats.colorUsage[color] = (stats.colorUsage[color] || 0) + 1;
            });
        });

        return stats;
    }

    /**
     * Export flags as JSON
     */
    exportFlags() {
        const exportData = this.flags.map(flag => ({
            id: flag.id,
            name: flag.name,
            slices: flag.slices,
            shape: flag.shape,
            variation: flag.variation,
            colors: flag.colors,
            svg: flag.svg
        }));
        
        const blob = new Blob([JSON.stringify(exportData, null, 2)], {type: 'application/json'});
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'dynasty-flags.json';
        a.click();
        URL.revokeObjectURL(url);
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    const heatmap = new DynastyHeatmapWithFlags('dynasty-heatmap-container');
    heatmap.initialize();
    
    // Add control buttons
    const controls = document.createElement('div');
    controls.innerHTML = `
        <div style="position: absolute; top: 10px; left: 10px; z-index: 1000;">
            <button onclick="heatmap.toggleHeatmap()">Toggle Heatmap</button>
            <button onclick="heatmap.toggleFlags()">Toggle Flags</button>
            <button onclick="heatmap.exportFlags()">Export Flags</button>
        </div>
    `;
    document.body.appendChild(controls);
    
    // Make heatmap globally accessible
    window.heatmap = heatmap;
});
