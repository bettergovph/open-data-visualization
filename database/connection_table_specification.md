# Connection Table Specification for Political Dynasty Relationships

## Database Schema Requirements

### 1. Main Relationships Table
```sql
CREATE TABLE relationships (
    id SERIAL PRIMARY KEY,
    person1_id INTEGER REFERENCES political_dynasties(id),
    person2_id INTEGER REFERENCES political_dynasties(id),
    relationship_type_id INTEGER REFERENCES connection_types(id),
    relationship_description TEXT,
    source_url VARCHAR(500),
    confidence_level INTEGER CHECK (confidence_level >= 1 AND confidence_level <= 10),
    verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100) DEFAULT 'LLM_Analysis',
    notes TEXT
);
```

### 2. Connection Types Table (Extended)
```sql
CREATE TABLE connection_types (
    id SERIAL PRIMARY KEY,
    code INTEGER UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    category VARCHAR(50), -- 'family', 'political', 'business'
    bidirectional BOOLEAN DEFAULT TRUE,
    hierarchy_level INTEGER -- for ordering relationships
);
```

### 3. Required Connection Types
```sql
INSERT INTO connection_types (code, name, description, category, bidirectional, hierarchy_level) VALUES
-- Family Relationships
(1, 'Father', 'Biological or adoptive father', 'family', TRUE, 1),
(2, 'Mother', 'Biological or adoptive mother', 'family', TRUE, 1),
(3, 'Son', 'Biological or adoptive son', 'family', TRUE, 2),
(4, 'Daughter', 'Biological or adoptive daughter', 'family', TRUE, 2),
(5, 'Husband', 'Spouse (male)', 'family', TRUE, 1),
(6, 'Wife', 'Spouse (female)', 'family', TRUE, 1),
(7, 'Brother', 'Male sibling', 'family', TRUE, 2),
(8, 'Sister', 'Female sibling', 'family', TRUE, 2),
(9, 'Uncle', 'Father or mother''s brother', 'family', TRUE, 3),
(10, 'Aunt', 'Father or mother''s sister', 'family', TRUE, 3),
(11, 'Nephew', 'Brother or sister''s son', 'family', TRUE, 3),
(12, 'Niece', 'Brother or sister''s daughter', 'family', TRUE, 3),
(13, 'Cousin', 'Child of uncle or aunt', 'family', TRUE, 3),
(14, 'Grandfather', 'Father or mother''s father', 'family', TRUE, 4),
(15, 'Grandmother', 'Father or mother''s mother', 'family', TRUE, 4),
(16, 'Grandson', 'Son or daughter''s son', 'family', TRUE, 4),
(17, 'Granddaughter', 'Son or daughter''s daughter', 'family', TRUE, 4),
(18, 'Father-in-law', 'Spouse''s father', 'family', TRUE, 2),
(19, 'Mother-in-law', 'Spouse''s mother', 'family', TRUE, 2),
(20, 'Son-in-law', 'Daughter''s husband', 'family', TRUE, 2),
(21, 'Daughter-in-law', 'Son''s wife', 'family', TRUE, 2),

-- Political Relationships
(22, 'Political Ally', 'Political supporter or ally', 'political', TRUE, 2),
(23, 'Political Rival', 'Political opponent', 'political', TRUE, 2),
(24, 'Successor', 'Political successor', 'political', FALSE, 2),
(25, 'Predecessor', 'Political predecessor', 'political', FALSE, 2),
(26, 'Mentor', 'Political mentor', 'political', FALSE, 2),
(27, 'Protege', 'Political protege', 'political', FALSE, 2),

-- Business Relationships
(28, 'Business Partner', 'Business associate', 'business', TRUE, 2),
(29, 'Business Rival', 'Business competitor', 'business', TRUE, 2),
(30, 'Investor', 'Financial investor', 'business', FALSE, 2),
(31, 'Client', 'Business client', 'business', FALSE, 2);
```

