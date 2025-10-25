/**
 * Dynasty Flag Generator
 * Creates unique visual flags for each political dynasty
 * 10 colors × 10 slices × 3 shapes × 10 variations = 3,000 combinations
 */

class DynastyFlagGenerator {
    constructor() {
        this.colors = [
            '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7',
            '#DDA0DD', '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E9'
        ];
        
        this.shapes = ['rectangle', 'horizontal-rectangle'];
        this.czechShapes = ['triangle']; // Czech style uses triangles
        this.symbols = ['circle', 'cross', 'crescent', 'star', 'diamond', 'triangle', 'square', 'hexagon', 'arrow', 'heart'];
        this.sliceOrientations = ['vertical', 'horizontal', 'diagonal-right', 'diagonal-left'];
        this.maxSlices = 10;
        this.maxVariations = 10;
    }

    /**
     * Generate a unique flag for a dynasty based on its ID
     */
    generateFlag(dynastyId, dynastyName) {
        // Use dynasty ID to ensure consistent flags
        const seed = this.hashString(dynastyName + dynastyId);
        
        // Create seeded random number generator
        const rng = this.createSeededRNG(seed);
        
        // Generate random number of slices with better distribution
        // Use weighted random to favor 2-8 slices (more interesting flags)
        const sliceWeights = [1, 3, 4, 4, 4, 4, 4, 4, 3, 1]; // Weights for 1-10 slices
        const totalWeight = sliceWeights.reduce((sum, weight) => sum + weight, 0);
        let randomValue = rng() * totalWeight;
        
        let numSlices = 1;
        for (let i = 0; i < sliceWeights.length; i++) {
            randomValue -= sliceWeights[i];
            if (randomValue <= 0) {
                numSlices = i + 1;
                break;
            }
        }
        
        // Generate random variation
        const variation = Math.floor(rng() * this.maxVariations);
        
        // Randomly decide if this should be a Czech-style flag (50% chance for testing)
        const isCzechStyle = rng() < 0.5;
        console.log(`Flag ${dynastyId} (${dynastyName}): ${isCzechStyle ? 'Czech Style' : 'Regular Style'}`);
        
        // Generate shape sequence based on style
        const shapeSequence = isCzechStyle ? 
            this.generateCzechShapeSequence(numSlices, seed) : 
            this.generateShapeSequence(numSlices, seed);
        
        // Generate symbol overlay (optional) - more randomization
        const hasSymbol = rng() > 0.4; // 60% chance of having a symbol
        const symbol = hasSymbol ? this.symbols[Math.floor(rng() * this.symbols.length)] : null;
        
        // Generate slice orientation
        const orientation = this.sliceOrientations[Math.floor(rng() * this.sliceOrientations.length)];
        
        return {
            id: dynastyId,
            name: dynastyName,
            slices: numSlices,
            shape: shapeSequence[0], // First shape for compatibility
            shapeSequence: shapeSequence, // Full sequence of shapes
            symbol: symbol, // Overlay symbol
            orientation: orientation, // Slice orientation
            variation: variation,
            colors: this.generateColorScheme(seed, numSlices),
            svg: this.createSVGFlag(numSlices, shapeSequence[0], variation, seed, symbol, orientation)
        };
    }

    /**
     * Generate color scheme for the flag
     */
    generateColorScheme(seed, numSlices) {
        const colors = [];
        const usedColors = new Set();
        
        for (let i = 0; i < numSlices; i++) {
            let colorIndex;
            do {
                colorIndex = (seed + i * 7) % this.colors.length;
            } while (usedColors.has(colorIndex) && usedColors.size < this.colors.length);
            
            usedColors.add(colorIndex);
            colors.push(this.colors[colorIndex]);
        }
        
        return colors;
    }

    /**
     * Create SVG flag based on parameters
     */
    createSVGFlag(slices, shape, variation, seed, symbol = null, orientation = 'vertical') {
        const size = 40;
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('width', size);
        svg.setAttribute('height', size);
        svg.setAttribute('viewBox', `0 0 ${size} ${size}`);
        
        // Generate shape sequence avoiding consecutive identical shapes
        const shapeSequence = this.generateShapeSequence(slices, seed);
        const colors = this.generateColorScheme(seed, slices);
        
        // Create flag slices based on orientation
        const flagSlices = this.createOrientedSlices(slices, size, shapeSequence, colors, variation, orientation);
        flagSlices.forEach(slice => svg.appendChild(slice));
        
        // Add symbol overlay if present
        if (symbol) {
            const symbolElement = this.createSymbolOverlay(symbol, size, variation, seed);
            svg.appendChild(symbolElement);
        }
        
        return svg.outerHTML;
    }

