/**
 * Test script to verify that consecutive identical shapes are avoided
 */

// Load the flag generator (simplified version for testing)
class DynastyFlagGenerator {
    constructor() {
        this.shapes = ['circle', 'triangle', 'rectangle', 'horizontal-rectangle'];
        this.maxSlices = 10;
        this.maxVariations = 10;
    }

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

    createSeededRNG(seed) {
        let currentSeed = seed;
        return function() {
            // Linear congruential generator
            currentSeed = (currentSeed * 1664525 + 1013904223) % Math.pow(2, 32);
            return currentSeed / Math.pow(2, 32);
        };
    }

    hashString(str) {
        let hash = 0;
        for (let i = 0; i < str.length; i++) {
            const char = str.charCodeAt(i);
            hash = ((hash << 5) - hash) + char;
            hash = hash & hash; // Convert to 32-bit integer
        }
        return Math.abs(hash);
    }

    generateFlag(dynastyId, dynastyName) {
        const seed = this.hashString(dynastyName + dynastyId);
        
        // Create seeded random number generator
        const rng = this.createSeededRNG(seed);
        
        // Generate random number of slices (1-10)
        const numSlices = Math.floor(rng() * this.maxSlices) + 1;
        
        // Generate shape sequence avoiding consecutive identical shapes
        const shapeSequence = this.generateShapeSequence(numSlices, seed);
        
        return {
            id: dynastyId,
            name: dynastyName,
            slices: numSlices,
            shapeSequence: shapeSequence
        };
    }
}

// Test the consecutive shape avoidance
function testConsecutiveShapes() {
    const generator = new DynastyFlagGenerator();
    const testDynasties = [
        'Aquino Dynasty', 'Marcos Dynasty', 'Duterte Dynasty', 'Estrada Dynasty',
        'Roxas Dynasty', 'Villar Dynasty', 'Cayetano Dynasty', 'Binay Dynasty',
        'Lacson Dynasty', 'Poe Dynasty', 'Garcia Dynasty', 'Magsaysay Dynasty',
        'Quirino Dynasty', 'Osmeña Dynasty', 'Laurel Dynasty', 'Ramos Dynasty'
    ];
    
    let totalConsecutive = 0;
    let totalFlags = 0;
    
    console.log('🧪 Testing consecutive shape avoidance...\n');
    
    testDynasties.forEach((name, index) => {
        const flag = generator.generateFlag(index + 1, name);
        const sequence = flag.shapeSequence;
        
        // Check for consecutive identical shapes
        let consecutiveCount = 0;
        for (let i = 1; i < sequence.length; i++) {
            if (sequence[i] === sequence[i-1]) {
                consecutiveCount++;
            }
        }
        
        totalConsecutive += consecutiveCount;
        totalFlags++;
        
        console.log(`🏴 ${flag.name}:`);
        console.log(`   Slices: ${flag.slices}`);
        console.log(`   Sequence: ${sequence.join(' → ')}`);
        console.log(`   Consecutive: ${consecutiveCount}`);
        console.log('');
    });
    
    console.log('📊 Summary:');
    console.log(`   Total Flags: ${totalFlags}`);
    console.log(`   Total Consecutive Shapes: ${totalConsecutive}`);
    console.log(`   Success Rate: ${((totalFlags - totalConsecutive) / totalFlags * 100).toFixed(1)}%`);
    
    if (totalConsecutive === 0) {
        console.log('✅ SUCCESS: No consecutive identical shapes found!');
    } else {
        console.log('❌ FAILURE: Some consecutive identical shapes were found.');
    }
    
    return totalConsecutive === 0;
}

// Run the test
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { testConsecutiveShapes, DynastyFlagGenerator };
} else {
    // Run in browser
    testConsecutiveShapes();
}