### 4. Indexes for Performance
```sql
-- Primary indexes
CREATE INDEX idx_relationships_person1 ON relationships(person1_id);
CREATE INDEX idx_relationships_person2 ON relationships(person2_id);
CREATE INDEX idx_relationships_type ON relationships(relationship_type_id);
CREATE INDEX idx_relationships_confidence ON relationships(confidence_level);

-- Composite indexes
CREATE INDEX idx_relationships_persons ON relationships(person1_id, person2_id);
CREATE INDEX idx_relationships_verified ON relationships(verified, confidence_level);

-- Full text search
CREATE INDEX idx_relationships_description_fts ON relationships USING gin(to_tsvector('english', relationship_description));
```

### 5. Data Validation Rules
```sql
-- Ensure no self-relationships
ALTER TABLE relationships ADD CONSTRAINT no_self_relationship 
    CHECK (person1_id != person2_id);

-- Ensure confidence level is valid
ALTER TABLE relationships ADD CONSTRAINT valid_confidence 
    CHECK (confidence_level >= 1 AND confidence_level <= 10);

-- Ensure at least one person exists
ALTER TABLE relationships ADD CONSTRAINT person1_exists 
    FOREIGN KEY (person1_id) REFERENCES political_dynasties(id);
ALTER TABLE relationships ADD CONSTRAINT person2_exists 
    FOREIGN KEY (person2_id) REFERENCES political_dynasties(id);
```

### 6. Views for Analysis
```sql
-- View for family relationships
CREATE VIEW family_relationships AS
SELECT 
    r.id,
    p1.first_name || ' ' || p1.last_name as person1_name,
    p2.first_name || ' ' || p2.last_name as person2_name,
    ct.name as relationship_type,
    r.relationship_description,
    r.confidence_level,
    r.source_url,
    r.verified
FROM relationships r
JOIN political_dynasties p1 ON r.person1_id = p1.id
JOIN political_dynasties p2 ON r.person2_id = p2.id
JOIN connection_types ct ON r.relationship_type_id = ct.id
WHERE ct.category = 'family';

-- View for cross-dynasty relationships
CREATE VIEW cross_dynasty_relationships AS
SELECT 
    r.id,
    p1.first_name || ' ' || p1.last_name as person1_name,
    p1.last_name as dynasty1,
    p2.first_name || ' ' || p2.last_name as person2_name,
    p2.last_name as dynasty2,
    ct.name as relationship_type,
    r.relationship_description,
    r.confidence_level
FROM relationships r
JOIN political_dynasties p1 ON r.person1_id = p1.id
JOIN political_dynasties p2 ON r.person2_id = p2.id
JOIN connection_types ct ON r.relationship_type_id = ct.id
WHERE p1.last_name != p2.last_name;
```

### 7. API Endpoints Needed
```python
# GET /api/relationships/person/{person_id}
# GET /api/relationships/dynasty/{dynasty_name}
# GET /api/relationships/cross-dynasty
# POST /api/relationships (for importing LLM results)
# PUT /api/relationships/{id}/verify
# DELETE /api/relationships/{id}
```

### 8. CSV Import Format
The LLM should return CSV with these exact columns:
```csv
person1_name,person2_name,relationship_type,relationship_description,dynasty1,dynasty2,source_url,confidence_level
```

### 9. Data Processing Pipeline
1. **Import CSV** from LLM analysis
2. **Match names** to existing political_dynasties records
3. **Validate relationships** using confidence levels
4. **Insert into relationships table** with proper foreign keys
5. **Update verification status** based on source quality
6. **Generate reports** on relationship patterns

### 10. Quality Assurance
- **Duplicate detection**: Prevent duplicate relationships
- **Confidence filtering**: Only import relationships with confidence >= 7
- **Source verification**: Validate source URLs
- **Manual review**: Flag relationships for manual verification
- **Audit trail**: Track all changes and imports