    /**
     * Generate Czech-style shape sequence (all triangles)
     */
    generateCzechShapeSequence(slices, seed) {
        // Czech flags use triangles, so return all triangles
        console.log(`Generating Czech style with ${slices} triangles`);
        return Array(slices).fill('triangle');
    }

    /**
     * Generate shape sequence avoiding consecutive identical shapes
     */
    generateShapeSequence(slices, seed) {
        const sequence = [];
        let lastShape = null;
        
        // Create a seeded random number generator for consistency
        const rng = this.createSeededRNG(seed);
        
        for (let i = 0; i < slices; i++) {
            let shapeIndex;
            let attempts = 0;
            
            do {
                // Use random number generator to pick shape
                shapeIndex = Math.floor(rng() * this.shapes.length);
                attempts++;
            } while (this.shapes[shapeIndex] === lastShape && attempts < 10);
            
            // If we still have the same shape after 10 attempts, just use it
            // (this handles edge cases with very few slices)
            const selectedShape = this.shapes[shapeIndex];
            sequence.push(selectedShape);
            lastShape = selectedShape;
        }
        
        return sequence;
    }

    /**
     * Create a seeded random number generator for consistent results
     */
    createSeededRNG(seed) {
        let currentSeed = seed;
        return function() {
            // Linear congruential generator
            currentSeed = (currentSeed * 1664525 + 1013904223) % Math.pow(2, 32);
            return currentSeed / Math.pow(2, 32);
        };
    }

    /**
     * Create oriented slices based on orientation type
     */
    createOrientedSlices(numSlices, size, shapeSequence, colors, variation, orientation) {
        const slices = [];
        
        switch (orientation) {
            case 'vertical':
                for (let i = 0; i < numSlices; i++) {
                    slices.push(this.createVerticalSlice(i, numSlices, size, shapeSequence[i], colors[i], variation));
                }
                break;
            case 'horizontal':
                for (let i = 0; i < numSlices; i++) {
                    slices.push(this.createHorizontalSlice(i, numSlices, size, shapeSequence[i], colors[i], variation));
                }
                break;
            case 'diagonal-right':
                for (let i = 0; i < numSlices; i++) {
                    slices.push(this.createDiagonalSlice(i, numSlices, size, shapeSequence[i], colors[i], variation, 'right'));
                }
                break;
            case 'diagonal-left':
                for (let i = 0; i < numSlices; i++) {
                    slices.push(this.createDiagonalSlice(i, numSlices, size, shapeSequence[i], colors[i], variation, 'left'));
                }
                break;
        }
        
        return slices;
    }

    /**
     * Create a proper flag slice with no gaps (vertical)
     */
    createVerticalSlice(index, totalSlices, size, shape, color, variation) {
        const sliceWidth = size / totalSlices;
        const x = index * sliceWidth;
        const y = 0;
        const width = sliceWidth;
        const height = size;
        
        return this.createFlagSlice(x, y, width, height, shape, color, variation);
    }

    /**
     * Create horizontal slice
     */
    createHorizontalSlice(index, totalSlices, size, shape, color, variation) {
        const sliceHeight = size / totalSlices;
        const x = 0;
        const y = index * sliceHeight;
        const width = size;
        const height = sliceHeight;
        
        return this.createFlagSlice(x, y, width, height, shape, color, variation);
    }

    /**
     * Create diagonal slice with straight lines
     */
    createDiagonalSlice(index, totalSlices, size, shape, color, variation, direction) {
        const sliceWidth = size / totalSlices;
        const x = index * sliceWidth;
        const y = direction === 'right' ? index * sliceWidth : (totalSlices - 1 - index) * sliceWidth;
        const width = sliceWidth;
        const height = size;
        
        const slice = this.createFlagSlice(x, y, width, height, shape, color, variation);
        
        // Add rigid diagonal rotation
        const rotation = direction === 'right' ? 45 : -45;
        slice.setAttribute('transform', `rotate(${rotation} ${x + width/2} ${y + height/2})`);
        
        return slice;
    }

    /**
     * Create radial slice (pie slices)
     */
    createRadialSlice(index, totalSlices, size, shape, color, variation) {
        const anglePerSlice = 360 / totalSlices;
        const startAngle = index * anglePerSlice;
        const endAngle = (index + 1) * anglePerSlice;
        const centerX = size / 2;
        const centerY = size / 2;
        const radius = size / 2;
        
        // Create pie slice path
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        const startX = centerX + radius * Math.cos(startAngle * Math.PI / 180);
        const startY = centerY + radius * Math.sin(startAngle * Math.PI / 180);
        const endX = centerX + radius * Math.cos(endAngle * Math.PI / 180);
        const endY = centerY + radius * Math.sin(endAngle * Math.PI / 180);
        
        const largeArcFlag = anglePerSlice > 180 ? 1 : 0;
        const pathData = `M ${centerX} ${centerY} L ${startX} ${startY} A ${radius} ${radius} 0 ${largeArcFlag} 1 ${endX} ${endY} Z`;
        
        path.setAttribute('d', pathData);
        path.setAttribute('fill', color);
        
        return path;
    }

    /**
     * Create a rigid flag slice with straight lines
     */
    createFlagSlice(x, y, width, height, shape, color, variation) {
        // Create a group for this slice
        const sliceGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        
        // Create perfectly straight background rectangle
        const background = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        background.setAttribute('x', x);
        background.setAttribute('y', y);
        background.setAttribute('width', width);
        background.setAttribute('height', height);
        background.setAttribute('fill', color);
        sliceGroup.appendChild(background);
        
        // Create rigid geometric shape with straight lines
        let shapeElement;
        switch (shape) {
            case 'triangle':
                shapeElement = this.createRigidTriangle(x, y, width, height, color);
                break;
            case 'rectangle':
                shapeElement = this.createRigidRectangle(x, y, width, height, color);
                break;
            case 'horizontal-rectangle':
                shapeElement = this.createRigidHorizontalRectangle(x, y, width, height, color);
                break;
        }
        
        if (shapeElement) {
            sliceGroup.appendChild(shapeElement);
        }
        
        return sliceGroup;
    }

    /**
     * Create symbol overlay with enhanced variety
     */
    createSymbolOverlay(symbol, size, variation, seed) {
        const overlayGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        
        // Create seeded RNG for consistent positioning
        const rng = this.createSeededRNG(seed);
        
        // Determine number of symbols (1-4) for more variety
        const numSymbols = Math.floor(rng() * 4) + 1;
        
        for (let i = 0; i < numSymbols; i++) {
            let symbolElement;
            
            switch (symbol) {
                case 'circle':
                    symbolElement = this.createOverlayCircle(size, variation, rng);
                    break;
                case 'cross':
                    symbolElement = this.createOverlayCross(size, variation, rng);
                    break;
                case 'crescent':
                    symbolElement = this.createOverlayCrescent(size, variation, rng);
                    break;
                case 'star':
                    symbolElement = this.createOverlayStar(size, variation, rng);
                    break;
                case 'diamond':
                    symbolElement = this.createOverlayDiamond(size, variation, rng);
                    break;
                case 'triangle':
                    symbolElement = this.createOverlayTriangle(size, variation, rng);
                    break;
                case 'square':
                    symbolElement = this.createOverlaySquare(size, variation, rng);
                    break;
                case 'hexagon':
                    symbolElement = this.createOverlayHexagon(size, variation, rng);
                    break;
                case 'arrow':
                    symbolElement = this.createOverlayArrow(size, variation, rng);
                    break;
                case 'heart':
                    symbolElement = this.createOverlayHeart(size, variation, rng);
                    break;
            }
            
            if (symbolElement) {
                overlayGroup.appendChild(symbolElement);
            }
        }
        
        return overlayGroup;
    }

    /**
     * Create overlay circle with enhanced randomization
     */
    createOverlayCircle(size, variation, rng) {
        const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        
        // Random position with margin (avoid edges)
        const margin = size * 0.1;
        const x = margin + rng() * (size - 2 * margin);
        const y = margin + rng() * (size - 2 * margin);
        
        // Random size (5-25% of flag size)
        const radius = (rng() * 0.2 + 0.05) * size;
        
        // Random color from our palette
        const colorIndex = Math.floor(rng() * this.colors.length);
        const color = this.colors[colorIndex];
        
        circle.setAttribute('cx', x);
        circle.setAttribute('cy', y);
        circle.setAttribute('r', radius);
        circle.setAttribute('fill', color);
        circle.setAttribute('opacity', 0.6 + rng() * 0.4);
        
        // Random rotation
        if (rng() > 0.5) {
            circle.setAttribute('transform', `rotate(${rng() * 360} ${x} ${y})`);
        }
        
        return circle;
    }

    /**
     * Create overlay cross
     */
    createOverlayCross(size, variation, rng) {
        const cross = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        
        // Random position
        const x = rng() * size;
        const y = rng() * size;
        const length = (rng() * 0.3 + 0.2) * size;
        const thickness = (rng() * 0.1 + 0.05) * size;
        
        // Random color
        const colorIndex = Math.floor(rng() * this.colors.length);
        const color = this.colors[colorIndex];
        
        // Horizontal bar
        const hBar = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        hBar.setAttribute('x', x - length/2);
        hBar.setAttribute('y', y - thickness/2);
        hBar.setAttribute('width', length);
        hBar.setAttribute('height', thickness);
        hBar.setAttribute('fill', color);
        hBar.setAttribute('opacity', 0.7 + rng() * 0.3);
        
        // Vertical bar
        const vBar = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        vBar.setAttribute('x', x - thickness/2);
        vBar.setAttribute('y', y - length/2);
        vBar.setAttribute('width', thickness);
        vBar.setAttribute('height', length);
        vBar.setAttribute('fill', color);
        vBar.setAttribute('opacity', 0.7 + rng() * 0.3);
        
        cross.appendChild(hBar);
        cross.appendChild(vBar);
        
        return cross;
    }

    /**
     * Create overlay crescent
     */
    createOverlayCrescent(size, variation, rng) {
        const crescent = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        
        // Random position
        const x = rng() * size;
        const y = rng() * size;
        const radius = (rng() * 0.2 + 0.1) * size;
        
        // Random color
        const colorIndex = Math.floor(rng() * this.colors.length);
        const color = this.colors[colorIndex];
        
        // Create crescent using two circles
        const outerCircle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        outerCircle.setAttribute('cx', x);
        outerCircle.setAttribute('cy', y);
        outerCircle.setAttribute('r', radius);
        outerCircle.setAttribute('fill', color);
        outerCircle.setAttribute('opacity', 0.7 + rng() * 0.3);
        
        const innerCircle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        innerCircle.setAttribute('cx', x + radius * 0.3);
        innerCircle.setAttribute('cy', y);
        innerCircle.setAttribute('r', radius * 0.8);
        innerCircle.setAttribute('fill', 'white');
        
        crescent.appendChild(outerCircle);
        crescent.appendChild(innerCircle);
        
        return crescent;
    }

    /**
     * Create overlay star
     */
    createOverlayStar(size, variation, rng) {
        const star = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
        
        // Random position with margin
        const margin = size * 0.1;
        const x = margin + rng() * (size - 2 * margin);
        const y = margin + rng() * (size - 2 * margin);
        const radius = (rng() * 0.2 + 0.05) * size;
        
        // Create 5-pointed star
        const points = [];
        for (let i = 0; i < 10; i++) {
            const angle = (i * Math.PI) / 5;
            const r = (i % 2 === 0) ? radius : radius * 0.4;
            const px = x + r * Math.cos(angle - Math.PI / 2);
            const py = y + r * Math.sin(angle - Math.PI / 2);
            points.push(`${px},${py}`);
        }
        
        star.setAttribute('points', points.join(' '));
        star.setAttribute('fill', this.colors[Math.floor(rng() * this.colors.length)]);
        star.setAttribute('opacity', 0.6 + rng() * 0.4);
        
        // Random rotation
        star.setAttribute('transform', `rotate(${rng() * 360} ${x} ${y})`);
        
        return star;
    }

    /**
     * Create overlay diamond
     */
    createOverlayDiamond(size, variation, rng) {
        const diamond = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
        
        // Random position with margin
        const margin = size * 0.1;
        const x = margin + rng() * (size - 2 * margin);
        const y = margin + rng() * (size - 2 * margin);
        const width = (rng() * 0.2 + 0.05) * size;
        const height = (rng() * 0.2 + 0.05) * size;
        
        const points = [
            `${x},${y - height/2}`,
            `${x + width/2},${y}`,
            `${x},${y + height/2}`,
            `${x - width/2},${y}`
        ].join(' ');
        
        diamond.setAttribute('points', points);
        diamond.setAttribute('fill', this.colors[Math.floor(rng() * this.colors.length)]);
        diamond.setAttribute('opacity', 0.6 + rng() * 0.4);
        
        // Random rotation
        diamond.setAttribute('transform', `rotate(${rng() * 360} ${x} ${y})`);
        
        return diamond;
    }

    /**
     * Create overlay triangle
     */
    createOverlayTriangle(size, variation, rng) {
        const triangle = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
        
        // Random position with margin
        const margin = size * 0.1;
        const x = margin + rng() * (size - 2 * margin);
        const y = margin + rng() * (size - 2 * margin);
        const side = (rng() * 0.2 + 0.05) * size;
        
        const points = [
            `${x},${y - side/2}`,
            `${x - side/2},${y + side/2}`,
            `${x + side/2},${y + side/2}`
        ].join(' ');
        
        triangle.setAttribute('points', points);
        triangle.setAttribute('fill', this.colors[Math.floor(rng() * this.colors.length)]);
        triangle.setAttribute('opacity', 0.6 + rng() * 0.4);
        
        // Random rotation
        triangle.setAttribute('transform', `rotate(${rng() * 360} ${x} ${y})`);
        
        return triangle;
    }

    /**
     * Create overlay square
     */
    createOverlaySquare(size, variation, rng) {
        const square = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        
        // Random position with margin
        const margin = size * 0.1;
        const x = margin + rng() * (size - 2 * margin);
        const y = margin + rng() * (size - 2 * margin);
        const side = (rng() * 0.2 + 0.05) * size;
        
        square.setAttribute('x', x - side/2);
        square.setAttribute('y', y - side/2);
        square.setAttribute('width', side);
        square.setAttribute('height', side);
        square.setAttribute('fill', this.colors[Math.floor(rng() * this.colors.length)]);
        square.setAttribute('opacity', 0.6 + rng() * 0.4);
        
        // Random rotation
        square.setAttribute('transform', `rotate(${rng() * 360} ${x} ${y})`);
        
        return square;
    }

    /**
     * Create overlay hexagon
     */
    createOverlayHexagon(size, variation, rng) {
        const hexagon = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
        
        // Random position with margin
        const margin = size * 0.1;
        const x = margin + rng() * (size - 2 * margin);
        const y = margin + rng() * (size - 2 * margin);
        const radius = (rng() * 0.2 + 0.05) * size;
        
        const points = [];
        for (let i = 0; i < 6; i++) {
            const angle = (i * Math.PI) / 3;
            const px = x + radius * Math.cos(angle);
            const py = y + radius * Math.sin(angle);
            points.push(`${px},${py}`);
        }
        
        hexagon.setAttribute('points', points.join(' '));
        hexagon.setAttribute('fill', this.colors[Math.floor(rng() * this.colors.length)]);
        hexagon.setAttribute('opacity', 0.6 + rng() * 0.4);
        
        // Random rotation
        hexagon.setAttribute('transform', `rotate(${rng() * 360} ${x} ${y})`);
        
        return hexagon;
    }

    /**
     * Create overlay arrow
     */
    createOverlayArrow(size, variation, rng) {
        const arrow = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
        
        // Random position with margin
        const margin = size * 0.1;
        const x = margin + rng() * (size - 2 * margin);
        const y = margin + rng() * (size - 2 * margin);
        const length = (rng() * 0.2 + 0.05) * size;
        const width = length * 0.3;
        
        const points = [
            `${x + length/2},${y}`,
            `${x - length/2},${y - width/2}`,
            `${x - length/2 + width/2},${y}`,
            `${x - length/2},${y + width/2}`
        ].join(' ');
        
        arrow.setAttribute('points', points);
        arrow.setAttribute('fill', this.colors[Math.floor(rng() * this.colors.length)]);
        arrow.setAttribute('opacity', 0.6 + rng() * 0.4);
        
        // Random rotation
        arrow.setAttribute('transform', `rotate(${rng() * 360} ${x} ${y})`);
        
        return arrow;
    }

    /**
     * Create overlay heart
     */
    createOverlayHeart(size, variation, rng) {
        const heart = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        
        // Random position with margin
        const margin = size * 0.1;
        const x = margin + rng() * (size - 2 * margin);
        const y = margin + rng() * (size - 2 * margin);
        const scale = (rng() * 0.2 + 0.05) * size;
        
        // Heart path
        const path = `M ${x},${y + scale/4} C ${x - scale/2},${y - scale/4} ${x - scale},${y - scale/4} ${x - scale},${y + scale/4} C ${x - scale},${y + scale/2} ${x},${y + scale} ${x},${y + scale} C ${x},${y + scale} ${x + scale},${y + scale/2} ${x + scale},${y + scale/4} C ${x + scale},${y - scale/4} ${x + scale/2},${y - scale/4} ${x},${y + scale/4} Z`;
        
        heart.setAttribute('d', path);
        heart.setAttribute('fill', this.colors[Math.floor(rng() * this.colors.length)]);
        heart.setAttribute('opacity', 0.6 + rng() * 0.4);
        
        // Random rotation
        heart.setAttribute('transform', `rotate(${rng() * 360} ${x} ${y})`);
        
        return heart;
    }

    /**
     * Create individual shape for the flag (legacy method)
     */
    createShape(shape, index, totalSlices, size, offsetX, offsetY, color, variation) {
        const element = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        
        // Calculate position and size based on slice - ensure no gaps
        const sliceSize = size / totalSlices;
        const x = (index * sliceSize) + offsetX;
        const y = offsetY;
        const width = sliceSize; // No gaps between slices
        const height = size - (offsetY * 2);
        
        let shapeElement;
        
        switch (shape) {
            case 'circle':
                shapeElement = this.createCircle(x, y, width, height, color, variation);
                break;
            case 'triangle':
                shapeElement = this.createTriangle(x, y, width, height, color, variation);
                break;
            case 'rectangle':
                shapeElement = this.createRectangle(x, y, width, height, color, variation);
                break;
            case 'horizontal-rectangle':
                shapeElement = this.createHorizontalRectangle(x, y, width, height, color, variation);
                break;
        }
        
        element.appendChild(shapeElement);
        return element;
    }

    /**
     * Create circle shape with size and position variations
     */
    createCircle(x, y, width, height, color, variation) {
        const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        
        // Size variations: big, medium, small
        const sizeVariations = [1.0, 0.8, 0.6]; // big, medium, small (max 1.0 to fit slice)
        const sizeIndex = variation % sizeVariations.length;
        const baseRadius = Math.min(width, height) / 2;
        const variationRadius = baseRadius * sizeVariations[sizeIndex];
        
        // Position variations: center, corners, edges
        const positionVariations = [
            { x: 0.5, y: 0.5 }, // center
            { x: 0.2, y: 0.2 }, // top-left corner
            { x: 0.8, y: 0.2 }, // top-right corner
            { x: 0.2, y: 0.8 }, // bottom-left corner
            { x: 0.8, y: 0.8 }, // bottom-right corner
            { x: 0.5, y: 0.2 }, // top edge
            { x: 0.5, y: 0.8 }, // bottom edge
            { x: 0.2, y: 0.5 }, // left edge
            { x: 0.8, y: 0.5 }  // right edge
        ];
        
        const posIndex = Math.floor(variation / 3) % positionVariations.length;
        const position = positionVariations[posIndex];
        
        const centerX = x + width * position.x;
        const centerY = y + height * position.y;
        
        circle.setAttribute('cx', centerX);
        circle.setAttribute('cy', centerY);
        circle.setAttribute('r', variationRadius);
        circle.setAttribute('fill', color);
        circle.setAttribute('opacity', 0.8 + (variation % 2) * 0.2);
        
        return circle;
    }

    /**
     * Create rigid triangle with straight lines (Czech flag style)
     */
    createRigidTriangle(x, y, width, height, color) {
        const triangle = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
        const centerX = x + width / 2;
        const centerY = y + height / 2;
        
        // Czech flag style triangle - pointing left
        const points = `${x + 5},${y + 5} ${x + 5},${y + height - 5} ${centerX},${centerY}`;
        
        triangle.setAttribute('points', points);
        triangle.setAttribute('fill', color);
        triangle.setAttribute('opacity', 0.9);
        
        return triangle;
    }

    /**
     * Create rigid rectangle with straight lines
     */
    createRigidRectangle(x, y, width, height, color) {
        const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        
        // Perfectly straight rectangle with small margin
        const margin = Math.min(width, height) * 0.1;
        rect.setAttribute('x', x + margin);
        rect.setAttribute('y', y + margin);
        rect.setAttribute('width', width - 2 * margin);
        rect.setAttribute('height', height - 2 * margin);
        rect.setAttribute('fill', color);
        rect.setAttribute('opacity', 0.9);
        
        return rect;
    }

    /**
     * Create rigid horizontal rectangle
     */
    createRigidHorizontalRectangle(x, y, width, height, color) {
        const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        
        // Horizontal rectangle with straight lines
        const margin = Math.min(width, height) * 0.1;
        const rectHeight = height * 0.6; // Shorter height for horizontal look
        const centerY = y + (height - rectHeight) / 2;
        
        rect.setAttribute('x', x + margin);
        rect.setAttribute('y', centerY);
        rect.setAttribute('width', width - 2 * margin);
        rect.setAttribute('height', rectHeight);
        rect.setAttribute('fill', color);
        rect.setAttribute('opacity', 0.9);
        
        return rect;
    }

    /**
     * Create triangle shape (legacy - keeping for compatibility)
     */
    createTriangle(x, y, width, height, color, variation) {
        const triangle = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
        const points = this.calculateTrianglePoints(x, y, width, height, variation);
        
        triangle.setAttribute('points', points);
        triangle.setAttribute('fill', color);
        triangle.setAttribute('opacity', 0.8 + (variation % 2) * 0.2);
        
        return triangle;
    }

    /**
     * Create rectangle shape
     */
    createRectangle(x, y, width, height, color, variation) {
        const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        
        // Add variation to rectangle
        const variationWidth = width * (0.8 + (variation % 3) * 0.1);
        const variationHeight = height * (0.8 + (variation % 2) * 0.1);
        const centerX = x + (width - variationWidth) / 2;
        const centerY = y + (height - variationHeight) / 2;
        
        rect.setAttribute('x', centerX);
        rect.setAttribute('y', centerY);
        rect.setAttribute('width', variationWidth);
        rect.setAttribute('height', variationHeight);
        rect.setAttribute('fill', color);
        rect.setAttribute('opacity', 0.8 + (variation % 2) * 0.2);
        
        // Add rotation variation
        if (variation % 4 === 0) {
            rect.setAttribute('transform', `rotate(45 ${centerX + variationWidth/2} ${centerY + variationHeight/2})`);
        }
        
        return rect;
    }

    /**
     * Create horizontal rectangle shape (common in real flags)
     */
    createHorizontalRectangle(x, y, width, height, color, variation) {
        const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        
        // Horizontal rectangles are wider than they are tall
        const horizontalWidth = width * 1.5; // Make it wider
        const horizontalHeight = height * 0.6; // Make it shorter
        const centerX = x + (width - horizontalWidth) / 2;
        const centerY = y + (height - horizontalHeight) / 2;
        
        // Add variation to horizontal rectangle
        const variationWidth = horizontalWidth * (0.8 + (variation % 3) * 0.1);
        const variationHeight = horizontalHeight * (0.8 + (variation % 2) * 0.1);
        const finalCenterX = centerX + (horizontalWidth - variationWidth) / 2;
        const finalCenterY = centerY + (horizontalHeight - variationHeight) / 2;
        
        rect.setAttribute('x', finalCenterX);
        rect.setAttribute('y', finalCenterY);
        rect.setAttribute('width', variationWidth);
        rect.setAttribute('height', variationHeight);
        rect.setAttribute('fill', color);
        rect.setAttribute('opacity', 0.8 + (variation % 2) * 0.2);
        
        // Add rotation variation for horizontal rectangles
        if (variation % 3 === 0) {
            rect.setAttribute('transform', `rotate(15 ${finalCenterX + variationWidth/2} ${finalCenterY + variationHeight/2})`);
        } else if (variation % 3 === 1) {
            rect.setAttribute('transform', `rotate(-15 ${finalCenterX + variationWidth/2} ${finalCenterY + variationHeight/2})`);
        }
        
        return rect;
    }

    /**
     * Calculate triangle points based on variation
     */
    calculateTrianglePoints(x, y, width, height, variation) {
        const centerX = x + width / 2;
        const centerY = y + height / 2;
        const size = Math.min(width, height) / 2;
        
        switch (variation % 4) {
            case 0: // Point up
                return `${centerX},${y} ${x},${y + height} ${x + width},${y + height}`;
            case 1: // Point down
                return `${centerX},${y + height} ${x},${y} ${x + width},${y}`;
            case 2: // Point left
                return `${x},${centerY} ${x + width},${y} ${x + width},${y + height}`;
            case 3: // Point right
                return `${x + width},${centerY} ${x},${y} ${x},${y + height}`;
        }
    }

    /**
     * Hash string to number for consistent randomization
     */
    hashString(str) {
        let hash = 0;
        for (let i = 0; i < str.length; i++) {
            const char = str.charCodeAt(i);
            hash = ((hash << 5) - hash) + char;
            hash = hash & hash; // Convert to 32-bit integer
        }
        return Math.abs(hash);
    }

    /**
     * Generate flags for all dynasties
     */
    generateAllFlags(dynasties) {
        return dynasties.map(dynasty => 
            this.generateFlag(dynasty.id, dynasty.name)
        );
    }

    /**
     * Create flag legend
     */
    createFlagLegend(flags) {
        const legend = document.createElement('div');
        legend.className = 'dynasty-flag-legend';
        legend.innerHTML = '<h4>Dynasty Flags</h4>';
        
        flags.forEach(flag => {
            const item = document.createElement('div');
            item.className = 'flag-legend-item';
            item.innerHTML = `
                <div class="flag-preview">${flag.svg}</div>
                <span class="flag-name">${flag.name}</span>
                <span class="flag-info">${flag.slices} slices, ${flag.shape}</span>
            `;
            legend.appendChild(item);
        });
        
        return legend;
    }

    /**
     * Create a flag from saved parameters using the existing flag generation logic
     */
    createFlagFromSavedParameters(params) {
        const { slices, orientation, shapeSequence, colorScheme, symbol, variation, isCzechStyle } = params;
        
        // Create SVG element
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('width', '100');
        svg.setAttribute('height', '60');
        svg.setAttribute('viewBox', '0 0 100 60');
        svg.style.border = '1px solid #ddd';
        svg.style.borderRadius = '4px';
        
        // Create flag slices based on saved parameters
        const sliceWidth = 100 / slices;
        const sliceHeight = 60;
        
        for (let i = 0; i < slices; i++) {
            const x = i * sliceWidth;
            const y = 0;
            const width = sliceWidth;
            const height = sliceHeight;
            
            // Get shape and color from saved parameters
            const shape = shapeSequence[i] || 'rectangle';
            const color = colorScheme[i] || '#FF6B6B';
            
            // Create the slice
            const slice = this.createFlagSlice(x, y, width, height, shape, color, variation);
            svg.appendChild(slice);
        }
        
        // Add symbol if present
        if (symbol && symbol !== 'None') {
            const symbolElement = this.createSymbolOverlay(symbol, 20, variation, 0);
            svg.appendChild(symbolElement);
        }
        
        return svg;
    }

    /**
     * Create a flag from saved parameters
     */
    createFlagFromParameters(flagParams) {
        const {
            slices,
            orientation,
            shape_sequence,
            color_scheme,
            symbol,
            variation,
            is_czech_style,
            seed
        } = flagParams;

        // Create the flag using the saved parameters
        // We need to create a custom flag generation that uses the saved parameters
        const flag = this.createFlagFromSavedParameters({
            slices: slices,
            orientation: orientation,
            shapeSequence: shape_sequence,
            colorScheme: color_scheme,
            symbol: symbol,
            variation: variation,
            isCzechStyle: is_czech_style
        });

        return {
            svg: flag,
            name: `Dynasty Flag (ID: ${seed})`,
            slices: slices,
            shape: is_czech_style ? 'Czech-style' : 'Standard',
            orientation: orientation,
            colors: color_scheme,
            symbol: symbol || 'None',
            variation: variation
        };
    }
}

// CSS for flag styling
const flagStyles = `
.dynasty-flag-legend {
    position: absolute;
    top: 10px;
    right: 10px;
    background: white;
    padding: 15px;
    border-radius: 8px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    max-height: 400px;
    overflow-y: auto;
    z-index: 1000;
}

.flag-legend-item {
    display: flex;
    align-items: center;
    margin: 8px 0;
    padding: 5px;
    border-radius: 4px;
    transition: background-color 0.2s;
}

.flag-legend-item:hover {
    background-color: #f0f0f0;
}

.flag-preview {
    width: 30px;
    height: 30px;
    margin-right: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
}

.flag-preview svg {
    max-width: 100%;
    max-height: 100%;
}

.flag-name {
    font-weight: bold;
    margin-right: 10px;
    min-width: 120px;
}

.flag-info {
    font-size: 0.8em;
    color: #666;
    font-style: italic;
}

.dynasty-flag-marker {
    width: 40px;
    height: 40px;
    border-radius: 50%;
    border: 2px solid white;
    box-shadow: 0 2px 6px rgba(0,0,0,0.3);
    display: flex;
    align-items: center;
    justify-content: center;
    background: white;
}

.dynasty-flag-marker svg {
    width: 32px;
    height: 32px;
}
`;

// Add styles to document
if (typeof document !== 'undefined') {
    const styleSheet = document.createElement('style');
    styleSheet.textContent = flagStyles;
    document.head.appendChild(styleSheet);
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = DynastyFlagGenerator;
}

// Make available globally for browser use
if (typeof window !== 'undefined') {
    window.DynastyFlagGenerator = DynastyFlagGenerator;
}
